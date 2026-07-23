# Labs (subrepos)

| Subrepo | Path | Pin | Upstream |
|---------|------|-----|----------|
| **DeerFlow** | `labs/deer-flow` | **v2.0.0** | https://github.com/bytedance/deer-flow |

## DeerFlow

ByteDance Super Agent harness (multi-agent, sandbox, skills). Used by CrewLab as the heavy multi-agent runtime alongside the lightweight `crew-spec` meeting model.

```powershell
# clone / update after git clone CrewLab
cd C:\Dev\CrewLab
git submodule update --init --recursive labs/deer-flow

# verify pin
git -C labs/deer-flow describe --tags
# expect: v2.0.0
```

Upstream has no `2.20` / `v2.2.0` tag; official 2.x release tag is **`v2.0.0`**. Main tracks unreleased `2.1.0`.

See also: `skills/deerflow/SKILL.md`, local runtime often at `C:\Users\GHC\deer-flow` if already installed outside the submodule.
