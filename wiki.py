"""The campaign wiki: characters, NPCs, places, items and factions, one Markdown file each.

content/wiki/<slug>.md has YAML front matter (title, type, aliases, summary, player, narrator, source,
obsidian_portal_url) and a Markdown body. The build links the first mention of any page's title or
alias in each post and wiki page, and lists on every wiki page the posts that mention it.
"""

from __future__ import annotations

import html as htmllib
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

# Display order and headings for the wiki index.
TYPES = {
    "character": "Player characters",
    "npc": "People",
    "creature": "Creatures",
    "place": "Places",
    "item": "Items",
    "faction": "Factions",
    "deity": "Deities",
    "other": "Lore and events",
}
# One-word label for search results.
LABELS = {
    "character": "Player character", "npc": "Person", "creature": "Creature", "place": "Place",
    "item": "Item", "faction": "Faction", "deity": "Deity", "other": "Lore",
}

# The note tools/wiki_from_extract.py puts above compiled facts; left out of the search index.
LOG_NOTE = "From the adventure log Compiled from the session posts. Each line links to the session it comes from."

# Tags whose text is never auto-linked: existing links, headings, code.
SKIP_TAGS = {"a", "h1", "h2", "h3", "h4", "h5", "h6", "code", "pre", "script", "style"}


PICTURE = re.compile(r"!\[[^\]]*\]\(\s*<?([^)\s>]+)")


@dataclass
class WikiPage:
    slug: str
    title: str
    type: str = "other"
    aliases: list[str] = field(default_factory=list)
    summary: str = ""
    player: str = ""
    former: bool = False  # a player character no longer played
    narrator: bool = False  # writes the log, so is at every session even when no post names him
    source: str = ""
    obsidian_portal_url: str = ""
    body_md: str = ""
    html: str = ""
    mentioned_in: list = field(default_factory=list)  # posts, newest first
    cited_html: str = ""  # html with "(Session Title)" links as session numbers, set by the build
    top_picture: str = ""  # the first picture and its caption, when the wiki layout puts it at the top
    facts: list = field(default_factory=list)  # the facts box (wikistyle.facts), when the layout has one
    thumb: str = ""  # small copy of the first picture for list cards (images/thumbs/...), set by the build

    @property
    def path(self) -> str:
        return f"wiki/{self.slug}/"

    @property
    def pictures(self) -> list[str]:
        """Images in the page's own text, in order; list pages badge a page that has any."""
        return PICTURE.findall(self.body_md)

    @property
    def names(self) -> list[str]:
        return [self.title, *self.aliases]


def parse_wiki_page(path: Path, split_front_matter) -> WikiPage:
    meta, body = split_front_matter(path.read_text(encoding="utf-8"))
    if "title" not in meta:
        raise ValueError(f"{path.name}: front matter has no title")
    kind = str(meta.get("type") or "other").lower()
    if kind not in TYPES:
        raise ValueError(f"{path.name}: unknown type {kind!r} (use one of {', '.join(TYPES)})")
    aliases = meta.get("aliases") or []
    if isinstance(aliases, str):
        aliases = [a.strip() for a in aliases.split(",") if a.strip()]
    return WikiPage(
        slug=str(meta.get("slug") or path.stem),
        title=str(meta["title"]),
        type=kind,
        aliases=[str(a) for a in aliases],
        summary=str(meta.get("summary") or ""),
        player=str(meta.get("player") or ""),
        former=bool(meta.get("former")),
        narrator=bool(meta.get("narrator")),
        source=str(meta.get("source") or ""),
        obsidian_portal_url=str(meta.get("obsidian_portal_url") or ""),
        body_md=body,
    )


