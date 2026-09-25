"""
marc_converter.py
-----------------
Converts ParseResult objects (from holdings_parser.py) into pymarc
Field objects:
  853 – Captions and Pattern (Basic Bibliographic Unit)
  863 – Enumeration and Chronology (Basic Bibliographic Unit)

References:
  MARC 21 Format for Holdings Data
  https://www.loc.gov/marc/holdings/
"""

from __future__ import annotations

import re
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

try:
    from pymarc import Field, Subfield, Record
    HAS_PYMARC = True
except ImportError:
    HAS_PYMARC = False

from marc_serials.parser import (ParseResult, HoldingsRange, EnumChron,
                             SEASON_CODES, MARC_CHRON_CODES, is_codeable)

# The converter's own name for it, kept so the call sites below read as they
# always did.
_is_codeable = is_codeable


# ---------------------------------------------------------------------------
# Frequency codes (853 $w)
# ---------------------------------------------------------------------------

FREQUENCY_CODES: Dict[str, str] = {
    "a": "Annual",
    "b": "Bimonthly (every 2 months)",
    "c": "Semiweekly",
    "d": "Daily",
    "e": "Biweekly (every 2 weeks)",
    "f": "Semiannual",
    "g": "Biennial",
    "h": "Triennial",
    "i": "Three times a week",
    "j": "Three times a month",
    "m": "Monthly",
    "q": "Quarterly",
    "s": "Semimonthly (twice a month)",
    "t": "Three times a year",
    "w": "Weekly",
    "u": "Unknown",
    "z": "Other",
    "": "(not specified)",
}

# ---------------------------------------------------------------------------
# Caption defaults
# ---------------------------------------------------------------------------

DEFAULT_CAPTIONS = {
    "year":  "(year)",
    "month": "(month)",
    "season": "(season)",
    "day":   "(day)",
}

# What MARC 21 writes where a level has no caption on the piece.  The standard
# allows either a caption invented and bracketed, or "an asterisk used in place
# of data", and full correlation between an 853's captions and its 863's values
# is *required* where the 863 is compressed -- which every field this tool
# writes is.  So the level cannot simply be left out, and it must not be guessed
# at either: the "39" of "39 no 1" is very probably a volume, and "very probably"
# is not something to write into a record as though the piece had said it.
#
# The parenthesised form is Harvard's documented practice and sits with the
# "(year)" and "(month)" captions already written into the same field.
NO_CAPTION = "(*)"

# Suggestions for a cataloguer filling the caption in by hand, by position.
# Only suggestions: until 0.8.9 these were written into the 853 whenever a
# statement captioned nothing, so a record asserted "v. 39" on the strength of
# position alone, with nothing on screen to say the word had been supplied.
SUGGESTED_ENUM_CAPTIONS = ("v.", "no.", "pt.")


def suggested_enum_caption(index: int) -> str:
    """What to offer a cataloguer for this level, not what to write without one."""
    if index < len(SUGGESTED_ENUM_CAPTIONS):
        return SUGGESTED_ENUM_CAPTIONS[index]
    return f"level {index + 1}"

# ---------------------------------------------------------------------------
# Subfield conventions
# ---------------------------------------------------------------------------
#
# STANDARD follows MARC 21: $a-$f carry enumeration, $i-$m carry chronology,
# and chronology values are the numeric codes (01-12, 21-24).
#
# HOUSE reproduces the local practice found in existing records, where the year
# occupies $a (an enumeration subfield), enumeration is pushed down to $b/$c,
# and chronology values are written as text ("Mar") rather than codes.  Those
# records are internally inconsistent about the chronology subfield -- 50 use
# $i, one uses $c -- so HOUSE follows the majority and uses $i.

CONVENTION_STANDARD = "standard"
CONVENTION_HOUSE    = "house"

# Enumeration is positional: the first level goes in the first subfield of
# `enum`, the second in the next, and so on.  MARC 21 puts enumeration captions
# in $a-$f in descending order of significance and says nothing about which
# words they hold, so nothing here names a level either.
_SUBFIELD_MAPS: Dict[str, Dict[str, Any]] = {
    CONVENTION_STANDARD: {"enum": ("a", "b", "c", "d", "e", "f"),
                          "year": "i", "month": "j", "day": "k"},
    # No day subfield: the local records this reproduces have no precedent for
    # one, and inventing a code would be worse than saying the day cannot be
    # placed. A statement carrying one is named, not silently levelled off.
    CONVENTION_HOUSE:    {"enum": ("b", "c", "d", "e", "f"),
                          "year": "a", "month": "i"},
}

# 863 first indicator: the level a library reports its holdings at.
#
# Field encoding level, matching Leader/17: 3 is a summary statement, 4 a
# detailed one.  Z39.71 4.3 defines them -- level 3 includes "only the highest
# levels (first-order designators)", level 4 "the most specific levels
# (including all hierarchical levels)" -- but which level an institution
# reports at is that institution's policy, not a property of any field.
#
# That was measured, not assumed.  Every 863/864/865 example in the five LC
# documents under docs/marc/ was grouped by the enumeration and chronology
# subfields it carries: of 129 stating an indicator, in 12 distinct shapes,
# four shapes are marked *both* ways, and those four cover 89 of the 129.
# "$a $i" -- a volume and a year, what most statements here convert to -- is
# marked 3 twenty-two times and 4 twenty-three times, and one field is
# byte-identical in two documents marked 3 in one and 4 in the other:
# "863 30 $8 1.1 $i 1964-1981" against "863 40 $8 1.1 $i 1964-1981".
#
# So this is not a rule with exceptions.  A function of the field cannot
# return two values for one input, so there is no rule to find, and nothing
# but the field is available where the indicator is written.  Same data,
# different institution.  scripts/measure_863_indicator.py reproduces it;
# see CORPUS-FINDINGS.
#
# So it is declared rather than inferred.  4 is the default because it is what
# the tool wrote unconditionally before this existed, and because a tool that
# encodes every level it can read is reporting in detail.
HOLDINGS_LEVELS = {
    "3": "Summary — first level of enumeration and chronology only",
    "4": "Detailed — every level the statement gives",
}
DEFAULT_HOLDINGS_LEVEL = "4"


# 853 $u: how many parts of a level make one of the level above it.
#
# "Number (or the code var or und) that specifies the total number of parts
# that comprise the next higher level of enumeration. May be used with each
# level of enumeration except the first level (subfield $a or $g) because
# there is no higher level" -- MARC 21 853-855, docs/marc/hd853855.md. The
# standard's own illustration is "a quarterly publication requires 4 issues to
# make 1 volume".
#
# Declared, never derived, and for the same reason the holdings level is: it
# is a fact about the publication, not about the statement. An 866 saying
# "v.1-5 (1990-1994)" is equally true of a monthly and a quarterly, and a
# frequency of "monthly" does not settle it either -- a monthly with two
# volumes a year has six issues to a volume, not twelve. Guessing would write
# a publication pattern nobody verified into every record in the file.
UNITS_PER_HIGHER_CODES = {"var": "Varies", "und": "Undetermined"}


def resolve_units_per_higher(raw) -> str:
    """
    A usable $u value, or "" for "not specified".

    Accepts a count, or the two codes the standard defines. Anything else is
    not written: a $u is a claim about how the serial is published, and a
    malformed one would make that claim wrongly rather than not at all. The
    screen validates before sending, so this is the backstop rather than the
    place a cataloguer is told.
    """
    value = (str(raw) if raw is not None else "").strip().lower()
    if not value:
        return ""
    if value in UNITS_PER_HIGHER_CODES:
        return value
    # "Because subfield $u is variable in length, no leading zero is used for a
    # single-character number."
    if value.isdigit() and value == value.lstrip("0") and 0 < int(value) < 1000:
        return value
    return ""


def resolve_holdings_level(raw) -> str:
    """The declared level, or the default when nothing usable was given."""
    value = (str(raw) if raw is not None else "").strip()
    return value if value in HOLDINGS_LEVELS else DEFAULT_HOLDINGS_LEVEL


# 853 indicators per convention (existing local records use "2"/"0")
_INDICATORS = {
    CONVENTION_STANDARD: ("3", "1"),
    CONVENTION_HOUSE:    ("2", "0"),
}

# What MARC 21 defines for the 853's two indicators: compressibility and
# expandability first, caption evaluation second. Both are 0-3, and neither
# defines a blank (docs/marc/hd853855.md). The settings screen reads this too.
INDICATOR_VALUES = "0123"

# The chronology levels a convention can place, in the order they are offered
# to the user.  Enumeration is not in this list: it has no fixed names, only
# positions, and its subfields come from the "enum" sequence above.
CONVENTION_LEVELS = ("year", "month", "day")

# How many enumeration levels the settings dialog offers to move.  Records go
# deeper only rarely, and any level past these keeps the convention's own code.
EDITABLE_ENUM_LEVELS = 3

# The ways a screen may name an enumeration level: by position ("e1", 1), or
# by the words the old three-level model used.  Position is what is stored.
_LEGACY_ENUM_KEYS = {"vol": 0, "issue": 1, "part": 2}

_ORDINALS = ("1st", "2nd", "3rd", "4th", "5th", "6th")


