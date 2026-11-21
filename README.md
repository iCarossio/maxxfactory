# maxxfactory

**A lights-out software factory for AI coding agents.** Tokenmaxxing, but every token goes to the right tier.

You bring a plan and the AI coding subscriptions you already pay for. maxxfactory turns the plan into a Linear project, then runs it unattended for hours, ticket by ticket, like a production line:

- **Design office.** A flagship model plans the work, and a flagship of another vendor runs a pre-mortem on it: "we are at the deadline and we failed, why?"
- **Assembly line.** Cheaper models build each ticket in its own git worktree, many tickets in parallel.
- **Quality control.** A model that did not build the ticket inspects it, preferably from another vendor. A ticket goes back to the line until it converges: checks green, review approved, one clean commit.
- **Lights out.** State lives on disk and in Linear, not in a chat. Runs survive restarts, quota outages and compacted sessions; you are called only for a critical alert.
- **Every machine at full capacity, nothing wasted.** Each role draws from its tier by the credit left on every subscription, so every plan is used before its reset. Models come back the minute their quota resets, credits are never bought, and small atomic tickets plus capped review rounds keep tokens from being burnt in loops.

## Skills

Skills for Claude Code (or any harness that reads `~/.claude/skills`):

| Skill | When | What it does |
|---|---|---|
| `/maxxfactory-init` | once per machine | finds your CLIs and their accounts, asks which subscriptions you pay for, gives every model its tier, smoke-tests them, prints what each role can use and what is missing |
| `/maxxfactory-plan` | once per project | your plan and KPIs, a pre-mortem by a flagship of another vendor, guardrails, then the Linear project with milestones, tickets and dependencies |
| `/maxxfactory-plan-more` | when the project grows | plans more work for an existing project, from new scope or from parked ideas: tickets or a QA pass added to a current milestone (plan review and your approval), or a new milestone (KPIs, pre-mortem, plan review, approval) |
| `/maxxfactory-run` | per project, for hours | runs the tickets: plan, review the plan, implement, review the code, repeat until approved, one commit per ticket, Linear kept up to date |
| `/maxxfactory-continue` | after a session ends | resumes a run where it stopped, without setup questions |
| `/maxxfactory-idea` | any time | parks your quick ideas, verbatim, in an "Ideas (unscheduled)" milestone, out of every ETA, until you promote them |
| `/maxxfactory-status` | any time | every configured model, its subscription, the share of its 5-hour, weekly and monthly quota used, and when each resets |
| `/maxxfactory-usage` | any time | tokens consumed, in total and per harness, today, over the last 7 days and the last 30 days |
| `/maxxfactory-clean` | any time | commits what is worth keeping, deletes junk, removes orphan and finished worktrees and merged branches, reports the work in progress to resume with `/maxxfactory-continue` |

## Methodology

maxxfactory exists because cheap models write good code when the work is planned well, cut small and checked by someone else, and because most subscriptions expire unused. Each rule below answers a way long agent runs fail.

- **Planning with the brain.** Thinking is done by the strongest models; typing by cheaper ones. A Tier 1 flagship (the coordinator) plans the project and writes every ticket's brief; Tier 2 models implement and review it. The brain never writes code, the hands never decide scope.
- **KPIs.** No plan starts without measurable expectations: each KPI has a target and a way to measure it (a command, a query, a count, a date). "Works well" is refused.
- **Definition of done.** Every ticket carries its acceptance criteria and its checks (`CHECKS:` line). Done means the checks pass, a reviewer approved with no blocking finding, and the work is one commit on the project branch.
- **Deadlines.** Every plan and milestone has a date. The ETA is a schedule of the remaining tickets (stages that run in parallel, one after the other), shown as one progress bar per milestone and mirrored on Linear.
- **Pre-mortem.** Before any ticket exists, a flagship of another vendor is told "we are at the deadline and the project failed: why?". Each reason becomes a guardrail: a KPI, a check, a ticket or a rule.
- **Adversarial review.** No model reviews its own work: the implementer of a ticket never reviews it, and the planner's vendor never reviews the plan. Enforced in code.
- **Measurable and atomic tickets.** One ticket is one concern, about 400 changed lines at most, one commit, with the files it touches declared so parallel tickets never collide. Bigger is split, tiny is grouped.
- **Model convergence.** A ticket loops implement → review → fix until the reviewer approves. After round 3 the implementer is escalated (a fresh Tier 2 model, or one tier up for a project pinned to Tier 3) instead of looping on the same mistakes. A review counts only if it parses, did not touch the code, and an "approve" carries no blocking finding.
- **Long autonomous sessions.** A run lasts hours with you away. State lives on disk and in Linear, not in the conversation, so a new or compacted session resumes exactly (`/maxxfactory-continue`). Every change of plan is logged with its source (`bin/decision`). You are interrupted only for a CRITICAL alert.
- **Spend what you pay for, never more.** Inside a tier, models are drawn by the credit left on each subscription, so every plan is used before its reset. Quota resets are reused the minute they happen; credits are never bought.

