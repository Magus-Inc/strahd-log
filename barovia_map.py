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
from dataclasses import dataclass, field
from pathlib import Path

import yaml

import wiki

W, H = 1000, 750
# About how much road an hour on foot covers, going by the hours the official map marks on its
# roads (the median over data/travel-times.yaml). It sets the scale bar.
HOUR = 37
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

# Roads, as polylines. A vertex shared by two roads is a junction, and every place on the map
# sits on a vertex, so the roads double as the graph the trail is routed over. Tracks are drawn
# dotted but are routed over like roads. Where the roads run and where they meet follows the
# official map of Barovia; the hours in data/travel-times.yaml only set the scale bar.
ROADS = {
    "Old Svalich Road (east)": [(998, 390), (960, 394), (930, 398)],
    "Manor lane": [(960, 394), (964, 370), (968, 345)],
    "Gates to the village": [(930, 398), (880, 418), (830, 436), (780, 450)],
    "Village to the Ivlis crossroads": [(780, 450), (745, 480), (712, 520), (680, 555)],
    "The loop past Tser Falls": [(680, 555), (640, 535), (600, 515), (576, 485), (582, 445), (600, 405),
                                 (610, 360)],
    "Road to the castle": [(610, 360), (645, 368), (680, 382), (700, 392), (720, 398)],
    "Old Svalich Road (the hairpin)": [(610, 360), (585, 335), (560, 315), (520, 312), (488, 308), (500, 284),
                                       (526, 262), (550, 248)],
    "Old Svalich Road (the lake shore)": [(550, 248), (510, 252), (465, 256), (420, 262), (400, 268),
                                          (380, 270), (350, 278)],
    "Vallaki lane": [(400, 268), (400, 250)],
    # From the Luna River crossroads (P) the Old Svalich Road bends south-west past the fork to
    # Argynvostholt, then north-west to the Raven River crossroads (R); there is no straight road
    # between the two crossroads.
    "Old Svalich Road (P to R)": [(350, 278), (322, 298), (292, 309), (263, 307), (240, 290), (220, 262)],
    "Old Svalich Road (west)": [(220, 262), (195, 256), (160, 244), (120, 232), (60, 222), (2, 215)],
    "Bonegrinder lane": [(488, 308), (474, 300)],
    "Abbey road": [(120, 232), (125, 220), (133, 208)],
    "Argynvostholt road": [(263, 307), (292, 330), (318, 352), (330, 375)],
    "Road to Tsolenka Pass": [(220, 262), (232, 300), (226, 345), (205, 395), (186, 440), (178, 490), (198, 535),
                              (240, 578)],
    "Vineyard road": [(195, 256), (184, 292), (165, 322), (150, 340)],
    "Amber Temple road": [(240, 578), (288, 614), (330, 648), (352, 672), (362, 705), (366, 748)],
}
TRACKS = {
    # Down the west bank of the Luna River to Berez: the trail keeps to the bank, never the water.
    "Berez trail": [(350, 278), (340, 310), (345, 350), (342, 400), (330, 450)],
    "Lake Baratok trail": [(350, 278), (310, 250), (276, 232), (242, 225)],
    "Tower of Kazan spur": [(242, 225), (258, 214), (250, 202)],
    # Up from the abbey into the hills on the west side of Lake Baratok, to the werewolf den. The
    # official map shows no road there; this is a track, drawn dotted.
    "Werewolf den trail": [(133, 208), (150, 196), (170, 186), (192, 172)],
    "Lake Baratok to the Raven River crossroads": [(242, 225), (231, 244), (220, 262)],
    "Wizard of Wines trail": [(150, 340), (130, 352), (110, 360)],
    "Yester Hill trail": [(150, 340), (130, 400), (100, 452), (70, 488)],
    # The trail climbs about an hour and a half up into the peaks to the Amber Temple.
    "Amber Temple trail": [(352, 672), (366, 662), (362, 648), (380, 640)],
    # The Vistani camp sits on dry land just south of Tser Pool.
    "Tser Pool trail (to the camp)": [(680, 555), (690, 530)],
}
# Drawn like tracks but never walked by the trail: the party never took them.
UNUSED_TRACKS = {
    "Tser Pool trail (past the pool)": [(690, 530), (655, 515), (628, 485), (606, 448), (600, 405)],
}