def enum_level_fields(count: int = EDITABLE_ENUM_LEVELS) -> List[Dict[str, str]]:
    """
    The enumeration rows a settings dialog renders, as {key, label}.

    The key is what the API reads back ("e1" is the first level), so the screen
    and resolve_convention name positions the same way.
    """
    return [{"key": f"e{i + 1}",
             "label": f"{_ORDINALS[i]} enumeration",
             # What the field produces when left blank, which is what a
             # placeholder is for. The suggestion sits in the help text beside
             # the grid instead: a placeholder reading "v." promised a caption
             # the tool would not write.
             "default_caption": NO_CAPTION,
             "suggestion": suggested_enum_caption(i)}
            for i in range(count)]


def enum_index(key) -> Optional[int]:
    """The enumeration level a caller's key names, or None if it names none."""
    if isinstance(key, bool):
        return None
    if isinstance(key, int):
        return key if key >= 0 else None
    if isinstance(key, str):
        key = key.strip().lower()
        if key in _LEGACY_ENUM_KEYS:
            return _LEGACY_ENUM_KEYS[key]
        if re.fullmatch(r"e?\d+", key):
            index = int(key.lstrip("e"))
            if key.startswith("e"):        # "e1" is the first level
                index -= 1
            return index if index >= 0 else None
    return None


def enum_subfield(spec_or_map, index: int) -> Optional[str]:
    """The subfield code for enumeration level `index`, or None if too deep."""
    smap = spec_or_map.get("subfields", spec_or_map)
    codes = smap.get("enum", ())
    return codes[index] if index < len(codes) else None

# 853 carries enumeration captions in $a-$h and chronology captions in $i-$m.
# Everything a convention must not touch -- $8 (linking), $u (units per level),
# $v (numbering continuity), $w (frequency), $x/$y/$z -- falls outside a-m, so
# one allowlist covers the whole rule.
_ALLOWED_SUBFIELDS = frozenset("abcdefghijklm")


def convention_presets() -> Dict[str, Dict[str, Any]]:
    """
    The named presets, in the shape the UI populates its fields from.

    Exposed so the template renders from this single source of truth instead of
    duplicating the maps in JavaScript.
    """
    return {
        name: {
            "subfields": dict(_SUBFIELD_MAPS[name]),
            "indicators": list(_INDICATORS[name]),
            "chron_as_text": name == CONVENTION_HOUSE,
        }
        for name in (CONVENTION_STANDARD, CONVENTION_HOUSE)
    }


def resolve_convention(
    name: str = CONVENTION_STANDARD,
    subfields: Optional[Dict[str, str]] = None,
    indicators=None,
    chron_as_text: Optional[bool] = None,
) -> tuple:
    """
    Merge user overrides onto a named preset.

    Returns (spec, rejections) where spec is
    {"subfields": {...}, "indicators": (i1, i2), "chron_as_text": bool}.

    Anything invalid falls back to the preset value and is described in
    `rejections`; a bad subfield code would otherwise corrupt every record it
    touched, silently and identically.
    """
    name = (name or CONVENTION_STANDARD).strip().lower()
    if name not in _SUBFIELD_MAPS:
        name = CONVENTION_STANDARD

    smap = dict(_SUBFIELD_MAPS[name])
    rejections: List[str] = []

    def _in_use(exclude: str) -> set:
        """Every code the map currently spends, ignoring one key."""
        used = set()
        for key, val in smap.items():
            if key == exclude:
                continue
            used.update(val if isinstance(val, tuple) else [val])
        return used

    # A screen written against the old three-level model sends "vol"/"issue"/
    # "part" at the top level; those name enumeration positions now, so fold
    # them into the enumeration patch rather than rejecting them.
    incoming: Dict[str, Any] = {}
    enum_patch: Dict[Any, Any] = {}
    for level, code in (subfields or {}).items():
        if level in smap:
            incoming[level] = code
        elif enum_index(level) is not None:
            enum_patch[level] = code
        else:
            rejections.append(f"Unknown level '{level}' ignored.")
    if enum_patch:
        given = incoming.get("enum")
        if isinstance(given, dict):
            enum_patch.update(given)
        elif given is not None:
            rejections.append(
                "Enumeration was given both as a sequence and by level; "
                "the sequence was used."
            )
            enum_patch = {}
        if enum_patch:
            incoming["enum"] = enum_patch

    # Enumeration is settled first so a chronology override is checked against
    # the codes enumeration ends up with, not the ones it started with.
    for level in sorted(incoming, key=lambda k: k != "enum"):
        code = incoming[level]

        # Enumeration takes a sequence: one code per level, in order.  A screen
        # that only shows the first few levels can send {0: "d"} instead and
        # patch those positions, leaving the convention's depth alone.
        if level == "enum":
            if isinstance(code, dict):
                codes = list(smap["enum"])
                unknown = []
                patched: set = set()
                for key, value in code.items():
                    index = enum_index(key)
                    if index is None or index >= len(codes):
                        unknown.append(str(key))
                        continue
                    codes[index] = str(value or "").strip().lower()
                    patched.add(index)
                if unknown:
                    rejections.append(
                        f"No enumeration level {', '.join(unknown)} in this "
                        f"convention - it has room for {len(smap['enum'])}."
                    )
                # A screen editing the first few levels does not see the ones
                # below, so it cannot know that moving level 1 to $c collides
                # with the level that already held $c.  The levels the
                # cataloguer set win; an untouched level holding a code they
                # claimed drops out, and the depth that costs is reported.
                taken = {codes[i] for i in patched}
                kept = [c for i, c in enumerate(codes)
                        if i in patched or c not in taken]
                if len(kept) != len(codes):
                    rejections.append(
                        f"Enumeration now has room for {len(kept)} levels, not "
                        f"{len(codes)}: a level you did not set was using a "
                        f"subfield you moved another level to."
                    )
                codes = kept
            else:
                codes = [str(c or "").strip().lower()
                         for c in (code if isinstance(code, (list, tuple)) else [code])]
            bad = [c for c in codes if len(c) != 1 or c not in _ALLOWED_SUBFIELDS]
            if bad:
                rejections.append(
                    f"{', '.join(repr(c) for c in bad)} cannot carry an "
                    f"enumeration caption (853 captions live in $a-$m) - kept "
                    f"{''.join('$' + c for c in smap['enum'])}."
                )
                continue
            repeated = sorted({c for c in codes if codes.count(c) > 1})
            if repeated:
                rejections.append(
                    f"{', '.join('$' + c for c in repeated)} would carry two "
                    f"enumeration levels at once - kept "
                    f"{''.join('$' + c for c in smap['enum'])}."
                )
                continue
            clash = sorted(set(codes) & _in_use("enum"))
            if clash:
                rejections.append(
                    f"{', '.join('$' + c for c in clash)} is already used by "
                    f"chronology, so enumeration kept "
                    f"{''.join('$' + c for c in smap['enum'])}."
                )
                continue
            smap["enum"] = tuple(codes)
            continue

        code = (str(code or "")).strip().lower()
        if code == smap[level]:
            continue
        if len(code) != 1 or code not in _ALLOWED_SUBFIELDS:
            rejections.append(
                f"'{code}' is not a usable caption subfield for {level} "
                f"(853 captions live in $a-$m) - kept ${smap[level]}."
            )
            continue
        if code in _in_use(level):
            owner = "enumeration" if code in smap.get("enum", ()) else next(
                (l for l, c in smap.items()
                 if not isinstance(c, tuple) and c == code and l != level), "another level")
            rejections.append(
                f"${code} is already used by {owner}, so {level} kept "
                f"${smap[level]} - two levels cannot share a subfield."
            )
            continue
        smap[level] = code

    # Each indicator is checked on its own, so a bad first indicator does not
    # cost the cataloguer a good second one. Anything outside 0-3 used to be
    # written as typed: "4" or "9" went into every 853, and a cleared box
    # wrote a blank, with nothing on screen or in the file to say so.
    ind = _INDICATORS[name]
    if indicators is not None:
        try:
            given = list(indicators)[:2]
        except TypeError:
            given = None
            rejections.append(
                f"853 indicators {indicators!r} unreadable - kept "
                f"{ind[0]} and {ind[1]}.")
        if given is not None:
            kept = list(ind)
            for pos, (label, value) in enumerate(zip(("first", "second"), given)):
                value = "" if value is None else str(value).strip()
                if len(value) == 1 and value in INDICATOR_VALUES:
                    kept[pos] = value
                elif not value:
                    rejections.append(
                        f"The 853 {label} indicator was left blank - kept "
                        f"{ind[pos]}. MARC 21 defines 0, 1, 2 and 3 for it.")
                else:
                    rejections.append(
                        f"\"{value}\" is not an 853 {label} indicator MARC 21 "
                        f"defines (0, 1, 2 or 3) - kept {ind[pos]}.")
            ind = tuple(kept)

    text = (name == CONVENTION_HOUSE) if chron_as_text is None else bool(chron_as_text)

    return {"subfields": smap, "indicators": ind, "chron_as_text": text}, rejections


# Reverse of MARC_CHRON_CODES for writing chronology as text in HOUSE mode.
_CODE_TO_TEXT: Dict[str, str] = {
    "01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr", "05": "May",
    "06": "Jun", "07": "Jul", "08": "Aug", "09": "Sep", "10": "Oct",
    "11": "Nov", "12": "Dec",
    "21": "Spring", "22": "Summer", "23": "Fall", "24": "Winter",
}


