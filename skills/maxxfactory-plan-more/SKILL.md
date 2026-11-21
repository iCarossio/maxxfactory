---
name: maxxfactory-plan-more
description: /maxxfactory-plan for a project that already exists. Plans more work for a Linear project planned with /maxxfactory-plan or running under /maxxfactory-run. Three shapes, chosen with the user. One or a few tickets added to a current milestone, a QA pass added to a current milestone, or a new major milestone. Takes new scope from the user, or ideas parked with /maxxfactory-idea (promoted and closed as duplicates of their tickets on approval). Tickets added to an existing milestone inherit its KPIs and pre-mortem and get an adversarial plan review by a Tier 1 model of another vendor; a new milestone is refused without measurable KPIs and gets a pre-mortem and the plan review. Every finding is shown to the user, the accepted ones are folded in, and only after the user approves are the Linear issues (and milestone) and relations created, PLAN.md appended, the decision logged and the ETAs recomputed. Use when the user says "plan more", "add a ticket", "add tickets to the milestone", "add a QA pass", "add a milestone", "extend the project", "new phase", "promote idea ENG-40", "schedule these ideas", "/maxxfactory-plan-more [ENG-40,...]", or brings new scope for a project the autopilot already knows.
---

# Autopilot: plan more

**Caveman, always.** Your first action, before any other tool call: invoke the `caveman` skill (`/caveman`), and keep it for the whole session, including after a resume or a context compaction (invoke it again then). If it is not installed, follow its rules anyway: answer first, no ceremony, commands, paths, numbers and errors verbatim. Every subagent you start talks caveman too: `run-model` adds the rule to every model prompt by itself, and every Agent-tool (subagent) prompt you write starts with "Invoke the `caveman` skill first and answer terse." Persisted text stays plain prose: code, comments, docs, commits, Linear, `PLAN.md`.

This is `/maxxfactory-plan` for a project that already exists: the same planning care and the same approval, scoped to what is added and fitted into the plan that is already running.

You are the **planner**. A project exists: `PLAN.md` at the repo root, `.autopilot/state.json`, a Linear project, maybe tickets in flight under `/maxxfactory-run`. You add work to it. The user is present: ask what you need, show your work, and create nothing in Linear before the user approves.

## Which shape

Decide it first, with the user when it is not obvious, and say which one you took:

| Shape | When | Spec | Treatment |
|---|---|---|---|
| **Tickets** | one or a few tickets that serve a milestone that exists (a missing piece, a fix, a follow-up) | `"into": "<milestone id>"` | plan review, approval |
| **QA pass** | checking what a milestone built: test suites, parity runs, a manual checklist turned into tickets | `"into": "<milestone id>"` | plan review, approval |
| **New milestone** | scope with its own outcome: it needs a KPI the current milestones do not have, or about 8 tickets and more | no `into` | KPIs, pre-mortem, plan review, approval |

Tickets added to a milestone inherit its KPIs, rules, guardrails and pre-mortem; that is why they skip the KPI gate and the pre-mortem. If the added tickets need a KPI of their own, or the plan reviewer says they widen the milestone, it is a new milestone: do not stretch `into` to avoid the pre-mortem. The steps below apply to the three shapes; where they differ it is marked **(into)** or **(new milestone)**.

A QA pass is at least: one ticket that runs the suites or the checklist and reports (per-suite counts, report paths, no fixing), then fix tickets cut from its report. When the failure list is not known yet, plan the run ticket alone and come back with its report; a big list is split as in `references/fanout-qa.md` (one diagnosis per scope, one sub-ticket per root cause).

`bin/<x>` below means the `bin` directory next to this SKILL.md (`~/.claude/skills/maxxfactory-plan-more/bin/<x>` after `install.sh`, `${CLAUDE_PLUGIN_ROOT}/skills/maxxfactory-plan-more/bin/<x>` as a plugin). Everything goes through `bin/milestone add`; never hand-edit `state.json`, the milestone sections of `PLAN.md` or Linear for this.

