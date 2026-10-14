"""
An expression copied for another tool matches what the workbench matches.

The workbench runs every expression through Python's `re`, ignoring case and
against the whole statement. marc_serials.flavours writes the same expression
for other tools, and the promise worth testing is that it means the same thing
there: the same statements match, and none extra.

Where the tool's own engine is on this machine -- Node for JavaScript, Perl for
PCRE, Java for Java and Alma's Drools rules -- the expression is run in that
engine, because a translation checked only against our idea of the target is
checked against the same mistakes that wrote it. Where the engine is missing
the test skips, visibly. Oracle cannot be run here; its output is written in a
subset that Python reads the same way, and is checked in Python.

Every expression the detector writes for the three corpora is checked, against
every corpus statement and its upper- and lower-case forms, so a flavour that
loses "ignore case" or "whole statement" fails here.
"""

from __future__ import annotations

import functools
import json
import re
import shutil
import subprocess
import sys

import pytest

from conftest import DATA_DIR, REPO_ROOT
from marc_serials.detector import detect_patterns
from marc_serials.flavours import (FLAVOURS, ORACLE_MAX_BYTES, choices,
                                   convert)

ENGINES = REPO_ROOT / "tests" / "engines"
CORPORA = ("textual_holdings_corpus.txt", "lc_holdings_examples.txt",
           "outside_catalog_examples.txt")


def _lines(path):
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")]


@functools.lru_cache(maxsize=None)
def corpus():
    """Every detector expression, and the statements to try them on."""
    regexes, statements = [], []
    for name in CORPORA:
        lines = _lines(DATA_DIR / name)
        statements += lines
        regexes += [g.regex for g in detect_patterns(lines) if g.regex]
    tried = list(dict.fromkeys(
        s for line in statements for s in (line, line.upper(), line.lower())))
    return tuple(regexes), tuple(tried)


# Hand-written expressions for what the detector never writes, but a
# cataloguer editing one might. Each with statements it should and should not
# match.
HAND = [
    (r"v\.(?P<vol>\d+)|no\.(?P<num>\d+)", ["v.12", "NO.3", "v.1 no.2", "x"]),
    (r"(?P<a>\d)-(?P=a)", ["1-1", "1-2"]),
    (r"(\d)\1", ["11", "12", "1"]),
    (r"(\d)\1 0", ["11 0", "110"]),
    (r"v\.(?=\d)\d+(?!x)", ["v.1", "v.1x", "v.x"]),
    (r"(?<=v\.)\d+", ["v.1"]),
    (r"[\]\-^a]+", ["]-^a", "b"]),
    (r"[-a^][\^-]", ["-^", "a-", "^^", "b-"]),
    (r"[^/\d]+/[\d/]+", ["ab/12/3", "a/b"]),
    (r"say \"so\" \\ ok", ['say "so" \\ ok', "say so ok"]),
    (r"a{,2}b{2,}c{3}", ["aabbccc", "bbccc", "aaabbccc"]),
    (r"x.{1,3}?y", ["x12y", "xy"]),
    (r"(?i)Spring|(?:Fall)", ["spring", "FALL", "winter"]),
    (r"^v\.1$", ["v.1", "v.12"]),
    (r"\bv\.\d+\b", ["v.1"]),
    (r"\x41\t?é", ["Aé", "A\té", "ae"]),
    (r"a{}b", ["a{}b"]),
    (r"a(?#a note)*b(?#another){2}", ["aabb", "b", "abbb", "a*b{2}"]),
    # Statements here hold no line breaks: see flavours.py on ".".
    (r"x\u2028?y", ["xy", "x y"]),
    (r"[&&a]+", ["&a", "b"]),
]


def _reference(regex, statements):
    compiled = re.compile(regex, re.IGNORECASE)
    return "".join("1" if compiled.fullmatch(s) else "0" for s in statements)


