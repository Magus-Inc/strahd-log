"""`just map-edit` edits data/geography.yaml: these are the edits behind its buttons and drags."""
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import geo_edit  # noqa: E402

GEO = """# the top comment stays
roads:
  # the east road
  East: [[0, 0], [50, 0], [100, 0]]
  North: [[50, 0], [50, -50]]
  Winding: {points: [[100, 0], [100, 100], [150, 100]], shapes: {0: {bends: 3, width: 20}}}
tracks: {}
unused_tracks: {}
lakes:
  Pond: [[10, 10], [20, 10], [15, 20]]
  "": [[30, 30], [40, 30], [35, 40]]
rivers: {}
forests:
  # the wood
  - [[200, 200], [300, 200], [250, 300]]
mountains:
  - {at: [5, 6], radius: 7, count: 8, size: 9}
labels:
  - {text: "Pond", at: [15, 30], size: 10, angle: 0}
"""
MAP = """places:
  town: {xy: [50, 0], anchor: end}
spots:
  bend: {xy: [100, 100], label: the bend}
sprites:
  town: {image: town, xy: [50, 0], width: 20}
"""
TRAVEL = """junctions:
  east-end: [100, 0]
legs: []
"""


def data(text):
    return yaml.safe_load(text)


def test_rewriting_the_real_file_unchanged_changes_nothing():
    text = (ROOT / "data" / "geography.yaml").read_text(encoding="utf-8")
    out = text
    for section, key, spec in geo_edit.outlines(data(text)):
        out = geo_edit.set_entry(out, section, key, geo_edit.dump_way(spec))
    assert out == text


def test_moving_a_crossroads_moves_every_road_and_the_place_on_it_but_not_its_picture():
    geo, places, travel = geo_edit.move_point(GEO, MAP, TRAVEL, (50, 0), (55.04, 3))
    roads = data(geo)["roads"]
    assert roads["East"] == [[0, 0], [55, 3], [100, 0]] and roads["North"] == [[55, 3], [50, -50]]
    assert "# the east road" in geo and geo.startswith("# the top comment stays")
    assert "town: {xy: [55, 3], anchor: end}" in places
    assert "image: town, xy: [50, 0]" in places  # sprites are placed by hand, not dragged along
    assert travel == TRAVEL
    geo, places, travel = geo_edit.move_point(GEO, MAP, TRAVEL, (100, 0), (101, 1))
    assert data(travel)["junctions"]["east-end"] == [101, 1]
    assert data(geo)["roads"]["Winding"]["shapes"] == {0: {"bends": 3, "width": 20}}  # shapes stay put
    with pytest.raises(geo_edit.EditError):
        geo_edit.move_point(GEO, MAP, TRAVEL, (7, 7), (8, 8))


def test_adding_and_deleting_points_keeps_shapes_on_their_stretches():
    geo = geo_edit.insert_point(GEO, "roads", "East", 0, (25, 5))
    assert data(geo)["roads"]["East"] == [[0, 0], [25, 5], [50, 0], [100, 0]]
    geo = geo_edit.insert_point(GEO, "roads", "Winding", 1, (125, 110))
    assert data(geo)["roads"]["Winding"] == {"points": [[100, 0], [100, 100], [125, 110], [150, 100]],
                                             "shapes": {0: {"bends": 3, "width": 20}}}
    geo = geo_edit.insert_point(GEO, "roads", "Winding", 0, (90, 50))  # inside the switchbacks: back to smooth
    assert data(geo)["roads"]["Winding"] == [[100, 0], [90, 50], [100, 100], [150, 100]]
    geo = geo_edit.insert_point(GEO, "lakes", "", 2, (30, 38))  # the closing stretch of an outline
    assert data(geo)["lakes"][""][-1] == [30, 38]
    geo = geo_edit.insert_point(GEO, "forests", 0, 0, (250, 190))
    assert data(geo)["forests"][0][1] == [250, 190] and "  # the wood" in geo


