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
