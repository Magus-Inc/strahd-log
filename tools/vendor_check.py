"""Check the libraries we use (the library rules in AGENTS.md).

Every file in static/vendor/ is listed in data/vendor.yaml with its version, where it came from, why
we use it, a permissive license whose text sits next to it, and the sha256 of the exact file, so a
copied library can only change through a PR that also changes its fingerprint. Each library stays
under the phone budget (MAX_GZIP_BYTES zipped).

Every Python package in requirements*.txt is listed in data/python-libraries.yaml with why we use it.

Both lists also say how well each library is kept up (Chris, 2026-11-03): when it was first and last
released, how many downloads a week (popularity), whether bug and security fixes are landing, and
one of the MAINTENANCE states, with its risks written down. A new, quiet, unmaintained or little-used
library is not refused, but its risk must be listed (upkeep_problems has the rules).

    python tools/vendor_check.py               # list problems (the tests run this too)
    python tools/vendor_check.py --advisories  # ask osv.dev for known security problems (monthly workflow)
    python tools/vendor_check.py --recheck     # today's registry facts against the upkeep rules (monthly)
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import json
import re
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

# How well a library is kept up. "active": releases and fixes keep coming. "stable": quiet because it
# is finished, and bug and security reports still get answered. "new": under NEW_DAYS old, so nobody
# knows yet whether it will be kept up. "unmaintained": fixes have stopped (abandoned).
MAINTENANCE = ("active", "stable", "new", "unmaintained")
UPKEEP = ("first_release", "last_release", "weekly_downloads", "maintenance", "fixes", "checked")
NEW_DAYS = 365           # younger than this is "new"
QUIET_DAYS = 2 * 365     # no release for this long: say whether it is stable or unmaintained
LOW_DOWNLOADS = 1_000    # fewer a week than this: few eyes on its bugs
RECHECK_DAYS = 365       # look at every library again at least this often


def entries(root: Path = ROOT) -> list[dict]:
    path = root / "data" / "vendor.yaml"
    if not path.exists():
        return []
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("libraries") or []


def _date(value) -> dt.date | None:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    try:
        return dt.date.fromisoformat(str(value))
    except ValueError:
        return None


def upkeep_problems(name: str, e: dict, today: dt.date | None = None) -> list[str]:
    """The maintenance and popularity rules for one library entry."""
    today = today or dt.date.today()
    found = [f"{name}: missing {key}" for key in UPKEEP if e.get(key) is None or not str(e.get(key)).strip()]
    if "risks" not in e:
        found.append(f"{name}: missing risks (write risks: [] when there are none)")
    dates = {}
    for key in ("first_release", "last_release", "checked"):
        if e.get(key) is not None:
            dates[key] = _date(e[key])
            if dates[key] is None:
                found.append(f"{name}: {key} must be a date like 2026-11-03, not {e[key]!r}")
    first, last, checked = dates.get("first_release"), dates.get("last_release"), dates.get("checked")
    state = e.get("maintenance")
    if state is not None and state not in MAINTENANCE:
        found.append(f"{name}: maintenance {state!r} is not one of {list(MAINTENANCE)}")
    risks = e.get("risks") if e.get("risks") is not None else []
    if not isinstance(risks, list) or not all(isinstance(r, str) and r.strip() for r in risks):
        found.append(f"{name}: risks must be a list of sentences")
        risks = ["?"]
    if first and last and first > last:
        found.append(f"{name}: first_release {first} is after last_release {last}")
    if last and checked and last > checked:
        found.append(f"{name}: last_release {last} is after checked {checked}")
    if checked and checked > today:
        found.append(f"{name}: checked {checked} is in the future")
    if first and checked and (checked - first).days < NEW_DAYS and state != "new":
        found.append(f"{name}: first released {first}, under a year before it was checked: mark it new and list its risks")
    if state == "new" and not risks:
        found.append(f"{name}: a new library gets extra scrutiny: list its risks")
    if last and checked and (checked - last).days > QUIET_DAYS and state in ("active", "new"):
        found.append(f"{name}: no release since {last}: say whether it is stable (finished, fixes still answered) or unmaintained")
    if state == "unmaintained" and not risks:
        found.append(f"{name}: unmaintained (bug and security fixes have stopped): list the risk")
    downloads = e.get("weekly_downloads")
    if downloads is not None and (isinstance(downloads, bool) or not isinstance(downloads, int)):
        found.append(f"{name}: weekly_downloads must be a whole number, not {downloads!r}")
    elif isinstance(downloads, int) and downloads < LOW_DOWNLOADS and not risks:
        found.append(f"{name}: only {downloads} downloads a week: list low popularity as a risk")
    return found


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
        found.extend(upkeep_problems(name, e))
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


def _key(package: str) -> str:
    return re.sub(r"[-_.]+", "-", package).lower()


def requirements(root: Path = ROOT) -> dict[str, tuple[str, str | None]]:
    """Every package named in requirements*.txt: normalized name -> (name as written, pinned version)."""
    out: dict[str, tuple[str, str | None]] = {}
    for path in sorted(root.glob("requirements*.txt")):
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.split("#")[0].strip()
            m = re.match(r"([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]*\])?\s*(?:==\s*([^\s;,]+))?", line)
            if m and not line.startswith("-") and not (m.group(2) is None and _key(m.group(1)) in out):
                out[_key(m.group(1))] = (m.group(1), m.group(2))  # an exact pin anywhere wins
    return out


def python_entries(root: Path = ROOT) -> list[dict]:
    path = root / "data" / "python-libraries.yaml"
    if not path.exists():
        return []
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("libraries") or []


def python_problems(root: Path = ROOT) -> list[str]:
    required = requirements(root)
    found: list[str] = []
    listed = set()
    for e in python_entries(root):
        name = e.get("name") or "?"
        listed.add(_key(name))
        if _key(name) not in required:
            found.append(f"{name}: listed in data/python-libraries.yaml but not in requirements*.txt")
        if not str(e.get("why") or "").strip():
            found.append(f"{name}: missing why")
        found.extend(upkeep_problems(name, e))
    for key, (name, _) in sorted(required.items()):
        if key not in listed:
            found.append(f"{name}: in requirements*.txt but not listed in data/python-libraries.yaml")
    return found


def _libraries(root: Path):
    """(name, package, version, ecosystem, entry) for every copied library and Python package."""
    for e in entries(root):
        yield e["name"], e.get("npm") or e["name"], str(e["version"]), "npm", e
    pins = requirements(root)
    for e in python_entries(root):
        name, version = pins.get(_key(e["name"]), (e["name"], None))
        yield e["name"], e["name"], version, "PyPI", e


def osv(package: str, version: str, ecosystem: str = "npm") -> list[dict]:
    body = json.dumps({"package": {"name": package, "ecosystem": ecosystem}, "version": version}).encode()
    req = urllib.request.Request("https://api.osv.dev/v1/query", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp).get("vulns") or []


def advisories(root: Path = ROOT, query=osv) -> list[str]:
    out = []
    for name, package, version, ecosystem, _ in _libraries(root):
        if not version:
            continue  # not pinned (tzdata): pip installs the latest
        for v in query(package, version, ecosystem):
            out.append(f"{name} {version}: {v.get('id')} {v.get('summary') or ''}".rstrip())
    return out


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "strahd-log-library-check"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def registry(package: str, ecosystem: str) -> dict:
    """Today's facts from npm or PyPI: first and last release dates, weekly downloads, latest version."""
    if ecosystem == "npm":
        meta = _get(f"https://registry.npmjs.org/{package}")
        times = [v for k, v in meta["time"].items() if k not in ("created", "modified")]
        downloads = _get(f"https://api.npmjs.org/downloads/point/last-week/{package}")["downloads"]
        latest = meta["dist-tags"]["latest"]
    else:
        meta = _get(f"https://pypi.org/pypi/{package}/json")
        times = [f["upload_time"] for files in meta["releases"].values() for f in files if not f.get("yanked")]
        downloads = _get(f"https://pypistats.org/api/packages/{_key(package)}/recent")["data"]["last_week"]
        latest = meta["info"]["version"]
    times = sorted(t[:10] for t in times)
    return {"first_release": _date(times[0]), "last_release": _date(times[-1]),
            "weekly_downloads": downloads, "latest": latest}


