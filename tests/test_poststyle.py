"""The look settings for a post in the one post format (tests/test_post_format.py checks the format)."""
import re
from pathlib import Path

import pytest

import build
import poststyle

ROOT = Path(build.__file__).parent
TAGLINE_LOOK, CARD_TAGLINE = "subtitle", "instead"  # Chris's tagline picks (2026-11-02 tagline look page)
md = build.render_markdown
POST = "## Story\n\n### Into the Fog\n\nWe ran.\n\n## Key Locations\n\n* **Fog**: thick.\n"


# --- settings -------------------------------------------------------------------------------

def test_defaults_keep_the_story_heading_and_scenes_as_written(tmp_path):
    style = poststyle.load_style(tmp_path / "missing.yaml")
    assert style == poststyle.AS_WRITTEN
    html = poststyle.apply(md(POST), style)
    assert "<h2>Story</h2>" in html and "<h3>Into the Fog</h3>" not in html


def test_unknown_setting_or_value_is_refused(tmp_path):
    f = tmp_path / "style.yaml"
    f.write_text("cast: confetti\n", encoding="utf-8")
    with pytest.raises(ValueError, match="cast"):
        poststyle.load_style(f)
    f.write_text("headings: real\n", encoding="utf-8")  # a clean-up setting the post format replaced
    with pytest.raises(ValueError, match="headings"):
        poststyle.load_style(f)


def test_blog_uses_the_picks():
    """Chris's picks for this blog (2026-11-01 post style page, 2026-11-02 layout and tagline pages)."""
    style = poststyle.load_style(ROOT / "data" / "post-style.yaml")
    assert style == {"cast": "pills", "glance": "none", "tagline": "keep", "picture": "scene",
                     "story": "titled", "story-title": "Malron’s Account", "scenes": "written",
                     "slides": "above-story", "relink": "each-heading",
                     "tagline-look": TAGLINE_LOOK, "card-tagline": CARD_TAGLINE}


# --- story heading and scenes -----------------------------------------------------------------

def test_no_heading_leaves_the_story_bare():
    html = poststyle.apply(md(POST), {"story": "no-heading", "scenes": "written"})
    assert "<h2>" not in html.split(poststyle.STORY_END)[0] and "<h3>Into the Fog</h3>" in html


def test_the_story_ends_before_the_first_recap_list():
    html = poststyle.apply(md(POST + "\n## Plot Points\n\n* We left.\n"), {"story": "titled"})
    assert html.index("We ran.") < html.index(poststyle.STORY_END) < html.index("<h2>Key Locations</h2>")
    assert html.count(poststyle.STORY_END) == 1


def test_hand_made_wiki_links_look_like_the_others():
    html = poststyle.apply(md("## Story\n\nWe met [Ireena](/wiki/ireena/).\n"), {})
    assert '<a class="wiki-link" href="/wiki/ireena/">Ireena</a>' in html


# --- cast -----------------------------------------------------------------------------------

def test_cast_list_shows_the_characters_above_the_story():
    for pick in ("list", "pills+list"):
        html = poststyle.apply(md(POST), {"cast": pick, "story": "titled"}, ["Crusty", "Aera shan Ravanór"])
        assert html.startswith("<h2>Characters</h2>\n<ul>\n<li>Crusty</li>\n<li>Aera shan Ravanór</li>\n</ul>\n" + poststyle.STORY)
    assert "Characters" not in poststyle.apply(md(POST), {"cast": "pills"}, ["Crusty"])


# --- glance, picture ------------------------------------------------------------------------

def test_glance_none_removes_the_box():
    text = "## At a Glance\n\n* **A**: b\n\n" + POST
    assert "Glance" not in poststyle.apply(md(text), {"glance": "none"})
    assert "<h2>At a Glance</h2>" in poststyle.apply(md(text), {})


def test_picture_top_moves_the_feature_picture_and_credit_first():
    text = ("## Story\n\nOne.\n\nTwo.\n\n![Horngaard](/images/vladimir-horngaard-ai.jpg)\n\n"
            "*AI-generated image (Google Gemini). Not official art.*\n\nThree.\n")
    html = poststyle.apply(md(text), {"picture": "top"})
    assert html.startswith('<p><img alt="Horngaard" src="/images/vladimir-horngaard-ai.jpg"></p>\n<p><em>AI-generated')
    assert html.index("One.") < html.index("Two.") < html.index("Three.")


# --- the real blog --------------------------------------------------------------------------

@pytest.fixture
def site(real_build):
    # Plain values only: a failing assert would otherwise try to print the posts' wiki graph.
    return real_build.out, [(p.slug, [c.slug for c in p.cast]) for p in real_build.posts]


def test_every_post_follows_the_template(site):
    out, posts = site
    checks = {"Characters section": r"<h[23][^>]*>Characters", "heading colon": r":\s*</h[23]>",
              "bold-line heading": r"<p><strong>[^<]{1,60}</strong><br", "red wiki link": r'<a href="/wiki/', "dash list": r"<p>- ", "glance box": r'class="callout glance"',
              "summary heading": r"<h[23][^>]*>Summary",
              "heading as a bullet": r"<li><strong>[^<]*:</strong></li>"}
    problems = []
    for slug, _ in posts:
        page = (out / "posts" / slug / "index.html").read_text(encoding="utf-8")
        body = re.split(r'<div class="prose"[^>]*>', page, maxsplit=1)[1].split("</article>", 1)[0]
        body = body.split('<section class="where-we-were">', 1)[0]
        body = re.sub(r"<blockquote>.*?</blockquote>", "", body, flags=re.S)  # quoted letters keep their bold
        problems += [f"{slug}: {name}: {m.group(0)[:60]}" for name, rx in checks.items()
                     for m in [re.search(rx, body)] if m]
        if 'class="pills"' not in page:
            problems.append(f"{slug}: no pills")
    assert problems == []


def test_pills_match_the_characters_list(site):
    _, posts = site
    assert dict(posts)["the-quest-for-the-missing-bones"] == [
        "aera-shan-ravanor", "gumbo", "liren", "malron-lichtstrahl", "shabasta"]  # named without links
    assert dict(posts)["the-beacon-of-argynvostholt"] == ["aera-shan-ravanor", "crusty", "malron-lichtstrahl", "olfin-darning",
                                             "shabasta"]


def test_every_story_has_its_parent_heading_and_long_ones_their_scenes(site):
    out, posts = site
    problems = []
    for slug, _ in posts:
        page = (out / "posts" / slug / "index.html").read_text(encoding="utf-8")
        if page.count(">Malron’s Account</h2>") != 1:
            problems.append(f"{slug}: no Malron’s Account heading")
    assert problems == []
    beacon = (out / "posts" / "the-beacon-of-argynvostholt" / "index.html").read_text(encoding="utf-8")
    assert 'class="toc-h3"><a href="#called-before-noon">Called Before Noon' in beacon


def test_one_rule_between_the_slides_and_the_story():
    """The story's own heading draws the rule above it, so the slides draw none below them."""
    css = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
    assert re.search(r"\.prose h2 \{[^}]*border-top", css)
    assert not re.search(r"section\.deck, section\.decks \{[^}]*border-bottom", css)