| Script | Role |
|---|---|
| `bin/milestone` | `add <spec>` (a new milestone, or with `"into"` tickets of an existing one): validation, pre-mortem of the delta (new milestone only), plan review, approval stop, decision, Linear, `PLAN.md`, state, bars. Resumable. `list`, `recompute`, `sync` (dates, bars, and tidy), `tidy [--dry-run]`. |
| `bin/decision` | The sourced Decision log in `PLAN.md`. |
| `bin/eta` | One bar + ETA per milestone, then overall. `--from-mcp FILE` schedules from a Linear MCP `list_issues` snapshot (no `LINEAR_API_KEY`); a proposed milestone stays on the bars. |
| `bin/idea` | `list`, `promote ENG-1,... --id --name` (new milestone) or `--into <milestone id> --id <batch slug>` (tickets): turns parked ideas into this skill's spec skeleton. |
| `bin/bgrun` | Runs the 10-40 min review under a stall and timeout watchdog. |

Not this skill: a project with no `PLAN.md` / no Linear project yet (`/maxxfactory-plan`); grouping tickets that already exist into a milestone (`bin/milestone adopt`, see `/maxxfactory-run` setup); a change the running coordinator makes by itself during a re-plan, such as a split or a follow-up a review asked for (a decision under `/maxxfactory-run`, "Changes of plan"); an idea to keep for later without planning it (`/maxxfactory-idea`).

## Inputs

The work comes from one of:
- **New scope from the user** (a message, a doc, a spec): start at step 0.
- **Ideas parked with `/maxxfactory-idea`**: identifiers (`/maxxfactory-plan-more ENG-40,ENG-41`), titles ("the RBAC idea"), or "promote the ideas about X". Resolve them with `bin/idea list` (match titles there; ask only if two ideas match). Propose the ideas related to them (`related` column) and let the user decide which come along: an idea left out stays parked. Then, after step 0:
  ```
  bin/idea promote ENG-40,ENG-41 --id <milestone-slug> --name "<milestone name>"
  ```
  **(into)** `bin/idea promote ENG-40 --into <milestone id> --id <batch-slug>` instead: the same skeleton with `"into"`, without KPIs and plan to fill.
  It writes the skeleton `.autopilot/plan/milestones/<id>/spec.json`: the owner's words of every idea quoted in `description`, one placeholder ticket per idea (`from_idea`), KPIs, plan and ticket instructions marked `TODO`, and `from_ideas`. If a skeleton already exists for that id (an earlier, interrupted session), continue from it; `--force` only when the user wants to start over.
- **A skeleton or spec already on disk** (`.autopilot/plan/milestones/<id>/spec.json`): continue from it; `status.json` next to it says which steps of `bin/milestone add` already ran.

## 0. Context

1. Find the repo (`.autopilot/state.json`); read `PLAN.md` (goal, KPIs, architecture, rules, pre-mortem, Decision log, existing milestone sections), `bin/milestone list` and the head of `bin/eta`.
2. `bin/decision check`: pending decisions are synced first; a new milestone is not built on an unsynced plan.
3. Is `/maxxfactory-run` active on this project (inflight tickets in state, running `run-model` processes)? Then the run keeps going on the current milestones while you work: never pause it, never touch its worktrees. `bin/milestone add` writes state under the lock; the coordinator picks up the new queue at its next re-plan.

## 1. Intake gate (nothing planned without expectations)

Show the project's `Model tiers per phase` table from `PLAN.md` with the pools of today (`bin/run-model pool <role>`); the owner confirms it or changes it for this milestone (a change is a decision).

**(into)** Show `bin/milestone list` and confirm the milestone the tickets join. Ask only: what must exist or be checked when they are done, how it is verified (the acceptance and the `CHECKS:` of each ticket), which of the milestone's KPIs it serves, and whether it must land before something in flight. No KPI of its own: if the user needs one, it is a new milestone. Then go to step 2.

**(new milestone)** Ask for, and do not proceed without the following. For promoted ideas, the owner's words quoted in the skeleton are the starting point, not the answer: an idea says what, rarely how much or how it is measured. Restate each idea in one line, then ask only what it leaves open.
1. **What exists when the milestone is done**, for whom, why now, and what is out of scope.
2. **Milestone KPIs**: each with a target and a measurement (command, query, count, date). Push back on vague ones; if the user cannot name one, propose three and let them pick. No measurable KPI: stop here.
3. **Ordering**: must it wait for a current milestone, run beside it, or preempt it? A deadline?
4. **Design bar** (any milestone with a UI): the references the owner names or shows, saved under `.autopilot/plan/milestones/<id>/refs/`, and the look criteria, exactly as in `/maxxfactory-plan` step 0 item 5. A reference the owner gives is a success criterion: the milestone gets a design KPI (screenshots side by side with the references, owner sign-off) and every UI ticket gets look criteria and screenshot acceptance. Functional KPIs never stand in for it.

