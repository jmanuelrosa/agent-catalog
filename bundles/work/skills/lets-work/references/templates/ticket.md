---
work-id: <work-id>
id: T-<nnn>
type: <feature | bug | chore>
status: todo
imported-from: <SRC-nn when brought in by lets-work; omit otherwise>
priority: <high | medium | low>
blocked-by: <T ids, or none>
spec-refs: <S ids, or none>
repos:
  - <repo-name>
branch: <one per repo, filled when work starts>
pr: <one URL per repo, filled when the PR exists>
external-key: <the Jira key or issue URL it was imported from, or where the user exported it>
---

# T-<nnn>: <Title>

## Context

<At most three lines: why this ticket exists and where it sits in the work.>

## Description

<What has to be true when it is done. Detail that belongs to a spec is cited, not copied.>

## Steps to reproduce

<Bugs only; delete this section for other types.>

## Acceptance criteria

Each criterion names how it is verified: a command, a test, or an observable behaviour.
Evidence is written under the criterion when it is checked.

- [ ] AC-1: <criterion>. Verified by: <method>.
- [ ] AC-2: <criterion>. Verified by: <method>.

## Out of scope

- <What this ticket deliberately does not do.>

## Next

<The skill to run next.>
