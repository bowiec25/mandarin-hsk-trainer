"""Modes say which fields to show; build_question turns Card + Mode into a Question."""

import pytest

from quizkit.models import Card
from quizkit.modes import MissingFieldError, Mode, build_question

CARD = Card(
    id="capital-fr",
    fields={"country": "France", "flag": "blue-white-red"},
    answers=["Paris"],
    level=1,
)


def test_question_shows_fields_in_mode_order():
    mode = Mode(name="hard", show=["flag", "country"])
    q = build_question(CARD, mode)
    assert list(q.shown) == ["flag", "country"]
    assert q.shown["country"] == "France"
    assert q.accepted_answers == ["Paris"]
    assert q.card_id == "capital-fr"
    assert q.mode == "hard"


def test_missing_field_gives_clear_error():
    mode = Mode(name="with_map", show=["country", "map"])
    with pytest.raises(MissingFieldError, match="map"):
        build_question(CARD, mode)


def test_mode_must_show_something():
    with pytest.raises(ValueError):
        Mode(name="empty", show=[])


def test_answer_from_defaults_to_the_card_and_is_checked():
    assert Mode(name="m", show=["country"]).answer_from == "card"
    assert (
        Mode(name="m", show=["country"], answer_from="sentence").answer_from
        == "sentence"
    )
    with pytest.raises(ValueError):
        Mode(name="m", show=["country"], answer_from="map")


def test_skill_defaults_to_default_and_cannot_be_blank():
    from pydantic import ValidationError

    assert Mode(name="m", show=["country"]).skill == "default"
    with pytest.raises(ValidationError):
        Mode(name="m", show=["country"], skill="")
