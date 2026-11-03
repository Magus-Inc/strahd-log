"""Our own map of Barovia, and the party's breadcrumb trail along its roads.

draw_base() returns the map as standalone SVG, sketched in ink to lie on the parchment
(static/images/map/parchment.jpg): ink-outlined conifers, hatched mountains, lakes and rivers drawn
as one body of water, dirt roads, mist at the edges. Hand-drawn place sprites (data/map.yaml
`sprites`) lie over it. It is generated from a fixed seed, so every build draws the same map. The
geography follows where the table map puts things; nothing is traced. Places and the trail are an
overlay (templates/_map.html), so this base stays a clean source map.

The roads are also a graph: each leg of the trail runs along the roads between two places by the
shortest route (route()), the way the party actually travelled, instead of a straight line.
"""

from __future__ import annotations

import heapq
import math
import random
import re
import zlib
from dataclasses import dataclass, field
from pathlib import Path

import yaml

import wiki

W, H = 1000, 750
# About how much road an hour on foot covers, going by the hours the official map marks on its
# roads (the median over data/travel-times.yaml). It sets the scale bar.
HOUR = 41  # map units per hour on foot; the roads traced from the official map wind, so the scale grew from 37
SEED = 1987

INK = "#3b2a1a"        # outlines and lettering
PAPER = "#ece2c8"
TREE = "#4f5e36"
TREE_DARK = "#26382a"
WATER = "#8fa9b3"
WATER_EDGE = "#3f6684"
ROAD = "#dcc79c"
RUTS = "#a88a5c"
SNOW = "#e9dcb8"
ROCK = "#7a6a55"

# --- geography (drawing space 1000 x 750, x east, y south) -------------------------------------

# The geography lives in data/geography.yaml (`just map-edit` drags it): roads, tracks and the
# tracks the party never took, as points along each way; lakes as shores; rivers downstream last;
# forest outlines, mountain clusters and labels. A point two ways share is a junction, and every place
# on the map sits on a point, so the ways double as the graph the trail is routed over. Where the
# roads run and where they meet follows the official map of Barovia; nothing is traced, and the hours
# in data/travel-times.yaml only set the scale bar.
GEOGRAPHY = Path(__file__).resolve().parent / "data" / "geography.yaml"
WAY_SECTIONS = ("roads", "tracks", "unused_tracks", "rivers")
WIGGLE_EVERY = 10  # map units between the kinks of a wiggled stretch


def shape_points(a, b, shape: dict, seed: str) -> list[tuple[float, float]]:
    """The points a shaped stretch adds between a and b (not a or b themselves).

    {bends: n, width: w}: switchbacks, n points swinging w/2 to either side of the line in turn, which
    the drawn curve turns into S-bends. {wiggle: r}: a kink every WIGGLE_EVERY units, up to r off the
    line, from a seed made of the way's name, so every build draws the same road.
    """
    (ax, ay), (bx, by) = a, b
    length = math.dist(a, b) or 1.0
    px, py = (by - ay) / length, -(bx - ax) / length  # a unit step to the right of a -> b

    def at(t: float, off: float) -> tuple[float, float]:
        x, y = ax + (bx - ax) * t + px * off, ay + (by - ay) * t + py * off
        return (round(x, 1) + 0.0, round(y, 1) + 0.0)

    if set(shape) <= {"bends", "width"} and "bends" in shape:
        n, half = int(shape["bends"]), float(shape.get("width", 12)) / 2
        return [at(i / (n + 1), half if i % 2 else -half) for i in range(1, n + 1)]
    if set(shape) <= {"wiggle"} and "wiggle" in shape:
        rng = random.Random(zlib.crc32(seed.encode("utf-8")))
        r, k = float(shape["wiggle"]), max(2, round(length / WIGGLE_EVERY))
        return [at(i / k, rng.uniform(-r, r)) for i in range(1, k)]
    raise ValueError(f"unknown shape {shape}")


def expand_way(name: str, spec) -> list[tuple[float, float]]:
    """A way from data/geography.yaml as the points it is drawn and routed through."""
    if not isinstance(spec, dict):
        return [tuple(p) for p in spec]
    points = [tuple(p) for p in spec["points"]]
    shapes = {int(i): s for i, s in (spec.get("shapes") or {}).items()}
    out = []
    for i, p in enumerate(points):
        out.append(p)
        if i in shapes and i + 1 < len(points):
            try:
                out += shape_points(p, points[i + 1], shapes[i], f"{name}/{i}")
            except ValueError as err:
                raise ValueError(f"{name}: {err}") from None
    bad = [i for i in shapes if not 0 <= i < len(points) - 1]
    if bad:
        raise ValueError(f"{name}: a shape on stretch {bad[0]}, but the way has {len(points) - 1} stretches")
    return out


def load_geography(path: Path = GEOGRAPHY) -> dict:
    """data/geography.yaml, with every way expanded into the points it is drawn through."""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    geo = {sec: {name: expand_way(name, spec) for name, spec in (data.get(sec) or {}).items()}
           for sec in WAY_SECTIONS}
    geo["lakes"] = {name: [tuple(p) for p in pts] for name, pts in (data.get("lakes") or {}).items()}
    geo["forests"] = [[tuple(p) for p in pts] for pts in data.get("forests") or []]
    geo["mountains"] = [(tuple(m["at"]), m["radius"], m["count"], m["size"]) for m in data.get("mountains") or []]
    geo["labels"] = [(lab["text"], tuple(lab["at"]), lab["size"], lab.get("angle", 0)) for lab in data.get("labels") or []]
    return geo


