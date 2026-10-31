# Spec: Site deploy workflow

**Status:** draft, pending human review
**Brief:** Replace the manual `wrangler deploy` of the Astro site in `site/` with a GitHub Actions workflow that deploys it to Cloudflare automatically on merges to `main`.
Gate it so a merge deploys only when it changes something the site renders, add a manual redeploy trigger and a concurrency group, keep credentials least-privilege, and pin actions the way `ci.yml` already does.
PR preview deploys were to be assessed and recommended, not required.

## Objective & acceptance criteria

1. A push to `main` that changes any **site input** builds the site and deploys it to the `agent-catalog` Worker with no manual step.
2. A push to `main` that changes no site input starts no run of the workflow, for example an edit confined to `skills/<name>/references/**`, `skills/<name>/scripts/**`, `docs/**`, `tests/**` or `Makefile`.
3. The paths filter lists exactly the site inputs in [Site inputs](#site-inputs), and `site/src/lib/catalog.ts` states the coupling next to the line that resolves the catalog root.
4. A `workflow_dispatch` run on `main` deploys regardless of paths; a dispatch on any other ref builds but never deploys.
5. At most one run on `main` is in flight at a time, a deploy in flight is never cancelled, and when several merges queue up, the newest commit is the one that ends up deployed.
6. A pull request that changes a site input runs the build with no secrets and no deploy, and fails when the site does not build; a newer push to the same PR cancels the older run.
7. Least privilege holds: `permissions: {}` at workflow level, `contents: read` as the only job grant, `CLOUDFLARE_API_TOKEN` stored as a secret of the `production` environment and referenced only in the deploy step's `env`, no cache restored anywhere in the workflow, and `persist-credentials: false` on every checkout.
8. Every `uses:` is pinned to a full 40-character commit SHA with a `# vX.Y.Z` comment, wrangler runs at an exact version, and dependencies install with `--frozen-lockfile`.
9. Both jobs run on the Node version in `site/.node-version`, which satisfies Astro 7.4.4 (`>=22.23.4`) and wrangler 4.156.0 (`>=22.0.0`).
10. `site/README.md` says how the site deploys and how to trigger a manual redeploy.

## Domain

No `CONTEXT.md` exists, and none is created: the terms below are build and delivery terms, which a domain glossary leaves out.

- **Catalog root**: the repository root the site reads catalog data from at build time; `CATALOG_ROOT` overrides it and it defaults to the parent of `site/` (`site/src/lib/catalog.ts:4`, `site/README.md`). Existing term, unchanged.
- **Site input** (new): a tracked file whose change can alter the built site, which is anything under `site/` plus every catalog file that `site/src/lib/catalog.ts` reads. The deploy gate's paths filter is the list of site inputs.
- **Production**: the `agent-catalog` Worker serving `agents.jmanuelrosa.dev` (`site/wrangler.jsonc:2,8-13`), and the GitHub environment named `production` that guards its credential.
- **Site build check** (new): the build-only run of the workflow on a pull request.

## Design

### Current state, read from the code

- The site is a static Astro 7.4.4 build (`site/package.json:15`, `build` script `astro build` at `site/package.json:8`) with output in `site/dist/` (gitignored by `site/.gitignore`).
- Deploys target **Workers static assets**, not Pages: `site/wrangler.jsonc` declares an assets-only Worker named `agent-catalog` with `assets.directory: ./dist`, a committed `account_id`, and a `custom_domain` route for `agents.jmanuelrosa.dev`. Commit `2061b56` added only that file and the `site/.gitignore` entries.
- `wrangler` is not a dependency of the site (`site/package.json`); today's deploy is a locally installed wrangler (4.156.0 on the maintainer's machine, the current npm latest) run by hand from `site/`.
- The package manager is Bun (`site/bun.lock`). Astro's bin has a `node` shebang, so `bun run build` executes Astro under Node, and Astro 7.4.4 declares `engines.node >=22.23.4`. The maintainer builds on Node v24.13.0.
- The site reads the catalog from outside `site/` at build time. `site/src/lib/catalog.ts` resolves `root` to the repository root (`:4`) and reads from it with `node:fs` (see [Site inputs](#site-inputs)); under `site/src/pages/`, `catalog.astro`, `attribution.astro`, `index.astro`, `docs/concepts.astro`, `docs/start.astro` and `docs/playbooks.astro` render that data. Every other module under `site/src/lib/` is self-contained.
- `ci.yml` never builds the site, so a site that fails to build is today only discovered at deploy time.
- Conventions to match from `.github/workflows/ci.yml`: actions pinned by full SHA with a version comment (`actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1` at `:22`, `oven-sh/setup-bun@0c5077e51419868618aeaa5fe8019c62421857d6 # v2.2.0` at `:84`), concurrency group `${{ github.workflow }}-${{ github.ref }}` (`:11-13`), `persist-credentials: false` on the SAST checkout (`:42`), `branches: main` scalar form (`:6`), floating Bun with no version input.
- `.github/dependabot.yml` bumps every `github-actions` pin under `/` weekly with a 7-day cooldown, so new pins in a new workflow are covered with no config change.
- The uncommitted change in `site/astro.config.mjs` adds `output: 'static'`, which is Astro's default; nothing here depends on it.

### Site inputs

Each pattern maps to a read in `site/src/lib/catalog.ts`. GitHub's `*` does not cross `/`; `**` does.

| Read in `catalog.ts` | Filter pattern |
|---|---|
| The site itself: sources, config, `package.json`, `bun.lock`, `wrangler.jsonc`, `.node-version` | `site/**` |
| `licenses.json` (`:61`, optional) | `licenses.json` |
| `bundle-registry.json` (`:124`) | `bundle-registry.json` |
| `skill-registry.json` (`:143`) | `skill-registry.json` |
| Frontmatter of `skills/<name>/SKILL.md` for upstream and local entries (`:149`, `:168`) | `skills/*/SKILL.md` |
| `bundles/<name>/bundle.json` (`:127`) | `bundles/*/bundle.json` |
| Listing of `bundles/<name>/agents/` (`:135`, not filtered by extension) and each agent's frontmatter (`:216`) | `bundles/*/agents/**` |
| Listing of `bundles/<name>/skills/` (`:136`) and each skill's frontmatter (`:182`) | `bundles/*/skills/*/SKILL.md` |
| Listing of `agents/*.md` and their frontmatter (`:208-212`) | `agents/*.md` |
| The workflow file | `.github/workflows/site.yml` |

`site/**` already covers `site/.node-version`.
Only frontmatter is read from `SKILL.md` and agent files, so a body-only edit still triggers a run; the path filter cannot see inside a file, and that run republishes identical content, which wrangler uploads as zero new assets.

### Flow

1. A push to `main`, a pull request, or a manual dispatch starts the workflow; push and pull request runs start only if the change touches a site input.
2. `build` checks out the full repository (the catalog root must be present), installs with the frozen lockfile, runs `bun run build` in `site/`, and uploads `site/dist` as the artifact `site-dist`.
3. `deploy` runs only when `github.ref` is `refs/heads/main`. It targets the `production` environment, downloads `site-dist` into `site/dist`, and runs `wrangler deploy` from `site/` so `site/wrangler.jsonc` supplies the Worker name, account id and route.
4. Rollback: re-run the last good run from the Actions tab, which rebuilds and redeploys that commit, or run `wrangler rollback` locally.

### Choices and the strongest rejected alternative

- **Gate with a workflow-level `paths` filter.** Rejected: a change-detection job (`dorny/paths-filter` or a `git diff` step) that always runs and skips later jobs. It adds a third-party action and a runner start to every push, and pays off only when a status must always report, as a required check would. If the site build ever becomes a required check, switch then, because a path-filtered workflow leaves a required check pending.
- **File-level site inputs, not whole directories** (Decision item 6). Rejected: `skills/**`, `bundles/**`, `agents/**`. Of the 11 commits on `main`, two (Dependabot bumps under `skills/agent-platform-tuning/references/` and `skills/cloud-trace-querying/scripts/`) would deploy under the broad filter and render nothing new. Most churn in this repo lands in skill references and scripts, which the site never reads. The cost of precision is drift: if `catalog.ts` starts reading a new file, the filter must grow with it. The comment in `catalog.ts` names that coupling where the reads live, and `workflow_dispatch` is the escape hatch.
- **Two jobs, build then deploy, joined by an artifact.** Rejected: one job that builds and deploys. The build installs the full Astro dependency tree and executes it; splitting means the job that can read the token never installs or runs that tree, and an environment secret is not even present in the build job. The cost is one artifact round trip, roughly 10 to 20 seconds. The same split gives the pull request build check for free, since it is the deploy job skipped.
- **`npx --yes wrangler@<exact> deploy` in the deploy job** (Decision item 1). Rejected: `cloudflare/wrangler-action@v4`. With a `bun.lock` present the action auto-detects Bun and installs wrangler by running `bun i wrangler@<version>` inside `site/`, an unfrozen install of the whole Astro tree in the token-holding job, rewriting the lockfile in the workspace. The deploy job needs Node anyway, since wrangler 4.156.0 requires Node 22 and above, and `npx` ships with Node, so no Bun setup is needed there.
- **Trigger on `push`, not on `workflow_run` after CI.** Rejected: chaining after `ci.yml`. CI never builds the site, so waiting on it gates nothing site-related and adds latency, and a `workflow_run` chain into a secret-bearing workflow is the privilege-escalation pattern OWASP flags.
- **One concurrency group per ref, cancelling only on pull requests.** Rejected: `cancel-in-progress: true` everywhere, as `ci.yml` does. Cancelling a deploy mid-upload can leave a partial asset upload behind and wastes the run. With cancellation off, GitHub keeps one in-flight run and replaces any older pending run with the newest, so the latest merge wins without interrupting an upload.
- **No caching in this workflow.** `setup-node` defaults `package-manager-cache` to true and `setup-bun` caches its executable by default; both are switched off because a poisoned cache restored on `main` would feed straight into a production deploy (OWASP CI/CD, "Caching enabled in release or publish workflows"). The cost is a few seconds of Bun download and an uncached `bun install`.
- **Static API token, scoped to the Worker deploy.** OWASP prefers OIDC federation for deploy credentials; Cloudflare API tokens offer no GitHub OIDC trust, so the check is satisfied another way: the token carries only Workers Scripts edit on one account, lives as a `production` environment secret restricted to `main`, appears only in the deploy step's `env`, and expires (Decision items 2 and 3).
- **No required reviewer on `production`** (Decision item 4). OWASP's deployment gate asks for human approval before production deploys. The merge to `main` is that approval here; a second click per merge would bring back the manual step the brief removes.

### Threat notes

- Token blast radius: Workers Scripts edit at account scope can replace any Worker in the account. Scope the token to the `agent-catalog` Worker if the dashboard offers Worker-level resources (Cloudflare documents resource-level token scoping where available).
- Pull requests, including from forks and Dependabot, run only `build` under `pull_request`, with `contents: read` and no secrets. `pull_request_target` is never used.
- A dispatch from a non-`main` ref cannot deploy: the job `if` blocks it, and the environment's branch policy blocks it again.
- A compromised build dependency can alter `dist/`, which would be published regardless of the job split; it cannot read the token.
- No `${{ }}` expression appears inside a `run:` script. The only value a run step interpolates is `$WRANGLER_VERSION`, a shell variable set from workflow `env:`.

## Contracts

There is one slice, so the contracts here are between the workflow and the systems around it: the trigger and path list, the GitHub environment and secret, the artifact, and the runtime pins.

### Workflow skeleton: `.github/workflows/site.yml`

Triggers, paths, permissions, concurrency, job graph, environment, artifact and secret names are fixed as written.
`<sha>` and `vX.Y.Z` are resolved by the implementer as described in the slice.
Step names follow `ci.yml`'s sentence-case style.

```yaml
name: Site

on:
  push:
    branches: main
    paths: &site-inputs
      - site/**
      - licenses.json
      - bundle-registry.json
      - skill-registry.json
      - skills/*/SKILL.md
      - bundles/*/bundle.json
      - bundles/*/agents/**
      - bundles/*/skills/*/SKILL.md
      - agents/*.md
      - .github/workflows/site.yml
  pull_request:
    paths: *site-inputs
  workflow_dispatch:

permissions: {}

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}

env:
  WRANGLER_VERSION: 4.156.0

jobs:
  build:
    name: Build site
    runs-on: ubuntu-latest
    timeout-minutes: 15
    permissions:
      contents: read
    steps:
      - name: Checkout code
        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false

      - name: Setup Node
        uses: actions/setup-node@<sha> # vX.Y.Z
        with:
          node-version-file: site/.node-version
          package-manager-cache: false

      - name: Setup Bun
        uses: oven-sh/setup-bun@0c5077e51419868618aeaa5fe8019c62421857d6 # v2.2.0
        with:
          no-cache: true

      - name: Install dependencies
        working-directory: site
        run: bun install --frozen-lockfile

      - name: Build site
        working-directory: site
        run: bun run build

      - name: Upload build output
        uses: actions/upload-artifact@<sha> # vX.Y.Z
        with:
          name: site-dist
          path: site/dist
          if-no-files-found: error
          retention-days: 7

  deploy:
    name: Deploy to Cloudflare
    needs: build
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    timeout-minutes: 10
    environment: production
    permissions:
      contents: read
    steps:
      - name: Checkout code
        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false

      - name: Setup Node
        uses: actions/setup-node@<sha> # vX.Y.Z
        with:
          node-version-file: site/.node-version
          package-manager-cache: false

      - name: Download build output
        uses: actions/download-artifact@<sha> # vX.Y.Z
        with:
          name: site-dist
          path: site/dist

      - name: Deploy with wrangler
        working-directory: site
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ vars.CLOUDFLARE_ACCOUNT_ID }}
        run: npx --yes "wrangler@$WRANGLER_VERSION" deploy
```

Notes the skeleton relies on:

- `if: github.ref == 'refs/heads/main'` covers pull requests too, because a pull request's `github.ref` is `refs/pull/<n>/merge`.
- The deploy job checks out only so `site/.node-version` and `site/wrangler.jsonc` are on disk; it installs nothing from the repository.
- YAML anchors (`&site-inputs`, `*site-inputs`) are supported in Actions workflows since September 2025; merge keys (`<<`) are not, and are not used.
- `CLOUDFLARE_ACCOUNT_ID` is an environment variable, not a secret: an account id is an identifier, not a credential. `site/wrangler.jsonc` carries no `account_id`, because wrangler prefers the config value over the environment variable.
- `retention-days: 7` lets a reviewer download a pull request's built site from the run page, which covers part of what a preview would.

### Names other parties depend on

| Name | Kind | Set by | Used by |
|---|---|---|---|
| `production` | GitHub environment, deployment branches limited to `main`, no required reviewers | user (manual setup) | `deploy` job |
| `CLOUDFLARE_API_TOKEN` | environment secret of `production` | user (manual setup) | `Deploy with wrangler` step |
| `CLOUDFLARE_ACCOUNT_ID` | environment variable of `production` | user (manual setup) | `Deploy with wrangler` step |
| `site-dist` | workflow artifact holding `site/dist` | `build` job | `deploy` job |
| `site/.node-version` | file containing `24` | platform slice | both `Setup Node` steps |
| `WRANGLER_VERSION` | workflow `env`, exact version | platform slice | `Deploy with wrangler` step |

### Example trigger outcomes

| Change merged to `main` | Run? | Why |
|---|---|---|
| `site/src/pages/index.astro` | yes, deploys | `site/**` |
| `skills/astro/SKILL.md` | yes, deploys | `skills/*/SKILL.md` (description may change) |
| `skills/agent-platform-tuning/references/requirements.txt` only | no | never read by the site |
| `skills/cloud-trace-querying/scripts/requirements.txt` only | no | never read by the site |
| `bundles/platform/agents/platform-staff-engineer.md` | yes, deploys | `bundles/*/agents/**` |
| `bundles/platform/skills/platform-failure-modes/references/ci-pipelines.md` only | no | only `SKILL.md` frontmatter is read |
| `skill-registry.json` | yes, deploys | registry drives the skill list |
| `.github/workflows/ci.yml` only | no | not this workflow |
| `docs/specs/site-deploy.md` only | no | not a site input |

## Work breakdown

### Slice: Site deploy workflow (owner: platform-staff-engineer)

- **Owns:** `.github/workflows/site.yml` (new), `site/.node-version` (new), `site/README.md`, `site/src/lib/catalog.ts` (one comment, no behavior change)
- **Parallel:** yes
- **Depends on:** none (the user's manual setup below must be done before this slice's PR merges, not before it is built)

Pre-authorized by this spec: a new workflow file; three new GitHub-owned actions (`actions/setup-node`, `actions/upload-artifact`, `actions/download-artifact`), each pinned by SHA; running wrangler 4.156.0 through `npx` in CI; running `zizmor` once through `uvx` to audit the new workflow.
Not authorized: adding `wrangler` or any other package to `site/package.json` or `site/bun.lock`, editing `ci.yml` or `dependabot.yml`, changing repository settings, environments or secrets.

**Task 1: Pin the Node version** (AC 9)

- Create `site/.node-version` containing `24`.
- Acceptance: `actions/setup-node` resolves Node 24.x from it in the PR run's log; locally, `node --version` under a version manager that reads `.node-version` reports 24.x.

**Task 2: Workflow triggers and the build job** (AC 2, 3, 5, 6, 7, 8, 9)

- Create `.github/workflows/site.yml` with the `on`, `permissions`, `concurrency`, `env` and `build` blocks exactly as in [Contracts](#contracts).
- Resolve each new pin to the latest release at implementation time, as the commit SHA (not an annotated tag object): `gh api repos/actions/setup-node/releases/latest --jq .tag_name`, then `gh api repos/actions/setup-node/commits/<tag> --jq .sha`; same for `upload-artifact` and `download-artifact`, which must come from the same major line. Reuse `ci.yml`'s existing `checkout` and `setup-bun` pins unchanged, so Dependabot's group bumps both workflows together.
- Acceptance: the PR for this slice (it touches `site/**` and the workflow) runs `build` green and uploads `site-dist`; every `uses:` has a 40-character SHA and a version comment; no step restores a cache.

**Task 3: The deploy job** (AC 1, 4, 5, 7, 8)

- Add the `deploy` job exactly as in [Contracts](#contracts): `needs: build`, `if: github.ref == 'refs/heads/main'`, `environment: production`, the token only in the deploy step's `env`, wrangler invoked through `$WRANGLER_VERSION`.
- Acceptance: `uvx zizmor .github/workflows/site.yml` reports no high-severity finding (record any medium or low finding and the reason it stays in the completion report); no `${{ }}` expression appears inside a `run:` script; on the PR run, `deploy` is skipped. The post-merge deploy (AC 1, 5) is verified by the user after the manual setup, since the seat cannot reach the `production` secret.

**Task 4: Name the coupling and document the deploy** (AC 3, 10)

- In `site/src/lib/catalog.ts`, add one comment directly above `const root` (`:4`) saying that every catalog path read in this file is mirrored in the paths filter of `.github/workflows/site.yml`, and that a new read needs a matching entry there or merges that change it never deploy. No other change to the file.
- In `site/README.md`, add a short deploy section: the site deploys to Cloudflare from `.github/workflows/site.yml` on merges to `main` that change a site input; pull requests that touch one get a build check; redeploy by hand with `gh workflow run site.yml --ref main`. Keep the README's one-sentence-per-line style and fish syntax for any shell example.
- Acceptance: `make lint` passes; each pattern in the workflow's `&site-inputs` list maps to a row of the [Site inputs](#site-inputs) table, and each `readFileSync`, `readdirSync` or `existsSync` in `catalog.ts` maps to a pattern.

## One-time manual setup (user)

Do steps 1 to 3 before merging the platform slice's PR; the merge itself touches the workflow file and triggers the first deploy.

1. **Create the Cloudflare API token.** Dashboard, My Profile, API Tokens, Create Token, Create Custom Token.
   - Name: `github-actions-agent-catalog-site`.
   - Permissions: Account, Workers Scripts, Edit. Nothing else.
   - Account resources: Include, the account that owns the `agent-catalog` Worker. If the form offers Worker-level resources, include only the `agent-catalog` Worker.
   - Zone resources: none (Decision item 2).
   - Client IP address filtering: none; GitHub-hosted runner ranges are too broad to help.
   - TTL: an end date 12 months out (Decision item 3).
2. **Create the `production` environment** with deployment branches limited to `main` and no required reviewers. Settings, Environments, New environment, `production`, Deployment branches and tags, Selected branches and tags, add `main`. From fish, in the repo:

   ```fish
   echo '{"deployment_branch_policy":{"protected_branches":false,"custom_branch_policies":true}}' | gh api -X PUT 'repos/{owner}/{repo}/environments/production' --input -
   gh api -X POST 'repos/{owner}/{repo}/environments/production/deployment-branch-policies' -f name=main -f type=branch
   ```

   The repository is public, so environments and environment secrets are available on any GitHub plan.

3. **Store the token as an environment secret.** `gh secret set CLOUDFLARE_API_TOKEN --env production`, then paste the token at the prompt, so it never lands in shell history.
   Then store the account id as an environment variable: `gh variable set CLOUDFLARE_ACCOUNT_ID --env production --body ACCOUNT_ID`.
4. **Check repository Actions settings.** Settings, Actions, General: Workflow permissions set to "Read repository contents and packages permissions". Optionally, set fork pull request workflows to require approval for all outside collaborators.
5. **Watch the first deploy** after the slice merges: `gh run list --workflow site.yml --limit 1`, then `gh run watch <run-id>`. If the deploy step fails with a Cloudflare authentication error that names an endpoint, add only the permission that endpoint needs to the token, then re-run the job.
6. **Stop deploying by hand.** A local `wrangler deploy` still works and stays the fallback for a `routes` change (Decision item 2), but anything else deployed by hand is overwritten by the next CI deploy.
7. **Bump wrangler by hand.** Dependabot does not read `WRANGLER_VERSION`; raise it in the workflow when you upgrade wrangler locally.

## Decision items

1. **How the deploy job runs wrangler.**
   Options: `npx --yes wrangler@<exact>` in a dedicated job; `cloudflare/wrangler-action@v4` pinned by SHA; `wrangler` as an exact devDependency in `site/package.json`.
   Recommendation: `npx`, because the action's Bun path does an unfrozen full install in the token-holding job, and the devDependency is a new dependency plus a `bun.lock` write the agent hooks deny, so you would make that write yourself.
   Move to the devDependency if you want wrangler hash-locked and bumped by a future Bun Dependabot entry.
   Default: `npx --yes "wrangler@$WRANGLER_VERSION" deploy` with `WRANGLER_VERSION: 4.156.0`.
2. **Token zone scope.**
   Options: Workers Scripts edit only; add Zone, Workers Routes, Edit on `jmanuelrosa.dev`.
   Cloudflare's Workers authorization guide says redeploying a Worker whose custom domain is already attached needs only Worker edit access, while adding, changing or removing a route or custom domain also needs Workers Routes write on the zone.
   Recommendation: Workers Scripts edit only. A future change to `routes` in `site/wrangler.jsonc` then fails the CI deploy with a visible auth error, and you deploy that one change by hand.
   Default: Workers Scripts edit only. Precondition: `agents.jmanuelrosa.dev` is already attached to the Worker, which the current manual deploys imply; the first CI deploy proves it.
3. **Token lifetime.**
   Options: an end date; no expiry.
   Recommendation: 12 months. An expired token fails a deploy loudly, while a leaked token with no expiry stays live.
   Default: 12 months.
4. **Human approval on `production`.**
   Options: no required reviewers; require your approval per deploy.
   Recommendation: none, since the merge to `main` is the approval and the brief asks to remove the manual step. This overrides the OWASP deployment-gate check; the branch policy, the job `if`, and the scoped token are the compensating controls.
   Default: no required reviewers.
5. **Pull request runs.**
   Options: build check only; build check plus Cloudflare preview deploys; nothing on pull requests.
   Recommendation: build check only. A Workers preview (`wrangler versions upload` with a preview alias) needs the token in pull request context. Fork and Dependabot PRs get no secrets, and working around that takes `pull_request_target` or a `workflow_run` chain, both OWASP-flagged escalation paths. A preview would also publish unreviewed content on a public URL. Its value is low for a single-maintainer static site whose output is deterministic from the repo, and the 7-day `site-dist` artifact covers ad hoc inspection. Revisit if outside contributors start sending site changes, and then limit previews to same-repo branches under a separate `preview` environment and token.
   Default: build check only.
6. **Filter precision.**
   Options: file-level site inputs; whole `skills/**`, `bundles/**` and `agents/**` directories.
   Recommendation: file-level. The evidence and the drift mitigation are in [Design](#choices-and-the-strongest-rejected-alternative).
   Default: file-level, as in the skeleton.
7. **Where the Node version comes from.**
   Options: `site/.node-version`; an inline `node-version: 24` in both jobs; `lts/*`.
   Recommendation: `site/.node-version`, one source both jobs and local version managers read, set to the major you build with today.
   Default: `site/.node-version` containing `24`.

## Out of scope

- Cloudflare preview deploys for pull requests (Decision item 5).
- Changing `ci.yml`, adding the site build to it, or making the site build a required check.
- Workflow security scanning in CI (zizmor, CodeQL `actions`); this slice runs zizmor once, locally.
- Branch protection, rulesets, and Dependabot coverage for the `bun` ecosystem.
- Adding `wrangler` to the site's dependencies.
- Moving the custom domain, adding routes, or any other change to `site/wrangler.jsonc`.
- Deploy notifications beyond GitHub's default failed-run email, and automated rollback.
- Any change to what the site renders.
