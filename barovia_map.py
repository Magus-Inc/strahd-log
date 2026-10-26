"""Our own map of Barovia, and the party's trail across it.

draw_base() returns the map as standalone SVG: brown leather, black quill ink, no labels for
places we track (those are drawn as an overlay, so the base stays a clean source map). The art is
generated from a fixed seed, so every build draws the same map. The geography is placed loosely
after the table map; nothing is traced.

Places and the trail come from data/map.yaml and the wiki: see load_places() and trail().
"""

from __future__ import annotations

import math
import random
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

import wiki

W, H = 1000, 750
INK = "#1b120b"
SEED = 1987

# --- geography (drawing space 1000 x 750, x east, y south) -------------------------------------

LAKES = {
    "Lake Zarovich": [(322, 196), (350, 178), (400, 170), (455, 168), (510, 176), (548, 192), (552, 212),
                      (520, 230), (470, 236), (420, 238), (370, 232), (335, 220)],
    "Lake Baratok": [(186, 182), (202, 168), (222, 170), (232, 190), (226, 214), (214, 232), (196, 230),
                     (186, 210)],
    "Luna Lake": [(170, 552), (196, 540), (236, 538), (262, 548), (256, 564), (222, 572), (186, 568)],
    "Tser Pool": [(662, 440), (676, 436), (686, 452), (684, 474), (670, 480), (660, 466)],
    "": [(422, 400), (436, 394), (446, 410), (440, 432), (428, 440), (420, 424)],
}

RIVERS = {
    "Luna River": [(352, 234), (356, 270), (362, 310), (372, 352), (358, 400), (330, 452), (300, 492),
                   (270, 524), (250, 540)],
    "": [(172, 556), (140, 540), (104, 520), (62, 504), (14, 488)],
    "Ivlis River": [(684, 474), (722, 486), (766, 482), (808, 474), (852, 484), (896, 500), (940, 492),
                    (992, 484)],
    "Raven River": [(190, 226), (160, 240), (126, 248), (80, 254), (40, 258), (8, 262)],
    " ": [(582, 414), (612, 422), (640, 424), (664, 444)],
    "  ": [(582, 414), (548, 420), (520, 412), (490, 396), (466, 380)],
}

ROADS = {
    "Old Svalich Road": [(996, 412), (948, 418), (880, 430), (795, 440), (752, 458), (704, 478), (672, 468),
                         (640, 448), (600, 422), (582, 414), (590, 384), (598, 350), (566, 318), (528, 300),
                         (500, 270), (468, 252), (430, 256), (390, 244), (346, 260), (300, 256), (262, 252),
                         (232, 262), (210, 240), (172, 236), (138, 234), (102, 230), (60, 222), (6, 214)],
    "castle": [(598, 350), (632, 346), (664, 356), (692, 358)],
    "argynvostholt": [(346, 260), (334, 300), (326, 342)],
    "tsolenka": [(232, 262), (206, 300), (180, 348), (166, 400), (186, 452), (226, 506), (262, 540),
                 (300, 576), (336, 600)],
    "windmill": [(528, 300), (500, 312)],
}
TRACKS = {  # footpaths, drawn dotted
    "wizard": [(206, 300), (160, 318), (120, 334), (96, 348)],
    "berez": [(326, 372), (316, 410), (308, 436)],
    "yester": [(96, 360), (72, 388), (52, 412)],
}

FORESTS = [
    [(236, 70), (330, 58), (420, 84), (560, 66), (650, 74), (660, 136), (580, 152), (470, 150), (330, 150),
     (250, 140)],
    [(352, 262), (474, 262), (526, 296), (474, 334), (382, 318)],
    [(110, 270), (176, 262), (196, 330), (168, 420), (126, 470), (84, 420), (96, 330)],
    [(56, 470), (148, 436), (226, 520), (176, 534), (96, 540)],
    [(120, 580), (260, 584), (322, 646), (200, 662), (110, 630)],
    [(730, 150), (862, 116), (956, 180), (972, 330), (904, 384), (806, 336), (760, 250)],
    [(694, 492), (830, 516), (964, 520), (962, 650), (800, 652), (700, 610)],
    [(520, 330), (604, 302), (640, 398), (560, 420)],
    [(26, 92), (152, 100), (200, 168), (150, 198), (40, 210)],
    [(590, 470), (650, 500), (640, 600), (580, 640), (560, 540)],
]

