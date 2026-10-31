"""The output vocabulary the catalog's own scripts print through.

`ui` and `colors` are vendored from the dotkit repository and pinned in the root
`dotkit.json`, so the catalog runs on a machine that has no dotfiles checkout. Change
them in dotkit and re-vendor: tests/test_catalog.py rejects an edit made to the copy.
Each script reaches this package through a committed `dotkit` symlink beside its
executable.

Stdlib-only, with no exemption. These modules are imported by skill scripts that may
run with nothing but `python3`.
"""
