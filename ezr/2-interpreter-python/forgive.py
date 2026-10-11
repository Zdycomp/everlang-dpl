#!/usr/bin/env python3
"""
forgive.py — Ever ("E"), the forgiving front door.

E does not refuse a program over a misplaced comma. It heals what it
can, says exactly what it healed and why, and only refuses when the
intent is genuinely ambiguous — never by guessing structure that
wasn't there.

DESIGN

This is a layer, not a rewrite of the parser. `parse()` in syntax.py
is untouched and still strict — every existing test that depends on
exact error behavior keeps working exactly as before. `parse_forgiving`
sits in front of it: heal the token stream, then hand the result to
the same, unmodified parser. If healing didn't apply, the tokens are
identical and behavior is identical to calling parse() directly.

What gets healed, and why each one is safe:

  trailing comma        [1, 2, 3,]         unambiguous — drop it
  missing comma         [1 2 3]            only inside [ ], { }, or
                                            f(...) — never in bare
                                            grouping parens, where
                                            adjacency is genuinely
                                            unclear
  stray semicolon       let x = 1;         every language E's authors
                                            come from uses one; treat
                                            it as a statement border
  colon for equals       let x: 5          only in let/ever, the one
                                            place = is required
  equals for colon       {a = 1}           only inside { }, the one
                                            place : is required
  stray = for ==         if x = 5          = is ONLY legal once, right
                                            after let/ever's NAME;
                                            anywhere else it can only
                                            have meant ==
  keyword case           Let x = 1         a bare NAME spelled exactly
                                            like a keyword is not a
                                            plausible variable name

What does NOT get healed, on purpose:
  missing closing bracket, unterminated string, wrong bracket KIND
  closing the wrong opener, missing def body. Guessing where these end
  is guessing structure, not fixing a slip. E explains these clearly
  instead — teaching still happens, just without inventing code.

Codric Enterprise · Ricky (Dreid) · 2026
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from syntax import (T, Token, lex, KEYWORDS, Node, E as ParseErr,
                    e_z, Defect)


@dataclass
class Correction:
    line:    int
    what:    str      # what E saw
    became:  str      # what E assumed instead
    reason:  str      # why that assumption is safe
    form:    str = "" # SEMANTICS.md §9.5. structured token edit, replayable.
    kind:    int = 1  # 0 plain, 1 inferred. SEMANTICS.md §9.2.
    name:    str = "" # canonical name from ever_repair.

    def line1(self) -> str:
        return f"line {self.line}: {self.what} → {self.became}"

    def full(self) -> str:
        return f"line {self.line}: {self.what} → {self.became}\n    {self.reason}"


_OPENERS = {T.LBRACK: T.RBRACK, T.LBRACE: T.RBRACE, T.LPAR: T.RPAR}
_VALUE_START = {T.NUM, T.STR, T.NAME, T.LPAR, T.LBRACK, T.LBRACE}
_VALUE_KW = {"true", "false", "z"}


def _is_value_start(tok: Token) -> bool:
    if tok.kind in _VALUE_START:
        return True
    return tok.kind is T.KW and tok.text in _VALUE_KW


def _strip_semicolons(src: str) -> Tuple[str, List[Correction]]:
    """Drop stray `;` from raw source before lexing — the lexer has no
    token for it at all, so it must be handled before lex() runs.
    Respects strings and comments: a semicolon inside "..." or after
    # is data, not a mistake."""
    out = []
    corrections: List[Correction] = []
    line = 1
    in_str = False
    i, n = 0, len(src)
    while i < n:
        ch = src[i]
        if ch == "\n":
            line += 1
            out.append(ch); i += 1; continue
        if ch == "#" and not in_str:
            while i < n and src[i] != "\n":
                out.append(src[i]); i += 1
            continue
        if ch == '"':
            in_str = not in_str
            out.append(ch); i += 1; continue
        if ch == ";" and not in_str:
            corrections.append(Correction(
                line, "';'", "(removed)",
                "E does not need statement terminators; the "
                "semicolon is simply dropped",
                form="SEMI_DROP", kind=0, name="stray_semicolon"))
            i += 1
            continue
        out.append(ch); i += 1
    return "".join(out), corrections


