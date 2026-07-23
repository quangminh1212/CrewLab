"""Attach / detach CrewLab skills into Hermes via junctions only."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def package_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_hermes_home() -> Path:
    if os.environ.get("HERMES_HOME"):
        return Path(os.environ["HERMES_HOME"])
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "hermes"


def _is_reparse(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        return bool(path.stat().st_file_attributes & 0x400)  # type: ignore[attr-defined]
    except Exception:
        # fallback: directory junction often has no children resolved the same way
        return path.is_symlink() or path.is_junction() if hasattr(path, "is_junction") else path.is_symlink()


def _ensure_junction(dst: Path, src: Path) -> None:
    src = src.resolve()
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() or dst.is_symlink():
        try:
            if hasattr(dst, "is_junction") and dst.is_junction():
                target = Path(os.readlink(dst)) if hasattr(os, "readlink") else None
                # Windows junction: compare via cmd
                pass
            # Re-create if wrong
            if dst.resolve() == src:
                return
        except Exception:
            pass
        # remove junction/dir carefully
        if dst.is_dir() and not dst.is_symlink():
            # only rmdir junction / empty
            subprocess.run(["cmd", "/c", "rmdir", str(dst)], check=False, capture_output=True)
        elif dst.is_symlink() or (hasattr(dst, "is_junction") and dst.is_junction()):
            dst.unlink()
        else:
            raise RuntimeError(f"Path exists and is not a junction: {dst}")
    # mklink /J
    r = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(dst), str(src)],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"mklink failed: {r.stdout} {r.stderr}")


def attach_to_hermes(hermes_home: Path | None = None) -> list[str]:
    home = hermes_home or default_hermes_home()
    if not home.is_dir():
        raise FileNotFoundError(f"Hermes home not found: {home}")
    skills_src = package_root() / "skills"
    skills_dst = home / "skills"
    linked: list[str] = []
    for skill_dir in sorted(skills_src.iterdir()):
        if not skill_dir.is_dir():
            continue
        if not (skill_dir / "SKILL.md").is_file():
            continue
        dst = skills_dst / skill_dir.name
        _ensure_junction(dst, skill_dir)
        linked.append(str(dst))
    # optional context note
    note_src = package_root() / "templates" / "HERMES.md"
    if note_src.is_file():
        (home / "crewlab-HERMES.md").write_text(note_src.read_text(encoding="utf-8"), encoding="utf-8")
        linked.append(str(home / "crewlab-HERMES.md"))
    return linked


def uninstall_from_hermes(hermes_home: Path | None = None) -> list[str]:
    home = hermes_home or default_hermes_home()
    skills_src = package_root() / "skills"
    skills_dst = home / "skills"
    removed: list[str] = []
    for skill_dir in sorted(skills_src.iterdir()):
        if not skill_dir.is_dir() or not (skill_dir / "SKILL.md").is_file():
            continue
        dst = skills_dst / skill_dir.name
        if dst.exists() or dst.is_symlink():
            subprocess.run(["cmd", "/c", "rmdir", str(dst)], check=False, capture_output=True)
            removed.append(str(dst))
    note = home / "crewlab-HERMES.md"
    if note.is_file():
        note.unlink()
        removed.append(str(note))
    return removed
