"""What a change does to the built site: compare two builds, page by page.

    python tools/site_diff.py                      # build main and this checkout, compare them
    python tools/site_diff.py --base origin/main --fail-on-change
    python tools/site_diff.py --old public-a --new public-b   # compare two folders already built

A refactor must leave every page as it was, so its pull request runs this with --fail-on-change.
Text outputs (HTML, JSON, XML, SVG, CSS, JS, plain text) are compared word for word. Pictures are
re-encoded by Pillow and their bytes differ between Windows and Linux, so they are compared by
name only; share cards already carry a hash of their source picture in their names.
"""

from __future__ import annotations

import argparse
import difflib
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEXT = {".html", ".json", ".xml", ".svg", ".css", ".js", ".txt", ".md", ""}  # "" = _redirects, CNAME
SITE_URL = "https://owlbear.dicelore.quest"


@dataclass
class Report:
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    diffs: dict[str, list[str]] = field(default_factory=dict)

    @property
    def unchanged(self) -> bool:
        return not (self.added or self.removed or self.changed)


def is_text(path: Path) -> bool:
    return path.suffix.lower() in TEXT


def files(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}


def compare(old: Path, new: Path) -> Report:
    a, b = files(old), files(new)
    report = Report(added=sorted(b - a), removed=sorted(a - b))
    for name in sorted(a & b):
        if not is_text(Path(name)):
            continue
        before = (old / name).read_text(encoding="utf-8").splitlines()
        after = (new / name).read_text(encoding="utf-8").splitlines()
        if before != after:
            report.changed.append(name)
            report.diffs[name] = list(difflib.unified_diff(before, after, f"old/{name}", f"new/{name}",
                                                           n=1, lineterm=""))
    return report


def summary(report: Report, max_lines: int = 400) -> str:
    if report.unchanged:
        return "No changes: every page is the same."
    out = [f"{len(report.changed)} changed, {len(report.added)} added, {len(report.removed)} removed"]
    out += [f"  added   {name}" for name in report.added]
    out += [f"  removed {name}" for name in report.removed]
    out += [f"  changed {name}" for name in report.changed]
    budget = max_lines
    hidden = 0
    for name in report.changed:
        lines = report.diffs.get(name, [])
        shown, rest = lines[:max(budget, 0)], lines[max(budget, 0):]
        if shown:
            out += ["", *shown]
        budget -= len(shown)
        hidden += len(rest)
    if hidden:
        out += ["", f"... {hidden} more diff lines not shown"]
    return "\n".join(out)


def build_ref(ref: str, out: Path, work: Path) -> None:
    """Build the site as it is at a git ref, with that ref's own build.py."""
    tree = work / "tree"
    subprocess.run(["git", "worktree", "add", "--detach", "--force", str(tree), ref], cwd=ROOT, check=True,
                   capture_output=True, text=True)
    try:
        build_checkout(tree, out)
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(tree)], cwd=ROOT, check=False,
                       capture_output=True, text=True)


def build_checkout(checkout: Path, out: Path) -> None:
    env = {k: v for k, v in os.environ.items() if k not in ("GOATCOUNTER", "GOOGLE_ANALYTICS", "URL", "BASE_PATH")}
    code = ("import sys; from pathlib import Path; import build; "
            f"build.build(out_dir=Path(sys.argv[1]), site_url={SITE_URL!r}, base_path='/')")
    subprocess.run([sys.executable, "-c", code, str(out)], cwd=checkout, env=env, check=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare the built site of two versions")
    parser.add_argument("--base", default="origin/main", help="git ref to compare against (default origin/main)")
    parser.add_argument("--old", type=Path, help="an already built site to compare (skips building)")
    parser.add_argument("--new", type=Path, help="with --old: the other built site")
    parser.add_argument("--fail-on-change", action="store_true", help="exit 1 if any page differs")
    parser.add_argument("--max-lines", type=int, default=400, help="diff lines to print at most")
    args = parser.parse_args(argv)
    if args.old and args.new:
        report = compare(args.old, args.new)
    else:
        work = Path(tempfile.mkdtemp(prefix="site-diff-"))
        try:
            build_ref(args.base, work / "old", work)
            build_checkout(ROOT, work / "new")
            report = compare(work / "old", work / "new")
        finally:
            shutil.rmtree(work, ignore_errors=True)
    sys.stdout.reconfigure(encoding="utf-8")
    print(summary(report, args.max_lines))
    return 1 if args.fail_on_change and not report.unchanged else 0


if __name__ == "__main__":
    sys.exit(main())
