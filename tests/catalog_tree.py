"""Where the catalog's trees are, and how its registries and frontmatter are read.

Shared by every module in this suite. The name is deliberately one no other suite
directory could also claim: in pytest's prepend import mode a bare module name binds to
whichever directory reached `sys.path` first, and that fails silently when the two
copies happen to agree.
"""

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
AGENTS = ROOT / "agents"
BUNDLES = ROOT / "bundles"
REGISTRY_KINDS = ("skill", "agent", "bundle")


def registry(kind):
    return json.loads((ROOT / f"{kind}-registry.json").read_text())


def upstream_name(entry):
    """The directory kura installs an upstream entry under: its `name`, else the
    basename of `upstream_path`. A repo-root skill (`upstream_path: "."`) carries a name."""
    return entry.get("name") or entry["upstream_path"].rstrip("/").rsplit("/", 1)[-1]


def upstream_skill_entries():
    for repo, source in registry("skill")["upstream"].items():
        for entry in source["skills"]:
            yield repo.rstrip("/"), entry


def upstream_skills():
    for repo, entry in upstream_skill_entries():
        yield repo, upstream_name(entry)


def upstream_skill_dirs():
    for _, name in upstream_skills():
        yield SKILLS / name


def skill_entries():
    """Every registered skill, local and upstream, keyed by the name kura installs it under."""
    entries = {entry["name"]: entry for entry in registry("skill")["local"]}
    entries.update((upstream_name(entry), entry) for _, entry in upstream_skill_entries())
    return entries


def frontmatter_block(path):
    """The raw frontmatter text, or None when the file opens without one."""
    text = path.read_text()
    if not text.startswith("---\n"):
        return None
    return text.split("---\n", 2)[1]


def frontmatter(path):
    """The frontmatter, parsed. PyYAML is the oracle here as everywhere in this suite."""
    block = frontmatter_block(path)
    assert block is not None, f"{path.name} has no frontmatter block"
    return yaml.safe_load(block)


def agent_files():
    """Every agent definition either harness could load: registry agents and seat agents."""
    yield from sorted(AGENTS.glob("*.md"))
    yield from sorted(BUNDLES.glob("*/agents/*.md"))


def skill_files():
    """Every SKILL.md either harness could load, standalone and bundle-owned."""
    yield from sorted(SKILLS.glob("*/SKILL.md"))
    yield from sorted(BUNDLES.glob("*/skills/*/SKILL.md"))


def seat_agents():
    """Every staff-engineer agent shipped by a bundle, with its frontmatter."""
    for path in sorted(BUNDLES.glob("*/agents/*-staff-engineer.md")):
        block = frontmatter_block(path)
        yield path, (yaml.safe_load(block) if block else {})
