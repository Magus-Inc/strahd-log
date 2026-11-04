# Working in strahd-log

- Python 3.13 (`py -3.13` on Windows), run through `just` recipes. `just test` before finishing any change.
- Recipe lines must work in both pwsh and sh. Put logic in Python, not in shell.
- Read and write text with `encoding="utf-8"`; tests must not depend on line endings or the OS.
- Tests build their own fixtures in `tmp_path`; never depend on the Obsidian Portal export folder.
- `build()` runs named stages; their order lives only in `build.STAGES` (tests/test_stages.py). A new
  step on posts or wiki pages is a new stage there. `build.prepare()` runs them without writing files.
- Tests that check the real blog use the `real_build` fixture (`tests/conftest.py`), built once per run.
- A change that should not change the site (a refactor) must show "No changes" in `just site-diff`; the
  Checks workflow prints the site diff for every pull request.
- The site build needs only `requirements.txt`; keep importer and test packages in `requirements-dev.txt`.
- Scripts (Chris, 2026-11-02): the site runs its own JavaScript plus libraries copied into
  `static/vendor/`; apart from Google Analytics' tag (below) it never loads a script, stylesheet or
  font from another site (no CDNs), so
  readers' browsers talk only to the blog, GoatCounter and Google Analytics. The one outside script
  is Google Analytics 4's own tag (`googletagmanager.com/gtag/js`, Chris asked for it beside
  GoatCounter, 2026-11-04), turned on only by `GOOGLE_ANALYTICS` in the publish workflow; it sets
  Google's cookies, and every count still goes to GoatCounter too. Reach for a library when our own code
  would pass about 150 lines or the problem is a known hard one; small helpers stay hand-written,
  and working code is left alone. Each library: a permissive license (MIT, BSD, ISC, Apache-2.0; OFL
  for fonts) with its text beside the file, at most 30 KB zipped (60 KB for all libraries on one
  page), loaded only on the pages that use it, the unminified build when it fits, no cookies,
  storage or network calls of its own, and listed in `data/vendor.yaml` with version, download URL,
  sha256 and why. `tests/test_vendor.py` enforces this, and a monthly workflow opens an issue when
  osv.dev reports a security problem in a listed version (or a pinned Python package). Every page
  must stay readable on a phone, even if a script fails.
- Libraries, JS or Python (Chris, 2026-11-03): before adding one, also weigh how well it is kept up,
  and write it down in its entry (`data/vendor.yaml`, or `data/python-libraries.yaml` for every
  package in `requirements*.txt`): first and last release, weekly downloads (how popular it is),
  whether bug and security fixes are landing, `maintenance` (active, stable, new or unmaintained) and
  its `risks`. Very new (under a year) is not a reason to refuse it, but it gets extra scrutiny and
  its risk is listed. No release for two years can mean finished and stable or abandoned: decide
  which from whether reports still get answered and fixed, and say so. Bug and security fixes that
  have stopped, or few users, are risks to list. Weigh all of it in the decision and write the
  reasoning in the PR. `tests/test_library_upkeep.py` enforces the entries, and the monthly workflow
  re-checks them against npm and PyPI and opens an issue when one changes or is a year old.
