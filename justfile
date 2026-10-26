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

# Build the site into public/
build:
    {{python}} build.py

# Build, then serve public/ at http://localhost:8000 (Ctrl+C to stop)
serve port="8000":
    {{python}} build.py --serve --port {{port}}
