#!/usr/bin/env python3
"""track.py - push-and-forget tracking of open PRs/MRs for the ship and pr skills.

Polls GitHub and GitLab with plain gh/glab calls, compares each PR with the
last snapshot it saw, and turns only real changes into events. A model is
started only for events it can act on, once a burst has settled, inside a
scratch worktree. The model edits files and writes a result file; this script,
not the model, commits, pushes the PR's own branch, replies to bots, and
interrupts the user only for judgment calls, stuck runs and requested changes.

Subcommands:
  add <url> [--agent A] [--worktree P]   start tracking and merge once ready
  merge <ref> [--off]                    merge once ready, or stop doing so
  rm <ref> [--force]                     stop tracking
  ls [--json]                            list tracked PRs
  ack <ref>                              clear a PR's "needs you" items
  drafts <ref>                           reply drafts for teammates
  poll [--notify] [--dispatch]           one pass; launchd runs this (--dispatch acts:
                                         runs agents, pushes, merges)
  watch [<ref>...] [--interval N]        print events for an in-session Monitor
  events <ref>                           the batch a reacting agent works on
  take <ref>                             apply work a failed push left behind
"""

import argparse
import contextlib
import fcntl
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dotkit import ui

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_NOT_FOUND = 2
EXIT_FETCH_FAILED = 3
EXIT_TAKE_REFUSED = 4

SETTLE_SECONDS = int(os.environ.get("PR_TRACK_SETTLE", "180"))
MAX_RUNS_PER_DAY = int(os.environ.get("PR_TRACK_MAX_RUNS", "6"))
MAX_PARALLEL_RUNS = int(os.environ.get("PR_TRACK_MAX_PARALLEL", "2"))
MAX_CI_ATTEMPTS = int(os.environ.get("PR_TRACK_MAX_CI_ATTEMPTS", "2"))
RUN_TIMEOUT_SECONDS = int(os.environ.get("PR_TRACK_RUN_TIMEOUT", "1800"))
WATCH_INTERVAL = int(os.environ.get("PR_TRACK_WATCH_INTERVAL", "60"))
BODY_CAP = int(os.environ.get("PR_TRACK_BODY_CAP", "2000"))
DAY_SECONDS = 24 * 60 * 60
ATTENTION_KEEP = 10
MERGE_ORDER = ("squash", "merge", "rebase")

AGENTS = ("claude", "pi", "codex")
AGENT_NAMES = {"claude": "Claude Code", "pi": "pi", "codex": "Codex"}
ACTIONABLE = {"conflict", "ci-failed", "parent-merged", "base-changed", "changes-requested"}
FAILED_CI = {"FAILURE", "ERROR"}
FINAL_STATES = {"MERGED", "CLOSED"}
FINAL_KINDS = {"merged": "merged", "closed": "closed without merging"}

GITHUB_RE = re.compile(r"^https://(?P<hostname>[^/]+)/(?P<repo>[^/]+/[^/]+)/pull/(?P<number>\d+)")
GITLAB_RE = re.compile(r"^https://(?P<hostname>[^/]+)/(?P<repo>.+?)/-/merge_requests/(?P<number>\d+)")
GITLAB_BOT_RE = re.compile(r"(^project_\d+_bot|^group_\d+_bot|bot$|^coderabbitai$)")
COMMIT_HEADER_RE = re.compile(
    r"^(feat|fix|chore|docs|refactor|test|perf|ci|build|style|revert)(\([a-z0-9./_-]+\))?: [a-z0-9`].{0,90}[^.]$")
FORBIDDEN_IN_MESSAGES = (chr(0x2014), chr(0x2013), "Co-Authored-By", "Generated with")

CLAUDE_TOOLS = (
    "Read,Edit,Write,Glob,Grep,"
    "Bash(git status:*),Bash(git diff:*),Bash(git log:*),Bash(git show:*),"
    "Bash(git merge:*),Bash(git add:*),Bash(gh pr view:*),Bash(gh pr diff:*),"
    "Bash(python3 *ship/scripts/track.py events *)"
)
DEFAULT_AGENT_COMMANDS = {
    "claude": ["claude", "-p", "{prompt}", "--permission-mode", "acceptEdits",
               "--add-dir", "{pr_dir}", "--allowedTools", CLAUDE_TOOLS],
    "pi": ["pi", "-p", "--no-session", "{prompt}"],
    "codex": ["codex", "exec", "{prompt}"],
}

PROMPT = """React to new activity on {url} by following the "React" section of {skill_md}.
Read the events with: python3 {script} events {key}
Your working directory is a scratch worktree at origin/{head}; the PR's base is origin/{base}.
Write your result to {result}.
Never run git commit or git push, and never post, reply or resolve anything yourself:
the tracker commits, pushes and replies from your result file once you exit."""


def state_dir():
    configured = os.environ.get("PR_TRACK_STATE_DIR")
    if configured:
        return Path(configured)
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "pr-track"


def state_file():
    return state_dir() / "state.json"


@contextlib.contextmanager
def locked_state():
    root = state_dir()
    root.mkdir(parents=True, exist_ok=True)
    with open(root / "state.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = load_state()
        yield state
        save_state(state)


def load_state():
    path = state_file()
    if not path.exists():
        return {"version": 1, "me": {}, "prs": {}}
    return json.loads(path.read_text())


def save_state(state):
    path = state_file()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True))
    tmp.replace(path)


def parse_url(url):
    url = url.strip().rstrip("/")
    for host, pattern in (("gitlab", GITLAB_RE), ("github", GITHUB_RE)):
        match = pattern.match(url)
        if match:
            number = int(match["number"])
            sep = "!" if host == "gitlab" else "#"
            return {
                "host": host,
                "hostname": match["hostname"],
                "repo": match["repo"],
                "number": number,
                "url": match.group(0),
                "key": f"{match['hostname']}/{match['repo']}{sep}{number}",
            }
    return None


