"""The post style template: one look for every post, whatever era it was written in."""
import re
from pathlib import Path

import pytest

import build
import poststyle

ROOT = Path(build.__file__).parent
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
                     "bold": "plain", "glance": "new-posts", "tagline": "keep", "picture": "scene"}


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

@pytest.fixture(scope="module")
def site(tmp_path_factory):
    out = tmp_path_factory.mktemp("site")
    # Plain values only: a failing assert would otherwise try to print the posts' wiki graph.
    posts = [(p.slug, [c.slug for c in p.cast]) for p in build.build(out_dir=out)]
    return out, posts


def test_every_post_follows_the_template(site):
    out, posts = site
    checks = {"Characters section": r"<h[23][^>]*>Characters", "heading colon": r":\s*</h[23]>",
              "bold-line heading": r"<p><strong>[^<]{1,60}</strong><br", "red wiki link": r'<a href="/wiki/', "dash list": r"<p>- ",
              "heading as a bullet": r"<li><strong>[^<]*:</strong></li>"}
    problems = []
    for slug, _ in posts:
        page = (out / "posts" / slug / "index.html").read_text(encoding="utf-8")
        body = page.split('<div class="prose">', 1)[1].split("</article>", 1)[0]
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
