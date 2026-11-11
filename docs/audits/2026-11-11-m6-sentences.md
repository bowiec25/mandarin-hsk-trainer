# Sentence bank audit: 2026-11-11 (end of M6, whole bank)

> **In plain words:** the milestone-end audit (CLAUDE.md rule). The read-only `data-auditor` checked every sentence in the bank. It flagged nothing, so nothing was removed (ADR 0015: flagged sentences would be removed without asking anyone).

- **Bank:** `data/generated/sentences.jsonl`: 27 words (all band 1), **47 sentences**. Unchanged since this morning's audit (`2026-11-11-sentences.md`).
- **Removed list:** `data/generated/sentences_removed.json` holds 1 sentence (国: 这个国很大。); it isn't in the bank, so it wasn't audited again.
- **Checks:** natural, English, reading, level, sense (see `.claude/agents/data-auditor.md`).
- **Flags:** 0. **Unsure:** 0. **Formatting:** none (the bank is consistent: lowercase pinyin, full-width punctuation, dictionary tones).
- **Notes from the auditor (no action):**
  - Readings checked and right: 便宜 pián yi (cheap), 都 dōu, 吧 ba, 哪 nǎ, 上 shàng, 个 gè.
  - Senses checked: 做 in 做饭 = "cook", 菜 in 买菜 = food / vegetables, 人 in 中国人, 三 in 星期三: all taught meanings.
  - Every compound used (上午, 汉语, 孩子, 牛奶, 水果, 漂亮, 桌子, 小时, 老师, 再见, 说话, 星期, 中国, 学校, 学生, 学习, 朋友, 喜欢, 现在, 这里, 做饭) is band 1.
- **Result:** no change to the bank.

## Audited
爱 · 我爱我的妈妈。 · 他爱喝茶。
八 · 我有八个朋友。 · 现在八点了。
爸爸 · 我爸爸在家。 · 爸爸喜欢喝茶。
吧 · 我们去吧。 · 你坐吧。
白天 · 白天我在学校。 · 今天白天很热。
百 · 这本书一百块。
半 · 现在九点半。 · 我学习了半个小时。
包子 · 我喜欢吃包子。 · 这个包子很好吃。
杯子 · 这个杯子很漂亮。 · 我的杯子在桌子上。
本 · 我有三本书。 · 这本书很好看。
便宜 · 这个很便宜。
病 · 我的病好了。
不 · 我不想吃饭。
不客气 · 谢谢！不客气。 · 你说谢谢，我说不客气。
不要 · 你不要说话。 · 我不要茶，我要水。
菜 · 这个菜很好吃。 · 我想去买菜。
茶 · 我喜欢喝茶。 · 你喝茶吗？
唱 · 她会唱很多歌。
超市 · 超市里有很多水果。 · 我去超市买牛奶。
都 · 我们都是学生。 · 他们都很忙。
国 · 你是哪国人？
课 · 我们上午上汉语课。
人 · 这里有很多人。 · 他是中国人。
三 · 我有三个孩子。 · 今天星期三。
谢谢 · 谢谢你！ · 谢谢老师，再见。
有点儿 · 今天有点儿冷。 · 我有点儿忙。
做 · 妈妈在做饭。 · 你今天做什么？