def run(cmd, cwd=None, check=True, stdin=None):
    # Every caller passes an argv list and no shell is involved.
    # bearer:disable python_lang_os_command_injection
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, input=stdin)
    if check and result.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd[:3])} failed: {result.stderr.strip()[:300]}")
    return result


def cap(text):
    text = (text or "").strip()
    return text if len(text) <= BODY_CAP else text[:BODY_CAP] + " [...]"


def is_github_bot(author):
    if not author:
        return False
    return author.get("__typename") == "Bot" or author.get("login", "").endswith("[bot]")


# --- fetching ---------------------------------------------------------------------


def github_query(repo, numbers):
    owner, name = repo.split("/", 1)
    fields = """title url state isDraft mergeable mergeStateStatus baseRefName headRefName headRefOid reviewDecision
      commits(last: 1) { nodes { commit { statusCheckRollup { state } } } }
      comments(last: 50) { nodes { databaseId body url author { login __typename } } }
      reviews(last: 50) { nodes { databaseId body state url author { login __typename } } }
      reviewThreads(last: 100) { nodes { id isResolved path
        root: comments(first: 1) { nodes { databaseId } }
        comments(last: 20) { nodes { databaseId body url author { login __typename } } } } }"""
    aliases = "\n".join(f"pr{n}: pullRequest(number: {n}) {{ {fields} }}" for n in numbers)
    settings = "defaultBranchRef { name } squashMergeAllowed mergeCommitAllowed rebaseMergeAllowed"
    return (f"query {{ repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) "
            f"{{ {settings} {aliases} }} }}")


def normalize_github(node):
    commits = node.get("commits", {}).get("nodes") or []
    rollup = (commits[0]["commit"].get("statusCheckRollup") or {}) if commits else {}
    comments = []

    def add(raw, kind, thread=None):
        if raw.get("databaseId") is None or not (raw.get("body") or "").strip():
            return
        author = raw.get("author") or {}
        root = ((thread or {}).get("root") or {}).get("nodes") or [{}]
        comments.append({
            "id": f"{kind}:{raw['databaseId']}",
            "kind": kind,
            "author": author.get("login", "ghost"),
            "bot": is_github_bot(author),
            "url": raw.get("url"),
            "path": (thread or {}).get("path"),
            "thread": (thread or {}).get("id"),
            "reply_to": root[0].get("databaseId") if thread else None,
            "body": cap(raw.get("body")),
        })

    for raw in node.get("comments", {}).get("nodes") or []:
        add(raw, "conversation")
    for raw in node.get("reviews", {}).get("nodes") or []:
        add(raw, "review")
    threads = node.get("reviewThreads", {}).get("nodes") or []
    for thread in threads:
        if thread.get("isResolved"):
            continue
        for raw in thread.get("comments", {}).get("nodes") or []:
            add(raw, "inline", thread)
    return {
        "merge_state": node.get("mergeStateStatus"),
        "open_threads": sum(1 for t in threads if not t.get("isResolved")),
        "title": node.get("title"),
        "state": node.get("state"),
        "draft": bool(node.get("isDraft")),
        "base": node.get("baseRefName"),
        "head": node.get("headRefName"),
        "head_sha": node.get("headRefOid"),
        "mergeable": node.get("mergeable"),
        "ci": rollup.get("state"),
        "review": node.get("reviewDecision"),
        "comments": comments,
    }


def fetch_github(hostname, repo, numbers):
    query = github_query(repo, numbers)
    result = run(["gh", "api", "graphql", "--hostname", hostname, "-f", f"query={query}"])
    data = json.loads(result.stdout)["data"]["repository"]
    settings = {
        "default_branch": (data.get("defaultBranchRef") or {}).get("name"),
        "merge_methods": [m for m, field in (("squash", "squashMergeAllowed"), ("merge", "mergeCommitAllowed"),
                                             ("rebase", "rebaseMergeAllowed")) if data.get(field)],
    }
    return {n: normalize_github(data[f"pr{n}"]) | settings for n in numbers if data.get(f"pr{n}")}


GITLAB_STATES = {"opened": "OPEN", "merged": "MERGED", "closed": "CLOSED", "locked": "CLOSED"}
GITLAB_CI = {"failed": "FAILURE", "success": "SUCCESS", "canceled": "ERROR"}


def normalize_gitlab(mr, discussions):
    pipeline = mr.get("head_pipeline") or {}
    ci_state = pipeline.get("status")
    comments = []
    for discussion in discussions:
        notes = discussion.get("notes") or []
        if any(n.get("resolvable") and n.get("resolved") for n in notes):
            continue
        for note in notes:
            if note.get("system") or not (note.get("body") or "").strip():
                continue
            username = (note.get("author") or {}).get("username", "ghost")
            position = note.get("position") or {}
            comments.append({
                "id": f"note:{note['id']}",
                "kind": "inline" if position else "conversation",
                "author": username,
                "bot": bool(GITLAB_BOT_RE.search(username)),
                "url": f"{mr.get('web_url')}#note_{note['id']}",
                "path": position.get("new_path"),
                "thread": discussion.get("id"),
                "reply_to": None,
                "body": cap(note.get("body")),
            })
    status = mr.get("detailed_merge_status")
    return {
        "merge_state": "CLEAN" if status == "mergeable" else (status or "").upper(),
        "open_threads": sum(1 for d in discussions if any(
            n.get("resolvable") and not n.get("resolved") for n in d.get("notes") or [])),
        "title": mr.get("title"),
        "state": GITLAB_STATES.get(mr.get("state"), "OPEN"),
        "draft": bool(mr.get("draft")),
        "base": mr.get("target_branch"),
        "head": mr.get("source_branch"),
        "head_sha": mr.get("sha"),
        "mergeable": "CONFLICTING" if mr.get("has_conflicts") else "MERGEABLE",
        "ci": GITLAB_CI.get(ci_state, "PENDING" if ci_state else None),
        "review": None,
        "comments": comments,
    }


