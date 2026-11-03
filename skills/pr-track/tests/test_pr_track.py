"""The /pr-track script: change detection, dispatch gating, finalizing a run, and take.

Fetchers are replaced with in-memory snapshots and replies with a recorder, so no
case reaches GitHub or GitLab, and no agent is ever started: dispatch is swapped
for a recorder. Commit, push and take run real git against a throwaway bare origin.
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "track.py"
URL = "https://github.com/acme/app/pull/7"
CHILD_URL = "https://github.com/acme/app/pull/8"
KEY = "github.com/acme/app#7"


def _load():
    cached = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec = importlib.util.spec_from_file_location("pr_track", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.dont_write_bytecode = cached


track = _load()
POLL = type("Args", (), {"notify": False, "dispatch": True})


def snapshot(**overrides):
    base = {
        "title": "feat: thing", "state": "OPEN", "draft": False, "base": "main", "head": "feature/thing",
        "head_sha": "abc", "mergeable": "MERGEABLE", "ci": "PENDING", "review": None, "comments": [],
        "merge_state": "BLOCKED", "open_threads": 0, "default_branch": "main", "merge_methods": ["squash", "merge"],
    }
    return base | overrides


def comment(cid, author="coderabbitai", bot=True, kind="inline"):
    return {"id": f"{kind}:{cid}", "kind": kind, "author": author, "bot": bot, "url": f"{URL}#{cid}",
            "path": "a.py", "thread": f"T{cid}", "reply_to": cid, "body": "please fix"}


@pytest.fixture
def state_home(tmp_path, monkeypatch):
    monkeypatch.setenv("PR_TRACK_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("PR_TRACK_NOTIFY", "0")
    return tmp_path / "state"


@pytest.fixture
def remote(monkeypatch):
    """Serve fetches from a dict the case mutates between polls."""
    served = {}

    def whoami(state, host, hostname):
        state["me"][hostname] = "me"
        return "me"

    monkeypatch.setattr(track, "whoami", whoami)
    monkeypatch.setitem(track.FETCHERS, "github",
                        lambda hostname, repo, numbers: {n: served[n] for n in numbers if n in served})
    return served


@pytest.fixture
def dispatched(monkeypatch):
    calls = []
    monkeypatch.setattr(track, "dispatch", lambda pr, now: calls.append((pr["key"], now)) or pr.pop("pending"))
    monkeypatch.setattr(track.shutil, "which", lambda name: f"/bin/{name}")
    return calls


def clock(monkeypatch, *times):
    ticks = iter(times)
    monkeypatch.setattr(track.time, "time", lambda: next(ticks))


@pytest.mark.parametrize(("url", "key"), [
    (URL, KEY),
    ("https://gitlab.com/group/sub/proj/-/merge_requests/12", "gitlab.com/group/sub/proj!12"),
])
def test_parse_url_keys_by_host_repo_and_number(url, key):
    assert track.parse_url(url)["key"] == key


def test_parse_url_rejects_non_pr_links():
    assert track.parse_url("https://github.com/acme/app/issues/3") is None


def test_normalize_github_skips_resolved_threads_and_keeps_reply_targets():
    node = {
        "state": "OPEN", "mergeable": "MERGEABLE", "commits": {"nodes": []},
        "comments": {"nodes": [{"databaseId": 1, "body": "", "author": {"login": "a"}}]},
        "reviews": {"nodes": [{"databaseId": 2, "body": "lgtm", "author": {"login": "bob", "__typename": "User"}}]},
        "reviewThreads": {"nodes": [
            {"id": "T3", "isResolved": True, "comments": {"nodes": [{"databaseId": 3, "body": "x", "author": {}}]}},
            {"id": "T4", "isResolved": False, "path": "a.py", "root": {"nodes": [{"databaseId": 40}]},
             "comments": {"nodes": [
                 {"databaseId": 4, "body": "nit", "author": {"login": "coderabbitai", "__typename": "Bot"}}]}},
        ]},
    }
    comments = track.normalize_github(node)["comments"]
    assert [(c["id"], c["bot"]) for c in comments] == [("review:2", False), ("inline:4", True)]
    assert (comments[1]["thread"], comments[1]["reply_to"]) == ("T4", 40)


def test_normalize_gitlab_skips_resolved_discussions_and_system_notes():
    mr = {"state": "opened", "web_url": "https://gitlab.com/g/p/-/merge_requests/1", "has_conflicts": True,
          "head_pipeline": {"status": "failed"}}
    discussions = [
        {"id": "D1", "notes": [{"id": 1, "body": "done", "resolvable": True, "resolved": True,
                                "author": {"username": "alice"}}]},
        {"id": "D2", "notes": [{"id": 2, "body": "moved", "system": True, "author": {"username": "alice"}}]},
        {"id": "D3", "notes": [{"id": 3, "body": "rename this", "author": {"username": "project_9_bot"},
                                "position": {"new_path": "a.py"}}]},
    ]
    current = track.normalize_gitlab(mr, discussions)
    assert (current["mergeable"], current["ci"]) == ("CONFLICTING", "FAILURE")
    assert [(c["id"], c["bot"], c["thread"]) for c in current["comments"]] == [("note:3", True, "D3")]


def test_baseline_reports_existing_problems_but_not_existing_comments():
    current = snapshot(mergeable="CONFLICTING", comments=[comment(1)])
    assert [e["kind"] for e in track.diff_snapshot(None, current, "me")] == ["conflict"]


def test_only_new_comments_from_others_become_events():
    old = track.snapshot_of(snapshot(comments=[comment(1)]))
    current = snapshot(comments=[comment(1), comment(2), comment(3, author="me", bot=False)])
    events = track.diff_snapshot(old, current, "me")
    assert [e["ref"] for e in events] == ["inline:2"]


def test_conflict_and_ci_failure_fire_on_transition_only():
    old = track.snapshot_of(snapshot(mergeable="CONFLICTING", ci="FAILURE"))
    assert track.diff_snapshot(old, snapshot(mergeable="CONFLICTING", ci="FAILURE"), "me") == []
    fresh = track.snapshot_of(snapshot())
    kinds = [e["kind"] for e in track.diff_snapshot(fresh, snapshot(mergeable="CONFLICTING", ci="FAILURE"), "me")]
    assert kinds == ["conflict", "ci-failed"]


def test_unknown_mergeable_keeps_the_last_real_answer():
    old = track.snapshot_of(snapshot(mergeable="CONFLICTING"))
    assert track.merge_mergeable(old, snapshot(mergeable="UNKNOWN"))["mergeable"] == "CONFLICTING"


@pytest.mark.parametrize(("event", "actionable"), [
    ({"kind": "comment", "bot": True, "source": "inline"}, True),
    ({"kind": "comment", "bot": True, "source": "review"}, True),
    ({"kind": "comment", "bot": True, "source": "conversation"}, False),
    ({"kind": "comment", "bot": False, "source": "inline"}, True),
    ({"kind": "comment", "bot": False, "source": "conversation"}, True),
    ({"kind": "conflict"}, True),
    ({"kind": "changes-requested"}, True),
    ({"kind": "approved"}, False),
    ({"kind": "merged"}, False),
])
def test_only_actionable_events_can_wake_a_model(event, actionable):
    assert track.is_actionable(event) is actionable


def _track(state_home, url, served, number, worktree=None, **snap):
    served[number] = snapshot(**snap)
    with track.locked_state() as state:
        parsed = track.parse_url(url)
        state["prs"][parsed["key"]] = parsed | {"agent": "claude", "worktree": str(worktree or state_home)}
        track.refresh(state, [parsed["key"]], 0)


def test_parent_merge_wakes_the_stacked_child(state_home, remote):
    _track(state_home, URL, remote, 7, head="feature/parent")
    _track(state_home, CHILD_URL, remote, 8, head="feature/child", base="feature/parent")
    remote[7] = snapshot(head="feature/parent", state="MERGED")
    with track.locked_state() as state:
        events, failures = track.refresh(state, list(state["prs"]), 100)
    assert failures == []
    assert [e["kind"] for e in events["github.com/acme/app#8"]] == ["parent-merged"]


def test_dispatch_waits_for_the_burst_to_settle(state_home, remote, dispatched, monkeypatch):
    _track(state_home, URL, remote, 7)
    remote[7] = snapshot(comments=[comment(1, author="alice", bot=False)])
    clock(monkeypatch, 1000, 1000 + track.SETTLE_SECONDS - 1, 1000 + track.SETTLE_SECONDS)
    for _ in range(3):
        track.cmd_poll(POLL)
    assert dispatched == [(KEY, 1000 + track.SETTLE_SECONDS)]


def test_bot_summary_comment_never_dispatches(state_home, remote, dispatched, monkeypatch):
    _track(state_home, URL, remote, 7)
    remote[7] = snapshot(comments=[comment(1, kind="conversation")])
    clock(monkeypatch, 1000, 1000 + 10 * track.SETTLE_SECONDS)
    track.cmd_poll(POLL)
    track.cmd_poll(POLL)
    assert dispatched == []


def test_ci_failing_past_the_attempt_cap_escalates_instead_of_dispatching(state_home, remote, dispatched,
                                                                          monkeypatch):
    _track(state_home, URL, remote, 7)
    with track.locked_state() as state:
        state["prs"][KEY]["ci_attempts"] = track.MAX_CI_ATTEMPTS
    remote[7] = snapshot(ci="FAILURE")
    clock(monkeypatch, 1000, 1000 + 10 * track.SETTLE_SECONDS)
    track.cmd_poll(POLL)
    assert dispatched == []
    assert "CI still fails" in track.load_state()["prs"][KEY]["attention"][0]["reason"]


def test_merged_pr_is_untracked(state_home, remote):
    _track(state_home, URL, remote, 7)
    remote[7] = snapshot(state="MERGED")
    track.cmd_poll(POLL)
    assert track.load_state()["prs"] == {}


def git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    origin = tmp_path / "origin.git"
    work = tmp_path / "work"
    git("init", "--bare", "--initial-branch=main", str(origin), cwd=tmp_path)
    git("clone", str(origin), str(work), cwd=tmp_path)
    for key, value in (("user.name", "t"), ("user.email", "t@t"), ("commit.gpgsign", "false"),
                       ("core.hooksPath", "/dev/null")):
        git("config", key, value, cwd=work)
    (work / "a.py").write_text("x = 1\n")
    git("add", "a.py", cwd=work)
    git("commit", "-m", "init", cwd=work)
    git("push", "-u", "origin", "main", cwd=work)
    git("remote", "set-head", "origin", "main", cwd=work)
    git("switch", "-c", "feature/thing", cwd=work)
    git("push", "-u", "origin", "feature/thing", cwd=work)
    return work


@pytest.fixture
def replies(monkeypatch):
    posted = []
    monkeypatch.setattr(track, "post_reply", lambda pr, event, body, resolve: posted.append(
        (event["author"], body, resolve)))
    return posted


def _ran(state_home, repo, batch, result, **snap):
    """A finished run: tracked PR, prep worktree, the batch it saw and the result it wrote."""
    with track.locked_state() as state:
        state["me"]["github.com"] = "me"
        pr = state["prs"][KEY] = track.parse_url(URL) | {
            "agent": "claude", "worktree": str(repo), "snapshot": track.snapshot_of(snapshot(**snap)),
            "batch": batch, "run": {"pid": 0, "started_at": 0}}
        prep = track.ensure_prep(pr)
        if result is not None:
            track.pr_dir(KEY).mkdir(parents=True, exist_ok=True)
            (track.pr_dir(KEY) / "result.json").write_text(json.dumps(result))
    return prep


def _finalize():
    with track.locked_state() as state:
        outcome = track.finalize(state["prs"][KEY], state, notify_enabled=False)
    return outcome, track.load_state()["prs"][KEY]


def test_finalize_commits_pushes_and_replies_only_to_bots(state_home, repo, replies):
    bot = {"kind": "comment", "ref": "inline:1", "author": "coderabbitai", "bot": True, "source": "inline"}
    human = {"kind": "comment", "ref": "inline:2", "author": "alice", "bot": False, "source": "inline",
             "url": f"{URL}#2"}
    prep = _ran(state_home, repo, [bot, human], {
        "commit": "fix(a): bump x",
        "replies": [{"ref": "inline:1", "body": "Fixed."}, {"ref": "inline:2", "body": "Done."}],
    })
    (prep / "a.py").write_text("x = 2\n")

    outcome, pr = _finalize()
    assert outcome == "pushed"
    assert git("log", "-1", "--format=%s", "origin/feature/thing", cwd=repo) == "fix(a): bump x"
    assert git("show", "origin/feature/thing:a.py", cwd=repo) == "x = 2"
    assert [(author, resolve) for author, _, resolve in replies] == [("coderabbitai", True)]
    assert "on behalf of @me" in replies[0][1]
    assert "Done." in (track.pr_dir(KEY) / "drafts.md").read_text()
    assert not prep.exists()
    assert "attention" not in pr


def test_finalize_replaces_an_invalid_commit_message(state_home, repo, replies):
    prep = _ran(state_home, repo, [{"kind": "ci-failed"}], {"commit": "Fixed stuff."})
    (prep / "a.py").write_text("x = 3\n")
    _finalize()
    assert git("log", "-1", "--format=%s", "origin/feature/thing", cwd=repo).startswith("fix: address review")


def test_finalize_commits_a_resolved_merge_with_the_base(state_home, repo, replies):
    git("switch", "main", cwd=repo)
    (repo / "c.py").write_text("z = 1\n")
    git("add", "c.py", cwd=repo)
    git("commit", "-m", "main moved", cwd=repo)
    git("push", cwd=repo)
    git("switch", "feature/thing", cwd=repo)
    prep = _ran(state_home, repo, [{"kind": "conflict"}], {})
    git("merge", "--no-commit", "--no-ff", "origin/main", cwd=prep)

    outcome, _ = _finalize()
    assert outcome == "pushed"
    assert git("rev-parse", "origin/feature/thing^2", cwd=repo) == git("rev-parse", "origin/main", cwd=repo)


def test_finalize_escalates_judgment_calls_and_requested_changes(state_home, repo, replies):
    _ran(state_home, repo, [{"kind": "changes-requested"}], {"escalate": ["alice wants the module split"]})
    outcome, pr = _finalize()
    assert outcome == "no change"
    assert [a["reason"] for a in pr["attention"]] == ["alice wants the module split", "a reviewer requested changes"]


def test_finalize_without_a_result_escalates(state_home, repo, replies):
    _ran(state_home, repo, [{"kind": "ci-failed"}], None)
    outcome, pr = _finalize()
    assert outcome == "no result"
    assert "without a result" in pr["attention"][0]["reason"]


def test_finalize_never_pushes_the_default_branch(state_home, repo, replies):
    git("push", "origin", "main:develop", cwd=repo)
    prep = _ran(state_home, repo, [{"kind": "ci-failed"}], {"commit": "fix: x"}, head="main", base="develop")
    (prep / "a.py").write_text("x = 4\n")
    outcome, pr = _finalize()
    assert outcome == "stuck"
    assert pr["prepared"] is True
    assert "refusing to push main" in pr["attention"][0]["reason"]
    assert git("show", "origin/main:a.py", cwd=repo) == "x = 1"


def test_take_applies_kept_work_to_the_branch_worktree(state_home, repo):
    with track.locked_state() as state:
        state["prs"][KEY] = track.parse_url(URL) | {
            "agent": "claude", "worktree": str(repo), "snapshot": track.snapshot_of(snapshot())}
        prep = track.ensure_prep(state["prs"][KEY])
        (prep / "a.py").write_text("x = 2\n")
        (prep / "b.py").write_text("y = 1\n")
        state["prs"][KEY]["prepared"] = True

    assert track.cmd_take(type("Args", (), {"ref": "7"})) == track.EXIT_OK
    assert (repo / "a.py").read_text() == "x = 2\n"
    assert (repo / "b.py").read_text() == "y = 1\n"
    assert not prep.exists()
    assert "prepared" not in track.load_state()["prs"][KEY]


def test_take_refuses_a_dirty_target(state_home, repo):
    with track.locked_state() as state:
        state["prs"][KEY] = track.parse_url(URL) | {
            "agent": "claude", "worktree": str(repo), "snapshot": track.snapshot_of(snapshot())}
        track.ensure_prep(state["prs"][KEY])
        state["prs"][KEY]["prepared"] = True
    (repo / "a.py").write_text("local edit\n")
    assert track.cmd_take(type("Args", (), {"ref": "7"})) == track.EXIT_TAKE_REFUSED


def test_events_prints_the_batch_with_bodies(state_home, remote, capsys):
    _track(state_home, URL, remote, 7)
    batch = [{"kind": "comment", "ref": "inline:1", "author": "coderabbitai", "bot": True, "body": "please fix",
              "at": 1}]
    directory = track.pr_dir(KEY)
    directory.mkdir(parents=True)
    (directory / "events.json").write_text(json.dumps(batch))
    track.cmd_events(type("Args", (), {"ref": URL}))
    out = capsys.readouterr().out
    assert "== comment" in out and "please fix" in out and "inline:1" in out


READY = {"ci": "SUCCESS", "merge_state": "CLEAN"}


def _merge_pr(state_home, remote, monkeypatch, merge=True, **snap):
    _track(state_home, URL, remote, 7, **(READY | snap))
    with track.locked_state() as state:
        state["prs"][KEY]["merge"] = merge
    merged = []
    monkeypatch.setitem(track.MERGERS, "github", lambda pr: merged.append(pr["key"]) or "squash")
    return merged


def test_ready_pr_set_to_merge_is_merged_after_it_settles(state_home, remote, monkeypatch):
    merged = _merge_pr(state_home, remote, monkeypatch)
    clock(monkeypatch, 1, 1 + track.SETTLE_SECONDS)
    track.cmd_poll(POLL)
    assert merged == []
    track.cmd_poll(POLL)
    assert merged == [KEY]
    assert track.load_state()["prs"][KEY]["merged_by_tracker"] is True


def test_pr_not_set_to_merge_is_never_merged(state_home, remote, monkeypatch):
    merged = _merge_pr(state_home, remote, monkeypatch, merge=False)
    clock(monkeypatch, 10 * track.SETTLE_SECONDS)
    track.cmd_poll(POLL)
    assert merged == []


@pytest.mark.parametrize(("snap", "blocker"), [
    ({"merge_state": "BLOCKED"}, "merge state BLOCKED"),
    ({"ci": "PENDING"}, "ci PENDING"),
    ({"open_threads": 1}, "unresolved threads"),
    ({"draft": True}, "draft"),
    ({"base": "feature/parent"}, "stacked on a non-default base"),
])
def test_merge_blockers_name_what_is_missing(snap, blocker):
    pr = {"snapshot": track.snapshot_of(snapshot(**(READY | snap))), "quiet_since": 0}
    assert blocker in track.merge_blockers(pr, 10 * track.SETTLE_SECONDS)


def test_pending_work_and_escalations_block_the_merge():
    pr = {"snapshot": track.snapshot_of(snapshot(**READY)), "quiet_since": 0}
    assert track.merge_blockers(pr, 10 * track.SETTLE_SECONDS) == []
    assert "work in progress" in track.merge_blockers(pr | {"pending": [{}]}, 10 * track.SETTLE_SECONDS)
    assert "waiting on the user" in track.merge_blockers(pr | {"attention": [{}]}, 10 * track.SETTLE_SECONDS)


def test_merge_github_pins_the_head_commit_and_the_allowed_method(monkeypatch):
    calls = []
    monkeypatch.setattr(track, "run", lambda cmd, **kw: calls.append(cmd))
    pr = track.parse_url(URL) | {"snapshot": track.snapshot_of(snapshot(merge_methods=["merge", "rebase"]))}
    assert track.merge_github(pr) == "merge"
    assert calls == [["gh", "pr", "merge", URL, "--merge", "--match-head-commit", "abc"]]


def test_failed_merge_escalates_once_per_commit(state_home, remote, monkeypatch):
    _track(state_home, URL, remote, 7, **READY)
    with track.locked_state() as state:
        state["prs"][KEY] |= {"merge": True, "quiet_since": 0}
    attempts = []

    def refuse(pr):
        attempts.append(1)
        raise RuntimeError("base branch policy")

    monkeypatch.setitem(track.MERGERS, "github", refuse)
    monkeypatch.setattr(track.time, "time", lambda: 10 * track.SETTLE_SECONDS)
    track.cmd_poll(POLL)
    with track.locked_state() as state:
        state["prs"][KEY].pop("attention")
    track.cmd_poll(POLL)
    assert len(attempts) == 1


@pytest.mark.parametrize(("state", "message"), [("MERGED", "merged"), ("CLOSED", "closed without merging")])
def test_merge_and_close_notify(state_home, remote, monkeypatch, state, message):
    sent = []
    monkeypatch.setattr(track, "notify", lambda title, text: sent.append(text))
    _track(state_home, URL, remote, 7)
    remote[7] = snapshot(state=state)
    track.cmd_poll(type("Args", (), {"notify": True, "dispatch": True}))
    assert sent == [message]


def test_merge_github_prefers_squash_when_the_repo_allows_it(monkeypatch):
    calls = []
    monkeypatch.setattr(track, "run", lambda cmd, **kw: calls.append(cmd))
    pr = track.parse_url(URL) | {"snapshot": track.snapshot_of(snapshot(merge_methods=["rebase", "merge", "squash"]))}
    assert track.merge_github(pr) == "squash"
    assert "--squash" in calls[0]


@pytest.mark.parametrize(("option", "squash"), [("default_off", True), ("always", True), ("never", False)])
def test_merge_gitlab_squashes_unless_the_project_forbids_it(monkeypatch, option, squash):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        project = {"default_branch": "main", "squash_option": option, "merge_method": "merge"}
        return type("R", (), {"stdout": json.dumps(project)})

    monkeypatch.setattr(track, "run", fake_run)
    pr = track.parse_url("https://gitlab.com/g/p/-/merge_requests/3") | {"snapshot": track.snapshot_of(snapshot())}
    assert track.merge_gitlab(pr) == ("squash" if squash else "merge")
    assert ("squash=true" in calls[-1]) is squash
