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
  barovia: {xy: [800, 440], label: Village of Barovia, names: [Village of Barovia]}
  vallaki: {xy: [390, 244]}
  krezk: {xy: [102, 230], anchor: end}
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
    assert by_slug["krezk"].label_xy == (92.0, 234.0)
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
    write(root / "data" / "map.yaml", "places:\n  barovia: {xy: [800, 440], names: [Village of Barovia]}\n  vallaki: {xy: [390, 244]}\n"
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
    vallaki, castle = (388, 243), (707, 357)
    path = barovia_map.route(graph, vallaki, castle)
    assert path[0] == vallaki and path[-1] == castle
    assert (590, 312) in path  # through the fork below the castle, as the road runs
    assert all(b in graph[a] for a, b in zip(path, path[1:]))
    assert barovia_map.route(graph, vallaki, vallaki) == [vallaki]


def test_every_mapped_place_sits_on_a_road():
    import yaml
    spec = yaml.safe_load(Path("data/map.yaml").read_text(encoding="utf-8"))
    graph = barovia_map.road_graph()
    for slug, place in spec["places"].items():
        assert tuple(place["xy"]) in graph, slug


def test_trail_passes_the_east_gate_only_once():
    # The party came through the east gate of Barovia once, from Durst Manor into the village.
    import yaml
    sessions = yaml.safe_load(Path("data/trail.yaml").read_text(encoding="utf-8"))["sessions"]
    assert [stem for stem, stops in sessions.items() if "gates-of-barovia" in (stops or [])] == ["2024-02-13-barovia-barovia"]
