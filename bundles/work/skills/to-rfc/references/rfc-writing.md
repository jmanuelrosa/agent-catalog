# Writing the RFC

Read at write time and again before every revision is shown.
These rules come from a real RFC's review: 31 comment threads from engineering and product leads, a technical refinement, and a ruling from the CTO.

## What an RFC is

- It gives a rough idea of what we build and what still needs a solution. Everything else is a to-do or context, and goes elsewhere.
- It validates the technical solution and is never the product's source of truth. A product gap (behaviour, copy, a limit or threshold the tickets leave open) goes back to the ticket's acceptance criteria; the RFC keeps only the technical value any answer needs (a date, a state).
- It architects what is new: components, data, contracts and the flows between systems. Screens, states and copy belong in the design file, linked.
- Around 2,000 words. Detail belongs in `research.md` and the specs; summarise it here in a line or two. A section that grows past a page is probably context.

## Rules

- Include only what changes or needs agreement. A section that restates behaviour we keep, or an alert that already exists, has nothing to decide: drop it.
- State a verdict when one option clearly wins, and let reviewers push back. Ask a question only when the options are really open.
- Write what we propose, not who said it or which meeting decided it. Provenance goes in the decision log only.
- Separate what the tickets require from what we propose. A number, threshold, rule or rejection the tickets do not contain is worded as our proposal ("we propose a one-hour cache"). Anything whose source has origin `inference` reads as a proposal. Never write "was rejected" for an option nobody discussed.
- Every claim survives "where is this coming from?": its `SRC` id is in `rfc.log.md` or `research.md`, ready to quote in a reply.
- No hypothetical risks from reading code alone. A risk goes in with data, or with the measurement that would size it. What the code supports is not how production runs.
- Define every status or term introduced where it first appears, by the value the system stores (`PENDING`, `LIVE`); quote the design's name for a state when one exists, never invent UI names such as colours. Independent states (is it deployed, does it receive events) stay separate values.
- Each bullet reads on its own: give the consequence, not only the mechanism.
- Name out-of-scope work once, in Non-goals, and keep it out of the verdicts.
- Leave out task breakdowns, `file:line` references, deployment checklists, full schemas and raw measurements. A short snippet is fine when it is a contract reviewers must agree on.
- No people's names; roles instead ("the product side", "support").
- One sentence per line, plain words, first-person plural ("we propose").
- Link every ticket key to its tracker and every PR to its host.

## Before showing the draft

Go through every item; fix the draft rather than explain an exception.

- [ ] Title is `[Team] Subject (EPIC-KEY)`, prefixed `[WIP]` while a draft.
- [ ] Section 1 states the count of questions in section 8, or asks for sign-off.
- [ ] Section 3 architects components, data, contracts and flows; no subsection only describes what the UI does, and no colour, copy, chip, tooltip or modal behaviour appears.
- [ ] No product decision in the RFC; each product gap is logged for its ticket.
- [ ] Every `3.x` opens with `**Verdict:**` and holds only the chosen solution; weighed options sit in section 6 under that subsection's name, each saying how it would work and why we don't do it.
- [ ] Every section and bullet changes something or needs agreement.
- [ ] Section 8 holds only what is really open, each with an owner and our recommendation.
- [ ] No mention of "the meeting" or of who said what in the body.
- [ ] Every number, threshold, rule and status in section 3 traces to a source; inferences read as proposals.
- [ ] Each drawback is a cost of the chosen design, not a constraint to keep in mind.
- [ ] Every status or term introduced is defined by its stored value.
- [ ] Every query on a large table names its scope and its cache.
- [ ] Superseded designs are deleted, not moved to section 6.
- [ ] Around 2,000 words.
- [ ] A small diagram opens section 3 when the flow spans systems.

## Write this instead

These drew reviewer comments on a real RFC.

| Drew a comment | Write instead |
|---|---|
| "The meeting chose this check 'for now'." | "We revisit this check if it does not work in practice." and a decision log row |
| "The dot warns after 3 days", when the ticket leaves N open | "The API returns the date of the last event"; the threshold goes to the ticket's acceptance criteria |
| "A saved path is yellow, then green", names the design never used | "`path_status` is `PENDING` (the design's "Deploying path"), then `LIVE` ("Path can be forwarded")" |
| One status merging "path deployed" and "receiving events" | Two values the API returns side by side |
| A per-host daily view over 7 days of a table with hundreds of millions of rows | The latest event per host, cached for one hour like the existing monitoring |
| "Hosts found in traffic become domains" | "They are stored inert until the customer promotes them", since request headers are untrusted |
| The table a meeting dropped, moved to section 6 | Delete it; the decision log records the change |
| "Assigning the project on open was rejected", when nobody discussed it | "We propose a read-only preview instead, because ..." |
| A visitor-reset risk derived from reading the parser, with no data | Leave it out, or state the measurement that would size it |
| "Includes projects that do not run on Spacelift", because the code supports other providers | Confirm with the infrastructure owner first |
| A section on certificate validation we keep as it is | Delete the section |
| A 3.x subsection walking through what each screen shows | The component, data and contract behind it; link the design for the screens |
| A table of rejected signals inside 3.2 | The chosen signal in 3.2; the others in section 6 under "Path liveness" |