## Tiers

The default tier table (`DEFAULT_TIER_TABLE` in `bin/autopilot_lib.py`, overridable in `models.json`) gives every model a level:

| Tier | Examples | Role |
|---|---|---|
| 0 frontier | Claude Fable and Mythos, GPT-6 Astra, Gemini 4 Carbon | never automatic; only with `--allow-tier0` |
| 1 flagship | Claude Opus, GPT-6.1 Sol, Gemini 4 Argon, GLM-5.3, Kimi K3, Qwen 3.8 Max, DeepSeek V4 Pro, Muse Spark | coordination, plan reviews, pre-mortems, milestone reviews; backup code reviewer |
| 2 balanced | Claude Sonnet, GPT-6.1 Terra, Gemini 4 Hydrogen, Gemini 3.8 Flash, Grok 4.7 and 4.3, Mistral Large 4 ("Le Chonk", through Vibe), DeepSeek V4.1 Flash, Qwen 3.8 Flash and Plus, GLM-5.3 Flash (paid ids, e.g. OpenCode Go) | implement and review tickets (never the same model on one ticket) |
| 3 fast | Claude Haiku, GPT-6 Luna, Gemini Flash-Lite | implementation, only in a project pinned to it |
| 4 small and free | the free models of opencode and OpenRouter: Poolside Laguna, NVIDIA Nemotron (Super, Ultra, Lightning, Nano), Xiaomi MiMo Flash, Google Gemma 4, Inkling, LongCat, Hy4 Flash, Flint, Ling, ERNIE Flash, Beam, the `-free` ids of DeepSeek and GLM, `openrouter/free`; every Mistral model but Large; Gemini older than 3.5 | trivial tasks only |

A model's tier comes from the first matching row of `DEFAULT_TIER_TABLE`; any model id with `free` in it (`opencode/*-free`, OpenRouter `:free`) is Tier 4 whatever the table says. To trust one above its tier (e.g. a free model you want as a Tier 2 reviewer), set `owner_tier` on its roster entry with your reason: it then keeps its `level`, and `no_implement` limits it to reviews.

Rules enforced in code:

- **Roles keep their tier.** A tier out of quota waits for its reset; it never silently falls to another. One exception: when no Tier 2 reviewer is eligible, the code review falls back to Tier 1 (logged).
- **Weighted draw.** A role's model is drawn at random among its tier, weighted by credit left, subscription (paid, unconfirmed, free) and an optional per-model `capacity` (overridable per project in `state.json`).
- **Vendor's own CLI.** Anthropic through Claude Code, OpenAI through Codex, Google through Antigravity, Mistral through Vibe, xAI through Grok; other vendors through pi (OpenCode Go) or opencode (free models).
- **No speed variants.** `-fast` variants cost more for the same quality and are refused (Flash and Flash-Lite are families, not speed variants).
- **The coordinator's account is protected.** Detected at run time; models on it run last, for cheap roles only, while it keeps a reserve (30% of the 5-hour window, 20% of the weekly one). `coordinator_as_peer: true` in `models.json` draws it like any other account; the reserve still applies.
- **Latest versions.** `run-model discover --apply` (daily) finds newer model ids, smoke-tests them and switches the roster.

