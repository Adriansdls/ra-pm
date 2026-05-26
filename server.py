#!/usr/bin/env python3
"""
ra-pm — LLM-native project + strategy management MCP server
Adrian Sanchez de la Sierra

Data lives in ~/.ra/ — global across all projects.
"""

import json
import os
import subprocess
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import yaml
from mcp.server.fastmcp import FastMCP

from models import (
    Area, Claim, Focus, InboxIdea, Issue, IssueStatus, Priority,
    Project, ProjectStatus, RaProjectMarker, Thesis,
)

mcp = FastMCP("ra-pm")

DATA         = Path.home() / ".ra"
PROJECTS_FILE = DATA / "projects.yaml"
FOCUS_FILE    = DATA / "focus.yaml"
IDEAS_FILE    = DATA / "ideas.yaml"
ISSUES_DIR    = DATA / "issues"
HANDOFFS_DIR  = DATA / "handoffs"
THESIS_DIR    = DATA / "thesis"


# ── helpers ──────────────────────────────────────────────────────────────────

def _ensure():
    for d in [DATA, ISSUES_DIR, HANDOFFS_DIR, THESIS_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def _load(path: Path, default=None):
    if path.exists():
        with open(path) as f:
            return yaml.safe_load(f) or (default if default is not None else {})
    return default if default is not None else {}


def _save(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def _load_issues(project: str) -> list:
    d = ISSUES_DIR / project
    if not d.exists():
        return []
    issues = []
    for f in sorted(d.glob("*.md")):
        text = f.read_text()
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                meta = yaml.safe_load(parts[1]) or {}
                meta["_file"] = f.name
                meta["_notes"] = parts[2].strip()
                issues.append(meta)
    return issues


def _save_issue(project: str, issue: dict) -> str:
    d = ISSUES_DIR / project
    d.mkdir(parents=True, exist_ok=True)
    notes    = issue.pop("_notes", "")
    filename = issue.pop("_file", None)
    if not filename:
        slug     = issue["title"].lower()[:40].replace(" ", "-").replace("/", "-")
        filename = f"{issue['id']:03d}-{slug}.md"
    issue["updated"] = date.today().isoformat()
    clean   = {k: v for k, v in issue.items() if not k.startswith("_")}
    content = f"---\n{yaml.dump(clean, default_flow_style=False, allow_unicode=True, sort_keys=False)}---\n{notes}\n"
    (d / filename).write_text(content)
    return filename


def _touch(project_id: str):
    projects = _load(PROJECTS_FILE, default=[])
    for p in projects:
        if p["id"] == project_id:
            p["last_touched"] = date.today().isoformat()
    _save(PROJECTS_FILE, projects)


def _open_issues(project: str):
    return [i for i in _load_issues(project) if i.get("status") not in ("done", "cancelled")]


def _load_projects() -> list[dict]:
    return _load(PROJECTS_FILE, default=[])


def _register_project(project: Project):
    """Upsert a project into projects.yaml."""
    projects = _load_projects()
    data = project.model_dump(mode="json", exclude_none=True)
    # Convert date objects to iso strings
    for k, v in data.items():
        if hasattr(v, "isoformat"):
            data[k] = v.isoformat()
    existing = next((i for i, p in enumerate(projects) if p["id"] == project.id), None)
    if existing is not None:
        # Merge — don't overwrite fields the user already set unless we have better data
        for k, v in data.items():
            if v is not None:
                projects[existing][k] = v
    else:
        data.setdefault("created", date.today().isoformat())
        data.setdefault("last_touched", date.today().isoformat())
        projects.append(data)
        (ISSUES_DIR / project.id).mkdir(parents=True, exist_ok=True)
    _save(PROJECTS_FILE, projects)


def _load_thesis(project_id: str) -> Optional[dict]:
    path = THESIS_DIR / f"{project_id}.yaml"
    if path.exists():
        return _load(path, default={})
    return None


def _save_thesis(project_id: str, thesis: Thesis):
    data = thesis.model_dump(mode="json")
    _save(THESIS_DIR / f"{project_id}.yaml", data)


def _llm_call(prompt: str, max_tokens: int = 1024) -> str:
    """Call Claude via anthropic SDK. Returns raw text content."""
    import anthropic
    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


PRIORITY_RANK = {"p0": 0, "p1": 1, "p2": 2, "p3": 3}


# ── tools ─────────────────────────────────────────────────────────────────────

@mcp.tool()
def ra_boot() -> dict:
    """
    Session start briefing. Call this at the start of every session.
    Returns: all active projects with open issue counts, current focus, recent handoffs,
    inbox ideas count, and top priority recommendation across all projects.
    """
    _ensure()
    projects  = _load(PROJECTS_FILE, default=[])
    focus     = _load(FOCUS_FILE, default={})
    ideas     = _load(IDEAS_FILE, default=[])
    inbox     = [i for i in ideas if i.get("project") == "inbox"]

    summaries = []
    for p in projects:
        if p.get("status") == "archived":
            continue
        open_i  = _open_issues(p["id"])
        wip     = [i for i in open_i if i.get("status") == "in-progress"]
        p0      = [i for i in open_i if i.get("priority") == "p0"]

        latest_handoff = None
        hdir = HANDOFFS_DIR / p["id"]
        if hdir.exists():
            files = sorted(hdir.glob("*.md"), reverse=True)
            if files:
                latest_handoff = files[0].read_text()[:400].strip()

        score = len(p0) * 100 + len(wip) * 50
        summaries.append({
            "id":             p["id"],
            "name":           p["name"],
            "last_touched":   p.get("last_touched", "never"),
            "open":           len(open_i),
            "in_progress":    len(wip),
            "p0":             len(p0),
            "momentum_score": score,
            "latest_handoff": latest_handoff,
        })

    summaries.sort(key=lambda x: x["momentum_score"], reverse=True)

    recommendation = "No active work. Use ra_capture() to add ideas or ra_add_project() to register a project."
    top = next((s for s in summaries if s["in_progress"] > 0 or s["p0"] > 0), None)
    if focus.get("project"):
        recommendation = f"Resume focus: {focus['project']} — {focus.get('issue_title', 'no specific issue')}"
    elif top:
        recommendation = f"Highest momentum: {top['name']} ({top['in_progress']} in-progress, {top['p0']} urgent)"

    return {
        "date":           date.today().isoformat(),
        "focus":          focus,
        "projects":       summaries,
        "inbox_ideas":    len(inbox),
        "recommendation": recommendation,
    }


@mcp.tool()
def ra_projects() -> list:
    """List all tracked projects with open issue counts and last touched date."""
    _ensure()
    projects = _load(PROJECTS_FILE, default=[])
    result = []
    for p in projects:
        open_i = _open_issues(p["id"])
        result.append({
            **{k: v for k, v in p.items()},
            "open_issues":    len(open_i),
            "in_progress":    len([i for i in open_i if i.get("status") == "in-progress"]),
        })
    return result


@mcp.tool()
def ra_add_project(
    id: str,
    name: str,
    description: str = "",
    workspace_path: str = "",
    status: str = "active",
) -> dict:
    """
    Register a new project.
    id: short slug e.g. 'tostadito', 'raising-agents'
    workspace_path: absolute path to project directory
    """
    _ensure()
    projects = _load(PROJECTS_FILE, default=[])
    if any(p["id"] == id for p in projects):
        return {"error": f"Project '{id}' already exists. Use ra_projects() to list."}
    p = Project(
        id=id,
        name=name,
        description=description or None,
        workspace_path=workspace_path or None,
        status=ProjectStatus(status),
        created=date.today(),
        last_touched=date.today(),
    )
    _register_project(p)
    return {"added": p.model_dump(mode="json", exclude_none=True)}


@mcp.tool()
def ra_capture(
    title: str,
    area: str,
    why: str,
    project: str = "inbox",
    hypothesis: str = "",
    priority: str = "p2",
) -> dict:
    """
    Capture an idea or issue.
    project: project id or 'inbox' (default) if unclear which project
    area: content | research | dev | ops | design | infra | strategy
    why: strategic rationale — required. No idea without a why.
    hypothesis: testable prediction (encouraged)
    priority: p0 | p1 | p2 | p3
    """
    _ensure()
    if not why.strip():
        return {"error": "why is required — every idea needs a strategic rationale"}

    if project == "inbox":
        ideas = _load(IDEAS_FILE, default=[])
        idea = InboxIdea(
            title=title,
            area=area if area in [a.value for a in Area] else None,
            why=why,
            hypothesis=hypothesis or None,
            priority=Priority(priority),
            project="inbox",
            created=date.today().isoformat(),
        )
        ideas.append(idea.model_dump(mode="json", exclude_none=True))
        _save(IDEAS_FILE, ideas)
        return {"stored": "inbox", "title": title, "tip": "Use ra_focus(project) then re-capture to assign"}

    issues   = _load_issues(project)
    next_id  = max((i.get("id", 0) for i in issues), default=0) + 1
    issue = Issue(
        id=next_id,
        title=title,
        status=IssueStatus.idea,
        priority=Priority(priority),
        area=Area(area),
        why=why,
        hypothesis=hypothesis or None,
        created=date.today(),
        updated=date.today(),
    )
    issue_dict = issue.model_dump(mode="json", exclude_none=True)
    filename   = _save_issue(project, issue_dict)
    _touch(project)
    return {"stored": project, "id": next_id, "file": filename}


@mcp.tool()
def ra_focus(project: str, issue_id: int = 0) -> dict:
    """
    Set current focus to a project (and optionally a specific issue).
    issue_id=0 means let the system pick the best next issue.
    Returns: full project state + last session handoff + recommended next action.
    """
    _ensure()
    projects = _load(PROJECTS_FILE, default=[])
    p = next((x for x in projects if x["id"] == project), None)
    if not p:
        return {"error": f"Project '{project}' not found. Use ra_projects() to list."}

    open_i     = _open_issues(project)
    wip        = [i for i in open_i if i.get("status") == "in-progress"]
    p0         = [i for i in open_i if i.get("priority") == "p0"]
    p1         = [i for i in open_i if i.get("priority") == "p1"]

    target = None
    if issue_id:
        all_issues = _load_issues(project)
        target = next((i for i in all_issues if i.get("id") == issue_id), None)
    elif p0:
        target = p0[0]
    elif wip:
        target = wip[0]
    elif p1:
        target = p1[0]
    elif open_i:
        target = min(open_i, key=lambda x: PRIORITY_RANK.get(x.get("priority", "p3"), 3))

    focus = Focus(
        project=project,
        issue_id=target.get("id") if target else None,
        issue_title=target.get("title") if target else None,
        set_at=datetime.now().isoformat(),
    )
    _save(FOCUS_FILE, focus.model_dump(mode="json", exclude_none=True))
    _touch(project)

    latest_handoff = None
    hdir = HANDOFFS_DIR / project
    if hdir.exists():
        files = sorted(hdir.glob("*.md"), reverse=True)
        if files:
            latest_handoff = files[0].read_text().strip()

    return {
        "focused_on":    project,
        "project_name":  p.get("name"),
        "current_issue": target,
        "open_issues":   open_i,
        "last_session":  latest_handoff,
        "next_action":   f"Work on: {target['title']}" if target else "No open issues — use ra_capture()",
    }


@mcp.tool()
def ra_issues(project: str, status: str = "") -> list:
    """
    List issues for a project.
    status: filter by status (idea|planned|in-progress|blocked|done|cancelled) or empty for all open.
    """
    _ensure()
    issues = _load_issues(project)
    if status:
        return [i for i in issues if i.get("status") == status]
    return [i for i in issues if i.get("status") not in ("done", "cancelled")]


@mcp.tool()
def ra_advance(
    project: str,
    issue_id: int,
    new_status: str,
    what_happened: str,
    learned: str = "",
) -> dict:
    """
    Advance an issue with mandatory reasoning.
    new_status: planned | in-progress | blocked | done | cancelled
    what_happened: required — what was done or decided
    learned: optional but strongly encouraged when closing (done/cancelled)
    """
    _ensure()
    issues = _load_issues(project)
    issue  = next((i for i in issues if i.get("id") == issue_id), None)
    if not issue:
        return {"error": f"Issue #{issue_id} not found in project '{project}'"}

    old_status     = issue.get("status")
    issue["status"] = new_status

    log = f"\n## {date.today().isoformat()} — {old_status} → {new_status}\n{what_happened}"
    if learned:
        log += f"\n\n**Learned:** {learned}"
    issue["_notes"] = (issue.get("_notes", "") + log).strip()

    _save_issue(project, issue)
    _touch(project)

    return {
        "issue":      issue_id,
        "title":      issue["title"],
        "old_status": old_status,
        "new_status": new_status,
    }


@mcp.tool()
def ra_handoff(project: str, summary: str) -> dict:
    """
    Store session summary. Call at end of any significant work session.
    summary: what was done, what's next, open questions, blockers.
    This is what future-you (and future Claude) will read at session start.
    """
    _ensure()
    hdir = HANDOFFS_DIR / project
    hdir.mkdir(parents=True, exist_ok=True)
    ts       = datetime.now().strftime("%Y-%m-%d_%H%M")
    filename = hdir / f"{ts}.md"
    filename.write_text(f"# Handoff — {ts}\n\n{summary}\n")
    _touch(project)
    return {"stored": str(filename), "project": project}


@mcp.tool()
def ra_brief(project: str) -> dict:
    """
    Strategic brief for a project.
    Returns: thesis, claims + evidence, gaps, open questions, next highest-leverage action.
    Use at session start or when direction feels unclear.
    """
    _ensure()
    thesis = _load(THESIS_DIR / f"{project}.yaml", default={
        "statement":      "Not yet defined — use ra_set_thesis()",
        "claims":         [],
        "open_questions": [],
    })

    open_i = _open_issues(project)
    done_i = [i for i in _load_issues(project) if i.get("status") == "done"]
    claims = thesis.get("claims", [])
    gaps   = [c for c in claims if c.get("confidence") in ("low", None) or not c.get("evidence_ref")]

    p0 = [i for i in open_i if i.get("priority") == "p0"]
    p1 = [i for i in open_i if i.get("priority") == "p1"]

    next_action = "Define thesis with ra_set_thesis()"
    if thesis.get("statement") and thesis["statement"] != "Not yet defined — use ra_set_thesis()":
        if p0:
            next_action = f"URGENT #{p0[0]['id']}: {p0[0]['title']}"
        elif gaps:
            next_action = f"Strengthen claim: '{gaps[0].get('claim', '')}' — run experiment"
        elif p1:
            next_action = f"#{p1[0]['id']}: {p1[0]['title']}"
        elif open_i:
            next_action = f"#{open_i[0]['id']}: {open_i[0]['title']}"

    return {
        "project":               project,
        "thesis":                thesis.get("statement"),
        "claims":                claims,
        "evidence_gaps":         gaps,
        "open_questions":        thesis.get("open_questions", []),
        "open_issues":           len(open_i),
        "closed_issues":         len(done_i),
        "next_highest_leverage": next_action,
    }


@mcp.tool()
def ra_set_thesis(project: str, statement: str, open_questions: list = None) -> dict:
    """
    Set or update the thesis statement for a project.
    statement: one clear sentence — what this project proves, achieves, or is for.
    open_questions: list of strategic unknowns that could change direction.
    """
    _ensure()
    thesis_file = THESIS_DIR / f"{project}.yaml"
    existing    = _load(thesis_file, default={"claims": [], "open_questions": []})
    thesis = Thesis(
        statement=statement,
        open_questions=open_questions or existing.get("open_questions", []),
        claims=[Claim(**c) for c in existing.get("claims", []) if isinstance(c, dict)],
        updated=date.today(),
    )
    _save_thesis(project, thesis)
    _touch(project)
    return {"updated": project, "thesis": statement}


@mcp.tool()
def ra_claim(project: str, claim: str, evidence_ref: str, confidence: str) -> dict:
    """
    Register a thesis claim backed by evidence.
    claim: specific, testable statement (not vague)
    evidence_ref: path to EVIDENCE_PACK, experiment id, or concrete description
    confidence: low | medium | high
    """
    _ensure()
    thesis_file = THESIS_DIR / f"{project}.yaml"
    existing    = _load(thesis_file, default={"statement": "", "claims": [], "open_questions": []})
    claims_raw  = existing.get("claims", [])
    new_claim   = Claim(
        id=len(claims_raw) + 1,
        claim=claim,
        evidence_ref=evidence_ref,
        confidence=confidence,
        registered=date.today(),
    )
    claims_raw.append(new_claim.model_dump(mode="json"))
    existing["claims"] = claims_raw
    _save(thesis_file, existing)
    _touch(project)
    return {"registered": new_claim.model_dump(mode="json")}


@mcp.tool()
def ra_prioritize() -> dict:
    """
    Cross-project prioritization.
    Returns a ranked list of what to work on NOW across all active projects.
    Scoring: p0 issues (100pts), in-progress momentum (50pts), p1 issues (20pts).
    Use when deciding where to spend a session.
    """
    _ensure()
    projects = _load(PROJECTS_FILE, default=[])
    ranked   = []

    for p in projects:
        if p.get("status") == "archived":
            continue
        open_i = _open_issues(p["id"])
        wip    = [i for i in open_i if i.get("status") == "in-progress"]
        p0     = [i for i in open_i if i.get("priority") == "p0"]
        p1     = [i for i in open_i if i.get("priority") == "p1"]

        score   = len(p0) * 100 + len(wip) * 50 + len(p1) * 20
        reasons = []
        if p0:     reasons.append(f"{len(p0)} urgent (p0)")
        if wip:    reasons.append(f"{len(wip)} in-progress")
        if p1:     reasons.append(f"{len(p1)} high priority (p1)")
        if not open_i: reasons.append("no open issues")

        top = (p0 or wip or p1 or open_i or [None])[0]
        ranked.append({
            "project":      p["id"],
            "name":         p["name"],
            "score":        score,
            "reasons":      reasons,
            "last_touched": p.get("last_touched", "never"),
            "top_issue":    {"id": top.get("id"), "title": top.get("title"), "status": top.get("status")} if top else None,
        })

    ranked.sort(key=lambda x: x["score"], reverse=True)
    for i, r in enumerate(ranked):
        r["rank"] = i + 1

    return {
        "date":           date.today().isoformat(),
        "ranked":         ranked,
        "recommendation": f"Start with: {ranked[0]['name']}" if ranked else "No active projects",
    }


@mcp.tool()
def ra_calibrate(project: str) -> dict:
    """
    Strategic calibration for a project.
    Returns structured questions to re-anchor on strategy.
    Use: when direction feels unclear, after major new evidence, or monthly.
    """
    _ensure()
    thesis  = _load(THESIS_DIR / f"{project}.yaml", default={"statement": "undefined", "claims": [], "open_questions": []})
    open_i  = _open_issues(project)
    claims  = thesis.get("claims", [])
    weak    = [c for c in claims if c.get("confidence") == "low"]

    return {
        "project":         project,
        "current_thesis":  thesis.get("statement"),
        "questions": [
            f"Is the thesis still: '{thesis.get('statement')}'? If not, what changed?",
            "What's the #1 unknown that would force a pivot if answered differently?",
            "Which open issue, if shipped, would have the highest leverage on the thesis?",
            f"You have {len(open_i)} open issues. Which 3 matter most? Which can be killed?",
            "What are you saying yes to that is actually a distraction?",
            "What would you ship in 30 days if the project had to prove itself?",
            f"You have {len(weak)} low-confidence claim(s). What experiment would strengthen the weakest?",
        ],
        "weak_claims":    weak,
        "open_questions": thesis.get("open_questions", []),
        "open_issues":    open_i,
        "next_step":      "Answer via ra_advance(), ra_claim(), ra_set_thesis(), or ra_capture()",
    }


@mcp.tool()
def ra_inbox() -> dict:
    """
    List all unclassified ideas in the inbox. Uses LLM to suggest project routing for each idea,
    based on idea content + project theses. Returns ideas with routing suggestions and reasoning.
    Use when the session briefing reports inbox ideas, or when you want to triage.
    """
    _ensure()
    ideas    = _load(IDEAS_FILE, default=[])
    inbox    = [i for i in ideas if i.get("project") == "inbox"]
    projects = _load(PROJECTS_FILE, default=[])

    if not inbox:
        return {"inbox_count": 0, "ideas": [], "tip": "Inbox is clear."}

    # Build project context for LLM: id, name, thesis
    project_context = []
    for p in projects:
        if p.get("status") == "archived":
            continue
        thesis = _load_thesis(p["id"])
        project_context.append({
            "id":     p["id"],
            "name":   p["name"],
            "thesis": thesis.get("statement", "no thesis yet") if thesis else "no thesis yet",
        })

    ideas_payload = [
        {k: v for k, v in i.items() if k not in ("_file", "_notes")}
        for i in inbox
    ]

    prompt = f"""You are routing unclassified project ideas to the right project.

Projects and their strategic thesis:
{json.dumps(project_context, indent=2)}

Inbox ideas to route:
{json.dumps(ideas_payload, indent=2)}

For each idea, decide the best project based on the idea's content, area, and why — matched against the project theses.

Return a JSON array with the same ideas, each augmented with:
- "suggested_project": the project id that best fits (or "inbox" if genuinely ambiguous)
- "routing_reason": one sentence explaining why
- "suggested_priority": p0 | p1 | p2 | p3 based on the why and urgency signals

Respond with JSON array only. No prose."""

    try:
        raw = _llm_call(prompt, max_tokens=1024)
        # Strip possible markdown code fences
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        routed = json.loads(raw)
    except Exception as e:
        routed = [{**i, "routing_reason": f"LLM routing failed: {e}"} for i in ideas_payload]

    return {
        "inbox_count": len(inbox),
        "ideas":       routed,
        "tip":         "For each idea: call ra_capture(title, area, why, project=<suggested_project>) to move it out of inbox",
    }


@mcp.tool()
def ra_stale() -> dict:
    """
    Show all stale in-progress issues across ALL projects (not touched in 4+ days).
    Use to identify what's blocked or forgotten. Stale work is invisible until you look.
    """
    _ensure()
    projects = _load(PROJECTS_FILE, default=[])
    stale    = []
    today    = date.today()

    for p in projects:
        if p.get("status") == "archived":
            continue
        issues = _load_issues(p["id"])
        wip    = [i for i in issues if i.get("status") == "in-progress"]
        for i in wip:
            updated_str = str(i.get("updated", p.get("last_touched", "")))[:10]
            try:
                updated = datetime.strptime(updated_str, "%Y-%m-%d").date()
                days    = (today - updated).days
            except Exception:
                days = 0
            if days >= 4:
                stale.append({
                    "project":      p["id"],
                    "project_name": p["name"],
                    "issue_id":     i.get("id"),
                    "title":        i.get("title"),
                    "days_stale":   days,
                    "priority":     i.get("priority"),
                })

    stale.sort(key=lambda x: x["days_stale"], reverse=True)
    return {
        "stale_count": len(stale),
        "items":       stale,
        "tip":         "Use ra_advance() to update status or ra_handoff() to document why it's blocked",
    }


@mcp.tool()
def ra_init(cwd: str, name: str = "") -> dict:
    """
    Index a project directory. Uses LLM to infer project identity from README, git log, package.json.
    Creates .ra-project.yaml marker in the project root and registers the project in ~/.ra/.
    Call when opening an unindexed project directory for the first time.

    cwd: absolute path to the project directory (use the actual working directory)
    name: optional override for the project name (LLM will infer if not given)
    """
    _ensure()
    cwd_path = Path(cwd).expanduser().resolve()
    if not cwd_path.exists():
        return {"error": f"Directory not found: {cwd}"}

    # Check if already indexed
    marker_path = cwd_path / ".ra-project.yaml"
    if marker_path.exists():
        try:
            existing = yaml.safe_load(marker_path.read_text()) or {}
            return {
                "status":  "already_indexed",
                "project": existing.get("id"),
                "name":    existing.get("name"),
                "tip":     f"Project already registered as '{existing.get('id')}'. Use ra_focus('{existing.get('id')}') to load context.",
            }
        except Exception:
            pass

    # Gather signals
    signals: dict[str, str] = {}
    for candidate in ["README.md", "README.rst", "ABOUT.md", "CLAUDE.md"]:
        fp = cwd_path / candidate
        if fp.exists():
            signals["readme"] = fp.read_text()[:3000]
            signals["readme_file"] = candidate
            break
    if (cwd_path / "package.json").exists():
        try:
            signals["package_json"] = (cwd_path / "package.json").read_text()[:1000]
        except Exception:
            pass
    if (cwd_path / ".git").exists():
        try:
            result = subprocess.run(
                ["git", "-C", str(cwd_path), "log", "--oneline", "-10"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                signals["git_log"] = result.stdout.strip()
        except Exception:
            pass
    signals["directory_name"] = cwd_path.name

    if not signals:
        return {"error": f"No indexable signals found in {cwd}. Add a README.md or initialize git."}

    # LLM inference
    prompt = f"""You are indexing a software/content project directory for a personal PM system.

Raw signals from the directory:
{json.dumps(signals, indent=2)}

Infer the project's identity. Return JSON only (no prose, no markdown fences):
{{
  "id": "<slug, lowercase, hyphens, max 30 chars>",
  "name": "<human readable name, 2-5 words>",
  "description": "<1-2 sentences: what this project is and its primary goal>",
  "area": "<one of: content | research | dev | ops | design | infra | strategy>",
  "thesis_statement": "<one sentence: what would make this project successful — or null if unclear>",
  "open_questions": ["<calibration question 1>", "<calibration question 2>"]
}}"""

    try:
        raw = _llm_call(prompt, max_tokens=512)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        inferred = json.loads(raw)
    except Exception as e:
        return {"error": f"LLM inference failed: {e}. Signals gathered: {list(signals.keys())}"}

    # Name override
    if name.strip():
        inferred["name"] = name.strip()
        inferred["id"]   = name.strip().lower().replace(" ", "-")[:30]

    # Validate area
    valid_areas = [a.value for a in Area]
    if inferred.get("area") not in valid_areas:
        inferred["area"] = "dev"

    # Create .ra-project.yaml marker
    marker = RaProjectMarker(
        id=inferred["id"],
        name=inferred["name"],
        description=inferred.get("description"),
        area=inferred.get("area"),
    )
    marker_path.write_text(
        "# Generated by ra_init() — do not edit by hand\n"
        + yaml.dump(marker.model_dump(mode="json"), default_flow_style=False, allow_unicode=True)
    )

    # Register project
    project = Project(
        id=inferred["id"],
        name=inferred["name"],
        workspace_path=str(cwd_path),
        description=inferred.get("description"),
        area=inferred.get("area"),
    )
    _register_project(project)

    # Set thesis if inferred
    if inferred.get("thesis_statement"):
        thesis = Thesis(
            statement=inferred["thesis_statement"],
            open_questions=inferred.get("open_questions", []),
        )
        _save_thesis(project.id, thesis)

    # Build response
    qs = inferred.get("open_questions", [])
    result: dict = {
        "status":      "indexed",
        "project_id":  project.id,
        "name":        project.name,
        "description": project.description,
        "area":        project.area,
        "marker":      str(marker_path),
    }
    if qs:
        result["calibration_questions"] = qs
    if inferred.get("thesis_statement"):
        result["thesis_drafted"] = inferred["thesis_statement"]

    return result


@mcp.tool()
def ra_migrate() -> dict:
    """
    One-time migration: create .ra-project.yaml marker files for all existing registered projects
    that have a workspace_path set. Idempotent — safe to run multiple times.
    Skips projects without workspace_path or where the directory doesn't exist.
    """
    _ensure()
    projects = _load(PROJECTS_FILE, default=[])
    created  = []
    skipped  = []
    errors   = []

    for p in projects:
        pid  = p.get("id", "?")
        path = p.get("workspace_path", "")
        if not path:
            skipped.append({"id": pid, "reason": "no workspace_path"})
            continue

        wp = Path(path).expanduser().resolve()
        if not wp.exists():
            skipped.append({"id": pid, "reason": f"directory not found: {wp}"})
            continue

        marker_path = wp / ".ra-project.yaml"
        if marker_path.exists():
            skipped.append({"id": pid, "reason": "marker already exists"})
            continue

        try:
            marker = RaProjectMarker(
                id=p["id"],
                name=p.get("name", p["id"]),
                description=p.get("description"),
                area=p.get("area"),
            )
            marker_path.write_text(
                "# Generated by ra_migrate() — do not edit by hand\n"
                + yaml.dump(marker.model_dump(mode="json"), default_flow_style=False, allow_unicode=True)
            )
            created.append({"id": pid, "marker": str(marker_path)})
        except Exception as e:
            errors.append({"id": pid, "error": str(e)})

    return {
        "created": created,
        "skipped": skipped,
        "errors":  errors,
        "summary": f"{len(created)} markers created, {len(skipped)} skipped, {len(errors)} errors",
    }


if __name__ == "__main__":
    _ensure()
    mcp.run()
