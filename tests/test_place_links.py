"""A place named by description ("the werewolves' cave", "the tower at Lake Baratok") links its own page
(Chris, 2026-11-02): from Mother Night's page the cave should be one tap away, not two."""
import re

import pytest

import build
import wiki

PAGES = wiki.load_wiki(build.ROOT / "content" / "wiki", build.split_front_matter)
BY_SLUG = {p.slug: p for p in PAGES}
LINKER = wiki.Linker(PAGES)

# Words that can only mean one place in this campaign -> the page they mean. Kept to phrases that never
# point anywhere else in the posts: "the castle" and "the Abbey" are always Ravenloft and St. Markovia's;
# "the Vistani camp" or "the church" are not on the list, because there is more than one.
DESCRIBED = {
    r"werewol(?:f|ves)['’]? (?:den|cave)|cave (?:at|by) Lake Baratok": "lake-baratok-cave",
    r"tower (?:at|by|on the shore of) Lake Baratok": "tower-of-khazan",
    r"\bthe Abbey\b": "abbey-of-saint-markovia",
    r"\brefugee camp\b|\brefugees\b[^.]{0,40}\bcamp": "refugee-camp",
    r"\bwinery\b|\bthe vineyard\b": "wizard-of-wines",
    r"\bthe castle\b": "castle-ravenloft",
}


def story(page: wiki.WikiPage) -> str:
    """The page's own text (above the generated log), rendered and linked as the site shows it."""
    ours = page.body_md.split("<!-- from-the-log -->")[0]
    html, _ = LINKER.link(build.render_markdown(ours), self_slug=page.slug)
    return re.sub(r"<img [^>]*>", "", html)  # picture alt text is not a place a reader can tap


def links(html: str) -> set[str]:
    return set(re.findall(r'href="/wiki/([^/"#]+)/"', html))


def test_lake_baratok_links_the_tower_and_the_werewolf_den():
    assert {"tower-of-khazan", "lake-baratok-cave"} <= links(story(BY_SLUG["lake-baratok"]))


def test_mother_night_links_the_werewolves_cave_not_just_the_lake():
    html = story(BY_SLUG["mother-night"])
    assert "lake-baratok-cave" in links(html)
    assert re.search(r'<a class="wiki-link" href="/wiki/lake-baratok-cave/"[^>]*>werewolves', html)


def test_place_pages_link_the_places_they_touch():
    """The cave is up in the hills above the lake and the tower on its shore: each page links the others."""
    assert "lake-baratok" in links(story(BY_SLUG["lake-baratok-cave"]))
    assert "lake-baratok" in links(story(BY_SLUG["tower-of-khazan"]))


@pytest.mark.parametrize("slug", sorted(BY_SLUG))
def test_a_place_named_by_description_links_its_page(slug):
    page = BY_SLUG[slug]
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", page.body_md.split("<!-- from-the-log -->")[0])
    text = re.sub(r"\[[^\]]*\]\(/posts/[^)]*\)", "", text)  # post titles ("Finishing up at the vineyard")
    html = story(page)
    missing = [(m.group(0), target) for pattern, target in DESCRIBED.items() if target != slug
               for m in [re.search(pattern, text)] if m and target not in links(html)]
    assert not missing, f"{slug} names a place without linking it: {missing}"


def test_hand_written_wiki_links_look_like_the_automatic_ones():
    linker = wiki.Linker([wiki.WikiPage(slug="cave", title="Lake Baratok Cave", type="place",
                                        summary="The werewolf den.")])
    html, mentioned = linker.link('<p>In the <a href="/wiki/cave/">werewolves\' cave</a> we found it.</p>')
    assert '<a class="wiki-link" href="/wiki/cave/" title="The werewolf den.">werewolves\' cave</a>' in html
    assert mentioned == {"cave"}
    # Links that already carry a class (map sprites, citations) are left as they are.
    html, _ = linker.link('<p><a class="sprite" href="/wiki/cave/">x</a></p>')
    assert '<a class="sprite" href="/wiki/cave/">' in html
