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
