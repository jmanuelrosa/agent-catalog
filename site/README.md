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

## Deploy

`.github/workflows/site.yml` deploys the site to the `agent-catalog` Cloudflare Worker whenever a merge to `main` changes a site input: anything under `site/`, a catalog file that `src/lib/catalog.ts` reads, or the workflow itself.
A pull request that changes a site input gets a build check and never deploys.
Both jobs run on the Node major in `.node-version`, and wrangler runs at the exact `WRANGLER_VERSION` set in the workflow, which Dependabot does not bump.

Redeploy `main` by hand, for example after a failed run or to pick up a catalog change the paths filter missed:

```fish
gh workflow run site.yml --ref main
```

A dispatch from any other branch builds the site without deploying it.
To roll back, re-run the last good run from the Actions tab, or run `wrangler rollback` from this directory.
A change to `routes` in `wrangler.jsonc` fails the CI deploy, because the token cannot edit routes; deploy that one change by hand with `wrangler deploy`.
Any other manual deploy is overwritten by the next CI deploy.

### One-time setup

The deploy reads two values from the `production` GitHub environment: the `CLOUDFLARE_API_TOKEN` secret and the `CLOUDFLARE_ACCOUNT_ID` variable.
`wrangler.jsonc` carries no `account_id`, so a local `wrangler deploy` uses the account of your `wrangler login`, or `CLOUDFLARE_ACCOUNT_ID` from your shell when the login spans several accounts.

1. In the Cloudflare dashboard, create a custom API token named `github-actions-agent-catalog-site` with only Account, Workers Scripts, Edit, on the account that owns the `agent-catalog` Worker (narrowed to the `agent-catalog` Worker if the form offers it), no zone resources, and an end date 12 months out.
2. Create the `production` environment with deployment branches limited to `main` and no required reviewers:

   ```fish
   echo '{"deployment_branch_policy":{"protected_branches":false,"custom_branch_policies":true}}' | gh api -X PUT 'repos/{owner}/{repo}/environments/production' --input -
   gh api -X POST 'repos/{owner}/{repo}/environments/production/deployment-branch-policies' -f name=main -f type=branch
   ```

3. Store the token as an environment secret, pasting it at the prompt so it stays out of shell history:

   ```fish
   gh secret set CLOUDFLARE_API_TOKEN --env production
   ```

4. Store the account id, shown on the Workers overview page in the dashboard, as an environment variable:

   ```fish
   gh variable set CLOUDFLARE_ACCOUNT_ID --env production --body ACCOUNT_ID
   ```

5. In Settings, Actions, General, set Workflow permissions to read repository contents and packages.

When the token expires, the deploy step fails with a Cloudflare authentication error; create a new token and repeat step 3.
