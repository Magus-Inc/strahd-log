"""The map's geography lives in data/geography.yaml, so `just map-edit` can change it without code."""
import math
from pathlib import Path

import pytest
import yaml

import barovia_map

ROOT = Path(__file__).resolve().parent.parent
GEO = ROOT / "data" / "geography.yaml"


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_the_drawing_code_holds_no_coordinates():
    source = (ROOT / "barovia_map.py").read_text(encoding="utf-8")
    for name in ("ROADS", "TRACKS", "UNUSED_TRACKS", "LAKES", "RIVERS", "FORESTS", "MOUNTAINS", "LABELS"):
        assert f"\n{name} = {{" not in source and f"\n{name} = [" not in source, name


def test_the_map_draws_what_the_file_says():
    data = yaml.safe_load(GEO.read_text(encoding="utf-8"))
    assert barovia_map.ROADS == {k: [tuple(p) for p in v] for k, v in data["roads"].items()}
    assert list(barovia_map.LAKES) == list(data["lakes"])  # order matters: it feeds the seeded drawing
    assert barovia_map.MOUNTAINS[0] == (tuple(data["mountains"][0]["at"]), data["mountains"][0]["radius"],
                                        data["mountains"][0]["count"], data["mountains"][0]["size"])
    assert barovia_map.LABELS[0][0] == data["labels"][0]["text"]
    assert "Bonegrinder lane" in barovia_map.ROADS and "Tser Pool" in barovia_map.LAKES


MINI = """roads:
  Plain: [[0, 0], [100, 0]]
  Winding:
    points: [[0, 0], [0, 100], [50, 100]]
    shapes: {0: {bends: 3, width: 20}}
tracks:
  Rough:
    points: [[0, 0], [100, 50]]
    shapes: {0: {wiggle: 4}}
unused_tracks: {}
lakes:
  Pond: [[10, 10], [20, 10], [15, 20]]
rivers: {}
forests: []
mountains:
  - {at: [5, 6], radius: 7, count: 8, size: 9}
labels:
  - {text: "Pond", at: [15, 30], size: 10, angle: 0}
"""


def test_switchbacks_bend_back_and_forth_between_the_two_points(tmp_path):
    geo = barovia_map.load_geography(write(tmp_path / "g.yaml", MINI))
    way = geo["roads"]["Winding"]
    assert way[0] == (0, 0) and way[-2:] == [(0, 100), (50, 100)]
    bends = way[1:-2]
    assert len(bends) == 3
    # The road runs down x = 0; the bends swing 10 either side of it, in turn, evenly spaced.
    assert [x for x, _ in bends] == [10, -10, 10]
    assert [y for _, y in bends] == [25, 50, 75]
    # Every point is a vertex of the trail graph, so the trail follows the bends.
    assert geo["roads"]["Plain"] == [(0, 0), (100, 0)]


def test_wiggle_is_small_seeded_and_the_same_every_build(tmp_path):
    path = write(tmp_path / "g.yaml", MINI)
    one = barovia_map.load_geography(path)["tracks"]["Rough"]
    two = barovia_map.load_geography(path)["tracks"]["Rough"]
    assert one == two and one[0] == (0, 0) and one[-1] == (100, 50)
    assert len(one) > 6
    length = math.dist((0, 0), (100, 50))
    for x, y in one[1:-1]:
        # distance from the straight line, which runs along (2, 1)
        off = abs(x * 50 - y * 100) / length
        assert off <= 4.01
    assert any(abs(x * 50 - y * 100) / length > 0.5 for x, y in one[1:-1])


def test_unknown_shapes_are_refused(tmp_path):
    bad = MINI.replace("{wiggle: 4}", "{zigzag: 4}")
    with pytest.raises(ValueError, match="Rough"):
        barovia_map.load_geography(write(tmp_path / "g.yaml", bad))
    past_end = MINI.replace("shapes: {0: {wiggle: 4}}", "shapes: {1: {wiggle: 4}}")
    with pytest.raises(ValueError, match="Rough"):
        barovia_map.load_geography(write(tmp_path / "g.yaml", past_end))


def test_use_geography_swaps_the_map_the_drawing_uses(tmp_path):
    try:
        barovia_map.use_geography(write(tmp_path / "g.yaml", MINI))
        assert list(barovia_map.ROADS) == ["Plain", "Winding"]
        assert barovia_map.MOUNTAINS == [((5, 6), 7, 8, 9)]
        assert barovia_map.LABELS == [("Pond", (15, 30), 10, 0)]
        assert "Pond" in barovia_map.draw_base()
    finally:
        barovia_map.use_geography()
    assert "Bonegrinder lane" in barovia_map.ROADS