LAKES = {
    "Lake Zarovich": [(322, 195), (335, 160), (370, 130), (420, 115), (480, 115), (530, 135), (550, 170),
                      (540, 205), (500, 222), (450, 230), (400, 234), (355, 224)],
    "Lake Baratok": [(200, 152), (222, 140), (246, 144), (258, 160), (256, 184), (244, 198), (222, 203), (204, 192), (197, 172)],
    "Luna Lake": [(180, 588), (200, 576), (226, 578), (232, 596), (218, 612), (190, 612)],
    "Tser Pool": [(676, 455), (692, 450), (702, 466), (700, 494), (690, 508), (678, 496), (674, 478)],
    "": [(350, 462), (366, 456), (378, 466), (372, 480), (356, 480)],  # the marsh by Berez
    # Two ponds in the hills along the branch of the Luna that feeds Tser Falls, as on the official
    # map and the old Obsidian Portal map.
    "Hill pond (west)": [(418, 372), (432, 364), (446, 370), (444, 386), (428, 390), (416, 384)],
    "Hill pond (east)": [(478, 380), (492, 372), (504, 382), (502, 410), (494, 428), (484, 418), (480, 398)],
    "Falls pond": [(550, 368), (566, 360), (582, 366), (580, 378), (562, 382)],
}

RIVERS = {
    "Raven River": [(212, 192), (196, 224), (178, 262), (150, 272), (100, 272), (50, 268), (2, 265)],
    "Luna River": [(338, 224), (352, 262), (362, 300), (366, 350), (360, 400), (345, 445), (330, 500),
                   (290, 560), (232, 588)],
    "Luna River (west)": [(180, 596), (130, 560), (70, 530), (2, 525)],
    "Ivlis River": [(700, 494), (740, 506), (780, 490), (840, 496), (910, 500), (998, 505)],
    # The water: Lake Zarovich drains south as the Luna; a branch of the Luna runs east through
    # the hill ponds and over Tser Falls into Tser Pool, which drains east as the Ivlis.
    "Tser Falls": [(366, 350), (400, 352), (432, 356), (470, 362), (520, 368), (566, 372), (582, 400),
                   (600, 405)],
    "To the west hill pond": [(432, 356), (431, 370)],
    "To the east hill pond": [(470, 362), (490, 382)],
    "Below the falls": [(600, 405), (630, 440), (674, 470)],
    "Northern streams": [(392, 116), (388, 80), (380, 45), (378, 14)],
    "Northern streams 2": [(500, 116), (510, 80), (522, 45), (530, 14)],
}

FORESTS = [
    [(150, 14), (700, 14), (700, 100), (560, 112), (420, 104), (300, 112), (150, 100)],    # the north band
    [(14, 75), (250, 75), (250, 140), (260, 300), (150, 300), (14, 300)],                 # around Krezk
    # Old Bonegrinder's wood: the reason the road climbs north round the hairpin instead of
    # cutting straight across to Vallaki.
    [(428, 270), (476, 266), (492, 284), (470, 316), (432, 322), (418, 296)],
    [(250, 290), (330, 296), (440, 300), (450, 410), (360, 412), (260, 400)],             # south of Vallaki
    [(552, 420), (650, 420), (660, 560), (640, 712), (560, 712), (540, 560)],             # the ridge below the falls
    [(750, 38), (986, 38), (986, 338), (900, 370), (800, 400), (750, 300)],               # north of the village
    [(650, 580), (986, 562), (986, 736), (650, 736)],                                     # southeast
    [(14, 600), (180, 630), (300, 650), (300, 736), (280, 736), (280, 680), (14, 680)],   # southwest
]

