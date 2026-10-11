#!/usr/bin/env python3
"""
ever.py — Ever / Tapestry, the interpreter

This is the part that makes Ever a language you write in rather than a
checker you run over other people's code.

Every value in an Ever program is a thread: a name, the thing it holds,
and how much that binding is trusted. The program is the weave. Nothing
executes below the floor, and nothing reaches Certain without earning it.

    anchor total = 500          # pinned; survives translation
    let   rate   = 0.08
    ever  tax    = total * rate # confidence propagates through arithmetic
    ascend tax by 190           # evidence; three aligned points to rise
    show  tax

Codric Enterprise · Ricky (Dreid) · 2026
Theory of Relative E:  E = MC²
"""

from __future__ import annotations

import re
import sys
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Dict, List, Optional, Tuple

# ── constants, identical to 0-atom-c/tapestry.h ──
E_ZERO               = 0
E_CERTAIN            = 256
E_EXECUTE_FLOOR      = 128
E_PI_WIDTH_WARN      = 81
E_PI_WIDTH_ENUMERATE = 25
E_EMULATE_CEILING    = 3
E_ASCEND_POINTS      = 3
E_PHI                = 1.6180339887
E_INTAKE             = 120     # what a literal is worth before evidence


class State(IntEnum):
    Z = 0; CONFIDENT = 1; CERTAIN = 2; EQUIV = 3; EXPRESS = 4
    EMULATING = 5; EVOLVED = 6; ANCHORED = 7; ABSENT = 8; ERROR = 9


class Defect(IntEnum):
    NONE = 0; UNBOUND = 1; MISBOUND = 2; UNBOUNDED = 3
    OVERBOUND = 4; ORPHANED = 5


class Lang(IntEnum):
    C = 0; CPP = 1; PYTHON = 2; RUBY = 3; SQL = 4; JAVA = 5; HTML = 6
    RUST = 7; GO = 8; TS = 9; SWIFT = 10; EVER = 11


DEFECT_NAME = {d: d.name.lower() for d in Defect}


# ═════════════════════════════════════════════
# The thread
# ═════════════════════════════════════════════

@dataclass
class E:
    """A binding: a name, the thing it holds, and how much it is trusted."""
    ident: str = ""
    value: Any = None
    state: State = State.Z
    defect: Defect = Defect.NONE
    confidence: int = 0
    lo: int = 0
    hi: int = 0
    lang: Lang = Lang.EVER
    anchor_id: int = 0
    generation: int = 0
    ascend_points: int = 0
    error_distance: int = 0
    reason: str = ""
    born_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    # ── predicates ──
    @property
    def is_z(self) -> bool:
        return self.state == State.Z

    @property
    def is_cleared(self) -> bool:
        if self.state in (State.Z, State.ERROR, State.ABSENT):
            return False
        return self.confidence > E_ZERO

    @property
    def can_execute(self) -> bool:
        return self.is_cleared and self.confidence >= E_EXECUTE_FLOOR

    @property
    def is_anchored(self) -> bool:
        return self.anchor_id != 0

    @property
    def width(self) -> int:
        return self.hi - self.lo

    def pi_status(self) -> str:
        w = self.width
        if w > E_PI_WIDTH_WARN:      return "APPROACHING_Z"
        if w > E_PI_WIDTH_ENUMERATE: return "ENUMERATE"
        return "ACCEPTABLE"

    def type_name(self) -> str:
        v = self.value
        if v is None:            return "void"
        if isinstance(v, bool):  return "bool"
        if isinstance(v, int):   return "int"
        if isinstance(v, float): return "real"
        if isinstance(v, str):   return "text"
        if isinstance(v, list):  return "list"
        return "foreign"

    def serialize(self) -> str:
        return "|".join(str(x) for x in (
            int(self.state), self.type_name(), int(self.lang),
            int(self.defect), self.confidence, self.lo, self.hi,
            self.error_distance, self.generation, self.ascend_points,
            self.anchor_id, -1, self.born_ms,
            self.ident, self.value, self.reason))

    def __repr__(self) -> str:
        mark = "\u2693" if self.is_anchored else ""
        if self.is_z:
            return f"E<Z>({self.ident} \u2014 {self.reason})"
        return (f"E<{self.state.name}>{mark}({self.ident} = {self.value!r} "
                f"@ {self.confidence}/256)")


