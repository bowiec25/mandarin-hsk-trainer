"""BlockSpec: a block's ID card in code. Mirrors the block's SPEC.md (ADR 0003)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class BlockSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    kind: Literal["script", "agent"]  # ADR 0002
    goal: str = Field(min_length=1)
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
