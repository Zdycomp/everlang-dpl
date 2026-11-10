#!/usr/bin/env python3
"""
edapt — bridges and fixes common mistakes across real languages.

WHAT THIS IS

Ever's own forgiving layer (forgive.py) heals well-defined slips in
Ever source. Edapt is the same discipline pointed outward: a small,
honest set of deterministic fixes for the most common syntax mistakes
in Python, JavaScript, Go, Rust, and Java/Kotlin — sourced from what
is actually documented as common across those languages, not guessed.

WHAT THIS IS NOT

Not a universal parser for five languages. Edapt does not build an
AST for your Python file; it recognizes specific, well-known mistake
SHAPES with targeted, conservative regex/line rules and fixes only
the ones it can fix without guessing structure. A file it doesn't
recognize is left alone and reported as unhandled — never silently
skipped and never guessed at.

Every fixer here was verified by actually compiling or running the
before/after pair through the real toolchain (python3, node, go,
rustc, javac) — see tests/test_edapt.py. A fixer that has not been
run through its real compiler does not belong in this file.

Codric Enterprise · Ricky (Dreid) · 2026
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class Fix:
    line: int
    what: str
    became: str
    reason: str
    form: str = ""  # SEMANTICS.md §9.5. structured edit, replayable.
    kind: int = 1   # 0 plain, 1 inferred. SEMANTICS.md §9.2.
    name: str = ""  # canonical repair name, same role as forgive.Correction.name.

    def line1(self) -> str:
        return f"line {self.line}: {self.what} → {self.became}"


@dataclass
class FixResult:
    code:  str
    fixes: List[Fix] = field(default_factory=list)


# ═══════════════════════════════════════════════
# Shared helpers — string/comment-aware scanning so a fix never
# touches text inside a literal or a comment.
# ═══════════════════════════════════════════════

@dataclass(frozen=True)
class _Syntax:
    line_comment: str
    block: Optional[Tuple[str, str]] = None
    triple: Tuple[str, ...] = ()   # delimiters of strings that span lines
    multiline: str = ""            # one-char quotes that may span lines
    raw: str = ""                  # one-char quotes with no backslash escapes
    regex: bool = False            # /.../ literals (JavaScript)
    template: str = ""             # quote whose ${ ... } holds code
    lifetimes: bool = False        # 'a is a lifetime, not a char (Rust)


_SYNTAX: Dict[str, _Syntax] = {
    "python":     _Syntax("#", triple=('"""', "'''")),
    "javascript": _Syntax("//", ("/*", "*/"), multiline="`", regex=True,
                          template="`"),
    "go":         _Syntax("//", ("/*", "*/"), multiline="`", raw="`"),
    "rust":       _Syntax("//", ("/*", "*/"), multiline='"', lifetimes=True),
    "java":       _Syntax("//", ("/*", "*/"), triple=('"""',)),
    "kotlin":     _Syntax("//", ("/*", "*/"), triple=('"""',)),
}

# A '/' after one of these starts a regex literal, not a division.
_REGEX_AFTER_CHAR = set("(,=:[!&|?{};+-*%<>~^")
_REGEX_AFTER_WORD = {"return", "typeof", "case", "in", "of", "do", "else",
                     "void", "delete", "throw", "new", "instanceof",
                     "yield", "await"}
_RUST_CHAR = re.compile(r"'(\\.[^']*|[^\\'])'")
_RUST_RAW = re.compile(r'b?r(#*)"')
_WORD = "_$"
_FILL = "\0"


def _regex_end(line: str, i: int) -> int:
    """Index just past the regex literal opening at line[i], or -1."""
    j, in_class = i + 1, False
    while j < len(line):
        c = line[j]
        if c == "\\":
            j += 2; continue
        if c == "[":
            in_class = True
        elif c == "]":
            in_class = False
        elif c == "/" and not in_class:
            return j + 1
        j += 1
    return -1


