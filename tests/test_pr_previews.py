import re
import subprocess
from pathlib import Path

import pytest
import yaml

import build
import pr_previews

ROOT = Path(__file__).resolve().parent.parent
REPO = "Magus-Inc/strahd-log"


def test_preview_address_follows_the_site_base_path():
    assert pr_previews.preview_path("", 62) == "/pr-preview/pr-62/"
    assert pr_previews.preview_path("/strahd-log", 62) == "/strahd-log/pr-preview/pr-62/"
    assert pr_previews.preview_url("https://owlbear.dicelore.quest/", "", 62) == \
        "https://owlbear.dicelore.quest/pr-preview/pr-62/"


def test_robots_blocks_previews_only():
    assert pr_previews.robots_txt("") == "User-agent: *\nDisallow: /pr-preview/\n"
    assert pr_previews.robots_txt("/strahd-log/") == "User-agent: *\nDisallow: /strahd-log/pr-preview/\n"


def test_only_branches_of_this_repository_get_previews():
    pulls = [{"number": 9, "isCrossRepository": False}, {"number": 3, "isCrossRepository": True},
             {"number": 5, "isCrossRepository": False}, {"number": 7}]
    assert [p["number"] for p in pr_previews.previewable(pulls)] == [5, 9]
    assert [p["number"] for p in pr_previews.previewable(pulls, skip=9)] == [5]


def test_preview_build_never_sees_the_token_or_the_counter():
    env = pr_previews.preview_env({"PATH": "/bin", "GH_TOKEN": "x", "GITHUB_TOKEN": "y", "GOATCOUNTER": "owlbear",
                                   "BASE_PATH": "/"}, "https://owlbear.dicelore.quest/", "", 62)
    assert env == {"PATH": "/bin", "URL": "https://owlbear.dicelore.quest", "BASE_PATH": "/pr-preview/pr-62/"}


def test_mark_page_adds_noindex_and_banner_once():
    html = "<!doctype html>\n<html><head>\n<title>x</title></head><body class='a'><p>Hi</p></body></html>"
    once = pr_previews.mark_page(html, 62, REPO)
    assert pr_previews.mark_page(once, 62, REPO) == once
    assert once.count('<meta name="robots" content="noindex, nofollow">') == 1
    assert once.index("noindex") < once.index("<title>")
    assert "https://github.com/Magus-Inc/strahd-log/pull/62" in once
    assert once.index("<body class='a'>") < once.index("Preview of") < once.index("<p>Hi</p>")


def internal_links(site: Path) -> list[str]:
    links = []
    for page in site.rglob("*.html"):
        text = re.sub(r"<script>.*?</script>", "", page.read_text(encoding="utf-8"), flags=re.S)
        links += [l for l in re.findall(r'(?:href|src)="([^"]*)"', text)
                  if not l.startswith(("http://", "https://", "#", "mailto:"))]
    return links


def test_real_site_built_as_a_preview_works_under_its_folder(tmp_path, monkeypatch):
    """The real content, built the way the workflow builds a pull request: links, CSS and pictures
    resolve inside /pr-preview/pr-62/, and nothing in it is indexed, counted or claims the domain."""
    public = tmp_path / "public"
    env = pr_previews.preview_env({"GOATCOUNTER": "owlbear"}, "https://owlbear.dicelore.quest", "", 62)
    monkeypatch.delenv("GOATCOUNTER", raising=False)
    monkeypatch.setenv("BASE_PATH", env["BASE_PATH"])
    site = public / "pr-preview" / "pr-62"
    build.build(out_dir=site, site_url=env["URL"])
    pr_previews.mark_preview(site, 62, REPO)

    assert not (site / "CNAME").exists()
    pages = list(site.rglob("*.html"))
    assert len(pages) > 20
    for page in pages:
        html = page.read_text(encoding="utf-8")
        assert 'name="robots" content="noindex' in html, page
        assert "goatcounter" not in html, page
    links = internal_links(site)
    assert links
    for link in links:
        assert link.startswith("/pr-preview/pr-62/"), link
        target = public / link.lstrip("/").split("#")[0].split("?")[0]
        assert target.exists() or (target / "index.html").exists(), link


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo_with_pulls(tmp_path):
    """A clone whose origin has pull/1/head (builds) and pull/2/head (build fails), like GitHub."""
    origin, work = tmp_path / "origin.git", tmp_path / "src"
    git(tmp_path, "init", "-q", "--bare", str(origin))
    git(tmp_path, "init", "-q", str(work))
    for key, value in (("user.name", "t"), ("user.email", "t@example.com"), ("commit.gpgsign", "false")):
        git(work, "config", key, value)
    fake_build = ("import os, pathlib\n"
                  "out = pathlib.Path('public'); out.mkdir()\n"
                  "(out / 'CNAME').write_text('owlbear.dicelore.quest')\n"
                  "(out / 'index.html').write_text('<html><head></head><body>' + os.environ['BASE_PATH'] + '|'"
                  " + os.environ.get('GOATCOUNTER', '') + os.environ.get('GH_TOKEN', '') + '</body></html>')\n")
    (work / "build.py").write_text(fake_build, encoding="utf-8")
    git(work, "add", ".")
    git(work, "commit", "-qm", "good")
    git(work, "push", "-q", str(origin), "HEAD:refs/pull/1/head")
    (work / "build.py").write_text("raise SystemExit('broken')\n", encoding="utf-8")
    git(work, "commit", "-qam", "bad")
    git(work, "push", "-q", str(origin), "HEAD:refs/pull/2/head")
    git(work, "remote", "add", "origin", str(origin))
    return work


