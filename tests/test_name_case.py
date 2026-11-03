"""Names written in small letters link too (Chris, 2026-11-03: the flesh golem, the windmill, dream pastries
went unlinked because the posts write them in lower case). A name of two or more words links in any
case of its first letters; a "The ..." title links after "the" ("the windmill"). A one-word name
("Rose", "Thorn", "Manor") is an ordinary word in small letters, so it links only as written, and so do
the names in data/name-case.yaml `exact:` (a "signet ring" is not always Kasimir's)."""
import re

import pytest
import yaml

import build
import wiki


def page(slug, title, *aliases, type="item"):
    return wiki.WikiPage(slug=slug, title=title, type=type, aliases=list(aliases), summary=title)


def linked(linker, text):
    html, _ = linker.link(f"<p>{text}</p>")
    return re.findall(r'href="/wiki/([^/]+)/"[^>]*>([^<]+)<', html)


def test_a_name_of_two_words_links_in_small_letters():
    linker = wiki.Linker([page("dream-pastries", "Dream Pastries")])
    assert linked(linker, "We ate the dream pastries.") == [("dream-pastries", "dream pastries")]
    assert linked(linker, "Dream pastries again.") == [("dream-pastries", "Dream pastries")]


def test_a_the_title_links_after_the():
    linker = wiki.Linker([page("the-windmill", "The Windmill", type="place")])
    assert linked(linker, "We climbed the windmill.") == [("the-windmill", "the windmill")]
    assert linked(linker, "A windmill turned.") == []


def test_a_one_word_name_links_only_as_written():
    linker = wiki.Linker([page("rose-durst", "Rose Durst", "Rose", type="npc")])
    assert linked(linker, "A rose on the grave.") == []
    assert linked(linker, "Rose waved.") == [("rose-durst", "Rose")]


def test_exact_names_link_only_as_written():
    linker = wiki.Linker([page("signet-ring", "Kasimir's Ring", "Signet ring")], exact={"Signet ring"})
    assert linked(linker, "a signet ring") == []
    assert linked(linker, "the Signet ring") == [("signet-ring", "Signet ring")]


def test_two_pages_with_the_same_name_in_small_letters_link_only_as_written():
    linker = wiki.Linker([page("a", "Red Door"), page("b", "Red door")])
    assert linked(linker, "a red door") == []


def test_exact_names_are_real_names():
    pages = wiki.load_wiki(build.ROOT / "content" / "wiki", build.split_front_matter)
    names = {n for p in pages for n in p.names}
    data = yaml.safe_load((build.ROOT / "data" / "name-case.yaml").read_text(encoding="utf-8"))
    for name in data["exact"]:
        assert name in names, f"name-case.yaml: {name!r} is no wiki page's name"


@pytest.fixture(scope="module")
def site_pages(tmp_path_factory):
    out = tmp_path_factory.mktemp("name-case") / "public"
    build.build(out_dir=out, site_url="https://owlbear.dicelore.quest", base_path="/")
    return lambda path: (out / path / "index.html").read_text(encoding="utf-8")


@pytest.mark.parametrize("path, slug, words", [
    ("posts/the-windmill-heist", "the-windmill", "the windmill"),
    ("posts/entering-the-spirit-realm", "gallows-speaker", "gallows speaker"),
    ("posts/the-fallen-star-ape-sacrifice-and-redemption", "the-void", "the void"),
    ("posts/helping-victor", "dream-pastries", "dream pastries"),
])
def test_names_in_small_letters_link_on_the_site(site_pages, path, slug, words):
    html = site_pages(path)
    assert re.search(rf'href="/wiki/{slug}/"[^>]*>{words}<', html), (path, words)


def test_an_exact_name_keeps_a_page_that_differs_only_in_case_exact_too():
    linker = wiki.Linker([page("a", "Red Door"), page("b", "Red door")], exact={"Red Door"})
    assert linked(linker, "a red door") == []
