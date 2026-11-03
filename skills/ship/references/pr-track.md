# PR track

One script, `scripts/track.py`, does every mechanical part with plain `gh`/`glab` and `git` calls: it polls, compares with the last snapshot, records only real changes, and after a model run it commits, pushes and replies.
A model runs only when an event is something it can act on, after a burst has settled, inside a scratch worktree.
It ships inside the `ship` skill, which `pr` depends on: global install `~/.claude/skills/ship/scripts/track.py`, project install `.claude/skills/ship/scripts/track.py`.
The user's shell has `prt` as a shortcut for the same script.

## Commands

| Command | Does |
|---|---|
| `track.py add <url> --agent <claude\|pi\|codex>` | Start tracking, merging included. Run it from the PR's repo. `--agent` names the harness you are running in, which is the one that reacts later |
| `track.py merge <ref> [--off]` | `--off` keeps tracking a PR without merging it; without it, merging is back on and it prints what the merge is still waiting for |
| `track.py ls` | Tracked PRs with state, CI, reply drafts, and every "needs you" item |
| `track.py ack <ref>` | Clear a PR's "needs you" items once the user has dealt with them |
| `track.py drafts <ref>` | The replies drafted for teammates, with the comment each answers |
| `track.py rm <ref>` | Stop tracking. Refuses while kept work is waiting, unless `--force` |
| `track.py take <ref>` | Apply work a failed push left behind to the worktree where the branch is checked out |
| `track.py watch [<ref>...]` | Print events as they happen, for an in-session Monitor |

`<ref>` is the URL, the key `ls` prints, or the bare number when it is unique.
Merged and closed PRs notify once, then drop out.

## How it runs

The background path is a launchd job from the dotfiles `ai` role running `track.py poll --notify --dispatch` every few minutes.
Each pass costs one GraphQL request per GitHub repo, or two REST calls per GitLab MR, and no tokens.

| Event | Result |
|---|---|
| Bot inline comment or review, teammate comment, CI failure, conflict, base changed, stacked parent merged | Once no new event arrived for `PR_TRACK_SETTLE` seconds, the tracked agent runs headless in a scratch worktree. The script then commits, pushes the PR's branch, replies to bots and resolves their threads, and files teammate replies as drafts |
| Changes requested | The same run, plus a notification |
| Merged or closed | A notification, then untracked |
| Approval, bot summary comments (walkthroughs, previews, coverage) | Nothing |

The user hears about a PR (a macOS notification, plus a "needs you" line in `ls`) only when:

- the agent flags a judgment call: an ambiguous or disputed teammate comment, a design question, or a request outside the PR's scope
- it is stuck: CI still failing after `PR_TRACK_MAX_CI_ATTEMPTS` fixes, the daily run cap (`PR_TRACK_MAX_RUNS`) reached, a run that wrote no result, or a commit or push that failed
- a reviewer requested changes
- a merge failed (once per commit)

### Merging

A tracked PR is merged by the script, never by a model, once every one of these holds:

- it is open and not a draft
- the host says it can merge: GitHub's `mergeStateStatus` is `CLEAN` (required checks and reviews satisfied, up to date when the branch rules demand it), or GitLab's `detailed_merge_status` is `mergeable`
- CI passed, and no review thread is unresolved
- its base is the default branch, so a stacked child waits until its parent merges and the host retargets it
- no event is pending, no run is in progress, no work is kept, and nothing is waiting on the user
- nothing changed for `PR_TRACK_SETTLE` seconds, so a fresh push gets its checks registered first

GitHub merges with `--match-head-commit`, so a push that lands in between makes the merge fail instead of merging unreviewed code.
The method is squash when the repo allows it, otherwise whichever of merge or rebase it allows. GitLab squashes unless the project forbids squashing, and otherwise follows the project's merge method.
The branch is never deleted by the script; the repo's own auto-delete setting decides.
Merging follows the repo's rules, so a repo that requires no review merges on green CI and resolved threads.

Pushes are plain fast-forward pushes of the PR's own head branch: never forced, never to the base or default branch.
A rejected push (the user pushed meanwhile) keeps the work for `take` and says so.
Replies the script posts end with `Posted by <agent> on behalf of @<login>`.
Teammates are never replied to and their threads never resolved, whatever the result file says: the script turns those into drafts.

### In-session watch (Claude Code)

When the user is actively working on a PR and wants this session to react instead, arm a Monitor on `python3 ~/.claude/skills/ship/scripts/track.py watch <ref>` with `timeout_ms: 1800000`.
The background job skips a PR while a watcher holds it.
Handle each `event|<key>|<json>` line in the user's worktree with the judgment rules in React, then ship through `/ship` as usual.
Re-arm on expiry; stop on `all-closed`. Pi has no Monitor, so in Pi the background job is the only path.

## React

This is what a headless run follows. Your working directory is a detached worktree at the PR's head; the prompt names the PR, the base and the result path.

1. **Read the batch**: `python3 <script> events <key>`. It prints the PR, `head=` and `base=`, then each event with its `ref` and body.
2. **Handle each event**:
   - **Bot comment**: judge the claim against the code, not the bot's confidence. Valid: fix it. Not valid or out of scope: leave the code. Either way write a reply, one to three sentences naming the change or the reason.
   - **Teammate comment**: fix it when the ask is clear and inside the PR's scope, and draft a reply. When it is ambiguous, disputes the approach, asks a design question or reaches outside the PR, change nothing for it and escalate it in one sentence.
   - **CI failure**: `gh pr view <url> --json statusCheckRollup` names the failing check. Fix a cause in the code; a flaky or infrastructure failure is an escalation, not a code change.
   - **Conflict, base changed, or parent merged**: `git merge --no-commit --no-ff origin/<base>`, with the base from the `branches` line. Resolve every hunk keeping both intents; when a stacked parent was squash-merged, its own changes already sit in the base, so prefer the base side for them. `git add` the resolved files and leave the merge uncommitted. A conflict you cannot resolve with confidence is an escalation: `git merge --abort` and say which files.
   - **Changes requested**: treat the review's comments as teammate comments.
3. **Write the result** to the path in the prompt, as JSON:

   ```json
   {"commit": "fix(api): handle an empty cart",
    "replies": [{"ref": "inline:123", "body": "Fixed: the cart check now runs first.", "resolve": true}],
    "drafts": [{"ref": "inline:456", "body": "Renamed it to fetchCart."}],
    "escalate": ["alice asks to split the module; that is a design call"]}
   ```

   `commit` is one conventional-commit header (`<type>(<scope>): <subject>`, lower-case, no period, no dashes other than `-`) for your file changes; leave it out when you changed nothing. `ref` comes from the events. Put a reply to a teammate in `drafts`, never in `replies`. Every key is optional; `{}` means there was nothing to do.

Never `git commit`, `git push`, post, reply, resolve or edit the PR yourself, and never touch files outside the working directory except the result file.
