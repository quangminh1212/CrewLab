# CrewLab (external module)

SoT: `C:\Dev\CrewLab`  
Skill: `/crewlab` (junction under Hermes `skills/crewlab`)

## Model

- **One agent = one task** — no agent may own two tasks.
- Crew **meets** (standup/sync/review) to unblock and re-assign only via decision.
- Ship **together** — project complete when all tasks done + no open blockers.

## CLI

```text
cd C:\Dev\CrewLab
python -m pip install -e .
crewlab init my-project
crewlab validate my-project/crew-spec.yaml
crewlab meeting my-project/crew-spec.yaml
crewlab task my-project/crew-spec.yaml --agent builder --status done --result "..."
crewlab status my-project/crew-spec.yaml
```

Attach: `scripts\install.ps1` or `crewlab attach`
