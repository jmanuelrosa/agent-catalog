"""Every shipped artifact loads, and no vendored skill pre-approves a shell."""

import yaml
from catalog_tree import (
    AGENTS,
    BUNDLES,
    ROOT,
    SKILLS,
    frontmatter_block,
    upstream_skill_dirs,
)


def artifact_files():
    """Skills, standalone agents and bundle-owned artifacts all need valid frontmatter."""
    return sorted({
        *SKILLS.rglob("SKILL.md"),
        *AGENTS.glob("*.md"),
        *BUNDLES.rglob("SKILL.md"),
        *BUNDLES.glob("*/agents/*.md"),
    })


def test_every_artifact_ships_frontmatter_a_yaml_parser_accepts():
    """The failure this exists for is lexical and silent: an unquoted ": " in a plain
    value reads as a mapping where none is allowed, so the block fails whole and the
    artifact does not load, with no error anywhere.

    PyYAML is the oracle. kura's scanner is the thing that has to agree with it, and
    that contract is asserted in kura's own suite; this asserts the corpus.
    """
    offenders = []
    for path in artifact_files():
        block = frontmatter_block(path)
        if block is None:
            offenders.append(f"{path.relative_to(ROOT)}: no frontmatter block")
            continue
        try:
            parsed = yaml.safe_load(block)
        except yaml.YAMLError as error:
            offenders.append(f"{path.relative_to(ROOT)}: {error.__class__.__name__}")
            continue
        if not isinstance(parsed, dict) or "name" not in parsed:
            offenders.append(f"{path.relative_to(ROOT)}: declares no name")
    assert offenders == [], "\n".join(offenders)


def test_no_upstream_skill_grants_itself_bash():
    """In Claude Code `allowed-tools` runs the listed tools without a prompt for the
    turn, so a vendored skill naming Bash pre-approves commands nobody here reviewed.
    `kura update` replaces an upstream tree wholesale, which is how a stripped line
    comes back."""
    offenders = []
    for skill in upstream_skill_dirs():
        block = frontmatter_block(skill / "SKILL.md")
        granted = (yaml.safe_load(block) if block else {}).get("allowed-tools") or []
        if "Bash" in " ".join(map(str, granted if isinstance(granted, list) else [granted])):
            offenders.append(skill.name)
    assert offenders == [], (
        f"upstream skills granting themselves Bash: {', '.join(offenders)}. "
        "Upstream reintroduced the line; strip `allowed-tools` from the frontmatter "
        "again after `kura update`."
    )
