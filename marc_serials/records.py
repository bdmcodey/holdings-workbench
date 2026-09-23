"""
MARC record handling shared by every application.

Reading a file into the shape the screens want, writing a conversion back onto
a record, and lining a converted statement up with the 866 it came from. None of
it depends on Flask, so it is testable on its own.

Each of these existed twice, once in converter/app.py and once in
workbench/app.py, and the copies had drifted -- not in what they did, but in
what they said. The workbench's copy of remove_converted_866s() carried a
one-line docstring where the converter's carried the account of the 0.5.2 data
loss and the warning never to build `sources` from get_fields("866"). Losing the
reasoning is how the reasoning stops being followed.
"""

from __future__ import annotations

import io
from typing import Optional

from pymarc import MARCReader, MARCWriter

# The default lives with the setting it belongs to, so the two cannot drift.
from .converter import DEFAULT_HOLDINGS_LEVEL, SubfieldData


# ---------------------------------------------------------------------------
# The identifier a cataloguer looks a record up by
# ---------------------------------------------------------------------------

# Holdings records usually carry no 245: the title lives on the bibliographic
# record, not on the holdings attached to it.  So the row label falls back to
# "Record 3", and a real file measured here -- 372 holdings records -- produced
# 372 rows reading "Record 1", "Record 2", ... with no title, no ISSN, and the
# same location on every one.  Indistinguishable.  The identifier is not
# decoration on that screen; it is the only thing that tells two rows apart.
#
# 999 $b because the file this was built against is an Ex Libris Alma export,
# where the MMS ID is the identifier shown beside every record and the one
# reports are keyed on.  The same 999 carries $d, the holdings MMS ID, and the
# record also has 001 and 004 -- all four unique across the file.  $b is the
# default because it is the number a cataloguer recognises, not because it is
# the most precise: internal linking numbers are not what anyone searches by.
#
# Configurable rather than fixed is the next change; this is written as a spec
# string from the start so that change is a setting rather than a rewrite.
DEFAULT_IDENTIFIER_SPEC = "999$b"


def parse_identifier_spec(spec: str) -> Optional[tuple[str, str]]:
    """
    Split "999$b" into ("999", "b"), or "001" into ("001", "").

    Liberal about how it is written -- "999$b", "999 $b", "999b" and "999"
    all arrive from somewhere, and a cataloguer typing a field into a settings
    box should not have to know which one this wanted.  Returns None for
    anything that is not a MARC tag, so a typo shows as "no identifier" rather
    than silently matching nothing.
    """
    text = (spec or "").strip().replace("$", " ").replace("|", " ")
    parts = text.split()
    if not parts:
        return None
    tag = parts[0]
    # "999b" with nothing between them.
    if len(parts) == 1 and len(tag) == 4 and tag[:3].isdigit():
        return tag[:3], tag[3].lower()
    if len(tag) != 3 or not tag.isdigit():
        return None
    code = parts[1][0].lower() if len(parts) > 1 and parts[1] else ""
    return tag, code


# Tags the tool reads as holdings data rather than as identity.  Enumeration,
# chronology and textual holdings are what it converts; offering one as "the
# field to find a record by" would be offering the cataloguer their own data
# back as a label.  Excluded from the candidate list for that reason alone --
# nothing stops someone naming one by hand.
_HOLDINGS_DATA_TAGS = {"853", "854", "855", "863", "864", "865",
                       "866", "867", "868"}