def gitlab_mr_path(repo, number):
    return f"projects/{quote(repo, safe='')}/merge_requests/{number}"


def fetch_gitlab(hostname, repo, numbers):
    out = {}
    for number in numbers:
        base = gitlab_mr_path(repo, number)
        mr = json.loads(run(["glab", "api", "--hostname", hostname, base]).stdout)
        discussions = json.loads(run(["glab", "api", "--hostname", hostname,
                                      f"{base}/discussions?per_page=100"]).stdout)
        out[number] = normalize_gitlab(mr, discussions)
    return out


FETCHERS = {"github": fetch_github, "gitlab": fetch_gitlab}


def whoami(state, host, hostname):
    cached = state["me"].get(hostname)
    if cached:
        return cached
    if host == "github":
        login = run(["gh", "api", "user", "--hostname", hostname, "--jq", ".login"]).stdout.strip()
    else:
        login = json.loads(run(["glab", "api", "--hostname", hostname, "user"]).stdout)["username"]
    state["me"][hostname] = login
    return login


# --- change detection -------------------------------------------------------------


def snapshot_of(current):
    return {k: v for k, v in current.items() if k != "comments"} | {
        "seen": sorted(c["id"] for c in current["comments"])}


def diff_snapshot(old, current, me):
    """Events between the stored snapshot and a fresh fetch; `old` None is a baseline."""
    events = []
    if old is None:
        if current["mergeable"] == "CONFLICTING":
            events.append({"kind": "conflict", "base": current["base"]})
        if current["ci"] in FAILED_CI:
            events.append({"kind": "ci-failed"})
        return events

    seen = set(old.get("seen", []))
    for comment in current["comments"]:
        if comment["id"] in seen or comment["author"] == me:
            continue
        events.append({"kind": "comment", "ref": comment["id"], "source": comment["kind"]} | {
            k: comment[k] for k in ("author", "bot", "url", "path", "thread", "reply_to", "body")})

    if current["mergeable"] == "CONFLICTING" and old.get("mergeable") != "CONFLICTING":
        events.append({"kind": "conflict", "base": current["base"]})
    if current["ci"] in FAILED_CI and old.get("ci") not in FAILED_CI:
        events.append({"kind": "ci-failed"})
    if current["base"] != old.get("base") and old.get("base"):
        events.append({"kind": "base-changed", "from": old.get("base"), "to": current["base"]})
    if current["review"] != old.get("review") and current["review"] in ("APPROVED", "CHANGES_REQUESTED"):
        events.append({"kind": current["review"].lower().replace("_", "-")})
    if current["state"] in FINAL_STATES and old.get("state") not in FINAL_STATES:
        events.append({"kind": current["state"].lower()})
    return events


def stamp(events, now):
    return [e | {"at": now} for e in events]


def is_actionable(event):
    """Bot conversation comments are summaries, previews and coverage reports, never asks."""
    if event["kind"] == "comment":
        return not (event.get("bot") and event.get("source") == "conversation")
    return event["kind"] in ACTIONABLE


def merge_mergeable(old, current):
    """GitHub answers UNKNOWN while it recomputes; keep the last real answer."""
    if current["mergeable"] == "UNKNOWN" and old:
        current["mergeable"] = old.get("mergeable")
    return current


def link_parents(prs, merged_now, events_by_key):
    """A tracked PR whose base is another tracked PR's head is stacked on it."""
    for parent_key in merged_now:
        parent = prs[parent_key]
        head = (parent.get("snapshot") or {}).get("head")
        for key, pr in prs.items():
            if key == parent_key or pr["repo"] != parent["repo"] or pr["hostname"] != parent["hostname"]:
                continue
            if (pr.get("snapshot") or {}).get("base") == head:
                events_by_key.setdefault(key, []).append(
                    {"kind": "parent-merged", "parent": parent["url"], "branch": head})


def pid_alive(pid):
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def watched(pr):
    return pid_alive(pr.get("watcher_pid"))


def refresh(state, keys, now):
    """Fetch every PR in `keys`, store the new snapshots, return {key: events}."""
    groups = {}
    for key in keys:
        pr = state["prs"][key]
        groups.setdefault((pr["host"], pr["hostname"], pr["repo"]), []).append(key)

    events_by_key, merged_now, failures = {}, [], []
    for (host, hostname, repo), group in groups.items():
        try:
            me = whoami(state, host, hostname)
            fetched = FETCHERS[host](hostname, repo, [state["prs"][k]["number"] for k in group])
        except (RuntimeError, json.JSONDecodeError, KeyError) as error:
            failures.append(f"{hostname}/{repo}: {error}")
            continue
        for key in group:
            pr = state["prs"][key]
            current = fetched.get(pr["number"])
            if current is None:
                failures.append(f"{key}: not found")
                continue
            current = merge_mergeable(pr.get("snapshot"), current)
            events = diff_snapshot(pr.get("snapshot"), current, me)
            if events or current["head_sha"] != (pr.get("snapshot") or {}).get("head_sha"):
                pr["quiet_since"] = now
            pr["snapshot"] = snapshot_of(current)
            if current["ci"] == "SUCCESS":
                pr.pop("ci_attempts", None)
            if any(e["kind"] == "merged" for e in events):
                merged_now.append(key)
            if events:
                events_by_key[key] = events

    link_parents(state["prs"], merged_now, events_by_key)
    return {k: stamp(v, now) for k, v in events_by_key.items()}, failures


# --- telling the user -------------------------------------------------------------


