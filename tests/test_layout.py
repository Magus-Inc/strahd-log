"""The layout review (2026-11-02): every post in the same order, whatever era it was written in.
Title, tagline, pills, then the slides, then Malron's Account (all of the story, its pictures too),
then the recap lists, then the map."""
import re
from pathlib import Path

import pytest

import article
import build
import poststyle
import wiki

ROOT = Path(build.__file__).parent
md = build.render_markdown
STYLE = {**poststyle.AS_WRITTEN, "story": "titled", "cast": "pills", "scenes": "written"}


def styled(text: str, **picks) -> str:
    return poststyle.apply(md(text), {**STYLE, **picks})


# A post in the one post format (tests/test_post_format.py); the story's opening lines and
# pictures are all under "## Story".
OPENING = ("## Story\n\nThe air of Castle Ravenloft has changed.\n\n"
           "![The flooded larders](/images/larders-ai.jpg)\n\n*AI-generated image (Google Gemini). Not official art.*\n\n"
           "### A Turning Point\n\nWe are at a turning point.\n\n"
           "## Key Locations\n\n* **Larders**: Cold.\n")


def test_a_note_about_the_post_stays_first():
    html = styled("Note: Written from the session notes.\n\n" + OPENING)
    assert html.index("Note: Written") < html.index(poststyle.STORY) < html.index("The air of Castle")


# --- slides -----------------------------------------------------------------------------------

def decks(html: str, at: str) -> str:
    return article.add_decks(html, [article.Deck("", "main", ["slides/a/1.webp"])], at)


def test_slides_sit_above_the_story_by_default():
    html = decks(styled(OPENING), "above-story")
    assert html.index('class="deck"') < html.index("Malron’s Account") < html.index("The air of Castle")


def test_slides_can_follow_the_story_or_close_the_post():
    html = decks(styled(OPENING), "after-story")
    assert html.index("We are at a turning") < html.index('class="deck"') < html.index("Key Locations")
    html = decks(styled(OPENING), "end")
    assert html.index("Key Locations") < html.index('class="deck"')
    assert html.rstrip().endswith("</section>")


# --- links: the first mention in every section -------------------------------------------------

def pages():
    return [wiki.WikiPage(slug="cyrus-belview", title="Cyrus Belview", type="npc", aliases=["Cyrus"]),
            wiki.WikiPage(slug="emil", title="Emil Toranescu", type="npc", aliases=["Emil"])]


SECTIONED = ("<h2>Malron’s Account</h2>\n<h3>The Wrong Spoon</h3>\n<p>Cyrus wanted a spoon. Cyrus waited.</p>\n"
             "<h3>The Cells</h3>\n<p>Cyrus pointed at Emil.</p>\n"
             "<h2>Notable NPCs</h2>\n<ul>\n<li>Cyrus Belview: The servant.</li>\n<li>Emil Toranescu: A prisoner.</li>\n</ul>")


def test_once_per_post_links_only_the_first_mention():
    html, _ = wiki.Linker(pages()).link(SECTIONED)
    assert html.count('href="/wiki/cyrus-belview/"') == 1


def test_each_heading_links_its_own_first_mention():
    html, mentioned = wiki.Linker(pages()).link(SECTIONED, each_section=r"<h[23][ >]")
    assert mentioned == {"cyrus-belview", "emil"}
    assert html.count('href="/wiki/cyrus-belview/"') == 3  # one per scene, one in Notable NPCs
    assert html.count('href="/wiki/emil/"') == 2
    assert "<p><a" in html and "Cyrus waited." in html  # the second mention in a scene stays plain
    assert '<li><a class="wiki-link" href="/wiki/cyrus-belview/"' in html


def test_a_hand_made_link_counts_for_its_own_section_only():
    text = ('<h3>One</h3>\n<p><a href="/wiki/emil/">Emil</a> and Emil.</p>\n<h3>Two</h3>\n<p>Emil.</p>')
    html, _ = wiki.Linker(pages()).link(text, each_section=r"<h[23][ >]")
    assert html.count('href="/wiki/emil/"') == 2


def test_the_blog_links_every_section():
    assert poststyle.load_style(ROOT / "data" / "post-style.yaml")["relink"] == "each-heading"


# --- every post, as built ----------------------------------------------------------------------

@pytest.fixture
def site(real_build):
    return real_build.out, [p.slug for p in real_build.posts]


def body(out: Path, slug: str) -> str:
    page = (out / "posts" / slug / "index.html").read_text(encoding="utf-8")
    prose = re.split(r'<div class="prose"[^>]*>', page, maxsplit=1)[1].split("</article>", 1)[0]
    return prose.split('<section class="where-we-were">', 1)[0]


def test_nothing_but_notes_and_slides_comes_before_the_story(site):
    out, slugs = site
    problems = []
    for slug in slugs:
        before = body(out, slug).split("<!--story-->", 1)[0]
        before = re.sub(r'<section class="decks?.*?</section>\s*', "", before, flags=re.S)
        before = re.sub(r'<aside class="margin-note".*?</aside>\s*', "", before, flags=re.S)
        if before.strip():
            problems.append(f"{slug}: {before.strip()[:80]}")
    assert problems == []


def test_no_headings_inside_quotes_and_no_pictures_in_the_recap(site):
    out, slugs = site
    problems = []
    for slug in slugs:
        html = body(out, slug)
        for quote in re.findall(r"<blockquote>.*?</blockquote>", html, re.S):
            if re.search(r"<h[1-6]", quote):
                problems.append(f"{slug}: heading in a quote")
        recap = re.split(r'<h2 id="(?:key-locations|encounters)"', html, maxsplit=1)
        if len(recap) > 1 and "<img" in recap[1]:
            problems.append(f"{slug}: picture in the recap")
    assert problems == []


def test_recap_lists_are_bullets(site):
    out, slugs = site
    problems = []
    names = "key-locations|encounters|loot|notable-npcs|plot-points|session-highlights"
    for slug in slugs:
        for section in re.findall(rf'<h2 id="(?:{names})">.*?(?=<h2|$)', body(out, slug), re.S):
            for p in re.findall(r"(?<!<li>)<p>(?!<img)(.*?)</p>", re.sub(r"<li>.*?</li>|<aside.*?</aside>", "", section, flags=re.S), re.S):
                problems.append(f"{slug}: {p[:60]}")
    assert problems == []


def test_every_notable_npc_entry_is_linked_when_the_wiki_has_them(site):
    out, _ = site
    html = body(out, "depths-of-ravenloft")
    npcs = re.search(r'<h2 id="notable-npcs">.*?</ul>', html, re.S).group(0)
    for slug in ("cyrus-belview", "emil", "volenta"):
        assert f'href="/wiki/{slug}/"' in npcs, slug


def test_depths_of_ravenloft_reads_in_order(site):
    out, _ = site
    html = body(out, "depths-of-ravenloft")
    assert "Chronicle of the Larder" not in html
    assert html.index("The Slides") < html.index("Malron’s Account") < html.index("The air of")


def test_each_section_relinks_under_big_headings_only():
    html, _ = wiki.Linker(pages()).link(SECTIONED, each_section=build.SECTION_START["each-section"])
    assert html.count('href="/wiki/cyrus-belview/"') == 2  # once in the story, once in Notable NPCs
