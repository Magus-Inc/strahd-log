---
name: update-wiki
description: Bring the wiki up to date with a new or edited session post, adding missing pages and extending descriptions in Malron's words. Use whenever a post is added to content/posts/, or when Chris asks to fill in or expand wiki pages.
---

# Keep the wiki living

Chris wants the wiki to grow with the campaign (2026-10-28): every new session adds what it showed
us to the pages it touches, and creates pages for anyone or anything new. Two layers do this, and
both cite the posts they come from.

1. **The fact list ("From the adventure log").** Add one entry per person, place, item or faction
   the post mentions to a `data/log-extract/*.json` file (the newest `posts-partN.json`, or a new
   part), each with short facts citing the post's file stem. Put spelling merges, wrong facts and
   bad aliases in `data/log-extract/corrections.yaml`. Then run `just wiki-from-log`. It rewrites
   only the section after `<!-- from-the-log -->` and the wholly compiled pages.
2. **The description.** Above `<!-- from-the-log -->`, a `## Description` section opens with
   `*Written from the session logs, in Malron's words.*` and tells the story of that person or
   place as Malron knows it. For each page the new post adds something real to:
   - Extend it: add a sentence or a paragraph at the right point in the story (in time order; a
     `###` subsection when a place gets a new visit), ending with a link to the post,
     `([Post title](/posts/<slug>/))`. Don't restate what is already there.
   - If the page has no description yet and the post makes the subject matter (a recurring NPC, a
     place the party spent a session in, an item that changed a fight), write one from every post
     that mentions it, not just the new one.
   - A page whose `source:` is exactly `Compiled from the adventure log` is deleted and rebuilt by
     `just wiki-from-log`. When you give it a description, change `source:` to
     `Compiled from the adventure log, with a description written for the site` so it is kept.
   - Pages written on Obsidian Portal keep their original text. Put the description above it and
     never reword theirs.
   - A new page needs `title`, `type` (character, npc, creature, place, item, faction, deity,
     other), `summary` (one line) and `aliases` for other spellings the posts use. An alias must not
     be an ordinary word, because aliases link automatically everywhere.

## The rules for what goes in

- **Only what the posts say.** The DM changes the module, so events, outcomes and who did what come
  only from the posts (and from Chris). The book is good for spellings only; use the wiki's own page
  titles. Summarize, never quote, published book text.
- **Malron's voice.** First person ("we", "I"), past tense, in-world, as in the posts. No dice, DCs,
  levels, spell or feature names, rules talk, DM name or player names. Real player names appear
  only on each PC's own wiki page.
- **Say what you don't know.** When the posts leave something open, the description leaves it open
  too ("we have yet to learn what it opens"). Never fill a gap from the module.
- **Speaker slips happen.** If a post credits a line or a deed to a character and another post or
  the context says otherwise, don't pick one quietly: ask Chris if it matters, as `dnd-scribe`'s
  recap skill does.
- **Corrections go back to the source.** If a description turns out wrong because a post was wrong,
  fix the post too (or ask Chris) so the fact list and the story agree.

## Before the pull request

- `just test`, then `just build` and look at two or three changed pages at phone width
  (iPhone 13 viewport in Playwright works). Put the screenshots on the `previews` branch under a
  folder for the PR and show them in the PR body and to Chris.
- List the pages added and extended in the PR body, so Chris can skim what changed.
