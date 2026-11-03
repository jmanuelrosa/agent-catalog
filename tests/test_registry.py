"""The three registries name exactly what ships, in the shape kura reads.

A registry row naming nothing, a shipped artifact no row names, and a `global` flag that
means something other than a boolean all fail the same way: kura installs a different
set than the one the catalog appears to describe, and nothing in the catalog says so.
"""

import json
import re

import pytest
from catalog_tree import (
    AGENTS,
    BUNDLES,
    SKILLS,
    registry,
    skill_entries,
    upstream_name,
    upstream_skill_entries,
    upstream_skills,
)

FULL_SHA = re.compile(r"[0-9a-f]{40}")


def test_every_registered_skill_has_a_directory():
    """A registry row naming nothing is a skill `sync` reports missing and refuses to
    exit 0 over, and a row nobody notices is how that happens."""
    names = [entry["name"] for entry in registry("skill")["local"]]
    names += [name for _, name in upstream_skills()]
    missing = [name for name in names if not (SKILLS / name / "SKILL.md").is_file()]
    assert missing == [], f"registered skills with no SKILL.md: {missing}"


def test_every_bundle_carries_what_kura_refuses_to_install_without():
    """A bundle with no manifest, no agent or no skill is a catalog error kura names.

    These arrived from `plugins/`, where the manifest was `.claude-plugin/plugin.json` and
    nothing read it: Claude Code ignored the keys the catalog cared about, and kura
    never looked. `bundle.json` is read, so a missing one is now a bundle that does not
    exist rather than one that merely looks untagged.
    """
    for bundle in sorted(entry for entry in BUNDLES.iterdir() if entry.is_dir()):
        assert (bundle / "bundle.json").is_file(), bundle.name
        assert list((bundle / "agents").glob("*.md")), bundle.name
        assert list((bundle / "skills").glob("*/SKILL.md")), bundle.name


def test_every_shipped_bundle_has_one_registry_entry():
    bundles = registry("bundle")
    assert bundles["version"] == 3
    names = [entry["name"] for entry in bundles["local"]]
    assert len(names) == len(set(names))
    assert set(names) == {path.name for path in BUNDLES.iterdir() if path.is_dir()}
    for name in names:
        manifest = json.loads((BUNDLES / name / "bundle.json").read_text())
        assert manifest["name"] == name


def test_bundle_groups_are_descriptive_and_project_scoped():
    unsupported = {"global", "dependencies", "dependency_only"}
    for entry in registry("bundle")["local"]:
        assert not unsupported.intersection(entry), entry["name"]
        groups = entry["groups"]
        assert isinstance(groups, list) and groups, entry["name"]
        assert all(isinstance(group, str) and group for group in groups), entry["name"]
        assert len(groups) == len(set(groups)), entry["name"]
        assert "global" not in groups, entry["name"]
        manifest = json.loads((BUNDLES / entry["name"] / "bundle.json").read_text())
        assert "groups" not in manifest, entry["name"]
        assert "global" not in manifest, entry["name"]


def test_standalone_agents_are_registered_and_global():
    agents = registry("agent")
    assert set(agents) == {"$schema", "version", "upstream", "local"}
    assert agents["version"] == 3
    registered = {entry["name"] for entry in agents["local"]}
    shipped = {path.stem for path in AGENTS.glob("*.md")}
    assert registered == shipped
    assert all(entry["global"] is True for entry in agents["local"])


@pytest.mark.parametrize(("kind", "collection"), [("skill", "skills"), ("agent", "agents")])
def test_global_root_policy_is_boolean_and_separate_from_groups(kind, collection):
    entries = registry(kind)["local"] + [
        entry for repo in registry(kind)["upstream"].values() for entry in repo[collection]
    ]
    for entry in entries:
        assert type(entry.get("global", False)) is bool, entry
        assert "global" not in entry.get("groups", []), entry


@pytest.mark.parametrize("artifact_type", ["agent", "bundle"])
def test_agent_and_bundle_schemas_match_the_skill_registry(artifact_type):
    assert registry(artifact_type)["$schema"] == registry("skill")["$schema"].replace(
        "skill-registry.schema.json", f"{artifact_type}-registry.schema.json"
    )


def test_every_upstream_names_a_branch_and_a_full_sha_commit():
    """kura fetches the pinned commit, and drift tooling compares it against the tip of the
    branch. An upstream missing either is one nothing can update or audit."""
    unpinned = [
        repo
        for repo, source in registry("skill")["upstream"].items()
        if not source.get("branch") or not FULL_SHA.fullmatch(source.get("commit") or "")
    ]
    assert unpinned == [], f"upstreams with no branch or no full-SHA commit: {unpinned}"


def test_to_plan_dependencies_have_registered_sources():
    entries = skill_entries()
    assert entries["to-plan"]["dependencies"] == ["research", "grilling"]

    pending = list(entries["to-plan"]["dependencies"])
    visited = set()
    while pending:
        name = pending.pop()
        if name in visited:
            continue
        visited.add(name)
        assert name in entries, f"unregistered dependency: {name}"
        assert (SKILLS / name / "SKILL.md").is_file(), f"missing dependency: {name}"
        pending.extend(entries[name].get("dependencies", []))


def test_teammate_dependencies_are_installed_dependency_only_skills():
    """teammate reads its dependencies by path, so each must ship beside it and stay hidden."""
    upstream = {upstream_name(entry): entry for _, entry in upstream_skill_entries()}
    teammate = next(entry for entry in registry("skill")["local"] if entry["name"] == "teammate")
    for name in teammate["dependencies"]:
        assert (SKILLS / name / "SKILL.md").is_file(), f"missing dependency: {name}"
        if name in {"how", "why", "teach", "domain-modeling"}:
            assert upstream[name].get("dependency_only") is True, name


def test_the_global_set_holds_exactly_the_documented_membership():
    """Registry root policy changes the global set even while sync is disabled."""
    global_roots = {entry["name"] for entry in registry("skill")["local"] if entry.get("global", False)}
    global_roots.update(
        upstream_name(entry) for _, entry in upstream_skill_entries() if entry.get("global", False)
    )
    assert global_roots == {
        "ac",
        "agent-audit",
        "agent-writer",
        "setup-review",
        "setup-review-mechanics",
        "ship",
        "cc-fewer-permission-prompts",
        "cloudflare",
        "coderabbit",
        "commit",
        "diagram",
        "documentation-and-adrs",
        "feature-team",
        "grill-me",
        "grill-with-docs",
        "handoff",
        "humanizer",
        "planning-and-task-breakdown",
        "pr",
        "product-lead",
        "research",
        "review-mechanics",
        "skill-writer",
        "teammate",
        "to-plan",
        "to-rfc",
        "triage",
        "watch",
    }
