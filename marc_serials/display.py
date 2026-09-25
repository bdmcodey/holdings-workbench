"""
display.py
----------
The 866 an ILS generates from an 853 and its 863s, as Alma writes it.

Used to close the circle the tool is part of: holdings are exported, converted
here, loaded back, and the ILS regenerates each 866 from the new 853/863s. If
those 866s are exported and converted again, they must come back as the same
853/863s -- anything else is drift, and a bug somewhere. Alma cannot be run
from here, so this reproduces what it writes, and scripts/round_trip.py runs
every statement round the loop.

Written against the 48 866s in a real Alma export that were generated from
hand-entered 863s and are linked back to them by $8. Every one of the 48 is
reproduced exactly (tests/test_display.py pins their shapes). What those 48
show:

    levels joined by ":"                          v.44:no.3
    chronology in parentheses, year:month         (1987:May/June)
    months as Alma abbreviates them               Mar.  May  June  July  Sept.
    a range written as both boundaries in full    v.3(1987)-v.3(1988)
    $w g as a trailing comma                      v.45(1988),
    no enumeration: the chronology bare           1986-1994

What they do not show -- seasons, a day, a chronology-only range with months,
$w n -- follows Z39.71's pattern for the rest ("1990:Jan.-1994:Dec.",
"2014:Nov. 7", ";" for a non-gap break), and is where a second look at real
Alma output would help.
"""

from __future__ import annotations

from typing import Optional

# Alma's month forms, from the export. Seasons are Z39.71's words; Alma's own
# are not in the sample.
_CHRON_LABELS = {
    "01": "Jan.", "02": "Feb.", "03": "Mar.", "04": "Apr.", "05": "May",
    "06": "June", "07": "July", "08": "Aug.", "09": "Sept.", "10": "Oct.",
    "11": "Nov.", "12": "Dec.",
    "21": "Spring", "22": "Summer", "23": "Fall", "24": "Winter",
}

_ENUM_CODES = "abcdef"
_CHRON_CODES = "ijkl"


def _sub(field, code: str) -> str:
    """First value of a subfield, from a pymarc Field or the converter's FieldData."""
    for sf in getattr(field, "subfields", None) or ():
        if sf.code == code:
            return (sf.value or "").strip()
    return ""


def _is_chronology_caption(caption: str) -> bool:
    """
    "(year)", "(month)" and the like name chronology, whatever subfield holds
    them. "(*)" is the one parenthesised caption that does not: it stands for
    an enumeration level with no caption on the piece.
    """
    return (caption.startswith("(") and caption.endswith(")")
            and caption != "(*)")


# Which kind of chronology a subfield holds, when its 853 caption does not say.
_CHRON_KIND_BY_CODE = {"i": "(year)", "j": "(month)", "k": "(day)", "l": "(year)"}


def _ends(value: str) -> tuple[str, str, bool]:
    """
    A compressed value's two boundaries: "3-5" -> ("3", "5"), "7" -> ("7", "7"),
    "6-" -> ("6", "", open). Combined values ("05/06") are one boundary.
    """
    if value.endswith("-"):
        return value[:-1], "", True
    if "-" in value:
        start, _, end = value.partition("-")
        return start, end, False
    return value, value, False


def _chron_text(value: str) -> str:
    """A coded month or season as Alma writes it: "05/06" -> "May/June"."""
    return "/".join(_CHRON_LABELS.get(part, part) for part in value.split("/"))