def use_geography(path: Path = GEOGRAPHY) -> None:
    """Draw and route over the geography in `path` from now on (the map editor reloads after each change)."""
    global ROADS, TRACKS, UNUSED_TRACKS, LAKES, RIVERS, FORESTS, MOUNTAINS, LABELS
    geo = load_geography(path)
    ROADS, TRACKS, UNUSED_TRACKS, RIVERS = geo["roads"], geo["tracks"], geo["unused_tracks"], geo["rivers"]
    LAKES, FORESTS, MOUNTAINS, LABELS = geo["lakes"], geo["forests"], geo["mountains"], geo["labels"]


ROADS: dict[str, list] = {}
TRACKS: dict[str, list] = {}
UNUSED_TRACKS: dict[str, list] = {}  # drawn like tracks but never walked by the trail: the party never took them
LAKES: dict[str, list] = {}
RIVERS: dict[str, list] = {}
FORESTS: list[list] = []
MOUNTAINS: list[tuple] = []
LABELS: list[tuple] = []
use_geography()


# --- drawing helpers ----------------------------------------------------------------------------

def jitter(rng: random.Random, points, amount=1.4):
    return [(x + rng.uniform(-amount, amount), y + rng.uniform(-amount, amount)) for x, y in points]


Point = tuple[float, float]
Bezier = tuple[Point, Point, Point, Point]  # start, two control points, end


def curves_of(points, closed=False) -> list[Bezier]:
    """Catmull-Rom through the points, as one cubic Bezier per pair of neighbouring points."""
    pts = list(points)
    if len(pts) < 2:
        return []
    pts = (pts[-1:] + pts + pts[:2]) if closed else (pts[:1] + pts + pts[-1:])
    out = []
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        out.append((p1, c1, c2, p2))
    return out


def bezier_path(beziers: list[Bezier], closed=False) -> str:
    if not beziers:
        return ""
    d = [f"M{beziers[0][0][0]:.1f},{beziers[0][0][1]:.1f}"]
    d += [f"C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {p[0]:.1f},{p[1]:.1f}" for _, c1, c2, p in beziers]
    return " ".join(d) + (" Z" if closed else "")


def smooth_path(points, closed=False) -> str:
    """Catmull-Rom through the points, as cubic Beziers."""
    return bezier_path(curves_of(points, closed), closed)


def bezier_points(bez: Bezier, step: float = 1.0) -> list[Point]:
    """Points along one Bezier, about `step` apart."""
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = bez
    n = max(4, int(math.dist(bez[0], bez[3]) / step) + 1)
    out = []
    for k in range(n + 1):
        u = k / n
        v = 1 - u
        a, b, c, d = v * v * v, 3 * v * v * u, 3 * v * u * u, u * u * u
        out.append((a * x0 + b * x1 + c * x2 + d * x3, a * y0 + b * y1 + c * y2 + d * y3))
    return out


def inside(point, polygon) -> bool:
    x, y = point
    hit = False
    for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            hit = not hit
    return hit


def near_line(point, line, distance) -> bool:
    px, py = point
    for (x1, y1), (x2, y2) in zip(line, line[1:]):
        dx, dy = x2 - x1, y2 - y1
        t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy or 1)))
        if math.hypot(px - (x1 + t * dx), py - (y1 + t * dy)) < distance:
            return True
    return False


def tree(rng: random.Random, x: float, y: float) -> str:
    """A small conifer sketched in ink: a wobbly two-tier outline over a green wash, a trunk tick."""
    h = rng.uniform(9, 13)
    w = h * rng.uniform(0.34, 0.44)

    def j() -> float:
        return rng.uniform(-0.5, 0.5)

    d = (f"M{x + j():.1f},{y - h:.1f} L{x - w * 0.6 + j():.1f},{y - h * 0.45:.1f} L{x - w * 0.25:.1f},{y - h * 0.48:.1f} "
         f"L{x - w + j():.1f},{y:.1f} L{x + w + j():.1f},{y:.1f} L{x + w * 0.25:.1f},{y - h * 0.48:.1f} "
         f"L{x + w * 0.6 + j():.1f},{y - h * 0.45:.1f} Z")
    return (f'<g class="tree" data-xy="{x:.1f},{y:.1f}">'
            f'<path d="{d}" fill="{TREE}" fill-opacity="0.78" stroke="{INK}" stroke-width="0.55" stroke-linejoin="round"/>'
            f'<path d="M{x:.1f},{y:.1f} v2.2 M{x + w * 0.15:.1f},{y - h * 0.3:.1f} l{w * 0.5:.1f},{h * 0.25:.1f}" '
            f'stroke="{INK}" stroke-width="0.5"/></g>')


def mountain(rng: random.Random, x: float, y: float, size: float) -> str:
    """A peak sketched in ink: a ragged ridge with a shoulder, hatching down the shadowed east face."""
    w = size * rng.uniform(0.8, 1.15)
    h = size * rng.uniform(0.8, 1.15)
    px = x + rng.uniform(-w * 0.15, w * 0.15)
    sx, sy = px + w * rng.uniform(0.3, 0.5), y - h * rng.uniform(0.45, 0.6)
    ridge = [(x - w, y), (x - w * 0.62, y - h * rng.uniform(0.3, 0.5)), (x - w * 0.35, y - h * rng.uniform(0.55, 0.7)),
             (px, y - h), (px + w * 0.18, y - h * rng.uniform(0.75, 0.9)), (sx, sy),
             (x + w * 0.75, y - h * rng.uniform(0.1, 0.25)), (x + w, y)]
    pts = " ".join(f"{a + rng.uniform(-0.6, 0.6):.1f},{b + rng.uniform(-0.6, 0.6):.1f}" for a, b in ridge)
    hatch = []
    n = int(4 + size / 4)
    for i in range(1, n):
        t = i / n
        ax, ay = px + (x + w - px) * t, (y - h) + h * t
        hatch.append(f"M{ax:.1f},{ay:.1f} l{-w * 0.28 * (1 - t * 0.5):.1f},{h * 0.32 * (1 - t * 0.4):.1f}")
    return (f'<polygon points="{pts}" fill="{SNOW}" fill-opacity="0.55"/>'
            f'<path d="M{px:.1f},{y - h:.1f} L{sx:.1f},{sy:.1f} L{x + w:.1f},{y:.1f} L{px + w * 0.12:.1f},{y:.1f} Z" '
            f'fill="{ROCK}" fill-opacity="0.28"/>'
            f'<path d="{" ".join(hatch)}" stroke="{INK}" stroke-width="0.45" fill="none"/>'
            f'<path d="M{px:.1f},{y - h:.1f} q{w * 0.05:.1f},{h * 0.4:.1f} {w * 0.12:.1f},{h * 0.75:.1f}" fill="none" '
            f'stroke="{INK}" stroke-width="0.6"/>'
            f'<polyline points="{pts}" fill="none" stroke="{INK}" stroke-width="0.95" stroke-linejoin="round" '
            f'stroke-linecap="round"/>')


