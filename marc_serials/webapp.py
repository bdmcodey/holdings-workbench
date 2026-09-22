"""
The MARC Serials Toolkit application.

Upload a MARC file, detect the patterns in its 866 statements, confirm what
each captured value means, and convert with those patterns applied. A statement
no confirmed pattern matches is read by marc_serials.parser.parse_866(), so an
empty pattern library converts exactly as the plain parser does.

There was a time when this was three applications on three ports -- a
converter, a pattern detector, and this, which joined them up. They shared a
goal and duplicated each other's code, and the copies drifted: one of them
deleted the other's pattern libraries for six months. They are one application
now. The converter's screens and the detector's screens were both already here.

Run it:
    marc-serials                 (after `pip install -e .`)
    python run.py                (from a clone, without installing)

Both open http://localhost:5003. The port is settable with MARC_PORT; 5003
rather than 5000 because macOS gives 5000 to AirPlay Receiver.
"""

from __future__ import annotations

import io
import json
import logging
import os
import re
import sys
import time
from typing import Optional

# Run from a clone without installing: put the repository root on the path so
# `import marc_serials` resolves. A pip-installed copy already has it and this
# is a no-op.
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_BASE_DIR)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from flask import (Flask, jsonify, render_template, request, send_file,
                   send_from_directory, session)

try:
    from pymarc import MARCReader
    HAS_PYMARC = True
except ImportError:
    HAS_PYMARC = False

from marc_serials.store import (
    LIBRARY_EXT,
    LIBRARY_TTL_SECONDS,
    UPLOAD_TTL_SECONDS,
    file_path as _file_path,
    load_file as _load_file,
    purge_old_stored_files as _purge_old_stored_files,
    save_file as _save_file,
)
from marc_serials.converter import (
    DEFAULT_HOLDINGS_LEVEL,
    HOLDINGS_LEVELS,
    resolve_holdings_level,
    resolve_units_per_higher,
)
from marc_serials.records import (
    DEFAULT_IDENTIFIER_SPEC,
    identifier_candidates,
    parse_identifier_spec,
    record_identifier,
    add_853 as _add_853,
    apply_record_conversion as _apply_record_conversion,
    display_marc_field as _display_marc_field,
    encoding_level_conflict,
    encoding_level_differs,
    encoding_level_summary,
    single_part_conflict,
    match_866_sources as _match_866_sources,
    read_marc_file as _read_marc_file,
    records_from_bytes,
    refuse_unreadable,
    records_to_bytes as _records_to_bytes,
    remove_converted_866s as _remove_converted_866s,
)
from marc_serials.parser import parse_866
from marc_serials.converter import (CONVENTION_LEVELS, CONVENTION_STANDARD,
                            enum_level_fields,
                            FREQUENCY_CODES, convention_presets,
                            convert_holdings, convert_record, resolve_convention)
from marc_serials.detector import detect_patterns
from marc_serials.budget import (BACKTRACKING_PROBES, MatchFailed, MatchTimeout,
                          completes_within_budget, match_statements,
                          too_slow_message)

import marc_serials.library as plib
from marc_serials.bridge import (CAPTION_CHOICES, ENCODABLE_KINDS, KIND_IGNORE,
                            KIND_LABELS, KIND_UNRESOLVED,
                            PARSER_SOURCE, SKIPPED_SOURCE, UNMATCHED_SOURCE,
                            apply_patterns, build_parse_result, infer_roles,
                            split_statement)

# ---------------------------------------------------------------------------

app = Flask(__name__,
            template_folder=os.path.join(_BASE_DIR, "templates"),
            static_folder=os.path.join(_BASE_DIR, "static"))
app.secret_key = os.environ.get("SECRET_KEY", "marc-workbench-dev-key")

app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024   # 25 MB

# Re-read a template when its file changes, instead of once per process.
#
# Jinja compiles a template on first render and keeps it for the life of the
# process, and Flask only turns that off when debug is on -- which it is not
# here, because run.py starts the server with debug=False.  shared/about.json
# is read per request, so the two are on different schedules: after a pull, the
# header reports the new version out of a page compiled from the old template.
# That combination cost a real afternoon.  Every symptom said "the update did
# not work" while the badge said it had.
#
# The cost is one stat() per render of one file, which is nothing against the
# conversion it sits in front of.  The benefit is that "restart the server"
# stops being a step anybody has to remember.
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Flask names its session cookie "session" at path / by default, and the three
# apps are served from one hostname -- so with the stock name the workbench and
# the converter overwrite each other's cookie. Neither can then read what it
# wrote, and the cataloguer is told their uploaded file has gone. The workbench
# is the newcomer, so it is the one that yields.
# One application, so the cookie needs no name of its own. It carried one
# because the workbench and the converter ran on the same host and the
# workbench's session signed the converter out of its own upload.

# Uploads, pattern libraries and the sweep that ages them out live in
# marc_serials.store, shared with the converter. Keeping the rules in one place
# is not tidiness: the converter had its own sweep that aged every file in the
# directory as an upload, so running it deleted the libraries this application
# was deliberately keeping. See marc_serials/store.py.

# Bounds on user-supplied text, matching the pattern detector's: a regex the
# cataloguer edited runs against statements the cataloguer uploaded, so both
# sides are capped to limit catastrophic-backtracking exposure.
MAX_STATEMENT_CHARS = 500
MAX_STATEMENTS = 5000
MAX_TEST_STATEMENTS = 2000

# How many of a group's examples the confirmation screen can step through.
# Bounded because a group can hold thousands and each one costs a match.
EXAMPLE_LIMIT = 25

# How many records one review page previews. Previewing a record costs well
# under a millisecond, so the ceiling is response size, not time.
PREVIEW_PAGE = 50
PREVIEW_PAGE_MAX = 200

# The pattern being confirmed, as it appears to the preview: ahead of everything
# already in the library, and never written to it.
CANDIDATE_ID = "__candidate__"
CANDIDATE_LABEL = "This pattern"
CANDIDATE_PRIORITY = 10 ** 6


# ---------------------------------------------------------------------------
# Server-side storage.  Binary MARC and the pattern library are held on disk;
# only a UUID per kind goes into the session cookie, which Flask caps at 4 KB --
# a single generated regex can run to a quarter of that.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# The pattern library, for this session
# ---------------------------------------------------------------------------

def _load_library() -> list:
    """The confirmed patterns for this session, in the order they are tried."""
    raw = _load_file("pattern_library", LIBRARY_EXT, refresh=True)
    if not raw:
        return []
    try:
        document = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        app.logger.warning("Stored pattern library was unreadable; ignoring it.")
        return []
    patterns, errors = plib.from_export(document)
    if errors:
        # Dropped silently before. A pattern that stops loading takes every
        # record it used to read with it, and the screen looks the same.
        app.logger.warning("Stored pattern library: %d entr%s could not be "
                           "read and were ignored: %s", len(errors),
                           "y" if len(errors) == 1 else "ies", "; ".join(errors))
    return patterns


def _save_library(patterns) -> None:
    payload = json.dumps(plib.to_export(patterns), indent=2).encode("utf-8")
    _save_file("pattern_library", payload, LIBRARY_EXT)


# ---------------------------------------------------------------------------
# MARC helpers.  These mirror converter/app.py; the standalone converter is
# deliberately left untouched, so the glue is repeated rather than imported --
# importing its app.py would execute a second Flask application at import time.
# ---------------------------------------------------------------------------

def _parser_fallback(data: dict) -> bool:
    """Whether an unmatched statement falls to the standard parser. Default yes."""
    value = data.get("parser_fallback", True)
    if isinstance(value, str):
        return value.strip().lower() not in ("", "0", "false", "no")
    return bool(value)


def _keep_separate(data: dict) -> set:
    """
    Records the cataloguer has told not to merge patterns on.

    Whether two statements recording different amounts of detail are one
    publication is a judgement about the serial, so it is theirs to make, per
    record.
    """
    raw = data.get("keep_separate")
    if not isinstance(raw, (list, tuple)):
        return set()
    out = set()
    for value in raw:
        try:
            out.add(int(value))
        except (TypeError, ValueError):
            continue
    return out


