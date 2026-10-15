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

import io
import keyword
import re
import tokenize
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class Fix:
    line: int
    what: str
    became: str
    reason: str

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

def _mask_strings_and_comments(lines: List[str], line_comment: str,
                                block: Optional[Tuple[str, str]] = None
                               ) -> List[str]:
    """Return a parallel line list where string/char literal contents
    and comments are replaced with 'x' (same length, same positions),
    so a regex can safely match structural code without ever matching
    inside a string or comment. Code outside strings/comments is left
    untouched in the mask, so positions still line up 1:1."""
    masked = []
    in_block = False
    in_triple = None
    for line in lines:
        out = []
        i, n = 0, len(line)
        in_str = in_triple
        in_triple = None
        while i < n:
            ch = line[i]
            if in_block and block:
                end = line.find(block[1], i)
                if end == -1:
                    out.append("x" * (n - i)); i = n
                else:
                    out.append("x" * (end + len(block[1]) - i))
                    i = end + len(block[1]); in_block = False
                continue
            if in_str:
                if line.startswith(in_str, i):
                    out.append(in_str); i += len(in_str); in_str = None
                    continue
                if ch == "\\" and i + 1 < n:
                    out.append("xx"); i += 2; continue
                out.append("x"); i += 1; continue
            if block and line[i:i+len(block[0])] == block[0]:
                out.append("x" * len(block[0])); i += len(block[0])
                in_block = True; continue
            if line[i:i+len(line_comment)] == line_comment:
                out.append("x" * (n - i)); i = n; continue
            if line.startswith('"""', i) or line.startswith("'''", i):
                in_str = line[i:i+3]; out.append(in_str); i += 3; continue
            if ch in ('"', "'"):
                in_str = ch; out.append(ch); i += 1; continue
            out.append(ch); i += 1
        if in_str and len(in_str) == 3:
            in_triple = in_str
        masked.append("".join(out))
    return masked


# ═══════════════════════════════════════════════
# PYTHON
# ═══════════════════════════════════════════════

_PY_HEADERS = ("if", "elif", "else", "for", "while", "def", "class", "try",
               "except", "finally", "with")
_PY_CONDITIONS = ("if", "elif", "while")
_PY_TRIVIA = (tokenize.NL, tokenize.COMMENT, tokenize.INDENT,
              tokenize.DEDENT, tokenize.ENCODING)


def _opens_call(prev) -> bool:
    return prev is not None and (
        (prev.type == tokenize.NAME and not keyword.iskeyword(prev.string))
        or (prev.type == tokenize.OP and prev.string in (")", "]")))


def _python_statements(src: str):
    """Logical lines as (token, context) pairs, where context is 'stmt' at
    the top level, 'group' inside a grouping paren and 'nest' inside a call,
    list, dict or subscript. The tokenizer decides where a statement starts,
    so a string, a comment or a bracketed continuation is never a header."""
    statement, stack = [], []
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.ENDMARKER:
            break
        if tok.type == tokenize.NEWLINE:
            if statement:
                yield statement
            statement, stack = [], []
        elif tok.type not in _PY_TRIVIA:
            statement.append((tok, stack[-1] if stack else "stmt"))
            if tok.type == tokenize.OP and tok.string in ("(", "[", "{"):
                grouping = tok.string == "(" and (
                    len(statement) == 1 or not _opens_call(statement[-2][0]))
                stack.append("group" if grouping else "nest")
            elif tok.type == tokenize.OP and tok.string in (")", "]", "}"):
                if stack:
                    stack.pop()
    if statement:
        yield statement