def smooth_points(points, n: int = 8) -> list[Point]:
    """The Catmull-Rom curve smooth_path() draws, as points (n per span)."""
    pts = list(points)
    pts = pts[:1] + pts + pts[-1:]
    out = [pts[1]]
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        for k in range(1, n + 1):
            t = k / n
            u = 1 - t
            out.append((u ** 3 * p1[0] + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t ** 3 * p2[0],
                        u ** 3 * p1[1] + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t ** 3 * p2[1]))
    return out


def into_lakes(points) -> list[Point]:
    """The river, with an end that stops at a lake's shore carried a little way into the lake."""
    pts = list(points)
    for end in (0, -1):
        x, y = pts[end]
        for shore in LAKES.values():
            if inside((x, y), shore) or near_line((x, y), shore + shore[:1], 22):
                cx = sum(a for a, _ in shore) / len(shore)
                cy = sum(b for _, b in shore) / len(shore)
                d = math.dist((x, y), (cx, cy)) or 1
                inner = (x + (cx - x) / d * 12, y + (cy - y) / d * 12)
                pts.insert(0, inner) if end == 0 else pts.append(inner)
                break
    return pts


def draw_water(rng: random.Random) -> str:
    """Lakes and rivers as one body of water, in ink.

    Every ink bank is drawn before any water, so where a river meets a lake or another river the
    water runs on through without a seam. Rivers widen downstream; the wide ones carry faint pale
    streaks of slow current, and the lakes ink contour lines inside the shore.
    """
    ink, water, rings, flow = [], [], [], []
    for pts in LAKES.values():
        shore = jitter(rng, [q for a, b in zip(pts, pts[1:] + pts[:1])
                             for q in (a, ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2))], 2.2)
        d = smooth_path(shore, closed=True)
        ink.append(f'<path d="{d}" fill="none" stroke="{INK}" stroke-width="2.6" stroke-linejoin="round"/>')
        water.append(f'<path d="{d}" fill="{WATER}"/>')
        cx = sum(x for x, _ in pts) / len(pts)
        cy = sum(y for _, y in pts) / len(pts)
        for k, scale in enumerate((0.88, 0.77, 0.66)):
            ring = [(cx + (x - cx) * scale, cy + (y - cy) * scale) for x, y in shore]
            rings.append(f'<path d="{smooth_path(ring, closed=True)}" fill="none" stroke="{INK}" '
                         f'stroke-width="0.45" stroke-opacity="{0.45 - k * 0.1:.2f}"/>')
    for name, pts in RIVERS.items():
        small = "streams" in name or name.startswith("To the")
        line = smooth_points(into_lakes(pts), 10)
        w0, w1 = (1.6, 2.6) if small else (2.6, 6.0)
        step = 4
        for i in range(0, len(line) - 1, step):
            seg = line[i:i + step + 1]
            w = w0 + (w1 - w0) * i / max(len(line) - 1, 1)
            d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in seg)
            ink.append(f'<path d="{d}" fill="none" stroke="{INK}" stroke-width="{w + 1.8:.2f}" '
                       f'stroke-linecap="round" stroke-linejoin="round"/>')
            water.append(f'<path d="{d}" fill="none" stroke="{WATER}" stroke-width="{w:.2f}" '
                         f'stroke-linecap="round" stroke-linejoin="round"/>')
        if not small:
            d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in line[len(line) // 4:])
            flow.append(f'<path d="{d}" fill="none" stroke="#dfe8ea" stroke-width="0.7" stroke-opacity="0.7" '
                        f'stroke-dasharray="9 7 3 9" stroke-linecap="round"/>')
    return "".join(ink + water + rings + flow)


ROAD_WIDTH = 3      # a road's dirt surface, in map units (its ink edge is drawn 4.8 wide under it)
# Breadcrumb lanes across a road, off its middle in map units: the first trip over a stretch runs down
# the middle, later trips beside it, all on the dirt (Chris, 2026-11-02: crumbs on the road's black
# edge were hard to see). A fourth trip shares the least-used lane.
LANES = (0.0, 0.9, -0.9)


def draw_roads() -> str:
    """Dirt roads with an ink edge and faint wheel ruts, every edge before any surface so junctions
    join cleanly; tracks are dotted ink."""
    roads = [smooth_path(p) for p in ROADS.values()]
    casing = "".join(f'<path d="{d}" fill="none" stroke="{INK}" stroke-opacity="0.85" stroke-width="4.8" '
                     f'stroke-linecap="round" stroke-linejoin="round"/>' for d in roads)
    surface = "".join(f'<path d="{d}" fill="none" stroke="{ROAD}" stroke-width="{ROAD_WIDTH}" stroke-linecap="round" '
                      f'stroke-linejoin="round"/>' for d in roads)
    ruts = "".join(f'<path d="{d}" fill="none" stroke="{RUTS}" stroke-width="0.6" stroke-dasharray="4 5" '
                   f'stroke-opacity="0.7"/>' for d in roads)
    tracks = "".join(f'<path d="{smooth_path(p)}" fill="none" stroke="{INK}" stroke-width="1.7" '
                     f'stroke-dasharray="0.5 4.5" stroke-linecap="round"/>'
                     for p in list(TRACKS.values()) + list(UNUSED_TRACKS.values()))
    return casing + surface + ruts + tracks


def compass(x: float, y: float, r: float) -> str:
    star = []
    for i in range(8):
        a = math.radians(i * 45 - 90)
        length = r if i % 2 == 0 else r * 0.55
        tip = (x + length * math.cos(a), y + length * math.sin(a))
        left = (x + r * 0.13 * math.cos(a - math.pi / 2), y + r * 0.13 * math.sin(a - math.pi / 2))
        right = (x + r * 0.13 * math.cos(a + math.pi / 2), y + r * 0.13 * math.sin(a + math.pi / 2))
        fill = INK if i % 2 == 0 else PAPER
        star.append(f'<path d="M{left[0]:.1f},{left[1]:.1f} L{tip[0]:.1f},{tip[1]:.1f} L{right[0]:.1f},{right[1]:.1f} Z" '
                    f'fill="{fill}"/>')
    return (f'<g stroke="{INK}" stroke-width="0.8"><circle cx="{x}" cy="{y}" r="{r * 0.72:.1f}" fill="none"/>'
            f'{"".join(star)}<text x="{x}" y="{y - r - 5:.1f}" text-anchor="middle" font-size="15" stroke="none" '
            f'fill="{INK}">N</text></g>')


def mists(rng: random.Random) -> str:
    """Soft white mist creeping in from the edges, like the clouds on the table map."""
    defs = ('<radialGradient id="puff"><stop offset="0" stop-color="#fbfbfa" stop-opacity="0.95"/>'
            '<stop offset="0.6" stop-color="#f2f2f0" stop-opacity="0.55"/>'
            '<stop offset="1" stop-color="#f2f2f0" stop-opacity="0"/></radialGradient>')
    puffs = []
    for _ in range(90):
        edge = rng.choice("nsew")
        d = abs(rng.gauss(0, 22))
        if edge in "ns":
            x, y = rng.uniform(0, W), d if edge == "n" else H - d
        else:
            x, y = d if edge == "w" else W - d, rng.uniform(0, H)
        r = rng.uniform(26, 70)
        puffs.append(f'<ellipse cx="{x:.0f}" cy="{y:.0f}" rx="{r:.0f}" ry="{r * 0.6:.0f}" fill="url(#puff)"/>')
    return defs, "".join(puffs)


# --- the base map --------------------------------------------------------------------------------

def draw_base(sprites: list[Sprite] = ()) -> str:
    """The base map, drawn to lie on the parchment (static/images/map/parchment.jpg), under the sprites."""
    rng = random.Random(SEED)
    water = list(LAKES.values())
    lines = list(ROADS.values()) + list(TRACKS.values()) + list(UNUSED_TRACKS.values()) + list(RIVERS.values())

    # Clearings under the sprites, so no tree or peak is drawn under a building.
    clearings = [((sp.x, sp.y), max(sp.width, sp.height) * 0.45) for sp in sprites]

    def clear(point, margin=9) -> bool:
        return (not any(inside(point, lake) for lake in water)
                and not any(near_line(point, l, margin) for l in lines)
                and not any(math.dist(point, c) < r for c, r in clearings))

    parts = []
    # Faint grass so the open country reads as land.
    marks = []
    for _ in range(360):
        p = (rng.uniform(40, W - 40), rng.uniform(60, H - 60))
        if clear(p, 12) and not any(inside(p, poly) for poly in FORESTS):
            x, y = p
            marks.append(f"M{x:.1f},{y:.1f} l-2,-4 M{x + 2:.1f},{y:.1f} l0,-5 M{x + 4:.1f},{y:.1f} l2,-4")
    parts.append(f'<path d="{" ".join(marks)}" fill="none" stroke="#3b2a1a" stroke-opacity="0.45" stroke-width="0.55"/>')

    parts.append(draw_water(rng))
    parts.append(draw_roads())

    # Mountains, back to front.
    peaks = []
    for (cx, cy), radius, count, size in MOUNTAINS:
        for _ in range(count):
            a, r = rng.uniform(0, math.tau), radius * math.sqrt(rng.random())
            p = (cx + r * math.cos(a), cy + r * math.sin(a) * 0.55)
            if 8 < p[0] < W - 8 and 18 < p[1] < H - 8 and clear(p, 16):
                peaks.append((p, size * rng.uniform(0.7, 1.15)))
    peaks.sort(key=lambda pk: pk[0][1])
    parts.append("".join(mountain(rng, x, y, s) for (x, y), s in peaks))

    # Forests: trees on a jittered grid, drawn back to front.
    trees = []
    for poly in FORESTS:
        xs, ys = [x for x, _ in poly], [y for _, y in poly]
        y = min(ys)
        while y < max(ys):
            x = min(xs) + rng.uniform(0, 8)
            while x < max(xs):
                p = (x + rng.uniform(-2.5, 2.5), y + rng.uniform(-2.5, 2.5))
                if inside(p, poly) and clear(p) and not any(math.dist(p, pk) < s for pk, s in peaks):
                    trees.append(p)
                x += rng.uniform(8, 11)
            y += rng.uniform(7, 9)
    trees.sort(key=lambda p: p[1])
    parts.append("".join(tree(rng, x, y) for x, y in trees))

    for text, (x, y), size, angle in LABELS:
        parts.append(f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="middle" font-style="italic" '
                     f'transform="rotate({angle} {x} {y})" fill="{INK}" stroke="{PAPER}" stroke-width="3.5" '
                     f'paint-order="stroke" letter-spacing="0.6">{text}</text>')

    mist_defs, mist = mists(rng)
    parts.append(mist)
    parts.append(f'<g fill="{INK}" stroke="{PAPER}" stroke-width="5" paint-order="stroke">'
                 f'<text x="60" y="72" font-size="46" letter-spacing="2">Barovia</text></g>')
    parts.append(compass(930, 662, 32))
    # Scale: five hours on foot, an hour to each band.
    scale = [f'<g stroke="{INK}" stroke-width="0.8"><path d="M60,700 h{5 * HOUR}" fill="none"/>']
    for i in range(5):
        scale.append(f'<rect x="{60 + i * HOUR}" y="696" width="{HOUR}" height="5" fill="{INK if i % 2 == 0 else PAPER}"/>')
    scale.append(f'</g><text x="{60 + 2.5 * HOUR}" y="718" font-size="11" text-anchor="middle" fill="{INK}">'
                 f'About 5 hours on foot, roughly</text>')
    parts.append("".join(scale))

    defs = mist_defs
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
        f'font-family="\'Palatino Linotype\', Palatino, \'Book Antiqua\', Georgia, serif">'
        f'<title>Barovia, drawn for the Owlbear Chronicles</title><defs>{defs}</defs>'
        + "".join(parts)
        + f'<rect x="8" y="8" width="{W - 16}" height="{H - 16}" fill="none" stroke="{INK}" stroke-width="2"/>'
          f'<rect x="13" y="13" width="{W - 26}" height="{H - 26}" fill="none" stroke="{INK}" stroke-width="0.6"/>'
          "</svg>\n"
    )


