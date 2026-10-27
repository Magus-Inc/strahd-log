"""Our own map of Barovia, and the party's breadcrumb trail along its roads.

draw_base() returns the map as standalone SVG in the style of a hand-coloured regional map: light
parchment, green conifer woods, snow-capped grey mountains, blue lakes and rivers, tan roads and
mist at the edges. It is generated from a fixed seed, so every build draws the same map. The
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
from dataclasses import dataclass, field
from pathlib import Path

import yaml

import wiki

W, H = 1000, 750
SEED = 1987

INK = "#3b2a1a"        # outlines and lettering
PAPER = "#ece2c8"
TREE = "#3e5b3a"
TREE_DARK = "#26382a"
WATER = "#86a9c4"
WATER_EDGE = "#3f6684"
ROAD = "#a8875a"
SNOW = "#f4f3ef"
ROCK = "#8f969b"

# --- geography (drawing space 1000 x 750, x east, y south) -------------------------------------

# Roads, as polylines. A vertex shared by two roads is a junction, and every place on the map
# sits on a vertex, so the roads double as the graph the trail is routed over. Tracks are drawn
# dotted but are routed over like roads. The layout and the relative lengths follow the travel
# times in data/travel-times.yaml: about HOUR drawing units of road per hour on foot.
HOUR = 26

ROADS = {
    "Old Svalich Road (east)": [(998, 388), (950, 394), (905, 398), (850, 410)],
    "Manor lane": [(905, 398), (912, 372), (925, 350)],
    "Gates to the village": [(850, 410), (808, 428), (765, 440)],
    "Village to the Ivlis crossroads": [(765, 440), (722, 452), (678, 462)],
    "Road south from the crossroads": [(678, 462), (688, 510), (694, 556)],
    "Ivlis crossroads to Tser Pool": [(678, 462), (640, 462), (602, 456)],
    "The switchback past Tser Falls": [(602, 456), (560, 452), (528, 432), (507, 398), (505, 358), (518, 322)],
    "Road to the castle": [(518, 322), (548, 316), (562, 300), (592, 286)],
    "Old Svalich Road (Vallaki)": [(518, 322), (480, 306), (445, 300), (405, 276), (365, 262), (325, 265),
                                   (290, 252), (277, 250), (264, 252), (230, 262)],
    "Old Svalich Road (west)": [(230, 262), (192, 258), (168, 248), (136, 238), (105, 232), (55, 224), (2, 218)],
    "Abbey road": [(105, 232), (110, 220), (118, 208)],
    "Argynvostholt road": [(230, 262), (248, 300), (258, 340), (262, 375)],
    "Road south": [(230, 262), (214, 298), (205, 335), (215, 395), (232, 455), (240, 515), (262, 590)],
    "Amber Temple road": [(262, 590), (300, 625), (345, 640)],
    "Vineyard road": [(205, 335), (185, 352), (165, 368)],
    "Yester Hill road": [(168, 248), (158, 280), (150, 310), (128, 345), (105, 385)],
}
TRACKS = {
    "Lake Baratok trail": [(230, 262), (212, 232), (198, 206), (190, 182)],
    "Den track": [(150, 310), (126, 320)],
    "Berez track": [(262, 375), (280, 420), (300, 455)],
}

LAKES = {
    "Lake Zarovich": [(262, 222), (270, 196), (300, 172), (350, 158), (410, 152), (465, 156), (510, 170),
                      (525, 195), (505, 218), (455, 232), (400, 238), (345, 240), (300, 236)],
    "Lake Baratok": [(135, 172), (150, 160), (172, 162), (184, 176), (182, 196), (168, 208), (148, 206),
                     (136, 194)],
    "Luna Lake": [(165, 590), (190, 578), (222, 580), (236, 594), (225, 610), (195, 616), (170, 608)],
    "Tser Pool": [(608, 476), (624, 470), (644, 478), (646, 494), (628, 502), (610, 494)],
}

RIVERS = {
    "Luna River": [(262, 224), (250, 248), (246, 278), (262, 302), (272, 340), (278, 380), (292, 422),
                   (304, 470), (290, 530), (240, 580), (228, 588)],
    "Luna River (west)": [(165, 596), (120, 590), (70, 600), (2, 596)],
    "Raven River": [(170, 205), (196, 230), (222, 252), (240, 272)],
    "Ivlis River": [(646, 486), (678, 474), (722, 478), (765, 466), (810, 468), (860, 452), (910, 456),
                    (998, 446)],
    "Tser Falls": [(430, 355), (470, 375), (500, 398)],
    "Below the falls": [(500, 398), (515, 440), (548, 468), (590, 482), (612, 484)],
    "Northern streams": [(392, 154), (388, 110), (380, 70), (378, 22)],
    "Northern streams 2": [(480, 154), (500, 110), (520, 60), (530, 22)],
}

FORESTS = [
    [(236, 70), (330, 58), (420, 86), (560, 70), (650, 80), (660, 134), (580, 140), (470, 136), (330, 136),
     (250, 126)],
    [(330, 284), (440, 318), (470, 360), (440, 420), (360, 420), (318, 380)],
    [(30, 280), (120, 272), (140, 300), (110, 420), (60, 440), (26, 380)],
    [(40, 470), (150, 450), (200, 520), (160, 560), (60, 560)],
    [(110, 630), (230, 640), (300, 690), (180, 712), (96, 680)],
    [(640, 170), (780, 140), (900, 170), (972, 260), (960, 370), (880, 385), (800, 400), (700, 380), (620, 330)],
    [(700, 500), (830, 510), (968, 500), (966, 660), (800, 664), (708, 614)],
    [(530, 340), (590, 330), (640, 400), (600, 430), (540, 410)],
    [(26, 96), (130, 104), (150, 150), (120, 160), (40, 200)],
    [(480, 470), (600, 500), (640, 600), (560, 640), (470, 560)],
]

MOUNTAINS = [  # (centre, radius, count, size)
    ((450, 650), 120, 50, 28),   # Mount Ghakis and the Balinoks
    ((110, 120), 46, 12, 20),    # Mount Baratok
    ((830, 52), 120, 24, 22),
    ((420, 30), 260, 26, 16),
    ((380, 480), 46, 10, 15),
    ((300, 560), 40, 10, 18),    # Tsolenka Pass
]

LABELS = [  # (text, (x, y), size, angle)
    ("Lake Zarovich", (398, 200), 16, 0),
    ("Svalich Woods", (560, 108), 15, -4),
    ("Svalich Woods", (860, 262), 15, 62),
    ("Svalich Woods", (840, 596), 15, -8),
    ("Svalich Woods", (104, 508), 13, 40),
    ("Luna River", (292, 352), 11, 78),
    ("Ivlis River", (836, 484), 11, -10),
    ("Mount Ghakis", (450, 704), 15, 0),
    ("Old Svalich Road", (952, 414), 10, -4),
    ("Tser Falls", (468, 414), 10, 0),
]


# --- drawing helpers ----------------------------------------------------------------------------

def jitter(rng: random.Random, points, amount=1.4):
    return [(x + rng.uniform(-amount, amount), y + rng.uniform(-amount, amount)) for x, y in points]


def smooth_path(points, closed=False) -> str:
    """Catmull-Rom through the points, as cubic Beziers."""
    pts = list(points)
    if len(pts) < 2:
        return ""
    pts = (pts[-1:] + pts + pts[:2]) if closed else (pts[:1] + pts + pts[-1:])
    d = [f"M{pts[1][0]:.1f},{pts[1][1]:.1f}"]
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d.append(f"C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}")
    return " ".join(d) + (" Z" if closed else "")


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
    """A small conifer: two shades of green, the shadow side darker."""
    h = rng.uniform(9, 13)
    w = h * rng.uniform(0.36, 0.46)
    return (f'<path d="M{x:.1f},{y - h:.1f} L{x - w:.1f},{y:.1f} L{x + w:.1f},{y:.1f} Z" fill="{TREE}"/>'
            f'<path d="M{x:.1f},{y - h:.1f} L{x + w:.1f},{y:.1f} L{x + w * 0.15:.1f},{y:.1f} Z" fill="{TREE_DARK}"/>')


def mountain(rng: random.Random, x: float, y: float, size: float) -> str:
    """A peak lit from the west: snow on the lit face, grey rock in shadow, a snow cap."""
    w = size * rng.uniform(0.8, 1.15)
    h = size * rng.uniform(0.8, 1.15)
    px = x + rng.uniform(-w * 0.12, w * 0.12)
    lit = f"M{x - w:.1f},{y:.1f} L{px:.1f},{y - h:.1f} L{px + w * 0.1:.1f},{y:.1f} Z"
    shade = f"M{px:.1f},{y - h:.1f} L{x + w:.1f},{y:.1f} L{px + w * 0.1:.1f},{y:.1f} Z"
    outline = f"M{x - w:.1f},{y:.1f} L{px:.1f},{y - h:.1f} L{x + w:.1f},{y:.1f}"
    return (f'<path d="{lit}" fill="{SNOW}"/><path d="{shade}" fill="{ROCK}"/>'
            f'<path d="{outline}" fill="none" stroke="{INK}" stroke-width="0.9" stroke-linejoin="round"/>')


def castle(x: float, y: float) -> str:
    """Castle Ravenloft on its crag."""
    stone, dark = "#9aa0a4", "#5d6468"
    return (
        f'<g stroke="{INK}" stroke-width="0.9" stroke-linejoin="round">'
        f'<path d="M{x - 26},{y + 14} q8,-10 16,-12 q10,-4 14,-14 q6,8 16,10 q10,4 12,16 Z" fill="{dark}"/>'
        f'<path d="M{x - 11},{y + 2} v-22 h22 v22 Z" fill="{stone}"/>'
        f'<path d="M{x - 11},{y - 20} l11,-12 l11,12 Z" fill="{dark}"/>'
        f'<path d="M{x - 21},{y + 4} v-16 h7 v16 Z M{x + 14},{y + 4} v-18 h7 v18 Z" fill="{stone}"/>'
        f'<path d="M{x - 21},{y - 12} l3.5,-8 l3.5,8 Z M{x + 14},{y - 14} l3.5,-9 l3.5,9 Z" fill="{dark}"/>'
        f'<path d="M{x - 3},{y + 2} v-7 h6 v7" fill="{INK}"/></g>')


def manor(x: float, y: float) -> str:
    """Durst Manor: a tall townhouse with a pointed roof, out past the gates in the mists."""
    return (f'<g stroke="{INK}" stroke-width="0.8" stroke-linejoin="round">'
            f'<path d="M{x - 8},{y + 2} v-16 h16 v16 Z" fill="#8a7e74"/>'
            f'<path d="M{x - 10},{y - 14} l10,-10 l10,10 Z" fill="#4a3b33"/>'
            f'<path d="M{x - 5},{y - 10} h3 v3 h-3 Z M{x + 2},{y - 10} h3 v3 h-3 Z M{x - 5},{y - 4} h3 v3 h-3 Z '
            f'M{x + 2},{y - 4} h3 v3 h-3 Z" fill="#e9d79b" stroke-width="0.4"/></g>')


def village(rng: random.Random, x: float, y: float, n: int = 5) -> str:
    """A cluster of roofs."""
    out = []
    for _ in range(n):
        hx, hy = x + rng.uniform(-11, 11), y + rng.uniform(-8, 6)
        out.append(f'<path d="M{hx - 3.5:.1f},{hy:.1f} v-4 l3.5,-3.5 l3.5,3.5 v4 Z" fill="#b9634a" '
                   f'stroke="{INK}" stroke-width="0.6"/>')
    return "".join(out)


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

def draw_base(travel: list[dict] | None = None) -> str:
    """The base map; `travel` (load_travel()) adds the hours on foot along each leg of road."""
    rng = random.Random(SEED)
    water = list(LAKES.values())
    lines = list(ROADS.values()) + list(TRACKS.values()) + list(RIVERS.values())

    # Clearings around the buildings, so no tree or peak is drawn over them.
    clearings = [((592, 280), 26), ((925, 342), 20)]

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
    parts.append(f'<path d="{" ".join(marks)}" fill="none" stroke="#9c9a6a" stroke-width="0.7"/>')

    for name, pts in LAKES.items():
        shore = jitter(rng, [q for a, b in zip(pts, pts[1:] + pts[:1])
                             for q in (a, ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2))], 3)
        parts.append(f'<path d="{smooth_path(shore, closed=True)}" fill="{WATER}" stroke="{WATER_EDGE}" stroke-width="1.4"/>')
        cx = sum(x for x, _ in pts) / len(pts)
        cy = sum(y for _, y in pts) / len(pts)
        ring = [(cx + (x - cx) * 0.72, cy + (y - cy) * 0.72) for x, y in shore]
        parts.append(f'<path d="{smooth_path(ring, closed=True)}" fill="none" stroke="#b9d0e0" stroke-width="1" '
                     f'stroke-dasharray="10 6"/>')
    for name, pts in RIVERS.items():
        width = 1.6 if "streams" in name else 2.8
        parts.append(f'<path d="{smooth_path(jitter(rng, pts, 0.8))}" fill="none" stroke="{WATER_EDGE}" '
                     f'stroke-width="{width + 1:.1f}" stroke-linecap="round"/>'
                     f'<path d="{smooth_path(pts)}" fill="none" stroke="{WATER}" stroke-width="{width - 0.8:.1f}" '
                     f'stroke-linecap="round"/>')

    for pts in ROADS.values():
        d = smooth_path(pts)
        parts.append(f'<path d="{d}" fill="none" stroke="#6f5434" stroke-width="4" stroke-linecap="round"/>'
                     f'<path d="{d}" fill="none" stroke="#d8c39a" stroke-width="2.4" stroke-linecap="round"/>')
    for pts in TRACKS.values():
        parts.append(f'<path d="{smooth_path(pts)}" fill="none" stroke="#6f5434" stroke-width="1.6" '
                     f'stroke-dasharray="1 5" stroke-linecap="round"/>')

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

    parts.append(castle(592, 286))
    parts.append(manor(925, 350))
    for x, y in [(765, 440), (277, 250), (105, 232)]:
        parts.append(village(rng, x, y + 12, 6))
    parts.append(f'<path d="M150,374 h12 v10 h-12 Z M164,378 h10 v7 h-10 Z" fill="#8b5a3c" stroke="{INK}" stroke-width="0.6"/>')

    parts.extend(hours_label(leg) for leg in travel or [] if leg["label"])

    for text, (x, y), size, angle in LABELS:
        parts.append(f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="middle" font-style="italic" '
                     f'transform="rotate({angle} {x} {y})" fill="{INK}" stroke="{PAPER}" stroke-width="3.5" '
                     f'paint-order="stroke" letter-spacing="0.6">{text}</text>')

    mist_defs, mist = mists(rng)
    parts.append(mist)
    parts.append(f'<g fill="{INK}" stroke="{PAPER}" stroke-width="5" paint-order="stroke">'
                 f'<text x="60" y="72" font-size="46" letter-spacing="2">Barovia</text></g>')
    parts.append(compass(930, 662, 32))
    # Scale: eight hours on foot, in two-hour steps.
    scale = [f'<g stroke="{INK}" stroke-width="0.8"><path d="M60,700 h{8 * HOUR}" fill="none"/>']
    for i in range(4):
        scale.append(f'<rect x="{60 + i * 2 * HOUR}" y="696" width="{2 * HOUR}" height="5" '
                     f'fill="{INK if i % 2 == 0 else PAPER}"/>')
    scale.append(f'</g><text x="{60 + 4 * HOUR}" y="718" font-size="11" text-anchor="middle" fill="{INK}">'
                 f'Eight hours on foot, more or less</text>')
    parts.append("".join(scale))

    defs = (
        '<radialGradient id="paper" cx="50%" cy="46%" r="75%">'
        f'<stop offset="0" stop-color="{PAPER}"/><stop offset="0.75" stop-color="#e2d4b2"/>'
        '<stop offset="1" stop-color="#c9b48a"/></radialGradient>' + mist_defs
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
        f'font-family="\'Palatino Linotype\', Palatino, \'Book Antiqua\', Georgia, serif">'
        f'<title>Barovia, drawn for the Owlbear Chronicles</title><defs>{defs}</defs>'
        f'<rect width="{W}" height="{H}" fill="url(#paper)"/>'
        + "".join(parts)
        + f'<rect x="8" y="8" width="{W - 16}" height="{H - 16}" fill="none" stroke="{INK}" stroke-width="2"/>'
          f'<rect x="13" y="13" width="{W - 26}" height="{H - 26}" fill="none" stroke="{INK}" stroke-width="0.6"/>'
          "</svg>\n"
    )


# --- the road graph ------------------------------------------------------------------------------

Point = tuple[float, float]


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
    sessions: list = field(default_factory=list)  # posts with a stop here, newest first

    @property
    def path(self) -> str:
        return f"wiki/{self.slug}/"

    @property
    def label_xy(self) -> tuple[float, float]:
        if self.anchor == "start":
            return self.x + 10, self.y + 4
        if self.anchor == "end":
            return self.x - 10, self.y + 4
        if self.anchor == "below":
            return self.x, self.y + 17
        return self.x, self.y - 10

    @property
    def text_anchor(self) -> str:
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
                             [str(n) for n in spec.get("names") or page.names], anchor, bool(spec.get("offroad")))
    parent = {slug: slug for slug in places}
    for slug, target in (data.get("within") or {}).items():
        if target not in places:
            raise ValueError(f"data/map.yaml: {slug!r} is within unknown place {target!r}")
        if slug in by_slug:
            parent[slug] = target
    return places, parent


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


def load_visits(path: Path, places: dict[str, Place]) -> dict[str, list[str]]:
    """{post file stem: [place slugs]}: where the party actually went each session (data/trail.yaml).

    Mentions are not visits: a session can talk about the castle all night without going there.
    The visit list is written by reading each post (today by Claude, later by the same step that
    writes the post) and reviewed like any other content.
    """
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    visits = {}
    for stem, slugs in (data.get("sessions") or {}).items():
        unknown = [s for s in slugs or [] if s not in places]
        if unknown:
            raise ValueError(f"{path.name}: {stem}: unknown places {', '.join(unknown)}")
        visits[str(stem)] = list(slugs or [])
    return visits


def trail(posts: list, places: dict[str, Place], parent: dict[str, str], pages: list[wiki.WikiPage],
          visits: dict[str, list[str]] | None = None) -> list[dict]:
    """[{post, n, stops, segments, marker}] oldest first; also fills each Place.sessions.

    A post listed in `visits` uses that list (an empty list means "nowhere on the map"); any other
    post falls back to the places it mentions, in order. n numbers the sessions on the map.
    """
    visits = visits or {}
    legs = []
    for post in sorted(posts, key=lambda p: (p.date, p.slug)):
        stem = post.source.stem if post.source else post.slug
        here = visits[stem] if stem in visits else stops(wiki.plain_text(post.html), places, parent, pages)
        if here:
            legs.append({"post": post, "n": len(legs) + 1, "stops": here})
            for slug in here:
                places[slug].sessions.insert(0, post)
    add_route(legs, places)
    return legs


def add_route(legs: list[dict], places: dict[str, Place]) -> None:
    """Give each leg its breadcrumbs along the roads, and a numbered marker where it ended.

    leg["segments"] is a list of {"d", "road", "points"}: one per hop from the party's previous
    stop, following the road graph by the shortest route; a hop with no road between the two
    places is drawn straight and marked off-road. Repeat trips over the same road are nudged a
    little to the side so a well-worn road shows several crumb lines. Markers for sessions that
    ended at the same place fan out around it.
    """
    graph = road_graph()
    node = {slug: None if p.offroad else nearest_vertex(graph, p.x, p.y) for slug, p in places.items()}
    worn: dict[tuple[Point, Point], int] = {}
    markers_at: dict[str, int] = {}
    previous = None
    for leg in legs:
        leg["segments"] = []
        for slug in leg["stops"]:
            if previous and previous != slug:
                a, b = node[previous], node[slug]
                path = route(graph, a, b) if a and b else None
                if path:
                    n = max(worn.get(tuple(sorted(e)), 0) for e in zip(path, path[1:]))
                    for e in zip(path, path[1:]):
                        worn[tuple(sorted(e))] = worn.get(tuple(sorted(e)), 0) + 1
                    shift = ((n % 4) - 1.5) * 1.3
                    leg["segments"].append({"road": True, "points": path, "d": smooth_path(offset(path, shift))})
                else:
                    pa, pb = places[previous], places[slug]
                    pts = [(pa.x, pa.y), (pb.x, pb.y)]
                    leg["segments"].append({"road": False, "points": pts, "d": smooth_path(pts)})
            previous = slug
        end = places[leg["stops"][-1]]
        k = markers_at.get(end.slug, 0)
        markers_at[end.slug] = k + 1
        angle = math.radians(k * 137.5 + 100)
        r = 11 + 4.2 * math.sqrt(k)
        leg["marker"] = (round(end.x + r * math.cos(angle), 1), round(end.y + r * math.sin(angle), 1))


def offset(points: list[Point], by: float) -> list[Point]:
    """The polyline moved sideways by `by` (perpendicular to each vertex's direction of travel)."""
    if not by or len(points) < 2:
        return points
    out = []
    for i, (x, y) in enumerate(points):
        ax, ay = points[max(i - 1, 0)]
        bx, by_ = points[min(i + 1, len(points) - 1)]
        dx, dy = bx - ax, by_ - ay
        length = math.hypot(dx, dy) or 1
        out.append((x - dy / length * by, y + dx / length * by))
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


def hours_text(hours: float) -> str:
    return f"{hours:g} h"


def hours_label(leg: dict) -> str:
    """The leg's hours, small and upright, beside the road halfway along it."""
    points, half = leg["points"], path_length(leg["points"]) / 2
    for a, b in zip(points, points[1:]):
        step = math.dist(a, b)
        if half <= step:
            break
        half -= step
    t = half / (step or 1)
    x, y = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
    dx, dy = (b[0] - a[0]) / (step or 1), (b[1] - a[1]) / (step or 1)
    angle = math.degrees(math.atan2(dy, dx))
    if angle > 90:
        angle -= 180
    elif angle <= -90:
        angle += 180
    nx, ny = -dy, dx  # perpendicular; pick the side above the road (or left of a steep one)
    if ny > 0 or (abs(ny) < 0.35 and nx > 0):
        nx, ny = -nx, -ny
    side = leg.get("side", 1)
    lx, ly = x + nx * 7 * side, y + ny * 7 * side
    if abs(angle) > 55:  # steep road: keep the text level, beside it
        angle, lx, ly = 0, x + nx * 9 * side, y + ny * 9 * side + 3
        anchor = "end" if nx * side < 0 else "start"
    else:
        anchor = "middle"
        ly += 3
    return (f'<text class="hours" data-from="{leg["from"]}" data-to="{leg["to"]}" x="{lx:.1f}" y="{ly:.1f}" '
            f'font-size="8.5" text-anchor="{anchor}" transform="rotate({angle:.0f} {lx:.1f} {ly:.1f})" '
            f'fill="#7a1f1f" stroke="{PAPER}" stroke-width="2.5" paint-order="stroke">{hours_text(leg["hours"])}</text>')
