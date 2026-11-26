---
name: to-specs
description: Turn an RFC into small atomic specs - proposes the list of specs for approval, then takes one spec at a time, challenging the user with questions, logging each answer and its reason, and writing that spec only from what they decided. Use when the user wants to write, review, continue or revise the specs of a work, or to challenge one spec.
argument-hint: "<work-id> [S-<nn>]"
disable-model-invocation: true
---

# To specs

Many small specs, each a two-minute read, instead of one long one.
The user is the author; this skill asks, challenges and writes down.

First read `../lets-work/references/conventions.md` (sibling of this skill's base directory).

## Resume

Read `work.md`, `rfc.md` and `research.md` if they exist, `specs/INDEX.md` if it exists, `glossary.md`, and the headings and summaries of `sources.md`.
A spec uses the glossary's terms; a new term settled while grilling a spec is added there.
With a spec id in ARGUMENTS, go straight to that spec.
With no RFC, the spec list comes from `research.md`, the description in `work.md`, and a short interview; nothing is missing.

## Imported specs

A spec with `status: imported` was brought in by `/lets-work`; it gets a challenge pass, not a rewrite.

1. Read its verbatim original in `sources.md` beside the mapped spec, and check the mapping lost nothing.
2. Check it against the RFC, `research.md`, the other specs and `glossary.md`: gaps, contradictions, undefined terms, behaviour that is really two specs.
3. Put what you find to the user in rounds, each with a recommended answer, and log every answer in the spec's own log before the next round.
4. Apply the changes the user accepts and set the status to `draft` or `accepted`, as they say.

## The list first

When `specs/INDEX.md` does not exist or the user wants to reshape it:

1. Propose the list: one line per spec with a title and what it covers. Split by capability or decision area, so that each spec can be read, challenged and changed alone. A spec that needs "and" in its title is two specs.
2. Let the user add, merge, split, reorder and rename. Log the reshaping in `rfc.log.md` when an RFC exists.
3. Write `specs/INDEX.md` (template: `../lets-work/references/templates/specs-index.md`) with every spec as `draft`. Write no spec file yet.

## One spec at a time

For the next `draft` spec, or the one the user names:

1. Re-read only what bears on it: the RFC sections it details, the sources it cites, the specs it depends on.
2. Challenge it in rounds. Ask about the behaviour, the edges, the failure cases, what it leaves to another spec, and anything in the RFC or the sources that contradicts what the user just said. Each question carries a recommended answer.
3. **Append every answer to `S-<nn>-<slug>.log.md` before the next round** (template: `../lets-work/references/templates/log.md`).
4. When no question is left, write `S-<nn>-<slug>.md` (template: `../lets-work/references/templates/spec.md`) from the log alone: scope, behaviour as short statements, one line per decision citing its entry, and open questions for anything undecided.
5. Show it to the user, apply and log their changes, set its status, update its row in `INDEX.md`.
6. Stop and ask before starting the next spec. One spec per sitting is a normal outcome.

## Rules

- Never write a spec the user has not been questioned on, and never fill a gap with a sensible default.
- When a spec outgrows a two-minute read, propose a split instead of adding sections.
- A decision that changes the RFC is logged in `rfc.log.md` and the RFC line is updated; the spec does not silently diverge from it.

## Finish

State which specs were written or changed, which remain `draft`, and point to the next spec or to `/to-tickets <work-id>`.
