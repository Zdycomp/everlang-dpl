"""Shared DPL grammar pieces: token kinds, AST nodes, diagnostics, and the
recursive-descent statement parser used by both the baseline parser and the
Quantification Ultra Parser's slow path. See README.md for the grammar."""
from typing import List, NamedTuple, Optional, Tuple, Union

KW_PARTICLE = "KW_PARTICLE"
KW_COLLIDE = "KW_COLLIDE"
KW_CONFIDENCE = "KW_CONFIDENCE"
IDENT = "IDENT"
INT = "INT"
STRING = "STRING"
COLON = "COLON"
LT = "LT"
GT = "GT"
EQ = "EQ"
AT = "AT"
LPAREN = "LPAREN"
RPAREN = "RPAREN"
ARROW = "ARROW"
NEWLINE = "NEWLINE"
ERROR = "ERROR"
EOF = "EOF"

KEYWORDS = {"particle": KW_PARTICLE, "collide": KW_COLLIDE, "confidence": KW_CONFIDENCE}
SYMBOLS = {":": COLON, "<": LT, ">": GT, "=": EQ, "@": AT, "(": LPAREN, ")": RPAREN}


class Token(NamedTuple):
    kind: str
    text: str
    line: int
    col: int


class Diagnostic(NamedTuple):
    stage: str
    severity: str
    line: int
    col: int
    message: str
    hint: str


class Declaration(NamedTuple):
    name: str
    type_spec: str
    value: str
    confidence: int
    line: int


class Collision(NamedTuple):
    left: str
    right: str
    target: Optional[str]
    line: int


Statement = Union[Declaration, Collision]


class TokenStream(tuple):
    """An immutable token sequence that also records the indices where the
    lexer already verified a complete, newline/EOF-terminated declaration.
    Immutability is what keeps that index trustworthy."""

    def __new__(cls, tokens, declaration_starts=()):
        self = super().__new__(cls, tokens)
        self.declaration_starts = tuple(declaration_starts)
        return self


class ParseResult(NamedTuple):
    statements: List[Statement]
    diagnostics: List[Diagnostic]


# (kind, required text, what was expected, fix hint) for each token after `particle`.
DECLARATION_STEPS: Tuple[Tuple[str, Optional[str], str, str], ...] = (
    (IDENT, None, "a particle name", "name the particle, e.g. `particle rate : E<float> = \"0.5\" @ confidence(200)`"),
    (COLON, None, "':'", "separate the name from its type with ':'"),
    (IDENT, "E", "'E'", "particle types are written E<Type>"),
    (LT, None, "'<'", "particle types are written E<Type>"),
    (IDENT, None, "a type name", "put a type inside E<...>, e.g. E<float>"),
    (GT, None, "'>'", "close the type with '>'"),
    (EQ, None, "'='", "assign the value with '=' after the type"),
    (STRING, None, "a quoted value", "values are double-quoted strings, e.g. \"0.5\""),
    (AT, None, "'@'", "attach confidence with `@ confidence(N)`"),
    (KW_CONFIDENCE, None, "'confidence'", "attach confidence with `@ confidence(N)`"),
    (LPAREN, None, "'('", "write confidence as confidence(N)"),
    (INT, None, "a confidence number", "confidence is a whole number from 0 to 256"),
    (RPAREN, None, "')'", "close confidence(N) with ')'"),
)
DECLARATION_KINDS = [KW_PARTICLE] + [step[0] for step in DECLARATION_STEPS]

_NAME, _TYPE, _VALUE, _CONF = 0, 4, 7, 11


def describe(tok) -> str:
    kind, text = tok[0], tok[1]
    if kind == NEWLINE:
        return "end of line"
    if kind == EOF:
        return "end of file"
    if kind == STRING:
        return f'string "{text}"'
    return f"'{text}'"


def skip_line(toks, i: int) -> int:
    """Returns the index just past the current line's NEWLINE (or at EOF)."""
    while toks[i][0] != NEWLINE and toks[i][0] != EOF:
        i += 1
    return i + 1 if toks[i][0] == NEWLINE else i


def _fail(toks, i: int, expected: str, hint: str, diags: List[Diagnostic]) -> int:
    tok = toks[i]
    if tok[0] != ERROR:  # the lexer already reported bad characters
        diags.append(Diagnostic("parse", "error", tok[2], tok[3],
                                f"expected {expected}, found {describe(tok)}", hint))
    return skip_line(toks, i)


def _finish(toks, i: int, node: Statement, diags: List[Diagnostic]):
    kind = toks[i][0]
    if kind == NEWLINE:
        return node, i + 1
    if kind == EOF:
        return node, i
    return None, _fail(toks, i, "end of line", "put each statement on its own line", diags)


def parse_statement(toks, i: int, diags: List[Diagnostic]):
    """Parses one line starting at toks[i]. Returns (statement or None, next index).
    Errors are appended to `diags`; the rest of a bad line is skipped."""
    kind = toks[i][0]
    if kind == NEWLINE:
        return None, i + 1
    if kind == ERROR:
        return None, skip_line(toks, i)
    if kind == KW_PARTICLE:
        values = []
        j = i + 1
        for step_kind, required, expected, hint in DECLARATION_STEPS:
            tok = toks[j]
            if tok[0] != step_kind or (required is not None and tok[1] != required):
                return None, _fail(toks, j, expected, hint, diags)
            values.append(tok[1])
            j += 1
        node = Declaration(values[_NAME], values[_TYPE], values[_VALUE], int(values[_CONF]), toks[i][2])
        return _finish(toks, j, node, diags)
    if kind == KW_COLLIDE:
        j = i + 1
        if toks[j][0] != IDENT:
            return None, _fail(toks, j, "a particle name", "write `collide a b`", diags)
        if toks[j + 1][0] != IDENT:
            return None, _fail(toks, j + 1, "a second particle name", "write `collide a b`", diags)
        left, right = toks[j][1], toks[j + 1][1]
        j += 2
        target = None
        if toks[j][0] == ARROW:
            if toks[j + 1][0] != IDENT:
                return None, _fail(toks, j + 1, "a name after '->'", "write `collide a b -> c` to bind the result", diags)
            target = toks[j + 1][1]
            j += 2
        return _finish(toks, j, Collision(left, right, target, toks[i][2]), diags)
    return None, _fail(toks, i, "'particle' or 'collide'", "statements start with `particle` or `collide`", diags)