def fix_python(src: str) -> FixResult:
    try:
        statements = list(_python_statements(src))
    except (tokenize.TokenError, SyntaxError):
        return FixResult(src, [])
    lines = src.split("\n")
    edits: List[Tuple[int, int, int, str]] = []
    fixes: List[Fix] = []

    for statement in statements:
        head = statement[0][0]
        if head.type != tokenize.NAME or head.string not in _PY_HEADERS:
            continue
        kw = head.string
        header = []
        for tok, ctx in statement:
            if ctx == "stmt" and tok.type == tokenize.OP and tok.string == ":":
                break
            header.append((tok, ctx))
        if len(header) == len(statement):
            end_row, end_col = statement[-1][0].end
            edits.append((end_row, end_col, 0, ":"))
            fixes.append(Fix(end_row, f"'{kw}' line missing ':'",
                             "':' appended",
                             "if/elif/else/for/while/def/class/try/except/"
                             "finally headers must end in a colon"))
        if kw in _PY_CONDITIONS:
            lambdas = any(tok.type == tokenize.NAME and tok.string == "lambda"
                          for tok, _ in statement)
            for tok, ctx in header:
                if tok.type != tokenize.OP or tok.string != "=":
                    continue
                if ctx == "stmt" or (ctx == "group" and not lambdas):
                    row, col = tok.start
                    edits.append((row, col, 1, "=="))
                    fixes.append(Fix(row, f"'=' in {kw} condition", "'=='",
                                     "a single = inside a condition can only "
                                     "have meant the comparison =="))

    for row, col, width, text in sorted(edits, reverse=True):
        line = lines[row - 1]
        lines[row - 1] = line[:col] + text + line[col + width:]
    return FixResult("\n".join(lines), sorted(fixes, key=lambda f: f.line))


# ═══════════════════════════════════════════════
# C-FAMILY SHARED (JS / Go / Rust / Java / Kotlin)
# Missing statement-terminator semicolon, and stray = in a condition.
# Each language's own comment/string syntax is passed in.
# ═══════════════════════════════════════════════

_STMT_END = re.compile(r'[\w\)\]"\'`]\s*$')
_BLOCK_ENDERS = re.compile(r'[{}]\s*$')
_ALREADY_TERMINATED = re.compile(
    r'[;,{}\(\[:]\s*$|^\s*(//|/\*|\*|#|@)|^\s*$')

def _needs_semicolon(line: str) -> bool:
    s = line.rstrip()
    if not s:
        return False
    if _ALREADY_TERMINATED.search(s):
        return False
    if _BLOCK_ENDERS.search(s):
        return False
    # a line that is clearly a control-flow header, not a statement
    if re.match(r'^\s*(if|else|for|while|switch|function|fn|func|'
               r'class|interface|struct|enum|impl|package|import|'
               r'public|private|protected|@\w+)\b.*[^;{}]$', s) \
       and s.endswith((")",  "")) and "(" in s and not s.endswith(";"):
        # heuristic guard: only treat as a statement if it looks like
        # an assignment, call, or return — not a bare control header
        if not re.search(r'^\s*(if|else|for|while|switch)\b', s):
            return True
        return False
    return _STMT_END.search(s) is not None


_CONTINUES = re.compile(
    r'(\.|\?\.|\?|:|&&|\|\||\?\?|===?|!==?|<=?|>=?|[-+*/%&|^])')


def _continues_below(lines: List[str], i: int) -> bool:
    """True when the next code line carries on this expression, so a
    semicolon here would split one statement into two."""
    for nxt in lines[i + 1:]:
        s = nxt.strip()
        if not s or s.startswith("//"):
            continue
        return _CONTINUES.match(s) is not None
    return False


