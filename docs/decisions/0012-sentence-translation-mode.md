# 0012: Sentence translation modes, graded for the gist by the Claude judge

- **Status:** Accepted (2026-11-05)
- **In plain words:** Two new quiz modes. You see a Chinese sentence (`translate`: characters only; `translate_pinyin`: characters + pinyin) and type what it means in English. A sentence can be translated many ways, so there's no answer list: if your answer isn't close to the saved English, the Claude judge decides whether you **got the gist**. Without Claude, you mark yourself against the saved English.

## Context
- The user asked for it twice (FUTURE.md 2026-11-02, again 2026-11-04): "translate whole sentences, not just words".
- The pieces exist since M4: every banked sentence has its English (a reference answer); live sentences come with one (ADR 0011); the generic judge (ADR 0007) grades free text and already lets a sentence mode raise its 100-character limit.
- The judge's rubric is written for **words** and is strict ("too broad is wrong", "when unsure, say no"). Applied to sentences, it would mark most fair translations wrong.
- The user's choices (2026-11-05): **"gist is enough"**, and **two modes** (with and without pinyin), like `char` / `char_pinyin`.
- The bank is small (23 words, 40 sentences), so translate mode must also get sentences live.

## Decision
1. **Two modes, as config:** `translate` shows `sentence`; `translate_pinyin` shows `sentence` + `sentence_pinyin`. The expected answer is the **sentence's English**, not the word's meaning, so a mode also says where its answer comes from (`answer_from: "card" | "sentence"`, default `"card"`; the 4 current modes are unchanged).
2. **Which sentences:** the deck still deals words from the band (same `deck_builder`, `--n`, `--seed`); each word's sentence comes from `live_sentences` (bank or new, ADR 0011), so the bank keeps growing. A word with no sentence (bank empty and Claude unavailable) is **skipped** with a note, and isn't scored.
3. **Grading, two layers as for words:** the grader first (the reference English, typos allowed: a near-copy is instantly right); otherwise the judge.
4. **One judge, a second rubric:** `ClaudeJudge` gets an optional `rubric` (default: today's word rubric, so nothing changes for words). The sentence rubric, "the gist":
   - accept if the main meaning is understood: who does what, and any negation;
   - accept different wording, a missing small detail, and a tense or article slip;
   - reject a wrong main meaning, the opposite (a lost 不), a different subject or action, a fragment, or something unrelated;
   - when unsure, lean to accept *only* if the main meaning is clearly there.
   
   The rubric is part of the cache key. `max_chars` is 200 for these modes. It stays generic: the rubric names no language.
5. **Measured before trusted (ADR 0007 rule 5):** a new hand-labelled eval set of about 30 sentence answers (`tests/data/judge_eval_sentences.jsonl`): clear gists, near misses, lost negations, a wrong subject, fragments, an injection attempt. The user labels the borderline ones. The bar is the same as for words: ≥ 90% right, and **no** wrong "yes" on the must-reject cases (wrong meaning, opposite).
6. **Without Claude:** with `--no-judge`, or when the judge is off or failing, the quiz shows the reference English and asks **"Did you get the gist? (y/n)"**. Your answer is the score. This is just another `Judge` (a callable), so the engine doesn't change.
7. **After each answer:** show the reference English and the word the sentence was for (hanzi, pinyin, meaning), so each question also teaches the word. `translate` also shows the pinyin then.

## PR plan (small PRs, ADR → helper → block → wiring → docs)
1. This ADR.
2. Judge: the `rubric` option + the sentence eval set + an eval run (`/new-block` isn't needed: it changes an existing block, so test-writer → build → block-reviewer).
3. The modes + CLI wiring: `answer_from`, the sentence question, skipping a word with no sentence, the self-mark fallback, the after-answer display.
4. Docs: PLAN, SETUP_LOG, COURSE_MAP, build map.

## Why / alternatives considered
- **The current word rubric:** it would reject fair translations ("too broad", "unsure → no"). Gist needs its own rules.
- **A second judge block:** duplicates the cache, timeout, switch-off and injection guard. One option on the generic block is enough.
- **Strict "same meaning" or "close to the reference":** fairer to the saved English, but the user chose gist: the goal is understanding, not exact wording.
- **Pre-built sentence decks:** sentences don't exist for most words yet; live + bank (ADR 0011) fills them as you play.
- **Without Claude, show the answer only:** no score; self-marking keeps the quiz usable offline and honest.

## Consequences
- ✅ Real reading practice with any wording accepted, built from parts we already have.
- ✅ Words are unaffected: the default rubric and the 4 modes stay as they are.
- ⚠️ Most answers need a judge call (a sentence rarely matches the reference): about 6 s each with Haiku, and plan usage. Self-marking is the fallback.
- ⚠️ "Gist" is a judgment, so expect borderline calls. The eval set measures it; adjust the rubric after real play.
- ⚠️ The judge and live sentences both call Claude in this mode; `--no-judge --no-live` gives bank sentences + self-marking.
