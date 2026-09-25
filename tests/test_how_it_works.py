"""
docs/HOW-IT-WORKS.md says which version it describes, and must say the current one.

The explainer is written for librarians and quotes numbers -- tests passed, the
corpus outcomes, the round trip -- that move with the tool. A guide that
describes an older version without saying so misleads the people it is for.
This does not check the prose; it makes each release look at it, by failing
until the "Describes version" line is moved up to about.json's version.
"""

from __future__ import annotations

import json
import re

from conftest import REPO_ROOT


def test_the_guide_describes_the_current_version():
    about = json.loads((REPO_ROOT / "marc_serials" / "shared" / "about.json")
                       .read_text(encoding="utf-8"))
    guide = (REPO_ROOT / "docs" / "HOW-IT-WORKS.md").read_text(encoding="utf-8")
    stated = re.search(r"Describes version (\d+\.\d+\.\d+)", guide)
    assert stated, "the guide no longer says which version it describes"
    assert stated.group(1) == about["version"], (
        f"docs/HOW-IT-WORKS.md describes {stated.group(1)}, the tool is "
        f"{about['version']}: check the guide against this release, update "
        "its numbers, and move the version up")
    assert f"as of {about['version']}" in guide, (
        "the checks table still gives its results for an older version")
