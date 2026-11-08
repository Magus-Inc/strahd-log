"""Who is not counted (Chris, 2026-11-08: his reports were mostly his own visits and scans).

Browsers that say they are automated (`navigator.webdriver`, as headless scanners and test tools do)
load no Google Analytics and send nothing to GoatCounter. Opening any page with `?notrack=1` marks that
browser as Chris's own and it counts nothing from then on; `?notrack=0` turns counting back on. The
choice lives in the browser's localStorage; blocked storage must not break the page or stop counting.

templates/_no_count.js sets `window.dontCount`; GA's loader, the page-view pixel, votes and read
events all check it. The script runs under plain Node against a pretend browser, and the whole page
runs in headless Chromium through Node's Playwright where it is installed.
"""
import functools
import http.server
import json
import shutil
import subprocess
import threading

import jinja2
import pytest

import build
from test_build import write_post
from test_read_depth import ACCOUNT, NODE, fake_read, has_playwright, needs_node, reading_js

needs_browser = pytest.mark.skipif(not has_playwright(), reason="Node with Playwright and Chromium is needed")


def no_count_js() -> str:
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(build.ROOT / "templates"))
    return env.get_template("_no_count.js").render()


# Run _no_count.js once per visit against one pretend browser and report window.dontCount and what
# localStorage holds after each visit. storage "blocked" throws on every use, as Safari's private
# mode and blocked site data do.
FAKE_BROWSER = r"""
const vm = require("vm");
const [script, json] = process.argv.slice(1);
const setup = JSON.parse(json);
const held = {};
const storage = setup.storage === "blocked"
  ? {getItem() { throw new Error("blocked"); }, setItem() { throw new Error("blocked"); }, removeItem() { throw new Error("blocked"); }}
  : {getItem: k => (k in held ? held[k] : null), setItem: (k, v) => { held[k] = String(v); }, removeItem: k => { delete held[k]; }};
const out = [];
for (const search of setup.visits) {
  const window = {};
  const context = {window, navigator: {webdriver: !!setup.webdriver}, location: {search}, URLSearchParams};
  Object.defineProperty(window, "localStorage", {get: () => storage});
  Object.defineProperty(context, "localStorage", {get: () => storage});
  vm.runInNewContext(script, context);
  out.push({dontCount: window.dontCount, stored: {...held}});
}
process.stdout.write(JSON.stringify(out));
"""