def _skipped_records(data: dict) -> set:
    """
    Records the cataloguer has told the tool not to touch.

    Skipping is stronger than every other switch on the screen: the record is
    not converted, its 866s are not removed, and its existing 853/863 are left
    alone even when "clear existing" is set. It comes out of a run byte for
    byte as it went in, which is the whole point -- these are the ones going to
    be catalogued by hand.
    """
    raw = data.get("skip_records")
    if not isinstance(raw, (list, tuple)):
        return set()
    out = set()
    for value in raw:
        try:
            out.add(int(value))
        except (TypeError, ValueError):
            continue
    return out


def _record_title(record) -> str:
    """The 245 $a$b of a record, trimmed of ISBD punctuation."""
    field = record.get("245")
    if not field:
        return ""
    return " ".join(field.get_subfields("a", "b")).strip().rstrip(" /:")


def _identifier_spec() -> str:
    """
    The field this cataloguer finds records by.

    Absent from the session means nobody has chosen, so the default applies.
    Present and empty means somebody chose "no identifier", which is a
    different thing and must survive a reload -- otherwise the tool keeps
    re-offering a choice that has already been made.

    Kept in the session rather than in the file, because it describes the
    library's ILS rather than this upload: the next file from the same
    institution wants the same field.
    """
    spec = session.get("identifier_spec")
    return DEFAULT_IDENTIFIER_SPEC if spec is None else spec


def _load_all_records() -> Optional[list]:
    """
    Every pymarc Record in the stored file, at its own position.

    Positions are preserved rather than compacted: every index here means the
    same record it means in the file, which is what the record_index the screens
    send is counted against. api_upload_marc() refuses a file containing a
    record pymarc cannot decode, so nothing in this list is None.
    """
    marc_bytes = _load_file("marc_file")
    if not marc_bytes:
        return None
    return records_from_bytes(marc_bytes)


# ---------------------------------------------------------------------------
# Conversion, with the library applied
# ---------------------------------------------------------------------------

def _parse_all(texts, patterns, fallback: bool = True) -> tuple[list, list]:
    """
    Parse every statement, preferring a confirmed pattern.

    `fallback` decides what becomes of a statement no pattern matches: the
    standard parser reads it, or nothing is written and its 866 is left alone.
    Returns (parse_results, sources) in step with `texts`.
    """
    parsed, sources = [], []
    for text in texts:
        result, source = apply_patterns(text, patterns, fallback)
        parsed.append(result)
        sources.append(source)
    return parsed, sources


def _source_labels(patterns) -> dict:
    labels = {p.id: p.label for p in patterns}
    labels[PARSER_SOURCE] = "Standard parser"
    labels[UNMATCHED_SOURCE] = "No pattern matched — left as it is"
    labels[SKIPPED_SOURCE] = "Skipped — left as it is"
    return labels


def _requested_indices(data: dict, total: int, offset: int, limit: int) -> list:
    """
    Which records a review request wants: an explicit list, or a page.

    An explicit list exists because the review screen pages through whatever
    the *filter* is showing, not through the file in order -- with a filter on,
    records 1-50 of the file are not the first fifty a cataloguer is looking at.
    """
    raw = data.get("indices")
    if isinstance(raw, (list, tuple)):
        wanted = []
        for value in raw[:PREVIEW_PAGE_MAX]:
            try:
                index = int(value)
            except (TypeError, ValueError):
                continue
            if 0 <= index < total and index not in wanted:
                wanted.append(index)
        return wanted
    return list(range(offset, min(offset + limit, total)))


def _review_row(record, index, *, patterns, fallback, conv_opts, captions,
                frequency, continuity, rejections, merge_patterns,
                skipped: bool, with_previews: bool,
                holdings_level: str = DEFAULT_HOLDINGS_LEVEL,
                units_per_higher: str = "") -> dict:
    """
    One record as the review screen sees it: what it would produce, and what
    read it.

    `with_previews` is the difference between the two callers.  The filters and
    the row status need only the counts, for every record in the file; the
    fields themselves are wanted only for the handful on screen, and carrying
    them for a 400-record file would be most of a megabyte spent on rows nobody
    has opened.  Both come from here, so a filter can never disagree with the
    preview it filtered on.
    """
    row = {
        "index": index,
        "title": _record_title(record) or f"Record {index + 1}",
        "converted": 0,
        "held": 0,
        "flagged": 0,
        "sources": [],
        "has_866": False,
        "skipped": skipped,
        # Set when the holdings written exceed the level the cataloguer
        # declared -- a per-record fact, and the one worth a marker. Reported,
        # never corrected: see records.encoding_level_conflict().
        "leader_note": None,
        # Set when this record's own Leader/17 disagrees with that level. Not
        # a marker, because on a real file it is true of every row and the
        # count belongs in one line above the list -- but carried so the
        # filter can still find them.
        "leader_mismatch": False,
        # Set when Leader/06 says single-part item and the holdings say
        # otherwise. Counted for the file rather than marked per row, for the
        # same reason as the encoding level: on a migrated file it is true of
        # nearly all of them.
        "single_part": False,
    }
    if with_previews:
        row["previews"] = []

    statements = [t for t in ((f["a"] or "") for f in record.get_fields("866")) if t]
    row["has_866"] = bool(statements)

    # A preview that showed fields a skipped record will never get would be
    # showing something that is not going to happen.
    if skipped or not statements:
        return row

    parsed, sources = _parse_all(statements, patterns, fallback)
    rc = convert_record(
        parsed, existing_853s=list(record.get_fields("853")), captions=captions,
        frequency=frequency, numbering_continuity=continuity,
        merge_patterns=merge_patterns, holdings_level=holdings_level,
        units_per_higher=units_per_higher,
        **conv_opts,
    )
    previews = _previews_from(rc, rejections, list(record.get_fields("853")),
                              sources, patterns)
    for preview, text in zip(previews, statements):
        preview["source_866"] = text

    row["converted"] = sum(1 for p in previews if p["fields_863"])
    row["held"] = sum(1 for p in previews if not p["fields_863"])
    # Converted, and the tool cannot vouch for it. Counted apart from "held"
    # because these records *do* have fields -- what they need is a look, not
    # a pattern.
    row["flagged"] = sum(1 for p in previews if p.get("flagged"))
    row["sources"] = sorted({p["source"] for p in previews})
    row["leader_note"] = encoding_level_conflict(record, rc.fields_863,
                                                 holdings_level)
    row["leader_mismatch"] = encoding_level_differs(record, holdings_level)
    row["single_part"] = single_part_conflict(record, rc.fields_863)
    if with_previews:
        row["previews"] = previews
    return row


def _previews_from(rc, rejections=(), existing_853s=(), sources=(),
                   patterns=()) -> list:
    """
    One preview entry per statement, in 866 field order, annotated with whatever
    read it -- a confirmed pattern by name, or the standard parser.
    """
    by_link = {}
    for fld in existing_853s or ():
        by_link[(fld.get("8") or "").strip()] = _display_marc_field(fld)

    labels = _source_labels(patterns)
    merged = set(rc.merged_links)
    out = []
    for idx, c in enumerate(rc.results):
        link = str(c.linking_number)
        display = c.field_853.display() if c.field_853 else by_link.get(link)
        source = sources[idx] if idx < len(sources) else PARSER_SOURCE
        out.append({
            "field_853": display,
            "fields_863": [f.display() for f in c.fields_863],
            "warnings": c.warnings + list(rejections),
            "conformed": c.conformed,
            "needs_review": c.needs_review,
            "flagged": c.flagged,
            "link": link,
            "existing": bool(c.conformed and display),
            "source": source,
            "source_label": labels.get(source, "Standard parser"),
            "from_pattern": source != PARSER_SOURCE,
            "merged_run": link in merged,
        })
    return out


# ---------------------------------------------------------------------------
# Pattern annotation for the confirmation screen
# ---------------------------------------------------------------------------