MOUNTAINS = [  # (centre, radius, count, size)
    ((470, 640), 120, 46, 26),   # Mount Ghakis and the Balinoks
    ((166, 130), 60, 14, 18),
    ((830, 52), 120, 22, 20),
    ((420, 30), 260, 26, 16),
    ((560, 520), 60, 10, 18),
    ((250, 420), 40, 8, 14),
]

REGION_LABELS = [
    ("Lake Zarovich", (436, 206), 16, 0),
    ("Svalich Woods", (600, 108), 15, -4),
    ("Svalich Woods", (870, 250), 15, 62),
    ("Svalich Woods", (840, 590), 15, -8),
    ("Svalich Woods", (130, 500), 13, 48),
    ("Luna River", (382, 330), 11, 72),
    ("Ivlis River", (830, 470), 11, 0),
    ("Raven River", (66, 246), 10, 0),
    ("Mount Ghakis", (470, 690), 15, 0),
    ("Old Svalich Road", (870, 452), 10, -6),
    ("Tser Falls", (582, 398), 10, 0),
]


# --- drawing helpers ----------------------------------------------------------------------------

def jitter(rng: random.Random, points, amount=1.6):
    return [(x + rng.uniform(-amount, amount), y + rng.uniform(-amount, amount)) for x, y in points]


def smooth_path(points, closed=False) -> str:
    """Catmull-Rom through the points, as cubic Beziers."""
    pts = list(points)
    if closed:
        pts = pts[-1:] + pts + pts[:2]
    else:
        pts = pts[:1] + pts + pts[-1:]
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
    """A small conifer in a few quill strokes."""
    h = rng.uniform(9, 14)
    w = h * rng.uniform(0.42, 0.55)
    tiers = []
    for i in range(3):
        top = y - h + i * h * 0.28
        half = w * (0.45 + i * 0.28)
        base = top + h * 0.42
        tiers.append(f"M{x - half:.1f},{base:.1f} L{x + rng.uniform(-.6, .6):.1f},{top:.1f} L{x + half:.1f},{base:.1f}")
    trunk = f"M{x:.1f},{y - h * 0.15:.1f} L{x:.1f},{y + 2:.1f}"
    return f'<path d="{" ".join(tiers)} {trunk}"/>'


def mountain(rng: random.Random, x: float, y: float, size: float) -> str:
    """A peak with hatching down its shaded east face."""
    w = size * rng.uniform(0.8, 1.2)
    h = size * rng.uniform(0.75, 1.15)
    px = x + rng.uniform(-w * 0.1, w * 0.1)
    outline = f"M{x - w:.1f},{y:.1f} L{px:.1f},{y - h:.1f} L{x + w:.1f},{y:.1f}"
    hatch = []
    for i in range(1, 6):
        t = i / 6
        sx, sy = px + (x + w - px) * t, (y - h) + h * t
        hatch.append(f"M{sx:.1f},{sy:.1f} l{-w * 0.28:.1f},{h * 0.22:.1f}")
    snow = f"M{px - w * 0.25:.1f},{y - h * 0.72:.1f} l{w * 0.12:.1f},{h * 0.08:.1f} l{w * 0.13:.1f},{-h * 0.06:.1f}"
    return (f'<path d="{outline}" stroke-width="1.4"/>'
            f'<path d="{" ".join(hatch)} {snow}" stroke-width="0.7"/>')


