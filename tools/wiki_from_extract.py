"""Add what the adventure logs say about each character, place and thing to content/wiki/.

Input: one or more JSON files of entities extracted from the posts (by a person or a model), each
a list of {"name", "type", "aliases", "summary", "player"?, "facts": [{"text", "post"}]} where
"post" is a post's file name without ".md". Entities that share a name or alias are merged.

Reviewed fixes live next to the extracts in corrections.yaml (see load_corrections), so they
survive the extraction being redone.

For a page someone wrote, the facts go in a "From the adventure log" section after their text, and
new aliases are added; nothing they wrote is changed. Every other entity gets a draft page with
`source: Compiled from the adventure log`. Those pages are wholly generated: each run deletes and
rewrites them, so to keep an edit to one, change its `source`.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
MARKER = "<!-- from-the-log -->"
COMPILED = "Compiled from the adventure log"
TYPES = {"character", "npc", "creature", "place", "item", "faction", "deity", "other"}
# Words that are names in one sentence and ordinary words in the next; never used as aliases.
GENERIC = {
    "abbot", "baron", "baroness", "bishop", "brother", "captain", "count", "devil", "father",
    "god", "guard", "king", "lady", "lord", "master", "mayor", "mother", "priest", "queen",
    "sister", "the", "village", "castle", "church", "tower", "town", "abbey", "temple",
    "ethereal",
}


def slugify(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")


def split_front_matter(text: str) -> tuple[dict, str]:
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text.replace("\r\n", "\n"), re.S)
    return (yaml.safe_load(m.group(1)) or {}, m.group(2)) if m else ({}, text)


def load_corrections(path: Path) -> dict:
    """Reviewed fixes, all optional:

    same: [[Preferred Title, Other Spelling, ...], ...]  # one entity; the first name is its title
    not_alias: [Name, ...]                                # never used as an alias
    facts: {"exact fact text": "replacement" or null}     # null drops the fact
    move_facts: {"exact fact text": "Other Entity"}       # e.g. two people who share a name
    types: {Name: type}
    summaries: {Name: "summary"}
    players: {Name: "Player Name"}                         # who played a player character
    former: [Name, ...]                                    # player characters no longer played
    """
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def apply_corrections(entities: list[dict], fixes: dict) -> list[dict]:
    fact_fixes, moves = fixes.get("facts") or {}, fixes.get("move_facts") or {}
    not_alias = {n.lower() for n in fixes.get("not_alias") or []}
    out, moved = [], {}
    for original in entities:
        e = dict(original, aliases=[a for a in original.get("aliases", []) if a.lower() not in not_alias], facts=[])
        out.append(e)
        for fact in original.get("facts", []):
            text = fact["text"]
            if text in moves:
                target = moved.setdefault(moves[text], {"name": moves[text], "type": original.get("type", "other"),
                                                        "aliases": [], "summary": "", "facts": []})
                target["facts"].append(fact)
            elif text in fact_fixes:
                if fact_fixes[text]:
                    e["facts"].append(dict(fact, text=fact_fixes[text]))
            else:
                e["facts"].append(fact)
    out += moved.values()
    # Tie spellings together through a fact-less entity carrying every name.
    out += [{"name": names[0], "aliases": list(names[1:]), "facts": [], "preferred": True}
            for names in fixes.get("same") or []]
    return out


def merge_entities(entities: list[dict]) -> list[list[dict]]:
    """Group entities that share any name or alias (case-insensitive)."""
    parent = list(range(len(entities)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    owner: dict[str, int] = {}
    for i, e in enumerate(entities):
        for name in [e["name"], *e.get("aliases", [])]:
            key = name.strip().lower()
            if key in owner:
                parent[find(i)] = find(owner[key])
            else:
                owner[key] = i
    groups: dict[int, list[dict]] = defaultdict(list)
    for i, e in enumerate(entities):
        groups[find(i)].append(e)
    return list(groups.values())


def usable_alias(name: str, refused: set[str] = frozenset()) -> bool:
    return len(name) >= 3 and name[0].isupper() and name.lower() not in GENERIC | refused


def load_posts(posts_dir: Path) -> dict[str, tuple[str, str]]:
    """{file stem: (slug, title)}"""
    posts = {}
    for path in posts_dir.glob("*.md"):
        meta, _ = split_front_matter(path.read_text(encoding="utf-8"))
        slug = meta.get("slug") or re.sub(r"^\d{4}-\d\d-\d\d-", "", path.stem)
        posts[path.stem] = (slug, str(meta.get("title", slug)))
    return posts


def fact_lines(group: list[dict], posts: dict[str, tuple[str, str]]) -> list[str]:
    facts, seen = [], set()
    for e in group:
        for f in e.get("facts", []):
            stem = f.get("post", "")
            if stem not in posts or f["text"] in seen:
                continue
            seen.add(f["text"])
            facts.append((stem, f["text"].strip().rstrip(".") + "."))
    facts.sort(key=lambda sf: sf[0])  # file names start with the date
    return [f"* {text} ([{posts[stem][1]}](/posts/{posts[stem][0]}/))" for stem, text in facts]


def log_section(lines: list[str]) -> str:
    return (f"{MARKER}\n## From the adventure log\n\n"
            "*Compiled from the session posts. Each line links to the session it comes from.*\n\n"
            + "\n".join(lines) + "\n")


def apply(extract_files: list[Path], wiki_dir: Path, posts_dir: Path,
          corrections: dict | None = None) -> tuple[int, int]:
    """Return (pages updated, pages created)."""
    fixes = corrections or {}
    entities = [e for f in extract_files for e in json.loads(f.read_text(encoding="utf-8"))]
    entities = apply_corrections(entities, fixes)
    refused = {n.lower() for n in fixes.get("not_alias") or []}
    types = {k.lower(): v for k, v in (fixes.get("types") or {}).items()}
    summaries = {k.lower(): v for k, v in (fixes.get("summaries") or {}).items()}
    players = {k.lower(): v for k, v in (fixes.get("players") or {}).items()}
    former = {n.lower() for n in fixes.get("former") or []}
    posts = load_posts(posts_dir)
    # A fact citing a post that was folded into another (data/redirects.yaml) cites the new one.
    redirects_file = posts_dir.parent.parent / "data" / "redirects.yaml"
    if redirects_file.exists():
        moved = (yaml.safe_load(redirects_file.read_text(encoding="utf-8")) or {}).get("posts") or {}
        for e in entities:
            for f in e.get("facts", []):
                f["post"] = moved.get(f.get("post"), f.get("post"))
    wiki_dir.mkdir(parents=True, exist_ok=True)

    # Compiled pages are wholly generated: start them afresh so merged or renamed ones go away.
    for path in wiki_dir.glob("*.md"):
        if split_front_matter(path.read_text(encoding="utf-8"))[0].get("source") == COMPILED:
            path.unlink()

    existing: dict[str, Path] = {}  # lower-case name -> page file
    for path in sorted(wiki_dir.glob("*.md")):
        meta, _ = split_front_matter(path.read_text(encoding="utf-8"))
        for name in [meta.get("title", ""), *(meta.get("aliases") or [])]:
            existing.setdefault(str(name).lower(), path)
    taken = set(existing)  # names already claimed, so no two pages share an alias

    # Resolve every group to one page first, so two groups that land on the same page (say
    # "Ismark" and "Ismark the Lesser", both aliases of one page) add up instead of overwriting.
    targets: dict[Path, dict] = {}
    groups = merge_entities(entities)
    # Bigger groups first, so the best-attested entity keeps a contested alias.
    groups.sort(key=lambda g: -sum(len(e.get("facts", [])) for e in g))
    for group in groups:
        names = Counter(n for e in group for n in [e["name"], *e.get("aliases", [])])
        page = next((existing[n.lower()] for n in names if n.lower() in existing), None)
        if page is None:
            preferred = [e["name"] for e in group if e.get("preferred")]
            title = preferred[0] if preferred else max(
                (e["name"] for e in group), key=lambda n: (names[n], len(n.split()), len(n)))
            # A generic word as a title would be linked everywhere, like a generic alias.
            if title.lower() in taken or not usable_alias(title, refused) or not fact_lines(group, posts):
                continue
            page = wiki_dir / f"{slugify(title)}.md"
            if page.exists():
                continue
            kind = Counter(e["type"] for e in group if e.get("type")).most_common(1)[0][0]
            kind = next((types[n.lower()] for n in names if n.lower() in types), kind)
            targets[page] = {"new": True, "meta": {"title": title, "type": kind if kind in TYPES else "other"},
                             "group": []}
            existing[title.lower()] = page
        target = targets.setdefault(page, {"new": False, "group": []})
        target["group"] += group

    updated = created = 0
    for page, target in targets.items():
        group = target["group"]
        if target["new"]:
            meta, body_prefix, front = dict(target["meta"]), "", None
            created += 1
        else:
            text = page.read_text(encoding="utf-8").replace("\r\n", "\n")
            meta, body = split_front_matter(text)
            front = text[: len(text) - len(body)]
            body_prefix = body.split(MARKER)[0].strip("\n")
            updated += 1
        original = dict(meta)
        names = Counter(n for e in group for n in [e["name"], *e.get("aliases", [])])
        aliases = list(meta.get("aliases") or [])
        for name, _count in names.most_common():
            if (name != meta["title"] and name not in aliases and usable_alias(name, refused)
                    and name.lower() not in taken):
                aliases.append(name)
        for name in [meta["title"], *aliases]:
            taken.add(name.lower())
        if aliases:
            meta["aliases"] = aliases
        fixed = next((summaries[n.lower()] for n in [meta["title"], *names] if n.lower() in summaries), "")
        if target["new"] and fixed:
            meta["summary"] = fixed
        elif not meta.get("summary"):
            summary = fixed or next((e["summary"] for e in group if e.get("summary")), "")
            if summary:
                meta["summary"] = summary
        player = next((players[n.lower()] for n in [meta["title"], *names] if n.lower() in players), "")             or next((e["player"] for e in group if e.get("player")), "")
        if player and not meta.get("player"):
            meta["player"] = player
        if meta["title"].lower() in former and target["new"]:
            meta["former"] = True
        if target["new"]:
            meta["source"] = COMPILED
        if front is None or meta != original:
            order = ["title", "type", "aliases", "summary", "player", "former", "source", "obsidian_portal_url"]
            meta = {k: meta[k] for k in order if k in meta} | {k: v for k, v in meta.items() if k not in order}
            front = "---\n" + yaml.safe_dump(meta, sort_keys=False, allow_unicode=True, width=1000) + "---\n"
        body = (body_prefix + "\n\n" if body_prefix.strip() else "") + log_section(fact_lines(group, posts))
        page.write_text(front.rstrip("\n") + "\n\n" + body, encoding="utf-8", newline="\n")
    return updated, created


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Merge entities extracted from the posts into the wiki")
    parser.add_argument("extract", type=Path, nargs="*",
                        help="JSON entity files (default: data/log-extract/*.json)")
    parser.add_argument("--corrections", type=Path,
                        help="reviewed fixes (default: corrections.yaml next to the extract files)")
    parser.add_argument("--wiki", type=Path, default=ROOT / "content" / "wiki")
    parser.add_argument("--posts", type=Path, default=ROOT / "content" / "posts")
    args = parser.parse_args(argv)
    files = args.extract or sorted((ROOT / "data" / "log-extract").glob("*.json"))
    corrections = load_corrections(args.corrections or files[0].parent / "corrections.yaml")
    updated, created = apply(files, args.wiki, args.posts, corrections)
    print(f"Updated {updated} wiki pages and created {created} from the adventure log")
    return 0


if __name__ == "__main__":
    sys.exit(main())
