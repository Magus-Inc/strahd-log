# Working in strahd-log

- Python 3.13 (`py -3.13` on Windows), run through `just` recipes. `just test` before finishing any change.
- Recipe lines must work in both pwsh and sh. Put logic in Python, not in shell.
- Read and write text with `encoding="utf-8"`; tests must not depend on line endings or the OS.
- Tests build their own fixtures in `tmp_path`; never depend on the Obsidian Portal export folder.
- The site build needs only `requirements.txt`; keep importer and test packages in `requirements-dev.txt`.
- No external JavaScript on the site. It must stay readable on a phone.
- Posts are the players' own writing. Fix conversion problems in `tools/import_op.py`, not by
  rewording a post, unless Chris asks.