def ripples(rng: random.Random, points) -> str:
    """Offset contour lines inside a lake, the way engravers drew water."""
    cx = sum(x for x, _ in points) / len(points)
    cy = sum(y for _, y in points) / len(points)
    out = []
    for scale in (0.78, 0.56):
        ring = [(cx + (x - cx) * scale, cy + (y - cy) * scale) for x, y in points]
        out.append(f'<path d="{smooth_path(jitter(rng, ring, 1.2), closed=True)}" stroke-width="0.6" '
                   f'stroke-dasharray="{rng.randint(6, 12)} {rng.randint(3, 6)}"/>')
    return "".join(out)


def compass(x: float, y: float, r: float) -> str:
    star = []
    for i in range(8):
        a = math.radians(i * 45 - 90)
        length = r if i % 2 == 0 else r * 0.55
        tip = (x + length * math.cos(a), y + length * math.sin(a))
        left = (x + r * 0.12 * math.cos(a - math.pi / 2), y + r * 0.12 * math.sin(a - math.pi / 2))
        right = (x + r * 0.12 * math.cos(a + math.pi / 2), y + r * 0.12 * math.sin(a + math.pi / 2))
        fill = INK if i % 2 == 0 else "none"
        star.append(f'<path d="M{left[0]:.1f},{left[1]:.1f} L{tip[0]:.1f},{tip[1]:.1f} L{right[0]:.1f},{right[1]:.1f} Z" '
                    f'fill="{fill}"/>')
    return (f'<g stroke-width="1"><circle cx="{x}" cy="{y}" r="{r * 0.7:.1f}" fill="none"/>'
            f'<circle cx="{x}" cy="{y}" r="{r * 0.78:.1f}" fill="none" stroke-width="0.5"/>{"".join(star)}'
            f'<text x="{x}" y="{y - r - 6:.1f}" text-anchor="middle" font-size="16" stroke="none" fill="{INK}">N</text></g>')


def castle(x: float, y: float) -> str:
    """Castle Ravenloft on its crag."""
    return (
        f'<g stroke-width="1.1">'
        f'<path d="M{x - 30},{y + 18} q8,-10 16,-12 q10,-4 14,-14 q6,8 16,10 q10,4 14,16" stroke-width="1.4"/>'
        f'<path d="M{x - 12},{y + 2} v-22 h24 v22 M{x - 12},{y - 20} l12,-12 l12,12 M{x - 4},{y + 2} v-8 h8 v8"/>'
        f'<path d="M{x - 22},{y + 4} v-16 h7 v16 M{x - 22},{y - 12} l3.5,-7 l3.5,7 M{x + 15},{y + 4} v-18 h7 v18 '
        f'M{x + 15},{y - 14} l3.5,-8 l3.5,8"/>'
        f'<path d="M{x - 8},{y - 12} h3 M{x + 5},{y - 12} h3 M{x - 1},{y - 4} v3" stroke-width="1.6"/></g>')


def creases(rng: random.Random) -> str:
    """Folds, scuffs and old stains in the hide, under the ink."""
    out = []
    for x in (W / 3, 2 * W / 3):
        pts = [(x + rng.uniform(-6, 6), y) for y in range(0, H + 50, 50)]
        out.append(f'<path d="{smooth_path(pts)}" stroke="#2a170a" stroke-opacity="0.35" stroke-width="2.2" fill="none"/>'
                   f'<path d="{smooth_path([(px + 2.5, py) for px, py in pts])}" stroke="#c49a6a" stroke-opacity="0.25" '
                   f'stroke-width="1.2" fill="none"/>')
    pts = [(x, H / 2 + rng.uniform(-6, 6)) for x in range(0, W + 50, 50)]
    out.append(f'<path d="{smooth_path(pts)}" stroke="#2a170a" stroke-opacity="0.3" stroke-width="2" fill="none"/>')
    for _ in range(26):
        x, y, length = rng.uniform(30, W - 30), rng.uniform(30, H - 30), rng.uniform(15, 70)
        a = rng.uniform(0, math.pi)
        out.append(f'<path d="M{x:.0f},{y:.0f} l{length * math.cos(a):.0f},{length * math.sin(a):.0f}" '
                   f'stroke="#2a170a" stroke-opacity="{rng.uniform(0.12, 0.3):.2f}" stroke-width="{rng.uniform(0.5, 1.4):.1f}"/>')
    for _ in range(3):
        x, y, r = rng.uniform(120, W - 120), rng.uniform(120, H - 120), rng.uniform(28, 46)
        out.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{r:.0f}" fill="none" stroke="#3a210f" stroke-opacity="0.22" '
                   f'stroke-width="{rng.uniform(2, 4):.1f}" stroke-dasharray="{rng.randint(30, 80)} {rng.randint(4, 14)}"/>')
    return "".join(out)


