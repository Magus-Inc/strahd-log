"""Pull request previews on GitHub Pages.

GitHub Pages serves one site, so the Pages workflow builds main and then every open pull request
from this repository into public/pr-preview/pr-N/, and deploys them together. A closed pull
request is simply not built again, so its preview disappears on the next deploy.

    python tools/pr_previews.py build --origin https://owlbear.dicelore.quest --base-path ""
    python tools/pr_previews.py comment --pr 62 --url https://owlbear.dicelore.quest/pr-preview/pr-62/

Previews stay out of search engines and page-view counts: robots.txt at the site root blocks
/pr-preview/, every preview page gets a noindex tag, and the build runs without GOATCOUNTER. This is
done here, not in the pull request's own build.py, so it holds for branches made before this file
existed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PREVIEW_DIR = "pr-preview"
MARKER = "<!-- pr-preview -->"
# Variables a pull request's own build must not see: the token, and the page-view counter.
HIDDEN_ENV = ("GH_TOKEN", "GITHUB_TOKEN", "GOATCOUNTER", "ACTIONS_RUNTIME_TOKEN", "ACTIONS_ID_TOKEN_REQUEST_TOKEN",
              "ACTIONS_ID_TOKEN_REQUEST_URL")


def normalize_base_path(base: str) -> str:
    base = base.strip().strip("/")
    return f"/{base}/" if base else "/"


def preview_path(base_path: str, number: int) -> str:
    """'/' and 62 -> '/pr-preview/pr-62/'."""
    return f"{normalize_base_path(base_path)}{PREVIEW_DIR}/pr-{number}/"


def preview_url(origin: str, base_path: str, number: int) -> str:
    return origin.rstrip("/") + preview_path(base_path, number)


def robots_txt(base_path: str) -> str:
    return f"User-agent: *\nDisallow: {normalize_base_path(base_path)}{PREVIEW_DIR}/\n"


def previewable(pulls: list[dict], skip: int | None = None) -> list[dict]:
    """Open pull requests whose branch is in this repository (never a fork's code), oldest first."""
    keep = [p for p in pulls if p.get("number") != skip and p.get("isCrossRepository") is False]
    return sorted(keep, key=lambda p: p["number"])


def banner(number: int, repo: str) -> str:
    return (f'<div role="note" style="background:#7a1f1f;color:#fff;text-align:center;padding:.5em 1em;'
            f'font:600 15px/1.4 system-ui,sans-serif">Preview of '
            f'<a style="color:#fff" href="https://github.com/{repo}/pull/{number}">pull request #{number}</a>'
            f' &middot; not the live blog</div>')


def mark_page(html: str, number: int, repo: str) -> str:
    """Add a noindex tag and a preview banner to one page (once, even if run twice)."""
    if 'name="robots"' not in html:
        html = re.sub(r"(<head[^>]*>)", r'\1<meta name="robots" content="noindex, nofollow">', html, count=1,
                      flags=re.I)
    if "Preview of <a" not in html:
        html = re.sub(r"(<body[^>]*>)", lambda m: m.group(1) + banner(number, repo), html, count=1, flags=re.I)
    return html


def mark_preview(site: Path, number: int, repo: str) -> None:
    """Make a built pull request site safe to publish under the live one."""
    for name in ("CNAME", "robots.txt"):
        (site / name).unlink(missing_ok=True)
    for page in site.rglob("*.html"):
        text = page.read_text(encoding="utf-8")
        page.write_text(mark_page(text, number, repo), encoding="utf-8", newline="")


def preview_env(env: dict[str, str], origin: str, base_path: str, number: int) -> dict[str, str]:
    env = {k: v for k, v in env.items() if k not in HIDDEN_ENV}
    env.update(URL=origin.rstrip("/"), BASE_PATH=preview_path(base_path, number))
    return env


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(cmd, check=True, text=True, **kw)


def open_pulls(repo: str) -> list[dict]:
    out = run(["gh", "pr", "list", "--repo", repo, "--state", "open", "--limit", "100",
               "--json", "number,headRefOid,isCrossRepository,title"],
              capture_output=True).stdout
    return json.loads(out)


def build_one(pull: dict, public: Path, work: Path, origin: str, base_path: str, repo: str,
              checkout: Path = ROOT) -> None:
    number = pull["number"]
    tree = work / f"pr-{number}"
    if tree.exists():
        shutil.rmtree(tree)
    run(["git", "fetch", "--depth", "1", "--no-tags", "origin", f"pull/{number}/head"], cwd=checkout)
    run(["git", "worktree", "add", "--detach", "--force", str(tree), "FETCH_HEAD"], cwd=checkout)
    try:
        run([sys.executable, "build.py"], cwd=tree, env=preview_env(dict(os.environ), origin, base_path, number))
        target = public / PREVIEW_DIR / f"pr-{number}"
        if target.exists():
            shutil.rmtree(target)
        shutil.move(str(tree / "public"), str(target))
        mark_preview(target, number, repo)
    finally:
        run(["git", "worktree", "remove", "--force", str(tree)], cwd=checkout)


def build_previews(public: Path, origin: str, base_path: str, repo: str, pulls: list[dict],
                   work: Path, checkout: Path = ROOT) -> dict:
    """Build each pull request into public/pr-preview/; a failed one is reported, not fatal."""
    public.joinpath("robots.txt").write_text(robots_txt(base_path), encoding="utf-8")
    (public / PREVIEW_DIR).mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    results: dict = {"built": [], "failed": [], "shas": {}}
    for pull in pulls:
        try:
            build_one(pull, public, work, origin, base_path, repo, checkout)
            results["built"].append(pull["number"])
            if pull.get("headRefOid"):
                results["shas"][str(pull["number"])] = pull["headRefOid"]
        except (subprocess.CalledProcessError, OSError) as err:
            print(f"Preview for #{pull['number']} failed: {err}", file=sys.stderr)
            results["failed"].append(pull["number"])
    return results


def comment_body(number: int, url: str, state: str, sha: str = "", run_url: str = "") -> str:
    """The one comment the workflow keeps up to date on each pull request."""
    if state == "built":
        lines = [f"**Preview:** {url}", "",
                 f"Rebuilt for {sha[:7]} on every push. Search engines and page views skip it, and it goes away "
                 "when this pull request closes." if sha else
                 "Rebuilt on every push. Search engines and page views skip it, and it goes away when this pull "
                 "request closes."]
    elif state == "failed":
        lines = ["**Preview:** the build failed, so there is no preview for this push."
                 + (f" [Workflow log]({run_url})" if run_url else "")]
    elif state == "removed":
        lines = ["**Preview:** removed now that this pull request is closed."]
    else:
        raise ValueError(f"unknown preview state {state!r}")
    return MARKER + "\n" + "\n".join(lines) + "\n"


def comments_from_env(env: dict[str, str]) -> list[tuple[int, str]]:
    """(pull request number, comment body) for every pull request this deploy touched: each preview
    built or failed, and the pull request that is closing."""
    results = json.loads(env.get("RESULTS") or "{}")
    shas = {int(k): v for k, v in (results.get("shas") or {}).items()}
    origin, base, run_url = env.get("ORIGIN", ""), env.get("BASE_PATH", ""), env.get("RUN_URL", "")
    out = [(n, comment_body(n, preview_url(origin, base, n), "built", shas.get(n, ""))) for n in results.get("built", [])]
    out += [(n, comment_body(n, "", "failed", run_url=run_url)) for n in results.get("failed", [])]
    if env.get("CLOSED") == "true" and env.get("NUMBER"):
        out.append((int(env["NUMBER"]), comment_body(int(env["NUMBER"]), "", "removed")))
    return sorted(out)


def upsert_comment(repo: str, number: int, body: str) -> None:
    """Keep one preview comment per pull request; leave it alone when nothing changed."""
    comments = json.loads(run(["gh", "api", "--paginate", "--slurp", f"repos/{repo}/issues/{number}/comments"],
                              capture_output=True).stdout)
    mine = [c for page in comments for c in page if MARKER in (c.get("body") or "")]
    if mine and mine[0].get("body") == body:
        return
    if mine:
        run(["gh", "api", "-X", "PATCH", f"repos/{repo}/issues/comments/{mine[0]['id']}", "-f", f"body={body}"],
            capture_output=True)
    else:
        run(["gh", "api", "-X", "POST", f"repos/{repo}/issues/{number}/comments", "-f", f"body={body}"],
            capture_output=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="build open pull requests into public/pr-preview/")
    b.add_argument("--origin", required=True)
    b.add_argument("--base-path", default="")
    b.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", "Magus-Inc/strahd-log"))
    b.add_argument("--skip", type=int, help="leave out this pull request (it is closing)")
    b.add_argument("--public", type=Path, default=ROOT / "public")
    b.add_argument("--work", type=Path, default=ROOT / ".previews")
    c = sub.add_parser("comment", help="add or update the preview comment on a pull request")
    c.add_argument("--pr", type=int, required=True)
    c.add_argument("--state", choices=["built", "failed", "removed"], required=True)
    c.add_argument("--url", default="")
    c.add_argument("--sha", default="")
    c.add_argument("--run-url", default="")
    c.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", "Magus-Inc/strahd-log"))
    e = sub.add_parser("comment-from-env", help="the workflow's comment step: NUMBER, RESULTS, CLOSED, ORIGIN, ...")
    e.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", "Magus-Inc/strahd-log"))
    args = parser.parse_args(argv)
    if args.cmd == "comment-from-env":
        failed = 0
        for number, body in comments_from_env(dict(os.environ)):
            try:
                upsert_comment(args.repo, number, body)
            except subprocess.CalledProcessError as err:
                print(f"Could not comment on #{number}: {err}", file=sys.stderr)
                failed += 1
        return 1 if failed else 0
    if args.cmd == "build":
        pulls = previewable(open_pulls(args.repo), args.skip)
        results = build_previews(args.public, args.origin, args.base_path, args.repo, pulls, args.work)
        print(json.dumps(results))
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as fh:
                fh.write(f"results={json.dumps(results)}\n")
    else:
        upsert_comment(args.repo, args.pr, comment_body(args.pr, args.url, args.state, args.sha, args.run_url))
    return 0


if __name__ == "__main__":
    sys.exit(main())
