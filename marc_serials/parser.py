"""
holdings_parser.py
------------------
Parses textual MARC 866 holdings statements into structured data
that can be used to generate 853 (caption/pattern) and 863
(enumeration/chronology) MARC fields.

Supported 866 $a patterns (case-insensitive):
  v.1(1990)-v.5(1994)
  v.1:no.1(1990:Jan.)-v.5:no.4(1994:Dec.)
  v.1:no.1(1990:Spring)-v.5:no.4(1994:Winter)
  v.6(1995)-                          ← open-ended / current
  Vol. 1, No. 1 (Spring 1990)-...
  1990-1994                           ← year-only holdings
  v.1-5(1990-1994)                    ← compressed range format
  v.1:no.1-v.2:no.4(1990-1991)       ← chron at end only
  Multiple ranges: "v.1(1990)-v.3(1992), v.5(1994)-"

Also supports a second, chronology-first "block" grammar found in older and
locally-maintained records, dispatched separately by _looks_like_block():
  1993: (1 [Feb])
  2019: (1-6 [Feb-Nov])2020: (7-12 [Jan-Dec])
  1949: 1 (1-6 [Apr-Sep])
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional, List, Tuple, Set

# ---------------------------------------------------------------------------
# Month / season normalisation
# ---------------------------------------------------------------------------

MONTH_MAP: dict[str, str] = {
    "jan": "Jan.", "feb": "Feb.", "mar": "Mar.", "apr": "Apr.",
    "may": "May", "jun": "Jun.", "jul": "Jul.", "aug": "Aug.",
    "sep": "Sep.", "oct": "Oct.", "nov": "Nov.", "dec": "Dec.",
    # Long forms
    "january": "Jan.", "february": "Feb.", "march": "Mar.",
    "april": "Apr.", "june": "Jun.", "july": "Jul.",
    "august": "Aug.", "september": "Sep.", "october": "Oct.",
    "november": "Nov.", "december": "Dec.",
}

SEASON_MAP: dict[str, str] = {
    "spring": "Spring", "summer": "Summer",
    "fall": "Fall", "autumn": "Fall", "winter": "Winter",
}

# MARC 21 chronology codes used in 863 $j: months 01-12, seasons 21-24.
#
# Ported from the marc_853_encoding table in extract.py by Phani Chaitanya
# Pendyala (MIT). See THIRD-PARTY-NOTICES.md.
MARC_CHRON_CODES: dict[str, str] = {
    "jan": "01", "january": "01",
    "feb": "02", "february": "02",
    "mar": "03", "march": "03",
    "apr": "04", "april": "04",
    "may": "05",
    "jun": "06", "june": "06",
    "jul": "07", "july": "07",
    "aug": "08", "august": "08",
    "sep": "09", "sept": "09", "september": "09",
    "oct": "10", "october": "10",
    "nov": "11", "november": "11",
    "dec": "12", "december": "12",
    "spring": "21", "spr": "21",
    "summer": "22", "sum": "22",
    "fall": "23", "autumn": "23", "aut": "23",
    "winter": "24", "win": "24", "wint": "24",
}

SEASON_CODES = {"21", "22", "23", "24"}


def chron_unit_code(raw: str) -> Optional[str]:
    """Return the MARC chronology code for a month/season name, or None."""
    return MARC_CHRON_CODES.get(raw.strip().rstrip(".").lower())


# ---------------------------------------------------------------------------
# What a coded chronology subfield can hold
# ---------------------------------------------------------------------------
#
# This lived in converter.py until 0.12.0, where it decided whether a value
# could be written into an 863.  The 853 has to answer the same question one
# step earlier -- a level whose only value is prose is not a level the serial
# has -- so it sits here, below the code table it tests against, and the
# converter imports it.  Two copies of one rule drift.

# A chronology subfield an 853 labels "(month)" or "(season)" holds MARC codes:
# months 01-12, seasons 21-24, joined by "-" for a range and "/" for a combined
# issue.  Anything else is prose.
_CHRON_CODE = r"(?:0[1-9]|1[0-2]|2[1-4])"
_CHRON_VALUE_RE = re.compile(rf"^{_CHRON_CODE}(?:[-/]{_CHRON_CODE})*-?$")

# A year subfield holds four-digit years, likewise joined.
_YEAR_VALUE_RE = re.compile(r"^\d{4}(?:[-/]\d{4})*-?$")

# A day subfield holds days of the month, joined the same way.
_DAY_VALUE_RE = re.compile(r"^(?:0?[1-9]|[12]\d|3[01])(?:[-/](?:0?[1-9]|[12]\d|3[01]))*-?$")


def is_codeable(level, value: str) -> bool:
    """Whether `value` may be written into the coded subfield for `level`."""
    if level == "month":
        return bool(_CHRON_VALUE_RE.match(value))
    if level == "year":
        return bool(_YEAR_VALUE_RE.match(value))
    if level == "day":
        return bool(_DAY_VALUE_RE.match(value))
    return True


def demonstrates_level(level, value: str) -> bool:
    """
    Whether `value` shows the serial *has* this level, which is a different
    question from whether the value can be written.

    "v. 15 no. 6 - v. 23 nos. 2/3 (Nov/Dec 1994 - Late Summer 2002)" carries
    '11/12-Late Summer'.  No subfield can hold that, so the 863 writes no $j
    and says why -- but Nov/Dec is a month, and a serial with a November/
    December issue has a month level whatever the other end of the range is
    called.  The 853 declares it; the 863 still records nothing.

    "v. 15 (1998 Buyers Guide)" carries 'Buyers Guide', where no part is a
    month at all, and gets no caption.

    Not a second copy of is_codeable(): that one answers "may this be
    written?", which governs the 863, and this one answers "does the serial
    have this level?", which governs the 853.  They gave the same answer until
    a value turned out to be half of each.
    """
    return any(is_codeable(level, part)
               for part in re.split(r"[-/]", value) if part)

def normalise_chron_unit(raw: str) -> str:
    """Normalise a month or season string to MARC-standard form."""
    raw = raw.strip().rstrip(".")
    key = raw.lower()
    if key in MONTH_MAP:
        return MONTH_MAP[key]
    if key in SEASON_MAP:
        return SEASON_MAP[key]
    return raw  # return as-is (e.g. "Spr.", user-supplied)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class EnumLevel:
    """
    One level of enumeration: the caption a statement used, and its value.

    Both matter, and they are separate things.  MARC 853 carries enumeration
    captions in $a-$f in descending order of significance, and the *word* in
    each is just a label -- "no." in $a is a serial numbered by issue with no
    volume above it, which is ordinary.  Tying the level to the word ("issue
    means $b") is what made those statements unconvertible.
    """
    caption: Optional[str] = None    # as written, normalised: "v.", "no.", "pt."
    value: Optional[str] = None      # "1", "1-5", "1/2"


@dataclass
class EnumChron:
    """One boundary (start or end) of a holdings range."""
    # Enumeration levels, most significant first.  A serial numbered only by
    # issue has one level whose caption is "no."; a volume/issue/part serial
    # has three.  Position in this list is the level -- nothing else decides it.
    enum: List[EnumLevel] = field(default_factory=list)
    year: Optional[str] = None       # four-digit year string
    month: Optional[str] = None      # month or season (normalised)
    day: Optional[str] = None        # day (uncommon for journals)

    # Chronology levels this boundary's wording demonstrates but whose value
    # could not be written -- "1981 - Sep 1996" states a month at one end only,
    # so there is no range to record and _pair_or_drop() drops the value.  The
    # serial still has a month level, and the 853 has to declare it: the 853
    # maps the whole structure a serial can have, while the 863 carries the
    # values one holding actually pins down.  Without this the level vanished
    # with the value, and an 866 stating a month produced an 853 saying the
    # serial has none.
    demonstrated: Set[str] = field(default_factory=set)

    def level(self, index: int) -> Optional[EnumLevel]:
        """The enumeration level at `index`, or None when there is none."""
        return self.enum[index] if index < len(self.enum) else None

    def value_at(self, index: int) -> Optional[str]:
        lvl = self.level(index)
        return lvl.value if lvl else None

    def has_enum(self) -> bool:
        return any(lvl.value for lvl in self.enum)

    def has_chron(self) -> bool:
        return any([self.year, self.month, self.day])

    def __str__(self) -> str:
        parts = [f"{lvl.caption or ''}{lvl.value}"
                 for lvl in self.enum if lvl.value]
        chron_parts = []
        if self.year:
            chron_parts.append(self.year)
        if self.month:
            chron_parts.append(self.month)
        if chron_parts:
            parts.append(f"({'  :'.join(chron_parts)})")
        return "".join(parts)


def _sole_offset(short: List[Optional[str]],
                 long: List[Optional[str]]) -> Optional[int]:
    """
    The one offset at which `short` sits inside `long`, or None if not exactly
    one does.  A missing caption on either side matches anything, since it
    states nothing to contradict.
    """
    fits = [k for k in range(len(long) - len(short) + 1)
            if all(a is None or b is None or a == b
                   for a, b in zip(short, long[k:]))]
    return fits[0] if len(fits) == 1 else None


@dataclass
class HoldingsRange:
    """A single holdings range (start–end, or start– if open)."""
    start: EnumChron = field(default_factory=EnumChron)
    end: Optional[EnumChron] = None   # None means open-ended
    open_ended: bool = False          # True  ⇒ still being received
    raw: str = ""                     # original text for this range
    # 863 $w on this field: the break between it and the next 863.  Set only
    # where the statement itself shows the break -- one run of a discontinuous
    # list to the next, a comma or semicolon between two runs, or one the
    # statement ends on.  Two separate 866s may have a gap between them that
    # neither states, but that is a reading of the record rather than of the
    # statement, and is not decided here.
    break_after: str = ""

    def __post_init__(self) -> None:
        self.align_boundaries()

    def align_boundaries(self) -> None:
        """
        Slide a boundary that omits its leading levels down to where it fits.

        Position in `enum` is the level, and for a range written out in full
        that is all anyone needs.  A range that states two levels at one end and
        one at the other breaks it: "v. 12 no. 1-no. 6" puts "no. 6" at position
        0, where the other end has "v. 12", and the 863 comes out "$a 12-6" --
        volume 12 to volume 6, a range that runs backwards and is not what the
        statement says.

        The captions settle it.  The end's "no." can only be the level the start
        also calls "no.", so an empty level is pushed in front of it and the two
        line up: "$a 12 $b 1-6".

        Only a boundary whose captions fit at exactly one offset is moved.  If
        they fit nowhere, or in more than one place, nothing is moved and the
        converter reports the values it cannot place -- guessing which level a
        value belongs to is the error this exists to prevent, and a wrong guess
        here is invisible in the output.

        Run at construction, and again by anything that fills the boundaries in
        afterwards -- the parser builds an empty range and populates it, so
        construction is too early there.  Running twice costs nothing: once the
        captions line up there is nothing left to move.
        """
        if self.end is None:
            return

        s_caps = [lvl.caption for lvl in self.start.enum]
        e_caps = [lvl.caption for lvl in self.end.enum]
        if not any(s_caps) or not any(e_caps):
            return                      # nothing captioned to align by

        if all(s is None or e is None or s == e
               for s, e in zip(s_caps, e_caps)):
            return                      # they already agree where both speak

        if len(e_caps) < len(s_caps):
            offset = _sole_offset(e_caps, s_caps)
            if offset:
                self.end.enum = [EnumLevel()] * offset + self.end.enum
        elif len(s_caps) < len(e_caps):
            offset = _sole_offset(s_caps, e_caps)
            if offset:
                self.start.enum = [EnumLevel()] * offset + self.start.enum

    def enum_depth(self) -> int:
        """How many enumeration levels either boundary of this range states."""
        return max((len(ec.enum) for ec in (self.start, self.end) if ec),
                   default=0)

    def enum_captions(self) -> List[Optional[str]]:
        """
        The caption for each enumeration level, most significant first.

        Taken from whichever boundary states one, since a range often writes
        its captions only at the start ("v. 1 no. 1-v. 5 no. 4" writes them
        twice, "v. 1-v. 5 no. 4" only once).
        """
        captions: List[Optional[str]] = [None] * self.enum_depth()
        for ec in (self.start, self.end):
            if ec is None:
                continue
            for i, lvl in enumerate(ec.enum):
                if captions[i] is None and lvl.caption:
                    captions[i] = lvl.caption
        return captions

    def caption_levels(self) -> dict:
        """Which levels appear in this range: enumeration depth plus chronology."""
        levels: dict = {}
        depth = self.enum_depth()
        if depth:
            levels["enum_depth"] = depth
            levels["enum_captions"] = self.enum_captions()
        for ec in [self.start, self.end]:
            if ec is None:
                continue
            for name, value in (("year", ec.year),
                                ("month", ec.month),
                                ("day", ec.day)):
                # A value that cannot be coded is prose on its way to being
                # dropped and named -- "v. 15 (1998 Buyers Guide)" puts
                # 'Buyers Guide' in the month slot.  It occupies the slot; it
                # does not show the serial has that level, so it must not earn
                # a caption the 863 will never fill with anything.
                if value is not None and demonstrates_level(name, value):
                    levels[name] = True
            for name in ec.demonstrated:
                levels[name] = True
        return levels


@dataclass
class ParseResult:
    """Result of parsing a single 866 $a value."""
    ranges: List[HoldingsRange] = field(default_factory=list)
    raw: str = ""
    warnings: List[str] = field(default_factory=list)
    success: bool = True
    needs_review: bool = False   # values were found but could not be placed

    # Segments the parser could make nothing of and passed over, kept as text.
    #
    # A comma-separated segment that yields neither enumeration nor chronology
    # is skipped with a warning naming it. Recorded here as well, because the
    # converter has to put the record where a cataloguer will see it: a warning
    # alone only shows when the row is opened, and nobody opens a row that
    # looks converted. That is the reasoning 0.9.6 applied to chronology
    # wording a coded subfield cannot hold; this is the same shape.
    #
    # Held as a list rather than a flag so the caller can say which segment,
    # and so nothing has to read it back out of a warning string.
    skipped_segments: List[str] = field(default_factory=list)

    def caption_union(self) -> dict:
        """
        Union of levels across all ranges.

        Enumeration depth is the deepest any range reaches, and each level's
        caption comes from the first range that names it -- one 853 has to
        describe every 863 linked to it, so it declares as many levels as the
        fullest statement uses.
        """
        union: dict = {}
        captions: List[Optional[str]] = []
        for r in self.ranges:
            levels = r.caption_levels()
            for key in ("year", "month", "day"):
                if levels.get(key):
                    union[key] = True
            for i, cap in enumerate(levels.get("enum_captions", [])):
                if i >= len(captions):
                    captions.append(cap)
                elif captions[i] is None:
                    captions[i] = cap
        if captions:
            union["enum_depth"] = len(captions)
            union["enum_captions"] = captions
        return union


# ---------------------------------------------------------------------------
# Tokeniser / regex helpers
# ---------------------------------------------------------------------------

# Matches a single enumeration+chronology unit such as:
#   v.1:no.2(1990:Mar.)  or  Vol.1,No.2(Spring 1990)  or  1990
#
# Group names used below:
#   vol_cap   – caption word for volume   (v, vol, volume)
#   vol_num   – volume number
#   iss_cap   – caption word for issue    (no, n, nr, num, number, issue, iss, pt, part)
#   iss_num   – issue number
#   chron_raw – everything inside ( )
#   year_only – bare year with no parens

# 863 $w, the break indicator: the code that says what the break before the next
# 863 is.  "g" is a gap -- parts lacking from the holdings, or a break whose
# cause is not known, which is the honest reading of a cataloguer writing
# "nos. 1, 3".  "n" is a non-gap break, for parts never published or a
# discontinuity in the numbering itself; nothing here can tell that apart from a
# gap, so nothing here writes it.
BREAK_GAP = "g"
BREAK_NON_GAP = "n"


# Caption words, and the normalised form each is written back as.  The word
# says what a level is *called*, never which level it is: "no." is ordinary in
# $a for a serial numbered by issue with no volume above it.
_CAPTION_WORDS = (
    (r"v(?:ol(?:ume)?)?", "v."),
    (r"nos?|n|nr|num(?:ber)?s?|iss(?:ue)?s?", "no."),
    (r"pts?|parts?", "pt."),
    (r"ser(?:ies)?", "ser."),
)
_CAPTION_ALT = "|".join(alt for alt, _ in _CAPTION_WORDS)

# One enumeration level: an optional caption, then its value.  The value may be
# a range ("1-5") or a combined designation ("7/8"), the two forms holdings use
# to compress a level.
_ENUM_LEVEL_RE = re.compile(
    rf"""
    (?:(?P<cap>{_CAPTION_ALT})\s*[.\s]*\s*)?
    (?P<num>\d+[a-zA-Z]?(?:\s*[-/]\s*\d+[a-zA-Z]?)?)
    """,
    re.IGNORECASE | re.VERBOSE,
)

# An ordinal written out -- "50th", "3rd", "21st".
#
# The value pattern above ends in an optional letter, which is there for a
# genuine suffix: "v. 4a" is volume 4a and writes $a 4a.  An ordinal defeats it
# by being one letter longer, so "50th" matched as the value "50t" and left a
# stray "h" for the rest of the statement to account for.  That produced the
# refusal message "Read '50t' but could not account for 'h Anniversary Issue
# (2017)'", which points a cataloguer at a place reading never stopped.
#
# An ordinal is not an enumeration value in any case: "50th Anniversary Issue"
# numbers nothing, and the statement is refused either way.  Recognising it
# here is what makes the refusal say something true.
_ORDINAL_RE = re.compile(r"^\d+(?:st|nd|rd|th)(?![a-zA-Z])", re.IGNORECASE)

# What separates one enumeration level from the next: ":", "," or whitespace.
_LEVEL_SEP_RE = re.compile(r"^[\s:,]\s*")

# The chronology block, in parentheses after the enumeration.
_CHRON_BLOCK_RE = re.compile(r"\(\s*(?P<chron_raw>[^)]+)\)")


def normalise_caption(raw: Optional[str]) -> Optional[str]:
    """
    The standard written form of a caption word: "Vol."/"volume" -> "v.".

    The word is preserved, the style is not.  Without this, "v. 1 no. 1" and
    "Vol. 1, No. 1" would build 853s that differ only in punctuation and stop
    sharing one field across a record.
    """
    if not raw:
        return None
    key = raw.strip().rstrip(".").lower()
    for alt, canonical in _CAPTION_WORDS:
        if re.fullmatch(alt, key, re.IGNORECASE):
            return canonical
    return raw.strip()


def _parse_enum_levels(text: str) -> Tuple[List[EnumLevel], int]:
    """
    Read consecutive enumeration levels off the front of `text`.

    Returns the levels and how far into `text` they reached.  Levels are taken
    in the order they are written -- position is the level, and the caption
    word is carried along rather than deciding anything.
    """
    levels: List[EnumLevel] = []
    pos = 0
    while pos < len(text):
        chunk = text[pos:]
        if levels:
            sep = _LEVEL_SEP_RE.match(chunk)
            if not sep:
                break
            chunk = chunk[sep.end():]
            offset = pos + sep.end()
        else:
            offset = pos

        m = _ENUM_LEVEL_RE.match(chunk)
        if not m or not m.group("num"):
            break
        # An ordinal, not a value with a suffix.  Checked against the text at
        # the number's own start, so a caption in front of it does not matter.
        if _ORDINAL_RE.match(chunk[m.start("num"):]):
            break
        # A second or later level must name itself.  Without that rule the
        # "18" of "Apr 18, 1996" or a stray number after a caption would be
        # swallowed as another level.
        if levels and not m.group("cap"):
            break
        # "1 - 55" is the range 1-55. The spaces are how it was typed, not part
        # of the value, and written into $a they made "$a 1 - 55" -- which the
        # round trip read back as "1-55" and reported as drift.
        value = re.sub(r"\s*([-/])\s*", r"\1", m.group("num").strip())
        levels.append(EnumLevel(caption=normalise_caption(m.group("cap")),
                                value=value))
        pos = offset + m.end()

    return levels, pos


# A year, optionally split across the turn of one: "1996", "1996/97",
# "1996/1997".  A serial whose winter issue straddles the new year is numbered
# that way as a matter of course, and MARC records the pair in 863 $i the same
# way it records a combined month in $j -- slash-joined, both halves in full.
_YEAR_TOKEN = r"\d{4}(?:\s*/\s*\d{2,4})?"
_SPLIT_YEAR_RE = re.compile(r"^(\d{4})\s*/\s*(\d{2,4})$")


def normalise_year(raw: Optional[str]) -> Optional[str]:
    """
    '1996' -> '1996';  '1996/97' -> '1996/1997';  '1999/00' -> '1999/2000'.

    The two-digit half takes the first year's century, and rolls forward when
    that would put it in the past: "1999/00" is 1999-2000, not 1999-1900.
    """
    if not raw:
        return raw
    m = _SPLIT_YEAR_RE.match(raw.strip())
    if not m:
        return raw.strip()
    first, second = m.group(1), m.group(2)
    if len(second) == 4:
        return f"{first}/{second}"
    full = int(first[:2] + second.zfill(2))
    if full < int(first):
        full += 100
    return f"{first}/{full}"


# Simpler pattern for year-only holdings (e.g. "1990" or "1990-1994")
_YEAR_ONLY_RE = re.compile(rf"^\s*({_YEAR_TOKEN})\s*$")

# Z39.71 chronology standing alone, with no enumeration before it and no
# parentheses round it: "1990:Jan.", "1994:Winter/Spring", "2014:Nov. 7". It is
# what an ILS generates for a serial whose 853 has chronology captions only,
# and it went unread twice over: the year-first grammar claimed anything that
# opened "year:", and the enumeration grammar wants its chronology in
# parentheses. See D31.
_BARE_CHRON = (rf"{_YEAR_TOKEN}\s*:\s*[A-Za-z][A-Za-z./]*"
               rf"(?:\s*[:\s]\s*\d{{1,2}})?")
_BARE_CHRON_RE = re.compile(rf"^\s*{_BARE_CHRON}\s*$")

# A year written before a volume: "1990: v.1". The year is the date the volume
# belongs to, not a level above it -- a volume is the first level of
# enumeration, and "$a 1990 $b 1" put "v." second, under a level captioned
# "(*)". A year before an issue ("2004 no. 3") is left as it was: journals
# really do number by year, and that reading is the cataloguer's to confirm.
_YEAR_BEFORE_VOLUME_RE = re.compile(
    rf"^\s*({_YEAR_TOKEN})\s*[:\s]\s*(?=v(?:ol(?:ume)?)?\b\.?\s*\d)", re.IGNORECASE)
_BARE_CHRON_RANGE_RE = re.compile(
    rf"^\s*(?:{_BARE_CHRON}|{_YEAR_TOKEN})\s*(-)\s*(?:{_BARE_CHRON}|{_YEAR_TOKEN})\s*$")

# Matches the start of a new range: a volume-level caption at the beginning
# e.g. "v.", "vol.", "volume" – but NOT "no.", "n.", "pt." etc.
_VOL_START_RE = re.compile(
    r"^\s*(?:v(?:ol(?:ume)?)?)\s*[.\s]", re.IGNORECASE
)
_YEAR_START_RE = re.compile(rf"^\s*{_YEAR_TOKEN}\s*(?:$|-)")

def _is_designation_prefix(before: str, after: str) -> bool:
    """
    True when `before` heads the statement `after` rather than being a range.

    "Series 1, v. 6 no. 1 (Summer/Fall 1992)" is one statement: the series is a
    designation the volume sits under, and splitting it off leaves two ranges
    numbered by hierarchies that no single 853 can describe.  "v. 1, v. 5
    (1994)" is two ranges, and reads the same way to a cataloguer, so the test
    is whether the two sides number by the same caption: a repeated caption is
    a second range, a caption that appears only on the left is a heading.

    A designation states no chronology -- once it does, it is a range of its
    own whatever it is called.
    """
    if "(" in before or ")" in before:
        return False
    left, consumed = _parse_enum_levels(before)
    if not left or consumed < len(before.strip()):
        return False
    if any(lvl.caption is None for lvl in left):
        return False
    right, _ = _parse_enum_levels(after)
    right_captions = {lvl.caption for lvl in right if lvl.caption}
    if not right_captions:
        return False
    return not any(lvl.caption in right_captions for lvl in left)


# ---------------------------------------------------------------------------
# Discontinuous lists
# ---------------------------------------------------------------------------
#
# "v. 19 nos. 1, 3, 5, 7-12 (Jan, Mar, May, Jul-Dec 1915)" is four runs of
# holdings with gaps between them, written the compact way a cataloguer writes
# them.  MARC 21 records gaps as separate 863s under one 853, so the four runs
# are four fields -- which is exactly what the converter already builds from a
# statement written out longhand:
#
#   v. 1 no. 1 (Jan 1990), v. 1 no. 3 (Mar 1990)
#     -> 863 $8 1.1 $a 1 $b 1 $i 1990 $j 01
#        863 $8 1.2 $a 1 $b 3 $i 1990 $j 03
#
# So the compact form is expanded into the longhand one and handed to the unit
# parser, rather than given a grammar of its own.  Everything the unit parser
# knows about captions, combined issues and seasons then applies unchanged.

# One item of a list: a number, a combined designation ("7/8"), or a run
# ("7-12").  An item carrying its own caption is a new statement, not a
# continuation of this one, and never reaches here -- _split_ranges() has
# already cut the statement there.
_LIST_VALUE = (r"\d+[a-zA-Z]?(?:\s*/\s*\d+[a-zA-Z]?)*"
               r"(?:\s*-\s*\d+[a-zA-Z]?(?:\s*/\s*\d+[a-zA-Z]?)*)?")
_LIST_ITEM_RE = re.compile(rf"^{_LIST_VALUE}$")

# The first item of a list, with everything before it: "v. 19 nos. " and "1".
# The prefix ends in a caption, because the caption is what every later item
# inherits.  A list with no caption anywhere -- "8,13,15,17,19,20-" -- is
# matched by _LIST_ITEM_RE instead and takes an empty prefix: nothing says what
# those numbers are, and nothing has to, because they are the most significant
# enumeration level and the 853 writes "(*)" for a level with no caption.
_LIST_HEAD_RE = re.compile(
    rf"""^(?P<prefix>.*?(?:{_CAPTION_ALT})\s*\.?\s*)
         (?P<item>{_LIST_VALUE})\s*$""",
    re.IGNORECASE | re.VERBOSE,
)

# The chronology block at the very end of a statement.
_TRAILING_CHRON_RE = re.compile(r"\(\s*(?P<chron>[^()]*?)\s*\)\s*$")

# A chronology item that states only a year, or a run of them.
_BARE_YEAR_ITEM_RE = re.compile(rf"^{_YEAR_TOKEN}(?:\s*-\s*{_YEAR_TOKEN})?$")

# One year, which "1915/16" still is -- a single publication year written across
# the turn of one.  "1982-1994" is not, and the difference decides whether a
# chronology stated once can be given to every run of a list.
_SINGLE_YEAR_ITEM_RE = re.compile(rf"^{_YEAR_TOKEN}$")

_FIRST_INT_RE = re.compile(r"\d+")


def _split_top_level(text: str, sep: str = ",") -> List[str]:
    """Split on `sep`, ignoring any that falls inside brackets of either kind."""
    depth = 0
    parts: List[str] = []
    current: List[str] = []
    for ch in text:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    parts.append("".join(current))
    return [p.strip() for p in parts]


def _chron_items(raw: str) -> Optional[List[str]]:
    """
    The chronology block read as a list, or None if it is not one.

    The list has to be homogeneous: months and seasons throughout, or years
    throughout.  A mixed one is how the American date convention writes a single
    date -- "(Apr 18, 1996)" splits into "Apr 18" and "1996" -- and reading that
    as two items would break one date into two holdings runs.
    """
    parts = [p for p in _split_top_level(raw) if p]
    if len(parts) < 2:
        return parts
    if all(p[:1].isalpha() for p in parts):
        return parts
    if all(_BARE_YEAR_ITEM_RE.match(p) for p in parts):
        return parts
    return None


def _carry_year_back(parts: List[str]) -> List[str]:
    """
    Give every chronology item the year it is written under.

    "(Jan, Mar, May, Jul-Dec 1915)" states 1915 once, at the end, for all four.
    "(Nov 1915, Jan 1916)" states one for each.  Reading right to left covers
    both: an item without a year belongs to the nearest year on its right.
    """
    carried: Optional[str] = None
    out: List[str] = []
    for part in reversed(parts):
        found = re.search(rf"\b{_YEAR_TOKEN}", part)
        if found:
            carried = found.group(0)
            out.append(part)
        elif carried:
            out.append(f"{part} {carried}")
        else:
            out.append(part)
    return list(reversed(out))


def _gap_after(item: str, nxt: str) -> str:
    """
    The 863 $w break indicator for the break between two items of a list.

    "g" is a gap break -- parts lacking, or a break whose cause is not known --
    which is what a cataloguer listing "nos. 1, 3" is recording.  Two items that
    run straight on ("nos. 1, 2") have no break to indicate, and nothing is
    written.  Numbering that cannot be read as integers is not evidence of
    continuity, so it is treated as a gap.
    """
    ends = _FIRST_INT_RE.findall(item)
    starts = _FIRST_INT_RE.findall(nxt)
    if ends and starts and int(starts[0]) == int(ends[-1]) + 1:
        return ""
    return BREAK_GAP


def _note_undistributable(warnings: Optional[List[str]], chron: str,
                          runs: int) -> None:
    """
    Record a chronology stated once for a list it cannot be shared across.

    A compressed 863 carries the dates of its own run.  A single year can be
    every run's year and is written to all of them; a range, or anything more
    specific than a year, belongs to the statement as a whole and to no
    particular run in it.  There is no notation for that, so it is named --
    which keeps it accounted for, and tells the cataloguer what to add by hand.
    """
    if warnings is None:
        return
    note = (
        f"'{chron}' was left out: it is stated once for all {runs} runs of this "
        f"statement, and it is not a single year that could be true of each of "
        f"them. Each 863 records the dates of its own run, and there is no way "
        f"to divide this one between them. The holdings themselves are "
        f"recorded; add the dates by hand if they matter."
    )
    if note not in warnings:
        warnings.append(note)


def _expand_distributed_list(text: str,
                             warnings: Optional[List[str]] = None,
                             ) -> Optional[tuple]:
    """
    Read a list of discontinuous runs, or None if the statement is not one.

    Returns what the list *is* -- the prefix every item inherits, the items
    themselves, a chronology for each, and whether the last one is still open --
    and leaves reading each run to the caller, which has two ways to do it
    depending on whether the list captions anything.

    "v. 19 nos. 1, 3, 5, 7-12 (Jan, Mar, May, Jul-Dec 1915)" becomes

        v. 19 nos. 1 (Jan 1915)
        v. 19 nos. 3 (Mar 1915)
        v. 19 nos. 5 (May 1915)
        v. 19 nos. 7-12 (Jul-Dec 1915)

    All of it or none of it.  The two lists have to be the same length, because
    pairing them is the whole claim being made: four issue runs against three
    months says the statement was not understood, and a converter that carried
    on would file holdings under the wrong dates.  A single bare year is the one
    exception -- "(1915)" is stated once for every run in the list and applies to
    all of them.
    """
    chron_raw = None
    head = text.strip()
    m = _TRAILING_CHRON_RE.search(head)
    if m:
        chron_raw = m.group("chron")
        head = head[:m.start()].strip()

    # "8,13,15,17,19,20-(1982-1994)" is still being received, and the hyphen
    # saying so is the last thing before the chronology.  Taken off here so the
    # final item parses as a plain number, and put back on the statement built
    # from it, which is where _parse_one_range looks for it.
    open_ended = bool(re.search(r"-\s*$", head))
    if open_ended:
        head = re.sub(r"-\s*$", "", head).strip()

    parts = [p for p in _split_top_level(head) if p]
    if len(parts) < 2:
        return None

    first = _LIST_HEAD_RE.match(parts[0])
    if first:
        prefix, first_item = first.group("prefix"), first.group("item")
    elif _LIST_ITEM_RE.match(parts[0]):
        prefix, first_item = "", parts[0]
    else:
        return None
    if not all(_LIST_ITEM_RE.match(p) for p in parts[1:]):
        return None

    items = [first_item] + parts[1:]

    chrons: List[Optional[str]] = [None] * len(items)
    if chron_raw:
        chron_parts = _chron_items(chron_raw)
        if chron_parts is None:
            return None
        if len(chron_parts) == 1 and _SINGLE_YEAR_ITEM_RE.match(chron_parts[0]):
            # "(1915)" is the year every run in the list falls in, stated once.
            chrons = [chron_parts[0]] * len(items)
        elif len(chron_parts) == len(items):
            chrons = list(_carry_year_back(chron_parts))
        elif len(chron_parts) == 1:
            # One chronology for several runs that is not a single year.
            # "(1982-1994)" spans the statement, not any one run in it, and
            # "(Jan 1915)" cannot be true of both no. 1 and no. 3.  Giving it to
            # each run would put twelve years on a single issue.  The
            # enumeration is unambiguous and is kept; the chronology is named.
            _note_undistributable(warnings, chron_raw.strip(), len(items))
        else:
            return None

    return prefix, items, chrons, open_ended


def is_distributed_list(text: str) -> bool:
    """
    Whether `text` lists several runs of holdings rather than describing one.

    Public because the Workbench needs the same answer the parser uses. A
    statement like this is more ranges than a confirmed pattern has roles to
    describe -- a pattern captures a fixed set of values and pairs them as one
    compressed range -- so the Workbench neither splits it into fragments for
    the confirm step nor lets a pattern claim it, and hands it to the parser
    whole.
    """
    return _expand_distributed_list(text) is not None


def _parse_chronology_list(text: str,
                           warnings: Optional[List[str]] = None,
                           ) -> Optional[List[HoldingsRange]]:
    """
    One HoldingsRange per run of "(1986-1988, 1993-1994)".

    The enumerated form of this has worked since the distributed-list work:
    "v. 24 nos. 2-5, 8-10 (Apr-Jul, Oct-Dec 1920)" becomes two 863s with a gap
    between them.  The chronology-only form did not, because the list lives
    entirely inside the parentheses and _expand_distributed_list() has nothing
    before them to drive the expansion from.  So the statement was read as far
    as the first year and the rest was dropped -- and dropped *silently*, with
    no warning, no flag and nothing held for review, which is the fourth state
    rule 4 says must not exist.  Found while auditing a real 372-record file:
    one statement of 1057, "(1986-1988, 1993-1994)", which converted to
    "$i 1986" and lost 1988, 1993 and 1994 without saying so.

    Deliberately narrow.  Every part must read as chronology on its own and
    none may carry enumeration, so "(Jan, Mar-May, Sep, Oct 1982)" -- where the
    year is stated once at the end and the parts are not chronologies -- is not
    a list by this definition and keeps the behaviour it already had, which
    names what it could not encode rather than dropping it.
    """
    head = text.strip()
    match = _TRAILING_CHRON_RE.search(head)
    if not match:
        return None
    if head[:match.start()].strip():
        return None                     # something before the parentheses

    parts = [p for p in (q.strip() for q in
                         _split_top_level(match.group("chron"))) if p]
    if len(parts) < 2:
        return None

    ranges: List[HoldingsRange] = []
    for part in parts:
        hr = _parse_one_range(f"({part})", warnings)
        # A year of its own on every part, not merely "some chronology". The
        # first version of this asked for chronology and turned
        # "(Jan, Mar-May, Sep, Oct 1982)" -- where the year is stated once, at
        # the end, for all of them -- into four 863s of which three carried a
        # month and no year at all. Holdings filed under a month in no
        # particular year are worse than the warning that shape already had.
        if hr.start.has_enum() or not hr.start.year:
            return None                 # not a list of chronologies after all
        hr.raw = f"({part})"
        ranges.append(hr)

    # Non-consecutive runs, so each but the last ends at a gap. $w g, the same
    # break indicator the enumerated form of this already writes.
    for hr in ranges[:-1]:
        hr.break_after = "g"
    return ranges


def _parse_distributed_list(text: str,
                            warnings: Optional[List[str]] = None,
                            ) -> Optional[List[HoldingsRange]]:
    """
    One HoldingsRange per run of a discontinuous list, or None if it is not one.

    Every expanded statement has to parse.  A list the parser can read four
    fifths of is the case this whole area exists to refuse: the 866 is removed
    once anything is written from it, so the fifth run would be deleted rather
    than recorded.
    """
    read = _expand_distributed_list(text, warnings)
    if read is None:
        return None
    prefix, items, chrons, open_ended = read

    ranges: List[HoldingsRange] = []
    for i, (item, chron) in enumerate(zip(items, chrons)):
        last = i == len(items) - 1

        if prefix:
            # Written back out longhand and handed to the unit parser, so
            # everything it knows about captions, combined issues and seasons
            # applies unchanged.
            stmt = f"{prefix}{item}" + (f" ({chron})" if chron else "")
            if last and open_ended:
                stmt += "-"
            hr = _parse_one_range(stmt, warnings)
            if not (hr.start.has_enum() or hr.start.has_chron()):
                return None
            hr.raw = stmt
        else:
            # No caption anywhere in the list.  There is nothing to parse on the
            # enumeration side -- _LIST_ITEM_RE has already established that the
            # item is a plain value -- and the unit parser refuses a lone
            # captionless number by design, because on its own it says nothing
            # about which level it is.  Inside a list it is not on its own: it
            # is the only enumeration level there is, and the 853 writes "(*)"
            # for a level with no caption rather than guessing at one.
            shown: Set[str] = set()
            year, month, day = (_parse_chron(chron, warnings, shown) if chron
                                else (None, None, None))
            hr = HoldingsRange(
                start=EnumChron(enum=[EnumLevel(value=item)],
                                year=year, month=month, day=day,
                                demonstrated=shown),
                open_ended=last and open_ended,
                raw=item,
            )
        ranges.append(hr)

    for i in range(len(ranges) - 1):
        ranges[i].break_after = _gap_after(items[i], items[i + 1])
    return ranges


def _split_ranges(text: str) -> List[str]:
    """
    Split a holdings string into individual range strings.

    Splits on comma or semicolon that is:
      - NOT inside parentheses, AND
      - Followed by a volume-level caption (v., Vol., etc.) OR a bare year,
        OR preceded by a closing parenthesis.

    This avoids splitting "Vol. 1, No. 1 (Spring 1990)" on the comma
    between the volume and issue captions, and -- see
    _is_designation_prefix -- on the comma after a series designation.
    """
    # Collect candidate split positions
    depth = 0
    candidates: List[int] = []
    segment_start = 0
    chars = list(text)
    for i, ch in enumerate(chars):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif (ch == "/" and depth == 0
              and i > 0 and chars[i - 1].isspace()
              and i + 1 < len(chars) and chars[i + 1].isspace()):
            # A slash separates only when whitespace surrounds it.  A bare
            # slash carries meaning inside a statement -- combined issues
            # ("v.1/2"), combined months ("Jul./Aug."), split years
            # ("1990/91") -- and splitting on those would corrupt it.
            #
            # split_multi_range() in the detector has drawn this distinction
            # since 0.5.1; _split_ranges() never did, so
            # "v.1(1990)-v.3(1992) / v.5(1994)-v.8(1997)" reached _parse_unit()
            # as one unit and came out as "$a 1 $i 1990" -- one volume of the
            # eight it states.  None of the conditions below apply: unlike a
            # comma, a spaced slash is never part of a caption or a
            # designation, so there is nothing to disambiguate.
            candidates.append(i)
            segment_start = i + 1
        elif ch in (",", ";") and depth == 0:
            # Look back: is the preceding non-space character ")" or a digit?
            before = text[:i].rstrip()
            # Look ahead: what follows the separator?
            after = text[i + 1:].lstrip()
            preceded_by_close = before.endswith(")")
            followed_by_vol = bool(_VOL_START_RE.match(after))
            followed_by_year = bool(_YEAR_START_RE.match(after))
            # A mark with nothing after it closes the statement: the break
            # after its last run, which is how an ILS writes a gap after
            # "1986-1988" or "v.37-v.52" as surely as after "v.45(1988)".
            # Until the round trip checked it, only the last was read, and
            # "1986-1988," was refused whole.
            at_end = not after
            if not (preceded_by_close or followed_by_vol or followed_by_year
                    or at_end):
                continue
            if _is_designation_prefix(text[segment_start:i], after):
                continue
            candidates.append(i)
            segment_start = i + 1

    if not candidates:
        return [text.strip()]

    results = []
    prev = 0
    for pos in candidates:
        segment = text[prev:pos].strip()
        if segment:
            results.append(segment)
        prev = pos + 1
    segment = text[prev:].strip()
    if segment:
        results.append(segment)
    return results


def _split_with_separators(text: str) -> List[Tuple[str, str]]:
    """_split_ranges(), keeping the separator after each segment."""
    segments = _split_ranges(text)
    # Re-find the separators rather than re-deriving the split: the segments
    # are known, so the character after each one in the text is its separator.
    out: List[Tuple[str, str]] = []
    at = 0
    for seg in segments:
        found = text.find(seg, at)
        if found < 0:           # cannot happen for a segment taken from text
            out.append((seg, ""))
            continue
        at = found + len(seg)
        rest = text[at:].lstrip()
        out.append((seg, rest[0] if rest[:1] in (",", ";") else ""))
    return out


def _break_between(prev: "HoldingsRange", sep: str, nxt: Optional["HoldingsRange"]) -> str:
    """
    The $w a separator between two runs of one statement stands for.

    Z39.71: a comma marks a gap, a semicolon a break that is not a gap. A comma
    between two runs whose first-level numbering carries straight on is not
    written, the same test _gap_after() applies inside a list. At the end of a
    statement there is nothing to compare with, so the comma is taken at its
    word.
    """
    if sep == ";":
        return BREAK_NON_GAP
    if sep != ",":
        return ""
    if nxt is not None:
        last = prev.end if prev.end is not None else prev.start
        if last.enum and nxt.start.enum:
            ends = _FIRST_INT_RE.findall(last.enum[0].value or "")
            starts = _FIRST_INT_RE.findall(nxt.start.enum[0].value or "")
            if ends and starts and int(starts[0]) == int(ends[-1]) + 1:
                return ""
    return BREAK_GAP


def _chron_unit_value(raw: str) -> str:
    """
    MARC code for a month/season if recognised, else normalised text.
    Combined issues ('Jan/Feb') are encoded part-by-part ('01/02').
    """
    if "/" in raw:
        parts = [p for p in raw.split("/") if p.strip()]
        codes = [chron_unit_code(p) for p in parts]
        if all(c is not None for c in codes):
            return "/".join(codes)
    code = chron_unit_code(raw)
    return code if code is not None else normalise_chron_unit(raw)


def _parse_chron_single(raw: str,
                        warnings: Optional[List[str]] = None,
                        ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Parse ONE chronology boundary (no range hyphen), e.g.:
      '1990'  '1990:Mar.'  'Spring 1990'  '1990 Spring'  'Mar. 1990'  'Jan'
      'Apr 18, 1996'  -> ('1996', '04', '18')
    Returns (year, month_code_or_text, day).
    """
    raw = raw.strip()
    if not raw:
        return None, None, None

    # Bare year, including a split one ("1996/97")
    m = re.match(rf"^({_YEAR_TOKEN})$", raw)
    if m:
        return normalise_year(m.group(1)), None, None

    # Mon D, YYYY -- a day-level date.  Every other alternative here wants the
    # year adjacent to the month, so "Apr 18, 1996" matched none of them and
    # the whole boundary was returned as (None, None): the month and the year
    # went with the day.  All three levels are kept now; 863 $k holds the day.
    m = re.match(rf"^([A-Za-z.]+)\s+(\d{{1,2}})\s*,?\s+({_YEAR_TOKEN})$", raw)
    if m and chron_unit_code(m.group(1)) is not None:
        return (normalise_year(m.group(3)), _chron_unit_value(m.group(1)),
                m.group(2).lstrip("0") or "0")

    # YYYY:Mon. D -- Z39.71's year-first form with a day, as an ILS writes it
    # when it generates an 866 from an 863 carrying $k ("2014:Nov. 7", or
    # "2014:Nov.:7").
    m = re.match(rf"^({_YEAR_TOKEN})\s*:\s*([A-Za-z.]+)\s*[:\s]\s*(\d{{1,2}})$", raw)
    if m and chron_unit_code(m.group(2)) is not None:
        return (normalise_year(m.group(1)), _chron_unit_value(m.group(2)),
                m.group(3).lstrip("0") or "0")

    # YYYY:Mon. or YYYY Season (year first)
    m = re.match(rf"({_YEAR_TOKEN})\s*[:\s]\s*([A-Za-z./]+(?:\s+[A-Za-z./]+)?)$", raw)
    if m:
        return normalise_year(m.group(1)), _chron_unit_value(m.group(2)), None

    # Mon. YYYY or Season YYYY (chron before year)
    m = re.match(rf"([A-Za-z./]+(?:\s+[A-Za-z./]+)?)\s*[:\s]\s*({_YEAR_TOKEN})$", raw)
    if m:
        return normalise_year(m.group(2)), _chron_unit_value(m.group(1)), None

    # Mon D -- a day-level date with the year supplied by the other boundary
    # or by the block it sits in, e.g. the 'Jan 28' in '[Jan 28-Dec 29]'.
    m = re.match(r"^([A-Za-z.]+)\s+(\d{1,2})$", raw)
    if m and chron_unit_code(m.group(1)) is not None:
        return None, _chron_unit_value(m.group(1)), m.group(2).lstrip("0") or "0"

    # Bare month/season name (year supplied by the other boundary,
    # e.g. the 'Jan' in 'Jan-Jun 1984')
    m = re.match(r"^([A-Za-z./]+)$", raw)
    if m:
        return None, _chron_unit_value(m.group(1)), None

    return None, None, None


# "1960-66" is 1960 to 1966, written the way a cataloguer writes it. MARC
# wants both years in full, and until this existed the two-digit end was read
# as no year at all: "(1960-66)" produced "$i 1960" and the 66 went nowhere --
# no field, no warning, nothing held for review. Fifteen statements of a real
# 1057-statement file are written this way, and the conversion audit found nine
# of them the first time it ran.
_ABBREVIATED_END_YEAR_RE = re.compile(r"(?<!\d)(\d{4})(\s*-\s*)(\d{2})(?!\d)")


def _expand_abbreviated_end_year(raw: str,
                                 warnings: Optional[List[str]] = None) -> str:
    """
    "1960-66" -> "1960-1966", where two digits can only be a year.

    Two digits after a four-digit year and a hyphen are ambiguous in principle:
    "1990-12" could be 1990 to 2012, or December 1990 written the ISO way. The
    two cases separate cleanly, because a month cannot exceed 12 -- so a value
    above 12 is expanded, and one at or below it is left alone and *said*,
    rather than guessed at in either direction. Neither the corpus nor the
    1057-statement file this was measured against contains the ambiguous form;
    it is handled because leaving it to drop silently is what went wrong here
    in the first place.
    """
    def expand(match: "re.Match") -> str:
        start, dash, short = match.group(1), match.group(2), match.group(3)
        # Months run 01-12, so "00" is not one and "1999-00" is unambiguous:
        # 1999 to 2000. Only a value that could actually be a month is left
        # for the cataloguer to settle.
        if 1 <= int(short) <= 12:
            note = (f"'{start}-{short}' could be {start} to a year ending "
                    f"{short}, or month {short} of {start}. Neither was "
                    "assumed, so the second half is not encoded.")
            if warnings is not None and note not in warnings:
                warnings.append(note)
            return match.group(0)
        end = int(start) // 100 * 100 + int(short)
        if end < int(start):
            end += 100                  # "1999-00" is 1999 to 2000
        return f"{start}{dash}{end}"

    return _ABBREVIATED_END_YEAR_RE.sub(expand, raw)


def _parse_chron(raw: str,
                 warnings: Optional[List[str]] = None,
                 demonstrated: Optional[Set[str]] = None,
                 ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Parse a chronology string, including ranges within a single group:
      '1990'          -> ('1990', None)
      '1990:Mar.'     -> ('1990', '03')
      'Jan-Jun 1984'  -> ('1984', '01-06')     # year shared across range
      'Jan 1990-Dec 1994' -> ('1990-1994', '01-12')
      'Jan 1956-Jan 1957' -> ('1956-1957', '01-01')   # both ends named, kept
      '1981-Sep 1996' -> ('1981-1996', None)   # one end only: cannot be placed
      '1990-1994'     -> ('1990-1994', None)
    Months and seasons are returned as MARC chronology codes
    (01-12, seasons 21-24) for use in 863 $j; a day, when the statement gives
    one, goes to 863 $k.
    Returns (year, month, day).
    """
    raw = _expand_abbreviated_end_year(raw.strip(), warnings)

    if "-" in raw:
        left, right = (p.strip() for p in raw.split("-", 1))
        # More than one hyphen: one end carries a range of its own, "Mar
        # 1978-Oct-Dec 1986". The first hyphen made the end "Oct-Dec 1986",
        # which no single boundary reads, and the end year and every month
        # went (the cataloguer's report, 0.29.0). The dividing hyphen is the
        # one with a whole date -- a year in it -- on each side.
        # The end's own range comes back paired ("10-12"), and the converter
        # reduces the run to its outer ends and says so.
        start_read = end_read = None
        if raw.count("-") > 1:
            for hyphen in re.finditer("-", raw):
                l_part = raw[:hyphen.start()].strip()
                r_part = raw[hyphen.end():].strip()
                start = _parse_chron(l_part) if "-" in l_part \
                    else _parse_chron_single(l_part)
                inner = _parse_chron(r_part) if "-" in r_part \
                    else _parse_chron_single(r_part)
                if all(side[0] and side[0] != text and "-" not in side[0]
                       for side, text in ((start, l_part), (inner, r_part))):
                    left, start_read, end_read = l_part, start, inner
                    break
        l_year, l_month, l_day = start_read or _parse_chron_single(left, warnings)
        r_year, r_month, r_day = end_read or _parse_chron_single(right, warnings)

        # Year: share the right-hand year if the left boundary omits it.
        # Equal years collapse: the year is the most significant chronology
        # level, so there is nothing above it whose endpoints a repeat would
        # be pairing with.
        if l_year and r_year:
            year = l_year if l_year == r_year else f"{l_year}-{r_year}"
        else:
            year = l_year or r_year

        month = _pair_or_drop(l_month, r_month, raw, "month or season", warnings,
                              demonstrated, "month")
        # The day follows exactly the same rule, and for the same reason: a
        # lone '18' in $k pairs positionally with whatever $i and $j hold, so
        # it would claim a precision the other end of the range never gave.
        day = _pair_or_drop(l_day, r_day, raw, "day", warnings,
                            demonstrated, "day")

        # Equal ends collapse where nothing above them ranges -- D15's own
        # rule. "Jan 1956-Jan 1957" keeps "01-01", because the year ranges and
        # a lone "01" would pair with only one end of it; "Oct 7-Oct 21, 1993"
        # is October at both ends of one year, and "$j 10" says so. Writing
        # "10-10" was not wrong, but an 866 generated from it reads back as
        # "10", and the round trip reported the difference as drift.
        year_ranges = bool(l_year and r_year and l_year != r_year)
        if not year_ranges and l_month and l_month == r_month:
            month = l_month
            if l_day and l_day == r_day:
                day = l_day

        if year or month or day:
            return year, month, day
        return raw, None, None  # unparseable: preserve raw so nothing is lost

    year, month, day = _parse_chron_single(raw, warnings)
    if year or month or day:
        return year, month, day

    # Give up - return raw as year string so the data is not dropped
    return raw, None, None


def _pair_or_drop(left: Optional[str], right: Optional[str], raw: str,
                  what: str, warnings: Optional[List[str]],
                  demonstrated: Optional[Set[str]] = None,
                  level: Optional[str] = None) -> Optional[str]:
    """
    Join the two ends of one chronology level, or drop a value only one gives.

    Two ends naming the same month keep both -- "Jan 1956 - Jan 1957" is
    '01-01', not '01'.  Collapsing it lost the pairing with the years either
    side, leaving "$i 1956-1957 $j 01", which reads as one January spanning two
    years.

    One end naming a value and the other not -- "1981 - Sep 1996", "Aug
    1984-1985" -- cannot be recorded at all.  A reader pairs the subfields
    positionally, so "$i 1981-1996 $j 09" says the run *begins* in September
    1981, which the statement never claimed.  There is no notation for a
    chronology belonging to one end only, so the value is dropped and named.
    This is the only place that can tell the two cases apart: by the time the
    converter sees a lone '09' it cannot know whether the other end said the
    same thing or said nothing.
    """
    if left and right:
        return f"{left}-{right}"
    if not (left or right):
        return None
    lone = left or right
    # The value goes; the level stays.  One end of this range said the serial
    # is numbered by month -- that is true of the serial however little of it
    # this range can record, and the 853 has to say so.
    if demonstrated is not None and level and demonstrates_level(level, lone):
        demonstrated.add(level)
    if warnings is not None:
        note = (
            f"Only one end of '{raw}' gives a {what} ({lone}); with nothing at "
            "the other end it cannot be recorded as a range, so it was left out."
        )
        if note not in warnings:
            warnings.append(note)
    return None


def _parse_unit(text: str,
                warnings: Optional[List[str]] = None,
                ) -> Optional[EnumChron]:
    """
    Parse a single enumeration+chronology unit (one boundary of a range).
    Returns None if nothing meaningful is found.
    """
    text = text.strip()
    if not text:
        return None

    # Year-only shorthand.  Normalised like every other year: 0.8.1 taught the
    # parser to read a year written across the turn of one ("1996/97" is the
    # single publication year 1996/1997), and _parse_chron() does it at all four
    # of its sites.  This one was missed, so a statement that is *only* a year
    # kept the raw text -- and the year subfield holds four-digit years, so
    # "1996/97" was then refused and named, from a statement with nothing else
    # in it to convert.
    m = _YEAR_ONLY_RE.match(text)
    if m:
        return EnumChron(year=normalise_year(m.group(1)))

    if _BARE_CHRON_RE.match(text):
        year, month, day = _parse_chron_single(text, warnings)
        if year and (month or day):
            return EnumChron(year=year, month=month, day=day)

    lead = _YEAR_BEFORE_VOLUME_RE.match(text)
    if lead:
        rest = _parse_unit(text[lead.end():], warnings)
        if rest is None:
            return None
        if rest.year:
            # A second year after the volume: two dates for one unit, which
            # is not a reading to guess between. Refused whole, and said.
            if warnings is not None:
                note = (f"'{text}' gives the year twice, before and after the "
                        "volume — nothing was converted from this statement "
                        "rather than guess which is meant.")
                if note not in warnings:
                    warnings.append(note)
            return None
        rest.year = normalise_year(lead.group(1))
        return rest

    levels, pos = _parse_enum_levels(text)

    rest = text[pos:].lstrip()
    consumed = len(text) - len(rest)
    chron = _CHRON_BLOCK_RE.match(rest)
    if chron and chron.group("chron_raw").rstrip().endswith("-"):
        # An open end inside the dates of a unit that is not the whole
        # statement, "v.1(1990)-v.5(1994-)". _parse_one_range moves it out
        # where there is only one unit; here it has nowhere to go, and the
        # date reader would drop it without a word.
        if warnings is not None:
            note = (f"'{text}' leaves its dates open inside the parentheses, "
                    "where an open end cannot be recorded — nothing was "
                    "converted from this statement rather than drop it.")
            if note not in warnings:
                warnings.append(note)
        return None
    if chron:
        consumed += chron.end()

    if not levels and not chron:
        return None

    # The match has to account for the whole unit, whether or not a caption is
    # present.  In "v. 19 nos. 1, 3, 5, 7-12 (Jan, Mar, May, Jul-Dec 1915)" it
    # reaches only as far as "v. 19 nos. 1", and in "v. 58 Suppl. (Sep 2003)"
    # only as far as "v. 58"; converting either alone is worse than converting
    # nothing, because the 866 is removed once anything is written from it and
    # the rest of the statement goes with it.
    if consumed != len(text):
        if warnings is not None:
            note = (
                f"Read '{text[:consumed].strip()}' but could not account for "
                f"'{text[consumed:].strip()}' — nothing was converted from this "
                "statement rather than convert part of it."
            )
            if note not in warnings:
                warnings.append(note)
        return None

    # A number with no caption of its own is only an enumeration level when
    # something else in the statement says so: a captioned level must follow
    # it.  "39 no 1" is v.39 no.1, because a number sitting a level above an
    # issue is a volume.  Without that anchor there is nothing to read the
    # level from, and "2016?" would become a volume rather than an uncertain
    # year.
    if levels and levels[0].caption is None and len(levels) == 1:
        return None

    ec = EnumChron(enum=levels)

    if chron:
        ec.year, ec.month, ec.day = _parse_chron(
            chron.group("chron_raw"), warnings, ec.demonstrated)

    # A boundary whose chronology was entirely dropped still demonstrates the
    # levels it named, so it is not empty even though every value went.
    return ec if (ec.has_enum() or ec.has_chron() or ec.demonstrated) else None


# Chronology written after the enumeration without parentheses, as older
# summary statements have it: "v.3-36 1963-1995", "v.40 no.4-6 2003.",
# "v.1-8 no.3 1987-August 1994". It means what "v.3-36 (1963-1995)" means, and
# is read as that. The two halves are told apart by what each can hold: the
# enumeration opens with a caption and ends on a value; the dates open with a
# four-digit year, or a month or season before one, and run to the end with no
# caption in them. A statement that already has parentheses is left alone, and
# anything these do not describe -- "v.1// 1982//", "2016 ed." -- is refused
# as before.
_UNBRACKETED_CHRON_RE = re.compile(
    rf"""^(?P<enum>(?:{_CAPTION_ALT})(?![a-z]).*?\d[a-zA-Z]?)
         \s+
         (?P<chron>(?:[A-Za-z]+\.?(?:/[A-Za-z]+\.?)*\s+)?\d{{4}}(?!\d)[A-Za-z0-9\s./:-]*?)
         \s*\.?\s*$""",
    re.IGNORECASE | re.VERBOSE,
)
_CAPTION_IN_CHRON_RE = re.compile(rf"(?<![A-Za-z])(?:{_CAPTION_ALT})\s*\.?\s*\d",
                                  re.IGNORECASE)


def _bracket_trailing_chron(raw: str) -> str:
    """ "v.3-36 1963-1995" -> "v.3-36 (1963-1995)"; anything else unchanged."""
    if "(" in raw or ")" in raw:
        return raw
    m = _UNBRACKETED_CHRON_RE.match(raw.strip())
    if not m:
        return raw
    chron = m.group("chron").strip()
    # Every word in it has to be a month or a season: "v.1 2000 copies" is
    # not a date.
    if (_CAPTION_IN_CHRON_RE.search(chron)
            or any(chron_unit_code(w) is None
                   for w in re.findall(r"[A-Za-z]+", chron))):
        return raw
    # An open end stays outside the parentheses, where it is read as one:
    # "v.35 2025-" is "v.35 (2025)-", not a year with a dangling hyphen.
    # Only after a single volume, though: "v.1-3 1990-" does not say whether
    # the run of volumes or the holding is what is open, and is refused.
    if chron.endswith("-"):
        if "-" in m.group("enum"):
            return raw
        return f"{m.group('enum')} ({chron[:-1].rstrip()})-"
    return f"{m.group('enum')} ({chron})"


def _parse_one_range(raw: str,
                     warnings: Optional[List[str]] = None,
                     ) -> HoldingsRange:
    """
    Parse a single range string like:
      "v.1:no.1(1990:Jan.)-v.5:no.4(1994:Dec.)"
      "v.6(1995)-"    (open-ended)
    """
    raw = raw.strip()
    hr = HoldingsRange(raw=raw)
    raw = _bracket_trailing_chron(raw)

    # The open end written inside the parentheses, "v.35 (2025-)", is the
    # same holding as "v.35(2025)-". Read inside, the hyphen had nothing after
    # it and was dropped without a word: "$a 35 $i 2025", a closed holding.
    # Moved out when the statement is one unit; with an end unit after it,
    # "v.1(1990)-v.5(1994-)", there is no reading to move it to, and the
    # unit parser refuses it.
    inside = re.search(r"-\s*\)\s*$", raw)
    if inside:
        moved = raw[:inside.start()].rstrip() + ")"
        if len(_smart_split_range(moved)) == 1:
            raw = moved + "-"

    # Check for open-ended (ends with bare "-")
    open_ended = bool(re.search(r"-\s*$", raw))
    if open_ended:
        raw_trimmed = re.sub(r"-\s*$", "", raw).strip()
        hr.open_ended = True
    else:
        raw_trimmed = raw

    # Split on the range separator "-" that lies between two units.
    # Strategy: split on " - " or hyphen NOT inside parentheses and not
    # part of a number like "no.1-4".
    #
    # We find the "-" that separates two major enum-chron units by
    # scanning for a hyphen that is:
    #   1. Not inside parentheses
    #   2. Preceded by a digit or ")"
    #   3. Followed by a letter (start of a caption) or digit or whitespace
    parts = _smart_split_range(raw_trimmed)

    if len(parts) == 1:
        start = _parse_unit(parts[0], warnings)
        if start and open_ended and _has_inner_range(start):
            # "v.1-3 (1990)-", "v.1 (1990-1992)-": a run already, then open.
            # A compressed 863 has one hyphen per subfield, so the open end
            # could only be written as "$a 1-3-" -- and the statement does not
            # say whether the volumes run on from 3 or the holding from 1990.
            if warnings is not None:
                note = (f"'{hr.raw}' gives a run and then leaves it open, so "
                        "which part is still being received cannot be told "
                        "from the statement — nothing was converted from this "
                        "statement rather than guess.")
                if note not in warnings:
                    warnings.append(note)
            return hr
        hr.start = start or EnumChron()
    elif len(parts) >= 2:
        start = _parse_unit(parts[0], warnings)
        end = _parse_unit(parts[1], warnings)
        if end is None:
            # _parse_unit() refuses a unit it can only read part of, and says
            # so: "nothing was converted from this statement rather than
            # convert part of it".  Keeping the start made that untrue -- the
            # statement above wrote "$a 1 $i 1990" under a warning saying
            # nothing had been written, and was neither held nor flagged, so
            # nobody would have looked.  Refusing the range is what the
            # message has always claimed happens.
            return hr
        hr.start = start or EnumChron()
        hr.end = end

    hr.align_boundaries()
    return hr


def _has_inner_range(unit: "EnumChron") -> bool:
    """Whether any value in one boundary is already a run: "1-3", "1990-1992"."""
    values = [lvl.value for lvl in unit.enum] + [unit.year, unit.month, unit.day]
    return any(v and "-" in v for v in values)


def _smart_split_range(text: str) -> List[str]:
    """
    Split "start-end" at the hyphen separating the two major units.
    Handles hyphens inside parentheses (chronology ranges like 1990-1994
    inside parens) and compressed formats like "v.1-5(1990-1994)".
    """
    depth = 0
    candidate_positions = []
    for i, ch in enumerate(text):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "-" and depth == 0:
            candidate_positions.append(i)

    if not candidate_positions:
        return [text]

    # "1990: v.1-1992: v.3": a hyphen followed by a year and then a volume
    # opens the second unit, as surely as one followed by the volume itself.
    for pos in candidate_positions:
        if _YEAR_BEFORE_VOLUME_RE.match(text[pos + 1:]) \
                and _YEAR_BEFORE_VOLUME_RE.match(text):
            return [text[:pos].strip(), text[pos + 1:].strip()]

    # Two bare Z39.71 chronologies, "1990:Jan.-1994:Dec.": the hyphen between
    # them is the only one that can divide the statement.
    bare = _BARE_CHRON_RANGE_RE.match(text)
    if bare and (_BARE_CHRON_RE.match(text[:bare.start(1)])
                 or _BARE_CHRON_RE.match(text[bare.end(1):])):
        return [text[:bare.start(1)].strip(), text[bare.end(1):].strip()]

    # Prefer the split that produces two non-trivial units.
    # Heuristic: prefer positions where the character before is ")" or digit
    # and after is alpha (start of caption) or "(" or digit.
    #
    # The neighbours are the nearest *non-space* characters, not the adjacent
    # ones. "v. 1 (2001) - v. 5 (2005)" is written with spaces around its
    # separator at least as often as without, and reading the spaces themselves
    # matched no rule: the statement parsed as a single unit, the end of the
    # range was dropped, an 863 was produced for the start alone, and the 866
    # was then removed as converted -- losing the holdings with no warning.
    best = None
    for pos in candidate_positions:
        before = text[:pos].rstrip()[-1:]
        after = text[pos + 1:].lstrip()[:1]
        if before in (")", ) or (before.isdigit() and after.isalpha()):
            best = pos
            break
        # Fallback: any hyphen between digit and alpha
        if before.isdigit() and after.isalpha():
            best = pos
            break

    if best is None:
        # Year-only range shorthand ("1990-1994") still splits on its hyphen.
        if re.fullmatch(rf"\s*{_YEAR_TOKEN}\s*-\s*{_YEAR_TOKEN}\s*", text):
            best = candidate_positions[0]
        else:
            # Every remaining candidate is a digit-digit hyphen, i.e. a
            # range WITHIN one caption level ("nos. 1-6", "v.1-5") rather
            # than a start/end separator.  Parse the string as one unit
            # and let _ENUM_CHRON_RE capture the range tokens.
            return [text]

    left = text[:best].strip()
    right = text[best + 1:].strip()
    return [left, right] if right else [left]


# ---------------------------------------------------------------------------
# Block ("chronology-first") format
# ---------------------------------------------------------------------------
#
# A second holdings grammar, common in older and locally-maintained records:
#
#     1993: (1 [Feb])
#     2019: (1-6 [Feb-Nov])2020: (7-12 [Jan-Dec])2021: (13-15 [Feb-Jun])
#     1949: 1 (1-6 [Apr-Sep])
#     N2002: ([Mar], [Jul], [Aug])2005: ([Aug])
#
# Year comes first, then an optional volume, then a parenthesised body of
# comma-separated "issue [chronology]" items.  Blocks repeat with no separator
# between them, and each item becomes its own 863.
#
# This is a different grammar from _ENUM_CHRON_RE above, not a looser version
# of it, so it gets its own parser and is dispatched by _looks_like_block().

_BLOCK_RE = re.compile(
    r"""
    (?P<marker>[NM])?\s*                 # unexplained local marker
    (?P<year>\d{4}|\?)\s*:?\s*           # year, or '?' for unknown
    (?:v(?:ol(?:ume)?)?\.?\s*)?          # optional volume caption
    (?P<vol>\d+)?\s*                     # volume number, outside the parens
    \(\s*(?P<body>[^()]*(?:\([^()]*\)[^()]*)*)\)
    """,
    re.IGNORECASE | re.VERBOSE,
)

# One item inside a block body: "1-4 [Jan 5-Jan 26]", "[Aug]", "12"
_BLOCK_ITEM_RE = re.compile(
    r"(?P<iss>\d+[a-z]?(?:\s*-\s*\d+[a-z]?)?)?\s*"
    r"(?:\[(?P<chron>[^\]]*)\])?",
    re.IGNORECASE,
)

# Split a block body on commas that are not inside a [...] chronology group
_BLOCK_BODY_SPLIT_RE = re.compile(r",(?![^\[]*\])")

# A statement is in block format when it opens with "YEAR:" or "?:"
# The year-first grammar opens "year:" and then a volume or a parenthesised
# body -- "1993: (1 [Feb])", "1949: 1 (1-6 [Apr-Sep])". A word after the colon
# is Z39.71's own chronology, "1990:Jan.-1994:Dec.", which this used to claim
# and convert to nothing (D31).
_BLOCK_SNIFF_RE = re.compile(r"^\s*[NM]?\s*(?:\d{4}|\?)\s*:(?!\s*[A-Za-z])",
                             re.IGNORECASE)

# Curly-brace cataloguer notes: "{Memorial Issue}", "{2nd printing}"
_BRACE_NOTE_RE = re.compile(r"\{([^}]*)\}?")


def _excise_brace_notes(text: str) -> tuple[str, List[str]]:
    """
    Lift cataloguer notes out of a statement so the holdings can be read.

    The note was already reported before this existed -- and then the statement
    was parsed with the note still in it, so the grammar met text it had no
    rule for and returned nothing. "1993: {Memorial Issue} (1 [Feb])" warned
    that the note was preserved and then found no block at all, which loses the
    holdings to say something about the note. The same statement without the
    note parses perfectly.

    Rule 4 is what decides the shape of this: a note is *encoded*, *deliberately
    dropped with a reason*, or *held for review*, and never a fourth thing. It
    is dropped with a reason, which is what the warning is, and what remains is
    the statement the cataloguer actually recorded holdings in.

    "{lcub}" and "{rcub}" are left alone. They are MARC's escapes for a literal
    brace, not notes, and reading one as a note would delete a character the
    cataloguer typed on purpose.
    """
    if "{" not in text:
        return text, []

    notes: List[str] = []

    def take(match: "re.Match") -> str:
        body = match.group(1).strip()
        if body.lower() in ("lcub", "rcub"):
            return match.group(0)          # a literal brace, not a note
        if body:
            note = f"Cataloguer note preserved, not encoded: '{body}'."
            if note not in notes:
                notes.append(note)
        return " "

    cleaned = _BRACE_NOTE_RE.sub(take, text)
    # Excising from the middle leaves a gap that the grammars would otherwise
    # read as a separator.
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return (cleaned or text), notes


def _looks_like_block(text: str) -> bool:
    """True when `text` uses the chronology-first block grammar."""
    return bool(_BLOCK_SNIFF_RE.match(text))


def _bracket_chron_unit(raw: str) -> Tuple[Optional[str], Optional[str]]:
    """
    MARC chronology for one side of a bracketed group, as (month, day).

    'Jun 1'    -> ('06', '1')
    'Jul/Aug'  -> ('07/08', None)   (combined issue, via _chron_unit_value)
    'summer'   -> ('22', None)
    'Sum'      -> ('Sum', None)     (unrecognised: preserved, not dropped)
    """
    raw = raw.strip()
    if not raw:
        return None, None
    m = re.match(r"([A-Za-z]+(?:\s*/\s*[A-Za-z]+)*)\s*(\d{1,2})?", raw)
    if not m:
        return None, None
    month = _chron_unit_value(re.sub(r"\s*", "", m.group(1)))
    day = (m.group(2) or "").lstrip("0") or m.group(2)
    return month, day or None


def _parse_bracket_chron(raw: str) -> Tuple[Tuple[Optional[str], Optional[str]],
                                            Tuple[Optional[str], Optional[str]]]:
    """
    Parse a bracketed chronology group into ((start month, day), (end month, day)).

    '[Feb]'            -> (('02', None),  (None, None))
    '[Feb-Nov]'        -> (('02', None),  ('11', None))
    '[Jan 5-Jan 26]'   -> (('01', '5'),   ('01', '26'))
    '[Jul/Aug]'        -> (('07/08', None), (None, None))
    """
    raw = raw.strip()
    if not raw:
        return (None, None), (None, None)
    if "-" in raw:
        left, right = (p.strip() for p in raw.split("-", 1))
        return _bracket_chron_unit(left), _bracket_chron_unit(right)
    return _bracket_chron_unit(raw), (None, None)


def _drop_unfilled_top_level(ranges: List[HoldingsRange]) -> None:
    """
    Remove a placeholder level no block in the statement ever fills.

    The empty level exists to keep a block that omits its higher level in step
    with one that states it -- the two "2"s of
    "N1984: (2 (1))M1985: 2 (2 [summer])" are the same level and belong in the
    same subfield.  Where *no* block states it there is nothing to be in step
    with, and declaring it anyway would put a level in the 853 that the serial
    does not have: "1993: (1 [Feb])" would produce "$a (*) $b (*)" over an 863
    filling only $b.
    """
    if not any(len(hr.start.enum) > 1 for hr in ranges):
        return
    if any(hr.start.value_at(0) for hr in ranges):
        return
    for hr in ranges:
        if hr.start.enum and hr.start.enum[0].value is None:
            hr.start.enum = hr.start.enum[1:]


def _parse_block_format(text: str) -> ParseResult:
    """
    Parse the chronology-first block grammar into HoldingsRange objects.

    Role assignment is positional and therefore determinate: a number *before*
    the parentheses is the volume, numbers *inside* are issues.  Statements
    whose numbers sit in neither position are left unconverted and flagged for
    review rather than guessed at.
    """
    result = ParseResult(raw=text)

    for note in _BRACE_NOTE_RE.findall(text):
        if note.strip():
            result.warnings.append(f"Cataloguer note preserved, not encoded: '{note.strip()}'.")

    markers = sorted({m.group("marker").upper()
                      for m in _BLOCK_RE.finditer(text) if m.group("marker")})
    if markers:
        result.warnings.append(
            f"Unexplained marker(s) {', '.join(markers)} found before the year — "
            "parsed around them; meaning not encoded."
        )

    for blk in _BLOCK_RE.finditer(text):
        year = blk.group("year")
        year = None if year == "?" else year
        vol = blk.group("vol")
        body = blk.group("body") or ""

        items = [i for i in _BLOCK_BODY_SPLIT_RE.split(body) if i.strip()]
        if not items:
            items = [""]          # "(...)" with nothing usable inside

        for item in items:
            item = item.strip()
            # A nested group -- the "(1)" in "N1984: (2 (1))" -- is not part of
            # the issue-and-chronology shape this grammar reads, and its meaning
            # is local to whoever wrote it. Named rather than dropped in
            # silence; guessing at it would be worse.
            nested = re.search(r"\(([^()]*)\)", item)
            if nested and nested.group(1).strip():
                note = (f"Nested group '({nested.group(1).strip()})' inside "
                        f"'{item}' is not encoded.")
                if note not in result.warnings:
                    result.warnings.append(note)

            im = _BLOCK_ITEM_RE.match(item)
            if not im:
                continue
            issue = (im.group("iss") or "").strip() or None
            (c_start, d_start), (c_end, d_end) = \
                _parse_bracket_chron(im.group("chron") or "")

            if not any([vol, issue, year, c_start]):
                continue

            # Positional, and it always was: a number *before* the parens is
            # the higher level and numbers *inside* are the lower one.
            #
            # Which means the lower one keeps its position when the higher is
            # absent.  Appending both in turn shifted it up instead, so
            # "N1984: (2 (1))M1985: 2 (2 [summer])" put the 1984 issue in $a and
            # the 1985 issue in $b -- the same level of the same serial in two
            # subfields, under an 853 that then read "$a no. $b no.", two levels
            # with one name.  An empty level holds the place the block omits.
            #
            # Neither level is captioned, because the format names neither.  It
            # is positional notation; reading "volume" and "issue" out of it was
            # the tool supplying two words the record never used, and the 853
            # writes NO_CAPTION for a level nobody has named.  A cataloguer who
            # knows this house format can set the captions once in the settings,
            # which is a stated choice rather than a hidden default.
            enum: List[EnumLevel] = []
            if vol:
                enum.append(EnumLevel(value=vol))
            if issue:
                if not vol:
                    enum.append(EnumLevel())
                enum.append(EnumLevel(value=issue))
            start = EnumChron(enum=enum, year=year, month=c_start, day=d_start)
            # The end boundary exists when either chronology level differs:
            # "[Jan 5-Jan 26]" is one month and two days, and dropping the end
            # because the months match would lose the second day.
            end = (EnumChron(month=c_end, day=d_end)
                   if (c_end and c_end != c_start) or (d_end and d_end != d_start)
                   else None)
            result.ranges.append(
                HoldingsRange(start=start, end=end, raw=item or body.strip())
            )

    if result.ranges:
        _drop_unfilled_top_level(result.ranges)
        return result

    # ── Degenerate forms: "?: 2", "?: 16" — a value with no positional
    # evidence for whether it is a volume or an issue.  Extract it so it is
    # visible, but do not convert it.
    m = re.match(r"^\s*[NM]?\s*(?:(?P<year>\d{4})|\?)\s*:\s*(?P<num>\d+)\s*$", text)
    if m:
        result.needs_review = True
        result.success = False
        result.warnings.append(
            f"Found the number '{m.group('num')}' but nothing indicates whether it is "
            "a volume or an issue — left unconverted for review."
        )
        return result

    result.success = False
    result.warnings.append(
        "Looks like a year-first holdings statement but no usable block was found."
    )
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_866(text: str) -> ParseResult:
    """
    Parse a MARC 866 $a textual holdings string.

    Returns a ParseResult with one or more HoldingsRange objects and
    any warnings generated during parsing.

    Examples
    --------
    >>> r = parse_866("v.1:no.1(1990:Jan.)-v.5:no.4(1994:Dec.)")
    >>> r.ranges[0].start.enum[0].value
    '1'
    >>> r.ranges[0].end.year
    '1994'
    """
    result = ParseResult(raw=text)

    if not text or not text.strip():
        result.success = False
        result.warnings.append("Empty holdings string.")
        return result

    # Notes come out before either grammar sees the statement, because both
    # were defeated by one: the note is reported and the holdings around it are
    # read, rather than the note costing the whole statement.
    cleaned, note_warnings = _excise_brace_notes(text)

    # Chronology-first records use a different grammar entirely; dispatch
    # before the enumeration-first path rather than trying to widen it.
    if _looks_like_block(cleaned):
        block = _parse_block_format(cleaned)
        block.raw = text          # what the cataloguer wrote, notes and all
        block.warnings = note_warnings + [w for w in block.warnings
                                          if w not in note_warnings]
        return block

    result.warnings.extend(note_warnings)

    # Notes from the unit parser are kept apart from the segment-level ones.
    # They say *why* a unit was refused, which is worth carrying onto the
    # degenerate path -- a truncated statement otherwise reports only "no
    # recognisable holdings ranges", which does not say that most of one was
    # read and deliberately not converted. The generic per-segment line is not
    # worth carrying: on that path it only repeats what the degenerate result
    # already says.
    segments = _split_with_separators(cleaned)
    notes: List[str] = []
    # (last range read from a segment, the separator after that segment), for
    # the $w each separator stands for once the next segment is read.
    pending_break: List[Tuple["HoldingsRange", str]] = []
    for seg, sep in segments:
        before = len(result.ranges)
        _read_segment(seg, result, notes)
        if len(result.ranges) > before:
            if pending_break:
                prev, prev_sep = pending_break.pop()
                if not prev.break_after:
                    prev.break_after = _break_between(
                        prev, prev_sep, result.ranges[before])
            pending_break = [(result.ranges[-1], sep)] if sep else []
    if pending_break:
        prev, prev_sep = pending_break.pop()
        if not prev.break_after:
            prev.break_after = _break_between(prev, prev_sep, None)

    result.warnings.extend(w for w in notes if w not in result.warnings)

    if not result.ranges:
        # The statement with its notes taken out, as both grammars read it:
        # given the raw text, "2016? {gift}" matched nothing here and the note
        # was reported nowhere.
        degenerate = _parse_degenerate(cleaned)
        degenerate.raw = text
        degenerate.warnings[:0] = note_warnings
        # Why the unit parser refused is worth carrying only when nothing was
        # converted after all. Where the last resort did read something --
        # "2016?", a year -- that refusal ends "nothing was converted from this
        # statement", beside a year that was, and the "?" it points at is
        # already named by the last resort's own warning.
        # Nor when the statement is an 863 written out as text: the unit
        # parser's "Read '2' but could not account for '.1 54-62 ...'" points
        # at a place reading never stopped for a reason, and the last resort
        # says what the text is.
        if not degenerate.ranges and not _looks_like_863_values(cleaned):
            degenerate.warnings.extend(w for w in notes
                                       if w not in degenerate.warnings)
        return degenerate

    return result


def _read_segment(seg: str, result: "ParseResult", notes: List[str]) -> None:
    """Read one segment of a statement into `result`, as parse_866 always has."""
    seg_notes: List[str] = []

    # A segment listing several discontinuous runs is several ranges, and
    # MARC records them as several 863s.  Tried before the unit parser
    # because the unit parser reads the first run and refuses the rest.
    listed = _parse_distributed_list(seg, seg_notes)
    if listed is not None:
        notes.extend(w for w in seg_notes if w not in notes)
        result.ranges.extend(listed)
        return

    # A list stated as chronology alone, "(1986-1988, 1993-1994)". Tried
    # before the unit parser for the same reason the enumerated list is:
    # the unit parser reads the first run and drops the rest.
    seg_notes = []
    chron_runs = _parse_chronology_list(seg, seg_notes)
    if chron_runs is not None:
        notes.extend(w for w in seg_notes if w not in notes)
        result.ranges.extend(chron_runs)
        return

    seg_notes = []
    hr = _parse_one_range(seg, seg_notes)
    notes.extend(w for w in seg_notes if w not in notes)
    if not hr.start.has_enum() and not hr.start.has_chron():
        result.skipped_segments.append(seg)
        result.warnings.append(
            f"Could not parse segment: '{seg}' — it will be skipped."
        )
        return
    result.ranges.append(hr)


# An 863 written out as text, codes gone: "2.1 54-62 1-1 1998-2006 21-21 g" is
# $8 2.1 $a 54-62 $b 1-1 $i 1998-2006 $j 21-21 $w g. A link number first, then
# at least two values, a break code or a full stop, and perhaps a note after.
# Found in another library's catalogue (D33), where it looks like encoded
# holdings that were never turned back into display text.
_863_VALUE = r"(?:-?\d+(?:[-/]\d+)*-?|[gn]|\.)"
_863_AS_TEXT_RE = re.compile(
    rf"^\s*(?P<link>\d+\.\d+)\s+{_863_VALUE}(?:\s+{_863_VALUE})+(?:\s+\D.*)?$")


def _looks_like_863_values(text: str) -> bool:
    m = _863_AS_TEXT_RE.match(text)
    return bool(m) and len(re.findall(r"\d+", text[m.end("link"):])) >= 2


def _parse_degenerate(text: str) -> ParseResult:
    """
    Last resort for single-value statements that neither grammar accepts:
    "2016?", "? 106", "?: 16".

    A year alone is usable holdings data.  A bare number is not — nothing says
    which level it belongs to — so it is surfaced for review, never guessed.
    """
    result = ParseResult(raw=text)

    m = re.match(r"^\s*(?P<year>\d{4})\s*\?\s*$", text)
    if m:
        result.ranges.append(HoldingsRange(
            start=EnumChron(year=m.group("year")), raw=text.strip()
        ))
        result.warnings.append(
            f"Year '{m.group('year')}' recorded as uncertain ('?') in the source; "
            "the qualifier is not encoded."
        )
        return result

    m = re.match(r"^\s*\??\s*(?P<num>\d+)\s*$", text)
    if m:
        result.needs_review = True
        result.success = False
        result.warnings.append(
            f"Found the number '{m.group('num')}' but nothing indicates whether it is "
            "a volume, an issue or a year — left unconverted for review."
        )
        return result

    result.success = False
    if _looks_like_863_values(text):
        # Said plainly, because the generic message and "Read '2' but could
        # not account for '.1 54-62 ...'" both point at the wrong thing. The
        # values could be lined up with subfields, but what each one counts
        # was in the 853, which is not in the text, and captions are not
        # guessed.
        link = _863_AS_TEXT_RE.match(text).group("link")
        result.warnings.append(
            f"This looks like the values of an 863 written out as text "
            f"(starting with its link number, {link}) rather than a holdings "
            "statement. What each number counts was in an 853 that is not "
            "part of the text, so nothing was converted. Rewrite the 866 as a "
            "statement (Edit), or enter the 853 and 863 by hand."
        )
        return result
    result.warnings.append(
        "No recognisable holdings ranges found. "
        "Please check the input format."
    )
    return result
