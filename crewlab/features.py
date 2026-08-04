"""Feature parity matrix vs referenced upstreams (CrewAI, ChatDev, MetaGPT, AutoGen, …).

CrewLab is NOT a re-host of CrewAI runtime. This module maps upstream concepts
to native CrewLab capabilities so `crewlab features` can prove coverage.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Status = Literal["native", "mapped", "partial", "n/a"]


@dataclass(frozen=True)
class Feature:
    id: str
    source: str  # crewai | chatdev | metagpt | autogen | superpowers | deerflow | hermes
    name: str
    status: Status
    crewlab: str  # where / how in CrewLab


# Core CrewAI surface + peer multi-agent patterns we intentionally cover.
FEATURE_MATRIX: tuple[Feature, ...] = (
    # --- CrewAI ---
    Feature("crewai.agent.role", "crewai", "Agent role / goal / backstory", "mapped", "agents[].role + mission (+ goal on crew)"),
    Feature("crewai.agent.llm", "crewai", "Per-agent LLM binding", "mapped", "agents[].backend + backends.* CLI (multi-runtime)"),
    Feature("crewai.agent.tools", "crewai", "Agent tools", "partial", "CLI backends own tools; agent.tools[] is advisory metadata"),
    Feature("crewai.agent.delegation", "crewai", "Allow delegation", "mapped", "crewlab reassign + meeting decision (no silent steal)"),
    Feature("crewai.agent.memory", "crewai", "Agent/crew memory", "mapped", "project MEMORY.md + lessons via run/plan"),
    Feature("crewai.task.description", "crewai", "Task description + expected_output", "mapped", "tasks[].title/description + expected_output"),
    Feature("crewai.task.context", "crewai", "Task context from prior outputs", "mapped", "depends_on + CHAT_LOG + prior task results in kickoff prompt"),
    Feature("crewai.task.human_input", "crewai", "Human input gate", "mapped", "agents[].backend=manual | run --step"),
    Feature("crewai.task.output_file", "crewai", "Task output file", "mapped", "runs/<task_id>/result.md via kickoff"),
    Feature("crewai.crew.sequential", "crewai", "Process.sequential", "native", "process: sequential + depends_on gates in kickoff"),
    Feature("crewai.crew.hierarchical", "crewai", "Process.hierarchical + manager", "mapped", "process: hierarchical + manager agent + plan phase"),
    Feature("crewai.crew.kickoff", "crewai", "Crew.kickoff()", "native", "crewlab run / crewlab kickoff"),
    Feature("crewai.crew.planning", "crewai", "Planning before execution", "mapped", "crewlab plan (+ auto plan on hierarchical)"),
    Feature("crewai.crew.verbose", "crewai", "Verbose step logs", "mapped", "run --verbose + MEETING_LOG + RUN_LOG.md"),
    Feature("crewai.crew.callbacks", "crewai", "Step/task callbacks", "partial", "hooks via shell post_cmd; no Python callback API"),
    Feature("crewai.flows", "crewai", "CrewAI Flows", "partial", "sequential depends_on graph + meetings; no visual flow DSL"),
    Feature("crewai.knowledge", "crewai", "Knowledge sources", "partial", "knowledge_paths[] mounted into prompts"),
    # --- ChatDev ---
    Feature("chatdev.company_roles", "chatdev", "Software company roles waterfall", "mapped", "examples/chatdev-software + process sequential"),
    Feature("chatdev.phase_chat", "chatdev", "Phase/role chat handoff", "mapped", "crewlab chat + meeting rounds"),
    Feature("chatdev.review_gate", "chatdev", "Review before ship", "mapped", "reviewer task + definition_of_done"),
    # --- MetaGPT ---
    Feature("metagpt.sop", "metagpt", "SOP product→arch→code→QA", "mapped", "examples/metagpt-sop"),
    Feature("metagpt.message_pool", "metagpt", "Shared message pool", "native", "CHAT_LOG.md + chat.jsonl (crewlab chat)"),
    Feature("metagpt.role_action", "metagpt", "Role owns one SOP action", "native", "one agent = one task_id"),
    # --- AutoGen ---
    Feature("autogen.group_chat", "autogen", "Multi-agent group chat", "mapped", "crewlab chat --all + meeting"),
    Feature("autogen.human_in_loop", "autogen", "Human-in-the-loop", "mapped", "backend=manual + run --step"),
    Feature("autogen.speaker_select", "autogen", "Speaker selection", "partial", "process order + next_ready; no dynamic LLM speaker pick"),
    # --- Superpowers ---
    Feature("superpowers.skills", "superpowers", "Skill-based methodology", "mapped", "skills/crewlab + Hermes /crewlab"),
    Feature("superpowers.worktree", "superpowers", "Isolated worktrees", "partial", "agent.workdir override; no auto git worktree yet"),
    Feature("superpowers.subagent", "superpowers", "Subagent execution", "mapped", "kickoff dispatches per-agent CLI backends"),
    # --- DeerFlow / Hermes ---
    Feature("deerflow.harness", "deerflow", "Long-horizon super-agent harness", "integrated", "labs/deer-flow + /deerflow skill"),
    Feature("hermes.host", "hermes", "Host skill runtime", "integrated", "crewlab attach → Hermes skill junction"),
    # --- Multi-CLI room (CrewLab extension for multi-runtime crews) ---
    Feature("crewlab.multi_cli", "crewlab", "Heterogeneous CLI agents in one crew", "native", "backends: hermes|grok|codex|claude|openclaw|opencode|manual|shell"),
)


def features_for(source: str | None = None) -> list[Feature]:
    if not source:
        return list(FEATURE_MATRIX)
    s = source.strip().lower()
    return [f for f in FEATURE_MATRIX if f.source == s or f.id.startswith(s + ".")]


def format_features(*, source: str | None = None, gaps_only: bool = False) -> str:
    rows = features_for(source)
    if gaps_only:
        rows = [f for f in rows if f.status in {"partial", "n/a"}]
    lines = [
        "CrewLab feature parity (upstream concepts → native mapping)",
        f"total={len(FEATURE_MATRIX)} shown={len(rows)}"
        + (f" source={source}" if source else "")
        + (" gaps_only" if gaps_only else ""),
        "",
        f"{'status':8} {'source':12} {'feature':42} crewlab",
        "-" * 100,
    ]
    for f in rows:
        lines.append(f"{f.status:8} {f.source:12} {f.name:42} {f.crewlab}")
    # summary counts
    from collections import Counter

    c = Counter(x.status for x in FEATURE_MATRIX)
    lines.append("")
    lines.append(
        "summary: "
        + ", ".join(f"{k}={v}" for k, v in sorted(c.items()))
    )
    partial = [f for f in FEATURE_MATRIX if f.status == "partial"]
    if partial and not gaps_only:
        lines.append(f"partial gaps: {len(partial)} (use --gaps)")
    return "\n".join(lines)


def coverage_ok(*, allow_partial: bool = True) -> list[str]:
    """Return problems if critical features are missing."""
    problems: list[str] = []
    for f in FEATURE_MATRIX:
        if f.status == "n/a":
            problems.append(f"n/a: {f.id}")
        elif f.status == "partial" and not allow_partial:
            problems.append(f"partial: {f.id}")
    return problems
