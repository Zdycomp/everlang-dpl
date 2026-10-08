#!/usr/bin/env python3
"""
lexers.py — four independent scanners for the same language.

Each is written in the style its own technique leads to, and none was
adjusted to match another. That is the point. Where they disagree, the
disagreement is evidence that the token contract was never actually
written down — the incumbent's SPEC table is an implementation, not a
specification, and an implementation cannot be the thing an independent
implementation is checked against.

  L1 regex_master   one alternation, ordered longest-first  (incumbent)
  L2 handrolled     character scanner, explicit maximal munch
  L3 dfa            character classes and a transition table
  L4 trie           longest-match operator trie + typed sub-scanners

All four return contract.LexOut. None of them raises: a scanner that
throws makes totality a property of the caller instead of the language
(SEMANTICS.md G1).

Codric Enterprise · Ricky (Dreid) · 2026
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Set, Tuple

from contract import Fail, LexOut, Tok
from spec import SPEC

# ═════════════════════════════════════════════
# Shared vocabulary — the part that IS agreed
# ═════════════════════════════════════════════

#: Reserved words, as the incumbent declares them.
#: Gen-0 keeps all nineteen even though the grammar reaches six.
_NATIVE_KEYWORDS: Set[str] = {
    "if", "then", "else", "def", "let", "true", "false",
    "anchor", "ezr", "z", "show", "expect", "ascend", "in",
    "assimilate", "learn", "equiv", "example", "to", "by",
}

PUNCT: Dict[str, str] = {"(": "LPAR", ")": "RPAR", ",": "COMMA",
                         "[": "LBRACK", "]": "RBRACK"}


def keywords() -> Set[str]:
    """The reserved set: the ruling if one exists, else all nineteen the
    incumbent declares."""
    return set(SPEC.get("reserved_words", sorted(_NATIVE_KEYWORDS)))


def cmp_kind(native: str) -> str:
    """Which kind a bare '<' or '>' carries. Unratified, each scanner
    answers from its own design."""
    return SPEC.get("cmp_kind", native)


def unterminated(native: str) -> str:
    return SPEC.get("unterminated_string_defect", native)


#: Back-compat alias for callers that want the current reserved set.
KEYWORDS = _NATIVE_KEYWORDS
SPACE = " \t\r"


def _eof(pos: int, line: int) -> Tok:
    return Tok("EOF", "", pos, line)


# ═════════════════════════════════════════════
# L1 — one master regex, alternatives ordered
# ═════════════════════════════════════════════

_SPEC: List[Tuple[str, str]] = [
    ("NUM",   r"\d+\.\d+|\d+"),
    ("STR",   r'"[^"\n]*"'),
    ("CMP",   r"<=|>=|==|!="),
    ("EQ",    r"="),
    ("OP",    r"[-+*/<>]"),
    ("LPAR",  r"\("),
    ("RPAR",  r"\)"),
    ("LBRACK", r"\["),
    ("RBRACK", r"\]"),
    ("COMMA", r","),
    ("NAME",  r"[A-Za-z_]\w*"),
]
_MASTER = re.compile("|".join(f"(?P<{k}>{p})" for k, p in _SPEC))


def lex_regex_master(src: str) -> LexOut:
    """Longest match by alternation order. Ordering is the whole
    algorithm: CMP precedes OP so `<=` is not read as `<` then `=`,
    and NUM precedes NAME so `1x` is not read as one identifier."""
    kw = keywords()
    out = LexOut()
    i, line, n = 0, 1, len(src)

    while i < n:
        ch = src[i]
        if ch == "\n":
            line += 1; i += 1; continue
        if ch in SPACE:
            i += 1; continue
        if ch == "#":
            while i < n and src[i] != "\n":
                i += 1
            continue

        m = _MASTER.match(src, i)
        if not m:
            # A quote that matched nothing is an unterminated string:
            # the STR alternative requires the closing quote, so it
            # simply does not fire. The incumbent classified that as
            # misbound; whether that is right is question two.
            defect = unterminated("misbound") if ch == '"' else "misbound"
            out.fail = Fail("lex", defect, i, line)
            return out

        kind, text = m.lastgroup, m.group()
        if kind == "OP" and text in "<>":
            kind = cmp_kind("OP")
        if kind == "NAME" and text in kw:
            kind = "KW"
        out.toks.append(Tok(kind, text, i, line))
        i = m.end()

    out.toks.append(_eof(i, line))
    return out


# ═════════════════════════════════════════════
# L2 — hand-rolled, maximal munch stated outright
# ═════════════════════════════════════════════

_TWO_CHAR = ("<=", ">=", "==", "!=")


def lex_handrolled(src: str) -> LexOut:
    """A scanner written the way you write one by hand: look at the
    character, decide what it can start, then take as much as will go.

    Scanning `<` means immediately asking whether an `=` follows, which
    puts `<` and `<=` in the same branch of the code — so this author
    files both under CMP. That is a design consequence, not a decision
    taken to match or to differ from anyone else.
    """
    kw = keywords()
    out = LexOut()
    i, line, n = 0, 1, len(src)

    while i < n:
        ch = src[i]

        if ch == "\n":
            line += 1; i += 1; continue
        if ch in SPACE:
            i += 1; continue
        if ch == "#":
            while i < n and src[i] != "\n":
                i += 1
            continue

        start = i

        # number: digits, optionally one dot with digits after it
        if ch.isdigit():
            while i < n and src[i].isdigit():
                i += 1
            if i + 1 < n and src[i] == "." and src[i + 1].isdigit():
                i += 1
                while i < n and src[i].isdigit():
                    i += 1
            out.toks.append(Tok("NUM", src[start:i], start, line))
            continue

        # name or keyword
        if ch.isalpha() or ch == "_":
            while i < n and (src[i].isalnum() or src[i] == "_"):
                i += 1
            text = src[start:i]
            out.toks.append(
                Tok("KW" if text in kw else "NAME", text, start, line))
            continue

        # string: run to the closing quote, and say so if there isn't one
        if ch == '"':
            i += 1
            while i < n and src[i] not in '"\n':
                i += 1
            if i >= n or src[i] != '"':
                out.fail = Fail("lex", unterminated("unbounded"), start, line)
                return out
            i += 1
            out.toks.append(Tok("STR", src[start:i], start, line))
            continue

        # two-character comparisons, then one-character ones
        pair = src[i:i + 2]
        if pair in _TWO_CHAR:
            out.toks.append(Tok("CMP", pair, start, line))
            i += 2
            continue
        if ch in "<>":
            out.toks.append(Tok(cmp_kind("CMP"), ch, start, line))
            i += 1
            continue
        if ch == "=":
            out.toks.append(Tok("EQ", ch, start, line))
            i += 1
            continue
        if ch in "+-*/":
            out.toks.append(Tok("OP", ch, start, line))
            i += 1
            continue
        if ch in PUNCT:
            out.toks.append(Tok(PUNCT[ch], ch, start, line))
            i += 1
            continue

        out.fail = Fail("lex", "misbound", start, line)
        return out

    out.toks.append(_eof(i, line))
    return out


# ═════════════════════════════════════════════
# L3 — character classes and a transition table
# ═════════════════════════════════════════════

def _cls(ch: str) -> str:
    if ch.isdigit():          return "d"
    if ch.isalpha() or ch == "_": return "a"
    if ch in SPACE:           return "s"
    if ch == "\n":            return "n"
    if ch == '"':             return "q"
    if ch == "#":             return "h"
    if ch == ".":             return "."
    if ch in "<>=!":          return "c"   # can begin a comparison
    if ch in "+-*/":          return "o"
    if ch in "(),[]":         return "p"
    return "?"


#: state -> class -> (next state, action)
#: action: "" keep scanning, "emit:<KIND>" accept before this char
_TABLE: Dict[str, Dict[str, Tuple[str, str]]] = {
    "start": {
        "d": ("num", ""), "a": ("name", ""), "q": ("str", ""),
        "c": ("cmp", ""), "o": ("op", ""),   "p": ("punct", ""),
        "s": ("start", ""), "n": ("start", ""), "h": ("comment", ""),
    },
    "num":  {"d": ("num", ""), ".": ("numdot", "")},
    "numdot": {"d": ("numfrac", "")},
    "numfrac": {"d": ("numfrac", "")},
    "name": {"a": ("name", ""), "d": ("name", "")},
    "cmp":  {"c": ("cmp2", "")},
}


def lex_dfa(src: str) -> LexOut:
    """A table walk. Runs of a class are consumed by the table; every
    accepting state names the kind it produces.

    This author gives `<`, `>`, `=`, `!` one class, because the machine
    cannot know which of them it is holding until it has seen whether
    an `=` follows. `=` alone is separated out at accept time — it is
    the one member of the class that is not a comparison.
    """
    kw = keywords()
    out = LexOut()
    i, line, n = 0, 1, len(src)

    while i < n:
        ch = src[i]
        k = _cls(ch)

        if k == "n":
            line += 1; i += 1; continue
        if k == "s":
            i += 1; continue
        if k == "h":
            while i < n and src[i] != "\n":
                i += 1
            continue

        start, start_line = i, line

        # '.' reaches the table only when it starts a token, and no
        # token starts with one. Found by the forge: the table lookup
        # raised KeyError instead of refusing, which makes G1 a
        # property of the caller rather than of the language.
        if k in ("?", "."):
            out.fail = Fail("lex", "misbound", start, line)
            return out

        if k == "q":
            i += 1
            while i < n and src[i] != '"' and src[i] != "\n":
                i += 1
            if i >= n or src[i] != '"':
                out.fail = Fail("lex", unterminated("unbounded"), start, start_line)
                return out
            i += 1
            out.toks.append(Tok("STR", src[start:i], start, start_line))
            continue

        if k == "p":
            out.toks.append(Tok(PUNCT[ch], ch, start, line))
            i += 1
            continue

        if k == "o":
            out.toks.append(Tok("OP", ch, start, line))
            i += 1
            continue

        if k == "c":
            # one class, two outcomes: pair, or the bare character
            if i + 1 < n and src[i + 1] == "=":
                out.toks.append(Tok("CMP", src[i:i + 2], start, line))
                i += 2
            elif ch == "=":
                out.toks.append(Tok("EQ", ch, start, line))
                i += 1
            elif ch == "!":
                out.fail = Fail("lex", "misbound", start, line)
                return out
            else:
                out.toks.append(Tok(cmp_kind("CMP"), ch, start, line))
                i += 1
            continue

        # table-driven runs: numbers and names
        state = _TABLE["start"][k][0]
        i += 1
        while i < n:
            nk = _cls(src[i])
            row = _TABLE.get(state, {})
            if nk not in row:
                break
            state = row[nk][0]
            i += 1

        if state in ("num", "numfrac"):
            out.toks.append(Tok("NUM", src[start:i], start, line))
        elif state == "numdot":
            # a trailing dot with no digits after it is not a number
            out.fail = Fail("lex", "misbound", i - 1, line)
            return out
        else:
            text = src[start:i]
            out.toks.append(
                Tok("KW" if text in kw else "NAME", text, start, line))

    out.toks.append(_eof(i, line))
    return out


# ═════════════════════════════════════════════
# L4 — operator trie, longest match wins
# ═════════════════════════════════════════════

_OPERATORS: Dict[str, str] = {
    "<=": "CMP", ">=": "CMP", "==": "CMP", "!=": "CMP",
    "<": "OP", ">": "OP",
    "+": "OP", "-": "OP", "*": "OP", "/": "OP",
    "=": "EQ", "(": "LPAR", ")": "RPAR", ",": "COMMA",
    "[": "LBRACK", "]": "RBRACK",
}


#: End-of-token marker. A unique object, not a string: the first
#: version used "$", which is also a character a source text may
#: contain, so a '$' in the input walked into the marker and the next
#: character indexed a tuple. The fuzzer found it at generation 7 on
#: `false =$= 35`. A sentinel that cannot collide with the alphabet it
#: indexes is the fix, not a guard against the one character that
#: happened to break it.
_END = object()


def _build_trie(table: Dict[str, str]) -> dict:
    root: dict = {}
    for text, kind in table.items():
        node = root
        for c in text:
            node = node.setdefault(c, {})
        node[_END] = (text, kind)
    return root


_TRIE = _build_trie(_OPERATORS)


def lex_trie(src: str) -> LexOut:
    """Operators come out of a trie walked as far as it will go, so
    maximal munch is a property of the data structure rather than of
    the order somebody wrote the alternatives in.

    This author took the kind names straight off the incumbent's table,
    where `<` and `>` are filed under OP. Nothing in the trie forces
    that; it is inherited, and inheritance is exactly what makes a
    witness dependent rather than independent.
    """
    kw = keywords()
    out = LexOut()
    i, line, n = 0, 1, len(src)

    while i < n:
        ch = src[i]
        if ch == "\n":
            line += 1; i += 1; continue
        if ch in SPACE:
            i += 1; continue
        if ch == "#":
            while i < n and src[i] != "\n":
                i += 1
            continue

        start = i

        if ch == '"':
            j = src.find('"', i + 1)
            nl = src.find("\n", i + 1)
            if j < 0 or (0 <= nl < j):
                out.fail = Fail("lex", unterminated("unbounded"), start, line)
                return out
            out.toks.append(Tok("STR", src[i:j + 1], start, line))
            i = j + 1
            continue

        if ch.isdigit():
            m = re.compile(r"\d+\.\d+|\d+").match(src, i)
            out.toks.append(Tok("NUM", m.group(), start, line))
            i = m.end()
            continue

        if ch.isalpha() or ch == "_":
            m = re.compile(r"[A-Za-z_]\w*").match(src, i)
            text = m.group()
            out.toks.append(
                Tok("KW" if text in kw else "NAME", text, start, line))
            i = m.end()
            continue

        # walk the trie for the longest operator that matches
        node, j, best = _TRIE, i, None
        while j < n and src[j] in node:
            node = node[src[j]]
            j += 1
            if _END in node:
                best = (node[_END], j)
        if best is None:
            out.fail = Fail("lex", "misbound", start, line)
            return out
        (text, kind), end = best
        if text in ("<", ">"):
            kind = cmp_kind("OP")
        out.toks.append(Tok(kind, text, start, line))
        i = end

    out.toks.append(_eof(i, line))
    return out


# ═════════════════════════════════════════════
# Registry
# ═════════════════════════════════════════════

LEXERS = {
    "L1-regex-master": lex_regex_master,
    "L2-handrolled":   lex_handrolled,
    "L3-dfa":          lex_dfa,
    "L4-trie":         lex_trie,
}

__all__ = ["LEXERS", "KEYWORDS", "lex_regex_master", "lex_handrolled",
           "lex_dfa", "lex_trie"]
