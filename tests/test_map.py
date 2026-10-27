import re
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

import barovia_map
import build
import wiki


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def page(slug, title, aliases=(), kind="place"):
    return wiki.WikiPage(slug=slug, title=title, type=kind, aliases=list(aliases))


PAGES = [page("barovia", "Barovia", ["Village of Barovia"]), page("vallaki", "Vallaki", ["Vellaki"]),
         page("blue-water-inn", "Blue Water Inn"), page("krezk", "Krezk"), page("strahd", "Strahd", kind="npc")]
MAP = """places:
  barovia: {xy: [780, 450], label: Village of Barovia, names: [Village of Barovia]}
  vallaki: {xy: [400, 270]}
  krezk: {xy: [120, 232], anchor: end}
within:
  blue-water-inn: vallaki
"""


@pytest.fixture
def places(tmp_path):
    return barovia_map.load_places(write(tmp_path / "map.yaml", MAP), PAGES)


def test_base_map_is_deterministic_svg():
    svg = barovia_map.draw_base()
    assert svg == barovia_map.draw_base()
    root = ET.fromstring(svg)
    assert root.tag.endswith("svg") and root.get("viewBox") == "0 0 1000 750"
    assert "Lake Zarovich" in svg and "<script" not in svg


def test_load_places_labels_names_and_parents(places):
    by_slug, parent = places
    assert by_slug["barovia"].title == "Village of Barovia" and by_slug["barovia"].names == ["Village of Barovia"]
    assert by_slug["vallaki"].names == ["Vallaki", "Vellaki"]
    assert by_slug["krezk"].label_xy == (110.0, 236.0)
    assert parent["blue-water-inn"] == "vallaki" and "strahd" not in parent


def test_load_places_rejects_unknown_pages(tmp_path):
    with pytest.raises(ValueError, match="nowhere"):
        barovia_map.load_places(write(tmp_path / "m.yaml", "places:\n  nowhere: {xy: [1, 2]}\n"), PAGES)


def test_stops_follow_first_mention_and_map_rooms_to_places(places):
    by_slug, parent = places
    text = "We left Krezk, slept at the Blue Water Inn, then Vallaki again. Barovia is grim."
    # "Barovia" alone is the land, not the village, so it is not a stop.
    assert barovia_map.stops(text, by_slug, parent, PAGES) == ["krezk", "vallaki"]
    assert barovia_map.stops("Back to the Village of Barovia.", by_slug, parent, PAGES) == ["barovia"]


def test_visits_override_mentions_and_draw_strokes(tmp_path, places):
    by_slug, parent = places
    posts = []
    for stem, title, body in [("2024-01-01-a", "A", "Talk of Vallaki."), ("2024-01-08-b", "B", "Krezk!"),
                              ("2024-01-15-c", "C", "Nowhere much.")]:
        post = build.parse_post(write(tmp_path / "posts" / f"{stem}.md", f"---\ntitle: {title}\ndate: '{stem[:10]}'\n---\n\n{body}\n"))
        post.html = build.render_markdown(post.body_md)
        posts.append(post)
    visits = barovia_map.load_visits(write(tmp_path / "trail.yaml", "sessions:\n  2024-01-01-a: [barovia]\n  2024-01-15-c: [vallaki, krezk]\n"), by_slug)
    legs = barovia_map.trail(posts, by_slug, parent, PAGES, visits)
    # A talks about Vallaki but was in the village; B has no entry, so its mentions count.
    assert [(leg["post"].title, leg["stops"]) for leg in legs] == [("A", ["barovia"]), ("B", ["krezk"]), ("C", ["vallaki", "krezk"])]
    assert [len(leg["segments"]) for leg in legs] == [0, 1, 2]
    assert [leg["n"] for leg in legs] == [1, 2, 3]
    # Every hop follows the roads: each step of its path is a road (or track) edge.
    graph = barovia_map.road_graph()
    for leg in legs:
        for seg in leg["segments"]:
            assert seg["road"]
            assert all(b in graph[a] for a, b in zip(seg["points"], seg["points"][1:]))
    # Barovia to Krezk is a long way round by road, not a straight line.
    assert len(legs[1]["segments"][0]["points"]) > 10
    # Sessions ending at the same place get markers fanned around it, not on top of each other.
    assert legs[1]["marker"] != legs[2]["marker"]
    assert [p.title for p in by_slug["krezk"].sessions] == ["C", "B"]


def test_load_visits_rejects_unknown_places(tmp_path, places):
    with pytest.raises(ValueError, match="atlantis"):
        barovia_map.load_visits(write(tmp_path / "trail.yaml", "sessions:\n  x: [atlantis]\n"), places[0])


