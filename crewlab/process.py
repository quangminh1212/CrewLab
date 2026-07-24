"""Crew process models inspired by CrewAI / ChatDev / MetaGPT.

collaborative — default: meeting-centric one-agent-one-task (CrewLab native)
sequential    — waterfall dependencies (ChatDev / CrewAI sequential)
hierarchical  — lead delegates via meetings; workers report up (CrewAI hierarchical)
"""

from __future__ import annotations

from typing import Any

ALLOWED_PROCESS = frozenset({"collaborative", "sequential", "hierarchical"})

PROCESS_META: dict[str, dict[str, str]] = {
    "collaborative": {
        "source": "CrewLab + hermes-agent",
        "url": "https://github.com/NousResearch/hermes-agent",
        "hint": "Meet, unblock, ship; one agent owns one task.",
    },
    "sequential": {
        "source": "CrewAI sequential + ChatDev waterfall",
        "url": "https://github.com/crewAIInc/crewAI",
        "hint": "Respect depends_on strictly; next task only after prior done.",
    },
    "hierarchical": {
        "source": "CrewAI hierarchical process",
        "url": "https://github.com/crewAIInc/crewAI",
        "hint": "Lead coordinates; workers only their task; reassign only via decision.",
    },
}


def normalize_process(spec: dict[str, Any]) -> str:
    raw = (spec.get("process") or "collaborative").strip().lower()
    if raw not in ALLOWED_PROCESS:
        return "collaborative"
    return raw


def process_notes(spec: dict[str, Any]) -> list[str]:
    """Runtime hints for status/meeting based on process model."""
    proc = normalize_process(spec)
    meta = PROCESS_META[proc]
    notes = [f"process={proc} ({meta['source']})", meta["hint"]]
    if proc == "sequential":
        tasks = [t for t in (spec.get("tasks") or []) if isinstance(t, dict)]
        for t in tasks:
            deps = t.get("depends_on") or []
            if deps:
                notes.append(f"  sequential gate: {t.get('id')} waits on {', '.join(deps)}")
    return notes
