"""build() runs named stages in one place (refactor plan step 3, 2026-11-03).

The order matters (post style before wiki links, links before citations, slides and party before the
reading aids and the map), and build.STAGES is the only place it is written down.
"""
from pathlib import Path

import pytest

import build

ROOT = Path(__file__).resolve().parent.parent

ORDER = ["style_posts", "number_posts", "link_names", "cite_wiki", "style_wiki", "attach_slides",
         "attach_party", "reading_aids", "lay_out_map"]


def write_post(folder: Path, name: str, front: str, body: str = "Body.\n") -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(f"---\n{front}---\n\n{body}", encoding="utf-8")


@pytest.fixture
def content(tmp_path):
    folder = tmp_path / "content" / "posts"
    write_post(folder, "2024-01-09-first.md", "title: First Night\ndate: '2024-01-09'\n", "We met Ireena.\n")
    write_post(folder, "2024-02-13-second.md", "title: Wolves\ndate: '2024-02-13'\n")
    wiki = tmp_path / "content" / "wiki"
    wiki.mkdir()
    (wiki / "ireena.md").write_text("---\ntitle: Ireena\ntype: npc\n---\n", encoding="utf-8")
    return folder


def test_stages_run_in_the_order_written_down():
    assert [stage.__name__ for stage in build.STAGES] == ORDER


def test_every_stage_takes_the_site():
    for stage in build.STAGES:
        assert list(stage.__annotations__) [:1] == ["site"], stage.__name__


def test_build_runs_exactly_the_stages(content, tmp_path, monkeypatch):
    ran = []

    def recorder(stage):
        def run(site):
            ran.append(stage.__name__)
            stage(site)
        run.__name__ = stage.__name__
        return run

    monkeypatch.setattr(build, "STAGES", tuple(recorder(s) for s in build.STAGES))
    build.build(content, tmp_path / "public", site_url="https://x.example")
    assert ran == ORDER


def test_prepare_readies_the_site_without_writing_files(content, tmp_path):
    site = build.prepare(content)
    assert [p.slug for p in site.posts] == ["second", "first"]
    assert [p.number for p in site.posts] == [2, 1]
    assert 'href="/wiki/ireena/"' in site.posts[1].html  # names linked
    assert site.posts[1].minutes >= 1  # reading aids ran
    assert not (tmp_path / "public").exists()


def test_build_lives_in_build_py_only():
    # build.py stays the entry point: `python build.py`, `just build` and the tests import it.
    assert not (ROOT / "site").exists()