def identifier_candidates(records, limit: int = 6) -> list[dict]:
    """
    Fields in this file that could serve as the identifier, best first.

    Three properties make a field an identifier, and measuring all three is
    what separates a real one from a field that merely looks promising:

      * it is on every record -- one missing is a row that cannot be found;
      * it appears at most once per record -- a repeated field is data about
        the record, not a name for it;
      * its values are distinct on every record that carries it -- not merely
        more than one value between them. Two holdings of the same serial
        share a title, so 245 $a can be distinct on two records out of three:
        enough to look like a candidate, not enough to name a row.

    Measured against a 372-record Alma export, those three together return
    exactly the four identifiers it carries (001, 004, 999 $b, 999 $d) and
    reject everything else.  The middle test is what earns its place: 866 $a
    has 371 distinct values across 372 records and would otherwise rank near
    the top, but it occurs up to 33 times in a single record.

    Ranked rather than filtered, so a file where nothing scores perfectly
    still offers its best few with the numbers attached, and the cataloguer
    decides.  Each candidate carries a sample value, because that is what
    makes one recognisable -- "991000485469603731" is an MMS ID to the person
    who uses them, and "999$b" is not.
    """
    total = len(records)
    if not total:
        return []

    seen_values: dict[str, list] = {}
    repeats: dict[str, int] = {}
    for record in records:
        if record is None:
            continue
        per_record: dict[str, int] = {}
        first: dict[str, str] = {}
        for field in record.get_fields():
            if field.tag in _HOLDINGS_DATA_TAGS:
                continue
            if field.tag < "010":
                keys = [(field.tag, (getattr(field, "data", "") or "").strip())]
            else:
                keys = [(f"{field.tag}${sf.code}", (sf.value or "").strip())
                        for sf in field.subfields]
            for key, value in keys:
                per_record[key] = per_record.get(key, 0) + 1
                first.setdefault(key, value)
        for key, count in per_record.items():
            repeats[key] = max(repeats.get(key, 0), count)
        for key, value in first.items():
            seen_values.setdefault(key, []).append(value)

    out = []
    for key, values in seen_values.items():
        present = len(values)
        distinct = len(set(values))
        if distinct < 2:
            continue                      # a constant is a label, not a name
        sample = next((v for v in values if v), "")
        out.append({
            "spec": key,
            "present": present,
            "total": total,
            "distinct": distinct,
            "repeated": repeats.get(key, 1) > 1,
            # Distinct on every record that has it, rather than merely having
            # more than one value. A title is the case that forced this: two
            # holdings of the same serial share one, so 245 $a can come back
            # distinct on 2 of 3 records -- enough to look like a candidate,
            # and not enough to name a row, because choosing it would label
            # two rows identically. Carried rather than filtered, so a file
            # with nothing better still offers its best and says what is
            # wrong with it.
            "unique": distinct == present,
            "sample": sample,
        })

    # Order of the two tests matters and is not arbitrary. "Appears once in
    # this record" comes first because a repeated field has no single value to
    # put beside a row at all; "distinct across records" comes second, because
    # a field that does have one value per record but shares it between two is
    # still displayable, just ambiguous. Structure before distinctiveness.
    out.sort(key=lambda c: (not c["repeated"],
                            c["unique"],
                            c["present"] / total,
                            c["distinct"] / max(c["present"], 1)),
             reverse=True)
    return out[:limit]


def record_identifier(record, spec: str = DEFAULT_IDENTIFIER_SPEC) -> str:
    """
    What this record should be found by, or "" when it carries no such field.

    Control fields (001-009) hold data rather than subfields, so a spec naming
    one is read whole and any subfield code on it ignored.  Never raises: a
    record missing the field is the ordinary case, not an error, and it is the
    caller's business to notice that every record is missing it.
    """
    parsed = parse_identifier_spec(spec)
    if not parsed:
        return ""
    tag, code = parsed
    fields = record.get_fields(tag)
    if not fields:
        return ""
    field = fields[0]
    if tag < "010":
        return (getattr(field, "data", "") or "").strip()
    if not code:
        return ""
    return (field.get(code) or "").strip()


def read_marc_file(fileobj,
                   identifier_spec: str = DEFAULT_IDENTIFIER_SPEC) -> list[dict]:
    """
    Read a MARC file and extract records with their 866 fields.

    Returns a list of record dicts for the UI.

    `identifier_spec` names the field each record should be found by, written
    as "999$b" or "001".  A record without that field gets "" -- the ordinary
    case, since files come from every ILS there is.  Every record getting ""
    means the file does not carry that field at all, which is worth saying to
    the cataloguer rather than showing a column of blanks; the caller is where
    that belongs, because only the caller knows it has the whole file.
    """
    records_out = []
    reader = MARCReader(fileobj, to_unicode=True, force_utf8=True,
                        utf8_handling="replace")
    for rec_idx, record in enumerate(reader):
        if record is None:
            # pymarc yields None for a record it could not decode -- a bad
            # length in the leader, a truncated directory. Its position is
            # kept, so every index here still means the same record it means
            # in the file, and it is marked rather than dropped. Reading
            # straight through used to raise AttributeError on the next line,
            # so one damaged record in a library export made the whole file
            # fail to upload with nothing to say which record was at fault.
            records_out.append({
                "index": rec_idx,
                "title": f"Record {rec_idx + 1} — could not be read",
                "identifier": "",
                "issn": "",
                "location": "",
                "fields_866": [],
                "has_853": False,
                "has_863": False,
                "unreadable": True,
            })
            continue

        title_field = record.get("245")
        title = ""
        if title_field:
            title = title_field.get_subfields("a", "b")
            title = " ".join(title).strip().rstrip(" /:")

        issn_field = record.get("022")
        issn = issn_field["a"] if issn_field and issn_field["a"] else ""

        holdings_loc = record.get("852")
        location = ""
        if holdings_loc:
            loc_parts = holdings_loc.get_subfields("b", "c")
            location = " > ".join(loc_parts)

        fields_866 = []
        for f in record.get_fields("866"):
            subfield_a = f.get("a") or ""
            subfield_z = f.get("z") or ""
            fields_866.append({
                "ind1": f.indicator1,
                "ind2": f.indicator2,
                "a": subfield_a,
                "z": subfield_z,
                "display": f"866 {f.indicator1}{f.indicator2} $a {subfield_a}"
                           + (f" $z {subfield_z}" if subfield_z else ""),
            })

        records_out.append({
            "index": rec_idx,
            "title": title or f"Record {rec_idx + 1}",
            "identifier": record_identifier(record, identifier_spec),
            "issn": issn,
            "location": location,
            "fields_866": fields_866,
            "has_853": bool(record.get_fields("853")),
            "has_863": bool(record.get_fields("863")),
            "unreadable": False,
        })

    return records_out


