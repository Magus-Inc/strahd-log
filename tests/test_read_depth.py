"""How far down a post readers get (Chris, 2026-11-04): GoatCounter's /read/<post>/halfway event
fires once the reader has had all of Malron's Account on screen, and /finished once they reach the
map ("Where we were"). Wiki pages send no read events.

The browser tests scroll a real post in headless Chromium through Node's Playwright, with a fake
clock, and record the events the page sends; they are skipped where Node, Playwright or Chromium is
missing. The same script also runs under plain Node against a pretend page, which needs only Node.
"""
import functools
import http.server
import json
import re
import shutil
import subprocess
import threading
from pathlib import Path

import jinja2
import pytest

import build

NODE = shutil.which("node")
POST = "echoes-of-the-black-terro"  # has Malron's Account, recap lists and the map
NOTED = "the-abbot-unveiled-wings-lies-and-the-fallen-star"  # its last margin note hangs past the account


def reading_js(counter: str = "owlbear", ga: str = "") -> str:
    """templates/_read_depth.js as a post page renders it with the counter (and Google Analytics) on."""
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(build.ROOT / "templates"))
    return env.get_template("_read_depth.js").render(base="/", counter=counter, ga=ga)


def has_playwright() -> bool:
    if NODE is None:
        return False
    launch = "require('playwright').chromium.launch().then(b => b.close()).catch(() => process.exit(1))"
    try:
        found = subprocess.run([NODE, "-e", launch], capture_output=True, timeout=60)
    except subprocess.TimeoutExpired:
        return False
    return found.returncode == 0


needs_node = pytest.mark.skipif(NODE is None, reason="Node is needed to run the reading script")
needs_browser = pytest.mark.skipif(not has_playwright(), reason="Node with Playwright and Chromium is needed to scroll a post")

# Scroll the post one step at a time and report which read events each step sent. Each step puts
# the top (or `edge`) of an element `offset` pixels below the bottom of the screen (negative: on screen), then
# lets `wait` seconds pass on the page's clock.
SCROLLER = r"""
const {chromium} = require("playwright");
(async () => {
  const [url, stepsJson, width] = process.argv.slice(1);
  const steps = JSON.parse(stepsJson);
  const browser = await chromium.launch();
  const page = await browser.newPage({viewport: {width: Number(width), height: 800}});
  const sent = [];
  await page.route("https://*.goatcounter.com/**", route => {
    sent.push(new URL(route.request().url()).searchParams.get("p"));
    route.fulfill({status: 204, body: ""});
  });
  await page.clock.install();
  await page.goto(url);
  const out = [];
  for (const step of steps) {
    await page.evaluate(([selector, offset, edge]) => {
      const el = document.querySelector(selector);
      if (!el) throw new Error("no " + selector);
      const top = el.getBoundingClientRect()[edge || "top"] + window.scrollY;
      window.scrollTo(0, top - window.innerHeight - offset);
      window.dispatchEvent(new Event("scroll"));
    }, [step.selector, step.offset, step.edge]);
    await page.clock.runFor(step.wait * 1000);
    await page.evaluate(() => new Promise(r => requestAnimationFrame(() => r())));
    out.push(sent.splice(0).map(p => p.split("/").pop()));
  }
  await browser.close();
  process.stdout.write(JSON.stringify(out));
})().catch(e => { console.error(e); process.exit(1); });
"""


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def counted_site(real_build, tmp_path_factory):
    """The shared real build's post (built without the counter), with the reading script the counter
    turns on (templates/_read_depth.js, as post.html includes it), served over HTTP from a copy."""
    out = tmp_path_factory.mktemp("counted")
    shutil.copytree(real_build.out, out, dirs_exist_ok=True)
    script = reading_js()
    for post in (POST, NOTED):
        page = out / "posts" / post / "index.html"
        html = page.read_text(encoding="utf-8")
        page.write_text(html.replace("</body>", f"<script>\n{script}\n</script>\n</body>", 1), encoding="utf-8")
    handler = functools.partial(Quiet, directory=str(out))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield out, f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def scroll(url: str, steps: list[dict], width: int = 400) -> list[list[str]]:
    done = subprocess.run([NODE, "-e", SCROLLER, url, json.dumps(steps), str(width)], capture_output=True, text=True,
                          encoding="utf-8", timeout=120)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def reading_script(html: str) -> str:
    return html.split("// Reading:")[1].split("</script>")[0]


def test_the_markers_are_the_end_of_the_account_and_the_map(real_build):
    script = (build.ROOT / "templates" / "_read_depth.js").read_text(encoding="utf-8")
    assert "story-end" in script and "where-we-were" in script
    html = (real_build.out / "posts" / POST / "index.html").read_text(encoding="utf-8")
    assert "<!--story-end-->" in html and 'class="where-we-were"' in html


