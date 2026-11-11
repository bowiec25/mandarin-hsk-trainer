# 0015: Sentence audits act on their own (no human approval)

- **Status:** Accepted (2026-11-11)
- **In plain words:** the example sentences Claude writes are checked by scripts (every sentence) and by the read-only `data-auditor` (at milestone ends and as the bank grows). Until now the user had to approve each removal the auditor suggested. From now on, **whatever the auditor flags is removed automatically** (unsure counts as remove), a dated report records it, and the user gets a one-line summary. Nobody approves sentences one by one.

## Context
- The rule came from M4 Step 6 (`CLAUDE.md`, `.claude/agents/data-auditor.md`, the playbook): "show the user its flags; remove only the sentences they agree with". No accepted ADR made a person the gate: ADR 0008 asked for a one-off spot-check at M4, and ADRs 0009–0010 point at the auditor for what scripts can't judge.
- Live sentences (ADR 0011) make the bank grow while you play: 4 new words in one short web session on 2026-11-11. A person ruling on every flag doesn't scale.
- The learner is learning Chinese, so they can't judge "is this natural?" better than the auditor anyway. On 2026-11-11 they were asked to rule on one flag (这个国很大。, unnatural) and on a capital letter in pinyin. Their answer: "we dont want a human approving sentences, how is that remotely scalable".
- Removing a sentence is cheap and safe. A word with no sentence is skipped (translate modes) or shown without one, and live sentences write new ones.

## Decision
1. **Scripts first.** Anything code can check stays a script check on every sentence before it's shown or saved (ADR 0002). When an audit finds a kind of mistake a script *could* catch (e.g. capitalised pinyin), it goes on the list for the script checker (`docs/FUTURE.md`), not on a person.
2. **The auditor acts.** Every sentence it flags (natural, english, reading, level, sense) is **removed**, and so is every "unsure". There's no "keep" verdict, and nobody approves removals. Pure formatting notes that aren't errors (e.g. pinyin capitals) are tidied in the same pass, and the bank is then loaded once, which re-checks every sentence with the scripts, so a slip while tidying can't get in.
3. **A record, not a question.** Each run is saved as `docs/audits/<date>-sentences.md` (flags, what was removed, the audited list), and the user gets a one-line summary in chat.
4. **When it runs:** unchanged. At each milestone end, and whenever the bank has grown by about 50 sentences since the last report ("only new").
5. **Its planted test stays** (`tests/data/auditor_planted*`): the auditor's instructions changed, so it is re-run, as `CLAUDE.md` says.

## Why / alternatives considered
- **Keep the human gate:** doesn't scale with live sentences, and asks a learner to judge Chinese.
- **Fix a wrong reading instead of removing the sentence:** the auditor often names the right pinyin, but fixing it is a hand edit to Claude's data. Removing is simpler, and a new sentence (checked by the scripts) replaces it.
- **Only remove "high-confidence" flags, ask about the rest:** still a person in the loop, now for the hardest cases, which are the ones a learner can least judge. Removing is cheap, so removing them all is safer.
- **No auditor, scripts only:** scripts can't tell natural Chinese from stilted Chinese (这个国很大 passes every script check).

## Consequences
- ✅ Audits scale with the bank. The user is never asked to judge data.
- ✅ A wrong sentence leaves the bank as soon as an audit sees it. A record stays for every removal.
- ⚠️ The auditor may remove a fine sentence (a false flag). Cost: one word briefly has fewer sentences, until live sentences write another.
- ⚠️ **A removed sentence can come back** (found by `/code-review`): nothing remembers removals yet, so Claude may write the same sentence again, and it passes the scripts again. Until a "removed list" checked by the bank exists (`docs/FUTURE.md`, next in line), the next audit catches it again.
- ⚠️ Between audits, a live sentence that passes the scripts but reads oddly can still be shown (as before, ADR 0011). Running the auditor automatically as a batch job, so the user doesn't have to start it, is in `docs/FUTURE.md`.
