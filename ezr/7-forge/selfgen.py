#!/usr/bin/env python3
"""
selfgen.py — the language writes its own parser.

`grammar_doc.py` already emits the grammar *from* the parser, so the
document cannot drift from the code. This closes the other half of that
circle: it emits a working parser *from* the grammar, so the code
cannot drift from the document either.

The output is Python source on disk — not a table walked at runtime, an
actual file you can open and read. It is then loaded and registered as
a fifth parser, and from that point it is judged exactly like the four
hand-written ones: same corpus, same laws, same fuzz.

That is the whole value. A generated parser that agrees with four
independently hand-written parsers over half a million programs is
evidence that the stated grammar really does describe what the
implementations do. A generated parser that disagrees is a finding —
and it is a sharper finding than any of the others the forge can make,
because exactly one of two things must be wrong: the grammar is not
what the parsers implement, or a parser is not what the grammar says.

## What is generated, and what is not

Generated: the control flow. Which alternative to attempt, in what
order, where to backtrack, how to turn left recursion into a loop that
still builds a left-associated tree.

Not generated: the tree constructors. Those are the actions already
attached to the rules, called here by rule index, so the generated
parser builds the same shape as the chart parser by construction.
Independence in SEMANTICS.md 2.2 is independence of *derivation*, and
the derivation at issue is the parsing strategy, not the choice of
which dataclass to instantiate.

## The bound, stated

The emitter handles direct left recursion and ordered alternatives with
local backtracking. It does not handle indirect left recursion, and it
does not compute FOLLOW sets — it orders alternatives longest-first and
backtracks, which is a PEG discipline rather than an LL one. For this
grammar those coincide, and the forge is what establishes that they
coincide rather than an argument here.

Codric Enterprise
"""

from __future__ import annotations

import os
from typing import Dict, List, Sequence, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "generated")
OUT_PATH = os.path.join(OUT_DIR, "parser_gen.py")

Rule = Tuple[str, Tuple[str, ...], object]


# ═════════════════════════════════════════════
# Grammar analysis
# ═════════════════════════════════════════════

def nonterminals(rules: Sequence[Rule]) -> set:
    return {lhs for lhs, _, _ in rules}


def split_left_recursion(lhs: str, indexed: List[Tuple[int, Tuple[str, ...]]]
                         ) -> Tuple[List, List]:
    """A -> A alpha  from  A -> beta.

    The first group becomes a loop, the second the thing the loop
    starts from. This is what keeps `1 - 2 - 3` left-associated: the
    tree is rebuilt on each turn of the loop with the accumulated node
    on the left, which is the same shape the left-recursive rule states.
    """
    rec, base = [], []
    for idx, rhs in indexed:
        if rhs and rhs[0] == lhs:
            rec.append((idx, rhs[1:]))
        else:
            base.append((idx, rhs))
    return rec, base


def order_alternatives(alts: List[Tuple[int, Tuple[str, ...]]]
                       ) -> List[Tuple[int, Tuple[str, ...]]]:
    """Longest first, original order preserved among equals.

    Longest-first is what makes `f(1)` parse as a call rather than as
    the name `f` followed by junk: the longer alternative is attempted
    while the shorter one would also have succeeded, and the shorter one
    is only reached if the longer genuinely fails.
    """
    return sorted(alts, key=lambda p: (-len(p[1]), alts.index(p)))


# ═════════════════════════════════════════════
# Emitter
# ═════════════════════════════════════════════

PRELUDE = '''"""
parser_gen.py — GENERATED. Do not edit.

Emitted by selfgen.py from the ratified grammar. To change what this
file does, change the grammar and re-emit; an edit here is overwritten
the next time anything regenerates it, and worse, it would be a parser
that no longer matches the document it claims to implement.

Every function below corresponds to one nonterminal. Left recursion has
been turned into a loop that rebuilds the tree on each turn, which is
how left associativity survives the transformation.
"""

from contract import Fail, ParseOut
from parsers import GRAMMAR as _RULES, _matches, _sync_grammar


class _Fail(Exception):
    """Local control flow. Never escapes parse()."""
    __slots__ = ()


class _State:
    __slots__ = ("t", "i", "high")

    def __init__(self, toks):
        self.t = [x for x in toks if x.kind != "EOF"]
        self.i = 0
        self.high = 0          # furthest token reached, for diagnostics

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else None

    def want(self, sym):
        tok = self.peek()
        if tok is None or not _matches(sym, tok):
            raise _Fail()
        self.i += 1
        if self.i > self.high:
            self.high = self.i
        return tok

    def at_end(self):
        return self.i >= len(self.t)


def _act(idx, kids):
    return _RULES[idx][2](kids)

'''

