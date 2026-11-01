import pytest
from pydantic import ValidationError

from quizkit.blocks.base import BlockSpec


def test_blockspec_kind_must_be_script_or_agent():
    BlockSpec(name="fetcher", kind="script", goal="Download the word list")
    with pytest.raises(ValidationError):
        BlockSpec(name="x", kind="robot", goal="nope")
