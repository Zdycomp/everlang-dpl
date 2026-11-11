#!/usr/bin/env python3
"""
contract.py — what every front end in the forge must agree on.

The forge builds several independent lexers and several independent
parsers and runs every combination. For that to mean anything, the
combinations have to be comparable, so this module fixes three things
and nothing else:

  1. the token stream  — kind, text, position, line
  2. the AST           — a canonical s-expression per tree
  3. failure           — a defect class and a line, never a message

Prose is deliberately excluded from the contract. Two implementations
that both reject `a $ b` are in agreement even if one says "unexpected
character" and the other says "no rule matches"; requiring identical
wording would manufacture disagreements that are not about the
language. What they must agree on is *that* it fails, *where*, and
*which of EZR's five binding defects* it is.

The forge defines its own AST rather than importing the incumbent's.
Sharing the incumbent's node classes would make every parser partly the
incumbent, and corroboration between witnesses that share an ancestor
is not corroboration — SEMANTICS.md 2.2 requires independence.

Codric Enterprise · Ricky (Dreid) · 2026
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

# ═════════════════════════════════════════════
# Tokens
# ═════════════════════════════════════════════

#: The canonical kinds. Every lexer emits exactly these names.
KINDS = ("NUM", "STR", "NAME", "KW", "OP", "CMP",
         "LPAR", "RPAR", "LBRACK", "RBRACK", "COMMA", "EQ", "EOF")

#: EZR's five binding defects (SEMANTICS.md 1). A front end failure
#: classifies into one of these; it does not raise.
DEFECTS = ("unbound", "misbound", "unbounded", "overbound", "orphaned")


@dataclass(frozen=True)
class Tok:
    kind: str
    text: str
    pos: int
    line: int

    def __repr__(self) -> str:
        return f"{self.kind}:{self.text!r}@{self.pos}"

    def canon(self) -> str:
        return f"{self.kind}({self.text})@{self.pos}L{self.line}"


@dataclass(frozen=True)
class Fail:
    """A refusal. Carries a defect class and a place, never prose."""
    stage: str           # "lex" | "parse"
    defect: str
    pos: int
    line: int

    def canon(self) -> str:
        return f"FAIL[{self.stage}/{self.defect}]@{self.pos}L{self.line}"


@dataclass
class LexOut:
    toks: List[Tok] = field(default_factory=list)
    fail: Optional[Fail] = None

    @property
    def ok(self) -> bool:
        return self.fail is None

    def canon(self) -> str:
        if self.fail:
            return self.fail.canon()
        return " ".join(t.canon() for t in self.toks)

    def kinds(self) -> Tuple[str, ...]:
        return tuple(t.kind for t in self.toks)


# ═════════════════════════════════════════════
# AST
# ═════════════════════════════════════════════

class N:
    """Base node. Every node can state its own canonical form."""

    def kids(self) -> List["N"]:
        return []

    def sexp(self) -> str:
        raise NotImplementedError

    def size(self) -> int:
        return 1 + sum(k.size() for k in self.kids())

    def height(self) -> int:
        ks = self.kids()
        return 1 + (max(k.height() for k in ks) if ks else 0)

    def __str__(self) -> str:
        return self.sexp()


def _num(v: float) -> str:
    return str(int(v)) if float(v) == int(v) else repr(float(v))


@dataclass
class Num(N):
    value: float
    def sexp(self) -> str: return _num(self.value)


@dataclass
class Str(N):
    value: str
    def sexp(self) -> str: return f'(str {self.value!r})'


@dataclass
class Bool(N):
    value: bool
    def sexp(self) -> str: return "true" if self.value else "false"


@dataclass
class Var(N):
    name: str
    def sexp(self) -> str: return self.name


@dataclass
class Bin(N):
    op: str
    left: N
    right: N
    def kids(self) -> List[N]: return [self.left, self.right]
    def sexp(self) -> str:
        return f"({self.op} {self.left.sexp()} {self.right.sexp()})"


@dataclass
class If(N):
    cond: N
    then: N
    els: N
    def kids(self) -> List[N]: return [self.cond, self.then, self.els]
    def sexp(self) -> str:
        return (f"(if {self.cond.sexp()} {self.then.sexp()} "
                f"{self.els.sexp()})")


@dataclass
class Call(N):
    name: str
    args: List[N] = field(default_factory=list)
    def kids(self) -> List[N]: return list(self.args)
    def sexp(self) -> str:
        inner = "".join(" " + a.sexp() for a in self.args)
        return f"(call {self.name}{inner})"


@dataclass
class Def(N):
    name: str
    params: List[str]
    body: N
    def kids(self) -> List[N]: return [self.body]
    def sexp(self) -> str:
        ps = " ".join(self.params)
        return f"(def {self.name} ({ps}) {self.body.sexp()})"


@dataclass
class Lst(N):
    """A list literal.

    Its confidence is the chain rule applied to its elements: a list is
    no more trusted than the least-trusted thing in it (SEMANTICS.md
    2.1). That falls straight out of the existing law rather than being
    a new rule for collections.
    """
    items: List[N] = field(default_factory=list)

    def kids(self) -> List[N]:
        return list(self.items)

    def sexp(self) -> str:
        inner = "".join(" " + i.sexp() for i in self.items)
        return f"(list{inner})"


@dataclass
class Let(N):
    """A local binding: `let x = v in body`.

    Not mutation -- `x` names a thread that already exists, and the
    body is evaluated with that name bound. Nothing is overwritten,
    which is what keeps G9 true.
    """
    name: str
    value: N
    body: N

    def kids(self) -> List[N]:
        return [self.value, self.body]

    def sexp(self) -> str:
        return f"(let {self.name} {self.value.sexp()} {self.body.sexp()})"


@dataclass
class Prog(N):
    defs: List[Def] = field(default_factory=list)
    expr: Optional[N] = None

    def kids(self) -> List[N]:
        ks: List[N] = list(self.defs)
        if self.expr is not None:
            ks.append(self.expr)
        return ks

    def sexp(self) -> str:
        parts = [d.sexp() for d in self.defs]
        if self.expr is not None:
            parts.append(self.expr.sexp())
        return "(prog " + " ".join(parts) + ")"


@dataclass
class ParseOut:
    ast: Optional[N] = None
    fail: Optional[Fail] = None

    @property
    def ok(self) -> bool:
        return self.fail is None and self.ast is not None

    def canon(self) -> str:
        if self.fail:
            return self.fail.canon()
        return self.ast.sexp() if self.ast else "(none)"


# ═════════════════════════════════════════════
# Unparse — the other half of the round trip
# ═════════════════════════════════════════════

def unparse(node: N) -> str:
    """AST back to source, fully parenthesised.

    Fully parenthesised on purpose: the round-trip law tests that the
    parser reads back what the printer wrote, not that the printer
    guesses precedence correctly. Those are two different properties
    and mixing them hides which one broke.
    """
    if isinstance(node, Num):
        return _num(node.value)
    if isinstance(node, Str):
        return '"' + node.value + '"'
    if isinstance(node, Bool):
        return "true" if node.value else "false"
    if isinstance(node, Var):
        return node.name
    if isinstance(node, Bin):
        return f"({unparse(node.left)} {node.op} {unparse(node.right)})"
    if isinstance(node, If):
        return (f"(if {unparse(node.cond)} then {unparse(node.then)} "
                f"else {unparse(node.els)})")
    if isinstance(node, Lst):
        return "[" + ", ".join(unparse(i) for i in node.items) + "]"
    if isinstance(node, Let):
        return (f"(let {node.name} = {unparse(node.value)} "
                f"in {unparse(node.body)})")
    if isinstance(node, Call):
        return f"{node.name}({', '.join(unparse(a) for a in node.args)})"
    if isinstance(node, Def):
        return (f"def {node.name}({', '.join(node.params)}) = "
                f"{unparse(node.body)}")
    if isinstance(node, Prog):
        parts = [unparse(d) for d in node.defs]
        if node.expr is not None:
            parts.append(unparse(node.expr))
        return "\n".join(parts)
    raise TypeError(f"cannot unparse {type(node).__name__}")


# ═════════════════════════════════════════════
# Skeleton — structure with the constants erased
# ═════════════════════════════════════════════

CMP_OPS = {"<", ">", "<=", ">=", "==", "!="}
ARITH_OPS = {"+", "-", "*", "/"}


def skeleton(node: N) -> str:
    """The idea, not the spelling.

    VOWELS.md's consensus oracle counts ideas rather than strings; the
    same collapse is what lets the forge tell a real second witness
    from the same witness in a different hat.
    """
    if isinstance(node, (Num, Str, Bool)):
        return "K"
    if isinstance(node, Var):
        return "V"
    if isinstance(node, Bin):
        op = "CMP" if node.op in CMP_OPS else node.op
        return f"({skeleton(node.left)} {op} {skeleton(node.right)})"
    if isinstance(node, If):
        return (f"if {skeleton(node.cond)} then {skeleton(node.then)} "
                f"else {skeleton(node.els)}")
    if isinstance(node, Lst):
        return f"LIST({', '.join(skeleton(i) for i in node.items)})"
    if isinstance(node, Let):
        return f"let V = {skeleton(node.value)} in {skeleton(node.body)}"
    if isinstance(node, Call):
        return f"CALL({', '.join(skeleton(a) for a in node.args)})"
    if isinstance(node, Def):
        return skeleton(node.body)
    if isinstance(node, Prog):
        return " ; ".join(skeleton(k) for k in node.kids())
    return "?"


__all__ = [
    "KINDS", "DEFECTS", "Tok", "Fail", "LexOut",
    "N", "Num", "Str", "Bool", "Var", "Bin", "If", "Call", "Def", "Prog",
    "Lst", "Let",
    "ParseOut", "unparse", "skeleton", "CMP_OPS", "ARITH_OPS",
]