def _cases(flavour):
    """
    (converted text, statements, what the workbench matches) per expression.

    One set of statements for all of them -- the corpus, the hand-written
    cases' statements, and both case-forms of each -- so each engine starts
    once: starting Java costs about a second.
    """
    regexes, statements = corpus()
    tried = tuple(dict.fromkeys(statements + tuple(
        t for _, hand in HAND for s in hand for t in (s, s.upper(), s.lower()))))
    out = []
    for regex in list(regexes) + [regex for regex, _ in HAND]:
        result = convert(regex, flavour)
        if result.text:
            out.append((result.text, tried, _reference(regex, tried)))
    return out


def _run(cmd, stdin):
    done = subprocess.run(cmd, input=stdin, capture_output=True, text=True,
                          encoding="utf-8", timeout=300, cwd=ENGINES)
    assert done.returncode == 0, done.stderr
    return done.stdout


def _lines_body(regexes, statements):
    assert not any("\n" in t for t in list(regexes) + list(statements))
    return "\n".join(list(regexes) + ["--"] + list(statements)) + "\n"


def _check(cases, run_batch):
    """Run each case's text in the engine; compare with the workbench."""
    by_statements = {}
    for text, statements, want in cases:
        by_statements.setdefault(statements, []).append((text, want))
    for statements, items in by_statements.items():
        got = run_batch([t for t, _ in items], statements)
        assert len(got) == len(items)
        for (text, want), bits in zip(items, got):
            assert bits == want, (text, [s for s, w, g in
                                         zip(statements, want, bits) if w != g])


# ── The flavours, in their own engines ────────────────────────────────────────

def test_python_matches_with_search_alone():
    """The Python copy needs neither re.IGNORECASE nor fullmatch."""
    def run(texts, statements):
        return ["".join("1" if re.search(t, s) else "0" for s in statements)
                for t in texts]
    _check(_cases("python"), run)


@pytest.mark.skipif(not shutil.which("node"), reason="Node is not installed")
def test_javascript_in_node():
    def run(texts, statements):
        return json.loads(_run(["node", "match.js"], json.dumps(
            {"regexes": texts, "statements": statements})))
    _check(_cases("javascript"), run)


@pytest.mark.skipif(not shutil.which("perl"), reason="Perl is not installed")
def test_pcre_in_perl():
    def run(texts, statements):
        return _run(["perl", "match.pl"],
                    _lines_body(texts, statements)).splitlines()
    _check(_cases("pcre"), run)


@functools.lru_cache(maxsize=None)
def _java_ready():
    """Java 11 runs a single source file directly; older Java cannot."""
    if not shutil.which("java"):
        return False
    done = subprocess.run(["java", "-version"], capture_output=True, text=True)
    m = re.search(r'version "(\d+)', done.stderr)
    return bool(m) and int(m.group(1)) >= 11


@pytest.mark.skipif(not _java_ready(), reason="Java 11 or later is not installed")
def test_java_in_java():
    def run(texts, statements):
        return _run(["java", "Match.java"],
                    _lines_body(texts, statements)).splitlines()
    _check(_cases("java"), run)


@pytest.mark.skipif(not _java_ready(), reason="Java 11 or later is not installed")
def test_alma_rule_text_in_java():
    """Unquoted as a rule's string, and matched as Drools matches: whole value."""
    def run(texts, statements):
        return _run(["java", "Match.java"], _lines_body(
            ["alma:" + t for t in texts], statements)).splitlines()
    _check(_cases("alma"), run)


def _oracle_as_python(text):
    """Oracle's POSIX classes, in Python's spelling; the rest is the same."""
    for posix, python in (("[:digit:]", r"\d"), ("[:space:]", r"\s"),
                          ("[:alnum:]", "a-zA-Z0-9")):
        text = text.replace(posix, python)
    return text


def test_oracle_in_python():
    """
    Oracle is not here to run it; what it is given is checked in Python.

    REGEXP_LIKE(column, pattern, 'i') finds a statement when the pattern
    matches anywhere in it, which ^ and $ make the whole of it.
    """
    def run(texts, statements):
        return ["".join("1" if re.search(_oracle_as_python(t), s, re.IGNORECASE)
                        else "0" for s in statements) for t in texts]
    _check(_cases("oracle"), run)


