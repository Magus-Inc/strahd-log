"""The post style template: one look for every post, whatever era it was written in."""
import re
from pathlib import Path

import pytest

import build
import article
import poststyle

ROOT = Path(build.__file__).parent
TAGLINE_LOOK, CARD_TAGLINE = "subtitle", "instead"  # Chris's tagline picks (2026-11-02 tagline look page)
md = build.render_markdown


# --- settings -------------------------------------------------------------------------------

def test_defaults_leave_posts_as_written(tmp_path):
    style = poststyle.load_style(tmp_path / "missing.yaml")
    assert style == poststyle.AS_WRITTEN
    html = md("**Seeking Szoldar**  \nWe set out.\n\n## Characters:\n\n* [Aera](/wiki/aera/)\n")
    assert poststyle.apply(html, style).html == html


def test_unknown_setting_or_value_is_refused(tmp_path):
    f = tmp_path / "style.yaml"
    f.write_text("cast: confetti\n", encoding="utf-8")
    with pytest.raises(ValueError, match="cast"):
        poststyle.load_style(f)
    f.write_text("colour: red\n", encoding="utf-8")
    with pytest.raises(ValueError, match="colour"):
        poststyle.load_style(f)


def test_blog_uses_the_picks():
    """Chris's picks for this blog (2026-11-01 post style page)."""
    style = poststyle.load_style(ROOT / "data" / "post-style.yaml")
    assert style == {"cast": "pills", "headings": "real", "entries": "bullets", "links": "gold",
                     "bold": "plain", "glance": "none", "tagline": "keep", "picture": "scene",
                     "story": "titled", "story-title": "Malron’s Account", "scenes": "written",
                     # the layout review, 2026-11-02
                     "slides": "above-story", "opening": "in-story", "extra-titles": "hide", "quotes": "letters",
                     "recap-prose": "bullets", "sections": "template", "recap-pictures": "story",
                     "relink": "each-heading",
                     # the tagline look, 2026-11-02
                     "tagline-look": TAGLINE_LOOK, "card-tagline": CARD_TAGLINE}


# --- cast -----------------------------------------------------------------------------------

CHARS = "## Characters:\n\n* [Aera shan Ravanór](/wiki/aera-shan-ravanor/)\n* [Crusty](/wiki/crusty/)\n\n## Summary:\n\nWe ran.\n"


def test_pills_drop_the_characters_list_and_report_who_it_named():
    out = poststyle.apply(md(CHARS), {**poststyle.AS_WRITTEN, "cast": "pills"})
    assert "Characters" not in out.html and "We ran." in out.html
    assert 'href="/wiki/crusty/"' in out.characters and "Summary" not in out.characters


def test_pills_drop_the_old_bold_characters_block_with_race_and_class():
    text = ("**Characters:**  \n- **Liren:** Dragonborn Barbarian  \n- **Aera:** Elf Rogue\n\n"
            "**Summary:**  \nFather Lucian helped us.\n")
    for headings in ("as-written", "real"):
        out = poststyle.apply(md(text), {**poststyle.AS_WRITTEN, "cast": "pills", "headings": headings})
        assert "Characters" not in out.html and "Dragonborn" not in out.html, headings
        assert "Father Lucian helped us." in out.html
        assert "Liren" in out.characters and "Aera" in out.characters


def test_list_keeps_the_section_and_still_reports_who_it_named():
    out = poststyle.apply(md(CHARS), {**poststyle.AS_WRITTEN, "cast": "list"})
    assert "<h2>Characters:</h2>" in out.html and 'href="/wiki/crusty/"' in out.characters


# --- headings -------------------------------------------------------------------------------

REAL = {**poststyle.AS_WRITTEN, "headings": "real"}


def test_bold_first_lines_become_headings():
    html = poststyle.apply(md("**Seeking Szoldar**  \nWe set out.\n\n**The Crossroads**  \nTwo scarecrows.\n"), REAL).html
    assert html == "<h3>Seeking Szoldar</h3>\n<p>We set out.</p>\n<h3>The Crossroads</h3>\n<p>Two scarecrows.</p>"


def test_section_names_are_h2_and_place_headings_h3_without_colons():
    html = poststyle.apply(md("## Vallaki\n\nTown.\n\n### Key Locations:\n\nx\n\n**Summary:**  \nWe ran.\n"), REAL).html
    assert "<h3>Vallaki</h3>" in html and "<h2>Key Locations</h2>" in html and "<h2>Summary</h2>" in html
    assert ":</h" not in html


def test_quoted_writing_is_left_alone():
    text = "> **Q: Are you working for Strahd?**  \n> **A: No**\n\nHe said **no**.\n"
    html = poststyle.apply(md(text), {**poststyle.AS_WRITTEN, "headings": "real", "bold": "plain"}).html
    assert "<blockquote>\n<p><strong>Q: Are you working for Strahd?</strong><br>" in html
    assert "<p>He said no.</p>" in html


