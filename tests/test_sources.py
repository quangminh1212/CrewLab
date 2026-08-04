from pathlib import Path

from crewlab.cli import main
from crewlab.sources import check_catalog, load_catalog
from crewlab.validate import validate_spec
from crewlab.io_util import load_spec


def test_catalog_integrated_evidence():
    problems = check_catalog()
    assert not problems, problems
    entries = load_catalog()
    assert len(entries) >= 5
    integrated = [e for e in entries if e.status == "integrated"]
    assert len(integrated) >= 4


def test_cli_sources():
    assert main(["sources"]) == 0


def test_github_inspired_examples_validate():
    root = Path(__file__).resolve().parents[1]
    for name in (
        "chatdev-software",
        "crewai-sequential",
        "metagpt-sop",
        "ship-feature",
        "multi-cli-room",
    ):
        path = root / "examples" / name / "crew-spec.yaml"
        assert path.is_file(), name
        r = validate_spec(load_spec(path))
        assert r.ok, f"{name}: {r.summary()}"