`bin/harness check` shows, per role, the candidates and what is missing.

## Supported harnesses

One JSON adapter per CLI in `harnesses/`. Several logins of one CLI are several accounts, each with its own quota.

| Harness | CLI | Accounts | Quota probe | Token log |
|---|---|---|---|---|
| Claude Code | `claude` | `CLAUDE_CONFIG_DIR` | `/usage` | yes |
| OpenAI Codex | `codex` | `CODEX_HOME` | session logs | yes |
| Google Antigravity | `agy` | one | `/usage` | yes |
| xAI Grok | `grok` | `GROK_HOME` | `/usage` | yes |
| pi (OpenCode Go) | `pi` | `PI_CODING_AGENT_DIR` | OpenCode Go limits | yes |
| opencode | `opencode` | `XDG_DATA_HOME` | OpenCode Go limits (free models: none) | yes |
| Mistral Vibe | `vibe` | one | billing | no |
| Google Gemini CLI | `gemini` | one | none | yes (untested) |

Google models run through Antigravity; the Gemini CLI adapter is shipped but untested, and the vendor-to-CLI rule keeps Google models off it. Add any other CLI with a non-interactive mode with `bin/harness new` (see `/maxxfactory-init`).

## Under the hood

- **Pipeline.** `bin/pipeline` moves every in-flight ticket on by itself (implement, rebase, checks, review, next round) in parallel git worktrees; the coordinator only merges approvals (`bin/pipeline merge`), or not even that with `auto_merge`; `auto_start` starts the next unblocked tickets.
- **No wasted rounds.** Fast checks every round, the full suite once after approval; a blocked or empty round goes to the coordinator before any check or review; reviewers verify the previous findings first and cannot move the goalposts; a ticket still open after round 5 goes to the coordinator for triage, unless its reviews keep converging (hard stop at round 8); `CHECKS:` lines that are not shell commands are refused; hung checks and leaked processes are reaped.
- **Milestones and ETA.** `bin/milestone` and `bin/eta`: one progress bar and ETA per major milestone, synced to Linear.
- **Decision log.** `bin/decision`: every change of plan, with its source, in `PLAN.md`.
- **Alerts.** `bin/alert`: CRITICAL alerts (a vendor out of quota everywhere, a role with no model), also posted on the Linear project.
- **Quota recovery.** `run-model usage --apply` cools down exhausted models until their exact reset; free Codex and Claude weekly resets are claimed automatically (`codex_auto_reset`, `claude_auto_reset`; never a paid option).
- **One commit per ticket.** `bin/rebase-wt` brings a worktree onto the project branch head, `bin/finish` commits the ticket as one commit, cherry-picks it onto the project branch and removes the worktree.
- **Only live worktrees.** The pipeline removes finished and never-started worktrees and their branches every hour (`bin/gc`), stops what still runs in them, and reports the ones that hold unmerged work instead of deleting them.
- **Spotlight off.** `bin/spotlight check` (macOS): agents rewrite thousands of files an hour, and an indexed repo or worktrees directory keeps Spotlight busy all day. Init, run and resume check it; `bin/eta` warns while a tree is indexed.
- **Housekeeping.** `bin/docker-up` / `bin/docker-reap` keep the Docker daemon up and remove dead containers; `bin/bgrun` runs long commands under a stall watchdog.
- **Linear without MCP.** `bin/linear` is a minimal GraphQL client (`LINEAR_API_KEY`) for harnesses that have no Linear tools.
- **Nothing personal in the repo.** Roster, accounts and cooldowns live in `~/.config/maxxfactory/`; project state in `<repo>/.autopilot/`.

## Commands

The skills are the interface; they call the runtime in `bin/`, which you can also run by hand (the header of each file documents its usage).

