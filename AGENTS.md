# Working in strahd-log

- Python 3.13 (`py -3.13` on Windows), run through `just` recipes. `just test` before finishing any change.
- Recipe lines must work in both pwsh and sh. Put logic in Python, not in shell.
- Read and write text with `encoding="utf-8"`; tests must not depend on line endings or the OS.
- Tests build their own fixtures in `tmp_path`; never depend on the Obsidian Portal export folder.
- Tests that check the real blog use the `real_build` fixture (`tests/conftest.py`), built once per run.
- A change that should not change the site (a refactor) must show "No changes" in `just site-diff`; the
  Checks workflow prints the site diff for every pull request.
- The site build needs only `requirements.txt`; keep importer and test packages in `requirements-dev.txt`.
- Scripts (Chris, 2026-11-02): the site runs its own JavaScript plus libraries copied into
  `static/vendor/`; it never loads a script, stylesheet or font from another site (no CDNs), so
  readers' browsers talk only to the blog and GoatCounter. Reach for a library when our own code
  would pass about 150 lines or the problem is a known hard one; small helpers stay hand-written,
  and working code is left alone. Each library: a permissive license (MIT, BSD, ISC, Apache-2.0; OFL
  for fonts) with its text beside the file, at most 30 KB zipped (60 KB for all libraries on one
  page), loaded only on the pages that use it, the unminified build when it fits, no cookies,
  storage or network calls of its own, and listed in `data/vendor.yaml` with version, download URL,
  sha256 and why. `tests/test_vendor.py` enforces this, and a monthly workflow opens an issue when
  osv.dev reports a security problem in a listed version. Every page must stay readable on a phone,
  even if a script fails.
- Wiki text above `<!-- from-the-log -->` is ours; only the section after it is generated. Tools
  add facts there, each citing the post it came from. Above it, agents may write and extend a
  `## Description` in Malron's words from the posts, and for new people and places the DM's
  description from the session transcript (the rules are dnd-scribe's `update-wiki` skill), but never
  reword text someone else wrote, such as the Obsidian Portal pages. The one exception (Chris,
  2026-11-02): a few loose Obsidian Portal lines left under the story, or a pasted `## As “…”` section
  from a merge, are folded into the story with every fact kept, so the page reads as one article.
- Wiki aliases are linked automatically everywhere, so an alias must not be an ordinary word
  ("Abbot", "Manor" in another town); `tools/wiki_from_extract.py` keeps a list of words to refuse.
- Posts are the players' own writing. Fix conversion problems in `tools/import_op.py`, not by
  rewording a post, unless Chris asks.
- Names are spelled as the Curse of Strahd book spells them (`data/spellings.yaml`; `just spellings`
  fixes new text). The book fixes spellings only: what happened comes from the posts and Chris.
  A wiki alias links a name wherever it appears, so a misspelled alias hides a wrong word behind a
  right link ("Sarepool crossroads" for Tser Pool Crossroads). `tests/test_spellings.py` fails on an
  alias spelled a letter or two off its page's name: fix it in `fix:`, or list it under `keep:` with why.
- One look for every post: `data/post-style.yaml` (Chris's picks) and `poststyle.py` restyle the
  rendered HTML at build time (PC pills, real headings, bulleted recap entries...), so old posts are
  never reworded to match. Change the look there, not in the posts.
- Every post reads in one order (layout review, Chris, 2026-11-02): title, tagline, PC pills, the
  slides, "Malron’s Account" (all of the story, its opening lines and pictures too), the recap lists
  (Key Locations, Encounters, Loot, Notable NPCs, Plot Points, Session Highlights; every entry a
  bullet), then the map. No second title above the story. `tests/test_layout.py` checks every post.
- Wiki links: the first mention of a name links in every section of the On this page box, every
  scene and every recap list, so a reader who jumps to a section finds its links (Chris,
  2026-11-02). The build does this (`relink: each-heading`); don't hand-link repeats.
- Every story sits under one "Malron’s Account" heading, split by scene headings from
  `data/scene-headings.yaml` (short, in Malron's voice, at natural breaks; a very short story gets
  `[]`). A new post needs its entry there; the build fails if a heading's opening words don't
  match exactly one paragraph. Chris checks new headings before they go live.
- Posts read as Malron's journal: first person, in-world, no dice or rules talk, no DM or player
  names. Table talk goes only in a `Note:` paragraph, which renders as a handwritten margin note,
  and only notes Chris picks. Real player names appear only on each PC's own wiki page.
- The map (`barovia_map.py`) is our own drawing. Never trace or embed a published Curse of Strahd
  map in the repo; a licensed background, if we ever get one, is an overlay swap, not a commit here.
- One layout for every wiki page (Chris, 2026-11-02): `data/wiki-style.yaml` and `wikistyle.py`
  lay out the rendered page at build time: the first picture at the top in a facts box (other
  names, first and last session seen), the `## Description` shown as "Malron’s Account", any stat
  block after it, and "From the adventure log" folded under a story. Keep writing pages as before
  (`## Description`, picture inside it); change the look in the yaml, not in the pages.
- Every AI picture we host keeps its full-size original (Chris, 2026-11-02): the page shows the
  smaller copy in `static/images/` (720px wide portraits, 1100px landscapes) and the original
  Gemini picture, full size as a JPEG, goes in `static/images/full/` under the same name. The build gives the picture a
  `data-full` address and the picture viewer loads it only when a reader taps the picture.
