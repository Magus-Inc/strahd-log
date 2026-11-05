"""Section headings link to themselves (Chris, 2026-11-04): the only way to get a link like
/start/#story was from the home page's buttons, so every h2 and h3 on a page carries a small link to
its own section that readers can tap (it copies the address too) and share."""
import re

import pytest

import build
import headings

LINK = re.compile(r'<a class="heading-link" href="#([^"]+)"')


def test_heading_with_an_id_links_to_it():
    html = headings.link_headings('<main><h2 id="loot">Loot</h2></main>')
    assert LINK.findall(html) == ["loot"]
    assert html.startswith('<main><h2 id="loot">Loot<a class="heading-link"')


def test_heading_that_names_a_section_links_to_the_section():
    # The home page's buttons go to /start/#story, the section, not to its heading's own id.
    html = headings.link_headings('<main><section class="start-section" id="story" aria-labelledby="story-title">'
                                  '<h2 id="story-title">The story so far</h2></section></main>')
    assert LINK.findall(html) == ["story"]


def test_heading_without_an_id_gets_one_that_no_other_element_uses():
    html = headings.link_headings('<main><section id="the-plan"></section><h3>The Plan</h3><h3>The Plan</h3></main>')
    assert LINK.findall(html) == ["the-plan-2", "the-plan-3"]
    assert '<h3 id="the-plan-2">The Plan<a' in html


def test_card_titles_scripts_and_the_header_are_left_alone():
    page = ('<header><h2>Menu</h2></header><main>'
            '<h3><a class="stretched" href="/wiki/x/">X</a></h3>'
            '<h2><a id="place-title" href="#"></a></h2>'
            '<script>var t = "<h2>' + "' + name + '" + '</h2>";</script></main>'
            '<script>var u = "<h3>Nope</h3>";</script>')
    assert headings.link_headings(page) == page


def test_the_link_adds_no_words_to_the_heading():
    # Tables of contents, search and tests read heading text; the link is an icon with a label.
    html = headings.link_headings('<main><h2 id="loot">Loot</h2></main>')
    m = re.search(r"<h2[^>]*>(.*)</h2>", html, re.S)
    assert re.sub(r"<[^>]+>", "", m.group(1)) == "Loot"
    assert 'aria-label="Link to this section: Loot"' in html


def test_build_links_the_headings_of_every_page_it_writes(tmp_path):
    out = tmp_path / "page.html"
    build.write(out, '<main><h2 id="loot">Loot</h2></main>')
    assert LINK.findall(out.read_text(encoding="utf-8")) == ["loot"]
    build.write(tmp_path / "feed.xml", "<h2>Loot</h2>")
    assert "heading-link" not in (tmp_path / "feed.xml").read_text(encoding="utf-8")


START_SECTIONS = ["party", "story", "fortune", "map", "how-to-read", "about"]


def test_start_here_sections_are_linkable(real_build):
    html = (real_build.out / "start" / "index.html").read_text(encoding="utf-8")
    links = LINK.findall(html)
    for section in START_SECTIONS:
        assert section in links, section
    chapters = re.findall(r'<h3 id="([^"]+)">[^<]*<a class="heading-link"', html)
    assert len(chapters) >= 6  # each story chapter can be shared too


def test_every_heading_link_on_the_site_lands_on_its_page(real_build):
    pages = sorted(real_build.out.rglob("*.html"))
    linked = 0
    for path in pages:
        html = path.read_text(encoding="utf-8")
        ids = set(re.findall(r'\sid="([^"]+)"', html))
        for target in LINK.findall(html):
            assert target in ids, f"{path.relative_to(real_build.out)} links to missing #{target}"
            linked += 1
        all_ids = re.findall(r'\sid="([^"]+)"', html)
        for target in re.findall(r'<h[23] id="([^"]+)"', html):
            assert all_ids.count(target) == 1, f"{path.relative_to(real_build.out)} has #{target} twice"
    assert linked > 500


def test_post_sections_link_to_themselves(real_build):
    post = real_build.posts[0]
    html = (real_build.out / post.path / "index.html").read_text(encoding="utf-8")
    main = html.split('<main', 1)[1].split("</main>", 1)[0]
    for level, attrs, inner in re.findall(r"<h([23])([^>]*)>(.*?)</h\1>", main, re.S):
        if 'class="stretched"' in inner or "<a " in inner.split('<a class="heading-link"')[0]:
            continue
        assert 'class="heading-link"' in inner, f"h{level} {inner[:60]}"


def test_tapping_a_heading_link_copies_the_address():
    base = (build.ROOT / "templates" / "base.html").read_text(encoding="utf-8")
    assert "a.heading-link" in base and "clipboard" in base
    css = (build.ROOT / "static" / "style.css").read_text(encoding="utf-8")
    assert ".heading-link" in css


# --- found in review --------------------------------------------------------------------------

def test_a_section_with_an_id_is_the_target_even_without_aria_labelledby():
    # The tags page: <section id="wolves"><h2>Wolves</h2>; its tag cloud links to #wolves.
    html = headings.link_headings('<main><section class="tag-section" id="wolves">\n  <h2>Wolves</h2>\n</section></main>')
    assert LINK.findall(html) == ["wolves"]
    assert 'aria-labelledby="wolves-title-name"' in html and '<h2 id="wolves-title">' in html


def test_a_section_is_still_named_by_its_heading_words_alone():
    # Screen readers name a region from aria-labelledby: the link's label must not be read twice.
    html = headings.link_headings('<main><section id="story" aria-labelledby="story-title">'
                                  '<h2 id="story-title">The story so far</h2></section></main>')
    label = re.search(r'aria-labelledby="([^"]+)"', html).group(1)
    named = re.search(rf'id="{label}"[^>]*>(.*?)</', html).group(1)
    assert named == "The story so far"


def test_single_quoted_ids_and_empty_headings():
    html = headings.link_headings("<main><h2 id='b'>B</h2><h3><img src=x alt=''></h3></main>")
    assert LINK.findall(html) == ["b"] and html.count("id=") == 1


def test_the_wiki_pages_lists_keep_the_same_address_as_sessions_are_added(real_build):
    html = (real_build.out / "wiki" / "castle-ravenloft" / "index.html").read_text(encoding="utf-8")
    links = LINK.findall(html)
    assert "appears-in" in links and "on-the-map" in links
    assert not any(re.search(r"\d", t) for t in links)


def test_the_icon_is_bright_enough_to_see_on_a_phone():
    css = (build.ROOT / "static" / "style.css").read_text(encoding="utf-8")
    rule = re.search(r"\.heading-link \{([^}]*)\}", css).group(1)
    assert float(re.search(r"opacity: ([\d.]+)", rule).group(1)) >= 0.75