# --- the road graph ------------------------------------------------------------------------------



def road_graph() -> dict[Point, dict[Point, float]]:
    """Every road and track vertex, joined to its neighbours along the road."""
    graph: dict[Point, dict[Point, float]] = {}
    for pts in list(ROADS.values()) + list(TRACKS.values()):
        for a, b in zip(pts, pts[1:]):
            d = math.dist(a, b)
            graph.setdefault(a, {})[b] = d
            graph.setdefault(b, {})[a] = d
    return graph


def nearest_vertex(graph, x: float, y: float, within: float = 30) -> Point | None:
    best = min(graph, key=lambda v: math.dist(v, (x, y)), default=None)
    return best if best is not None and math.dist(best, (x, y)) <= within else None


def route(graph, start: Point, end: Point) -> list[Point] | None:
    """Shortest path along the roads (Dijkstra), as the list of vertices walked."""
    queue, seen, came = [(0.0, start)], {start: 0.0}, {}
    while queue:
        dist, here = heapq.heappop(queue)
        if here == end:
            path = [end]
            while path[-1] in came:
                path.append(came[path[-1]])
            return path[::-1]
        if dist > seen[here]:
            continue
        for there, step in graph[here].items():
            if dist + step < seen.get(there, math.inf):
                seen[there] = dist + step
                came[there] = here
                heapq.heappush(queue, (dist + step, there))
    return None