# --- the base map --------------------------------------------------------------------------------

def draw_base() -> str:
    rng = random.Random(SEED)
    water = list(LAKES.values())
    roads = list(ROADS.values()) + list(TRACKS.values())
    rivers = list(RIVERS.values())

    def clear(point, margin=10) -> bool:
        return (not any(inside(point, lake) for lake in water)
                and not any(near_line(point, line, margin) for line in roads + rivers))

    parts = []
    # Mountains, back to front so nearer peaks overlap farther ones.
    peaks = []
    for (cx, cy), radius, count, size in MOUNTAINS:
        for _ in range(count):
            a, r = rng.uniform(0, math.tau), radius * math.sqrt(rng.random())
            p = (cx + r * math.cos(a), cy + r * math.sin(a) * 0.55)
            if 8 < p[0] < W - 8 and 18 < p[1] < H - 8 and clear(p, 14):
                peaks.append((p, size * rng.uniform(0.7, 1.15)))
    peaks.sort(key=lambda pk: pk[0][1])
    parts.append('<g id="mountains" fill="none">' + "".join(mountain(rng, x, y, s) for (x, y), s in peaks) + "</g>")

    # Forests: trees on a jittered grid inside each wood.
    trees = []
    for poly in FORESTS:
        xs, ys = [x for x, _ in poly], [y for _, y in poly]
        y = min(ys)
        while y < max(ys):
            x = min(xs) + rng.uniform(0, 9)
            while x < max(xs):
                p = (x + rng.uniform(-3, 3), y + rng.uniform(-3, 3))
                if inside(p, poly) and clear(p) and not any(math.dist(p, pk) < s for pk, s in peaks):
                    trees.append(p)
                x += rng.uniform(10, 14)
            y += rng.uniform(9, 12)
    trees.sort(key=lambda p: p[1])
    parts.append('<g id="forest" stroke-width="0.9" fill="none">' + "".join(tree(rng, x, y) for x, y in trees) + "</g>")

    # Rolling hills and grass tufts in the open country, so the plains read as land.
    marks = []
    for _ in range(420):
        p = (rng.uniform(40, W - 40), rng.uniform(60, H - 60))
        if (clear(p, 12) and not any(inside(p, poly) for poly in FORESTS)
                and not any(math.dist(p, pk) < s * 1.6 for pk, s in peaks)
                and not near_line(p, [(620, 300), (760, 380)], 50)):
            x, y = p
            if rng.random() < 0.45:
                w = rng.uniform(8, 16)
                marks.append(f"M{x - w:.1f},{y:.1f} q{w:.1f},{-w * 0.55:.1f} {2 * w:.1f},0")
            else:
                marks.append(f"M{x:.1f},{y:.1f} l-2,-4 M{x + 2:.1f},{y:.1f} l0,-5 M{x + 4:.1f},{y:.1f} l2,-4")
    parts.append(f'<path d="{" ".join(marks)}" fill="none" stroke-width="0.7" stroke-opacity="0.8"/>')

    # Water.
    for name, pts in LAKES.items():
        shore = jitter(rng, [q for a, b in zip(pts, pts[1:] + pts[:1])
                              for q in (a, ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2))], 4.5)
        parts.append(f'<path d="{smooth_path(shore, closed=True)}" fill="#3d2615" fill-opacity="0.35" stroke-width="1.7"/>')
        parts.append(ripples(rng, pts))
    for pts in rivers:
        d = smooth_path(jitter(rng, pts, 1.2))
        parts.append(f'<path d="{d}" fill="none" stroke-width="2.6"/><path d="{d}" fill="none" stroke="#8a6040" stroke-width="0.9"/>')

    # Roads: a doubled line for the Old Svalich Road, dotted tracks.
    for name, pts in ROADS.items():
        d = smooth_path(jitter(rng, pts, 1.0))
        width = 2.2 if name == "Old Svalich Road" else 1.4
        parts.append(f'<path d="{d}" fill="none" stroke-width="{width}" stroke-dasharray="14 3 2 3"/>')
    for pts in TRACKS.values():
        parts.append(f'<path d="{smooth_path(jitter(rng, pts, 1.0))}" fill="none" stroke-width="1.6" '
                     f'stroke-dasharray="0.5 5" stroke-linecap="round"/>')

    parts.append(castle(707, 352))

    # Region names, in the map's own hand.
    for text, (x, y), size, angle in REGION_LABELS:
        parts.append(f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="middle" font-style="italic" '
                     f'transform="rotate({angle} {x} {y})" stroke="#916339" stroke-width="5" paint-order="stroke" '
                     f'fill="{INK}" letter-spacing="1">{text}</text>')

    # The mists at the edge of the world: ragged scumbling.
    mist = []
    for _ in range(260):
        edge = rng.choice("nsew")
        depth = abs(rng.gauss(0, 18))
        if edge in "ns":
            x, y = rng.uniform(0, W), depth if edge == "n" else H - depth
        else:
            x, y = depth if edge == "w" else W - depth, rng.uniform(0, H)
        length = rng.uniform(10, 40)
        mist.append(f"M{x:.0f},{y:.0f} q{length / 2:.0f},{rng.uniform(-4, 4):.0f} {length:.0f},0")
    parts.append(f'<path d="{" ".join(mist)}" fill="none" stroke-width="0.6" stroke-opacity="0.55"/>')

    # Cartouche, scale and compass.
    parts.append(
        f'<g stroke="#916339" stroke-width="6" paint-order="stroke" fill="{INK}">'
        f'<text x="64" y="70" font-size="48" font-style="italic" letter-spacing="3">Barovia</text>'
        f'<text x="70" y="98" font-size="12" letter-spacing="2" stroke-width="4">as the Owlbears found it</text></g>'
        f'<path d="M58,80 q90,7 208,-3" fill="none" stroke-width="1.1"/>')
    parts.append(compass(930, 660, 34))
    scale = [f'<path d="M60,694 h200" stroke-width="1.2"/>']
    for i in range(6):
        scale.append(f'<path d="M{60 + i * 40},688 v12" stroke-width="1"/>')
        if i < 5:
            scale.append(f'<rect x="{60 + i * 40}" y="691" width="40" height="5" fill="{INK if i % 2 == 0 else "none"}" stroke-width="0.8"/>')
    scale.append(f'<text x="160" y="716" font-size="11" text-anchor="middle" stroke="none" fill="{INK}">Leagues, more or less</text>')
    parts.append("".join(scale))

    leather = (
        '<filter id="leather" x="0" y="0" width="100%" height="100%">'
        '<feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="3" seed="7" result="grain"/>'
        '<feColorMatrix in="grain" type="matrix" values="0 0 0 0 0.16  0 0 0 0 0.09  0 0 0 0 0.04  0 0 0 0.9 -0.25"/>'
        '<feComposite in2="SourceGraphic" operator="in" result="speck"/>'
        '<feTurbulence type="fractalNoise" baseFrequency="0.012" numOctaves="3" seed="11" result="blotch"/>'
        '<feColorMatrix in="blotch" type="matrix" values="0 0 0 0 0.20  0 0 0 0 0.11  0 0 0 0 0.05  0 0 0 1.1 -0.32" result="stain"/>'
        '<feMerge><feMergeNode in="SourceGraphic"/><feMergeNode in="stain"/><feMergeNode in="speck"/></feMerge></filter>'
        '<filter id="quill"><feTurbulence type="fractalNoise" baseFrequency="0.035" numOctaves="2" seed="3"/>'
        '<feDisplacementMap in="SourceGraphic" scale="2.4"/></filter>'
        '<radialGradient id="hide" cx="50%" cy="48%" r="72%">'
        '<stop offset="0" stop-color="#a87c4f"/><stop offset="0.55" stop-color="#916339"/>'
        '<stop offset="0.85" stop-color="#5e3a1e"/><stop offset="1" stop-color="#2e1a0c"/></radialGradient>'
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
        f'font-family="\'Palatino Linotype\', Palatino, \'Book Antiqua\', Georgia, serif">'
        f'<title>Barovia, drawn for the Owlbear Chronicles</title><defs>{leather}</defs>'
        f'<rect width="{W}" height="{H}" fill="url(#hide)" filter="url(#leather)"/>'
        + creases(random.Random(SEED + 1)) +
        f'<g filter="url(#quill)" stroke="{INK}" stroke-linecap="round" stroke-linejoin="round" fill="none">'
        f'<rect x="14" y="14" width="{W - 28}" height="{H - 28}" stroke-width="2.4"/>'
        f'<rect x="22" y="22" width="{W - 44}" height="{H - 44}" stroke-width="0.8"/>'
        + "".join(parts) + "</g></svg>\n"
    )