Keep the user's answers verbatim: they are the `user:"..."` source of the approval decision. A promoted idea whose answers turn it into something else than its words (narrowed, split, merged with another) is fine: say so in `why`, the idea's words stay quoted in `description`.

## 2. Draft the spec (you, Tier 1)

Read the code the milestone touches before writing (conventions, existing checks, the notes of the tickets it builds on, `docs/notes/*`). Then write `.autopilot/plan/milestones/<id>/spec.json` (format: `bin/milestone --help`):
- `id`, `name`, `description`, `why`, `kpis` (ids `<id>-K1`, ...).
- **(into)** `"into": "<existing milestone id>"`, and `id` is a new slug for this batch (`core-qa-2`, `auth-followups`; never the id of a milestone), `name` a short label for it ("QA pass 2"). No `kpis` (only a KPI this batch adds to the milestone, rare) and no `plan` unless the tickets need a rule of their own. The directory is still `.autopilot/plan/milestones/<id>/`.
- `plan`: markdown with the goal, the architecture decisions (with rejected alternatives), the rules and guardrails of this milestone, and a `Pre-mortem` table filled in step 4.
- `tickets`: as in `/maxxfactory-plan` step 6: precise instructions for a cheap implementer, `CHECKS:` line, `**Acceptance**`, guardrails, what not to touch, and `touches` (the files or modules it changes). One ticket is one commit. **Atomic tickets (enforced).** Splitting the work is a goal of planning, not a detail. Every ticket is one concern of at most about 400 changed lines, estimate S or M (never L: split it), and declares `touches`: the files or modules it changes (max 8). Two tickets that can run in parallel never change the same file outside a shared test or docs path (a directory named tests, test, __tests__ or docs at any depth, or a file named *.test.*, *.spec.*, test_*.py or *_test.py): give each hot file (an API router, the runtime, a shared store) one owner per stage, and chain the others with `blocked_by`. Prefer vertical slices that each ship a working, checked piece over a big ticket and a cleanup ticket. `bin/linear import` and `bin/milestone add` refuse a ticket list that breaks these rules, and the plan review checks them. Why: on 2026-11-12 an L ticket (22 files, +2051/-638 lines) took 18 rounds: each new reviewer found new bugs in the big diff, and parallel tickets editing the same files forced 5 merge rounds. Tickets of this milestone that change a file a ticket in flight also changes are blocked by that ticket. Include the unglamorous ones: integration with the existing milestones, real-data fixtures, docs merge, final QA against the milestone KPIs. **Fan-out: contract first, then one reference (enforced by the plan review).** When three or more tickets apply the same pattern (convert N pages, add N connectors, port N endpoints), the plan has, before them: (1) a contract ticket that lands every shared type, prop and component signature the N tickets need, so none of them has to touch a shared file; (2) one reference ticket, implemented at Tier 1 (`inflight.<ISSUE>.pool` or a `Tier 1` note), that converts the first instance end to end (code, tests, screenshots, notes) and that every other ticket of the fan-out is blocked by and names as the pattern to copy. A ticket that would need a shared file changed stops with `STATUS: blocked` (the pipeline hands it to the coordinator at once). **No shared ledger files.** A docs or test-helper file that every ticket of a fan-out edits (an inventory, a registry, a list of headings) is generated from the code or split into one file per ticket. Why: on 2026-11-20 ten parallel page conversions each hit the same missing prop, invented their own, and spent 1 to 3 extra review rounds each on it; every one of them also edited the same shared inventory file, which produced merge rounds and a red project branch.
- **Checks in two levels.** Give each ticket a `CHECKS_FAST:` line (or the project a state.json `checks_fast`): typecheck, lint and the tests of what it touches, a few minutes. The full suite (`CHECKS:`) runs once, after the review approves.
- `blocked_by`: real dependencies only, on new slugs or existing issues (`ENG-12`). An ordering-only dependency on a current milestone is not a blocker: say it in `plan`.
- Latest stable technologies for anything new, verified on this machine, as in `/maxxfactory-plan` step 1; existing dependencies keep their versions.

