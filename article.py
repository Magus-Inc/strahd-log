"""Reading aids for a rendered session post: reading time, table of contents, the "At a Glance"
callout, a short teaser for the session cards, and who was at the table.

Every function takes the post's rendered HTML (after wiki links are added) and returns either a
value or new HTML; none of them change the Markdown the players wrote.
"""

from __future__ import annotations

import html as htmllib
import re

import wiki

WORDS_PER_MINUTE = 230
GLANCE = re.compile(r"at a glance", re.I)


def reading_minutes(html: str) -> int:
    return max(1, round(len(wiki.plain_text(html).split()) / WORDS_PER_MINUTE))


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "section"


def add_heading_ids(html: str) -> tuple[str, list[dict]]:
    """Give every h2 and h3 an id; return (html, [{level, id, text}]) for a table of contents."""
    toc, used = [], set()

    def name(m: re.Match) -> str:
        level, attrs, inner = int(m.group(1)), m.group(2), m.group(3)
        text = wiki.plain_text(inner).rstrip(":").strip()
        anchor = slug(text)
        base, n = anchor, 2
        while anchor in used:
            anchor, n = f"{base}-{n}", n + 1
        used.add(anchor)
        toc.append({"level": level, "id": anchor, "text": text})
        if "id=" in attrs:
            return m.group(0)
        return f'<h{level}{attrs} id="{anchor}">{inner}</h{level}>'

    return re.sub(r"<h([23])([^>]*)>(.*?)</h\1>", name, html, flags=re.S), toc


def glance_items(html: str) -> list[str]:
    """The <li> contents of the list right after an "At a Glance" heading, as HTML."""
    m = re.search(r"<h[1-6][^>]*>(?:(?!</h).)*at a glance(?:(?!</h).)*</h[1-6]>\s*<ul>(.*?)</ul>", html, re.I | re.S)
    if not m:
        return []
    return [li.strip() for li in re.findall(r"<li>(.*?)</li>", m.group(1), re.S)]


def wrap_glance(html: str) -> str:
    """Put the "At a Glance" heading and its list in a callout box."""
    return re.sub(r"(<h[1-6][^>]*>(?:(?!</h).)*at a glance(?:(?!</h).)*</h[1-6]>\s*<ul>.*?</ul>)",
                  r'<aside class="callout glance">\1</aside>', html, count=1, flags=re.I | re.S)


NOTE = re.compile(r"<p>(?:<strong>)?Note:\s*(?:</strong>)?\s*(.*?)(?:</strong>)?</p>", re.S)


def margin_notes(html: str) -> str:
    """Turn each "Note:" paragraph into a table note, written in a second hand beside Malron's
    journal: what was said at the table, curated by Chris, as against what happened in Barovia."""
    def note(m: re.Match) -> str:
        text = m.group(1).strip()
        text = re.sub(r"^\[Meta details\]\s*", "", text)
        if text.startswith("[") and text.endswith("]"):
            text = text[1:-1].strip()
        text = re.sub(r"^Meta details:\s*", "", text)
        return f'<aside class="margin-note" aria-label="From the table"><p>{text}</p></aside>'
    return NOTE.sub(note, html)


def add_deck(html: str, slides: list[str], pdf: str = "") -> str:
    """Put the session's slide deck (root-relative image paths, in order) right after the "At a
    Glance" callout, or before the first section heading when there is none: a strip that swipes on a phone, with a link
    to the PDF when there is one."""
    if not slides:
        return html
    n = len(slides)
    items = "".join(f'<li><img src="/{escape(src)}" alt="Slide {i} of {n}" loading="lazy" decoding="async"></li>'
                    for i, src in enumerate(slides, 1))
    link = f' &middot; <a href="/{escape(pdf)}" download>Download PDF</a>' if pdf else ""
    deck = ('<section class="deck" aria-label="Session slides">\n<h2>The Slides</h2>\n'
            f'<ol class="deck-strip">{items}</ol>\n'
            f'<p class="deck-meta"><span class="deck-count">1 / {n}</span>'
            f'<span class="deck-hint"> &middot; swipe, or tap a slide to enlarge</span>{link}</p>\n</section>\n')
    m = re.search(r'<aside class="callout glance">.*?</aside>\n?', html, re.S)
    if m:
        at = m.end()
    else:
        h2 = re.search(r"<h2[ >]", html)
        at = h2.start() if h2 else 0
    return html[:at] + deck + html[at:]


def teaser(html: str, limit: int = 150) -> str:
    """One or two plain-text lines for a session card: the first glance bullet, else the first paragraph."""
    items = glance_items(html)
    if items:
        text = wiki.plain_text(items[0])
    else:
        m = re.search(r"<p>(.*?)</p>", html, re.S)
        text = wiki.plain_text(m.group(1)) if m else wiki.plain_text(html)
    text = re.sub(r"^[^:]{1,40}:\s*", "", text)  # "Reunion: Liren and Gumbo rise..." -> "Liren and Gumbo rise..."
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(",;:.")
    return cut + "…"


def cast(post_mentions: set[str], pages: list[wiki.WikiPage]) -> list[wiki.WikiPage]:
    """Player characters this post mentions, for the cast pills."""
    return sorted((p for p in pages if p.type == "character" and p.slug in post_mentions), key=lambda p: p.title)


def escape(text: str) -> str:
    return htmllib.escape(text, quote=True)