def load_wiki(wiki_dir: Path, split_front_matter) -> list[WikiPage]:
    if not wiki_dir.is_dir():
        return []
    pages = [parse_wiki_page(p, split_front_matter) for p in sorted(wiki_dir.glob("*.md"))]
    slugs = [p.slug for p in pages]
    dupes = {s for s in slugs if slugs.count(s) > 1}
    if dupes:
        raise ValueError(f"duplicate wiki slugs: {', '.join(sorted(dupes))}")
    seen: dict[str, str] = {}
    for page in pages:
        for name in page.names:
            other = seen.setdefault(name, page.slug)
            if other != page.slug:
                raise ValueError(f"wiki name {name!r} is used by both {other} and {page.slug}")
    return sorted(pages, key=lambda p: p.title.lower())


# An HTML tag, allowing ">" inside quoted attribute values.
TAG = re.compile(r"""(<(?:[^>"']|"[^"]*"|'[^']*')*>)""")
# Markdown's smarty extension turns ' into &rsquo; and & into &amp;; a name written either way
# should match text written either way.
APOSTROPHES = "(?:'|’|‘|&rsquo;|&lsquo;|&#8217;|&#39;)"
AMPERSAND = "(?:&amp;|&)"


def fold(name: str) -> str:
    """A name as text, with curly apostrophes straightened: the key names are matched under."""
    return htmllib.unescape(name).replace("’", "'").replace("‘", "'")


def name_pattern(name: str) -> str:
    parts = []
    for ch in name:
        parts.append(APOSTROPHES if ch == "'" else AMPERSAND if ch == "&" else re.escape(ch))
    return "".join(parts)


class Linker:
    """Finds wiki names in rendered HTML and links the first mention of each page."""

    def __init__(self, pages: list[WikiPage]):
        self.by_name = {fold(name): page for page in pages for name in page.names}
        names = sorted(self.by_name, key=len, reverse=True)  # longest first: "Rose Durst" before "Rose"
        alternation = "|".join(name_pattern(n) for n in names)
        self.pattern = re.compile(rf"(?<!\w)({alternation})(?!\w)") if names else None
        self.by_href = {f"/wiki/{p.slug}/": p for p in pages}

    def link(self, html: str, self_slug: str | None = None, each_section: str | None = None) -> tuple[str, set[str]]:
        """Return (html with first mentions linked, slugs of every page mentioned). With each_section,
        a pattern for the tags that start a section (headings), the first mention in every section
        links, so a reader who jumps to a section finds the links there."""
        if self.pattern is None:
            return html, set()
        if each_section:
            parts = re.split(f"(?={each_section})", html)
            done = [self.link(part, self_slug) for part in parts]
            return "".join(h for h, _ in done), set().union(*(m for _, m in done))
        mentioned: set[str] = set()
        # Pages the author already linked by hand count as mentioned and are not linked again.
        for href in re.findall(r'href="(/wiki/[^"#]+/)"', html):
            if href in self.by_href:
                mentioned.add(self.by_href[href].slug)
        linked = set(mentioned)
        out, skip_depth = [], 0
        for token in TAG.split(html):
            if token.startswith("<"):
                m = re.match(r"<(/?)([a-zA-Z0-9]+)", token)
                if m and m.group(2).lower() in SKIP_TAGS and not token.endswith("/>"):
                    skip_depth += -1 if m.group(1) else 1
                    skip_depth = max(skip_depth, 0)
                out.append(self.style_hand_link(token))
                continue

            def replace(match: re.Match) -> str:
                page = self.by_name[fold(match.group(1))]
                if page.slug == self_slug:
                    return match.group(0)
                mentioned.add(page.slug)
                if skip_depth or page.slug in linked:
                    return match.group(0)
                linked.add(page.slug)
                title = htmllib.escape(page.summary or page.title, quote=True)
                return f'<a class="wiki-link" href="/wiki/{page.slug}/" title="{title}">{match.group(0)}</a>'

            out.append(self.pattern.sub(replace, token))
        return "".join(out), mentioned

    def style_hand_link(self, tag: str) -> str:
        """A link written by hand to a wiki page ("the [werewolves' cave](/wiki/lake-baratok-cave/)") looks
        like the automatic ones: gold, with the page's summary on hover. Classed links (map sprites) stay."""
        m = re.fullmatch(r'<a href="(/wiki/[^"#]+/)">', tag)
        page = self.by_href.get(m.group(1)) if m else None
        if page is None:
            return tag
        title = htmllib.escape(page.summary or page.title, quote=True)
        return f'<a class="wiki-link" href="{m.group(1)}" title="{title}">'


    def anchor(self, match: re.Match) -> str:
        page = self.by_name[fold(match.group(1))]
        title = htmllib.escape(page.summary or page.title, quote=True)
        return f'<a class="wiki-link" href="/wiki/{page.slug}/" title="{title}">{match.group(0)}</a>'


