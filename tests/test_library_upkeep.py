"""How well a library is kept up (Chris, 2026-11-03): age, last release, whether bug and security
fixes are landing, stable versus abandoned, and popularity are all weighed and written down for
every library we use, the ones copied into static/vendor/ and the Python packages alike."""
import datetime as dt
import pytest
import yaml

import vendor_check

from test_vendor import UPKEEP as GOOD, write_lib

TODAY = dt.date(2026, 11, 3)


def upkeep(**override):
    return vendor_check.upkeep_problems("tiny", {**GOOD, **override}, today=TODAY)


def test_a_well_kept_popular_library_passes():
    assert upkeep() == []


@pytest.mark.parametrize("key", ["first_release", "last_release", "weekly_downloads", "maintenance", "fixes", "checked"])
def test_every_upkeep_fact_is_written_down(key):
    assert any(f"missing {key}" in p for p in upkeep(**{key: None}))


def test_dates_must_be_dates():
    assert any("last_release" in p and "date" in p for p in upkeep(last_release="last spring"))


def test_maintenance_is_one_of_the_named_states():
    assert any("maintenance" in p for p in upkeep(maintenance="fine"))


def test_a_library_under_a_year_old_is_marked_new():
    assert any("new" in p for p in upkeep(first_release=dt.date(2026, 3, 1), risks=["Young."]))


def test_a_new_library_is_not_refused_but_must_list_its_risks():
    assert upkeep(first_release=dt.date(2026, 3, 1), maintenance="new",
                  risks=["Under a year old: nobody knows yet whether it will be kept up."]) == []
    assert any("risk" in p for p in upkeep(first_release=dt.date(2026, 3, 1), maintenance="new"))


def test_two_quiet_years_must_be_called_stable_or_unmaintained():
    quiet = dt.date(2024, 6, 1)
    assert any("stable" in p and "unmaintained" in p for p in upkeep(last_release=quiet))
    assert upkeep(last_release=quiet, maintenance="stable",
                  fixes="Finished: small, no open bug or security reports, maintainer still answers issues.") == []


def test_an_unmaintained_library_is_a_listed_risk():
    assert any("risk" in p for p in upkeep(maintenance="unmaintained"))
    assert upkeep(maintenance="unmaintained", risks=["No fixes since 2023: we would have to patch it ourselves."]) == []


def test_a_little_used_library_lists_low_popularity_as_a_risk():
    assert any("downloads" in p for p in upkeep(weekly_downloads=300))
    assert upkeep(weekly_downloads=300, risks=["Few users, so few eyes on bugs."]) == []


def test_dates_run_in_order_and_not_past_today():
    assert any("first_release" in p for p in upkeep(first_release=dt.date(2026, 10, 1)))
    assert any("checked" in p for p in upkeep(checked=dt.date(2027, 1, 1)))


def test_risks_are_a_list_of_sentences():
    assert any("risks" in p for p in upkeep(risks="some"))


def test_a_copied_library_needs_its_upkeep_written_down(tmp_path):
    write_lib(tmp_path, maintenance=None)
    found = vendor_check.problems(tmp_path)
    assert any("missing maintenance" in p for p in found)


def test_a_copied_library_with_its_upkeep_passes(tmp_path):
    write_lib(tmp_path)
    assert vendor_check.problems(tmp_path) == []


# Python packages: every one in requirements*.txt is listed in data/python-libraries.yaml.

def write_python(root, requirements="Pillow==13.0.0\nPyYAML==6.0.3\n", listed=("Pillow", "PyYAML"), **override):
    (root / "requirements.txt").write_text(requirements, encoding="utf-8")
    (root / "data").mkdir(exist_ok=True)
    libs = [{"name": n, "why": "Example.", **GOOD, **override} for n in listed]
    (root / "data" / "python-libraries.yaml").write_text(yaml.safe_dump({"libraries": libs}), encoding="utf-8")


def test_listed_python_packages_pass(tmp_path):
    write_python(tmp_path)
    assert vendor_check.python_problems(tmp_path) == []


def test_a_python_package_left_off_the_list_is_caught(tmp_path):
    write_python(tmp_path, requirements="Pillow==13.0.0\nPyYAML==6.0.3\nrequests==2.0\n")
    assert any("requests" in p and "not listed" in p for p in vendor_check.python_problems(tmp_path))


