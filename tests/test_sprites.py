"""The map's sprites are cut from grid sheets; a picture that spills over its cell's line must not
be cut in half, and must not show up in its neighbour's sprite (Chris, 2026-11-02: the gates' right
tower and statue sat beside the Abbey of St. Markovia as a "little tower with a white trail")."""

import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import make_sprites  # noqa: E402


def sheet_with_spill() -> Image.Image:
    """Two pictures side by side on a 400x200 sheet with two cells. The left one runs 15 px past the
    cell line at x=200, with a faint wash (like mist) trailing off it."""
    px = np.full((200, 400, 3), 255, dtype=np.uint8)
    px[40:160, 20:215] = 60      # left picture, over the line
    px[120:150, 215:225] = 225   # faint mist trailing off it
    px[30:170, 240:380] = 90     # right picture
    return Image.fromarray(px)


def test_cells_split_at_the_gap_between_pictures_not_the_grid_line():
    boxes = make_sprites.cells(sheet_with_spill(), 2, 1)
    (lx0, _, lx1, _), (rx0, _, rx1, _) = boxes
    assert lx0 == 0 and rx1 == 400
    assert 215 <= lx1 == rx0 <= 240


def test_a_sprite_holds_only_its_own_picture():
    sheet = sheet_with_spill()
    left_box, right_box = make_sprites.cells(sheet, 2, 1)
    right = np.asarray(make_sprites.cut(sheet.crop(right_box)))
    left = np.asarray(make_sprites.cut(sheet.crop(left_box)))
    # The right sprite is the right picture (140 wide) plus its faded edge, nothing of the left one.
    assert right.shape[1] < 140 + 2 * make_sprites.BAND + 1
    assert (right[..., :3][right[..., 3] > 200].min(axis=1) >= 80).all()
    # The left picture comes out whole, past the grid line.
    assert left.shape[1] >= 195


def test_the_abbey_sprite_has_no_piece_of_the_gates_beside_it():
    """The live abbey sprite: the top half of its left fifth, where the gates' tower and statue
    were, is empty (the abbey's rock reaches the left edge lower down)."""
    im = np.asarray(Image.open(ROOT / "static" / "images" / "map" / "sprites" / "abbey-of-saint-markovia.webp")
                    .convert("RGBA"))
    left = im[: im.shape[0] // 2, : im.shape[1] // 5, 3]
    assert (left > 128).mean() < 0.02