- Wiki text above `<!-- from-the-log -->` is ours; only the section after it is generated. Tools
  add facts there, each citing the post it came from. Above it, agents may write and extend a
  `## Description` in Malron's words from the posts, and for new people and places the DM's
  description from the session transcript (the rules are dnd-scribe's `update-wiki` skill), but never
  reword text someone else wrote, such as the Obsidian Portal pages. The one exception (Chris,
  2026-11-02): a few loose Obsidian Portal lines left under the story, or a pasted `## As “…”` section
  from a merge, are folded into the story with every fact kept, so the page reads as one article.
- Player names and sources (Chris, 2026-11-04): a player's real name shows only in a PC page's
  Player box, on the Dungeon Master page and in an art credit ("drawn by ..."); story text says "his
  player". No visible line says where text came from (session logs, notes, recordings, Discord, "Ryan
  shared", "shared at the table"): that goes in the hidden `sources:` ids. Wiki pages show no source
  line. The table-talk margin notes may say "the DM" or "Shabasta's player". `tests/test_player_mentions.py`
  checks the built site.
- Hard-to-hear words (Chris, 2026-11-04): when a transcript may have misheard a number or phrase that
  goes on the site, keep it and mark it `{?a d2?}` instead of leaving it out or guessing. The site
  shows it underlined with a "?" and a tooltip saying it isn't confirmed yet (`suspect.py`), and the
  Discord bot's corpus spells that out. Drop the braces once Chris or the DM confirms it.
- Wiki aliases are linked automatically everywhere, so an alias must not be an ordinary word
  ("Abbot", "Manor" in another town); `tools/wiki_from_extract.py` keeps a list of words to refuse.
- Posts are the players' own writing. Fix conversion problems in `tools/import_op.py`, not by
  rewording a post, unless Chris asks.
- Names are spelled as the Curse of Strahd book spells them (`data/spellings.yaml`; `just spellings`
  fixes new text). The book fixes spellings only: what happened comes from the posts and Chris.
  A wiki alias links a name wherever it appears, so a misspelled alias hides a wrong word behind a
  right link ("Sarepool crossroads" for Tser Pool Crossroads). `tests/test_spellings.py` fails on an
  alias spelled a letter or two off its page's name: fix it in `fix:`, or list it under `keep:` with why.
- One post format (Chris, 2026-11-03): every post file is written one way. Front matter has
  `cast:` (the player characters there, by wiki page title) and `sources:` (hidden reference ids
  for the notes, transcripts, recordings and Discord posts it came from, `[]` when none; the table
  of ids is private, in dnd-scribe `campaign/sources.yaml`); then an optional `## At a Glance`,
  one `## Story` with its `###` scene headings (short, in Malron's voice, at natural breaks), then
  `## Key Locations`, `## Encounters`, `## Loot`, `## Notable NPCs`, `## Plot Points`,
  `## Session Highlights`, one bullet per entry (`* **Name**: text`). `tests/test_post_format.py`
  checks every post: a post that drifts is fixed in the file, never with a new style rule.
- Pictures in a post (Chris, 2026-11-03): at most 3 in all (`poststyle.MAX_PICTURES`), the feature
  picture and any maps included; the slides are a deck and do not count. A post Chris names may hold 4
  (`picture-cap: 4` in its front matter, never more). They go only in the story, each on a line of its
  own after the paragraph it shows (after that paragraph's `Note:` margin notes), with words between
  two pictures, none twice, and an AI picture keeps its `*AI-generated ...*` credit line, the model only (no month or year, Chris 2026-11-04):
  `*AI-generated image (Google Gemini).*` (a PC's portrait: `*AI-generated portrait (Google Gemini).*`), with no
  "Not official art" or "Not player art": "AI-generated" already says it (Chris, 2026-11-04). Never what it
  was drawn from. It may add one short sentence a reader needs to read the picture right, e.g. the
  golem's "The flowers above its rope crown are Aera’s illusion." (Chris, 2026-11-04): that line is the
  caption readers see. Every credit names what it shows in a few words: in a post the build adds
  "of <wiki page>" (linked), on a wiki page "of <page title>" (`article.name_ai_subjects`); a picture with
  no wiki page writes its own "*AI-generated image of <1-5 words> (Google Gemini).*". A picture's alt text also shows on hover. A post with more than one picture names its feature picture in
  the front matter (`feature: name.jpg`): it gives the link preview and the home page card, and goes first under `picture: top`. When the post has an AI picture the feature is one of them, never a photo of the table (Chris, 2026-11-04).
  Check pictures against the story for spoilers: no form, identity or outcome before the story reveals
  it. Reuse a wiki picture before making one. `tests/test_post_format.py` checks the rules.
- The look settings in `data/post-style.yaml` (Chris's picks) decide how that format becomes a page
  (`poststyle.apply_format`): pills, "Malron’s Account" over the story, gold links, scene headings
  shown or not. Change the look there, not in the posts.
- Every post reads in one order (layout review, Chris, 2026-11-02): title, tagline, PC pills, the
  slides, "Malron’s Account" (all of the story, its opening lines and pictures too), the recap lists
  (Key Locations, Encounters, Loot, Notable NPCs, Plot Points, Session Highlights; every entry a
  bullet), then the map. No second title above the story. `tests/test_layout.py` checks every post.
- Every Plot Points entry is told in Malron’s Account (Chris, 2026-11-03: "Feels odd if they list
  something that wasn't already mentioned above"). `data/plot-points.yaml` names, for each entry, a
  phrase from the account that tells it, and `tests/test_plot_points.py` checks every post. When the
  story leaves a plot point out, add it to the story from the transcript, Chris's notes or Ryan's
  texts; never invent it.
- Wiki links: the first mention of a name links in every section of the On this page box, every
  scene and every recap list, so a reader who jumps to a section finds its links (Chris,
  2026-11-02). The build does this (`relink: each-heading`); don't hand-link repeats.
- Posts read as Malron's journal: first person, in-world, no dice or rules talk, no DM or player
  names. Table talk goes only in a `Note:` paragraph, which renders as a handwritten margin note,
  and only notes Chris picks. Real player names appear only on each PC's own wiki page.
- No room codes from the book (K20, K-62, room S15) in Malron's words (Chris, 2026-11-03): name or
  describe the room instead. A code worth keeping for readers goes in a `Note:` margin paragraph.
  On the wiki the same holds for Malron's Account and the adventure-log lines: a page that is a room
  in the book keeps its code in `book_room:` front matter, shown in the facts box ("In the book").
  `tests/test_room_codes.py` checks every post and wiki page.
- The map (`barovia_map.py`) is our own drawing. Never trace or embed a published Curse of Strahd
  map in the repo; a licensed background, if we ever get one, is an overlay swap, not a commit here.
- The map's roads, tracks, rivers, lakes, forests, mountains and labels are data in
  `data/geography.yaml`, not code; `just map-edit` edits that file, and hand edits go there too.
  A winding stretch can be a shape (`{bends, width}` switchbacks or `{wiggle}`) instead of many points.
- One layout for every wiki page (Chris, 2026-11-02): `data/wiki-style.yaml` and `wikistyle.py`
  lay out the rendered page at build time: the first picture at the top in a facts box (other
  names, first and last session seen), the `## Description` shown as "Malron’s Account", any stat
  block after it, and "From the adventure log" folded under a story. Keep writing pages as before
  (`## Description`, picture inside it); change the look in the yaml, not in the pages.
- Every AI picture we host keeps its full-size original (Chris, 2026-11-02): the page shows the
  smaller copy in `static/images/` (720px wide portraits, 1100px landscapes) and the original
  Gemini picture, full size as a JPEG, goes in `static/images/full/` under the same name. The build gives the picture a
  `data-full` address and the picture viewer loads it only when a reader taps the picture.
- Pages full of pictures load small copies (Chris, 2026-11-04: Start here loaded 1.5 MB of full-size
  pictures). The build makes them; never commit or link a hand-made small copy. Home cards use
  `images/cards/` (`make_card_pictures`), wiki list cards and faces `images/thumbs/` (`make_thumbnails`),
  Start here `images/small/` (`make_start_pictures`: 400px portraits, 800/1100px chapter pictures in a
  `srcset`, the castle at 1100px). Wiki articles and session logs keep the full-size pictures. A new
  page with a grid of pictures goes in `GRID_PAGES` in `tests/test_picture_weight.py` and gets small
  copies the same way; that test fails when a grid page loads a full-size picture or one over 100 KB,
  or when any other page that is not an article shows more than 6 pictures.
