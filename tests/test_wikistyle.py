"""The wiki page template: one layout for every wiki page (Chris, 2026-11-02, the Zorya page)."""
from pathlib import Path

import pytest

import build
import wikistyle

ROOT = Path(build.__file__).parent
md = build.render_markdown

# A page the way update-wiki writes them: a Description with the picture, then the compiled notes.
PAGE = """Aera's companion.

## What she is

* **Tiny undead.** AC 13.

## Description

![Zorya, a ghostly pseudodragon](/images/zorya-ai.jpg)

*AI-generated image (Google Gemini, November 2026), drawn from this page and the session logs. Not official art.*

*Written from the session logs, in Malron's words.*

When we first explored Argynvostholt, a pseudodragon found Aera.

<!-- from-the-log -->
## From the adventure log

*Compiled from the session posts. Each line links to the session it comes from.*

* Found at Argynvostholt.
* Scouted for Gertruda.
"""


def style(**picks) -> dict:
    return {**wikistyle.AS_WRITTEN, **{k.replace("_", "-"): v for k, v in picks.items()}}


def test_defaults_leave_pages_as_written(tmp_path):
    assert wikistyle.load_style(tmp_path / "missing.yaml") == wikistyle.AS_WRITTEN
    html = md(PAGE)
    out = wikistyle.apply(html, wikistyle.AS_WRITTEN, "creature")
    assert out.html == html and out.picture == ""


def test_unknown_setting_or_value_is_refused(tmp_path):
    f = tmp_path / "wiki-style.yaml"
    f.write_text("top: confetti\n", encoding="utf-8")
    with pytest.raises(ValueError, match="top"):
        wikistyle.load_style(f)
    f.write_text("colour: red\n", encoding="utf-8")
    with pytest.raises(ValueError, match="colour"):
        wikistyle.load_style(f)


# --- the picture at the top ------------------------------------------------------------------

@pytest.mark.parametrize("top", ["picture", "infobox"])
def test_first_picture_and_its_credit_move_to_the_top(top):
    out = wikistyle.apply(md(PAGE), style(top=top), "creature")
    assert 'src="/images/zorya-ai.jpg"' in out.picture and "AI-generated image" in out.picture
    assert "zorya-ai.jpg" not in out.html and "AI-generated" not in out.html
    assert "Written from the session logs" not in out.picture  # not a caption


def test_a_drawing_keeps_its_own_caption_and_the_second_picture_stays_in_the_text():
    page = ("## Description\n\n![Crusty, drawn by Grant](/images/crusty-by-grant.jpg)\n\n*Crusty, drawn by Grant Haseloff.*\n\n"
            "![Crusty, AI](/images/crusty-ai-portrait.jpg)\n\n*AI-generated portrait. Not player art.*\n\nCrusty stands tall.\n")
    out = wikistyle.apply(md(page), style(top="picture"), "character")
    assert "crusty-by-grant.jpg" in out.picture and "drawn by Grant Haseloff" in out.picture
    assert "crusty-ai-portrait.jpg" in out.html and "crusty-ai-portrait.jpg" not in out.picture


def test_a_picture_vote_moves_up_whole():
    html = md(PAGE.replace("![Zorya, a ghostly pseudodragon](/images/zorya-ai.jpg)",
                           "![Zorya](/images/zorya-ai.jpg)\n\n![Zorya](/images/zorya-ai-2.jpg)"))
    html = build.article.ai_credits(build.article.add_image_votes(html))
    out = wikistyle.apply(html, style(top="picture"), "creature")
    assert out.picture.count("<img") == 2 and 'class="vote-group' in out.picture
    assert "<img" not in out.html


def test_a_picture_in_the_compiled_notes_stays_there():
    page = "Text.\n\n<!-- from-the-log -->\n## From the adventure log\n\n![Map](/images/map.jpg)\n"
    out = wikistyle.apply(md(page), style(top="picture"), "place")
    assert out.picture == "" and "map.jpg" in out.html


# --- one story, told once --------------------------------------------------------------------

def test_description_is_titled_malrons_account_without_the_written_from_line():
    out = wikistyle.apply(md(PAGE), style(story_heading="account"), "creature")
    assert "<h2>Malron’s Account</h2>" in out.html and ">Description<" not in out.html
    assert "Written from the session logs" not in out.html


def test_story_heading_can_go():
    out = wikistyle.apply(md(PAGE), style(story_heading="none"), "creature")
    assert ">Description<" not in out.html and "<h2>Malron" not in out.html
    assert "When we first explored" in out.html


def test_sections_above_the_story_move_below_it():
    out = wikistyle.apply(md(PAGE), style(extras="after-story"), "creature")
    h = out.html
    assert h.index("companion") < h.index(">Description<") < h.index("When we first") \
        < h.index("What she is") < h.index("Tiny undead") < h.index("From the adventure log")


def test_compiled_notes_fold_under_a_story():
    out = wikistyle.apply(md(PAGE), style(log="folded"), "creature")
    assert '<details class="log-notes">' in out.html
    assert "<summary>From the adventure log: 2 notes, session by session</summary>" in out.html
    assert "<h2>From the adventure log</h2>" not in out.html
    assert "Found at Argynvostholt" in out.html and out.html.rstrip().endswith("</details>")