def _example_values(regex: str, statements, roles) -> list:
    """
    What each capture group catches, one entry per example statement.

    Deliberately *not* pooled across examples.  A cataloguer checking a pattern
    is checking one statement at a time -- this 866, these captured values, that
    853 -- and a column mixing values from several statements cannot be lined up
    against any of them.

    Only a full match contributes values, for the same reason pattern_bridge
    only converts on one: values pulled out of a substring look like a working
    pattern on this screen, and are exactly what the conversion will refuse to
    use.  A partial match shows empty, which is what the pattern will do.
    """
    try:
        compiled = re.compile(regex, re.IGNORECASE)
    except re.error:
        return []

    out = []
    for statement in list(statements)[:EXAMPLE_LIMIT]:
        s = (statement or "").strip()[:MAX_STATEMENT_CHARS]
        m = compiled.fullmatch(s)
        caught = m.groupdict() if m else {}
        out.append({r.group: (caught.get(r.group) or "") for r in roles})
    return out


def _statement_origins(do_split: bool) -> dict:
    """
    Map each statement back to the 866 field it came from.

    Splitting means a statement need not equal any $a -- "v.1(1990)-v.3(1992) /
    v.5(1994)-v.8(1997)" becomes two -- so the client cannot match an example to
    its record by comparing text, and the association has to be made here, while
    the statements are being taken apart.

    First occurrence wins: the same holdings string can appear on two records,
    and either one previews the numbering equally well.
    """
    stored = _load_file("marc_file")
    if not stored:
        return {}

    origins: dict = {}
    for record in _read_marc_file(io.BytesIO(stored)):
        for field_index, fld in enumerate(record["fields_866"]):
            text = (fld["a"] or "").strip()
            if not text:
                continue
            pieces = split_statement(text) if do_split else [text]
            for piece in pieces:
                key = piece.strip()[:MAX_STATEMENT_CHARS]
                if key and key not in origins:
                    origins[key] = {
                        "record_index": record["index"],
                        "field_index": field_index,
                        "source_866": text,
                    }
    return origins


# What confirming a pattern still changes, now that parse_866() reads every
# statement it can and a confirmed pattern supplies only what it cannot.
DECIDES_READING = "reading"     # the parser writes nothing for these
DECIDES_CAPTION = "caption"     # the parser reads them; the 853 wants a word
DECIDES_NOTHING = "nothing"     # the parser reads them, captions and all

# How many of a cluster's statements to examine. Every one is parsed for a
# cluster of ordinary size; the cap only bounds a pathological one.
DECISION_SAMPLE = 200


def _what_confirming_decides(examples) -> str:
    """
    What a cataloguer's answers on this pattern would actually affect.

    Before 0.10.0 a confirmed pattern read its statements itself, so every
    answer changed the output and the screen could ask about all of them alike.
    The parser reads them now. An answer still decides the *reading* of a
    statement the parser refuses -- "v.1(1990)-5(1994)" carries a 5 no caption
    reaches, and nothing but a cataloguer can say what it is. Otherwise it
    decides a *caption*: the word the 853 declares for a level the statement
    writes as a bare number, where the parser can only write "(*)". Where the
    statement names its own captions, the answer changes nothing, and asking
    for it is asking a question whose answer is discarded.
    """
    caption_slots = 0
    for text in list(examples)[:DECISION_SAMPLE]:
        result = parse_866(text)
        if not result.ranges:
            return DECIDES_READING
        for hr in result.ranges:
            for boundary in (hr.start, hr.end):
                if boundary is None:
                    continue
                caption_slots += sum(1 for lvl in boundary.enum if not lvl.caption)
    return DECIDES_CAPTION if caption_slots else DECIDES_NOTHING


def _annotate_group(group_dict: dict, origins: Optional[dict] = None) -> dict:
    """Add the roles to offer, and per-example values and provenance."""
    named = group_dict.get("named_groups") or []
    roles = infer_roles(named)
    examples = group_dict.get("examples") or []
    shown = examples[:EXAMPLE_LIMIT]
    origins = origins or {}

    group_dict["suggested_roles"] = [r.to_dict() for r in roles]
    group_dict["example_values"] = _example_values(
        group_dict.get("regex") or "", shown, roles
    )
    group_dict["example_sources"] = [
        origins.get((e or "").strip()[:MAX_STATEMENT_CHARS]) for e in shown
    ]
    group_dict["examples_shown"] = len(shown)
    group_dict["decides"] = _what_confirming_decides(examples)
    # A pattern only wants a decision if one is outstanding *and* the answer
    # would change something. Both halves matter: an unresolved role on a
    # statement the parser reads in full is not work, it is a question with no
    # consequence.
    group_dict["needs_decision"] = (
        any(r.needs_a_decision for r in roles)
        and group_dict["decides"] != DECIDES_NOTHING
    )
    return group_dict


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template(
        "tool.html",
        has_pymarc=HAS_PYMARC,
        frequency_codes=FREQUENCY_CODES,
        holdings_levels=HOLDINGS_LEVELS,
        default_holdings_level=DEFAULT_HOLDINGS_LEVEL,
        convention_levels=CONVENTION_LEVELS,
        enum_levels=enum_level_fields(),
        convention_presets=convention_presets(),
        kind_choices=[(k, KIND_LABELS[k]) for k in ENCODABLE_KINDS],
        caption_choices=list(CAPTION_CHOICES),
        ignore_kind=KIND_IGNORE,
        ignore_label=KIND_LABELS[KIND_IGNORE],
        unresolved_kind=KIND_UNRESOLVED,
        about=_load_about(),
    )


@app.route("/api/upload-marc", methods=["POST"])
def api_upload_marc():
    """
    Take the MARC file once and serve both halves of the tool from it.

    Returns the record list the converter side needs *and* the 866 statements
    the detector side needs, so the cataloguer never uploads the same file to
    two tools again.
    """
    if not HAS_PYMARC:
        return jsonify({"error": "pymarc is not installed on the server."}), 500
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded."}), 400

    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Empty filename."}), 400

    for key in ("marc_file", "marc_file_converted"):
        val = session.get(key)
        if val is not None and not (isinstance(val, str) and len(val) == 32):
            session.pop(key, None)

    try:
        file_bytes = f.read()
        spec = _identifier_spec()
        records = _read_marc_file(io.BytesIO(file_bytes), identifier_spec=spec)

        # Checked before anything is stored, so a refused file leaves the
        # cataloguer's current file and pattern library exactly as they were.
        refusal = refuse_unreadable(records)
        if refusal:
            return jsonify({"error": refusal}), 400

        _save_file("marc_file", file_bytes)
        session.pop("marc_file_converted", None)
        _forget_decisions()

        statements = [
            fld["a"].strip()
            for rec in records for fld in rec["fields_866"] if (fld["a"] or "").strip()
        ]
        # Whether the identifier field was found at all, so the screen can say
        # "this file has no 999 $b" once rather than draw an empty slot beside
        # every row and leave the cataloguer to wonder which is broken, the
        # file or the tool.
        return jsonify({
            "records": records,
            "total": len(records),
            "statements": statements,
            "count": len(statements),
            "identifier_field": spec,
            "identifier_found": any(r.get("identifier") for r in records),
            # What this file could be identified by instead, so a cataloguer
            # whose ILS is not Alma is offered its actual fields rather than
            # asked to guess one.
            "identifier_candidates": identifier_candidates(
                records_from_bytes(file_bytes)),
        })
    except Exception as exc:
        app.logger.exception("Request failed")
        return jsonify({"error": str(exc)}), 500


@app.route("/api/identifier", methods=["POST"])
def api_identifier():
    """
    Change the field records are found by, without re-uploading.

    The record list is built once, at upload, so a naive version of this
    setting would take effect "next time you upload a file" -- which is the
    lag the frequency and numbering-continuity controls already have and which
    is worth not adding a third of.  Recomputing costs one pass over the
    stored file, so the screen can simply be told the new identifiers.

    Returns the identifier for every record rather than the whole summary:
    nothing else about a record changes when the field does, and a 372-record
    file's summaries are most of a megabyte.

    POST JSON: {"spec": "999$b"}.  An empty spec means "no identifier", which
    is a choice and is remembered as one.
    """
    if not HAS_PYMARC:
        return jsonify({"error": "pymarc is not installed on the server."}), 500

    data = request.get_json(force=True) or {}
    raw = data.get("spec", "")
    spec = "" if raw is None else str(raw).strip()

    # A spec that is neither empty nor a MARC field is a typo, and saying so
    # beats storing it and showing an empty column that looks like the file's
    # fault.
    if spec and parse_identifier_spec(spec) is None:
        return jsonify({
            "error": f"{spec!r} is not a MARC field. Write it as 999$b, "
                     "or 001 for a control field.",
        }), 400

    session["identifier_spec"] = spec

    records = _load_all_records()
    if records is None:
        # Nothing uploaded yet is not an error: the choice is still recorded,
        # and the next upload will use it.
        return jsonify({"spec": spec, "identifiers": [], "found": False})

    identifiers = [record_identifier(rec, spec) if spec else "" for rec in records]
    return jsonify({
        "spec": spec,
        "identifiers": [{"index": i, "identifier": v}
                        for i, v in enumerate(identifiers)],
        "found": any(identifiers),
    })