def _major(version: str) -> int:
    m = re.match(r"\d+", version)
    return int(m.group()) if m else 0


def changes(name: str, e: dict, live: dict, today: dt.date) -> list[str]:
    """What has changed since the entry was written, even where the rules still pass."""
    out = []
    checked, last = _date(e.get("checked")), _date(live.get("last_release"))
    if last and checked and (checked - last).days <= QUIET_DAYS < (today - last).days:
        out.append(f"{name}: no release since {last}, now over two years: decide again whether it is stable or unmaintained")
    first = _date(live.get("first_release"))
    if e.get("maintenance") == "new" and first and (today - first).days >= NEW_DAYS:
        out.append(f"{name}: first released {first}, so it is no longer new: mark it active, stable or unmaintained")
    was, now = e.get("weekly_downloads"), live.get("weekly_downloads")
    if isinstance(was, int) and isinstance(now, int) and now * 2 < was:
        out.append(f"{name}: downloads fell from {was} to {now} a week: is it losing its users?")
    return out


def recheck(root: Path = ROOT, fetch=registry, today: dt.date | None = None) -> list[str]:
    """Run the upkeep rules on today's registry facts, and say what has changed since we last looked."""
    today = today or dt.date.today()
    out = []
    for name, package, version, ecosystem, e in _libraries(root):
        live = fetch(package, ecosystem)
        now = {**e, **{k: live[k] for k in ("first_release", "last_release", "weekly_downloads")}, "checked": today}
        out += [f"{p} (today's registry facts)" for p in upkeep_problems(name, now, today=today)]
        out += changes(name, e, live, today)
        checked = _date(e.get("checked"))
        if checked and (today - checked).days > RECHECK_DAYS:
            out.append(f"{name}: upkeep last checked {checked}: look again and update its entry")
        if version and live["latest"] != version and (ecosystem == "npm" or _major(live["latest"]) > _major(version)):
            # A copied file never updates itself, so any newer release counts. A Python pin a patch
            # behind is normal; a whole major version behind, its line may no longer get fixes.
            out.append(f"{name}: {live['latest']} is out and we use {version}: read its release notes for bug and security fixes")
    return out


def main(argv: list[str] | None = None) -> int:
    args = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    args.add_argument("--advisories", action="store_true", help="look up known security problems on osv.dev")
    args.add_argument("--recheck", action="store_true", help="check upkeep against today's npm and PyPI facts")
    opts = args.parse_args(argv)
    if opts.advisories:
        found = advisories()
    elif opts.recheck:
        found = recheck()
    else:
        found = problems() + python_problems()
    print("\n".join(found) if found else "No problems.")
    return 1 if found and not (opts.advisories or opts.recheck) else 0


if __name__ == "__main__":
    sys.exit(main())
