"""Checks on the real posts in content/posts/ (the other tests build their own fixtures)."""
import re
from pathlib import Path

import pytest

import build

POSTS = sorted((Path(build.__file__).parent / "content" / "posts").glob("*.md"))


def test_posts_found():
    assert POSTS


@pytest.mark.parametrize("path", POSTS, ids=lambda p: p.stem)
def test_post_body_has_no_title_heading(path):
    """The post page already shows the title as its heading, so a "# Title" line in the body
    shows it twice. Headings inside a post start at ##."""
    post = build.parse_post(path)
    html = build.render_markdown(post.body_md)
    assert not re.search(r"<h1[\s>]", html), f"{path.name}: remove the '# {post.title}' line from the body"


ROOT = Path(build.__file__).parent
WIKI = sorted((ROOT / "content" / "wiki").glob("*.md"))
LOCAL_IMAGE = re.compile(r"!\[[^\]]*\]\((/images/[^)\s]+)\)")


@pytest.mark.parametrize("path", POSTS + WIKI, ids=lambda p: p.stem)
def test_local_images_exist(path):
    """Every /images/ picture a post or wiki page shows is in static/images/."""
    for src in LOCAL_IMAGE.findall(path.read_text(encoding="utf-8")):
        assert (ROOT / "static" / src.lstrip("/")).is_file(), f"{path.name}: missing {src}"


@pytest.mark.parametrize("path", [p for p in POSTS if p.name < "2026-10-31"], ids=lambda p: p.stem)
def test_post_features_a_picture(path):
    """Chris (2026-10-31): every post so far features one picture, often an NPC or place."""
    assert "![" in path.read_text(encoding="utf-8"), f"{path.name}: add a feature picture"


def test_ai_pictures_in_posts_are_on_wiki_pages():
    """A post's AI picture also sits on the wiki page it shows, so readers can find it again."""
    wiki_images = {src for p in WIKI for src in LOCAL_IMAGE.findall(p.read_text(encoding="utf-8"))}
    for path in POSTS:
        for src in LOCAL_IMAGE.findall(path.read_text(encoding="utf-8")):
            if "-ai" in src:
                assert src in wiki_images, f"{path.name}: {src} is on no wiki page"


@pytest.mark.parametrize("path", POSTS, ids=lambda p: p.stem)
def test_ai_pictures_carry_the_credit(path):
    """Each AI picture in a post is followed by the AI-generated credit line."""
    text = path.read_text(encoding="utf-8")
    for m in re.finditer(r"!\[[^\]]*\]\(/images/[^)\s]*-ai[^)\s]*\)", text):
        assert text[m.end():m.end() + 200].lstrip().startswith("*AI-generated"), f"{path.name}: credit after {m.group(0)}"