def _mask(lines: List[str], syn: _Syntax,
          unterminated: Optional[List[int]] = None,
          open_ended: Optional[List[int]] = None) -> List[str]:
    """Return a parallel line list, same lengths and positions, where
    every character inside a string, char or regex literal is _FILL and
    every comment is blanked. Delimiters are kept. State carries across
    lines, so a docstring, template literal, text block or block comment
    is masked for its whole extent. _FILL is neither a word character
    nor a bracket, so a line that starts or ends inside a literal never
    looks like code. Line numbers of strings that never close are
    appended to `unterminated`, and of lines that end with a string
    still open (it closes further down) to `open_ended`."""
    masked = []
    opened = 0            # line the open string started on
    in_block = False
    delim = None          # closing delimiter of the open string, if any
    escapes = spans = False
    last = ""             # last significant code token, for regex detection
    holes: List[int] = [] # open-brace depth inside each ${ ... } we are in
    for line in lines:
        out = []
        i, n = 0, len(line)
        word_end = -1
        while i < n:
            ch = line[i]
            if in_block:
                end = line.find(syn.block[1], i)
                stop = n if end == -1 else end + len(syn.block[1])
                out.append(" " * (stop - i)); i = stop
                in_block = end == -1
                continue
            if delim:
                if escapes and ch == "\\":
                    out.append(_FILL * min(2, n - i)); i += 2
                    continue
                if line.startswith(delim, i):
                    out.append(delim); i += len(delim); delim = None
                    last = '"'
                    continue
                if delim == syn.template and line.startswith("${", i):
                    out.append(_FILL * 2); i += 2
                    holes.append(0); delim = None; last = "("
                    continue
                out.append(_FILL); i += 1
                continue
            if syn.block and line.startswith(syn.block[0], i):
                out.append(" " * len(syn.block[0])); i += len(syn.block[0])
                in_block = True; continue
            if line.startswith(syn.line_comment, i):
                out.append(" " * (n - i)); i = n; continue
            if syn.lifetimes and word_end != i:
                m = _RUST_RAW.match(line, i)
                if m:
                    out.append(m.group(0)); i = m.end()
                    delim, escapes, spans = '"' + m.group(1), False, True
                    opened = len(masked) + 1
                    continue
            hit = next((t for t in syn.triple if line.startswith(t, i)), None)
            if hit:
                out.append(hit); i += len(hit)
                delim, escapes, spans = hit, True, True
                opened = len(masked) + 1
                continue
            if ch == "'" and syn.lifetimes:
                m = _RUST_CHAR.match(line, i)
                if m:
                    out.append("'" + _FILL * (len(m.group(0)) - 2) + "'")
                    i = m.end(); last = '"'
                else:
                    out.append(ch); i += 1
                continue
            if ch in "\"'" or ch in syn.multiline:
                out.append(ch); i += 1
                delim, escapes = ch, ch not in syn.raw
                spans = ch in syn.multiline
                opened = len(masked) + 1
                continue
            if ch == "/" and syn.regex and (
                    not last or last[-1] in _REGEX_AFTER_CHAR
                    or last in _REGEX_AFTER_WORD):
                end = _regex_end(line, i)
                if end != -1:
                    out.append("/" + _FILL * (end - i - 2) + "/")
                    i = end; last = '"'
                    continue
            if holes and ch == "{":
                holes[-1] += 1
            elif holes and ch == "}":
                if holes[-1] == 0:      # the hole closes: back to the template
                    holes.pop()
                    out.append(_FILL); i += 1
                    delim, escapes, spans = syn.template, True, True
                    continue
                holes[-1] -= 1
            out.append(ch)
            if ch.isalnum() or ch in _WORD:
                last = last + ch if word_end == i else ch
                word_end = i + 1
            elif not ch.isspace():
                last = ch
            i += 1
        if delim and not spans and not (escapes and line.endswith("\\")):
            delim = None   # an unterminated one-line string ends with its line
            if unterminated is not None:
                unterminated.append(opened)
        masked.append("".join(out))
        if delim and open_ended is not None:
            open_ended.append(len(masked))
    if delim and unterminated is not None:
        unterminated.append(opened)
    return masked


_PAIRS = {")": "(", "]": "[", "}": "{"}


