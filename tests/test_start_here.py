"""The Start here page for new readers (Chris's picks on the start here pick page, 2026-11-04).

Picked: its own page, linked from the menu with one line on the home page; the "choose your way in"
layout (a castle picture, a two-line hook, four big buttons, the sections below); the premise and story
in Malron's voice, the tips in the site's plain voice; six chapters by place, each a short paragraph
with tags for the big moments; today's party big, everyone who came and went small; and the extras
Faces to know, Madam Eva's fortune, How to read this blog, a map teaser and About this record.
Upkeep: every session must sit in a chapter, so a new post can't be forgotten (this file checks it).
"""
import re
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

import build
import start
from test_plain_wording import stiff

ROOT = build.ROOT
DATA = ROOT / "data" / "start-here.yaml"


def post(slug, day, listed=(), party=None):
    return SimpleNamespace(slug=slug, title=slug.title(), date=datetime(2024, 1, day), path=f"posts/{slug}/",
                           listed=list(listed), party=party or {}, number=day, tagline="")


def page(slug, kind="character", player="", dm=False, picture=""):
    return SimpleNamespace(slug=slug, title=slug.title(), type=kind, player=player, dm=dm, summary="",
                           pictures=[f"/images/{picture}"] if picture else [], thumb="", names=[slug.title()])


@pytest.fixture
def world(tmp_path):
    static = tmp_path / "static"
    (static / "images").mkdir(parents=True)
    for name in ("a.jpg", "b.jpg", "castle.jpg"):
        (static / "images" / name).write_bytes(b"x")
    olfin, veyren = page("olfin", player="P1", picture="a.jpg"), page("veyren", player="P2", picture="b.jpg")
    posts = [post("four", 4, ["olfin"]), post("three", 3, ["olfin"], {"died": [veyren]}),
             post("two", 2, ["olfin", "veyren"], {"joined": [veyren]}), post("one", 1, ["olfin"])]
    pages = [olfin, veyren, page("tome", "item"), page("ireena", "npc")]
    data = {"hero": "castle.jpg", "hook": "Hook.", "premise": "Premise.",
            "chapters": [{"title": "First", "from": "one", "through": "two", "picture": "a.jpg", "text": "Text one."},
                         {"title": "Second", "from": "three", "through": "four", "picture": "b.jpg", "text": "Text two.",
                          "won": ["tome"]}],
            "faces": ["ireena"],
            "fortune": [{"card": "Traitor", "told": "Of history.", "points_to": "tome", "found_in": "three"},
                        {"card": "Bishop", "told": "A sword.", "points_to": "tome"}],
            "how_to_read": ["Gold names open the wiki."], "about": "About."}
    return SimpleNamespace(posts=posts, pages=pages, data=data, static=static)


def load(world):
    return start.plan(world.data, world.posts, world.pages, world.static)


# --- the plan, from data/start-here.yaml ---------------------------------------------------------

def test_chapters_take_their_sessions_oldest_first(world):
    plan = load(world)
    assert [[p.slug for p in c.posts] for c in plan.chapters] == [["one", "two"], ["three", "four"]]
    assert plan.uncovered == []


def test_a_new_post_after_the_last_chapter_is_listed_as_uncovered(world):
    world.posts.insert(0, post("five", 5, ["olfin"]))
    assert [p.slug for p in load(world).uncovered] == ["five"]


@pytest.mark.parametrize("change, message", [
    (lambda d: d["chapters"][1].update({"from": "four"}), "starts at four, but three comes right after"),
    (lambda d: d["chapters"][0].update({"from": "two"}), "must start at the first session, one"),
    (lambda d: d["chapters"][0].update({"through": "nowhere"}), "unknown post nowhere"),
    (lambda d: d["chapters"][0].update({"picture": "missing.jpg"}), "no picture static/images/missing.jpg"),
    (lambda d: d.update({"faces": ["nobody"]}), "no wiki page nobody"),
    (lambda d: d["fortune"][0].update({"points_to": "nobody"}), "no wiki page nobody"),
    (lambda d: d["chapters"][1].update({"won": ["nobody"]}), "no wiki page nobody"),
])
def test_mistakes_in_the_data_stop_the_build(world, change, message):
    change(world.data)
    with pytest.raises(ValueError, match=message):
        load(world)


def test_the_big_moments_come_from_the_party_data_and_the_won_list(world):
    first, second = load(world).chapters
    assert [(m.kind, m.label) for m in first.moments] == [("party", "Veyren joins")]
    assert [(m.kind, m.label) for m in second.moments] == [("died", "Veyren died"), ("won", "Tome")]


def test_leaving_is_a_moment_too(world):
    world.posts[0].party = {"left": [world.pages[1]]}
    assert ("left", "Veyren leaves") in [(m.kind, m.label) for m in load(world).chapters[1].moments]


def test_todays_party_is_the_newest_sessions_cast_and_the_rest_came_and_went(world):
    plan = load(world)
    assert [p.slug for p in plan.party] == ["olfin"]
    assert [(m.page.slug, m.status) for m in plan.past] == [("veyren", "died")]


def test_a_character_brought_back_is_in_the_party_again(world):
    veyren = world.pages[1]
    world.posts[0].party = {"revived": [veyren]}
    plan = load(world)
    assert [p.slug for p in plan.party] == ["olfin", "veyren"] and plan.past == []


def test_one_nights_changes_count_in_story_order_not_file_order(world):
    """Gumbo and Liren returned and left in one session: they have left, whatever order the keys are in."""
    veyren = world.pages[1]
    world.posts[0].party = {"left": [veyren], "returned": [veyren]}
    assert [(m.page.slug, m.status) for m in load(world).past] == [("veyren", "left")]


