"""The Start here page (start/): what a reader who lands on the blog cold needs first.

data/start-here.yaml holds the words; this module checks them against the posts and wiki and works
out the rest: each chapter's sessions and big moments (from data/party.yaml), today's party (the
newest session's cast) and everyone who came and went. Chris picked the page's shape on the start here
pick page, 2026-11-04.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
from pathlib import Path

import yaml

# Party changes shown as a chapter's big moments, in the order they happen within one session, as
# (data/party.yaml key, tag kind, words for one, several). The same order settles who is in the party
# when one session has two changes for a character (Gumbo and Liren returned and left in one night).
MOMENTS = (("joined", "party", ("joins", "join")), ("returned", "party", ("returns", "return")),
           ("died", "died", ("died", "died")), ("revived", "revived", ("is brought back", "are brought back")),
           ("left", "left", ("leaves", "leave")))
NEEDED = ("title", "from", "through", "picture")


@dataclass
class Moment:
    kind: str  # died, revived, party or won: the tag's look
    label: str
    page: object = None  # the wiki page a "won" tag links to


@dataclass
class Chapter:
    title: str
    posts: list  # oldest first
    picture: str  # images/<file>
    html: str = ""
    moments: list[Moment] = field(default_factory=list)

    @property
    def first(self):
        return self.posts[0]

    @property
    def span(self) -> str:
        """"Nov 2023 to Jan 2024", or one month when it all happened in one."""
        start, end = (p.date.strftime("%b %Y") for p in (self.posts[0], self.posts[-1]))
        return start if start == end else f"{start} to {end}"


@dataclass
class Member:
    page: object
    status: str  # died or left


@dataclass
class Card:
    card: str
    told: str
    page: object
    found_in: object = None  # the post where we found it
    status: str = ""


@dataclass
class Tip:
    """One line of How to read this blog, showing its own example (Chris, 2026-11-04): a gold wiki name,
    a red session title, a margin note in the table's hand, or a stretch of the map's dotted red road."""
    html: str
    note: str = ""  # a margin note shown after the line, in the table's handwriting


# A short stretch of the map's breadcrumb road, drawn like the map draws it (.map .crumb in style.css).
CRUMB_SAMPLE = ('<svg class="crumb-sample" width="64" height="14" viewBox="0 0 64 14" aria-hidden="true" '
                'focusable="false"><path d="M2 10 C 16 2, 30 2, 40 7 S 58 12, 62 4"/></svg>')


@dataclass
class StartPage:
    hero: str
    hook: str
    premise_html: str
    chapters: list[Chapter]
    uncovered: list  # sessions after the last chapter, oldest first: data/start-here.yaml needs them
    party: list  # wiki pages of today's party
    past: list[Member]
    fortune: list[Card]
    how_to_read: list[Tip]
    about: str
    small: dict = field(default_factory=dict)  # images/... -> [(small copy, width)], smallest first; set by the build


def first_name(page) -> str:
    return page.title.split()[0]


def load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def plan(data: dict, posts: list, pages: list, static_dir: Path, render=lambda md: md) -> StartPage:
    """The page from the data, the posts (newest first) and the wiki. Raises ValueError on a mistake in
    the data, so the build stops; a session after the last chapter is only listed in `uncovered`."""
    by_slug = {p.slug: p for p in posts}
    by_page = {w.slug: w for w in pages}
    oldest = sorted(posts, key=lambda p: (p.date, p.slug))
    where = {p.slug: i for i, p in enumerate(oldest)}

    def wiki_page(slug: str, what: str):
        if slug not in by_page:
            raise ValueError(f"data/start-here.yaml: {what}: no wiki page {slug}")
        return by_page[slug]

    def post_named(slug: str, what: str):
        if slug not in by_slug:
            raise ValueError(f"data/start-here.yaml: {what}: unknown post {slug}")
        return by_slug[slug]

    def picture(name: str, what: str) -> str:
        if not (static_dir / "images" / name).is_file():
            raise ValueError(f"data/start-here.yaml: {what}: no picture static/images/{name}")
        return f"images/{name}"

    chapters, next_index = [], 0
    for entry in data.get("chapters") or []:
        missing = [key for key in NEEDED if not entry.get(key)]
        if missing:
            raise ValueError(f"data/start-here.yaml: a chapter ({entry.get('title', 'no title')}) has no "
                             + ", ".join(missing))
        title = entry["title"]
        first, last = post_named(entry["from"], title), post_named(entry["through"], title)
        if where[first.slug] != next_index:
            expected = oldest[next_index].slug if next_index < len(oldest) else "nothing"
            if next_index == 0:
                raise ValueError(f"data/start-here.yaml: {title} must start at the first session, {expected}")
            raise ValueError(f"data/start-here.yaml: {title} starts at {first.slug}, but {expected} comes right after "
                             "the chapter before")
        if where[last.slug] < where[first.slug]:
            raise ValueError(f"data/start-here.yaml: {title} ends before it starts")
        chapter = Chapter(title, oldest[where[first.slug]:where[last.slug] + 1], picture(entry["picture"], title),
                          render(entry.get("text", "")))
        for post in chapter.posts:
            for key, kind, words in MOMENTS:
                people = post.party.get(key) or []
                if people:
                    names = " and ".join(first_name(p) for p in people)
                    chapter.moments.append(Moment(kind, f"{names} {words[len(people) > 1]}"))
        for slug in entry.get("won") or []:
            thing = wiki_page(slug, f"{title} won")
            chapter.moments.append(Moment("won", thing.title, thing))
        chapters.append(chapter)
        next_index = where[last.slug] + 1

    # Who is with us: every player character whose last change in data/party.yaml is not a death or a
    # leaving (died, then brought back or returned, is with us again). The narrator is always with us.
    status: dict[str, str] = {}
    for post in oldest:
        for key, _, _ in MOMENTS:
            for person in post.party.get(key) or []:
                status[person.slug] = {"died": "died", "left": "left"}.get(key, "with us")
    seen = []
    for post in oldest:
        for slug in post.listed:
            if slug not in seen:
                seen.append(slug)
    # Every player character, played now or before (a few early ones have no player on their page).
    players = [w for w in pages if w.type == "character" and not getattr(w, "dm", False)]
    players.sort(key=lambda w: seen.index(w.slug) if w.slug in seen else len(seen))
    party = [w for w in players if getattr(w, "narrator", False) or status.get(w.slug, "with us") == "with us"]
    party.sort(key=lambda w: not getattr(w, "narrator", False))  # Malron, who writes it, first
    past = [Member(w, status[w.slug]) for w in players if w not in party]

    fortune = []
    for entry in data.get("fortune") or []:
        found = post_named(entry["found_in"], entry["card"]) if entry.get("found_in") else None
        fortune.append(Card(entry["card"], entry["told"], wiki_page(entry["points_to"], entry["card"]), found,
                            entry.get("status", "")))

    tips = []
    for entry in data.get("how_to_read") or []:
        text = escape(str(entry["text"]), quote=False)
        if entry.get("wiki"):
            w = wiki_page(entry["wiki"], "how_to_read")
            example = f'<a class="wiki-link" href="/{w.path}">{escape(w.title)}</a>'
        elif entry.get("post"):
            p = post_named(entry["post"], "how_to_read")
            example = f'<a class="session-link" href="/{p.path}">{escape(p.title)}</a>'
        elif entry.get("map"):
            example = CRUMB_SAMPLE
        else:
            example = ""
        tips.append(Tip(text.replace("{example}", example), escape(str(entry.get("note", "")), quote=False)))

    count = len(posts)
    return StartPage(
        hero=picture(data["hero"], "hero") if data.get("hero") else "",
        hook=str(data.get("hook", "")).replace("{sessions}", str(count)),
        premise_html=render(data.get("premise", "")),
        chapters=chapters,
        uncovered=oldest[next_index:],
        party=party,
        past=past,
        fortune=fortune,
        how_to_read=tips,
        about=str(data.get("about", "")),
    )