def test_a_name_on_its_own_line_in_a_recap_section_is_an_entry():
    text = "## Notable NPCs:\n\n**Cyrus Belview**  \nThe castle's cook.\n\n**What we learned:**  \nMuch.\n"
    html = poststyle.apply(md(text), {**REAL, "entries": "bullets"}).html
    assert "<li><strong>Cyrus Belview</strong>: The castle&rsquo;s cook.</li>" in html
    assert "<h2>What we learned</h2>" in html


def test_a_bold_line_alone_is_a_heading_even_in_a_recap_section():
    html = poststyle.apply(md("## Notable NPCs:\n\n**Victor**: A wizard.\n\n**What we learned:**\n\n* **A:** b\n"),
                           {**REAL, "entries": "bullets"}).html
    assert "<h2>What we learned</h2>" in html and "<li><strong>Victor</strong>: A wizard.</li>" in html


def test_a_bold_quote_alone_is_not_a_heading():
    text = "**\u201cThe cows have teeth after all.\u201d**\n"
    assert poststyle.apply(md(text), REAL).html == md(text)


def test_label_lines_are_not_headings():
    html = poststyle.apply(md("**Victor**: A wizard.  \n**Stella**: His daughter.\n"), REAL).html
    assert "<h" not in html


# --- entries --------------------------------------------------------------------------------

BULLETS = {**poststyle.AS_WRITTEN, "entries": "bullets"}


def test_run_together_entries_become_one_bullet_each():
    text = ("## Encounters:\n\n**Lady Fiona**: We talked.  \n**The druid**: Watched us.\n\n"
            "**Mirror**: A mirror.\n\n## Summary:\n\n**Bold** start stays a paragraph.\n")
    html = poststyle.apply(md(text), BULLETS).html
    assert ("<ul>\n<li><strong>Lady Fiona</strong>: We talked.</li>\n<li><strong>The druid</strong>: Watched us.</li>\n"
            "<li><strong>Mirror</strong>: A mirror.</li>\n</ul>") in html
    assert "<p><strong>Bold</strong> start stays a paragraph.</p>" in html


def test_dash_lines_become_a_real_list():
    html = poststyle.apply(md("**Plot Points:**  \n- We spoke.  \n- We learned.\n"), {**REAL, "entries": "bullets"}).html
    assert html == "<h2>Plot Points</h2>\n<ul>\n<li>We spoke.</li>\n<li>We learned.</li>\n</ul>"


def test_prose_in_a_recap_section_stays_prose():
    text = "## Encounters:\n\nHarkus warned us of the order.\n"
    assert poststyle.apply(md(text), BULLETS).html == md(text)


# --- links and bold -------------------------------------------------------------------------

def test_hand_made_wiki_links_look_like_the_others():
    html = poststyle.apply(md("[Rose](/wiki/rose-durst/) and [a site](https://example.com/)."),
                           {**poststyle.AS_WRITTEN, "links": "gold"}).html
    assert '<a class="wiki-link" href="/wiki/rose-durst/">Rose</a>' in html
    assert '<a href="https://example.com/">' in html


def test_plain_story_unbolds_names_but_keeps_labels():
    text = ("## Summary:\n\nUnder the bed was **Pidlwick**. A **black dragon** burst out.\n\n"
            "**Reunion:** they rise.\n\n## Loot:\n\n* A ring worth **150 gold**\n")
    html = poststyle.apply(md(text), {**poststyle.AS_WRITTEN, "bold": "plain"}).html
    assert "<p>Under the bed was Pidlwick. A black dragon burst out.</p>" in html
    assert "<p><strong>Reunion:</strong> they rise.</p>" in html
    assert "<strong>150 gold</strong>" in html  # recap sections keep their bold


# --- story heading ------------------------------------------------------------------------

NOHEAD = {**poststyle.AS_WRITTEN, "headings": "real", "story": "no-heading"}


def test_the_summary_heading_goes_and_the_story_starts_after_the_pills():
    html = poststyle.apply(md("## Summary:\n\nWe ran.\n\n## Key Locations:\n\n* **A**: b\n"), NOHEAD).html
    assert "Summary" not in html and html.startswith("<!--story-->\n<p>We ran.</p>")
    assert "<h2>Key Locations</h2>" in html


def test_a_summary_with_a_title_keeps_the_title_as_a_scene_heading():
    html = poststyle.apply(md("## Summary: The Crawl\n\nWe crawled.\n"), NOHEAD).html
    assert "Summary" not in html and "<h3>The Crawl</h3>" in html


def test_the_old_bold_summary_line_goes_too():
    html = poststyle.apply(md("**Summary:**  \nFather Lucian helped us.\n"),
                           {**poststyle.AS_WRITTEN, "story": "no-heading"}).html
    assert html == "<!--story-->\n<p>Father Lucian helped us.</p>"


def test_slides_go_where_the_summary_heading_was():
    html = poststyle.apply(md("## Characters:\n\n* x\n\n## Summary:\n\nWe ran.\n\n## Loot:\n\n* y\n"), NOHEAD).html
    html = article.add_deck(html, ["slides/a/1.webp"])
    assert html.index("<h2>Characters</h2>") < html.index('class="deck"') < html.index("We ran.")


