"""Quiz score helpers."""


def percent_correct(correct: int, total: int) -> float:
    """Share of answers that were right, as a percentage from 0 to 100."""
    return correct / total * 10
