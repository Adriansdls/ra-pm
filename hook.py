#!/usr/bin/env python3
"""
ra-pm session hook — runs at UserPromptSubmit, output becomes system-reminder in Claude's context.
CWD-aware: shows project-specific briefing when in a registered project dir, global view otherwise.
"""

import os
import sys
from datetime import date, datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit(0)

DATA = Path.home() / ".ra"


def _load(path, default=None):
    if path.exists():
        try:
            with open(path) as f:
                return yaml.safe_load(f) or (default if default is not None else {})
        except Exception:
            pass
    return default if default is not None else {}


def _open_issues(project_id):
    d = DATA / "issues" / project_id
    if not d.exists():
        return []
    issues = []
    for f in sorted(d.glob("*.md")):
        text = f.read_text()
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                meta = yaml.safe_load(parts[1]) or {}
                issues.append(meta)
    return [i for i in issues if i.get("status") not in ("done", "cancelled")]


def days_ago(date_str) -> int:
    if not date_str or str(date_str) == "never":
        return 999
    try:
        d = datetime.strptime(str(date_str)[:10], "%Y-%m-%d").date()
        return (date.today() - d).days
    except Exception:
        return 999


def momentum_bar(days: int) -> str:
    if days == 0:  return "██████████"
    if days <= 1:  return "████████░░"
    if days <= 3:  return "██████░░░░"
    if days <= 7:  return "████░░░░░░"
    if days <= 14: return "██░░░░░░░░"
    return               "░░░░░░░░░░"


def _load_records_hook(subdir_root: Path, project: str) -> list[dict]:
    d = subdir_root / project
    if not d.exists():
        return []
    records = []
    for f in sorted(d.glob("*.yaml")):
        r = _load(f)
        if r:
            records.append(r)
    return records


def _load_northstar(project_id: str) -> dict | None:
    path = DATA / "northstar" / f"{project_id}.yaml"
    d = _load(path)
    return d if d else None


def detect_project(cwd: Path) -> str | None:
    """Walk up from cwd to home looking for .ra-project.yaml. Returns project id or None."""
    home = Path.home()
    for p in [cwd] + list(cwd.parents):
        marker = p / ".ra-project.yaml"
        if marker.exists():
            try:
                data = yaml.safe_load(marker.read_text())
                return (data or {}).get("id")
            except Exception:
                return None
        if p == home:
            break
    return None


def is_indexable_dir(cwd: Path) -> bool:
    """True if the directory looks like a project but has no .ra-project.yaml marker."""
    signals = ["README.md", "README.rst", "ABOUT.md", "package.json", ".git", "pyproject.toml", "Cargo.toml"]
    return any((cwd / s).exists() for s in signals)