def test_a_player_who_misses_the_latest_session_is_still_in_the_party(world):
    world.posts[0].listed = []
    assert [p.slug for p in load(world).party] == ["olfin"]


def test_a_chapter_missing_a_key_says_which(world):
    del world.data["chapters"][0]["picture"]
    with pytest.raises(ValueError, match="First.*has no picture"):
        load(world)


def test_the_fortune_says_found_with_the_session_or_still_looking(world):
    cards = load(world).fortune
    assert [(c.card, c.page.slug, c.found_in.slug if c.found_in else None) for c in cards] == [
        ("Traitor", "tome", "three"), ("Bishop", "tome", None)]


# --- the real blog -------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def real_plan():
    site = build.prepare()
    return site.start, site


def test_every_session_sits_in_a_chapter(real_plan):
    """Upkeep (Chris's pick): a new post must be added to a chapter in the same pull request."""
    plan, _ = real_plan
    assert plan.uncovered == [], ("add these sessions to the last chapter (or a new one) in data/start-here.yaml "
                                  "and update its text: " + ", ".join(p.slug for p in plan.uncovered))


def test_six_chapters_by_place(real_plan):
    plan, _ = real_plan
    assert [c.title for c in plan.chapters] == ["The House in the Fog", "The Village Under the Castle", "Vallaki",
                                                "The Broken Land", "Castle Ravenloft", "The Abbey and the Beacon"]


def test_each_chapter_is_a_short_paragraph(real_plan):
    plan, _ = real_plan
    for chapter in plan.chapters:
        words = len(re.sub(r"<[^>]+>", " ", chapter.html).split())
        assert 35 <= words <= 90, f"{chapter.title}: {words} words"


def test_the_text_we_wrote_uses_plain_words():
    data = yaml.safe_load(DATA.read_text(encoding="utf-8"))
    texts = [data["hook"], data["premise"], data["about"], *data["how_to_read"],
             *[c["text"] for c in data["chapters"]], *[f["told"] for f in data["fortune"]]]
    assert [hit for text in texts for hit in stiff(text)] == []


def test_the_fortune_is_madam_evas_five_cards(real_plan):
    plan, _ = real_plan
    tser_pool = (ROOT / "content" / "posts" / "2024-04-16-tser-pool.md").read_text(encoding="utf-8")
    for card in plan.fortune:
        assert f"**{card.card}" in tser_pool
    assert len(plan.fortune) == 5


def test_todays_party_matches_the_latest_session_with_malron_first(real_plan):
    plan, site = real_plan
    assert {p.slug for p in plan.party} == set(site.posts[0].listed)
    assert plan.party[0].slug == "malron-lichtstrahl"


def test_everyone_who_played_is_shown_once(real_plan):
    plan, site = real_plan
    players = {w.slug for w in site.pages if w.type == "character" and not w.dm}
    assert {"grom-shield-breaker", "weeble-wobleston", "veyren"} <= players
    shown = [p.slug for p in plan.party] + [m.page.slug for m in plan.past]
    assert sorted(shown) == sorted(players)


@pytest.fixture(scope="module")
def start_html(real_build):
    return (real_build.out / "start" / "index.html").read_text(encoding="utf-8")


def test_the_page_opens_with_a_hook_and_four_ways_in(start_html):
    assert "<h1" in start_html and "Welcome to Barovia" in start_html
    doors = re.findall(r'<a class="door" href="([^"]+)"', start_html)
    assert doors == ["#story", "#party", "/posts/session-zero/", "/map/"]


@pytest.mark.parametrize("section", ["story", "party", "faces", "fortune", "map", "how-to-read", "about"])
def test_every_picked_section_is_on_the_page(start_html, section):
    assert f'id="{section}"' in start_html


def test_no_player_names_on_the_page(start_html):
    """Real player names appear only on each PC's own wiki page."""
    pages = build.prepare().pages
    for page in pages:
        for person in [page.player] + [p.get("name", "") for p in page.people]:
            for part in (person or "").replace("’", "'").split():
                if len(part) > 3 and part[0].isupper() and part not in ("Malron",):
                    assert not re.search(rf"\b{re.escape(part)}\b", start_html.replace("’", "'")), (page.slug, part)


def test_every_link_and_picture_on_the_page_exists(real_build, start_html):
    for target in re.findall(r'(?:href|src)="/([^"#?]*)"', start_html):
        if target.startswith(("feed.xml", "style.css")) or not target:
            continue
        path = real_build.out / target
        assert path.is_file() or (path / "index.html").is_file(), target


def test_the_menu_links_to_start_here_on_every_page(real_build):
    for page in ("index.html", "wiki/index.html", "posts/session-zero/index.html", "start/index.html"):
        html = (real_build.out / page).read_text(encoding="utf-8")
        assert re.search(r'<nav class="site-nav".*?<a href="/start/"[^>]*>Start here</a>', html, re.S), page
    start_page = (real_build.out / "start" / "index.html").read_text(encoding="utf-8")
    assert '<a href="/start/" aria-current="page">Start here</a>' in start_page


def test_the_home_page_has_one_line_for_new_readers(real_build):
    html = (real_build.out / "index.html").read_text(encoding="utf-8")
    assert re.search(r'<p class="new-here">New here\? <a href="/start/">', html)


def test_chapter_names_link_to_the_wiki(start_html):
    story = start_html.split('id="story"')[1].split('id="party"')[0]
    assert 'href="/wiki/ireena-kolyana/"' in story
    assert 'href="/wiki/vallaki/"' in story
