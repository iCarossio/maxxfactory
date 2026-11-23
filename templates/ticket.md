# <Ticket title>

<The Linear description rewritten as precise instructions for a cheap implementer: exact inputs (files, formats, counts),
the architecture decision when the ticket shapes the project, what not to touch (files owned by parallel tickets, read-only data,
shared docs), its own port and container name if it starts a server, and the notes of the tickets it builds on (docs/notes/<ISSUE>.md).>

CHECKS: <command && command>
CHECKS_FAST: <optional: what implementers run each round when the project has two-level checks; else state.json checks_fast>
Touches: `<path>`, `<path>` <the files or folders this ticket expects to change: it keeps parallel tickets apart, it is not a fence. The implementer edits any other file the acceptance needs and reports it. What must not change goes in the instructions, by name: "Do not touch: `<path>`">

**Acceptance**
- <criterion verifiable by the CHECKS line or a named test>
- <criterion>

**Look** (tickets that change something a user sees; do not remove)
- References to match: <images under .autopilot/plan/refs/>
- Look criteria on realistic data: <e.g. one line per row <= 52 px, no raw ids or markup, no clipping, empty/loading/error states>
- Full-page screenshots at desktop and phone widths in docs/notes/<ISSUE>/, next to the references. Working but ugly is not done.

**Guardrails from the pre-mortem** (do not remove)
- <guardrail text, with the pre-mortem reason id it comes from>

COMMON RULES
- Never copy expected outputs, fixtures or snapshots into the product; never hard-code test answers; never ship test-only code.
- Fix causes in shared code (generators, engines), not in generated files.
- Do not weaken tests, thresholds or baselines.
- New dependencies: the latest stable release that installs on the project's pinned runtime; never pin an older version without a written reason in docs/notes/<ISSUE>.md.
- Write notes for later tickets in docs/notes/<ISSUE>.md, never in shared docs (parallel tickets).

Coordinator decision: <appended after each review round for every dispute settled, so later reviewers don't raise it again>
