#!/usr/bin/env python3
"""
syntax.py — Ever / Tapestry, stages 1 through 3

    1. Lexer      source  -> [Token]
    2. Parser     [Token] -> AST
    3. Semantic   AST     -> AST, resolved and typed
    4. Execution  handled by eval_ast below and by abstract.py

Ever previously jumped straight to stage 4 and walked strings. That
worked, and it cost three things that only an AST can give back:

  - ultracode measured characters instead of structure, so `n*1` and
    `n` looked like different amounts of program
  - transpilation was impossible; you cannot emit Rust from a regex
  - nothing could answer "is this spec even expressible in my grammar",
    which is the exact gap the notebook batch exposed at cell 7

EVERY STAGE RETURNS E<T>. A lexing error is not an exception, it is a Z
carrying a defect class and a source position. Evaluation being total is
a property of the whole pipeline or it is not a property at all.

Codric Enterprise · Ricky (Dreid) · 2026
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Set, Tuple

from ever import (
    E, State, Defect, e_z, e_val,
    E_CERTAIN, E_ZERO, E_INTAKE, E_EXECUTE_FLOOR,
)


# ═════════════════════════════════════════════
# 1. LEXER
# ═════════════════════════════════════════════

class T(Enum):
    NUM = auto(); STR = auto(); NAME = auto(); KW = auto()
    OP = auto(); CMP = auto(); LPAR = auto(); RPAR = auto()
    COMMA = auto(); EQ = auto(); EOF = auto()
    LBRACK = auto(); RBRACK = auto()
    LBRACE = auto(); RBRACE = auto(); COLON = auto()


KEYWORDS = {"if", "then", "else", "def", "let", "true", "false",
            "anchor", "ever", "z", "show", "expect", "ascend",
            "assimilate", "learn", "equiv", "example", "to", "by",
            "and", "or", "not", "for", "in", "while", "do",
            "extern", "from"}

SPEC = [
    (T.NUM,   r'\d+\.\d+|\d+'),
    (T.STR,   r'"[^"\n]*"'),
    (T.CMP,   r'<=|>=|==|!='),
    (T.EQ,    r'='),
    (T.OP,    r'[-+*/<>.]'),
    (T.LPAR,  r'\('),
    (T.RPAR,  r'\)'),
    (T.COMMA, r','),
    (T.LBRACK, r'\['),
    (T.RBRACK, r'\]'),
    (T.LBRACE, r'\{'),
    (T.RBRACE, r'\}'),
    (T.COLON, r':'),
    (T.NAME,  r'[A-Za-z_]\w*'),
]
MASTER = re.compile("|".join(f"(?P<{t.name}>{p})" for t, p in SPEC))


@dataclass
class Token:
    kind: T
    text: str
    pos: int
    line: int = 1

    def __repr__(self) -> str:
        return f"{self.kind.name}({self.text})"


def lex(src: str) -> Tuple[List[Token], Optional[E]]:
    """Source into tokens. Returns (tokens, error-or-None)."""
    toks: List[Token] = []
    i, line = 0, 1
    n = len(src)

    while i < n:
        ch = src[i]
        if ch == "\n":
            line += 1; i += 1; continue
        if ch in " \t\r":
            i += 1; continue
        if ch == "#":
            while i < n and src[i] != "\n":
                i += 1
            continue

        m = MASTER.match(src, i)
        if not m:
            return toks, e_z("lex",
                             f"unexpected character {ch!r} at {i} (line {line})",
                             Defect.MISBOUND)

        kind = T[m.lastgroup]
        text = m.group()
        if kind is T.NAME and text in KEYWORDS:
            kind = T.KW
        if kind is T.STR and not text.endswith('"'):
            return toks, e_z("lex", f"unterminated string at line {line}",
                             Defect.UNBOUNDED)

        toks.append(Token(kind, text, i, line))
        i = m.end()

    toks.append(Token(T.EOF, "", i, line))
    return toks, None


# ═════════════════════════════════════════════
# 2. AST
# ═════════════════════════════════════════════

class Node:
    """Base. Every node knows its own size and shape."""

    def size(self) -> int:
        """Structural size. This is what ultracode should have been
        measuring all along: nodes, not characters."""
        return 1 + sum(c.size() for c in self.children())

    def depth(self) -> int:
        cs = self.children()
        return 1 + (max(c.depth() for c in cs) if cs else 0)

    def children(self) -> List["Node"]:
        return []

    def shape(self) -> str:
        """Structure with the constants erased. Two programs with the
        same shape are the same idea with different numbers in it."""
        return type(self).__name__


@dataclass
class Num(Node):
    value: float
    raw: str = ""    # the literal text: "1" vs "1.0" — drives INT vs REAL inference
    def shape(self) -> str: return "Num"
    def is_float_literal(self) -> bool:
        """True if the source text contained a decimal point."""
        return "." in self.raw if self.raw else self.value != int(self.value)
    def __str__(self) -> str:
        return str(int(self.value)) if self.value == int(self.value) \
            else str(self.value)


@dataclass
class Str(Node):
    value: str
    def __str__(self) -> str: return f'"{self.value}"'


@dataclass
class Bool(Node):
    value: bool
    def __str__(self) -> str: return "true" if self.value else "false"


@dataclass
class Var(Node):
    name: str
    def shape(self) -> str: return "Var"
    def __str__(self) -> str: return self.name


@dataclass
class BinOp(Node):
    op: str
    left: Node
    right: Node
    def children(self) -> List[Node]: return [self.left, self.right]
    def shape(self) -> str:
        return f"({self.left.shape()} {self.op} {self.right.shape()})"
    def __str__(self) -> str: return f"{self.left} {self.op} {self.right}"


@dataclass
class If(Node):
    cond: Node
    then: Node
    els: Node
    def children(self) -> List[Node]: return [self.cond, self.then, self.els]
    def shape(self) -> str:
        return f"if {self.cond.shape()} then {self.then.shape()} " \
               f"else {self.els.shape()}"
    def __str__(self) -> str:
        return f"if {self.cond} then {self.then} else {self.els}"


@dataclass
class Call(Node):
    name: str
    args: List[Node] = field(default_factory=list)
    def children(self) -> List[Node]: return list(self.args)
    def shape(self) -> str:
        return f"{self.name}({', '.join(a.shape() for a in self.args)})"
    def __str__(self) -> str:
        return f"{self.name}({', '.join(str(a) for a in self.args)})"


@dataclass
class FnDef(Node):
    name: str
    params: List[str]
    body: Node
    def children(self) -> List[Node]: return [self.body]
    def __str__(self) -> str:
        return f"def {self.name}({', '.join(self.params)}) = {self.body}"


@dataclass
class ListLit(Node):
    """`[a, b, c]` — an ordered collection."""
    items: List[Node] = field(default_factory=list)
    def children(self) -> List[Node]: return list(self.items)
    def shape(self) -> str:
        return f"List[{','.join(i.shape() for i in self.items)}]"
    def __str__(self) -> str:
        return "[" + ", ".join(str(i) for i in self.items) + "]"


@dataclass
class RecordLit(Node):
    """`{k: v, ...}` — named fields. Structurally identical to an SQL
    row and an HTML element, which is why EValue has one RECORD tag
    rather than three."""
    keys:   List[str] = field(default_factory=list)
    values: List[Node] = field(default_factory=list)
    def children(self) -> List[Node]: return list(self.values)
    def shape(self) -> str:
        return f"Record[{','.join(self.keys)}]"
    def __str__(self) -> str:
        return "{" + ", ".join(f"{k}: {v}" for k, v
                               in zip(self.keys, self.values)) + "}"


@dataclass
class UnaryOp(Node):
    """`not expr` — the only prefix operator in the language."""
    op: str
    operand: Node
    def children(self) -> List[Node]: return [self.operand]
    def shape(self) -> str: return f"Unary[{self.op}]({self.operand.shape()})"
    def __str__(self) -> str: return f"{self.op} {self.operand}"


@dataclass
class Index(Node):
    """`xs[i]` — reading an element out of a list."""
    target: Node
    key: Node
    def children(self) -> List[Node]: return [self.target, self.key]
    def shape(self) -> str: return f"Index({self.target.shape()},{self.key.shape()})"
    def __str__(self) -> str: return f"{self.target}[{self.key}]"


@dataclass
class Field(Node):
    """`r.name` — reading a field out of a record."""
    target: Node
    name: str
    def children(self) -> List[Node]: return [self.target]
    def shape(self) -> str: return f"Field({self.target.shape()},{self.name})"
    def __str__(self) -> str: return f"{self.target}.{self.name}"


@dataclass
class ForRange(Node):
    """`for NAME = start to end [by step] { body }` — a loop bounded
    by a known start and end, so it needs no anchoring proof: the
    range itself is the termination argument."""
    var:   str
    start: Node
    end:   Node
    step:  Optional[Node]
    body:  Node
    def children(self) -> List[Node]:
        cs = [self.start, self.end, self.body]
        if self.step: cs.append(self.step)
        return cs
    def shape(self) -> str: return f"ForRange({self.body.shape()})"
    def __str__(self) -> str:
        by = f" by {self.step}" if self.step else ""
        return f"for {self.var} = {self.start} to {self.end}{by} {{ {self.body} }}"


@dataclass
class ForIn(Node):
    """`for NAME in list { body }` — bounded by the list's own length,
    which is already known before the loop starts."""
    var:  str
    seq:  Node
    body: Node
    def children(self) -> List[Node]: return [self.seq, self.body]
    def shape(self) -> str: return f"ForIn({self.body.shape()})"
    def __str__(self) -> str: return f"for {self.var} in {self.seq} {{ {self.body} }}"


@dataclass
class While(Node):
    """`while cond { body }` — the one open-ended loop. Not anchored
    by a proof; guarded by a fixed iteration backstop the same way
    E_ANCHORED_MAX_DEPTH backstops anchored recursion."""
    cond: Node
    body: Node
    def children(self) -> List[Node]: return [self.cond, self.body]
    def shape(self) -> str: return f"While({self.body.shape()})"
    def __str__(self) -> str: return f"while {self.cond} {{ {self.body} }}"


@dataclass
class Extern(Node):
    """`extern NAME(params) from "libpath"` — declares NAME as a
    callable resolved to a real compiled C symbol, loaded at the
    point this statement runs. Declaration only: no value of its own,
    like Show — the effect is registering a callable, not producing
    a result to bind."""
    name:    str
    params:  List[str]
    libpath: str
    def children(self) -> List[Node]: return []
    def shape(self) -> str: return "Extern"
    def __str__(self) -> str:
        return (f'extern {self.name}({", ".join(self.params)}) '
               f'from "{self.libpath}"')


@dataclass
class ZLit(Node):
    """The zero-absolute literal. Not the number zero — the explicit
    ABSENCE of a measurement. Kept as its own node, not folded into
    Var("z"), so semantic analysis can treat it as a value with zero
    confidence rather than a name that happens to be unbound."""
    def shape(self) -> str: return "ZLit"
    def __str__(self) -> str: return "z"


@dataclass
class Let(Node):
    """A binding statement: `let NAME = expr` or `ever NAME = expr`.

    ONE node for both keywords, distinguished by `tracked` — the same
    "role, not kind" choice made for the C-side generic IR (form.h):
    `let` and `ever` differ in what they mean, not in what shape they
    are, so they do not need to be different classes.
    """
    name: str
    value: Node
    tracked: bool = False     # True for 'ever', False for 'let'
    def children(self) -> List[Node]: return [self.value]
    def shape(self) -> str: return "Let"
    def __str__(self) -> str:
        kw = "ever" if self.tracked else "let"
        return f"{kw} {self.name} = {self.value}"


@dataclass
class Show(Node):
    """`show NAME` — a statement, not an expression: it has no value
    of its own to fold into an outer expression, only an effect (write
    a formatted line). This is exactly why Program exists — the
    original grammar had no way to sequence a statement like this at
    all."""
    name: str
    def children(self) -> List[Node]: return []
    def shape(self) -> str: return "Show"
    def __str__(self) -> str: return f"show {self.name}"


@dataclass
class Program(Node):
    """An ordered sequence of statements: Let | Show | FnDef, or a
    bare expression evaluated for its side effect of being type-checked
    (rare, but not forbidden). This is the node type that was missing
    entirely — `program()` used to parse exactly one statement and
    demand EOF, which is why every multi-line .ever file in this
    project was actually being executed by a regex line-splitter
    living inside test-harness code rather than by the real parser."""
    statements: List[Node] = field(default_factory=list)
    def children(self) -> List[Node]: return list(self.statements)
    def shape(self) -> str:
        return f"Program[{','.join(s.shape() for s in self.statements)}]"
    def __str__(self) -> str:
        return "\n".join(str(s) for s in self.statements)


# ═════════════════════════════════════════════
# 2. PARSER — recursive descent over tokens
# ═════════════════════════════════════════════

@dataclass
class Recovery:
    """A syntax slip the parser fixed instead of failing on — a missing
    comma, a trailing comma, `=` used where a record wants `:`. This is
    the whole boundary of what E forgives: PUNCTUATION, never MEANING.
    A misspelled keyword, a missing `then`, a wrong operator still
    hard-fail, because guessing what those meant would mean computing
    an answer nobody asked for. Punctuation between two values has
    exactly one sane reading; that is what makes it safe to fix.
    """
    line:    int
    message: str
    teach:   str


class Parser:
    """Grammar, stated:

        program   := fndef | expr
        fndef     := 'def' NAME '(' params ')' '=' expr
        expr      := ifexpr | compare
        ifexpr    := 'if' expr 'then' expr 'else' expr
        compare   := additive [ CMP additive ]
        additive  := multiply { ('+' | '-') multiply }
        multiply  := atom { ('*' | '/') atom }
        atom      := NUM | STR | 'true' | 'false'
                   | NAME '(' args ')' | NAME | '(' expr ')'

    Left-associative, comparison lowest. This is the whole language;
    anything not derivable here is outside the grammar, and saying so
    precisely is the point of writing it down.
    """

    def __init__(self, toks: List[Token]):
        self.toks = toks
        self.i = 0
        # Syntax slips fixed instead of failed on — see Recovery.
        # Punctuation only, never a guess about what the person meant
        # to compute.
        self.recoveries: List["Recovery"] = []

    def _recover(self, message: str, teach: str) -> None:
        line = self.peek().line
        self.recoveries.append(Recovery(line, message, teach))

    def _sep_list(self, close: T, item_fn, ctx: str) -> list:
        """One or more items separated by commas, forgiving a missing
        comma between two items and a trailing comma before `close`.
        A missing comma is only inserted when the next token genuinely
        starts a new item — otherwise this falls through to whatever
        error the caller's own grammar raises, so a truly malformed
        program still fails loudly rather than being guessed at.
        """
        items = []
        if self.at(close):
            return items
        items.append(item_fn())
        while True:
            if self.at(T.COMMA):
                self.take()
                if self.at(close):
                    self._recover(
                        f"trailing comma in {ctx}",
                        "A comma after the last item is harmless — "
                        "removed it and kept going.")
                    break
                items.append(item_fn())
                continue
            if self.at(close) or self.at(T.EOF):
                break
            self._recover(
                f"missing comma in {ctx}",
                "Items need a comma between them — inserted one and "
                "kept going.")
            items.append(item_fn())
        return items

    # ── helpers ──
    def peek(self) -> Token: return self.toks[self.i]
    def at(self, kind: T, text: Optional[str] = None) -> bool:
        t = self.peek()
        return t.kind is kind and (text is None or t.text == text)
    def take(self) -> Token:
        t = self.toks[self.i]
        if t.kind is not T.EOF:
            self.i += 1
        return t
    def expect(self, kind: T, text: Optional[str] = None) -> Token:
        if not self.at(kind, text):
            got = self.peek()
            raise ParseError(f"expected {text or kind.name}, "
                             f"found {got.text or 'end of input'} "
                             f"at line {got.line}")
        return self.take()

    # ── grammar ──
    def program(self) -> Node:
        """Parse a full program: zero or more statements to EOF.

        Single-statement callers are unaffected: source consisting of
        one bare expression still returns that expression directly
        (not wrapped in a one-element Program), so every existing call
        site that expects `parse("1 + 1")` to hand back a BinOp keeps
        doing so. A Program wrapper only appears for more than one
        statement, or when the sole statement is let/ever/show — none
        of which parsed at all before this change, so nothing that
        used to work can have been relying on their absence.
        """
        statements: List[Node] = []
        while not self.at(T.EOF):
            stmt = self.statement()
            statements.append(stmt)
            # Let/Show/FnDef all start with a distinctive keyword, so
            # sequencing them needs no separator: 'show x\nshow y' is
            # unambiguous by construction. A bare expression-statement
            # has no such marker, so two of them back to back ("1 2")
            # would be silently accepted as two statements with no
            # lexical reason to believe that was intended rather than
            # a typo. A bare expression is therefore only legal as the
            # LAST statement — this is exactly the original grammar's
            # "one expression, then EOF" rule, preserved for the case
            # it was written for.
            if not isinstance(stmt, (Let, Show, FnDef, Extern)) and not self.at(T.EOF):
                t = self.peek()
                raise ParseError(f"unexpected {t.text!r} at line {t.line}")
        if len(statements) == 1 and isinstance(
                statements[0],
                (Num, Str, Bool, Var, ZLit, BinOp, If, Call, FnDef,
                 ListLit, RecordLit, UnaryOp, Index, Field,
                 ForRange, ForIn, While)):
            return statements[0]
        return Program(statements)

    def statement(self) -> Node:
        if self.at(T.KW, "def"):
            return self.fndef()
        if self.at(T.KW, "let") or self.at(T.KW, "ever"):
            return self.letstmt()
        if self.at(T.KW, "show"):
            return self.showstmt()
        if self.at(T.KW, "extern"):
            return self.externstmt()
        return self.expr()

    def externstmt(self) -> Extern:
        self.expect(T.KW, "extern")
        name = self.expect(T.NAME).text
        self.expect(T.LPAR)
        params: List[str] = []
        if not self.at(T.RPAR):
            params.append(self.expect(T.NAME).text)
            while self.at(T.COMMA):
                self.take()
                params.append(self.expect(T.NAME).text)
        self.expect(T.RPAR)
        self.expect(T.KW, "from")
        libpath = self.expect(T.STR).text[1:-1]   # strip quotes
        return Extern(name, params, libpath)

    def forstmt(self) -> Node:
        self.expect(T.KW, "for")
        var = self.expect(T.NAME).text
        if self.at(T.KW, "in"):
            self.take()
            seq = self.expr()
            self.expect(T.KW, "do")
            return ForIn(var, seq, self.expr())
        self.expect(T.EQ)
        start = self.expr()
        self.expect(T.KW, "to")
        end = self.expr()
        step = None
        if self.at(T.KW, "by"):
            self.take()
            step = self.expr()
        self.expect(T.KW, "do")
        return ForRange(var, start, end, step, self.expr())

    def whilestmt(self) -> Node:
        self.expect(T.KW, "while")
        cond = self.expr()
        self.expect(T.KW, "do")
        return While(cond, self.expr())

    def letstmt(self) -> Let:
        tracked = self.at(T.KW, "ever")
        self.take()                       # consume 'let' or 'ever'
        name = self.expect(T.NAME).text
        self.expect(T.EQ)
        value = self.expr()
        return Let(name, value, tracked=tracked)

    def showstmt(self) -> Show:
        self.expect(T.KW, "show")
        name = self.expect(T.NAME).text
        return Show(name)

    def listlit(self) -> ListLit:
        self.expect(T.LBRACK)
        items = self._sep_list(T.RBRACK, self.expr, "a list")
        self.expect(T.RBRACK)
        return ListLit(items)

    def recordlit(self) -> RecordLit:
        self.expect(T.LBRACE)
        keys: List[str] = []
        vals: List[Node] = []
        def field():
            keys.append(self.expect(T.NAME).text)
            # `:` is the grammar; `=` reads the same in this position
            # and there is nothing else it could mean here, so it is
            # forgiven rather than failed on.
            if self.at(T.EQ):
                self.take()
                self._recover(
                    "'=' used where a record wants ':'",
                    "Record fields use `key: value` — accepted '=' "
                    "the same way.")
            else:
                self.expect(T.COLON)
            vals.append(self.expr())
            return None
        self._sep_list(T.RBRACE, field, "a record")
        self.expect(T.RBRACE)
        return RecordLit(keys, vals)

    def fndef(self) -> FnDef:
        self.expect(T.KW, "def")
        name = self.expect(T.NAME).text
        self.expect(T.LPAR)
        params = self._sep_list(
            T.RPAR, lambda: self.expect(T.NAME).text, "a parameter list")
        self.expect(T.RPAR)
        self.expect(T.EQ)
        return FnDef(name, params, self.expr())

    def expr(self) -> Node:
        if self.at(T.KW, "if"):
            self.take()
            cond = self.expr()
            self.expect(T.KW, "then")
            then = self.expr()
            self.expect(T.KW, "else")
            return If(cond, then, self.expr())
        if self.at(T.KW, "for"):
            return self.forstmt()
        if self.at(T.KW, "while"):
            return self.whilestmt()
        return self.orexpr()

    # or binds loosest, and next, not tightest — 'a and b or not c'
    # reads as '(a and b) or (not c)', matching every C-family language
    def orexpr(self) -> Node:
        node = self.andexpr()
        while self.at(T.KW, "or"):
            self.take()
            node = BinOp("or", node, self.andexpr())
        return node

    def andexpr(self) -> Node:
        node = self.notexpr()
        while self.at(T.KW, "and"):
            self.take()
            node = BinOp("and", node, self.notexpr())
        return node

    def notexpr(self) -> Node:
        if self.at(T.KW, "not"):
            self.take()
            return UnaryOp("not", self.notexpr())
        return self.compare()

    def compare(self) -> Node:
        left = self.additive()
        if self.at(T.CMP) or (self.at(T.OP) and self.peek().text in "<>"):
            op = self.take().text
            return BinOp(op, left, self.additive())
        return left

    def additive(self) -> Node:
        node = self.multiply()
        while self.at(T.OP) and self.peek().text in "+-":
            op = self.take().text
            node = BinOp(op, node, self.multiply())
        return node

    def multiply(self) -> Node:
        node = self.postfix()
        while self.at(T.OP) and self.peek().text in "*/":
            op = self.take().text
            node = BinOp(op, node, self.postfix())
        return node

    def postfix(self) -> Node:
        node = self.atom()
        while True:
            if self.at(T.LBRACK):
                self.take()
                key = self.expr()
                self.expect(T.RBRACK)
                node = Index(node, key)
                continue
            if self.at(T.OP) and self.peek().text == ".":
                self.take()
                name = self.expect(T.NAME).text
                node = Field(node, name)
                continue
            break
        return node

    def atom(self) -> Node:
        t = self.peek()
        if t.kind is T.NUM:
            self.take(); return Num(float(t.text), raw=t.text)
        if t.kind is T.STR:
            self.take(); return Str(t.text[1:-1])
        if t.kind is T.KW and t.text in ("true", "false"):
            self.take(); return Bool(t.text == "true")
        if t.kind is T.KW and t.text == "z":
            self.take(); return ZLit()
        if t.kind is T.LBRACK:
            return self.listlit()
        if t.kind is T.LBRACE:
            return self.recordlit()
        if t.kind is T.LPAR:
            self.take()
            node = self.expr()
            self.expect(T.RPAR)
            return node
        if t.kind is T.OP and t.text == "-":
            self.take()
            return BinOp("-", Num(0), self.atom())
        if t.kind is T.NAME:
            self.take()
            if self.at(T.LPAR):
                self.take()
                args = self._sep_list(T.RPAR, self.expr, "a call")
                self.expect(T.RPAR)
                return Call(t.text, args)
            return Var(t.text)
        raise ParseError(f"unexpected {t.text or 'end of input'} "
                         f"at line {t.line}")


class ParseError(Exception):
    pass


def parse(src: str) -> Tuple[Optional[Node], Optional[E]]:
    toks, err = lex(src)
    if err:
        return None, err
    try:
        p = Parser(toks)
        node = p.program()
        if node is not None:
            node._recoveries = p.recoveries  # type: ignore[attr-defined]
        return node, None
    except ParseError as exc:
        return None, e_z("parse", str(exc), Defect.UNBOUNDED)


# ═════════════════════════════════════════════
# 3. SEMANTIC ANALYSIS
# ═════════════════════════════════════════════

class Ty(Enum):
    # NUM kept for backward compat; INT and REAL are the precise forms
    INT  = "int"   # integer literals and integer arithmetic
    REAL = "real"  # float literals and mixed-numeric arithmetic
    NUM  = "num"   # numeric result where INT/REAL unknown (legacy)
    TEXT = "text"  # string values
    BOOL = "bool"  # boolean values
    ANY  = "any"   # unknown — not yet inferred
    ERR  = "err"   # type error

    @classmethod
    def numeric(cls, a: "Ty", b: "Ty") -> "Ty":
        """The output type of a numeric operation over two typed operands.
        INT OP INT → INT.  Any real component → REAL.
        ANY OP X → X (ANY contributes nothing; the concrete side wins).
        """
        if cls.ERR in (a, b):
            return cls.ERR
        # strip ANY from the equation — it contributes nothing
        concrete = [t for t in (a, b) if t not in (cls.ANY,)]
        if not concrete:
            return cls.NUM   # both unknown
        if len(concrete) == 1:
            # one side is ANY — the concrete side determines the type
            c = concrete[0]
            return c if c in (cls.INT, cls.REAL) else cls.NUM
        # both sides concrete
        if cls.REAL in (a, b):
            return cls.REAL
        if cls.INT == a == b:
            return cls.INT
        if cls.NUM in (a, b):
            # NUM + INT → NUM (could refine but safe to leave ambiguous)
            return cls.NUM
        return cls.ERR

    def is_numeric(self) -> bool:
        return self in (Ty.INT, Ty.REAL, Ty.NUM)


# The Dynamic Profiler is optional: syntax.py must stay usable without
# it, so the import is guarded and every call site tolerates None.
try:
    from profiler import (Observation, classify, observe_source_flags,
                          Profiler, TAXONOMY, Tier)
    _PROFILER_AVAILABLE = True
except ImportError:      # pragma: no cover
    _PROFILER_AVAILABLE = False
    Observation = None


@dataclass
class Analysis:
    """What the semantic pass learned, before anything ran."""
    ty: Ty = Ty.ANY
    free: Set[str] = field(default_factory=set)
    calls: Set[str] = field(default_factory=set)
    recursive: bool = False
    measure: Optional[str] = None
    size: int = 0
    depth: int = 0
    shape: str = ""
    errors: List[str] = field(default_factory=list)
    fn_type: Optional[Any] = None  # FnType for function definitions

    # ── Dynamic Profiler ──────────────────────────────────────────
    # What constructs this program used, and what that implies about
    # its author. None when the profiler module is unavailable.
    observation: Optional[Any] = None
    proficiency: Optional[int] = None   # 0..256, same scale as trust
    scaffold: Optional[str] = None      # how much help to show

    @property
    def clean(self) -> bool:
        return not self.errors

    @property
    def construct_mix(self) -> Dict[str, float]:
        """The simple-vs-advanced ratio, which is the question the
        profiler exists to answer."""
        if not self.observation:
            return {}
        return {
            "simple":       self.observation.simple_ratio,
            "advanced":     self.observation.advanced_ratio,
            "unique":       self.observation.unique,
            "total":        self.observation.total,
        }


@dataclass
class ProgramAnalysis:
    """Result of analysing a whole Program: every name that ended up
    bound, every name a `show` referenced, and errors gathered across
    every statement in source order."""
    bound:      Set[str] = field(default_factory=set)
    shown:      Set[str] = field(default_factory=set)
    errors:     List[str] = field(default_factory=list)
    statements: List[Analysis] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.errors


@dataclass
class FnType:
    """The inferred type signature of a function.

    param_types: what the function expects for each parameter.
                 A newly defined function starts with ANY for all params;
                 inference fills these in from the body.
    return_type: what the function produces.
    """
    param_types: List[Ty]
    return_type: Ty

    def __str__(self) -> str:
        params = ", ".join(t.value for t in self.param_types)
        return f"({params}) → {self.return_type.value}"


class Semantic:
    """Stage 3. Scope resolution, arity checking and type inference,
    all before a single value is computed.

    Ever used to discover an unbound name at evaluation time, wrapped in
    a Z. That is not wrong, but it is late: it means a defect only
    surfaces on the input that reaches it. Catching it here means the
    binding is checked whether or not that branch ever runs.

    TYPE INFERENCE is Hindley-Milner lite: bottom-up from literals,
    propagating through operators, meeting at if-branches. Functions
    gain a FnType: parameter types derived from use inside the body,
    return type from the body's inferred type.
    """

    NUMERIC_OPS = {"+", "-", "*", "/"}
    COMPARE_OPS = {"<", ">", "<=", ">=", "==", "!="}
    LOGIC_OPS   = {"and", "or"}

    def __init__(self, known_fns: Optional[Dict[str, int]] = None,
                 known_fn_types: Optional[Dict[str, FnType]] = None,
                 profiler: Optional[Any] = None,
                 source: Optional[str] = None):
        self.fns: Dict[str, int] = dict(known_fns or {})
        self.fn_types: Dict[str, FnType] = dict(known_fn_types or {})
        self.vars: Dict[str, Ty] = {}   # current scope variable types

        # ── Dynamic Profiler wiring ──────────────────────────────
        # The semantic pass already walks every node to check scope
        # and infer types. Classifying constructs on that same walk
        # costs one dict increment per node, so profiling is free:
        # no second traversal, no separate parse.
        self.profiler = profiler if _PROFILER_AVAILABLE else None
        self.source   = source
        self.last_observation = None

    def analyse_program(self, prog: "Program",
                        preexisting: Optional[Set[str]] = None) -> "ProgramAnalysis":
        """Statement-level analysis: threads bound names across an
        ordered sequence of Let/Ever/Show/FnDef statements.

        analyse() handles one expression in isolation. A program is a
        sequence where each statement's bindings are visible to the
        ones after it — `let y = x + 1` after `let x = 1` must not
        report x as unbound just because analyse() alone has no notion
        of "what came before". This is that missing thread.

        `preexisting` seeds the bound-set from names already live in
        a runtime scope — needed for REPL/embedder use, where each
        call analyses only the newest line but the scope carries
        everything typed before it. Without this, line 2 of a REPL
        session sees line 1's binding in the runtime scope but the
        semantic pass still calls it unbound, and rejects it before
        execution ever looks the name up.
        """
        bound: Set[str] = set(preexisting or ())
        errors: List[str] = []
        analyses: List[Analysis] = []
        shown: Set[str] = set()

        for stmt in prog.statements:
            cls = type(stmt).__name__

            if cls == "FnDef":
                a = self.analyse(stmt)
                analyses.append(a)
                errors.extend(f"in def {stmt.name}: {e}" for e in a.errors)
                continue

            if cls == "Extern":
                self.fns[stmt.name] = len(stmt.params)
                continue

            if cls == "Let":
                a = self.analyse(stmt.value, bound=bound)
                analyses.append(a)
                errors.extend(a.errors)
                bound.add(stmt.name)
                continue

            if cls == "Show":
                if stmt.name not in bound and stmt.name not in self.fns:
                    errors.append(f"show references unbound name "
                                  f"'{stmt.name}'")
                shown.add(stmt.name)
                continue

            # a bare expression statement (only legal as the last one)
            a = self.analyse(stmt, bound=bound)
            analyses.append(a)
            errors.extend(a.errors)

        return ProgramAnalysis(bound=bound, shown=shown,
                               errors=errors, statements=analyses)

    def analyse(self, node: Node,
                bound: Optional[Set[str]] = None) -> Analysis:
        a = Analysis()
        bound = set(bound or ())

        if isinstance(node, FnDef):
            self.fns[node.name] = len(node.params)

            # PHASE 1: first pass with ALL params typed as ANY.
            # This lets us discover the return type even before we know
            # the param types, which matters for recursive functions.
            param_types_v1 = [Ty.ANY] * len(node.params)
            self.vars = dict(zip(node.params, param_types_v1))
            inner = self.analyse(node.body, set(node.params))
            return_ty = inner.ty

            # PHASE 2: refine param types from usage in the body.
            # Walk the body tracking which type each param must be for
            # the expression to type-check without errors. This is the
            # core of Hindley-Milner inference lite.
            param_types_v2 = self._infer_param_types(
                node.params, node.body, return_ty)

            # PHASE 3: re-analyse with refined param types to get the
            # final return type under the correct param assumptions.
            self.vars = dict(zip(node.params, param_types_v2))
            inner2 = self.analyse(node.body, set(node.params))
            return_ty = inner2.ty

            # store the inferred function signature
            fn_ty = FnType(param_types_v2, return_ty)
            self.fn_types[node.name] = fn_ty

            a = inner2
            a.recursive = node.name in inner2.calls
            a.free -= set(node.params)
            if a.recursive:
                a.measure = self._measure(node)
            a.size = node.size(); a.depth = node.depth()
            a.shape = node.body.shape()
            a.fn_type = fn_ty          # attach the signature to the analysis
            for name in sorted(a.free):
                msg = f"unbound name '{name}'"
                if msg not in a.errors:
                    a.errors.append(msg)
            self._profile(node, a)
            return a

        a.ty = self._walk(node, bound, a)
        a.size = node.size(); a.depth = node.depth(); a.shape = node.shape()
        for name in sorted(a.free):
            msg = f"unbound name '{name}'"
            if msg not in a.errors:
                a.errors.append(msg)
        self._profile(node, a)
        return a

    def _profile(self, node: Node, a: Analysis) -> None:
        """Record what this program demonstrates, and fold it into the
        running Proficiency Score.

        Called at the end of analyse(), on the tree that was just
        type-checked. Two properties matter here:

        1. It never raises. A profiler fault must not take down the
           semantic pass — analysis is load-bearing, profiling is not.
        2. It only updates the persistent score when a profiler was
           handed in. Without one, the Analysis still carries the
           observation, so callers can inspect the construct mix
           without any state being written anywhere.
        """
        if not _PROFILER_AVAILABLE:
            return
        try:
            obs = classify(node)
            if self.source:
                observe_source_flags(obs, self.source)
            obs.errors = len(a.errors)
            a.observation = obs
            self.last_observation = obs

            if self.profiler is not None:
                p = self.profiler.observe(obs)
                a.proficiency = p.rounded
                a.scaffold    = p.scaffold
        except Exception:
            # profiling is best-effort and never fatal
            pass

    def _walk(self, node: Node, bound: Set[str], a: Analysis) -> Ty:
        # ── LITERALS: precise type from the source text ──
        # Num.is_float_literal() checks the raw source: "1" → INT, "1.0" → REAL
        if isinstance(node, Num):
            ty = Ty.REAL if node.is_float_literal() else Ty.INT
            a.ty = ty; return ty
        if isinstance(node, Str):
            a.ty = Ty.TEXT; return Ty.TEXT
        if isinstance(node, Bool):
            a.ty = Ty.BOOL; return Ty.BOOL

        if isinstance(node, Var):
            if node.name not in bound:
                a.free.add(node.name)
            # Look up the variable's type in the function signature
            known = self.vars.get(node.name)
            ty = known if known else Ty.ANY
            a.ty = ty; return ty

        if isinstance(node, BinOp):
            lt = self._walk(node.left, bound, a)
            rt = self._walk(node.right, bound, a)

            # ── boolean connectives: BOOL, BOOL -> BOOL ──
            if node.op in self.LOGIC_OPS:
                for t, side in ((lt, "left"), (rt, "right")):
                    if t not in (Ty.BOOL, Ty.ANY):
                        a.errors.append(
                            f"{node.op} needs a truth value on the "
                            f"{side}, got {t.value}")
                a.ty = Ty.BOOL
                return Ty.BOOL

            # ── comparisons always produce BOOL ──
            if node.op in self.COMPARE_OPS:
                if lt == Ty.TEXT and rt == Ty.BOOL or \
                   lt == Ty.BOOL and rt == Ty.TEXT:
                    a.errors.append(
                        f"comparing {lt.value} with {rt.value}")
                a.ty = Ty.BOOL
                return Ty.BOOL

            # ── string concatenation: TEXT + TEXT → TEXT ──
            if node.op == "+" and (lt == Ty.TEXT or rt == Ty.TEXT):
                if lt != Ty.TEXT or rt != Ty.TEXT:
                    if lt != Ty.ANY and rt != Ty.ANY:
                        a.errors.append(
                            f"cannot concatenate text with {(lt if lt != Ty.TEXT else rt).value}")
                a.ty = Ty.TEXT
                return Ty.TEXT

            # ── arithmetic ──
            for t, side in ((lt, "left"), (rt, "right")):
                if t is Ty.TEXT:
                    a.errors.append(
                        f"cannot apply '{node.op}' to text on the {side}")
                if t is Ty.BOOL:
                    a.errors.append(
                        f"cannot apply '{node.op}' to a bool on the {side}")
            if node.op == "/" and isinstance(node.right, Num) \
                    and node.right.value == 0:
                a.errors.append("division by a literal zero")

            # ── numeric type propagation ──
            result = Ty.numeric(lt, rt)
            # division always produces REAL (5/2 = 2.5)
            if node.op == "/":
                result = Ty.REAL
            a.ty = result
            return result

        if isinstance(node, If):
            ct = self._walk(node.cond, bound, a)
            if ct is Ty.TEXT:
                a.errors.append("condition is text, not a truth value")
            tt = self._walk(node.then, bound, a)
            et = self._walk(node.els, bound, a)
            numeric = {Ty.INT, Ty.REAL, Ty.NUM}
            # INT/REAL/NUM are precision variants of the same family —
            # NUM specifically means "numeric, precision not yet
            # pinned" (e.g. a recursive call's own return type, still
            # being inferred). Treating that as a hard clash against
            # INT rejected well-typed recursive functions like
            # `fib`: the then-arm returns a param inferred as INT,
            # the else-arm a same-function recursive call whose
            # return type resolves to NUM before the fixed point is
            # reached. Both are numbers; only a genuine category
            # clash (numeric vs text, text vs bool, ...) is an error.
            both_numeric = tt in numeric and et in numeric
            if (tt is not Ty.ANY and et is not Ty.ANY
                    and tt != et and not both_numeric):
                a.errors.append(
                    f"branches disagree: then is {tt.value}, "
                    f"else is {et.value}")
            if both_numeric and tt != et:
                a.ty = Ty.REAL if Ty.REAL in (tt, et) else Ty.numeric(tt, et)
            else:
                a.ty = tt if tt == et else Ty.ANY
            return a.ty

        if isinstance(node, Call):
            a.calls.add(node.name)
            for arg in node.args:
                self._walk(arg, bound, a)
            expected = self.fns.get(node.name)
            if expected is None:
                try:
                    from builtins_ml import BUILTINS
                    b = BUILTINS.get(node.name)
                    if b is not None:
                        expected = b.arity
                except ImportError:
                    pass
            if expected is not None and expected != len(node.args):
                a.errors.append(
                    f"{node.name} takes {expected} argument(s), "
                    f"given {len(node.args)}")
            return Ty.ANY

        if isinstance(node, UnaryOp):
            ot = self._walk(node.operand, bound, a)
            if node.op == "not" and ot not in (Ty.BOOL, Ty.ANY):
                a.errors.append(f"not needs a truth value, got {ot.value}")
            a.ty = Ty.BOOL
            return Ty.BOOL

        if isinstance(node, Index):
            self._walk(node.target, bound, a)
            kt = self._walk(node.key, bound, a)
            if kt not in (Ty.INT, Ty.ANY, Ty.NUM):
                a.errors.append(f"index must be a number, got {kt.value}")
            return Ty.ANY   # element type isn't tracked per-list

        if isinstance(node, Field):
            self._walk(node.target, bound, a)
            return Ty.ANY   # field type isn't tracked per-record

        if isinstance(node, ForRange):
            self._walk(node.start, bound, a)
            self._walk(node.end, bound, a)
            if node.step:
                self._walk(node.step, bound, a)
            inner_bound = set(bound) | {node.var}
            self._walk(node.body, inner_bound, a)
            return Ty.ANY

        if isinstance(node, ForIn):
            self._walk(node.seq, bound, a)
            inner_bound = set(bound) | {node.var}
            self._walk(node.body, inner_bound, a)
            return Ty.ANY

        if isinstance(node, While):
            ct = self._walk(node.cond, bound, a)
            if ct not in (Ty.BOOL, Ty.ANY):
                a.errors.append(f"while needs a truth value, got {ct.value}")
            self._walk(node.body, bound, a)
            return Ty.ANY

        return Ty.ANY

    def _infer_param_types(self, params: List[str],
                            body: Node, return_ty: Ty) -> List[Ty]:
        """Infer parameter types from their use in the function body.

        Strategy: collect every constraint a parameter must satisfy for
        the body to type-check. The type is the JOIN of all constraints.
        JOIN means: if all uses say INT → INT; if any use says REAL → REAL;
        if uses conflict → ANY (we cannot resolve the contradiction here).

        This is a single-pass unification, not full HM. It handles the
        common cases: arithmetic params, comparison params, text params.
        Higher-order and polymorphic params stay as ANY.
        """
        param_types: List[Ty] = [Ty.ANY] * len(params)
        param_idx = {name: i for i, name in enumerate(params)}

        def collect(node: Node, expected: Ty = Ty.ANY) -> Ty:
            """Walk the node and collect type constraints on params."""
            if isinstance(node, Num):
                return Ty.REAL if node.is_float_literal() else Ty.INT
            if isinstance(node, Str):
                return Ty.TEXT
            if isinstance(node, Bool):
                return Ty.BOOL
            if isinstance(node, Var):
                if node.name in param_idx:
                    idx = param_idx[node.name]
                    if expected != Ty.ANY:
                        # constrain this parameter
                        cur = param_types[idx]
                        if cur == Ty.ANY:
                            param_types[idx] = expected
                        elif cur != expected:
                            # conflict: leave as ANY (polymorphic or error)
                            param_types[idx] = Ty.ANY
                return param_types[param_idx[node.name]] if node.name in param_idx else Ty.ANY
            if isinstance(node, BinOp):
                if node.op in self.COMPARE_OPS:
                    lt = collect(node.left, Ty.ANY)
                    rt = collect(node.right, Ty.ANY)
                    # narrow params from what the other side implies
                    if isinstance(node.left, Var) and node.left.name in param_idx:
                        idx = param_idx[node.left.name]
                        if param_types[idx] == Ty.ANY and rt.is_numeric():
                            param_types[idx] = rt
                    if isinstance(node.right, Var) and node.right.name in param_idx:
                        idx = param_idx[node.right.name]
                        if param_types[idx] == Ty.ANY and lt.is_numeric():
                            param_types[idx] = lt
                    return Ty.BOOL
                if node.op in self.NUMERIC_OPS:
                    # handle + first for text concatenation
                    if node.op == "+":
                        lt_peek = collect(node.left, Ty.ANY)
                        rt_peek = collect(node.right, Ty.ANY)
                        if lt_peek == Ty.TEXT or rt_peek == Ty.TEXT:
                            return Ty.TEXT
                if node.op in self.NUMERIC_OPS:
                    lt = collect(node.left, Ty.ANY)
                    rt = collect(node.right, Ty.ANY)
                    # What type does the non-param side demand?
                    # e.g. in (n + 1): n is ANY, 1 is INT → n must be INT
                    # e.g. in (n * 2.0): n is ANY, 2.0 is REAL → n must be REAL
                    def narrow(var_node, other_ty: Ty):
                        if isinstance(var_node, Var) and var_node.name in param_idx:
                            idx = param_idx[var_node.name]
                            if param_types[idx] == Ty.ANY and other_ty not in (Ty.ANY, Ty.NUM):
                                param_types[idx] = other_ty
                            elif param_types[idx] == Ty.ANY and other_ty == Ty.NUM:
                                param_types[idx] = Ty.INT  # default numeric to INT
                    narrow(node.left, rt)
                    narrow(node.right, lt)
                    # re-read the param type after narrowing
                    lt2 = param_types[param_idx[node.left.name]] if (isinstance(node.left, Var) and node.left.name in param_idx) else lt
                    rt2 = param_types[param_idx[node.right.name]] if (isinstance(node.right, Var) and node.right.name in param_idx) else rt
                    if node.op == "/":
                        return Ty.REAL
                    return Ty.numeric(lt2, rt2)
                return Ty.ANY
            if isinstance(node, If):
                collect(node.cond, Ty.BOOL)
                tt = collect(node.then, expected)
                et = collect(node.els, expected)
                if tt == et:
                    return tt
                if tt.is_numeric() and et.is_numeric():
                    return Ty.REAL
                return Ty.ANY
            if isinstance(node, Call):
                # push return type of known function as expected for its args
                ft = self.fn_types.get(node.name)
                for i, arg in enumerate(node.args):
                    exp_arg = ft.param_types[i] if (ft and i < len(ft.param_types)) else Ty.ANY
                    collect(arg, exp_arg)
                return ft.return_type if ft else Ty.ANY
            return Ty.ANY

        collect(body, return_ty)
        return param_types

    @staticmethod
    def _measure(fn: FnDef) -> Optional[str]:
        """A parameter that strictly decreases in every self-call.

        On the AST this is a structural question rather than a regex
        one, so it sees through parentheses and nesting that the string
        version could not.
        """
        calls: List[Call] = []

        def collect(n: Node) -> None:
            if isinstance(n, Call) and n.name == fn.name:
                calls.append(n)
            for c in n.children():
                collect(c)

        collect(fn.body)
        if not calls:
            return None

        for idx, p in enumerate(fn.params):
            good = True
            for call in calls:
                if idx >= len(call.args):
                    good = False; break
                arg = call.args[idx]
                if isinstance(arg, BinOp) and isinstance(arg.left, Var) \
                        and arg.left.name == p and isinstance(arg.right, Num):
                    if arg.op == "-" and arg.right.value > 0:
                        continue
                    if arg.op == "/" and arg.right.value > 1:
                        continue
                good = False
                break
            if good:
                return p
        return None


# ═════════════════════════════════════════════
# 4. EXECUTION over the AST
# ═════════════════════════════════════════════

def eval_ast(node: Node, env: Dict[str, E],
             fns: Dict[str, FnDef], depth: int = 0,
             limit: int = 3) -> E:
    """Stage 4, walking a tree instead of a string.

    Same semantics as abstract.py: chain by min, Z absorbs, a Z
    condition spans both branches, branches are lazy under a known
    condition.
    """
    if isinstance(node, Num):
        v = int(node.value) if node.value == int(node.value) else node.value
        return e_val("lit", v, E_CERTAIN)
    if isinstance(node, Str):
        return e_val("lit", node.value, E_CERTAIN)
    if isinstance(node, Bool):
        return e_val("lit", node.value, E_CERTAIN)

    if isinstance(node, Var):
        v = env.get(node.name)
        return v if v is not None else \
            e_z(node.name, f"{node.name} was never bound", Defect.UNBOUND)

    if isinstance(node, BinOp):
        a = eval_ast(node.left, env, fns, depth, limit)
        if a.is_z:
            return a
        b = eval_ast(node.right, env, fns, depth, limit)
        if b.is_z:
            return b
        conf = min(a.confidence, b.confidence)
        try:
            if node.op == "+":  v = a.value + b.value
            elif node.op == "-": v = a.value - b.value
            elif node.op == "*": v = a.value * b.value
            elif node.op == "/":
                if b.value == 0:
                    return e_z("div", "division by zero", Defect.MISBOUND)
                v = a.value / b.value
            elif node.op == "<":  v = a.value < b.value
            elif node.op == ">":  v = a.value > b.value
            elif node.op == "<=": v = a.value <= b.value
            elif node.op == ">=": v = a.value >= b.value
            elif node.op == "==": v = a.value == b.value
            elif node.op == "!=": v = a.value != b.value
            else:
                return e_z("op", f"unknown operator {node.op}",
                           Defect.MISBOUND)
        except TypeError:
            return e_z("op", f"cannot {node.op} {a.type_name()} "
                             f"with {b.type_name()}", Defect.MISBOUND)
        if isinstance(v, float) and v == int(v):
            v = int(v)
        return e_val("op", v, conf)

    if isinstance(node, If):
        cond = eval_ast(node.cond, env, fns, depth, limit)
        if not cond.is_z:
            taken = node.then if cond.value else node.els
            r = eval_ast(taken, env, fns, depth, limit)
            if r.is_z:
                return r
            return e_val("if", r.value, min(cond.confidence, r.confidence))
        # unknown condition: both arms, then span
        a = eval_ast(node.then, env, fns, depth, limit)
        b = eval_ast(node.els, env, fns, depth, limit)
        if a.is_z or b.is_z:
            return e_z("if", "condition unknown and a branch is Z",
                       Defect.UNBOUND)
        if a.value == b.value:
            return e_val("if", a.value, min(a.confidence, b.confidence))
        from ever import e_equiv, E_PI_WIDTH_WARN
        if not isinstance(a.value, (int, float)) or \
           not isinstance(b.value, (int, float)):
            return e_z("if", "branches are not spannable", Defect.UNBOUNDED)
        lo, hi = sorted([int(a.value), int(b.value)])
        if hi - lo > E_PI_WIDTH_WARN:
            return e_z("if", f"branches span {hi - lo}, past the pi "
                             f"threshold", Defect.UNBOUNDED)
        r = e_equiv("if", lo, hi)
        r.confidence = min(a.confidence, b.confidence)
        return r

    if isinstance(node, Call):
        fn = fns.get(node.name)
        if fn is None:
            return e_z(node.name, f"{node.name} was never defined",
                       Defect.UNBOUND)
        if depth > limit:
            return e_z(node.name, f"depth ceiling {limit} exceeded",
                       Defect.UNBOUNDED)
        args = [eval_ast(a, env, fns, depth, limit) for a in node.args]
        for a in args:
            if a.is_z:
                return a
        if len(args) != len(fn.params):
            return e_z(node.name, f"expected {len(fn.params)} argument(s), "
                                  f"got {len(args)}", Defect.MISBOUND)
        local = dict(zip(fn.params, args))
        r = eval_ast(fn.body, local, fns, depth + 1, limit)
        if r.is_z:
            return r
        return e_val(node.name, r.value,
                     min([r.confidence] + [a.confidence for a in args]))

    return e_z("eval", f"cannot evaluate {type(node).__name__}",
               Defect.MISBOUND)


# ═════════════════════════════════════════════
# The pipeline, end to end, returning E at every stage
# ═════════════════════════════════════════════

@dataclass
class Compiled:
    src: str
    tokens: List[Token] = field(default_factory=list)
    ast: Optional[Node] = None
    analysis: Optional[Analysis] = None
    error: Optional[E] = None
    stage: str = ""

    @property
    def ok(self) -> bool:
        return self.error is None and (self.analysis is None
                                       or self.analysis.clean)


def compile_ever(src: str,
                 known_fns: Optional[Dict[str, int]] = None) -> Compiled:
    """1 -> 2 -> 3, stopping at the first stage that refuses."""
    c = Compiled(src=src)

    toks, err = lex(src)
    c.tokens = toks
    if err:
        c.error, c.stage = err, "lex"
        return c

    try:
        c.ast = Parser(toks).program()
    except ParseError as exc:
        c.error, c.stage = e_z("parse", str(exc), Defect.UNBOUNDED), "parse"
        return c

    c.analysis = Semantic(known_fns).analyse(c.ast)
    c.stage = "semantic" if c.analysis.errors else "ready"
    return c


# ═════════════════════════════════════════════
# Grammar coverage — the gap the notebook batch exposed
# ═════════════════════════════════════════════

def shapes_of(nodes: List[Node]) -> Dict[str, int]:
    """How many genuinely distinct structures, ignoring constants.

    Cell 7 of the notebook batch returned three 'independent' candidates
    that were the same formula with different base cases. On strings
    they looked different. On shapes they are one, and one candidate
    cannot corroborate itself.
    """
    counts: Dict[str, int] = {}
    for n in nodes:
        s = n.shape()
        counts[s] = counts.get(s, 0) + 1
    return counts


def skeleton(node: Node) -> str:
    """Shape with comparison operators and constants collapsed.

    `if n < 1 then 1 else ...` and `if n <= 0 then 1 else ...` are the
    same idea with the base case nudged. Counting them as two
    independent solutions was what let a single overfitted formula look
    like a consensus in the notebook batch.
    """
    if isinstance(node, (Num, Str, Bool)):
        return "K"
    if isinstance(node, Var):
        return "V"
    if isinstance(node, BinOp):
        op = "CMP" if node.op in Semantic.COMPARE_OPS else node.op
        return f"({skeleton(node.left)} {op} {skeleton(node.right)})"
    if isinstance(node, If):
        return (f"if {skeleton(node.cond)} then {skeleton(node.then)} "
                f"else {skeleton(node.els)}")
    if isinstance(node, Call):
        return f"CALL({', '.join(skeleton(a) for a in node.args)})"
    if isinstance(node, FnDef):
        return skeleton(node.body)
    return "?"


def distinct_skeletons(bodies: List[str]) -> Tuple[int, Dict[str, int]]:
    """How many genuinely different ideas, not how many strings."""
    counts: Dict[str, int] = {}
    for b in bodies:
        node, err = parse(b)
        if node is None:
            continue
        k = skeleton(node)
        counts[k] = counts.get(k, 0) + 1
    return len(counts), counts


def distinct_shapes(bodies: List[str]) -> Tuple[int, Dict[str, int]]:
    asts: List[Node] = []
    for b in bodies:
        node, err = parse(b)
        if node is not None:
            asts.append(node)
    counts = shapes_of(asts)
    return len(counts), counts


if __name__ == "__main__":
    print("\n" + "=" * 68)
    print("EVER — the pipeline, all four stages")
    print("=" * 68)

    src = "def fact(n) = if n <= 1 then 1 else n * fact(n - 1)"
    print(f"\nsource: {src}\n")

    toks, _ = lex(src)
    print(f"1. LEXER    {len(toks)} tokens")
    print("            " + " ".join(t.text for t in toks[:14]) + " ...")

    c = compile_ever(src)
    print(f"\n2. PARSER   {type(c.ast).__name__}, "
          f"{c.ast.size()} nodes, depth {c.ast.depth()}")
    print(f"            {c.ast}")

    a = c.analysis
    print(f"\n3. SEMANTIC type={a.ty.value} recursive={a.recursive} "
          f"measure={a.measure}")
    print(f"            calls={sorted(a.calls)} free={sorted(a.free)}")
    print(f"            errors={a.errors or 'none'}")
    print(f"            shape={a.shape}")

    fns = {c.ast.name: c.ast}
    print("\n4. EXECUTE")
    for n in (1, 3, 5):
        r = eval_ast(Call("fact", [Num(n)]), {}, fns, 0, limit=99)
        print(f"            fact({n}) = {r.value}  @ {r.confidence}/256")
    print()