def project_briefing(project_id: str) -> list[str]:
    """Tight single-project briefing: issues, momentum, last handoff."""
    projects  = _load(DATA / "projects.yaml", default=[])
    focus     = _load(DATA / "focus.yaml", default={})
    p = next((x for x in projects if x.get("id") == project_id), None)
    if not p:
        return []

    open_i      = _open_issues(project_id)
    wip         = [i for i in open_i if i.get("status") == "in-progress"]
    p0          = [i for i in open_i if i.get("priority") == "p0"]
    p1          = [i for i in open_i if i.get("priority") == "p1"]
    days        = days_ago(p.get("last_touched", "never"))
    ns          = _load_northstar(project_id)
    bets        = _load_records_hook(DATA / "bets", project_id)
    experiments = _load_records_hook(DATA / "experiments", project_id)
    findings    = _load_records_hook(DATA / "findings", project_id)

    latest_handoff = None
    hdir = DATA / "handoffs" / project_id
    if hdir.exists():
        files = sorted(hdir.glob("*.md"), reverse=True)
        if files:
            latest_handoff = files[0].read_text()[:300].strip()

    out = []
    out.append(f"╔══ {p['name'].upper()}  {date.today().isoformat()} ══╗")
    out.append("")

    # Focus
    if focus.get("project") == project_id and focus.get("issue_title"):
        out.append(f"FOCUS  #{focus.get('issue_id', '?')} {focus['issue_title']}")
        out.append("")

    # North Star
    if ns:
        current_str = f"now: {ns['current']}  →  " if ns.get("current") is not None else ""
        out.append(f"NORTH STAR  {ns.get('metric', '')}")
        out.append(f"            {current_str}target: {ns.get('target', '?')} ({ns.get('timeframe', '')})")
        indicators = ns.get("leading_indicators") or []
        if indicators:
            out.append(f"            leading: {indicators[0]}")
        out.append("")

    # Top Bet
    active_bets = [b for b in bets if b.get("status", "active") == "active"]
    if active_bets:
        top_bet = max(active_bets, key=lambda b: b.get("confidence", 0))
        bet_exp_ids = {e.get("id") for e in experiments if e.get("bet_id") == top_bet.get("id")}
        running_for_bet = [e for e in experiments if e.get("bet_id") == top_bet.get("id") and e.get("status", "running") == "running"]
        bet_findings = [f for f in findings if f.get("experiment_id") in bet_exp_ids]
        last_f_days = min((days_ago(f.get("logged")) for f in bet_findings), default=999)
        finding_str = f"last finding {last_f_days}d ago" if last_f_days < 999 else "no findings yet"
        n = len(running_for_bet)
        exp_str = f"{n} experiment{'s' if n != 1 else ''} running"
        conf = top_bet.get("confidence", 0)
        stmt = (top_bet.get("statement") or "")[:70]
        out.append(f"TOP BET  #{top_bet.get('id')} [{conf:.0%}]  {stmt}")
        out.append(f"         {exp_str}  ·  {finding_str}")
        out.append("")

    # Learn Today
    learn = []
    running_all = [e for e in experiments if e.get("status", "running") == "running"]
    for e in running_all[:2]:
        hyp = (e.get("hypothesis") or "")[:60]
        started = days_ago(e.get("started"))
        learn.append(f"  → Exp #{e.get('id')}  \"{hyp}\"  running {started}d")
    for b in active_bets[:3]:
        if b.get("confidence", 0) < 0.5:
            b_exp_ids = {e.get("id") for e in experiments if e.get("bet_id") == b.get("id")}
            b_findings = [f for f in findings if f.get("experiment_id") in b_exp_ids]
            if not any(days_ago(f.get("logged")) < 14 for f in b_findings):
                ev = (b.get("evidence_needed") or "")[:60]
                learn.append(f"  → Bet #{b.get('id')}  evidence gap — {ev}")
    if learn:
        out.append("LEARN TODAY")
        out.extend(learn[:3])
        out.append("")

    # Urgent
    if p0:
        out.append("URGENT (p0)")
        for i in p0:
            out.append(f"  #{i.get('id')} {i.get('title')}")
        out.append("")

    # Issues summary
    bar = momentum_bar(days)
    stale_marker = "  STALE" if days > 7 else ""
    out.append(f"MOMENTUM  {bar}  {days}d ago{stale_marker}")
    out.append(f"  {len(open_i)} open  ·  {len(wip)} in-progress  ·  {len(p1)} p1")
    if wip:
        for i in wip[:3]:
            out.append(f"  → #{i.get('id')} {i.get('title')}")
    out.append("")

    # Last handoff
    if latest_handoff:
        preview = latest_handoff[:200].replace("\n", " ")
        out.append(f"LAST SESSION  {preview}")
        out.append("")

    # Recommendation
    if p0:
        rec = f"Tackle urgent: #{p0[0].get('id')} {p0[0].get('title')}"
    elif wip:
        rec = f"Resume: #{wip[0].get('id')} {wip[0].get('title')}"
    elif p1:
        rec = f"Start: #{p1[0].get('id')} {p1[0].get('title')}"
    elif open_i:
        rec = f"Pick up: #{open_i[0].get('id')} {open_i[0].get('title')}"
    elif running_all:
        rec = f"Advance experiment: #{running_all[0].get('id')} — log a finding via ra_finding()"
    else:
        rec = "No open issues — capture new work with ra_capture()"

    out.append(f"NEXT  {rec}")
    out.append("╚══════════════════════════════════════════╝")
    return out


