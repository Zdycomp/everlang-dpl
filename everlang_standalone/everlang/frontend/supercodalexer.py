"""Supercodalexer: token-for-token identical to BaselineLexer, but scanning in C.
A well-formed declaration line is matched whole by one regex and its 14 token
positions read from the match's spans at once; any other line is scanned token
by token with a single master regex."""
import re
from itertools import repeat
from operator import add, itemgetter
from typing import List, Tuple

from .grammar import (
    ARROW, AT, COLON, DECLARATION_KINDS, EOF, EQ, ERROR, GT, IDENT, INT, KEYWORDS, KW_COLLIDE,
    KW_CONFIDENCE, KW_PARTICLE, LPAREN, LT, NEWLINE, RPAREN, STRING, SYMBOLS, TokenStream,
)
from .results import bad_string, unexpected_char

# Fast-path line shapes. Identifier groups here may capture a keyword (e.g. a
# particle named `collide`); the caller rejects those and rescans the line, since
# the master regex would lex them as keywords.
_WORD_END = r'(?![A-Za-z0-9_])'
_NAME = r'[A-Za-z_][A-Za-z0-9_]*'
# Unrolled-loop forms of "(?:[^"\\\n]|\\["\\])*" and "(?:[^"\\\n]|\\.)*": same
# language and greedy extent, without an alternation per character.
_STRING = r'"[^"\\\n]*(?:\\["\\][^"\\\n]*)*"'
_BADSTR = r'"[^"\\\n]*(?:\\.[^"\\\n]*)*"?'
_LINE_END = r'[ \t]*(?:#[^\n]*)?(\n|\Z)'
_DECL_LINE = re.compile(
    r'[ \t]*(particle)' + _WORD_END
    + r'[ \t]*(' + _NAME + r')'
    + r'[ \t]*(:)'
    + r'[ \t]*(E)' + _WORD_END
    + r'[ \t]*(<)'
    + r'[ \t]*(' + _NAME + r')'
    + r'[ \t]*(>)'
    + r'[ \t]*(=)'
    + r'[ \t]*(' + _STRING + r')'
    + r'[ \t]*(@)'
    + r'[ \t]*(confidence)' + _WORD_END
    + r'[ \t]*(\()'
    + r'[ \t]*([0-9]+)'
    + r'[ \t]*(\))'
    + _LINE_END
)
_COLLIDE_LINE = re.compile(
    r'[ \t]*(collide)' + _WORD_END
    + r'[ \t]*(' + _NAME + r')' + _WORD_END  # without the guard, backtracking splits `_x9` into `_` and `x9`
    + r'[ \t]*(' + _NAME + r')' + _WORD_END
    + r'(?:[ \t]*(->)[ \t]*(' + _NAME + r')' + _WORD_END + r')?'
    + _LINE_END
)
# SuperTranspiler's own DPL spacing: every column follows from the field lengths.
_CANONICAL_DECL = re.compile(
    r'particle (' + _NAME + r') : E<(' + _NAME + r')> = (' + _STRING + r') '
    r'@ confidence\(([0-9]+)\)(\n|\Z)'
)
_DECL_KINDS = tuple(DECLARATION_KINDS)
_START = itemgetter(0)

# Leading spaces/tabs are folded into each match so whitespace never costs a
# separate iteration. Alternative order matters: STRING (well-formed) is tried
# before BADSTR, which catches unterminated strings and unknown escapes with the
# same extent BaselineLexer gives them.
_MASTER = re.compile(
    r'[ \t]*(?:'
    r'(?P<NL>\n)'
    r'|(?P<COMMENT>#[^\n]*)'
    r'|(?P<IDENT>[A-Za-z_][A-Za-z0-9_]*)'
    r'|(?P<INT>[0-9]+)'
    r'|(?P<STRING>' + _STRING + r')'
    r'|(?P<ARROW>->)'
    r'|(?P<SYM>[:<>=@()])'
    r'|(?P<BADSTR>' + _BADSTR + r')'
    r'|(?P<ERR>[^ \t\n])'  # not `.`: backtracking would hand ERR a trailing space at end of input
    r')'
)
_UNESCAPE = re.compile(r'\\(["\\])')


