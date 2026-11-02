"""Skull badge for sessions where a player character died (even if brought back) and a party badge for
sessions where a new character joined, came back or left. Both come from data/party.yaml."""
import json
import re
from pathlib import Path

import pytest
import yaml

import build

ROOT = build.ROOT


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def card_for(html: str, title: str) -> str:
    return next(c for c in re.findall(r'<li class="card[^"]*".*?</li>', html, re.S) if f">{title}<" in c)


@pytest.fixture
def party_site(tmp_path):
    posts = tmp_path / "content" / "posts"
    write(posts / "2026-01-01-gallows.md", "---\ntitle: Gallows\ndate: '2026-01-01'\ntags: [Vallaki]\n---\n\nOlfin Darning fell.\n")
    write(posts / "2026-02-01-quiet.md", "---\ntitle: Quiet Night\ndate: '2026-02-01'\ntags: [Vallaki]\n---\n\nOlfin Darning slept.\n")
    write(posts / "2026-03-01-bat.md", "---\ntitle: The Bat\ndate: '2026-03-01'\n---\n\nOlfin Darning and Veyren fought.\n")
    wiki_dir = tmp_path / "content" / "wiki"
    write(wiki_dir / "olfin-darning.md", "---\ntitle: Olfin Darning\ntype: character\n---\n\nPaladin.\n")
    write(wiki_dir / "veyren.md", "---\ntitle: Veyren\ntype: character\n---\n\nDruid.\n")
    write(wiki_dir / "shabasta.md", "---\ntitle: Shabasta\ntype: character\n---\n\nBard.\n")
    party = tmp_path / "data" / "party.yaml"
    write(party, "gallows:\n  died: [shabasta]\n"
                 "bat:\n  died: [olfin-darning]\n  brought_back: [olfin-darning]\n  joined: [veyren]\n")
    out = tmp_path / "public"
    build.build(posts, out, site_url="https://x.example", wiki_dir=wiki_dir, party_file=party)
    return out


def test_home_cards_carry_a_skull_for_a_death_and_nothing_for_a_quiet_session(party_site):
    home = read(party_site / "index.html")
    gallows = card_for(home, "Gallows")
    assert 'class="death-tag"' in gallows and "<svg" in gallows and "Shabasta" in gallows
    assert 'aria-label="Shabasta died"' in gallows
    quiet = card_for(home, "Quiet Night")
    assert "death-tag" not in quiet and "party-tag" not in quiet


def test_a_character_brought_back_still_gets_the_skull_and_says_so(party_site):
    hero = read(party_site / "index.html").split('<section class="chronicle"')[0]
    assert "death-tag" in hero and 'aria-label="Olfin died and was brought back"' in hero
    assert ">Olfin<" in hero  # first name only on the badge


def test_new_character_gets_the_party_badge(party_site):
    bat = read(party_site / "index.html").split('<section class="chronicle"')[0]  # the newest: the hero
    assert 'class="party-tag"' in bat and "Veyren joins" in bat


def test_post_page_says_who_died_and_who_joined_with_wiki_links(party_site):
    page = read(party_site / "posts" / "bat" / "index.html")
    head = page.split('class="post-head"')[1].split("</header>")[0]
    assert 'class="party-notes"' in head
    assert '<a href="/wiki/olfin-darning/">Olfin Darning</a> died and was brought back' in head
    assert '<a href="/wiki/veyren/">Veyren</a> joins the party' in head
    assert "party-notes" not in read(party_site / "posts" / "quiet" / "index.html")


def test_tags_page_and_appears_in_list_carry_the_badges(party_site):
    tags = read(party_site / "tags" / "index.html")
    row = next(li for li in tags.split("<li>") if "Gallows" in li)
    assert "death-tag" in row
    appears = read(party_site / "wiki" / "olfin-darning" / "index.html").split('class="appears-in"')[1]
    assert "death-tag" in appears and "party-tag" in appears


