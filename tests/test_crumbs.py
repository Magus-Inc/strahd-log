"""Breadcrumbs ride on the road, in lanes, so backtracking shows without leaving the road.

Chris (2026-11-02): on the road to the Wizard of Wines the crumbs sat beside the road, on its black
edge, and looked dashed in some places and solid in others. A road's surface is ROAD_WIDTH wide; a
crumb's centre must stay well inside it, the first trip over a stretch runs down the middle, and a
trip back over the same stretch takes another lane instead of landing on (or near) an earlier one.
"""

import math
from pathlib import Path

import barovia_map
import build
import wiki
from barovia_map import Place

ROOT = Path(__file__).resolve().parent.parent
LANE_ROOM = barovia_map.ROAD_WIDTH / 2 - 0.5  # the most a crumb's centre may sit off the road's middle


def place(slug, xy):
    return Place(slug=slug, title=slug, x=xy[0], y=xy[1], names=[slug])


def road_legs(*trips):
    """Legs walking the vineyard road's stops in order: vineyard junction <-> Raven River side."""
    ends = {"a": place("a", (195, 256)), "b": place("b", (150, 340)), "c": place("c", (110, 360))}
    legs = [{"stops": list(stops)} for stops in trips]
    barovia_map.add_route(legs, ends)
    return legs


def shift_of(drawn, points):
    """How far each drawn vertex sits from the road's own polyline."""
    return [min(barovia_map._distance_to_segment(p, a, b) for a, b in zip(points, points[1:])) for p in drawn]


def real_legs():
    posts = build.load_posts(ROOT / "content" / "posts")
    build.number_sessions(posts)
    pages = wiki.load_wiki(ROOT / "content" / "wiki", build.split_front_matter)
    places, parent = barovia_map.load_places(ROOT / "data" / "map.yaml", pages)
    spots = barovia_map.load_spots(ROOT / "data" / "map.yaml", places)
    visits = barovia_map.load_visits(ROOT / "data" / "trail.yaml", places, spots)
    return barovia_map.trail(posts, places, parent, pages, visits, spots)


def test_the_first_trip_down_a_road_runs_down_its_middle():
    (leg,) = road_legs(["a", "b"])
    (seg,) = leg["segments"]
    assert max(shift_of(seg["drawn"], seg["points"])) < 0.05


def test_a_trip_back_takes_another_lane_still_on_the_road():
    there, back = road_legs(["a", "b"], ["b", "a"])
    out, home = there["segments"][0], back["segments"][0]
    assert all(0.6 < s <= LANE_ROOM for s in shift_of(home["drawn"], home["points"]))
    # A third trip takes the lane on the other side, clear of both.
    third = road_legs(["a", "b"], ["b", "a"], ["a", "b"])[2]["segments"][0]
    for p in third["drawn"][1:-1]:
        assert min(math.dist(p, q) for q in home["drawn"]) > 1.2


def test_turning_back_at_a_junction_makes_no_loop():
    """Out to the Wizard of Wines and straight back up the road: where the trail turns back at the
    vineyard junction it must not swing wide (the loop Chris saw by the vineyard)."""
    leg = road_legs(["a", "c", "a"])[0]
    for seg in leg["segments"]:
        assert max(shift_of(seg["drawn"], seg["points"])) <= LANE_ROOM


def test_every_crumb_on_the_real_trail_stays_on_its_road():
    for leg in real_legs():
        for seg in leg["segments"]:
            if seg["road"]:
                assert max(shift_of(seg["drawn"], seg["points"])) <= LANE_ROOM, leg["post"].slug
                assert seg["d"] == barovia_map.smooth_path(seg["drawn"])
