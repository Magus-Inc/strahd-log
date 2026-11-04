"""The Start here page (start/): what a reader who lands on the blog cold needs first.

data/start-here.yaml holds the words; this module checks them against the posts and wiki and works
out the rest: each chapter's sessions and big moments (from data/party.yaml), today's party (the
newest session's cast) and everyone who came and went. Chris picked the page's shape on the start here
pick page, 2026-11-04.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

# Party changes shown as a chapter's big moments, in this order, as (tag kind, words for one, several).
# A character who leaves is shown on the party list instead, so "left" is not a big moment.
MOMENTS = (("died", "died", ("died", "died")), ("revived", "revived", ("is brought back", "are brought back")),
           ("joined", "party", ("joins", "join")), ("returned", "party", ("returns", "return")))


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
class StartPage:
    hero: str
    hook: str
    premise_html: str
    chapters: list[Chapter]
    uncovered: list  # sessions after the last chapter, oldest first: data/start-here.yaml needs them
    party: list  # wiki pages of today's party
    past: list[Member]
    faces: list
    fortune: list[Card]
    how_to_read: list[str]
    about: str


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

    newest = oldest[-1] if oldest else None
    party = [by_page[s] for s in (newest.listed if newest else []) if s in by_page]
    party.sort(key=lambda w: not getattr(w, "narrator", False))  # Malron, who writes it, first
    status: dict[str, str] = {}
    for post in oldest:  # the last change counts: died, then brought back or returned, is with us again
        for key, people in post.party.items():
            for person in people:
                status[person.slug] = {"died": "died", "left": "left"}.get(key, "with us")
    in_party = {p.slug for p in party}
    seen = []
    for post in oldest:
        for slug in post.listed:
            if slug not in seen:
                seen.append(slug)
    # Every player character, played now or before (a few early ones have no player on their page).
    players = [w for w in pages if w.type == "character" and not getattr(w, "dm", False)]
    players.sort(key=lambda w: seen.index(w.slug) if w.slug in seen else len(seen))
    past = [Member(w, "died" if status.get(w.slug) == "died" else "left") for w in players if w.slug not in in_party]

    fortune = []
    for entry in data.get("fortune") or []:
        found = post_named(entry["found_in"], entry["card"]) if entry.get("found_in") else None
        fortune.append(Card(entry["card"], entry["told"], wiki_page(entry["points_to"], entry["card"]), found,
                            entry.get("status", "")))

    count = len(posts)
    return StartPage(
        hero=picture(data["hero"], "hero") if data.get("hero") else "",
        hook=str(data.get("hook", "")).replace("{sessions}", str(count)),
        premise_html=render(data.get("premise", "")),
        chapters=chapters,
        uncovered=oldest[next_index:],
        party=party,
        past=past,
        faces=[wiki_page(s, "faces") for s in data.get("faces") or []],
        fortune=fortune,
        how_to_read=list(data.get("how_to_read") or []),
        about=str(data.get("about", "")),
    )
