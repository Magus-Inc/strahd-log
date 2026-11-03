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


# --- phrases: the build links these words in posts and log notes too (Chris picked it, 2026-11-02) --------

PHRASES = wiki.load_phrases(build.ROOT / "data" / "described-places.yaml", PAGES)


def test_a_phrase_links_only_its_bracketed_words_and_counts_as_a_mention():
    cave = wiki.WikiPage(slug="cave", title="Lake Baratok Cave", type="place", summary="The den.")
    abbey = wiki.WikiPage(slug="abbey", title="Abbey of St. Markovia", type="place", summary="An abbey.")
    linker = wiki.Linker([cave, abbey], {"cave": ["werewolf den"], "abbey": ["the [Abbey]"]})
    html, mentioned = linker.link("<p>The werewolf den lies west. We rode to the Abbey. The Abbey again.</p>")
    assert '<a class="wiki-link" href="/wiki/cave/" title="The den.">werewolf den</a>' in html
    assert 'to the <a class="wiki-link" href="/wiki/abbey/" title="An abbey.">Abbey</a>.' in html
    assert html.count("/wiki/abbey/") == 1 and mentioned == {"cave", "abbey"}
    # A capital at the start of a sentence still matches; other words around the phrase do not.
    html, _ = linker.link("<p>Werewolf den, then the Abbeys and the abbeyard.</p>")
    assert '<a class="wiki-link" href="/wiki/cave/" title="The den.">Werewolf den</a>' in html
    assert "/wiki/abbey/" not in html


def test_a_name_that_starts_in_a_phrase_wins_and_a_name_after_it_still_links():
    pages = [wiki.WikiPage(slug="abbey", title="Abbey of St. Markovia", type="place"),
             wiki.WikiPage(slug="markovia", title="St. Markovia", type="npc"),
             wiki.WikiPage(slug="tower", title="Tower of Khazan", type="place"),
             wiki.WikiPage(slug="lake", title="Lake Baratok", type="place")]
    linker = wiki.Linker(pages, {"abbey": ["the [Abbey]"], "tower": ["[tower] at Lake Baratok"]})
    html, mentioned = linker.link("<p>We rode to the Abbey of St. Markovia, then the tower at Lake Baratok.</p>")
    assert '<a class="wiki-link" href="/wiki/abbey/" title="Abbey of St. Markovia">Abbey of St. Markovia</a>' in html
    assert '<a class="wiki-link" href="/wiki/tower/" title="Tower of Khazan">tower</a> at ' \
           '<a class="wiki-link" href="/wiki/lake/" title="Lake Baratok">Lake Baratok</a>' in html
    assert mentioned == {"abbey", "tower", "lake"}


def test_a_bold_list_entry_that_is_a_phrase_links_its_words():
    castle = wiki.WikiPage(slug="castle", title="Castle Ravenloft", type="place")
    linker = wiki.Linker([castle], {"castle": ["the [castle]"]})
    html = wiki.link_npc_names("<h2>Key Locations</h2><p><strong>The castle</strong>: dark.</p>", linker)
    assert '<strong>The <a class="wiki-link" href="/wiki/castle/"' in html


def test_a_phrase_listed_for_two_places_is_refused(tmp_path):
    path = tmp_path / "described-places.yaml"
    path.write_text("phrases:\n  a: [the castle]\n  b: [The castle]\n", encoding="utf-8")
    pages = [wiki.WikiPage(slug=s, title=s.upper() + " page", type="place") for s in "ab"]
    with pytest.raises(ValueError, match="twice"):
        wiki.load_phrases(path, pages)


def test_a_phrase_never_links_on_its_own_page_or_inside_a_heading():
    cave = wiki.WikiPage(slug="cave", title="Lake Baratok Cave", type="place")
    linker = wiki.Linker([cave], {"cave": ["werewolf den"]})
    assert "<a " not in linker.link("<h2>The werewolf den</h2><p>The werewolf den.</p>", self_slug="cave")[0]


