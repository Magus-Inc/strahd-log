"""The script rule (AGENTS.md): the site runs its own JavaScript plus libraries copied into
static/vendor/ and listed in data/vendor.yaml. Nothing loads from another site."""
import gzip
import hashlib
import random
import re
from pathlib import Path

import pytest
import yaml

import build
import vendor_check

ROOT = Path(__file__).resolve().parent.parent
LIB = b"window.tiny = function (x) { return x + 1; };\n"
MIT = "MIT License\n\nCopyright (c) 2024 Someone\n"


def write_lib(root: Path, body: bytes = LIB, **override) -> dict:
    vendor = root / "static" / "vendor"
    vendor.mkdir(parents=True, exist_ok=True)
    (vendor / "tiny-1.2.3.min.js").write_bytes(body)
    (vendor / "tiny-LICENSE.txt").write_text(MIT, encoding="utf-8")
    entry = {"name": "tiny", "version": "1.2.3", "npm": "tiny", "file": "tiny-1.2.3.min.js",
             "license": "MIT", "license_file": "tiny-LICENSE.txt",
             "source": "https://registry.npmjs.org/tiny/-/tiny-1.2.3.tgz",
             "sha256": hashlib.sha256(body).hexdigest(), "why": "Example."}
    entry.update(override)
    (root / "data").mkdir(exist_ok=True)
    (root / "data" / "vendor.yaml").write_text(yaml.safe_dump({"libraries": [entry]}), encoding="utf-8")
    return entry


def test_a_listed_library_with_its_license_passes(tmp_path):
    write_lib(tmp_path)
    assert vendor_check.problems(tmp_path) == []


def test_no_vendor_folder_and_no_list_is_fine(tmp_path):
    assert vendor_check.problems(tmp_path) == []


def test_a_changed_file_is_caught_by_its_fingerprint(tmp_path):
    write_lib(tmp_path)
    (tmp_path / "static" / "vendor" / "tiny-1.2.3.min.js").write_bytes(LIB + b"steal();\n")
    assert any("sha256" in p for p in vendor_check.problems(tmp_path))


def test_an_unlisted_file_in_vendor_is_refused(tmp_path):
    write_lib(tmp_path)
    (tmp_path / "static" / "vendor" / "sneaky.js").write_text("x()", encoding="utf-8")
    assert any("sneaky.js" in p and "not listed" in p for p in vendor_check.problems(tmp_path))


@pytest.mark.parametrize("license", ["GPL-3.0", "AGPL-3.0", "LGPL-2.1", "unknown", ""])
def test_only_permissive_licenses_are_allowed(tmp_path, license):
    write_lib(tmp_path, license=license)
    assert any("license" in p for p in vendor_check.problems(tmp_path))


def test_the_license_text_must_sit_next_to_the_library(tmp_path):
    write_lib(tmp_path)
    (tmp_path / "static" / "vendor" / "tiny-LICENSE.txt").unlink()
    assert any("tiny-LICENSE.txt" in p for p in vendor_check.problems(tmp_path))


def test_a_library_over_the_phone_size_budget_is_refused(tmp_path):
    big = random.Random(1).randbytes(40_000)  # random bytes do not compress
    assert len(gzip.compress(big)) > vendor_check.MAX_GZIP_BYTES
    write_lib(tmp_path, body=big)
    assert any("KB zipped" in p for p in vendor_check.problems(tmp_path))


def test_every_entry_says_where_it_came_from_and_why(tmp_path):
    write_lib(tmp_path, source="", why="")
    found = vendor_check.problems(tmp_path)
    assert any("source" in p for p in found) and any("why" in p for p in found)


def test_the_repos_own_vendor_list_passes():
    assert vendor_check.problems(ROOT) == []


def test_advisories_are_looked_up_per_listed_version(tmp_path):
    write_lib(tmp_path)
    asked = []

    def fake_osv(package, version):
        asked.append((package, version))
        return [{"id": "GHSA-xxxx", "summary": "Prototype pollution"}]

    found = vendor_check.advisories(tmp_path, query=fake_osv)
    assert asked == [("tiny", "1.2.3")]
    assert found == ["tiny 1.2.3: GHSA-xxxx Prototype pollution"]


