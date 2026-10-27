# Contributing

Thanks for helping keep the Curse of Strahd log tidy. Changes come in as pull requests; Chris
reviews and merges them, and every merge to `main` publishes the site.

## Adding a session post

1. Fork the repository (or make a branch if you have write access).
2. Add `content/posts/YYYY-MM-DD-<slug>.md`, for example
   `content/posts/2026-09-15-into-the-amber-temple.md`:

   ```markdown
   ---
   title: 'Into the Amber Temple'
   date: '2026-09-15T21:00:00-05:00'
   tagline: Cold, dark and whispering
   tags: [Amber Temple, Vasilka]
   ---

   ## At a Glance:

   * **The climb:** ...
   ```

   `title` and `date` are required. `date` is the session's start in Central time, with the
   offset (`-05:00` in summer, `-06:00` in winter). Quote a title that contains a colon.
   `slug` defaults to the file name without the date; `tagline` and `tags` are optional.
3. Check it locally (needs Python 3.13 and [just](https://github.com/casey/just)):

   ```
   just setup     # once
   just test
   just serve     # then open http://localhost:8000
   ```

4. Open a pull request. The checks run the tests and a full build; fix anything they flag.

## Fixing an existing post

Edit the Markdown file in `content/posts/` directly. The posts came from Obsidian Portal through
`tools/import_op.py`; do not re-run the import, or it will overwrite edits made since.

## Wiki pages

Each page is `content/wiki/<name>.md`. Write anything above the `<!-- from-the-log -->` line; the
section below it ("From the adventure log") is generated from the posts and is replaced when the
wiki is rebuilt, so fix a wrong fact there by fixing the post or by noting the correction above the
line. Add `aliases:` for other names a page goes by and posts will link to it automatically.

## Other changes

The site's look lives in `templates/` and `static/style.css`; the build is `build.py`. Keep the
site readable on a phone and free of external JavaScript, and add or update tests in `tests/`
for code changes. See `AGENTS.md` for the conventions.

## Deploys

GitHub Pages publishes the site at <https://owlbear.dicelore.quest/> about a minute after a pull
request is merged to `main`. Every pull request gets the same tests and build first, so a broken
post is caught before it goes live.
