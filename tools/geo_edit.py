"""Edits to data/geography.yaml (and the places that sit on its points), for `just map-edit`.

Every edit rewrites only the entries it changes, so the comments in the file stay where they are.
A point two ways share, or that a place, spot, landmark or travel-time junction sits on, moves as
one: drag a crossroads and every road that meets there, and the place on it, comes along.
"""

from __future__ import annotations

import math
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import barovia_map  # noqa: E402

WAYS = ("roads", "tracks", "unused_tracks", "rivers")   # open lines; their stretches can take a shape
OUTLINES = ("lakes", "forests")                          # closed outlines
POINTED = ("places", "spots", "landmarks")               # data/map.yaml sections whose xy sits on a point
NEAR = 0.05                                              # two coordinates this close are the same point
WIDTH = 110                                              # wrap long point lists at about this many characters


class EditError(ValueError):
    """An edit that would break the map; the message says why, in plain words."""


# --- writing yaml back, one entry at a time -------------------------------------------------------

def num(v: float) -> str:
    v = round(float(v), 1)
    return str(int(v)) if v.is_integer() else f"{v:g}"


def dump_points(points) -> str:
    return "[" + ", ".join(f"[{num(x)}, {num(y)}]" for x, y in points) + "]"


def dump_shape(shape: dict) -> str:
    return "{" + ", ".join(f"{k}: {num(v)}" for k, v in shape.items()) + "}"


def dump_way(spec) -> str:
    if not isinstance(spec, dict) or not spec.get("shapes"):
        return dump_points(spec["points"] if isinstance(spec, dict) else spec)
    shapes = ", ".join(f"{i}: {dump_shape(s)}" for i, s in sorted((int(i), s) for i, s in spec["shapes"].items()))
    return "{points: " + dump_points(spec["points"]) + ", shapes: {" + shapes + "}}"


def wrap(head: str, body: str) -> list[str]:
    """`head + body` as lines, broken between points, continuation lines indented four spaces."""
    lines, cur = [], head
    pieces = re.split(r"(?<=\]), (?=\[)", body)
    for i, piece in enumerate(pieces):
        piece += "," if i < len(pieces) - 1 else ""
        if i and len(cur) + 1 + len(piece) > WIDTH:
            lines.append(cur)
            cur = "    " + piece
        else:
            cur += ("" if i == 0 else " ") + piece
    lines.append(cur)
    return lines


def _section(lines: list[str], section: str) -> tuple[int, int]:
    """The lines of a top-level section's body: (first, end)."""
    for i, line in enumerate(lines):
        if re.match(rf"^{re.escape(section)}:(\s|$)", line):
            end = i + 1
            while end < len(lines) and not re.match(r"^[^\s#]", lines[end]):
                end += 1
            return i + 1, end
    raise EditError(f"data/geography.yaml has no {section} section")


def _continued(lines: list[str], start: int, end: int) -> int:
    stop = start + 1
    while stop < end and lines[stop].startswith("    "):
        stop += 1
    return stop


def _entry(lines: list[str], section: str, key: str) -> tuple[int, int, str]:
    first, end = _section(lines, section)
    for i in range(first, end):
        m = re.match(r"^  ([^\s#-][^\n]*?|\"[^\"]*\"):(\s|$)", lines[i])
        if m and yaml.safe_load(m.group(1)) == key:
            return i, _continued(lines, i, end), m.group(1)
    raise EditError(f"no {section[:-1].replace('_', ' ')} called {key!r}")


def _item(lines: list[str], section: str, index: int) -> tuple[int, int]:
    first, end = _section(lines, section)
    items = [i for i in range(first, end) if lines[i].startswith("  - ")]
    if not 0 <= index < len(items):
        raise EditError(f"no {section} item {index}")
    return items[index], _continued(lines, items[index], end)


def set_entry(text: str, section: str, key, value: str) -> str:
    """The text with one entry's value replaced: a named way or lake, or a numbered list item."""
    lines = text.splitlines()
    if isinstance(key, int):
        a, b = _item(lines, section, key)
        new = wrap("  - ", value)
    else:
        a, b, token = _entry(lines, section, key)
        new = wrap(f"  {token}: ", value)
    return "\n".join(lines[:a] + new + lines[b:]) + "\n"


# --- reading ------------------------------------------------------------------------------------

def load(text: str) -> dict:
    return yaml.safe_load(text) or {}


def same(a, b) -> bool:
    return abs(a[0] - b[0]) <= NEAR and abs(a[1] - b[1]) <= NEAR


def spec_of(data: dict, section: str, key):
    try:
        return data[section][key]
    except (KeyError, IndexError, TypeError):
        raise EditError(f"no {section} entry {key!r}") from None


def points_of(spec) -> list[list[float]]:
    return [list(p) for p in (spec["points"] if isinstance(spec, dict) else spec)]