def _chron_text(value: Optional[str]) -> Optional[str]:
    """Render a chronology value as text ('03' -> 'Mar'), preserving ranges."""
    if value is None:
        return None
    out = []
    for tok in re.split(r"([-/])", value):
        out.append(_CODE_TO_TEXT.get(tok, tok) if tok not in "-/" else tok)
    return "".join(out)


def caption_slot(caption: str) -> Optional[str]:
    """
    What kind of level an 853 caption labels: "year", "month", or "enum".

    Enumeration captions are not named further.  "v.", "no." and "pt." are
    words a cataloguer chose; which level each one *is* comes from the subfield
    it sits in, not from the word.
    """
    c = (caption or "").strip().lower()
    if not c:
        return None
    if "year" in c:
        return "year"
    if "season" in c or "month" in c or "chron" in c:
        return "month"
    # Before the enumeration fallback: "(day)" is short and wordlike, so
    # without this it reads as an enumeration caption and $k comes back as a
    # numbering level.
    if "day" in c:
        return "day"
    # An asterisk is MARC's "this level has no caption", in either of the two
    # written forms. Without this the tool could not read back the 853 it writes
    # itself, and a record it had already converted would stop conforming.
    if c in ("*", "(*)", "[*]"):
        return "enum"
    # Anything else short enough to be a caption is an enumeration caption.
    # MARC 21 does not restrict the words, and cataloguers use more than three
    # of them -- "Bd.", "Heft", "Report no.", "n.s. v."
    if re.fullmatch(r"\(?\[?[a-z][a-z0-9 .,/'\]-]{0,23}\)?", c):
        return "enum"
    return None


def _existing_link(existing_853) -> Optional[str]:
    """The $8 linking number carried by an existing 853, if it has one."""
    if existing_853 is None:
        return None
    for sf in getattr(existing_853, "subfields", []):
        if getattr(sf, "code", None) == "8" and getattr(sf, "value", None):
            return sf.value.strip()
    return None


def read_853_slots(existing_853) -> Dict[str, Any]:
    """
    Read an existing 853 into the same shape a convention uses.

    Returns {"enum": (codes in subfield order), "year": code, "month": code},
    omitting what the field does not declare.  Enumeration codes keep the order
    they appear in, because that order *is* the hierarchy.

    Accepts a pymarc Field or any object exposing .subfields with .code/.value.
    Returns {} when nothing recognisable is declared.
    """
    slots: Dict[str, Any] = {}
    enum_codes: List[str] = []
    if existing_853 is None:
        return slots
    for sf in getattr(existing_853, "subfields", []):
        code = getattr(sf, "code", None)
        value = getattr(sf, "value", None)
        if code not in _ALLOWED_SUBFIELDS:
            continue
        level = caption_slot(value)
        if level == "enum":
            if code not in enum_codes:
                enum_codes.append(code)
        elif level and level not in slots:
            slots[level] = code
    if enum_codes:
        slots["enum"] = tuple(enum_codes)
    return slots


def read_853_captions(existing_853) -> List[str]:
    """The enumeration caption words an existing 853 declares, in order."""
    captions: List[str] = []
    for sf in getattr(existing_853, "subfields", []):
        if getattr(sf, "code", None) not in _ALLOWED_SUBFIELDS:
            continue
        value = getattr(sf, "value", None)
        if caption_slot(value) == "enum":
            captions.append(value)
    return captions


def _uses_season_chronology(parse_result: ParseResult) -> bool:
    """True if any parsed month value is a MARC season code (21-24)."""
    for r in parse_result.ranges:
        for ec in (r.start, r.end):
            if ec is None or not ec.month:
                continue
            for token in ec.month.replace("/", "-").split("-"):
                if token.strip() in SEASON_CODES:
                    return True
    return False


# ---------------------------------------------------------------------------
# Data class for the generated field data (serialisable without pymarc)
# ---------------------------------------------------------------------------

@dataclass
class SubfieldData:
    code: str
    value: str


@dataclass
class FieldData:
    """Serialisable representation of a MARC field."""
    tag: str
    indicator1: str
    indicator2: str
    subfields: List[SubfieldData] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tag": self.tag,
            "indicator1": self.indicator1,
            "indicator2": self.indicator2,
            "subfields": [{"code": sf.code, "value": sf.value}
                          for sf in self.subfields],
        }

    def display(self) -> str:
        """Human-readable string like '853 ## $8 1 $a v. $b no. ...'"""
        ind = f"{self.indicator1}{self.indicator2}".replace(" ", "#")
        sf_parts = " ".join(
            f"${sf.code} {sf.value}" for sf in self.subfields
        )
        return f"{self.tag} {ind} {sf_parts}"

    def to_pymarc(self) -> "Field":
        """Convert to a pymarc Field object (requires pymarc installed)."""
        if not HAS_PYMARC:
            raise RuntimeError("pymarc is not installed.")
        subfield_list = []
        for sf in self.subfields:
            subfield_list.append(Subfield(code=sf.code, value=sf.value))
        return Field(
            tag=self.tag,
            indicators=[self.indicator1, self.indicator2],
            subfields=subfield_list,
        )


@dataclass
class ConversionResult:
    """Output of convert_holdings()."""
    field_853: Optional[FieldData]        # None when conforming to an existing 853
    fields_863: List[FieldData]
    linking_number: int                   # the $8 linking number used
    warnings: List[str] = field(default_factory=list)
    conformed: bool = False               # reused the record's existing 853
    needs_review: bool = False            # values found but deliberately not converted
    # Fields were produced, and something about them should be looked at before
    # they are loaded.  Distinct from needs_review, which writes nothing at all:
    # here the record exists and may well be right, but the tool cannot vouch
    # for it, and silence would be read as vouching.
    flagged: bool = False

    def all_fields(self) -> List[FieldData]:
        return ([self.field_853] if self.field_853 else []) + self.fields_863

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field_853": self.field_853.to_dict() if self.field_853 else None,
            "fields_863": [f.to_dict() for f in self.fields_863],
            "linking_number": self.linking_number,
            "warnings": self.warnings,
            "conformed": self.conformed,
            "needs_review": self.needs_review,
            "flagged": self.flagged,
        }


# ---------------------------------------------------------------------------
# Caption builder
# ---------------------------------------------------------------------------

def _enum_caption_overrides(captions: Optional[Dict[str, Any]]) -> Dict[int, str]:
    """
    Cataloguer overrides for enumeration captions, keyed by level index.

    Accepts "e1"/"e2"/... and plain integers, and still accepts the old
    "vol"/"issue"/"part" keys as levels 1, 2 and 3 so a screen that has not
    been updated keeps working.
    """
    out: Dict[int, str] = {}
    for key, value in (captions or {}).items():
        if not value:
            continue
        index = enum_index(key)
        if index is not None:
            out[index] = value
    return out


