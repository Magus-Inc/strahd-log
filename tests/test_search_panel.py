"""Search from every page (Chris, 2026-11-04: "Can we make search easier to access especially on mobile.
Feels like it takes so many extra clicks and page loads").

Every page's header has a magnifier (phones) and a Search link (wider screens) that open a search panel
over the page: one tap, the keyboard comes up, results show as you type, and no page loads until a result
is chosen. Without the script both are plain links to the search page. The browser test drives the
built site in Chromium when Node's Playwright is installed (the cloud sessions have it; CI skips it).
"""
import functools
import http.server
import json
import re
import shutil
import subprocess
import threading

import pytest

import build

TEMPLATES = build.ROOT / "templates"


@pytest.fixture(scope="module")
def site(real_build):
    return real_build.out


def pages(site):
    for page in sorted(site.rglob("*.html")):
        html = page.read_text(encoding="utf-8")
        if 'class="site-header"' in html:  # forwarding pages have no header
            yield page.relative_to(site).as_posix(), html


def test_every_page_has_a_search_button_that_works_without_the_script(site):
    count = 0
    for name, html in pages(site):
        count += 1
        header = re.search(r'<header class="site-header">.*?</header>', html, re.S).group(0)
        button = re.search(r'<a class="search-button" href="([^"]+)"([^>]*)>', header)
        assert button, name
        assert button.group(1) == "/search/" and 'aria-label="Search"' in button.group(2) and "data-search-open" in button.group(2)
        assert re.search(r'<a class="nav-search" href="/search/" data-search-open', header), name
    assert count > 300


def test_every_page_carries_one_search_panel_and_one_matcher(site):
    for name, html in pages(site):
        assert html.count('<dialog class="search-panel"') == 1, name
        assert html.count("var SearchMatch =") == 1 and html.count("var SearchResults =") == 1, name
        panel = re.search(r'<dialog class="search-panel".*?</dialog>', html, re.S).group(0)
        # Without the script, Enter in the panel still searches on the search page.
        assert '<form class="search-panel-bar" action="/search/" method="get" role="search">' in panel
        assert re.search(r'<input id="site-search-q" name="q" type="search" enterkeyhint="search"', panel)


def test_the_index_is_fetched_only_when_search_is_used():
    """search-index.json is over half a megabyte: reading a post must not download it."""
    panel = (TEMPLATES / "_search_panel.html").read_text(encoding="utf-8")
    script = panel.split("<script data-search-panel>")[1]
    own = script.split('{% endfilter %}')[1]
    assert own.count('fetch(base + "search-index.json")') == 1
    load = re.search(r"function load\(\) \{.*?\n      \}", own, re.S).group(0)
    assert "fetch(" in load
    assert "load()" not in own.replace(load, "").split("function open()")[0], "nothing calls load() before open()"


def test_phones_show_the_magnifier_and_drop_search_from_the_menu():
    css = (build.ROOT / "static" / "style.css").read_text(encoding="utf-8")
    assert re.search(r"\n\.search-button \{[^}]*display: none", css)
    phone = re.search(r"@media \(max-width: 719px\) \{\n  \.search-button \{ display: block; \}\n  \.site-nav \.nav-search \{ display: none; \}", css)
    assert phone
    # The panel takes the whole phone screen.
    assert re.search(r"@media \(max-width: 719px\) \{\n  dialog\.search-panel \{ width: 100vw; height: 100vh; height: 100dvh;", css)


def test_the_search_page_waits_for_the_shared_script():
    """search.html's script needs SearchMatch and SearchResults, which the panel defines: it must run after it."""
    base = (TEMPLATES / "base.html").read_text(encoding="utf-8")
    assert base.index('{% include "_search_panel.html" %}') < base.index("{% block scripts %}")
    page = (TEMPLATES / "search.html").read_text(encoding="utf-8")
    assert page.index("{% block scripts %}") < page.index("SearchMatch.search(")


# --- in a real browser ----------------------------------------------------------------------------

NODE = shutil.which("node")


def has_playwright() -> bool:
    if not NODE:
        return False
    return subprocess.run([NODE, "-e", "require('playwright')"], capture_output=True).returncode == 0


needs_browser = pytest.mark.skipif(not has_playwright(), reason="Node's Playwright is needed to drive Chromium")