def test_posts_include_the_reading_script():
    post = (build.ROOT / "templates" / "post.html").read_text(encoding="utf-8")
    assert '{% include "_read_depth.js" %}' in post


def test_wiki_pages_send_no_read_events():
    for name in ("wiki_page.html", "wiki_index.html", "base.html"):
        template = (build.ROOT / "templates" / name).read_text(encoding="utf-8")
        assert "_read_depth" not in template and '"/read" + path' not in template


@needs_browser
def test_halfway_waits_for_the_whole_account(counted_site):
    _, root = counted_site
    url = f"{root}/posts/{POST}/"
    first_recap = "#key-locations"  # the heading right after Malron's Account
    got = scroll(url, [
        {"selector": first_recap, "offset": 60, "wait": 2},   # the account's last lines are still below
        {"selector": first_recap, "offset": -20, "wait": 2},  # the account is all read
    ])
    assert "halfway" not in got[0]
    assert "halfway" in got[1]


@needs_browser
def test_finished_waits_for_the_map(counted_site):
    _, root = counted_site
    url = f"{root}/posts/{POST}/"
    got = scroll(url, [
        {"selector": ".where-we-were .map-figure", "offset": 20, "wait": 900},  # lists done, map just below
        {"selector": ".where-we-were .map-figure", "offset": -20, "wait": 2},   # the map is on screen
    ])
    assert "finished" not in got[0]
    assert "halfway" in got[0] and "started" in got[0]
    assert got[1] == ["finished"]


@needs_browser
def test_a_post_without_a_map_finishes_at_the_end_of_its_text(counted_site):
    out, root = counted_site
    html = (out / "posts" / POST / "index.html").read_text(encoding="utf-8")
    without = re.sub(r'<section class="where-we-were">.*?</section>', "", html, flags=re.S)
    assert without != html
    copy = out / "posts" / "no-map" / "index.html"
    copy.parent.mkdir()
    copy.write_text(without, encoding="utf-8")
    got = scroll(f"{root}/posts/no-map/", [
        {"selector": ".prose", "edge": "bottom", "offset": 20, "wait": 900},  # the text's end is just below
        {"selector": ".prose", "edge": "bottom", "offset": -20, "wait": 2},
    ])
    assert "finished" not in got[0]
    assert "finished" in got[1]


@needs_browser
def test_on_a_wide_screen_halfway_waits_for_the_last_margin_note(counted_site):
    # From 1500px wide the "From the table" notes float in the margin, and this post's last one runs
    # on below the Key Locations heading: the account is not all on screen until the note is.
    _, root = counted_site
    got = scroll(f"{root}/posts/{NOTED}/", [
        {"selector": "#key-locations", "offset": -20, "wait": 2},
        {"selector": ".prose > aside.margin-note:has(+ #key-locations)", "edge": "bottom", "offset": 30, "wait": 2},
        {"selector": ".prose > aside.margin-note:has(+ #key-locations)", "edge": "bottom", "offset": -10, "wait": 2},
    ], width=1600)
    assert "halfway" not in got[0] + got[1]
    assert "halfway" in got[2]


# The same script under Node with a pretend page, so the rules are checked wherever Node is (the
# Checks workflow too), not only where Playwright is. Boxes are [top, bottom] on the page.
FAKE_PAGE = r"""
const vm = require("vm");
const [script, pageJson] = process.argv.slice(1);
const page = JSON.parse(pageJson);
let scrollY = 0, timers = [], handlers = [];
const sent = [];
const rect = box => ({top: box[0] - scrollY, bottom: box[1] - scrollY});
const prose = {nodeType: 1, dataset: {readMinutes: String(page.minutes)}, getBoundingClientRect: () => rect(page.prose)};
const kids = page.nodes.map(n => n.comment !== undefined
  ? {nodeType: 8, data: n.comment, parentNode: prose}
  : {nodeType: 1, parentNode: prose, getBoundingClientRect: () => rect(n.box)});
kids.forEach((k, i) => { k.nextSibling = kids[i + 1] || null; });
const map = page.map ? {getBoundingClientRect: () => rect(page.map)} : null;
const context = {
  NodeFilter: {SHOW_COMMENT: 128},
  location: {pathname: "/posts/x/"},
  window: {innerHeight: 800, addEventListener: (name, f) => handlers.push(f)},

  document: {
    title: "X", visibilityState: "visible", addEventListener: () => {},
    querySelector: sel => sel === ".prose[data-read-minutes]" ? prose : sel === ".where-we-were .map-figure" ? map : null,
    createTreeWalker: () => { const c = kids.filter(k => k.nodeType === 8); let i = 0; return {nextNode: () => c[i++] || null}; },
  },
  Image: class { set src(url) { sent.push(new URL(url).searchParams.get("p").split("/").pop()); } },

  setInterval: f => { timers.push(f); return timers.length; },
  clearInterval: id => { timers[id - 1] = null; },
  Math, Number, String, encodeURIComponent, URL,
};
context.gtag = (kind, name) => sent.push("ga:" + kind + ":" + name);
if (page.gtag !== false) context.window.gtag = context.gtag; else delete context.gtag;
vm.runInNewContext(script, context);
const out = [];
for (const step of page.steps) {
  scrollY = step.scroll;
  handlers.forEach(f => f());
  for (let s = 0; s < step.wait; s++) timers.forEach(f => f && f());
  out.push(sent.splice(0));
}
process.stdout.write(JSON.stringify(out));
"""