def _contexts(masked: List[str], literal_brace=None
              ) -> Tuple[List[str], List[str]]:
    """For each line, the innermost open bracket at its start and at its
    end: '' at top level, '(' or '[', '{' for a block, 'L' for a brace
    that `literal_brace(before, enclosing)` says holds data, not
    statements. Mismatched closers are ignored — diagnosis is
    check_brackets' job."""
    stack: List[str] = []
    starts, ends = [], []
    before = ""
    for m in masked:
        starts.append(stack[-1] if stack else "")
        for tok in re.finditer(r"[A-Za-z_$][\w$]*|\S", m):
            t = tok.group(0)
            if t in "([":
                stack.append(t)
            elif t == "{":
                enclosing = stack[-1] if stack else ""
                stack.append("L" if literal_brace and
                             literal_brace(before, enclosing) else "{")
            elif t in _PAIRS:
                want = _PAIRS[t]
                if stack and (stack[-1] == want or
                              want == "{" and stack[-1] == "L"):
                    stack.pop()
            before = t
        ends.append(stack[-1] if stack else "")
    return starts, ends


def _next_code(masked: List[str], i: int) -> str:
    for m in masked[i + 1:]:
        if m.strip():
            return m.strip()
    return ""


def _bracket_balance(text: str) -> dict:
    """Count of each bracket kind, open minus close, over CODE ONLY
    (caller must pass masked text)."""
    return {
        "()": text.count("(") - text.count(")"),
        "[]": text.count("[") - text.count("]"),
        "{}": text.count("{") - text.count("}"),
    }


def _depth0(code: str, pattern: str) -> List[int]:
    """Positions where `pattern` matches outside every bracket."""
    hits, depth = [], 0
    rx = re.compile(pattern)
    for i, ch in enumerate(code):
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif depth == 0 and rx.match(code, i):
            hits.append(i)
    return hits


def _lines(src: str) -> List[str]:
    """Split on '\\n' only. str.splitlines() also breaks on U+0085,
    U+2028 and friends, which are legal inside a string literal."""
    lines = src.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def _join(out: List[str], src: str) -> str:
    return "\n".join(out) + ("\n" if src.endswith("\n") else "")


# ═══════════════════════════════════════════════
# PYTHON
# ═══════════════════════════════════════════════

_PY_BLOCK_KW = re.compile(
    r'^(\s*)(if|elif|else|for|while|def|class|try|except|finally|with)\b'
    r'(.*?)\s*$')
_PY_BARE_KW = ("else", "try", "finally")

def _py_logical_starts(masked: List[str]) -> List[bool]:
    """True for each line that begins a statement: not inside a bracket
    opened on an earlier line and not after a backslash continuation.
    A `for`/`if` inside a multi-line comprehension is not a header."""
    starts, _ = _contexts(masked)
    return [s == "" and not (i and masked[i-1].rstrip().endswith("\\"))
            for i, s in enumerate(starts)]


def fix_python(src: str) -> FixResult:
    syn = _SYNTAX["python"]
    lines = _lines(src)
    fixes: List[Fix] = []
    out = list(lines)

    broken: List[int] = []   # lines whose string never closes: not ours to fix
    masked = _mask(out, syn, broken, broken)
    logical = _py_logical_starts(masked)
    for i, (raw, m) in enumerate(zip(out, masked)):
        code = m.rstrip()
        mobj = _PY_BLOCK_KW.match(code)
        if not mobj or not logical[i] or i + 1 in broken:
            continue
        indent, kw, rest = mobj.groups()
        # A ':' outside every bracket means the header already has its
        # colon — `if x: continue` keeps its body on the same line.
        if _depth0(code, r":(?!=)"):
            continue
        if kw in _PY_BARE_KW and rest.strip():
            continue  # `else x` is not a header that lost its colon
        if code.endswith(("(", "[", "{", ",", "\\")):
            continue  # continuation line, not a finished header
        bal = _bracket_balance(code)
        if bal["()"] != 0 or bal["[]"] != 0 or bal["{}"] != 0:
            continue  # unbalanced on this line — don't guess
        fixes.append(Fix(i + 1, f"'{kw}' line missing ':'",
                         "':' appended",
                         "if/elif/else/for/while/def/class/try/except/"
                         "finally headers must end in a colon",
                         form="COLON_APPEND", kind=1, name="missing_colon"))
        # Insert at the end of the code, ahead of any trailing comment.
        out[i] = raw[:len(code)] + ":" + raw[len(code):]

    # = vs == inside an `if`/`elif`/`while` condition. Re-mask `out`,
    # not the original — a line can be missing BOTH the colon and have
    # the wrong operator, and the colon pass above already healed it.
    # Only a '=' outside every bracket is touched: inside one it is a
    # keyword argument (`if f(x=1):`), which is legal.
    masked2 = _mask(out, syn)
    logical = _py_logical_starts(masked2)
    for i, (raw, m) in enumerate(zip(out, masked2)):
        code = m.rstrip()
        cond = re.match(r'^(\s*)(if|elif|while)\b(.*):$', code)
        if not cond or not logical[i] or i + 1 in broken:
            continue
        kw = cond.group(2)
        stray = [p for p in _depth0(code[:-1], r"=")
                 if code[p+1:p+2] != "=" and code[p-1] not in "=!<>:+-*/%&|^@~"]
        if stray:
            fixes.append(Fix(i + 1, f"'=' in {kw} condition",
                             "'==' ",
                             "a single = inside a condition can only "
                             "have meant the comparison ==",
                             form="EQ_TO_CMP", kind=1,
                             name="equals_for_compare"))
            for p in reversed(stray):
                raw = raw[:p] + "==" + raw[p+1:]
            out[i] = raw

    return FixResult(_join(out, src), fixes)


