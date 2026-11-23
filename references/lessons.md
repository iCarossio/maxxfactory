# Lessons from real runs (by symptom)

Read the section whose symptom you observe. These are facts measured on real projects; dates mark when they were learnt. Add yours at the end, with the date.

## Files change in a worktree after a round finished; check runs die with rc=143; servers vanish

**opencode ghost sessions (2026-10-25).** Without `--standalone`, `opencode run` is a client of `opencode serve --service`: sessions and their shell jobs run in the service, keep going after the client exits or is killed, and are resumed when the service restarts. Ghost sessions from earlier rounds then edit worktrees after "done" and run things like `pkill -f "npm run parity"` against every checkout. `run-model` passes `--standalone` (the adapter does). If ghosts exist: `opencode service stop`, keep it stopped (check with `pgrep -fl "opencode serve --service"`, never `opencode service status`, which starts the service; an interactive `opencode` TUI left open also restarts it), and ask the user before deleting sessions (`opencode session list` / `delete`). After a ghost, re-check every worktree it could touch: a "done" round may have been partly reverted.

## `docker version` blocks; runs report `docker_hung`; serve tests hang for everyone

**Docker can hang under many parallel container start/stop cycles (2026-10-25).** `bin/docker-up --restart` probes with a bounded `docker version` and, when the runtime runs but the daemon is silent, restarts it (on OrbStack `orb stop && orb start`, because `orb restart docker` may hang too; containers survive). If it still does not answer, kill the stuck docker clients and run it again. Implementers must never restart Docker themselves: the brief says to stop and report. Then restart the stuck checks and rounds, and `run-model reset` any model cooled during the hang. With a sufficiently sized VM (e.g. 32-64 GB), up to 5 Docker-heavy jobs at a time were fine; the hangs came with small VM memory and 3 capture-heavy suites at once.

## Docker is down after the machine restarted

**OrbStack does not always start at login (2026-11-01).** After a reboot every run died and `docker` failed with `connect: no such file or directory` on the socket. `bin/docker-up` starts the runtime and waits until the daemon answers; run it at setup, on each heartbeat and when resuming.

## Everything stalled for hours overnight, logs stopped at the same minute

**The machine slept on battery overnight.** On macOS, `caffeinate` does not prevent sleep on battery; `pmset -g log` shows `Entering Sleep ... Using Batt` (on Linux, check logind/systemd-inhibit). At setup and on each heartbeat check that the machine is on AC power (`pmset -g batt` on macOS, `/sys/class/power_supply` or `upower` on Linux); if not, tell the user at the next turn.

## A ticket's untracked file disappeared after `rebase-wt`

`git stash pop` silently does not restore an untracked file whose path now exists on the branch (e.g. a notes file both tickets create). Recover it from the stash's untracked tree (`git show <stash>^3:<path>`, or from the dangling commit after a drop) and merge the two versions.

## A pre-commit hook fails in `finish` although the worktree passed

"package doesn't seem to be present in your lockfile" (or missing generated code in a fresh worktree) means the checkout's dependencies are stale, not the change: run the repo's install (`yarn install --immutable`, then its codegen) and commit again before sending anything back to the implementer.

## Checks fail with `ERR_CONNECTION_REFUSED` storms

A leftover `cmd &` from the implementer restarting the same server mid-run, or a reviewer starting/stopping servers in the same worktree, or two wrappers rebuilding the same `dist/` while a third serves it. Fixes: never review and check the same worktree at the same time; before checks, make sure nothing of the implementer still runs (`ps` for the worktree path, `docker rm -f <name>`); build once and make sure no wrapper rebuilds (`serve:prod` instead of a no-build serve); each suite gets its own port, container name and checkout.

## Regeneration overwrote a ticket's generated output

Regenerate and check idempotency only with the repo's own pipeline command (as named in the ticket notes), never with a remembered list of scripts: an older list silently drops newer steps.

## All tests green, converter still wrong on real data

**Invented fixtures pass by construction (2026-10-27).** A content sync read fields that live in an undocumented metadata table and a redirects format never used in production, with all tests passing on fixtures the implementer wrote. Require fixtures sampled verbatim from real snapshots, plus one test that round-trips a real record against the current output.

## The same failing cases get "fixed" round after round with a new list each time

