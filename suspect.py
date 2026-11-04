"""Words that were hard to hear at the table, kept and marked as not yet confirmed (Chris, 2026-11-04).

A post or wiki page writes them as {?a d2?}: the transcript caught something, but it may be misheard.
Chris: "tag numbers that were hard to hear as suspect and to be verified (provenance)". The site shows
the words with a dotted underline, a small "?" and a tooltip, and a tap (phones have no hover) shows the note; screen readers hear the note; the Discord
bot's corpus gets the note in words. Once someone confirms the words, drop the braces.
"""
from __future__ import annotations

import re

NOTE = "Hard to hear at the table; not yet confirmed"
MARK = re.compile(r"\{\?([^{}?\n]+?)\?\}")


def to_html(markdown_text: str) -> str:
    """Markdown with each mark turned into its flagged span (inline HTML, which Markdown keeps)."""
    return MARK.sub(lambda m: f'<span class="suspect" tabindex="0" title="{NOTE}">{m.group(1)}'
                              f'<span class="suspect-note"> ({NOTE.lower()})</span></span>', markdown_text)


def plain(markdown_text: str) -> str:
    """Markdown with each mark spelled out, for readers with no tooltip (the Discord bot)."""
    return MARK.sub(lambda m: f"{m.group(1)} ({NOTE.lower()})", markdown_text)
