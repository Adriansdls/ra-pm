# ra-pm

LLM-native project + strategy management as a Claude Code MCP server.

Five-layer architecture for high-impact projects: North Star → Theory of Change → Bets → Experiments → Evidence Ledger.

Works across all your projects simultaneously. One install, CWD-aware context per session.

## What it does

- **Session briefing** — injected automatically before every message. Shows North Star, top bet, learn-today experiments, momentum, and last handoff. CWD-aware: tight single-project view in a registered dir, cross-project overview otherwise.
- **Auto-indexing** — `ra_init(cwd)` reads your README, git log, and package.json. Claude infers project identity, description, area, and thesis. Creates a `.ra-project.yaml` marker in the root.
- **Learning system** — explicit bets with confidence scores, hypothesis-driven experiments, immutable evidence ledger. Rigor enforced in code (Pydantic), not prompts.
- **Messy project entry** — `ra_scan(cwd)` reads all files + git + session history. `ra_extract(...)` saves all five layers atomically. Go from chaos to structure in one LLM pass.
- **Inbox routing** — unclassified ideas routed to the right project by Claude, matched against each project's thesis.
- **Handoffs** — session summaries so the next session knows where you left off.

## Install

```bash
git clone git@github.com:Adriansdls/ra-pm.git
cd ra-pm
bash install.sh
```

Requires: Python 3.10+, Claude Code CLI.

## Quickstart

```
# In any Claude Code session:
mcp__ra-pm__ra_boot          # session briefing across all projects
mcp__ra-pm__ra_init          # index current project (new machine / new project)
mcp__ra-pm__ra_scan          # read a messy project — returns signals for LLM to structure
mcp__ra-pm__ra_audit         # structural integrity check — what layers are missing?
```

## Tools (31 total)

### Work layer (issues + sessions)

| Tool | What it does |
|------|-------------|
| `ra_boot()` | Session briefing — all projects, focus, latest handoffs, recommendation |
| `ra_init(cwd, name?)` | LLM-powered project indexing — infers identity from README/git/package.json |
| `ra_migrate()` | Create `.ra-project.yaml` markers for all projects with known `workspace_path` |
| `ra_projects()` | List all tracked projects |
| `ra_add_project(id, name, ...)` | Register a project manually |
| `ra_capture(title, area, why, project?, bet_id?, experiment_id?)` | Capture an idea or issue |
| `ra_focus(project, issue_id?)` | Set focus, load project context + last session handoff |
| `ra_issues(project, status?)` | List open (or filtered) issues |
| `ra_advance(project, id, status, what_happened)` | Move issue forward with mandatory reasoning |
| `ra_handoff(project, summary)` | Store session summary — call at end of work |
| `ra_brief(project)` | All five layers: North Star, theory, top bets, running experiments, evidence gaps |
| `ra_set_thesis(project, statement)` | Set/update project thesis |
| `ra_claim(project, claim, evidence_ref, confidence)` | Register evidence-backed claim |
| `ra_prioritize()` | Cross-project ranking: p0 urgency → in-progress momentum → p1 |
| `ra_calibrate(project)` | Strategic calibration questions |
| `ra_inbox()` | LLM routes unclassified inbox ideas to the right projects |
| `ra_stale()` | Show in-progress issues not touched in 4+ days |

### Learning system (v2)

| Tool | What it does |
|------|-------------|
| `ra_northstar(project, metric, target, timeframe, why_this_metric, leading_indicators?)` | Set the one metric that captures impact |
| `ra_theory(project, inputs, activities, outputs, outcomes, impact, assumptions)` | Define causal chain — assumptions required |
| `ra_bet(project, statement, rationale, confidence, evidence_needed)` | Register a strategic bet (confidence 0.0–1.0) |
| `ra_bet_update(project, id, confidence_delta, evidence_ref, reasoning)` | Update bet confidence with evidence + reasoning |
| `ra_experiment(project, hypothesis, bet_id, method, expected_learning)` | Launch hypothesis-driven experiment |
| `ra_finding(project, experiment_id, result, implication, confidence_delta, source)` | Log evidence — auto-updates bet confidence |
| `ra_decide(project, decision, rationale, alternatives_rejected?, bets_affected?)` | Immutable decision log |
| `ra_synthesize(project, what_happened, what_learned, bets_affected?, experiments_advanced?)` | Deep session close — registers findings + bet updates |
| `ra_audit(project)` | Check for missing layers, stale experiments, bets without experiments, untested assumptions |
| `ra_scan(cwd)` | Read all files + git + session history → signals dict for LLM to structure |
| `ra_extract(cwd, north_star, theory_of_change, bets, experiments, decisions, issues)` | Save all five layers atomically — the chaos→structure operation |
| `ra_history(project)` | Session archaeology via agenth — extracts implicit bets and decisions from past transcripts |

## Data model

All data stored in `~/.ra/` — global, machine-local:

```
~/.ra/
├── projects.yaml
├── focus.yaml
├── ideas.yaml
├── issues/<project>/      # markdown + YAML frontmatter
├── handoffs/<project>/    # session summaries
├── thesis/<project>.yaml
├── northstar/<project>.yaml
├── theory/<project>.yaml
├── bets/<project>/        # 001-slug.yaml, 002-slug.yaml ...
├── experiments/<project>/
├── findings/<project>/
└── decisions/<project>/
```

Project marker (`.ra-project.yaml`) lives in each project root. Commit it to your repo — it enables CWD-aware briefing on any machine.

## Issue lifecycle

```
idea → planned → in-progress → done
                             → blocked
                             → cancelled
```

Priority: `p0` (now) · `p1` (soon) · `p2` (later) · `p3` (someday)

Area: `content` · `research` · `dev` · `ops` · `design` · `infra` · `strategy`

## New machine setup

```bash
# 1. Clone ra-pm and install
git clone git@github.com:Adriansdls/ra-pm.git && cd ra-pm && bash install.sh

# 2. For each existing project: re-index with local paths
mcp__ra-pm__ra_init(cwd="/local/path/to/project")

# 3. Or bulk-create markers if workspace_path is already set
mcp__ra-pm__ra_migrate()
```

Issue data (`~/.ra/`) syncs separately — use your preferred method (rsync, Dropbox, etc).

## Messy project entry

For a project with no structure yet:

```
1. ra_scan(cwd)            → returns signals: files, git_log, session_summaries
2. Claude reads signals    → infers North Star, bets, experiments, decisions
3. ra_extract(cwd, ...)    → saves all five layers atomically
4. ra_audit(project)       → check what's still missing
```

## Enforcement

| Rule | How |
|------|-----|
| Bet requires rationale + evidence_needed | Pydantic required fields |
| Experiment requires bet_id | Validated against existing bets |
| Finding requires implication | Pydantic required field |
| Confidence bounded 0.0–1.0 | `Field(ge=0.0, le=1.0)` |
| Decision is immutable | No update tool exists |
| Theory requires assumptions | Validated non-empty list |