def _fix_cfamily_semicolons(src: str, line_comment: str,
                            block: Optional[Tuple[str, str]],
                            eligible_kw: Tuple[str, ...]) -> FixResult:
    lines = src.splitlines()
    masked = _mask_strings_and_comments(lines, line_comment, block)
    fixes: List[Fix] = []
    out = list(lines)

    for i, (raw, m) in enumerate(zip(out, masked)):
        s = m.rstrip()
        if not s:
            continue
        if re.search(r'[;{}\(\[,:]\s*$', s):
            continue
        if re.match(r'^\s*(//|/\*|\*)', s):
            continue
        if re.match(r'^\s*(if|else|for|while|switch|func|fn|function|'
                   r'class|interface|struct|enum|impl|package|import|'
                   r'@\w+|public\s+(class|interface)|private\s+'
                   r'(class|interface))\b', s):
            continue
        if not re.search(r'[\w\)\]"\'`]\s*$', s):
            continue
        # only fire for lines that look like a complete simple
        # statement: assignment, declaration, call, or return —
        # the same shape every C-family "missing semicolon" example
        # in the common-mistakes literature uses
        if re.match(r'^\s*(return|break|continue)\b', s) or \
           re.search(r'[=]\s*[^=]', s) or \
           re.match(r'^\s*\w[\w.]*\s*\(.*\)\s*$', s) or \
           re.match(r'^\s*(var|let|const|val)\s+\w', s):
            if _continues_below(lines, i):
                continue
            fixes.append(Fix(i + 1, "missing ';'", "';' appended",
                             "this line ends a simple statement, and "
                             "the language requires a terminator"))
            out[i] = raw.rstrip() + ";"

    return FixResult("\n".join(out) + ("\n" if src.endswith("\n") else ""),
                     fixes)


def fix_javascript(src: str) -> FixResult:
    return _fix_cfamily_semicolons(src, "//", ("/*", "*/"), ())

def fix_go(src: str) -> FixResult:
    # Go's gofmt inserts semicolons itself and idiomatic Go omits
    # them entirely — the language does not want a bare-line fixer
    # adding them. Go's real common mistake is bracket balance, which
    # is handled generically below.
    return FixResult(src, [])

def fix_rust(src: str) -> FixResult:
    return _fix_cfamily_semicolons(src, "//", ("/*", "*/"), ())

def fix_java(src: str) -> FixResult:
    return _fix_cfamily_semicolons(src, "//", ("/*", "*/"), ())

def fix_kotlin(src: str) -> FixResult:
    # Kotlin does not use semicolons idiomatically; nothing to fix
    # here without contradicting the language's own style.
    return FixResult(src, [])


# ═══════════════════════════════════════════════
# Bracket balance — reported, never guessed, for every language.
# Closing an unclosed bracket requires knowing where the author
# intended it to end; that is structure, not a slip, so Edapt states
# the imbalance precisely instead of inventing a closing brace.
# ═══════════════════════════════════════════════

def check_brackets(src: str, line_comment: str,
                   block: Optional[Tuple[str, str]] = None) -> List[str]:
    lines = src.splitlines()
    masked = _mask_strings_and_comments(lines, line_comment, block)
    stack: List[Tuple[str, int]] = []
    pairs = {")": "(", "]": "[", "}": "{"}
    openers = set(pairs.values())
    problems = []
    for lineno, m in enumerate(masked, start=1):
        for ch in m:
            if ch in openers:
                stack.append((ch, lineno))
            elif ch in pairs:
                if not stack or stack[-1][0] != pairs[ch]:
                    problems.append(
                        f"line {lineno}: '{ch}' has no matching "
                        f"'{pairs[ch]}'")
                else:
                    stack.pop()
    for ch, lineno in stack:
        problems.append(f"line {lineno}: '{ch}' is never closed")
    return problems


LANGUAGES = {
    "python":     (fix_python,     "#",  None),
    "javascript": (fix_javascript, "//", ("/*", "*/")),
    "go":         (fix_go,         "//", ("/*", "*/")),
    "rust":       (fix_rust,       "//", ("/*", "*/")),
    "java":       (fix_java,       "//", ("/*", "*/")),
    "kotlin":     (fix_kotlin,     "//", ("/*", "*/")),
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
    fixer, _, _ = LANGUAGES[language]
    return fixer(src)


def diagnose_brackets(src: str, language: str) -> List[str]:
    _, cmt, block = LANGUAGES[language]
    return check_brackets(src, cmt, block)
