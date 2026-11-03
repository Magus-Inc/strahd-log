"""Hidden `sources:` lists in post and wiki front matter (Chris, 2026-11-03).

A page lists what it was written from, and the site never shows the list. The repo is public, so
an entry is only ever one of two things:

- a reference id, `<kind>-<6 letters or digits>` (`discord-w4k9rt`, `notes-7k2m9q`): it says a
  source of that kind exists, never where it lives or what it says. The private dnd-scribe repo
  keeps the table of ids (`sources.yaml`) and checks that every id used here is in it;
- a public https link, such as the Obsidian Portal page a post came from.

A file path, a quote or a date slipped into the list is refused, so private material can't leak in.
"""

from __future__ import annotations

import re

KINDS = ("notes", "transcript", "recording", "discord")
REFERENCE_ID = re.compile(rf"^(?:{'|'.join(KINDS)})-[a-z0-9]{{6}}$")
PUBLIC_LINK = re.compile(r"^https://([A-Za-z0-9.-]+\.[A-Za-z]{2,})(?:/[^\s]*)?$")
# Share links to private files and chat look public but aren't: never a source.
PRIVATE_HOSTS = ("1drv.ms", "onedrive.live.com", "sharepoint.com", "drive.google.com", "docs.google.com",
                 "discord.com", "discordapp.com", "discord.gg")


def is_valid_source(entry) -> bool:
    """One entry: a reference id or a public https link."""
    if not isinstance(entry, str):
        return False
    if REFERENCE_ID.match(entry):
        return True
    link = PUBLIC_LINK.match(entry)
    host = link.group(1).lower() if link else ""
    return bool(link) and not any(host == h or host.endswith("." + h) for h in PRIVATE_HOSTS)


def parse_sources(value, where: str) -> list[str]:
    """A front-matter `sources:` value as a list, or ValueError naming the page and the bad entry."""
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{where}: sources: must be a list of reference ids or https links")
    for entry in value:
        if not is_valid_source(entry):
            raise ValueError(f"{where}: sources: {entry!r} is not a reference id "
                             f"(<{'|'.join(KINDS)}>-<6 letters or digits>) or a public https link")
    if len(set(value)) != len(value):
        raise ValueError(f"{where}: sources: lists an entry twice")
    return list(value)