def test_build_writes_map_page_and_post_maps(tmp_path):
    root = tmp_path
    write(root / "content" / "posts" / "2024-01-09-first.md", "---\ntitle: First\ndate: '2024-01-09'\n---\n\nIn the Village of Barovia.\n")
    write(root / "content" / "posts" / "2024-01-16-second.md", "---\ntitle: Second\ndate: '2024-01-16'\n---\n\nOn to Vallaki.\n")
    write(root / "content" / "wiki" / "barovia.md", "---\ntitle: Barovia\ntype: place\naliases: [Village of Barovia]\n---\n")
    write(root / "content" / "wiki" / "vallaki.md", "---\ntitle: Vallaki\ntype: place\n---\n")
    write(root / "content" / "wiki" / "blue-water-inn.md", "---\ntitle: Blue Water Inn\ntype: place\n---\n")
    write(root / "data" / "map.yaml", "places:\n  barovia: {xy: [780, 450], names: [Village of Barovia]}\n  vallaki: {xy: [400, 270]}\n"
                                      "within:\n  blue-water-inn: vallaki\n")
    out = root / "public"
    build.build(root / "content" / "posts", out, site_url="https://x.example", base_path="/strahd-log/")

    assert (out / "map" / "barovia.svg").is_file()
    page_html = (out / "map" / "index.html").read_text(encoding="utf-8")
    assert 'href="/strahd-log/map/barovia.svg"' in page_html and 'class="crumb' in page_html
    assert 'data-zoom="in"' in page_html and 'href="/strahd-log/posts/second/"' in page_html
    assert 'href="/strahd-log/wiki/vallaki/"' in page_html and 'id="show-trail"' in page_html
    second = (out / "posts" / "second" / "index.html").read_text(encoding="utf-8")
    assert "Where we were" in second and 'class="crumb current"' in second and 'class="marker current"' in second
    inn = (out / "wiki" / "blue-water-inn" / "index.html").read_text(encoding="utf-8")
    assert "On the map" in inn and 'data-place="vallaki"' in inn
    assert 'href="/strahd-log/map/"' in (out / "index.html").read_text(encoding="utf-8")


def test_no_map_file_means_no_map(tmp_path):
    write(tmp_path / "content" / "posts" / "2024-01-09-a.md", "---\ntitle: A\ndate: '2024-01-09'\n---\n\nHi.\n")
    out = tmp_path / "public"
    build.build(tmp_path / "content" / "posts", out, site_url="https://x.example")
    assert not (out / "map").exists() and "/map/" not in (out / "index.html").read_text(encoding="utf-8")


def test_route_follows_roads_between_junctions():
    graph = barovia_map.road_graph()
    vallaki, castle = (400, 270), (720, 398)
    path = barovia_map.route(graph, vallaki, castle)
    assert path[0] == vallaki and path[-1] == castle
    assert (488, 308) in path and (610, 360) in path  # round the hairpin by Old Bonegrinder, then the fork
    assert all(b in graph[a] for a, b in zip(path, path[1:]))
    assert barovia_map.route(graph, vallaki, vallaki) == [vallaki]


def test_every_mapped_place_sits_on_a_road():
    import yaml
    spec = yaml.safe_load(Path("data/map.yaml").read_text(encoding="utf-8"))
    graph = barovia_map.road_graph()
    for slug, place in spec["places"].items():
        if place.get("offroad"):
            assert barovia_map.nearest_vertex(graph, *place["xy"]) is None, slug  # really off the roads
        else:
            assert tuple(place["xy"]) in graph, slug


def test_trail_passes_the_east_gate_only_once():
    # The party came through the east gate of Barovia once, from Durst Manor into the village.
    import yaml
    sessions = yaml.safe_load(Path("data/trail.yaml").read_text(encoding="utf-8"))["sessions"]
    assert [stem for stem, stops in sessions.items() if "gates-of-barovia" in (stops or [])] == ["2024-02-13-barovia-barovia"]


def test_answered_sessions_use_the_new_places():
    import yaml
    sessions = yaml.safe_load(Path("data/trail.yaml").read_text(encoding="utf-8"))["sessions"]
    assert sessions["2024-07-16-dream-pies"] == ["tser-pool", "tser-crossroads", "the-windmill"]
    assert sessions["2025-01-14-the-hunt-for-the-heart-stone"] == ["vallaki", "tser-crossroads"]
    assert sessions["2025-04-15-the-whispering-wall"] == ["yester-hill", "whispering-wall"]
    assert sessions["2026-02-10-unwelcome-guests"] == ["vallaki", "tser-crossroads", "castle-ravenloft"]
    assert "2026-02-03-notebook" not in sessions  # merged into welcome-back-to-vellanki


