# 📘 New Project Playbook

**What this is:** every safety net, check and Claude setting we used, explained simply, so you can **copy them into any new project**.
Each item says: **what it is**, **why you want it**, **what to ask Claude for**, and **where it lives** in this repo, so you can copy it.

> **How to use it:** start a new project, open this file, and work down the checklist. Or just tell Claude:
> *"Set up this project using the playbook at github.com/bowiec25/mandarin-hsk-trainer/blob/main/docs/PLAYBOOK.md"*

**Contents:** [🎓 Lessons by milestone](#-lessons-by-milestone) · [✅ Checklist](#-quick-checklist) · [🚦 How strict is each thing?](#-how-strict-is-each-thing) · then one section per item.

---

## 🎓 Lessons by milestone

The short version: what each stage built, and **what to think about next time**. A new entry gets added at the end of every milestone.

### 🗺️ Planning (before any code)
**Built:** the plan in `docs/PLAN.md`, with a "Where we are" checklist at the top.
**Think about next time:**
1. **Write down exactly what "done" looks like**, e.g. our table of the 4 quiz modes. Everything else followed from it.
2. **Split the app into small parts with one job each** (blocks) before writing code.
3. **Decide upfront what's a script and what's AI.** It shapes cost, speed and testing.
4. **Plan in milestones**, each one = an issue + small PRs, and keep a progress checklist you can glance at.
5. **Say how you want to work** (e.g. "small steps, explain simply, stop often"), and put it in CLAUDE.md or memory so it sticks.

### 🧱 M0: Setup
**Built:** tools installed, GitHub login, a Python project, git, safety files, a public GitHub repo with CI, protected `main`, squash-only merges.
**Think about next time:**
1. **Separate "once per computer" from "every project".** Logins and your git name are per computer. Everything else is per project.
2. **Protect secrets before the first commit** (`.gitignore`, `.env.example`, noreply email).
3. **Check what a tool actually did.** `uv init` quietly used `master`, and we only noticed because we checked.
4. **Have Claude look things up rather than guess:** versions, tags, plan limits. A guessed version broke the first CI run.
5. **Know your platform's limits.** Free GitHub = branch protection on public repos only. CI files need the `workflow` permission.
6. **Test your safety nets.** We tried pushing straight to `main`, and it was rejected.

### 🧰 M1: Foundations
**Built:** decision records, data shapes, permissions + hooks, the `/new-block` skill, and 2 helper subagents.
**Think about next time:**
1. **How strict is it?** 🔴 hard rule / 🟠 automatic / 🔵 guidance / ⚪ habit. If it matters, make it 🔴. Only GitHub settings stop *everyone*.
2. **Script vs AI applies to your own tools too:** Claude asks the questions, and a script makes the files.
3. **Every helper needs a trigger.** Plan *when* each skill, subagent or hook runs, and make it visible (e.g. the verdict pasted into the PR).
4. **Re-check the plan before each step ("Still the right thing?").** It changed 4 of 6 pieces.
5. **Test first, then try to break it on purpose** (`cat .env`, a messy edit, planted mistakes).
6. **Give helpers only the tools they need.** A reviewer that *can't* edit is safer than one told not to.
7. **Small steps, small PRs:** one piece = one branch = one PR.

### 📥 M2: Data in
**Built:** the data source chosen and pinned (ADR 0004), a stronger starter test for blocks, the `fetcher` (download + fingerprint check), the `normalizer` (raw lists → 978 quiz cards), and a word-count test on the real data.
**Think about next time:**
1. **Research the data before building anything.** The original plan had the wrong word list and wrong counts.
2. **Pin your data source** (exact version + fingerprints) and keep the licence next to it.
3. **Look at the real data before writing the SPEC.** My own notes had the wrong field names, and two surprises (multi-reading words, an empty `pos`) only showed up by looking.
4. **Ask "does this serve the real goal?"** The HSK-exam check showed what v1 trains (reading) and what it doesn't (listening), and we wrote down the future idea instead of building it now.
5. **Use a fresh reviewer each round.** Each round found something the previous one missed.
6. **A subagent flags questions, you check them against reality.**
7. **Test the real committed data, not just the code.** Exact counts + "re-running gives the same file" means CI catches accidents.

### 🎮 M3: First playable quiz
**Built:** the code review setup (`/code-review` before every PR + the Claude GitHub app on every PR), the `grader` and `cedict_cleaner` (marking answers), the `deck_builder` (picking words) and `engine` (running the quiz), built in parallel with a git worktree, the `hsk quiz` CLI, and a toy capitals quiz proving the generic parts are reusable.
**Think about next time:**
1. **Prove "reusable" with a second, tiny user, and lock it in with a test.** The capitals quiz needed zero changes to `quizkit` to run (and showed one weak spot, see 2); a scan test now fails if `quizkit` ever imports Mandarin code. Calling something generic isn't proof.
2. **Fix a shared weak spot where it lives, not in each user.** The CLI first worked around a late-Ctrl-C bug with its own loop; the capitals quiz showed every new quiz would have to copy that. Fixing it once in the engine removed both workarounds. A second user is what makes this kind of thing visible.
3. **The front door takes longer than you'd think.** Most CLI bugs were at the edges: Ctrl-C, Windows text encoding, CI colouring the output, showing "havent" instead of "haven't". Test them with scripted typing, and run each fix's test against the old code to see it fail.
4. **Two review layers, and check that they really ran.** Locally, `/code-review` was the deep one (7–8 findings per PR); the GitHub review was lighter. Green on GitHub isn't the same as reviewed: read the log, and test the review once with a planted bug.
5. **Test blocks together on the real data.** The cleaner and grader each passed their own tests; together, on all 978 cards, they found a bug (给 = "to").
6. **Rules are a stopgap for language.** The play-test confirmed it: marking answers needs judgment. Shipping with rules was right (you can study now), but plan the agent and collect the cases it gets wrong.
7. **Parallel sessions pay off for independent parts.** Two blocks in the time of one, using a worktree, as long as only one session edits the shared docs.

### ✍️ M4: Sentences (first AI agent)
**Built:** "Still the right thing?" as a gate (issue form + a CI check on the PR description); the first agents, all via `claude -p` under the subscription: `answer_writer` (one answer list, ADR 0006), a **generic Claude judge** with an eval set (ADR 0007), `sentence_writer` with Claude-written pinyin checked by script (ADR 0010); the script checkers `sentence_validator` (ADR 0009) and the pinyin check; **live sentences + a growing bank** (`sentence_bank`, `live_sentences`, ADR 0011); and a read-only **`data-auditor`** subagent for the data. 881 tests, ADRs 0005–0011.
**Think about next time:**
1. **Re-planning is a feature: make it a gate.** "Still the right thing?" changed the plan five times in M4 (answer agent first, judge moved in from M5, one answer list, a generic judge, live sentences instead of a batch). Each change got a new ADR; old ADRs were marked superseded, not rewritten, so the history stays readable.
2. **Measure before you trust.** Counting showed the "safe" fallback list was mostly junk; a 20-word trial found wrong pinyin; one real call (4 s, 2,700 tokens) settled the model; one real quiz showed how often the strict checker rejects. Small, cheap measurements beat guesses every time.
3. **Layer the checks on AI output.** Force the reply's shape (`--json-schema`) → script checks for everything code can decide (words, band, pinyin) → a read-only AI reviewer for what it can't (natural? right meaning?) → what it flags is removed, written down (`docs/audits/`). (Until 2026-11-11 a person made the call; ADR 0015 dropped that gate.) Each layer caught things the others missed.
4. **Judgment pieces need their own tests, kept in the repo.** pytest can't (and shouldn't) call Claude, so the judge has a hand-labelled eval set and the auditor a planted bank with an answer key. Re-run them whenever their prompt changes.
5. **Split agent work into small PRs, planned up front.** The judge PR did four jobs and dragged; Step 5 was seven small PRs (ADR → checker → writer → pinyin → ADR → bank → live), each reviewable on its own.
6. **Live AI: test the slow and late paths.** Background threads only call Claude, file writes stay on the main thread, and there's always a fallback, a switch-off and an off flag. The one real crash the review found was a late error arriving after the quiz had moved on.
7. **Explain what the user will see, not how it works.** The trickiest moments were jargon ("the checker rejected the reply"). Say "Claude wrote it, our script checked it, it failed because 每 is band 2" and ask one question at a time.

