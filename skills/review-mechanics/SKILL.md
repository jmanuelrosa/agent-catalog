---
name: review-mechanics
description: Machinery for producing a code review report, covering the verification bar, effort levels, seat routing, skip rules and report format. Invoke before writing any review, from /code-review or by hand.
---

# Producing a review

The severities, the eight axes and the reviewer's boundaries live in `~/.claude/rules/code-review.md` and are already loaded.
This skill is the machinery for turning a read diff into a report.

## The verification bar

Every finding carries three things, or it is not reported:

1. A `file:line` in the **source**, read and confirmed. Not inferred from a name, a path, or a convention.
2. A concrete failure scenario: the inputs or state, then the wrong output, crash, or cost. "This could be a problem" is not one.
3. The mechanism, in one clause. What is actually wrong, not that something feels wrong.

A finding that cannot state a failure scenario is an opinion.
Drop it rather than dressing it as a risk.
When you are unsure whether a path is reachable, say so in the finding and lower the severity rather than hedging the wording.

Never claim a behaviour you have not read.
If the diff changes a function, open its callers before asserting anything about the effect.

Before a candidate becomes a finding, read the strongest counterevidence: the guard upstream of the path, the test that already covers it, the caller that never passes the input.
A candidate the counterevidence disproves is dropped, not downgraded.
Once a defect is confirmed, search the sibling paths for the same pattern, since the second occurrence is usually in the file the diff did not touch.

Severity follows the traced impact and nothing else.
Absent tests, many callers, a scary API name, or several reviewers agreeing never raise it.
A missing test is a test-adequacy finding that names the unprotected contract, not evidence that the contract is broken.
Expected behaviour comes from the spec and the callers, never from the implementation under review, and an existing test is supporting evidence rather than intent.

A deleted guard, check, catch, or validation is a finding unless the diff or the spec names what replaces it.
Protections are usually there because something failed once, and the reviewer cannot run `git blame` to find out what.

## Failure scenarios

Correctness and contract findings come from scenarios, not from reading the diff and waiting for a bug to look wrong.
For each changed input, trace it through callers, transformation, storage and the externally visible effect, and construct the concrete scenario from the rows that apply.
Do not demand the cartesian product; pick the rows the change can actually reach, and say expected versus actual for each.

| Dimension | Scenarios |
|---|---|
| Values | Missing vs null vs false vs zero; empty, single, many; min, max, off-by-one; malformed or oversized input; precision and overflow; encoding and Unicode normalisation |
| State and ownership | New, existing, deleted, soft-deleted, stale, partially migrated records; invalid transitions; changed role or tenant; missing parent; duplicate identifier |
| Time and order | Time zones and DST; expiry boundary; clock assumptions; out-of-order events; pagination with tied sort keys; cache invalidation |
| Concurrency | Two writers; lost update; check-then-act race; lock ordering; cancellation; double submit; duplicate delivery and the scope of idempotency |
| Partial failure | Database commits and the queue fails; remote succeeds and local times out; retry after a side effect; cleanup that itself fails; exhausted retries; dependency unavailable |
| Compatibility | Old and new clients or workers side by side; historical payloads; default vs explicit config; flag off, on and mixed; rolling deploy and rollback |
| Event-driven | First vs repeated action on the same record; same vs different identity; pending vs settled work; a consumer that keys on identity and so misses the repeat |
| UI | Loading, empty, error and disabled states; a stale async response landing late; keyboard, focus and screen-reader paths; localisation; slow or offline network; a capability that disappears at a breakpoint with no alternative |

State the invariants: what must hold before, during and after the operation.
A scenario that breaks one is the finding; a row with no reachable scenario is covered and needs no line in the report.

## Effort

Effort changes the bar, not the axes: at `low` and `medium` report only what you are most confident in, and from `high` up cast a wider net and let the verification bar do the filtering.

`/code-review` takes the level as its first argument, and this table is the authority on which one.
Every other artifact that tells you to run a review names a level consistent with it.

| Situation | Effort |
|---|---|
| A hook, a config tweak, or a one-file fix you already understand | `low` |
| An ordinary single-concern diff before `/commit` | `medium` |
| One seat's completed slice, or any diff against a stack you do not know | `high` |
| A multi-seat or multi-worktree integration, or a release | `max` |
| A deep pass you do not want to spend local tokens on | `ultra` |

