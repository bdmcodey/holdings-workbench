"""
CHANGELOG.md is generated, and must stay current.

about.json is the source of truth: the application reads it for the version
badge and the "What has changed" panel, so it is the copy that gets kept up to
date. CHANGELOG.md exists for people reading the repository rather than running
the tool -- and a repository seeded fresh has no commit history to tell the
story, so it is the only place the story is told.

Two copies of one list drift. This is the test that stops them.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys

from conftest import REPO_ROOT

ABOUT = REPO_ROOT / "marc_serials" / "shared" / "about.json"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"
BUILDER = REPO_ROOT / "scripts" / "build_changelog.py"


def test_the_changelog_is_current():
    """
    Regenerate it with:

        python scripts/build_changelog.py
    """
    done = subprocess.run([sys.executable, str(BUILDER), "--check"],
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stderr or done.stdout


def test_every_released_version_appears():
    """
    The check above compares whole files, which would also pass if the builder
    and the changelog were wrong in the same way. This asserts the thing that
    actually matters, from the data rather than from the renderer.
    """
    about = json.loads(ABOUT.read_text(encoding="utf-8"))
    text = CHANGELOG.read_text(encoding="utf-8")

    versions = [entry["version"] for entry in about["changelog"]]
    assert versions, "about.json carries no changelog"
    missing = [v for v in versions if f"## {v} — " not in text]
    assert not missing, f"not in CHANGELOG.md: {missing}"


def test_the_current_version_is_the_newest_entry():
    """A release that bumps the version and forgets the entry is the usual slip."""
    about = json.loads(ABOUT.read_text(encoding="utf-8"))
    assert about["changelog"][0]["version"] == about["version"]


def test_the_packaged_version_matches_about_json():
    """
    The version is written down twice: about.json, which the application reads
    for its badge, and pyproject.toml, which is what `pip install` records.

    Nothing kept them together until this test. That is the shape of defect
    this project has fixed more than once -- a dependency pin that diverged
    across three requirements files, a data-loss fix applied to one copy of a
    function and not the other -- and a version that disagrees with itself is
    the same bug wearing a smaller hat: the screen says one thing and the
    installed package says another, and the report that follows is
    unreproducible.

    pyproject.toml is read as text rather than with a TOML parser, because
    tomllib arrived in 3.11 and the project supports 3.10.
    """
    about = json.loads(ABOUT.read_text(encoding="utf-8"))
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    declared = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.MULTILINE)
    assert declared, "pyproject.toml declares no version"
    assert declared.group(1) == about["version"], (
        f'pyproject.toml says {declared.group(1)}, '
        f'about.json says {about["version"]}'
    )