# ── What each flavour can and cannot write ────────────────────────────────────

def test_every_flavour_writes_every_detector_expression_but_oracle():
    regexes, _ = corpus()
    assert len(regexes) >= 100
    for flavour in FLAVOURS:
        failed = [r for r in regexes if convert(r, flavour).error]
        if flavour == "oracle":
            # Measured at 0.36.0: 62 of 107 fit in 512 bytes, 45 do not.
            assert all("Too long for Oracle" in convert(r, flavour).error
                       for r in failed)
            assert len(failed) < len(regexes) / 2
        else:
            assert not failed, flavour


def test_oracle_is_refused_by_length_not_cut():
    regexes, _ = corpus()
    for regex in regexes:
        result = convert(regex, "oracle")
        if result.text:
            assert len(result.text.encode("utf-8")) <= ORACLE_MAX_BYTES
        else:
            assert re.search(r"\d+ bytes", result.error)


def test_oracle_output_has_no_perl_only_syntax():
    regexes, _ = corpus()
    for regex in regexes:
        text = convert(regex, "oracle").text
        if text:
            # No (?:, (?<name>, (?i) or lookaround: a "(?" not escaped.
            assert not re.search(r"(?<!\\)\(\?", text), text


@pytest.mark.parametrize("regex, what", [
    (r"v\.(?=\d)", "lookahead"),
    (r"(?<=v)\d", "lookbehind"),
    (r"\bv\b", "word boundary"),
    (r"(\d)\1", "back-reference"),
    (r"[\D]", r"\D inside"),
    (r"[\\a]", "backslash inside"),
])
def test_oracle_refuses_what_it_cannot_write(regex, what):
    result = convert(regex, "oracle")
    assert result.text is None and what in result.error
    assert result.error.startswith("Oracle SQL has no way to write")


@pytest.mark.skipif(sys.version_info < (3, 11),
                    reason="possessive repeats arrived in Python 3.11")
def test_possessive_and_atomic_where_the_flavour_lacks_them():
    assert convert(r"\d++", "pcre").text == r"(?i)^\d++$"
    assert convert(r"(?>\d+)", "java").text == r"(?iu)^(?>\d+)$"
    assert "possessive" in convert(r"\d++", "javascript").error
    assert "atomic" in convert(r"(?>\d+)", "oracle").error


def test_settings_other_than_ignore_case_are_refused():
    assert convert(r"(?i)v\.\d", "pcre").text == r"(?i)^v\.\d$"
    assert "(?x)" in convert(r"(?x)v \. \d", "pcre").error
    assert "(?s)" in convert(r"(?s:.)", "java").error


def test_shapes_of_each_flavour():
    regex = r"v\.(?P<start_num>\d+)/(?P<end_num_2>\d+)"
    assert convert(regex, "python").text == \
        r"(?i)^v\.(?P<start_num>\d+)/(?P<end_num_2>\d+)$"
    assert convert(regex, "pcre").text == \
        r"(?i)^v\.(?<start_num>\d+)/(?<end_num_2>\d+)$"
    assert convert(regex, "javascript").text == \
        r"/^v\.(?<start_num>\d+)\/(?<end_num_2>\d+)$/i"
    assert convert(regex, "java").text == \
        r"(?iu)^v\.(?<startNum>\d+)/(?<endNum2>\d+)$"
    assert convert(regex, "alma").text == \
        r"(?iu)v\\.(?<startNum>\\d+)/(?<endNum2>\\d+)"
    assert convert(regex, "oracle").text == r"^v\.\d+/\d+$"


def test_java_names_stay_distinct_and_backreferences_follow():
    result = convert(r"(?P<a_b>\d)(?P<aB>\d)(?P=a_b)", "java").text
    assert result == r"(?iu)^(?<aB>\d)(?<aB2>\d)\k<aB>$"


