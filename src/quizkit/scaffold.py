"""The block 'photocopier': creates a new block's blank files, the same way every time.

Run:  uv run python -m quizkit.scaffold <name> --kind script|agent
                    --package hsk_trainer|quizkit --goal "..." [--dry-run]

Creates (ADR 0003):
    src/<package>/blocks/<name>/__init__.py   BLOCK_SPEC + run() stub
    src/<package>/blocks/<name>/SPEC.md       the 7 sections, ready to fill in
    tests/blocks/test_<name>.py               contract test (spec + SPEC.md complete)
Never overwrites an existing block.
"""

import argparse
import re
import sys
from pathlib import Path

from quizkit.blocks.base import SPEC_SECTIONS

KINDS = ("script", "agent")
PACKAGES = ("quizkit", "hsk_trainer")
NAME_RULE = re.compile(r"^[a-z][a-z0-9_]*$")

SPEC_HINTS = {
    "Goal": "One or two sentences: what does this block do, and why does it exist?",
    "Kind": "{kind}. Why? (ADR 0002: script if code can check the output; agent if it needs judgment)",
    "Inputs": "What goes in? (files, models, settings), with types",
    "Outputs": "What comes out? (files, models), with types and where they are saved",
    "Tools": "Libraries or functions it uses. For agents: the script functions it may call",
    "Failure modes": "What can go wrong, and what the block does then (error, skip, retry?)",
    "How to test": "Which tests prove it works, and any manual checks",
}

INIT_TEMPLATE = '''"""{name}: {goal}

See SPEC.md in this folder (ADR 0003).
"""

from quizkit.blocks.base import BlockSpec

BLOCK_SPEC = BlockSpec(
    name="{name}",
    kind="{kind}",
    goal="{goal}",
    inputs=[],  # TODO: fill in from SPEC.md
    outputs=[],  # TODO: fill in from SPEC.md
)


def run() -> None:
    """TODO: implement (see SPEC.md)."""
    raise NotImplementedError("{name} is not built yet")
'''

TEST_TEMPLATE = '''"""Contract test for the {name} block: its ID card and SPEC.md are complete."""

from pathlib import Path

import {package}.blocks.{name} as block
from quizkit.blocks.base import missing_spec_sections


def test_block_spec_matches():
    assert block.BLOCK_SPEC.name == "{name}"
    assert block.BLOCK_SPEC.kind == "{kind}"


def test_spec_md_has_every_section():
    spec_md = Path(block.__file__).parent / "SPEC.md"
    assert missing_spec_sections(spec_md) == []
'''


def _spec_md(name: str, kind: str, goal: str) -> str:
    parts = [f"# Block: `{name}`\n", f"> **In plain words:** {goal}\n"]
    for section in SPEC_SECTIONS:
        hint = SPEC_HINTS[section].format(kind=kind)
        body = (
            f"{goal}\n\n<!-- TODO: {hint} -->"
            if section == "Goal"
            else f"<!-- TODO: {hint} -->"
        )
        parts.append(f"## {section}\n{body}\n")
    return "\n".join(parts)


def scaffold_block(
    name: str,
    *,
    kind: str,
    package: str,
    goal: str,
    root: Path = Path("."),
    dry_run: bool = False,
) -> list[Path]:
    """Create (or, with dry_run, just list) the files for a new block."""
    if not NAME_RULE.match(name):
        raise ValueError(
            f"block name {name!r} must be snake_case, e.g. 'sentence_writer'"
        )
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}, not {kind!r}")
    if package not in PACKAGES:
        raise ValueError(f"package must be one of {PACKAGES}, not {package!r}")
    goal = goal.strip().replace('"', "'") or "TODO: one-line goal"

    root = Path(root)
    blocks_dir = root / "src" / package / "blocks"
    block_dir = blocks_dir / name
    test_file = root / "tests" / "blocks" / f"test_{name}.py"
    if block_dir.exists() or test_file.exists():
        raise FileExistsError(
            f"block {name!r} already exists, so it won't be overwritten"
        )

    files: dict[Path, str] = {}
    if not (blocks_dir / "__init__.py").exists():
        files[blocks_dir / "__init__.py"] = f'"""Blocks for {package} (ADR 0003)."""\n'
    files[block_dir / "__init__.py"] = INIT_TEMPLATE.format(
        name=name, kind=kind, goal=goal
    )
    files[block_dir / "SPEC.md"] = _spec_md(name, kind, goal)
    files[test_file] = TEST_TEMPLATE.format(name=name, kind=kind, package=package)

    if not dry_run:
        for path, content in files.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
    return list(files)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a new block's blank files.")
    parser.add_argument("name", help="snake_case block name, e.g. fetcher")
    parser.add_argument("--kind", required=True, choices=KINDS)
    parser.add_argument("--package", required=True, choices=PACKAGES)
    parser.add_argument("--goal", default="", help="one-line goal")
    parser.add_argument("--root", default=".", help="project folder (default: here)")
    parser.add_argument(
        "--dry-run", action="store_true", help="only list what would be created"
    )
    args = parser.parse_args(argv)

    try:
        paths = scaffold_block(
            args.name,
            kind=args.kind,
            package=args.package,
            goal=args.goal,
            root=Path(args.root),
            dry_run=args.dry_run,
        )
    except (ValueError, FileExistsError) as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1

    verb = "Would create" if args.dry_run else "Created"
    root = Path(args.root)
    for path in paths:
        print(f"{verb}: {path.relative_to(root).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
