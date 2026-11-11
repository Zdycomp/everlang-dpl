#!/usr/bin/env python3
"""
test_lexer.py — Ever / Tapestry, lexer unit tests

Tests that the lexer produces the EXACT token stream for every input:
correct kind, correct text, correct line number. No hand-waving.

Architecture note: these tests feed strings in and assert the output
token sequence precisely. They are the compile-time check on the lexer,
analogous to the C E_LAYOUT_ASSERT macros on the ABI struct — if the
lexer changes and these fail, you changed the language surface.

Codric Enterprise · Ricky (Dreid) · 2026
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '2-interpreter-python'))

from syntax import lex, T, Token

passed = failed = 0


def ok(name, cond):
    global passed, failed
    if cond:
        passed += 1; print(f"  \u2713 {name}")
    else:
        failed += 1; print(f"  \u2717 {name}")


def tokens(src):
    """Lex src and return (kind, text) pairs, excluding EOF."""
    toks, err = lex(src)
    if err:
        return None
    return [(t.kind, t.text) for t in toks if t.kind != T.EOF]


def kinds(src):
    """Lex src and return just the kinds, excluding EOF."""
    toks, err = lex(src)
    if err:
        return None
    return [t.kind for t in toks if t.kind != T.EOF]


def err_at(src):
    """Lex src and return the error particle, or None if clean."""
    _, err = lex(src)
    return err


def line_nums(src):
    """Lex src and return (kind, line) pairs, excluding EOF."""
    toks, err = lex(src)
    if err:
        return None
    return [(t.kind, t.line) for t in toks if t.kind != T.EOF]


print("\n=== Lexer unit tests ===\n")

# ── Token kind coverage ──────────────────────────────────────
print("Token kind coverage — every kind produced at least once")

ok("NUM integer",    tokens("42")     == [(T.NUM, "42")])
ok("NUM float",      tokens("3.14")   == [(T.NUM, "3.14")])
ok("NUM negative",   tokens("-42")    == [(T.OP, "-"), (T.NUM, "42")])
ok("STR double",     tokens('"hi"')   == [(T.STR, '"hi"')])
ok("STR single-quote is unknown", __import__('syntax').lex("'hi'")[1] is not None)  # grammar is double-quote only
ok("NAME plain",     tokens("x")      == [(T.NAME, "x")])
ok("NAME underscore",tokens("_x")     == [(T.NAME, "_x")])
ok("NAME alphanum",  tokens("x1")     == [(T.NAME, "x1")])
ok("LPAR",           tokens("(")      == [(T.LPAR, "(")])
ok("RPAR",           tokens(")")      == [(T.RPAR, ")")])
ok("COMMA",          tokens(",")      == [(T.COMMA, ",")])
ok("EQ",             tokens("=")      == [(T.EQ, "=")])
ok("OP plus",        tokens("+")      == [(T.OP, "+")])
ok("OP minus",       tokens("-")      == [(T.OP, "-")])
ok("OP star",        tokens("*")      == [(T.OP, "*")])
ok("OP slash",       tokens("/")      == [(T.OP, "/")])
ok("OP lt",          tokens("<")      == [(T.OP, "<")])
ok("OP gt",          tokens(">")      == [(T.OP, ">")])
ok("CMP lte",        tokens("<=")     == [(T.CMP, "<=")])
ok("CMP gte",        tokens(">=")     == [(T.CMP, ">=")])
ok("CMP eq",         tokens("==")     == [(T.CMP, "==")])
ok("CMP neq",        tokens("!=")     == [(T.CMP, "!=")])

# ── Keywords ─────────────────────────────────────────────────
print("\nAll keywords classified as KW, not NAME")
keywords = [
    "if", "then", "else", "def", "let", "true", "false",
    "anchor", "ever", "z", "show", "expect", "ascend",
    "assimilate", "learn", "equiv", "example", "to", "by",
]
for kw in keywords:
    ok(f"kw:{kw}", tokens(kw) == [(T.KW, kw)])

ok("true is KW not NAME",  tokens("true")  == [(T.KW, "true")])
ok("false is KW not NAME", tokens("false") == [(T.KW, "false")])
ok("trueish is NAME",      tokens("trueish") == [(T.NAME, "trueish")])
ok("defn is NAME",         tokens("defn")  == [(T.NAME, "defn")])

# ── Exact token stream (chord tests) ─────────────────────────
print("\nExact token streams — chord sequences")

ok("42 + 1", tokens("42 + 1") == [
    (T.NUM, "42"), (T.OP, "+"), (T.NUM, "1")])

ok("1 * 2 + 3", tokens("1 * 2 + 3") == [
    (T.NUM, "1"), (T.OP, "*"), (T.NUM, "2"), (T.OP, "+"), (T.NUM, "3")])

ok("n <= 1", tokens("n <= 1") == [
    (T.NAME, "n"), (T.CMP, "<="), (T.NUM, "1")])

ok("if n <= 1 then 1 else 0", tokens("if n <= 1 then 1 else 0") == [
    (T.KW, "if"), (T.NAME, "n"), (T.CMP, "<="), (T.NUM, "1"),
    (T.KW, "then"), (T.NUM, "1"), (T.KW, "else"), (T.NUM, "0")])

ok("def f(n) = n", tokens("def f(n) = n") == [
    (T.KW, "def"), (T.NAME, "f"), (T.LPAR, "("),
    (T.NAME, "n"), (T.RPAR, ")"), (T.EQ, "="), (T.NAME, "n")])

ok("def add(x, y) = x + y", tokens("def add(x, y) = x + y") == [
    (T.KW, "def"), (T.NAME, "add"), (T.LPAR, "("),
    (T.NAME, "x"), (T.COMMA, ","), (T.NAME, "y"),
    (T.RPAR, ")"), (T.EQ, "="),
    (T.NAME, "x"), (T.OP, "+"), (T.NAME, "y")])

ok("f(g(x))", tokens("f(g(x))") == [
    (T.NAME, "f"), (T.LPAR, "("),
    (T.NAME, "g"), (T.LPAR, "("), (T.NAME, "x"), (T.RPAR, ")"),
    (T.RPAR, ")")])

ok('"hello world"', tokens('"hello world"') == [(T.STR, '"hello world"')])

ok("3.14", tokens("3.14") == [(T.NUM, "3.14")])

ok("1 != 2", tokens("1 != 2") == [
    (T.NUM, "1"), (T.CMP, "!="), (T.NUM, "2")])

# ── <= vs < = distinction ─────────────────────────────────────
print("\nTwo-character operator precedence")
ok("<= is one CMP token",  tokens("<=") == [(T.CMP, "<=")])
ok(">= is one CMP token",  tokens(">=") == [(T.CMP, ">=")])
ok("== is one CMP token",  tokens("==") == [(T.CMP, "==")])
ok("!= is one CMP token",  tokens("!=") == [(T.CMP, "!=")])
ok("< then = are separate",tokens("< =") == [(T.OP, "<"), (T.EQ, "=")])

# ── Comments ─────────────────────────────────────────────────
print("\nComment stripping")
ok("comment dropped",      tokens("x # this is ignored") == [(T.NAME, "x")])
ok("comment only = empty", tokens("# nothing") == [])
ok("inline comment",       tokens("42 # the answer") == [(T.NUM, "42")])
ok("code after comment",   tokens("# line 1\nx") == [(T.NAME, "x")])

# ── Whitespace ────────────────────────────────────────────────
print("\nWhitespace handling")
ok("spaces ignored",  tokens("  x  ") == [(T.NAME, "x")])
ok("tabs ignored",    tokens("\tx\t") == [(T.NAME, "x")])
ok("newline ignored", tokens("x\ny") == [(T.NAME, "x"), (T.NAME, "y")])
ok("empty string",    tokens("") == [])
ok("only whitespace", tokens("   ") == [])

# ── Line number tracking ──────────────────────────────────────
print("\nLine number tracking")
ok("single line = 1",   line_nums("x + 1") == [(T.NAME, 1), (T.OP, 1), (T.NUM, 1)])
ok("newline increments",
   line_nums("x\ny") == [(T.NAME, 1), (T.NAME, 2)])
ok("comment line counted",
   line_nums("# skip\nx") == [(T.NAME, 2)])
ok("multi-line expr",
   [ln for _, ln in line_nums("x\n+\n1")] == [1, 2, 3])

# ── EOF token ────────────────────────────────────────────────
print("\nEOF token always present")
toks, _ = lex("42")
ok("EOF is the last token",  toks[-1].kind == T.EOF)
ok("EOF text is empty",      toks[-1].text == "")
toks2, _ = lex("")
ok("empty input has only EOF", len(toks2) == 1 and toks2[0].kind == T.EOF)

# ── Error cases ───────────────────────────────────────────────
print("\nError cases — unknown characters produce Z")
ok("dollar is unknown",    err_at("x $ y") is not None)
ok("error is a Z",         err_at("x $ y").is_z)
ok("error names position", "at" in err_at("x $ y").reason.lower() or
                            "character" in err_at("x $ y").reason.lower())
ok("at sign is unknown",   err_at("@x") is not None)
ok("hash is not unknown",  err_at("# comment") is None)  # hash = comment
ok("valid after error",    err_at("x + y") is None)

# ── String edge cases ─────────────────────────────────────────
print("\nString edge cases")
ok("empty string",         tokens('""') == [(T.STR, '""')])
ok("string with spaces",   tokens('"a b"') == [(T.STR, '"a b"')])
ok("string with digits",   tokens('"42"') == [(T.STR, '"42"')])
ok("unterminated string",  err_at('"oops') is not None)

# ── Number edge cases ─────────────────────────────────────────
print("\nNumber edge cases")
ok("zero",            tokens("0") == [(T.NUM, "0")])
ok("large int",       tokens("99999") == [(T.NUM, "99999")])
ok("zero point five", tokens("0.5") == [(T.NUM, "0.5")])
ok("no leading dot",  kinds(".5") != [T.NUM])   # not a valid number
ok("two numbers",     tokens("1 2") == [(T.NUM, "1"), (T.NUM, "2")])

print(f"\n=== Lexer: {passed} passed, {failed} failed ===\n")
raise SystemExit(0 if failed == 0 else 1)