# A one-minute post: the account's last block ends at 1500 and its margin note at 1700, the recap
# lists run to 2200 and the map starts at 2400. The screen is 800 tall.
ACCOUNT = [{"comment": "story"}, {"box": [0, 900]}, {"box": [900, 1500]}, {"box": [1400, 1700]},
           {"comment": "story-end"}, {"box": [1550, 2200]}]


def fake_read(steps, nodes=ACCOUNT, map_box=(2400, 2900), prose=(0, 2200), script=None, gtag=True) -> list[list[str]]:
    page = {"minutes": 1, "prose": list(prose), "nodes": nodes, "map": list(map_box) if map_box else None,
            "steps": steps, "gtag": gtag}
    done = subprocess.run([NODE, "-e", FAKE_PAGE, script or reading_js(), json.dumps(page)], capture_output=True,
                          text=True, encoding="utf-8", timeout=60)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


@needs_node
def test_halfway_is_the_bottom_of_the_account_and_its_notes():
    got = fake_read([{"scroll": 0, "wait": 1}, {"scroll": 800, "wait": 1}, {"scroll": 899, "wait": 1},
                     {"scroll": 900, "wait": 1}])
    assert got[0] == [] and got[1] == []  # the recap heading (1550) is on screen, the note (1700) not yet
    assert got[2] == []
    assert got[3] == ["halfway"]


@needs_node
def test_finished_is_the_map_after_half_the_reading_time():
    got = fake_read([{"scroll": 1500, "wait": 40}, {"scroll": 1601, "wait": 1}, {"scroll": 0, "wait": 1}])
    assert got[0] == ["halfway", "started"]  # the end of the text (2200) is on screen, the map (2400) not
    assert got[1] == ["finished"]
    assert got[2] == []  # each event once a visit


@needs_node
def test_finished_waits_for_half_the_reading_time():
    got = fake_read([{"scroll": 1700, "wait": 20}, {"scroll": 1700, "wait": 11}])
    assert got[0] == ["halfway"]
    assert got[1] == ["started", "finished"]


@needs_node
def test_without_a_map_or_marks_the_end_of_the_text_counts():
    got = fake_read([{"scroll": 1399, "wait": 31}, {"scroll": 1400, "wait": 1}],
                    nodes=[{"box": [0, 2200]}], map_box=None)
    assert got[0] == ["started"]
    assert got[1] == ["halfway", "finished"]


@needs_node
def test_each_read_event_also_goes_to_google_analytics_once():
    """With GA4 on (Chris, 2026-11-04) every GoatCounter read event is also a GA4 event: read_started,
    read_halfway, read_finished, each still once a visit."""
    script = reading_js(ga="G-TEST123AB")
    got = fake_read([{"scroll": 1500, "wait": 40}, {"scroll": 1601, "wait": 1}, {"scroll": 0, "wait": 1}],
                    script=script)
    assert got[0] == ["halfway", "ga:event:read_halfway", "started", "ga:event:read_started"]
    assert got[1] == ["finished", "ga:event:read_finished"]
    assert got[2] == []


@needs_node
def test_google_analytics_alone_still_gets_read_events():
    got = fake_read([{"scroll": 1700, "wait": 31}], script=reading_js(counter="", ga="G-TEST123AB"))
    assert got[0] == ["ga:event:read_halfway", "ga:event:read_started", "ga:event:read_finished"]


@needs_node
def test_read_events_without_googles_tag_still_reach_goatcounter():
    """If the inline GA setup is ever missing, the reading script keeps going instead of throwing."""
    page = {"minutes": 1, "prose": [0, 2200], "nodes": ACCOUNT, "map": [2400, 2900], "gtag": False,
            "steps": [{"scroll": 1700, "wait": 31}]}
    done = subprocess.run([NODE, "-e", FAKE_PAGE, reading_js(ga="G-TEST123AB"), json.dumps(page)],
                          capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout) == [["halfway", "started", "finished"]]
