"""Cut the map's place sprites out of the sprite sheets and fade their edges into the parchment.

The sheets in tools/sprite_sheets/ were drawn for this map with Gemini (prompts in SHEETS below),
each picture alone in a cell of a grid on a white ground. For each picture this finds it in its
cell, makes the white ground transparent, keeps the drawing itself solid, and breaks the outer
edge up with noise so it fades into the parchment like dry-brush ink instead of a cut-out edge.

    python tools/make_sprites.py        # writes static/images/map/sprites/<name>.webp
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
STYLE = ("hand-drawn fantasy map icons, brown iron-gall ink linework with fine cross-hatching, muted "
         "watercolor washes, slightly elevated three-quarter view, each icon alone on plain white")
# sheet file -> (columns, rows, [sprite name per cell, row by row; None skips a cell])
SHEETS = {
    "places-1.jpg": (4, 3, ["castle-ravenloft", "barovia", "vallaki", "krezk",
                            None, "the-windmill", "tower-of-khazan", "argynvostholt",
                            "wizard-of-wines", "yester-hill", "durst-manor", "tser-pool"]),
    "places-2.jpg": (4, 2, ["gates", "abbey-of-saint-markovia", "berez", "amber-temple",
                            "watchtower", "bridge", "dead-tree", "whispering-wall"]),
}
BAND = 9        # how far in from the edge the fade reaches, in sheet pixels
MAX_SIDE = 260  # sprites are stored at most this big


def cut(cell: Image.Image, seed: int = 7) -> Image.Image:
    """One picture from its cell, on a transparent ground with a dithered edge."""
    rgb = np.asarray(cell.convert("RGB")).astype(int)
    ink = rgb.min(axis=2) <= 236
    ys, xs = np.where(ink)
    if not len(xs):
        raise ValueError("empty cell")
    x0, x1 = max(xs.min() - BAND, 0), min(xs.max() + 1 + BAND, rgb.shape[1])
    y0, y1 = max(ys.min() - BAND, 0), min(ys.max() + 1 + BAND, rgb.shape[0])
    rgb = rgb[y0:y1, x0:x1]
    base = np.clip((255 - rgb.min(axis=2)) * 6, 0, 255) / 255.0
    # The picture's silhouette with its small holes filled, and how far each pixel is inside it.
    silhouette = Image.fromarray(((base > 0.15) * 255).astype("uint8"))
    silhouette = silhouette.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.MinFilter(5))
    depth = np.zeros(base.shape)
    layer = silhouette
    for _ in range(BAND):
        depth += np.asarray(layer) > 0
        layer = layer.filter(ImageFilter.MinFilter(3))
    rng = np.random.default_rng(seed)
    blotch = np.asarray(Image.fromarray((rng.random(base.shape) * 255).astype("uint8"))
                        .filter(ImageFilter.GaussianBlur(2.5))) / 255.0
    blotch = (blotch - blotch.mean()) / (blotch.std() + 1e-6)
    keep = np.clip((depth / BAND + 0.18 * blotch - 0.35 * rng.random(base.shape) + 0.1) * 1.6, 0, 1)
    solid = np.asarray(silhouette.filter(ImageFilter.MaxFilter(3))) / 255.0
    alpha = (np.maximum(solid, base) * keep * 255).astype("uint8")
    colour = ImageEnhance.Brightness(Image.fromarray(rgb.astype("uint8"))).enhance(1.12)
    colour = ImageEnhance.Contrast(colour).enhance(0.95)
    out = Image.fromarray(np.dstack([np.asarray(colour), alpha]))
    out.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    return out


def main(out_dir: Path = ROOT / "static" / "images" / "map" / "sprites") -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for sheet, (cols, rows, names) in SHEETS.items():
        im = Image.open(ROOT / "tools" / "sprite_sheets" / sheet)
        w, h = im.size
        for i, name in enumerate(names):
            if name is None:
                continue
            r, c = divmod(i, cols)
            cell = im.crop((c * w // cols, r * h // rows, (c + 1) * w // cols, (r + 1) * h // rows))
            cut(cell, seed=i).save(out_dir / f"{name}.webp", quality=88, method=6)
            print(name)


if __name__ == "__main__":
    main(*(Path(a) for a in sys.argv[1:]))
