---
name: to-rfc
description: Write or revise an RFC for a piece of work - interviews the user from the research, files every open point as an author verdict, a product gap for the tickets, or a question for reviewers, saves each answer and its reason before the next round, then writes the RFC from the team template and its writing rules. Revise mode saves reviewer comments as a numbered round, rules on them one by one and drafts sourced replies. Local file only. Use when the user wants to write, draft, continue or revise an RFC, or answer comments on one.
argument-hint: "<work-id> [revise]"
model: opus
disable-model-invocation: true
---

# To RFC

The RFC is written from the user's decisions, not from the model's ideas.
The interview is the work; the document is its receipt.
Keep three things apart throughout: facts with sources, decisions the author makes, and questions that belong to reviewers.

First read `../lets-work/references/conventions.md` (sibling of this skill's base directory).
Load the `grilling` and `domain-modeling` skills for the interview.

## Resume

Read `work.md`, `research.md`, the headings and summaries of `sources.md`, `glossary.md`, and, if they exist, `rfc.md`, `rfc.log.md` and the latest `rfc-reviews/` round.
Never re-ask a question the log already answers.
With `revise`, or when reviewers have commented, go to **Revise**.

## Imported RFC

An `rfc.md` with `status: imported` was brought in by `/lets-work`; it gets a challenge pass instead of the interview.

1. Read its verbatim original in `sources.md` and check the mapping lost nothing.
2. Run the checklist of `references/rfc-writing.md` over it, and the three-way sort below over every point it leaves open.
3. Check its claims against `research.md` and `sources.md`; a claim with no source is a question for the user, not a fact.
4. Put what you find to the user in rounds, each with a recommended answer, logging every answer in `rfc.log.md` before the next round.
5. Apply the accepted changes, then set the status to `draft` or `in-review`. If reviewers already commented on the original, continue with **Revise**.

## Coverage first

Before the first question, check the coverage table of `research.md`.
If it is missing or a section has a gap, say which, and recommend `/to-research <work-id>` for those gaps.
The user may go on anyway; a gap then becomes a question in the interview.

## Interview

Use grilling's design tree: settle prerequisite decisions before dependent ones, ask the whole frontier in one numbered round, each question with its evidence, the concrete options and a recommended answer first.
Look facts up yourself, saving them to `sources.md` and `research.md`; put only decisions to the user.

**Write before the next round.**
Append one `D` entry per answer to `rfc.log.md` (template: `../lets-work/references/templates/log.md`) before doing anything else, with the user's words, their reason, and its outcome.

Every point ends in exactly one outcome:

| Outcome | Who settles it | Where it goes |
|---|---|---|
| **verdict**: the author can decide and one option clearly wins | the user, now | a `3.x` subsection opening with **Verdict:**; the weighed options go to section 6 |
| **product-gap**: behaviour, copy, a limit or threshold the tickets leave open | the product side, on the ticket | not the RFC: the log entry names the ticket and our recommendation, and `/to-tickets` raises it as an acceptance-criteria question; section 3 keeps only the technical value any answer needs |
| **reviewer-question**: architecture, data, infrastructure or rollout where the options are really open | engineering reviewers | section 8 as `Q<n>`, with owner, context, options and our recommendation |

Behaviour that exists today and does not change has nothing to decide and goes nowhere.
A point the user skips without naming an owner is not settled; it stays on the frontier.
A value the tickets leave open (a threshold, a count, a time window) is a product gap even when we have a good recommendation: make the system return what any answer needs (the date of the last event, not the number of days).

Challenge every verdict before it lands, and collect what you find for sections 5 and 6:

- failure cases, rollback, and compatibility with what runs today;
- a new table against extending the existing one: a data migration is riskier than a filter in code, so a new table needs a reason reviewers can weigh, and an extended one lists the readers that must filter;
- every query on a large table: the narrowest query (the latest event per key, cached like the existing monitoring) beats a rolling scan or a view;
- the data existing customers have on the day of the rollout: missing history, what gets backfilled, statuses computed from data that does not exist yet;
- input anyone can send (request headers) stays inert until a user acts on it.

Use domain-modeling throughout: challenge terms against `glossary.md`, sharpen fuzzy language, and write settled terms into it as they land.
Offer an ADR only when domain-modeling's three conditions hold and the verdict is the author's; draft it in `adr/` in the project's ADR format, noting that reviewers can still overturn it until the RFC is accepted.

If an answer changes a load-bearing premise, go back to research for that premise before asking anything downstream of it.
The interview ends when the frontier is empty, or every remaining item is a section 8 question with an owner and a recommendation, and the user confirms shared understanding.

## Write

1. Read `references/rfc-writing.md` (in this skill's base directory).
2. Fill `rfc.md` from `../lets-work/references/templates/rfc.md`, or the team's own template when the repository has one. Write from the log, `research.md` and `sources.md` only. Delete every guidance line.
3. Aim for around 2,000 words. Detail that is not a decision stays in `research.md` or goes to the specs.
4. Run the checklist of `rfc-writing.md` and fix the draft until every item holds.
5. Run the `unslop` skill over the prose.
6. Show the path, the word count, the verdicts, the section 8 questions with their owners, and the product gaps with the tickets they belong to.

Walk the user through the verdicts and section 8 if they want it; log each change they ask for.

## Revise

For reviewer comments (page comments, threads, a refinement meeting, an AI summary of one):

1. **Open a round.** Create `rfc-reviews/R<n>/round.md` (template: `../lets-work/references/templates/round.md`, `kind: external`). Save every comment **verbatim** as an item, including page-level ones and threads whose anchor text an earlier revision deleted. For meeting notes or a summary, list each decision with its quote and confirm the ambiguous ones with the user before saving them.
2. **Sort each item** in its `Recommended` line: agree and change; reword because it was unclear; source request; pushback that needs the user's decision; acknowledgement only.
3. **One at a time.** Show each item with its recommendation, take the user's ruling and reason, and write them into the round before showing the next. Pushback is never answered without the user.
4. **Draft replies** in the item's `Outcome`, in the author's voice: first person, short, humble, saying what changed and in which section. Answer source requests from `sources.md`: quote the ticket, give the code reference, or the meeting timestamp. When the claim was an inference, say so and own it.
5. **Revise the RFC.** A reversed verdict is rewritten and what it replaced is deleted (never moved to section 6). Answered section 8 items get `Answered (date):` or move to section 3. Log each change in `rfc.log.md` and replace the matching decision-log row. Re-run the checklist and `unslop`.
6. Set the round to `fixed`.

Tell the user, when they publish: collect the comments again right before updating the page, since threads added meanwhile land on blocks the revision rewrites, and post every reply before updating, because rewriting a block detaches its comments.

## Boundaries

- Writes only in the work directory: `rfc.md`, `rfc.log.md`, `rfc-reviews/`, `glossary.md`, `adr/`, and new entries in `sources.md` and `research.md`.
- Publishes nothing and posts no reply. Sharing the RFC is the user's own step.
- No task breakdown and no implementation; the follow-up is `/to-specs <work-id>`.
