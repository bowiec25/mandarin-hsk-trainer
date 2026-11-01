"""Smoke test: proves the package installs and imports. Gives CI something real to run."""

import mandarin_hsk_trainer


def test_package_imports():
    assert callable(mandarin_hsk_trainer.main)