# ═══════════════════════════════════════════════
# C-FAMILY SHARED (JS / Rust / Java)
# Missing statement-terminator semicolon. A ';' is appended only where
# the line is a whole statement on its own: it starts and ends directly
# inside a block (never inside ( ), [ ] or a data brace), and the next
# line does not carry the expression on.
# ═══════════════════════════════════════════════

_HEADER_KW = re.compile(
    r'^\s*(if|else|for|while|switch|func|fn|function|class|interface|'
    r'struct|enum|impl|trait|package|import|@\w+|public\s+(class|interface)|'
    r'private\s+(class|interface))\b')
# A line starting with one of these continues the statement before it.
_CONTINUES = re.compile(
    r'^([.?:*/%&|^<>=,)\]{]|[+-](?![+-])|'
    r'(else|where|as|instanceof|in|of|throws|extends|implements)\b)')
_DANGLING = re.compile(
    r'\b(new|typeof|instanceof|in|of|void|delete|throw|extends|case|else|'
    r'do|as|await|yield)$')
_LITERAL_BEFORE = {
    "javascript": (set("=(,[?|&"),
                   {"return", "const", "let", "var", "import", "export",
                    "case", "typeof", "in", "of", "yield", "await", "new",
                    "throw", "default"}),
    "java":       (set("=(,[]"), {"return"}),
    "rust":       (set("=(,[!"), set()),
}


def _literal_brace(language: str):
    chars, words = _LITERAL_BEFORE[language]
    def is_literal(before: str, enclosing: str) -> bool:
        if before == ":":   # `key: {` nests data; `case 1: {` opens a block
            return enclosing in ("L", "(", "[")
        return before in chars or before in words
    return is_literal


def _fix_semicolons(src: str, language: str) -> FixResult:
    lines = _lines(src)
    broken: List[int] = []   # lines that end inside a string: not ours to fix
    masked = _mask(lines, _SYNTAX[language], broken, broken)
    starts, ends = _contexts(masked, _literal_brace(language))
    rust = language == "rust"
    fixes: List[Fix] = []
    out = list(lines)
    found: List[Tuple[int, int, bool]] = []   # line index, insert column, ASI hazard

    for i, (raw, m) in enumerate(zip(out, masked)):
        s = m.rstrip()
        if not s or i + 1 in broken:
            continue
        if starts[i] not in ("", "{") or ends[i] not in ("", "{"):
            continue  # inside a call, an array or an object/struct literal
        if re.search(r'[;{}\(\[,:]\s*$', s):
            continue
        if _HEADER_KW.match(s):
            continue
        if re.match(r'^\s*[.?:+\-/%&|^<>=,)\]}#]', s):
            continue  # the tail of a longer expression, or an attribute
        if not re.search(r'[\w\)\]"\'`]\s*$', s):
            continue
        if _DANGLING.search(s):
            continue  # ends on a word that needs an operand
        nxt = _next_code(masked, i)
        if _CONTINUES.match(nxt):
            continue  # the statement carries on to the next line
        if rust:
            if "$" in s or "=>" in s:
                continue  # macro_rules body, or a match arm
            if re.match(r'^\s*(pub(\([^)]*\))?\s+)?\w+\s*:(?!:)', s):
                continue  # a struct field
            if nxt.startswith("}") and not re.match(r'^\s*let\b', s):
                continue  # a block's tail expression is its value
        # only fire for lines that look like a complete simple
        # statement: assignment, declaration, call, or return —
        # the same shape every C-family "missing semicolon" example
        # in the common-mistakes literature uses
        if re.match(r'^\s*(return|break|continue)\b', s) or \
           re.search(r'[=]\s*[^=]', s) or \
           re.match(r'^\s*\w[\w.]*\s*\(.*\)\s*$', s) or \
           re.match(r'^\s*(var|let|const|val)\s+\w', s):
            found.append((i, len(s), nxt[:1] in ("(", "[", "`")))

    # JavaScript inserts the terminator itself, so a file written without
    # semicolons is valid as it stands and is left alone. Where the lines
    # lacking one outnumber the lines that have one, only a line the next
    # one would swallow (it starts with ( [ or `) is still healed: that is
    # the one place the omission changes what the program means.
    if language == "javascript":
        have = sum(1 for m in masked if m.rstrip().endswith(";"))
        if len(found) > have:
            found = [f for f in found if f[2]]

    for i, col, _ in found:
        fixes.append(Fix(i + 1, "missing ';'", "';' appended",
                         "this line ends a simple statement, and "
                         "the language requires a terminator",
                         form="SEMI_APPEND", kind=1,
                         name="missing_semicolon"))
        # Insert at the end of the code, ahead of any trailing comment.
        out[i] = out[i][:col] + ";" + out[i][col:]

    return FixResult(_join(out, src), fixes)