**Per-case harness tuning.** A literal list of pages/ids in capture or compare code that changes behaviour for exactly the failing cases, then a "metadata" file, then a "generator" with hard-coded exclusions. Ask for the general rule (derived from the content or from metadata recorded with the baseline) and a test that fails on literal paths in the harness. When the expected output itself is inconsistent and no recorded fact explains it, stop the loop early: decide that those cases become explicit, reviewed exception entries (url, field, reason) and every other case follows the derived rule. Verify exception claims against the source data with one grep before accepting them.

## A reviewer wiped a ticket's work

**Reviewers can modify the tree (2026-10-25).** A free-tier reviewer ran `git stash`, a generator, then `git stash drop && git checkout -- .`. `bin/review` snapshots and restores the tree and prints `TREE RESTORED`; discard the verdict of the reviewer flagged `modified tree`. A dropped stash is still recoverable: `git fsck --no-reflog --unreachable | grep commit`, find the `WIP on <branch>` commit, `git stash apply <sha>`.

## Reviewer verdicts contradict a quick run

Typical false positives seen: "Go regexp rejects `(?:...)`" (it doesn't), "fails" claims disproved by the saved report, findings that contradict a documented coordinator decision, demands outside the ticket's scope (third-party embeds, data owned by a human). One command, then reject in writing.

## Codex usage limits

Codex models on one ChatGPT account share one usage limit (5 h and weekly windows); `run-model usage` reads them from the session logs of each `CODEX_HOME`. `bin/codex-reset` redeems a "Full reset" through the TUI (`/usage` -> Redeem reset -> the earliest-expiring one), only when the weekly window is at 100%; `run-model` claims it by itself (standing authorization, `codex_auto_reset`). See `lessons-codex-resets.md`.

## Grok on quota

A 402 balance message is a quota, not a billing request: it cools down and comes back at the subscription renewal shown by `/usage` in an interactive `grok` session (the CLI `grok usage` needs a session id). Set the cooldown to that time instead of retrying hourly.

## OpenRouter through opencode

Only `:free` ids when the account has no credits (never `openrouter/auto` or paid ids). A model missing from models.dev must be declared under `provider.openrouter.models` in `~/.config/opencode/opencode.jsonc`.

## A Tier 1 model reviewed ticket code, a Tier 4 model was the second reviewer

**Hand-ordered pools drifted off the tier policy (2026-11-09).** The coordinator reordered the review and implement pools by hand to work around outages: a flagship (Tier 1) became a ticket code reviewer, a free-plan Mistral model (Tier 4) the second reviewer, and a balanced model (Tier 2) an implementer. The policy is one tier per role: Tier 3 implements and fixes, Tier 2 reviews ticket code, Tier 1 only plans, pre-mortems, reviews milestones and coordinates, Tier 4 only does trivial tasks. Fix: tiers are data (`level` per roster entry, `roles` in `models.json` bounded in code), pools are derived from them and drawn by credit left, `run-model --model` refuses a model outside the role's tier, and `harness pools set` is gone. When a tier is out of quota, wait for its reset or raise the CRITICAL alert; never move a role to another tier. The earlier "model ranking" of this file (it put a flagship first as a ticket reviewer) is withdrawn: the tier table decides. (The ticket code review now has one built-in, logged backup decided by `bin/review` alone: Tier 1 when no Tier 2 reviewer is eligible; see below.)

## Reviews ended INCOMPLETE twice while eligible reviewers were healthy

**2026-11-09.** Implementers claude-sonnet, codex-luna (three accounts) and claude-haiku-b; the only vendor no implementer used was Google, so `bin/review` drew agy-gemini-flash. It hit its quota (`Resets in 162h57m57s`), `run-model --model` has no fallback, and the review ended `all_failed (no verdict)` / INCOMPLETE. `reset_from_text` did not parse `162h57m57s`, so the cooldown lasted the 60 min default and the next round drew Gemini again. codex-terra-* (never implementers) were healthy the whole time. Fix: the vendor preference applies only among healthy reviewers; a reviewer without a usable verdict is replaced by the next eligible one within the same `bin/review` call; `h/m/s` durations are parsed. Then escalation made codex-terra an implementer too, leaving no Tier 2 reviewer at all: the fix makes Tier 1 the logged backup reviewer (never the coordinator's account, never an implementer) instead of waiting; the CRITICAL alert fires only when neither tier has one.

## A review was killed as `quota` while the log shows normal activity

**Quota phrases echoed by the model (2026-10-29).** A reviewer that reads this repository (or any file with "usage limit" / "rate limit exceeded" in it) prints those phrases into its log; the watchdog took them for the CLI's own quota loop and killed the run. `run-model` now counts only short plain lines without code or quote characters, three of them, before calling a run `quota`; adapter `quota_patterns` classify the final exit only. If it happens again: `run-model reset <key>` and relaunch.

## A reviewer was flagged `modified tree` but changed nothing

The fingerprint covers the whole working directory (tracked state, untracked content, HEAD). Editing the repo yourself while a review runs there (a hot fix to a script, a doc update) flags that review and discards its verdict. Edit in another checkout, or wait for the review to finish.
- 2026-11-04: `run-model wait <pool> <excluded>` knows nothing about vendors. For a plan review it returned `claude-opus-b`, another account of the planner's vendor, and `bin/review` then refused with NO_REVIEWER. Pass every key of the excluded vendor (all `claude-*` keys, including `-b` accounts) until `wait` takes a vendor filter.
- 2026-11-04: the ETA kept slipping while the tail of `stages` held eight single-item stages that nobody had re-checked. Three of those items were independent: one only needed an owner token for its live run, another only needed a plan, and the third only conflicted on generated files. `bin/eta` now prints `REPLAN:` lines (slip, serial tail, idle lanes); act on them.
- 2026-11-04: implementers that run full suites under load hit their watchdog and leave no STATUS block. One left an orphaned test runner suite, reparented to PID 1 (init / launchd), that kept running in the worktree the coordinator was about to check. After any `timeout`, list `ps -Ao ppid,pid,command | awk '$1==1'` filtered on the worktree paths, and stop those process trees before checking. The resolved work was in the tree each time: run the coordinator check instead of another implementer round.
- 2026-11-04: dead test runs can leave orphaned headless browsers or test processes reparented to PID 1 (init / launchd). On each heartbeat, list `ps -Ao ppid,pid,etime,command | awk '$1==1'` filtered on the test runner or browser binary path, and stop the trees older than one hour. A plain `kill` may not be enough; use `kill -9` for survivors.
- 2026-11-04: `bin/state implementer <ISSUE> <key>` run from inside a secondary sub-repo recorded the coordinator in that sub-repo's `.autopilot/state.json`, not in the project state, and still printed `ok`. `bin/review` then let the coordinator's model review a ticket it had edited. Always run `bin/state` with `AUTOPILOT_REPO=<project repo>`, and check with `state get implementers.<ISSUE>` before the next review. Fix to make: refuse when the resolved repo is not the project's.
- 2026-11-04: in the coordinator shell, `ls` is aliased to `ls -l`, so `$(ls pattern)` builds argument lists of long-format lines (node then fails with "bad option: -rw-r--r--@"). Build file lists with `find` or `grep -l`, never with `ls`.

- **A network outage looks like every model failing.** On 2026-11-04 a DNS outage (`ENOTFOUND` on every API) turned three runs into `all_failed` and put a false cooldown on every model in the pools. Before treating `all_failed` as quotas, read the tail of one output file and run one `curl` to an API host. If it was the network: `run-model reset` each key that errored, smoke one model per vendor, and relaunch each ticket with an "interrupted, not rejected" round that keeps the partial tree. Candidate harness fix: `run-model` should detect `ENOTFOUND`/`ECONNREFUSED` in the output, classify it as `network`, retry with backoff, and set no cooldown.

- **A one-lane check queue idles the machine.** On 2026-11-05 six full checks waited behind one running check at load 5 on 16 cores. Run checks in lanes: a second lane opens while the 1-minute load is below about 0.9 x cores (`QCHECK_LANES`, `QCHECK_MAX_LOAD` in the project's `qcheck.sh`). Waiting `qcheck` processes keep the old script after an edit: stop and re-queue the critical-path ones.

- **`bin/review` does not fall back to another account of the same vendor.** On 2026-11-05 the default Codex account hit its usage limit mid-review; `bin/review` picked codex-sol, then codex-luna on the same account, and returned INCOMPLETE twice while the `-b` and `-c` accounts had quota. Workaround: `EXCLUDE=<the exhausted account's keys>`. Harness fix: on a quota failure, cool down every key of that account and retry the same vendor on the next account before giving up.

- **`restore()` loses tracked work when the ticket's new files are staged (`A`).** `snapshot()` records them in the `git stash create` commit; `restore()` runs `reset -q` (the added files become untracked), `checkout -- .`, then `stash apply`, which refuses because those files already exist untracked. Result on 2026-11-05 (after a reviewer edited the tree): every modification to tracked files was gone, only the added files were left. Recovery: find the dangling `WIP on <branch>` commit from the review start (`git fsck --unreachable`), then `git checkout <that commit> -- .` and confirm with `git diff --quiet <commit> -- .`. Harness fix: restore with `git checkout <stash> -- .` (plus the cached patch), or remove the snapshot's added paths before `stash apply`; and print the snapshot commit id in every restore message so the coordinator can recover directly.

- **Helper links in a worktree get committed.** On 2026-11-05 the coordinator linked `node_modules` and `migration/node_modules` into a migration worktree to run tests, forgot to remove them before `finish`, and the repo's ignore rule was `node_modules/` (directories only), so `finish` committed both links. Checking the commit out replaced the main checkout's installed packages with self-referencing links. Fix: untrack them, ignore rule `node_modules`, then `npm ci` in both package roots. Harness fix: `finish` must refuse to commit a symlink or any path named `node_modules`, and worktrees should get dependencies by `npm ci`, never by links.

- **A findings file built by a script can be silently missing.** On 2026-11-05 the coordinator's inline python that extracts review findings into `<ISSUE>-findings-r<n>c.md` crashed (the review file was not pure JSON) inside a backgrounded command, so `mkbrief` built a brief with no findings and the implementer ran a round "blind". Before dispatching, check that the findings file exists and that the brief contains a phrase from it (`grep -c`); `mkbrief` should fail when a findings path is given but missing.

## A long coordinator command hung silently for hours

**A command the coordinator ran itself had no watchdog.** A sync proof drove a headless browser that never finished one page. The process sat idle with almost no CPU for 2.5 h, while the coordinator waited for its completion notification, which never comes for a hang. `run-model` guards model runs, but the coordinator's own long commands (checks, syncs, proofs, captures, pipelines) were bare background shells, and the heartbeat rule "check that every log moved" was not enforced because no heartbeat ran. Run every such command through `bin/bgrun` (stall and timeout watchdog, kills the whole tree, exits 124 with the process tree in the log), and treat a silent long step as a defect of the tool: per-step progress lines and bounded waits that fail closed with the step named.

## A healthy check was killed twice as a stall

`bgrun` judged progress only by output. A test runner that prints a result only when a whole test file ends was silent for 45 minutes while it ran builds, so two healthy checks were killed. Progress now also counts any new working process in the run's tree; polling utilities (`sleep`, `date`, `ps`, ...) do not count, so a stuck wait loop still stalls. Self-tests cover both cases.

## A 3.7 h proof ran without one of its flags

The coordinator saved a long proof command in a file and ran it with `bash -c "$(cat file)"`. The last flag (`--accept-unproved visualSource=...`) had landed on a second line. The shell ran the proof without it, then tried the flag as a command (rc=127). The proof's substance passed, but its verdict was FAIL for the missing acceptance. Rule: before launching a saved command file, check that it is one line (`wc -l`), parse it with `bash -n`, and grep it for every flag you expect.

## A diagnosis brief burned 8 model runs as "bad output"

`mkbrief diag` asks for a JSON verdict, but `run-model run implement` required a `STATUS` line, so every model's valid diagnosis was rejected and the pool fell through to the last resort. `run-model` now accepts a `"verdict"` block for briefs named `*-diag-*`.

## Symlinked node_modules in a side worktree

To run a fix round beside a long proof, the coordinator symlinked the proof worktree's `node_modules` and acquisition folder into a new worktree. The implementer ran `npm ci` and a fresh acquisition there. This time npm replaced the symlink rather than emptying its target, and the acquisition replaced its symlink with a real folder, so the proof survived. Rule: give a side worktree its own `npm ci` and copies of its inputs, never symlinks into a worktree that is in use.

## A fallback implementer stops on its predecessor's partial work (2026-11-08)

`claude-sonnet` timed out after 80 minutes of correct partial work in a round whose brief demanded a clean site tree. `run-model` fell back to `codex-terra-c`, which saw the dirty tree, followed the brief literally and returned `STATUS: blocked` in 21 seconds. The round looked like a blocker but was an interruption. Fix candidate: when `run-model` falls back after a timeout or idle kill in the same worktree, prepend to the brief "a previous attempt in this round was interrupted: the uncommitted changes are its partial work; verify and continue". Until then, read `tried` in the JSON line before treating a short `blocked` as real, and write clean-tree rules as "sync-managed files" rather than "the whole tree".

## docker-reap removed another run's running container

On 2026-11-08 the reaper removed a running database container of another autopilot run on the same machine: it was older than 2 h and no process referenced it by name (compose-managed containers are referenced by no process). "No owning process" does not mean "dead" for a running service container. Fix to make: reap only exited or never-started containers by default, or only containers whose name or compose project matches the current project; until then pass `--keep` with every other project's prefix.
- 2026-11-10: three accounts of the same Tier 3 model were cooled down as `waiting_input` in a row. The evidence was code in the model's own output (`question=(f"Approve this plan? ..."`, `agent_id: str, *, ...`, `x.mission_id,`): the input-prompt pattern matched anywhere in the last 2000 characters. `run-model` now calls a run `waiting_input` only when the last line is a prompt and not code, after 30 s of silence (adapter `waiting_patterns` to add a CLI's own prompts). A run cooled as `waiting_input` with code in its reason is a false positive: `run-model reset` the keys.
- 2026-11-10: a CLI was reported "not installed" only at run time, hours into the night: the user's shell had a function of that name wrapping a binary that had been removed. `run-model` runs the binary, never the shell, so `bin/harness discover` and `check` now test for a real executable on PATH and list the roster entries it makes unusable at setup.
- 2026-11-10: the coordinator's own account was used as an ordinary implementer and reviewer, which spends the quota the coordinator needs to stay alive. The coordinator account is now detected from the session (adapter `coordinator_env` + `account_env`), its models run last and only for cheap roles, and only while it keeps `coordinator_reserve`. Another login of the same CLI is a normal account and must not be held back.

## The owner's running app breaks after a full check on the project branch

Symptom: the app the owner uses (`next start` on a fixed port) serves HTML whose CSS and JS return 500; pages render unstyled and nothing reacts to clicks. Cause: the coordinator ran the full checks (which include `next build`) in the main checkout, the same directory the running server serves `.next` from; each build rewrote the chunk names under it (2026-11-10, broken for hours unnoticed). Fix: run project-branch checks in a dedicated detached worktree (`git worktree add --detach <wt> <branch>`, then `git checkout --detach <branch>` before each run), never in a checkout that serves a live app. After a merge that adds a startup migration or backfill, restart the owner's app only on purpose and watch its first startup: a strict backfill over old dev data can crash-loop the API.

## The reaper removed another project's container

Symptom: `docker-reap --apply` at a heartbeat removed a dev proxy container of an unrelated project on the same machine (2026-11-11). Cause: the reaper considered every container on the daemon. Fix: the reaper is scoped to the project (`--only` or state.json `docker_reap_only`) and only reports without a scope; running compose services and containers with a restart policy are never removed.

## wait-approval also returns on triage (2026-11-14)

Symptom: the coordinator read "wait-approval completed" as an approval and ran `pipeline merge` on a ticket in `triage` (5 rounds of failed checks, never reviewed). Cause: `wait-approval` wakes on an approval OR an attention line; the merge does not refuse a triage ticket. Rule: read the returned line; merge only `<ISSUE> r<n>` lines from approved.txt, never an `ATTENTION:`/triage line. Second cause in the same run: a CHECKS line ending in `| wc -l | grep -qx 0` always fails on macOS (BSD `wc` pads with spaces); use `| grep -c . | grep -qx 0`.

## A coordinator decision appended below the CHECKS line does not change the checks (2026-11-14)

Symptom: four rounds in a row "checks failed" within a minute on `--max-mb 10`, although a "Coordinator decision" appended to the ticket said the gate is 16. Cause: the pipeline runs the ticket's `CHECKS:` line verbatim; appended text only reaches the implementer. Rule: when a decision changes a gate, edit the `CHECKS:` line itself (and every place in the description that repeats it), then check `grep -n "^CHECKS" ticket.md`.

- 2026-11-15: a ticket CHECKS line with the full `npm test` (46 min alone) hits the pipeline's 60-minute check limit when three tickets test in parallel, and the timeout costs a round. Ticket CHECKS run the related suites; the full suite runs once per batch on the integration branch.

## An implementer that answers STATUS: blocked is counted as a finished round (2026-11-17)

Symptom: a ticket burns all 5 rounds in about 12 minutes with `CHANGED: none` each time; triage reports "no changes present in worktree". Cause: the ticket's `touches` omitted files its instructions required; the implementer correctly stopped with `STATUS: blocked`, and `bin/pipeline` treats any run with a STATUS line as ok, so it went to review, got "nothing implemented", and started the next fix round. Fix now: on every heartbeat grep `.autopilot/out/<ISSUE>-impl-*.md` for `STATUS: blocked`, read its NOTES, extend touches or decide, then `pipeline fix`. Follow-up for bin/pipeline: route `STATUS: blocked` to attention.txt instead of a fix round.

## Coordinator notes that narrow a ticket cost rounds (2026-11-17)
- Unblocking a ticket early (a coordinator decision) came with a note limiting runner edits to one write; the ticket's acceptance needed a second runner step. The implementer returned STATUS: blocked twice.
- Async conversion of a shared helper has callers outside `touches`; the implementer was blocked for four rounds before the coordinator saw it (rounds took 1-2 minutes each).
- Rule: before starting a ticket that makes a function async, grep its callers and add them to `touches`. Before adding a "keep edits minimal" note, re-read the acceptance. Scan `<ISSUE>-impl-<n>.md` for `STATUS: blocked` on every wake-up, not only at heartbeats.
- 2026-11-17 (round 6): a rebase brought in a new devDependency (@playwright/test, from another merged ticket) but `rebase-wt` does not reinstall, so `tsc` failed on files the ticket never touched. After merging a ticket that changes package.json, run `npm ci` in every in-flight worktree (or have rebase-wt do it when package-lock.json changed).
- 2026-11-17 (rounds 8-9): a fix brief listing 3-4 independent items got "partial" returns in about 2 minutes with every item listed as outstanding. When a ticket is past round 6, give one focused item per round (the correctness bug first, then each missing test), each with its own acceptance line.

## A blocked round with no changes still went to checks and review (2026-11-17)
Symptom: `ATTENTION: ... stuck: bin/review exit 3` after round 1; the worktree held only reviewer junk. The implementer had answered `STATUS: blocked, CHANGED: none` (it needed two files outside its touches), yet the pipeline ran the checks and a review on the empty diff; the reviewer started a local server and the tree restore failed.
Fix in the moment: read `<ISSUE>-impl-<n>.md` first. When the round is blocked on a scope question, widen the touches (decision), remove the junk under `.tmp/`, and `pipeline fix <ISSUE> <coordinator findings>`.
Since 2026-11-20 the pipeline routes `STATUS: blocked` to triage before any check or review.

## Orphaned check runs hang for hours (2026-11-20)
Symptom: `pipeline status` showed 7 tickets stuck in `checks` for up to 6 h; no `.check` file had been written for an hour; check and `pytest -n 4` processes at 0% CPU, all children of a dead check runner. The pipeline's `check_timeout_minutes` (60) never fired, because the runner holding the timer had died (machine load above 300 earlier that day). Effect: no check could finish, the machine stayed loaded, and leaked dev-server processes from merged worktrees added up (13 stopped by hand).
What the runtime does now: `pipeline run` stops a check that wrote nothing for `check_silence_minutes` (25) on each tick, whoever started it, and reaps every process whose working directory is the ticket's worktree before a rerun; `finish` reaps the worktree's processes before removing it (`lib.reap_worktree`).

## Rounds that could not succeed still paid checks and a review (2026-11-20)
Symptom: tickets came back `STATUS: blocked` or with an empty diff, and each still ran a full check and a review (about an hour) to learn nothing; ten full suites (unit, build, end-to-end, 25 min each) ran at once and unrelated tests timed out, sending tickets to triage for failures that were not theirs; other projects' check jobs on the same machine filled this project's `max_jobs`; most triages at round 5 were settled with "one more round"; later reviews raised new findings on code earlier rounds had passed.
What the runtime does now:
- `STATUS: blocked` goes to triage at once; a round that changed nothing is run again one tier up, then goes to triage.
- Two-level checks (`checks_fast` in state.json or `CHECKS_FAST:` in the ticket): fast checks each round, the full suite once after the review approves (stage `final`, `max_full_jobs` at a time).
- Check slots count this project's jobs only.
- Past `max_rounds`, a review with fewer findings than the previous one goes on by itself, up to `max_rounds_hard`.
- The review brief lists what the round was asked to fix: later rounds verify those first and block only on regressions, real defects and unmet acceptance criteria.
- Opt-in: `auto_start` (queued tickets whose blockers are merged and whose `Touches` do not overlap start alone) and `auto_merge` (approved tickets are merged by the loop).

## Old worktrees pile up (2026-11-20)

Symptom: worktrees of merged tickets, of tickets dropped from the plan and of tickets never started stayed on disk for days, with their branches. Each one costs disk, indexing and dependency installs, keeps servers alive, and a session resumed later can start editing a worktree no ticket owns.

What the runtime does now: `pipeline run` runs the worktree garbage collection every `gc_minutes` (60), and `/maxxfactory-continue` runs `bin/gc` first. Removed: worktrees of done tickets (leftover work saved as a patch in `.autopilot/gc/`), worktrees with no change and no commit for 24 h, and `autopilot/*` branches without a worktree. A worktree that holds work but is not in flight is never deleted: it is reported as an orphan and the coordinator decides at the next heartbeat.

## 2026-11-21: environment gaps sent good rounds to triage

- A fast check that runs `npm` directly does not load the project `.env`; a `just` recipe does. Write fast checks that need the environment as `set -a && . ./.env && set +a && ...`.
- A worktree created by `auto_start` has no `.env` (it is gitignored). Until the pipeline copies it by itself, the project `setup` step must copy it (`cp -n <repo>/.env .env`). An implementer without it writes its own from `.env.example`.
- `pipeline fix` on a ticket that was on hold does not rebase first: the implementer then works on a stale tree and reports itself blocked on files another ticket already changed. Run `rebase-wt` before dispatching such a round.
- An empty round after an environment failure is correct, not a stall: reset `round`, clear `tree`/`empty_retry`, and send the ticket back to checks.
- Two full suites at once on 16 cores (load 37-41) fail browser and container tests that pass alone. Keep `max_full_jobs` at 1 on one machine, and rerun the failing tests alone before sending an approved ticket back.
- Test runs rewrite tracked screenshots of other tickets and add `.next-dev-smoke` entries to `web/tsconfig.json`: restore them before a merge.

## QA run killed by the coordinator's own PLAN.md edits (2026-11-21)
Symptom: a 4-hour full QA ended with 9 suites "report missing"; the log shows "Dirty site refused". Cause: the QA read the site from the coordinator checkout, and `bin/decision add` rewrote PLAN.md there mid-run; the QA refuses a dirty site. Rule: long QA runs read a detached worktree frozen at a commit (`git worktree add --detach <wt>/qa HEAD`), never the checkout where the coordinator writes PLAN.md, decisions or notes.

## A run that looked alive and was waiting for nothing (2026-11-22)
Symptom: the owner asks "are we done?" and gets a long status with a table; hours later nothing has moved and the ETA is still two hours away. Three causes, each fixed in the runtime:
- The coordinator resumed through `/maxxfactory-continue`, which told it to read the run rulebook as a file. A compaction dropped it: no bars, no tick, no heartbeat from then on. Rule: the rulebook is loaded by invoking the `maxxfactory-run` skill, and invoked again after every compaction.
- The last ticket was held by the coordinator (stage `hold`), so the pipeline had nothing to approve and `wait-approval` could never return; the two tickets behind it needed the owner (a DNS switch), which no file recorded. Rule: `owner_wait` in state.json names every ticket that waits on the owner; `wait-approval` ends on DONE, WAITING ON OWNER, STUCK, and every 10 minutes.
- The held ticket had no `est`, so its ETA was "now + 141 min" at every reading. Rule: `bin/eta` prints the `RUN:` verdict first, shows a date only while the run moves, marks a date that rests on an unestimated held ticket as a guess, and leaves owner work out of it.

## Parity suites read a dist/ the site tests were rebuilding (2026-11-22)
Symptom: a final QA run had landing visual captures fail with `net::ERR_HTTP_RESPONSE_CODE_FAILURE` on pages that exist; dist/*.html timestamps were newer than the build step. Cause: the site's `npm test` ran in the background in the same worktree and rebuilt dist/ while parity:visual served it. Also: running the parity suites by hand without `PARITY_BASE=http://localhost:$SERVE_PORT` made them hit whatever listened on the default port 4321 (the test suite's server). Rule: run site tests in their own detached worktree, never beside parity suites on the same dist; always export PARITY_BASE with SERVE_PORT, as the QA runner does.

## A night lost to a login, a permission and two manual steps (2026-11-22)
Symptom: the coordinator's Claude login ended in the middle of the night; after the resume, the run waited until morning on `gh workflow run publish.yml`, which the permission system refused, and on a DNS switch planned as an owner click although a Cloudflare tool was connected.
Causes: nothing read the login's end date (`claude auth status` reports it); the permission template forbade pre-allowing a publish, so the one outward action of the plan needed a human; the plan listed manual steps without first checking what a CLI, an MCP tool or an API could do.
Rules:
- `bin/harness logins` before a run and on every resume; a login that ends before the run does is renewed first. The pipeline alerts 12 hours ahead.
- Every outward action is a row of the plan's `Pre-authorized actions`, approved once and pre-allowed with `bin/permit`; the owner types `! bin/permit apply` (an agent cannot write its own settings).
- `bin/access scan` before any prerequisite is asked: ask for access, not for clicks.

## New worktrees appear in a folder nobody chose; Spotlight indexes hundreds of thousands of files there (2026-11-22)
Symptom: `bin/eta` shows `SPOTLIGHT: <a folder outside the code folder> indexed (400000 items)` although the folder that holds the repo is excluded; `git worktree list` shows every ticket worktree under the home directory, named after a directory the repo no longer has. Cause: state.json recorded `worktrees_dir` as an absolute path at setup; the repo was later moved and renamed, the path stayed, and every new worktree went to the old place. The folder had been given a `.noindex` suffix, which did not stop the indexing.
What the runtime does now: the worktrees directory is always `<repo>-wt`, next to the repo, derived from where the repo is (`lib.worktrees_dir`); a `worktrees_dir` in an older state.json is ignored for new worktrees, its in-flight tickets finish where they are and `bin/gc` still collects them. `bin/pipeline wt <name>` is the one way to create a worktree by hand, and `pipeline start` refuses one outside the directory. `bin/spotlight check` checks the parent folder of the repo (one exclusion covers the repo, its worktrees and their neighbours) and is a step of init, plan, plan-more, run and continue.
Moving worktrees that are in flight: stop the pipeline and every process running in them first, move the directory, `git worktree repair <each path>`, rewrite the `wt` of each `inflight` entry with `bin/state`, then start the pipeline again.

## The runtime's own repo carried the name of the project a lesson came from (2026-11-22)
Symptom: lesson headings named a project. Cause: nothing checked what an update of the runtime writes. Rule: the runtime is changed only through `/maxxfactory-update` (general rules, conflict check with the rules in place, the owner decides contradictions), and `bin/leak check` refuses identities, home paths, e-mails, tracker identifiers and the owner's private terms in the pending change.

## A failure mail from CI after every merged ticket; CI minutes spent on a draft PR (2026-11-22)
Symptom: the owner receives "CI: All jobs have failed" mails every few minutes during a run; `gh run list` shows one `pull_request` run per push of the project branch, each several minutes long, on a PR that is a draft. Cause: the PR was opened as a draft as the rule says, but a draft PR still triggers `pull_request` workflows on every push, and the run pushes once per ticket; nothing read the workflows before the first push.
What the runtime does now: the workflows are read at planning and before the first push, and one that would run on the project branch or a draft PR is changed first, with the owner's agreement (jobs carry `if: github.event.pull_request.draft == false` and the trigger lists `ready_for_review`; push triggers name the branches that deploy). `bin/ci check` (setup, heartbeat, resume, and the pipeline's hourly housekeeping, which raises a CRITICAL alert) finds a PR that is not a draft or a run that started on the last push; the answer is `push` false until it is fixed. CI runs once, when the PR is marked ready to merge (`pr_ready`).