def test_a_junction_or_a_place_point_cannot_be_deleted():
    with pytest.raises(geo_edit.EditError, match="road North"):
        geo_edit.delete_point(GEO, MAP, TRAVEL, "roads", "East", 1)
    with pytest.raises(geo_edit.EditError, match="spot bend"):
        geo_edit.delete_point(GEO, MAP, TRAVEL, "roads", "Winding", 1)
    with pytest.raises(geo_edit.EditError, match="too few"):
        geo_edit.delete_point(GEO, MAP, TRAVEL, "lakes", "Pond", 0)
    geo = geo_edit.insert_point(GEO, "roads", "Winding", 1, (125, 110))
    geo = geo_edit.delete_point(geo, MAP, TRAVEL, "roads", "Winding", 2)
    assert data(geo)["roads"]["Winding"]["points"] == [[100, 0], [100, 100], [150, 100]]


def test_shapes_can_be_set_cleared_and_turned_into_points():
    geo = geo_edit.set_shape(GEO, "roads", "East", 1, {"wiggle": "3"})
    assert data(geo)["roads"]["East"] == {"points": [[0, 0], [50, 0], [100, 0]], "shapes": {1: {"wiggle": 3}}}
    geo = geo_edit.set_shape(geo, "roads", "East", 1, None)
    assert data(geo)["roads"]["East"] == [[0, 0], [50, 0], [100, 0]]
    with pytest.raises(geo_edit.EditError):
        geo_edit.set_shape(GEO, "lakes", "Pond", 0, {"wiggle": 3})
    with pytest.raises(ValueError):
        geo_edit.set_shape(GEO, "roads", "East", 0, {"zigzag": 3})
    with pytest.raises(geo_edit.EditError, match="bends"):
        geo_edit.set_shape(GEO, "roads", "East", 0, {"bends": 99, "width": 10})
    geo = geo_edit.bake(GEO, "roads", "Winding", 0)
    assert data(geo)["roads"]["Winding"] == [[100, 0], [110, 25], [90, 50], [110, 75], [100, 100], [150, 100]]
    with pytest.raises(geo_edit.EditError):
        geo_edit.bake(geo, "roads", "Winding", 0)


def test_lakes_and_forests_move_whole_and_mountains_and_labels_move_by_their_centre():
    geo = geo_edit.shift(GEO, "lakes", "Pond", 5, -5)
    assert data(geo)["lakes"]["Pond"] == [[15, 5], [25, 5], [20, 15]]
    geo = geo_edit.move_item(GEO, "mountains", 0, (50, 60.04))
    assert data(geo)["mountains"][0] == {"at": [50, 60], "radius": 7, "count": 8, "size": 9}
    geo = geo_edit.move_item(GEO, "labels", 0, (1, 2))
    assert data(geo)["labels"][0] == {"text": "Pond", "at": [1, 2], "size": 10, "angle": 0}
    with pytest.raises(geo_edit.EditError):
        geo_edit.shift(GEO, "roads", "East", 1, 1)


def test_the_editor_state_marks_junctions_and_places():
    st = geo_edit.state(GEO, MAP, TRAVEL)
    winding = next(w for w in st["ways"] if w["key"] == "Winding")
    assert winding["shapes"] == {"0": {"bends": 3, "width": 20}} and len(winding["drawn"]) == 6
    pins = {tuple(p["xy"]): p for p in st["pins"]}
    assert pins[(50, 0)]["junction"] and pins[(50, 0)]["place"]
    assert "junction east-end" in pins[(100, 0)]["users"]
    assert pins[(100, 100)]["place"] and not pins[(100, 100)]["junction"]
    assert (0, 0) not in pins


