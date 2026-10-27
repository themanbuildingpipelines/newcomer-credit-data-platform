"""
Tests for generator/run.py: the files on disk, not just the data in memory.
"""
import json
from pathlib import Path

from generator.run import main, pence_to_str


def test_money_formatting_is_exact():
    assert pence_to_str(125050) == "1250.50"
    assert pence_to_str(-125050) == "-1250.50"
    assert pence_to_str(5) == "0.05"
    assert pence_to_str(-5) == "-0.05"
    assert pence_to_str(0) == "0.00"


def test_cli_writes_every_file_and_a_matching_manifest(tmp_path):
    main(["--seed", "3", "--customers", "20", "--out", str(tmp_path)])

    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["seed"] == 3
    for name, info in manifest["files"].items():
        lines = Path(info["path"]).read_text().splitlines()
        assert len(lines) - 1 == info["rows"], f"row count mismatch in {name}"

    assert (tmp_path / "truth" / "generator_truth.csv").exists()


def test_same_seed_gives_byte_identical_files(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    main(["--seed", "3", "--customers", "20", "--out", str(first)])
    main(["--seed", "3", "--customers", "20", "--out", str(second)])

    m1 = json.loads((first / "manifest.json").read_text())
    m2 = json.loads((second / "manifest.json").read_text())
    for name in m1["files"]:
        assert m1["files"][name]["sha256"] == m2["files"][name]["sha256"], name
