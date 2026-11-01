"""The block 'photocopier' (quizkit.scaffold) and the SPEC checker."""

import pytest

from quizkit.blocks.base import SPEC_SECTIONS, missing_spec_sections, spec_section
from quizkit.scaffold import main, scaffold_block


def test_creates_the_block_files(tmp_path):
    created = scaffold_block(
        "fetcher",
        kind="script",
        package="hsk_trainer",
        goal="Download the list",
        root=tmp_path,
    )
    block = tmp_path / "src" / "hsk_trainer" / "blocks" / "fetcher"
    assert block / "__init__.py" in created
    assert block / "SPEC.md" in created
    assert tmp_path / "tests" / "blocks" / "test_fetcher.py" in created
    for path in created:
        assert path.exists()

    code = (block / "__init__.py").read_text(encoding="utf-8")
    assert 'name="fetcher"' in code
    assert 'kind="script"' in code
    assert "Download the list" in code


def test_new_spec_has_every_section(tmp_path):
    scaffold_block(
        "grader", kind="script", package="quizkit", goal="Check answers", root=tmp_path
    )
    spec = tmp_path / "src" / "quizkit" / "blocks" / "grader" / "SPEC.md"
    assert missing_spec_sections(spec) == []


def test_package_blocks_init_is_created_once(tmp_path):
    scaffold_block(
        "a_block", kind="script", package="hsk_trainer", goal="A", root=tmp_path
    )
    created = scaffold_block(
        "b_block", kind="agent", package="hsk_trainer", goal="B", root=tmp_path
    )
    assert tmp_path / "src" / "hsk_trainer" / "blocks" / "__init__.py" not in created


@pytest.mark.parametrize("bad_name", ["Fetcher", "my-block", "2fast", "", "has space"])
def test_bad_names_are_rejected(tmp_path, bad_name):
    with pytest.raises(ValueError):
        scaffold_block(
            bad_name, kind="script", package="quizkit", goal="x", root=tmp_path
        )


def test_bad_kind_or_package_rejected(tmp_path):
    with pytest.raises(ValueError):
        scaffold_block("ok", kind="robot", package="quizkit", goal="x", root=tmp_path)
    with pytest.raises(ValueError):
        scaffold_block(
            "ok", kind="script", package="elsewhere", goal="x", root=tmp_path
        )


def test_never_overwrites_an_existing_block(tmp_path):
    scaffold_block(
        "fetcher", kind="script", package="hsk_trainer", goal="x", root=tmp_path
    )
    with pytest.raises(FileExistsError):
        scaffold_block(
            "fetcher", kind="script", package="hsk_trainer", goal="x", root=tmp_path
        )


def test_dry_run_writes_nothing(tmp_path):
    planned = scaffold_block(
        "fetcher",
        kind="script",
        package="hsk_trainer",
        goal="x",
        root=tmp_path,
        dry_run=True,
    )
    assert len(planned) == 4  # blocks/__init__.py, block __init__.py, SPEC.md, test
    assert not any(tmp_path.rglob("*"))


def test_command_line(tmp_path, capsys):
    code = main(
        [
            "demo",
            "--kind",
            "script",
            "--package",
            "quizkit",
            "--goal",
            "Demo",
            "--root",
            str(tmp_path),
            "--dry-run",
        ]
    )
    assert code == 0
    assert "would create" in capsys.readouterr().out.lower()


def test_checker_spots_missing_sections(tmp_path):
    spec = tmp_path / "SPEC.md"
    spec.write_text("# x\n\n## Goal\nDo a thing\n\n## Kind\nscript\n", encoding="utf-8")
    missing = missing_spec_sections(spec)
    assert "Inputs" in missing
    assert "Goal" not in missing
    assert len(missing) == len(SPEC_SECTIONS) - 2


# ---- spec_section + the stronger contract test --------------------------------------


def test_spec_section_returns_one_sections_text(tmp_path):
    spec = tmp_path / "SPEC.md"
    spec.write_text(
        "## Inputs\n- `word: str`\n\n## Outputs\n- `int`\n", encoding="utf-8"
    )
    assert spec_section(spec, "Inputs").strip() == "- `word: str`"
    assert spec_section(spec, "outputs").strip() == "- `int`"  # case-insensitive
    assert spec_section(spec, "Tools") == ""  # missing section → empty


def test_contract_test_checks_inputs_and_outputs(tmp_path):
    scaffold_block(
        "fetcher", kind="script", package="hsk_trainer", goal="x", root=tmp_path
    )
    test_code = (tmp_path / "tests" / "blocks" / "test_fetcher.py").read_text(
        encoding="utf-8"
    )
    assert "test_inputs_and_outputs_match_spec" in test_code
    assert "spec_section" in test_code