def _protected_eq_positions(tokens: List[Token]) -> set:
    """Every token index where a bare '=' is legitimate, not a slip.

    Three shapes, all structural rather than purely local, so this is
    a small pre-pass rather than a peek at one or two prior tokens:
      let NAME =        /  ever NAME =        — binding
      def NAME ( ... ) =                       — function definition,
                                                  the = after the
                                                  closing paren of the
                                                  parameter list
      for NAME =                               — range-loop header,
                                                  the = after the loop
                                                  variable
    """
    protected = set()
    n = len(tokens)
    for i, tok in enumerate(tokens):
        if tok.kind is not T.EQ:
            continue
        if i >= 2 and tokens[i - 1].kind is T.NAME \
                and tokens[i - 2].kind is T.KW \
                and tokens[i - 2].text in ("let", "ever", "for"):
            protected.add(i)
            continue
        if i >= 1 and tokens[i - 1].kind is T.RPAR:
            # walk back to find the matching '(' and check what's
            # immediately before IT
            depth = 1
            j = i - 2
            while j >= 0 and depth > 0:
                if tokens[j].kind is T.RPAR: depth += 1
                elif tokens[j].kind is T.LPAR: depth -= 1
                j -= 1
            # j now sits one before the matching '('
            if j >= 1 and tokens[j].kind is T.NAME \
                    and tokens[j - 1].kind is T.KW \
                    and tokens[j - 1].text == "def":
                protected.add(i)
    return protected


def _completes_value(tok: Token, next_tok: Optional[Token]) -> bool:
    """Does `tok` end a complete value, such that a value-start right
    after it (with no comma) is a missing-comma slip rather than one
    value continuing into the next token?

    Ever's postfix() rule chains '(' (call), '[' (index), and '.'
    (field) onto ANY atom, so this check is general rather than
    NAME-specific: whatever `tok` is, if the next token opens one of
    those three continuations, `tok` is the HEAD of a longer
    expression, not a finished value on its own. Missing this the
    first time indexing shipped turned `xs[i]` into `xs, [i]` inside
    a call's arguments; a chained `xs[0][1]` or `r.a.b` would hit the
    identical bug at the second link in the chain.
    """
    if next_tok and next_tok.kind is T.LBRACK:
        return False   # tok[...] — an index continuing this value
    if next_tok and next_tok.kind is T.OP and next_tok.text == ".":
        return False   # tok.field — a field access continuing this value
    if tok.kind in (T.NUM, T.STR, T.RPAR, T.RBRACK, T.RBRACE):
        return True
    if tok.kind is T.NAME:
        return not (next_tok and next_tok.kind is T.LPAR)
    if tok.kind is T.KW and tok.text in _VALUE_KW:
        return True
    return False


def _heal_keyword_case(tokens: List[Token]) -> Tuple[List[Token], List[Correction]]:
    """First stage: normalise keyword-spelled NAMEs to real keywords.
    Runs before everything else, because later stages (protecting a
    legitimate = after let/ever/def) need to see 'Let' as KW, not as
    a NAME that happens to spell it."""
    out: List[Token] = []
    corrections: List[Correction] = []
    for tok in tokens:
        if tok.kind is T.NAME and tok.text.lower() in KEYWORDS \
                and tok.text != tok.text.lower():
            corrections.append(Correction(
                tok.line, f"'{tok.text}'", f"'{tok.text.lower()}'",
                "keywords in E are lowercase; a name spelled exactly "
                "like one is almost certainly meant as one",
                form=f"KW_LOWER:{tok.text.lower()}",
                kind=0, name="keyword_case"))
            out.append(Token(T.KW, tok.text.lower(), tok.pos, tok.line))
        else:
            out.append(tok)
    return out, corrections


