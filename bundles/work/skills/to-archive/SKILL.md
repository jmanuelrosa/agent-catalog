---
name: to-archive
description: Close a piece of work - moves its whole local work directory to the archive root after the user confirms, so the decisions, rulings and sources stay searchable. Never deletes. Use when the user says a work is finished, wants to close or archive it, or wants to bring an archived one back.
argument-hint: "<work-id> [restore]"
disable-model-invocation: true
---

# To archive

The work directory is the memory of why things were decided, so closing a work moves it, it does not delete it.

First read `../lets-work/references/conventions.md` (sibling of this skill's base directory).

## Archive

1. Resolve the work directory. A work id is required; never archive "the only open one" by inference.
2. Show what is still open: tickets not `done`, specs not `accepted` or `superseded`, review rounds not `fixed`, open questions. Open items do not block the archive, but the user sees them first.
3. Ask for confirmation, naming the source and destination paths.
4. Set `status: accepted` in `work.md` (or `superseded` if the user says the work was abandoned), add a `closed` date and one line on the outcome in the user's words.
5. Move `<root>/<repo>/<work-id>/` to `<root>-archive/<repo>/<work-id>/`. If the destination exists, stop and ask; never merge or overwrite.

## Restore

With `restore`, move the directory back from the archive to the work root, after the same confirmation, and set `status: draft` in `work.md`.

## Rules

- Never delete a work directory, in either root, even when asked to "clean up". Tell the user the path and let them remove it themselves.
- Nothing in the repository is touched: no branch is deleted, no PR is closed.
