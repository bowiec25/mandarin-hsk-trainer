"""BlockSpec: a block's ID card in code. Mirrors the block's SPEC.md (ADR 0003)."""

import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# The 7 sections every block's SPEC.md must have (ADR 0003).
SPEC_SECTIONS = [
    "Goal",
    "Kind",
    "Inputs",
    "Outputs",
    "Tools",
    "Failure modes",
    "How to test",
]


class BlockSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    kind: Literal["script", "agent"]  # ADR 0002
    goal: str = Field(min_length=1)
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)


def spec_section(spec_md: Path, section: str) -> str:
    """Return the text under one `## <section>` heading (case-insensitive), or ''."""
    text = Path(spec_md).read_text(encoding="utf-8")
    pattern = rf"^##\s+{re.escape(section)}\s*$\n(.*?)(?=^##\s|\Z)"
    match = re.search(pattern, text, re.MULTILINE | re.DOTALL | re.IGNORECASE)
    return match.group(1) if match else ""


def missing_spec_sections(spec_md: Path) -> list[str]:
    """Return the required SPEC.md sections (## headings) that are missing."""
    text = Path(spec_md).read_text(encoding="utf-8")
    headings = {
        h.strip().lower() for h in re.findall(r"^##\s+(.+?)\s*$", text, re.MULTILINE)
    }
    return [s for s in SPEC_SECTIONS if s.lower() not in headings]
