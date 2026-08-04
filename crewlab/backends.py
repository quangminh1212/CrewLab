"""CLI backends for heterogeneous multi-agent crews.

Each agent may bind to a different runtime (Hermes, Grok, Codex, Claude Code,
OpenClaw, OpenCode, manual, or raw shell). CrewLab orchestrates; backends execute.

Headless command shapes follow public CLIs (deep-research 2026-08):
  claude  -p / --print
  codex   exec
  hermes  chat -q
  openclaw agent exec --message-file
  grok    -p / --single --cwd
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class BackendSpec:
    id: str
    title: str
    detect: tuple[str, ...] = ()
    notes: str = ""
    # Human-readable example (docs only)
    example: str = ""


def _argv_hermes(prompt_file: Path, cwd: Path, **_: Any) -> list[str]:
    text = prompt_file.read_text(encoding="utf-8")
    return ["hermes", "chat", "-q", text]


def _argv_grok(prompt_file: Path, cwd: Path, **_: Any) -> list[str]:
    text = prompt_file.read_text(encoding="utf-8")
    return ["grok", "-p", text, "--cwd", str(cwd), "--output-format", "plain"]


def _argv_codex(prompt_file: Path, cwd: Path, **_: Any) -> list[str]:
    text = prompt_file.read_text(encoding="utf-8")
    return ["codex", "exec", "--cd", str(cwd), text]


def _argv_claude(prompt_file: Path, cwd: Path, **_: Any) -> list[str]:
    text = prompt_file.read_text(encoding="utf-8")
    # claude -p accepts prompt; CWD is workspace
    return ["claude", "-p", text]


def _argv_openclaw(prompt_file: Path, cwd: Path, **_: Any) -> list[str]:
    return [
        "openclaw",
        "agent",
        "exec",
        "--message-file",
        str(prompt_file),
        "--cwd",
        str(cwd),
        "--json",
    ]


def _argv_opencode(prompt_file: Path, cwd: Path, **_: Any) -> list[str]:
    text = prompt_file.read_text(encoding="utf-8")
    return ["opencode", "run", text]


def _argv_cursor(prompt_file: Path, cwd: Path, **_: Any) -> list[str]:
    text = prompt_file.read_text(encoding="utf-8")
    binary = "cursor-agent" if shutil.which("cursor-agent") else "cursor"
    return [binary, "-p", text]


ARGV_BUILDERS: dict[str, Callable[..., list[str]]] = {
    "hermes": _argv_hermes,
    "grok": _argv_grok,
    "codex": _argv_codex,
    "claude": _argv_claude,
    "openclaw": _argv_openclaw,
    "opencode": _argv_opencode,
    "cursor": _argv_cursor,
}


BUILTIN_BACKENDS: dict[str, BackendSpec] = {
    "manual": BackendSpec(
        id="manual",
        title="Manual / human-in-the-loop",
        notes="Writes prompt only; operator completes and marks task done.",
        example="(no process)",
    ),
    "dry-run": BackendSpec(
        id="dry-run",
        title="Dry-run (no process)",
        notes="Always no-op; used by tests and plan previews.",
        example="(no process)",
    ),
    "shell": BackendSpec(
        id="shell",
        title="Raw shell command",
        notes="Requires agents[].cli as full command template ({prompt_file}, {cwd}, …).",
        example='agents[].cli: \'my-agent --file "{prompt_file}"\'',
    ),
    "hermes": BackendSpec(
        id="hermes",
        title="Hermes Agent CLI",
        detect=("hermes",),
        notes="One-shot: hermes chat -q <prompt>",
        example="hermes chat -q <prompt>",
    ),
    "grok": BackendSpec(
        id="grok",
        title="Grok Build CLI",
        detect=("grok",),
        notes="Headless: grok -p <prompt> --cwd <dir> --output-format plain",
        example="grok -p <prompt> --cwd .",
    ),
    "codex": BackendSpec(
        id="codex",
        title="OpenAI Codex CLI",
        detect=("codex",),
        notes="Non-interactive: codex exec --cd <dir> <prompt>",
        example="codex exec --cd . <prompt>",
    ),
    "claude": BackendSpec(
        id="claude",
        title="Claude Code CLI",
        detect=("claude",),
        notes="Headless: claude -p <prompt> (workspace = process cwd)",
        example="claude -p <prompt>",
    ),
    "openclaw": BackendSpec(
        id="openclaw",
        title="OpenClaw CLI",
        detect=("openclaw",),
        notes="Headless: openclaw agent exec --message-file <path> --cwd <dir> --json",
        example="openclaw agent exec --message-file prompt.md --cwd .",
    ),
    "opencode": BackendSpec(
        id="opencode",
        title="OpenCode CLI",
        detect=("opencode",),
        notes="opencode run <prompt> when installed.",
        example="opencode run <prompt>",
    ),
    "cursor": BackendSpec(
        id="cursor",
        title="Cursor agent CLI",
        detect=("cursor-agent", "cursor"),
        notes="cursor-agent -p <prompt> if present.",
        example="cursor-agent -p <prompt>",
    ),
}


ALLOWED_BACKENDS = frozenset(BUILTIN_BACKENDS.keys()) | frozenset({"custom"})


@dataclass
class BackendResolve:
    backend_id: str
    command: str  # display string
    available: bool
    reason: str = ""
    detect_hit: str | None = None
    argv: list[str] | None = None
    shell: bool = False


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
        if b.example:
            lines.append(f"             cmd: {b.example}")
        if b.notes:
            lines.append(f"             {b.notes}")
    lines.append("")
    lines.append("Per agent: agents[].backend + optional agents[].cli / agents[].workdir")
    lines.append("Dispatch: crewlab run | kickoff  (prompt → CLI headless → runs/<task>/result.md)")
    return "\n".join(lines)


def resolve_agent_backend(
    agent: dict[str, Any],
    *,
    prompt_file: Path | None = None,
    cwd: Path | None = None,
) -> BackendResolve:
    """Resolve backend id + argv/command for one agent dict."""
    raw = (agent.get("backend") or agent.get("runtime") or "manual").strip().lower()
    custom_cli = (agent.get("cli") or agent.get("backend_cmd") or "").strip()
    pf = prompt_file or Path("prompt.md")
    work = cwd or Path(".")

    if raw == "custom" or (raw == "shell" and custom_cli):
        if not custom_cli:
            return BackendResolve("shell", "", False, "shell/custom requires agents[].cli")
        cmd = custom_cli.format(
            prompt_file=str(pf),
            prompt="",
            cwd=str(work),
            agent_id=str(agent.get("id") or ""),
            task_id="",
            goal="",
            result_file="",
            cli=custom_cli,
        )
        return BackendResolve(raw if raw != "custom" else "shell", cmd, True, "custom cli", shell=True)

    if raw not in BUILTIN_BACKENDS:
        return BackendResolve(raw, custom_cli, False, f"unknown backend: {raw}")

    if raw in {"manual", "dry-run"}:
        return BackendResolve(raw, "", True, BUILTIN_BACKENDS[raw].notes)

    if custom_cli:
        cmd = custom_cli.format(
            prompt_file=str(pf),
            prompt="",
            cwd=str(work),
            agent_id=str(agent.get("id") or ""),
            task_id="",
            goal="",
            result_file="",
            cli=custom_cli,
        )
        return BackendResolve(raw, cmd, True, "override cli", shell=True)

    spec = BUILTIN_BACKENDS[raw]
    hit = next((n for n in spec.detect if shutil.which(n)), None) if spec.detect else None
    if spec.detect and not hit:
        return BackendResolve(
            raw,
            "",
            False,
            f"{raw} not on PATH — will write prompt only (manual fallback)",
        )

    builder = ARGV_BUILDERS.get(raw)
    argv = builder(pf, work) if builder and prompt_file else None
    display = " ".join(shlex.quote(x) for x in (argv or [raw])) if argv else (spec.example or raw)
    return BackendResolve(raw, display, True, "ok", detect_hit=hit, argv=argv, shell=False)


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
    """Write prompt artifact and optionally execute agent CLI (argv preferred)."""
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

    run_cwd = Path(agent.get("workdir") or work_dir)
    try:
        run_cwd.mkdir(parents=True, exist_ok=True)
    except Exception:
        run_cwd = work_dir

    resolved = resolve_agent_backend(agent, prompt_file=prompt_file, cwd=run_cwd)
    if resolved.backend_id in {"manual", "dry-run"} or (
        not resolved.argv and not resolved.shell and not resolved.command
    ):
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

    # Rebuild argv now that prompt_file exists
    if not resolved.shell and resolved.backend_id in ARGV_BUILDERS:
        try:
            argv = ARGV_BUILDERS[resolved.backend_id](prompt_file, run_cwd)
        except Exception as e:
            return RunResult(
                ok=False,
                backend=resolved.backend_id,
                exit_code=None,
                prompt_file=str(prompt_file),
                result_file=str(result_file),
                mode="executed",
                error=f"argv build failed: {e}",
            )
        cmd_display = " ".join(shlex.quote(a) for a in argv[:4]) + (" …" if len(argv) > 4 else "")
        use_shell = False
        popen_arg: str | list[str] = argv
    else:
        cmd = resolved.command
        if "{prompt_file}" in cmd or "{cwd}" in cmd:
            cmd = render_command(
                cmd,
                prompt=prompt,
                prompt_file=prompt_file,
                cwd=run_cwd,
                agent_id=agent_id,
                task_id=task_id,
                goal=goal,
                result_file=result_file,
                cli=str(agent.get("cli") or ""),
            )
        cmd_display = cmd
        use_shell = True
        popen_arg = cmd

    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    full_env["CREWLAB_AGENT"] = agent_id
    full_env["CREWLAB_TASK"] = task_id
    full_env["CREWLAB_PROMPT_FILE"] = str(prompt_file)
    full_env["CREWLAB_RESULT_FILE"] = str(result_file)
    full_env["CREWLAB_GOAL"] = goal[:500]

    try:
        completed = subprocess.run(
            popen_arg,
            shell=use_shell,
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
            command=cmd_display,
            mode="executed",
        )
    except subprocess.TimeoutExpired:
        return RunResult(
            ok=False,
            backend=resolved.backend_id,
            exit_code=None,
            prompt_file=str(prompt_file),
            result_file=str(result_file),
            command=cmd_display,
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
            command=cmd_display,
            mode="executed",
            error=str(e),
        )
