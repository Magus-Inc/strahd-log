"""A place's card lists every session tied to it, not only the one whose number sits there.

Chris (2026-11-01): Old Bonegrinder showed one session, but others went near it, left from it or
passed it. Each row carries the session's map number and how it relates: "here" means its number
sits at this place; the rest set out from here, ended or stopped here, went to a spot near here, or
passed by on the road.
"""
import math
import re

import pytest

import barovia_map
import build
from test_map import MAP, PAGES, real_legs, spot_posts, write

NEAR_MAP = MAP + """spots:
  tser-falls-bridge: {xy: [600, 405], label: Tser Falls bridge}
  krezk-gate: {xy: [150, 240], label: the road below Krezk, near: krezk}
"""


def kinds(related, slug):
    return [(leg["n"], kind) for leg, kind, _ in related.get(slug, [])]


@pytest.fixture
def world(tmp_path):
    path = write(tmp_path / "map.yaml", NEAR_MAP)
    places, parent = barovia_map.load_places(path, PAGES)
    spots = barovia_map.load_spots(path, places)
    visits = barovia_map.load_visits(write(tmp_path / "trail.yaml", """sessions:
  2024-01-01-a: [barovia]
  2024-01-08-b: {stops: [barovia, tser-falls-bridge, vallaki], marker: tser-falls-bridge}
  2024-01-15-c: {stops: [vallaki, krezk-gate], marker: vallaki}
  2024-01-22-d: [krezk]
  2024-01-29-e: [barovia]
"""), places, spots)
    legs = barovia_map.trail(spot_posts(tmp_path, ["2024-01-01-a", "2024-01-08-b", "2024-01-15-c", "2024-01-22-d", "2024-01-29-e"]),
                             places, parent, PAGES, visits, spots)
    return legs, places, spots


def test_spots_can_name_the_place_they_are_near(world):
    _, _, spots = world
    assert spots["krezk-gate"].near == "krezk" and spots["tser-falls-bridge"].near is None


def test_a_spot_must_be_near_a_real_place(tmp_path):
    path = write(tmp_path / "map.yaml", MAP + "spots:\n  x: {xy: [1, 1], near: atlantis}\n")
    places, _ = barovia_map.load_places(path, PAGES)
    with pytest.raises(ValueError, match="atlantis"):
        barovia_map.load_spots(path, places)


def test_each_place_lists_every_related_session_oldest_first(world):
    legs, places, spots = world
    related = barovia_map.place_sessions(legs, places, spots)
    # Barovia: A and E end there with their numbers; B set out from there.
    assert kinds(related, "barovia")[:2] == [(1, "here"), (2, "from")]
    assert (5, "here") in kinds(related, "barovia")
    # Vallaki: B ended there (its number is at the bridge), C's number sits there.
    assert kinds(related, "vallaki")[:2] == [(2, "ended"), (3, "here")]
    # Krezk: C went to the road below it, D's number sits there, E set out from it.
    assert kinds(related, "krezk")[:3] == [(3, "near"), (4, "here"), (5, "from")]
    # A near row names the spot, so the card can say where exactly.
    near = [extra for leg, kind, extra in related["krezk"] if kind == "near"]
    assert near == ["the road below Krezk"]
    # Every row's session appears once per place.
    for rows in related.values():
        ns = [leg["n"] for leg, _, _ in rows]
        assert ns == sorted(set(ns))


def test_passing_a_place_on_the_road_counts():
    # E travels from Krezk back to Barovia: any place its crumbs come within reach of is "past".
    legs = [{"n": 1, "path": ["a"], "marker_at": None, "segments": []},
            {"n": 2, "path": ["b"], "marker_at": None,
             "segments": [{"road": True, "points": [(0, 0), (100, 0)]}]}]
    P = barovia_map.Place
    places = {"a": P("a", "A", 0, 0, []), "b": P("b", "B", 100, 0, []), "mill": P("mill", "Mill", 50, 15, []),
              "far": P("far", "Far", 50, 60, [])}
    related = barovia_map.place_sessions(legs, places, {})
    assert kinds(related, "mill") == [(2, "past")]
    assert kinds(related, "a") == [(1, "here"), (2, "from")]
    assert "far" not in related


def test_old_bonegrinder_lists_the_sessions_that_went_near_it_or_by_it():
    # Chris: "Did we really only have one event at the old bone grinder?" One session happened there
    # (the heist); others met the pie cart at its turnoff, headed down its road, left from it, or
    # passed the turnoff on the Vallaki road.
    legs, places, spots = real_legs()
    related = barovia_map.place_sessions(list(legs.values()), places, spots)
    rows = {leg["post"].slug: kind for leg, kind, _ in related["the-windmill"]}
    assert rows["the-windmill-heist"] == "here"
    assert rows["dream-pies"] == "near" and rows["the-hunt-for-the-heart-stone"] == "near"
    assert rows["entering-the-spirit-realm"] == "from"
    assert rows["the-oath-the-spy-and-the-silver-moon"] == "past"
    assert [k for k in rows.values()].count("here") == 1


def test_map_card_shows_numbers_and_how_each_session_relates(tmp_path):
    root = tmp_path
    write(root / "content" / "posts" / "2024-01-09-first.md", "---\ntitle: First\ndate: '2024-01-09'\n---\n\nIn the Village of Barovia.\n")
    write(root / "content" / "posts" / "2024-01-16-second.md", "---\ntitle: Second\ndate: '2024-01-16'\n---\n\nOn to Vallaki.\n")
    write(root / "content" / "wiki" / "barovia.md", "---\ntitle: Barovia\ntype: place\naliases: [Village of Barovia]\n---\n")
    write(root / "content" / "wiki" / "vallaki.md", "---\ntitle: Vallaki\ntype: place\n---\n")
    write(root / "data" / "map.yaml", "places:\n  barovia: {xy: [780, 450], names: [Village of Barovia]}\n  vallaki: {xy: [400, 270]}\n")
    out = root / "public"
    build.build(root / "content" / "posts", out, site_url="https://x.example", base_path="/")
    html = (out / "map" / "index.html").read_text(encoding="utf-8")
    data = build.json.loads(re.search(r"var data = (\{.*?\});\n", html).group(1))
    rows = data["places"]["barovia"]["sessions"]
    assert [(r["i"], r["k"]) for r in rows] == [(1, "here"), (2, "from")]
    # The card draws the number in the same red disc as the map's markers when the number sits here,
    # and an outlined one with a short reason otherwise.
    assert "place-num" in html and "set out from here" in html and "passed by" in html
    css = build.ROOT.joinpath("static", "style.css").read_text(encoding="utf-8")
    assert re.search(r"\.place-num\.here \{[^}]*background", css)