@app.route("/api/detect", methods=["POST"])
def api_detect():
    """
    Cluster statements by structure and return a regex per cluster, each with
    the roles to offer the cataloguer and the values those roles would take.

    Statements come from the request, or from the uploaded file when none are
    given -- the file is already on the server, so the client need not resend it.
    """
    data = request.get_json(force=True) or {}
    raw = data.get("statements")
    do_split = bool(data.get("split_multi_range", True))

    if not raw:
        stored = _load_file("marc_file")
        records = _read_marc_file(io.BytesIO(stored)) if stored else []
        raw = [fld["a"].strip() for rec in records
               for fld in rec["fields_866"] if (fld["a"] or "").strip()]

    if not raw:
        return jsonify({"error": "No statements provided."}), 400

    statements: list[str] = []
    for s in raw:
        if do_split:
            statements.extend(split_statement(s))
        elif s.strip():
            statements.append(s.strip())

    statements = [s[:MAX_STATEMENT_CHARS] for s in statements if s.strip()]
    if not statements:
        return jsonify({"error": "All statements were empty after processing."}), 400
    statements = statements[:MAX_STATEMENTS]

    try:
        # Built from the stored file rather than from `raw`, so an example
        # resolves to its record whether the client resent the statements or
        # left the server to read them.
        origins = _statement_origins(do_split)
        groups = [_annotate_group(g.to_dict(), origins)
                  for g in detect_patterns(statements)]
        return jsonify({
            "total_statements": len(statements),
            "total_patterns": len(groups),
            "split_multi_range": do_split,
            "groups": groups,
        })
    except Exception as exc:
        app.logger.exception("Request failed")
        return jsonify({"error": str(exc)}), 500


@app.route("/api/test-regex", methods=["POST"])
def api_test_regex():
    """
    Test a possibly-edited regex against statements, and re-offer roles for it.

    Editing the expression can add or remove capture groups, so the roles come
    back too -- decisions already made are kept, anything new needs deciding.
    """
    data = request.get_json(force=True) or {}
    regex_str = data.get("regex", "")
    statements = data.get("statements", [])

    if not regex_str:
        return jsonify({"error": "No regex provided."}), 400
    if len(regex_str) > plib.MAX_REGEX_CHARS:
        return jsonify({
            "error": f"Regex exceeds the {plib.MAX_REGEX_CHARS:,}-character test limit.",
        }), 400

    statements = [str(s)[:MAX_STATEMENT_CHARS] for s in statements[:MAX_TEST_STATEMENTS]]

    try:
        compiled = re.compile(regex_str, re.IGNORECASE)
    except re.error as exc:
        return jsonify({"error": f"Invalid regex: {exc}"}), 400

    # The expression on this screen has usually just been edited by hand, which
    # is where a runaway one comes from. The matching runs in a child process
    # this request can kill; see regex_budget.
    statements = [s.strip() for s in statements]
    try:
        matches = match_statements(regex_str, statements)
    except MatchTimeout:
        return jsonify({"error": too_slow_message()}), 400
    except MatchFailed as exc:
        return jsonify({"error": f"The expression could not be run: {exc}"}), 400

    # "matched" means the pattern spans the whole statement, because that is
    # what the Workbench will convert on -- see pattern_bridge. A partial hit is
    # still reported, with the span it covers, so the cataloguer can see how
    # close the expression came and what it missed; it just does not count.
    results = [{
        "statement": s,
        "matched": m["full"],
        "full_match": m["full"],
        "partial_match": m["partial"],
        "groups": m["groups"] if m["full"] else {},
        "span": m["span"],
    } for s, m in zip(statements, matches)]

    matched_n = sum(1 for r in results if r["matched"])
    names = sorted(compiled.groupindex, key=lambda n: compiled.groupindex[n])
    prior = [plib.GroupRole.from_dict(r) for r in (data.get("roles") or [])
             if isinstance(r, dict)]
    roles = plib.merge_roles(names, prior) if prior else infer_roles(names)

    return jsonify({
        "results": results,
        "matched": matched_n,
        "failed": len(results) - matched_n,
        "match_rate": matched_n / len(results) if results else 1.0,
        "roles": [r.to_dict() for r in roles],
        # Aligned with the statements sent, so the card can keep showing the
        # example it was already on after the expression is edited.
        "example_values": _example_values(regex_str, statements, roles),
        "decides": _what_confirming_decides(statements),
        "needs_decision": (any(r.needs_a_decision for r in roles)
                           and _what_confirming_decides(statements)
                           != DECIDES_NOTHING),
    })


@app.route("/api/pattern-preview", methods=["POST"])
def api_pattern_preview():
    """
    Show what a pattern would produce, with the linking numbers it would get.

    This is the confirmation step, so it has to show the real thing.  $8 is a
    record-level decision -- convert_record() shares one 853 across statements
    expressing the same publication pattern and numbers them 1.1, 1.2, then 2.1
    when the pattern changes -- so previewing a statement on its own always read
    "1.1" and quietly misrepresented what conversion would write.

    Given the record an example came from, the whole record is converted with
    the candidate pattern in front of the confirmed library, exactly as
    /api/preview-record converts it, and the example's own row is marked.

    Statements pasted rather than uploaded have no record to sit in; those fall
    back to previewing the statement alone, beside the standard parser.
    """
    data = request.get_json(force=True) or {}
    regex_str = data.get("regex") or ""
    do_split = bool(data.get("split", True))

    if not regex_str:
        return jsonify({"error": "No regex provided."}), 400
    if len(regex_str) > plib.MAX_REGEX_CHARS:
        return jsonify({
            "error": f"Regex exceeds the {plib.MAX_REGEX_CHARS:,}-character limit.",
        }), 400

    try:
        compiled = re.compile(regex_str, re.IGNORECASE)
    except re.error as exc:
        return jsonify({"error": f"Invalid regex: {exc}"}), 400

    roles = plib.assign_levels([plib.GroupRole.from_dict(r)
                                for r in (data.get("roles") or [])
                                if isinstance(r, dict)])
    unresolved = [r.group for r in roles if r.kind == KIND_UNRESOLVED]

    conv_opts, rejections = _convention_opts(data)
    captions = data.get("captions") or None
    frequency = data.get("frequency", "")
    continuity = data.get("numbering_continuity", "r")
    units_per_higher = resolve_units_per_higher(data.get("units_per_higher"))
    holdings_level = resolve_holdings_level(data.get("holdings_level"))

    if unresolved:
        # Nothing to show until every value has a meaning; the client renders
        # the list rather than a preview.
        return jsonify({"scope": "unresolved", "previews": [],
                        "unresolved": unresolved, "rejections": rejections})

    record_index = data.get("record_index")
    field_index = data.get("field_index")

    # ── Record scope: the numbering conversion would actually write ──────────
    if HAS_PYMARC and isinstance(record_index, int):
        all_records = _load_all_records()
        if all_records and 0 <= record_index < len(all_records):
            candidate, errors = plib.validate_pattern({
                "id": CANDIDATE_ID,
                "label": CANDIDATE_LABEL,
                "regex": regex_str,
                "roles": [r.to_dict() for r in roles],
                "split": do_split,
                # Ahead of everything confirmed: the cataloguer is looking at
                # this pattern, so it must be the one that reads its own shape.
                "priority": CANDIDATE_PRIORITY,
            })
            if candidate is None:
                return jsonify({"error": "; ".join(errors)}), 400

            record = all_records[record_index]
            existing_853s = list(record.get_fields("853"))

            texts, field_indexes = [], []
            for idx, fld in enumerate(record.get_fields("866")):
                text = fld["a"] or ""
                if text:
                    texts.append(text)
                    field_indexes.append(idx)

            # The candidate is about to be run against this record's
            # statements by the conversion below, which nothing could stop.
            if not completes_within_budget(regex_str, texts):
                return jsonify({"error": too_slow_message()}), 400

            patterns = [candidate] + _load_library()
            parsed, sources = _parse_all(texts, patterns,
                                         _parser_fallback(data))
            rc = convert_record(
                parsed,
                existing_853s=existing_853s,
                captions=captions,
                frequency=frequency,
                numbering_continuity=continuity,
                merge_patterns=record_index not in _keep_separate(data),
                holdings_level=holdings_level,
                units_per_higher=units_per_higher,
                **conv_opts,
            )
            previews = _previews_from(rc, rejections, existing_853s,
                                      sources, patterns)
            for preview, text, idx in zip(previews, texts, field_indexes):
                preview["source_866"] = text
                preview["is_example"] = (idx == field_index)

            return jsonify({
                "scope": "record",
                "record": {
                    "index": record_index,
                    "title": _record_title(record) or f"Record {record_index + 1}",
                },
                "previews": previews,
                "unresolved": [],
                "rejections": rejections,
            })

    # ── Statement scope: no record to sit in ────────────────────────────────
    statements = [str(s)[:MAX_STATEMENT_CHARS]
                  for s in (data.get("statements") or [])[:EXAMPLE_LIMIT]]
    if not statements:
        return jsonify({"error": "No statements to preview."}), 400

    if not completes_within_budget(regex_str, statements):
        return jsonify({"error": too_slow_message()}), 400

    def _fields(parse_result):
        conversion = convert_holdings(
            parse_result, linking_number=1, captions=captions,
            frequency=frequency, numbering_continuity=continuity,
            holdings_level=holdings_level, units_per_higher=units_per_higher,
            **conv_opts,
        )
        return {
            "field_853": conversion.field_853.display() if conversion.field_853 else None,
            "fields_863": [f.display() for f in conversion.fields_863],
            "warnings": conversion.warnings,
            "needs_review": conversion.needs_review,
        }

    previews = []
    for statement in statements:
        pattern_result = build_parse_result(statement, compiled, roles, do_split,
                                            _parser_fallback(data))
        pattern_side = _fields(pattern_result) if pattern_result else None
        parser_side = _fields(parse_866(statement))
        differs = (
            pattern_side is None
            or pattern_side["field_853"] != parser_side["field_853"]
            or pattern_side["fields_863"] != parser_side["fields_863"]
        )
        previews.append({
            "statement": statement,
            "matched": pattern_result is not None,
            "pattern": pattern_side,
            "parser": parser_side,
            "differs": differs,
        })

    return jsonify({
        "scope": "statement",
        "record": None,
        "previews": previews,
        "unresolved": [],
        "rejections": rejections,
    })


