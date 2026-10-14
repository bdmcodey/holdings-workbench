"""
flavours.py
-----------
A pattern's expression, written for another tool's regex dialect.

The workbench runs every expression through Python's `re`, ignoring case and
against the whole statement (`fullmatch`). Neither of those two settings is in
the expression's text, so an expression copied as it stands into another tool
matches differently there: "Vol." where the expression says "v.", or part of a
statement where the workbench wanted all of it. Every flavour here carries both
settings in whatever form that tool takes them.

The expression is read into a small syntax tree and written out again, not
patched with string substitutions. A substitution cannot tell `(?P<` from the
same characters inside a character class, or a backslash that escapes from one
that is escaped, and getting either wrong yields an expression that looks right
and quietly matches nothing.

One difference is left alone. In JavaScript and Java, "." does not match a
carriage return or a Unicode line separator; in Python it does. A statement is
one line of one MARC subfield and holds neither, and writing every "." as
"[^\\n]" would lengthen every expression to cover a case that cannot arise.

Nothing is dropped to make an expression fit. A construct a flavour cannot
express -- a lookbehind for Oracle, a possessive repeat for JavaScript -- makes
that flavour refuse the expression with a reason, and the screen shows the
reason where the expression would have been.

Public API
----------
    from marc_serials.flavours import convert, FLAVOURS

    result = convert(r"v\\.(?P<start_num>\\d+)", "javascript")
    result.text     # '/^v\\.(?<start_num>\\d+)$/i'
    result.error    # None, or why this flavour cannot write it
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, replace
from typing import List, Optional, Union

from marc_serials.detector import MAX_REGEX_CHARS


# ── The flavours ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Flavour:
    key: str
    label: str
    # What the copied text is and what it will not do, for the cataloguer
    # choosing it. Shown whenever this flavour is chosen, not only when
    # something goes wrong, because the limits apply to every expression.
    alert: str
    # "info" for a faithful translation; "warn" where the copy does less than
    # the workbench does, or has not been checked in the tool it is for.
    severity: str


# Oracle's REGEXP_ functions accept a pattern of at most 512 bytes.
ORACLE_MAX_BYTES = 512

FLAVOURS = {f.key: f for f in (
    Flavour(
        "python", "Python",
        "Python's re module, as the workbench runs it. (?i) at the start makes "
        "capitals and lower case match alike, and ^ … $ makes it match a whole "
        "statement rather than part of one.",
        "info"),
    Flavour(
        "pcre", "PCRE (PHP, Perl, R, regex101)",
        "PCRE, the dialect of PHP, Perl, R, grep -P and regex101's default. "
        "Named values are written (?<name>…). (?i) ignores capitals, and ^ … $ "
        "matches a whole statement.",
        "info"),
    Flavour(
        "javascript", "JavaScript",
        "A JavaScript regular expression literal, /…/i. The i after the last "
        "slash ignores capitals. If your tool takes the expression and its "
        "options separately, leave out the slashes and the i, and turn on its "
        "ignore-case option instead.",
        "info"),
    Flavour(
        "java", "Java",
        "Java's java.util.regex, and tools built on it. (?iu) ignores capitals, "
        "accented ones too, and ^ … $ matches a whole statement. Java does not allow "
        "underscores in the names of values, so they are joined up: start_num "
        "becomes startNum. To put it inside a Java string, double every "
        "backslash.",
        "info"),
    Flavour(
        "alma", "Alma normalization rules (Drools)",
        "For an Alma normalization rule: the text to put between the quotation "
        "marks after matches. Backslashes are already doubled, as a quoted "
        "string in a rule needs, and there is no ^ or $ because matches always "
        "compares the whole value. Not yet checked in Alma — try it on one "
        "record before running a rule across a set. If Alma compares the whole "
        "field rather than the statement in $a, add .* at both ends.",
        "warn"),
    Flavour(
        "oracle", "Oracle SQL (Alma Analytics)",
        "Oracle SQL finds the statements that fit the pattern; it cannot pull "
        "the values out of them, because Oracle cannot name them. Use it as "
        "REGEXP_LIKE(column, '…', 'i') — the 'i' is needed, or capitals will "
        "not match. Groups are taken out and repeated spaces merged to save "
        "length, which does not change what matches. Oracle accepts at most "
        "512 bytes, so a long pattern may have no Oracle form; its card says "
        "so.",
        "warn"),
)}

DEFAULT_FLAVOUR = "python"


def choices() -> list:
    """The flavours in menu order, for the page."""
    return [{"key": f.key, "label": f.label, "alert": f.alert,
             "severity": f.severity} for f in FLAVOURS.values()]


@dataclass(frozen=True)
class Converted:
    text: Optional[str]
    error: Optional[str] = None

    def as_dict(self) -> dict:
        return {"text": self.text, "error": self.error}


class Unsupported(ValueError):
    """The flavour cannot express something in the expression; says what."""


# ── Syntax tree ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Lit:
    ch: str


@dataclass(frozen=True)
class Shorthand:
    letter: str                 # d D s S w W


@dataclass(frozen=True)
class Anchor:
    kind: str                   # ^ $ A Z b B


@dataclass(frozen=True)
class Dot:
    pass


@dataclass(frozen=True)
class Range:
    lo: str
    hi: str


@dataclass(frozen=True)
class CharClass:
    negated: bool
    items: tuple                # Lit | Range | Shorthand


@dataclass(frozen=True)
class Group:
    # capture noncap ahead not_ahead behind not_behind atomic
    kind: str
    body: "Node"
    name: Optional[str] = None


@dataclass(frozen=True)
class Repeat:
    body: "Node"
    lo: int
    hi: Optional[int]           # None: no upper bound
    mode: str                   # greedy lazy possessive


@dataclass(frozen=True)
class Backref:
    ref: Union[int, str]


@dataclass(frozen=True)
class Seq:
    items: tuple


@dataclass(frozen=True)
class Alt:
    branches: tuple


Node = Union[Lit, Shorthand, Anchor, Dot, CharClass, Group, Repeat, Backref,
             Seq, Alt]


# ── Reading a Python expression ───────────────────────────────────────────────

_SIMPLE_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "f": "\f", "v": "\v",
                   "a": "\a"}
_QUANT_RE = re.compile(r"\{(\d*)(?:(,)(\d*))?\}")
_FLAGS = set("aiLmsux")
_OCT = set("01234567")


class _Reader:
    """
    Reads a Python `re` expression into the tree above.

    The expression has already compiled under Python, so this does not repeat
    Python's error checking. What it must not do is misread something valid,
    so anything it does not recognise is refused rather than guessed at.
    """

    def __init__(self, source: str):
        self.s = source
        self.i = 0

    def read(self) -> Node:
        node = self._alt()
        if self.i != len(self.s):
            raise Unsupported(f"an unexpected {self.s[self.i]!r}")
        return node

    def _peek(self) -> str:
        return self.s[self.i] if self.i < len(self.s) else ""

    def _take(self, n: int = 1) -> str:
        out = self.s[self.i:self.i + n]
        self.i += n
        return out

    def _alt(self) -> Node:
        branches = [self._seq()]
        while self._peek() == "|":
            self.i += 1
            branches.append(self._seq())
        return branches[0] if len(branches) == 1 else Alt(tuple(branches))

    def _seq(self) -> Node:
        items: List[Node] = []
        while self.i < len(self.s) and self.s[self.i] not in "|)":
            atom = self._atom()
            if atom is None:            # a comment, or a redundant (?i)
                # Python repeats what came before: a(?#note)* is a*.
                if items and self._peek() in ("*", "+", "?", "{"):
                    if isinstance(items[-1], Repeat):
                        raise Unsupported("a repeat after a comment")
                    items[-1] = self._quantified(items[-1])
                continue
            items.append(self._quantified(atom))
        return items[0] if len(items) == 1 else Seq(tuple(items))

    def _quantified(self, atom: Node) -> Node:
        c = self._peek()
        if c == "*":
            lo, hi = 0, None
            self.i += 1
        elif c == "+":
            lo, hi = 1, None
            self.i += 1
        elif c == "?":
            lo, hi = 0, 1
            self.i += 1
        elif c == "{":
            m = _QUANT_RE.match(self.s, self.i)
            # Python reads "{" as a literal brace unless it is a well-formed
            # repeat; "{}" is a literal too.
            if not m or (m.group(1) == "" and m.group(2) is None):
                return atom
            lo = int(m.group(1)) if m.group(1) else 0
            if m.group(2) is None:
                hi = lo
            else:
                hi = int(m.group(3)) if m.group(3) else None
            self.i = m.end()
        else:
            return atom
        mode = "greedy"
        if self._peek() == "?":
            mode = "lazy"
            self.i += 1
        elif self._peek() == "+":
            mode = "possessive"
            self.i += 1
        return Repeat(atom, lo, hi, mode)

    def _atom(self) -> Optional[Node]:
        c = self._take()
        if c == "(":
            return self._group()
        if c == "[":
            return self._class()
        if c == "\\":
            return self._escape(in_class=False)
        if c == ".":
            return Dot()
        if c in "^$":
            return Anchor(c)
        return Lit(c)

    def _group(self) -> Optional[Node]:
        if self._peek() != "?":
            body = self._alt()
            self._close()
            return Group("capture", body)
        self.i += 1
        c = self._peek()
        if c == ":":
            self.i += 1
            return self._group_body("noncap")
        if c == "P":
            self.i += 1
            if self._peek() == "<":
                self.i += 1
                end = self.s.index(">", self.i)
                name = self.s[self.i:end]
                self.i = end + 1
                body = self._alt()
                self._close()
                return Group("capture", body, name)
            if self._peek() == "=":
                self.i += 1
                end = self.s.index(")", self.i)
                name = self.s[self.i:end]
                self.i = end + 1
                return Backref(name)
            raise Unsupported("an unrecognised (?P group")
        if c == "=":
            self.i += 1
            return self._group_body("ahead")
        if c == "!":
            self.i += 1
            return self._group_body("not_ahead")
        if c == ">":
            self.i += 1
            return self._group_body("atomic")
        if c == "<":
            nxt = self.s[self.i + 1:self.i + 2]
            if nxt == "=":
                self.i += 2
                return self._group_body("behind")
            if nxt == "!":
                self.i += 2
                return self._group_body("not_behind")
            raise Unsupported("an unrecognised (?< group")
        if c == "#":
            end = self.s.index(")", self.i)
            self.i = end + 1
            return None
        if c == "(":
            raise Unsupported("a conditional group, (?(…)")
        # Inline settings: (?i) for the whole expression, or (?i:…) for part.
        m = re.compile(r"([aiLmsux]*)(?:-([imsx]*))?([:)])").match(self.s, self.i)
        if m:
            flags = set(m.group(1)) | set(m.group(2) or "")
            self.i = m.end()
            if flags - {"i"} or m.group(2):
                written = m.group(0)[:-1]
                raise Unsupported(f"the inline setting (?{written})")
            # Every flavour already ignores capitals, so (?i) says nothing new.
            if m.group(3) == ")":
                return None
            body = self._alt()
            self._close()
            return Group("noncap", body)
        raise Unsupported("an unrecognised (? group")

    def _group_body(self, kind: str) -> Node:
        body = self._alt()
        self._close()
        return Group(kind, body)

    def _close(self) -> None:
        if self._take() != ")":
            raise Unsupported("an unclosed group")

    def _class(self) -> Node:
        negated = False
        if self._peek() == "^":
            negated = True
            self.i += 1
        items: List[Node] = []
        first = True
        while True:
            if self.i >= len(self.s):
                raise Unsupported("an unclosed [")
            c = self._take()
            if c == "]" and not first:
                break
            first = False
            item = self._escape(in_class=True) if c == "\\" else Lit(c)
            # A range: a single character, "-", and another that is not "]".
            if (isinstance(item, Lit) and self._peek() == "-"
                    and self.s[self.i + 1:self.i + 2] not in ("]", "")):
                self.i += 1
                c2 = self._take()
                hi = self._escape(in_class=True) if c2 == "\\" else Lit(c2)
                if not isinstance(hi, Lit):
                    raise Unsupported("a range ending in a class such as \\d")
                items.append(Range(item.ch, hi.ch))
            else:
                items.append(item)
        return CharClass(negated, tuple(items))

    def _escape(self, in_class: bool) -> Node:
        c = self._take()
        if not c:
            raise Unsupported("a trailing backslash")
        if c in "dDsSwW":
            return Shorthand(c)
        if c == "b" and in_class:
            return Lit("\b")
        if c in "bBAZ":
            return Anchor(c)
        if c in _SIMPLE_ESCAPES:
            return Lit(_SIMPLE_ESCAPES[c])
        if c == "x":
            return Lit(chr(int(self._take(2), 16)))
        if c == "u":
            return Lit(chr(int(self._take(4), 16)))
        if c == "U":
            return Lit(chr(int(self._take(8), 16)))
        if c == "N":
            end = self.s.index("}", self.i)
            name = self.s[self.i + 1:end]
            self.i = end + 1
            return Lit(unicodedata.lookup(name))
        if c.isdigit():
            # Python's rule: a leading 0, or three octal digits, is a character
            # by its octal code; otherwise one or two digits name a group.
            if c == "0":
                digits = c
                while len(digits) < 3 and self._peek() in _OCT and self._peek():
                    digits += self._take()
                return Lit(chr(int(digits, 8)))
            nxt = self.s[self.i:self.i + 2]
            if (c in _OCT and len(nxt) == 2
                    and nxt[0] in _OCT and nxt[1] in _OCT):
                self.i += 2
                return Lit(chr(int(c + nxt, 8)))
            if in_class:
                raise Unsupported("a group number inside [ ]")
            digits = c
            if self._peek().isdigit():
                digits += self._take()
            return Backref(int(digits))
        if c.isalnum():
            raise Unsupported(f"the escape \\{c}")
        return Lit(c)


# ── Shortening, for a flavour that only answers "does it match?" ─────────────

def _find_only(node: Node) -> Node:
    """
    The same set of matching statements, written shorter.

    Only valid where the caller asks whether the whole statement matches and
    nothing more -- no values read out, no position reported. Then:

    * a group that is not repeated and holds no alternation is only brackets;
    * a lazy repeat finds a match exactly when the greedy one does;
    * x*x* matches what x* matches.
    """
    if isinstance(node, Seq):
        items: List[Node] = []
        for item in node.items:
            item = _unbracket(_find_only(item))
            items.extend(item.items if isinstance(item, Seq) else (item,))
        out: List[Node] = []
        for item in items:
            if (out and isinstance(item, Repeat) and item.lo == 0
                    and item.hi is None and item == out[-1]):
                continue
            out.append(item)
        return out[0] if len(out) == 1 else Seq(tuple(out))
    if isinstance(node, Alt):
        return Alt(tuple(_unbracket(_find_only(b)) for b in node.branches))
    if isinstance(node, Group):
        body = _find_only(node.body)
        if node.kind in ("capture", "noncap"):
            return Group("noncap", body)
        return replace(node, body=body)
    if isinstance(node, Repeat):
        body = _find_only(node.body)
        mode = "greedy" if node.mode == "lazy" else node.mode
        # (x)* is x* when x is one atom; a repeat inside must keep its group,
        # or (a*)? would become the different a*?.
        if (isinstance(body, Group) and body.kind == "noncap"
                and isinstance(body.body, (Lit, Shorthand, Dot, CharClass))):
            body = body.body
        return Repeat(body, node.lo, node.hi, mode)
    return node


def _unbracket(node: Node) -> Node:
    """A group holding no alternation, as its contents; anything else as is."""
    if (isinstance(node, Group) and node.kind == "noncap"
            and not isinstance(node.body, Alt)):
        return node.body
    return node


# ── Writing ───────────────────────────────────────────────────────────────────

_META = set("\\^$.|?*+()[]{}")
_PCRE_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,31}\Z")


def _java_name(name: str, taken: set) -> str:
    """start_num -> startNum: Java names are letters and digits only."""
    parts = [p for p in re.split(r"[^A-Za-z0-9]+", name) if p]
    out = "".join([parts[0]] + [p[:1].upper() + p[1:] for p in parts[1:]]) \
        if parts else ""
    if not out or not out[0].isalpha():
        out = "g" + out
    candidate, n = out, 2
    while candidate in taken:
        candidate, n = f"{out}{n}", n + 1
    taken.add(candidate)
    return candidate


def _names(node: Node, found: List[str]) -> List[str]:
    if isinstance(node, Group) and node.name:
        found.append(node.name)
    for child in _children(node):
        _names(child, found)
    return found


def _children(node: Node) -> tuple:
    if isinstance(node, Seq):
        return node.items
    if isinstance(node, Alt):
        return node.branches
    if isinstance(node, (Group, Repeat)):
        return (node.body,)
    return ()


class _Writer:
    def __init__(self, flavour: str, tree: Node):
        self.f = flavour
        self.names = {}
        if flavour in ("java", "alma"):
            taken: set = set()
            for name in _names(tree, []):
                self.names[name] = _java_name(name, taken)
        elif flavour in ("pcre", "javascript"):
            for name in _names(tree, []):
                if not _PCRE_NAME.match(name):
                    raise Unsupported(f"the value name {name!r}")
                self.names[name] = name

    @property
    def oracle(self) -> bool:
        return self.f == "oracle"

    # Anything that is not a printable character goes in as a code, except in
    # Oracle, which has no escape for one and takes the character itself.
    def _char(self, ch: str, specials: set) -> str:
        if ch in specials:
            return "\\" + ch
        if not self.oracle and (ord(ch) < 32 or ord(ch) == 127):
            return f"\\x{ord(ch):02x}"
        # Line and paragraph separators end a JavaScript literal.
        if self.f == "javascript" and ch in "\u2028\u2029":
            return f"\\u{ord(ch):04x}"
        return ch

    def _lit(self, ch: str) -> str:
        specials = _META | ({"/"} if self.f == "javascript" else set())
        return self._char(ch, specials)

    def write(self, node: Node) -> str:
        if isinstance(node, Seq):
            out = []
            for i, item in enumerate(node.items):
                text = self.write(item)
                # \1 followed by a digit would read as \10.
                nxt = node.items[i + 1] if i + 1 < len(node.items) else None
                if (isinstance(item, Backref) and isinstance(item.ref, int)
                        and isinstance(nxt, Lit) and nxt.ch.isdigit()):
                    text = f"(?:{text})"
                out.append(text)
            return "".join(out)
        if isinstance(node, Alt):
            return "|".join(self.write(b) for b in node.branches)
        if isinstance(node, Lit):
            return self._lit(node.ch)
        if isinstance(node, Dot):
            return "."
        if isinstance(node, Shorthand):
            return "\\" + node.letter
        if isinstance(node, Anchor):
            return self._anchor(node.kind)
        if isinstance(node, CharClass):
            return self._oracle_class(node) if self.oracle else self._class(node)
        if isinstance(node, Group):
            return self._group(node)
        if isinstance(node, Repeat):
            return self._repeat(node)
        if isinstance(node, Backref):
            return self._backref(node.ref)
        raise Unsupported(f"{type(node).__name__}")  # pragma: no cover

    def _anchor(self, kind: str) -> str:
        if kind in "^$":
            return kind
        if kind in "bB":
            if self.oracle:
                raise Unsupported(f"a word boundary, \\{kind}")
            return "\\" + kind
        if kind == "A":
            return "\\A" if self.f in ("python", "pcre", "java", "alma") else "^"
        # Python's \Z is the very end, which is \z in PCRE and Java.
        if self.f == "python":
            return "\\Z"
        return "\\z" if self.f in ("pcre", "java", "alma") else "$"

    def _class(self, node: CharClass) -> str:
        specials = set("\\]^-[")
        if self.f in ("java", "alma"):
            specials |= {"&"}           # && is intersection in a Java class
        if self.f == "javascript":
            specials |= {"/"}
        parts = []
        last = len(node.items) - 1
        for i, item in enumerate(node.items):
            if isinstance(item, Lit):
                # "-" is plain first or last, "^" anywhere but first: [-/] reads
                # better than [\-/]. "]" and "[" are always escaped, because
                # JavaScript reads [] as an empty class and Java [[ as a union.
                plain = ((item.ch == "-" and i in (0, last))
                         or (item.ch == "^" and (i > 0 or node.negated)))
                parts.append(item.ch if plain else self._char(item.ch, specials))
            elif isinstance(item, Range):
                parts.append(self._char(item.lo, specials) + "-"
                             + self._char(item.hi, specials))
            else:
                parts.append("\\" + item.letter)
        return "[" + ("^" if node.negated else "") + "".join(parts) + "]"

    def _oracle_class(self, node: CharClass) -> str:
        """
        A POSIX bracket expression, which has no escapes at all.

        "]" is literal only first, "-" only last, "^" anywhere but first, and a
        backslash is either literal or an escape depending on whom you ask,
        so it is refused rather than guessed.
        """
        if (not node.negated and len(node.items) == 1
                and isinstance(node.items[0], Lit)):
            return self._lit(node.items[0].ch)
        close = dash = caret = bracket = False
        body = []
        for item in node.items:
            if isinstance(item, Shorthand):
                if item.letter not in "dsw":
                    raise Unsupported(f"\\{item.letter} inside [ ]")
                body.append({"d": "[:digit:]", "s": "[:space:]",
                             "w": "[:alnum:]_"}[item.letter])
                continue
            chars = [item.ch] if isinstance(item, Lit) else [item.lo, item.hi]
            if "\\" in chars:
                raise Unsupported("a backslash inside [ ]")
            if isinstance(item, Range):
                if "]" in chars or "-" in chars or "[" in chars or "^" in chars:
                    raise Unsupported("a range starting or ending in ] - [ or ^")
                body.append(f"{item.lo}-{item.hi}")
            elif item.ch == "]":
                close = True
            elif item.ch == "-":
                dash = True
            elif item.ch == "^":
                caret = True
            elif item.ch == "[":
                bracket = True
            else:
                body.append(item.ch)
        text = ("]" if close else "") + "".join(body)
        if caret:
            # Anywhere but first; with nothing else to go before it, "-" or "["
            # can, and in [^^] the second is literal.
            if text:
                text += "^"
            elif dash:
                text, dash = "-^", False
            elif bracket:
                text, bracket = "[^", False
            else:
                text = "^"
        if bracket:
            text += "["
        if dash:
            text += "-"
        return "[" + ("^" if node.negated else "") + text + "]"

    def _group(self, node: Group) -> str:
        if node.kind == "capture" and node.name and not self.oracle:
            name = self.names.get(node.name, node.name)
            opener = f"(?P<{name}>" if self.f == "python" else f"(?<{name}>"
            return opener + self.write(node.body) + ")"
        if node.kind in ("capture", "noncap"):
            # Oracle has only plain groups; they count, but nothing here reads
            # them.
            if self.oracle:
                return "(" + self.write(node.body) + ")"
            return ("(" if node.kind == "capture" else "(?:") \
                + self.write(node.body) + ")"
        if node.kind == "atomic":
            if self.f not in ("python", "pcre", "java", "alma"):
                raise Unsupported("an atomic group, (?>…)")
            return "(?>" + self.write(node.body) + ")"
        if self.oracle:
            raise Unsupported("a lookahead or lookbehind")
        opener = {"ahead": "(?=", "not_ahead": "(?!",
                  "behind": "(?<=", "not_behind": "(?<!"}[node.kind]
        return opener + self.write(node.body) + ")"

    def _repeat(self, node: Repeat) -> str:
        body = self.write(node.body)
        if node.lo == 0 and node.hi is None:
            q = "*"
        elif node.lo == 1 and node.hi is None:
            q = "+"
        elif node.lo == 0 and node.hi == 1:
            q = "?"
        elif node.hi is None:
            q = f"{{{node.lo},}}"
        elif node.lo == node.hi:
            q = f"{{{node.lo}}}"
        else:
            q = f"{{{node.lo},{node.hi}}}"
        if node.mode == "lazy":
            q += "?"
        elif node.mode == "possessive":
            if self.f not in ("python", "pcre", "java", "alma"):
                raise Unsupported("a possessive repeat, such as *+")
            q += "+"
        return body + q

    def _backref(self, ref: Union[int, str]) -> str:
        if self.oracle:
            raise Unsupported("a back-reference to an earlier value")
        if isinstance(ref, int):
            return f"\\{ref}"
        if self.f == "python":
            return f"(?P={ref})"
        return f"\\k<{self.names.get(ref, ref)}>"


# ── Putting it together ───────────────────────────────────────────────────────

def _whole(tree: Node) -> Node:
    """The expression with any ^ and $ of its own taken off; they are added."""
    if isinstance(tree, Seq):
        items = list(tree.items)
        if items and items[0] == Anchor("^"):
            items = items[1:]
        if items and items[-1] == Anchor("$"):
            items = items[:-1]
        return items[0] if len(items) == 1 else Seq(tuple(items))
    if tree in (Anchor("^"), Anchor("$")):
        return Seq(())
    return tree


def convert(regex: str, flavour: str) -> Converted:
    """
    `regex`, as the workbench runs it, written for `flavour`.

    Raises KeyError for a flavour that does not exist; every problem with the
    expression itself comes back as `error`, for the screen to show.
    """
    if flavour not in FLAVOURS:
        raise KeyError(flavour)
    if not isinstance(regex, str) or not regex:
        return Converted(None, "There is no expression.")
    if len(regex) > MAX_REGEX_CHARS:
        return Converted(None, f"The expression is longer than "
                               f"{MAX_REGEX_CHARS:,} characters.")
    try:
        re.compile(regex, re.IGNORECASE)
    except re.error as exc:
        return Converted(None, f"The expression is not valid: {exc}")
    except RecursionError:
        return Converted(None, "The expression is nested too deeply.")
    try:
        tree = _whole(_Reader(regex).read())
        if flavour == "oracle":
            tree = _unbracket(_find_only(tree))
        body = _Writer(flavour, tree).write(tree)
        if isinstance(tree, Alt):
            body = ("(" if flavour == "oracle" else "(?:") + body + ")"
    except Unsupported as exc:
        name = FLAVOURS[flavour].label.split(" (")[0]
        return Converted(None, f"{name} has no way to write {exc}.")
    except (RecursionError, ValueError, IndexError):
        return Converted(None, "The expression could not be read for "
                               "conversion.")

    if flavour in ("python", "pcre"):
        return Converted(f"(?i)^{body}$")
    # Java ignores case only between A and Z unless told u as well, and the
    # workbench ignores it in accented letters too: "été" matches "ÉTÉ".
    if flavour == "java":
        return Converted(f"(?iu)^{body}$")
    if flavour == "javascript":
        return Converted(f"/^{body}$/i")
    if flavour == "alma":
        text = f"(?iu){body}".replace("\\", "\\\\").replace('"', '\\"')
        return Converted(text)
    text = f"^{body}$"
    size = len(text.encode("utf-8"))
    if size > ORACLE_MAX_BYTES:
        return Converted(None, f"Too long for Oracle: {size:,} bytes, and "
                               f"Oracle accepts at most {ORACLE_MAX_BYTES}.")
    return Converted(text)
