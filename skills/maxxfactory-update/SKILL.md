---
name: maxxfactory-update
description: Change maxxfactory itself (its skills, bin scripts, prompts, templates, tests, lessons) under fixed rules. Restates the request as general rules, finds the root cause when it comes from an incident, checks every rule against the rules already in place and stops for the owner's decision on any contradiction or break, enforces the rule in code where a script can, updates every skill and doc that touches the subject, records the lesson anonymized (no owner, company, project, path or ticket name; `bin/leak check`), and runs the self-test. Use when the user says "/maxxfactory-update ...", "update maxxfactory", "maxxfactory must / should / must never ...", "add a rule to the autopilot", "change the run / plan / init skill", "record this lesson in maxxfactory", or reports a behaviour of the runtime to fix for good.
---

# Autopilot: update the runtime

**Caveman, always.** Your first action, before any other tool call: invoke the `caveman` skill (`/caveman`), and keep it for the whole session, including after a resume or a context compaction (invoke it again then). If it is not installed, follow its rules anyway: answer first, no ceremony, commands, paths, numbers and errors verbatim. Every subagent you start talks caveman too: every Agent-tool (subagent) prompt you write starts with "Invoke the `caveman` skill first and answer terse." Persisted text stays plain prose: code, comments, docs, commits, skills, lessons.

maxxfactory is shared: many people run it on projects you will never see. An update is a change to everyone's runtime, so it must hold for all of them, agree with the rules already there, and say nothing about whose project it came from.

`bin/<x>` below means the `bin` directory next to this SKILL.md. The maxxfactory repo is the parent of the real path of that directory (`cd "$(dirname "$(realpath <bin>/leak)")/.."`): every edit happens there, never in a project. It must be a git checkout; a copy without `.git` (a packaged plugin) cannot be updated: tell the owner to clone the repo and run `install.sh` from the clone.

