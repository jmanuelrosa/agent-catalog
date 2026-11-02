"""The registry half of the code-review policy: its mechanics reach every machine, and its rival does not.

The policy itself is resident in each consumer's harness, and its deferred half is the
`review-mechanics` skill shipped here. Both claims below are about what kura installs,
which this catalog decides.
"""

from catalog_tree import SKILLS, registry, upstream_name, upstream_skill_entries

MECHANICS = SKILLS / "review-mechanics" / "SKILL.md"

# A reviewer whose axes are a subset of the policy's and whose severity scale is one of the
# four the policy collapsed. It is upstream, so its body cannot be fixed; dropping `review`
# from its groups is what stops `scout` and `--group review` offering it as a reviewer, and
# that only works while kura leaves hand-maintained groups alone.
SUPERSEDED = "code-review-and-quality"


def test_the_mechanics_skill_is_a_global_root():
    """Without global root policy it never links, so the stub points at nothing.

    `kura sync` derives the user-scope set from the `global` flag, and prunes anything
    in that tree it cannot derive.
    """
    entries = [skill for skill in registry("skill")["local"] if skill["name"] == "review-mechanics"]
    assert len(entries) == 1, f"expected one local entry, found {len(entries)}"
    assert entries[0]["global"] is True, (
        "`review-mechanics` is not a global root, so it never reaches ~/.claude/skills"
    )


def test_the_superseded_reviewer_is_named_and_untagged():
    """Three halves of one claim, and the third is the one that can rot silently.

    Its body is upstream and unfixable, so the policy states precedence and the registry
    stops advertising it as a reviewer. `registry.stamp_entry` writes only `updated_at`,
    which is what makes a hand-maintained `groups` survive `kura update`; if that ever
    changes, `review` comes back and this fails.
    """
    assert SUPERSEDED in MECHANICS.read_text(), (
        "the mechanics skill stopped naming the rival reviewer"
    )
    assert (SKILLS / SUPERSEDED / "SKILL.md").is_file()

    entries = [entry for _, entry in upstream_skill_entries() if upstream_name(entry) == SUPERSEDED]
    assert len(entries) == 1, f"expected one tracked entry, found {len(entries)}"
    assert "review" not in entries[0]["groups"], (
        f"`{SUPERSEDED}` is tagged `review` again, so scout offers it as a reviewer"
    )
