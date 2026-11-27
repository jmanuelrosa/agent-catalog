---
name: to-build
description: Build one ticket from its approved task list - dispatches each task to its staff-engineer seat, one at a time, records each result in the task list, then has an independent checker verify every acceptance criterion and writes the evidence into the ticket. Leaves all changes uncommitted. Use when the user wants to implement, build, continue or resume a ticket whose tasks are approved.
argument-hint: "<work-id> T-<nnn> [T-<nnn>.<n>]"
disable-model-invocation: true
---

# To build

Runs the plan that `/to-subtasks` wrote and the user approved.
It orchestrates; the seats write the code.

First read `../lets-work/references/conventions.md` (sibling of this skill's base directory).

## Preflight

1. Read `ticket.md` and `tasks.md`. If `tasks.md` is missing or not `approved`, stop and point to `/to-subtasks`.
2. For each repo of the ticket, confirm the checkout is on the ticket's branch, or ask the user which branch to use and record it in the ticket frontmatter. Do not create or switch branches without asking.
3. Set the ticket to `in-progress`.
4. Resume from the file: tasks already `done` are skipped, a task left `in-progress` is re-examined against its `Done when` before anything is redone.

## Run the tasks

For each task in order (or only the one named in ARGUMENTS):

1. Mark it `in-progress` in `tasks.md`.
2. Dispatch its seat with a brief that stands alone: the goal in one sentence, the acceptance criteria it covers quoted in full, the files it owns, the `Done when` check, the absolute paths of the ticket and of the specs it cites, and the results of the tasks it depends on. Tell it to leave its changes uncommitted.
3. When it returns, run or confirm the `Done when` check yourself. Write the three-line `Result` (what changed, what was verified, what is left) and set the status **before** starting the next task.
4. A seat that returns a question or a needed decision stops the run. Put the question to the user, log the answer in `ticket.log.md`, then continue.

Tasks run one at a time.
Only tasks marked `Independent: yes` may be dispatched together, and only when their dependencies are done.

## Check the criteria

When every task is `done`:

1. Dispatch the `acceptance-checker` agent with the absolute path of `ticket.md` and of each repo checkout. It did not write the code, so it reads the criteria cold.
2. For each criterion, write the evidence it returned under the criterion in `ticket.md`, and tick the box only for a `met` verdict.
3. A `not-met` criterion becomes a new task for the owning seat, appended to `tasks.md` and run like the others. An `unverifiable` one is reported to the user with what was missing.
4. When every box is ticked, set the ticket to `in-review`. Otherwise it stays `in-progress`.

## Rules

- No commit, no push, no PR. The working tree is left for the user to ship with their own command.
- Never tick a criterion on a seat's word; only on the checker's evidence.
- Never widen a task beyond the files it owns. A seat that needs another file reports it, and the task list is amended with the user's agreement.

## Finish

State the tasks run, the criteria met and not met, the files changed per repo, and what the user does next: ship a draft PR, then `/to-review <work-id> T-<nnn>` once its checks pass.
