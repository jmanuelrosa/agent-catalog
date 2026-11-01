"""The catalog is consistent with its registries, its licenses and its own README."""

import configparser
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
REGISTRY_KINDS = ("skill", "agent", "bundle")


def registry(kind):
    return json.loads((ROOT / f"{kind}-registry.json").read_text())


def upstream_name(entry):
    """The directory kura installs an upstream entry under: its `name`, else the
    basename of `upstream_path`. A repo-root skill (`upstream_path: "."`) carries a name."""
    return entry.get("name") or entry["upstream_path"].rstrip("/").rsplit("/", 1)[-1]


def upstream_skills():
    for repo, source in registry("skill")["upstream"].items():
        for entry in source["skills"]:
            yield repo.rstrip("/"), upstream_name(entry)


def licenses():
    return json.loads((ROOT / "licenses.json").read_text())


def test_kuras_inputs_are_present():
    for kind in REGISTRY_KINDS:
        assert (ROOT / f"{kind}-registry.json").is_file(), kind
        assert (ROOT / f"{kind}s").is_dir(), kind


def test_every_registered_skill_has_a_directory():
    names = [entry["name"] for entry in registry("skill")["local"]]
    names += [name for _, name in upstream_skills()]
    missing = [name for name in names if not (ROOT / "skills" / name / "SKILL.md").is_file()]
    assert missing == []


def test_every_registered_agent_and_bundle_has_a_source():
    missing = [
        entry["name"] for entry in registry("agent")["local"]
        if not (ROOT / "agents" / f"{entry['name']}.md").is_file()
    ]
    missing += [
        entry["name"] for entry in registry("bundle")["local"]
        if not (ROOT / "bundles" / entry["name"] / "bundle.json").is_file()
    ]
    assert missing == []


def test_every_seat_bundle_says_what_it_is_not_for():
    seats = [
        path.parent.parent.name
        for path in (ROOT / "bundles").glob("*/agents/*-staff-engineer.md")
    ]
    unclear = [
        name for name in seats
        if json.loads((ROOT / "bundles" / name / "bundle.json").read_text())["description"].count("Not for:") != 1
    ]
    assert seats and unclear == []


def test_every_upstream_source_has_a_license_entry():
    recorded = licenses()["upstream"]
    sources = {repo for repo, _ in upstream_skills()}
    assert sorted(sources - recorded.keys()) == [], "add these to licenses.json"
    assert sorted(recorded.keys() - sources) == [], "these licenses.json entries no longer ship"


def test_a_source_without_a_license_file_says_why():
    for repo, info in licenses()["upstream"].items():
        if not info.get("file"):
            assert info.get("note"), f"{repo} has no license file and no note explaining it"


def test_every_license_file_exists_and_is_referenced():
    recorded = licenses()["upstream"].values()
    referenced = {info[key] for info in recorded for key in ("file", "notice") if info.get(key)}
    on_disk = {str(path.relative_to(ROOT)) for path in (ROOT / "LICENSES").iterdir()}
    assert sorted(referenced - on_disk) == [], "referenced but missing"
    assert sorted(on_disk - referenced) == [], "in LICENSES/ but not in licenses.json"


def test_the_readme_attribution_table_is_current():
    result = subprocess.run(
        [sys.executable, str(ROOT / "bin" / "attribution"), "--check"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr


def dotkit_links():
    return sorted(path for path in ROOT.glob("**/dotkit") if path.is_symlink())


def test_every_dotkit_link_resolves_to_the_catalog_copy():
    """A clone with core.symlinks=false materialises a symlink as a file holding its
    target, and the failure is an ImportError deep in a skill script. Relative targets,
    so the link survives any clone location and the harness symlink in front of it."""
    real = ROOT / "lib" / "python" / "dotkit"
    links = dotkit_links()
    assert links, "no dotkit symlink found"
    for link in links:
        assert not link.readlink().is_absolute(), f"{link.relative_to(ROOT)} must be relative"
        assert link.resolve() == real.resolve(), f"{link.relative_to(ROOT)} -> {link.resolve()}"


DOTKIT_LOCK = json.loads((ROOT / "dotkit.json").read_text())


@pytest.mark.parametrize("name", sorted(DOTKIT_LOCK["files"]))
def test_the_vendored_dotkit_copy_is_unedited(name):
    """ui.py and colors.py are copies from the dotkit repository. Change them there and
    run its `bin/dotkit-vendor` against this checkout, so every consumer gets the edit."""
    copy = ROOT / DOTKIT_LOCK["target"] / name
    actual = hashlib.sha256(copy.read_bytes()).hexdigest()
    assert actual == DOTKIT_LOCK["files"][name], f"{copy.relative_to(ROOT)} differs from dotkit {DOTKIT_LOCK['rev'][:12]}"


def suite_roots():
    parser = configparser.ConfigParser()
    parser.read(ROOT / "pytest.ini")
    return [line for line in parser["pytest"]["testpaths"].split() if line]


def is_upstream(path):
    relative = path.relative_to(ROOT)
    upstream = {Path("skills") / name for _, name in upstream_skills()}
    return any(prefix == relative or prefix in relative.parents for prefix in upstream)


@pytest.mark.parametrize("root", suite_roots())
def test_every_listed_suite_exists(root):
    assert (ROOT / root).is_dir(), root


def test_no_suite_written_here_is_missing_from_pytest_ini():
    listed = {ROOT / root for root in suite_roots()}
    found = {
        path.parent for path in ROOT.glob("**/tests/test_*.py")
        if not is_upstream(path) and ".git" not in path.parts
    }
    assert sorted(str(p.relative_to(ROOT)) for p in found - listed) == []
