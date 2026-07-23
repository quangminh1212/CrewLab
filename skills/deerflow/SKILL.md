---
name: deerflow
description: >
  DeerFlow Super Agent harness (ByteDance) vendored as CrewLab subrepo at
  labs/deer-flow pin v2.0.0. Multi-agent research/code/create with sandbox,
  memory, skills. Use when user asks DeerFlow, deer-flow, super agent harness,
  or heavy multi-agent runtime beyond crew-spec meetings.
metadata:
  author: CrewLab
  version: "2.0.0"
  hermes:
    tags: [deerflow, multi-agent, harness, subagent]
    category: development
---

# DeerFlow (CrewLab subrepo)

## SoT in this project

| Item | Value |
|------|--------|
| Path | `C:\Dev\CrewLab\labs\deer-flow` |
| Git pin | **v2.0.0** (`7e7f0410`) |
| Upstream | https://github.com/bytedance/deer-flow |
| Package version | `2.0.0` (backend/frontend at tag) |

```powershell
cd C:\Dev\CrewLab
git submodule update --init labs/deer-flow
git -C labs/deer-flow describe --tags   # v2.0.0
```

## Relation to CrewLab

- **CrewLab** `crew-spec`: light contract — one agent one task, meetings, STATE.
- **DeerFlow**: full Super Agent runtime (subagents, sandbox, UI/gateway).

Use DeerFlow when the crew needs a long-horizon harness; keep crew-spec for role/DoD tracking.

## Typical local runtime (if already running outside submodule)

Many machines also run a working tree at `C:\Users\GHC\deer-flow` (may be newer than v2.0.0). Prefer the **submodule pin** for reproducible CrewLab work.

| Surface | URL / path |
|---------|------------|
| UI | http://localhost:2026 |
| Gateway health | http://localhost:8001/health |
| Config example | `labs/deer-flow/config.example.yaml` |

```powershell
cd C:\Dev\CrewLab\labs\deer-flow
# follow upstream README / Makefile for setup (Node + Python + docker/nginx as required)
```

## Do not

- Do not silently bump the submodule past v2.0.0 without an explicit CrewLab decision.
- Do not commit `.env` / secrets from DeerFlow into CrewLab.
