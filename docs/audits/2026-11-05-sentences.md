# Sentence bank audit, 2026-11-05

**What:** the first `data-auditor` run (`.claude/agents/data-auditor.md`, M4 Step 6, issue #50) on the whole bank, `data/generated/sentences.jsonl`.
**Before:** 24 words, 44 sentences (the 20 trial words + 4 written live during the user's play).
**Result:** 4 flagged, 1 unsure. The user agreed all 4 were wrong and they were removed, leaving 23 words and 40 sentences (边 has none until live play writes new ones).
**Auditor tested first:** on the planted bank `tests/data/auditor_planted.jsonl` it caught 5/5 planted problems with the right check and flagged none of the 6 good sentences (answer key: `tests/data/auditor_planted_expected.md`).

## Flagged
| # | Word | Sentence | Check | Why | Decision |
|---|---|---|---|---|---|
| 1 | 百 | 我有一百个字。 "I have one hundred characters." | natural | Nobody "has" characters; a native speaker says 我会写一百个字 | removed |
| 2 | 边 | 他一边吃饭，一边看电视。 | level | Uses 边 only inside 一边……一边 ("while…"); 一边 is band 3, so a band-1 learner never sees 边 on its own | removed |
| 3 | 边 | 她一边说话，一边写字。 | level | Same as #2 | removed |
| 4 | 病 | 他有病，去医院看医生。 | natural | 他有病 usually means "he's crazy" (rude); "he's ill" is 他病了 | removed |

**Unsure, kept:** 不客气 · 谢谢！不客气。 (two speakers in one line; natural as a dialogue, Chinese and English match).

**No problems found with:** readings (都 dōu, 便宜 pián yi, 了 le, 上 shàng) or English.

**What it taught us:** flags 2–3 show a gap in the script checker (ADR 0009): it reads 一边 as 一 + 边, so the target word counts as "on its own" inside a harder compound. Logged in `docs/FUTURE.md`.

## Audited
爱 · 我爱我的妈妈。
爱 · 他爱喝茶。
八 · 我有八个朋友。
八 · 现在八点了。
爸爸 · 我爸爸在家。
爸爸 · 爸爸喜欢喝茶。
吧 · 我们去吧。
吧 · 你坐吧。
白天 · 白天我在学校。
白天 · 今天白天很热。
百 · 这本书一百块。
百 · 我有一百个字。
半 · 现在九点半。
半 · 我学习了半个小时。
包子 · 我喜欢吃包子。
包子 · 这个包子很好吃。
杯子 · 这个杯子很漂亮。
杯子 · 我的杯子在桌子上。
本 · 我有三本书。
本 · 这本书很好看。
边 · 他一边吃饭，一边看电视。
边 · 她一边说话，一边写字。
便宜 · 这个很便宜。
病 · 我的病好了。
病 · 他有病，去医院看医生。
不 · 我不想吃饭。
不客气 · 谢谢！不客气。
不客气 · 你说谢谢，我说不客气。
不要 · 你不要说话。
不要 · 我不要茶，我要水。
菜 · 这个菜很好吃。
菜 · 我想去买菜。
茶 · 我喜欢喝茶。
茶 · 你喝茶吗？
唱 · 她会唱很多歌。
超市 · 超市里有很多水果。
超市 · 我去超市买牛奶。
都 · 我们都是学生。
都 · 他们都很忙。
课 · 我们上午上汉语课。
三 · 我有三个孩子。
三 · 今天星期三。
做 · 妈妈在做饭。
做 · 你今天做什么？