def test_state_of_the_real_map_loads():
    st = geo_edit.state(*(open(ROOT / "data" / f, encoding="utf-8").read()
                          for f in ("geography.yaml", "map.yaml", "travel-times.yaml")))
    assert any(p["junction"] and p["place"] for p in st["pins"])  # the crossroads
    assert len(st["ways"]) > 40


def editor_files(tmp_path):
    import map_editor
    files = [tmp_path / "geography.yaml", tmp_path / "map.yaml", tmp_path / "travel-times.yaml"]
    for f, text in zip(files, (GEO, MAP, TRAVEL)):
        f.write_text(text, encoding="utf-8")
    from PIL import Image
    Image.new("RGBA", (20, 10)).save(tmp_path / "town.webp")
    return map_editor.Editor(*files, sprite_dir=tmp_path, wiki_dir=None), files


def test_the_editor_writes_checks_and_undoes(tmp_path):
    editor, (geo, places, travel) = editor_files(tmp_path)
    editor.apply({"op": "move", "from": [50, 0], "to": [60, 5]})
    assert data(geo.read_text(encoding="utf-8"))["roads"]["North"][0] == [60, 5]
    assert "xy: [60, 5]" in places.read_text(encoding="utf-8")
    editor.apply({"op": "sprite", "name": "town", "xy": [1, 2], "width": 30})
    assert editor.state()["undo"] == 2
    assert editor.undo() and editor.undo() and not editor.undo()
    assert (geo.read_text(encoding="utf-8"), places.read_text(encoding="utf-8")) == (GEO, MAP)
    # A change the map can't draw is refused and nothing is written.
    with pytest.raises(geo_edit.EditError):
        editor.apply({"op": "delete", "section": "roads", "key": "East", "index": 1})
    with pytest.raises(geo_edit.EditError):
        editor.apply({"op": "fly"})
    assert geo.read_text(encoding="utf-8") == GEO and not editor.history
    assert editor.base_svg().startswith("<svg")


def test_the_editor_server_saves_and_says_so(tmp_path):
    import json
    import threading
    import urllib.error
    import urllib.request

    import map_editor
    editor, (geo, _, _) = editor_files(tmp_path)
    server = map_editor.serve(0, editor, tmp_path)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        def post(path, body):
            req = urllib.request.Request(base + path, data=json.dumps(body).encode(), method="POST")
            return json.loads(urllib.request.urlopen(req).read())
        st = post("/geo", {"op": "shape", "section": "roads", "key": "East", "index": 0, "shape": {"wiggle": 2}})
        assert next(w for w in st["ways"] if w["key"] == "East")["shapes"] == {"0": {"wiggle": 2}}
        assert "shapes: {0: {wiggle: 2}}" in geo.read_text(encoding="utf-8")
        with pytest.raises(urllib.error.HTTPError) as err:
            post("/geo", {"op": "delete", "section": "roads", "key": "East", "index": 1})
        assert err.value.code == 400 and b"move it instead" in err.value.read()
        assert urllib.request.urlopen(base + "/edit/base.svg").read().startswith(b"<svg")
        page = urllib.request.urlopen(base + "/edit/").read().decode()
        assert "__SPRITES__" not in page and "Roads &amp; water" in page
        assert post("/undo", {})["undo"] == 0 and geo.read_text(encoding="utf-8") == GEO
    finally:
        server.shutdown()


def test_the_editor_reports_problems_and_hours(tmp_path):
    editor, _ = editor_files(tmp_path)
    st = editor.state()
    assert st["problems"] == [] and st["hours"] == []
    editor.apply({"op": "insert", "section": "roads", "key": "North", "after": 0, "xy": [52, -10]})
    editor.apply({"op": "move", "from": [52, -10], "to": [80, 0]})  # now lies along the east road
    assert any("drawn over each other" in p["text"] for p in editor.state()["problems"])


def test_the_real_editor_state_has_no_problems_and_every_leg():
    import map_editor
    st = map_editor.Editor().state()
    assert st["problems"] == [] and len(st["hours"]) > 20
