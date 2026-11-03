#!/usr/bin/env python3
"""Find the CVEs that reach a repository, including the ones that arrive inside a package.

Package advisories stop at the package: a Chrome CVE is never filed against Playwright,
although Playwright downloads and drives its own Chromium. This inventories what is
installed, resolves the browsers, runtimes and native libraries those packages embed to an
NVD CPE and an exact version, asks NVD which CVEs cover that version, asks OSV about the
packages themselves, and ranks everything by CISA KEV, then EPSS, then CVSS.

Read-only and keyless. Anything it cannot pin to a CPE and a concrete version is reported
as not assessed, and a failed lookup is reported as a failure, because either one read as
"no findings" is the exact false clean this exists to prevent.
"""

import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dotkit import ui

REGISTRY_PATH = Path(__file__).resolve().parent / "embeddings.json"
API_KEY_ENV = "NVD_API_KEY"
CACHE_ENV = "VULN_LOOKUP_CACHE"
CACHE_DIRNAME = "vuln-lookup"
USER_AGENT = "vuln-lookup"
EXIT_OK, EXIT_USAGE, EXIT_PARTIAL = 0, 1, 2
# NVD answers 403 rather than 429 when the anonymous rate limit trips.
RETRYABLE_STATUS = frozenset({403, 429, 500, 502, 503, 504})

SKIP_DIRS = {".git", ".hg", ".svn", "__pycache__", ".tox", ".nox", ".mypy_cache",
             ".pytest_cache", ".ruff_cache", ".next", ".turbo", ".cache"}
NODE_LOCKFILES = {"package-lock.json", "npm-shrinkwrap.json", "pnpm-lock.yaml", "yarn.lock"}
PYTHON_LOCKFILES = {"uv.lock", "poetry.lock"}
NODE_PIN_FILES = {".nvmrc", ".node-version", ".tool-versions"}
SEVERITY_RANK = {"CRITICAL": 9.0, "HIGH": 7.0, "MODERATE": 5.0, "MEDIUM": 5.0, "LOW": 2.0}
CVSS_METRICS = ("cvssMetricV40", "cvssMetricV31", "cvssMetricV30", "cvssMetricV2")
SEMVER = re.compile(r"^v?(\d+\.\d+\.\d+)$")
LEADING_VERSION = re.compile(r"^v?(\d+(?:\.\d+)*[a-z]?)")


def load_registry(path=REGISTRY_PATH):
    return json.loads(Path(path).read_text())


def version_key(version):
    """Orders `1.1.1w` after `1.1.1` and `1.1.10` after both, as OpenSSL and Chrome need.

    Trailing zeros are dropped because NVD writes Firefox's `157.0` as `157.0.0`, and a
    tuple comparison would otherwise call the fixed release vulnerable.
    """
    key = [(0, int(part), "") if part.isdigit() else (1, 0, part.lower())
           for part in re.findall(r"\d+|[a-zA-Z]+", str(version))]
    while key and key[-1] == (0, 0, ""):
        key.pop()
    return tuple(key)


def leading_version(text):
    match = LEADING_VERSION.match(str(text).strip())
    return match.group(1) if match else None


def normalise_pypi(name):
    return re.sub(r"[-_.]+", "-", name).lower()


# ----------------------------------------------------------------------------- network


class Throttle:
    def __init__(self, interval, clock=time.monotonic, sleep=time.sleep):
        self.interval, self.clock, self.sleep = interval, clock, sleep
        self.last = None

    def wait(self):
        if self.last is not None:
            elapsed = self.clock() - self.last
            if elapsed < self.interval:
                self.sleep(self.interval - elapsed)
        self.last = self.clock()


