# Mandarin HSK Trainer

A vocab trainer for **HSK 3.0, bands 1–3** (2026 revised syllabus, 978 words). You see Chinese and type the English meaning, in the terminal or in a local web page. It remembers how you're doing and brings back the words you need (Leitner boxes).

| Mode | You see | You type |
|---|---|---|
| `char` | 汉字 | the word's meaning |
| `char_pinyin` | 汉字 + pinyin | the word's meaning |
| `char_sentence` | 汉字 + an example sentence | the word's meaning |
| `full` | 汉字 + pinyin + sentence + its pinyin | the word's meaning |
| `translate` | a Chinese sentence | what it means (the gist is enough) |
| `translate_pinyin` | a Chinese sentence + pinyin | what it means |

> **Status:** v1 done (milestones M0–M6, 2026-11). Ideas for later: [docs/FUTURE.md](docs/FUTURE.md).

## Getting started

Requires [uv](https://docs.astral.sh/uv/) (it installs the right Python, 3.13, for you).

```bash
git clone https://github.com/bowiec25/mandarin-hsk-trainer.git
cd mandarin-hsk-trainer
uv sync                                  # install everything

uv run hsk web                           # the quiz + your stats in your browser
uv run hsk quiz --band 1 --mode char     # or in the terminal (--help for all options)
uv run hsk stats                         # how you're doing
```

Your progress is saved in `data/progress.db` (on your computer only, not in git).

**Claude (optional):** two features ask Claude while you play: the **judge** (decides answers the list doesn't have) and **live sentences** (new example sentences). They use the [Claude Code](https://claude.com/claude-code) `claude` command under your own subscription, with no API key. Without it, or with `--no-judge` / `--no-live`, the quiz still works: you mark yourself and get sentences from the saved bank.

## Development

```bash
uv run ruff check            # lint
uv run ruff format           # format
uv run pytest                # tests (Claude is never called in tests)
```

Every change goes through a pull request; CI must pass before it can merge into `main`.

## Design

The app is built from small reusable **blocks**, each a folder with a `SPEC.md`, its code and its tests.
- `src/quizkit/`: **generic** quiz parts (grader, deck, engine, judge, progress). Nothing Mandarin-specific: [examples/capitals_quiz.py](examples/capitals_quiz.py) is a whole quiz built from them (`uv run python examples/capitals_quiz.py`).
- `src/hsk_trainer/`: the **Mandarin** parts (word list, answers, sentences, pinyin) and the front ends (terminal, web).
- Checkable jobs are plain scripts. Jobs that need language judgment (writing answers and sentences) use a Claude agent, and a script checks its output.

## Docs

- [docs/build-map/index.html](docs/build-map/index.html): the build map, the whole project on one page (download it and open it in a browser)
- [docs/PLAN.md](docs/PLAN.md): the plan and progress, milestone by milestone
- [docs/SETUP_LOG.md](docs/SETUP_LOG.md): every step explained in plain English
- [docs/decisions/](docs/decisions/): why each big choice was made (ADRs)
- [docs/PLAYBOOK.md](docs/PLAYBOOK.md): a checklist for starting the next project this way
- [docs/FUTURE.md](docs/FUTURE.md): ideas for later
