# Mandarin HSK Trainer

A terminal vocab trainer for **HSK 3.0, bands 1–3** (2026 revised syllabus, ~1,000 words). You get tested on Chinese characters and type the English meaning, with four levels of help:

| Mode | You see |
|---|---|
| `char` | 汉字 |
| `char_pinyin` | 汉字 + pinyin |
| `char_sentence` | 汉字 + an example sentence |
| `full` | 汉字 + pinyin + sentence + sentence pinyin |

> **Status:** early setup (milestone M0). The quiz is not playable yet. See [docs/PLAN.md](docs/PLAN.md) for the roadmap.

## Getting started

Requires [uv](https://docs.astral.sh/uv/) (it installs the right Python, 3.13, for you).

```bash
git clone https://github.com/bowiec25/mandarin-hsk-trainer.git
cd mandarin-hsk-trainer
uv sync                      # install everything
uv run hsk                   # run it
```

For features that use Claude (from M4), copy `.env.example` to `.env` and add your `ANTHROPIC_API_KEY`.

## Development

```bash
uv run ruff check            # lint
uv run ruff format           # format
uv run pytest                # tests
```

Every change goes through a pull request, and CI must pass before it can merge.

## Design

The app is built from small reusable **blocks**. Generic quiz parts live in `src/quizkit/`, and Mandarin-specific parts live in `src/hsk_trainer/`, so the same engine can power other quizzes later.
Simple, checkable jobs are plain scripts. Jobs that need language judgment (like writing example sentences) use a Claude agent, and a script checks its output.

- [docs/PLAN.md](docs/PLAN.md): full plan and progress
- [docs/SETUP_LOG.md](docs/SETUP_LOG.md): every setup step explained in plain English