# --- places and the trail -----------------------------------------------------------------------

@dataclass
class Place:
    slug: str
    title: str
    x: float
    y: float
    names: list[str]
    anchor: str = "middle"  # where the label sits: above ("middle"), to the right ("start"), left ("end")
    sessions: list = field(default_factory=list)  # posts with a stop here, newest first

    @property
    def path(self) -> str:
        return f"wiki/{self.slug}/"

    @property
    def label_xy(self) -> tuple[float, float]:
        if self.anchor == "start":
            return self.x + 11, self.y + 5
        if self.anchor == "end":
            return self.x - 11, self.y + 5
        return self.x, self.y - 12


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
        if anchor not in ("middle", "start", "end"):
            raise ValueError(f"data/map.yaml: {slug}: anchor must be middle, start or end")
        places[slug] = Place(slug, str(spec.get("label") or page.title), float(x), float(y),
                             [str(n) for n in spec.get("names") or page.names], anchor)
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
    """[{post, stops: [place slugs]}] oldest first; also fills each Place.sessions.

    A post listed in `visits` uses that list (an empty list means "nowhere on the map"); any other
    post falls back to the places it mentions, in order.
    """
    visits = visits or {}
    legs = []
    for post in sorted(posts, key=lambda p: (p.date, p.slug)):
        stem = post.source.stem if post.source else post.slug
        if stem in visits:
            here = visits[stem]
        else:
            here = stops(wiki.plain_text(post.html), places, parent, pages)
        if here:
            legs.append({"post": post, "stops": here})
            for slug in here:
                places[slug].sessions.insert(0, post)
    add_strokes(legs, places)
    return legs


def add_strokes(legs: list[dict], places: dict[str, Place]) -> None:
    """Give each leg the curved trail strokes from the party's last stop through this session's.

    Each stroke bows a little to one side, and more for every earlier trip between the same two
    places, so a road walked many times shows as a bundle of lines rather than one.
    """
    trips: dict[frozenset, int] = {}
    previous = None
    for leg in legs:
        leg["strokes"] = []
        for slug in leg["stops"]:
            if previous and previous != slug:
                a, b = places[previous], places[slug]
                key = frozenset((previous, slug))
                n = trips.get(key, 0)
                trips[key] = n + 1
                length = math.hypot(b.x - a.x, b.y - a.y) or 1
                bow = (0.12 + 0.07 * n) * length * (1 if n % 2 == 0 else -1)
                mx, my = (a.x + b.x) / 2, (a.y + b.y) / 2
                cx, cy = mx - (b.y - a.y) / length * bow, my + (b.x - a.x) / length * bow
                leg["strokes"].append(f"M{a.x:.0f},{a.y:.0f} Q{cx:.0f},{cy:.0f} {b.x:.0f},{b.y:.0f}")
            previous = slug
