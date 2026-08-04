---
name: crewlab
description: >
  Multi-agent crew for Hermes: each agent owns exactly one task, the crew meets
  (standup/sync/review), unblocks, and ships the project together. Activate with /crewlab.
  Use when user wants a team of agents, crew meeting, multi-role project delivery,
  or "mỗi agent một task / họp cùng nhau / hoàn thiện dự án".
compatibility: Requires terminal; optional Hermes delegate_task for live roles
metadata:
  author: CrewLab
  version: "0.2.0"
  hermes:
    tags: [multi-agent, crew, meeting, orchestration, project]
    category: development
    requires_toolsets: [terminal]
---

# CrewLab — multi-agent crew

You are running **CrewLab**: a crew of agents that **meet** and **ship one project**.

## Hard rules

1. **One agent = one task** — never assign two active tasks to the same agent.
2. **No silent task stealing** — reassignment only via meeting decision + update `crew-spec` / STATE.
3. **Meet before thrash** — if blocked >1 step, call a meeting round (CLI or structured log).
4. **Ship together** — project complete only when all tasks `done|skipped` and no open blockers.

## Roles (default crew)

| Agent id | Role | Single task |
|----------|------|-------------|
| `lead` | Crew Lead | `plan-and-coordinate` |
| `builder` | Builder | `implement-core` |
| `reviewer` | Reviewer | `review-and-test` |
| `integrator` | Integrator | `integrate-and-ship` |

Detailed prompts: `agents/*.md` next to this skill (SoT `C:\Dev\CrewLab\skills\crewlab\agents`).

## Workflow

```text
1. Clarify goal → crewlab init <dir> --name <crew>
2. Edit crew-spec.yaml (agents[] each has task_id; tasks[] match)
3. crewlab validate <spec>
4. Loop:
   a. Each agent works ONLY its task
   b. crewlab task <spec> --agent <id> --status in_progress|done|blocked --result "..."
   c. crewlab meeting <spec>   # sync, blockers, next actions
   d. crewlab status <spec>
5. Stop when complete=true (DoD + all tasks closed)
```

## CLI (Windows)

```powershell
cd C:\Dev\CrewLab
python -m pip install -e ".[dev]"
crewlab init C:\Dev\CrewLab\runs\my-crew --name my-crew
crewlab validate C:\Dev\CrewLab\runs\my-crew
crewlab assign  C:\Dev\CrewLab\runs\my-crew
crewlab plan    C:\Dev\CrewLab\runs\my-crew
crewlab backends
crewlab features --source crewai
crewlab run     C:\Dev\CrewLab\runs\my-crew --dry-run
crewlab run     C:\Dev\CrewLab\runs\my-crew --step   # dispatch one agent CLI
crewlab chat    C:\Dev\CrewLab\runs\my-crew "sync note" --agent lead
crewlab meeting C:\Dev\CrewLab\runs\my-crew --kind kickoff
crewlab task    C:\Dev\CrewLab\runs\my-crew --agent builder --status done --result "impl ok"
crewlab blocker add C:\Dev\CrewLab\runs\my-crew "waiting on API" --agent builder
crewlab blocker resolve C:\Dev\CrewLab\runs\my-crew b1
crewlab decision add C:\Dev\CrewLab\runs\my-crew "Ship v1 without feature X"
crewlab reassign C:\Dev\CrewLab\runs\my-crew --agent builder --task review-and-test
crewlab status  C:\Dev\CrewLab\runs\my-crew
crewlab smoke
```

## Multi-CLI agents

Set per agent in `crew-spec.yaml`:

```yaml
agents:
  - id: builder
    role: Builder
    task_id: implement
    backend: codex   # hermes|grok|codex|claude|openclaw|opencode|cursor|manual|shell
    # cli: 'optional override template with {prompt_file}'
```

`crewlab run` builds prompts, writes `runs/<task_id>/prompt.md`, invokes CLI when on PATH, else prompt-only (manual complete + `crewlab task … --status done`).


Attach to Hermes (junction only, no core patch):

```powershell
powershell -File C:\Dev\CrewLab\scripts\install.ps1
# or: crewlab attach
```

## When user says /crewlab or "tạo crew"

1. Confirm **project goal** in one sentence.
2. Propose **≥2 agents**, each with **exactly one** task_id.
3. Write `crew-spec.yaml` (validate must PASS).
4. Run kickoff meeting; then execute tasks in dependency order.
5. After each major step, meeting or status update.
6. Closeout meeting when DoD met; summarize decisions + ship path.

## Meeting phases

`open` → `status_reports` → `blockers` → `sync_decisions` → `next_actions` → `close`

Each status report covers **only** that agent's owned task.

## Relation to other labs

| Lab | Focus |
|-----|--------|
| **CrewLab** | Multi-agent roles, one task each, meetings, ship project |
| **DeerFlow** (subrepo `labs/deer-flow` @ **v2.0.0**) | Super Agent harness — subagents, sandbox, UI; skill `/deerflow` |
| **LoopLab** | Single loop contract / OPAV / triage cron |
| AgentLab `loop-crew` | Legacy CrewAI sample loop (maker/verifier) |

Prefer CrewLab when the user wants a **team**, not a single loop agent.  
Prefer DeerFlow subrepo when the team needs the full long-horizon harness (see `skills/deerflow/SKILL.md`).

Feature parity vs referenced repos: `crewlab features` (matrix in `crewlab/features.py`).
