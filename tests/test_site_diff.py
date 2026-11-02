"""tools/site_diff.py: what a change does to the built site (refactor plan, step 1, 2026-11-02).

A refactor must leave every page as it was. Pictures are re-encoded by Pillow and differ between
Windows and Linux, so only text outputs are compared word for word; pictures are listed by name.
"""
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

import site_diff

ROOT = Path(__file__).resolve().parent.parent


def tree(root: Path, files: dict[str, str | bytes]) -> Path:
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
    return root


def test_identical_sites_have_no_changes(tmp_path):
    files = {"index.html": "<p>Hi</p>\n", "feed.xml": "<feed/>\n", "a.jpg": b"\xff\xd8one"}
    report = site_diff.compare(tree(tmp_path / "a", files), tree(tmp_path / "b", files))
    assert report.unchanged
    assert site_diff.summary(report) == "No changes: every page is the same."


def test_text_changes_show_a_diff(tmp_path):
    a = tree(tmp_path / "a", {"posts/x/index.html": "<h1>Old</h1>\n<p>same</p>\n"})
    b = tree(tmp_path / "b", {"posts/x/index.html": "<h1>New</h1>\n<p>same</p>\n"})
    report = site_diff.compare(a, b)
    assert not report.unchanged
    assert report.changed == ["posts/x/index.html"]
    text = site_diff.summary(report)
    assert "-<h1>Old</h1>" in text and "+<h1>New</h1>" in text
    assert "1 changed" in text


def test_added_and_removed_files_are_listed(tmp_path):
    a = tree(tmp_path / "a", {"old.html": "x\n", "keep.html": "k\n"})
    b = tree(tmp_path / "b", {"new.html": "y\n", "keep.html": "k\n"})
    report = site_diff.compare(a, b)
    assert report.added == ["new.html"]
    assert report.removed == ["old.html"]
    assert report.changed == []


def test_pictures_are_compared_by_name_only(tmp_path):
    # The same card encoded on another machine has other bytes; that is not a change.
    a = tree(tmp_path / "a", {"share/card-1a2b.jpg": b"\xff\xd8windows", "t.webp": b"RIFFa"})
    b = tree(tmp_path / "b", {"share/card-1a2b.jpg": b"\xff\xd8linux", "t.webp": b"RIFFb",
                              "share/card-9f9f.jpg": b"\xff\xd8new"})
    report = site_diff.compare(a, b)
    assert report.changed == []
    assert report.added == ["share/card-9f9f.jpg"]


@pytest.mark.parametrize("name", ["index.html", "search-index.json", "feed.xml", "map/barovia.svg",
                                  "robots.txt", "style.css", "_redirects", "CNAME", "x.js"])
def test_text_outputs_are_compared_word_for_word(name):
    assert site_diff.is_text(Path(name))


@pytest.mark.parametrize("name", ["a.jpg", "a.jpeg", "a.png", "a.webp", "a.gif", "f.woff2", "deck.pdf"])
def test_binary_outputs_are_not(name):
    assert not site_diff.is_text(Path(name))


def test_long_diffs_are_cut_but_every_changed_file_is_named(tmp_path):
    a = tree(tmp_path / "a", {f"p{i}.html": "".join(f"old {n}\n" for n in range(50)) for i in range(5)})
    b = tree(tmp_path / "b", {f"p{i}.html": "".join(f"new {n}\n" for n in range(50)) for i in range(5)})
    text = site_diff.summary(site_diff.compare(a, b), max_lines=40)
    for i in range(5):
        assert f"p{i}.html" in text
    assert "lines not shown" in text
    assert len(text.splitlines()) < 80


def test_cli_compares_two_folders_and_can_fail_on_change(tmp_path):
    a = tree(tmp_path / "a", {"index.html": "a\n"})
    b = tree(tmp_path / "b", {"index.html": "b\n"})
    same = subprocess.run([sys.executable, str(ROOT / "tools" / "site_diff.py"), "--old", str(a), "--new", str(a),
                           "--fail-on-change"], capture_output=True, text=True, encoding="utf-8")
    assert same.returncode == 0, same.stderr
    assert "No changes" in same.stdout
    differ = subprocess.run([sys.executable, str(ROOT / "tools" / "site_diff.py"), "--old", str(a), "--new", str(b),
                             "--fail-on-change"], capture_output=True, text=True, encoding="utf-8")
    assert differ.returncode == 1
    assert "index.html" in differ.stdout


def test_the_build_is_repeatable(real_build, tmp_path):
    """Two builds of the same commit match, so any difference site_diff shows comes from the change."""
    import build
    again = tmp_path / "public"
    build.build(out_dir=again, site_url=real_build.site_url, base_path=real_build.base_path)
    report = site_diff.compare(real_build.out, again)
    assert report.unchanged, site_diff.summary(report)


def test_just_has_a_site_diff_recipe():
    justfile = (ROOT / "justfile").read_text(encoding="utf-8")
    assert "site-diff" in justfile
    assert "tools/site_diff.py" in justfile


def test_checks_workflow_shows_what_a_pull_request_changes_on_the_site():
    flow = yaml.safe_load((ROOT / ".github" / "workflows" / "checks.yml").read_text(encoding="utf-8"))
    steps = flow["jobs"]["test-and-build"]["steps"]
    checkout = next(s for s in steps if s.get("uses", "").startswith("actions/checkout"))
    assert checkout.get("with", {}).get("fetch-depth") == 0  # site_diff builds main from history
    diff = [s for s in steps if "site_diff.py" in s.get("run", "")]
    assert diff, "a step runs tools/site_diff.py"
    assert "GITHUB_STEP_SUMMARY" in diff[0]["run"]
    assert diff[0].get("if") == "github.event_name == 'pull_request'"