def fix_javascript(src: str) -> FixResult:
    return _fix_semicolons(src, "javascript")

def fix_go(src: str) -> FixResult:
    # Go's gofmt inserts semicolons itself and idiomatic Go omits
    # them entirely — the language does not want a bare-line fixer
    # adding them. Go's real common mistake is bracket balance, which
    # is handled generically below.
    return FixResult(src, [])

def fix_rust(src: str) -> FixResult:
    return _fix_semicolons(src, "rust")

def fix_java(src: str) -> FixResult:
    return _fix_semicolons(src, "java")

def fix_kotlin(src: str) -> FixResult:
    # Kotlin does not use semicolons idiomatically; nothing to fix
    # here without contradicting the language's own style.
    return FixResult(src, [])


# ═══════════════════════════════════════════════
# Bracket balance and unterminated strings — reported, never guessed,
# for every language (SEMANTICS.md §9.4). Closing an unclosed bracket
# or string requires knowing where the author intended it to end; that
# is structure, not a slip, so Edapt states the imbalance precisely
# instead of inventing a closer.
# ═══════════════════════════════════════════════

def check_brackets(src: str, language: str) -> List[str]:
    unterminated: List[int] = []
    masked = _mask(_lines(src), _SYNTAX[language], unterminated)
    stack: List[Tuple[str, int]] = []
    openers = set(_PAIRS.values())
    problems = [f"line {n}: string is never closed" for n in unterminated]
    for lineno, m in enumerate(masked, start=1):
        for ch in m:
            if ch in openers:
                stack.append((ch, lineno))
            elif ch in _PAIRS:
                if not stack or stack[-1][0] != _PAIRS[ch]:
                    problems.append(
                        f"line {lineno}: '{ch}' has no matching "
                        f"'{_PAIRS[ch]}'")
                else:
                    stack.pop()
    for ch, lineno in stack:
        problems.append(f"line {lineno}: '{ch}' is never closed")
    return problems


LANGUAGES = {
    "python":     fix_python,
    "javascript": fix_javascript,
    "go":         fix_go,
    "rust":       fix_rust,
    "java":       fix_java,
    "kotlin":     fix_kotlin,
}

EXT_MAP = {
    ".py": "python", ".js": "javascript", ".mjs": "javascript",
    ".go": "go", ".rs": "rust", ".java": "java", ".kt": "kotlin",
}


def detect_language(path: str) -> Optional[str]:
    for ext, lang in EXT_MAP.items():
        if path.endswith(ext):
            return lang
    return None


def fix(src: str, language: str) -> FixResult:
    if language not in LANGUAGES:
        raise ValueError(f"unsupported language {language!r}; have "
                         f"{', '.join(sorted(LANGUAGES))}")
    return LANGUAGES[language](src)


def diagnose_brackets(src: str, language: str) -> List[str]:
    return check_brackets(src, language)
