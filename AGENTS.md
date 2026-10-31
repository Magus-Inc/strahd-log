# Working in strahd-log

- Python 3.13 (`py -3.13` on Windows), run through `just` recipes. `just test` before finishing any change.
- Recipe lines must work in both pwsh and sh. Put logic in Python, not in shell.
- Read and write text with `encoding="utf-8"`; tests must not depend on line endings or the OS.
- Tests build their own fixtures in `tmp_path`; never depend on the Obsidian Portal export folder.
- The site build needs only `requirements.txt`; keep importer and test packages in `requirements-dev.txt`.
- No external JavaScript on the site. It must stay readable on a phone.
- Wiki text above `<!-- from-the-log -->` is ours; only the section after it is generated. Tools
  add facts there, each citing the post it came from. Above it, agents may write and extend a
  `## Description` in Malron's words from the posts (see `.claude/skills/update-wiki`), but never
  reword text someone else wrote, such as the Obsidian Portal pages.
- Wiki aliases are linked automatically everywhere, so an alias must not be an ordinary word
  ("Abbot", "Manor" in another town); `tools/wiki_from_extract.py` keeps a list of words to refuse.
- Posts are the players' own writing. Fix conversion problems in `tools/import_op.py`, not by
  rewording a post, unless Chris asks.
- Names are spelled as the Curse of Strahd book spells them (`data/spellings.yaml`; `just spellings`
  fixes new text). The book fixes spellings only: what happened comes from the posts and Chris.
- Posts read as Malron's journal: first person, in-world, no dice or rules talk, no DM or player
  names. Table talk goes only in a `Note:` paragraph, which renders as a handwritten margin note,
  and only notes Chris picks. Real player names appear only on each PC's own wiki page.
- The map (`barovia_map.py`) is our own drawing. Never trace or embed a published Curse of Strahd
  map in the repo; a licensed background, if we ever get one, is an overlay swap, not a commit here.