### 🔤 Between M4 and M5: sentence translation
**Built:** the `translate` and `translate_pinyin` modes (ADR 0012): one generic judge with a second rubric (`GIST_RUBRIC`) and its own 33-case eval set, a generic `prepare` hook in the engine, a self-mark fallback. 5 small PRs (#55–#58 + docs). 955 tests.
**Think about next time:**
1. **When an ADR reuses a block in a new way, check that block's inputs and timing, not just its features.** ADR 0012 reused the sentence modes' live sentences, but there the sentence was a hint; in translate it is the answer, and the engine needed every answer before the quiz started. Reading the engine's code while writing the ADR would have caught it.
2. **Let the user label the borderline cases.** "Gist" was vague until you labelled 6 tricky answers; your labels became a rule in the prompt ("a missing key fact is wrong") and the eval checks it.
3. **A new setting must not change the old behaviour, so prove it.** The default rubric keeps the prompt byte for byte the same (a test compares against a hand copy), old cache lines are pinned, and the word eval was re-run.
4. **Grading settings depend on the task.** Typo forgiveness is right for one word and wrong for a sentence ("I do like tea" is 2 letters from "I don't like tea"). The code review found it.

### 🧠 M5: Learning smarts
**Built:** progress and spaced repetition (ADR 0013): 2 new generic blocks (`progress_store` = the filing cabinet, `leitner` = the teacher who moves cards), a schedule input for `deck_builder` (the dealer), glue in `quizkit/progress.py`, saving in `hsk quiz`, and `hsk stats`. 6 small PRs (#61–#66) + docs. 1148 tests.
**Think about next time:**
1. **Keep the storage dumb and the rule separate.** The cabinet only files notes; the teacher decides the box. So the rule (one pure function) can change after real use without touching saved answers.
2. **A safety net only covers what it can reach.** The conftest fixture kept tests away from the real progress file, but a test that starts the program in a **separate process** slipped past it and wrote to the real file. Check for subprocess tests whenever you add a "never touch real data" net.
3. **Save before you show.** Code that runs after a result is shown can be interrupted (Ctrl-C); save first, then print. The code review found it.
4. **Make "the same seed, the same deck" survive a new feature.** The dealer shuffles once for both paths, so a first quiz on an empty progress file deals exactly what it dealt without one; a test proves it for many seeds.
5. **A "look only" command must really only look.** `hsk stats` first set up an empty progress file just by opening it. Read-only commands: check they never create or change a file, and test it.
6. **Count "couldn't check" apart.** An answer nobody could mark shouldn't count as wrong in your accuracy, or move a box; show it separately so nothing is hidden.
7. **Split a step when it grows.** "Leitner + dealer" and "CLI + stats" were each one PR in the plan; each became two, and each review stayed small.

### 🌐 M6: Web UI
*(added when M6 is done)*

---

## ✅ Quick checklist

**Once per computer** (already done on this PC)
- [ ] Tools installed: `git`, `gh` (GitHub CLI), `uv` (Python)
- [ ] `gh auth login` (include the `workflow` permission)
- [ ] Git name + **noreply** email set
- [ ] (Optional) `git config --global init.defaultBranch main`

**Every new project**
*(🔴 hard rule · 🟠 automatic · 🔵 guidance · ⚪ habit, explained in "How strict is each thing?" below)*
- [ ] 1. Project + git started on `main`
- [ ] 2. 🔒 Secrets protected (`.gitignore` 🟠, `.env.example` ⚪, push protection 🔴)
- [ ] 3. ✅ Checks installed: lint, format, tests (🔵 locally)
- [ ] 4. 🧑‍⚖️ CI on GitHub runs the checks (🔴 once `main` is protected)
- [ ] 5. 🛡️ `main` protected + squash-merge + auto-delete branches (🔴)
- [ ] 6. 🤖 `CLAUDE.md` briefing note (🔵)
- [ ] 7. 🤖 Claude permissions: allowlist + deny (🔴, Claude only)
- [ ] 8. 🤖 Hooks: secrets lock 🔴 + auto-format 🟠 (Claude only)
- [ ] 9. 📝 Docs: README, decision records, PR template (⚪)
- [ ] 10. 🔁 The working routine: issue → branch → PR → merge (⚪, but 🔴 enforced at merge)
- [ ] 11. 🤖 Skills for repeated jobs, e.g. `/new-block` (🔵, with the mechanical part in a script)
- [ ] 12. 🤖 Subagents for fresh-eyes checks, e.g. a read-only reviewer (tools 🔴, triggers 🔵)
- [ ] 13. 🤖 Code review: `/code-review` before each PR (🔵) + Claude GitHub app on every PR (🟠, advice only)

---

## 🚦 How strict is each thing?

Some of these **physically stop** a mistake. Others are just **instructions or habits** that someone has to follow. Know which is which.

| Level | Meaning | Can it be ignored? |
|---|---|---|
| 🔴 **Hard rule** | A machine **blocks** the action | No (only by changing the setting itself) |
| 🟠 **Automatic** | Runs by itself and **fixes** things, but doesn't block | Not usually, but it only covers what it's set up for |
| 🔵 **Guidance** | Instructions Claude **reads and normally follows** | Yes: Claude can miss or misjudge it |
| ⚪ **Habit** | Good practice **people** choose to do | Yes, easily |

### The full list
| Thing | Strictness | Enforced by | When it kicks in | Applies to | ⚠️ Limits |
|---|---|---|---|---|---|
| `main` protection (PR + CI required) | 🔴 | GitHub | Every push or merge to `main` | **Everyone**, incl. you (admins included) | A repo admin can switch it off in Settings |
| Squash-only, auto-delete branches | 🔴 | GitHub | When merging | Everyone | Same as above |
| Push protection (API keys) | 🔴 | GitHub | Every push (public repos) | Everyone | Only spots *known* key formats; you can override online |
| "Block pushes that expose my email" | 🔴 | GitHub | Every push | You | Has to be ticked in GitHub settings |
| `deny` permission (`Read(./.env)`) | 🔴 | Claude Code | Every time Claude uses that tool | **Claude only** | Covers only the listed tool (Read), so it can't stop shell commands. That's why we added the hook |
| Secrets-lock hook | 🔴 | Claude Code (our script) | **Before** every Claude tool use | **Claude only** | Only blocks what the script recognises; project-only |
| Plan mode | 🔴 | Claude Code | While it's switched on | Claude only | Only if **you** turn it on (Shift+Tab) |
| "Ask before acting" (anything not on `allow`) | 🔴* | Claude Code | Every tool use | Claude only | *Depends on the permission mode: some modes ask less. `deny` and hooks still apply in every mode |
| CI checks on GitHub | 🟡 → 🔴 | GitHub | Every push and PR | Everyone | On its own it only *reports* ❌. It **blocks** only because `main` protection requires it |
| `.gitignore` (hides `.env`) | 🟠 | git | When files are added | Everyone | `git add -f` forces a file in anyway |
| Auto-format hook | 🟠 | Claude Code (our script) | **After** Claude edits a `.py` file | **Claude only** | Your *own* edits in VS Code aren't tidied, but CI catches them |
| `allow` list | (loosens) | Claude Code | Every tool use | Claude only | Makes things *less* strict: only list safe read/test commands |
| Subagent **tool limits** (reviewer can't edit) | 🔴 | Claude Code | Whenever the subagent runs | That subagent | Only as strict as the tool list: "only write in tests/" is just 🔵 |
| Subagent **triggers** (skill steps, CLAUDE.md rule) | 🔵 | Claude following instructions | Building a block | Claude only | Not forced. The PR checkbox + pasted verdict lets you check it happened |
| `/code-review` before each PR | 🔵 | Claude (CLAUDE.md rule + PR checkbox) | Before opening a PR | Claude only | Not forced; it's advice, not a gate |
| Claude review on GitHub | 🟠 | GitHub Action (`claude-code-review.yml`) | Every PR open + push | Every PR | Comments only, doesn't block; token expires yearly |
| Skills (`/new-block`) | 🔵 | Claude following SKILL.md | When you type the command (or Claude spots a match) | Claude only | Not enforced, so the file-making is done by a tested script |
| `CLAUDE.md` rules | 🔵 | Claude reading it | Start of every session | Claude only | Not enforced: Claude can forget or misjudge. Make anything important a 🔴 rule or hook |
| Running ruff/pytest locally | 🔵 / ⚪ | Claude (per CLAUDE.md) or you | When someone runs them | Whoever runs them | Nothing forces it locally. CI is the real gate |
| ADRs, PR template | ⚪ | People | When writing PRs / decisions | Everyone | Just a form to fill in |
| "Still the right thing?" in issues + PRs | ⚪ → 🔴 | GitHub (issue form + CI check) | Each issue and PR | Everyone | Proves an answer was written, not that it's good. `gh issue create` skips the form, so the PR check is the real gate |
| Small steps | ⚪ | You + Claude | Each plan | Everyone | A habit. Agent work: plan the 4-PR split before building (M4 Step 4b lesson) |
| No real Claude in tests | 🟠 | pytest (`tests/conftest.py` autouse fixture) | Every test | Everyone running tests | Only covers `quizkit.claude`; a test can still start another program on purpose |
| Judge eval bar (≥ 90%, no wrong "yes") | ⚪ | You + Claude, by hand | Prompt or model change | The judge | Not in CI (needs Claude); a small set catches big problems, not rare ones |
| Sentence bank audit (`data-auditor`, acts on its own, ADR 0015) | 🔵 | CLAUDE.md rule; dated report in `docs/audits/` | Each milestone end, every ~50 new sentences | The sentence bank | Whatever it flags (or is unsure about) is removed, no human approval; you get a one-line summary. Live sentences are shown before any audit |
| Live sentence checks (script checks every sentence Claude writes during play) | 🔴 | Our code (`sentence_validator` + pinyin + English checks inside `write_one`) | Every live sentence, before it's shown or saved | The quiz | Only as good as the rules: they catch wrong words and pinyin, not an unnatural sentence (that's the `data-auditor`, Step 6) |

### The big lesson
- **If it really matters, make it 🔴.** E.g. "Don't read `.env`" in CLAUDE.md is only 🔵, but the deny rule plus the hook makes it 🔴.
- **Claude-only vs everyone:** permissions and hooks only control **Claude**. Only **GitHub** settings stop **everyone**, you included.
- **Layers beat one lock:** for secrets we have `.gitignore` 🟠 + deny 🔴 + hook 🔴 + push protection 🔴.

💬 **Ask Claude for a new project:** *"For each safety measure, tell me whether it's a hard rule, automatic, guidance or a habit, and who it applies to."*

---

## 1. Project + git

| What | Why | Ask Claude | Where here |
|---|---|---|---|
| `uv init --package` | Makes a proper Python project (settings file, `src/` folder, Python version pinned) | *"Set up a uv package project"* | `pyproject.toml`, `src/` |
| `git init` on branch `main` | Starts the change history | *"Start git on main"* | `.git/` |
| `.gitattributes` with `* text=auto eol=lf` | Stops Windows vs Linux line-ending warnings | *"Add a .gitattributes for LF endings"* | `.gitattributes` |

⚠️ **Watch out:** `uv init` starts git itself, on `master`. Check with `git branch --show-current`.

**Downloaded data:** if you check files against a fingerprint (checksum), add `data/raw/** -text` to `.gitattributes`. Otherwise git may change their line endings, and the fingerprints stop matching on another computer.

### 📥 Data you download (from M2)
| What | Why | Where here |
|---|---|---|
| **Pin the exact version** (a commit SHA, not "latest") | The data never changes under you | ADR 0004, `fetcher/__init__.py` |
| **Check size + fingerprint (SHA-256)** of every file | Catches changed or broken downloads | `quizkit/download.py` |
| **Write to a temp file, then swap it in** | Never leaves a half-written file | `quizkit/files.py` `write_atomically()` |
| **Look at the real data before writing the SPEC** | Notes and docs drift; surprises (197 multi-reading words, 11 with no `pos`) only show up by looking | M2 Step 5 |
| **A test on the real committed data**: exact counts + "re-running gives the same file" | CI catches accidental data changes and a stale generated file | `tests/test_word_counts.py` |
| **Check the licence** and keep it next to the data | Public repos re-publish the data | `data/raw/hsk3_2026/LICENSE` |
| **Tests use a fake downloader** | Fast, works offline, no flaky internet | `fetch=` parameter |

💬 **Ask Claude:** *"Download X pinned to version Y, check size + SHA-256, write atomically, and test it with a fake downloader."*

---

## 2. 🔒 Secrets

| What | Why | Where here |
|---|---|---|
| `.env` in `.gitignore` | Your API keys never get uploaded | `.gitignore` |
| `.env.example` (key **names**, no values) | Shows what's needed without leaking anything | `.env.example` |
| Commits use your **noreply** email | Keeps your real email off the internet | git config |
| GitHub → Settings → Emails → **"Block command line pushes that expose my email"** | A safety net if you forget | GitHub website |

**Ask Claude:** *"Make sure secrets can't be committed, and add a .env.example"*
**Public repos** also get GitHub **push protection** for free: it blocks pushes that contain API keys.

---

## 3. ✅ Checks (the "validation")

**These are scripts, not AI.** They just pass or fail.

| Check | Like… | Command |
|---|---|---|
| `ruff check` | A spell-checker for code | `uv run ruff check` |
| `ruff format` | Auto-format in Word | `uv run ruff format` |
| `pytest` | A checklist of "does it work?" | `uv run pytest` |

**Why:** Claude can **check its own work** and fix mistakes before you see them (the "verification loop").
**Ask Claude:** *"Add ruff and pytest as dev tools with a smoke test"*. Then later: *"Write the tests first, show me they fail, then write the code."*
**Where here:** `pyproject.toml` (dev deps), `tests/`

**Tips:**
- **Scan the real data before you design.** A 20-line throwaway script that counts the clutter types turns guesses into a table (M3 Step 2: 354 answers start with "to ", only 2 cards are truly stuck).
- **Test blocks together on the real data, not just alone on toy examples.** Running cleaner + grader over all 978 cards found a bug neither block's own tests could (给 = "to" got stripped to nothing).
- **Test interactive programs with scripted typing.** Typer's `CliRunner` (or feeding text to stdin) plays the whole program in a test: answers, quitting, errors. No real keyboard needed.
- **Prove a fix's test fails without the fix.** Run the new test against the old code once (`git stash` the fix). If it passes there, it isn't testing the bug.
- **Windows + Chinese: force UTF-8 output.** Printing 爱 through a pipe crashes on Windows (old code page). Call `sys.stdout.reconfigure(encoding="utf-8")` at start-up, and keep one test that runs the real program through a pipe.
- **Guard your architecture with a test.** If one package must never use another (here: generic `quizkit` must never import `hsk_trainer`), a short test can scan the imports and fail the build. Prove it once with a planted import.
- **CI can differ from your machine** (colours, OS, paths). When a test fails only on CI, copy CI's environment locally (here `GITHUB_ACTIONS=true`) to reproduce it before fixing. Tests that read terminal output should strip colour codes.
- **Show people the original words, not the computer's matching form.** The grader compares "havent"; the screen must say "haven't".
- **Rules vs judgment:** if hand-written rules keep growing to cover messy language, that's a sign the job wants an agent (offline, validated by a script). Rules can be a stopgap to ship sooner.
- **Measure what a fallback adds before keeping it.** "Keep the old list too, so nothing is lost" sounded safe; counting showed it added 1,434 mostly-wrong answers (M4 Step 4a, ADR 0006). A 20-line script beats a guess.
- **Retire old designs completely, then guard it.** Search for every mention, sort into delete / change / keep-as-history, delete outright (git keeps the old version), and add a test that fails if the old names come back (`tests/test_retired.py`).
- **When one part depends on another's file, both read it the same way.** The quiz and the answer writer share one reader + checker (`load_answers`), so they can't disagree on what a good file is.
- **Review the whole change, not only each block.** Per-block reviews said ✅; the branch-wide `/code-review` found the risk between blocks.
- **An AI judge needs an eval, not just tests.** Tests (with a fake Claude) prove the plumbing; only a hand-labelled set run against the real model shows how often it's *right*. Set the bar first (here: ≥ 90% and **no** wrong "yes"), run it twice (models aren't fully consistent), and pick the model by the numbers (M4 Step 4b: Haiku = Sonnet, so Haiku).
- **When two models disagree with your label the same way, look at the label.** Decide on purpose, write *why* next to it, and never relabel just to pass.
- **Make it impossible for tests to call the real AI.** One autouse fixture (`tests/conftest.py`) makes `claude` look "not installed"; a test that needs it fakes it.
- **Live AI in an app: check, fall back, switch off, save.** Every live sentence goes through the same script checks as the batch ones; if Claude is slow or failing the app falls back (bank, or nothing), switches live off after 2 failures, has an off flag (`--no-live`), and saves what passes so it needs Claude less over time. Ask ahead (while the user answers the previous question) to hide the wait (M4 Step 5, ADR 0011).
- **Background threads: they only call the AI; files stay on the main thread.** Then a slow or failed call can't corrupt a file. Test the "late" paths too: a result (or an error) that arrives after the app has moved on was the one real crash the review found.
- **Force the AI's reply shape, then check it anyway.** `claude -p --json-schema` + a pydantic model; a bad reply counts as "couldn't check", never as right. Treat user text inside the prompt as data (escape it, wrap it in tags) and test an injection attempt.

---

## 4. 🧑‍⚖️ CI (GitHub runs the checks)

| What | Why | Where here |
|---|---|---|
| A workflow file that runs the checks on every push and PR | Proves the code works on a **clean computer**, not just yours | `.github/workflows/ci.yml` |

**Ask Claude:** *"Add a GitHub Actions CI that runs ruff and pytest with uv"*
⚠️ **Watch out:**
- Your `gh` login needs the **`workflow`** permission to upload CI files (`gh auth refresh -s workflow`)
- Third-party actions: **pin to a commit SHA**, not a tag (a tag can be moved to different code)
- Ask Claude to **look up current versions**, not guess them

**Debug a failure:** `gh run view <id> --log-failed`

---

## 5. 🛡️ Protect `main`

| Setting | Plain meaning |
|---|---|
| Require a PR | Changes go on a side branch first |
| Require CI to pass | Can't merge if ❌ |
| Include admins | The rules apply to you too |
| No force-push / no delete | History can't be wiped |
| **Squash merge only** | One tidy commit per PR |
| **Auto-delete branches** | No leftover branches |

**Ask Claude:** *"Protect main: require a PR and passing CI, include admins, squash-only, auto-delete branches"*
⚠️ **Watch out:** on GitHub's **free plan**, branch protection only works on **public** repos (private needs Pro).
**Test it:** try pushing straight to `main`. It should be **rejected**.

---

## 6. 🤖 `CLAUDE.md`: the briefing note

| What | Why |
|---|---|
| A short file that Claude reads at the start of **every** session | Claude knows your rules and commands without being told again |

**Ask Claude:** run `/init`, then *"trim it to the essentials and add our rules"*
**Keep it short:** every line costs space in every session.

| File | For | Shared? |
|---|---|---|
| `CLAUDE.md` | Everyone on this project | ✅ committed |
| `CLAUDE.local.md` | Just you, this project | ❌ gitignored |
| `~/.claude/CLAUDE.md` | You, **all** projects | n/a |

**Edit it with** `/memory`. **Where here:** `CLAUDE.md`

---

## 7. 🤖 Claude permissions

**Where:** `.claude/settings.json` (shared) or `.claude/settings.local.json` (just you)

| Type | Plain meaning | Example here |
|---|---|---|
| `allow` | "Don't ask me every time" | `uv run pytest`, `git status`, `gh pr view` |
| `deny` | "Never do this" | `Read(./.env)` |
| *(everything else)* | Claude **asks** first | commit, push, merge, delete |

**Rule of thumb:** only `allow` commands that **read or test**. Anything that **changes, uploads or deletes** should still ask.
**Ask Claude:** *"Add an allowlist for safe read and test commands, and deny reading .env"*

---

## 8. 🤖 Hooks: automatic little scripts

**Rule vs hook:** a **rule** is a fixed allow/deny list. A **hook** is a **script that runs automatically** before or after Claude uses a tool. It can **block** something or **do** something.

| Hook | When | Does | Where here |
|---|---|---|---|
| Secrets lock | **Before** any tool (PreToolUse) | Blocks anything touching `.env`, even shell commands | `.claude/hooks/block_env.py` |
| Auto-tidy | **After** an edit (PostToolUse) | Runs `ruff format` on the edited `.py` file | `.claude/hooks/format_python.py` |

**Ask Claude:** *"Copy the block_env and format_python hooks from my mandarin-hsk-trainer repo, with their tests"*
**Check they're on:** `/hooks`
⚠️ **Watch out:**
- **Test hooks** like any code (here: `tests/test_hooks.py`), then **live-test** them (e.g. have Claude try `cat .env`)
- Blocking by "mentions `.env`" is too broad, because it stops Claude writing docs. Check the **file path** for file tools, and only the **command text** for shell commands.
- Hooks live in **project** settings, so other projects aren't affected

---

## 9. 📝 Docs

| File | For | Why |
|---|---|---|
| `README.md` | **Humans** | What it is, how to run it |
| `CLAUDE.md` | **Claude** | Rules and commands |
| `docs/decisions/` (ADRs) | Future you | "We chose X because Y", so it doesn't get undone by accident |
| `.github/pull_request_template.md` | Reviewers | Every PR: What / Why / How tested / Checklist |
| `docs/build-map/index.html` | You, at a glance | A picture of what exists now and how it grew |

---

## 10. 🔁 The routine (every change)

```
issue → plan mode → branch → small commits → PR → CI ✅ → squash-merge
```

| Step | How |
|---|---|
| Issue | *"Create an issue for X"* (`gh issue create`) |
| **Plan mode** | **Shift+Tab**. Claude only reads and plans until you approve |
| Branch | Claude makes it, and the status line shows which one you're on |
| PR | Claude writes it from the template; `Part of #N` / `Closes #N` |
| Merge | `! gh pr merge <n> --squash` (after a look at `gh pr diff <n>`) |

**Habits that pay off:**
- Every plan starts with **"Still the right thing?"**, and you can ask Claude to *"challenge this step"*. Make it hard to skip: a **required field in an issue form** (`.github/ISSUE_TEMPLATE/*.yml`, `required: true`) plus a **PR-description CI check** inside the required job (copy `.github/scripts/check_pr_body.py` + its test). Add `edited` to the `pull_request` trigger types so fixing the description re-runs CI
- Ask Claude to **verify** things rather than assume (e.g. look up versions, run the checks)
- One small step at a time, then stop and check
- **Split agent work into small PRs, and plan the split up front:** (1) helper changes, (2) the block with fake-AI tests, (3) wiring it into the app, (4) the eval + live runs. M4 Step 4b did all four in one PR and it ran long and got hard to follow

---

## 11. 🤖 Skills: your own slash commands

**Plain meaning:** a **skill** = **saved instructions** that become a command. You type `/new-block` and Claude follows the same steps every time, so you don't have to explain them again.
**Strictness:** 🔵 guidance. Claude follows the steps, but nothing *blocks* it from going off-script. So put the important, mechanical part in a **script** (🔴-ish reliable).

| Skill here | What it does | Where |
|---|---|---|
| `/new-block` | "Hire a new worker": asks 3 questions → a **script** makes the blank files → Claude helps fill in the job description (SPEC.md) → tests run | `.claude/skills/new-block/SKILL.md` + `src/quizkit/scaffold.py` |

**When to make a skill:** if you've **explained the same thing to Claude 2–3 times**, turn it into a skill.

**3 ways to make one:**
| Way | When |
|---|---|
| ⭐ *"Turn what we just did into a skill called /X"* | **The best way:** do the task once by hand, then save it |
| *"What skills would help in this project?"* | You're not sure what would help |
| The **`skill-creator`** skill | Bigger skills: it helps write, test and improve them |
| Write `SKILL.md` yourself | It's just a text file with instructions |

**The trick that makes skills reliable: skill + script**
- ✍️ **Claude (the skill)** does the *thinking*: asking questions, drafting text
- 🖨️ **A script** does the *mechanical* part: making files, always identical, with tests
- That's ADR 0002 (script vs agent) applied to your own tools

**What makes a good skill:**
- A clear **description** saying *when* to use it (Claude reads it to decide when to trigger the skill)
- Numbered steps, plus **"stop and ask"** points
- A **dry-run** option, so you can try it safely
- Safety rules written in: "never overwrite", "dry run first"

💬 **Ask Claude:** *"Make a project skill called /<name> that does X. Put the mechanical part in a tested script, and give it a dry-run option."*
📍 **Where skills live:** `.claude/skills/<name>/SKILL.md` = this project only (committed, shared). `~/.claude/skills/` = all your projects.
⚠️ **Watch out:** a skill is only as good as its instructions. Try it once with a dry run before relying on it.

---

## 🧰 Other Claude features we've used

| Feature | Plain meaning | How |
|---|---|---|
| `!` prefix | You run a command, and the output lands in the chat | `! gh auth login` |
| Status line | A bar showing folder + **branch** + model | `/statusline` (project-only: `.claude/settings.local.json`) |
| Auto-memory | Claude remembers how you like to work, across sessions | Automatic |
| Artifacts: a build map | A visual page of the project (every kind of part and where it lives, the journey of a change, tests, a "How it grew" timeline), updated after every step, with a frozen snapshot per step in `docs/build-map/snapshots/` | Ask: *"Make a build map artifact of this project, keep its source in `docs/build-map/index.html`, and add 'update the build map' to CLAUDE.md's after-each-step list."* ⚠️ Keep the source in git, or it's lost with the session |
| **Headless Claude (`claude -p`) as an agent** | A script calls Claude Code without a chat, so a batch job runs under your subscription (no API key) | `claude -p --output-format json --model sonnet --tools "" --strict-mcp-config --no-session-persistence`, prompt on stdin, from an **empty temp folder** (no project files or CLAUDE.md). The JSON has the reply text and token usage. Copy `src/quizkit/claude.py` + its tests. Always pair it with a **script checker** and `--limit` / `--dry-run` |
| **Git worktrees: two Claude sessions at once** | A second folder of the same repo, on its own branch ("two desks, one notebook"), so two sessions build two features without touching each other's files | `git worktree add -b <branch> ../<repo>-<feature> main`, then `uv sync` there, open a new terminal, `cd` there, run `claude` with a starter prompt. Remove after merge: `git worktree remove ../<repo>-<feature>` |

**Worktree tips:**
- **Pick two features that only share a shape, not code** (here the engine only needs `list[Question]`, which already existed). If one needs the other's code, do them one after the other.
- **Only one session edits the shared docs** (plan, log, maps). Otherwise both PRs change the same lines and you get a merge conflict.
- **The second session may not see your memory notes** (they're stored per folder), so give it a starter prompt with the context. CLAUDE.md, skills and subagents are in git, so it has those.
- **Merge one PR, then update the other from `main`** before merging it (`git fetch origin` + `git merge origin/main`, then re-run the checks).
- **Hand back with a short report.** The second session ended with a pasteable summary (what was built, the process, what carries to the next step, ideas for later), which made writing the shared docs easy.
- **Clean up after the merge:** `git worktree remove ../<folder>` (it refuses if there is uncommitted work, which is a useful check) and close that terminal.

---

## 12. 🤖 Subagents: specialist helpers

**Plain meaning:** a **subagent** = a helper Claude that gets sent off to do **one job**, with **fresh eyes**. It doesn't see your chat, and it reports back briefly.

| | Skill | Subagent |
|---|---|---|
| Is | Instructions Claude follows | A separate helper |
| Sees your chat? | Yes | ❌ No, it starts fresh |
| Best for | Repeated processes | Fresh-eyes reviews, big messy jobs |

| Subagent here | Job | Tools (what it's *allowed* to do) |
|---|---|---|
| 🔍 `block-reviewer` | Checks a block against its job description + ADRs → ✅ / ⚠️ verdict | Read, Grep, Glob only, so it **can't change anything** 🔴 |
| 🧪 `test-writer` | Writes tests from the job description (not from the code) | Read, Write, Edit, Bash (told: only in `tests/` 🔵) |
| 🔎 `data-auditor` | Checks the **data**, not code: flags sentences the scripts can't judge (natural? English right? right reading? too hard? taught meaning?), each with a reason; flagged sentences are removed without asking (ADR 0015) | Read, Grep, Glob only 🔴 |

**How they get triggered** (none of these are 🔴, but together they make it reliable):
| Trigger | Strictness | Where |
|---|---|---|
| Built into the `/new-block` steps (6: test-writer, 8: reviewer) | 🔵 | `.claude/skills/new-block/SKILL.md` |
| CLAUDE.md rule: "no block PR without a ✅ review" | 🔵 | `CLAUDE.md` |
| PR template checkbox + pasted verdict | ⚪ (lets *you* see that it ran) | `.github/pull_request_template.md` |
| Claude spots a match from the helper's description | 🔵 unreliable | the agent file's `description` |
| You just ask: *"review the X block"* | ⚪ always works | n/a |
| CLAUDE.md rule: audit the sentence bank at each milestone end + every ~50 new sentences | 🔵 | `CLAUDE.md` |
| A dated report per audit (flags, your decisions, what was checked) | ⚪ (lets you see that it ran, and when) | `docs/audits/` |

**How you can see they ran:** they show up in the chat while they run, Claude shows you the verdict, and the ✅ verdict is pasted into the PR.

💬 **Ask Claude:** *"Make a read-only subagent that reviews X against Y, with a ✅/⚠️ checklist report. Wire it into my skill, CLAUDE.md and the PR template."*
📍 **Where:** `.claude/agents/<name>.md` (this project) or `~/.claude/agents/` (all projects). See and manage them with `/agents`.
⚠️ **Watch out:**
- **New subagents only load at session start:** `/exit` → `claude --continue`
- **Limit the tools.** A reviewer with no Write/Edit tools *can't* make changes (🔴). An instruction like "only write in tests/" is only 🔵.
- **Plan the triggers, not just the helper.** A helper nobody calls is useless.
- **Test it on a planted mistake** before trusting it. For a judgment helper, keep the planted file + an answer key in the repo (`tests/data/auditor_planted*`) and re-run it after every change to its instructions
- **AI-made data gets an AI reviewer, not a human gate.** Scripts check the rules; a read-only auditor checks meaning; what it flags is removed automatically; a dated report keeps it traceable (M4 Step 6: 4 of 44 sentences removed, and it found a gap in the script checker). A person approving each item doesn't scale, and a learner can't judge the language anyway (ADR 0015, 2026-11-11). A mistake a script could catch goes to the script, not to a person
- **After editing a subagent's instructions, test the new text, not the loaded one.** A running session may keep the version it loaded at start, so re-run its planted test in a fresh session, or have an agent read the file and follow it (2026-11-11)
- A read-only reviewer can't run tests, so it reviews by reading. Claude still runs pytest.
- **Fresh reviewer each round.** Round 2 found a gap round 1 missed. A new subagent has no memory of "what I already approved".
- **A subagent flags, reality decides.** The test-writer only sees the SPEC, so it can ask "may `pos` be empty?" but not answer it. Check questions like that against the real data (here: 11 words had no `pos`, which would have crashed the real run).

---

## 13. 🤖 Code review: a second pair of eyes on every change

**Plain meaning:** Claude reads the change like a careful teacher and hunts for bugs that **no test was written for**. Two cousins of the same reviewer, in two places (the GitHub one is a plugin, `code-review@claude-code-plugins`):

| | `/code-review` (local) | Claude GitHub app (automatic) |
|---|---|---|
| Where | In your Claude session | On GitHub, on every PR |
| When | Before the PR is opened | When a PR opens + on every new push |
| Who starts it | Claude (CLAUDE.md rule) 🔵 | Starts itself 🟠 |
| Where findings go | The chat (or PR comments with `--comment`) | Comments on the PR's lines |
| Can it block a merge? | No | No (unless you make it a required check) |

Also: write **`@claude`** in any PR or issue comment to ask the GitHub app a question. It works with the Claude app's own permissions, so it **may push a branch**. Protected `main` is what stops it reaching `main`.

💬 **Ask Claude:** *"Add code review: a CLAUDE.md rule to run `/code-review` before every PR, a PR-template checkbox, and set up the Claude GitHub app."* Then **you** type `/install-github-app` (it opens the browser), pick both workflows and your subscription.
📍 **Where:** `.github/workflows/claude-code-review.yml` + `claude.yml`, secret `CLAUDE_CODE_OAUTH_TOKEN` (GitHub → Settings → Secrets), rule in `CLAUDE.md`, checkbox in the PR template.
⚠️ **Watch out:**
- **The subscription token expires after 1 year.** Put an exact renewal date **before** expiry in your plan (here: before 2027-10-15). When it expires, the review job fails, and since review is advice-only, nobody may notice.
- **Green ≠ reviewed.** The review only runs once its workflow file on the branch matches `main`. The first run (the install PR itself) and any PR that edits the workflow show green but **skip**. Check the run log once.
- **Prove it with a planted bug** before trusting it: a throwaway PR with 2 hidden bugs (here it caught 1 of 2). Close it unmerged.
- **Change the workflow in its own PR.** Otherwise you lose the review on your real changes.
- **Fork PRs get no review** (GitHub hides secrets from forks). `@claude` only works for people with write access.
- **Never paste the token in chat.** The installer saves it as a GitHub secret.
- **Review is advice, not a gate.** Tests + CI + protected `main` are the gates. You decide which comments matter.
- **The `/install-github-app` PR is quick to merge**, but read its files first: check what permissions the workflows get.
- **Review is not the same as block review.** `block-reviewer` checks "does it match its SPEC?"; code review checks "is the code right?"
