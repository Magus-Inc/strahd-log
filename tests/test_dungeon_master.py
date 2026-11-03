"""The Dungeon Master's wiki page (Chris, 2026-11-03).

Chris: the page is titled "Dungeon Master", with Ryan's full name in the article itself, "like we do
for the player characters", and it sits in the player character section, "a section for humans".
No page title carries a real name. The DM is not a party member, so he never gets a cast pill, a
party badge or the "Player character" label.
"""
import json
import re
from pathlib import Path

import pytest

import article
import build
import wiki
import wikistyle

ROOT = build.ROOT
DM = ROOT / "content" / "wiki" / "dungeon-master.md"


def pages():
    return wiki.load_wiki(ROOT / "content" / "wiki", build.split_front_matter)


# --- how the build treats a DM page ------------------------------------------------------------

def test_dm_flag_is_read_from_front_matter(tmp_path):
    (tmp_path / "dm.md").write_text("---\ntitle: Dungeon Master\ntype: character\ndm: true\n"
                                    "player: Pat Example\n---\nRuns the game.\n", encoding="utf-8")
    page = wiki.parse_wiki_page(tmp_path / "dm.md", build.split_front_matter)
    assert page.dm and page.type == "character" and page.player == "Pat Example"


def test_dm_never_gets_a_cast_pill():
    pages_ = [wiki.WikiPage("liren", "Liren", type="character"),
              wiki.WikiPage("dungeon-master", "Dungeon Master", type="character", dm=True)]
    assert [p.title for p in article.cast({"liren", "dungeon-master"}, pages_)] == ["Liren"]


def test_dm_facts_box_says_run_by_not_played_by():
    page = wiki.WikiPage("dungeon-master", "Dungeon Master", type="character", dm=True, player="Pat Example")
    facts = dict(wikistyle.facts(page))
    assert facts["Run by"] == "Pat Example" and "Played by" not in facts


def test_dm_search_label():
    dm = wiki.WikiPage("dungeon-master", "Dungeon Master", type="character", dm=True)
    pc = wiki.WikiPage("liren", "Liren", type="character")
    assert wiki.label(dm) == "Dungeon Master" and wiki.label(pc) == "Player character"


def test_dm_named_in_a_characters_list_is_not_listed_as_cast():
    post = build.Post(title="S", date=None, slug="s", body_md="")
    post.html = "<p>x</p>"
    post.characters_html = "<ul><li>Liren</li><li>Dungeon Master</li></ul>"
    pages_ = [wiki.WikiPage("liren", "Liren", type="character"),
              wiki.WikiPage("dungeon-master", "Dungeon Master", type="character", dm=True)]
    build.link_wiki([post], pages_)
    assert post.listed == ["liren"]


def test_search_index_and_bot_corpus_do_not_call_the_dm_a_player_character():
    dm = wiki.WikiPage("dungeon-master", "Dungeon Master", type="character", dm=True, player="Pat Example")
    entry = json.loads(build.build_search_index([], [dm]))[0]
    assert entry["l"] == "Dungeon Master"
    corpus = json.loads(build.build_bot_corpus([], [dm], "/"))
    assert corpus["wiki"][0]["type"] == "dm"


def test_wiki_page_without_facts_box_says_run_by():
    text = (ROOT / "templates" / "wiki_page.html").read_text(encoding="utf-8")
    assert "Run by" in text


def test_party_file_refuses_the_dm():
    post = build.Post(title="S", date=None, slug="s", body_md="")
    dm = wiki.WikiPage("dungeon-master", "Dungeon Master", type="character", dm=True)
    with pytest.raises(ValueError, match="not a player character"):
        build.apply_party_entry(post, {"joined": ["dungeon-master"]}, {"dungeon-master": dm})


# --- the real page -----------------------------------------------------------------------------

def test_the_page_is_titled_dungeon_master_with_ryans_full_name_inside():
    page = next(p for p in pages() if p.slug == "dungeon-master")
    assert page.title == "Dungeon Master" and page.type == "character" and page.dm
    assert page.player == "Ryan Mathews"
    assert "Ryan Mathews" in page.body_md
    assert not page.aliases  # "the DM" in table notes must not link here and pull him into a post's cast


def test_no_page_title_carries_a_real_name():
    real = {part for p in pages() if p.player for part in p.player.split() if len(part) > 3}
    for p in pages():
        assert not any(re.search(rf"(?<!\w){re.escape(n)}(?!\w)", t) for n in real for t in p.names), p.slug


def test_page_uses_none_of_ryans_own_pictures():
    # Chris (2026-11-02): pictures Ryan shared on Discord are inspiration only, never posted.
    assert not wiki.PICTURE.findall(DM.read_text(encoding="utf-8"))


def test_every_post_and_page_the_dm_page_links_exists():
    text = DM.read_text(encoding="utf-8")
    links = re.findall(r"\]\((/(?:posts|wiki)/[^)]+/)\)", text)
    assert links
    posts = {f"/posts/{build.parse_post(p).slug}/" for p in (ROOT / "content" / "posts").glob("*.md")}
    wikis = {f"/wiki/{p.slug}/" for p in pages()}
    assert not [link for link in links if link not in posts | wikis]


def test_built_site_lists_the_dm_with_the_player_characters_and_in_no_cast(real_build):
    index = (real_build.out / "wiki" / "index.html").read_text(encoding="utf-8")
    pcs = index.index('id="player-characters"')
    nxt = index.index("<section", pcs)
    assert "/wiki/dungeon-master/" in index[pcs:nxt]
    page = (real_build.out / "wiki" / "dungeon-master" / "index.html").read_text(encoding="utf-8")
    assert "Ryan Mathews" in page and "Run by" in page and "Played by" not in page
    # The page is about the real table, so it is not "Malron's Account" (he doesn't know there is a table).
    assert "Malron’s Account" not in page and "Malron's Account" not in page
    for post in (real_build.out / "posts").glob("*/index.html"):
        html = post.read_text(encoding="utf-8")
        assert 'class="pill" href="/wiki/dungeon-master/"' not in html, post.parent.name
