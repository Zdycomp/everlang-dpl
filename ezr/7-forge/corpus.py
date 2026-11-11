#!/usr/bin/env python3
"""
corpus.py — what the language is required to do, and the machinery for
finding out what nobody wrote down.

Three sources of cases, in descending order of authority:

  GOLDEN    taken from SEMANTICS.md and PIPELINE.md. These are claims
            the project already published, so an implementation that
            fails one of them is wrong even if all four agree.

  PROBES    aimed at a named open question. A probe does not assert an
            answer; it exists so the forge can watch the witnesses
            answer and see whether they agree.

  FUZZ      generated. Grammar-directed programs must be accepted and
            must parse identically; mutated and random token soup must
            be accepted or refused identically. Disagreement anywhere
            is a counterexample, and by VOWELS.md's rule a
            counterexample becomes a case the next generation carries.

Codric Enterprise · Ricky (Dreid) · 2026
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import List, Optional

from spec import SPEC

ACCEPT = "accept"
REFUSE_LEX = "refuse-lex"
REFUSE_PARSE = "refuse-parse"


@dataclass
class Case:
    """One source text and what is required of it.

    `sexp` is asserted only when a published document fixes the tree.
    Where it is None the case still carries weight: every pair must
    agree with every other, they are just not told in advance what to
    agree on.
    """
    cid: str
    src: str
    outcome: Optional[str] = None
    sexp: Optional[str] = None
    note: str = ""
    origin: str = "golden"
    question: Optional[str] = None

    def __repr__(self) -> str:
        return f"<{self.cid} {self.src[:34]!r}>"


# ═════════════════════════════════════════════
# GOLDEN — published claims
# ═════════════════════════════════════════════

def _g(cid, src, outcome=None, sexp=None, note=""):
    return Case(cid, src, outcome, sexp, note, "golden")


GOLDEN: List[Case] = [
    # ── PIPELINE.md, "Every stage returns E<T>" ──
    _g("pipe-lex-reject", "a $ b", REFUSE_LEX,
       note="PIPELINE.md: stage 'lex', Z(misbound)"),
    _g("pipe-parse-reject", "1 +", REFUSE_PARSE,
       note="PIPELINE.md: stage 'parse', Z(unbounded)"),
    _g("pipe-ready", "1 + 1", ACCEPT, "(prog (+ 1 1))",
       note="PIPELINE.md: stage 'ready'"),

    # ── SEMANTICS.md 8, the worked example ──
    _g("sem-fact", "def fact(n) = if n <= 1 then 1 else n * fact(n - 1)",
       ACCEPT,
       "(prog (def fact (n) (if (<= n 1) 1 (* n (call fact (- n 1))))))",
       note="SEMANTICS.md 8"),

    # ── PIPELINE.md, "The AST measures structure" ──
    _g("ast-size-var", "n", ACCEPT, "(prog n)", note="1 node"),
    _g("ast-size-mul", "n * 1", ACCEPT, "(prog (* n 1))", note="3 nodes"),
    _g("ast-size-paren", "((n))", ACCEPT, "(prog n)",
       note="redundant parens vanish"),

    # ── PIPELINE.md, the stated grammar: associativity ──
    _g("assoc-sub", "1 - 2 - 3", ACCEPT, "(prog (- (- 1 2) 3))",
       note="additive is left-associative"),
    _g("assoc-div", "8 / 4 / 2", ACCEPT, "(prog (/ (/ 8 4) 2))",
       note="multiply is left-associative"),
    _g("assoc-add-chain", "1 + 2 + 3 + 4", ACCEPT,
       "(prog (+ (+ (+ 1 2) 3) 4))"),

    # ── precedence ──
    _g("prec-add-mul", "1 + 2 * 3", ACCEPT, "(prog (+ 1 (* 2 3)))"),
    _g("prec-mul-add", "1 * 2 + 3", ACCEPT, "(prog (+ (* 1 2) 3))"),
    _g("prec-cmp-lowest", "1 + 2 < 3 + 4", ACCEPT,
       "(prog (< (+ 1 2) (+ 3 4)))",
       note="PIPELINE.md: comparison lowest"),
    _g("prec-paren", "(1 + 2) * 3", ACCEPT, "(prog (* (+ 1 2) 3))"),
    _g("prec-div-sub", "10 - 6 / 3", ACCEPT, "(prog (- 10 (/ 6 3)))"),

    # ── unary minus ──
    _g("unary-mul", "-2 * 3", ACCEPT, "(prog (* (- 0 2) 3))",
       note="prefix minus binds tighter than '*'"),
    _g("unary-double", "- -2", ACCEPT, "(prog (- 0 (- 0 2)))"),
    _g("unary-after-op", "1 - -2", ACCEPT, "(prog (- 1 (- 0 2)))"),
    _g("unary-call", "-f(3)", ACCEPT, "(prog (- 0 (call f 3)))"),

    # ── atoms ──
    _g("atom-true", "true", ACCEPT, "(prog true)"),
    _g("atom-false", "false", ACCEPT, "(prog false)"),
    _g("atom-str", '"hi"', ACCEPT, "(prog (str 'hi'))"),
    _g("atom-real", "1.5", ACCEPT, "(prog 1.5)"),
    _g("atom-int-float", "2.0", ACCEPT, "(prog 2)",
       note="an integral real prints as an integer"),
    _g("atom-comment", "# note\n1", ACCEPT, "(prog 1)"),
    _g("atom-underscore", "_x", ACCEPT, "(prog _x)"),

    # ── calls ──
    _g("call-nullary", "f()", ACCEPT, "(prog (call f))"),
    _g("call-unary", "f(1)", ACCEPT, "(prog (call f 1))"),
    _g("call-binary", "f(1, 2)", ACCEPT, "(prog (call f 1 2))"),
    _g("call-nested", "f(g(1))", ACCEPT, "(prog (call f (call g 1)))"),
    _g("call-expr-arg", "f(1 + 2)", ACCEPT, "(prog (call f (+ 1 2)))"),

    # ── lists ──
    _g("list-empty", "[]", ACCEPT, "(prog (list))"),
    _g("list-three", "[1, 2, 3]", ACCEPT, "(prog (list 1 2 3))"),
    _g("list-nested", "[1, [2, 3]]", ACCEPT, "(prog (list 1 (list 2 3)))"),
    _g("list-exprs", "[1 + 1, n * 2]", ACCEPT,
       "(prog (list (+ 1 1) (* n 2)))"),
    _g("list-as-arg", "f([1, 2])", ACCEPT, "(prog (call f (list 1 2)))"),
    _g("list-unclosed", "[1, 2", REFUSE_PARSE),
    _g("list-trailing-comma", "[1,]", REFUSE_PARSE,
       note="the trailing-comma ruling covers brackets too"),
    _g("list-bare-open", "[", REFUSE_PARSE),

    # ── let ──
    _g("let-simple", "let x = 5 in x + 1", ACCEPT,
       "(prog (let x 5 (+ x 1)))"),
    _g("let-nested", "let x = 1 in let y = 2 in x + y", ACCEPT,
       "(prog (let x 1 (let y 2 (+ x y))))"),
    _g("let-in-def", "def f(n) = let d = n * 2 in d + 1", ACCEPT,
       "(prog (def f (n) (let d (* n 2) (+ d 1))))"),
    _g("let-list-value", "let a = [1, 2] in a", ACCEPT,
       "(prog (let a (list 1 2) a))"),
    _g("let-not-operand", "1 + let x = 2 in x", REFUSE_PARSE,
       note="let is an alternative of expr, not a member of atom -- "
            "the same placement the conditional has, for the same "
            "reason"),
    _g("let-no-in", "let x = 5 then x", REFUSE_PARSE),
    _g("let-no-value", "let x = in x", REFUSE_PARSE),

    # ── conditionals ──
    _g("if-simple", "if true then 1 else 2", ACCEPT,
       "(prog (if true 1 2))"),
    _g("if-nested-else", "if a then 1 else if b then 2 else 3", ACCEPT,
       "(prog (if a 1 (if b 2 3)))"),
    _g("if-else-extends", "if a then 1 else 2 != 3", ACCEPT,
       "(prog (if a 1 (!= 2 3)))",
       note="the else branch is a whole expr, so it swallows the "
            "comparison"),
    _g("if-else-arith", "if a then 1 else 2 + 3", ACCEPT,
       "(prog (if a 1 (+ 2 3)))"),
    _g("if-parenthesised", "(if a then 1 else 2) != 3", ACCEPT,
       "(prog (!= (if a 1 2) 3))",
       note="parentheses make a conditional an atom; nothing else "
            "does"),
    _g("if-not-operand", "1 + if a then 2 else 3", REFUSE_PARSE,
       note="PIPELINE.md: expr := ifexpr | compare. ifexpr is an "
            "alternative of expr, not a member of atom, so a "
            "conditional is never an operand."),
    _g("if-not-negatable", "-if a then 1 else 2", REFUSE_PARSE),
    _g("if-not-left-operand", "if a then 1 else 2 * 3 < 4", ACCEPT,
       "(prog (if a 1 (< (* 2 3) 4)))"),

    # ── definitions ──
    _g("def-nullary", "def z() = 0", ACCEPT, "(prog (def z () 0))"),
    _g("def-binary", "def add(a, b) = a + b", ACCEPT,
       "(prog (def add (a b) (+ a b)))"),

    # ── refusals the grammar requires ──
    _g("bad-trailing-op", "1 *", REFUSE_PARSE),
    _g("bad-leading-op", "* 1", REFUSE_PARSE),
    _g("bad-empty-paren", "()", REFUSE_PARSE),
    _g("bad-unclosed-paren", "(1", REFUSE_PARSE),
    _g("bad-unclosed-call", "f(1", REFUSE_PARSE),
    _g("bad-if-no-else", "if a then 1", REFUSE_PARSE),
    _g("bad-if-no-then", "if a else 1", REFUSE_PARSE),
    _g("bad-def-no-name", "def = 1", REFUSE_PARSE),
    _g("bad-def-no-body", "def f(n) =", REFUSE_PARSE),
    _g("bad-def-no-eq", "def f(n) n", REFUSE_PARSE),
    _g("bad-two-exprs", "1 2", REFUSE_PARSE),
    _g("bad-tail-after-def", "def f(n) = n garbage", REFUSE_PARSE,
       note="found by the forge: the incumbent's program() returned "
            "from the definition branch without checking for EOF, so "
            "everything after a definition was discarded and "
            "compile_ezr still reported 'ready'."),
    _g("bad-tail-parens", "def f(n) = n ) ) )", REFUSE_PARSE),
    _g("bad-tail-numbers", "def f(n) = n 1 2 3", REFUSE_PARSE),
    _g("bad-comma-loose", "1, 2", REFUSE_PARSE),
    _g("bad-empty", "", REFUSE_PARSE),
    _g("bad-only-comment", "# nothing", REFUSE_PARSE),
    _g("bad-lex-at", "a @ b", REFUSE_LEX),
    _g("bad-lex-dollar", "$", REFUSE_LEX),
    _g("bad-lex-unterminated", '"oops', REFUSE_LEX),
    _g("bad-lex-bang", "1 ! 2", REFUSE_LEX),
    _g("bad-lex-marker", "1 =$= 2", REFUSE_LEX,
       note="found by the forge at generation 7. The trie scanner used "
            "'$' as its end-of-token marker, and '$' is a character a "
            "source text may contain, so the walk stepped into the "
            "marker and the next character indexed a tuple. G1 says the "
            "front end refuses; it does not raise."),
    _g("bad-lex-marker-2", "a $ = b", REFUSE_LEX),
    _g("bad-lex-marker-3", "$$$", REFUSE_LEX),
]


# ═════════════════════════════════════════════
# PROBES — aimed at a named open question
# ═════════════════════════════════════════════

PROBES: List[Case] = [
    Case("q-cmp-lt", "1 < 2", None, None,
         "which kind carries a bare '<'", "probe", "cmp_kind"),
    Case("q-cmp-gt", "a > b", None, None,
         "which kind carries a bare '>'", "probe", "cmp_kind"),
    Case("q-cmp-le", "1 <= 2", None, None,
         "the two-character form, for contrast", "probe", "cmp_kind"),

    Case("q-unterm", '"no close', None, None,
         "defect for a string with no closing quote", "probe",
         "unterminated_string_defect"),
    Case("q-unterm-mid", 'f("x', None, None,
         "unterminated string after other tokens", "probe",
         "unterminated_string_defect"),

    Case("q-reserved-to", "def area(to) = to * 2", None, None,
         "'to' is reserved but unreachable in the grammar", "probe",
         "reserved_words"),
    Case("q-reserved-by", "def scale(by) = by + 1", None, None,
         "'by' is reserved but unreachable", "probe", "reserved_words"),
    Case("q-reserved-show", "def show(n) = n", None, None,
         "'show' is reserved but unreachable", "probe", "reserved_words"),
    Case("q-reserved-learn", "learn", None, None,
         "a bare reserved word that no rule can consume", "probe",
         "reserved_words"),

    Case("q-multi-def", "def f(n) = n\ndef g(n) = n + 1", None, None,
         "two definitions in one text", "probe", "multi_definition"),
    Case("q-multi-def-expr", "def d(n) = n * 2\nd(21)", None, None,
         "definitions followed by an expression", "probe",
         "multi_definition"),

    Case("q-chain-cmp", "1 < 2 < 3", None, None,
         "chained comparison", "probe", "chained_comparison"),

    Case("q-trail-arg", "f(1,)", None, None,
         "trailing comma in an argument list", "probe", "trailing_comma"),
    Case("q-trail-param", "def f(a,) = a", None, None,
         "trailing comma in a parameter list", "probe", "trailing_comma"),
]


# ═════════════════════════════════════════════
# FUZZ — generation
# ═════════════════════════════════════════════

_NAMES = ["n", "x", "y", "acc", "k", "m", "total", "_t", "step"]
_FNS = ["f", "g", "h", "fact", "tri", "step"]
_ADD = ["+", "-"]
_MUL = ["*", "/"]
_CMP = ["<", ">", "<=", ">=", "==", "!="]


class Fuzzer:
    """Grammar-directed generation, plus two kinds of damage.

    Well-formed programs test that the pairs build the *same tree*.
    Damaged ones test that they *refuse together* — which is the harder
    property, and the one that actually decides whether the language
    has an edge or just a habit.
    """

    def __init__(self, seed: int = 0):
        self.r = random.Random(seed)

    # ── well formed ──
    def atom(self, depth: int, bound: List[str]) -> str:
        r = self.r
        pick = r.random()
        if depth <= 0 or pick < 0.34:
            if bound and pick < 0.18:
                return r.choice(bound)
            if pick < 0.26:
                return str(r.randint(0, 99))
            if pick < 0.30:
                return f"{r.randint(0, 9)}.{r.randint(1, 9)}"
            return r.choice(["true", "false", str(r.randint(0, 99))])
        if pick < 0.44:
            return f"({self.expr(depth - 1, bound)})"
        if pick < 0.54:
            k = r.randint(0, 2)
            args = ", ".join(self.expr(depth - 1, bound) for _ in range(k))
            return f"{r.choice(_FNS)}({args})"
        if pick < 0.60:
            return f"-{self.atom(depth - 1, bound)}"
        if pick < 0.66:
            k = r.randint(0, 3)
            inner = ", ".join(self.expr(depth - 1, bound) for _ in range(k))
            return f"[{inner}]"
        return self.arith(depth - 1, bound)

    def arith(self, depth: int, bound: List[str]) -> str:
        r = self.r
        if depth <= 0:
            return self.atom(0, bound)
        op = r.choice(_ADD + _MUL)
        return f"{self.atom(depth - 1, bound)} {op} {self.atom(depth - 1, bound)}"

    def expr(self, depth: int, bound: List[str]) -> str:
        r = self.r
        p = r.random()
        if depth > 0 and p < 0.10:
            name = r.choice(_NAMES)
            return (f"let {name} = {self.expr(depth - 1, bound)} "
                    f"in {self.expr(depth - 1, bound + [name])}")
        if depth > 0 and p < 0.24:
            return (f"if {self.compare(depth - 1, bound)} "
                    f"then {self.expr(depth - 1, bound)} "
                    f"else {self.expr(depth - 1, bound)}")
        if p < 0.34:
            return self.compare(depth, bound)
        return self.arith(depth, bound)

    def compare(self, depth: int, bound: List[str]) -> str:
        return (f"{self.arith(depth, bound)} {self.r.choice(_CMP)} "
                f"{self.arith(depth, bound)}")

    def program(self, depth: int = 3) -> str:
        r = self.r
        if r.random() < 0.45:
            params = r.sample(_NAMES, r.randint(0, 2))
            name = r.choice(_FNS)
            body = self.expr(depth, params)
            one = f"def {name}({', '.join(params)}) = {body}"
            if bool(SPEC.get("multi_definition", False)) and r.random() < 0.4:
                p2 = r.sample(_NAMES, r.randint(0, 2))
                n2 = r.choice(_FNS)
                two = f"def {n2}({', '.join(p2)}) = {self.expr(depth, p2)}"
                tail = ""
                if bool(SPEC.get("trailing_expression", False)) \
                        and r.random() < 0.5:
                    tail = f"\n{self.expr(depth, [])}"
                return f"{one}\n{two}{tail}"
            return one
        return self.expr(depth, [])

    # ── damaged ──
    _POISON = list("$@?&`~\;:{}|^%'") + ["!!", "1x", '"', "..", "==",
                                        "[", "]", "let", "in"]

    def mutate(self, src: str) -> str:
        r = self.r
        if not src:
            return r.choice(self._POISON)
        kind = r.randrange(6)
        i = r.randrange(len(src))
        if kind == 0:
            return src[:i] + src[i + 1:]
        if kind == 1:
            return src[:i] + r.choice(self._POISON) + src[i:]
        if kind == 2:
            return src[:i] + r.choice(["(", ")", ",", "=", "*", "-"]) + src[i:]
        if kind == 3:
            j = r.randrange(len(src))
            i, j = min(i, j), max(i, j)
            return src[:i] + src[j:]
        if kind == 4:
            return src[:i] + r.choice(["if", "then", "else", "def",
                                       "true", "let", "anchor"]) + src[i:]
        return src[i:] + src[:i]

    _SOUP = (["def", "if", "then", "else", "true", "false", "let", "in"]
             + ["(", ")", "[", "]", ",", "=", "+", "-", "*", "/", "<", ">",
                "<=", ">=", "==", "!="]
             + ["n", "x", "f", "0", "1", "42", "1.5", '"s"', "#c\n"])

    def soup(self, k: int = 8) -> str:
        return " ".join(self.r.choice(self._SOUP)
                        for _ in range(self.r.randint(1, k)))

    # ── the stream the forge consumes ──
    def batch(self, n: int, max_depth: int = 5) -> List[Case]:
        """`max_depth` is the ceiling on generated program nesting.

        The convergence run held it at 5 throughout. Exploration cycles
        vary it, because depth is the one knob that changes the *shape*
        of what gets generated rather than just how much: a depth-7
        program nests conditionals and precedence chains that a depth-3
        program cannot express, so raising it reaches grammar the
        earlier search never had a way to reach.
        """
        out: List[Case] = []
        for i in range(n):
            roll = self.r.random()
            depth = self.r.randint(1, max(1, max_depth))
            if roll < 0.45:
                src, tag = self.program(depth), "wellformed"
            elif roll < 0.80:
                src, tag = self.mutate(self.program(depth)), "mutated"
            else:
                src, tag = self.soup(), "soup"
            out.append(Case(f"fz-{tag}-{i}", src, None, None, tag, "fuzz"))
        return out


def all_cases() -> List[Case]:
    return list(GOLDEN) + list(PROBES)


__all__ = ["Case", "GOLDEN", "PROBES", "Fuzzer", "all_cases",
           "ACCEPT", "REFUSE_LEX", "REFUSE_PARSE"]
