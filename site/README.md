# Agent Catalog site

The landing page and docs for the catalog, built with Astro.
Skill, agent, bundle and attribution data is read from the catalog's registries at build time, so the site never lists something the catalog does not contain.

```fish
bun install
bun run dev
bun run build
```

The catalog root defaults to the parent directory.
Set `CATALOG_ROOT` to build against another checkout, for example one that carries `licenses.json`:

```fish
set -x CATALOG_ROOT ~/Developer/agent-catalog
bun run build
```

`dist/` is a static site and deploys to any static host.
