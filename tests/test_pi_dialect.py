"""The frontmatter that lets Claude Code and Pi run the same agents and skills.

Two harnesses read one catalog, and each reads its own frontmatter dialect while
ignoring the other's. Claude Code reads `effort:` and `disallowedTools:`; Pi's
pi-subagents extension reads `thinking:` and `disallowed_tools:`. Nothing enforces
agreement at load time in either harness, so equality here is the guard.
"""

import re

import pytest
from catalog_tree import (
    AGENTS,
    agent_files,
    frontmatter,
    frontmatter_block,
    skill_files,
)

# Claude's key first, pi's second. One row per fact the two harnesses must agree on.
DUAL_KEYS = (("effort", "thinking"), ("disallowedTools", "disallowed_tools"))


def dual_keyed():
    """Every agent that pins a depth for Claude, which must pin the same one for pi.

    The invariant is `effort:`, not a filename: an agent carrying Claude's key and
    not pi's runs at two different depths depending on who spawned it. So the set is
    derived from the frontmatter rather than from a glob, because a glob is a guess
    about where such agents live and it was wrong twice over. `*-staff-engineer.md`
    missed the seven product-team agents, and a `tools:` filter then dropped them
    again along with the security advisor.

    That filter was the subtler half. `tools:` is a same-key dialect collision, both
    harnesses read that name and the values are Claude tool names, so an agent
    carrying one stays Claude-only for *tool* purposes. That says nothing about its
    depth pin, and using it to skip the effort check silenced eight files that could
    carry `thinking:` today. The two concerns are independent, so `tools_unbridged`
    records the collision separately and no longer suppresses anything.
    """
    for path in agent_files():
        if "effort" in frontmatter(path):
            yield path


def tools_unbridged():
    """The agents whose `tools:` allowlist is Claude-only, listed rather than inferred.

    Read-only advisors and the product-team bench. Their values are Claude tool names,
    which pi would misread, so the key is not bridged. Naming them keeps the exemption
    visible instead of hiding it in a predicate that also governs the depth pin.
    """
    return sorted(path for path in agent_files() if "tools" in frontmatter(path))


# --- the agent dialect --------------------------------------------------------


@pytest.mark.parametrize("path", list(dual_keyed()), ids=lambda p: p.name)
def test_every_agent_pinning_a_depth_carries_both_keys_equal(path):
    """`effort:` is Claude's dial and `thinking:` is pi's, and each harness ignores
    the other's key. A seat carrying only one runs at the pinned depth under one
    harness and at the session default under the other, which is exactly the drift
    the pins in the seat anatomy exist to prevent."""
    fm = frontmatter(path)
    assert "effort" in fm, f"{path.name} lost its Claude effort pin"
    assert "thinking" in fm, f"{path.name} carries no pi counterpart for effort"
    assert fm["effort"] == fm["thinking"], (
        f"{path.name} pins effort={fm['effort']} but thinking={fm['thinking']}, "
        "so the two harnesses run this seat at different depths"
    )


def test_every_agent_pinning_effort_is_in_the_dual_keyed_set():
    """The parametrize above passes vacuously if the set stops matching anything.

    Stated as an identity against the whole agent population rather than as a floor,
    so a file that gains `effort:` is covered the moment it does, and one that loses
    it drops out without anybody editing a number here.
    """
    found = set(dual_keyed())
    expected = {path for path in agent_files() if "effort" in frontmatter(path)}
    assert found == expected
    assert len(found) >= 22, (
        f"expected the architect, ux-shaper, the 15 seats and the product-team bench, "
        f"found {len(found)}"
    )


def test_the_unbridged_tools_exemption_does_not_hide_a_depth_pin():
    """The regression this module missed for as long as it globbed on a filename.

    Every agent carrying `tools:` is Claude-only for tools and still obliged to pin
    both depth keys, so the two sets are allowed to overlap freely. Asserting the
    overlap is non-empty is what proves the exemption no longer excuses a missing
    `thinking:`.
    """
    unbridged = set(tools_unbridged())
    assert unbridged, "no agent carries tools:, so this exemption is stale"
    assert unbridged & set(dual_keyed()), (
        "every tools:-carrying agent dropped out of the depth check, which is the "
        "exact hole that let eight agents run at pi's session default"
    )


@pytest.mark.parametrize("path", list(agent_files()), ids=lambda p: p.name)
def test_the_two_dialects_never_disagree_where_both_are_spoken(path):
    """Wherever an agent carries both keys of a pair, the values are equal.

    Equality only, not presence: `disallowedTools:` is carried by two agents and
    required of none, and presence of the depth pair is the first test's business.
    What no file may do is answer the same question differently per harness."""
    fm = frontmatter(path)
    for claude_key, pi_key in DUAL_KEYS:
        if claude_key in fm and pi_key in fm:
            assert fm[claude_key] == fm[pi_key], (
                f"{path.name}: {claude_key}={fm[claude_key]} but {pi_key}={fm[pi_key]}"
            )


@pytest.mark.parametrize("path", list(agent_files()), ids=lambda p: p.name)
def test_a_disallow_in_one_dialect_is_a_disallow_in_both(path):
    """Both directions, unlike the effort pair: a constraint is not a preference.

    `disallowedTools:` without `disallowed_tools:` means pi ignores a ban Claude
    enforces (architect's Agent ban is load-bearing: orchestration stays with the
    caller), and the reverse means Claude does. There is no agent for which one
    harness should enforce what the other waives."""
    fm = frontmatter(path)
    claude_key, pi_key = "disallowedTools", "disallowed_tools"
    if claude_key in fm or pi_key in fm:
        assert claude_key in fm and pi_key in fm, (
            f"{path.name} carries {claude_key if claude_key in fm else pi_key}: "
            "without its counterpart, so one harness silently ignores the ban"
        )