def test_offroad_place_is_reached_by_a_dotted_leg(tmp_path):
    pages = [page("yester-hill", "Yester Hill"), page("whispering-wall", "Whispering Wall"),
             page("wizard-of-wines", "Wizard of Wines")]
    places, parent = barovia_map.load_places(write(tmp_path / "map.yaml",
        "places:\n  wizard-of-wines: {xy: [330, 375]}\n  yester-hill: {xy: [70, 488]}\n"
        "  whispering-wall: {xy: [40, 520], offroad: true}\n"), pages)
    posts = []
    for stem in ("2025-04-01-a", "2025-04-15-b", "2025-04-29-c"):
        post = build.parse_post(write(tmp_path / "posts" / f"{stem}.md", f"---\ntitle: {stem}\ndate: '{stem[:10]}'\n---\n\nx\n"))
        post.html = "<p>x</p>"
        posts.append(post)
    visits = {"2025-04-01-a": ["wizard-of-wines", "yester-hill"], "2025-04-15-b": ["yester-hill", "whispering-wall"]}
    post = posts.pop()
    legs = barovia_map.trail(posts, places, parent, pages, visits)
    assert [s["road"] for s in legs[0]["segments"]] == [True]
    assert [s["road"] for s in legs[1]["segments"]] == [False]
    # Leaving an off-road place, the party walks back to the nearest road first, then follows it.
    legs = barovia_map.trail(posts + [post], places, parent, pages, {**visits, post.source.stem: ["wizard-of-wines"]})
    assert [s["road"] for s in legs[2]["segments"]] == [False, True]


ROOT = Path(__file__).resolve().parent.parent


def real_travel():
    pages = wiki.load_wiki(ROOT / "content" / "wiki", build.split_front_matter)
    places, _ = barovia_map.load_places(ROOT / "data" / "map.yaml", pages)
    return barovia_map.load_travel(ROOT / "data" / "travel-times.yaml", places)


def test_each_labelled_leg_shows_its_hours_from_the_table():
    import yaml
    table = {(leg["from"], leg["to"]): float(leg["hours"])
             for leg in yaml.safe_load((ROOT / "data" / "travel-times.yaml").read_text(encoding="utf-8"))["legs"]}
    travel = real_travel()
    assert {(leg["from"], leg["to"]): leg["hours"] for leg in travel} == table
    root = ET.fromstring(barovia_map.draw_base(travel))
    drawn = {(t.get("data-from"), t.get("data-to")): t.text for t in root.iter() if t.get("class") == "hours"}
    labelled = {(leg["from"], leg["to"]): barovia_map.hours_text(leg["hours"]) for leg in travel if leg["label"]}
    assert drawn == labelled
    assert drawn[("gates-of-barovia", "barovia")] == "3.5 h" and drawn[("ivlis-crossroads", "tser-crossroads")] == "8 h"


def test_travel_legs_need_known_ends_on_the_roads(tmp_path, places):
    by_slug, _ = places
    with pytest.raises(ValueError, match="unknown"):
        barovia_map.load_travel(write(tmp_path / "t.yaml", "legs:\n  - {from: vallaki, to: atlantis, hours: 1}\n"), by_slug)
    with pytest.raises(ValueError, match="road vertex"):
        barovia_map.load_travel(write(tmp_path / "t.yaml", "junctions:\n  nowhere: [500, 700]\n"
                                      "legs:\n  - {from: vallaki, to: nowhere, hours: 1}\n"), by_slug)
    assert barovia_map.load_travel(tmp_path / "missing.yaml", by_slug) == []


def test_places_keep_their_places_on_the_official_layout():
    # Where things sit relative to each other, as on the official map (y grows southward).
    import yaml
    xy = {slug: spec["xy"] for slug, spec in
          yaml.safe_load((ROOT / "data" / "map.yaml").read_text(encoding="utf-8"))["places"].items()}
    x = {slug: v[0] for slug, v in xy.items()}
    y = {slug: v[1] for slug, v in xy.items()}
    assert x["durst-manor"] > x["gates-of-barovia"] > x["barovia"] > x["castle-ravenloft"]   # east to west
    assert x["vallaki"] < x["the-windmill"] < x["tser-crossroads"] < x["castle-ravenloft"]
    assert x["raven-river-crossroads"] < x["vallaki"] and x["krezk"] < x["tower-of-kazan"] < x["raven-river-crossroads"]
    assert y["raven-river-crossroads"] < y["wizard-of-wines"] < y["argynvostholt"]          # south of the crossroads
    assert y["tser-crossroads"] < y["tser-pool"] and y["castle-ravenloft"] < y["barovia"]
    assert y["amber-temple"] > y["tsolenka-pass"] > y["yester-hill"] > y["krezk"]
