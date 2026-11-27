---
name: to-tickets
description: Cut specs into local tickets - proposes the ticket list for approval, then writes and reviews one ticket at a time, each with frontmatter, context, description and acceptance criteria that name how they are verified. Also writes a single ticket for a bug or a small change with no spec. Use when the user wants to create, write, review or revise tickets for a work.
argument-hint: "<work-id> [T-<nnn> | S-<nn>]"
disable-model-invocation: true
---

# To tickets

Tickets are local files.
Whether they ever reach a board is the user's own, separate step.

First read `../lets-work/references/conventions.md` (sibling of this skill's base directory).

## Resume

Read `work.md`, `specs/INDEX.md` and the accepted specs in scope, and the frontmatter of the existing tickets.
A work with no specs is normal: interview the user for the tickets they describe instead, logging answers to `ticket.log.md`.

## Imported tickets

A ticket with `status: imported` was brought in by `/lets-work` from Jira or an issue; it gets a challenge pass, not a rewrite.

1. Read its verbatim original in `sources.md` beside the mapped `ticket.md`, and check the mapping lost nothing.
2. Apply the verification bar below to every criterion, and check the ticket against the specs and the RFC above it when they exist: gaps, contradictions, terms not in `glossary.md`.
3. Put what you find to the user in rounds, each with a recommended answer, and log every answer in `ticket.log.md` before the next round.
4. Apply the changes the user accepts, and set the status to `todo`. The external ticket is not touched; telling the tracker is the user's step.

## The list first

1. Propose the tickets: title, type, the spec ids each one implements, priority, and `blocked-by`. Cut so that each ticket ships alone, as one PR per repo, and leaves the system working.
2. Check coverage both ways and show it: every behaviour statement of the specs in scope lands in a ticket, and every ticket traces to a spec or to an explicit user request.
   Every `product-gap` entry of `rfc.log.md` lands in a ticket too, as an open acceptance-criteria question carrying the RFC's recommendation, for the product side to answer.
3. Let the user reshape the list. Create nothing until they approve it.

## One ticket at a time

For each approved ticket, create `tickets/T-<nnn>-<slug>/ticket.md` from `../lets-work/references/templates/ticket.md`.

- **Context** is at most three lines. **Description** says what must be true when done, and cites specs instead of copying them.
- **Steps to reproduce** exists only for `type: bug`.
- **Acceptance criteria** are checkboxes numbered `AC-1`, `AC-2`, each ending with `Verified by:` and a method that can actually be carried out: a command, a named test, or a behaviour observable at a stated place.
- **Out of scope** names the neighbouring work this ticket leaves alone.

Show each ticket to the user before moving to the next.
Log their corrections and any decision made on the way in `ticket.log.md`.

## The verification bar

Reject a criterion, and say why, when:

- it has no method, or the method is "review the code" or "works as expected";
- it restates the description instead of naming a check;
- it cannot fail.

Propose a rewrite that passes the bar; the user decides.
A ticket with a rejected criterion stays out of `todo` until it is fixed.

## Finish

List the tickets written with their status and dependencies, name the one that can start now, and point to `/to-subtasks <work-id> T-<nnn>`.