def with_points(spec, points, shapes=None):
    if isinstance(spec, dict) or shapes:
        shapes = spec.get("shapes", {}) if shapes is None and isinstance(spec, dict) else (shapes or {})
        return {"points": points, "shapes": shapes} if shapes else points
    return points


def outlines(data: dict):
    """Every way and outline: (section, key, spec); forests are keyed by their number."""
    for section in WAYS + ("lakes",):
        for key, spec in (data.get(section) or {}).items():
            yield section, key, spec
    for i, spec in enumerate(data.get("forests") or []):
        yield "forests", i, spec


def users(geo_text: str, map_text: str, travel_text: str, xy) -> list[str]:
    """What sits on a point: the ways through it, and the places, spots, landmarks and junctions on it."""
    found = []
    for section, key, spec in outlines(load(geo_text)):
        if any(same(p, xy) for p in points_of(spec)):
            found.append(f"{section[:-1].replace('_', ' ')} {key if isinstance(key, str) else '#' + str(key + 1)}")
    data = load(map_text)
    for section in POINTED:
        for slug, item in (data.get(section) or {}).items():
            if isinstance(item, dict) and "xy" in item and same(item["xy"], xy):
                found.append(f"{section[:-1]} {slug}")
    for name, at in ((load(travel_text).get("junctions")) or {}).items():
        if same(at, xy):
            found.append(f"junction {name}")
    return found


# --- edits --------------------------------------------------------------------------------------

def move_point(geo_text: str, map_text: str, travel_text: str, old, new) -> tuple[str, str, str]:
    """Move a point, and everything that shares it, to `new`."""
    new = [round(float(new[0]), 1), round(float(new[1]), 1)]
    data, moved = load(geo_text), 0
    for section, key, spec in list(outlines(data)):
        pts = points_of(spec)
        if any(same(p, old) for p in pts):
            pts = [new if same(p, old) else p for p in pts]
            geo_text = set_entry(geo_text, section, key, dump_way(with_points(spec, pts)))
            moved += 1
    if not moved:
        raise EditError(f"no way has a point at {num(old[0])}, {num(old[1])}")
    map_text = _move_xy(map_text, POINTED, old, new)
    travel_text = _move_xy(travel_text, ("junctions",), old, new)
    return geo_text, map_text, travel_text


def _move_xy(text: str, sections, old, new) -> str:
    """`[x, y]` pairs at `old` inside the named sections of a yaml file, moved to `new`."""
    lines = text.splitlines()
    pair = re.compile(r"\[\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*\]")
    for section in sections:
        try:
            first, end = _section(lines, section)
        except EditError:
            continue
        for i in range(first, end):
            if lines[i].lstrip().startswith("#"):
                continue
            lines[i] = pair.sub(lambda m: f"[{num(new[0])}, {num(new[1])}]"
                                if same((float(m.group(1)), float(m.group(2))), old) else m.group(0), lines[i])
    return "\n".join(lines) + "\n"


def insert_point(geo_text: str, section: str, key, after: int, xy) -> str:
    """Add a point to a way or outline after point number `after`. A shape on that stretch is dropped."""
    data = load(geo_text)
    spec = spec_of(data, section, key)
    pts = points_of(spec)
    closed = section in OUTLINES
    if not 0 <= after < (len(pts) if closed else len(pts) - 1):
        raise EditError("add a point on a stretch between two points")
    pts.insert(after + 1, [round(float(xy[0]), 1), round(float(xy[1]), 1)])
    shapes = _shapes(spec)
    shapes = {(i + 1 if i > after else i): s for i, s in shapes.items() if i != after}
    return set_entry(geo_text, section, key, dump_way(with_points(spec, pts, shapes) if section in WAYS else pts))


def delete_point(geo_text: str, map_text: str, travel_text: str, section: str, key, index: int) -> str:
    """Remove a point. A junction, or a point a place sits on, can't go: move it instead."""
    spec = spec_of(load(geo_text), section, key)
    pts = points_of(spec)
    if not 0 <= index < len(pts):
        raise EditError("no such point")
    me = f"{section[:-1].replace('_', ' ')} {key if isinstance(key, str) else '#' + str(key + 1)}"
    others = [u for u in users(geo_text, map_text, travel_text, pts[index]) if u != me]
    if others:
        raise EditError("can't delete a point that " + ", ".join(others) + " also uses; move it instead")
    if len(pts) <= (3 if section in OUTLINES else 2):
        raise EditError("too few points left; a way needs two, a lake or forest three")
    del pts[index]
    shapes = {(i - 1 if i > index else i): s for i, s in _shapes(spec).items() if i not in (index - 1, index)}
    return set_entry(geo_text, section, key, dump_way(with_points(spec, pts, shapes) if section in WAYS else pts))


def _shapes(spec) -> dict[int, dict]:
    return {int(i): s for i, s in (spec.get("shapes") or {}).items()} if isinstance(spec, dict) else {}


