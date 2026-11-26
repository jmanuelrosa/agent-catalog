---
name: to-review
description: Review your own draft PR, thoroughly and with nit-picks - once CI is green, runs the code-reviewer agent over the PR diff across every review axis with a blind reader that sees only the diff, checks each acceptance criterion of the ticket, and saves the verified findings as a new numbered review round in the work directory. Posts nothing. Use when the user wants to review, re-review or self-review the PR of a ticket they built.
argument-hint: "<work-id> T-<nnn>"
disable-model-invocation: true
---

# To review

The author's own review, before anyone else looks.
Everything it finds stays local, as a round the user then rules on with `/to-triage`.

First read `../lets-work/references/conventions.md` (sibling of this skill's base directory).

This skill only reads the repository and the PR.
It edits no code, stages nothing, and posts no comment.

## Preflight

1. **Our tickets only.** Without a work id and a ticket, stop: point to `/lets-work` and `/to-tickets`. Someone else's PR is not reviewed here; point to the review command instead.
2. Read `ticket.md` for the PR of each repo. If the `pr` field is empty, find the open PR of the ticket's branch and record it. In a repo where the user works without PRs, review the ticket branch against the default branch and record `pr: none`; otherwise, with no PR yet, stop and tell the user to ship a draft first.
3. **CI gate.** Read the check status of the PR or the branch. If any check is pending or failing, stop and name the checks; a review of code that does not pass is a review of the wrong diff. If the repo has no checks configured, go on and record `no checks configured` in the round.
4. If the previous round is not `fixed`, stop and point to `/to-triage`; a new round starts only after the last one is closed.
5. Create `reviews/R<n>/`, where `n` is one more than the highest existing round, whatever its kind. Write `round.md` from `../lets-work/references/templates/round.md` with `kind: self`, the PR URL and the head commit.

## Review

1. Pin the diff: the PR's base (or the default branch) to its head commit, saved to a file in the session's temporary directory.
2. Dispatch the `code-reviewer` agent with: the path of the pinned diff, the ticket as the spec it implements, the acceptance criteria quoted in full, the round number, and for a second or later round the previous rounds' items with their rulings and outcomes.
3. State two things in that dispatch, by name:
   - **Author self-review, nit cap lifted.** Every verified nit is reported, sorted after blockers and importants. The cap of the review policy exists for reviews handed to someone else; here the author asked for all of them.
   - **The blind sample gets only the diff and the PR description.** No ticket, no spec, no history. Its job is to find what a reader without the context cannot follow.
4. In parallel, dispatch the `acceptance-checker` agent with the ticket and each repo checkout, and take its verdict per criterion.

## Write the round

1. Fill the `Acceptance` table from the checker.
2. Write each finding the reviewer verified as an item `R<n>-F01` onward: severity (the four words of the review policy), `file:line`, the dimension it came from, the claim with its concrete failure scenario, and a recommended ruling with one line of reasoning.
3. Order by severity: blockers, importants, nits, pre-existing. A `not-met` criterion is a blocker item.
4. Leave `Ruling`, `Why`, `Ruled on` and `Outcome` empty; they belong to triage.
5. An item an earlier round already ruled `reject` is not raised again unless the code changed under it; if it is, cite the earlier item.

## Finish

Print the counts per severity, the acceptance summary, and the path of the round.
Do not print the findings in full; the round file is where they are read.
Point to `/to-triage <work-id> T-<nnn>`.