| Script | Role |
|---|---|
| `bin/leak` | `check [--all] [--msg FILE]`: nothing private in the pending change (identity, home paths, e-mails, tracker identifiers, the owner's private terms). `terms`: what it looks for. |
| `tests/selftest.sh` | the behavioural self-test of the runtime (no model run, no quota spent). Every enforced rule has a `check` line there. |

## 0. Where you are

1. `git -C <repo> status --short`. Changes that are already pending are not yours: list them to the owner, never revert them, never fold them into this update.
2. Never touch a project from here: no edit of a project's `.autopilot/state.json`, pipeline, worktrees or `PLAN.md`. You may read a project (state, logs, briefs) to understand an incident.

## 1. Restate the request as rules

One line per rule, shown to the owner before anything else:

| # | Rule (general) | Why | Enforced by |
|---|---|---|---|
| R1 | Worktrees are created in `<repo>-wt`, next to the repo | a recorded path goes stale when the repo moves | `lib.worktrees_dir`, `pipeline wt` |

- The rule holds for any user, repo, tracker and machine. Replace the owner's case by the class it belongs to: "my shop repo" becomes "a repo", "that ticket" becomes "a ticket", "my laptop" becomes "macOS".
- A wish that only makes sense for one project is not an update: it belongs in that project's `AGENTS.md`, `PLAN.md` or `state.json`. Say so and stop there.
- "Enforced by" names a script whenever a script can check or do it. A rule written only in prose is broken at the first compaction.

## 2. Root cause, when the update comes from an incident

Read what really happened before writing a rule (the project's state, `pipeline.log`, briefs, the session). Often the rule already exists and something else broke it: a default that an old recorded value overrides, a step a skill forgot to name, a script that accepts what the skill forbids. Then the update fixes that hole; it does not add a second wording of the same rule.

## 3. Conflict check, before any edit

For every rule, search its subject and its synonyms in: `skills/*/SKILL.md`, `README.md`, `references/*.md`, `prompts/`, `templates/`, the docstrings and the code of `bin/` that implement the behaviour, and the `check` lines of `tests/selftest.sh`. Classify every hit and show the table:

| Hit (file:line) | What it says today | Relation | Action |
|---|---|---|---|

- **same**: already the rule. Keep one wording; fix why it was not followed (step 2).
- **extends**: the new rule adds a case or tightens it. Edit the hit so both read as one rule.
- **contradicts**: both cannot be followed. **Stop.**
- **breaks**: a caller, a CLI flag, a `state.json` key, data written by an older version, or a test that asserts the old behaviour stops working. **Stop.**

On a contradiction or a break, ask the owner before editing anything that depends on it (the rest of the update goes on). Quote both texts with `file:line`, say what each choice changes for a running project, give your recommendation, and offer: replace the old rule, keep it and drop the new one, or scope both (say when each applies). Record the answer in the lesson.

- The behaviour the owner's request names as wrong is already decided: replace it, and say so in the report. Everything else the change collides with is theirs to decide.
- Never: delete or reword a rule silently, leave two texts that contradict each other, or change a test's expectation to make it pass (that is replacing a rule: ask).
- The safety rules are never weakened without the owner's explicit words in this conversation: no paid credits or plans, no work destroyed, the coordinator's account protected, implementer and reviewer different models, nothing created before the owner's approval, no outward action that was not pre-authorized.

## 4. Apply

The installed skills are links to this repo: a pipeline that is running somewhere calls the edited scripts at its next tick. Every save leaves the scripts runnable (`python3 -m py_compile`, `bash -n` after each edit of `bin/`), and a behaviour a running project relies on changes only together with the code that still reads its old data.

In this order:

1. **Code.** The script that does or checks the thing (`bin/`), fail closed, with the rule and its date in the docstring. Data and settings written by older versions keep working: read the old key, never require a migration in the middle of a run.
2. **Every skill that touches the subject.** One skill holds the detail; the others name the command and point to it. A check that must happen "at the start" is a numbered step in each entry point (`init`, `plan`, `plan-more`, `run`, `continue`), not a sentence in one of them.
3. **`README.md`** (skill table, script table, methodology), **`templates/`** (`state.json` keys, `permissions.json` for a script the run must call without a prompt), **`install.sh`** when a skill is added or renamed.
4. **`tests/selftest.sh`**: one `check` per enforced behaviour, hermetic (temporary directory, fake CLIs, never the user's config).
5. **`references/lessons.md`**, at the end: a heading that names the symptom and the date, then symptom, cause, and what the runtime does now.
6. **Projects already running.** Say what they must do, if anything, as one command for the owner or for `/maxxfactory-continue`. Never do it for them from this skill.

## 5. Anonymize and generalize

Everything persisted in the repo (skills, code, comments, tests, lessons, README, commit messages) is public and must read the same for every user.

- Never: the owner's or anyone's name, e-mail, account or host name; a company, product, customer, repo, branch or domain name; a home path; a tracker identifier or team key; a decision number of a project; a quote of the owner's message; figures that identify a project.
- Write instead: `~/code`, `<repo>`, `<repo>-wt`, `<ISSUE>`, `ENG-1`, "a project", "a content site", "the owner". Keep what makes the lesson usable: the symptom, the tool and its exact message, the date, the orders of magnitude.
- The owner's own decisions are recorded as the rule they produce, not as "the owner decided".
- Before recording a lesson learnt on a project, add that project's names (company, product, repo, tracker team key) to `private-terms.txt` in the config directory (`bin/leak terms` prints its path). The file stays on the machine.
- `bin/leak check`: every finding is fixed by generalizing the text, never by weakening the script.

## 6. Verify

1. `tests/selftest.sh`: every line `ok`. A test of an old behaviour that now fails is a conflict: back to step 3.
2. `bin/leak check` (and `--msg <file>` for a commit message draft): `leak: clean`.
3. A skill was added or renamed: `./install.sh`, then check the link in `~/.claude/skills`.
4. A new or changed script: run it once for real (`-h`, then its read-only command).

## 7. Report

Short: the rules added or changed (`file:line`), the conflicts found and who settled each, what running projects must do, the self-test and leak results, the pending changes you left alone. Commit only when the owner asks; one commit per update, `feat(<scope>): <the rule>`, its message generalized like the rest.

## Rules

- A conflict is the owner's decision, never yours.
- Nothing private in the repo, not even in a test or a commit message.
- A rule a script can enforce is enforced by a script and tested.
- An update never touches a running project.