From promoted ideas: replace every `TODO` (the real add refuses one; `--dry-run` only warns). Each placeholder ticket becomes as many real tickets as the idea needs; every ticket that implements an idea keeps `"from_idea": "<its identifier>"`, and `from_ideas` stays as written, so the approval links each idea as a duplicate of its tickets and closes it. Integration, fixtures and QA tickets carry no `from_idea`. An idea the user drops during intake: remove it from `from_ideas` and from its tickets; it stays parked.

Then `bin/milestone add <spec> --dry-run`: fix every validation error, and show the user the stages and the ETA of every milestone with this one added. If it pushes an existing milestone's ETA, say so now.

**(into)** The dry run prints `valid: N tickets into milestone '<name>'`, and from then on the milestone's own bar reads "<name> (+N proposed)" until approval; `bin/milestone proposed --drop <batch id>` drops the draft.

From this first `--dry-run` on, the milestone is **proposed**: `bin/eta` and `bin/pipeline status` show it as its own bar, "<name> (proposed) ... (awaiting approval)", on a what-if schedule, so the owner sees it in every progress update without asking. The approval (`--approved`) turns it into a real milestone; a draft the owner drops is removed with `bin/milestone proposed --drop <id>`.

## 3. Adversarial review (plan review; pre-mortem for a new milestone)