# ── constructors ──

def e_z(ident: str, reason: str = "unverified",
        defect: Defect = Defect.UNBOUND) -> E:
    return E(ident=ident, state=State.Z, defect=defect, reason=reason)


def e_val(ident: str, value: Any, conf: int, lang: Lang = Lang.EVER) -> E:
    if conf <= E_ZERO:
        return e_z(ident, "confidence collapsed to zero")
    if conf >= E_CERTAIN:
        return E(ident=ident, value=value, state=State.CERTAIN,
                 confidence=E_CERTAIN, lo=E_CERTAIN, hi=E_CERTAIN, lang=lang)
    return E(ident=ident, value=value, state=State.CONFIDENT,
             confidence=conf, lo=conf, hi=conf, lang=lang)


def e_equiv(ident: str, lo: int, hi: int, lang: Lang = Lang.EVER) -> E:
    if lo > hi:
        lo, hi = hi, lo
    mid = (lo + hi) // 2
    return E(ident=ident, value=mid, state=State.EQUIV,
             confidence=mid, lo=lo, hi=hi, lang=lang)


# ═════════════════════════════════════════════
# The six A-operators
# ═════════════════════════════════════════════

NOTHING_WORDS = {"null", "nil", "None", "NULL", "undefined", "nullptr", "Z"}


def a_any(ident: str, literal: str, from_lang: Lang = Lang.EVER) -> E:
    """ANY — lift any language's literal into a thread."""
    s = (literal or "").strip()
    if not s:
        return e_z(ident, "no literal to lift")

    if s in NOTHING_WORDS:
        return e_z(ident, f"{from_lang.name} expressed nothing",
                   Defect.UNBOUND)

    if s in ("true", "True", "TRUE"):
        return e_val(ident, True, E_INTAKE, from_lang)
    if s in ("false", "False", "FALSE"):
        return e_val(ident, False, E_INTAKE, from_lang)

    if len(s) >= 2 and s[0] in "\"'" :
        if s[-1] == s[0]:
            return e_val(ident, s[1:-1], E_INTAKE, from_lang)
        return e_z(ident, "unterminated string literal", Defect.UNBOUNDED)

    try:
        return e_val(ident, int(s), E_INTAKE, from_lang)
    except ValueError:
        pass
    try:
        return e_val(ident, float(s), E_INTAKE, from_lang)
    except ValueError:
        pass

    p = e_val(ident, s, 100, from_lang)
    p.reason = "lifted as foreign, shape unresolved"
    return p


def a_assimilate(p: E, to: Lang) -> E:
    """ASSIMILATE — carry a thread into another language.

    Z does not cross. Anchored threads cross without loss; unanchored
    ones pay one confidence per crossing so drift stays visible.
    """
    if p.is_z:
        return e_z(p.ident, "Z does not translate", p.defect)
    if p.state == State.ERROR:
        return e_z(p.ident, "misbound thread does not translate",
                   Defect.MISBOUND)
    if p.lang == to:
        return p

    q = E(**{**p.__dict__})
    q.lang = to
    q.born_ms = int(time.time() * 1000)
    if not p.is_anchored:
        q.confidence = max(1, p.confidence - 1)
        q.lo = q.hi = q.confidence
        # Certain means exactly 256. A thread that paid for a crossing
        # is no longer Certain and must say so, or the state and the
        # number would disagree.
        if q.state == State.CERTAIN:
            q.state = State.CONFIDENT
        q.reason = (f"assimilated {p.lang.name} to {to.name}, "
                    f"unanchored, -1 confidence")
    else:
        q.reason = (f"assimilated {p.lang.name} to {to.name}, "
                    f"anchor {p.anchor_id} held")
    return q


_anchor_seq = [1000]


def a_anchor(p: E, anchor_id: Optional[int] = None) -> E:
    """ANCHOR — pin an identity that survives every translation."""
    if not p.is_cleared:
        return e_z(p.ident, "cannot anchor an uncleared binding",
                   p.defect or Defect.UNBOUND)
    if anchor_id is None:
        _anchor_seq[0] += 1
        anchor_id = _anchor_seq[0]
    if anchor_id == 0:
        return e_z(p.ident, "anchor id zero is reserved", Defect.UNBOUND)

    q = E(**{**p.__dict__})
    q.anchor_id = anchor_id
    q.state = State.ANCHORED
    q.reason = f"anchored {anchor_id} at confidence {q.confidence}"
    return q