FOOTER = '''

def parse(toks) -> ParseOut:
    """Entry point. Signature matches every hand-written parser."""
    _sync_grammar()
    st = _State(toks)
    try:
        node = _p_{start}(st)
    except _Fail:
        node = None
    if node is None or not st.at_end():
        # Report the furthest point the grammar reached, which is a more
        # useful place than wherever the last alternative happened to die.
        bad = st.t[min(st.high, len(st.t) - 1)] if st.t else None
        return ParseOut(fail=Fail("parse", "unbounded",
                                  bad.pos if bad else 0,
                                  bad.line if bad else 1))
    return ParseOut(ast=node)
'''


def _call(sym: str, var: str) -> str:
    """One symbol: a nonterminal call, or a terminal match."""
    if sym.startswith("%") or sym.startswith("'"):
        return f"{var} = st.want({sym!r})"
    return f"{var} = _p_{sym}(st)"


def _emit_body(rhs, idx, indent, prefix):
    """Parse a run of symbols, then run the rule's own action over them."""
    lines, names = [], list(prefix)
    for k, sym in enumerate(rhs):
        var = f"_x{k}"
        names.append(var)
        lines.append(indent + _call(sym, var))
    lines.append(f"{indent}return _act({idx}, [{', '.join(names)}])")
    return lines


def emit(rules, start: str = "S") -> str:
    by_lhs = {}
    for idx, (lhs, rhs, _) in enumerate(rules):
        by_lhs.setdefault(lhs, []).append((idx, rhs))

    out = [PRELUDE]

    for lhs in sorted(by_lhs):
        rec, base = split_left_recursion(lhs, by_lhs[lhs])
        base = order_alternatives(base)
        rec = order_alternatives(rec)

        # one helper per alternative, so the chooser stays readable
        for n, (idx, rhs) in enumerate(base):
            out.append(f"\ndef _alt_{lhs}_{n}(st):")
            out.append(f"    # {lhs} -> {' '.join(rhs) or '<empty>'}")
            out.extend(_emit_body(rhs, idx, "    ", []))

        for n, (idx, alpha) in enumerate(rec):
            out.append(f"\ndef _rec_{lhs}_{n}(st, node):")
            out.append(f"    # {lhs} -> {lhs} {' '.join(alpha)}")
            out.extend(_emit_body(alpha, idx, "    ", ["node"]))

        out.append(f"\ndef _p_{lhs}(st):")
        if not base:
            out.append("    raise _Fail()   # no base case: unreachable")
            continue

        alt_names = ", ".join(f"_alt_{lhs}_{n}" for n in range(len(base)))
        if len(base) == 1:
            out.append(f"    node = _alt_{lhs}_0(st)")
        else:
            out.append(f"    for _alt in ({alt_names},):")
            out.append("        _m = st.i")
            out.append("        try:")
            out.append("            node = _alt(st)")
            out.append("            break")
            out.append("        except _Fail:")
            out.append("            st.i = _m")
            out.append("    else:")
            out.append("        raise _Fail()")

        if rec:
            rec_names = ", ".join(f"_rec_{lhs}_{n}" for n in range(len(rec)))
            out.append("    while True:")
            out.append(f"        for _step in ({rec_names},):")
            out.append("            _m = st.i")
            out.append("            try:")
            out.append("                node = _step(st, node)")
            out.append("                break")
            out.append("            except _Fail:")
            out.append("                st.i = _m")
            out.append("        else:")
            out.append("            break")

        out.append("    return node")

    out.append(FOOTER.replace("{start}", start))
    return "\n".join(out) + "\n"


def generate(rules=None, start: str = "S", path: str = OUT_PATH) -> str:
    if rules is None:
        import parsers
        parsers._sync_grammar()
        rules = parsers.GRAMMAR
    os.makedirs(os.path.dirname(path), exist_ok=True)
    src = emit(rules, start)
    with open(path, "w") as fh:
        fh.write(src)
    return path


def load():
    """Generate, import, and hand back the parse function."""
    import importlib
    import sys
    generate()
    if OUT_DIR not in sys.path:
        sys.path.insert(0, OUT_DIR)
    mod = importlib.import_module("parser_gen")
    importlib.reload(mod)
    return mod.parse


if __name__ == "__main__":
    p = generate()
    with open(p) as fh:
        n = sum(1 for _ in fh)
    print(f"emitted {p}  ({n} lines)")