def global_briefing(discovery_hint: str | None = None) -> list[str]:
    """Full cross-project briefing (original behavior)."""
    projects = _load(DATA / "projects.yaml", default=[])
    focus    = _load(DATA / "focus.yaml", default={})
    ideas    = _load(DATA / "ideas.yaml", default=[])
    inbox    = [i for i in ideas if i.get("project") == "inbox"]

    active = [p for p in projects if p.get("status") != "archived"]
    if not active:
        return []

    rows       = []
    urgent     = []
    stale_wip  = []
    total_open = 0

    for p in active:
        open_i = _open_issues(p["id"])
        total_open += len(open_i)
        wip  = [i for i in open_i if i.get("status") == "in-progress"]
        p0   = [i for i in open_i if i.get("priority") == "p0"]
        p1   = [i for i in open_i if i.get("priority") == "p1"]
        days = days_ago(p.get("last_touched", "never"))

        for i in wip:
            wip_days = days_ago(i.get("updated", p.get("last_touched", "never")))
            if wip_days >= 4:
                stale_wip.append({
                    "project": p["name"], "id": p["id"],
                    "issue": i.get("title", "?"), "days": wip_days,
                })

        for i in p0:
            urgent.append({"project": p["name"], "issue": i.get("title", "?")})

        rows.append({
            "id":    p["id"],
            "name":  p["name"],
            "bar":   momentum_bar(days),
            "days":  days,
            "open":  len(open_i),
            "wip":   len(wip),
            "p0":    len(p0),
            "p1":    len(p1),
            "stale": days > 7,
        })

    rows.sort(key=lambda x: (-x["p0"] * 100, -x["wip"] * 50, -x["p1"] * 20, x["days"]))

    out = []
    out.append(f"╔══ RA-PM BRIEFING  {date.today().isoformat()} ══╗")
    out.append("")

    if focus.get("project"):
        issue_part = ""
        if focus.get("issue_id") and focus.get("issue_title"):
            issue_part = f"  →  #{focus['issue_id']} {focus['issue_title']}"
        out.append(f"FOCUS  {focus['project']}{issue_part}")
        out.append("")

    if urgent:
        out.append("URGENT (p0)")
        for u in urgent:
            out.append(f"  [{u['project']}]  {u['issue']}")
        out.append("")

    out.append("MOMENTUM")
    for r in rows:
        wip_str  = f"  {r['wip']} wip"   if r["wip"]  else ""
        open_str = f"  {r['open']} open" if r["open"] else "  no issues"
        stale    = "  STALE"             if r["stale"] else ""
        out.append(f"  {r['bar']}  {r['name']}{wip_str}{open_str}{stale}")
    out.append("")

    if stale_wip:
        out.append("STALE IN-PROGRESS  (blocked or forgotten?)")
        for s in stale_wip:
            out.append(f"  [{s['project']}]  {s['issue']}  —  {s['days']}d since update")
        out.append("")

    if inbox:
        out.append(f"INBOX  {len(inbox)} unclassified idea(s) — call ra_inbox() to route")
        out.append("")

    # Recommendation
    if urgent:
        rec = f"Tackle urgent: [{urgent[0]['project']}] {urgent[0]['issue']}"
    elif rows and rows[0]["wip"]:
        rec = f"Resume momentum: {rows[0]['name']} ({rows[0]['wip']} in-progress)"
    elif stale_wip:
        rec = f"Unstick: [{stale_wip[0]['project']}] \"{stale_wip[0]['issue']}\" — {stale_wip[0]['days']}d stale"
    elif rows and rows[0]["open"]:
        rec = f"Start: {rows[0]['name']} ({rows[0]['open']} open issues)"
    else:
        rec = "All clear — capture new work with ra_capture()"

    out.append(f"NEXT  {rec}")
    out.append("╚═════════════════════════════════════════╝")

    if discovery_hint:
        out.append("")
        out.append(f"UNINDEXED PROJECT  {discovery_hint}")
        out.append("  Call ra_init(cwd=<path>) to register and get project-specific context.")

    return out


def main():
    if not DATA.exists():
        return

    cwd = Path(os.environ.get("CWD", os.getcwd())).resolve()
    project_id = detect_project(cwd)

    if project_id:
        lines = project_briefing(project_id)
    else:
        hint = str(cwd) if is_indexable_dir(cwd) else None
        lines = global_briefing(discovery_hint=hint)

    if lines:
        print("\n".join(lines))


def already_shown() -> bool:
    flag = Path(f"/tmp/ra-pm-shown-{os.getppid()}")
    if flag.exists():
        return True
    flag.touch()
    return False


if __name__ == "__main__":
    try:
        if not already_shown():
            main()
    except Exception:
        pass
