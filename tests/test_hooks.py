"""Local hooks reuse the CI gates without configuring the developer's clone."""

import os
import shutil
import subprocess

import pytest
from catalog_tree import ROOT


@pytest.fixture
def repo(tmp_path, monkeypatch):
    # Ignore machine-level hook settings and inherited Git/Make invocation state.
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "MAKEFLAGS", "MFLAGS"):
        monkeypatch.delenv(name, raising=False)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    shutil.copy2(ROOT / "Makefile", tmp_path / "Makefile")
    return tmp_path


@pytest.mark.parametrize("failed_target", [None, "test", "lint"])
def test_prepush_runs_existing_gates_and_propagates_failure(repo, failed_target):
    # Override only the gate recipes: no real tests, linters, or downloads here.
    gates = repo / "gates.mk"
    gates.write_text("".join(
        f"{target}:\n\t@echo {target}\n\t@exit {23 if failed_target == target else 0}\n"
        for target in ("test", "lint")
    ))
    (repo / "prepush").touch()  # A same-named file must not disable the gate.
    result = subprocess.run(
        ["make", "--no-print-directory", "-f", "Makefile", "-f", "gates.mk", "prepush"],
        cwd=repo, capture_output=True, text=True,
    )
    assert (result.returncode == 0) == (failed_target is None), result.stderr
    assert result.stdout.splitlines() == (["test"] if failed_target == "test" else ["test", "lint"])
    if failed_target:
        assert failed_target in result.stderr


def test_hooks_setup_is_local_and_idempotent(repo):
    (repo / "hooks").touch()
    for _ in range(2):
        result = subprocess.run(
            ["make", "--no-print-directory", "hooks"],
            cwd=repo, capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
    configured = subprocess.run(
        ["git", "config", "--local", "--get-all", "core.hooksPath"],
        cwd=repo, capture_output=True, text=True, check=True,
    )
    assert configured.stdout.splitlines() == [".githooks"]


@pytest.mark.parametrize("status", [0, 23])
def test_executable_hook_dispatches_make_and_preserves_failure(repo, monkeypatch, status):
    hook = ROOT / ".githooks" / "pre-push"
    assert os.access(hook, os.X_OK), "pre-push must be executable in the checkout"
    (repo / ".githooks").mkdir()
    shutil.copy2(hook, repo / ".githooks" / "pre-push")
    subprocess.run(["make", "--no-print-directory", "hooks"], cwd=repo, check=True)
    stub_bin = repo / "bin"
    stub_bin.mkdir()
    stub_make = stub_bin / "make"
    stub_make.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$HOOK_LOG"\nexit "$HOOK_STATUS"\n')
    stub_make.chmod(0o755)
    log = repo / "make-args"
    monkeypatch.setenv("PATH", f"{stub_bin}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("HOOK_LOG", str(log))
    monkeypatch.setenv("HOOK_STATUS", str(status))

    direct = subprocess.run([str(repo / ".githooks" / "pre-push")], cwd=repo)
    assert direct.returncode == status
    assert log.read_text().splitlines() == ["--no-print-directory", "prepush"]
    log.unlink()
    # Exercise Git's real dispatch without pushing or contacting a remote.
    dispatched = subprocess.run(
        ["git", "hook", "run", "pre-push", "--", "origin", "unused"],
        cwd=repo, capture_output=True, text=True,
    )
    assert (dispatched.returncode == 0) == (status == 0), dispatched.stderr
    assert log.read_text().splitlines() == ["--no-print-directory", "prepush"]