def _build_853(
    parse_result: ParseResult,
    linking_number: int = 1,
    captions: Optional[Dict[str, str]] = None,
    frequency: str = "",
    numbering_continuity: str = "",
    units_per_higher: str = "",
    convention: str = CONVENTION_STANDARD,
    convention_spec: Optional[Dict[str, Any]] = None,
    warnings: Optional[List[str]] = None,
) -> FieldData:
    """
    Build an 853 (Captions and Pattern) field from a ParseResult.

    Enumeration captions are written in the order the statements use them, one
    subfield per level, with the word each statement actually used.  A serial
    numbered only by issue gets "$a no." -- correct, and previously impossible.

    Parameters
    ----------
    parse_result      : output of parse_866()
    linking_number    : integer used for $8 (matches 863 $8 prefix)
    captions          : overrides; "e1"/"e2"/... or "year"/"month"
    frequency         : 853 $w code (see FREQUENCY_CODES)
    numbering_continuity : 853 $v -- 'r' (renumbers per level) or 'c' (continuous)
    """
    caps = {**DEFAULT_CAPTIONS, **{k: v for k, v in (captions or {}).items()
                                   if k in DEFAULT_CAPTIONS}}
    enum_caps = _enum_caption_overrides(captions)
    levels = parse_result.caption_union()
    if convention_spec is None:
        convention_spec, _ = resolve_convention(convention)
    smap = convention_spec["subfields"]
    ind1, ind2 = convention_spec["indicators"]

    sfs: List[SubfieldData] = []
    sfs.append(SubfieldData("8", str(linking_number)))

    planned: List[tuple] = []

    declared = levels.get("enum_captions", [])
    for i, caption in enumerate(declared):
        code = enum_subfield(convention_spec, i)
        if code is None:
            if warnings is not None:
                note = (f"This convention has room for {len(smap['enum'])} "
                        f"enumeration levels and the holdings state "
                        f"{len(declared)}; level {i + 1} was not recorded.")
                if note not in warnings:
                    warnings.append(note)
            continue
        # A caption the cataloguer supplied wins, then one the statement wrote,
        # and only then NO_CAPTION -- which is a statement that there was none,
        # not a guess at what it would have been.
        planned.append((code, enum_caps.get(i) or caption or NO_CAPTION))

    if levels.get("year"):
        planned.append((smap["year"], caps["year"]))
    if levels.get("month"):
        cap = caps["season"] if _uses_season_chronology(parse_result) else caps["month"]
        planned.append((smap["month"], cap))
    # Only when the convention can actually place it: an 853 declaring a
    # caption its 863s never fill describes a level the record does not have.
    # _build_863_for_range names the day in that case; the 853 stays quiet.
    if levels.get("day") and smap.get("day"):
        planned.append((smap["day"], caps["day"]))

    # Sorted by subfield so the field reads correctly under either convention
    # (HOUSE puts the year first, in $a).
    # $v (numbering continuity) belongs to the level that renumbers, which is
    # the last enumeration level -- but only where there is a level above it to
    # renumber against.
    #
    # MARC 21 853-855: "$v ... May be used with each level of enumeration
    # except the first level (subfield $a or $g)", and the code it carries says
    # the numbering "restarts at the completion of the unit" -- the unit being
    # the next higher level.  A serial numbered by volume alone has no higher
    # unit, so there is nothing for its numbering to restart against and the
    # question $v answers does not arise.  Every example in the standard puts
    # $v after $b, $c or $d; none puts it after $a.
    #
    # Until 0.12.3 it went after whichever enumeration level came last, so a
    # single-level statement put it on the first -- 18 of the 117 corpus
    # statements, every one of them one level deep.
    #
    # $u (bibliographic units per next higher level) is still never guessed --
    # an 866 rarely states how many issues a volume holds, and inventing a
    # number would claim a pattern nobody verified. It is written only when the
    # cataloguer declares it, and then on the *second* enumeration level: $u on
    # $b says how many issues make a volume, which is what a single declared
    # number means. On a three-level serial the last level is a different
    # question -- parts per issue rather than issues per volume -- and is left
    # alone rather than given the same number. One statement of the 112 the
    # corpus produces an 853 for goes that deep; 89 are exactly two levels.
    #
    # Order within the level follows the standard's examples, which read
    # "$bno.$u12$vr": the caption, then $u, then $v.
    last_enum_code = planned[len(declared) - 1][0] if declared else None
    if len(declared) < 2:
        last_enum_code = None

    # "Not used with subfield $a or $g", so the guard is on the code and not
    # only on the count of levels.
    second_enum_code = planned[1][0] if len(declared) >= 2 else None
    if second_enum_code in ("a", "g"):
        second_enum_code = None

    # Three levels ask two questions and one number answers neither reliably.
    #
    # "$a ser. $b v. $c no." wants issues per volume *and* volumes per series,
    # and the standard writes a $u on each: "$bno.$u12$cpt.$u3". The box that
    # collects this asks for one number and calls it "issues per volume", so
    # putting it on $b -- which is what a rule reading "the second enumeration
    # level" does -- writes volumes per series under a label saying issues per
    # volume. The label and the placement disagreed, and the cataloguer reading
    # the label is the one who is right.
    #
    # Refused rather than resolved either way. The one statement that reaches
    # three levels does so because of a house convention recording an
    # enumeration restart rather than a caption the publication prints, which
    # is a poor thing to fix a rule to; and the real 1004-statement file this
    # was measured against has no three-level statement at all. So the cost of
    # refusing is one corpus statement, and the cost of guessing is a wrong
    # claim about how a serial is published, wherever the shape does occur.
    if len(declared) >= 3 and units_per_higher:
        if warnings is not None:
            note = (f"This statement has {len(declared)} levels of enumeration, "
                    "so one number cannot say how many of each make the level "
                    "above. $u was not written. MARC records it per level "
                    "-- \"$b no. $u 12 $c pt. $u 3\" -- which this tool does "
                    "not yet collect.")
            if note not in warnings:
                warnings.append(note)
        units_per_higher = ""

    # Sanitised here and not only at the request boundary. This function is
    # what writes MARC, and it should not write an invalid subfield whoever
    # called it -- a wrong $u makes a claim about the publication, where no $u
    # simply makes none.
    units_per_higher = resolve_units_per_higher(units_per_higher)

    for code, value in sorted(planned, key=lambda p: p[0]):
        sfs.append(SubfieldData(code, value))
        if units_per_higher and code == second_enum_code:
            sfs.append(SubfieldData("u", units_per_higher))
        if numbering_continuity and code == last_enum_code:
            sfs.append(SubfieldData("v", numbering_continuity))

    if frequency:
        sfs.append(SubfieldData("w", frequency))

    # First indicator 3, "Unknown", is the honest value while an 853 has no
    # $u: "Compression of the contents of subfields $a-$m in field 863 or 864
    # requires information in subfields $u and $v", and $v alone cannot
    # support a claim that the holdings can be compressed or expanded. A
    # numeric $u supplies what was missing, so an 853 carrying one is written
    # as 2, "Can compress or expand" -- the cataloguer's call, 22 September
    # 2026. Decided per field: $u only goes on a two-level 853, so one run
    # writes both.
    #
    # Only a numeric $u. "var" and "und" say the count varies or is not
    # known, which is the absence of what compression needs. And only over a
    # 3: a 0 or 1 in the box is somebody's deliberate statement, and the house
    # preset is 2 already.
    if (ind1 == "3" and units_per_higher.isdigit()
            and any(sf.code == "u" for sf in sfs)):
        ind1 = "2"

    return FieldData(
        tag="853",
        indicator1=ind1,
        indicator2=ind2,
        subfields=sfs,
    )


# ---------------------------------------------------------------------------
# 863 builder helpers
# ---------------------------------------------------------------------------

# The two level hierarchies an 863 carries, each most significant first.
# Enumeration and chronology are independent: a volume ranging says nothing
# about whether the year does.
_CHRON_LEVELS = ("year", "month", "day")

# Cataloguer-facing names, with their article, for warnings about a level that
# could not be written.
_LEVEL_WORDS = {
    "year":  ("a", "year"),
    "month": ("a", "month or season"),
    "day":   ("a", "day"),
}


def _enum_label(caption: Optional[str], index: int) -> tuple:
    """
    Name an enumeration level for a warning, by its caption where there is one.

    The caption is quoted and keeps its period, because it is a word the
    cataloguer wrote and one of the commonest is "no.".  Bare and stripped, it
    ran straight into the sentence around it -- "with no no level at the end",
    where the first "no" is a negation and the second is a caption.
    """
    word = (caption or "").strip()
    if not word or word == NO_CAPTION:
        # Naming it by the caption it might have had would be the same guess
        # the 853 no longer makes. Position is what is actually known.
        ordinal = _ORDINALS[index] if index < len(_ORDINALS) else f"{index + 1}th"
        return ("the", f"{ordinal} enumeration level, which has no caption")
    article = "an" if word[:1].lower() in "aeiou" else "a"
    if word.lower().startswith("level"):
        return (article, word)      # "level 4" already names itself
    return (article, f"'{word}' level")


# The codeability predicate moved to parser.py in 0.12.0, because the 853 has
# to answer the same question before the converter ever runs: a level whose
# only value is prose is not a level the serial has.  Imported rather than
# restated -- two copies of one rule drift.


def _note_unplaceable(warnings: Optional[List[str]], which: str,
                      label: tuple, value: str) -> None:
    """
    Record that one boundary states a level the other does not.

    A compressed 863 pairs its subfields positionally, so a value written for
    one end is read as covering both.  With nothing at the other end there is no
    range to express and no notation for half of one, so the level is left out
    -- and named here, which is what keeps it accounted for rather than lost.
    """
    if warnings is None:
        return
    article, word = label
    other = "end" if which == "start" else "start"
    note = (
        f"Only the {which} of this range gives {article} {word} ({value}); a "
        f"compressed 863 records the first and last part held, and there is "
        f"nothing at the {other} to pair it with, so it was left out."
    )
    if note not in warnings:
        warnings.append(note)


# How deep a serial is plausibly numbered.  MARC 21 gives enumeration $a-$f, so
# six levels are *allowed*; two or three are what serials actually use --
# volume, issue, and occasionally part.  The 112-statement corpus reaches three
# exactly once and never four.
PLAUSIBLE_ENUM_DEPTH = 3


def _check_enumeration_depth(levels: Dict[str, Any],
                             warnings: Optional[List[str]] = None) -> bool:
    """
    Flag a record claiming more enumeration levels than a serial plausibly has.

    The realistic way to reach four or more is a discontinuous list read as a
    hierarchy: "8,13,15,17,19,20-(1982-1994)" is six separate holdings, and
    filing them as $a 8 $b 13 $c 15 ... states that the library holds one
    issue, numbered six levels deep, which is not a loss but an invention.

    Nothing here can tell the two readings apart -- a genuinely deep serial and
    a list look identical once the values are in hand -- so this does not
    refuse, and does not drop anything. It says what was assumed, which is the
    difference between an error a cataloguer can catch and one they cannot.

    Returns True when the record was flagged.
    """
    captions = levels.get("enum_captions", [])
    if len(captions) <= PLAUSIBLE_ENUM_DEPTH:
        return False
    if warnings is not None:
        named = ", ".join(
            f"{cap or NO_CAPTION}" for i, cap in enumerate(captions))
        note = (
            f"{len(captions)} enumeration levels are claimed here ({named}). "
            f"Serials are numbered two or three levels deep; more than that "
            f"usually means a list of separate holdings, and separate holdings "
            f"cannot share one 863. Check this record before loading it."
        )
        if note not in warnings:
            warnings.append(note)
    return True