BROWSER = r"""
const {chromium} = require("playwright");
const [root, post] = process.argv.slice(1);
(async () => {
  const browser = await chromium.launch();
  const out = {};
  try {
    // An iPhone-sized screen with touch.
    const phone = await browser.newContext({viewport: {width: 390, height: 844}, hasTouch: true, isMobile: true});
    const page = await phone.newPage();
    const asked = [];
    page.on("request", r => asked.push(new URL(r.url()).pathname));
    await page.goto(root + post);
    out.menuSearchShown = await page.locator(".site-nav .nav-search").isVisible();
    out.buttonShown = await page.locator(".search-button").isVisible();
    out.indexBeforeTap = asked.includes("/search-index.json");
    const url = page.url();
    await page.locator(".search-button").tap();
    out.panelOpen = await page.locator("dialog.search-panel").evaluate(d => d.open);
    out.focused = await page.evaluate(() => document.activeElement && document.activeElement.id);
    await page.keyboard.type("Ireena");
    await page.locator(".search-panel-results li").first().waitFor();
    out.results = await page.locator(".search-panel-results li").count();
    out.status = await page.locator(".search-panel-status").textContent();
    out.firstHref = await page.locator(".search-panel-results li a.stretched").first().getAttribute("href");
    await page.keyboard.press("Enter");
    out.sameUrlAfterEnter = page.url() === url;
    out.focusedAfterEnter = await page.evaluate(() => document.activeElement && document.activeElement.id);
    await page.locator(".search-panel-close").tap();
    out.closed = await page.locator("dialog.search-panel").evaluate(d => !d.open);
    // A result, then Back to the post, and one tap brings the same search back.
    await page.locator(".search-button").tap();
    await page.locator(".search-panel-results li a.stretched").first().click();
    await page.waitForURL(u => u.pathname === out.firstHref);
    await page.goBack();
    await page.waitForURL(url);
    if (!await page.locator("dialog.search-panel").evaluate(d => d.open)) await page.locator(".search-button").tap();
    out.remembered = await page.locator("#site-search-q").inputValue();
    await phone.close();

    // A wide screen: "Search" in the bar opens the same panel, "/" too, and Esc closes it.
    const desk = await browser.newContext({viewport: {width: 1280, height: 900}});
    const wide = await desk.newPage();
    await wide.goto(root + post);
    out.deskButtonShown = await wide.locator(".search-button").isVisible();
    await wide.locator(".site-nav .nav-search").click();
    out.deskPanelOpen = await wide.locator("dialog.search-panel").evaluate(d => d.open);
    await wide.keyboard.press("Escape");
    out.deskClosedByEsc = await wide.locator("dialog.search-panel").evaluate(d => !d.open);
    await wide.keyboard.press("/");
    out.slashOpens = await wide.locator("dialog.search-panel").evaluate(d => d.open);
    // On the search page itself the button uses the page's own box.
    await wide.goto(root + "search/?q=strahd");
    await wide.locator(".site-nav .nav-search").click();
    out.searchPageFocus = await wide.evaluate(() => document.activeElement.id);
    out.searchPagePanel = await wide.locator("dialog.search-panel").evaluate(d => d.open);
    await desk.close();

    // No script: the magnifier is a link to the search page.
    const bare = await browser.newContext({viewport: {width: 390, height: 844}, javaScriptEnabled: false});
    const plain = await bare.newPage();
    await plain.goto(root + post);
    await plain.locator(".search-button").click();
    out.noScriptLandsOn = new URL(plain.url()).pathname;
    await bare.close();
  } finally {
    await browser.close();
  }
  process.stdout.write(JSON.stringify(out));
})();
"""


@pytest.fixture(scope="module")
def served(site):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(site))
    handler.log_message = lambda *a: None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/"
    server.shutdown()


@needs_browser
def test_search_in_a_browser(served, real_build):
    post = f"posts/{real_build.posts[0].slug}/"
    done = subprocess.run([NODE, "-e", BROWSER, served, post], capture_output=True, text=True, encoding="utf-8", timeout=180)
    assert done.returncode == 0, done.stderr
    out = json.loads(done.stdout)
    # Phone: one tap opens the panel with the keyboard's box focused, and nothing big loads before it.
    assert out["buttonShown"] and not out["menuSearchShown"]
    assert not out["indexBeforeTap"]
    assert out["panelOpen"] and out["focused"] == "site-search-q"
    assert out["results"] > 0 and "match" in out["status"]
    assert out["sameUrlAfterEnter"] and out["focusedAfterEnter"] != "site-search-q"  # Enter just hides the keyboard
    assert out["closed"]
    assert out["remembered"] == "Ireena"
    # Wide screen.
    assert not out["deskButtonShown"]
    assert out["deskPanelOpen"] and out["deskClosedByEsc"] and out["slashOpens"]
    assert out["searchPageFocus"] == "q" and not out["searchPagePanel"]
    # No script.
    assert out["noScriptLandsOn"] == "/search/"