def visit(visits, webdriver=False, storage="ok"):
    done = subprocess.run([NODE, "-e", FAKE_BROWSER, no_count_js(),
                           json.dumps({"visits": visits, "webdriver": webdriver, "storage": storage})],
                          capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


@needs_node
def test_an_ordinary_browser_counts():
    assert visit([""]) == [{"dontCount": False, "stored": {}}]


@needs_node
def test_an_automated_browser_never_counts():
    got = visit(["", "?notrack=0"], webdriver=True)
    assert [v["dontCount"] for v in got] == [True, True]


@needs_node
def test_notrack_is_remembered_until_turned_off():
    got = visit(["?notrack=1", "", "?page=2", "?notrack=0", ""])
    assert [v["dontCount"] for v in got] == [True, True, True, False, False]
    assert got[0]["stored"] == {"notrack": "1"}
    assert got[3]["stored"] == {}


@needs_node
def test_other_notrack_values_change_nothing():
    got = visit(["?notrack=yes", "?notrack=1", "?notrack=", "?notrack=true"])
    assert [v["dontCount"] for v in got] == [False, True, True, True]


@needs_node
def test_blocked_storage_does_not_break_the_page_or_stop_counting():
    got = visit(["", "?notrack=0", "?notrack=1", ""], storage="blocked")
    # Counting goes on; ?notrack=1 still keeps the page it is on out, but cannot be remembered.
    assert [v["dontCount"] for v in got] == [False, False, True, False]


def test_every_counter_checks_dont_count():
    base = (build.ROOT / "templates" / "base.html").read_text(encoding="utf-8")
    reading = (build.ROOT / "templates" / "_read_depth.js").read_text(encoding="utf-8")
    assert "if (!window.dontCount)" in base.split("<head>")[1].split("googletagmanager")[0]  # GA's loader
    assert "if (!window.dontCount) new Image()" in base.split("// Votes:")[1].split("</script>")[0]
    assert "if (window.dontCount) return;" in base.split("// Page-view count")[1]
    assert "if (!window.dontCount)" in reading
    head = base.split("</head>")[0]
    assert '{% include "_no_count.js" %}' in head
    assert head.index('{% include "_no_count.js" %}') < head.index("googletagmanager")
    assert '<script async src="https://www.googletagmanager.com' not in base  # GA loads only from the check


@needs_node
def test_read_events_go_nowhere_when_not_counting():
    script = reading_js(ga="G-TEST123AB")
    # GA's gtag is never defined when not counting (gtag False), so nothing at all is sent.
    got = fake_read([{"scroll": 1500, "wait": 40}], script="window.dontCount = true;\n" + script, gtag=False)
    assert got == [[]]


# The whole page in Chromium, built with both counters on.

PAGE_RUN = r"""
const {chromium} = require("playwright");
(async () => {
  const [root, stepsJson] = process.argv.slice(1);
  const browser = await chromium.launch();
  const out = [];
  const context = await browser.newContext();
  const page = await context.newPage();
  const sent = [];
  await context.route(/goatcounter\.com|googletagmanager\.com|google-analytics\.com/, route => {
    const u = new URL(route.request().url());
    sent.push(u.hostname.includes("goatcounter") ? "goatcounter" : u.hostname.includes("googletagmanager") ? "gtag.js" : "ga");
    route.fulfill({status: 200, contentType: "text/javascript", body: ""});
  });
  for (const step of JSON.parse(stepsJson)) {
    if (step.human) await page.addInitScript(() => Object.defineProperty(Navigator.prototype, "webdriver", {get: () => false}));
    await page.goto(root + step.path);
    await page.waitForLoadState("load");
    await page.waitForTimeout(300);
    // gtag.js reads its queue only as Arguments objects; arrays would be ignored.
    const queue = await page.evaluate(() => (window.dataLayer || []).map(e => [Object.prototype.toString.call(e), e[0]]));
    out.push({sent: [...new Set(sent.splice(0))].sort(), dontCount: await page.evaluate(() => window.dontCount), queue});
  }
  await browser.close();
  process.stdout.write(JSON.stringify(out));
})().catch(e => { console.error(e); process.exit(1); });
"""


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture
def counted(tmp_path, monkeypatch):
    folder = tmp_path / "content"
    write_post(folder, "2024-01-09-first.md", "title: First Night\ndate: '2024-01-09T21:00:00-06:00'\nslug: first\n",
               "## Arrival\n\nMist.\n")
    monkeypatch.setenv("GOATCOUNTER", "owlbear")
    monkeypatch.setenv("GOOGLE_ANALYTICS", "G-TEST123AB")
    out = tmp_path / "public"
    build.build(folder, out, site_url="https://log.example")
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(out)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def run_pages(root, steps):
    done = subprocess.run([NODE, "-e", PAGE_RUN, root, json.dumps(steps)], capture_output=True, text=True,
                          encoding="utf-8", timeout=120)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


@needs_browser
def test_a_headless_scanner_loads_no_analytics(counted):
    got = run_pages(counted, [{"path": "/posts/first/"}])  # Playwright's Chromium reports webdriver
    assert got == [{"sent": [], "dontCount": True, "queue": []}]


@needs_browser
def test_a_reader_counts_and_notrack_turns_it_off_and_on(counted):
    got = run_pages(counted, [{"path": "/posts/first/", "human": True}, {"path": "/?notrack=1"},
                              {"path": "/posts/first/"}, {"path": "/?notrack=0"}, {"path": "/posts/first/"}])
    assert got[0]["sent"] == ["goatcounter", "gtag.js"] and got[0]["dontCount"] is False
    assert got[0]["queue"][:2] == [["[object Arguments]", "js"], ["[object Arguments]", "config"]]
    assert got[1] == {"sent": [], "dontCount": True, "queue": []}
    assert got[2] == {"sent": [], "dontCount": True, "queue": []}  # remembered on a later page
    assert got[3]["sent"] == ["goatcounter", "gtag.js"]
    assert got[4]["sent"] == ["goatcounter", "gtag.js"]
