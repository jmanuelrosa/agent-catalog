---
name: vuln-lookup
description: >-
  Find the CVEs that reach a repository, including the ones that arrive inside a package:
  the Chromium Playwright and Puppeteer drive, the Chrome and Node inside Electron, the
  OpenSSL, zlib and libuv inside the Node runtime, the libvips stack inside sharp, and the
  OpenSSL inside Python wheels and interpreters. Queries NVD by CPE and exact version, OSV
  for the packages themselves, and ranks by CISA KEV, EPSS and CVSS. Keyless and read-only.
  Use during a dependency or supply-chain assessment, or when asked whether a CVE affects a
  project or which known vulnerabilities its stack carries.
---

# Vulnerability lookup

Package advisories stop at the package.
A Chrome CVE is filed against `google:chrome`, never against Playwright, although Playwright downloads and drives its own Chromium; the same holds for Electron's Node, the Node runtime's OpenSSL, and the libraries a wheel or a native addon links statically.
This skill inventories what is installed, resolves each embedded product to an NVD CPE and an exact version, and asks NVD which CVEs cover that version, alongside an OSV query for the packages themselves.

## Run it

The script sits in this skill's `scripts/` directory, wherever the harness installed the skill (a project's `.claude/skills/` or `.agents/skills/`, or `~/.claude/skills/`).

```fish
python3 <skill dir>/scripts/vuln_lookup.py scan <repo root> --json
python3 <skill dir>/scripts/vuln_lookup.py cve CVE-2026-12345 --json
```

- `scan` walks the repository (installed `node_modules`, lockfiles, virtualenvs, Dockerfiles, `.nvmrc`), so run it from a checkout where dependencies are installed: without `node_modules` the bundled browsers cannot be seen, and it says so by finding nothing to resolve.
- `--top N` keeps the N highest-ranked CVEs per bundled component (default in `embeddings.json`, `0` keeps all). Counts, KEV totals and fix versions always cover every match.
- `--packages-only` / `--embedded-only` narrow the run; `--refresh` ignores the response cache under `$TMPDIR/vuln-lookup` (or `$VULN_LOOKUP_CACHE`).
- NVD allows 5 anonymous requests per 30 seconds, so the first run takes a few seconds per bundled component; reruns inside a day are cached. An `NVD_API_KEY` in the environment raises the limit, and nothing requires one.
- Exit code `2` means at least one lookup failed: the report is partial, and its `errors` list says which.

## Read the output

- `embedded[]`: one entry per embedder, component and version, with `cve_count`, `kev_count`, `top_epss`, `clears_kev_at` (the version that closes every exploited-in-the-wild CVE), `clears_all_at`, and the ranked `cves`. `evidence` is the file the version was read from; cite it.
- `packages.findings[]`: OSV advisories per installed package version, with CVE aliases, KEV, EPSS and the nearest fixed version.
- `not_assessed[]`: components found but not checkable (Playwright's WebKit has no CPE, a sharp library with no mapping, a Node pin that is a range, a failed lookup). These go into the assessment's Not assessed section verbatim; they are unknown, not clean.
- `notes`: caveats on a component's version, such as a floating `node:22` tag resolved to today's newest 22.x when the deployed image may be older.

Ranking is KEV first, then EPSS, then CVSS, because a browser carries hundreds of CVEs at any version and only the exploited and likely-exploited ones change what to do next.
The count is not the finding.

## Turn leads into findings

The script answers "which CVEs cover this version", never "is this exploitable here".
Before a lead becomes a finding, decide reachability for the embedder:

- A test-only browser (Playwright, Puppeteer in CI) that loads only your own application has a narrow attack surface; the same browser used to scrape or render third-party pages is a full browser exposure.
- An Electron app's Chromium renders whatever its windows load: remote content raises every renderer CVE to the app's own risk.
- A runtime pin in a Dockerfile is what ships; a local `node --version` fallback is only the developer's toolchain, and the report labels it so.

The remedy is almost always the embedder, not the component: "bump Playwright to a release whose `browsers.json` pins Chrome >= `clears_kev_at`", not "upgrade Chrome".

## Extend it

`scripts/embeddings.json` is the registry: the API endpoints and limits, the component-to-CPE map, and one entry per embedder naming its resolver and how its version is read.
A new embedder that fits an existing resolver (another `versions.json`-style manifest, another browser downloader) is a JSON edit; a new way of reading a version is a new resolver function in `vuln_lookup.py`.
Verify a CPE `vendor:product` against NVD before adding it, because a wrong one returns zero CVEs and reads as clean.
