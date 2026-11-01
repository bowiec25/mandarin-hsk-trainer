# 0004: Word list = the 2026 HSK 3.0 syllabus, from `complete-hsk-vocabulary` (pinned)

- **Status:** Accepted (2026-11-02). Replaces the word counts in [0001](0001-hsk3-standard.md)
- **In plain words:** we teach the words from the **2026 revised HSK 3.0 syllabus** (bands 1–3 = about **1,000 words**), downloaded from one open-source list that we're allowed to use, **locked to one exact version** so it never changes under us.

## Context
ADR 0001 chose HSK 3.0, bands 1–3, using the 2021 counts (~500 / 1,272 / 2,245). While choosing a source we found that a **revised syllabus** (published November 2025, the version tested from 2026) cut the counts to **300 / 500 / 1,000** words (cumulative). The user plans to follow the current exam, so they chose the revised one.
We also need a source that is complete, has pinyin + English, and is **licensed** for re-publishing in a public repo.

## Decision
| What | Choice |
|---|---|
| Syllabus | **HSK 3.0, 2026 revised syllabus**, bands 1–3 |
| Source | [`drkameleon/complete-hsk-vocabulary`](https://github.com/drkameleon/complete-hsk-vocabulary) (its 2021 data comes from [`elkmovie/hsk30`](https://github.com/elkmovie/hsk30)) |
| Exact version | commit **`7ac65bf1a6387d35f1ade478906172a19311c7f9`** (2026-03-23) |
| Files | `wordlists/exclusive/newest/1.json`, `2.json`, `3.json` (*exclusive* = each word appears once, at the band where it's first introduced) |
| Licence | **MIT** (source and upstream). We keep their copyright notice next to the data |
| Checksums | recorded by the `fetcher` block (M2 piece 4), so a changed file is caught |

**Counts at the pinned version:**
| Band | New words | Cumulative | Official target | Gap |
|---|---|---|---|---|
| 1 | 294 | 294 | 300 | −2% |
| 2 | 197 | 491 | 500 | −2% |
| 3 | 487 | **978** | 1,000 | −2% |

The word-count test (M2 piece 6) checks these exact numbers, **and** that each band stays within 5% of the official target.

Each entry already has what the quiz needs: hanzi (`s`), pinyin (`f[].i.y`), English meanings (`f[].m`), plus part of speech (`p`) and frequency rank (`q`).

## Why / alternatives considered
- **2021 lists (`wordlists/…/new/`)**: more established, but no longer the syllabus being tested.
- **Both, as two decks**: more work now. Our `Card.level` + source design means a 2021 deck can be added later as a data-only change.
- **Official PDFs**: the authoritative source, but they'd need manual extraction, and they have no English meanings.
- **Other GitHub lists**: smaller, unlicensed or not updated for 2026.

## Consequences
- ✅ Matches the current exam. The total is smaller (978 words), so it's quicker to master.
- ✅ Pinned SHA + checksums = the same data every time, and changes are visible in PRs.
- ⚠️ The 2026 lists were added by a **community contributor** (Feb 2026), not taken directly from the official PDF. They match the official totals to within ~2%, but individual words might be wrong. Mistakes found later get fixed in our normalizer, or reported upstream.
- ⚠️ Sources disagree on the first exam date under the new syllabus (July vs December 2026). That doesn't change this decision.
- 🔁 To update the data: write a new ADR or a PR that bumps the SHA, with a diff of which words changed.