def test_build_previews_builds_each_pull_request_and_survives_a_broken_one(repo_with_pulls, tmp_path, monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "secret")
    monkeypatch.setenv("GOATCOUNTER", "owlbear")
    public = tmp_path / "public"
    public.mkdir()
    (public / "index.html").write_text("main", encoding="utf-8")
    results = pr_previews.build_previews(public, "https://owlbear.dicelore.quest", "", REPO,
                                         [{"number": 1}, {"number": 2}], tmp_path / "work", repo_with_pulls)
    assert results == {"built": [1], "failed": [2]}
    assert (public / "index.html").read_text(encoding="utf-8") == "main"
    assert (public / "robots.txt").read_text(encoding="utf-8") == "User-agent: *\nDisallow: /pr-preview/\n"
    preview = (public / "pr-preview" / "pr-1" / "index.html").read_text(encoding="utf-8")
    assert "/pr-preview/pr-1/|</body>" in preview  # right base path; no counter, no token
    assert "noindex" in preview and "pull request #1" in preview
    assert not (public / "pr-preview" / "pr-1" / "CNAME").exists()
    assert not (public / "pr-preview" / "pr-2").exists()
    assert "pr-" not in git(repo_with_pulls, "worktree", "list")


@pytest.mark.parametrize("closed, results, expect", [
    ("false", '{"built": [62], "failed": []}', "**Preview:** https://owlbear.dicelore.quest/pr-preview/pr-62/"),
    ("false", '{"built": [], "failed": [62]}', "the build failed"),
    ("false", "", "the build failed"),
    ("true", '{"built": [], "failed": []}', "removed now that this pull request is closed"),
])
def test_comment_matches_what_happened(closed, results, expect):
    number, body = pr_previews.comment_from_env({
        "NUMBER": "62", "RESULTS": results, "CLOSED": closed, "ORIGIN": "https://owlbear.dicelore.quest",
        "BASE_PATH": "", "SHA": "abcdef1234", "RUN_URL": "https://github.com/x/runs/1"})
    assert number == 62
    assert body.startswith(pr_previews.MARKER)
    assert expect in body


def workflow() -> dict:
    data = yaml.safe_load((ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8"))
    data["on"] = data.pop(True, data.get("on"))  # YAML 1.1 reads the key `on` as True
    return data


def test_workflow_deploys_main_and_previews_from_main_only():
    flow = workflow()
    assert flow["on"]["push"]["branches"] == ["main"]
    assert set(flow["on"]["pull_request_target"]["types"]) == {"opened", "reopened", "synchronize", "closed"}
    assert "pull_request" not in flow["on"]
    jobs = flow["jobs"]
    assert flow["permissions"] == {"contents": "read"}
    # The job that runs pull request code can only read, and never for a fork.
    assert jobs["build"]["permissions"] == {"contents": "read", "pull-requests": "read"}
    assert "head.repo.full_name == github.repository" in jobs["build"]["if"]
    for job in ("build", "comment"):
        checkout = jobs[job]["steps"][0]
        assert checkout["uses"].startswith("actions/checkout@")
        assert checkout["with"] == {"ref": "main", "persist-credentials": False}
    steps = {s.get("name") or s.get("id") or s["uses"]: s for s in jobs["build"]["steps"]}
    assert steps["Build"]["env"]["GOATCOUNTER"] == "owlbear"
    assert "GOATCOUNTER" not in steps["Build pull request previews"]["env"]
    assert "tools/pr_previews.py build" in steps["Build pull request previews"]["run"]
    assert jobs["deploy"]["permissions"] == {"pages": "write", "id-token": "write"}
    assert jobs["deploy"]["environment"]["name"] == "github-pages"
    assert jobs["comment"]["needs"] == ["build", "deploy"]
    assert jobs["comment"]["permissions"] == {"pull-requests": "write"}
    assert "comment-from-env" in jobs["comment"]["steps"][-1]["run"]


def test_workflow_comment_step_passes_what_the_script_reads():
    env = workflow()["jobs"]["comment"]["steps"][-1]["env"]
    assert {"GH_TOKEN", "NUMBER", "RESULTS", "CLOSED", "ORIGIN", "BASE_PATH", "SHA", "RUN_URL"} <= set(env)
    assert env["RESULTS"] == "${{ needs.build.outputs.results }}"