def unreadable_positions(records: list[dict]) -> list[int]:
    """One-based positions of the records read_marc_file() could not decode."""
    return [r["index"] + 1 for r in records if r.get("unreadable")]


def refuse_unreadable(records: list[dict]) -> Optional[str]:
    """
    Why this file cannot be worked on, or None when every record decoded.

    A record pymarc cannot decode cannot be written back out either, so
    converting the file would mean returning it with that record missing. The
    file is refused instead, naming the positions, which is the same rule the
    converter applies to a statement it can only partly read: better to say so
    than to hand back holdings with something quietly gone.
    """
    bad = unreadable_positions(records)
    if not bad:
        return None
    where = ", ".join(str(n) for n in bad[:10])
    more = f" and {len(bad) - 10} more" if len(bad) > 10 else ""
    plural = "s" if len(bad) > 1 else ""
    return (
        f"This file has {len(bad)} record{plural} that could not be read "
        f"(position{plural} {where}{more}). A record that cannot be read "
        f"cannot be written back out, so converting the file would return it "
        f"with that record missing. Nothing has been loaded. Repair or remove "
        f"the record{plural} and upload the file again."
    )


def records_from_bytes(data: bytes) -> list:
    """Every pymarc Record in `data`, in file order."""
    reader = MARCReader(io.BytesIO(data), to_unicode=True,
                        force_utf8=True, utf8_handling="replace")
    return list(reader)


def records_to_bytes(records: list) -> bytes:
    """Serialise a list of pymarc Records to MARC binary."""
    buf = io.BytesIO()
    writer = MARCWriter(buf)
    for rec in records:
        writer.write(rec)
    # close_fh defaults to True, which closes the BytesIO and makes the
    # getvalue() below raise "I/O operation on closed file".
    writer.close(close_fh=False)
    return buf.getvalue()


def add_853(record, field_data) -> None:
    """
    Add a regenerated 853, replacing any existing one with the same $8.

    A regenerated 853 supersedes the field it was built from — leaving both in
    place would give the record two patterns sharing one linking number, so the
    863s would be ambiguous.
    """
    link = next((sf.value for sf in field_data.subfields if sf.code == "8"), None)
    if link is not None:
        for old in list(record.get_fields("853")):
            if (old.get("8") or "").strip() == str(link).strip():
                record.remove_field(old)
    # Ordered, not appended. A record read in as 852, 866, 999 and given its
    # 853 by add_field() comes back out as 852, 866, 999, 853 -- valid MARC
    # and wrong to every eye that reads it, since the field describing the
    # pattern then sits after the textual holdings it explains and after the
    # local numbers at the end. pymarc inserts before the first higher tag,
    # and scans past equal ones, so repeated calls keep the order they were
    # made in: an 853 lands before its 863s, and linked 863s stay in sequence.
    record.add_ordered_field(field_data.to_pymarc())


def existing_863_count(record) -> int:
    """
    863s the record carried before this tool touched it.

    A record that has them was coded by hand, or by an earlier load, and the
    cataloguer's rule is that data already there is kept unless the tool is
    told to overwrite it ("Clear existing 853 / 863 first"). Measured on a real
    372-record export before that rule existed: 10 of the 13 records with 863s
    lost some or all of them to regenerated ones -- 38 fields, among them every
    $w g gap marker, since an 866 cannot carry one back.
    """
    return len(record.get_fields("863"))


