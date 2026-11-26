---
name: work-status
description: Show where a piece of work stands - derives an overview from the frontmatter of its local documents (RFC, specs, tickets, tasks, review rounds) and names the next step for each open thread. Read-only. Use when the user asks where they are, what is open, what is next, or wants to resume work in a fresh session.
argument-hint: "[<work-id>]"
disable-model-invocation: true
---

# Work status

A derived view.
It writes nothing, so it is safe to run at any time and from any session.

First read `../lets-work/references/conventions.md` (sibling of this skill's base directory).

## Steps

1. Resolve the root and the repo name. With a work id, show that work. Without one, list every open work of this repo with its title, status and what it imported, and stop there.
2. Read frontmatter and `Next` sections only; do not load document bodies or logs. Read at the source with a search for the frontmatter keys rather than opening every file.
3. Print, in this order and nothing else:
   - **Work:** id, title, status, path.
   - **RFC:** status, count of open questions.
   - **Specs:** one line each: id, title, status.
   - **Tickets:** one line each: id, title, status, blocked-by, branch, PR, and the latest review round with its status.
   - **Open threads:** every document whose status is not final, with its `Next` line.
   - **Suggested next step:** the single most useful skill to run now, and on what.

## Rules

- Report what the files say. If a status looks stale (a ticket `in-progress` whose tasks are all `done`), say so as an observation; do not fix it.
- A missing level is normal, not an error: a work that started at a ticket has no RFC.
