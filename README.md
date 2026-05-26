# ra-pm

LLM-native project + strategy management as a Claude Code MCP server.

Works across all your projects simultaneously. One install, CWD-aware context per session.

## What it does

- **Session briefing** — injected automatically before your first message. Shows the right context for where you are: tight single-project view when in a registered project, cross-project overview otherwise.
- **Auto-indexing** — `ra_init(cwd)` reads your README, git log, and package.json. Claude infers project identity, description, area, and thesis. Creates a `.ra-project.yaml` marker in the root.
- **LLM inbox routing** — unclassified ideas get routed to the right project by Claude, matched against each project's strategic thesis.
- **Thesis + claims layer** — track the strategic statement for each project, register evidence-backed claims, surface evidence gaps.
- **Handoffs** — store session summaries so the next session knows where you left off.

## Install

```bash
git clone git@github.com:Adriansdls/ra-pm.git
cd ra-pm
bash install.sh
```

Requires: Python 3.10+, Claude Code CLI, `ANTHROPIC_API_KEY` in env.

Manual steps if you prefer:
```bash
pip install -r requirements.txt
claude mcp add ra-pm python3 /path/to/ra-pm/server.py
# Add UserPromptSubmit hook pointing to hook.py in Claude Code settings
```

## Quickstart

```
# In any Claude Code session:
mcp__ra-pm__ra_boot          # session briefing
mcp__ra-pm__ra_init          # index current project (new machine / new project)
mcp__ra-pm__ra_projects      # list all tracked projects
mcp__ra-pm__ra_prioritize    # what to work on across all projects
```

## Tools

| Tool | What it does |
|------|-------------|
| `ra_boot()` | Session briefing — all projects, focus, latest handoffs, recommendation |
| `ra_init(cwd, name?)` | LLM-powered project indexing — infers identity from README/git/package.json |
| `ra_migrate()` | Create `.ra-project.yaml` markers for all projects with known `workspace_path` |
| `ra_projects()` | List all tracked projects |
| `ra_add_project(id, name, ...)` | Register a project manually |
| `ra_capture(title, area, why, project?)` | Capture an idea or issue — `why` required |
| `ra_focus(project, issue_id?)` | Set focus, load project context + last session handoff |
| `ra_issues(project, status?)` | List open (or filtered) issues |
| `ra_advance(project, id, status, what_happened)` | Move issue forward with mandatory reasoning |
| `ra_handoff(project, summary)` | Store session summary — call at end of work |
| `ra_brief(project)` | Strategic brief: thesis + claims + evidence gaps + next action |
| `ra_set_thesis(project, statement)` | Set/update project thesis |
| `ra_claim(project, claim, evidence_ref, confidence)` | Register evidence-backed claim |
| `ra_prioritize()` | Cross-project ranking: p0 urgency → in-progress momentum → p1 |
| `ra_calibrate(project)` | Strategic calibration questions |
| `ra_inbox()` | LLM routes unclassified inbox ideas to the right projects |
| `ra_stale()` | Show in-progress issues not touched in 4+ days |

## Data model

All data stored in `~/.ra/` — global, machine-local:

```
~/.ra/
├── projects.yaml         # registered projects
├── focus.yaml            # current focus
├── ideas.yaml            # inbox ideas
├── issues/<project>/     # per-project issue files (markdown + YAML frontmatter)
├── handoffs/<project>/   # session summaries
└── thesis/<project>.yaml # thesis + claims
```

Project marker (`.ra-project.yaml`) lives in each project root. Commit it to your repo — it's what enables CWD-aware briefing on any machine.

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
