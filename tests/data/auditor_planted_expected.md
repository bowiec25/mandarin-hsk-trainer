# data-auditor: the planted test (answer key)

How to run it (by hand, it needs Claude): ask Claude Code to *"run the data-auditor on tests/data/auditor_planted.jsonl"*, then compare its report with this key. Re-run it after any change to `.claude/agents/data-auditor.md`.

**Pass bar:** all 5 planted problems flagged, each with the right check (another check as well is fine), and none of the 6 good sentences marked **remove**. Marking a good one as **unsure** is noted, not a fail.

## Must be flagged (one per check)
| Word | Sentence | Check | Why it's wrong |
|---|---|---|---|
| 吃 | 我很吃饭。 | natural | 很 doesn't go with a plain action verb like 吃饭 |
| 爸爸 | 我爸爸在家。 / "My dad is at school." | english | 在家 = at home, not at school |
| 长 | 他的头发很长。 (… hěn zhǎng) | reading | 长 here = long → cháng; zhǎng = to grow |
| 人 | 那个男人是老师。 | level | 男人 is a band-3 word in a band-1 word's sentence (the script reads it as 男 + 人) |
| 走 | 他爷爷去年走了。 | sense | 走 = "passed away" here; the quiz teaches walk / go / leave |

## Must not be marked remove (good)
爱 我爱我的妈妈。 · 八 我有八个朋友。 · 吧 我们去吧。 · 坐 你坐吧。 · 爸爸 爸爸喜欢喝茶。 · 长 这条路很长。 (cháng, correct)