def excel(a: int, b: int) -> int:
    """Multiplicative uncertainty: u_result = u_a * u_b.

    A product of non-zero ignorances is never zero, so combination
    approaches Certain without attaining it. Capping one short keeps the
    language honest: Certain is earned at runtime, never accumulated.
    """
    if a >= E_CERTAIN and b >= E_CERTAIN:
        return E_CERTAIN
    v = a + b - (a * b // E_CERTAIN)
    return max(E_ZERO, min(E_CERTAIN - 1, v))


def a_ascend(p: E, evidence: E) -> E:
    """ASCEND — the only path upward. Three aligned points to rise."""
    if p.is_z:
        return e_z(p.ident, "Z cannot ascend; it must be resolved", p.defect)
    if not evidence.is_cleared:
        return p

    q = E(**{**p.__dict__})
    gap = abs(evidence.confidence - p.confidence)
    if gap > E_PI_WIDTH_ENUMERATE:
        q.ascend_points = 0
        q.reason = f"evidence disagreed by {gap}, ascent reset"
        return q

    q.ascend_points = p.ascend_points + 1
    if q.ascend_points < E_ASCEND_POINTS:
        q.reason = f"ascending: {q.ascend_points} of {E_ASCEND_POINTS} points"
        return q

    q.confidence = excel(p.confidence, evidence.confidence)
    q.lo = q.hi = q.confidence
    q.ascend_points = 0
    q.generation = p.generation + 1
    q.state = State.CERTAIN if q.confidence >= E_CERTAIN else State.EVOLVED
    q.reason = (f"ascended on {E_ASCEND_POINTS} aligned points to "
                f"{q.confidence}, generation {q.generation}")
    return q


def a_apply2all(threads: List[E], fn) -> Tuple[List[E], int]:
    """APPLY2ALL — broadcast, halting at the first Z."""
    out: List[E] = []
    for i, t in enumerate(threads):
        if t.is_z:
            return out + threads[i:], i
        out.append(fn(t))
    return out, -1


def a_autodidact(history: List[E], about: str) -> E:
    """AUTO-DIDACT — derive a rule from the corpus's own history."""
    if len(history) < E_ASCEND_POINTS:
        return e_z(about, "history too short to derive a rule")

    defects = [h.defect for h in history if not h.is_cleared
               and h.defect != Defect.NONE]
    if defects:
        common = max(set(defects), key=defects.count)
        if defects.count(common) >= E_ASCEND_POINTS:
            r = e_val(about, DEFECT_NAME[common], 180)
            r.reason = (f"derived: {DEFECT_NAME[common]} recurs "
                        f"{defects.count(common)} times")
            return r

    cleared = [h for h in history if h.is_cleared]
    if len(cleared) < E_ASCEND_POINTS:
        return e_z(about, "too few cleared observations to derive")

    confs = [h.confidence for h in cleared]
    mean, spread = sum(confs) // len(confs), max(confs) - min(confs)
    if spread > E_PI_WIDTH_WARN:
        return e_z(about, "history too scattered to derive a rule",
                   Defect.UNBOUNDED)

    rule = e_val(about, mean, 200 if spread <= E_PI_WIDTH_ENUMERATE else 150)
    rule.lo, rule.hi = min(confs), max(confs)
    rule.reason = (f"derived from {len(cleared)} observations, "
                   f"mean {mean}, spread {spread}")
    return rule


# ═════════════════════════════════════════════
# Arithmetic on threads — confidence propagates
# ═════════════════════════════════════════════

def combine(a: E, b: E, op: str, ident: str) -> E:
    """Z-contagion is absolute: any Z operand yields Z.

    Otherwise the result is worth the weaker of its inputs. You cannot
    become more certain by combining things you were less certain about.
    """
    if a.is_z:
        return e_z(ident, f"operand {a.ident} is Z", a.defect)
    if b.is_z:
        return e_z(ident, f"operand {b.ident} is Z", b.defect)

    try:
        if   op == "+": v = a.value + b.value
        elif op == "-": v = a.value - b.value
        elif op == "*": v = a.value * b.value
        elif op == "/":
            if b.value == 0:
                return e_z(ident, "division by zero", Defect.MISBOUND)
            v = a.value / b.value
        else:
            return e_z(ident, f"unknown operator {op}", Defect.MISBOUND)
    except TypeError:
        return e_z(ident,
                   f"cannot {op} {a.type_name()} with {b.type_name()}",
                   Defect.MISBOUND)

    conf = min(a.confidence, b.confidence)
    r = e_val(ident, v, conf)
    r.reason = f"{a.ident} {op} {b.ident}, worth the weaker input"
    return r


# ═════════════════════════════════════════════
# The interpreter
# ═════════════════════════════════════════════

class EverError(Exception):
    pass


class Ever:
    """Executes Ever source. The weave."""

    def __init__(self, trace: bool = False):
        self.threads: Dict[str, E] = {}
        self.archive: List[E] = []
        self.history: Dict[str, List[E]] = {}
        self.output: List[str] = []
        self.trace = trace
        self.blocked = 0

    # ── the loom ──

    def run(self, source: str) -> "Ever":
        for lineno, raw in enumerate(source.split("\n"), start=1):
            line = raw.split("#")[0].strip()
            if not line:
                continue
            try:
                self._exec(line, lineno)
            except EverError as e:
                self.output.append(f"  line {lineno}: {e}")
        return self

    def _record(self, p: E) -> None:
        self.threads[p.ident] = p
        self.history.setdefault(p.ident, []).append(p)
        if not p.is_cleared:
            self.archive.append(p)
        if self.trace:
            print(f"    {p}")

    def _exec(self, line: str, lineno: int) -> None:
        # anchor NAME = EXPR
        m = re.match(r'^anchor\s+(\w+)\s*=\s*(.+)$', line)
        if m:
            p = self._eval(m.group(2), m.group(1))
            self._record(a_anchor(p) if p.is_cleared else p)
            return

        # let / ever NAME = EXPR
        m = re.match(r'^(?:let|ever)\s+(\w+)\s*=\s*(.+)$', line)
        if m:
            self._record(self._eval(m.group(2), m.group(1)))
            return

        # z NAME "reason"
        m = re.match(r'^z\s+(\w+)\s*(?:"(.*)")?$', line)
        if m:
            self._record(e_z(m.group(1), m.group(2) or "declared unknown"))
            return

        # equiv NAME = LO..HI
        m = re.match(r'^equiv\s+(\w+)\s*=\s*(-?\d+)\s*\.\.\s*(-?\d+)$', line)
        if m:
            self._record(e_equiv(m.group(1), int(m.group(2)), int(m.group(3))))
            return

        # ascend NAME by N
        m = re.match(r'^ascend\s+(\w+)\s+by\s+(-?\d+)$', line)
        if m:
            name = m.group(1)
            p = self.threads.get(name)
            if p is None:
                raise EverError(f"{name} was never bound")
            ev = e_val(f"{name}_evidence", p.value, int(m.group(2)))
            self._record(a_ascend(p, ev))
            return

        # assimilate NAME to LANG
        m = re.match(r'^assimilate\s+(\w+)\s+to\s+(\w+)$', line)
        if m:
            name, lang = m.group(1), m.group(2).upper()
            p = self.threads.get(name)
            if p is None:
                raise EverError(f"{name} was never bound")
            if lang not in Lang.__members__:
                raise EverError(f"unknown language {lang}")
            self._record(a_assimilate(p, Lang[lang]))
            return

        # expect NAME >= N
        m = re.match(r'^expect\s+(\w+)\s*>=\s*(\d+)$', line)
        if m:
            name, floor = m.group(1), int(m.group(2))
            p = self.threads.get(name, e_z(m.group(1), "never bound"))
            if p.confidence < floor:
                self.blocked += 1
                blocked = e_z(name,
                              f"expected >= {floor}, had {p.confidence}")
                self._record(blocked)
                self.output.append(
                    f"  BLOCKED {name}: expected >= {floor}, "
                    f"had {p.confidence}")
            return

        # learn NAME
        m = re.match(r'^learn\s+(\w+)$', line)
        if m:
            name = m.group(1)
            rule = a_autodidact(self.history.get(name, []), f"{name}_rule")
            self._record(rule)
            self.output.append(f"  LEARNED {rule}")
            return

        # show NAME
        m = re.match(r'^show\s+(\w+)$', line)
        if m:
            name = m.group(1)
            p = self.threads.get(name)
            if p is None:
                self.output.append(f"  {name} was never bound")
            elif p.is_z:
                self.output.append(f"  {name} = Z  ({p.reason})")
            elif not p.can_execute:
                self.blocked += 1
                self.output.append(
                    f"  {name} withheld: {p.confidence}/256 is below the "
                    f"execute floor of {E_EXECUTE_FLOOR}")
            else:
                mark = " \u2693" if p.is_anchored else ""
                self.output.append(
                    f"  {name} = {p.value!r}  [{p.confidence}/256 "
                    f"{p.state.name}{mark}]")
            return

        raise EverError(f"cannot parse: {line}")

    # ── expressions ──

    def _eval(self, expr: str, ident: str) -> E:
        expr = expr.strip()
        m = re.match(r'^(.+?)\s*([-+*/])\s*(.+)$', expr)
        if m and not (expr[0] in "\"'"):
            a = self._atom(m.group(1).strip(), f"{ident}_l")
            b = self._atom(m.group(3).strip(), f"{ident}_r")
            return combine(a, b, m.group(2), ident)
        return self._atom(expr, ident)

    def _atom(self, tok: str, ident: str) -> E:
        # PROGRAM CONSTANTS are Certain about their value. A literal in
        # Ever source carries no uncertainty about what it is; the author
        # wrote it. Uncertainty belongs to data from outside and to
        # whether functions are correct.
        if re.fullmatch(r'-?\d+', tok):
            return e_val(ident, int(tok), E_CERTAIN)
        if re.fullmatch(r'-?\d*\.\d+', tok):
            return e_val(ident, float(tok), E_CERTAIN)
        if len(tok) >= 2 and tok[0] in "\"'" and tok[-1] == tok[0]:
            return e_val(ident, tok[1:-1], E_CERTAIN)
        if tok in ("true", "false"):
            return e_val(ident, tok == "true", E_CERTAIN)

        if tok in self.threads:
            src = self.threads[tok]
            q = E(**{**src.__dict__})
            # keep the source name so failures name the binding the author
            # wrote, not an internal temporary
            # a reference never inherits an anchor; the anchor belongs to
            # the binding that earned it
            q.anchor_id = 0
            if src.state == State.ANCHORED:
                q.state = State.CONFIDENT
            return q
        return a_any(ident, tok)

    # ── reporting ──

    def report(self) -> str:
        out = ["", "  weave", "  " + "\u2500" * 54]
        for name, p in self.threads.items():
            if name.endswith(("_l", "_r", "_evidence")):
                continue
            out.append(f"    {p}")
        out.append("")
        out.append(f"  threads {len(self.threads)}   "
                   f"archived {len(self.archive)}   blocked {self.blocked}")
        return "\n".join(out)


# ═════════════════════════════════════════════
# CLI
# ═════════════════════════════════════════════

DEMO = '''
# Ever — a language where every value carries how much it is trusted

anchor total = 500              # pinned; survives translation intact
let    rate  = 0.08
ever   tax   = total * rate     # confidence flows to the weaker input
show   tax                      # withheld: intake alone is below the floor

ascend tax by 125               # evidence, point 1
ascend tax by 130               # point 2
ascend tax by 128               # point 3 - now it rises
show   tax

z      ocr_text "OCR has not run"
ever   parsed = ocr_text + 1    # Z is contagious
show   parsed

ascend total by 130             # aligned evidence, within the pi-squared band
ascend total by 135
ascend total by 132
show   total
assimilate total to RUST        # anchored, so the crossing costs nothing
assimilate total to SWIFT
assimilate total to GO
show   total

equiv  severity = 100..115
show   severity

expect tax >= 200
learn  tax
'''

if __name__ == "__main__":
    if len(sys.argv) > 1:
        src = open(sys.argv[1]).read()
        title = sys.argv[1]
    else:
        src, title = DEMO, "demo"

    print(f"\n\u2550\u2550\u2550 Ever \u00b7 {title} \u2550\u2550\u2550")
    ev = Ever().run(src)
    for line in ev.output:
        print(line)
    print(ev.report())
    print()