MOUNTAINS = [  # (centre, radius, count, size)
    ((520, 610), 150, 60, 26),   # the southern massif
    ((440, 688), 60, 14, 32),    # Mount Ghakis
    ((250, 480), 95, 28, 20),    # the western mountains the Tsolenka road climbs through
    ((630, 270), 110, 26, 11),   # the highlands between Old Bonegrinder and the castle
    ((524, 286), 30, 14, 15),    # the hill the road climbs round, north of Old Bonegrinder
    ((700, 26), 60, 10, 22),     # Mount Baratok
    ((394, 632), 34, 10, 16),    # the peaks the Amber Temple trail climbs into
]

LABELS = [  # (text, (x, y), size, angle)
    ("Lake Zarovich", (426, 188), 16, 0),
    ("Svalich Woods", (560, 60), 15, -4),
    ("Svalich Woods", (870, 200), 15, 62),
    ("Svalich Woods", (850, 660), 15, -8),
    ("Svalich Woods", (90, 160), 13, 0),
    ("Luna River", (392, 330), 11, 84),
    ("Raven River", (70, 252), 10, 0),
    ("Ivlis River", (850, 516), 11, 0),
    ("Mount Ghakis", (440, 714), 15, 0),
    ("Old Svalich Road", (872, 440), 10, -21),
    ("Tser Falls", (560, 420), 10, 0),
    ("Gates of Barovia", (597, 318), 8.5, 0),
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


def draw_roads() -> str:
    """Dirt roads with an ink edge and faint wheel ruts, every edge before any surface so junctions
    join cleanly; tracks are dotted ink."""
    roads = [smooth_path(p) for p in ROADS.values()]
    casing = "".join(f'<path d="{d}" fill="none" stroke="{INK}" stroke-opacity="0.85" stroke-width="4.8" '
                     f'stroke-linecap="round" stroke-linejoin="round"/>' for d in roads)
    surface = "".join(f'<path d="{d}" fill="none" stroke="{ROAD}" stroke-width="3" stroke-linecap="round" '
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
    stop, following the road graph by the shortest route. An off-road place is reached by a short
    straight hop, marked off-road, from the road vertex nearest it; a hop between places with no
    road between them at all is drawn straight. Repeat trips over the same road are nudged a
    little to the side so a well-worn road shows several crumb lines. Markers for sessions that
    ended at the same place fan out around it.
    """
    graph = road_graph()
    node = {slug: nearest_vertex(graph, p.x, p.y, math.inf if p.offroad else 30) for slug, p in places.items()}
    worn: dict[tuple[Point, Point], int] = {}
    markers_at: dict[str, int] = {}
    previous = None
    for leg in legs:
        leg["segments"] = []
        for slug in leg["stops"]:
            if previous and previous != slug:
                pa, pb = places[previous], places[slug]
                a, b = node[previous], node[slug]
                path = route(graph, a, b) if a and b else None
                if path is None:
                    pts = [(pa.x, pa.y), (pb.x, pb.y)]
                    leg["segments"].append({"road": False, "points": pts, "d": smooth_path(pts)})
                    previous = slug
                    continue
                if pa.offroad:
                    pts = [(pa.x, pa.y), a]
                    leg["segments"].append({"road": False, "points": pts, "d": smooth_path(pts)})
                if len(path) > 1:
                    n = max(worn.get(tuple(sorted(e)), 0) for e in zip(path, path[1:]))
                    for e in zip(path, path[1:]):
                        worn[tuple(sorted(e))] = worn.get(tuple(sorted(e)), 0) + 1
                    shift = ((n % 4) - 1.5) * 1.3
                    leg["segments"].append({"road": True, "points": path, "d": smooth_path(offset(path, shift))})
                if pb.offroad:
                    pts = [b, (pb.x, pb.y)]
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