# --- story title and scene headings ---------------------------------------------------------

TITLED = {**NOHEAD, "story": "titled", "story-title": "Malron’s Account"}
SCENES = {**TITLED, "scenes": "written"}
TEMPLATE = ("## Characters:\n\n* x\n\n## Summary: The Crawl\n\nAs we woke, a revenant found us.\n\n"
            "We ran for three hours.\n\nNote: The table laughed.\n\n### The Foyer\n\nThick fog covered the floor.\n\n"
            "## Key Locations:\n\n### Krezk\n\n* **A**: b\n")


def test_the_story_gets_one_parent_heading_and_the_slides_sit_above_it():
    html = poststyle.apply(md(TEMPLATE), TITLED).html
    assert "Summary" not in html and "<!--story-->\n<h2>Malron’s Account</h2>" in html
    html = article.add_deck(html, ["slides/a/1.webp"])
    assert html.index('class="deck"') < html.index("<h2>Malron’s Account</h2>") < html.index("As we woke")


def test_a_post_with_no_summary_heading_gets_the_parent_heading_first():
    html = poststyle.apply(md("We crawled.\n\n### The Foyer\n\nFog.\n"), TITLED).html
    assert html.startswith("<!--story-->\n<h2>Malron’s Account</h2>\n<p>We crawled.</p>")


def test_the_parent_heading_goes_after_a_characters_list_that_stays():
    html = poststyle.apply(md("## Characters:\n\n* x\n\nWe crawled.\n"), {**TITLED, "cast": "list"}).html
    assert html.index("Characters") < html.index("Malron’s Account") < html.index("We crawled.")


def test_written_scene_headings_replace_the_old_ones_in_the_story_only():
    scenes = [("As we woke", "Called Before Noon"), ("Thick fog", "Strings of Black Wire")]
    html = poststyle.apply(md(TEMPLATE), SCENES, scenes).html
    assert re.findall(r"<h3>(.*?)</h3>", html) == ["Called Before Noon", "Strings of Black Wire", "Krezk"]
    assert html.index("<h2>Malron’s Account</h2>") < html.index("<h3>Called Before Noon</h3>\n<p>As we woke")
    assert "The Crawl" not in html and "The Foyer" not in html


def test_scene_anchors_ignore_case_quotes_and_links():
    html = md("He said, \u201cSome of you may die.\u201d\n\n[Krezk](/wiki/krezk/) at dawn.\n")
    out = poststyle.apply(html, SCENES, [('he said, "some of you', "One"), ("Krezk at", "Two")]).html
    assert "<h3>One</h3>\n<p>He said" in out and '<h3>Two</h3>\n<p><a' in out


def test_a_scene_anchor_that_matches_no_paragraph_or_two_is_an_error():
    with pytest.raises(ValueError, match="Lost words"):
        poststyle.apply(md("We ran.\n"), SCENES, [("Lost words", "X")])
    with pytest.raises(ValueError, match="We"):
        poststyle.apply(md("We ran.\n\nWe hid.\n"), SCENES, [("We", "X")])


def test_a_run_in_label_gives_way_to_the_written_heading():
    html = poststyle.apply(md("**The Secret Path.** In K-24 the room was wrecked.\n"), SCENES,
                           [("The Secret Path.", "The Coffin Wardrobe")]).html
    assert "<h3>The Coffin Wardrobe</h3>\n<p>In K-24" in html and "Secret Path" not in html


def test_scenes_as_written_ignore_the_list():
    html = poststyle.apply(md(TEMPLATE), TITLED, [("As we woke", "Called Before Noon")]).html
    assert "Called Before Noon" not in html and "<h3>The Crawl</h3>" in html


def test_every_post_has_its_scene_headings_listed():
    """Each post is listed, even with no breaks (a very short story), and headings stay short."""
    scenes = poststyle.load_scenes(ROOT / "data" / "scene-headings.yaml")
    slugs = {build.split_front_matter(p.read_text(encoding="utf-8"))[0]["slug"]
             for p in (ROOT / "content" / "posts").glob("*.md")}
    assert set(scenes) == slugs
    long = [h for hs in scenes.values() for _, h in hs if len(h.split()) > 6]
    assert long == []


# --- glance, picture ------------------------------------------------------------------------

def test_glance_none_removes_the_box():
    text = "## At a Glance:\n\n* **A:** b\n\n## Summary:\n\nx\n"
    html = poststyle.apply(md(text), {**poststyle.AS_WRITTEN, "glance": "none"}).html
    assert "Glance" not in html and "<h2>Summary:</h2>" in html


def test_picture_top_moves_the_feature_picture_and_credit_first():
    text = ("One.\n\nTwo.\n\n![Horngaard](/images/vladimir-horngaard-ai.jpg)\n\n"
            "*AI-generated image (Google Gemini, October 2026). Not official art.*\n\nThree.\n")
    html = poststyle.apply(md(text), {**poststyle.AS_WRITTEN, "picture": "top"}).html
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
