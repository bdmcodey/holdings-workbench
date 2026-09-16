"""
Every source file in the repository compiles without a warning about its own
text.

This exists because of one bug and the shape of it is worth keeping. A regex
written into an ordinary (non-raw) string or docstring -- ``"\\s*"`` rather than
``r"\\s*"`` -- is an *invalid escape sequence*. Python does not reject it; it
keeps the backslash and warns. Which warning you get depends on the version:

    3.10, 3.11    DeprecationWarning   -- silent unless you ask for it
    3.12 onward   SyntaxWarning        -- printed to the terminal on first run

So the same source is clean on one developer's machine and noisy on another's,
and the one who sees it is the one who has to decide whether it matters. This
test fails on either, so the suite catches it wherever it runs.

Two details, both learned the hard way:

*Compile the text, don't import the module.* Python emits these warnings when it
byte-compiles a file. Once ``__pycache__`` holds a current ``.pyc`` the compile
step is skipped and the warning never comes back -- so a test that imported the
package would pass on every run after the first, including in CI with a warm
cache. ``compile()`` on the source text always re-checks it.

*Walk the whole repository, not just the package.* ``scripts/`` and ``tests/``
are source too, and a corpus report that prints a stray backslash is the same
defect in a place nobody imports.
"""

from __future__ import annotations

import warnings
from typing import List, Tuple

from conftest import REPO_ROOT

# Directories that hold code we did not write, or output rather than source.
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "build", "dist", "node_modules"}

# Both spellings of the same complaint. Listed rather than caught as a single
# base class because they are unrelated in the hierarchy, and because naming
# them documents which Python versions this is defending against.
COMPILE_WARNINGS = (SyntaxWarning, DeprecationWarning)


def _source_files() -> List:
    return sorted(
        p for p in REPO_ROOT.rglob("*.py")
        if not (SKIP_DIRS & set(p.parts)) and not p.name.endswith(".egg-info")
    )


def _complaints(path) -> List[Tuple[int, str]]:
    """Compile one file's text and return whatever Python said about it."""
    text = path.read_text(encoding="utf-8")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        compile(text, str(path), "exec")
    return [
        (w.lineno, f"{w.category.__name__}: {w.message}")
        for w in caught
        if issubclass(w.category, COMPILE_WARNINGS)
    ]


def test_the_suite_can_see_the_source():
    """
    A guard on the guard. If the walk below ever returns nothing -- a renamed
    directory, a changed layout -- the real test would pass by finding no files
    to check, which is the failure mode that makes a test useless quietly.
    """
    files = _source_files()
    assert len(files) > 20, f"only found {len(files)} source files to check"
    names = {p.name for p in files}
    assert "detector.py" in names
    assert "corpus_report.py" in names


def test_no_source_file_compiles_with_a_warning():
    """
    The failure message names the file, the line and the text, because the
    warning itself is the only clue to where a stray backslash is: the line
    reported for a docstring is its *closing* quotes, not the escape.

    Fix is almost always to make the string raw -- ``r"..."`` -- which leaves
    what it holds byte-for-byte identical and stops Python reading the
    backslash as an escape it does not know.
    """
    found = []
    for path in _source_files():
        for lineno, message in _complaints(path):
            found.append(f"{path.relative_to(REPO_ROOT)}:{lineno}  {message}")

    assert not found, "source files compile with warnings:\n  " + "\n  ".join(found)
