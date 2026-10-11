#!/usr/bin/env python3
"""
lambda.py — Ever / Tapestry, the abstraction layer

This is what turns Ever from a trust calculus into a language you write
in: functions, conditionals, and recursion, with confidence semantics
defined for each.

Six decisions, made deliberately and implemented here:

  1. FUNCTIONS ARE ANCHORABLE THREADS.
     A function is a thread whose value is a closure. It earns confidence
     through Example, and once cleared it can be anchored. An anchored
     function survives translation.

  2. APPLICATION CHAINS BY MIN.
        conf(f(x)) = min(conf(f), conf(x1), ... conf(xn))
     This is the possibilistic rule: a result is no more trusted than its
     weakest input. It answers "what is the floor?" It is deliberately
     NOT the probabilistic rule (multiplication), which answers a
     different question. See CORROBORATION below.

  3. CORROBORATION MULTIPLIES UNCERTAINTY.
        u(a & b) = u(a) * u(b)
     Two independent witnesses agreeing. Confidence rises. This answers
     "what does the combined evidence support?"

     Two operators from two formalisms, kept apart on purpose. Mixing
     them silently would be the error; using each for its own question
     is not.

  4. A Z CONDITION SPANS BOTH BRANCHES.
     `if c then a else b` with c unknown does not collapse to Z. It
     yields an Equivalence covering both outcomes, and pi judges the
     width. If the branches are too far apart the range exceeds the pi
     threshold and it becomes Z on its own, without a special rule.

  5. RECURSION DEPTH IS EARNED.
     Unverified recursion stops at floor(pi) = 3. An anchored function
     recurses without a depth bound -- but anchoring a recursive function
     requires a DECREASING MEASURE, because confidence proves trust and
     not termination. Without the measure, the ceiling stays at 3.

  6. EVER IS PURE. LEXICAL SCOPE.
     No mutation. The archive's audit trail depends on every thread
     being a value that was derived, never overwritten.

Codric Enterprise · Ricky (Dreid) · 2026
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ever import (
    E, State, Defect, Lang,
    e_z, e_val, e_equiv, excel, a_anchor, a_assimilate, a_ascend,
    E_ZERO, E_CERTAIN, E_EXECUTE_FLOOR, E_PI_WIDTH_WARN,
    E_PI_WIDTH_ENUMERATE, E_ASCEND_POINTS, E_INTAKE,
)

E_DEPTH_CEILING = 3          # floor(pi). unverified recursion stops here.

#: The hard stop for anchored recursion. Was a bare 4000 at the one
#: place it is checked; named because physics_test.py and audit.py
#: both need to state it, and a magic number stated in three places
#: is a number that will disagree with itself.
E_HARD_DEPTH = 4000


# ═════════════════════════════════════════════
# Closures
# ═════════════════════════════════════════════

@dataclass
class Closure:
    """A function. Held as the value of a thread."""
    name: str
    params: List[str]
    body: str
    env: Dict[str, E] = field(default_factory=dict)   # lexical capture
    examples_passed: int = 0
    examples_failed: int = 0
    measure: Optional[str] = None    # param that must strictly decrease
    recursive: bool = False

    def arity(self) -> int:
        return len(self.params)

    def __repr__(self) -> str:
        m = f" measure={self.measure}" if self.measure else ""
        return f"<fn {self.name}({', '.join(self.params)}){m}>"


def e_fn(name: str, params: List[str], body: str,
         env: Optional[Dict[str, E]] = None,
         recursive: bool = False) -> E:
    """A freshly defined function. Unverified until Examples pass.

    It starts below the execute floor for the same reason a literal
    does: reading a definition tells you its shape, not that it works.
    """
    c = Closure(name=name, params=params, body=body,
                env=dict(env or {}), recursive=recursive)
    p = e_val(name, c, E_INTAKE)
    p.reason = f"defined, {len(params)} parameter(s), unverified"
    return p


# ═════════════════════════════════════════════
# Termination: the measure
# ═════════════════════════════════════════════

def find_measure(params: List[str], body: str, name: str) -> Optional[str]:
    """Look for a parameter that strictly decreases in every self-call.

    Confidence proves trust, not termination. A function can sit at
    240/256 and still loop forever. So unbounded depth is granted only
    when a decreasing measure is found: some parameter that every
    recursive call reduces.

    This is a deliberately conservative syntactic check. It recognises
    the structural forms (n - k, n / k for k > 1) and nothing else. When
    it cannot prove decrease it says so, and the depth ceiling stays at
    floor(pi) = 3. Refusing to guess is the point.
    """
    calls = re.findall(re.escape(name) + r'\s*\(([^()]*)\)', body)
    if not calls:
        return None

    for param in params:
        decreases_everywhere = True
        for args in calls:
            pieces = [a.strip() for a in args.split(",")]
            idx = params.index(param)
            if idx >= len(pieces):
                decreases_everywhere = False
                break
            arg = pieces[idx]
            # n - positive, or n / greater-than-one
            m_sub = re.fullmatch(rf'{re.escape(param)}\s*-\s*(\d+)', arg)
            m_div = re.fullmatch(rf'{re.escape(param)}\s*/\s*(\d+)', arg)
            if m_sub and int(m_sub.group(1)) > 0:
                continue
            if m_div and int(m_div.group(1)) > 1:
                continue
            decreases_everywhere = False
            break
        if decreases_everywhere:
            return param
    return None


def a_anchor_fn(p: E) -> E:
    """Anchor a function.

    A non-recursive cleared function anchors normally. A recursive one
    must carry a decreasing measure first, otherwise 'unbounded depth'
    means 'hangs'.
    """
    if not isinstance(p.value, Closure):
        return a_anchor(p)

    c = p.value
    if not p.is_cleared:
        return e_z(p.ident, "cannot anchor an unverified function",
                   Defect.UNBOUND)

    if c.recursive and not c.measure:
        return e_z(p.ident,
                   "recursive function has no decreasing measure; "
                   "confidence proves trust, not termination",
                   Defect.UNBOUNDED)

    q = a_anchor(p)
    if c.recursive:
        q.reason = (f"anchored {q.anchor_id}, recursion unbounded on "
                    f"decreasing measure '{c.measure}'")
    return q


# ═════════════════════════════════════════════
# Application — the chain rule
# ═════════════════════════════════════════════

class DepthExceeded(Exception):
    def __init__(self, name: str, limit: int):
        self.name, self.limit = name, limit


def chain(parts: List[E]) -> int:
    """conf(f(x)) = min over every participant.

    The possibilistic rule. A result is no more trusted than its weakest
    input. This is a floor, not a probability, and it is stated as such
    so nobody mistakes it for one.
    """
    return min((p.confidence for p in parts), default=E_ZERO)


# ═════════════════════════════════════════════
# Conditionals — a Z condition spans both branches
# ═════════════════════════════════════════════

SPANNABLE = (int, float)


def branch(cond: E, then_thunk, else_thunk, ident: str) -> E:
    """`if c then a else b`.

    EVALUATION STRATEGY IS HYBRID, AND IT HAS TO BE.

    When c is known, only the taken branch is evaluated. This is not an
    optimisation; it is required. Evaluating both branches eagerly makes
    every recursive function non-terminating, because the recursive arm
    runs even when the base case was the one selected.

    When c is Z, BOTH branches are evaluated, because the result spans
    them. That is the cost of not collapsing to Z: to say 'it is one of
    these two' you have to know what both of them are.

    So Ever is lazy in branches under a known condition and eager under
    an unknown one. The unknown case is where the expense lives, which
    is the correct place for it to live.
    """
    if not cond.is_z:
        taken = then_thunk() if cond.value else else_thunk()
        if taken.is_z:
            return taken
        c = chain([cond, taken])
        r = e_val(ident, taken.value, c)
        r.reason = f"branch taken on {cond.ident}"
        return r

    then_v = then_thunk()
    else_v = else_thunk()

    # unknown condition
    if then_v.is_z or else_v.is_z:
        return e_z(ident, "condition unknown and a branch is Z", cond.defect)

    a, b = then_v.value, else_v.value

    if isinstance(a, bool) or isinstance(b, bool) or \
       not isinstance(a, SPANNABLE) or not isinstance(b, SPANNABLE):
        if a == b:
            # both branches agree, so the unknown condition does not matter
            c = min(then_v.confidence, else_v.confidence)
            r = e_val(ident, a, c)
            r.reason = "condition unknown but both branches agree"
            return r
        return e_z(ident,
                   f"condition unknown and branches are not spannable "
                   f"({then_v.type_name()})", Defect.UNBOUNDED)

    lo, hi = (a, b) if a <= b else (b, a)
    r = e_equiv(ident, int(lo), int(hi))
    r.confidence = min(then_v.confidence, else_v.confidence)
    width = r.hi - r.lo
    r.reason = (f"condition {cond.ident} unknown; spans {lo}..{hi} "
                f"(width {width}, {r.pi_status()})")

    if width > E_PI_WIDTH_WARN:
        z = e_z(ident, f"branches span {width}, past the pi threshold "
                       f"of {E_PI_WIDTH_WARN}", Defect.UNBOUNDED)
        return z
    return r


# ═════════════════════════════════════════════
# The evaluator
# ═════════════════════════════════════════════

TOKEN = re.compile(r'''
    (?P<num>-?\d+\.\d+|-?\d+)
  | (?P<str>"[^"]*")
  | (?P<name>[A-Za-z_]\w*)
  | (?P<op><=|>=|==|!=|[-+*/<>()])
  | (?P<comma>,)
''', re.X)


class Lambda:
    """Evaluates Ever expressions including application and branching."""

    def __init__(self, trace: bool = False):
        self.globals: Dict[str, E] = {}
        self.trace = trace
        self.calls = 0
        self.max_depth_seen = 0

    # ── entry ──

    def define(self, name: str, params: List[str], body: str) -> E:
        recursive = bool(re.search(re.escape(name) + r'\s*\(', body))
        p = e_fn(name, params, body, env=dict(self.globals),
                 recursive=recursive)
        if recursive:
            p.value.measure = find_measure(params, body, name)
            if p.value.measure:
                p.reason = (f"defined, recursive, decreasing measure "
                            f"'{p.value.measure}'")
            else:
                p.reason = ("defined, recursive, no decreasing measure "
                            f"found; depth capped at {E_DEPTH_CEILING}")
        self.globals[name] = p
        return p

    def example(self, name: str, args: List[Any], expect: Any) -> bool:
        """Evidence. Passing cases earn a function confidence."""
        fp = self.globals.get(name)
        if fp is None or not isinstance(fp.value, Closure):
            return False
        c = fp.value
        try:
            got = self.apply(fp, [e_val(f"arg{i}", a, E_CERTAIN)
                                  for i, a in enumerate(args)], {}, 0)
            passed = (not got.is_z) and got.value == expect
        except DepthExceeded:
            # Running out of depth is a failed Example, not a silent
            # skip. It has to lower the function's standing like any
            # other failure, or the depth ceiling would be free.
            passed = False

        if passed:
            c.examples_passed += 1
        else:
            c.examples_failed += 1

        total = c.examples_passed + c.examples_failed
        # Each passing Example is an independent witness at intake
        # strength, so they corroborate under the law already verified
        # elsewhere: u_total = u_intake ^ passed. One example does not
        # make a function trustworthy any more than one observation
        # lets a binding Ascend, and this is the same bar rather than a
        # softer one. Failures then scale the result down by the share
        # of evidence that held.
        u = ((E_CERTAIN - E_INTAKE) / E_CERTAIN) ** c.examples_passed \
            if c.examples_passed else 1.0
        base = int(E_CERTAIN * (1.0 - u))
        share = c.examples_passed / total
        conf = min(E_CERTAIN - 1, int(base * share))
        if conf <= 0:
            # The definition still exists; only its trustworthiness is
            # zero. Collapsing to a bare Z would discard the closure,
            # and nothing in Ever is discarded. The thread reports Z and
            # cannot execute, but the body stays available for the
            # archive and for diagnosis.
            new = E(ident=name, value=c, state=State.Z,
                    defect=Defect.MISBOUND, confidence=0,
                    reason=f"0/{total} examples passed; definition kept")
        else:
            new = e_val(name, c, conf)
            new.reason = f"{c.examples_passed}/{total} examples passed"
        if fp.anchor_id:
            new.anchor_id, new.state = fp.anchor_id, State.ANCHORED
        self.globals[name] = new
        return passed

    # ── application ──

    def apply(self, fp: E, args: List[E], env: Dict[str, E],
              depth: int) -> E:
        if fp.is_z:
            return e_z("call", f"{fp.ident} is Z", fp.defect)
        if not isinstance(fp.value, Closure):
            return e_z("call", f"{fp.ident} is not a function",
                       Defect.MISBOUND)

        c: Closure = fp.value

        # depth is earned. anchored with a measure recurses freely;
        # everything else stops at floor(pi).
        earned = fp.anchor_id != 0 and c.measure is not None
        if not earned and depth > E_DEPTH_CEILING:
            raise DepthExceeded(c.name, E_DEPTH_CEILING)
        if depth > E_HARD_DEPTH:
            raise DepthExceeded(c.name, E_HARD_DEPTH)

        if len(args) != c.arity():
            return e_z(c.name,
                       f"expected {c.arity()} argument(s), got {len(args)}",
                       Defect.MISBOUND)

        for a in args:
            if a.is_z:
                return e_z(c.name, f"argument {a.ident} is Z", a.defect)

        self.calls += 1
        self.max_depth_seen = max(self.max_depth_seen, depth)

        local = dict(c.env)
        local.update(env)
        for pname, aval in zip(c.params, args):
            local[pname] = aval

        result = self.eval(c.body, local, depth + 1, ident=c.name)

        # the chain rule: no more trusted than the weakest participant
        conf = chain([fp] + args + [result])
        if result.is_z:
            return result
        out = e_val(c.name + "()", result.value, conf)
        out.reason = f"applied {c.name}, floor of {conf}"
        return out

    # ── expressions ──

    def eval(self, expr: str, env: Dict[str, E], depth: int,
             ident: str = "expr") -> E:
        expr = expr.strip()

        # if COND then A else B
        m = re.match(r'^if\s+(.+?)\s+then\s+(.+?)\s+else\s+(.+)$', expr)
        if m:
            cond = self.eval(m.group(1), env, depth, ident + "_c")
            t_src, e_src = m.group(2), m.group(3)
            return branch(
                cond,
                lambda: self.eval(t_src, env, depth, ident + "_t"),
                lambda: self.eval(e_src, env, depth, ident + "_e"),
                ident)

        return self.expr(expr, env, depth, ident)

    def expr(self, s: str, env: Dict[str, E], depth: int, ident: str) -> E:
        s = s.strip()

        # comparison, lowest precedence
        m = self.split_top(s, ["<=", ">=", "==", "!=", "<", ">"])
        if m:
            lhs, op, rhs = m
            a = self.expr(lhs, env, depth, ident + "_l")
            b = self.expr(rhs, env, depth, ident + "_r")
            if a.is_z:
                return e_z(ident, f"operand {a.ident} is Z", a.defect)
            if b.is_z:
                return e_z(ident, f"operand {b.ident} is Z", b.defect)
            try:
                v = {"<=": lambda x, y: x <= y, ">=": lambda x, y: x >= y,
                     "==": lambda x, y: x == y, "!=": lambda x, y: x != y,
                     "<": lambda x, y: x < y, ">": lambda x, y: x > y
                     }[op](a.value, b.value)
            except TypeError:
                return e_z(ident, f"cannot compare {a.type_name()} with "
                                  f"{b.type_name()}", Defect.MISBOUND)
            return e_val(ident, v, chain([a, b]))

        # additive then multiplicative
        for ops in (["+", "-"], ["*", "/"]):
            m = self.split_top(s, ops)
            if m:
                lhs, op, rhs = m
                a = self.expr(lhs, env, depth, ident + "_l")
                b = self.expr(rhs, env, depth, ident + "_r")
                if a.is_z:
                    return e_z(ident, f"operand {a.ident} is Z", a.defect)
                if b.is_z:
                    return e_z(ident, f"operand {b.ident} is Z", b.defect)
                if op == "/" and b.value == 0:
                    return e_z(ident, "division by zero", Defect.MISBOUND)
                try:
                    v = {"+": lambda x, y: x + y, "-": lambda x, y: x - y,
                         "*": lambda x, y: x * y,
                         "/": lambda x, y: x / y}[op](a.value, b.value)
                except TypeError:
                    return e_z(ident,
                               f"cannot {op} {a.type_name()} with "
                               f"{b.type_name()}", Defect.MISBOUND)
                return e_val(ident, v, chain([a, b]))

        # parenthesised
        if s.startswith("(") and self.matching(s) == len(s) - 1:
            return self.expr(s[1:-1], env, depth, ident)

        # application  name(args)
        m = re.match(r'^([A-Za-z_]\w*)\s*\(', s)
        if m and self.matching(s, m.end() - 1) == len(s) - 1:
            name = m.group(1)
            inner = s[m.end():-1].strip()
            args = []
            if inner:
                for piece in self.split_args(inner):
                    args.append(self.expr(piece, env, depth, "arg"))
            fp = env.get(name) or self.globals.get(name)
            if fp is None:
                return e_z(ident, f"{name} was never defined", Defect.UNBOUND)
            return self.apply(fp, args, {}, depth)

        # PROGRAM CONSTANTS are Certain about their value.
        #
        # A literal written in Ever source carries no uncertainty about
        # WHAT IT IS. The author wrote 1; it is 1. Uncertainty in Ever
        # belongs to data arriving from outside and to whether functions
        # are correct -- never to what the program says about itself.
        #
        # Treating a source literal like external input floors every
        # computation in the language at intake, which made a verified
        # function return the right answer and decline to certify it.
        if re.fullmatch(r'-?\d+', s):
            return e_val(ident, int(s), E_CERTAIN)
        if re.fullmatch(r'-?\d*\.\d+', s):
            return e_val(ident, float(s), E_CERTAIN)
        if s.startswith('"') and s.endswith('"') and len(s) >= 2:
            return e_val(ident, s[1:-1], E_CERTAIN)
        if s in ("true", "false"):
            return e_val(ident, s == "true", E_CERTAIN)

        if re.fullmatch(r'[A-Za-z_]\w*', s):
            v = env.get(s) or self.globals.get(s)
            if v is None:
                return e_z(ident, f"{s} was never bound", Defect.UNBOUND)
            # a reference never inherits an anchor
            q = E(**{**v.__dict__})
            q.ident = s
            q.anchor_id = 0
            if v.state == State.ANCHORED:
                q.state = State.CONFIDENT
            return q

        return e_z(ident, f"cannot parse: {s}", Defect.MISBOUND)

    # ── helpers ──

    @staticmethod
    def matching(s: str, start: int = 0) -> int:
        d = 0
        for i in range(start, len(s)):
            if s[i] == "(":
                d += 1
            elif s[i] == ")":
                d -= 1
                if d == 0:
                    return i
        return -1

    @staticmethod
    def split_top(s: str, ops: List[str]) -> Optional[Tuple[str, str, str]]:
        """Split on the rightmost top-level operator, left-associating."""
        d = 0
        i = len(s) - 1
        while i >= 0:
            ch = s[i]
            if ch == ")":
                d += 1
            elif ch == "(":
                d -= 1
            elif d == 0:
                for op in sorted(ops, key=len, reverse=True):
                    if s.startswith(op, i):
                        # not a leading sign, and there is a left side
                        if i == 0:
                            break
                        prev = s[i - 1]
                        if op in "+-" and prev in "+-*/<>=(":
                            break
                        return s[:i], op, s[i + len(op):]
            i -= 1
        return None

    @staticmethod
    def split_args(s: str) -> List[str]:
        out, d, cur = [], 0, ""
        for ch in s:
            if ch == "(":
                d += 1
            elif ch == ")":
                d -= 1
            if ch == "," and d == 0:
                out.append(cur)
                cur = ""
            else:
                cur += ch
        if cur.strip():
            out.append(cur)
        return out