def test_search_index_carries_deaths_and_party_changes(party_site):
    entries = {e["t"]: e for e in json.loads(read(party_site / "search-index.json"))}
    assert entries["Gallows"]["d"] == {"n": "Shabasta", "a": "Shabasta died"}
    assert entries["The Bat"]["c"] == "Veyren joins"
    assert "d" not in entries["Quiet Night"] and "c" not in entries["Quiet Night"]


def test_numbered_session_lists_keep_badges_in_the_text_column():
    """On a phone the badges wrapped under the session number and overlapped each other."""
    css = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
    assert re.search(r"\.session-list\.numbered \.row-tags \{[^}]*grid-column: 2", css)
    badges = (ROOT / "templates" / "_badges.html").read_text(encoding="utf-8")
    assert 'class="row-tags"' in badges


def test_search_and_map_pages_draw_both_badges():
    for name in ("search.html", "map.html"):
        text = (ROOT / "templates" / name).read_text(encoding="utf-8")
        assert "death-tag" in text and "party-tag" in text


def test_badges_are_styled():
    css = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
    for selector in (".death-tag", ".party-tag", ".party-notes"):
        assert selector in css


def test_labels_for_every_kind_of_change(tmp_path):
    post = build.Post(title="T", date=build.to_datetime("2026-01-01"), slug="t", body_md="")
    pages = {s: build.wiki.WikiPage(slug=s, title=t, type="character")
             for s, t in (("crusty", "Crusty"), ("shabasta", "Shabasta"), ("gumbo", "Gumbo"), ("liren", "Liren"))}
    build.apply_party_entry(post, {"joined": ["crusty"], "returned": ["shabasta"]}, pages)
    assert post.party_label == "Crusty joins, Shabasta returns"
    post2 = build.Post(title="U", date=post.date, slug="u", body_md="")
    build.apply_party_entry(post2, {"returned": ["gumbo", "liren"], "left": ["gumbo", "liren"]}, pages)
    assert post2.party_label == "Gumbo and Liren return, then leave"
    post3 = build.Post(title="V", date=post.date, slug="v", body_md="")
    build.apply_party_entry(post3, {"left": ["gumbo"]}, pages)
    assert post3.party_label == "Gumbo leaves"


@pytest.mark.parametrize("entry, message", [
    ({"died": ["nobody"]}, "nobody"),
    ({"died": ["mira"]}, "not a player character"),
    ({"brought_back": ["crusty"]}, "brought back without dying"),
    ({"exploded": ["crusty"]}, "exploded"),
])
def test_bad_entries_fail_the_build(entry, message):
    post = build.Post(title="T", date=build.to_datetime("2026-01-01"), slug="t", body_md="")
    pages = {"crusty": build.wiki.WikiPage(slug="crusty", title="Crusty", type="character"),
             "mira": build.wiki.WikiPage(slug="mira", title="Mira", type="npc")}
    with pytest.raises(ValueError, match=message):
        build.apply_party_entry(post, entry, pages)


def test_unknown_post_in_party_file_fails(tmp_path):
    posts = tmp_path / "content" / "posts"
    write(posts / "2026-01-01-a.md", "---\ntitle: A\ndate: '2026-01-01'\n---\n\nText.\n")
    party = tmp_path / "party.yaml"
    write(party, "no-such-post:\n  died: [aera]\n")
    with pytest.raises(ValueError, match="no-such-post"):
        build.build(posts, tmp_path / "out", site_url="https://x.example", party_file=party)


def test_real_party_file_names_real_posts_and_player_characters():
    data = yaml.safe_load((ROOT / "data" / "party.yaml").read_text(encoding="utf-8"))
    slugs = {build.parse_post(p).slug for p in (ROOT / "content" / "posts").glob("*.md")}
    pages = {p.stem for p in (ROOT / "content" / "wiki").glob("*.md")}
    assert set(data) <= slugs
    for entry in data.values():
        for names in entry.values():
            assert set(names) <= pages
