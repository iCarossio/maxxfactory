# <Project name>

**Owner:** <who decides> · **Deadline:** <date> · **Repo:** <path or URL> · **Default branch:** <main>

## Goal
<One paragraph: what exists at the deadline that does not exist today, for whom, and why now.>

## Expectations and KPIs
Each KPI is measurable at the deadline with the command or number in the "How measured" column. A KPI without a measurement is not accepted.

| # | KPI | Target | How measured (command / query / count) | Owner |
|---|---|---|---|---|
| K1 | <e.g. parity with the old site> | <e.g. 100% of 420 pages pass the visual diff> | `npm run parity -- --all` -> 0 failures | autopilot |
| K2 | <e.g. performance> | <p95 < 200 ms on /api/search> | `k6 run perf/search.js` | autopilot |
| K3 | <e.g. delivery> | <all P1 tickets Done by date> | Linear project view | owner |

## Design bar

Anything a user sees must look polished and modern, on par with the references below, not merely work. A reference the owner names or shows is a success criterion.

| Reference (image under .maxxfactory/plan/refs/) | What to match | Applies to |
|---|---|---|
| <ref-tables.png> | <density, one-line rows, severity pills> | <tables tickets> |

Look criteria checked on realistic data, at desktop and phone widths: <one line per row, no raw ids or markup, no clipping, states>. The owner signs off full-page screenshots side by side with the references before a UI milestone closes.

## Model tiers per phase

Confirmed by the owner at intake (verbatim), from `bin/run-model pool <role>`:

| Phase | Tier | Models and accounts now (capacity, credit left) | Excluded / last resort |
|---|---|---|---|
| Planning, coordination | 1 | | |
| Pre-mortem, plan review, milestone review | 1, another vendor than the planner | | |
| Implementation and fix rounds | 2 (3 only if pinned) | | coordinator account: last resort |
| Ticket code review | 2, never an implementer of the ticket (fallback Tier 1) | | coordinator account: last resort |
| Trivial tasks | 3-4 | | |

Draws inside a tier are weighted by the remaining total usage of each subscription (credit left x plan capacity).

## Non-goals
- <what is explicitly out of scope, so reviewers do not ask for it>

## Constraints
- <stack, conventions, data that must not change, human-only decisions, budget: subscriptions and free tiers only>

## Architecture and key decisions
- <decision, alternative rejected, why>

## Milestones and tickets
<One or more major milestones, in order. Each is a shippable outcome with its own KPIs or acceptance (measurable like
the project KPIs), its own Linear milestone and its own progress bar and ETA (`bin/eta`). Tickets: size S/M/L, what
blocks them (blockers may cross milestones), checks. A ticket is one commit when reasonable (< ~400 changed lines, one
concern). A milestone added later goes through `bin/milestone add`, which appends its section here.>

### M1 <name>
<What exists when this milestone is done, for whom.>

| # | KPI / acceptance | Target | How measured |
|---|---|---|---|
| M1-K1 | <e.g. the thin loop runs end to end> | <1 run green> | `make e2e` -> exit 0 |

| slug | title | size | blocked by | checks | guardrails |
|---|---|---|---|---|---|
| scaffold | ... | M | - | `npm test` | PM-3 |

### M2 <name>
| # | KPI / acceptance | Target | How measured |
|---|---|---|---|
| M2-K1 | ... | ... | ... |

| slug | title | size | blocked by | checks | guardrails |
|---|---|---|---|---|---|
| api | ... | L | scaffold | `npm test` | PM-1 |

## Pre-mortem: most probable failure reasons and their guardrails
<Filled from .maxxfactory/plan/premortem.md after the adversarial review. Every reason kept has a guardrail with a home: a KPI, a check, a ticket, or a rule in this plan.>

| # | Failure reason | P | Impact | Guardrail | Where it lives |
|---|---|---|---|---|---|
| PM-1 | ... | 0.6 | fatal | ... | ticket `scaffold` CHECKS / K1 / rule below |

## Rules for implementers and reviewers
- <project-specific rules derived from the guardrails: forbidden shortcuts, required tests, data sampled from real inputs>

## Human prerequisites
The agents do the maximum themselves, so the owner is asked for access, not for clicks. Not listed: anything an agent can do with the access it already has (`bin/access scan`). Route `access`: a login, an MCP connection or a token with exact scopes, after which the agents do the work. Route `human`: only what no CLI, MCP tool or API can do, with the reason. Asked in one batch before the Linear project exists. Secrets are handed over with `! pbcopyenv <NAME>` (into `.env`, never pasted in the chat); "How verified" is a command that proves the right without printing the value. Status: `provided` (verified on <date>), or `deferred` (the owner's words, the fallback shipped meanwhile, and the tickets held back, which are scheduled last). Nothing stays `missing` at approval.

| # | What the owner provides | Route (why, when `human`) | Needed by (tickets) | How handed over | How verified (command -> expected) | Status |
|---|---|---|---|---|---|---|
| H1 | <e.g. Cloudflare API token, `Zone.DNS:Edit` on example.com> | access | <dns-cutover> | `! pbcopyenv CLOUDFLARE_API_TOKEN` | `bin/check-dns-token` -> lists the zone's records | missing |
| H2 | <e.g. sign-off on the landing page design> | human: a judgement only the owner can make | <landing-polish> | reply in the session | decision `D-<n>` | deferred: "Monday"; fallback: ship behind a flag; holds back `landing-launch` |

## Pre-authorized actions
Every action the run takes outside the repo, or that the harness would otherwise stop to ask about: approved here once by the owner, added to the allowed commands of the machine with `bin/permit` on their consent, then run by the coordinator itself under the stated condition. Never listed: paying for credits or a plan, deleting data, a repository or a production resource.

| # | Action | Command or MCP tool (the rule) | When, and on what condition | Approved |
|---|---|---|---|---|
| A1 | <e.g. publish the site to production> | `Bash(gh workflow run publish.yml *)` | <after the final QA passes on preview> | <owner, date> |
| A2 | <e.g. switch DNS to the new host> | `mcp__cloudflare__execute` | <after A1 is verified on production> | <owner, date> |

## Open human decisions
- <decision, safe default shipped meanwhile, who decides>

## Decision log
Every change of plan after the first draft, with its source: an answer of the user, a pre-mortem reason, a plan or code
review finding, a re-plan signal, a quota limit, a safe default for an open human decision. Written with `bin/decision add`
before the change is acted on, then mirrored in Linear. A change of plan without a row here is a defect.

| # | Date | Change (before -> after) | Why | Source | Decided by | Affects | Linear |
|---|---|---|---|---|---|---|---|

## Approval
- Pre-mortem reviewed by: <models> on <date>
- Plan approved by: <owner> on <date>
