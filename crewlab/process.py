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
    if proc == "hierarchical":
        notes.append("  hierarchical: manager agent plans first; workers run when ready")
    return notes


def dependency_order(spec: dict[str, Any]) -> list[str]:
    """Topological-ish order of task ids (declaration order with deps first)."""
    tasks = [t for t in (spec.get("tasks") or []) if isinstance(t, dict) and t.get("id")]
    ids = [str(t["id"]) for t in tasks]
    deps_map = {
        str(t["id"]): [str(d) for d in (t.get("depends_on") or [])]
        for t in tasks
    }
    done: list[str] = []
    remaining = set(ids)
    guard = 0
    while remaining and guard < len(ids) * len(ids) + 2:
        guard += 1
        progressed = False
        for tid in list(remaining):
            if all(d in done or d not in deps_map for d in deps_map.get(tid, [])):
                # all deps done or unknown (unknown caught by validate)
                if all(d in done for d in deps_map.get(tid, []) if d in ids):
                    done.append(tid)
                    remaining.discard(tid)
                    progressed = True
        if not progressed:
            # cycle or missing — append rest in declaration order
            for tid in ids:
                if tid in remaining:
                    done.append(tid)
                    remaining.discard(tid)
            break
    return done