```
bin/run-model usage --apply
bin/bgrun --name milestone-<id> --idle 1800 --timeout 5400 --watch .autopilot/plan/milestones/<id> -- bin/milestone add <spec> --planner <your roster key>
```
in the background (10-40 min; a few minutes for tickets added to a milestone), while you re-read the spec. It runs:
- **(new milestone only)** a **pre-mortem** of the milestone by a Tier 1 model of another vendor (the milestone's adversarial review), two passes (the reasons, then an adversarial self-review against the repo), with the existing plan as context, so it raises how this milestone fails and how it breaks what is already planned; into `.autopilot/plan/milestones/<id>/premortem.md`;
- a **plan review** by a Tier 1 model of another vendor (`POOL=plan_review`): fit with the existing architecture, tickets and KPIs, real and complete dependencies, measurable KPIs; into `.../plan-review.md`. **(into)** The reviewer is told the tickets inherit the milestone's KPIs and guardrails, and checks that they serve it without widening it, that their dependencies on existing tickets are real, and that each is atomic. The pre-mortem is skipped by the runtime and the reason is logged in the decision.

Exit 3 is the expected stop (needs approval). Exit 2: a review gave nothing usable; wait for a reset (`bin/run-model wait premortem`), and tell the user when it lasts. Neither your own vendor nor a Tier 2 model is ever a substitute (the old `--allow-mid` is gone). `--review-k 2` adds a second plan reviewer of a distinct vendor only when the user asks.

## 4. Show everything to the user, then fold

**(into)** There is no pre-mortem table: paste the plan-review findings verbatim with your verdict on each, fold the accepted ones into the tickets (instructions, `CHECKS:`, `blocked_by`, a split), and show the ticket table and the ETAs from a new `--dry-run`. A finding that says the tickets widen the milestone is settled with the user: narrow them, or restart as a new milestone.

Paste the pre-mortem table and the plan-review findings verbatim (every reason, probability, impact, early signal, guardrail; every finding), plus your verdict on each: accept, reject with evidence, or merge. Do not soften them.

For each accepted reason or finding, give it a home in the spec: a milestone KPI, a `CHECKS:` command, a dedicated ticket with `blocked_by`, or a rule in `plan`. Fill the `Pre-mortem` table of `plan` (reason, verdict, guardrail, where it lives; rejected ones with their evidence): it lands in `PLAN.md` with the milestone, so every change made because of the review keeps its source.

If a reason changes something **outside** the milestone (an existing ticket's scope or blockers, an existing KPI, a shared rule), that is a decision on the current plan: after approval, `bin/decision add --source premortem:<id>/PM-<n>` (or `plan-review:milestone-<id> m<n>`), apply it under `/maxxfactory-run`'s "Changes of plan", then `bin/milestone recompute` and `sync --decision D-<n>`.

Show the updated spec (KPIs, ticket table, pre-mortem table, ETAs from a new `--dry-run`). Iterate until the user approves.

**Re-review after a material fold.** A rerun of `bin/milestone add <spec>` without `--approved` detects the changed spec and runs the pre-mortem and the plan review again. Do it when the fold added scope, tickets or architecture. When it only added the guardrails the reviewers asked for, the user may approve directly.

## 4b. Human prerequisites gate (both shapes)

Same rule as `/maxxfactory-plan` (step 1 and step 5b): walk every ticket of the spec and list what only a human can provide (an account, an API key or token, an OAuth app, a paid plan, DNS, an access grant, real data, a test user, a sign-off) that the project's `Human prerequisites` table of `PLAN.md` does not already hold as `provided`. Ask for all of it in one message, with `! pbcopyenv <NAME>` for every secret (never pasted in the chat), run each row's verify command yourself, and add the rows to the table. A row the owner cannot provide today is `deferred`: fallback, tickets held back (`blocked_by`, scheduled last), logged with `bin/decision add --source user:"<their words>"`. Do not run step 5 while a row is `missing`. Nothing needed: say so in one line and go on. A project with no table yet (planned before this rule): create it now for the whole remaining queue, not only for the added tickets.

## 5. Apply (only after approval)

```
bin/milestone add <spec> --approved --by <owner> --source user:"<their approval, verbatim>"
```
**(into)** It logs the decision ("milestone <name>: N tickets added"), creates the issues in the existing Linear milestone with their `blocks` relations, adds a subsection to that milestone's section of `PLAN.md`, appends the issues to the milestone in `state.json` (recorded under its `additions`) and recomputes and syncs as below. No Linear milestone is created.

**(new milestone)** It logs the decision, creates the Linear milestone, issues and `blocks` relations in the existing project (checkpointed: a rerun never duplicates), appends the milestone section to `PLAN.md`, updates `state.json` (milestones, blockers, sizes) and recomputes `queue`, `stages`, `critical_path`, then syncs the target dates and bars to Linear and marks the decision synced. After any failure, rerun the same command: it resumes after the last completed step.

When this milestone was first created as its own Linear project and then folded into the existing one, that project is left empty. Keep its creation checkpoint: `project_created: true` and `created_project_id` set to that project (see `/maxxfactory-plan`, folding). Sync runs tidy, which archives that created project and not the destination. Tidy also deletes an empty milestone that is not in state.json, except the "Ideas (unscheduled)" milestone and any milestone that still has an issue, including one whose only issues are archived.

A step is skipped only with `--skip-premortem "<why>"` / `--skip-review "<why>"`, with the user's consent; the reason is written into the decision.

Then: apply the outside-the-milestone decisions from step 4, run `bin/decision check` (must pass), and if `PLAN.md` is tracked on the project branch commit it alone (`docs(plan): milestone <name>`, or `docs(plan): <name>: <batch label>` for added tickets).

## 6. Handoff

Tell the user in a few lines: the shape you took, the Linear milestone link, the ideas closed into it (with their new tickets), the number of tickets, the top three failure reasons and their guardrails (a new milestone) or the findings folded in (added tickets), the `bin/eta` lines (one bar per milestone), and what happens next: the running `/maxxfactory-run` picks the tickets up at its next re-plan; if none is running, `/maxxfactory-run` starts them.

## Rules

- No human prerequisite left open at apply time (step 4b): `provided` and verified, or `deferred` with a fallback and a decision.

- You plan; you never implement. Reading the repo is allowed, editing code is not.
- Reviewers are read-only and never of your own vendor or model (`--planner` excludes them).
- Keep every reviewer's full output on disk under `.autopilot/plan/milestones/<id>/` and never paraphrase a reason into something weaker.
- No decision unsourced: the milestone itself, every change it forces on the existing plan, and every skipped step have a Decision log row synced to Linear.
- Budget: one pre-mortem (two passes) and one plan review per new milestone, one plan review per batch of added tickets, plus one rerun after a material fold. Never pay for extra credits: wait for a reset.
