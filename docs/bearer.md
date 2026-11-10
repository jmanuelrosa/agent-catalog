# Bearer review policy

Bearer scans the whole catalog and still fails on unreviewed findings.
No rule, path, severity or exit-code override is used.

`bearer.ignore` contains individual reviewed false-positive fingerprints with their source location and rationale.
`docs/bearer-review.json` binds those fingerprints to the reviewed source files and Bearer version.
The test suite rejects missing review records, fingerprint reuse across files, changed source hashes and scan-gate bypasses.
Bearer fingerprints can remain unchanged after a source edit, so a matching fingerprint alone is not enough to preserve an exception.

## Review boundaries

Operator-selected CLI input/output paths are intentional filesystem access, not a file-serving API.
Fixed argument-vector subprocess calls are not shell-command interpolation.
The trace-cluster and report-action hashes identify nonsecurity data; they do not protect passwords, authentication or integrity.
Local example servers and the internal GKE backend do not establish a public TLS endpoint.

Browser discovery and recording deliberately return page/selector evidence to the invoking operator.
That workflow is retained, including explicitly requested HTML capture.
Use authorized test data and keep browser URLs, DOM output, HAR files and diagnostic errors private.
These exceptions do not authorize publishing production page data or applying the examples unchanged to a public service.

Filestore HTTP file access now checks each opened component beneath the mounted root with no-follow descriptors.
The SSH tree/search scripts also reject escaped roots and discovered outside-root file links.
The dbt translator confines SQL, YAML and metadata sources before reading, copying or uploading their contents.
Regression tests exercise outside-root links, normal files, supported inside-root links, and HTTP path swaps.
The dbt checks assume the selected local source tree is not concurrently modified by another process.

## Updating an exception

Re-triage every finding for a changed source file before updating its recorded hash.
Fix confirmed defects first; keep uncertain findings blocking.
Add or retain only exact fingerprints with a source-specific explanation in `bearer.ignore`, then update the corresponding fingerprint list and SHA-256 in `docs/bearer-review.json`.
A Bearer version change also requires a fresh review.
Run the complete test suite and the pinned full scan before shipping.

The separate virtualenv-cleanup lock-lifetime race found during triage is not a path-traversal finding and remains outside this patch.