def test_compiled_notes_can_be_left_off_a_page_with_a_story():
    out = wikistyle.apply(md(PAGE), style(log="hidden"), "creature")
    assert "From the adventure log" not in out.html and "Found at Argynvostholt" not in out.html
    assert "When we first explored" in out.html


def test_a_page_with_only_compiled_notes_keeps_them_open():
    page = "<!-- from-the-log -->\n## From the adventure log\n\n* Sold us a wagon.\n"
    for log in ("folded", "hidden"):
        out = wikistyle.apply(md(page), style(log=log), "npc")
        assert "<h2>From the adventure log</h2>" in out.html and "Sold us a wagon" in out.html


def test_people_only_leaves_places_and_items_as_written():
    picks = style(top="picture", log="folded", kinds="people")
    assert wikistyle.apply(md(PAGE), picks, "place").html == md(PAGE)
    assert wikistyle.apply(md(PAGE), picks, "item").picture == ""
    for kind in ("character", "npc", "creature"):
        assert wikistyle.apply(md(PAGE), picks, kind).picture


# --- the infobox's facts ---------------------------------------------------------------------

class P:  # a stand-in post
    def __init__(self, n):
        self.number, self.title, self.path = n, f"Session {n}", f"posts/s{n}/"


def test_facts_first_and_last_seen_and_how_many_sessions():
    page = build.wiki.WikiPage(slug="zorya", title="Zorya", type="creature", aliases=["Pseudodragon Spirit"],
                               mentioned_in=[P(54), P(48), P(37)])  # newest first, as the build keeps them
    facts = dict(wikistyle.facts(page))
    assert facts["Also known as"] == "Pseudodragon Spirit"
    assert facts["First seen"] == (37, "Session 37", "posts/s37/")
    assert facts["Last seen"] == (54, "Session 54", "posts/s54/")
    assert facts["Sessions"] == 3


def test_facts_for_a_pc_and_a_page_seen_once():
    page = build.wiki.WikiPage(slug="malron", title="Malron", type="character", player="Chris", mentioned_in=[P(5)])
    facts = dict(wikistyle.facts(page))
    assert facts["Played by"] == "Chris" and "First seen" in facts
    assert "Last seen" not in facts and "Sessions" not in facts


# --- the blog --------------------------------------------------------------------------------

def test_blog_uses_the_picks():
    """Chris's picks on the wiki layout page (2026-11-02)."""
    assert wikistyle.load_style(ROOT / "data" / "wiki-style.yaml") == {
        "top": "infobox", "story-heading": "account", "story-title": "Malron’s Account",
        "extras": "after-story", "log": "folded", "kinds": "all"}


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    out = tmp_path_factory.mktemp("wiki-site") / "public"
    build.build(out_dir=out, site_url="https://owlbear.dicelore.quest", base_path="/")
    return out


def page(site, slug):
    return (site / "wiki" / slug / "index.html").read_text(encoding="utf-8")


def test_zorya_reads_picture_story_stats_then_folded_notes(site):
    """The page Chris asked about: picture and facts under the title, the story once, notes folded."""
    html = page(site, "zorya")
    assert html.index('class="infobox"') < html.index("zorya-ai.jpg") < html.index('<div class="prose">') \
        < html.index("<h2>Malron’s Account</h2>") < html.index("What she is") < html.index('<details class="log-notes">')
    assert ">First seen<" in html and ">Last seen<" in html and "Also known as" in html
    assert "Written from the session logs" not in html and ">Description<" not in html
    lede_and_body = html[html.index('<div class="prose">'):]
    assert "pseudodragon companion" not in lede_and_body  # the line under the title is not repeated


def test_every_wiki_picture_is_at_the_top_of_its_page(site):
    for f in sorted((ROOT / "content" / "wiki").glob("*.md")):
        md_text = f.read_text(encoding="utf-8")
        if "![" not in md_text.split("<!-- from-the-log -->")[0]:
            continue
        html = page(site, f.stem)
        top = html[:html.index('<div class="prose">')]
        assert '<aside class="infobox"' in top and "<img" in top, f.stem


def test_no_wiki_page_tells_its_story_under_description_any_more(site):
    for d in (site / "wiki").iterdir():
        if (d / "index.html").is_file():
            html = (d / "index.html").read_text(encoding="utf-8")
            assert "<h2>Description</h2>" not in html, d.name
            if "<h2>Malron’s Account</h2>" in html and "From the adventure log" in html:
                assert '<details class="log-notes">' in html, d.name


def test_a_picture_vote_at_the_top_sits_side_by_side():
    css = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
    assert ".infobox-picture .image-vote { display: grid; grid-template-columns: 1fr 1fr;" in css


def test_agents_md_says_where_the_wiki_layout_lives():
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "data/wiki-style.yaml" in text and "wikistyle.py" in text


def test_the_wiki_writing_rules_live_in_dnd_scribe():
    """Chris, 2026-11-02: the writing rules are ours; this public repo keeps only the build."""
    assert not (ROOT / ".claude" / "skills" / "update-wiki").exists()
    assert "dnd-scribe's `update-wiki` skill" in (ROOT / "AGENTS.md").read_text(encoding="utf-8")
