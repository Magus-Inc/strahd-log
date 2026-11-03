"""Edit the map on your own computer: `just map-edit`, then open the link.

Builds the site, serves public/ on localhost, and adds /edit/, the map with two modes:

- Pictures: drag a sprite to move it; scroll or pinch over it (or + / -) to resize. Saves to the
  `sprites:` section of data/map.yaml.
- Roads & water: drag the points of roads, tracks, rivers, lakes and forests, and the centres of
  mountain clusters and labels. A crossroads drags every road that meets there and the place on it.
  Tap a line to add a point, give that stretch switchbacks or a wiggle, or turn a shape into
  points; tap a point to delete it. Saves to data/geography.yaml (and moves the places, spots and
  travel-time junctions that sit on a moved point in data/map.yaml and data/travel-times.yaml).

Every change is written straight to the files (only the changed entries; comments stay), read back
to make sure it holds, and the page says "Saved" only then. Undo (Ctrl+Z) steps back through the
last 50 changes. Rebuild (or `just serve`) to see the result on the site.
"""

from __future__ import annotations

import http.server
import json
import re
import subprocess
import sys
import threading
import webbrowser
from functools import partial
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import geo_edit  # noqa: E402

MAP_FILE = ROOT / "data" / "map.yaml"
GEO_FILE = ROOT / "data" / "geography.yaml"
TRAVEL_FILE = ROOT / "data" / "travel-times.yaml"
SPRITE_DIR = ROOT / "static" / "images" / "map" / "sprites"
PUBLIC = ROOT / "public"
EDIT_PAGE = Path(__file__).resolve().parent / "map_editor.html"
UNDO = 50


def move_sprite(text: str, name: str, xy: tuple[float, float], width: float) -> str:
    """data/map.yaml text with one sprite's xy and width changed, everything else untouched."""
    start = text.find("\nsprites:")
    if start < 0:
        raise KeyError(name)
    line = re.compile(rf"^(  {re.escape(name)}: \{{.*?xy: )\[[^\]]*\](, width: )[\d.]+", re.M)
    head, tail = text[:start], text[start:]
    new, n = line.subn(lambda m: f"{m.group(1)}[{round(xy[0], 1):g}, {round(xy[1], 1):g}]{m.group(2)}{round(width):g}",
                       tail, count=1)
    if not n:
        raise KeyError(name)
    return head + new