def test_architect_bans_the_agent_tool_in_both_dialects():
    """The one place the disallow pair is load-bearing today: orchestration stays
    with the caller under either harness."""
    fm = frontmatter(AGENTS / "architect.md")
    assert fm["disallowedTools"] == "Agent"
    assert fm["disallowed_tools"] == "Agent"


# --- the keys pi ignores on a skill -------------------------------------------
#
# Agents are dual-keyed above because pi-subagents reads agent frontmatter. pi's own skill
# loader (dist/core/skills.js in 0.84.x) reads exactly three fields from a SKILL.md,
# `name`, `description` and `disable-model-invocation`, and drops the rest. An extension
# may read the file itself though, which is how `model:` came to mean one thing in both
# harnesses rather than two: the dotfiles repository's pi/extensions/skill-model/index.ts
# parses the frontmatter, resolves the value against the session's scoped catalogue and
# pins it for one agent run, which is the boundary Claude Code uses as well. That is why
# `model:` is not in the tuple.
#
# `allowed-tools:` and `effort:` still are Claude-only, silently. The
# consequence worth stating is the first one: a skill Claude Code restricts to a handful
# of tools runs with pi's full tool set. Enforcing it in the harness was considered and
# rejected, because the values are Claude permission specifiers with argument patterns
# (`Bash(git status *)`), so 17 of the 20 skills that carry the key qualify their Bash;
# a tool-name-level gate would have allowed an unrestricted shell for those 17 while
# reading like enforcement. What covers that surface instead is pi-sandbox, configured
# from the same Claude settings (see the dotfiles repository's test_pi_sandbox.py), which
# confines what any command may touch rather than which skill may run it.
#
# The set is frozen so the limitation cannot quietly widen. A skill added here is a
# decision to make, not a line to update: either the restriction does not matter under
# pi, or the surface it guards belongs in the sandbox config. Dropping `model:` from the
# tuple left the set itself unchanged, because every skill that declares a model also
# carries `allowed-tools:` or `effort:`.
#
# `cloudflare` took the first branch. Its `allowed-tools` lists only read-only commands
# and omits every mutating one, so what Claude gets from the key is a skipped prompt on
# the safe calls, not a gate on the dangerous ones. Under pi the writes prompt like any
# other command, which is the same outcome the key buys under Claude. The sandbox is not
# the answer for the rest of that surface either: a Cloudflare write leaves over the
# network and touches no path pi-sandbox can confine. What protects the account is
# `cf`'s own confirmation prompt on destructive commands plus the skill's "Before any
# write" section, which both harnesses read as prose.
#
# `sentry` took the first branch for the same reason. Its `allowed-tools` lists only the
# read subcommands, so resolve, archive, merge and `sentry api` writes prompt under both
# harnesses, and its "Writes change shared state" section is the guard both read.
#
# `teammate` took the first branch for `hooks:`. Its hook asks before any Write, Edit or
# NotebookEdit outside a `.teammate/` store, a second line behind the skill's read-only
# instructions. Under pi that line is gone: a file-tool write inside cwd goes through
# unprompted, so the instructions alone keep it read-only there, and outside cwd pi-sandbox
# prompts the same way the hook would.

SKILL_KEYS_PI_IGNORES = ("allowed-tools", "effort", "hooks")

CLAUDE_ONLY_SKILL_FRONTMATTER = {
    "ac", "agent-writer", "cloudflare", "coderabbit", "commit", "jira",
    "pr", "product-lead", "research", "sentry", "setup-review", "ship", "teammate",
    "0-refine-idea", "1-research", "2-write-prd", "3-red-team", "4-tech-shape",
    "5-decompose", "6-verify", "7-push-to-board", "8-living-spec", "setup-strategy",
    "agent-platform-alert-configuration", "cloud-run-alert-configuration", "aws-containers",
}


def skills_with_claude_only_keys():
    found = set()
    for path in skill_files():
        block = frontmatter_block(path)
        if block is None:
            continue
        if any(re.search(rf"^{key}:", block, re.MULTILINE) for key in SKILL_KEYS_PI_IGNORES):
            found.add(path.parent.name)
    return found


def test_the_set_of_skills_pi_reads_differently_has_not_widened():
    """A frozen set, because the drift is silent in both directions.

    pi reports nothing when it ignores a key, and Claude reports nothing when a skill
    gains one, so neither harness would ever mention that a new skill joined this list.
    """
    assert skills_with_claude_only_keys() == CLAUDE_ONLY_SKILL_FRONTMATTER


def test_no_skill_pretends_to_speak_pis_dialect():
    """`thinking:` on a SKILL.md would read as a pin pi honours, and pi reads no such key.

    `model:` is shared rather than dual-keyed, so a second key beside it is theatre, and
    the mistake worth catching is someone copying the agent convention one directory over.
    """
    for path in skill_files():
        block = frontmatter_block(path)
        if block is None:
            continue
        assert not re.search(r"^thinking:", block, re.MULTILINE), (
            f"{path.parent.name}/SKILL.md carries `thinking:`, which pi's skill loader "
            f"never reads; only agent frontmatter is dual-keyed"
        )
