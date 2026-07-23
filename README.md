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
- `skills/deerflow/` — DeerFlow subrepo skill (pin **v2.0.0**)
- `labs/deer-flow/` — **git submodule** [bytedance/deer-flow](https://github.com/bytedance/deer-flow) @ **v2.0.0**
- `examples/ship-feature/` — sample crew-spec
- `schemas/crew-spec.schema.json` — JSON Schema

## DeerFlow subrepo

```powershell
git submodule update --init --recursive labs/deer-flow
git -C labs/deer-flow describe --tags   # v2.0.0
```

Pin note: upstream has no `2.20` tag; official 2.x release is **v2.0.0**. See `labs/README.md`.