# --- sprites -------------------------------------------------------------------------------------

@dataclass
class Sprite:
    """A hand-drawn picture of a place, laid on the map over the base (data/map.yaml `sprites`)."""
    name: str
    image: str      # file stem in static/images/map/sprites/ (.webp)
    x: float        # centre of the picture, in the map's drawing space
    y: float
    width: float
    height: float   # from the image's own shape
    place: str | None = None  # the place it shows (a place slug): the picture links there

    @property
    def box(self) -> tuple[float, float, float, float]:
        return (round(self.x - self.width / 2, 1), round(self.y - self.height / 2, 1),
                round(self.width, 1), round(self.height, 1))


def load_sprites(path: Path, sprite_dir: Path) -> list[Sprite]:
    if not path.exists():
        return []
    from PIL import Image

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out = []
    for name, spec in (data.get("sprites") or {}).items():
        file = sprite_dir / f"{spec['image']}.webp"
        if not file.exists():
            raise ValueError(f"{path.name}: sprite {name}: no sprite image {file.name}")
        with Image.open(file) as im:
            iw, ih = im.size
        x, y = spec["xy"]
        width = float(spec["width"])
        place = spec.get("place", name)   # by default the sprite's name is its place; `place: null` for none
        out.append(Sprite(str(name), str(spec["image"]), float(x), float(y), width, round(width * ih / iw, 1),
                          str(place) if place else None))
    return out


# --- places and the trail -----------------------------------------------------------------------

@dataclass
class Place:
    slug: str
    title: str
    x: float
    y: float
    names: list[str]
    anchor: str = "middle"  # where the label sits: above ("middle"), below, to the right ("start"), left ("end")
    offroad: bool = False   # no road leads here; the trail arrives by a dotted line
    label_at: tuple[float, float] | None = None  # put the label here instead (e.g. on a lake)
    sessions: list = field(default_factory=list)  # posts with a stop here, newest first
    near: str | None = None  # spots only: the place this spot belongs with (its card lists sessions here)

    @property
    def path(self) -> str:
        return f"wiki/{self.slug}/"

    @property
    def label_xy(self) -> tuple[float, float]:
        if self.label_at:
            return self.label_at
        if self.anchor == "start":
            return self.x + 10, self.y + 4
        if self.anchor == "end":
            return self.x - 10, self.y + 4
        if self.anchor == "below":
            return self.x, self.y + 17
        return self.x, self.y - 10

    @property
    def text_anchor(self) -> str:
        if self.label_at:
            return "middle"
        return "middle" if self.anchor == "below" else self.anchor


