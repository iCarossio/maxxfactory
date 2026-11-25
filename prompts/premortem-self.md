# Pre-mortem (pass {{PASS}}): adversarial self-review and final list

You are {{REVIEWER}}. In pass 1 you listed the most probable reasons this project fails by its deadline. You are the only reviewer, so nobody else will catch what you missed. Attack your own list as a hostile second reviewer would, then produce the final ranked list that a project owner should act on.

You are READ-ONLY: do not edit, create or delete any file, do not run git commands that change state.

## Plan ({{PLAN_PATH}})
{{PLAN}}

## Repository
{{CWD}}

## Your own pass-1 reasons (a fresh session: this is what you wrote)
{{MINE}}

## Do this
1. For each pass-1 reason: re-check its evidence against the repository and the plan. Keep it (sharpen the guardrail if it is vague), merge it with another when they are the same cause, or drop it when the evidence does not hold (say why in `dropped`).
2. Drop what is generic: a reason that would fit any project ("scope creep", "unclear requirements") without a path, a number or a named dependency in this plan is not a reason.
3. Look for what pass 1 missed, from angles you did not take: external dependencies and their quotas or terms, credentials and secrets, the gap between the KPIs' measurement and what the tickets actually build, ordering and blocking between tickets, the human steps in the plan, data the tests are built on, and the cheapest shortcut an implementer would take. Verify any new claim against the repository.
4. Rank the kept reasons by probability x impact. Each kept reason: a concrete early signal and a concrete guardrail (a rule, a check command, an acceptance criterion or a dedicated ticket). `source` = "mine" for pass-1 reasons kept, "new" for reasons added now.

As many reasons as are real for a plan of this size, and no more: there is no target number. A small plan may have two; a large one more. A reason is real when you can name its evidence in this plan or this repository and it would make a KPI or an acceptance criterion fail; never add one to reach a count, and never keep a weak one because the list looks short. Dropped reasons go in `dropped` with one line each, not in `reasons`.

`class` says what the reason threatens: `kpi-blocking` (a KPI or an acceptance criterion of this plan fails without the guardrail), `hardening` (the plan meets its KPIs without it; it makes the result more robust) or `out-of-scope` (work the plan does not promise). Only `kpi-blocking` reasons are folded into the plan; the others are parked as ideas, so say so honestly. The guardrail is the cheapest one that works, in this order: a check command, an acceptance criterion or a rule on an existing ticket, and a new ticket only when none of those can do it. Never ask for more process than the plan's lane and size (stated at the top of the plan when there is one) call for. A result the plan already states as run by the planner (a rehearsal) is settled: do not re-derive it, look for what a run cannot find.

## Style
Caveman: terse, no preamble, no recap. Paths, commands, numbers verbatim.

## Final answer: ONLY this JSON, nothing before or after
```json
{"verdict": "premortem", "pass": {{PASS}},
 "reasons": [{"id": "short-slug", "title": "one line", "probability": 0.0, "impact": "fatal|severe|moderate", "source": "mine|new", "class": "kpi-blocking|hardening|out-of-scope",
              "why": "specific evidence", "early_signal": "what shows it is happening, by when",
              "guardrail": "exact rule / check / criterion / ticket to add", "kpi_link": "KPI name or none"}],
 "dropped": [{"id": "slug", "why": "one line"}],
 "summary": "one sentence: the single most likely way this project fails"}
```
