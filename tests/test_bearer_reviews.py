import hashlib
import json

import pytest
import yaml
from catalog_tree import ROOT

REVIEWS = json.loads((ROOT / "docs/bearer-review.json").read_text())
IGNORED = json.loads((ROOT / "bearer.ignore").read_text())


@pytest.mark.parametrize("path", sorted(REVIEWS["files"]))
def test_excepted_source_has_not_changed_since_review(path):
    expected = REVIEWS["files"][path]["sha256"]
    actual = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
    assert actual == expected, f"{path} changed; re-triage its Bearer exceptions"


def test_every_exception_has_one_reviewed_source():
    fingerprints = [
        fingerprint
        for source in REVIEWS["files"].values()
        for fingerprint in source["fingerprints"]
    ]
    assert fingerprints
    assert len(fingerprints) == len(set(fingerprints))
    assert set(fingerprints) == set(IGNORED)


def test_every_exception_records_its_source_and_reason():
    for path, source in REVIEWS["files"].items():
        assert source["fingerprints"], path
        for fingerprint in source["fingerprints"]:
            entry = IGNORED[fingerprint]
            assert entry["false_positive"] is True, fingerprint
            assert entry["comment"].startswith(f"{path}:"), fingerprint


def test_bearer_keeps_its_reviewed_version_and_failure_gate():
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    job = workflow["jobs"]["sast"]
    step = next(step for step in job["steps"] if step.get("name") == "Run Bearer")
    assert step["with"]["version"] == REVIEWS["bearer_version"]
    assert not job.get("continue-on-error")
    assert not step.get("continue-on-error")
    bypasses = {"only-rule", "skip-rule", "skip-path", "exclude-fingerprint", "exit-code"}
    assert not bypasses.intersection(step["with"])
