"""Section headings link to themselves (Chris, 2026-11-04), so readers can share a link like
/start/#story without hunting for it on the home page.

`link_headings` runs on every page the build writes. Each h2 and h3 in <main> gets an id if it has
none, and a small link icon after its words that points at its section: the <section> it labels when
there is one (the home page's buttons already go to /start/#story, not #story-title), else the heading.
Such a section is then named by a span around the heading's words, so screen readers don't read the
link's label as part of the section's name.
Headings that are links themselves (cards, the map's place title) and anything in a <script> are left
alone. A small script in base.html copies the address when the icon is tapped; without it the link
still works and the address bar shows it.
"""

from __future__ import annotations

import html as htmllib
import re

import article
import wiki

HEADING = re.compile(r"<h([23])([^>]*)>(.*?)</h\1>", re.S)
SCRIPT = re.compile(r"(<script\b.*?</script>)", re.S)
MAIN = re.compile(r"(<main\b[^>]*>)(.*)(</main>)", re.S)
ID = re.compile(r"""\sid=["']([^"']+)["']""")
UNNAMED_SECTION = re.compile(r'(<section\b(?![^>]*aria-labelledby)[^>]*\sid="([^"]+)"[^>]*)(>\s*<h[23])([^>]*>)')
ICON = ('<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">'
        '<path d="M10 14a4.5 4.5 0 0 0 6.4 0l3-3a4.5 4.5 0 0 0-6.4-6.4l-1.2 1.2"/>'
        '<path d="M14 10a4.5 4.5 0 0 0-6.4 0l-3 3a4.5 4.5 0 0 0 6.4 6.4l1.2-1.2"/></svg>')


def _sections(page: str) -> dict[str, str]:
    """{heading id: section id} for each <section> that names its heading with aria-labelledby."""
    found = {}
    for tag in re.findall(r"<section\b[^>]*>", page):
        sid, label = re.search(r'\sid="([^"]+)"', tag), re.search(r'\saria-labelledby="([^"]+)"', tag)
        if sid and label:
            found[label.group(1)] = sid.group(1)
    return found


def _name_sections(body: str) -> str:
    """A <section id> that opens with its heading is labelled by it, so the heading links to the section
    (the tags page's #wolves)."""
    def name(m: re.Match) -> str:
        own = ID.search(m.group(4))
        label = own.group(1) if own else f"{m.group(2)}-title"
        attrs = m.group(4) if own else f' id="{label}"{m.group(4)}'
        return f'{m.group(1)} aria-labelledby="{label}"{m.group(3)}{attrs}'
    return UNNAMED_SECTION.sub(name, body)


def link_headings(page: str) -> str:
    m = MAIN.search(page)
    if not m:
        return page
    parts = SCRIPT.split(m.group(2))
    parts = [p if i % 2 else _name_sections(p) for i, p in enumerate(parts)]
    page = page[:m.start(2)] + "".join(parts) + page[m.end(2):]
    m = MAIN.search(page)
    used = set(ID.findall(page))
    sections = _sections(page)
    renamed = {}

    def link(h: re.Match) -> str:
        level, attrs, inner = h.group(1), h.group(2), h.group(3)
        if "<a " in inner:
            return h.group(0)
        text = wiki.plain_text(inner).strip()
        if not text:
            return h.group(0)
        own = ID.search(attrs)
        if own:
            anchor = own.group(1)
        else:
            base = anchor = article.slug(text)
            n = 2
            while anchor in used:
                anchor, n = f"{base}-{n}", n + 1
            used.add(anchor)
            attrs = f'{attrs} id="{anchor}"'
        target = sections.get(anchor, anchor)
        if target != anchor:  # the section is named by the heading's words alone, not the link's label too
            renamed[anchor] = f"{anchor}-name"
            inner = f'<span id="{anchor}-name">{inner}</span>'
        label = htmllib.escape(f"Link to this section: {text}")
        return (f'<h{level}{attrs}>{inner}<a class="heading-link" href="#{target}" aria-label="{label}">'
                f"{ICON}</a></h{level}>")

    parts = SCRIPT.split(m.group(2))
    body = "".join(p if i % 2 else HEADING.sub(link, p) for i, p in enumerate(parts))
    for old, new in renamed.items():
        body = body.replace(f'aria-labelledby="{old}"', f'aria-labelledby="{new}"')
    return page[:m.start()] + m.group(1) + body + m.group(3) + page[m.end():]