# How many of the session's own statements a stored pattern is tried against.
# The probe is one child process either way; this bounds what it is handed.
PROBE_STATEMENT_LIMIT = 200


def _runaway_message(labels) -> str:
    """Name the patterns that were refused, and say what is wrong with them."""
    named = ", ".join(f"'{label}'" for label in labels)
    plural = "these patterns" if len(labels) > 1 else "this pattern"
    return (
        f"{named} could not be stored: the expression did not finish in time, "
        f"so {plural} would hang every conversion it was used in. "
        + too_slow_message().split(". ", 1)[1]
    )


def _probe_statements() -> list:
    """
    Text to try a pattern against when nothing in particular is being converted.

    The session's own statements where there is a file, because a pattern that
    runs away does it on the shapes it nearly matches, and those are here. Plus
    the fixed probes, which catch the classic runaway shapes and are all there
    is to go on when statements were pasted rather than uploaded.
    """
    mine: list = []
    try:
        mine = list(_statement_origins(True))[:PROBE_STATEMENT_LIMIT]
    except Exception:                    # pragma: no cover - no file, bad file
        mine = []
    return list(BACKTRACKING_PROBES) + mine


def _runaway_patterns(patterns, known: frozenset) -> list:
    """
    Which of `patterns` do not finish against the probe text, by label.

    Only expressions this session has not already stored are tried: reordering
    and removing are the same PUT as confirming, and re-probing an expression
    that is already in the library would charge a child process for a drag of
    the mouse.

    The library is the one door that matters. A pattern on the Test screen runs
    under regex_budget and cannot wedge anything; a pattern *stored* is run by
    every conversion afterwards, against every statement of every record, with
    nothing able to stop it. So it is checked on the way in.
    """
    fresh = [p for p in patterns if p.regex not in known]
    if not fresh:
        return []
    text = _probe_statements()
    return [p.label or p.id for p in fresh
            if not completes_within_budget(p.regex, text)]


@app.route("/api/patterns", methods=["GET", "PUT"])
def api_patterns():
    """
    Read or replace this session's confirmed patterns.

    PUT replaces the whole library, so confirming, reordering and removing are
    the same operation from the client's side.  Nothing invalid is stored: a
    rejected pattern comes back with the reason instead.
    """
    if request.method == "GET":
        patterns = _load_library()
        return jsonify({
            "patterns": [p.to_dict() for p in patterns],
            "count": len(patterns),
        })

    data = request.get_json(force=True) or {}
    patterns, errors = plib.load_patterns(data.get("patterns"))

    known = frozenset(p.regex for p in _load_library())
    runaway = _runaway_patterns(patterns, known)
    if runaway:
        return jsonify({
            "error": _runaway_message(runaway),
            "rejected": errors + [_runaway_message(runaway)],
        }), 400

    _save_library(patterns)
    return jsonify({
        "patterns": [p.to_dict() for p in patterns],
        "count": len(patterns),
        "rejected": errors,
    })


@app.route("/api/patterns/export", methods=["GET"])
def api_patterns_export():
    """Download the library so it can be reloaded, or shared with a colleague."""
    patterns = _load_library()
    payload = json.dumps(plib.to_export(patterns), indent=2).encode("utf-8")
    return send_file(
        io.BytesIO(payload),
        mimetype="application/json",
        as_attachment=True,
        download_name="holdings_patterns.json",
    )


@app.route("/api/patterns/import", methods=["POST"])
def api_patterns_import():
    """
    Load a previously exported library, replacing or adding to this session's.

    Accepts the file as an upload or the document as a JSON body.
    """
    if "file" in request.files:
        try:
            document = request.files["file"].read().decode("utf-8")
        except UnicodeDecodeError:
            return jsonify({"error": "That file is not a readable text file."}), 400
        merge = request.form.get("merge") not in (None, "", "0", "false", "False")
    else:
        body = request.get_json(silent=True) or {}
        document = body.get("library", body)
        merge = bool(body.get("merge"))

    incoming, errors = plib.from_export(document)
    if not incoming and errors:
        return jsonify({"error": "; ".join(errors), "rejected": errors}), 400

    existing = _load_library() if merge else []
    combined, more_errors = plib.load_patterns(
        [p.to_dict() for p in existing] + [p.to_dict() for p in incoming]
    )

    # An exported library is a file from somewhere else, so every expression in
    # it is new to this session and every one is tried.
    runaway = _runaway_patterns(combined, frozenset(p.regex for p in existing))
    if runaway:
        return jsonify({"error": _runaway_message(runaway),
                        "rejected": errors + more_errors +
                                    [_runaway_message(runaway)]}), 400

    _save_library(combined)

    return jsonify({
        "patterns": [p.to_dict() for p in combined],
        "count": len(combined),
        "imported": len(incoming),
        "rejected": errors + more_errors,
    })


