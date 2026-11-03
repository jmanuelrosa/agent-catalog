"""`vuln_lookup.py`: inventory, embedded-component resolution, NVD range filtering and ranking.

Every case builds a repository under `tmp_path` and answers the network from a fake keyed
by URL, so the suite runs offline and pins the request count. The cases that matter most
are the false cleans: a component that cannot be mapped, or a lookup that failed, must
surface as not assessed rather than vanish from the report.
"""

import importlib.util
import json
import sys
import urllib.error
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "vuln_lookup.py"
REGISTRY = SCRIPT.parent / "embeddings.json"


def _load():
    spec = importlib.util.spec_from_file_location("vuln_lookup", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    cached = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = cached
    return module


vl = _load()


def nvd_cve(cve_id, criteria, score=5.0, kev=False, **bounds):
    cve = {
        "id": cve_id,
        "published": "2026-10-01T00:00:00.000",
        "vulnStatus": "Analyzed",
        "descriptions": [{"lang": "en", "value": f"{cve_id} description"}],
        "metrics": {"cvssMetricV31": [{"cvssData": {"baseScore": score, "baseSeverity": "HIGH"}}]},
        "configurations": [{"nodes": [{"cpeMatch": [{"vulnerable": True, "criteria": criteria, **bounds}]}]}],
    }
    if kev:
        cve["cisaExploitAdd"] = "2026-10-02"
    return {"cve": cve}


CHROME = "cpe:2.3:a:google:chrome:*:*:*:*:*:*:*:*"


class FakeHttp:
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def json(self, url, body=None, headers=None):
        self.calls.append(url)
        for prefix, answer in self.routes.items():
            if url.startswith(prefix):
                return answer(url, body) if callable(answer) else answer
        raise AssertionError(f"unexpected request {url}")


class NoCache:
    def fetch(self, key, produce):
        return produce()


def make_feeds(routes, registry, clock=None, sleeps=None):
    times = iter(clock or [0.0] * 1000)
    return vl.Feeds(registry, FakeHttp(routes), NoCache(), clock=lambda: next(times),
                    sleep=(sleeps.append if sleeps is not None else lambda _: None))


@pytest.fixture
def registry():
    return json.loads(REGISTRY.read_text())


def base_routes(registry, nvd=None, osv=None):
    sources = registry["sources"]
    return {
        sources["nvd_cves"]: nvd or {"totalResults": 0, "vulnerabilities": []},
        sources["kev"]: {"vulnerabilities": []},
        sources["epss"]: {"data": []},
        sources["osv_querybatch"]: osv or (lambda url, body: {"results": [{} for _ in body["queries"]]}),
        sources["node_index"]: [],
    }


def playwright_repo(root, chromium="140.0.7339.16"):
    package = root / "node_modules" / "playwright-core"
    package.mkdir(parents=True)
    (package / "package.json").write_text(json.dumps({"name": "playwright-core", "version": "1.55.0"}))
    (package / "browsers.json").write_text(json.dumps({"browsers": [
        {"name": "chromium", "browserVersion": chromium},
        {"name": "chromium-headless-shell", "browserVersion": chromium},
        {"name": "webkit", "browserVersion": "26.0"},
        {"name": "ffmpeg", "browserVersion": None},
    ]}))
    return root


def test_a_chrome_cve_is_attributed_to_playwright_and_out_of_range_ones_are_dropped(tmp_path, registry):
    playwright_repo(tmp_path)
    nvd = {"totalResults": 2, "vulnerabilities": [
        nvd_cve("CVE-2026-0001", CHROME, versionEndExcluding="141.0.7390.54"),
        nvd_cve("CVE-2026-0002", CHROME, versionEndExcluding="139.0.0.0"),
    ]}
    feeds = make_feeds(base_routes(registry, nvd=nvd), registry)
    report = vl.scan(tmp_path, registry, feeds, top=20, include_packages=False)

    [chrome] = report["embedded"]
    assert (chrome["embedder"], chrome["embedder_version"], chrome["component"]) == ("playwright", "1.55.0", "chrome")
    assert [c["id"] for c in chrome["cves"]] == ["CVE-2026-0001"]
    assert chrome["clears_all_at"] == "141.0.7390.54"
    nvd_calls = [c for c in feeds.http.calls if c.startswith(registry["sources"]["nvd_cves"])]
    assert len(nvd_calls) == 1, "chromium and the headless shell share one version, so one lookup"
    assert "virtualMatchString=cpe:2.3:a:google:chrome:140.0.7339.16" in nvd_calls[0]


def test_webkit_is_reported_not_assessed_rather_than_clean(tmp_path, registry):
    playwright_repo(tmp_path)
    report = vl.scan(tmp_path, registry, make_feeds(base_routes(registry), registry), top=20,
                     include_packages=False)
    assert {(g["embedder"], g["component"]) for g in report["not_assessed"]} == {("playwright", "webkit")}


def test_a_failed_nvd_lookup_is_an_error_and_a_gap_not_an_empty_result(tmp_path, registry):
    playwright_repo(tmp_path)

    def down(url, body):
        raise urllib.error.URLError("unreachable")

    feeds = make_feeds(base_routes(registry, nvd=down), registry)
    report = vl.scan(tmp_path, registry, feeds, top=20, include_packages=False)
    assert report["embedded"] == []
    assert report["errors"]
    assert any(g["component"] == "chrome" and "not clean" in g["reason"] for g in report["not_assessed"])


def test_no_trigger_package_means_no_lookup(tmp_path, registry):
    (tmp_path / "README.md").write_text("nothing installed")
    feeds = make_feeds(base_routes(registry), registry)
    report = vl.scan(tmp_path, registry, feeds, top=20)
    assert report["embedded"] == [] and report["not_assessed"] == []
    assert not any(c.startswith(registry["sources"]["nvd_cves"]) for c in feeds.http.calls)


def test_kev_outranks_a_higher_cvss():
    findings = [
        {"id": "CVE-A", "kev": False, "epss": 0.9, "cvss": 9.8},
        {"id": "CVE-B", "kev": True, "epss": 0.1, "cvss": 6.5},
        {"id": "CVE-C", "kev": False, "epss": 0.95, "cvss": 4.0},
    ]
    assert [f["id"] for f in sorted(findings, key=vl.rank_key)] == ["CVE-B", "CVE-C", "CVE-A"]


def test_nvd_pages_until_total_and_throttles_between_requests(registry):
    pages = iter([
        {"totalResults": 3, "vulnerabilities": [nvd_cve("CVE-1", CHROME), nvd_cve("CVE-2", CHROME)]},
        {"totalResults": 3, "vulnerabilities": [nvd_cve("CVE-3", CHROME)]},
    ])
    sleeps = []
    routes = {registry["sources"]["nvd_cves"]: lambda url, body: next(pages)}
    feeds = make_feeds(routes, registry, clock=[0.0, 1.0, 6.0], sleeps=sleeps)
    found = feeds.nvd_for("google:chrome", "140.0.0.0")
    assert [c["id"] for c in found] == ["CVE-1", "CVE-2", "CVE-3"]
    rate = registry["limits"]["nvd_anonymous"]
    assert sleeps == [pytest.approx(rate["window_seconds"] / rate["requests"] - 1.0)]


@pytest.mark.parametrize("match, covered", [
    ({"criteria": CHROME, "vulnerable": True, "versionEndExcluding": "141.0"}, True),
    ({"criteria": CHROME, "vulnerable": False, "versionEndExcluding": "141.0"}, False),
    ({"criteria": CHROME, "vulnerable": True, "versionStartIncluding": "141.0"}, False),
    ({"criteria": "cpe:2.3:a:google:chrome:140.0.1:*:*:*:*:*:*:*", "vulnerable": True}, True),
    ({"criteria": "cpe:2.3:a:mozilla:firefox:*:*:*:*:*:*:*:*", "vulnerable": True}, False),
])
def test_match_covers_honours_vulnerable_flag_product_and_bounds(match, covered):
    assert vl.match_covers(match, "google:chrome", "140.0.1") is covered


def test_openssl_letter_releases_sort_after_their_base():
    assert vl.version_key("1.1.1w") > vl.version_key("1.1.1")
    assert vl.version_key("1.1.10") > vl.version_key("1.1.1w")


def test_a_release_written_with_fewer_zeros_is_not_older_than_its_fix():
    match = {"criteria": "cpe:2.3:a:mozilla:firefox:*:*:*:*:*:*:*:*", "vulnerable": True,
             "versionEndExcluding": "157.0.0"}
    assert not vl.match_covers(match, "mozilla:firefox", "157.0")


def test_lockfiles_feed_the_package_inventory(tmp_path):
    (tmp_path / "package-lock.json").write_text(json.dumps({"lockfileVersion": 3, "packages": {
        "": {"name": "app"},
        "node_modules/lodash": {"version": "4.17.20"},
        "node_modules/a/node_modules/@scope/b": {"version": "1.0.0"},
        "packages/local": {"link": True},
    }}))
    (tmp_path / "pnpm-lock.yaml").write_text(
        "lockfileVersion: '9.0'\n\npackages:\n\n  '@babel/core@7.24.0':\n    resolution: {}\n"
        "  minimist@1.2.5:\n    resolution: {}\n\nsnapshots:\n\n  minimist@1.2.5: {}\n")
    (tmp_path / "yarn.lock").write_text(
        '"@types/node@^20", "@types/node@^20.1":\n  version "20.11.0"\n\n'
        'left-pad@npm:^1.0.0:\n  version: 1.3.0\n')
    (tmp_path / "requirements.txt").write_text("Django==4.2.1\nrequests[socks]==2.31.0 ; python_version > '3'\nflask>=2\n")
    found = set(vl.inventory(vl.walk(tmp_path)))
    assert {
        vl.Package("npm", "lodash", "4.17.20"), vl.Package("npm", "@scope/b", "1.0.0"),
        vl.Package("npm", "@babel/core", "7.24.0"), vl.Package("npm", "minimist", "1.2.5"),
        vl.Package("npm", "@types/node", "20.11.0"), vl.Package("npm", "left-pad", "1.3.0"),
        vl.Package("PyPI", "django", "4.2.1"), vl.Package("PyPI", "requests", "2.31.0"),
    } <= found
    assert not any(p.name == "flask" for p in found), "a range is not an installed version"


def test_osv_findings_carry_cves_kev_and_the_nearest_fix(tmp_path, registry):
    (tmp_path / "requirements.txt").write_text("django==4.2.1\n")
    sources = registry["sources"]
    routes = base_routes(registry, osv=lambda url, body: {"results": [{"vulns": [{"id": "GHSA-x"}]}]})
    routes[sources["osv_vuln"]] = {
        "id": "GHSA-x", "aliases": ["CVE-2026-1111"], "summary": "SQL injection",
        "database_specific": {"severity": "HIGH"},
        "affected": [{"package": {"ecosystem": "PyPI", "name": "Django"},
                      "ranges": [{"events": [{"introduced": "0"}, {"fixed": "4.2.2"}, {"fixed": "3.0"}]}]}],
    }
    routes[sources["kev"]] = {"vulnerabilities": [{"cveID": "CVE-2026-1111"}]}
    report = vl.scan(tmp_path, registry, make_feeds(routes, registry), top=20, include_embedded=False)
    [finding] = report["packages"]["findings"]
    [vuln] = finding["vulns"]
    assert (vuln["cves"], vuln["kev"], vuln["fixed_in"]) == (["CVE-2026-1111"], True, "4.2.2")
    assert finding["evidence"] == ["requirements.txt"]


def test_a_floating_docker_node_tag_resolves_through_the_index(tmp_path, registry):
    (tmp_path / "Dockerfile").write_text("FROM node:22-alpine AS build\n")
    routes = base_routes(registry)
    routes[registry["sources"]["node_index"]] = [
        {"version": "v23.1.0", "openssl": "3.0.15+quic", "zlib": "1.3.0.1-motley", "uv": "1.48.0", "lts": False},
        {"version": "v22.11.0", "openssl": "3.0.15+quic", "zlib": "1.3.0.1-motley", "uv": "1.48.0", "lts": "Jod"},
        {"version": "v22.9.0", "openssl": "3.0.13+quic", "zlib": "1.3.0.1-motley", "uv": "1.46.0", "lts": False},
    ]
    feeds = make_feeds(routes, registry)
    components = [c for c in vl.embedded(registry, vl.walk(tmp_path), feeds, [])[0] if c.embedder == "node-runtime"]
    assert {(c.component, c.version) for c in components} == {
        ("node", "22.11.0"), ("openssl", "3.0.15"), ("zlib", "1.3.0.1"), ("libuv", "1.48.0")}
    assert all("floating pin" in c.note for c in components)


def test_an_engines_range_is_not_guessed_into_a_version(registry):
    release, reason = vl.resolve_node_pin(">=20 <23", [{"version": "v22.11.0"}])
    assert release is None and "range" in reason


def test_openssl_is_read_from_a_bundled_wheel_binary(tmp_path, registry):
    site = tmp_path / ".venv" / "lib" / "python3.12" / "site-packages"
    bindings = site / "cryptography" / "hazmat" / "bindings"
    bindings.mkdir(parents=True)
    (tmp_path / ".venv" / "pyvenv.cfg").write_text("home = /usr/bin\n")
    (bindings / "_rust.abi3.so").write_bytes(b"\x00\x01OpenSSL 3.2.1 30 Jan 2024\x00tail")
    tree = vl.walk(tmp_path)
    [spec] = [s for s in registry["embedders"] if s["resolver"] == "binary_banners"]
    [component] = vl.resolve_binary_banners(spec, tree, make_feeds(base_routes(registry), registry))
    assert (component.embedder, component.component, component.version) == ("cryptography", "openssl", "3.2.1")


def test_sharp_libraries_without_a_cpe_are_listed_as_gaps(tmp_path, registry):
    package = tmp_path / "node_modules" / "@img" / "sharp-libvips-darwin-arm64"
    package.mkdir(parents=True)
    (package / "package.json").write_text(json.dumps({"version": "1.2.0"}))
    (package / "versions.json").write_text(json.dumps({"vips": "8.16.0", "mozjpeg": "0826579"}))
    [spec] = [s for s in registry["embedders"] if s["name"] == "sharp"]
    results = list(vl.resolve_versions_manifest(spec, vl.walk(tmp_path), None))
    assert {type(r).__name__ for r in results} == {"Component", "Unassessed"}
    assert next(r for r in results if isinstance(r, vl.Component)).component == "libvips"


def test_every_mapped_component_has_a_cpe(registry):
    mapped = {c for spec in registry["embedders"] for c in spec["components"].values()}
    assert mapped <= set(registry["cpe"])
    assert {spec["resolver"] for spec in registry["embedders"]} <= set(vl.RESOLVERS)