def kept_existing_note(count: int) -> str:
    """What a record left alone because of its own 863s says about itself."""
    many = count != 1
    return (f"This record already has {count} 863 field{'s' if many else ''}, "
            f"so it was left exactly as it was: nothing was generated beside "
            f"{'them' if many else 'it'} and nothing was replaced. Tick "
            f"\"Clear existing 853 / 863 first\" to regenerate this record's "
            f"853s and 863s from its 866s instead.")


def existing_853_notes(record) -> list:
    """
    What is wrong with the 853s already on a record, said and never corrected.

    Two things: an indicator MARC 21 does not define for the 853 (0-3 in both
    positions, no blank), and two 853s sharing one $8, which leaves the 863s
    under that number unable to say which pattern they follow. Both were
    found on a real export -- one 853 coded "X" and blank, sharing $8 1 with
    the record's real pattern.
    """
    notes: list = []
    by_link: dict = {}
    for f in record.get_fields("853"):
        link = (f.get("8") or "").strip()
        by_link.setdefault(link, []).append(f)
        i1, i2 = f.indicator1 or " ", f.indicator2 or " "
        if i1 not in "0123" or i2 not in "0123" or " " in (i1, i2):
            shown = f"{i1}{i2}".replace(" ", "#")
            notes.append(
                f"The 853 already on this record with $8 {link or '(none)'} has "
                f"indicators \"{shown}\"; MARC 21 defines 0, 1, 2 and 3 for "
                f"each. It was left as it is.")
    for link, fields in by_link.items():
        if len(fields) > 1:
            notes.append(
                f"{len(fields)} 853s already on this record share "
                f"$8 {link or '(none)'}, so the 863s under that number cannot "
                f"say which pattern they follow. Left as they are.")
    return notes


def apply_record_conversion(record, rc) -> None:
    """
    Write a RecordConversion onto a pymarc record.

    863s already sitting under a link number we are about to write are dropped
    first: they describe the same holdings from an earlier run, so replacing
    them keeps re-conversion idempotent instead of accumulating duplicates.
    """
    links = set(rc.links_written)
    for old in list(record.get_fields("863")):
        if (old.get("8") or "").split(".")[0].strip() in links:
            record.remove_field(old)
    for f853 in rc.fields_853:
        add_853(record, f853)           # replaces any 853 sharing its $8
    for f863 in rc.fields_863:
        record.add_ordered_field(f863.to_pymarc())


def match_866_sources(record, texts) -> list:
    """
    Line each statement up with the 866 field it came from.

    Returns a list the same length as `texts`, holding either the matching field
    or None.  Each field is claimed at most once, so a record carrying the same
    statement twice maps to two distinct fields rather than the first one twice.

    Used by the single-statement route, where the text arrives from the client
    and may have been edited in the UI.  An edited statement matches nothing and
    yields None, which remove_converted_866s() then leaves alone: a field we
    cannot account for is never deleted.
    """
    claimed: list = []
    matched: list = []
    for text in texts:
        wanted = (text or "").strip()
        found = None
        for field in record.get_fields("866"):
            if any(field is c for c in claimed):
                continue
            if (field["a"] or "").strip() == wanted:
                found = field
                claimed.append(field)
                break
        matched.append(found)
    return matched


# 866 subfields the conversion accounts for. $a is what is converted; $x and $z
# are carried onto the 863s by carry_866_notes(); $8 links the 866 to an 863
# the conversion supersedes. Anything else on an 866 goes nowhere, so an 866
# carrying it is not removed.
ACCOUNTED_866_SUBFIELDS = frozenset("axz8")


def carry_866_notes(sources, rc) -> None:
    """
    Put each 866's notes -- $x nonpublic, $z public -- on the 863s it became.

    863 defines both, and Alma writes an 863's $z back out as its 866's $z, so
    a note left behind is a note the regenerated display loses. Measured on a
    real export: 5 of 5 hand-entered 863s with "$z Incomplete" had it in their
    Alma-generated 866, and the tool dropped all five.

    One statement can become several 863s, and a note is about the statement.
    It goes on the last of them, where a display reading them in order puts it
    after the holdings it qualifies -- and the placement is said, because it is
    a choice the note itself does not make.

    `sources` is aligned with rc.results, as for remove_converted_866s().
    """
    for field, result in zip(sources, rc.results):
        if field is None or not result.fields_863:
            continue
        notes = [(sf.code, sf.value) for sf in field.subfields
                 if sf.code in ("x", "z") and (sf.value or "").strip()]
        if not notes:
            continue
        target = result.fields_863[-1]
        for code, value in notes:
            target.subfields.append(SubfieldData(code, value))
        if len(result.fields_863) > 1:
            shown = "; ".join(f"${c} {v}" for c, v in notes)
            result.warnings.append(
                f"This statement became {len(result.fields_863)} 863s and its "
                f"866 carried a note ({shown}). The note was put on the last "
                f"of them; check whether it belongs to all of the holdings or "
                f"only to part.")