def load_places(path: Path, pages: list[wiki.WikiPage]) -> tuple[dict[str, Place], dict[str, str]]:
    """Places with coordinates, and {wiki slug: place slug} for every page that counts as one."""
    if not path.exists():
        return {}, {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    by_slug = {p.slug: p for p in pages}
    places: dict[str, Place] = {}
    for slug, spec in (data.get("places") or {}).items():
        page = by_slug.get(slug)
        if page is None:
            raise ValueError(f"data/map.yaml: no wiki page {slug!r}")
        x, y = spec["xy"]
        anchor = str(spec.get("anchor") or "middle")
        if anchor not in ("middle", "below", "start", "end"):
            raise ValueError(f"data/map.yaml: {slug}: anchor must be middle, below, start or end")
        places[slug] = Place(slug, str(spec.get("label") or page.title), float(x), float(y),
                             [str(n) for n in spec.get("names") or page.names], anchor, bool(spec.get("offroad")),
                             tuple(float(v) for v in spec["label_at"]) if spec.get("label_at") else None)
    parent = {slug: slug for slug in places}
    for slug, target in (data.get("within") or {}).items():
        if target not in places:
            raise ValueError(f"data/map.yaml: {slug!r} is within unknown place {target!r}")
        if slug in by_slug:
            parent[slug] = target
    return places, parent


def load_landmarks(path: Path, pages: list[wiki.WikiPage], places: dict[str, Place]) -> dict[str, Place]:
    """Landmarks from data/map.yaml `landmarks`: wiki pages for things drawn on the map that are not
    places to stop (a river, a wood, a mountain range, a lone tree). Only the page's own map shows one,
    zoomed in with a red dot and its name; the map page has no pin, label or card for it."""
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    by_slug = {p.slug: p for p in pages}
    marks: dict[str, Place] = {}
    for slug, spec in (data.get("landmarks") or {}).items():
        if slug not in by_slug:
            raise ValueError(f"data/map.yaml: landmark {slug!r} has no wiki page")
        if slug in places:
            raise ValueError(f"data/map.yaml: landmark {slug!r} is already a place")
        x, y = spec["xy"]
        marks[slug] = Place(slug, str(spec.get("label") or by_slug[slug].title), float(x), float(y), [],
                            str(spec.get("anchor") or "middle"))
    return marks


def load_spots(path: Path, places: dict[str, Place]) -> dict[str, Place]:
    """Spots from data/map.yaml `spots`: points on the roads (or off them) that are not places.

    A spot has no wiki page, pin, label or card. A session's trail can pass through one, and its
    marker can sit at one, so the numbers show where the main action was, such as a bridge or a
    stretch of road (see load_visits).
    """
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    spots: dict[str, Place] = {}
    for slug, spec in (data.get("spots") or {}).items():
        if slug in places:
            raise ValueError(f"data/map.yaml: spot {slug!r} is already a place")
        near = spec.get("near")
        if near is not None and near not in places:
            raise ValueError(f"data/map.yaml: spot {slug!r} is near unknown place {near!r}")
        x, y = spec["xy"]
        spots[slug] = Place(slug, str(spec.get("label") or slug), float(x), float(y), [],
                            offroad=bool(spec.get("offroad")), near=near)
    return spots


class Stops(list):
    """A session's stops in order (place or spot slugs), and the one its marker sits at (None: the last)."""

    def __init__(self, slugs=(), marker: str | None = None):
        super().__init__(slugs)
        self.marker = marker


def stops(text: str, places: dict[str, Place], parent: dict[str, str], pages: list[wiki.WikiPage]) -> list[str]:
    """Mapped places in a post's plain text, in the order first mentioned, repeats collapsed."""
    found: list[tuple[int, str]] = []
    for page in pages:
        place = parent.get(page.slug)
        if place is None:
            continue
        names = places[place].names if page.slug == place else page.names
        for name in names:
            m = re.search(rf"(?<!\w){wiki.name_pattern(wiki.fold(name))}(?!\w)", text)
            if m:
                found.append((m.start(), place))
    found.sort()
    order: list[str] = []
    for _, place in found:
        if place not in order:
            order.append(place)
    return order


def load_visits(path: Path, places: dict[str, Place], spots: dict[str, Place] | None = None) -> dict[str, Stops]:
    """{post file stem: Stops}: where the party actually went each session (data/trail.yaml).

    Mentions are not visits: a session can talk about the castle all night without going there.
    The visit list is written by reading each post (today by Claude, later by the same step that
    writes the post) and reviewed like any other content. An entry is a list of places, or
    {stops: [...], marker: slug} to put the session's number where its main action was instead of
    where it ended; stops may name spots as well as places.
    """
    if not path.exists():
        return {}
    spots = spots or {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    visits = {}
    for stem, entry in (data.get("sessions") or {}).items():
        if isinstance(entry, dict):
            slugs, marker = list(entry.get("stops") or []), entry.get("marker")
        else:
            slugs, marker = list(entry or []), None
        unknown = [s for s in slugs if s not in places and s not in spots]
        if unknown:
            raise ValueError(f"{path.name}: {stem}: unknown places {', '.join(unknown)}")
        if marker is not None and marker not in slugs:
            raise ValueError(f"{path.name}: {stem}: marker {marker!r} is not one of its stops")
        visits[str(stem)] = Stops(slugs, marker)
    return visits


def trail(posts: list, places: dict[str, Place], parent: dict[str, str], pages: list[wiki.WikiPage],
          visits: dict[str, list[str]] | None = None, spots: dict[str, Place] | None = None) -> list[dict]:
    """[{post, n, stops, path, segments, marker}] oldest first; also fills each Place.sessions.

    `path` is every stop the trail runs through, spots included; `stops` is just the places, for
    the lists of where the party went.

    A post listed in `visits` uses that list (an empty list means "nowhere on the map"); any other
    post falls back to the places it mentions, in order. n is the session's number among all sessions,
    on the map or not, so the map's numbers match the wiki's session citations.
    """
    visits = visits or {}
    legs = []
    for number, post in enumerate(sorted(posts, key=lambda p: (p.date, p.slug)), 1):
        stem = post.source.stem if post.source else post.slug
        here = visits[stem] if stem in visits else stops(wiki.plain_text(post.html), places, parent, pages)
        if here:
            named = [slug for slug in here if slug in places]
            legs.append({"post": post, "n": number, "stops": named, "path": list(here),
                         "marker_at": getattr(here, "marker", None)})
            for slug in named:
                places[slug].sessions.insert(0, post)
    add_route(legs, {**(spots or {}), **places})
    return legs


def add_route(legs: list[dict], places: dict[str, Place]) -> None:
    """Give each leg its breadcrumbs along the roads, and a numbered marker where it ended (or at
    leg["marker_at"], where its main action was). `places` includes any spots the legs pass.

    leg["segments"] is a list of {"d", "road", "points", "drawn"}: one per hop from the party's
    previous stop, following the road graph by the shortest route. An off-road place is reached by
    a short straight hop, marked off-road, from the road vertex nearest it; a hop between places
    with no road between them at all is drawn straight. Repeat trips over the same stretch of road
    take another lane (LANES) so a well-worn road shows several crumb lines. A crumb line follows
    the road's own drawn curve ("beziers"; "drawn" its corner points), "points" the road under it. Markers for sessions that ended at the same place fan out
    around it.
    """
    graph = road_graph()
    curves = road_curves()
    node = {slug: nearest_vertex(graph, p.x, p.y, math.inf if p.offroad else 30) for slug, p in places.items()}
    worn: dict[tuple[Point, Point], dict[float, int]] = {}
    markers_at: dict[str, int] = {}
    previous = None
    for leg in legs:
        leg["segments"] = []
        for slug in leg.get("path", leg["stops"]):
            if previous and previous != slug:
                pa, pb = places[previous], places[slug]
                a, b = node[previous], node[slug]
                path = route(graph, a, b) if a and b else None
                if path is None:
                    pts = [(pa.x, pa.y), (pb.x, pb.y)]
                    leg["segments"].append({"road": False, "points": pts, "drawn": pts, "d": smooth_path(pts)})
                    previous = slug
                    continue
                if pa.offroad:
                    pts = [(pa.x, pa.y), a]
                    leg["segments"].append({"road": False, "points": pts, "drawn": pts, "d": smooth_path(pts)})
                if len(path) > 1:
                    beziers = follow(path, lanes(path, worn), curves)
                    drawn = [bez[0] for bez in beziers] + [beziers[-1][3]]
                    leg["segments"].append({"road": True, "points": path, "drawn": drawn, "beziers": beziers,
                                            "d": bezier_path(beziers)})
                if pb.offroad:
                    pts = [b, (pb.x, pb.y)]
                    leg["segments"].append({"road": False, "points": pts, "drawn": pts, "d": smooth_path(pts)})
            previous = slug
        end = places[leg.get("marker_at") or leg.get("path", leg["stops"])[-1]]
        k = markers_at.get(end.slug, 0)
        markers_at[end.slug] = k + 1
        angle = math.radians(k * 137.5 + 100)
        r = 11 + 4.2 * math.sqrt(k)
        leg["marker"] = (round(end.x + r * math.cos(angle), 1), round(end.y + r * math.sin(angle), 1))


PASS_BY = 20  # map units: a trail this close to a place passed it (Old Bonegrinder sits 16 off the road)
# How a session relates to a place, strongest first; a place lists each session once, by the first that fits.
RELATIONS = ("here", "ended", "stop", "near", "from", "past")


def _distance_to_segment(p: Point, a: Point, b: Point) -> float:
    (px, py), (ax, ay), (bx, by) = p, a, b
    dx, dy = bx - ax, by - ay
    t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.dist(p, (ax + t * dx, ay + t * dy))


def place_sessions(legs: list[dict], places: dict[str, Place], spots: dict[str, Place] | None = None,
                   reach: float = PASS_BY) -> dict[str, list[tuple[dict, str, str | None]]]:
    """{place slug: [(leg, relation, spot label or None)]} oldest first: every session tied to a place.

    Chris (2026-11-01): a place's card should list more than the session whose number sits there.
    Relations: "here" (the session's number sits at this place), "ended" or "stop" (a listed stop
    without the number), "near" (a stop at a spot that is `near` this place; the label says which),
    "from" (the session set out from here, where the one before it ended), "past" (its crumbs pass
    within `reach` of the place). Call after trail(), which draws the segments.
    """
    spots = spots or {}
    related: dict[str, list[tuple[dict, str, str | None]]] = {}
    previous = None
    for leg in legs:
        path = list(leg.get("path", leg.get("stops", [])))
        marker = leg.get("marker_at") or (path[-1] if path else None)
        found: dict[str, tuple[str, str | None]] = {}

        def note(slug, kind, extra=None):
            if slug in places and (slug not in found or RELATIONS.index(kind) < RELATIONS.index(found[slug][0])):
                found[slug] = (kind, extra)

        if marker:
            note(marker, "here")
        for i, slug in enumerate(path):
            if i == len(path) - 1:
                note(slug, "ended")
            elif i > 0 or slug != previous:
                note(slug, "stop")
            else:
                note(slug, "from")
            spot = spots.get(slug)
            if spot is not None and spot.near:
                note(spot.near, "near", spot.title)
        if previous and (not path or path[0] != previous):
            note(previous, "from")
        pairs = [(a, b) for seg in leg.get("segments", []) for a, b in zip(seg["points"], seg["points"][1:])]
        if pairs:
            for slug, place in places.items():
                if slug not in found and min(_distance_to_segment((place.x, place.y), a, b) for a, b in pairs) < reach:
                    note(slug, "past")
        for slug, (kind, extra) in found.items():
            related.setdefault(slug, []).append((leg, kind, extra))
        if path:
            previous = path[-1]
    return related


def lanes(path: list[Point], worn: dict) -> list[float]:
    """The lane (a LANES value; + and - are the two sides of travel) for each edge of a trip along `path`.

    `worn` counts, for each edge, the trips in each lane, kept on the edge's own fixed side so trips
    in either direction agree on which side is which; it is updated. Each edge takes its least-used
    lane, and among equals keeps the lane it was in, so a trip changes lane only where it must.
    """
    out, current = [], LANES[0]
    for a, b in zip(path, path[1:]):
        key = (a, b) if (a, b) < (b, a) else (b, a)
        side = 1 if key == (a, b) else -1
        used = worn.setdefault(key, {})
        order = [current] + [lane for lane in LANES if lane != current]
        current = min(order, key=lambda lane: (used.get(lane * side, 0), order.index(lane)))
        used[current * side] = used.get(current * side, 0) + 1
        out.append(current)
    return out


TOUCH = 4.0      # drawn ways closer than this, centre to centre, read as meeting (road ink is 4.8 wide)
JUNCTION = 8.0   # right by a point two ways share they may run close: that is where they meet;
#                  much wider and a trail that leaves a junction along the road goes unflagged


def ways_touching(ways: dict[str, list[Point]]) -> list[tuple[str, str, Point]]:
    """Pairs of roads or trails whose drawn curves meet anywhere but at a point they share.

    Chris (2026-11-03): the dotted trail past Tser Pool was drawn across the loop road, so on the map
    they seemed to cross where the official map has them apart. Ways may meet only at a junction,
    a vertex both lines list. Returns (way, other way, where), one entry per pair, closest spot."""
    drawn = {name: [p for b in curves_of(pts) for p in bezier_points(b)] for name, pts in ways.items()}
    names = list(ways)
    found = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            shared = set(ways[a]) & set(ways[b])

            def free(points):
                return [p for p in points if all(math.dist(p, j) >= JUNCTION for j in shared)]

            best = None
            for p in free(drawn[a]):
                for q in free(drawn[b]):
                    d = math.dist(p, q)
                    if d < TOUCH and (best is None or d < best[0]):
                        best = (d, ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2))
            if best:
                found.append((a, b, best[1]))
    return found


def road_curves() -> dict[tuple[Point, Point], Bezier]:
    """The drawn curve of every road and track edge, by (from, to), both ways round."""
    out = {}
    for pts in list(ROADS.values()) + list(TRACKS.values()):
        for a, c1, c2, b in curves_of(pts):
            out[(a, b)] = (a, c1, c2, b)
            out[(b, a)] = (b, c2, c1, a)
    return out


def _unit(dx: float, dy: float) -> tuple[float, float]:
    length = math.hypot(dx, dy)
    return (dx / length, dy / length) if length else (0.0, 0.0)


def follow(path: list[Point], shifts: list[float], curves: dict) -> list[Bezier]:
    """The road's own drawn curve along `path`, moved sideways by shifts[i] along its i-th edge.

    Chris (2026-11-02): crumbs drawn as their own curve through the road's corner points bent
    differently from the road wherever it met another road or turned, drifting up to 3.6 units off
    it. So each crumb edge is the road's drawn curve for that edge with every point moved the same
    way at each end: along the curve's normal there (the mean of the two edges' directions at a
    corner, so the line stays joined), by the mean of the two edges' lanes.
    """
    beziers = [curves[e] for e in zip(path, path[1:])]
    n = len(beziers)
    moves = []
    for i in range(n + 1):
        into = _unit(beziers[i - 1][3][0] - beziers[i - 1][2][0], beziers[i - 1][3][1] - beziers[i - 1][2][1]) if i else None
        out_ = _unit(beziers[i][1][0] - beziers[i][0][0], beziers[i][1][1] - beziers[i][0][1]) if i < n else None
        ways = [t for t in (into, out_) if t]
        tx, ty = _unit(sum(t[0] for t in ways), sum(t[1] for t in ways))
        if not (tx or ty):  # a dead turn back: keep to the way out
            tx, ty = out_ or into
        lane = sum(shifts[j] for j in (i - 1, i) if 0 <= j < n) / len([j for j in (i - 1, i) if 0 <= j < n])
        moves.append((-ty * lane, tx * lane))
    out = []
    for i, (a, c1, c2, b) in enumerate(beziers):
        (ax, ay), (bx, by) = moves[i], moves[i + 1]
        out.append(((a[0] + ax, a[1] + ay), (c1[0] + ax, c1[1] + ay), (c2[0] + bx, c2[1] + by), (b[0] + bx, b[1] + by)))
    return out


# --- travel times --------------------------------------------------------------------------------

def load_travel(path: Path, places: dict[str, Place]) -> list[dict]:
    """[{from, to, hours, points}] from data/travel-times.yaml, each leg routed along the roads.

    A leg's ends are mapped places or the file's own named junctions; both must sit on a road
    vertex, and the leg follows the roads between them by the shortest route.
    """
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    at = {slug: (p.x, p.y) for slug, p in places.items()}
    at.update({name: (float(x), float(y)) for name, (x, y) in (data.get("junctions") or {}).items()})
    graph = road_graph()
    legs = []
    for item in data.get("legs") or []:
        a, b, hours = item["from"], item["to"], float(item["hours"])
        ends = [at.get(a), at.get(b)]
        if None in ends:
            raise ValueError(f"{path.name}: {a} -> {b}: unknown place or junction")
        if any(end not in graph for end in ends):
            raise ValueError(f"{path.name}: {a} -> {b}: both ends must sit on a road vertex")
        points = route(graph, *ends)
        if points is None:
            raise ValueError(f"{path.name}: {a} -> {b}: no road between them")
        legs.append({"from": a, "to": b, "hours": hours, "points": points, "side": int(item.get("side", 1)),
                     "label": bool(item.get("label", True))})
    return legs


def path_length(points: list[Point]) -> float:
    return sum(math.dist(a, b) for a, b in zip(points, points[1:]))
