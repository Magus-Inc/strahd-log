# Strahd Log

A static site for our Curse of Strahd adventure log, moved off Obsidian Portal
(<https://curseofstrahdowlbear.obsidianportal.com/adventure-log>). Posts are Markdown files; a small
Python build turns them into plain HTML in `public/`, ready for Netlify.

## Layout

| Path | What it is |
| --- | --- |
| `content/posts/YYYY-MM-DD-<slug>.md` | One post each: YAML front matter, then the Markdown body |
| `build.py` | Builds `public/`: home page, `/posts/<slug>/`, `/tags/`, `/feed.xml` (Atom) |
| `templates/` | Jinja2 page templates |
| `static/` | `style.css` and the favicon, copied into `public/` as is |
| `tools/import_op.py` | One-off importer from an Obsidian Portal export (Textile) |
| `tests/` | pytest tests; they build their own fixtures |
| `netlify.toml` | Netlify build settings |
| `public/` | Build output (not in git) |

## Recipes

Needs Python 3.13 (`py -3.13` on Windows) and [just](https://github.com/casey/just). Recipes work in
PowerShell and sh.

```
just setup                      # create .venv and install requirements-dev.txt
just test                       # run the tests
just build                      # build the site into public/
just serve                      # build, then serve at http://localhost:8000 (just serve 9000 for another port)
just import <export-folder>     # re-import an Obsidian Portal export into content/posts/
```

`requirements.txt` holds only what the site build needs (what Netlify installs);
`requirements-dev.txt` adds the importer and test packages.

## Adding a post

1. Create `content/posts/YYYY-MM-DD-<slug>.md`, for example
   `content/posts/2026-09-15-into-the-amber-temple.md`:

   ```markdown
   ---
   title: 'Into the Amber Temple'
   date: '2026-09-15T21:00:00-05:00'
   tagline: Cold, dark and whispering
   tags: [Amber Temple, Vasilka]
   slug: into-the-amber-temple
   ---

   ## At a Glance:

   * **The climb:** ...
   ```

   `title` and `date` are required. `date` is ISO 8601 with the Central-time offset (`-05:00` in
   summer, `-06:00` in winter); posts sort by it. `slug` defaults to the file name without the date;
   it sets the page address `/posts/<slug>/`. `tagline` and `tags` are optional. Quote titles that
   contain a colon.
2. Run `just serve` and check the post at <http://localhost:8000/>.
3. Commit the file and open a pull request (see `CONTRIBUTING.md`). GitHub runs the tests and a
   build on every pull request; Netlify publishes the site when it is merged to `main`.

## Wiki and search

`content/wiki/<slug>.md` holds one page per character, person, place, item or faction. Front
matter: `title`, `type` (`character`, `npc`, `creature`, `place`, `item`, `faction`, `deity`,
`other`), optional `aliases`, `summary`, `player`, `source`. The build
(`wiki.py`):

- links the first mention of each page's title or alias in every post and wiki page,
- lists on every wiki page the sessions that mention it ("Appears in"),
- writes `/wiki/`, one page per entry, and `/search/` with a prebuilt `search-index.json`. Search
  runs in the browser with a few lines of the site's own JavaScript; no outside scripts.

Pages come from two places, and the tools keep them apart:

- **Written by us** (`source: Written on Obsidian Portal`, or anything you add by hand). Never
  rewritten by the tools except to re-import from Obsidian Portal.
- **Compiled from the adventure log.** `just wiki-from-log` reads entity lists in
  `data/log-extract/*.json` (name, type, aliases, summary, facts, each fact citing the post it came
  from) and adds a "From the adventure log" section below any hand-written text, or creates a
  draft page. Re-running replaces only that section, and regenerates the compiled draft pages
  (`source: Compiled from the adventure log`) from scratch. Reviewed fixes (two spellings of one
  person, a wrong fact, an alias that mislinks, a wrong type) go in
  `data/log-extract/corrections.yaml`, so they survive the extraction being redone. Today the lists were made by having Claude read
  the posts; the same step can later run on session transcripts and open a pull request for review.

```
just import-wiki <export.json>  # Obsidian Portal character and wiki pages (see tools/import_op_wiki.py)
just wiki-from-log              # merge data/log-extract/*.json into content/wiki/
```

## The map

`/map/` shows our own map of Barovia, drawn by `barovia_map.py` in the style of a hand-coloured
regional map: parchment, green conifer woods, snow-capped mountains, blue lakes and rivers, tan
roads and mist at the edges. It is generated from a fixed seed, so every build draws the same map;
the geography follows the table map, and nothing is traced from a published map. The base image,
`/map/barovia.svg`, is clean: places and the trail are an overlay, so the background can be
swapped later without touching anything else.

- The roads in `barovia_map.ROADS` (and dotted `TRACKS`) are also a graph. Each leg of the party's
  trail follows the roads between two places by the shortest route, drawn as a thin red
  breadcrumb line; repeat trips sit side by side, so a well-worn road shows several lines.
- Each session gets a small numbered marker where it ended; hover for its date and title, tap to
  read it. Markers for sessions that ended in the same place fan out around it.
- `data/map.yaml` places wiki pages on the map (each on a road vertex) and says which rooms and
  buildings are `within` which place. `data/trail.yaml` lists where the party actually went each
  session; mentions are not visits.
- On `/map/` a toggle shows or hides the trail, a slider steps through it session by session, and
  buttons zoom and pan. Each post shows "Where we were"; each place's wiki page shows where it is.

The footer carries the disclaimer the Wizards of the Coast Fan Content Policy asks for.

## Design

`static/style.css` is a dark editorial theme with one blood-red accent: a serif for display, the
system sans for reading, an 18px body on a 68-character measure, colours that meet WCAG AA. No web
fonts, frameworks or outside scripts; a few lines of the site's own JavaScript drive the map,
search, the wiki filter and the table of contents highlight. `article.py` adds the reading aids:
reading time, heading ids and a table of contents, the "At a Glance" callout, card teasers and
the cast list.

## Importing from Obsidian Portal

`just import ../strahd-blog-export` reads `posts/<slug>.textile` (with `title:`/`date:`/`tagline:`/
`tags:` header lines), `posts/<slug>.html` and `manifest.csv`, and writes one Markdown file per post.
Textile becomes HTML with the `textile` package, then Markdown with `markdownify`. Obsidian Portal
wiki links (`[[Page]]`, `[[Page | Text]]`, `[[:character | Text]]`) become normal links to the wiki
page, using the href from the rendered post HTML when present; `[[File:...]]` assets become images.
Re-running overwrites the imported files with identical output, so do not hand-edit an imported post
and then re-import.

## Netlify

`netlify.toml` installs `requirements.txt` and runs `python build.py`, publishing `public/`. The feed
uses Netlify's `URL` variable for absolute links (it falls back to `http://localhost:8000` locally).

## GitHub Pages preview

`.github/workflows/pages.yml` publishes a preview to <https://magus-inc.github.io/strahd-log/> on
every push to `main`. A site under a sub-path needs its links prefixed, so the build takes a base
path (`--base-path /strahd-log/` or the `BASE_PATH` variable); Netlify and `just serve` use `/`.
Pages needs the repository to be public and Settings > Pages > Source set to "GitHub Actions".