def notify(title, message):
    if sys.platform != "darwin" or os.environ.get("PR_TRACK_NOTIFY") == "0":
        return
    # The title and message reach osascript as argv items, never as AppleScript source.
    # bearer:disable python_lang_os_command_injection
    subprocess.run(
        ["osascript", "-e", "on run argv", "-e",
         "display notification (item 1 of argv) with title (item 2 of argv)", "-e", "end run",
         message, title],
        capture_output=True)


def short_name(pr):
    sep = "!" if pr["host"] == "gitlab" else "#"
    return f"{pr['repo'].split('/')[-1]}{sep}{pr['number']}"


def escalate(pr, reasons, notify_enabled):
    """The only path that interrupts the user: judgment calls, stuck runs, requested changes."""
    if not reasons:
        return
    now = int(time.time())
    pr["attention"] = (pr.get("attention", []) + [{"at": now, "reason": r} for r in reasons])[-ATTENTION_KEEP:]
    for reason in reasons:
        print(f"escalate|{pr['key']}|{reason}")
    if notify_enabled:
        notify(f"pr-track: {short_name(pr)} needs you", "; ".join(reasons))


# --- the reacting agent -----------------------------------------------------------


def pr_dir(key):
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", key)
    return state_dir() / "prs" / slug


def prep_path(key):
    return pr_dir(key) / "worktree"


def remote_for(worktree, branch):
    configured = run(["git", "-C", worktree, "config", f"branch.{branch}.remote"], check=False).stdout.strip()
    if configured:
        return configured
    remotes = run(["git", "-C", worktree, "remote"], check=False).stdout.split()
    return remotes[0] if len(remotes) == 1 else "origin"


def ensure_prep(pr):
    snap = pr["snapshot"]
    prep = prep_path(pr["key"])
    if prep.exists():
        return prep
    worktree = pr["worktree"]
    remote = remote_for(worktree, snap["head"])
    run(["git", "-C", worktree, "fetch", "--quiet", remote, snap["head"], snap["base"]])
    run(["git", "-C", worktree, "worktree", "add", "--detach", str(prep), f"{remote}/{snap['head']}"])
    pr["prep_start"] = run(["git", "-C", str(prep), "rev-parse", "HEAD"]).stdout.strip()
    pr["remote"] = remote
    return prep


def drop_prep(pr):
    prep = prep_path(pr["key"])
    if prep.exists():
        run(["git", "-C", pr["worktree"], "worktree", "remove", "--force", str(prep)], check=False)
    for field in ("prep_start", "prepared"):
        pr.pop(field, None)


def agent_template(agent):
    override = os.environ.get(f"PR_TRACK_AGENT_CMD_{agent.upper()}")
    return shlex.split(override) if override else DEFAULT_AGENT_COMMANDS[agent]


def agent_command(agent, values):
    return [part.format(**values) for part in agent_template(agent)]