def test_phrases_name_real_pages_and_are_not_already_names():
    names = {wiki.fold(n) for p in PAGES for n in p.names}
    for slug, phrases in PHRASES.items():
        assert slug in BY_SLUG
        for phrase in phrases:
            assert wiki.fold(phrase.replace("[", "").replace("]", "")) not in names, phrase


def test_posts_and_log_notes_link_the_werewolf_den(site_pages):
    post = site_pages["posts/shadows-over-st-markovia"]
    assert re.search(r'href="/wiki/lake-baratok-cave/"[^>]*>werewolf den<', post)
    emil = site_pages["wiki/emil"]
    assert re.search(r'href="/wiki/lake-baratok-cave/"[^>]*>werewolf den<', emil)
    assert re.search(r'href="/wiki/abbey-of-saint-markovia/"[^>]*>abbey<', site_pages["wiki/liren"])


@pytest.fixture(scope="module")
def site_pages(tmp_path_factory):
    out = tmp_path_factory.mktemp("place-links") / "public"
    build.build(out_dir=out, site_url="https://owlbear.dicelore.quest", base_path="/")

    class Pages(dict):
        def __missing__(self, path):
            return (out / path / "index.html").read_text(encoding="utf-8")
    return Pages()


def facts_box(html: str) -> str:
    return re.search(r'<aside class="infobox".*?</aside>', html, re.S).group(0)


def row(html: str, label: str) -> set[str]:
    m = re.search(rf"<dt>{label}</dt>\s*<dd>(.*?)</dd>", facts_box(html), re.S)
    return links(m.group(1)) if m else set()


# --- Nearby, Places inside, Part of (Chris picked all three, 2026-11-02) -----------------------------------

import yaml  # noqa: E402

NEARBY = yaml.safe_load((build.ROOT / "data" / "nearby.yaml").read_text(encoding="utf-8"))["nearby"]
MAPPED = yaml.safe_load((build.ROOT / "data" / "map.yaml").read_text(encoding="utf-8"))["places"]


def test_nearby_lists_name_mapped_places_and_go_both_ways():
    for slug, near in NEARBY.items():
        assert slug in MAPPED and slug not in near, slug
        for other in near:
            assert other in MAPPED, (slug, other)
            assert slug in NEARBY.get(other, []), f"{other} should list {slug} as nearby too"


def test_every_place_on_the_map_has_a_nearby_place():
    assert set(MAPPED) <= set(NEARBY)


def test_lake_baratok_shows_the_tower_and_the_den_as_nearby(site_pages):
    near = row(site_pages["wiki/lake-baratok"], "Nearby")
    assert {"tower-of-khazan", "lake-baratok-cave", "luna-river-crossroads"} <= near
    assert "lake-baratok" in row(site_pages["wiki/lake-baratok-cave"], "Nearby")


def test_places_inside_and_part_of_come_from_the_map(site_pages):
    assert {"blue-water-inn", "wachterhaus", "baron-s-mansion"} <= row(site_pages["wiki/vallaki"], "Places inside")
    assert row(site_pages["wiki/shrine-of-mother-night"], "Part of") == {"lake-baratok-cave"}
    assert "shrine-of-mother-night" in row(site_pages["wiki/lake-baratok-cave"], "Places inside")
    # People and items get none of these rows.
    assert not row(site_pages["wiki/ireena-kolyana"], "Nearby")


# --- The church in Barovia village (Chris picked it, 2026-11-02) ------------------------------------------

def test_barovia_village_church_has_a_page_inside_the_village(site_pages):
    church = BY_SLUG["barovia-village-church"]
    assert church.type == "place"
    assert row(site_pages["wiki/barovia-village-church"], "Part of") == {"barovia"}
    for slug in ("doru", "father-donavich", "barovia"):
        assert "barovia-village-church" in links(story(BY_SLUG[slug])), slug
    assert re.search(r'href="/wiki/barovia-village-church/"[^>]*>village church<',
                     site_pages["posts/rest-for-the-wicked"])
