#!/usr/bin/env python3
"""
parsers.py — four independent parsers over the same token stream.

  P1 recdescent   a function per precedence level        (incumbent)
  P2 pratt        one loop, precedence from a bp table
  P3 shunting     explicit operator and operand stacks
  P4 earley       chart parser driven by a written grammar

The four differ in where precedence *lives*, which is the property
worth cross-checking. In P1 it is the call graph, in P2 a number, in P3
a stack discipline, in P4 the shape of the rules. Four encodings of one
claim: if they agree on every input, the claim is the language's and
not any one implementation's.

P1, P2 and P3 dispatch operators on token *text*. P4 dispatches on
token *kind*, because a written grammar must name terminal classes.
That difference is not incidental — it is how the forge finds out
whether the kinds were ever really specified.

Every parser returns contract.ParseOut. None raises past its own edge.

Codric Enterprise · Ricky (Dreid) · 2026
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

from contract import (Bin, Bool, Call, Def, Fail, If, Let, Lst, N, Num,
                      ParseOut, Prog, Str, Var)
from spec import SPEC

CMP_TEXT = {"<", ">", "<=", ">=", "==", "!="}
ADD_TEXT = {"+", "-"}
MUL_TEXT = {"*", "/"}


class _Refuse(Exception):
    """Internal. Carries the defect and place out to the edge, where it
    becomes a Fail. It never escapes this module."""

    def __init__(self, defect: str, pos: int, line: int):
        super().__init__(defect)
        self.defect, self.pos, self.line = defect, pos, line


def _num_node(text: str) -> Num:
    return Num(float(text))


def _refuse_at(tok) -> "_Refuse":
    return _Refuse("unbounded", tok.pos, tok.line)


# ═════════════════════════════════════════════
# Shared shell — the parts that are not about precedence
# ═════════════════════════════════════════════

class _Program:
    """Program shape, parameter lists and argument lists.

    These are shared because they are not where the four parsers
    differ. Duplicating them would manufacture agreement on the boring
    parts and dilute the disagreement on the interesting ones — the
    forge is only worth running if the witnesses differ where the
    question is.

    The three classes that mix this in supply peek/take/want/at_kind,
    a `fndef`, and a `top()` that parses one expression.
    """

    def program(self) -> Prog:
        multi = bool(SPEC.get("multi_definition", False))
        defs: List[Def] = []
        while self.at_kind("KW", "def"):
            defs.append(self.fndef())
            if not multi:
                break
        if defs:
            if self.at_kind("EOF"):
                return Prog(defs, None)
            if not multi or not bool(SPEC.get("trailing_expression", False)):
                raise _refuse_at(self.peek())
            tail = self.top()
            if not self.at_kind("EOF"):
                raise _refuse_at(self.peek())
            return Prog(defs, tail)
        e = self.top()
        if not self.at_kind("EOF"):
            raise _refuse_at(self.peek())
        return Prog([], e)

    def name_list(self) -> List[str]:
        trail = bool(SPEC.get("trailing_comma", False))
        names: List[str] = []
        if self.at_kind("RPAR"):
            return names
        names.append(self.want("NAME").text)
        while self.at_kind("COMMA"):
            self.take()
            if trail and self.at_kind("RPAR"):
                break
            names.append(self.want("NAME").text)
        return names

    def expr_list(self, closer: str = "RPAR") -> List[N]:
        trail = bool(SPEC.get("trailing_comma", False))
        args: List[N] = []
        if self.at_kind(closer):
            return args
        args.append(self.top())
        while self.at_kind("COMMA"):
            self.take()
            if trail and self.at_kind(closer):
                break
            args.append(self.top())
        return args

    def let_expr(self) -> N:
        """`let x = v in body`.

        At expression level, never at operand level -- the same
        placement the conditional has, and for the same reason: it is
        an alternative of expr in the published grammar, so it is never
        the left or right side of an infix operator.
        """
        self.want("KW", "let")
        name = self.want("NAME").text
        self.want("EQ")
        value = self.top()
        self.want("KW", "in")
        return Let(name, value, self.top())

    def list_literal(self) -> N:
        self.want("LBRACK")
        items = self.expr_list("RBRACK")
        self.want("RBRACK")
        return Lst(items)


# ═════════════════════════════════════════════
# P1 — recursive descent, one function per level
# ═════════════════════════════════════════════

class _RD(_Program):
    def __init__(self, toks):
        self.t, self.i = toks, 0

    def peek(self):
        return self.t[self.i]

    def at_kind(self, kind, text=None) -> bool:
        tk = self.peek()
        return tk.kind == kind and (text is None or tk.text == text)

    def at_text(self, texts) -> bool:
        tk = self.peek()
        return tk.kind != "EOF" and tk.text in texts

    def take(self):
        tk = self.t[self.i]
        if tk.kind != "EOF":
            self.i += 1
        return tk

    def want(self, kind, text=None):
        if not self.at_kind(kind, text):
            raise _refuse_at(self.peek())
        return self.take()

    def top(self) -> N:
        return self.expr()


    def fndef(self) -> Def:
        self.want("KW", "def")
        name = self.want("NAME").text
        self.want("LPAR")
        params = self.name_list()
        self.want("RPAR")
        self.want("EQ")
        return Def(name, params, self.expr())

    def expr(self) -> N:
        if self.at_kind("KW", "if"):
            self.take()
            c = self.expr()
            self.want("KW", "then")
            t = self.expr()
            self.want("KW", "else")
            return If(c, t, self.expr())
        if self.at_kind("KW", "let"):
            return self.let_expr()
        return self.compare()

    def compare(self) -> N:
        left = self.additive()
        if self.at_text(CMP_TEXT):
            op = self.take().text
            return Bin(op, left, self.additive())
        return left

    def additive(self) -> N:
        node = self.multiply()
        while self.at_text(ADD_TEXT):
            op = self.take().text
            node = Bin(op, node, self.multiply())
        return node

    def multiply(self) -> N:
        node = self.atom()
        while self.at_text(MUL_TEXT):
            op = self.take().text
            node = Bin(op, node, self.atom())
        return node

    def atom(self) -> N:
        tk = self.peek()
        if tk.kind == "NUM":
            self.take(); return _num_node(tk.text)
        if tk.kind == "STR":
            self.take(); return Str(tk.text[1:-1])
        if tk.kind == "KW" and tk.text in ("true", "false"):
            self.take(); return Bool(tk.text == "true")
        if tk.kind == "LBRACK":
            return self.list_literal()
        if tk.kind == "LPAR":
            self.take()
            node = self.expr()
            self.want("RPAR")
            return node
        if tk.text == "-" and tk.kind != "EOF":
            self.take()
            return Bin("-", Num(0), self.atom())
        if tk.kind == "NAME":
            self.take()
            if self.at_kind("LPAR"):
                self.take()
                args = self.expr_list()
                self.want("RPAR")
                return Call(tk.text, args)
            return Var(tk.text)
        raise _refuse_at(tk)


def parse_recdescent(toks) -> ParseOut:
    try:
        return ParseOut(ast=_RD(list(toks)).program())
    except _Refuse as r:
        return ParseOut(fail=Fail("parse", r.defect, r.pos, r.line))


# ═════════════════════════════════════════════
# P2 — Pratt, precedence as a number
# ═════════════════════════════════════════════

#: (left bp, right bp). Left-associative when right = left + 1.
_BP: Dict[str, Tuple[int, int]] = {
    "<": (1, 2), ">": (1, 2), "<=": (1, 2),
    ">=": (1, 2), "==": (1, 2), "!=": (1, 2),
    "+": (3, 4), "-": (3, 4),
    "*": (5, 6), "/": (5, 6),
}
#: Prefix minus binds tighter than any infix operator.
_PREFIX_BP = 7


class _Pratt(_Program):
    def __init__(self, toks):
        self.t, self.i = toks, 0

    def peek(self):
        return self.t[self.i]

    def at_kind(self, kind, text=None) -> bool:
        tk = self.peek()
        return tk.kind == kind and (text is None or tk.text == text)

    def top(self) -> N:
        return self.expr(0)

    def take(self):
        tk = self.t[self.i]
        if tk.kind != "EOF":
            self.i += 1
        return tk

    def want(self, kind, text=None):
        tk = self.peek()
        if tk.kind != kind or (text is not None and tk.text != text):
            raise _refuse_at(tk)
        return self.take()


    def fndef(self) -> Def:
        self.want("KW", "def")
        name = self.want("NAME").text
        self.want("LPAR")
        params = self.name_list()
        self.want("RPAR")
        self.want("EQ")
        return Def(name, params, self.expr(0))

    def expr(self, min_bp: int) -> N:
        # PIPELINE.md: expr := ifexpr | compare. An if is an
        # alternative of *expr*, not of atom, so it cannot become the
        # left operand of an infix operator. Parsing it in nud() made
        # it one, and 'if a then 1 else 2 != 3' then parsed as a
        # comparison whose left side was the conditional. The forge
        # found it; the published grammar settles it.
        if self.at_kind("KW", "if"):
            self.take()
            c = self.expr(0)
            self.want("KW", "then")
            t = self.expr(0)
            self.want("KW", "else")
            return If(c, t, self.expr(0))
        if self.at_kind("KW", "let"):
            return self.let_expr()
        return self.operand_expr(min_bp)

    def operand_expr(self, min_bp: int) -> N:
        """The comparison/arithmetic levels only.

        Kept separate from expr() because the operands of an infix
        operator are `multiply`s, not `expr`s: `1 + if a then 2 else 3`
        is outside the published grammar on the right of the plus for
        exactly the reason it is outside on the left. One entry point
        for both let a conditional in as a right operand while it was
        correctly refused as a left one, which is the kind of asymmetry
        a binding-power table makes easy to miss.
        """
        left = self.nud()
        while True:
            tk = self.peek()
            if tk.kind == "EOF":
                break
            bp = _BP.get(tk.text)
            if bp is None or bp[0] < min_bp:
                break
            # comparison is non-associative: one only, then stop
            self.take()
            right = self.operand_expr(bp[1])
            left = Bin(tk.text, left, right)
            if tk.text in CMP_TEXT:
                break
        return left

    def nud(self) -> N:
        tk = self.take()
        if tk.kind == "NUM":
            return _num_node(tk.text)
        if tk.kind == "STR":
            return Str(tk.text[1:-1])
        if tk.kind == "KW" and tk.text in ("true", "false"):
            return Bool(tk.text == "true")
        if tk.kind == "LBRACK":
            items = self.expr_list("RBRACK")
            self.want("RBRACK")
            return Lst(items)
        if tk.kind == "LPAR":
            node = self.expr(0)
            self.want("RPAR")
            return node
        if tk.text == "-" and tk.kind != "EOF":
            return Bin("-", Num(0), self.operand_expr(_PREFIX_BP))
        if tk.kind == "NAME":
            if self.peek().kind == "LPAR":
                self.take()
                args = self.expr_list()
                self.want("RPAR")
                return Call(tk.text, args)
            return Var(tk.text)
        raise _refuse_at(tk)


def parse_pratt(toks) -> ParseOut:
    try:
        return ParseOut(ast=_Pratt(list(toks)).program())
    except _Refuse as r:
        return ParseOut(fail=Fail("parse", r.defect, r.pos, r.line))


# ═════════════════════════════════════════════
# P3 — shunting-yard, precedence as stack discipline
# ═════════════════════════════════════════════

_PREC: Dict[str, int] = {
    "<": 1, ">": 1, "<=": 1, ">=": 1, "==": 1, "!=": 1,
    "+": 2, "-": 2, "*": 3, "/": 3,
}
_UNARY = "u-"
_PREC_UNARY = 4


class _Yard(_Program):
    """Dijkstra's algorithm, with the recursive shell that `if` and
    `def` need. The operator stack decides precedence; nothing in the
    call graph does."""

    def __init__(self, toks):
        self.t, self.i = toks, 0

    def peek(self):
        return self.t[self.i]

    def at_kind(self, kind, text=None) -> bool:
        tk = self.peek()
        return tk.kind == kind and (text is None or tk.text == text)

    def top(self) -> N:
        return self.expr()

    def take(self):
        tk = self.t[self.i]
        if tk.kind != "EOF":
            self.i += 1
        return tk

    def want(self, kind, text=None):
        tk = self.peek()
        if tk.kind != kind or (text is not None and tk.text != text):
            raise _refuse_at(tk)
        return self.take()


    def fndef(self) -> Def:
        self.want("KW", "def")
        name = self.want("NAME").text
        self.want("LPAR")
        params = self.name_list()
        self.want("RPAR")
        self.want("EQ")
        return Def(name, params, self.expr())

    @staticmethod
    def _reduce(vals: List[N], ops: List[str]) -> None:
        op = ops.pop()
        if op == _UNARY:
            if not vals:
                raise _Refuse("unbounded", 0, 1)
            vals.append(Bin("-", Num(0), vals.pop()))
            return
        if len(vals) < 2:
            raise _Refuse("unbounded", 0, 1)
        r = vals.pop()
        l = vals.pop()
        vals.append(Bin(op, l, r))

    def expr(self) -> N:
        # Same correction as P2, for the same reason: an if is a whole
        # expression, so it never enters the operand stack.
        if self.at_kind("KW", "if"):
            self.take()
            c = self.expr()
            self.want("KW", "then")
            t = self.expr()
            self.want("KW", "else")
            return If(c, t, self.expr())
        if self.at_kind("KW", "let"):
            return self.let_expr()
        vals: List[N] = []
        ops: List[str] = []
        want_operand = True
        cmp_seen = False

        while True:
            tk = self.peek()

            if want_operand:
                if tk.text == "-" and tk.kind != "EOF":
                    self.take()
                    ops.append(_UNARY)
                    continue
                vals.append(self.operand())
                want_operand = False
                continue

            if tk.kind == "EOF" or tk.text not in _PREC:
                break
            if tk.text in CMP_TEXT:
                if cmp_seen:
                    break          # non-associative: refuse the second
                cmp_seen = True

            self.take()
            prec = _PREC[tk.text]
            while ops:
                top = ops[-1]
                tp = _PREC_UNARY if top == _UNARY else _PREC[top]
                if tp >= prec:
                    self._reduce(vals, ops)
                else:
                    break
            ops.append(tk.text)
            want_operand = True

        if want_operand:
            raise _refuse_at(self.peek())
        while ops:
            self._reduce(vals, ops)
        if len(vals) != 1:
            raise _refuse_at(self.peek())
        return vals[0]

    def operand(self) -> N:
        tk = self.take()
        if tk.kind == "NUM":
            return _num_node(tk.text)
        if tk.kind == "STR":
            return Str(tk.text[1:-1])
        if tk.kind == "KW" and tk.text in ("true", "false"):
            return Bool(tk.text == "true")
        if tk.kind == "LBRACK":
            items = self.expr_list("RBRACK")
            self.want("RBRACK")
            return Lst(items)
        if tk.kind == "LPAR":
            node = self.expr()
            self.want("RPAR")
            return node
        if tk.kind == "NAME":
            if self.peek().kind == "LPAR":
                self.take()
                args = self.expr_list()
                self.want("RPAR")
                return Call(tk.text, args)
            return Var(tk.text)
        raise _refuse_at(tk)


def parse_shunting(toks) -> ParseOut:
    try:
        return ParseOut(ast=_Yard(list(toks)).program())
    except _Refuse as r:
        return ParseOut(fail=Fail("parse", r.defect, r.pos, r.line))


# ═════════════════════════════════════════════
# P4 — Earley, precedence as the shape of the rules
# ═════════════════════════════════════════════
#
# Terminals:  %KIND matches a token kind, 'text' matches token text.
# Left recursion encodes left associativity directly, which is the one
# place associativity is *stated* rather than implied by control flow.

_CORE_RULES: List[Tuple[str, Tuple[str, ...], Callable]] = [
    ("S",        ("program",),                       lambda c: c[0]),

    ("fndef",    ("'def'", "%NAME", "%LPAR", "%RPAR", "%EQ", "expr"),
     lambda c: Def(c[1].text, [], c[5])),
    ("fndef",    ("'def'", "%NAME", "%LPAR", "params", "%RPAR", "%EQ", "expr"),
     lambda c: Def(c[1].text, c[3], c[6])),

    ("params",   ("%NAME",),                         lambda c: [c[0].text]),
    ("params",   ("params", "%COMMA", "%NAME"),      lambda c: c[0] + [c[2].text]),

    ("expr",     ("ifexpr",),                        lambda c: c[0]),
    ("expr",     ("letexpr",),                       lambda c: c[0]),
    ("expr",     ("compare",),                       lambda c: c[0]),

    ("letexpr",  ("'let'", "%NAME", "%EQ", "expr", "'in'", "expr"),
     lambda c: Let(c[1].text, c[3], c[5])),

    ("ifexpr",   ("'if'", "expr", "'then'", "expr", "'else'", "expr"),
     lambda c: If(c[1], c[3], c[5])),

    ("compare",  ("additive", "%CMP", "additive"),
     lambda c: Bin(c[1].text, c[0], c[2])),
    ("compare",  ("additive",),                      lambda c: c[0]),

    ("additive", ("additive", "'+'", "multiply"),    lambda c: Bin("+", c[0], c[2])),
    ("additive", ("additive", "'-'", "multiply"),    lambda c: Bin("-", c[0], c[2])),
    ("additive", ("multiply",),                      lambda c: c[0]),

    ("multiply", ("multiply", "'*'", "unary"),       lambda c: Bin("*", c[0], c[2])),
    ("multiply", ("multiply", "'/'", "unary"),       lambda c: Bin("/", c[0], c[2])),
    ("multiply", ("unary",),                         lambda c: c[0]),

    ("unary",    ("'-'", "unary"),                   lambda c: Bin("-", Num(0), c[1])),
    ("unary",    ("atom",),                          lambda c: c[0]),

    ("atom",     ("%NUM",),                          lambda c: _num_node(c[0].text)),
    ("atom",     ("%STR",),                          lambda c: Str(c[0].text[1:-1])),
    ("atom",     ("'true'",),                        lambda c: Bool(True)),
    ("atom",     ("'false'",),                       lambda c: Bool(False)),
    ("atom",     ("%LPAR", "expr", "%RPAR"),         lambda c: c[1]),
    ("atom",     ("%NAME", "%LPAR", "%RPAR"),        lambda c: Call(c[0].text, [])),
    ("atom",     ("%NAME", "%LPAR", "arglist", "%RPAR"),
     lambda c: Call(c[0].text, c[2])),
    ("atom",     ("%LBRACK", "%RBRACK"),              lambda c: Lst([])),
    ("atom",     ("%LBRACK", "arglist", "%RBRACK"),   lambda c: Lst(c[1])),
    ("atom",     ("%NAME",),                         lambda c: Var(c[0].text)),

    ("arglist",  ("expr",),                          lambda c: [c[0]]),
    ("arglist",  ("arglist", "%COMMA", "expr"),      lambda c: c[0] + [c[2]]),
]

def _program_rules(multi: bool):
    """One definition per text, or a run of them.

    Left recursion on `deflist` again: the order definitions were
    written in is part of the program, and a right-recursive rule would
    build the list backwards.
    """
    if not multi:
        return [
            ("program", ("fndef",), lambda c: Prog([c[0]], None)),
            ("program", ("expr",),  lambda c: Prog([], c[0])),
        ]
    rules = [
        ("program", ("deflist",),         lambda c: Prog(c[0], None)),
        ("program", ("expr",),            lambda c: Prog([], c[0])),
        ("deflist", ("fndef",),           lambda c: [c[0]]),
        ("deflist", ("deflist", "fndef"), lambda c: c[0] + [c[1]]),
    ]
    if bool(SPEC.get("trailing_expression", False)):
        # Ambiguous, and known to be: see FINDINGS['trailing_expression']
        # in forge.py. Kept expressible so the ruling stays a ruling
        # rather than a fact of the code.
        rules.insert(1, ("program", ("deflist", "expr"),
                         lambda c: Prog(c[0], c[1])))
    return rules


def _trailing_rules(allowed: bool):
    if not allowed:
        return []
    return [
        ("params",  ("params", "%COMMA"),  lambda c: c[0]),
        ("arglist", ("arglist", "%COMMA"), lambda c: c[0]),
    ]


GRAMMAR: List[Tuple[str, Tuple[str, ...], Callable]] = []
_NONTERMS: Set[str] = set()
_BY_LHS: Dict[str, List[int]] = {}
_FINGERPRINT: Optional[tuple] = None


def _sync_grammar() -> None:
    """Rebuild the rules when a ruling has moved since last time.

    The grammar is the one parser where a ruling is a change of
    *specification* rather than of code, which is the clearest
    statement of what ratification actually does."""
    global GRAMMAR, _NONTERMS, _BY_LHS, _FINGERPRINT
    multi = bool(SPEC.get("multi_definition", False))
    trail = bool(SPEC.get("trailing_comma", False))
    fp = (multi, trail, bool(SPEC.get("trailing_expression", False)))
    if fp == _FINGERPRINT:
        return
    GRAMMAR = _program_rules(multi) + _CORE_RULES + _trailing_rules(trail)
    _NONTERMS = {lhs for lhs, _, _ in GRAMMAR}
    _BY_LHS = {}
    for idx, (lhs, _rhs, _act) in enumerate(GRAMMAR):
        _BY_LHS.setdefault(lhs, []).append(idx)
    _FINGERPRINT = fp


_sync_grammar()


def _matches(sym: str, tok) -> bool:
    if sym == "%CMP":
        # The grammar names a terminal class. Which kind the scanner
        # files a bare '<' under is question one; until it is settled
        # this rule means literally CMP, and the pairs whose scanner
        # says OP will not parse. That failure is the finding.
        ruled = SPEC.get("cmp_kind", None)
        if ruled is None:
            return tok.kind == "CMP"
        return tok.text in CMP_TEXT and tok.kind in ("CMP", ruled)
    if sym.startswith("%"):
        return tok.kind == sym[1:]
    if sym.startswith("'"):
        return tok.text == sym[1:-1] and tok.kind != "EOF"
    return False


class _Item:
    """A dotted rule. `derivs` holds the distinct child-tuples that
    reached it — more than one is the signature of ambiguity, and the
    forge would rather report that than pick a winner quietly."""

    __slots__ = ("rule", "dot", "start", "derivs")

    #: Two distinct derivations already prove ambiguity; keeping more
    #: only risks an exponential chart for no extra information.
    CAP = 2

    def __init__(self, rule: int, dot: int, start: int, kids: tuple):
        self.rule, self.dot, self.start = rule, dot, start
        self.derivs: List[tuple] = [kids]

    def key(self):
        return (self.rule, self.dot, self.start)

    def next_sym(self) -> Optional[str]:
        rhs = GRAMMAR[self.rule][1]
        return rhs[self.dot] if self.dot < len(rhs) else None

    def offer(self, kids: tuple) -> None:
        if len(self.derivs) < self.CAP and kids not in self.derivs:
            self.derivs.append(kids)


AMBIGUOUS = object()


def _value(item: "_Item", memo: dict):
    """Bottom-up evaluation, memoised on item identity.

    Returns AMBIGUOUS when this subtree has two derivations that do not
    agree. Two derivations reaching the same tree is not ambiguity —
    that is just the chart arriving twice — so the comparison is on the
    built value, never on the derivation.
    """
    hit = memo.get(id(item), _MISSING)
    if hit is not _MISSING:
        return hit

    memo[id(item)] = AMBIGUOUS      # guards a cyclic chart
    built = []
    for kids in item.derivs:
        vals = []
        bad = False
        for k in kids:
            if isinstance(k, _Item):
                v = _value(k, memo)
                if v is AMBIGUOUS:
                    bad = True
                    break
                vals.append(v)
            else:
                vals.append(k)
        if bad:
            continue
        try:
            built.append(GRAMMAR[item.rule][2](vals))
        except (IndexError, TypeError, AttributeError):
            continue

    if not built:
        result = AMBIGUOUS
    elif len(built) == 1:
        result = built[0]
    else:
        sexps = {b.sexp() if hasattr(b, "sexp") else repr(b) for b in built}
        result = built[0] if len(sexps) == 1 else AMBIGUOUS

    memo[id(item)] = result
    return result


_MISSING = object()


def parse_earley(toks) -> ParseOut:
    """Chart parse over the written grammar.

    Ambiguity is reported rather than silently resolved: a core
    language whose grammar admits two trees for one program is not a
    core language yet. The other three parsers cannot report this at
    all — they resolve by construction — which is the reason a
    grammar-driven witness is worth carrying.
    """
    _sync_grammar()
    t = [tk for tk in toks if tk.kind != "EOF"]
    n = len(t)

    chart: List[List[_Item]] = [[] for _ in range(n + 1)]
    index: List[Dict[tuple, _Item]] = [{} for _ in range(n + 1)]

    def add(col: int, rule: int, dot: int, start: int, kids: tuple) -> None:
        k = (rule, dot, start)
        have = index[col].get(k)
        if have is not None:
            have.offer(kids)
            return
        item = _Item(rule, dot, start, kids)
        index[col][k] = item
        chart[col].append(item)

    for r in _BY_LHS.get("S", []):
        add(0, r, 0, 0, ())

    for col in range(n + 1):
        j = 0
        while j < len(chart[col]):
            item = chart[col][j]
            j += 1
            sym = item.next_sym()

            if sym is None:                                    # complete
                lhs = GRAMMAR[item.rule][0]
                for parent in list(chart[item.start]):
                    if parent.next_sym() == lhs:
                        for pk in list(parent.derivs):
                            add(col, parent.rule, parent.dot + 1,
                                parent.start, pk + (item,))
                continue

            if sym in _NONTERMS:                               # predict
                for r in _BY_LHS[sym]:
                    add(col, r, 0, col, ())
                continue

            if col < n and _matches(sym, t[col]):              # scan
                for pk in list(item.derivs):
                    add(col + 1, item.rule, item.dot + 1,
                        item.start, pk + (t[col],))

    memo: dict = {}
    for item in chart[n]:
        if item.next_sym() is None and item.start == 0 \
                and GRAMMAR[item.rule][0] == "S":
            val = _value(item, memo)
            if val is AMBIGUOUS:
                return ParseOut(fail=Fail("parse", "overbound", 0,
                                          t[0].line if t else 1))
            return ParseOut(ast=val)

    # Nothing derived S over the whole input. Report the furthest column
    # the chart reached: that is where the grammar ran out, and it is
    # more useful than always blaming the last token.
    reach = max((c for c in range(n + 1) if chart[c]), default=0)
    bad = t[reach] if reach < n else (t[-1] if t else None)
    return ParseOut(fail=Fail("parse", "unbounded",
                              bad.pos if bad else 0,
                              bad.line if bad else 1))


# ═════════════════════════════════════════════
# Registry
# ═════════════════════════════════════════════

PARSERS = {
    "P1-recdescent": parse_recdescent,
    "P2-pratt":      parse_pratt,
    "P3-shunting":   parse_shunting,
    "P4-earley":     parse_earley,
}

__all__ = ["PARSERS", "GRAMMAR", "parse_recdescent", "parse_pratt",
           "parse_shunting", "parse_earley"]
