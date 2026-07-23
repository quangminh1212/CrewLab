# CrewLab

Multi-agent crews for Hermes / local CLI: **each agent owns one task**, the crew **meets**, unblocks, and **ships the project together**.

## Quick start

```powershell
cd C:\Dev\CrewLab
python -m pip install -e ".[dev]"
crewlab smoke
crewlab init runs\demo --name demo
crewlab validate runs\demo\crew-spec.yaml
crewlab meeting runs\demo\crew-spec.yaml
crewlab task runs\demo\crew-spec.yaml --agent builder --status in_progress
crewlab status runs\demo\crew-spec.yaml
```

## Hermes attach

```powershell
powershell -File C:\Dev\CrewLab\scripts\install.ps1
# chat: /crewlab
# detach: scripts\uninstall.ps1
```

## Rules

1. One agent ↔ one `task_id`
2. Reassign only via meeting decision
3. Complete when all tasks `done|skipped` and no open blockers

## Layout

- `crewlab/` — CLI + validate + meeting + state
- `skills/crewlab/` — Hermes skill + role prompts
- `examples/ship-feature/` — sample crew-spec
- `schemas/crew-spec.schema.json` — JSON Schema
