"""A toy capitals quiz built ONLY from quizkit: the M3 reuse check.

Run it:  uv run python examples/capitals_quiz.py
If this works without touching hsk_trainer, the generic blocks really are generic.
Its own cards and its own mode: everything else is quizkit as-is.
"""

import sys

from quizkit.blocks.deck_builder import build_deck
from quizkit.blocks.engine import Attempt, run_quiz
from quizkit.models import Card, Question
from quizkit.modes import Mode

# level 1 = Europe, level 2 = rest of the world (any meaning a quiz likes)
CARDS = [
    Card(id="fr", fields={"country": "France"}, answers=["Paris"], level=1),
    Card(id="de", fields={"country": "Germany"}, answers=["Berlin"], level=1),
    Card(id="it", fields={"country": "Italy"}, answers=["Rome", "Roma"], level=1),
    Card(id="es", fields={"country": "Spain"}, answers=["Madrid"], level=1),
    Card(id="jp", fields={"country": "Japan"}, answers=["Tokyo"], level=2),
    Card(id="au", fields={"country": "Australia"}, answers=["Canberra"], level=2),
    Card(id="ca", fields={"country": "Canada"}, answers=["Ottawa"], level=2),
    Card(id="cn", fields={"country": "China"}, answers=["Beijing", "Peking"], level=2),
]

COUNTRY = Mode(name="country", show=["country"])
N = 5  # questions per quiz


def ask(question: Question) -> str | None:
    try:
        return input(f"Capital of {question.shown['country']}? ")
    except EOFError:  # Ctrl-C needs nothing: run_quiz treats it as a quit
        print()
        return None


def tell(attempt: Attempt) -> None:
    g, right = attempt.grade, attempt.question.accepted_answers[0]
    if g.correct and g.typo:
        print(f"✅ close enough: {right}")
    elif g.correct:
        print("✅")
    else:
        print(f"❌ {right}")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):  # Windows pipes can't print ✅ otherwise
        sys.stdout.reconfigure(encoding="utf-8")
    questions = build_deck(CARDS, COUNTRY, n=N)
    result = run_quiz(questions, ask=ask, tell=tell)
    if not result.finished:
        print(f"Stopped after {result.answered} of {result.total}.")
    print(f"Score: {result.correct}/{result.answered}")


if __name__ == "__main__":
    main()