def set_shape(geo_text: str, section: str, key: str, index: int, shape: dict | None) -> str:
    """Give the stretch from point `index` to the next a shape (switchbacks or wiggle), or None for smooth."""
    if section not in WAYS:
        raise EditError("only roads, tracks and rivers take a shape")
    spec = spec_of(load(geo_text), section, key)
    pts = points_of(spec)
    if not 0 <= index < len(pts) - 1:
        raise EditError("no such stretch")
    shapes = _shapes(spec)
    if shape:
        shape = {k: float(v) for k, v in shape.items() if v not in (None, "")}
        barovia_map.shape_points(pts[index], pts[index + 1], shape, "check")  # refuses a bad shape
        if "bends" in shape:
            shape["bends"] = int(shape["bends"])
            if not 1 <= shape["bends"] <= 30:
                raise EditError("pick 1 to 30 bends")
        shapes[index] = shape
    else:
        shapes.pop(index, None)
    return set_entry(geo_text, section, key, dump_way({"points": pts, "shapes": shapes}))


def bake(geo_text: str, section: str, key: str, index: int) -> str:
    """Turn a shaped stretch into plain points, so each bend can be dragged on its own."""
    spec = spec_of(load(geo_text), section, key)
    pts, shapes = points_of(spec), _shapes(spec)
    if index not in shapes:
        raise EditError("that stretch has no shape to turn into points")
    extra = [list(p) for p in barovia_map.shape_points(pts[index], pts[index + 1], shapes[index], f"{key}/{index}")]
    pts[index + 1:index + 1] = extra
    shapes = {(i + len(extra) if i > index else i): s for i, s in shapes.items() if i != index}
    return set_entry(geo_text, section, key, dump_way({"points": pts, "shapes": shapes}))


def shift(geo_text: str, section: str, key, dx: float, dy: float) -> str:
    """Move a whole lake or forest outline."""
    if section not in OUTLINES:
        raise EditError("only a lake or a forest moves whole")
    pts = [[x + dx, y + dy] for x, y in points_of(spec_of(load(geo_text), section, key))]
    return set_entry(geo_text, section, key, dump_points(pts))


def move_item(geo_text: str, section: str, index: int, at) -> str:
    """Move a mountain cluster's centre or a label."""
    items = load(geo_text).get(section) or []
    if section not in ("mountains", "labels") or not 0 <= index < len(items):
        raise EditError("no such mountain or label")
    item = dict(items[index])
    item["at"] = [round(float(at[0]), 1), round(float(at[1]), 1)]
    parts = []
    for k, v in item.items():
        if k == "text":
            parts.append(f'text: "{v}"')
        elif k == "at":
            parts.append(f"at: [{num(v[0])}, {num(v[1])}]")
        else:
            parts.append(f"{k}: {num(v)}")
    return set_entry(geo_text, section, index, "{" + ", ".join(parts) + "}")


def check(geo_text: str) -> None:
    """Refuse a file the map can't draw."""
    try:
        barovia_map.geography_from(load(geo_text))
    except (ValueError, KeyError, TypeError) as err:
        raise EditError(f"the map can't use that: {err}") from None


def state(geo_text: str, map_text: str, travel_text: str) -> dict:
    """What the editor page draws: every way's points and shapes, the drawn line, and what sits where."""
    data = load(geo_text)
    geo = barovia_map.geography_from(data)
    ways = []
    for section, key, spec in outlines(data):
        drawn = geo[section][key] if section in geo and isinstance(geo[section], dict) else points_of(spec)
        ways.append({"section": section, "key": key, "points": points_of(spec),
                     "shapes": {str(i): s for i, s in _shapes(spec).items()},
                     "drawn": [list(p) for p in drawn], "closed": section in OUTLINES})
    count: dict[tuple, list[str]] = {}
    for w in ways:
        for p in w["points"]:
            count.setdefault((round(p[0], 1), round(p[1], 1)), []).append(w["key"] if isinstance(w["key"], str)
                                                                         else f"forest #{w['key'] + 1}")
    places = load(map_text)
    on = {}
    for section in POINTED:
        for slug, item in (places.get(section) or {}).items():
            if isinstance(item, dict) and "xy" in item:
                on.setdefault((round(item["xy"][0], 1), round(item["xy"][1], 1)), []).append(f"{section[:-1]} {slug}")
    for name, at in (load(travel_text).get("junctions") or {}).items():
        on.setdefault((round(at[0], 1), round(at[1], 1)), []).append(f"junction {name}")
    pins = []
    for xy in set(count) | set(on):
        names = count.get(xy, []) + on.get(xy, [])
        if len(names) > 1 or on.get(xy):
            pins.append({"xy": list(xy), "users": names, "junction": len(count.get(xy, [])) > 1,
                         "place": any(n.startswith(("place ", "spot ")) for n in on.get(xy, []))})
    return {"ways": ways, "pins": pins,
            "mountains": [{"at": m["at"], "radius": m["radius"]} for m in data.get("mountains") or []],
            "labels": [{"at": lab["at"], "text": lab["text"], "size": lab["size"]} for lab in data.get("labels") or []]}