def _note_no_subfield(warnings: Optional[List[str]], level: str,
                      value: str) -> None:
    """Record a chronology level this convention has nowhere to put."""
    if warnings is None:
        return
    article, word = _LEVEL_WORDS.get(level, ("a", level))
    note = (
        f"This convention has no subfield for {article} {word}, so the "
        f"{word} ({value}) was left out. MARC 21 puts it in 863 $k; the "
        f"standard convention writes it."
    )
    if note not in warnings:
        warnings.append(note)


def _note_caption_conflict(warnings: Optional[List[str]], stated: str,
                           value: str, declared: str) -> None:
    """
    Record a value whose level this record's 853 does not describe.

    One 853 is the caption pattern for every 863 linked to it, so a statement
    numbering by one hierarchy cannot share it with a statement numbering by
    another.  Writing the value anyway would file "v. 6" under "ser.", which
    reads as series 6 and is wrong in a way nothing downstream could detect.
    """
    if warnings is None:
        return
    note = (
        f"'{stated}{value}' was left out: this record's 853 calls that level "
        f"'{declared}', and one 853 has to describe every 863 under it. Split "
        f"the statements that number differently onto their own records."
    )
    if note not in warnings:
        warnings.append(note)


def _note_level_disagreement(warnings: Optional[List[str]], opens: str,
                             closes: str, value: str) -> None:
    """
    Record a closing value whose caption contradicts the level it would land in.

    A compressed 863 pairs the two ends level by level, so the level a value
    closes has to be the level the range opened.  "v. 12 no. 1-no. 6" states one
    level at the end and two at the start; HoldingsRange.align_boundaries()
    settles that one from the captions.  What reaches here is what the captions
    cannot settle -- a range that opens "v." and closes "pt." pairs nothing with
    nothing -- and a value whose level is unknown is not a value to place by
    position.  That is how "$a 12-6" was written: volume 12 to volume 6, from a
    statement that said no such thing.
    """
    if warnings is None:
        return
    note = (
        f"'{closes}{value}' was left out: this range opens at a '{opens}' level "
        f"and closes at a '{closes}' level, so which level '{value}' closes "
        f"cannot be told from the statement. A compressed 863 pairs the two "
        f"ends level by level, and there is no pairing for this one."
    )
    if note not in warnings:
        warnings.append(note)


def _unpairable_end_levels(hr: HoldingsRange,
                           warnings: Optional[List[str]] = None) -> set:
    """
    The end-boundary levels whose caption contradicts the start's at the same
    position, named as they are found.  Their values are not written.
    """
    blocked: set = set()
    if hr.end is None:
        return blocked
    for i, e_lvl in enumerate(hr.end.enum):
        s_lvl = hr.start.level(i)
        if not (e_lvl.value and e_lvl.caption and s_lvl and s_lvl.caption):
            continue
        if e_lvl.caption != s_lvl.caption:
            _note_level_disagreement(warnings, s_lvl.caption,
                                     e_lvl.caption, e_lvl.value)
            blocked.add(i)
    return blocked


def _note_unpairable_under_range(warnings: Optional[List[str]], label: tuple,
                                 value: str, above: str) -> None:
    """
    Record a lone value sitting under a level that is itself written as a range.

    "v. 40-45 no. 4" states one boundary, not two, so there is no other end to
    disagree with -- and the ambiguity is there all the same.  A compressed 863
    pairs its subfields position by position, so "$a 40-45 $b 4" describes issue
    4 of every volume from 40 to 45 just as well as it describes a run ending at
    v. 45 no. 4.  _hierarchy_values() has said so in its own docstring since
    0.6.2, about the two-boundary form; the single-boundary form reached the
    "nothing to disagree with" branch and wrote the value anyway.
    """
    if warnings is None:
        return
    _, word = label
    note = (
        f"'{value}' was left out. The {word} sits under a level written as the "
        f"range '{above}', and a compressed 863 pairs its subfields position by "
        f"position: '{above}' beside a single '{value}' reads as {value} of each "
        f"of them just as well as it reads as one run ending there, and nothing "
        f"in the notation tells the two apart. Writing both ends of the run out "
        f"in full is what records it."
    )
    if note not in warnings:
        warnings.append(note)


# The subfields Form of holdings is decided from: a range in any enumeration or
# chronology subfield makes the field compressed.  Named here rather than spelled
# as a literal at the point of use, because the same two groups are what "level"
# means everywhere in this module.
_ENUM_SUBFIELDS = "abcdefgh"
_CHRON_SUBFIELDS = "ijklm"


def _note_inner_range(warnings: Optional[List[str]], label: tuple,
                      start: str, end: str, written: str,
                      flags: Optional[set] = None, paired: bool = False) -> None:
    """
    Say that a range inside a boundary was read as "through", and how to undo it.

    Flagged, because the one reading the notation cannot settle is the
    cataloguer's: "nos. 1-3" is issues 1 through 3 by Z39.71, and the run
    starts at no. 1 -- unless it is one combined issue that should have been
    written "1/3", in which case the start is "1/3" and the 863 should say so.
    """
    if flags is not None:
        flags.add("inner_range")
    if warnings is None:
        return
    _, word = label
    if paired:
        note = (
            f"The {word} reads '{start}': one end of the range is a range of "
            f"its own. A compressed 863 records only the first and last part "
            f"held, so {written} was written. If that end is one combined part "
            f"rather than a range, edit the 866 to write it with a slash "
            f"instead of a hyphen and it will be kept whole."
        )
        if note not in warnings:
            warnings.append(note)
        return
    ranged = [v for v in (start, end) if "-" in v.rstrip("-")] or [start]
    both = len(ranged) > 1
    note = (
        f"{' and '.join(repr(v) for v in ranged)} ({word}) "
        f"{'are ranges' if both else 'is a range'} inside one end of the "
        f"holdings. A compressed 863 records only the first and last part "
        f"held, so {written} was written. If {'either' if both else 'it'} is "
        f"one combined part rather than a range, edit the 866 to write it "
        f"with a slash instead of a hyphen and it will be kept whole."
    )
    if note not in warnings:
        warnings.append(note)


def _note_uncodeable(warnings: Optional[List[str]], label: tuple,
                     value: str, flags: Optional[set] = None) -> None:
    """
    Record chronology wording the coded subfield cannot hold.

    This flags the record as well as naming the value.  "Late Summer" is the
    case that made it matter: it may be the Summer issue, or the serial may also
    have an Early Summer and coding both 22 would merge two different issues
    into one.  Nothing here can tell -- a cataloguer has to look at the piece --
    so the record is put where they will see it rather than left to a warning
    that only shows when the row is opened.
    """
    if flags is not None:
        flags.add("uncodeable")
    if warnings is None:
        return
    _, word = label
    note = (
        f"'{value}' is not something a {word} subfield can hold — it takes "
        f"MARC codes, not wording — so it was left out. Record it by hand if "
        f"it matters."
    )
    if note not in warnings:
        warnings.append(note)


