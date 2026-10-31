"""Drag the map's sprites into place on your own computer: `just map-edit`, then open the link.

Builds the site, serves public/ on localhost, and adds /edit/: the map with every sprite
draggable (scroll or pinch over a sprite to resize it). Each drop is saved straight into the
`sprites:` section of data/map.yaml (only that sprite's line changes; comments stay), and the
page says "Saved" once the file holds it. Rebuild (or `just serve`) to see the new spots on the site.
"""

from __future__ import annotations

import http.server
import json
import re
import subprocess
import sys
import webbrowser
from functools import partial
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAP_FILE = ROOT / "data" / "map.yaml"
PUBLIC = ROOT / "public"


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


EDIT_PAGE = """<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Place the map sprites</title>
<style>body{margin:0;font:15px Georgia,serif;background:#2b2118;color:#eee}
#bar{padding:8px 12px}#status{margin-left:1em;color:#cfe8b0}svg{display:block;width:100%;height:auto;touch-action:none}
.sp{cursor:grab}.sp.drag{cursor:grabbing;outline:1px dashed #fff}text.n{font-size:7px;fill:#000;paint-order:stroke;stroke:#fff;stroke-width:2px;pointer-events:none}</style>
<div id="bar">Drag a picture to move it; scroll over it (or use + / - after tapping it) to resize. <span id="status"></span></div>
<svg viewBox="0 0 1000 750" id="map"><image href="/images/map/parchment.jpg" width="1000" height="750"/>
<image href="/map/barovia.svg" width="1000" height="750"/><g id="sprites"></g><g id="pins"></g></svg>
<script>
const SPRITES = __SPRITES__, PLACES = __PLACES__, svg = document.getElementById("map"), g = document.getElementById("sprites");
const status = document.getElementById("status"); let active = null;
for (const p of PLACES) document.getElementById("pins").insertAdjacentHTML("beforeend",
  `<circle cx="${p.x}" cy="${p.y}" r="3" fill="#000"/><text class="n" x="${p.x + 5}" y="${p.y + 2}">${p.t}</text>`);
function pt(e){const m=svg.getScreenCTM().inverse();const q=new DOMPoint(e.clientX,e.clientY).matrixTransform(m);return q;}
function draw(s){s.el.setAttribute("x",s.x-s.w/2);s.el.setAttribute("y",s.y-s.w*s.r/2);s.el.setAttribute("width",s.w);s.el.setAttribute("height",s.w*s.r);}
async function save(s){status.textContent="Saving "+s.name+"...";
  const r=await fetch("/save",{method:"POST",body:JSON.stringify({name:s.name,xy:[s.x,s.y],width:s.w})});
  status.textContent=r.ok?"Saved "+s.name+" to data/map.yaml":"NOT saved: "+await r.text(); status.style.color=r.ok?"#cfe8b0":"#ff9a8a";}
for (const s of SPRITES){s.el=document.createElementNS("http://www.w3.org/2000/svg","image");s.el.setAttribute("href","/images/map/sprites/"+s.image+".webp");
  s.el.setAttribute("class","sp");g.appendChild(s.el);draw(s);
  s.el.addEventListener("pointerdown",e=>{active=s;const q=pt(e);s.dx=s.x-q.x;s.dy=s.y-q.y;s.el.classList.add("drag");s.el.setPointerCapture(e.pointerId);});
  s.el.addEventListener("pointermove",e=>{if(active!==s)return;const q=pt(e);s.x=q.x+s.dx;s.y=q.y+s.dy;draw(s);});
  s.el.addEventListener("pointerup",()=>{if(active===s){s.el.classList.remove("drag");save(s);}});
  s.el.addEventListener("wheel",e=>{e.preventDefault();s.w=Math.max(8,s.w*(e.deltaY<0?1.08:1/1.08));draw(s);clearTimeout(s.t);s.t=setTimeout(()=>save(s),400);});}
document.addEventListener("keydown",e=>{if(!active)return;if(e.key=="+"||e.key=="=")active.w*=1.08;else if(e.key=="-")active.w/=1.08;else return;draw(active);save(active);});
</script>"""


def edit_page() -> str:
    sys.path.insert(0, str(ROOT))
    import yaml

    import barovia_map
    sprites = barovia_map.load_sprites(MAP_FILE, ROOT / "static" / "images" / "map" / "sprites")
    data = yaml.safe_load(MAP_FILE.read_text(encoding="utf-8"))
    places = [{"x": v["xy"][0], "y": v["xy"][1], "t": k} for k, v in data["places"].items()]
    items = [{"name": s.name, "image": s.image, "x": s.x, "y": s.y, "w": s.width, "r": s.height / s.width} for s in sprites]
    return EDIT_PAGE.replace("__SPRITES__", json.dumps(items)).replace("__PLACES__", json.dumps(places))


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.rstrip("/") == "/edit":
            body = edit_page().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            super().do_GET()

    def do_POST(self):
        if self.path != "/save":
            self.send_error(404)
            return
        try:
            item = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            text = MAP_FILE.read_text(encoding="utf-8")
            new = move_sprite(text, item["name"], tuple(item["xy"]), float(item["width"]))
            MAP_FILE.write_text(new, encoding="utf-8")
            if MAP_FILE.read_text(encoding="utf-8") != new:  # make sure the file really holds it
                raise OSError("data/map.yaml did not keep the change")
        except Exception as err:  # tell the page, so a failed save never looks like a saved one
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(err).encode("utf-8"))
            return
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")


def main(port: int = 8001) -> None:
    subprocess.run([sys.executable, str(ROOT / "build.py")], check=True, cwd=ROOT)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), partial(Handler, directory=str(PUBLIC)))
    url = f"http://localhost:{port}/edit/"
    print(f"Sprite editor at {url} (Ctrl+C to stop)")
    webbrowser.open(url)
    server.serve_forever()


if __name__ == "__main__":
    main(*(int(a) for a in sys.argv[1:]))
