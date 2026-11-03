set dotenv-load
set windows-shell := ["pwsh", "-NoLogo", "-NoProfile", "-Command"]

py := if os_family() == "windows" { "py -3.13" } else { "python3" }
python := if os_family() == "windows" { ".venv/Scripts/python.exe" } else { ".venv/bin/python" }

default:
    @just --list

# Create .venv with the site and import/test dependencies
setup:
    {{py}} -m venv .venv
    {{python}} -m pip install -r requirements-dev.txt

# Run the unit tests
test:
    {{python}} -m pytest -q

# Convert an Obsidian Portal export folder into content/posts/ (safe to re-run)
import export:
    {{python}} tools/import_op.py "{{export}}"

# Import Obsidian Portal character and wiki pages (a JSON export; see tools/import_op_wiki.py)
import-wiki export:
    {{python}} tools/import_op_wiki.py "{{export}}"

# Add what the adventure logs say to the wiki (default input: data/log-extract/*.json)
wiki-from-log *files:
    {{python}} tools/wiki_from_extract.py {{files}}

# Spell names the Curse of Strahd way (data/spellings.yaml); add --check to only list them
spellings *args:
    {{python}} tools/fix_spellings.py {{args}}

# Build the site into public/
build:
    {{python}} build.py

# Build, then serve public/ at http://localhost:8000 (Ctrl+C to stop)
serve port="8000":
    {{python}} build.py --serve --port {{port}}

# Compare the built site with main, page by page (a refactor must show "No changes")
site-diff *args:
    {{python}} tools/site_diff.py {{args}}

# Edit the map in your browser: drag sprites, roads, crossroads, rivers, lakes; each change saves to data/
map-edit port="8001":
    {{python}} tools/map_editor.py {{port}}

# Re-cut the map sprites from tools/sprite_sheets/ into static/images/map/sprites/
map-sprites:
    {{python}} tools/make_sprites.py

# Check the libraries copied into static/vendor/ (add --advisories to ask osv.dev for security problems)
vendor-check *args:
    {{python}} tools/vendor_check.py {{args}}