# Reference lists whose entries start with a bold name: Key Locations, Encounters, Loot, Notable NPCs.
# A section starts at its heading, or in older posts at a bold "Notable NPCs:" line, and runs to the next
# heading or bold "Something:" line that starts a paragraph.
ENTRY_SECTIONS = r"(?:Key Locations|Encounters|Loot|Notable NPCs)"
NPC_SECTION = re.compile(rf"(<h([23])[^>]*>[^<]*{ENTRY_SECTIONS}[^<]*</h\2>|<p><strong>{ENTRY_SECTIONS}:?</strong>)"
                         r"(.*?)(?=<h[23][ >]|<p><strong>[^<]*:</strong>|$)", re.S | re.I)


def link_npc_names(html: str, linker: Linker) -> str:
    """In a post's reference lists (Key Locations, Encounters, Loot, Notable NPCs), link every bold
    entry name to its wiki page, even when the story already linked an earlier mention: the lists are
    where readers look someone up. Everywhere else only the first mention links."""
    if linker.pattern is None:
        return html

    def strong(m: re.Match) -> str:
        inner = m.group(1)
        if "<" in inner:  # already linked, or other markup: leave it
            return m.group(0)
        return "<strong>" + linker.pattern.sub(linker.anchor, inner) + "</strong>"

    return NPC_SECTION.sub(lambda m: m.group(1) + re.sub(r"<strong>(.*?)</strong>", strong, m.group(3), flags=re.S), html)

# A session reference as the wiki writes it: "(Title)" or "(Title, Title; Title)", each a link to a post,
# with nothing else inside the brackets. The space before the bracket goes too, so the marker hugs the word.
POST_LINK = r'<a href="/posts/([^"/]+)/">([^<]*)</a>'
# A short note after the links, such as a date ("..., February 2025"), stays behind in brackets.
CITATION = re.compile(rf" ?\(({POST_LINK}(?:[,;] {POST_LINK})*)(?:, ([^()<>]{{1,40}}))?\)")


def cite_sessions(html: str, marker, sep: str = "") -> tuple[str, list[str]]:
    """Turn bracketed session links into small markers: marker(post slug, plain title) -> HTML.

    Returns the new HTML and the cited post slugs in the order first cited."""
    cited: list[str] = []

    def replace(match: re.Match) -> str:
        parts = []
        for slug, title in re.findall(POST_LINK, match.group(1)):
            if slug not in cited:
                cited.append(slug)
            parts.append(marker(slug, htmllib.unescape(title)))
        note = match.group(match.re.groups) or ""  # the last group: the note after the links
        return sep.join(parts) + (f" ({note})" if note else "")

    return CITATION.sub(replace, html), cited


def plain_text(html: str) -> str:
    """Rendered HTML -> plain text for the search index."""
    text = re.sub(r"</?(?:p|li|ul|ol|h[1-6]|br|div|tr|td|th|blockquote|aside|table)[^>]*>", " ", html)
    text = TAG.sub("", text)
    return unicodedata.normalize("NFC", re.sub(r"\s+", " ", htmllib.unescape(text)).strip())
