"""The staff-engineer seats split into advisors and implementers, and architect routes to every implementer."""

from catalog_tree import AGENTS, seat_agents


def test_implementer_seats_are_the_ones_without_a_tools_allowlist():
    """The advisor/implementer split is readable from frontmatter alone.

    `tools:` is what makes a seat read-only, and a read-only seat owns no slice. Pinned
    so the next advisor seat is a deliberate addition here rather than a silent
    disappearance from architect's routing.
    """
    advisors = {p.stem for p, fm in seat_agents() if "tools" in fm}
    assert advisors == {"security-staff-engineer"}


def test_architect_routes_to_every_implementer_seat():
    """A seat architect never names is a seat it never assigns work to.

    This list rotted from twelve seats to seven without anyone noticing: design,
    mobile, desktop, dx and gtm each shipped without reaching architect.md, so
    architect silently defaulted their work to the frontend and backend seats. The
    symptom was invisible, because defaulting is indistinguishable from routing.
    """
    routing = (AGENTS / "architect.md").read_text()
    missing = sorted(
        path.stem
        for path, fm in seat_agents()
        if "tools" not in fm and path.stem.removesuffix("-staff-engineer") not in routing
    )
    assert missing == [], (
        f"seats absent from architect.md's enumeration: {', '.join(missing)}. "
        f"Architect cannot assign a slice to a seat it does not name."
    )