def test_top_level_alternation_is_grouped_before_anchoring():
    assert convert(r"v\.\d|no\.\d", "pcre").text == r"(?i)^(?:v\.\d|no\.\d)$"
    assert convert(r"v\.\d|no\.\d", "oracle").text == r"^(v\.\d|no\.\d)$"
    assert convert(r"v\.\d|no\.\d", "alma").text == r"(?iu)(?:v\\.\\d|no\\.\\d)"


def test_line_separators_are_escaped_in_a_javascript_literal():
    assert convert("x\u2028y", "javascript").text == r"/^x\u2028y$/i"


def test_brackets_escape_only_what_their_position_needs():
    assert convert(r"[-/]", "pcre").text == "(?i)^[-/]$"
    assert convert(r"[a\-z]", "pcre").text == r"(?i)^[a\-z]$"
    assert convert(r"[\^a^]", "pcre").text == r"(?i)^[\^a^]$"
    assert convert(r"[^^]", "javascript").text == "/^[^^]$/i"
    assert convert(r"[]a]", "javascript").text == r"/^[\]a]$/i"


def test_oracle_bracket_expressions():
    assert convert(r"[\s\d]", "oracle").text == "^[[:space:][:digit:]]$"
    assert convert(r"[\]\-^a]", "oracle").text == "^[]a^-]$"
    assert convert(r"[\-^]", "oracle").text == "^[-^]$"
    assert convert(r"[^^]", "oracle").text == "^[^^]$"
    assert convert(r"[\^]", "oracle").text == r"^\^$"
    assert convert(r"[\[a]", "oracle").text == "^[a[]$"


def test_oracle_shortening():
    # Groups that are only brackets go; a repeated one stays; \s*\s* is \s*;
    # a lazy repeat is greedy, which finds the same statements.
    assert convert(r"(?P<a>v\.)\s*\s*(?:x)?(?:ab)*.{1,3}?", "oracle").text == \
        r"^v\.\s*x?(ab)*.{1,3}$"
    assert convert(r"(a*)?", "oracle").text == "^(a*)?$"


def test_unusable_input():
    assert convert("", "pcre").error == "There is no expression."
    assert "not valid" in convert("v(", "pcre").error
    assert "longer than" in convert("a" * 5000, "pcre").error
    with pytest.raises(KeyError):
        convert("a", "perl6")


def test_choices_are_the_flavours_in_order():
    keys = [c["key"] for c in choices()]
    assert keys == ["python", "pcre", "javascript", "java", "alma", "oracle"]
    assert all(c["alert"] and c["severity"] in ("info", "warn")
               for c in choices())


# ── The endpoint ──────────────────────────────────────────────────────────────

def test_endpoint_converts_a_batch(client):
    response = client.post("/api/regex-flavour", json={
        "flavour": "javascript", "regexes": [r"v\.(?P<n>\d+)", "v("]})
    assert response.status_code == 200
    body = response.get_json()
    assert body["flavour"] == "javascript"
    assert body["results"][0] == {"text": r"/^v\.(?<n>\d+)$/i", "error": None}
    assert body["results"][1]["text"] is None
    assert "not valid" in body["results"][1]["error"]


@pytest.mark.parametrize("payload", [
    {"flavour": "cobol", "regexes": ["a"]},
    {"flavour": "pcre"},
    {"flavour": "pcre", "regexes": "a"},
    {"flavour": "pcre", "regexes": [1]},
    {"flavour": "pcre", "regexes": ["a"] * 5001},
])
def test_endpoint_refuses_bad_requests(client, payload):
    assert client.post("/api/regex-flavour", json=payload).status_code == 400


def test_page_offers_the_flavours(client):
    page = client.get("/").get_data(as_text=True)
    assert 'id="regex-flavour"' in page or "regex-flavour" in page
    for choice in choices():
        assert json.dumps(choice["label"]) in page