# The built site: every script, stylesheet and font is ours.

@pytest.fixture(scope="module")
def site(tmp_path_factory):
    out = tmp_path_factory.mktemp("site") / "public"
    build.build(out_dir=out, site_url="https://owlbear.dicelore.quest", base_path="/")
    return out


def outside(url: str) -> bool:
    """True for an address on another site (https://..., //...); the GoatCounter pixel is the one allowed."""
    url = url.strip()
    return bool(re.match(r"(?i)^(?:[a-z][a-z0-9+.-]*:)?//", url)) and ".goatcounter.com/" not in url


def test_outside_tells_our_files_from_other_sites():
    assert outside("https://cdn.jsdelivr.net/npm/x@1/x.js") and outside("//unpkg.com/x")
    assert not outside("/vendor/minisearch-7.1.0.js") and not outside("./x.js") and not outside("data:,x")
    assert not outside("https://owlbear.goatcounter.com/count?p=")


def test_the_site_loads_no_script_style_or_font_from_another_site(site):
    found = []
    for page in site.rglob("*.html"):
        html = page.read_text(encoding="utf-8")
        for tag in re.findall(r"<(?:script|link|iframe)\b[^>]*>", html, flags=re.I):
            for url in re.findall(r'\b(?:src|href)\s*=\s*["\']?([^"\'\s>]+)', tag, flags=re.I):
                if outside(url) and not re.search(r'rel=["\']?(?:canonical|alternate)', tag):
                    found.append(f"{page.relative_to(site).as_posix()}: {tag}")
        for code in re.findall(r"<script\b[^>]*>(.*?)</script>", html, flags=re.S | re.I):
            # Code a script pulls in itself (ES imports, workers, fetch): fine from our site, never from another.
            for url in re.findall(r"""(?:\bimport\s*\(\s*|\bfrom\s+|\bimport\s+|importScripts\(\s*|\bfetch\(\s*|\.src\s*=\s*)['"`]([^'"`]+)""", code):
                if outside(url):
                    found.append(f"{page.relative_to(site).as_posix()}: script loads {url}")
    for css in site.rglob("*.css"):
        for url in re.findall(r"(?:url\(|@import\s+)['\"]?([^'\")\s;]+)", css.read_text(encoding="utf-8")):
            if outside(url):
                found.append(f"{css.relative_to(site).as_posix()}: {url}")
    assert not found, found[:20]


def test_every_script_file_the_site_loads_is_a_listed_library(site):
    listed = {e["file"] for e in vendor_check.entries(ROOT)}
    for page in site.rglob("*.html"):
        for src in re.findall(r'<script\b[^>]*\bsrc="([^"]+)"', page.read_text(encoding="utf-8")):
            name = src.split("?")[0].rstrip("/").split("/")[-1]
            assert "/vendor/" in src and name in listed, (page.relative_to(site).as_posix(), src)


def test_no_page_loads_more_than_the_page_budget_of_libraries(site):
    sizes = {e["file"]: len(gzip.compress((ROOT / "static" / "vendor" / e["file"]).read_bytes(), compresslevel=9))
             for e in vendor_check.entries(ROOT)}
    for page in site.rglob("*.html"):
        files = {s.split("?")[0].split("/")[-1] for s in re.findall(r'<script\b[^>]*\bsrc="([^"]+)"', page.read_text(encoding="utf-8"))}
        total = sum(sizes.get(f, 0) for f in files)
        assert total <= vendor_check.MAX_PAGE_GZIP_BYTES, (page.relative_to(site).as_posix(), total)


def test_monthly_workflow_checks_libraries_for_security_fixes():
    flow = yaml.safe_load((ROOT / ".github" / "workflows" / "vendor-check.yml").read_text(encoding="utf-8"))
    triggers = flow.get("on") or flow.get(True)
    assert "schedule" in triggers and "workflow_dispatch" in triggers
    assert flow["permissions"] == {"contents": "read", "issues": "write"}
    steps = "\n".join(str(s.get("run", "")) for s in flow["jobs"]["advisories"]["steps"])
    assert "tools/vendor_check.py --advisories" in steps
    assert "gh issue create" in steps
    assert "gh issue list" in steps and "gh issue comment" in steps  # one open issue, not a new one each month