@app.route("/api/preview-record", methods=["POST"])
def api_preview_record():
    """
    Preview one whole record without writing anything.

    Linking numbers are a record-level property, so the whole record is
    converted and one preview returned per 866, in field order.
    """
    if not HAS_PYMARC:
        return jsonify({"error": "pymarc is not installed on the server."}), 500

    data = request.get_json(force=True) or {}
    all_records = _load_all_records()
    if all_records is None:
        return jsonify({"error": "No MARC file found. Please upload a file first."}), 400

    record_index = int(data.get("record_index", 0))
    if record_index >= len(all_records):
        return jsonify({"error": "Record index out of range."}), 400

    try:
        record = all_records[record_index]
        conv_opts, rejections = _convention_opts(data)
        patterns = _load_library()

        existing_853s = list(record.get_fields("853"))
        statements = [t for t in ((f["a"] or "") for f in record.get_fields("866")) if t]
        parsed, sources = _parse_all(statements, patterns,
                                     _parser_fallback(data))

        rc = convert_record(
            parsed,
            existing_853s=existing_853s,
            captions=data.get("captions") or None,
            frequency=data.get("frequency", ""),
            numbering_continuity=data.get("numbering_continuity", "r"),
            merge_patterns=record_index not in _keep_separate(data),
            holdings_level=resolve_holdings_level(data.get("holdings_level")),
            **conv_opts,
        )
        # Deliberately no write and no save: preview leaves the file untouched.
        previews = _previews_from(rc, rejections, existing_853s, sources, patterns)
        for pv, text in zip(previews, statements):
            pv["source_866"] = text

        return jsonify({
            "success": True,
            "record_index": record_index,
            "previews": previews,
        })
    except Exception as exc:
        app.logger.exception("Request failed")
        return jsonify({"error": str(exc)}), 500


@app.route("/api/preview-records", methods=["POST"])
def api_preview_records():
    """
    Preview a page of records in one request, for reviewing a file record by
    record rather than pattern by pattern.

    Previewing one record costs well under a millisecond; what makes reviewing a
    whole file impractical is a round trip per record.  This returns a page of
    them, each with the counts a reviewer filters on, so the work is "show me
    everything still held for review" rather than "open all 400 and look".

    Nothing is written: this is the read-only twin of /api/batch-convert.

    POST JSON: {"offset": 0, "limit": 50, ...conversion settings}
    """
    if not HAS_PYMARC:
        return jsonify({"error": "pymarc is not installed on the server."}), 500

    data = request.get_json(force=True) or {}
    all_records = _load_all_records()
    if all_records is None:
        return jsonify({"error": "No MARC file found. Please upload a file first."}), 400

    try:
        offset = max(0, int(data.get("offset", 0)))
    except (TypeError, ValueError):
        offset = 0
    try:
        limit = int(data.get("limit", PREVIEW_PAGE))
    except (TypeError, ValueError):
        limit = PREVIEW_PAGE
    limit = max(1, min(limit, PREVIEW_PAGE_MAX))

    conv_opts, rejections = _convention_opts(data)
    captions = data.get("captions") or None
    frequency = data.get("frequency", "")
    continuity = data.get("numbering_continuity", "r")
    units_per_higher = resolve_units_per_higher(data.get("units_per_higher"))
    holdings_level = resolve_holdings_level(data.get("holdings_level"))
    patterns = _load_library()
    fallback = _parser_fallback(data)
    keep_separate = _keep_separate(data)
    skip_records = _skipped_records(data)

    try:
        wanted = _requested_indices(data, len(all_records), offset, limit)
        out = [
            _review_row(all_records[index], index,
                        patterns=patterns, fallback=fallback,
                        conv_opts=conv_opts, captions=captions,
                        frequency=frequency, continuity=continuity,
                        rejections=rejections,
                        merge_patterns=index not in keep_separate,
                        skipped=index in skip_records,
                        with_previews=True, holdings_level=holdings_level,
                        units_per_higher=units_per_higher)
            for index in wanted
        ]

        return jsonify({
            "records": out,
            "total": len(all_records),
            "offset": offset,
            "limit": limit,
            "rejections": rejections,
        })
    except Exception as exc:
        app.logger.exception("Request failed")
        return jsonify({"error": str(exc)}), 500


@app.route("/api/review-index", methods=["POST"])
def api_review_index():
    """
    What every record in the file would produce, in counts rather than fields.

    The review screen filters and pages over the whole file, so it needs an
    answer for every record -- not just the page whose previews are loaded.
    Without this the filters silently lied: a record with no preview data
    passed every test, so "needs attention" showed the whole file from the
    second page on.

    It also answers "which records did this pattern read", which is what makes
    editing a pattern able to put the records it touched back into the review
    queue instead of leaving a stale tick beside them.

    Deliberately no field data: see _review_row.

    POST JSON: {...conversion settings}
    """
    if not HAS_PYMARC:
        return jsonify({"error": "pymarc is not installed on the server."}), 500

    data = request.get_json(force=True) or {}
    all_records = _load_all_records()
    if all_records is None:
        return jsonify({"error": "No MARC file found. Please upload a file first."}), 400

    conv_opts, rejections = _convention_opts(data)
    captions = data.get("captions") or None
    frequency = data.get("frequency", "")
    continuity = data.get("numbering_continuity", "r")
    units_per_higher = resolve_units_per_higher(data.get("units_per_higher"))
    holdings_level = resolve_holdings_level(data.get("holdings_level"))
    patterns = _load_library()
    fallback = _parser_fallback(data)
    keep_separate = _keep_separate(data)
    skip_records = _skipped_records(data)

    try:
        rows = [
            _review_row(record, index,
                        patterns=patterns, fallback=fallback,
                        conv_opts=conv_opts, captions=captions,
                        frequency=frequency, continuity=continuity,
                        rejections=rejections,
                        merge_patterns=index not in keep_separate,
                        skipped=index in skip_records,
                        with_previews=False, holdings_level=holdings_level,
                        units_per_higher=units_per_higher)
            for index, record in enumerate(all_records)
        ]
        # The file-wide half of the encoding-level question, counted once.
        # A marker on every row said this badly; one line says it well.
        return jsonify({
            "records": rows,
            "total": len(all_records),
            "encoding_level": encoding_level_summary(all_records, holdings_level),
            # Leader/06, counted the same way and for the same reason.
            "single_part": sum(1 for r in rows if r.get("single_part")),
            # And the records whose holdings go past the level being recorded
            # at. Counted rather than marked since 0.17.3: at level 3 against
            # a file of detailed holdings this is a majority, and a marker on
            # a majority says nothing.
            "beyond_level": sum(1 for r in rows if r.get("leader_note")),
            "with_holdings": sum(1 for r in rows if r.get("has_866")),
            "declared_level": holdings_level,
        })
    except Exception as exc:
        app.logger.exception("Request failed")
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# Conversion decisions, and the file built from them
#
# The converted file is not what the last click produced. It is rebuilt from
# the uploaded file and every decision the cataloguer has made, every time one
# of those decisions changes.
#
# It used to be what the last click produced, and that threw work away in
# silence. /api/convert-record read the *original* file, applied the one record
# it had been sent, and saved the result over the previous save -- so
# converting record 5 and then record 9 left a file with record 9 converted and
# record 5 back as it came in. The Download button stayed lit throughout and
# nothing said a thing. Measured on data/example_holdings.mrc: converting
# record 0 wrote 1 853 and 2 863s on it; converting record 1 next left record 0
# with none.
#
# Rebuilding keeps the property the old route had by accident and the tests
# pin: sending the same decision twice produces the same bytes, because the
# record it is applied to is read fresh from the upload each time. It is also
# what lets "Convert all records" leave a record its cataloguer has already
# converted by hand exactly as they converted it.
# ---------------------------------------------------------------------------

# Not ``.json``: store.ttl_for() keeps anything with that extension for thirty
# days, which is right for a pattern library and wrong for this. A decision is
# about one upload and is worthless once the upload has been swept, so it is
# kept on the upload's own six-hour limit.
DECISIONS_EXT = ".decisions"

# The session key holding them.
DECISIONS_KEY = "conversion_decisions"


def _empty_decisions() -> dict:
    """Nothing decided yet: no record converted on its own, no run over the file."""
    return {"records": {}, "batch": None}


def _load_decisions() -> dict:
    """Every conversion decision for this session, or an empty set of them."""
    raw = _load_file(DECISIONS_KEY, DECISIONS_EXT)
    if not raw:
        return _empty_decisions()
    try:
        document = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        app.logger.warning("Stored conversion decisions were unreadable; "
                           "ignoring them.")
        return _empty_decisions()
    records = document.get("records")
    batch = document.get("batch")
    return {
        "records": records if isinstance(records, dict) else {},
        "batch": batch if isinstance(batch, dict) else None,
    }


def _save_decisions(decisions: dict) -> None:
    _save_file(DECISIONS_KEY, json.dumps(decisions).encode("utf-8"),
               DECISIONS_EXT)


