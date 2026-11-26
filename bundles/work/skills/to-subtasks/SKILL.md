---
name: to-subtasks
description: Split one ticket into small tasks - reads the ticket and the code it touches, writes a task list where each task has one repo, one owning staff-engineer seat, the files it owns and a check for done, then stops for the user's approval. Writes no code. Use when the user wants to break down, plan or split a ticket before building it.
argument-hint: "<work-id> T-<nnn>"
disable-model-invocation: true
---

# To subtasks

A ticket usually hides several changes, sometimes in several repos.
This skill makes them explicit and gives each one an owner; `/to-build` runs them.

First read `../lets-work/references/conventions.md` (sibling of this skill's base directory).

## Resume

Read `ticket.md`, the specs it cites, and `tasks.md` if it exists.
An `approved` task list is not rewritten; changes to it are proposed and logged in `ticket.log.md`.

## Steps

1. **Read the code first.** Send a read-only search agent into each repo of the ticket to locate the files, patterns and tests the change touches. Save what matters as `SRC` entries in `sources.md` (paths, commit hash, what was learned) before planning.
2. **Inventory the seats.** List the staff-engineer agents actually installed (project and user agent directories). Only an installed seat can own a task.
3. **Cut the tasks.** Each task is one repo, one seat, and small enough to verify alone. Route by what the task changes: tests to qa, migrations and schema to database, pipelines and containers to platform, infrastructure as code to cloud, alerts and SLOs to sre, design tokens and shared components to design, build tooling to dx, and the application slice to frontend or backend, which also cover a slice whose specialist is not installed.
4. **One owner per file.** If two tasks need the same file, merge them or order them with `Depends on`. Mark a task `Independent: yes` only when it shares no file and no contract with any other open task.
5. **Tie every task to the ticket.** Each task names the acceptance criteria it covers, and every criterion is covered by at least one task. A task that covers none is either missing a criterion or out of scope; say which.
6. **Write `tasks.md`** from `../lets-work/references/templates/tasks.md` with `status: draft`, tasks numbered `T-<nnn>.1` onward in execution order, each with a `Done when` the seat can run.
7. **Stop.** Show the list, the criteria coverage and the order. On approval set `status: approved` with the date. Write no code and dispatch no seat.

## Rules

- If the ticket is too vague to split (a criterion with no method, a behaviour the spec leaves open), stop and send the user back to `/to-tickets` or `/to-specs`; do not plan around a gap.
- A design choice the ticket does not settle is a question for the user, logged in `ticket.log.md`, not a decision hidden in a task.
- If the split shows the ticket is really two tickets, say so before writing tasks.

## Finish

State the number of tasks, the seats involved and the repos touched, and point to `/to-build <work-id> T-<nnn>`.