def heal(tokens: List[Token]) -> Tuple[List[Token], List[Correction]]:
    """Repair a well-defined set of common slips in a token stream.
    Returns the healed stream and a record of every change made —
    never a silent fix, since a fix nobody is told about teaches
    nothing.

    Runs in two stages: keyword-case first (so every later stage sees
    real KW tokens, not NAMEs that merely spell one), then a single
    pass handling commas, colons, and stray '='/'=='.
    """
    tokens, corrections = _heal_keyword_case(tokens)
    out: List[Token] = []
    protected_eq = _protected_eq_positions(tokens)

    # bracket-kind stack, so "missing comma" only fires inside [ ], { }
    # or a call's ( ), never a bare grouping paren
    stack: List[Tuple[T, bool]] = []   # (opener kind, is_call_paren)

    i = 0
    n = len(tokens)
    while i < n:
        tok = tokens[i]

        # ── trailing comma before a closer ──
        if tok.kind is T.COMMA:
            nxt = tokens[i + 1] if i + 1 < n else None
            if nxt and nxt.kind in (T.RBRACK, T.RBRACE, T.RPAR):
                corrections.append(Correction(
                    tok.line, "trailing ','", "(removed)",
                    "a comma right before a closing bracket has "
                    "nothing after it to separate",
                    form="COMMA_TRAIL_DROP", kind=0, name="trailing_comma"))
                i += 1
                continue

        # ── track bracket context (before rewriting EQ/COLON, so the
        #    stack reflects where we structurally are) ──
        if tok.kind in _OPENERS:
            is_call = tok.kind is T.LPAR and out and out[-1].kind is T.NAME
            stack.append((tok.kind, is_call))
        elif tok.kind in (T.RBRACK, T.RBRACE, T.RPAR):
            if stack:
                stack.pop()

        # ── colon where = was required (let/ever binding) ──
        if tok.kind is T.COLON and len(out) >= 2 \
                and out[-1].kind is T.NAME \
                and out[-2].kind is T.KW and out[-2].text in ("let", "ever"):
            corrections.append(Correction(
                tok.line, "':'", "'='",
                "let/ever always bind with =; only { } fields use :",
                form="COLON_TO_EQ", kind=1, name="colon_for_equals"))
            tok = Token(T.EQ, "=", tok.pos, tok.line)

        # ── = where : was required (record field) ──
        elif tok.kind is T.EQ and stack and stack[-1][0] is T.LBRACE:
            corrections.append(Correction(
                tok.line, "'='", "':'",
                "fields inside { } are written name: value",
                form="EQ_TO_COLON", kind=1, name="equals_for_colon"))
            tok = Token(T.COLON, ":", tok.pos, tok.line)

        # ── stray = where == was meant ──
        # = is legitimate in exactly two shapes (see
        # _protected_eq_positions); anywhere else it can only mean ==.
        elif tok.kind is T.EQ and i not in protected_eq:
            corrections.append(Correction(
                tok.line, "'='", "'=='",
                "= only appears after let/ever NAME or a def's "
                "parameter list; anywhere else a single = can only "
                "have meant the comparison ==",
                form="EQ_TO_CMP", kind=1, name="equals_for_compare"))
            tok = Token(T.CMP, "==", tok.pos, tok.line)

        out.append(tok)

        # ── missing comma between two adjacent values ──
        # only inside [ ], { }, or a call's ( ) — never a bare
        # grouping paren, where "1 2" has no safe interpretation
        in_collection = bool(stack) and (
            stack[-1][0] in (T.LBRACK, T.LBRACE) or
            (stack[-1][0] is T.LPAR and stack[-1][1]))
        if in_collection:
            nxt = tokens[i + 1] if i + 1 < n else None
            if nxt and _is_value_start(nxt) and _completes_value(tok, nxt):
                corrections.append(Correction(
                    nxt.line, "missing ','", "',' inserted",
                    "two values back to back inside a collection "
                    "almost always means a comma was dropped",
                    form=f"COMMA_INSERT:{tok.kind.name}|{nxt.kind.name}",
                    kind=1, name="missing_comma"))
                out.append(Token(T.COMMA, ",", nxt.pos, nxt.line))

        i += 1

    return out, corrections


def parse_forgiving(src: str) -> Tuple[Optional[Node], Optional[ParseErr],
                                       List[Correction]]:
    """The forgiving front door. Heals what it safely can, then hands
    the result to the same strict parser everything else uses. If the
    program is still malformed after healing, the error is genuine —
    reported plainly, nothing invented to make it go away."""
    from syntax import Parser, ParseError

    clean_src, semi_corr = _strip_semicolons(src)
    toks, lerr = lex(clean_src)
    if lerr is not None:
        return None, lerr, semi_corr

    healed, corrections = heal(toks)
    corrections = semi_corr + corrections

    try:
        node = Parser(healed).program()
        return node, None, corrections
    except ParseError as exc:
        return None, e_z("parse", str(exc), Defect.UNBOUNDED), corrections
