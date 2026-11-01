"""Smoke test: proves both packages install and import. Gives CI something real to run."""

import hsk_trainer.cli
import quizkit


def test_packages_import():
    assert callable(hsk_trainer.cli.main)
    assert quizkit.__doc__
