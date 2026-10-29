"""
docs/HOW-IT-WORKS.md says which version it describes, and must say the current one.
So does docs/QUICK-START.md, which also names what to press, as the page names it.

The explainer is written for librarians and quotes numbers -- tests passed, the
corpus outcomes, the round trip -- that move with the tool. A guide that
describes an older version without saying so misleads the people it is for.
This does not check the prose; it makes each release look at it, by failing
until the "Describes version" line is moved up to about.json's version.
"""

from __future__ import annotations

import json
import re

from conftest import REPO_ROOT, page_source


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


# What the quick start tells a cataloguer to press or look for, as the page
# says it. Each must still be on the page under that name, and still in the
# guide: a button renamed on screen and not in the guide sends a first-time
# user looking for something that is not there.
QUICK_START_LABELS = [
    # (as the guide writes it, as the page's source has it)
    ("Drop the file on the box", "Drop a MARC file here, or click to browse"),
    ("Pattern library", "Pattern library"),
    ("**Import**", ">Import<"),
    ("**Export**", ">Export<"),
    ("Or paste 866 statements", "Or paste 866 statements"),
    ("**Use these statements**", "Use these statements"),
    ("**⟳ Find patterns**", "⟳ Find patterns"),
    ("still wants an answer", "still ${undecided === 1 ? 'wants' : 'want'}"),
    ("supplies a caption", "supplies' : 'supply'"),
    ("decides how a statement is read", "decides' : 'decide'"),
    ("**Review**", ">Review<"),
    ("**Confirm pattern**", "Confirm pattern"),
    ('"not read"', "not read</span>"),
    ("**Edit**", ">Edit</button>"),
    ("**Split**", ">Split</button>"),
    ('"Statements to look at"', "Statements to look at"),
    ("**Conversion settings**", "Conversion settings</summary>"),
    ("Frequency (853 `$w`)", "Frequency (853 $w)"),
    ("Numbering (853 `$v`)", "Numbering (853 $v)"),
    ("Issues per volume (853 `$u`)", "Issues per volume (853 $u)"),
    ("Holdings reported at (863 first indicator)", "Holdings reported at (863 first indicator)"),
    ("When something would be left out to fit MARC", "When something would be left out to fit MARC"),
    ("Clear existing 853 / 863 first", "Clear existing 853 / 863 first"),
    ("**Needs attention**", ">Needs attention<"),
    ("**Something left out**", ">Something left out<"),
    ("**This record's 853**", "This record's 853"),
    ("**Skip**", "> Skip</label>"),
    ("**Reviewed**", "> Reviewed</label>"),
    ("**Close**", "▴ Close"),
    ("**Remove each 866 once it has been converted**", "Remove each 866 once it has been converted"),
    ("**Convert all records**", "Convert all records"),
    ("**Download .mrc**", "Download .mrc"),
    ("**Download log**", "Download log"),
    ("**100% matched**", "% matched</span>"),
    ("**Confirmed**", ">Confirmed</span>"),
    ("**needs a decision**", "needs a decision</span>"),
    ('"To check:"', "To check:"),
    ('"Left out to fit MARC:"', "Left out to fit MARC:"),
]


def _quick_start() -> str:
    return (REPO_ROOT / "docs" / "QUICK-START.md").read_text(encoding="utf-8")


def test_the_quick_start_describes_the_current_version():
    about = json.loads((REPO_ROOT / "marc_serials" / "shared" / "about.json")
                       .read_text(encoding="utf-8"))
    stated = re.search(r"Describes version (\d+\.\d+\.\d+)", _quick_start())
    assert stated, "the quick start no longer says which version it describes"
    assert stated.group(1) == about["version"], (
        f"docs/QUICK-START.md describes {stated.group(1)}, the tool is "
        f"{about['version']}: walk through it against this release (every "
        "button it names, in order) and move the version up")


def test_what_the_quick_start_names_is_on_the_page():
    guide = _quick_start()
    page = page_source()
    for in_guide, on_page in QUICK_START_LABELS:
        assert in_guide in guide, f"the quick start no longer says {in_guide!r}"
        assert on_page in page, (
            f"the quick start says {in_guide!r}, and the page no longer has "
            f"{on_page!r}: rename it in the guide too")


def test_the_guides_point_at_each_other():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    how = (REPO_ROOT / "docs" / "HOW-IT-WORKS.md").read_text(encoding="utf-8")
    assert "docs/QUICK-START.md" in readme
    assert "(QUICK-START.md)" in how
    assert "(HOW-IT-WORKS.md)" in _quick_start()


def test_the_code_map_names_every_file_and_the_current_version():
    """
    docs/CODE-MAP.md is how the cataloguer keeps track of where everything is,
    written when the page was split into files of its own (0.48.0). A file
    added and not on the map, or one renamed, leaves it describing a project
    that is not there -- so this fails until the map is brought up to date.
    """
    code_map = (REPO_ROOT / "docs" / "CODE-MAP.md").read_text(encoding="utf-8")
    about = json.loads((REPO_ROOT / "marc_serials" / "shared" / "about.json")
                       .read_text(encoding="utf-8"))
    stated = re.search(r"Describes version (\d+\.\d+\.\d+)", code_map)
    assert stated and stated.group(1) == about["version"], (
        "docs/CODE-MAP.md describes another version: check it against this "
        "release and move the version up")
    package = REPO_ROOT / "marc_serials"
    engine = [p.name for p in package.glob("*.py") if p.name != "__init__.py"]
    page = [str(p.relative_to(package)) for p in (package / "static").rglob("*")
            if p.is_file()] + ["templates/tool.html"]
    missing = [name for name in engine + page if f"`{name}`" not in code_map]
    assert not missing, f"docs/CODE-MAP.md does not say what these are: {missing}"
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "docs/CODE-MAP.md" in readme