def _hierarchy_values(
    hr: HoldingsRange,
    level_keys,
    get,
    label_for,
    warnings: Optional[List[str]] = None,
    flags: Optional[set] = None,
) -> Dict[Any, str]:
    """
    The 863 value for every level of one hierarchy, as {key: value}.

    `level_keys` runs most significant first; `get(boundary, key)` reads one
    level off a boundary, and `label_for(key)` names it for a warning.  Two
    hierarchies use this: enumeration, keyed by position, and chronology, keyed
    by "year"/"month".  They are independent -- a volume ranging says nothing
    about whether the year does.

    A compressed 863 records the first part held and the last part held, and a
    reader pairs the subfields positionally: the first value of every subfield
    describes the first part, the second value the last part.  Everything below
    follows from that one fact, and from a single question asked per level --
    *does anything above this level range?*

    No second boundary at all
        A single unit ("v. 58 (Sep 2003)") has nothing to disagree with, so
        every value stands.  An open-ended range writes the trailing hyphen.

    Both ends known, different
        The obvious "41-43".

    Both ends known, equal
        "1-1" when a more significant level ranges, because "$a 41-43 $b 1"
        cannot be read back as v.41:no.1 - v.43:no.1 -- it describes issue 1 of
        each of volumes 41 to 43 just as well.  Plain "1" when nothing above
        ranges: "v. 43 no. 6 - v. 43 no. 7" loses nothing as "$a 43 $b 6-7".  A
        value already containing a range is left alone, since "no. 3-4 - no. 3-4"
        would become the unreadable "3-4-3-4".

    One end only, and the other boundary states nothing at all in this
    hierarchy
        One group is describing the whole range and the parser has hung it on
        whichever boundary carried it.  "v.1:no.1-v.2:no.4(1990-1991)" puts both
        years on the end; "(Jan 1956 - Jan 1957)" puts an already-paired
        "01-01" there.  The value covers both ends and is used as it stands.

    One end only, and nothing above it ranges
        Nothing to pair with, so the value is unambiguous:
        "1983: 5 (7-30 [Jan 28-Dec 29])" states its year once for a run whose
        months range within it.

    One end only, and something above it ranges
        Then the pairing matters and there is no notation for half of it.  The
        "December" in "v. 1 no. 1 (1995)-v. 12 no. 4 (December 2006)" belongs to
        the end alone; writing it asserts the holdings *begin* in December.  The
        "Spring" in "v. 118 no. 1 (Spring 2012)-v. 122 no. 1 (2016)" is the same
        thing pointing the other way.  The level is left out, and a warning names
        the value -- accounted for rather than silently discarded.
    """
    s, e = hr.start, hr.end
    oe = hr.open_ended

    # Whether each boundary was written out at all at this hierarchy.  A value
    # found on one boundary while the other is silent throughout came from a
    # group covering the whole range, not from one end of it -- which is what
    # separates the "01-01" of "(Jan 1956 - Jan 1957)", already a pair, from the
    # "1-2" of "v. 1 (1956) - v. 51 nos. 1-2 (2006)", which is a range inside
    # the end boundary and says nothing about where the run starts.
    speaks = {
        "start": any(get(s, key) is not None for key in level_keys),
        "end": e is not None and any(
            get(e, key) is not None for key in level_keys
        ),
    }

    out: Dict[str, str] = {}
    # The value of the nearest level above that was written as a range, or "".
    # A bare flag would do for the branching; the note quotes it.
    ranged_above = ""

    for key in level_keys:
        s_val = get(s, key)
        e_val = get(e, key) if e is not None else None
        value: Optional[str] = None

        if e is None:
            # Single unit: no other end to disagree with -- but a level *above*
            # can still be written as a range inside this one boundary, and then
            # the pairing is as ambiguous as it is with two.  A value that is
            # itself a range pairs fine ("$a 40-45 $b 2-5"); a lone one does not.
            if s_val is not None:
                if ranged_above and "-" not in s_val.rstrip("-"):
                    _note_unpairable_under_range(warnings, label_for(key),
                                                 s_val, ranged_above)
                else:
                    value = f"{s_val}-" if oe else s_val
        elif s_val is not None and e_val is not None:
            if s_val != e_val and ("-" in s_val or "-" in e_val):
                # A range inside a boundary: "v. 6 nos. 1-3 - v. 14 nos. 10-12".
                # A compressed 863 holds one pair per subfield -- the first part
                # held and the last -- so the run is no. 1 to no. 12, and
                # "1-3-10-12" was a value no reader can pair. The hyphen means
                # "through" (a combined issue is written with a slash), so the
                # outer ends are the reading; the record says so, in case one
                # was a combined issue written with the wrong mark.
                value = f"{s_val.split('-')[0]}-{e_val.split('-')[-1]}"
                _note_inner_range(warnings, label_for(key), s_val, e_val,
                                  value, flags)
            elif s_val != e_val:
                value = f"{s_val}-{e_val}"
            elif ranged_above and "-" not in s_val:
                value = f"{s_val}-{s_val}"
            else:
                value = s_val
        elif s_val is not None or e_val is not None:
            lone = s_val if s_val is not None else e_val
            which = "start" if s_val is not None else "end"
            other = "end" if which == "start" else "start"
            if speaks[other] and ranged_above:
                _note_unplaceable(warnings, which, label_for(key), lone)
            else:
                value = lone

        if value and not _is_codeable(key, value):
            # "(1998 Buyers Guide)" is a named issue, not a date, and
            # "Late Summer" is not a season MARC has a code for.  Both used to
            # reach $j, which the 853 declares as "(month)" -- and
            # "11/12-Late Summer" put codes and prose in one subfield.  The
            # record cannot carry it, so it is left out and named.
            _note_uncodeable(warnings, label_for(key), value, flags)
            value = None

        if value and value.rstrip("-").count("-") > 1:
            # Still two ranges in one value: one date group carried a range of
            # its own at an end, as "(Mar 1978-Oct-Dec 1986)" does for its last
            # months. No reader can pair "03-10-12"; the outer ends are the run.
            parts = value.rstrip("-").split("-")
            outer = f"{parts[0]}-{parts[-1]}" + ("-" if value.endswith("-") else "")
            _note_inner_range(warnings, label_for(key), value, "", outer, flags,
                              paired=True)
            value = outer

        if value:
            out[key] = value
            # A written value that is itself a range is what makes the levels
            # under it need both of their endpoints. Reading it back off the
            # output covers every branch above at once, including the one where
            # the range arrived pre-compressed from the parser ("1990-1991").
            if "-" in value.rstrip("-"):
                ranged_above = value

    return out


