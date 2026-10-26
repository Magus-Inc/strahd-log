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

# Build the site into public/
build:
    {{python}} build.py

# Build, then serve public/ at http://localhost:8000 (Ctrl+C to stop)
serve port="8000":
    {{python}} build.py --serve --port {{port}}