def remove_converted_866s(record, sources, rc) -> None:
    """
    Drop only those 866s whose statement actually produced 863s.

    Stripping used to be decided for the whole record, so a statement the parser
    could not read had its 866 removed alongside its converted neighbours and
    left nothing behind -- the holdings were simply gone, and the response still
    reported success.  Each field is now judged on its own result.

    `sources` is the 866 fields that were handed to convert_record(), in the
    same order as rc.results, and may contain None for a statement with no field
    to match.  Callers must build it themselves rather than reusing
    get_fields("866"): statements with an empty $a are filtered out before
    conversion, so the two lists are not otherwise aligned.  An 866 with nothing
    in $a is consequently never stripped, which is right -- it carried nothing
    to convert.
    """
    for field, result in zip(sources, rc.results):
        if field is not None and result.fields_863:
            # Removing an 866 used to take its $z with it, silently. $x and $z
            # are carried now; anything else would still go nowhere, so the
            # field stays and says why.
            left = sorted({sf.code for sf in field.subfields
                           if sf.code not in ACCOUNTED_866_SUBFIELDS})
            if left:
                result.warnings.append(
                    "This 866 was kept although its holdings were converted: it "
                    "also carries " + ", ".join(f"${c}" for c in left)
                    + ", which has nowhere to go in an 863.")
                continue
            record.remove_field(field)


def display_marc_field(fld) -> str:
    """
    Render a pymarc field the way FieldData.display() renders a generated one,
    so an existing 853 and a generated one look identical in the UI.
    """
    ind = f"{fld.indicator1}{fld.indicator2}".replace(" ", "#")
    # Values in real records often carry padding; strip it so an existing field
    # and a generated one render identically rather than with doubled spaces.
    sfs = " ".join(f"${sf.code} {(sf.value or '').strip()}" for sf in fld.subfields)
    return f"{fld.tag} {ind} {sfs}"


# ---------------------------------------------------------------------------
# Encoding level: surfaced, never rewritten
# ---------------------------------------------------------------------------

# m says the level is recorded per field rather than per record: "The value in
# the first indicator position ... of the applicable 863-865 ... fields indicate
# the level for each holdings data field."  So m cannot be contradicted.  u
# (Unknown) and z (Other level) assert nothing to contradict either.
_LEVELS_WITHOUT_A_CLAIM = {"m", "u", "z", " ", ""}


# Enumeration runs $a-$f and chronology $i-$l, most significant first, so
# "more than one of either" is "more than the first-order designator".
_ENUM_SUBFIELDS = "abcdef"
_CHRON_SUBFIELDS = "ijkl"


def _exceeds_summary(field_863) -> bool:
    """Whether a generated 863 records past the first level of enum or chron."""
    codes = [sf.code for sf in field_863.subfields if sf.code != "8"]
    return (sum(1 for c in codes if c in _ENUM_SUBFIELDS) > 1
            or sum(1 for c in codes if c in _CHRON_SUBFIELDS) > 1)


