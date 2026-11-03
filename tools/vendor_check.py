"""Check the JavaScript libraries copied into static/vendor/ (the script rule in AGENTS.md).

Every file in static/vendor/ is listed in data/vendor.yaml with its version, where it came from, why
we use it, a permissive license whose text sits next to it, and the sha256 of the exact file, so a
copied library can only change through a PR that also changes its fingerprint. Each library stays
under the phone budget (MAX_GZIP_BYTES zipped).

    python tools/vendor_check.py               # list problems (the tests run this too)
    python tools/vendor_check.py --advisories  # ask osv.dev for known security problems (monthly workflow)
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
MAX_GZIP_BYTES = 30 * 1024        # one library
MAX_PAGE_GZIP_BYTES = 60 * 1024   # all libraries on one page together
# Permissive licenses only: the blog's code is all rights reserved, and copyleft (GPL family) terms
# would at least muddy that. MIT/BSD ask that the copyright notice travel with the code: the license
# file beside the library does that. Prefer the unminified build when it fits the budget (easier review).
LICENSES = {"MIT", "ISC", "BSD-2-Clause", "BSD-3-Clause", "Apache-2.0", "0BSD", "OFL-1.1"}
REQUIRED = ("name", "version", "file", "license", "license_file", "source", "sha256", "why")


def entries(root: Path = ROOT) -> list[dict]:
    path = root / "data" / "vendor.yaml"
    if not path.exists():
        return []
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("libraries") or []


def problems(root: Path = ROOT) -> list[str]:
    vendor = root / "static" / "vendor"
    found: list[str] = []
    listed: set[str] = set()
    for e in entries(root):
        name = e.get("name") or e.get("file") or "?"
        for key in REQUIRED:
            if not str(e.get(key) or "").strip():
                found.append(f"{name}: missing {key}")
        if e.get("license") and e["license"] not in LICENSES:
            found.append(f"{name}: license {e['license']} is not one of {sorted(LICENSES)}")
        for key in ("file", "license_file"):
            if e.get(key):
                listed.add(e[key])
                if not (vendor / e[key]).is_file():
                    found.append(f"{name}: static/vendor/{e[key]} is missing")
        lib = vendor / str(e.get("file") or "")
        if e.get("file") and lib.is_file():
            data = lib.read_bytes()
            if hashlib.sha256(data).hexdigest() != str(e.get("sha256") or "").strip().lower():
                found.append(f"{name}: sha256 does not match static/vendor/{e['file']}")
            zipped = len(gzip.compress(data, compresslevel=9))
            if zipped > MAX_GZIP_BYTES:
                found.append(f"{name}: {zipped / 1024:.1f} KB zipped, over the {MAX_GZIP_BYTES // 1024} KB phone budget")
    if vendor.is_dir():
        for f in sorted(p for p in vendor.rglob("*") if p.is_file()):
            rel = f.relative_to(vendor).as_posix()
            if rel not in listed:
                found.append(f"static/vendor/{rel} is not listed in data/vendor.yaml")
    return found


def osv(package: str, version: str) -> list[dict]:
    body = json.dumps({"package": {"name": package, "ecosystem": "npm"}, "version": version}).encode()
    req = urllib.request.Request("https://api.osv.dev/v1/query", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp).get("vulns") or []


def advisories(root: Path = ROOT, query=osv) -> list[str]:
    out = []
    for e in entries(root):
        for v in query(e.get("npm") or e["name"], str(e["version"])):
            out.append(f"{e['name']} {e['version']}: {v.get('id')} {v.get('summary') or ''}".rstrip())
    return out


def main(argv: list[str] | None = None) -> int:
    args = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    args.add_argument("--advisories", action="store_true", help="look up known security problems on osv.dev")
    opts = args.parse_args(argv)
    found = advisories() if opts.advisories else problems()
    print("\n".join(found) if found else "No problems.")
    return 1 if found and not opts.advisories else 0


if __name__ == "__main__":
    sys.exit(main())