| Command | What it does |
|---|---|
| `install.sh [--agents] [--import <models.json>]` | links the skills and creates the user config |
| `bin/harness` | registry of CLIs, accounts and the model roster: `init`, `discover`, `list`, `check`, `pools`, `adapters`, `whoami`, `add-model`, `add-account`, `subscription`, `set`, `set-home`, `remove`, `new`, `migrate` |
| `bin/run-model` | `run` runs one model for one role and prints one JSON line; also `pool`, `whoami`, `smoke`, `discover`, `health`, `reset`, `wait`, `usage`, `status`, `alerts`, `vendor` |
| `bin/pipeline` | the ticket clock (implement, rebase, checks, review, fix rounds): `run`, `start`, `fix`, `retry`, `merge`, `status`, `wait-approval` |
| `bin/mkbrief` | fills the brief of an implementer, reviewer, plan reviewer or diagnosis from `prompts/` |
| `bin/review` | sends one round to one or several reviewers and prints compact verdicts |
| `bin/premortem` | pre-mortem of a plan by flagship models of other vendors |
| `bin/milestone` | milestones in `state.json` and Linear, each with its progress bar and ETA: `list`, `seed`, `add` (a new milestone, or tickets into an existing one), `adopt`, `recompute`, `sync`, `tidy`, `proposed` |
| `bin/idea` | parks, lists and promotes ideas in the "Ideas (unscheduled)" milestone |
| `bin/eta` | progress bar and ETA of the project (`-v` adds the schedule) |
| `bin/decision` | the sourced decision log in `PLAN.md` |
| `bin/state` | locked edits of `.autopilot/state.json` |
| `bin/alert` | lists, raises and resolves CRITICAL alerts |
| `bin/rebase-wt` | brings a worktree's ticket work onto the project branch head |
| `bin/finish` | commits a ticket as one commit, cherry-picks it onto the project branch, removes the worktree |
| `bin/gc` | removes the worktrees and branches no ticket needs any more (`--dry-run`) |
| `bin/tokens` | tokens consumed per harness and account, from the CLIs' local logs |
| `bin/linear` | minimal Linear GraphQL client (`LINEAR_API_KEY`) for harnesses without Linear tools |
| `bin/codex-reset`, `bin/claude-reset` | claim a free weekly usage reset on one account (never a paid option) |
| `bin/spotlight` | checks that Spotlight does not index the trees agents write to (macOS) |
| `bin/docker-up`, `bin/docker-reap` | start the Docker daemon when it is stopped; remove dead containers |
| `bin/bgrun` | runs a long command under a stall watchdog |
| `tests/selftest.sh` | behavioural suite against a fake harness (no quota spent) |

## Install

```bash
git clone https://github.com/iCarossio/maxxfactory
cd maxxfactory && ./install.sh
```

`install.sh` symlinks the nine skills into `~/.claude/skills` (`--agents` also links them into `~/.agents/skills`, for other harnesses that read the Agent Skills layout) and creates `~/.config/maxxfactory/` (`--import <models.json>` starts from an existing roster).

The links are absolute paths into this clone. **If you move or rename the clone, run `./install.sh` again**: the old links dangle and the skills (`/maxxfactory-continue` and the others) silently disappear from Claude Code.

Then run `/maxxfactory-init`. Requires Python 3.9+, git, a Linear workspace, and the model CLIs you want to use, logged in. On macOS, exclude the folder that holds your code from Spotlight (System Settings > Spotlight > Search Privacy); `bin/spotlight check` verifies it.

Upgrading from `linear-autopilot`: run `./install.sh` again from the renamed clone (see above); an existing `~/.config/linear-autopilot/` keeps working until you rename it to `~/.config/maxxfactory/`.

## Layout

```
skills/      one SKILL.md per skill
bin/         shared runtime (run-model, pipeline, review, premortem, milestone, eta, tokens, harness, gc, ...)
harnesses/   one JSON adapter per CLI
prompts/     briefs for implementers, reviewers and the pre-mortem
templates/   example roster, state, plan and ticket
references/  lessons from real runs
tests/       behavioural suite against a fake harness (no quota spent)
```

## License

MIT
