"""The flesh golem (Chris, 2026-11-03): its page is one tap away wherever the posts and the wiki name it,
and it is tied to Vasilka, who made the crown of flowers it still wears (Ryan, 7/21 session)."""
import re

import pytest

import build

GOLEM = 'href="/wiki/the-flesh-golem/"'


@pytest.fixture(scope="module")
def site_pages(tmp_path_factory):
    out = tmp_path_factory.mktemp("flesh-golem") / "public"
    build.build(out_dir=out, site_url="https://owlbear.dicelore.quest", base_path="/")

    class Pages(dict):
        def __missing__(self, path):
            return (out / path / "index.html").read_text(encoding="utf-8")
    return Pages()


@pytest.mark.parametrize("path", [
    "wiki/vasilka",
    "wiki/abbey-of-saint-markovia",
    "wiki/the-abbot",
    "posts/shadows-over-st-markovia",
    "posts/the-abbot-unveiled-wings-lies-and-the-fallen-star",
    "posts/the-fallen-star-ape-sacrifice-and-redemption",
])
def test_pages_that_name_the_golem_link_it(site_pages, path):
    assert GOLEM in site_pages[path], f"{path} names the flesh golem without linking it"


@pytest.mark.parametrize("path, before", [
    ("posts/the-abbot-unveiled-wings-lies-and-the-fallen-star", "Behind them loomed the "),
    ("posts/shadows-over-st-markovia", "The "),
    ("wiki/vasilka", "the Abbot’s "),
    ("wiki/abbey-of-saint-markovia", "his "),
])
def test_the_story_links_the_golem_where_it_is_named(site_pages, path, before):
    """Not just the bold Notable NPCs entry or the picture: the words in the story link."""
    html = site_pages[path].replace("&rsquo;", "’").replace("&#x27;", "’").replace("'", "’")
    assert re.search(rf'{re.escape(before)}<a class="wiki-link" {GOLEM}[^>]*>flesh golem<', html), path


def test_this_flesh_golem_or_a_flesh_golem_is_not_a_phrase():
    import wiki
    pages = [wiki.WikiPage(slug="the-flesh-golem", title="The Flesh Golem", type="creature")]
    phrases = wiki.load_phrases(build.ROOT / "data" / "described-places.yaml", wiki.load_wiki(
        build.ROOT / "content" / "wiki", build.split_front_matter))
    linker = wiki.Linker(pages, {"the-flesh-golem": phrases["the-flesh-golem"]})
    html, _ = linker.link("<p>He builds a flesh golem. Is this flesh golem his golem?</p>")
    assert "href" not in html
    html, _ = linker.link("<p>Then the golem threw a table.</p>")
    assert GOLEM in html


def test_the_golem_alone_links_in_a_scene_that_names_it_no_other_way(site_pages):
    """8/25 names it only as "the golem's thrown candlesticks"."""
    html = site_pages["posts/the-fallen-star-ape-sacrifice-and-redemption"]
    assert re.search(rf'{GOLEM}[^>]*>golem<', html)


def test_the_bride_the_abbot_is_building_is_not_linked_as_the_golem(site_pages):
    """In Welcome to Krezk "a flesh golem out of corpses" is the bride (Vasilka), not the Abbot's servant:
    those mentions are hand-linked to her page, and "the flesh golem" there must not link the servant."""
    html = site_pages["posts/welcome-to-krezk"]
    assert GOLEM not in html
    assert len(re.findall(r'href="/wiki/vasilka/"[^>]*>flesh golem<', html)) == 3


def test_the_golem_and_vasilka_link_each_other(site_pages):
    golem = site_pages["wiki/the-flesh-golem"]
    assert 'href="/wiki/vasilka/"' in golem
    story = re.sub(r"<[^>]+>", "", golem.split("From the adventure log")[0])
    assert "crown of flowers that Vasilka had made for it" in story
