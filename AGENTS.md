# Working in strahd-log

- Python 3.13 (`py -3.13` on Windows), run through `just` recipes. `just test` before finishing any change.
- Recipe lines must work in both pwsh and sh. Put logic in Python, not in shell.
- Read and write text with `encoding="utf-8"`; tests must not depend on line endings or the OS.
- Tests build their own fixtures in `tmp_path`; never depend on the Obsidian Portal export folder.
- The site build needs only `requirements.txt`; keep importer and test packages in `requirements-dev.txt`.
- No external JavaScript on the site. It must stay readable on a phone.
- Wiki text above `<!-- from-the-log -->` is ours; only the section after it is generated. Tools
  and agents add facts there, each citing the post it came from, and never edit the text above.
- Wiki aliases are linked automatically everywhere, so an alias must not be an ordinary word
  ("Abbot", "Manor" in another town); `tools/wiki_from_extract.py` keeps a list of words to refuse.
- Posts are the players' own writing. Fix conversion problems in `tools/import_op.py`, not by
  rewording a post, unless Chris asks.