def render_866(f853, f863) -> Optional[str]:
    """
    The 866 $a an ILS would generate for this 863 under this 853, or None when
    there is nothing to render.
    """
    if f863 is None:
        return None

    enum: list[tuple[str, str]] = []      # (caption, value)
    chron: list[tuple[str, str]] = []     # (caption, value)
    for code in _ENUM_CODES + _CHRON_CODES:
        value = _sub(f863, code)
        if not value:
            continue
        caption = _sub(f853, code)
        if code in _CHRON_CODES or _is_chronology_caption(caption):
            if not _is_chronology_caption(caption):
                caption = _CHRON_KIND_BY_CODE.get(code, "(year)")
            chron.append((caption, value))
        else:
            enum.append((caption, value))
    if not enum and not chron:
        return None

    ranged = any("-" in v for _, v in enum + chron)
    open_ended = any(v.endswith("-") for _, v in enum + chron)

    def boundary(side: int) -> str:
        levels = []
        for caption, value in enum:
            part = _ends(value)[side]
            if part:
                levels.append(f"{'' if caption == '(*)' else caption}{part}")
        dates = []
        for caption, value in chron:
            part = _ends(value)[side]
            if not part:
                continue
            # Only a month or season is a word; years and days stay numbers,
            # and a day follows its month after a space: "2014:Nov. 7".
            if caption in ("(month)", "(season)"):
                dates.append(_chron_text(part))
            elif caption == "(day)" and dates:
                dates[-1] = f"{dates[-1]} {part}"
            else:
                dates.append(part)
        text = ":".join(levels)
        when = ":".join(dates)
        if text and when:
            return f"{text}({when})"
        return text or when

    start = boundary(0)
    if open_ended:
        rendered = f"{start}-"
    elif ranged:
        rendered = f"{start}-{boundary(1)}"
    else:
        rendered = start

    brk = _sub(f863, "w")
    if brk == "g":
        rendered += ","
    elif brk == "n":
        rendered += ";"
    return rendered


# ── The round trip ────────────────────────────────────────────────────────────

SAME = "same"
CAPTION_ONLY = "caption only"    # the 853 names a level no 863 fills; see below
DRIFT = "drift"
NOT_CONVERTED = "not converted"


def _values(field) -> list:
    return [(sf.code, sf.value) for sf in field.subfields if sf.code != "8"]


def _shape(rc) -> tuple:
    """What a conversion wrote, without the $8s an ILS would renumber."""
    return ([(f.indicator1 + f.indicator2, _values(f)) for f in rc.fields_853],
            [(f.indicator1 + f.indicator2, _values(f)) for f in rc.fields_863])


def round_trip(statement: str) -> dict:
    """
    Convert a statement, generate the 866s an ILS would from the result, and
    convert those. The two conversions should write the same fields.

    Returns {"outcome", "generated", "first", "second"}. One difference is
    expected and reported apart as CAPTION_ONLY: a statement that names a level
    with no value -- the "no. 9" at one end of "v. 1 (1973)-v. 11 no. 9 (Sep
    1983)" -- keeps that level in its 853, and the first conversion says the
    value was left out. An 866 generated from the 863s has no way to name a
    level none of them fills, so the second 853 cannot carry it. Every 863 is
    still the same.
    """
    from marc_serials.converter import convert_record
    from marc_serials.parser import parse_866

    first = convert_record([parse_866(statement)])
    if not first.fields_863:
        return {"outcome": NOT_CONVERTED, "generated": [], "first": None,
                "second": None}

    by_link = {_sub(f, "8"): f for f in first.fields_853}
    generated = [render_866(by_link.get(_sub(f, "8").split(".")[0]), f)
                 for f in first.fields_863]
    second = convert_record([parse_866(g) for g in generated if g])

    a, b = _shape(first), _shape(second)
    if a == b:
        outcome = SAME
    elif a[1] == b[1] and _captions_filled(a) == b[0]:
        outcome = CAPTION_ONLY
    else:
        outcome = DRIFT
    return {"outcome": outcome, "generated": generated, "first": a, "second": b}


def _captions_filled(shape: tuple) -> list:
    """The 853s with only the captions some 863 gives a value for."""
    f853s, f863s = shape
    used = {code for _, values in f863s for code, _ in values}
    return [(ind, [(c, v) for c, v in values
                   if c in used or c not in _ENUM_CODES + _CHRON_CODES])
            for ind, values in f853s]