class Http:
    def __init__(self, limits, sleep=time.sleep):
        self.retries = limits["retries"]
        self.backoff = limits["retry_backoff_seconds"]
        self.timeout = limits["timeout_seconds"]
        self.sleep = sleep

    def json(self, url, body=None, headers=None):
        data = json.dumps(body).encode() if body is not None else None
        merged = {"User-Agent": USER_AGENT, "Accept": "application/json", **(headers or {})}
        if data is not None:
            merged["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=merged)
        for attempt in range(1, self.retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return json.load(response)
            except urllib.error.HTTPError as error:
                if error.code not in RETRYABLE_STATUS or attempt == self.retries:
                    raise
            except (urllib.error.URLError, TimeoutError):
                if attempt == self.retries:
                    raise
            self.sleep(self.backoff * attempt)
        raise RuntimeError("unreachable")


class Cache:
    def __init__(self, root, ttl, refresh=False, now=time.time):
        self.root, self.ttl, self.refresh, self.now = Path(root), ttl, refresh, now

    def _path(self, key):
        return self.root / (hashlib.sha256(key.encode()).hexdigest() + ".json")

    def fetch(self, key, produce):
        path = self._path(key)
        if not self.refresh and path.is_file() and self.now() - path.stat().st_mtime < self.ttl:
            return json.loads(path.read_text())
        value = produce()
        self.root.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
        return value


def default_cache_root():
    return Path(os.environ.get(CACHE_ENV) or Path(tempfile.gettempdir()) / CACHE_DIRNAME)


# ----------------------------------------------------------------------------- feeds


def cvss_of(cve):
    metrics = cve.get("metrics", {})
    for name in CVSS_METRICS:
        for metric in metrics.get(name, []):
            data = metric.get("cvssData", {})
            if "baseScore" in data:
                return data["baseScore"], data.get("baseSeverity") or metric.get("baseSeverity")
    return None, None


def english(descriptions, limit):
    text = next((d["value"] for d in descriptions if d.get("lang") == "en"), "")
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def cpe_matches(cve):
    for configuration in cve.get("configurations", []):
        for node in configuration.get("nodes", []):
            yield from node.get("cpeMatch", [])


def match_covers(match, product, version):
    """Whether one NVD cpeMatch marks `product` at `version` vulnerable.

    NVD's virtualMatchString also returns CVEs where the product is only the platform an
    extension runs on, so the server's answer is a candidate list and this is the filter.
    """
    parts = match.get("criteria", "").split(":")
    if len(parts) < 6 or f"{parts[3]}:{parts[4]}" != product or not match.get("vulnerable"):
        return False
    target = version_key(version)
    if parts[5] not in ("*", "-"):
        return version_key(parts[5]) == target
    bounds = (
        ("versionStartIncluding", lambda bound: target >= bound),
        ("versionStartExcluding", lambda bound: target > bound),
        ("versionEndIncluding", lambda bound: target <= bound),
        ("versionEndExcluding", lambda bound: target < bound),
    )
    return all(check(version_key(match[name])) for name, check in bounds if name in match)


def trim_nvd(cve, product, version, summary_chars):
    if cve.get("vulnStatus") == "Rejected":
        return None
    covering = [m for m in cpe_matches(cve) if match_covers(m, product, version)]
    if not covering:
        return None
    fixes = [m["versionEndExcluding"] for m in covering if "versionEndExcluding" in m]
    score, severity = cvss_of(cve)
    return {
        "id": cve["id"],
        "published": cve.get("published", "")[:10],
        "cvss": score,
        "severity": severity,
        "kev": bool(cve.get("cisaExploitAdd")),
        "fixed_in": max(fixes, key=version_key) if fixes else None,
        "summary": english(cve.get("descriptions", []), summary_chars),
    }


class Feeds:
    def __init__(self, registry, http, cache, api_key=None, clock=time.monotonic, sleep=time.sleep):
        self.sources = registry["sources"]
        self.limits = registry["limits"]
        self.http, self.cache, self.api_key = http, cache, api_key
        rate = self.limits["nvd_with_key" if api_key else "nvd_anonymous"]
        self.nvd_throttle = Throttle(rate["window_seconds"] / rate["requests"], clock, sleep)

    def _nvd(self, params):
        self.nvd_throttle.wait()
        url = f"{self.sources['nvd_cves']}?{urllib.parse.urlencode(params, safe=':*')}"
        headers = {"apiKey": self.api_key} if self.api_key else None
        return self.http.json(url, headers=headers)

    def nvd_for(self, product, version):
        def produce():
            page_size = self.limits["nvd_page_size"]
            match = f"cpe:2.3:a:{product}:{version}"
            found, start, total = [], 0, None
            while total is None or start < total:
                page = self._nvd({"virtualMatchString": match, "resultsPerPage": page_size,
                                  "startIndex": start})
                total = page.get("totalResults", 0)
                batch = page.get("vulnerabilities", [])
                for item in batch:
                    trimmed = trim_nvd(item["cve"], product, version, self.limits["summary_chars"])
                    if trimmed:
                        found.append(trimmed)
                if not batch:
                    break
                start += len(batch)
            return found

        return self.cache.fetch(f"nvd:{product}:{version}", produce)

    def nvd_cve(self, cve_id):
        def produce():
            items = self._nvd({"cveId": cve_id}).get("vulnerabilities", [])
            return items[0]["cve"] if items else None

        return self.cache.fetch(f"nvd-cve:{cve_id}", produce)

    def kev_ids(self):
        catalog = self.cache.fetch("kev", lambda: [v["cveID"] for v in self.http.json(
            self.sources["kev"]).get("vulnerabilities", [])])
        return set(catalog)

    def epss(self, cve_ids):
        scores, ids = {}, sorted(set(cve_ids))
        size = self.limits["epss_batch"]
        for offset in range(0, len(ids), size):
            batch = ids[offset: offset + size]

            def produce(batch=batch):
                url = f"{self.sources['epss']}?{urllib.parse.urlencode({'cve': ','.join(batch)}, safe=',')}"
                return {row["cve"]: float(row["epss"]) for row in self.http.json(url).get("data", [])}

            scores.update(self.cache.fetch("epss:" + ",".join(batch), produce))
        return scores

    def osv_ids(self, packages):
        ids = []
        size = self.limits["osv_batch"]
        for offset in range(0, len(packages), size):
            chunk = packages[offset: offset + size]
            queries = [{"package": {"name": p.name, "ecosystem": p.ecosystem}, "version": p.version}
                       for p in chunk]
            key = "osv-batch:" + hashlib.sha256(json.dumps(queries).encode()).hexdigest()
            results = self.cache.fetch(key, lambda queries=queries: self._osv_batch(queries))
            ids.extend(results)
        return ids

    def _osv_batch(self, queries):
        results = self.http.json(self.sources["osv_querybatch"], body={"queries": queries}).get("results", [])
        out = []
        for query, result in zip(queries, results):
            found = [v["id"] for v in result.get("vulns", [])]
            token = result.get("next_page_token")
            while token:
                more = self.http.json(self.sources["osv_querybatch"],
                                      body={"queries": [{**query, "page_token": token}]})["results"][0]
                found.extend(v["id"] for v in more.get("vulns", []))
                token = more.get("next_page_token")
            out.append(found)
        return out

    def osv_vuln(self, vuln_id):
        return self.cache.fetch(f"osv:{vuln_id}", lambda: self.http.json(
            self.sources["osv_vuln"] + urllib.parse.quote(vuln_id)))

    def electron_releases(self):
        return self.cache.fetch("electron-releases", lambda: [
            {key: release.get(key) for key in ("version", "chrome", "node")}
            for release in self.http.json(self.sources["electron_releases"])])

    def node_index(self):
        return self.cache.fetch("node-index", lambda: [
            {key: release.get(key) for key in ("version", "openssl", "zlib", "uv", "lts")}
            for release in self.http.json(self.sources["node_index"])])


# ----------------------------------------------------------------------------- inventory


@dataclass
class Tree:
    root: Path
    node_modules: list = field(default_factory=list)
    site_packages: list = field(default_factory=list)
    venv_pythons: list = field(default_factory=list)
    node_lockfiles: list = field(default_factory=list)
    python_lockfiles: list = field(default_factory=list)
    requirements: list = field(default_factory=list)
    package_jsons: list = field(default_factory=list)
    node_pins: list = field(default_factory=list)
    dockerfiles: list = field(default_factory=list)
    pyprojects: list = field(default_factory=list)


def walk(root):
    tree = Tree(root=root)
    for dirpath, dirnames, filenames in os.walk(root):
        here = Path(dirpath)
        if "pyvenv.cfg" in filenames:
            tree.site_packages.extend(sorted(here.glob("lib/python*/site-packages")))
            tree.site_packages.extend(sorted(here.glob("Lib/site-packages")))
            python = here / "bin" / "python"
            if python.exists():
                tree.venv_pythons.append(python)
            dirnames[:] = []
            continue
        kept = []
        for name in dirnames:
            if name == "node_modules":
                tree.node_modules.append(here / name)
            elif name not in SKIP_DIRS:
                kept.append(name)
        dirnames[:] = sorted(kept)
        for name in sorted(filenames):
            path = here / name
            if name in NODE_LOCKFILES:
                tree.node_lockfiles.append(path)
            elif name in PYTHON_LOCKFILES:
                tree.python_lockfiles.append(path)
            elif name.startswith("requirements") and name.endswith(".txt"):
                tree.requirements.append(path)
            elif name == "package.json":
                tree.package_jsons.append(path)
            elif name == "pyproject.toml":
                tree.pyprojects.append(path)
            elif name in NODE_PIN_FILES:
                tree.node_pins.append(path)
            elif name == "Dockerfile" or name.startswith("Dockerfile.") or name.endswith(".dockerfile"):
                tree.dockerfiles.append(path)
    return tree


@dataclass(frozen=True)
class Package:
    ecosystem: str
    name: str
    version: str


def read_package_lock(path):
    data = json.loads(path.read_text())
    found = set()
    for key, entry in data.get("packages", {}).items():
        if not key or entry.get("link") or "version" not in entry:
            continue
        name = entry.get("name") or key.rsplit("node_modules/", 1)[-1]
        found.add(Package("npm", name, entry["version"]))

    def legacy(deps):
        for name, entry in (deps or {}).items():
            if "version" in entry and not str(entry["version"]).startswith(("file:", "link:")):
                found.add(Package("npm", name, entry["version"]))
            legacy(entry.get("dependencies"))

    if not data.get("packages"):
        legacy(data.get("dependencies"))
    return found


PNPM_ENTRY = re.compile(r"^  '?/?((?:@[^/@\s']+/)?[^@/\s'(]+)@(\d[^\s'():]*)")
PNPM_V5_ENTRY = re.compile(r"^  '?/((?:@[^/\s']+/)?[^/\s']+)/(\d[^\s'/():_]*)")


def read_pnpm_lock(path):
    found, section = set(), None
    for line in path.read_text().splitlines():
        if line and not line.startswith(" "):
            section = line.rstrip(":")
            continue
        if section not in ("packages", "snapshots"):
            continue
        match = PNPM_ENTRY.match(line) or PNPM_V5_ENTRY.match(line)
        if match:
            found.add(Package("npm", match.group(1), match.group(2)))
    return found


YARN_VERSION = re.compile(r'^\s+version:?\s+"?([^"\s]+)"?')


def yarn_name(header):
    first = header.split(",")[0].strip().strip('"')
    at = first.rfind("@")
    return first[:at] if at > 0 else first


def read_yarn_lock(path):
    found, name = set(), None
    for line in path.read_text().splitlines():
        if line and not line.startswith((" ", "#")) and line.endswith(":"):
            name = None if line.startswith("__metadata") else yarn_name(line[:-1])
            continue
        match = YARN_VERSION.match(line)
        if name and match and not match.group(1).startswith("0.0.0-use.local"):
            found.add(Package("npm", name, match.group(1)))
            name = None
    return found


def read_node_modules(node_modules):
    found = set()
    for manifest in [*node_modules.glob("*/package.json"), *node_modules.glob("@*/*/package.json")]:
        try:
            data = json.loads(manifest.read_text())
        except (OSError, ValueError):
            continue
        if data.get("name") and data.get("version"):
            found.add(Package("npm", data["name"], data["version"]))
    return found


def read_toml_lock(path):
    data = tomllib.loads(path.read_text())
    return {
        Package("PyPI", normalise_pypi(entry["name"]), entry["version"])
        for entry in data.get("package", [])
        if "version" in entry and not {"editable", "virtual", "workspace", "directory"} & set(entry.get("source", {}))
    }


REQUIREMENT_PIN = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]*\])?\s*==\s*([^\s;#\\]+)")


def read_requirements(path):
    return {Package("PyPI", normalise_pypi(m.group(1)), m.group(2))
            for m in map(REQUIREMENT_PIN.match, path.read_text().splitlines()) if m}


def read_site_packages(site_packages):
    found = set()
    for metadata in site_packages.glob("*.dist-info/METADATA"):
        fields = {}
        for line in metadata.read_text(errors="replace").splitlines():
            if not line:
                break
            key, _, value = line.partition(": ")
            fields.setdefault(key, value)
        if fields.get("Name") and fields.get("Version"):
            found.add(Package("PyPI", normalise_pypi(fields["Name"]), fields["Version"]))
    return found


NODE_READERS = {"package-lock.json": read_package_lock, "npm-shrinkwrap.json": read_package_lock,
                "pnpm-lock.yaml": read_pnpm_lock, "yarn.lock": read_yarn_lock}


def inventory(tree):
    """Package -> the files that prove it is installed. Lockfiles and installed trees only,
    because a manifest range says what may resolve, not what did."""
    evidence = {}

    def add(packages, source):
        for package in packages:
            evidence.setdefault(package, set()).add(str(source.relative_to(tree.root)))

    for lockfile in tree.node_lockfiles:
        add(NODE_READERS[lockfile.name](lockfile), lockfile)
    if not tree.node_lockfiles:
        for node_modules in tree.node_modules:
            add(read_node_modules(node_modules), node_modules)
    for lockfile in tree.python_lockfiles:
        add(read_toml_lock(lockfile), lockfile)
    for requirements in tree.requirements:
        add(read_requirements(requirements), requirements)
    for site_packages in tree.site_packages:
        add(read_site_packages(site_packages), site_packages)
    return {package: sorted(paths) for package, paths in evidence.items()}


# ----------------------------------------------------------------------------- embedded components


@dataclass(frozen=True)
class Component:
    embedder: str
    embedder_version: str
    component: str
    version: str
    evidence: str
    note: str = ""


@dataclass(frozen=True)
class Unassessed:
    embedder: str
    component: str
    version: str
    evidence: str
    reason: str


def package_dirs(tree, pattern):
    seen, found = set(), []
    for node_modules in tree.node_modules:
        for candidate in (node_modules.glob(pattern), node_modules.glob(f".pnpm/*/node_modules/{pattern}"),
                          node_modules.glob(f"*/node_modules/{pattern}"),
                          node_modules.glob(f"@*/*/node_modules/{pattern}")):
            for directory in candidate:
                real = directory.resolve()
                if directory.is_dir() and real not in seen:
                    seen.add(real)
                    found.append(directory)
    return sorted(found)


def package_version(directory):
    try:
        return json.loads((directory / "package.json").read_text()).get("version", "")
    except (OSError, ValueError):
        return ""


def relative(tree, path):
    return str(Path(path).relative_to(tree.root))


def resolve_playwright_browsers(spec, tree, feeds):
    for directory in package_dirs(tree, spec["package"]):
        manifest = directory / spec["file"]
        if not manifest.is_file():
            continue
        owner_version = package_version(directory)
        for browser in json.loads(manifest.read_text()).get("browsers", []):
            name, version = browser.get("name"), browser.get("browserVersion")
            if name in spec["components"] and version:
                yield Component(spec["name"], owner_version, spec["components"][name], version,
                                relative(tree, manifest))
            elif name in spec.get("unmapped", {}):
                yield Unassessed(spec["name"], name, version or "", relative(tree, manifest),
                                 spec["unmapped"][name])


PUPPETEER_PAIR = re.compile(r"""['"]?([\w-]+)['"]?\s*:\s*['"]([^'"]+)['"]""")


def resolve_puppeteer_revisions(spec, tree, feeds):
    for directory in package_dirs(tree, spec["package"]):
        manifest = next(iter(sorted(directory.glob(spec["file"]))), None)
        if manifest is None:
            continue
        text = manifest.read_text()
        block = text[text.find("REVISIONS"):]
        block = block[: block.find("}") + 1]
        for name, raw in PUPPETEER_PAIR.findall(block):
            if name in spec["components"]:
                yield Component(spec["name"], package_version(directory), spec["components"][name],
                                raw.rsplit("_", 1)[-1], relative(tree, manifest))


def resolve_electron_release(spec, tree, feeds):
    for directory in package_dirs(tree, spec["package"]):
        version = package_version(directory)
        evidence = relative(tree, directory / spec["file"])
        release = next((r for r in feeds.electron_releases() if r.get("version") == version), None)
        if release is None:
            yield Unassessed(spec["name"], "chrome, node", "", evidence,
                             f"electron {version} is not in the Electron release metadata")
            continue
        for field_name, component in spec["components"].items():
            if release.get(field_name):
                yield Component(spec["name"], version, component, release[field_name], evidence,
                                spec.get("note", ""))


def resolve_versions_manifest(spec, tree, feeds):
    for directory in package_dirs(tree, spec["package"]):
        manifest = directory / spec["file"]
        if not manifest.is_file():
            continue
        evidence = relative(tree, manifest)
        for name, version in sorted(json.loads(manifest.read_text()).items()):
            if name in spec["components"]:
                yield Component(spec["name"], package_version(directory), spec["components"][name],
                                str(version), evidence)
            else:
                yield Unassessed(spec["name"], name, str(version), evidence,
                                 "no CPE mapping for this library in embeddings.json")


DOCKER_NODE = re.compile(r"^\s*FROM\s+(?:--\S+\s+)*(?:\S+/)?node:(\S+)", re.IGNORECASE | re.MULTILINE)
TOOL_VERSIONS_NODE = re.compile(r"^\s*(?:nodejs|node)\s+(\S+)", re.MULTILINE)


def node_pins(tree):
    """(raw pin, evidence) for every place the project says which Node it runs on."""
    pins = []
    for path in tree.node_pins:
        text = path.read_text()
        if path.name == ".tool-versions":
            pins.extend((m, path) for m in TOOL_VERSIONS_NODE.findall(text))
        elif text.strip():
            pins.append((text.strip().splitlines()[0], path))
    for path in tree.dockerfiles:
        pins.extend((tag.split("@")[0], path) for tag in DOCKER_NODE.findall(path.read_text()))
    for path in tree.package_jsons:
        try:
            engines = json.loads(path.read_text()).get("engines") or {}
        except (OSError, ValueError):
            continue
        if engines.get("node"):
            pins.append((engines["node"], path))
    return pins


def resolve_node_pin(raw, index):
    """(release, note) for a pin, or (None, reason). A floating pin resolves to the newest
    matching release, which is what a fresh install pulls today; the deployed build may be older."""
    pin = raw.strip().lower().removeprefix("v")
    pin = re.split(r"-(?:alpine|slim|bullseye|bookworm|buster|trixie|jammy|noble)", pin)[0]
    if "$" in pin:
        return None, f"node pin `{raw}` is a build argument, not a version"
    exact = SEMVER.match(pin)
    if exact:
        release = next((r for r in index if r["version"].lstrip("v") == exact.group(1)), None)
        return (release, "") if release else (None, f"node {exact.group(1)} is not in the Node release index")
    if pin in ("lts", "lts/*", "lts-alpine", "lts-slim"):
        candidates = [r for r in index if r.get("lts")]
    elif pin.startswith("lts/"):
        codename = pin.split("/", 1)[1]
        candidates = [r for r in index if str(r.get("lts") or "").lower() == codename]
    elif pin in ("node", "current", "latest", "stable"):
        candidates = list(index)
    elif re.fullmatch(r"\d+(?:\.\d+)?", pin):
        candidates = [r for r in index if r["version"].lstrip("v").startswith(pin + ".")]
    else:
        return None, f"node pin `{raw}` is a range, not a version"
    if not candidates:
        return None, f"node pin `{raw}` matches no release in the Node index"
    release = max(candidates, key=lambda r: version_key(r["version"]))
    return release, f"floating pin `{raw}` resolved to the newest match; the deployed build may be older"


def local_node_version():
    try:
        output = subprocess.run(["node", "--version"], capture_output=True, text=True, timeout=10, check=True)
    except (OSError, subprocess.SubprocessError):
        return None
    return output.stdout.strip()


def resolve_node_runtime(spec, tree, feeds):
    pins = [(raw, relative(tree, path)) for raw, path in node_pins(tree)]
    if not pins and tree.package_jsons:
        local = local_node_version()
        if local:
            pins = [(local, "local `node --version` (no pin in the project)")]
    if not pins:
        return
    index = feeds.node_index()
    for raw, evidence in sorted(set(pins)):
        release, note = resolve_node_pin(raw, index)
        if release is None:
            yield Unassessed(spec["name"], "node", raw, evidence, note)
            continue
        node_version = release["version"].lstrip("v")
        for field_name, component in spec["components"].items():
            value = node_version if field_name == "node" else leading_version(release.get(field_name) or "")
            if value:
                yield Component(spec["name"], node_version, component, value, evidence, note)


def resolve_python_runtime(spec, tree, feeds):
    interpreters = [(str(p), relative(tree, p)) for p in tree.venv_pythons]
    if not interpreters and (tree.python_lockfiles or tree.requirements or tree.pyprojects):
        interpreters = [(sys.executable, "the python3 running this script (no project virtualenv)")]
    for interpreter, evidence in interpreters:
        try:
            result = subprocess.run(
                [interpreter, "-I", "-c", "import ssl,sys;print(sys.version.split()[0]);print(ssl.OPENSSL_VERSION)"],
                capture_output=True, text=True, timeout=20, check=True)
        except (OSError, subprocess.SubprocessError) as error:
            yield Unassessed(spec["name"], "openssl", "", evidence, f"could not run the interpreter: {error}")
            continue
        python_version, banner = (result.stdout.splitlines() + ["", ""])[:2]
        match = re.match(r"OpenSSL (\d+\.\d+\.\d+[a-z]?)", banner)
        if match:
            yield Component(spec["name"], python_version, spec["components"]["openssl"], match.group(1), evidence)
        else:
            yield Unassessed(spec["name"], "ssl", banner, evidence, "the ssl module is not linked against OpenSSL")


def resolve_binary_banners(spec, tree, feeds):
    patterns = {name: re.compile(regex.encode()) for name, regex in spec["banners"].items()}
    limit = feeds.limits["binary_scan_max_bytes"]
    for site_packages in tree.site_packages:
        for glob in spec["paths"]:
            for binary in sorted(site_packages.glob(glob)):
                if not binary.is_file() or binary.stat().st_size > limit:
                    continue
                owner = binary.relative_to(site_packages).parts[0].removesuffix(".libs")
                content = binary.read_bytes()
                for name, pattern in patterns.items():
                    match = pattern.search(content)
                    if match:
                        yield Component(owner, "", spec["components"][name], match.group(1).decode(),
                                        relative(tree, binary), "version read from the bundled binary")


RESOLVERS = {
    "playwright_browsers": resolve_playwright_browsers,
    "puppeteer_revisions": resolve_puppeteer_revisions,
    "electron_release": resolve_electron_release,
    "versions_manifest": resolve_versions_manifest,
    "node_runtime": resolve_node_runtime,
    "python_runtime": resolve_python_runtime,
    "binary_banners": resolve_binary_banners,
}


def embedded(registry, tree, feeds, errors):
    components, unassessed = [], []
    for spec in registry["embedders"]:
        try:
            for result in RESOLVERS[spec["resolver"]](spec, tree, feeds):
                (components if isinstance(result, Component) else unassessed).append(result)
        except (OSError, ValueError, urllib.error.URLError) as error:
            errors.append(f"{spec['name']}: {error}")
            unassessed.append(Unassessed(spec["name"], "*", "", "", f"resolver failed: {error}"))
    return components, unassessed


# ----------------------------------------------------------------------------- ranking and assembly


def rank_key(finding):
    return (not finding.get("kev"), -(finding.get("epss") or 0.0), -(finding.get("cvss") or 0.0), finding["id"])


def osv_fixed(vuln, package):
    fixes = []
    for affected in vuln.get("affected", []):
        named = affected.get("package", {})
        if named.get("ecosystem") != package.ecosystem:
            continue
        name = normalise_pypi(named.get("name", "")) if package.ecosystem == "PyPI" else named.get("name")
        if name != package.name:
            continue
        for affected_range in affected.get("ranges", []):
            fixes.extend(e["fixed"] for e in affected_range.get("events", []) if "fixed" in e)
    later = [f for f in fixes if version_key(f) > version_key(package.version)]
    return min(later, key=version_key) if later else None


def trim_osv(vuln, package, summary_chars):
    aliases = vuln.get("aliases", [])
    cves = sorted({i for i in [vuln["id"], *aliases] if i.startswith("CVE-")})
    severity = (vuln.get("database_specific") or {}).get("severity")
    text = " ".join((vuln.get("summary") or vuln.get("details") or "").split())
    return {
        "id": vuln["id"],
        "cves": cves,
        "severity": severity,
        "cvss": SEVERITY_RANK.get(str(severity).upper()),
        "fixed_in": osv_fixed(vuln, package),
        "summary": text if len(text) <= summary_chars else text[: summary_chars - 1].rstrip() + "…",
    }


def assess_packages(packages, feeds, errors):
    if not packages:
        return [], []
    ordered = sorted(packages, key=lambda p: (p.ecosystem, p.name, version_key(p.version)))
    try:
        ids_per_package = feeds.osv_ids(ordered)
    except (urllib.error.URLError, ValueError, OSError) as error:
        errors.append(f"OSV: {error}")
        return [], [Unassessed("packages", "*", "", "", f"OSV lookup failed: {error}")]
    unique = sorted({i for ids in ids_per_package for i in ids})
    details, failed = {}, []
    with concurrent.futures.ThreadPoolExecutor(feeds.limits["osv_workers"]) as pool:
        futures = {pool.submit(feeds.osv_vuln, vuln_id): vuln_id for vuln_id in unique}
        for future in concurrent.futures.as_completed(futures):
            try:
                details[futures[future]] = future.result()
            except (urllib.error.URLError, ValueError, OSError) as error:
                failed.append(futures[future])
                errors.append(f"OSV {futures[future]}: {error}")
    findings = []
    for package, ids in zip(ordered, ids_per_package):
        vulns = [trim_osv(details[i], package, feeds.limits["summary_chars"]) for i in ids if i in details]
        if vulns or any(i in failed for i in ids):
            findings.append({"ecosystem": package.ecosystem, "name": package.name,
                             "version": package.version, "evidence": packages[package], "vulns": vulns})
    return findings, []


def assess_components(components, registry, feeds, errors):
    grouped = {}
    for c in components:
        key = (c.embedder, c.embedder_version, c.component, c.version)
        entry = grouped.setdefault(key, {"evidence": set(), "notes": set()})
        entry["evidence"].add(c.evidence)
        if c.note:
            entry["notes"].add(c.note)
    results, unassessed, lookups = [], [], {}
    for (embedder, embedder_version, component, version), entry in sorted(grouped.items()):
        product = registry["cpe"].get(component)
        evidence = sorted(entry["evidence"])
        if product is None:
            unassessed.append(Unassessed(embedder, component, version, ", ".join(evidence),
                                         "no CPE mapping in embeddings.json"))
            continue
        lookup = (product, version)
        if lookup not in lookups:
            try:
                lookups[lookup] = feeds.nvd_for(product, version)
            except (urllib.error.URLError, ValueError, OSError) as error:
                lookups[lookup] = None
                errors.append(f"NVD {product} {version}: {error}")
        cves = lookups[lookup]
        if cves is None:
            unassessed.append(Unassessed(embedder, component, version, ", ".join(evidence),
                                         "NVD lookup failed, so this is unknown, not clean"))
            continue
        results.append({"embedder": embedder, "embedder_version": embedder_version, "component": component,
                        "cpe": f"cpe:2.3:a:{product}:{version}", "version": version, "evidence": evidence,
                        "notes": sorted(entry["notes"]), "cves": [dict(c) for c in cves]})
    return results, unassessed


def enrich(embedded_results, package_findings, feeds, errors, top):
    all_cves = {c["id"] for r in embedded_results for c in r["cves"]}
    all_cves |= {cve for f in package_findings for v in f["vulns"] for cve in v["cves"]}
    try:
        kev = feeds.kev_ids()
    except (urllib.error.URLError, ValueError, OSError) as error:
        kev = set()
        errors.append(f"CISA KEV: {error}")
    try:
        epss = feeds.epss(all_cves) if all_cves else {}
    except (urllib.error.URLError, ValueError, OSError) as error:
        epss = {}
        errors.append(f"EPSS: {error}")

    for result in embedded_results:
        for cve in result["cves"]:
            cve["kev"] = cve["kev"] or cve["id"] in kev
            cve["epss"] = epss.get(cve["id"])
        ranked = sorted(result["cves"], key=rank_key)
        fixes = [c["fixed_in"] for c in ranked if c["fixed_in"]]
        kev_fixes = [c["fixed_in"] for c in ranked if c["kev"] and c["fixed_in"]]
        result.update({
            "cve_count": len(ranked),
            "kev_count": sum(c["kev"] for c in ranked),
            "top_epss": max((c["epss"] or 0.0 for c in ranked), default=0.0),
            "max_cvss": max((c["cvss"] or 0.0 for c in ranked), default=0.0),
            "unfixed_count": sum(not c["fixed_in"] for c in ranked),
            "clears_all_at": max(fixes, key=version_key) if fixes else None,
            "clears_kev_at": max(kev_fixes, key=version_key) if kev_fixes else None,
            "cves": ranked if top == 0 else ranked[:top],
        })
    embedded_results.sort(key=lambda r: (-r["kev_count"], -r["top_epss"], -r["max_cvss"], r["embedder"]))

    for finding in package_findings:
        for vuln in finding["vulns"]:
            vuln["kev"] = any(cve in kev for cve in vuln["cves"])
            vuln["epss"] = max((epss.get(cve, 0.0) for cve in vuln["cves"]), default=None)
        finding["vulns"].sort(key=rank_key)
    package_findings.sort(key=lambda f: rank_key(f["vulns"][0]) if f["vulns"] else (True, 0, 0, f["name"]))


def scan(root, registry, feeds, top, include_packages=True, include_embedded=True):
    errors = []
    tree = walk(root)
    packages = inventory(tree) if include_packages else {}
    package_findings, unassessed = assess_packages(packages, feeds, errors)
    embedded_results = []
    if include_embedded:
        components, component_gaps = embedded(registry, tree, feeds, errors)
        embedded_results, lookup_gaps = assess_components(components, registry, feeds, errors)
        unassessed += component_gaps + lookup_gaps
    enrich(embedded_results, package_findings, feeds, errors, top)
    return {
        "repo": str(root),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "packages": {"inventoried": len(packages), "vulnerable": len(package_findings),
                     "findings": package_findings},
        "embedded": embedded_results,
        "not_assessed": [vars(u) for u in sorted(set(unassessed), key=lambda u: (u.embedder, u.component))],
        "errors": errors,
    }


# ----------------------------------------------------------------------------- rendering


def fmt_epss(value):
    return f"{value:.2f}" if value is not None else "-"


def cve_line(cve):
    flags = "KEV " if cve.get("kev") else ""
    fixed = f", fixed in {cve['fixed_in']}" if cve.get("fixed_in") else ""
    return f"{flags}{cve['id']} cvss {cve.get('cvss') or '-'} epss {fmt_epss(cve.get('epss'))}{fixed}"


def render_scan(report, sample):
    ui.title(f"🛡️ Vulnerabilities reaching {ui.path(report['repo'])}")
    if report["embedded"]:
        ui.blank()
        ui.title("Bundled components")
        for r in report["embedded"]:
            owner = f"{r['embedder']} {r['embedder_version']}".strip()
            clears = f", clears all at {r['clears_all_at']}" if r["clears_all_at"] else ""
            kev_clear = f", clears KEV at {r['clears_kev_at']}" if r["clears_kev_at"] else ""
            ui.item(f"{owner} → {r['component']} {r['version']}: {r['cve_count']} CVEs, "
                    f"{r['kev_count']} KEV, top EPSS {fmt_epss(r['top_epss'])}{kev_clear}{clears}")
            for cve in r["cves"][:sample]:
                ui.note(cve_line(cve), indent=6)
    vulnerable = report["packages"]["findings"]
    ui.blank()
    ui.title(f"Packages ({report['packages']['inventoried']} inventoried)")
    if not vulnerable:
        ui.ok("No OSV advisories for the inventoried versions")
    for finding in vulnerable:
        ui.item(f"{finding['ecosystem']} {finding['name']} {finding['version']}: {len(finding['vulns'])} advisories")
        for vuln in finding["vulns"][:sample]:
            ids = ", ".join(vuln["cves"]) or vuln["id"]
            fixed = f", fixed in {vuln['fixed_in']}" if vuln["fixed_in"] else ""
            ui.note(f"{'KEV ' if vuln['kev'] else ''}{ids} {vuln['severity'] or '-'} "
                    f"epss {fmt_epss(vuln['epss'])}{fixed}", indent=6)
    if report["not_assessed"]:
        ui.blank()
        ui.title("Not assessed")
        for gap in report["not_assessed"]:
            ui.warn(f"{gap['embedder']} → {gap['component']} {gap['version']}: {gap['reason']}".replace("  ", " "))
    for error in report["errors"]:
        ui.err(error)
    total = sum(r["cve_count"] for r in report["embedded"])
    kev = sum(r["kev_count"] for r in report["embedded"])
    ui.done(f"{total} CVEs in {len(report['embedded'])} bundled components ({kev} KEV), "
            f"{len(vulnerable)} vulnerable packages, {len(report['not_assessed'])} not assessed")


def describe_cve(cve, kev, epss, summary_chars):
    score, severity = cvss_of(cve)
    affected = []
    for match in cpe_matches(cve):
        if match.get("vulnerable"):
            bounds = {k: v for k, v in match.items() if k.startswith("version")}
            affected.append({"criteria": match["criteria"], **bounds})
    return {
        "id": cve["id"],
        "status": cve.get("vulnStatus"),
        "published": cve.get("published", "")[:10],
        "cvss": score,
        "severity": severity,
        "kev": bool(cve.get("cisaExploitAdd")) or cve["id"] in kev,
        "epss": epss.get(cve["id"]),
        "summary": english(cve.get("descriptions", []), summary_chars * 5),
        "affected": affected,
        "references": [r["url"] for r in cve.get("references", [])],
    }


def render_cve(detail):
    ui.title(f"🔎 {detail['id']} ({detail['status']}, published {detail['published']})")
    ui.note(detail["summary"], indent=0)
    ui.item(f"cvss {detail['cvss'] or '-'} {detail['severity'] or ''}, epss {fmt_epss(detail['epss'])}"
            f"{', in CISA KEV' if detail['kev'] else ''}")
    for match in detail["affected"]:
        bounds = ", ".join(f"{k} {v}" for k, v in match.items() if k != "criteria")
        ui.item(f"{match['criteria']}{' (' + bounds + ')' if bounds else ''}")
    for url in detail["references"]:
        ui.note(url)


# ----------------------------------------------------------------------------- cli


def build_feeds(registry, refresh):
    limits = registry["limits"]
    cache = Cache(default_cache_root(), limits["cache_ttl_seconds"], refresh=refresh)
    return Feeds(registry, Http(limits), cache, api_key=os.environ.get(API_KEY_ENV) or None)


def main(argv=None, registry=None, feeds=None):
    registry = registry or load_registry()
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    scan_cmd = sub.add_parser("scan", help="inventory a repository and report every CVE that reaches it")
    scan_cmd.add_argument("path", type=Path)
    scan_cmd.add_argument("--json", action="store_true", help="machine-readable report")
    scan_cmd.add_argument("--top", type=int, default=registry["limits"]["default_top"],
                          help="ranked CVEs kept per bundled component (0 keeps all)")
    scan_cmd.add_argument("--packages-only", action="store_true")
    scan_cmd.add_argument("--embedded-only", action="store_true")
    scan_cmd.add_argument("--refresh", action="store_true", help="ignore cached responses")
    cve_cmd = sub.add_parser("cve", help="detail for one CVE id")
    cve_cmd.add_argument("cve_id")
    cve_cmd.add_argument("--json", action="store_true")
    cve_cmd.add_argument("--refresh", action="store_true")
    args = parser.parse_args(argv)
    feeds = feeds or build_feeds(registry, args.refresh)

    if args.command == "cve":
        cve = feeds.nvd_cve(args.cve_id.upper())
        if cve is None:
            ui.err(f"NVD has no record for {args.cve_id}")
            return EXIT_USAGE
        detail = describe_cve(cve, feeds.kev_ids(), feeds.epss([cve["id"]]), registry["limits"]["summary_chars"])
        print(json.dumps(detail, indent=2)) if args.json else render_cve(detail)
        return EXIT_OK

    root = args.path.expanduser().resolve()
    if not root.is_dir():
        ui.err(f"Not a directory: {ui.path(root)}")
        return EXIT_USAGE
    report = scan(root, registry, feeds, args.top, include_packages=not args.embedded_only,
                  include_embedded=not args.packages_only)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        render_scan(report, sample=3)
    return EXIT_PARTIAL if report["errors"] else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