def _forget_decisions() -> None:
    """
    Drop every decision.

    Called when a new file arrives. A decision is keyed by record position, and
    a position means nothing once the file behind it has changed.
    """
    session.pop(DECISIONS_KEY, None)


def _apply_one_decision(record, decision: dict, patterns: list) -> tuple:
    """
    Apply one cataloguer's per-record decision to one record, in place.

    The record has to be freshly read from the upload: a decision says what the
    record should end up as, not what to add to whatever is on it already.

    Returns (result, previews, sources).
    """
    conversions_input = decision.get("conversions", [])

    existing_853s = list(record.get_fields("853"))
    if decision.get("clear_existing_853_863"):
        record.remove_fields("853", "863")
        existing_853s = []

    remove_866 = any(c.get("remove_866", False) for c in conversions_input)
    conv_opts, rejections = _convention_opts(decision)
    specs = [c for c in conversions_input if c.get("text")]
    texts = [c["text"] for c in specs]

    # The text arrives from the client and may have been edited, so a spec
    # matching no field leaves every 866 alone: never delete a field we
    # cannot account for.
    sources_866 = _match_866_sources(record, texts)

    parsed, sources = _parse_all(texts, patterns, _parser_fallback(decision))

    first = specs[0] if specs else {}
    rc = convert_record(
        parsed,
        existing_853s=existing_853s,
        captions=first.get("captions") or None,
        frequency=first.get("frequency", ""),
        numbering_continuity=first.get("numbering_continuity", "r"),
        holdings_level=resolve_holdings_level(
            first.get("holdings_level", decision.get("holdings_level"))),
        **conv_opts,
    )
    _apply_record_conversion(record, rc)

    if remove_866:
        _remove_converted_866s(record, sources_866, rc)

    return rc, _previews_from(rc, rejections, (), sources, patterns), sources


def _rebuild_converted(decisions: dict, previews_for: Optional[int] = None):
    """
    Write the converted file from the upload and every decision on it.

    Each record takes the first of these that applies:

      * skipped by the run over the whole file -- left byte for byte as it came
        in, which is stronger than everything else on the screen and stronger
        than a decision made on the record earlier;
      * a decision the cataloguer made on that record alone -- applied as they
        made it, whatever the settings on the run over the whole file say;
      * the run over the whole file, if there has been one;
      * nothing, and the record is written out unchanged.

    `previews_for` asks for one record's previews back, which is what the
    per-record route reports; they are not kept for every record because a
    cataloguer may work through hundreds.

    Returns None if there is no uploaded file, otherwise a report of what the
    rebuild did.
    """
    all_records = _load_all_records()
    if all_records is None:
        return None

    patterns = _load_library()
    per_record = decisions.get("records") or {}
    batch = decisions.get("batch")

    # A run over the whole file carries the skip list and the merge choices;
    # with no such run there is nothing skipped and nothing kept separate.
    skip_records = _skipped_records(batch or {})
    keep_separate = _keep_separate(batch or {})

    rejections: list = []
    if batch is not None:
        frequency = batch.get("frequency", "")
        continuity = batch.get("numbering_continuity", "r")
        units_per_higher = resolve_units_per_higher(batch.get("units_per_higher"))
        holdings_level = resolve_holdings_level(batch.get("holdings_level"))
        # Defaults to keeping them: an ILS that regenerates 866s from 853/863
        # makes the originals redundant rather than wrong, and keeping them
        # means the file can be run through again with different settings.
        remove_866 = batch.get("remove_866", False)
        clear_existing = batch.get("clear_existing_853_863", False)
        conv_opts, rejections = _convention_opts(batch)
        captions = batch.get("captions") or None
        fallback = _parser_fallback(batch)

    summary: list = []
    by_source: dict = {}
    previews: list = []
    review_total = 0
    skipped_total = 0
    own_total = 0
    skipped_own = 0

    for rec_idx, record in enumerate(all_records):
        decision = per_record.get(str(rec_idx))

        # Before anything else, including clearing existing fields: a
        # skipped record is one the run does not touch at all.
        if rec_idx in skip_records:
            skipped_total += 1
            note = "Skipped: this record was left exactly as it was."
            if decision is not None:
                # Said out loud rather than quietly dropped. The decision is
                # kept, so clearing the skip and running again brings it back.
                skipped_own += 1
                note += (" The conversion you ran on this record on its own is "
                         "not in the file while it is skipped.")
            summary.append({
                "index": rec_idx,
                "converted_fields": 0,
                "conformed_fields": 0,
                "needs_review": 0,
                "skipped": True,
                "warnings": [note],
            })
            continue

        if decision is not None:
            rc, record_previews, sources = _apply_one_decision(
                record, decision, patterns)
            if rec_idx == previews_for:
                previews = record_previews
            for src in sources:
                by_source[src] = by_source.get(src, 0) + 1
            review_total += rc.needs_review
            own_total += 1
            summary.append({
                "index": rec_idx,
                "converted_fields": rc.converted,
                "conformed_fields": rc.conformed,
                "needs_review": rc.needs_review,
                "own_decision": True,
                "warnings": rc.warnings,
            })
            continue

        if batch is None:
            continue

        existing_853s = list(record.get_fields("853"))
        if clear_existing:
            record.remove_fields("853", "863")
            existing_853s = []

        fields_866 = record.get_fields("866")
        if not fields_866:
            continue

        texts = [f["a"] or "" for f in fields_866]
        sources_866 = [f for f, t in zip(fields_866, texts) if t]
        statements = [t for t in texts if t]

        parsed, sources = _parse_all(statements, patterns, fallback)
        for src in sources:
            by_source[src] = by_source.get(src, 0) + 1

        rc = convert_record(
            parsed,
            existing_853s=existing_853s,
            captions=captions,
            frequency=frequency,
            numbering_continuity=continuity,
            merge_patterns=rec_idx not in keep_separate,
            holdings_level=holdings_level,
            units_per_higher=units_per_higher,
            **conv_opts,
        )
        _apply_record_conversion(record, rc)

        if remove_866:
            _remove_converted_866s(record, sources_866, rc)

        review_total += rc.needs_review
        summary.append({
            "index": rec_idx,
            "converted_fields": rc.converted,
            "conformed_fields": rc.conformed,
            "needs_review": rc.needs_review,
            "warnings": rc.warnings,
        })

    _save_file("marc_file_converted", _records_to_bytes(all_records))

    return {
        "summary": summary,
        "by_source": by_source,
        "rejections": rejections,
        "needs_review": review_total,
        "skipped_records": skipped_total,
        "own_decisions": own_total,
        "skipped_own_decisions": skipped_own,
        "previews": previews,
        "converted_indexes": [row["index"] for row in summary
                              if not row.get("skipped")],
    }


@app.route("/api/convert-record", methods=["POST"])
def api_convert_record():
    """Record this cataloguer's decision about one record, and rebuild the file."""
    if not HAS_PYMARC:
        return jsonify({"error": "pymarc is not installed on the server."}), 500

    data = request.get_json(force=True) or {}
    all_records = _load_all_records()
    if all_records is None:
        return jsonify({"error": "No MARC file found. Please upload a file first."}), 400

    record_index = int(data.get("record_index", 0))

    try:
        if record_index >= len(all_records):
            return jsonify({"error": "Record index out of range."}), 400

        decisions = _load_decisions()
        decisions["records"][str(record_index)] = data

        # Rebuilt before the decision is stored, so a decision that cannot be
        # applied is not left behind to break every later rebuild with it.
        result = _rebuild_converted(decisions, previews_for=record_index)
        _save_decisions(decisions)

        return jsonify({
            "success": True,
            "previews": result["previews"],
            # How much of the file this cataloguer has now converted a record
            # at a time, so the screen can say so rather than leave them
            # counting.
            "records_with_decisions": result["own_decisions"],
        })
    except Exception as exc:
        app.logger.exception("Request failed")
        return jsonify({"error": str(exc)}), 500


