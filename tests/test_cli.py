from pathlib import Path

from crewlab.cli import main


def test_cli_validate_example():
    root = Path(__file__).resolve().parents[1]
    example = root / "examples" / "ship-feature" / "crew-spec.yaml"
    assert main(["validate", str(example)]) == 0


def test_cli_init_and_status(tmp_path: Path):
    proj = tmp_path / "c1"
    assert main(["init", str(proj), "--name", "c1"]) == 0
    assert main(["validate", str(proj / "crew-spec.yaml")]) == 0
    assert main(["assign", str(proj / "crew-spec.yaml")]) == 0
    assert main(["status", str(proj / "crew-spec.yaml")]) == 0
    assert (
        main(
            [
                "task",
                str(proj / "crew-spec.yaml"),
                "--agent",
                "lead",
                "--status",
                "done",
                "--result",
                "planned",
            ]
        )
        == 0
    )


def test_cli_accepts_project_directory(tmp_path: Path):
    """User flow: init dir then status/meeting/task with the directory path."""
    proj = tmp_path / "crew-dir"
    assert main(["init", str(proj), "--name", "dir-crew"]) == 0
    assert main(["validate", str(proj)]) == 0
    assert main(["assign", str(proj)]) == 0
    assert main(["status", str(proj)]) == 0
    assert main(["meeting", str(proj), "--dry-run"]) == 0
    assert (
        main(
            [
                "task",
                str(proj),
                "--agent",
                "lead",
                "--status",
                "in_progress",
            ]
        )
        == 0
    )
    assert main(["meeting", str(proj)]) == 0
