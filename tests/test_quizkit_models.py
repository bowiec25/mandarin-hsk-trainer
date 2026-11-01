"""Card and Question: the generic 'forms' every block fills in."""

import pytest
from pydantic import ValidationError

from quizkit.models import Card


def make_card(**overrides):
    data = {
        "id": "capital-fr",
        "fields": {"country": "France"},
        "answers": ["Paris"],
        "level": 1,
    }
    data.update(overrides)
    return Card(**data)


def test_valid_card():
    card = make_card()
    assert card.fields["country"] == "France"
    assert card.answers == ["Paris"]


def test_whitespace_is_trimmed():
    card = make_card(id="  capital-fr ", answers=["  Paris  "])
    assert card.id == "capital-fr"
    assert card.answers == ["Paris"]


@pytest.mark.parametrize(
    "bad",
    [
        {"id": "   "},  # blank id
        {"answers": []},  # no answers
        {"answers": ["  "]},  # only a blank answer
        {"level": 0},  # level must be >= 1
    ],
)
def test_bad_cards_are_rejected(bad):
    with pytest.raises(ValidationError):
        make_card(**bad)


def test_card_is_frozen():
    card = make_card()
    with pytest.raises(ValidationError):
        card.level = 2