def encoding_level_conflict(record, fields_863,
                            declared: str = DEFAULT_HOLDINGS_LEVEL
                            ) -> Optional[str]:
    """
    Whether the holdings being written exceed the level the cataloguer declared.

    This asks about *this record* and nothing else, which is the point of the
    rewrite. It used to compare the record's Leader/17 against the declared
    level, and that is a fact about the file rather than about a record: a
    372-record Alma export declaring level 3 throughout, converted by a library
    reporting at level 4, put the marker on 371 rows. A signal that fires on
    every row carries nothing, and it swamped "Needs attention" with the whole
    file. The cataloguer who reported it was right to call it overkill.

    So the file-wide comparison moved to where a file-wide fact belongs -- one
    line above the list, see encoding_level_summary() -- and what remains here
    is the question that genuinely varies from record to record:

        Level 3 is summary holdings, "only the highest levels (first-order
        designators)" (Z39.71 4.3). An 863 carrying "$a 1-5 $b 1-4 $i 1990-1994
        $j 01-12" is not that.

    Declaring level 4 therefore never flags anything: level 4 is "the most
    specific levels (including all hierarchical levels)", so no amount of
    detail can exceed it, and a serial with one level of enumeration is not
    under-reporting by having only one. On the export above this takes the
    marker from 371 records to none at the default, and to 242 of 371 at level
    3 -- where it means something specific, and the other 129 genuinely are
    summary.

    Reported and never corrected, deliberately. The encoding level is an
    assertion the library makes about its own holdings, and rewriting one on a
    cataloguer's behalf is a different kind of act from adding the fields they
    asked for.

    Returns the note to show, or None when there is nothing to say.
    """
    if declared != "3" or not fields_863:
        return None
    if not any(_exceeds_summary(f) for f in fields_863):
        return None
    return (
        "You are recording at level 3, which is summary holdings -- the first "
        "level of enumeration and chronology only. The fields written for this "
        "record go further than that, so its 863s claim less than they carry. "
        "Record at level 4 if these holdings are detailed."
    )


def single_part_conflict(record, fields_863) -> bool:
    """
    Whether Leader/06 calls this a single-part item while its holdings are not.

    Leader/06 = x is "Single-part item holdings" -- a thing complete in one
    part. A record whose holdings name a volume or an issue is describing
    something with numbered parts, and one whose chronology spans a range is
    describing more than one of them. Either way x is contradicted.

    What it should be instead is deliberately not decided here. v is multipart
    item holdings and y is serial item holdings, and telling a finite set of
    volumes from a continuing publication is a cataloguing judgement a holdings
    statement does not settle -- the same reasoning D18 reached for the
    encoding level. The tool says x cannot be right; the cataloguer says what
    is.

    Measured on a real 372-record Alma export, migrated from an ILS that kept
    no MARC holdings: 334 records coded x, of which 330 are contradicted, 3
    could genuinely be single-part ("(2010)", a year with nothing numbered),
    and 1 produced nothing to judge by. All 38 records coded y are correct,
    and 13 of those are the only ones in the file carrying an 853 -- the ones
    somebody had already worked on by hand.
    """
    leader = str(getattr(record, "leader", "") or "")
    if (leader[6] if len(leader) > 6 else "") != "x":
        return False
    if len(fields_863) > 1:
        return True                      # several runs is several parts
    for field in fields_863:
        if any(sf.code in _ENUM_SUBFIELDS for sf in field.subfields):
            return True                  # "v. 2" says there is a v. 1
        if any(sf.code in _CHRON_SUBFIELDS and "-" in sf.value
               for sf in field.subfields):
            return True                  # a span of more than one
    return False


def encoding_level_differs(record, declared: str = DEFAULT_HOLDINGS_LEVEL) -> bool:
    """
    Whether this record's own Leader/17 disagrees with the declared level.

    True on nearly every record of a file whose library records at one level
    and whose Leader says another, which is why it is deliberately *not* a
    marker beside a row -- 371 identical badges say less than one line saying
    371. It is carried per record all the same, so the filter can still gather
    exactly those records when there are few enough for that to be the useful
    thing to do.
    """
    leader = str(getattr(record, "leader", "") or "")
    current = leader[17] if len(leader) > 17 else ""
    if current in _LEVELS_WITHOUT_A_CLAIM:
        return False
    return current != declared


def encoding_level_summary(records, declared: str = DEFAULT_HOLDINGS_LEVEL
                           ) -> Optional[dict]:
    """
    How the file's own Leader/17 values stand against the declared level.

    A file-wide fact said once, rather than a marker repeated down a list of
    372 rows that all say the same thing. Whoever acts on this acts on it in
    their ILS, in one operation, not record by record.

    Returns None when every record already agrees, so the screen stays quiet
    when there is nothing to say.
    """
    counts: dict = {}
    total = 0
    for record in records:
        if record is None:
            continue
        total += 1
        leader = str(getattr(record, "leader", "") or "")
        current = leader[17] if len(leader) > 17 else ""
        if current in _LEVELS_WITHOUT_A_CLAIM or current == declared:
            continue
        counts[current] = counts.get(current, 0) + 1

    if not counts:
        return None
    return {
        "declared": declared,
        "records": sum(counts.values()),
        "total": total,
        "levels": dict(sorted(counts.items())),
    }