@app.route("/api/batch-convert", methods=["POST"])
def api_batch_convert():
    """
    Convert the rest of the file, applying the confirmed patterns.

    The rest of it: a record the cataloguer has already converted on its own
    keeps that conversion, with the settings they chose for it, rather than
    being redone with the settings on this run.
    """
    if not HAS_PYMARC:
        return jsonify({"error": "pymarc is not installed."}), 500

    data = request.get_json(force=True) or {}

    try:
        decisions = _load_decisions()
        decisions["batch"] = data

        result = _rebuild_converted(decisions)
        if result is None:
            return jsonify(
                {"error": "No MARC file found. Please upload a file first."}), 400
        _save_decisions(decisions)

        patterns = _load_library()
        labels = _source_labels(patterns)
        return jsonify({
            "success": True,
            # The headline figure. A skipped record has a row in the summary,
            # so the figure is the records the run converted, not its rows:
            # counting both put "5 records converted" beside "1 record skipped".
            "records_processed": len(result["converted_indexes"]),
            "needs_review": result["needs_review"],
            "skipped_records": result["skipped_records"],
            "own_decisions": result["own_decisions"],
            "skipped_own_decisions": result["skipped_own_decisions"],
            "converted_indexes": result["converted_indexes"],
            "rejections": result["rejections"],
            "by_source": [
                {"source": src, "label": labels.get(src, src), "count": n}
                for src, n in sorted(result["by_source"].items(),
                                     key=lambda kv: -kv[1])
            ],
            "summary": result["summary"],
        })
    except Exception as exc:
        app.logger.exception("Request failed")
        return jsonify({"error": str(exc)}), 500


@app.route("/api/download-converted", methods=["GET"])
def api_download_converted():
    """Download the converted MARC binary."""
    marc_bytes = _load_file("marc_file_converted") or _load_file("marc_file")
    if not marc_bytes:
        return "No converted file available.", 404

    return send_file(
        io.BytesIO(marc_bytes),
        mimetype="application/marc",
        as_attachment=True,
        download_name="holdings_converted.mrc",
    )


def _record_download_name(record, index: int) -> str:
    """
    A filename a cataloguer can recognise later.

    Their own identifier if the record carries one -- the MMS ID they looked
    the record up by is the thing they will search their downloads for -- and
    the record's position in the file if it does not. Reduced to characters
    that are safe in a filename on every platform rather than trusted: the
    identifier comes out of their MARC file, not out of this tool.
    """
    identifier = record_identifier(record, _identifier_spec()) or ""
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", identifier).strip("_")[:60]
    return f"holdings_{safe or f'record_{index + 1}'}.mrc"


@app.route("/api/download-record", methods=["GET"])
def api_download_record():
    """
    One record on its own, as it now stands in the converted file.

    For the cataloguer who has converted a handful of records by hand and wants
    those, rather than a run over everything they uploaded.
    """
    try:
        index = int(request.args.get("index", ""))
    except (TypeError, ValueError):
        return "Which record? No usable record number was given.", 400

    marc_bytes = _load_file("marc_file_converted") or _load_file("marc_file")
    if not marc_bytes:
        return "No file available.", 404

    records = records_from_bytes(marc_bytes)
    if not 0 <= index < len(records):
        return "Record index out of range.", 404

    record = records[index]
    return send_file(
        io.BytesIO(_records_to_bytes([record])),
        mimetype="application/marc",
        as_attachment=True,
        download_name=_record_download_name(record, index),
    )


# ---------------------------------------------------------------------------
# Shared chrome and request parsing
#
# These briefly lived in marc_serials/webui.py, which existed so three
# applications could share one copy. With one application there is nothing to
# share them with, and the indirection stopped earning its keep.
# ---------------------------------------------------------------------------

# Inside the package, so a non-editable `pip install` finds the stylesheet
# and the version file too.
SHARED_DIR = os.path.join(_BASE_DIR, "shared")


def _load_about() -> dict:
    """
    Version and changelog for the badge in the header.

    Read per request rather than cached at import, so editing the file and
    reloading the page is enough to see the change. Never fatal: a missing or
    malformed file degrades to no badge rather than a broken page.
    """
    try:
        with open(os.path.join(SHARED_DIR, "about.json"), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        app.logger.warning("Could not read shared/about.json", exc_info=True)
        return {}


@app.route("/ui.css")
def ui_css():
    """Serve the stylesheet."""
    return send_from_directory(SHARED_DIR, "ui.css", mimetype="text/css")


@app.route("/favicon.png")
@app.route("/favicon.ico")
def favicon():
    """
    The tab icon, under both names.

    The page links favicon.png, and browsers ask for /favicon.ico anyway --
    for a bookmark, or before any page has been parsed. Serving the same file
    under both answers the request that was returning 404 on every page load,
    which is the one console error every browser check in this project has
    reported and then ignored.
    """
    return send_from_directory(SHARED_DIR, "favicon.png", mimetype="image/png")


def _convention_opts(data: dict) -> tuple:
    """
    Build a caption-convention spec from a request body.

    The named preset ('standard' follows MARC 21; 'house' reproduces the local
    practice of year in $a with chronology as text) is only a starting point --
    per-level subfields, indicators and the chronology format may all be
    overridden.  Returns (kwargs for convert_holdings, rejection messages).
    """
    conv = (data.get("convention") or CONVENTION_STANDARD).strip().lower()

    subfields = data.get("subfields")
    if not isinstance(subfields, dict):
        subfields = None

    indicators = data.get("indicators")
    if not (isinstance(indicators, (list, tuple)) and len(indicators) == 2):
        indicators = None

    chron = data.get("chronology")
    if isinstance(chron, str) and chron.strip().lower() in ("text", "code"):
        chron_as_text = chron.strip().lower() == "text"
    else:
        chron_as_text = None

    spec, rejections = resolve_convention(
        conv, subfields=subfields, indicators=indicators,
        chron_as_text=chron_as_text
    )
    return {"convention_spec": spec}, rejections


# ---------------------------------------------------------------------------
# Converting one statement on its own
#
# Carried over from the standalone converter, which is where a cataloguer went
# to ask "what does this statement convert to?" without a file or a pattern.
# ---------------------------------------------------------------------------

@app.route("/api/parse-text", methods=["POST"])
def api_parse_text():
    """
    Parse a single 866 $a text string and return structured data + preview.

    This previews one statement in isolation, so its $8 is always 1.1.  Applied
    numbering is decided per record by convert_record(), which shares an 853
    across statements with the same publication pattern.
    """
    data = request.get_json(force=True)
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "No text provided"}), 400

    captions = data.get("captions") or {}
    frequency = data.get("frequency", "")
    continuity = data.get("numbering_continuity", "r")
    units_per_higher = resolve_units_per_higher(data.get("units_per_higher"))
    holdings_level = resolve_holdings_level(data.get("holdings_level"))
    linking = int(data.get("linking_number", 1))

    conv_opts, rejections = _convention_opts(data)
    parse_result = parse_866(text)
    conversion = convert_holdings(
        parse_result,
        linking_number=linking,
        captions=captions or None,
        frequency=frequency,
        numbering_continuity=continuity,
        holdings_level=holdings_level,
        units_per_higher=units_per_higher,
        **conv_opts,
    )
    conversion.warnings.extend(rejections)

    return jsonify({
        "parse": {
            "success": parse_result.success,
            "needs_review": parse_result.needs_review,
            "warnings": parse_result.warnings,
            "ranges": [
                {
                    "raw": r.raw,
                    "open_ended": r.open_ended,
                    "start": {
                        "enum": [{"caption": lvl.caption, "value": lvl.value}
                                 for lvl in r.start.enum],
                        "year": r.start.year,
                        "month": r.start.month,
                    },
                    "end": {
                        "enum": [{"caption": lvl.caption, "value": lvl.value}
                                 for lvl in r.end.enum] if r.end else [],
                        "year": r.end.year if r.end else None,
                        "month": r.end.month if r.end else None,
                    } if r.end else None,
                }
                for r in parse_result.ranges
            ],
        },
        "conversion": conversion.to_dict(),
        "preview": {
            "field_853": conversion.field_853.display() if conversion.field_853 else None,
            "fields_863": [f.display() for f in conversion.fields_863],
        },
    })



# ---------------------------------------------------------------------------

def main() -> None:
    """Run the application locally. Installed as the `marc-serials` command."""
    port = int(os.environ.get("MARC_PORT", 5003))
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", port=port)


if __name__ == "__main__":
    main()
