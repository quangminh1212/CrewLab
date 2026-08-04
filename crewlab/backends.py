"""CLI backends for heterogeneous multi-agent crews.

Each agent may bind to a different runtime (Hermes, Grok, Codex, Claude Code,
OpenClaw, OpenCode, manual, or raw shell). CrewLab orchestrates; backends execute.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BackendSpec:
    id: str
    title: str
    # Shell template; placeholders: {prompt_file} {prompt} {cwd} {agent_id} {task_id} {goal} {result_file}
    command: str
    detect: tuple[str, ...] = ()  # PATH names to probe
    notes: str = ""
    supports_prompt_file: bool = True


# Built-in backends. command may be overridden per-agent via agents[].cli / backend_cmd.
BUILTIN_BACKENDS: dict[str, BackendSpec] = {
    "manual": BackendSpec(
        id="manual",
        title="Manual / human-in-the-loop",
        command="",
        notes="Writes prompt only; operator completes and marks task done.",
    ),
    "dry-run": BackendSpec(
        id="dry-run",
        title="Dry-run (no process)",
        command="",
        notes="Always no-op; used by tests and plan previews.",
    ),
    "shell": BackendSpec(
        id="shell",
        title="Raw shell command",
        command="{cli}",
        notes="Requires agents[].cli as full command template.",
    ),
    "hermes": BackendSpec(
        id="hermes",
        title="Hermes Agent CLI",
        command='hermes chat -q "$(Get-Content -Raw \'{prompt_file}\')"',
        detect=("hermes",),
        notes="Uses Hermes CLI if on PATH; else treat as manual with prompt artifact.",
    ),
    "grok": BackendSpec(
        id="grok",
        title="Grok / Grok CLI",
        command='grok -p "$(Get-Content -Raw \'{prompt_file}\')"',
        detect=("grok",),
        notes="Grok Build TUI CLI when available.",
    ),
    "codex": BackendSpec(
        id="codex",
        title="OpenAI Codex CLI",
        command='codex exec -- "$(Get-Content -Raw \'{prompt_file}\')"',
        detect=("codex",),
        notes="OpenAI Codex coding agent CLI.",
    ),
    "claude": BackendSpec(
        id="claude",
        title="Claude Code CLI",
        command='claude -p "$(Get-Content -Raw \'{prompt_file}\')"',
        detect=("claude",),
        notes="Anthropic Claude Code.",
    ),
    "openclaw": BackendSpec(
        id="openclaw",
        title="OpenClaw CLI",
        command='openclaw run --prompt-file "{prompt_file}"',
        detect=("openclaw",),
        notes="OpenClaw department bridge / local agent host.",
    ),
    "opencode": BackendSpec(
        id="opencode",
        title="OpenCode CLI",
        command='opencode run "$(Get-Content -Raw \'{prompt_file}\')"',
        detect=("opencode",),
        notes="OpenCode agent CLI when installed.",
    ),
    "cursor": BackendSpec(
        id="cursor",
        title="Cursor agent CLI",
        command='cursor-agent -p "$(Get-Content -Raw \'{prompt_file}\')"',
        detect=("cursor-agent", "cursor"),
        notes="Cursor agent if CLI present; else manual.",
    ),
}


ALLOWED_BACKENDS = frozenset(BUILTIN_BACKENDS.keys()) | frozenset({"custom"})


@dataclass
class BackendResolve:
    backend_id: str
    command: str
    available: bool
    reason: str = ""
    detect_hit: str | None = None


def list_backends() -> list[BackendSpec]:
    return list(BUILTIN_BACKENDS.values())


def format_backends(*, probe: bool = True) -> str:
    lines = ["CrewLab CLI backends (multi-agent runtimes):", ""]
    for b in list_backends():
        avail = ""
        if probe and b.detect:
            hit = next((n for n in b.detect if shutil.which(n)), None)
            avail = f"  [PATH:{hit}]" if hit else "  [not on PATH → prompt-only fallback]"
        elif probe and b.id in {"manual", "dry-run"}:
            avail = "  [always]"
        lines.append(f"  {b.id:10} {b.title}{avail}")
        if b.notes:
            lines.append(f"             {b.notes}")
    lines.append("")
    lines.append("Per agent: agents[].backend + optional agents[].cli / agents[].workdir")
    return "\n".join(lines)


def resolve_agent_backend(agent: dict[str, Any]) -> BackendResolve:
    """Resolve backend id + command for one agent dict."""
    raw = (agent.get("backend") or agent.get("runtime") or "manual").strip().lower()
    custom_cli = (agent.get("cli") or agent.get("backend_cmd") or "").strip()

    if raw == "custom" or (raw == "shell" and custom_cli):
        if not custom_cli:
            return BackendResolve("shell", "", False, "shell/custom requires agents[].cli")
        return BackendResolve(raw if raw != "custom" else "shell", custom_cli, True, "custom cli")

    if raw not in BUILTIN_BACKENDS:
        return BackendResolve(raw, custom_cli, False, f"unknown backend: {raw}")

    spec = BUILTIN_BACKENDS[raw]
    if raw in {"manual", "dry-run"}:
        return BackendResolve(raw, "", True, spec.notes)

    if custom_cli:
        return BackendResolve(raw, custom_cli, True, "override cli")

    hit = next((n for n in spec.detect if shutil.which(n)), None) if spec.detect else None
    if spec.detect and not hit:
        return BackendResolve(
            raw,
            "",
            False,
            f"{raw} not on PATH — will write prompt only (manual fallback)",
            detect_hit=None,
        )
    return BackendResolve(raw, spec.command, True, "ok", detect_hit=hit)


def render_command(
    template: str,
    *,
    prompt: str,
    prompt_file: Path,
    cwd: Path,
    agent_id: str,
    task_id: str,
    goal: str,
    result_file: Path,
    cli: str = "",
) -> str:
    return template.format(
        prompt=prompt.replace('"', '\\"')[:4000],
        prompt_file=str(prompt_file),
        cwd=str(cwd),
        agent_id=agent_id,
        task_id=task_id,
        goal=goal.replace('"', "'")[:500],
        result_file=str(result_file),
        cli=cli,
    )


@dataclass
class RunResult:
    ok: bool
    backend: str
    exit_code: int | None
    stdout: str = ""
    stderr: str = ""
    prompt_file: str | None = None
    result_file: str | None = None
    command: str | None = None
    mode: str = "executed"  # executed | prompt_only | dry-run | skipped
    error: str | None = None


def invoke_backend(
    agent: dict[str, Any],
    *,
    prompt: str,
    work_dir: Path,
    task_id: str,
    goal: str,
    timeout: int = 600,
    dry_run: bool = False,
    env: dict[str, str] | None = None,
) -> RunResult:
    """Write prompt artifact and optionally execute agent CLI."""
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    agent_id = str(agent.get("id") or "agent")
    prompt_file = work_dir / "prompt.md"
    result_file = work_dir / "result.md"
    prompt_file.write_text(prompt, encoding="utf-8")

    if dry_run:
        return RunResult(
            ok=True,
            backend="dry-run",
            exit_code=0,
            prompt_file=str(prompt_file),
            result_file=str(result_file),
            mode="dry-run",
        )

    resolved = resolve_agent_backend(agent)
    if resolved.backend_id in {"manual", "dry-run"} or not resolved.command:
        # prompt-only path
        note = (
            f"# Awaiting {agent_id} ({resolved.backend_id})\n\n"
            f"Backend: {resolved.backend_id}\n"
            f"Reason: {resolved.reason}\n"
            f"Prompt: {prompt_file}\n"
            f"Write result to: {result_file}\n"
            f"Then: crewlab task <spec> --agent {agent_id} --status done --result @result.md\n"
        )
        result_file.write_text(note, encoding="utf-8")
        return RunResult(
            ok=True,
            backend=resolved.backend_id,
            exit_code=None,
            prompt_file=str(prompt_file),
            result_file=str(result_file),
            mode="prompt_only",
            error=resolved.reason if not resolved.available else None,
        )

    cmd = render_command(
        resolved.command,
        prompt=prompt,
        prompt_file=prompt_file,
        cwd=work_dir,
        agent_id=agent_id,
        task_id=task_id,
        goal=goal,
        result_file=result_file,
        cli=str(agent.get("cli") or ""),
    )
    run_cwd = Path(agent.get("workdir") or work_dir)
    try:
        run_cwd.mkdir(parents=True, exist_ok=True)
    except Exception:
        run_cwd = work_dir

    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    full_env["CREWLAB_AGENT"] = agent_id
    full_env["CREWLAB_TASK"] = task_id
    full_env["CREWLAB_PROMPT_FILE"] = str(prompt_file)
    full_env["CREWLAB_RESULT_FILE"] = str(result_file)

    try:
        # Windows: PowerShell-friendly; use shell=True for template expansion
        completed = subprocess.run(
            cmd,
            shell=True,
            cwd=str(run_cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=full_env,
        )
        out = (completed.stdout or "").strip()
        err = (completed.stderr or "").strip()
        if out and not result_file.exists():
            result_file.write_text(out, encoding="utf-8")
        elif not result_file.exists():
            result_file.write_text(
                f"# Result {agent_id}/{task_id}\n\nexit={completed.returncode}\n\n{err[:2000]}",
                encoding="utf-8",
            )
        return RunResult(
            ok=completed.returncode == 0,
            backend=resolved.backend_id,
            exit_code=completed.returncode,
            stdout=out[:8000],
            stderr=err[:4000],
            prompt_file=str(prompt_file),
            result_file=str(result_file),
            command=cmd,
            mode="executed",
        )
    except subprocess.TimeoutExpired:
        return RunResult(
            ok=False,
            backend=resolved.backend_id,
            exit_code=None,
            prompt_file=str(prompt_file),
            result_file=str(result_file),
            command=cmd,
            mode="executed",
            error=f"timeout after {timeout}s",
        )
    except Exception as e:
        return RunResult(
            ok=False,
            backend=resolved.backend_id,
            exit_code=None,
            prompt_file=str(prompt_file),
            result_file=str(result_file),
            command=cmd,
            mode="executed",
            error=str(e),
        )