class Supercodalexer:
    def lex(self, source: str) -> Tuple[TokenStream, list]:
        src = source.replace("\r\n", "\n")
        n = len(src)
        toks: List[tuple] = []
        starts: List[int] = []
        diags = []
        append, extend, mark = toks.append, toks.extend, starts.append
        canonical_match, decl_match, collide_match = _CANONICAL_DECL.match, _DECL_LINE.match, _COLLIDE_LINE.match
        line, pos = 1, 0
        while pos < n:
            m = canonical_match(src, pos)
            if m is not None:
                name, type_spec, raw, conf, nl = m.groups()
                if name not in KEYWORDS and type_spec not in KEYWORDS:
                    value = raw[1:-1]
                    if "\\" in value:
                        value = _UNESCAPE.sub(r"\1", value)
                    colon = 11 + len(name)
                    gt = colon + 4 + len(type_spec)
                    at = gt + 5 + len(raw)
                    rparen = at + 13 + len(conf)
                    mark(len(toks))
                    extend((
                        (KW_PARTICLE, "particle", line, 1),
                        (IDENT, name, line, 10),
                        (COLON, ":", line, colon),
                        (IDENT, "E", line, colon + 2),
                        (LT, "<", line, colon + 3),
                        (IDENT, type_spec, line, colon + 4),
                        (GT, ">", line, gt),
                        (EQ, "=", line, gt + 2),
                        (STRING, value, line, gt + 4),
                        (AT, "@", line, at),
                        (KW_CONFIDENCE, "confidence", line, at + 2),
                        (LPAREN, "(", line, at + 12),
                        (INT, conf, line, at + 13),
                        (RPAREN, ")", line, rparen),
                    ))
                    if nl:
                        append((NEWLINE, "\n", line, rparen + 1))
                        line += 1
                    pos = m.end()
                    continue
            m = decl_match(src, pos)
            if m is not None:
                name, type_spec, value, conf = m.group(2, 6, 9, 13)
                if name not in KEYWORDS and type_spec not in KEYWORDS:
                    value = value[1:-1]
                    if "\\" in value:
                        value = _UNESCAPE.sub(r"\1", value)
                    mark(len(toks))
                    r = m.regs
                    texts = ("particle", name, ":", "E", "<", type_spec, ">", "=",
                             value, "@", "confidence", "(", conf, ")")
                    cols = map(add, map(_START, r[1:15]), repeat(1 - pos))
                    extend(zip(_DECL_KINDS, texts, repeat(line), cols))
                    nl_start, nl_end = r[15]
                    if nl_end > nl_start:
                        append((NEWLINE, "\n", line, nl_start - pos + 1))
                        line += 1
                    pos = nl_end
                    continue
            else:
                m = collide_match(src, pos)
                if m is not None:
                    left, right, arrow, target = m.group(2, 3, 4, 5)
                    if left not in KEYWORDS and right not in KEYWORDS and target not in KEYWORDS:
                        r = m.regs
                        off = 1 - pos
                        append((KW_COLLIDE, "collide", line, r[1][0] + off))
                        append((IDENT, left, line, r[2][0] + off))
                        append((IDENT, right, line, r[3][0] + off))
                        if arrow is not None:
                            append((ARROW, "->", line, r[4][0] + off))
                            append((IDENT, target, line, r[5][0] + off))
                        nl_start, nl_end = r[6]
                        if nl_end > nl_start:
                            append((NEWLINE, "\n", line, nl_start + off))
                            line += 1
                        pos = nl_end
                        continue
            pos, line = self._scan_line(src, pos, line, append, diags)
        line_start = src.rfind("\n") + 1
        append((EOF, "", line, n - line_start + 1))
        return TokenStream(toks, starts), diags

    @staticmethod
    def _scan_line(src, pos, line, append, diags):
        """Token-by-token scan of one line starting at `pos` (a line start).
        Returns (next line start, next line number)."""
        line_start = pos
        master_match = _MASTER.match
        while True:
            m = master_match(src, pos)
            if m is None:  # only trailing spaces/tabs before end of input remain
                return len(src), line
            kind = m.lastgroup
            start = m.start(kind)
            col = start - line_start + 1
            pos = m.end()
            if kind == "NL":
                append((NEWLINE, "\n", line, col))
                return pos, line + 1
            if kind == "IDENT":
                text = m.group(kind)
                append((KEYWORDS.get(text, IDENT), text, line, col))
            elif kind == "SYM":
                text = m.group(kind)
                append((SYMBOLS[text], text, line, col))
            elif kind == "STRING":
                text = m.group(kind)[1:-1]
                if "\\" in text:
                    text = _UNESCAPE.sub(r"\1", text)
                append((STRING, text, line, col))
            elif kind == "INT":
                append((INT, m.group(kind), line, col))
            elif kind == "ARROW":
                append((ARROW, "->", line, col))
            elif kind == "COMMENT":
                continue
            else:
                text = m.group(kind)
                append((ERROR, text, line, col))
                if kind == "ERR":
                    diags.append(unexpected_char(text, line, col))
                else:
                    closed = len(text) > 1 and text.endswith('"') and not _ends_escaped(text)
                    diags.append(bad_string(closed, line, col))


def _ends_escaped(lexeme: str) -> bool:
    """True if the final '"' of a BADSTR lexeme is an escape (\\"), i.e. not a closing quote."""
    backslashes = 0
    i = len(lexeme) - 2
    while i > 0 and lexeme[i] == "\\":
        backslashes += 1
        i -= 1
    return backslashes % 2 == 1
