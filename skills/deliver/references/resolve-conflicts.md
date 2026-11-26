# Resolving conflicts with the base

How a merge of the PR's base into its branch gets resolved: by `/deliver` before it pushes, and by the tracker's headless run once a PR conflicts.
The merge is already started (`git merge --no-commit --no-ff <base>`), so in git's terms `ours` is the branch and `theirs` is the base.
Never commit or push it: the caller does that once every file is resolved.

1. **List the conflicts**: `git diff --name-only --diff-filter=U`.
2. **Read both intents before choosing.** `git log --oneline HEAD..MERGE_HEAD -- <file>` says what the base changed and why.
   - Resolve every hunk keeping both intents: a rename on one side and an edit on the other ends as the edited code under the new name.
   - When a stacked parent was squash-merged, its own changes already sit in the base, so prefer the base side for them.
   - A lockfile: take the base side (`git checkout --theirs -- <file>`), then regenerate it with the package manager it belongs to, lockfile-only where it can (`npm install --package-lock-only`, `pnpm install --lockfile-only`, `uv lock`). When the regeneration cannot run (sandbox, network, missing tool), the lockfile is an escalation.
   - A generated file: rerun its generator rather than hand-merging it, when the repo has one.
3. **Leave no markers**: `rg -n '^(<{7}|>{7}|\|{7})( |$)' <files>` comes back empty.
4. **Stage**: `git add` each resolved file. When the touched area has a quick check (a typecheck, the tests next to the files), run it, and treat a failure the merge caused as unresolved.

A conflict you cannot resolve with confidence (both sides rewrote the same logic differently, or the answer is a product decision) is an escalation: `git merge --abort`, then name each file with one sentence on why.