def dispatch(pr, now):
    directory = pr_dir(pr["key"])
    directory.mkdir(parents=True, exist_ok=True)
    prep = ensure_prep(pr)
    batch = pr.get("batch", []) + pr.pop("pending", [])
    pr["batch"] = batch
    (directory / "events.json").write_text(json.dumps(batch, indent=2))
    (directory / "result.json").unlink(missing_ok=True)
    if any(e["kind"] == "ci-failed" for e in batch):
        pr["ci_attempts"] = pr.get("ci_attempts", 0) + 1
    script = Path(os.path.abspath(__file__))
    values = {
        "url": pr["url"], "key": pr["key"], "head": pr["snapshot"]["head"], "base": pr["snapshot"]["base"],
        "skill_md": script.parent.parent / "references" / "pr-track.md", "script": script,
        "result": directory / "result.json", "pr_dir": directory,
    }
    values["prompt"] = PROMPT.format(**values)
    # The command is a fixed argv template (or the user's own env override) run without a shell,
    # and pr_dir() slugs the key, so neither the argv nor the log path carries a separator.
    # bearer:disable python_lang_os_command_injection, python_lang_path_traversal
    with open(directory / "agent.log", "a") as log:
        process = subprocess.Popen(agent_command(pr["agent"], values), cwd=prep, stdout=log,
                                   stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    pr["run"] = {"pid": process.pid, "started_at": now}
    pr.setdefault("runs", []).append(now)


def valid_commit_message(message):
    if not isinstance(message, str) or not message.strip():
        return False
    header = message.strip().splitlines()[0]
    return bool(COMMIT_HEADER_RE.match(header)) and not any(bad in message for bad in FORBIDDEN_IN_MESSAGES)


def load_result(pr):
    path = pr_dir(pr["key"]) / "result.json"
    if not path.exists():
        return None
    try:
        result = json.loads(path.read_text())
    except json.JSONDecodeError:
        return None
    return result if isinstance(result, dict) else None


def split_replies(result, batch):
    """Post only to bots; anything addressed to a human becomes a draft, whatever the model said."""
    by_ref = {e.get("ref"): e for e in batch if e.get("ref")}
    posts, drafts = [], [d for d in result.get("drafts") or [] if (d.get("body") or "").strip()]
    for reply in result.get("replies") or []:
        event = by_ref.get(reply.get("ref"))
        if not event or not (reply.get("body") or "").strip():
            continue
        (posts if event.get("bot") else drafts).append(reply | {"event": event})
    for draft in drafts:
        draft.setdefault("event", by_ref.get(draft.get("ref"), {}))
    return posts, drafts


def footer(pr, state):
    me = state["me"].get(pr["hostname"], "")
    return f"\n\n<sub>Posted by {AGENT_NAMES.get(pr['agent'], pr['agent'])} on behalf of @{me}</sub>"


def post_reply(pr, event, body, resolve):
    hostname, repo, number = pr["hostname"], pr["repo"], pr["number"]
    if pr["host"] == "github":
        if event.get("source") == "inline" and event.get("reply_to"):
            run(["gh", "api", "--hostname", hostname, "-X", "POST",
                 f"repos/{repo}/pulls/{number}/comments/{event['reply_to']}/replies", "-f", f"body={body}"])
        else:
            body = f"@{event.get('author')} {body}"
            run(["gh", "api", "--hostname", hostname, "-X", "POST",
                 f"repos/{repo}/issues/{number}/comments", "-f", f"body={body}"])
        if resolve and event.get("thread"):
            run(["gh", "api", "graphql", "--hostname", hostname, "-f", f"id={event['thread']}", "-f",
                 "query=mutation($id: ID!) { resolveReviewThread(input: {threadId: $id}) { thread { id } } }"])
        return
    base = gitlab_mr_path(repo, number)
    if event.get("thread"):
        run(["glab", "api", "--hostname", hostname, "-X", "POST",
             f"{base}/discussions/{event['thread']}/notes", "-f", f"body={body}"])
        if resolve:
            run(["glab", "api", "--hostname", hostname, "-X", "PUT",
                 f"{base}/discussions/{event['thread']}?resolved=true"])
    else:
        run(["glab", "api", "--hostname", hostname, "-X", "POST", f"{base}/notes", "-f", f"body={body}"])


def default_branch(pr):
    out = run(["git", "-C", pr["worktree"], "symbolic-ref", "--short",
               f"refs/remotes/{pr.get('remote', 'origin')}/HEAD"], check=False).stdout.strip()
    return out.split("/", 1)[1] if "/" in out else None


def commit_and_push(pr, prep, message):
    """Returns None on success or when there was nothing to push, else why it stopped."""
    git_dir = Path(run(["git", "-C", str(prep), "rev-parse", "--absolute-git-dir"]).stdout.strip())
    if (git_dir / "MERGE_HEAD").exists():
        if run(["git", "-C", str(prep), "diff", "--name-only", "--diff-filter=U"]).stdout.strip():
            return "the merge with the base still has conflicts the agent could not resolve"
        if run(["git", "-C", str(prep), "commit", "--no-edit", "--quiet"], check=False).returncode != 0:
            return "committing the merge with the base failed (a commit hook?)"
    run(["git", "-C", str(prep), "add", "--all"])
    if run(["git", "-C", str(prep), "diff", "--cached", "--quiet"], check=False).returncode != 0:
        if not valid_commit_message(message):
            message = f"fix: address review feedback on {short_name(pr)}"
        committed = run(["git", "-C", str(prep), "commit", "--quiet", "-F", "-"], check=False, stdin=message)
        if committed.returncode != 0:
            return f"committing the fix failed: {committed.stderr.strip()[:200]}"
    head = run(["git", "-C", str(prep), "rev-parse", "HEAD"]).stdout.strip()
    if head == pr.get("prep_start"):
        return None
    branch = pr["snapshot"]["head"]
    if branch in (pr["snapshot"]["base"], default_branch(pr)):
        return f"refusing to push {branch}: it is the base or default branch"
    pushed = run(["git", "-C", str(prep), "push", "--quiet", pr.get("remote", "origin"),
                  f"HEAD:refs/heads/{branch}"], check=False)
    if pushed.returncode != 0:
        return f"push to {branch} was rejected: {pushed.stderr.strip()[:200]}"
    pr["last_push"] = head
    return None


def write_drafts(pr, drafts):
    if not drafts:
        return
    path = pr_dir(pr["key"]) / "drafts.md"
    lines = []
    for draft in drafts:
        event = draft.get("event") or {}
        lines += [f"## {event.get('author', '?')}: {event.get('url', draft.get('ref', ''))}", "",
                  draft["body"].strip(), ""]
    # pr_dir() slugs the key to [A-Za-z0-9._-], so the path cannot leave the state directory.
    # bearer:disable python_lang_path_traversal
    with open(path, "a") as handle:
        handle.write("\n".join(lines) + "\n")
    pr["drafts"] = pr.get("drafts", 0) + len(drafts)


def finalize(pr, state, notify_enabled):
    """Turn a finished run's result into a commit, a push, bot replies and escalations."""
    batch = pr.pop("batch", [])
    pr.pop("run", None)
    prep = prep_path(pr["key"])
    result = load_result(pr)
    if result is None:
        escalate(pr, [f"the {pr['agent']} run ended without a result; see {pr_dir(pr['key']) / 'agent.log'}"],
                 notify_enabled)
        drop_prep(pr)
        return "no result"
    reasons = [str(r) for r in result.get("escalate") or [] if str(r).strip()]
    if any(e["kind"] == "changes-requested" for e in batch):
        reasons.append("a reviewer requested changes")
    posts, drafts = split_replies(result, batch)

    stopped = commit_and_push(pr, prep, result.get("commit")) if prep.exists() else None
    if stopped:
        pr["prepared"] = True
        escalate(pr, reasons + [f"{stopped}; the work is kept, `prt take {pr['number']}` applies it"],
                 notify_enabled)
        write_drafts(pr, drafts)
        return "stuck"

    tail = footer(pr, state)
    for post in posts:
        try:
            post_reply(pr, post["event"], post["body"].strip() + tail, post.get("resolve", True))
        except RuntimeError as error:
            reasons.append(f"could not reply to {post['event'].get('author')}: {error}")
    write_drafts(pr, drafts)
    drop_prep(pr)
    escalate(pr, reasons, notify_enabled)
    return "pushed" if pr.get("last_push") else "no change"


def settle_and_dispatch(state, now, notify_enabled, dispatch_enabled):
    running = sum(1 for pr in state["prs"].values() if pid_alive((pr.get("run") or {}).get("pid")))
    for key, pr in state["prs"].items():
        current_run = pr.get("run")
        if current_run:
            if pid_alive(current_run["pid"]):
                if now - current_run["started_at"] > RUN_TIMEOUT_SECONDS:
                    with contextlib.suppress(ProcessLookupError, PermissionError):
                        os.killpg(current_run["pid"], signal.SIGTERM)
                continue
            print(f"done|{key}|{finalize(pr, state, notify_enabled)}")

        pending = pr.get("pending") or []
        if pending and pr.get("ci_attempts", 0) >= MAX_CI_ATTEMPTS and any(
                e["kind"] == "ci-failed" for e in pending):
            pr["pending"] = pending = [e for e in pending if e["kind"] != "ci-failed"]
            escalate(pr, [f"CI still fails after {MAX_CI_ATTEMPTS} fixes"], notify_enabled)
        if not dispatch_enabled or not pending or pr.get("prepared"):
            continue
        if now - max(e["at"] for e in pending) < SETTLE_SECONDS or running >= MAX_PARALLEL_RUNS:
            continue
        pr["runs"] = [t for t in pr.get("runs", []) if now - t < DAY_SECONDS]
        if len(pr["runs"]) >= MAX_RUNS_PER_DAY or not shutil.which(agent_template(pr["agent"])[0]):
            if not pr.get("capped"):
                escalate(pr, [f"no {pr['agent']} run available (daily cap or not installed)"], notify_enabled)
            pr["capped"] = True
            continue
        try:
            dispatch(pr, now)
        except RuntimeError as error:
            escalate(pr, [f"could not start a run: {error}"], notify_enabled)
            continue
        pr.pop("capped", None)
        running += 1
        print(f"dispatch|{key}|{pr['agent']}")


def record(state, events_by_key, notify_enabled=False):
    for key, events in events_by_key.items():
        pr = state["prs"][key]
        for event in events:
            print(f"event|{key}|{json.dumps(event, sort_keys=True)}")
            if event["kind"] in FINAL_KINDS and notify_enabled and not pr.get("merged_by_tracker"):
                notify(f"pr-track: {short_name(pr)}", FINAL_KINDS[event["kind"]])
        actionable = [e for e in events if is_actionable(e)]
        if actionable:
            pr.setdefault("pending", []).extend(actionable)


def merge_blockers(pr, now):
    """Why a PR set to merge is not merged yet; empty means merge it now."""
    snap = pr.get("snapshot") or {}
    checks = [
        (snap.get("state") == "OPEN", "not open"),
        (not snap.get("draft"), "draft"),
        (snap.get("merge_state") == "CLEAN", f"merge state {snap.get('merge_state')}"),
        (snap.get("ci") in ("SUCCESS", None), f"ci {snap.get('ci')}"),
        (not snap.get("open_threads"), "unresolved threads"),
        (snap.get("default_branch") in (None, snap.get("base")), "stacked on a non-default base"),
        (pr.get("merge_skip_base") != snap.get("base"), "stacked on a non-default base"),
        (not (pr.get("pending") or pr.get("run") or pr.get("prepared")), "work in progress"),
        (not pr.get("attention"), "waiting on the user"),
        (now - pr.get("quiet_since", now) >= SETTLE_SECONDS, "settling"),
        (pr.get("merge_failed_sha") != snap.get("head_sha"), "merge already failed at this commit"),
    ]
    return [reason for ok, reason in checks if not ok]


def merge_github(pr):
    snap = pr["snapshot"]
    allowed = snap.get("merge_methods") or ["merge"]
    method = next(m for m in MERGE_ORDER if m in allowed)
    run(["gh", "pr", "merge", pr["url"], f"--{method}", "--match-head-commit", snap["head_sha"]])
    return method


def merge_gitlab(pr):
    """GitLab's MR payload carries no default branch, so the project is read only when merging."""
    snap = pr["snapshot"]
    project = json.loads(run(["glab", "api", "--hostname", pr["hostname"],
                              f"projects/{quote(pr['repo'], safe='')}"]).stdout)
    if snap["base"] != project.get("default_branch"):
        pr["merge_skip_base"] = snap["base"]
        return None
    squash = project.get("squash_option") != "never"
    command = ["glab", "api", "--hostname", pr["hostname"], "-X", "PUT",
               f"{gitlab_mr_path(pr['repo'], pr['number'])}/merge", "-f", f"sha={snap['head_sha']}"]
    if squash:
        command += ["-F", "squash=true"]
    run(command)
    return "squash" if squash else project.get("merge_method", "merge")


MERGERS = {"github": merge_github, "gitlab": merge_gitlab}


def auto_merge(state, now, notify_enabled):
    for key, pr in state["prs"].items():
        if not pr.get("merge") or merge_blockers(pr, now):
            continue
        try:
            method = MERGERS[pr["host"]](pr)
        except RuntimeError as error:
            pr["merge_failed_sha"] = pr["snapshot"]["head_sha"]
            escalate(pr, [f"could not merge: {error}"], notify_enabled)
            continue
        if method is None:
            continue
        pr["merged_by_tracker"] = True
        print(f"merged|{key}|{method}")
        if notify_enabled:
            notify(f"pr-track: {short_name(pr)}", f"merged ({method})")


def drop_finished(state):
    for key in [k for k, pr in state["prs"].items() if (pr.get("snapshot") or {}).get("state") in FINAL_STATES]:
        pr = state["prs"][key]
        if pr.get("prepared") or pid_alive((pr.get("run") or {}).get("pid")):
            continue
        drop_prep(pr)
        del state["prs"][key]
        print(f"untracked|{key}")


# --- commands ---------------------------------------------------------------------


def cmd_poll(args):
    now = int(time.time())
    with locked_state() as state:
        keys = [k for k, pr in state["prs"].items() if not watched(pr)]
        if not keys:
            return EXIT_OK
        events_by_key, failures = refresh(state, keys, now)
        for failure in failures:
            print(f"error|{failure}")
        record(state, events_by_key, args.notify)
        settle_and_dispatch(state, now, args.notify, args.dispatch)
        if args.dispatch:
            auto_merge(state, now, args.notify)
        drop_finished(state)
    return EXIT_OK


def resolve_ref(state, ref):
    parsed = parse_url(ref)
    if parsed and parsed["key"] in state["prs"]:
        return parsed["key"]
    if ref in state["prs"]:
        return ref
    matches = [k for k, pr in state["prs"].items() if ref.lstrip("#!") == str(pr["number"])]
    return matches[0] if len(matches) == 1 else None


def detect_agent():
    if os.environ.get("CLAUDECODE"):
        return "claude"
    if any(k.startswith("PI_CODING_AGENT") for k in os.environ):
        return "pi"
    if any(k.startswith("CODEX_") for k in os.environ):
        return "codex"
    return "claude"


def cmd_add(args):
    parsed = parse_url(args.url)
    if not parsed:
        ui.err(f"Not a GitHub PR or GitLab MR URL: {args.url}")
        return EXIT_USAGE
    worktree = args.worktree or os.getcwd()
    top = run(["git", "-C", worktree, "rev-parse", "--show-toplevel"], check=False).stdout.strip()
    if not top:
        ui.err(f"Not inside a git repository: {worktree}")
        return EXIT_USAGE
    now = int(time.time())
    with locked_state() as state:
        previous = state["prs"].get(parsed["key"])
        state["prs"][parsed["key"]] = (previous or {}) | parsed | {
            "agent": args.agent or detect_agent(), "worktree": top, "added_at": now, "merge": True}
        events_by_key, failures = refresh(state, [parsed["key"]], now)
        if failures:
            if previous is None:
                del state["prs"][parsed["key"]]
            else:
                state["prs"][parsed["key"]] = previous
            ui.err(f"Could not read {parsed['url']}: {failures[0]}")
            return EXIT_FETCH_FAILED
        pr = state["prs"][parsed["key"]]
        if pr["snapshot"]["state"] in FINAL_STATES:
            del state["prs"][parsed["key"]]
            ui.warn(f"{short_name(pr)} is already {pr['snapshot']['state'].lower()}; not tracking it")
            return EXIT_OK
        record(state, events_by_key)
    ui.ok(f"Tracking {short_name(pr)} ({pr['agent']} fixes, pushes and merges when ready; "
          f"you hear only what needs you)")
    return EXIT_OK


def cmd_rm(args):
    with locked_state() as state:
        key = resolve_ref(state, args.ref)
        if not key:
            ui.err(f"Not tracked: {args.ref}")
            return EXIT_NOT_FOUND
        pr = state["prs"][key]
        if pr.get("prepared") and not args.force:
            ui.warn(f"{short_name(pr)} has unpushed work at {ui.path(str(prep_path(key)))}; "
                    f"`prt take` it or pass --force")
            return EXIT_TAKE_REFUSED
        drop_prep(pr)
        del state["prs"][key]
    ui.ok(f"Stopped tracking {short_name(pr)}")
    return EXIT_OK


def cmd_ack(args):
    with locked_state() as state:
        key = resolve_ref(state, args.ref)
        if not key:
            ui.err(f"Not tracked: {args.ref}")
            return EXIT_NOT_FOUND
        state["prs"][key].pop("attention", None)
        state["prs"][key].pop("capped", None)
    ui.ok("Cleared")
    return EXIT_OK


def cmd_merge(args):
    with locked_state() as state:
        key = resolve_ref(state, args.ref)
        if not key:
            ui.err(f"Not tracked: {args.ref}")
            return EXIT_NOT_FOUND
        pr = state["prs"][key]
        pr["merge"] = not args.off
        blockers = merge_blockers(pr, int(time.time())) if pr["merge"] else []
    if not pr["merge"]:
        ui.ok(f"{short_name(pr)} will not be merged automatically")
    else:
        ui.ok(f"{short_name(pr)} merges once ready" + (f" (waiting: {', '.join(blockers)})" if blockers else ""))
    return EXIT_OK


def cmd_drafts(args):
    state = load_state()
    key = resolve_ref(state, args.ref)
    if not key:
        ui.err(f"Not tracked: {args.ref}")
        return EXIT_NOT_FOUND
    path = pr_dir(key) / "drafts.md"
    if not path.exists():
        ui.note("No reply drafts", indent=0)
        return EXIT_OK
    print(path.read_text())
    return EXIT_OK


def status_line(pr):
    snap = pr.get("snapshot") or {}
    bits = [snap.get("state", "?").lower()]
    if snap.get("mergeable") == "CONFLICTING":
        bits.append("conflicts")
    if snap.get("ci"):
        bits.append(f"ci {snap['ci'].lower()}")
    if pr.get("pending"):
        bits.append(f"{len(pr['pending'])} pending")
    if pid_alive((pr.get("run") or {}).get("pid")):
        bits.append(f"{pr['agent']} working")
    if pr.get("drafts"):
        bits.append(f"{pr['drafts']} reply drafts")
    if pr.get("merge"):
        bits.append("auto-merge")
    if watched(pr):
        bits.append("watched in session")
    return ", ".join(bits)


def cmd_ls(args):
    state = load_state()
    if args.json:
        print(json.dumps(state["prs"], indent=2, sort_keys=True))
        return EXIT_OK
    if not state["prs"]:
        ui.note("No tracked PRs", indent=0)
        return EXIT_OK
    ui.title("🛰️ Tracked PRs")
    for pr in sorted(state["prs"].values(), key=lambda p: p["key"]):
        title = (pr.get("snapshot") or {}).get("title") or ""
        ui.item(f"{short_name(pr)}  {title}  [{status_line(pr)}]")
        ui.note(pr["url"])
        for item in pr.get("attention", []):
            ui.warn(f"needs you: {item['reason']}")
    ui.done(f"{len(state['prs'])} tracked")
    return EXIT_OK


def cmd_events(args):
    state = load_state()
    key = resolve_ref(state, args.ref)
    if not key:
        print(f"not-tracked|{args.ref}")
        return EXIT_NOT_FOUND
    pr = state["prs"][key]
    snap = pr["snapshot"]
    print(f"pr|{pr['url']}|{snap.get('title')}")
    print(f"branches|head={snap['head']}|base={snap['base']}")
    batch_file = pr_dir(key) / "events.json"
    events = json.loads(batch_file.read_text()) if batch_file.exists() else pr.get("pending", [])
    for event in events:
        detail = {k: v for k, v in event.items()
                  if k not in ("kind", "at", "body", "thread", "reply_to", "source")}
        print(f"\n== {event['kind']} {json.dumps(detail, sort_keys=True)}")
        if event.get("body"):
            print(event["body"])
    return EXIT_OK


def cmd_watch(args):
    with locked_state() as state:
        keys = [resolve_ref(state, r) for r in args.refs] if args.refs else list(state["prs"])
        missing = [r for r, k in zip(args.refs, keys) if not k]
        if missing:
            print(f"not-tracked|{','.join(missing)}")
            return EXIT_NOT_FOUND
        for key in keys:
            state["prs"][key]["watcher_pid"] = os.getpid()
    try:
        while True:
            now = int(time.time())
            with locked_state() as state:
                live = [k for k in keys if k in state["prs"]]
                events_by_key, failures = refresh(state, live, now)
                for failure in failures:
                    print(f"error|{failure}", flush=True)
                for key, events in events_by_key.items():
                    for event in events:
                        print(f"event|{key}|{json.dumps(event, sort_keys=True)}", flush=True)
                drop_finished(state)
                live = [k for k in keys if k in state["prs"]]
            if not live:
                print("all-closed", flush=True)
                return EXIT_OK
            time.sleep(args.interval)
    finally:
        with locked_state() as state:
            for key in keys:
                if key in state["prs"] and state["prs"][key].get("watcher_pid") == os.getpid():
                    del state["prs"][key]["watcher_pid"]


def branch_worktree(any_worktree, branch):
    listing = run(["git", "-C", any_worktree, "worktree", "list", "--porcelain"]).stdout
    path = None
    for line in listing.splitlines():
        if line.startswith("worktree "):
            path = line.split(" ", 1)[1]
        elif line == f"branch refs/heads/{branch}":
            return path
    return None


def cmd_take(args):
    with locked_state() as state:
        key = resolve_ref(state, args.ref)
        if not key:
            ui.err(f"Not tracked: {args.ref}")
            return EXIT_NOT_FOUND
        pr = state["prs"][key]
        prep = prep_path(key)
        if not pr.get("prepared") or not prep.exists():
            ui.err(f"No kept work for {short_name(pr)}")
            return EXIT_NOT_FOUND
        head = pr["snapshot"]["head"]
        target = branch_worktree(pr["worktree"], head)
        if not target:
            ui.err(f"`{head}` is not checked out anywhere; `git switch {head}` in a worktree first")
            return EXIT_TAKE_REFUSED
        if run(["git", "-C", target, "status", "--porcelain"]).stdout.strip():
            ui.err(f"{ui.path(target)} has uncommitted changes; ship or stash them first")
            return EXIT_TAKE_REFUSED

        prep_head = run(["git", "-C", str(prep), "rev-parse", "HEAD"]).stdout.strip()
        if prep_head != pr.get("prep_start"):
            merged = run(["git", "-C", target, "merge", "--ff-only", "--quiet", prep_head], check=False)
            if merged.returncode != 0:
                ui.err(f"{head} moved since the work was kept; merge {prep_head[:10]} by hand")
                return EXIT_TAKE_REFUSED
            ui.ok(f"Fast-forwarded {head} to {prep_head[:10]}")

        run(["git", "-C", str(prep), "add", "--intent-to-add", "--all"])
        patch = run(["git", "-C", str(prep), "diff", "--binary", "--no-color", "--no-ext-diff",
                     "--src-prefix=a/", "--dst-prefix=b/", "HEAD"]).stdout
        if patch.strip():
            applied = run(["git", "-C", target, "apply", "--whitespace=nowarn"], check=False, stdin=patch)
            if applied.returncode != 0:
                ui.err(f"Patch did not apply: {applied.stderr.strip()[:300]}")
                return EXIT_TAKE_REFUSED
            ui.ok(f"Applied the uncommitted changes to {ui.path(target)}")
        drop_prep(pr)
        pr.pop("attention", None)
    ui.done(f"Review the changes in {ui.path(target)}, then /ship")
    return EXIT_OK


def main(argv=None):
    parser = argparse.ArgumentParser(prog="track.py", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add")
    add.add_argument("url")
    add.add_argument("--agent", choices=AGENTS)
    add.add_argument("--worktree")
    add.set_defaults(func=cmd_add)

    merge = sub.add_parser("merge")
    merge.add_argument("ref")
    merge.add_argument("--off", action="store_true")
    merge.set_defaults(func=cmd_merge)

    rm = sub.add_parser("rm")
    rm.add_argument("ref")
    rm.add_argument("--force", action="store_true")
    rm.set_defaults(func=cmd_rm)

    ls = sub.add_parser("ls")
    ls.add_argument("--json", action="store_true")
    ls.set_defaults(func=cmd_ls)

    for name, func in (("ack", cmd_ack), ("drafts", cmd_drafts), ("events", cmd_events), ("take", cmd_take)):
        command = sub.add_parser(name)
        command.add_argument("ref")
        command.set_defaults(func=func)

    poll = sub.add_parser("poll")
    poll.add_argument("--notify", action="store_true")
    poll.add_argument("--dispatch", action="store_true")
    poll.set_defaults(func=cmd_poll)

    watch = sub.add_parser("watch")
    watch.add_argument("refs", nargs="*")
    watch.add_argument("--interval", type=int, default=WATCH_INTERVAL)
    watch.set_defaults(func=cmd_watch)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
