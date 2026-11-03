"""The rules the map editor checks after every change; the real map must pass them all."""
from pathlib import Path

import yaml

import barovia_map

ROOT = Path(__file__).resolve().parent.parent

GEO = """roads:
  Road: [[0, 100], [100, 100], [200, 100]]
  Along: [[300, 0], [300, 60]]
tracks:
  Wet: [[400, 0], [450, 50]]
  Over: [[30, 60], [40, 140]]
unused_tracks: {}
lakes:
  Pond: [[440, 40], [460, 40], [460, 60], [440, 60]]
rivers:
  River: [[150, 0], [150, 200]]
  Brook: [[305, 0], [305, 60]]
forests: []
mountains: []
labels: []
"""
MAP = {"places": {"town": {"xy": [100, 100]}, "lost": {"xy": [120, 130]}, "hut": {"xy": [101, 101], "offroad": True}},
       "spots": {"bend": {"xy": [200, 100]}}}


def bridge(x, y):
    return barovia_map.Sprite(name="b", image="bridge", x=x, y=y, width=10, height=10)


def checked(tmp_path, sprites=(), wiki=None):
    path = tmp_path / "g.yaml"
    path.write_text(GEO, encoding="utf-8")
    try:
        barovia_map.use_geography(path)
        return [p["text"] for p in barovia_map.map_problems(MAP, list(sprites), wiki)]
    finally:
        barovia_map.use_geography()


def test_each_rule_is_found(tmp_path):
    found = checked(tmp_path)
    assert "lost is not on a road point any more" in found
    assert "hut is marked off the roads but sits right by one" in found
    assert "Road crosses River with no bridge" in found
    assert any(t.startswith("Along runs along Brook") for t in found)
    assert "Wet goes into Pond" in found
    assert "Road and Over are drawn over each other here" in found
    assert not any("town" in t or "bend" in t for t in found)


def test_a_bridge_makes_a_crossing_fine(tmp_path):
    assert "Road crosses River with no bridge" not in checked(tmp_path, [bridge(152, 100)])


def test_a_crossroads_page_must_name_the_ways_the_map_draws(tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "town.md").write_text("A sleepy four-way crossroads.", encoding="utf-8")
    assert "town's wiki page says four-way, the map draws 2 ways" in checked(tmp_path, wiki=wiki)


def test_the_real_map_breaks_no_rule():
    data = yaml.safe_load((ROOT / "data" / "map.yaml").read_text(encoding="utf-8"))
    sprites = barovia_map.load_sprites(ROOT / "data" / "map.yaml", ROOT / "static" / "images" / "map" / "sprites")
    assert barovia_map.map_problems(data, sprites, ROOT / "content" / "wiki") == []


def test_the_hours_report_lists_every_official_leg():
    data = yaml.safe_load((ROOT / "data" / "map.yaml").read_text(encoding="utf-8"))
    report = barovia_map.travel_report(ROOT / "data" / "travel-times.yaml", data)
    legs = yaml.safe_load((ROOT / "data" / "travel-times.yaml").read_text(encoding="utf-8"))["legs"]
    assert [(r["from"], r["to"], r["hours"]) for r in report] == [(l["from"], l["to"], l["hours"]) for l in legs]
    assert all(r["drawn"] > 0 and len(r["points"]) >= 2 for r in report)
