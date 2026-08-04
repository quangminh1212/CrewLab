# Sources — CrewLab equivalent GitHub projects

Machine-readable catalog: [`sources/catalog.yaml`](sources/catalog.yaml)  
CLI: `crewlab sources` · `crewlab features` · checked by `crewlab smoke`

| Upstream | License | Integration |
|----------|---------|-------------|
| [bytedance/deer-flow](https://github.com/bytedance/deer-flow) | MIT | **integrated** — `labs/deer-flow` submodule @ v2.0.0 + `/deerflow` |
| [crewAIInc/crewAI](https://github.com/crewAIInc/crewAI) | MIT | **integrated** — sequential/hierarchical, kickoff, plan, memory, expected_output |
| [OpenBMB/ChatDev](https://github.com/OpenBMB/ChatDev) | Apache-2.0 | **integrated** — `examples/chatdev-software/` roles |
| [FoundationAgents/MetaGPT](https://github.com/FoundationAgents/MetaGPT) | MIT | **integrated** — SOP example + shared message pool (`crewlab chat`) |
| [microsoft/autogen](https://github.com/microsoft/autogen) | CC-BY-4.0 | **integrated** — group chat + human-in-loop (`manual` backend) |
| [obra/superpowers](https://github.com/obra/superpowers) | MIT | **integrated** — skill host + multi-CLI subagent dispatch |
| [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) | MIT | **integrated** — skill junction + `backend: hermes` |

Native CrewLab model remains **one agent = one task + meetings**, not a re-host of CrewAI runtime.

## Feature parity

```powershell
crewlab features              # full matrix
crewlab features --source crewai
crewlab features --gaps       # partial items only
crewlab backends              # multi-CLI adapters
```

## Multi-CLI room

Heterogeneous agents (Grok / Hermes / Codex / Claude / OpenClaw / …) in one crew:

```powershell
crewlab validate examples\multi-cli-room
crewlab plan examples\multi-cli-room
crewlab run examples\multi-cli-room --dry-run
crewlab run examples\multi-cli-room --step   # one ready task via agent CLI
```