class Editor:
    """The three files the editor changes; every change checked, written, read back, and undoable."""

    def __init__(self, geo: Path = GEO_FILE, map_file: Path = MAP_FILE, travel: Path = TRAVEL_FILE,
                 sprite_dir: Path = SPRITE_DIR):
        self.files = (geo, map_file, travel)
        self.sprite_dir = sprite_dir
        self.history: list[tuple[str, str, str]] = []
        self.lock = threading.RLock()

    def texts(self) -> tuple[str, str, str]:
        return tuple(f.read_text(encoding="utf-8") for f in self.files)

    def _write(self, new: tuple[str, str, str]) -> None:
        for f, text in zip(self.files, new):
            if f.read_text(encoding="utf-8") != text:
                f.write_text(text, encoding="utf-8")
                if f.read_text(encoding="utf-8") != text:  # make sure the file really holds it
                    raise OSError(f"{f.name} did not keep the change")

    def apply(self, op: dict) -> None:
        """One edit from the page. The files are read fresh each time, so a hand edit in between is kept;
        anything the map can't draw is refused and nothing is written."""
        with self.lock:
            old = self.texts()
            geo, places, travel = old
            kind, section, key = op.get("op"), op.get("section"), op.get("key")
            if kind == "move":
                geo, places, travel = geo_edit.move_point(geo, places, travel, op["from"], op["to"])
            elif kind == "insert":
                geo = geo_edit.insert_point(geo, section, key, int(op["after"]), op["xy"])
            elif kind == "delete":
                geo = geo_edit.delete_point(geo, places, travel, section, key, int(op["index"]))
            elif kind == "shape":
                geo = geo_edit.set_shape(geo, section, key, int(op["index"]), op.get("shape"))
            elif kind == "bake":
                geo = geo_edit.bake(geo, section, key, int(op["index"]))
            elif kind == "shift":
                geo = geo_edit.shift(geo, section, key, float(op["dx"]), float(op["dy"]))
            elif kind == "item":
                geo = geo_edit.move_item(geo, section, int(op["index"]), op["at"])
            elif kind == "sprite":
                places = move_sprite(places, op["name"], tuple(op["xy"]), float(op["width"]))
            else:
                raise geo_edit.EditError(f"unknown edit {kind!r}")
            geo_edit.check(geo)
            new = (geo, places, travel)
            if new != old:
                self._write(new)
                self.history = (self.history + [old])[-UNDO:]

    def undo(self) -> bool:
        with self.lock:
            if not self.history:
                return False
            self._write(self.history.pop())
            return True

    def state(self) -> dict:
        with self.lock:
            out = geo_edit.state(*self.texts())
            out["undo"] = len(self.history)
        return out

    def base_svg(self) -> str:
        """The base map drawn from the files as they are now."""
        import barovia_map
        with self.lock:
            try:
                barovia_map.use_geography(self.files[0])
                return barovia_map.draw_base(barovia_map.load_sprites(self.files[1], self.sprite_dir))
            finally:
                barovia_map.use_geography()

    def page(self) -> str:
        import barovia_map
        import yaml
        sprites = barovia_map.load_sprites(self.files[1], self.sprite_dir)
        data = yaml.safe_load(self.files[1].read_text(encoding="utf-8"))
        places = [{"x": v["xy"][0], "y": v["xy"][1], "t": k} for k, v in data["places"].items()]
        items = [{"name": s.name, "image": s.image, "x": s.x, "y": s.y, "w": s.width, "r": s.height / s.width}
                 for s in sprites]
        return (EDIT_PAGE.read_text(encoding="utf-8").replace("__SPRITES__", json.dumps(items))
                .replace("__PLACES__", json.dumps(places)))


class Handler(http.server.SimpleHTTPRequestHandler):
    editor: Editor  # set by serve()

    def log_message(self, *args):  # keep the terminal quiet
        pass

    def _send(self, code: int, body, kind: str = "application/json") -> None:
        body = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", kind + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/")
        if path == "/edit":
            self._send(200, self.editor.page(), "text/html")
        elif path == "/edit/state":
            self._send(200, json.dumps(self.editor.state()))
        elif path == "/edit/base.svg":
            self._send(200, self.editor.base_svg(), "image/svg+xml")
        else:
            super().do_GET()

    def do_POST(self):
        try:
            item = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            if self.path == "/save":  # a sprite, from Pictures mode
                self.editor.apply({"op": "sprite", **item})
            elif self.path == "/geo":
                self.editor.apply(item)
            elif self.path == "/undo":
                if not self.editor.undo():
                    raise geo_edit.EditError("nothing to undo")
            else:
                self.send_error(404)
                return
        except Exception as err:  # tell the page, so a failed save never looks like a saved one
            self._send(400 if isinstance(err, (ValueError, KeyError)) else 500, str(err), "text/plain")
            return
        self._send(200, json.dumps(self.editor.state()))


def serve(port: int, editor: Editor | None = None, directory: Path = PUBLIC) -> http.server.ThreadingHTTPServer:
    handler = type("EditHandler", (Handler,), {"editor": editor or Editor()})
    return http.server.ThreadingHTTPServer(("127.0.0.1", port), partial(handler, directory=str(directory)))


def main(port: int = 8001) -> None:
    subprocess.run([sys.executable, str(ROOT / "build.py")], check=True, cwd=ROOT)
    server = serve(port)
    url = f"http://localhost:{port}/edit/"
    print(f"Map editor at {url} (Ctrl+C to stop)")
    webbrowser.open(url)
    server.serve_forever()


if __name__ == "__main__":
    main(*(int(a) for a in sys.argv[1:]))