`xhigh` sits between `high` and `max` and needs a reason to pick over either.
`ultra` is not a step up from `max`: it runs in the cloud, is billed separately from the session, and needs claude.ai account access, so it is a deliberate choice rather than the top of the ladder.

## Seat routing

A seat's `<discipline>-failure-modes` skill is the deep checklist for its axes, and its own trigger table picks which references to open.
Invoke the skill rather than naming reference files, so retitling a reference upstream does not strand this guidance.

| Axis | Seats |
|---|---|
| Contract and compatibility | `database-failure-modes`, `backend-failure-modes`, `platform-failure-modes` |
| Security and privacy | `security-failure-modes`, plus `frontend`, `mobile` and `desktop` for their own security references |
| Failure visibility and operability | any installed seat's `failure-visibility` reference, and `sre-failure-modes` for alerting and tracing |
| Test adequacy | `qa-failure-modes` |

Seats are bundles, so they load only when `kura add <discipline> --type bundle` ran in this project, the workspace is trusted, and the harness has been restarted from the repo root.
Check, then route.
If the seat is absent, review the axis from the policy and say in the summary that the deep checklist was unavailable.
Never assume a seat is present because the axis needs it.

## Skip rules

Report nothing in: generated or vendored trees, lockfiles, snapshots and fixtures asserting only shape, and vendored upstream skill trees (`skills/<upstream>` in agent-catalog), since `kura update` replaces those wholesale and a finding there is discarded on the next sync.

Do not spend the output cap on what a hook already blocks:

- Em and en dashes. `em-dash-gate.sh` refuses them at Write time.
- Lint and typecheck failures. `pre-commit-verify.sh` runs both before any commit.
- Attribution lines and `--no-verify`. `git-skill-gate.sh` hard-blocks them.

A finding that duplicates a hook teaches the reader that the report is padding.

## Nit discipline

At most three nits per review, and zero when a blocker is present.
Pick the three with the highest ratio of clarity gained to churn caused.
Everything else is dropped, not deferred to a list, because an appendix of nits is the same cost as reporting them.

## What is out of scope, because it writes

The reviewer does not mutate, so none of these run during a review:

`/code-review --fix`, `code-simplification`, `/simplify`, `knip --fix`, `coderabbit`, `pr`, `performance-optimization` steps 3 onward, `setup-review`'s apply step.

`--fix` is named first because it is the one the harness itself ships, so a ban that skipped it would read as forbidding only other people's tools.
`cc-staff-reviewer` and `pi-staff-reviewer` review harness setup and never application code, so no code finding routes there.

`code-review-and-quality` is superseded as a reviewer, not as a skill.
Its five axes are a subset of the policy's eight (it covers none of contract and rollback, failure visibility, or test adequacy) and its five-word scale is one of the dialects the policy exists to collapse.
What it is still good for is review technique the policy does not cover: change sizing, describing a change, handling disagreement, dependency discipline.

## Reporting

Lead with the verdict in one line: ship, ship after fixes, or do not ship, and the count per severity.
Then findings in the axis order the policy gives, blockers first within each axis.
Group by file only when a file carries three or more findings.

Each `blocker` and `important` finding is written so the reader knows what breaks, when, why, and what to change without reconstructing the path:

```text
- blocker `path:line` - Title naming the broken behaviour.
  Problem: the trigger, the cause and the effect, in plain words.
  Evidence: the code trace or test read, and the counterevidence that did not hold. Say when the evidence is static.
  Fix: the smallest sound change.
  Check: the test or command that would catch this and currently does not.
```

The `Check` line is what a later pass verifies the fix against, so it names an assertion, not a wish.
Nits and pre-existing findings keep the one-line form.

Close with a coverage ledger, one line per axis of the policy: `checked`, `not applicable` with the reason, or `unchecked` with the reason and what would check it.
A seat bundle that was absent, a caller that could not be read, or a path outside the diff that was not opened all land here as `unchecked`.
The ledger is what makes a clean review different from a review that did not happen: a review that says "looks good" with no ledger is the latter.
