"""
Things about the source that a different Python version would notice first.

This one was reported from a Windows machine running Python 3.12, where
`SyntaxWarning: invalid escape sequence '\\s'` prints on every start. The
development container runs 3.11, where the same problem is a DeprecationWarning
and silent by default, so nothing here caught it: a docstring in
marc_serials/detector.py quoted a regex without being a raw string.

Escape sequences that Python does not recognise have been deprecated for years
and are slated to become errors, so this is a real defect and not a style
preference. Asserted for every file, at the strictest setting, so the suite
fails wherever it is run rather than only where the warning happens to be loud.

Every compile-time warning counts, not only the escape sequence that prompted
this. `SyntaxWarning: "is" with a literal` is the same defect in a different
costume -- silent on one version, loud on another, and wrong on both -- and
there is no reason to let it past a test that is already compiling the file.
"""

from __future__ import annotations

import pathlib
import warnings

import pytest

from conftest import REPO_ROOT


def _python_files() -> list[pathlib.Path]:
    return sorted(p for p in REPO_ROOT.rglob("*.py")
                  if "__pycache__" not in p.parts
                  and ".git" not in p.parts
                  and ".venv" not in p.parts)


def test_there_are_files_to_check():
    """A glob that silently matches nothing would make the test below vacuous."""
    assert len(_python_files()) >= 15


@pytest.mark.parametrize("path", _python_files(), ids=lambda p: p.name)
def test_compiles_without_warnings(path: pathlib.Path):
    """
    A string that means to hold a backslash must say so.

    Either a raw string (r"\\s*") or a doubled backslash. The usual way this
    slips in is a docstring quoting a regex, which is exactly what happened.

    The line a warning reports for a docstring is its *closing* quotes, not the
    escape, so the fix is usually a few lines above where this points.
    """
    source = path.read_text(encoding="utf-8")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        compile(source, str(path), "exec")
    problems = [f"line {w.lineno}: {w.category.__name__}: {w.message}" for w in caught
                if issubclass(w.category, (SyntaxWarning, DeprecationWarning))]
    assert not problems, f"{path.relative_to(REPO_ROOT)} -> {problems}"