def test_a_listed_python_package_no_longer_required_is_caught(tmp_path):
    write_python(tmp_path, listed=("Pillow", "PyYAML", "textile"))
    assert any("textile" in p and "not in requirements" in p for p in vendor_check.python_problems(tmp_path))


def test_package_names_match_however_they_are_written(tmp_path):
    write_python(tmp_path, requirements="-r other.txt\n# comment\npillow==13.0.0  # images\npyyaml>=6\n")
    (tmp_path / "other.txt").write_text("", encoding="utf-8")
    assert vendor_check.python_problems(tmp_path) == []


def test_python_packages_need_their_upkeep_and_why(tmp_path):
    write_python(tmp_path, why="", maintenance=None)
    found = vendor_check.python_problems(tmp_path)
    assert any("missing why" in p for p in found) and any("missing maintenance" in p for p in found)


def test_the_repos_own_python_list_passes():
    assert vendor_check.python_problems(vendor_check.ROOT) == []


def test_python_pins_are_looked_up_for_advisories_too(tmp_path):
    write_python(tmp_path)
    asked = []

    def fake_osv(package, version, ecosystem):
        asked.append((package, version, ecosystem))
        return []

    assert vendor_check.advisories(tmp_path, query=fake_osv) == []
    assert asked == [("Pillow", "13.0.0", "PyPI"), ("PyYAML", "6.0.3", "PyPI")]


# The monthly re-check: today's registry facts against the same rules.

def fake_registry(**facts):
    base = {"first_release": dt.date(2015, 1, 1), "last_release": dt.date(2026, 10, 1),
            "weekly_downloads": 250_000, "latest": "1.2.3"}

    def fetch(package, ecosystem):
        return {**base, **facts}
    return fetch


def test_the_recheck_finds_nothing_when_all_is_well(tmp_path):
    write_lib(tmp_path)
    assert vendor_check.recheck(tmp_path, fetch=fake_registry(), today=TODAY) == []


def test_the_recheck_flags_an_active_library_that_went_quiet(tmp_path):
    write_lib(tmp_path)
    found = vendor_check.recheck(tmp_path, fetch=fake_registry(last_release=dt.date(2024, 1, 1)), today=TODAY)
    assert any("tiny" in p and "stable" in p for p in found)


def test_the_recheck_flags_a_newer_release_of_a_copied_library(tmp_path):
    write_lib(tmp_path)
    found = vendor_check.recheck(tmp_path, fetch=fake_registry(latest="1.3.0"), today=TODAY)
    assert any("1.3.0" in p and "1.2.3" in p for p in found)


def test_the_recheck_flags_a_python_pin_a_major_version_behind(tmp_path):
    # Older lines stop getting fixes (Pillow 11.3.0 had about 90 advisories fixed in 13.0.0). A pin a
    # patch or two behind is normal and not worth an issue every month.
    write_python(tmp_path, requirements="Pillow==11.3.0\nPyYAML==6.0.3\n")
    latest = {"Pillow": "13.0.0", "PyYAML": "6.0.4"}
    base = fake_registry()
    found = vendor_check.recheck(tmp_path, fetch=lambda p, eco: {**base(p, eco), "latest": latest[p]}, today=TODAY)
    assert [p for p in found if "13.0.0" in p and "11.3.0" in p and "Pillow" in p]
    assert not [p for p in found if "PyYAML" in p]


def test_the_recheck_asks_for_a_fresh_look_once_a_year(tmp_path):
    write_lib(tmp_path, **{**GOOD, "checked": dt.date(2025, 9, 1)})
    found = vendor_check.recheck(tmp_path, fetch=fake_registry(), today=TODAY)
    assert any("2025-09-01" in p and "look again" in p for p in found)


def test_the_monthly_workflow_runs_the_recheck_and_keeps_one_issue():
    flow = yaml.safe_load((vendor_check.ROOT / ".github" / "workflows" / "vendor-check.yml").read_text(encoding="utf-8"))
    steps = "\n".join(str(s.get("run", "")) for s in flow["jobs"]["advisories"]["steps"])
    assert "tools/vendor_check.py --recheck" in steps
    assert steps.count("gh issue list") >= 2 and steps.count("gh issue comment") >= 2


def test_the_written_rule_names_every_upkeep_fact():
    rule = (vendor_check.ROOT / "AGENTS.md").read_text(encoding="utf-8")
    for word in ("data/python-libraries.yaml", "maintenance", "popular", "security fixes", "stable", "abandoned"):
        assert word in rule, word