def _build_863_for_range(
    hr: HoldingsRange,
    linking_number: int,
    sequence: int,
    levels: dict,
    smap: Optional[Dict[str, str]] = None,
    chron_as_text: bool = False,
    warnings: Optional[List[str]] = None,
    flags: Optional[set] = None,
    holdings_level: str = DEFAULT_HOLDINGS_LEVEL,
) -> FieldData:
    """
    Build a single 863 field for one HoldingsRange.

    `smap` maps levels to subfield codes -- an ordered "enum" sequence plus the
    chronology codes -- so the 863 lands in the same subfields the governing 853
    declares.  `chron_as_text` writes chronology as
    text ("Mar") instead of MARC codes ("03").  `warnings`, when given, collects
    notes about values the range states that could not be encoded -- see
    _hierarchy_values, which decides what those are.
    """
    smap = smap or _SUBFIELD_MAPS[CONVENTION_STANDARD]

    sfs: List[SubfieldData] = []
    sfs.append(SubfieldData("8", f"{linking_number}.{sequence}"))

    depth = len(levels.get("enum_captions", []))
    captions = levels.get("enum_captions", [])

    planned: List[tuple] = []

    unpairable = _unpairable_end_levels(hr, warnings)

    def _enum_at(ec, i):
        if ec is None or (ec is hr.end and i in unpairable):
            return None
        return ec.value_at(i)

    enum_values = _hierarchy_values(
        hr, range(depth),
        _enum_at,
        lambda i: _enum_label(captions[i] if i < len(captions) else None, i),
        warnings,
        flags,
    )
    stated = hr.enum_captions()
    for i in range(depth):
        code = enum_subfield(smap, i)
        value = enum_values.get(i)
        if not (code and value):
            continue
        # One 853 governs every 863 linked to it, so a level's caption is the
        # same for all of them.  A range that calls this level something else
        # is describing a different hierarchy, and writing its value here would
        # file it under a caption the statement contradicts.
        mine = stated[i] if i < len(stated) else None
        theirs = captions[i] if i < len(captions) else None
        if mine and theirs and mine != theirs:
            _note_caption_conflict(warnings, mine, value, theirs)
            continue
        planned.append((code, value))

    chron_values = _hierarchy_values(
        hr, _CHRON_LEVELS,
        lambda ec, name: getattr(ec, name) if ec else None,
        lambda name: _LEVEL_WORDS[name],
        warnings,
        flags,
    )
    for name in _CHRON_LEVELS:
        if not levels.get(name):
            continue
        value = chron_values.get(name)
        if not value:
            continue
        code = smap.get(name)
        if not code:
            # The convention has no subfield for this level -- the house one
            # has no day. Levelling the value off in silence is the one thing
            # not to do, so it is named instead.
            _note_no_subfield(warnings, name, value)
            continue
        if name == "month" and chron_as_text:
            value = _chron_text(value)
        planned.append((code, value))

    for code, value in sorted(planned, key=lambda p: p[0]):
        sfs.append(SubfieldData(code, value))

    # $w says what the break between this field and the next one is.  Only a
    # statement that shows the break sets it -- "v. 19 nos. 1, 3" says issue 2
    # is not held -- and "g" is the code for that: parts lacking, or a break
    # whose cause is not known.  Two runs that follow straight on set nothing,
    # having no break to indicate.
    if hr.break_after:
        sfs.append(SubfieldData("w", hr.break_after))

    # Indicator 1 is Field encoding level, matching Leader/17, and it comes
    # from the caller's declared holdings level -- see HOLDINGS_LEVELS for why
    # it is declared rather than derived, and D18, which this closes.
    #
    # Indicator 2 is Form of holdings, and it describes *this field*: 0
    # compressed, 1 uncompressed, 2 and 3 the same pair where the display comes
    # from a linked 866.  docs/marc/hd863865.md: "Compressed means that the
    # stated field is expressed in a summarized form containing the enumeration
    # and chronology of more than one part expressed as a range of holdings and
    # comprising multiple holdings items.  Uncompressed means that each holdings
    # item is itemized, and thus recorded separately."
    #
    # So the value follows from whether this field holds a range.  0.6.1 (D18)
    # changed it from 1 to 0 because the fields it looked at were ranges and
    # saying "uncompressed" of "$a 41-43" is false; the same rule read the other
    # way makes 0 false of "$a 8", one volume out of a discontinuous list, which
    # is 45 of the 137 fields the corpus produces.  Every example in the
    # standard agrees: a range takes 0 or 2, a single item 1 or 3.
    ranged = any("-" in sf.value
                 for sf in sfs
                 if sf.code in _ENUM_SUBFIELDS + _CHRON_SUBFIELDS)
    return FieldData(
        tag="863",
        indicator1=holdings_level,          # field encoding level, declared
        indicator2="0" if ranged else "1",  # form of holdings
        subfields=sfs,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# The subfields that carry holdings. An 863 with none of them is a $8 and
# nothing else: not valid MARC, and not holdings.
_VALUE_SUBFIELDS = frozenset("abcdefghijklm")


def _with_values(fields_863: List["FieldData"], warnings: List[str]) -> List["FieldData"]:
    """
    Drop any 863 left with no value in it.

    A run whose every value was refused -- "(Feb, Jun, Aug 1998)" reaches here
    with its whole chronology in the year slot, and the year subfield takes
    codes, not wording -- used to be written anyway, as "863 41 $8 1.1". The
    statement then counted as converted, so "Remove each 866" deleted the only
    place its holdings were. Found by the round trip (0.28.0): 9 statements of
    a real 1,057-statement export.
    """
    kept = [f for f in fields_863
            if any(sf.code in _VALUE_SUBFIELDS for sf in f.subfields)]
    if len(kept) < len(fields_863):
        note = ("Nothing that could be written was left for "
                f"{'one run' if len(fields_863) - len(kept) == 1 else 'some runs'} "
                "of this statement, so no 863 was written for "
                f"{'it' if len(fields_863) - len(kept) == 1 else 'them'}.")
        if note not in warnings:
            warnings.append(note)
    return kept


def _held_empty(linking_number, warnings: List[str]) -> "ConversionResult":
    """Nothing writable at all: held for review, like any statement not read."""
    return ConversionResult(
        field_853=None,
        fields_863=[],
        linking_number=linking_number,
        warnings=warnings,
        needs_review=True,
    )


def convert_holdings(
    parse_result: ParseResult,
    linking_number: int = 1,
    captions: Optional[Dict[str, str]] = None,
    frequency: str = "",
    numbering_continuity: str = "",
    units_per_higher: str = "",
    existing_853=None,
    convention: str = CONVENTION_STANDARD,
    chron_as_text: bool = False,
    convention_spec: Optional[Dict[str, Any]] = None,
    holdings_level: str = DEFAULT_HOLDINGS_LEVEL,
) -> ConversionResult:
    """
    Convert a ParseResult into 853 + 863 MARC field data.

    Parameters
    ----------
    parse_result         : output of holdings_parser.parse_866()
    linking_number       : integer $8 linking number (1, 2, ...)
    captions             : caption overrides (keys: vol, issue, part, year, month)
    frequency            : 853 $w code
    numbering_continuity : 853 $v ('r' or 'c')
    existing_853         : the record's current 853, if it has one.  When it
                           declares a slot for every level found in the data,
                           only 863s are produced and field_853 is None so the
                           caller does not add a second, conflicting 853.
    convention           : CONVENTION_STANDARD or CONVENTION_HOUSE - the preset
                           a *regenerated* 853 starts from
    chron_as_text        : write chronology as text ("Mar") rather than MARC
                           codes ("03"), matching local practice
    convention_spec      : a fully-resolved spec from resolve_convention(),
                           letting the cataloger define the convention rather
                           than inherit a preset.  Overrides the two arguments
                           above.  Ignored when conforming to an existing 853,
                           whose own declared subfields always win.

    Returns
    -------
    ConversionResult; field_853 is None when conforming to an existing 853 or
    when the statement was withheld for review.
    """
    warnings = list(parse_result.warnings)
    # Collected by the notes below: a record the tool wrote fields for without
    # being able to vouch for all of them. Distinct from needs_review, which
    # writes nothing. "Needs attention" on the review screen is held or flagged.
    flags: set = set()

    # A segment the parser passed over is a place in the statement the tool
    # could not read. What is written from the other segments is sound, so the
    # record is not withheld -- but the tool is not vouching for the whole
    # statement, which is what flagged means. "v. 4 (1990), lacks 7" and
    # "v. 4 (1990), see also v. 9" both reach here carrying a number, and
    # nothing here can tell a gap note from holdings; a cataloguer has to look.
    if parse_result.skipped_segments:
        flags.add("skipped_segment")

    levels = parse_result.caption_union()

    # A caller may pass a fully-resolved spec (from the UI) or just a preset
    # name; resolving here keeps every existing call site working unchanged.
    if convention_spec is None:
        convention_spec, _ = resolve_convention(
            convention, chron_as_text=chron_as_text
        )
    chron_as_text = convention_spec["chron_as_text"]

    # Nothing was parsed, or the parser deliberately withheld a value because
    # its level could not be determined.  Emit no fields.
    if parse_result.needs_review or not parse_result.ranges:
        return ConversionResult(
            field_853=None,
            fields_863=[],
            linking_number=linking_number,
            warnings=warnings,
            needs_review=parse_result.needs_review,
        )

    # ── Conform to the record's own 853 when it covers every level found ──
    # An existing 853 covers the data when it declares at least as many
    # enumeration levels as the statements use, and a subfield for every
    # chronology level they use.  Depth is the test for enumeration, because
    # position is what an enumeration caption means.
    declared = read_853_slots(existing_853)
    depth_needed = len(levels.get("enum_captions", []))
    depth_declared = len(declared.get("enum", ()))
    chron_needed = {lvl for lvl in _CHRON_LEVELS if levels.get(lvl)}
    chron_declared = {lvl for lvl in _CHRON_LEVELS if lvl in declared}
    covers = (depth_declared >= depth_needed
              and chron_needed <= chron_declared)

    if declared and covers:
        # The 863s belong to the existing 853, so they must carry *its* $8 —
        # not this statement's position in the record.
        link = _existing_link(existing_853) or linking_number
        fields_863 = _with_values(
            [_build_863_for_range(hr, link, seq, levels, smap=declared,
                                  chron_as_text=chron_as_text, warnings=warnings,
                                  flags=flags, holdings_level=holdings_level)
             for seq, hr in enumerate(parse_result.ranges, start=1)],
            warnings)
        if not fields_863:
            return _held_empty(linking_number, warnings)
        return ConversionResult(
            field_853=None,           # the existing one governs; do not add another
            fields_863=fields_863,
            linking_number=link,
            warnings=warnings,
            conformed=True,
            flagged=_check_enumeration_depth(levels, warnings) or bool(flags),
        )

    if declared:
        missing = sorted(chron_needed - chron_declared)
        if depth_declared < depth_needed:
            missing.append(
                f"{depth_needed} enumeration levels (it declares "
                f"{depth_declared})"
            )
        warnings.append(
            "The existing 853 declares no level for "
            f"{', '.join(missing)} but the 866 contains "
            f"{'them' if len(missing) > 1 else 'one'} — "
            "regenerated a complete 853 from the data."
        )

    # ── Regenerate a complete 853 in the requested convention ──
    smap = convention_spec["subfields"]

    field_853 = _build_853(
        parse_result,
        linking_number=linking_number,
        captions=captions,
        frequency=frequency,
        numbering_continuity=numbering_continuity,
        units_per_higher=units_per_higher,
        convention_spec=convention_spec,
        warnings=warnings,
    )

    fields_863: List[FieldData] = []
    for seq, hr in enumerate(parse_result.ranges, start=1):
        f863 = _build_863_for_range(hr, linking_number, seq, levels, smap=smap,
                                    holdings_level=holdings_level,
                                    chron_as_text=chron_as_text, warnings=warnings,
                                    flags=flags)
        fields_863.append(f863)
    fields_863 = _with_values(fields_863, warnings)
    if not fields_863:
        return _held_empty(linking_number, warnings)

    return ConversionResult(
        field_853=field_853,
        fields_863=fields_863,
        linking_number=linking_number,
        warnings=warnings,
        flagged=_check_enumeration_depth(levels, warnings) or bool(flags),
    )


@dataclass
class RecordConversion:
    """Output of convert_record() -- everything one record needs written."""
    fields_853: List[FieldData] = field(default_factory=list)
    fields_863: List[FieldData] = field(default_factory=list)
    links_written: List[str] = field(default_factory=list)
    results: List[ConversionResult] = field(default_factory=list)  # per statement
    # Links whose run merged statements recording different amounts of detail.
    # The cataloguer may disagree that those are one publication, so the screen
    # marks them rather than presenting the merge as a finding.
    merged_links: List[str] = field(default_factory=list)
    # About the record rather than any one statement: a second 853 written
    # beside one that was already there, for instance.
    record_notes: List[str] = field(default_factory=list)

    @property
    def needs_review(self) -> int:
        return sum(1 for r in self.results if r.needs_review)

    @property
    def converted(self) -> int:
        return sum(1 for r in self.results if r.fields_863)

    @property
    def conformed(self) -> int:
        return sum(1 for r in self.results if r.conformed)

    @property
    def warnings(self) -> List[str]:
        seen, out = set(), []
        for w in self.record_notes:
            if w not in seen:
                seen.add(w)
                out.append(w)
        for r in self.results:
            for w in r.warnings:
                if w not in seen:
                    seen.add(w)
                    out.append(w)
        return out


def _set_subfield(field_data: FieldData, code: str, value: str) -> None:
    """Overwrite a subfield's value in place (used to stamp the final $8)."""
    for sf in field_data.subfields:
        if sf.code == code:
            sf.value = value
            return


def _pattern_key(field_853: FieldData) -> tuple:
    """The publication pattern an 853 expresses, ignoring its linking number."""
    return tuple((sf.code, sf.value) for sf in field_853.subfields if sf.code != "8")


def _pattern_map(field_853: FieldData) -> Dict[str, str]:
    """The same thing as a mapping, for comparing two patterns subfield by subfield."""
    return {sf.code: sf.value for sf in field_853.subfields if sf.code != "8"}


def _same_publication_pattern(a: Dict[str, str], b: Dict[str, str]) -> bool:
    """
    Whether two 853s describe one publication pattern rather than two.

    They do when every caption they both carry agrees, and one carries a subset
    of the other's.  A statement recording less detail than its neighbour --
    "v.5(1994)" beside "v.1:no.1(1990)" -- is the same publication with the
    issue simply not recorded, and an 863 need not fill every caption its 853
    declares.

    Carrying the *same* caption with a *different* value is a real change and
    never merges: month chronology and season chronology both use $j, so
    "$j (month)" and "$j (season)" disagree on a shared caption and stay apart.
    That distinction is the whole reason this is a subset test rather than an
    intersection one.
    """
    shared = a.keys() & b.keys()
    if any(a[k] != b[k] for k in shared):
        return False
    return a.keys() <= b.keys() or b.keys() <= a.keys()


def convert_record(
    parse_results: List[ParseResult],
    existing_853s: Optional[List] = None,
    captions: Optional[Dict[str, str]] = None,
    frequency: str = "",
    numbering_continuity: str = "",
    units_per_higher: str = "",
    convention_spec: Optional[Dict[str, Any]] = None,
    merge_patterns: bool = True,
    holdings_level: str = DEFAULT_HOLDINGS_LEVEL,
) -> RecordConversion:
    """
    Convert every 866 statement on one record, sharing 853s across statements
    that express the same publication pattern.

    MARC 21 treats the 853 as a caption *pattern*: a gap in holdings is another
    863 under the same 853, not a new one.  Numbering therefore cannot be
    decided per statement -- convert_holdings() cannot see its siblings -- so
    this function assigns every $8 once the whole record is known.

    Statements are grouped into *runs*: consecutive statements describing one
    publication pattern share a linking number and receive consecutive 863
    sequence numbers.  A pattern that returns after a different one has
    intervened starts a new run and takes the next linking number, because the
    publication changed twice and the record should say so:

        v. 1 no. 1-4 (Mar-Dec 2001)     months    $8 1
        v. 2 no. 1-4 (Winter-Fall 2002) seasons   $8 2
        v. 3 no. 1-4 (Mar-Dec 2003)     months    $8 3   <- not 1

    This means two identical 853s can be generated, differing only in $8.  That
    is deliberate and is not the fault v0.5.0 removed: that was one 853 per
    *statement* even where nothing had changed, whereas these mark genuinely
    separate runs either side of a change.

    Grouping therefore depends on 866 field order, which carries meaning -- a
    record whose 866s are not in publication order will produce more runs than
    it should.  A statement held for review does not break a run: nothing is
    known about it, so it is no evidence of a change.

    Statements conforming to an 853 already on the record adopt its $8 and are
    grouped by that field rather than by run, since it is one field already on
    the record and cannot be duplicated.  Any link number written to is
    reported in `links_written` so the caller can drop superseded 863s.

    `merge_patterns` False requires runs to agree exactly, so statements
    recording different amounts of detail stay apart.  Whether "v.5(1994)" beside
    "v.1:no.1(1990)" is one publication or two is a judgement about the serial,
    not about the strings, so a cataloguer who knows it is two can say so.
    """

    existing = list(existing_853s or [])
    out = RecordConversion()
    _compatible = (_same_publication_pattern if merge_patterns
                   else (lambda a, b: a == b))

    # Runs, in the order they open.  Each carries the members that share its
    # 853, the pattern they agree on, and the member whose 853 is the fullest --
    # that is the one field the record gets, so a run merged from a sparser
    # statement and a richer one is described by the richer.
    groups: "List[Dict[str, Any]]" = []
    by_link: "Dict[str, Dict[str, Any]]" = {}
    open_group: "Optional[Dict[str, Any]]" = None

    for pr in parse_results:
        # Pick the existing 853 this statement could conform to, if any.
        best = None
        for cand in existing:
            probe = convert_holdings(
                pr, existing_853=cand, captions=captions, frequency=frequency,
                numbering_continuity=numbering_continuity,
                units_per_higher=units_per_higher,
                convention_spec=convention_spec, holdings_level=holdings_level,
            )
            if probe.conformed:
                best = probe
                break

        cr = best or convert_holdings(
            pr, captions=captions, frequency=frequency,
            numbering_continuity=numbering_continuity,
            units_per_higher=units_per_higher,
            convention_spec=convention_spec, holdings_level=holdings_level,
        )
        out.results.append(cr)

        if cr.needs_review or not cr.fields_863:
            continue

        if cr.conformed:
            # An 853 already on the record: one field, so one group, however
            # many times statements return to it.
            link = str(cr.linking_number)
            group = by_link.get(link)
            if group is None:
                group = {"link": link, "pattern": None, "members": [], "head": cr}
                groups.append(group)
                by_link[link] = group
        elif (open_group is not None and open_group["link"] is None
              and _compatible(open_group["pattern"], _pattern_map(cr.field_853))):
            group = open_group
            pattern = _pattern_map(cr.field_853)
            if pattern != group["pattern"]:
                # Joined on a subset rather than an exact match: worth marking,
                # since it is the one grouping decision a cataloguer might not
                # agree with.
                group["merged"] = True
            if len(pattern) > len(group["pattern"]):
                # A later statement records more: the run is described by the
                # fuller 853, and the sparser 863s simply omit what they lack.
                group["pattern"] = pattern
                group["head"] = cr
        else:
            group = {"link": None, "pattern": _pattern_map(cr.field_853),
                     "members": [], "head": cr}
            groups.append(group)

        group["members"].append(cr)
        open_group = group

    # Allocate link numbers in run order, stepping around every 853 already on
    # the record -- not only the ones a statement conformed to. Stepping around
    # the conformed ones alone gave a new pattern $8 1 on a record whose own
    # 853 was $8 1 and matched nothing, and writing the new field then removed
    # the old one (records.add_853 replaces by $8). Measured on a real file
    # before this: an 853 with no 863s, whose statements took a different
    # pattern, came out replaced by the tool's own.
    existing_links = {(f.get("8") or "").strip() for f in existing}
    existing_links.discard("")
    taken = {g["link"] for g in groups if g["link"]} | existing_links
    nxt = 1
    for group in groups:
        if group["link"]:
            continue
        while str(nxt) in taken:
            nxt += 1
        group["link"] = str(nxt)
        taken.add(str(nxt))
        nxt += 1

    # Stamp $8 and let 863 sequence numbers run across the whole group.
    for group in groups:
        link = group["link"]
        out.links_written.append(link)
        if group.get("merged"):
            out.merged_links.append(link)
        seq = 1
        for cr in group["members"]:
            for f863 in cr.fields_863:
                _set_subfield(f863, "8", f"{link}.{seq}")
                out.fields_863.append(f863)
                seq += 1
            cr.linking_number = link
            # Every member reports the run's 853, not the one it would have had
            # alone. Only the head's field reaches the record, so a member
            # showing its own would be previewing a field that is never written
            # -- visible whenever a run merged a sparser statement with a
            # fuller one.
            if cr.field_853 is not None and group["head"].field_853 is not None:
                cr.field_853 = group["head"].field_853
            if cr.field_853 is not None:
                _set_subfield(cr.field_853, "8", link)
        # One 853 per run, the fullest of its members; conformed groups already
        # have their field on the record.
        head = group["head"]
        if head.field_853 is not None:
            out.fields_853.append(head.field_853)
            if existing_links:
                # Kept beside, not written over: the 853 already there is the
                # cataloguer's, and which pattern is right is theirs to say.
                out.record_notes.append(
                    f"An 853 was already on this record "
                    f"(${'8 ' + ', $8 '.join(sorted(existing_links))}), and "
                    f"these holdings do not match it. A second 853 was added "
                    f"as $8 {link} rather than replace it - check which "
                    f"pattern is right.")

    return out


def apply_to_record(
    record: "Record",
    conversion: ConversionResult,
    remove_866: bool = True,
    original_866_tag: Optional[str] = None,
) -> "Record":
    """
    Apply a ConversionResult to a pymarc Record in-place.

    Adds the 853/863 fields and optionally removes the source 866.

    Parameters
    ----------
    record           : pymarc Record to modify
    conversion       : output of convert_holdings()
    remove_866       : if True, remove matching 866 fields
    original_866_tag : specific 866 field tag to remove (for future use)
    """
    if not HAS_PYMARC:
        raise RuntimeError("pymarc must be installed to work with Record objects.")

    # Added in tag order rather than appended: see records.add_853() for why
    # a record that came in as 852, 866, 999 must not go out as 852, 866,
    # 999, 853, 863.
    record.add_ordered_field(conversion.field_853.to_pymarc())

    for f863 in conversion.fields_863:
        record.add_ordered_field(f863.to_pymarc())

    # Optionally strip source 866 fields
    if remove_866:
        record.remove_fields("866")

    return record
