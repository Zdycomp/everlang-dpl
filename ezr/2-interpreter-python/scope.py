"""
scope.py — Ever / Tapestry, Python-side universal map

Same API as scope.h / scope.c, implemented in Python.
The same five entry kinds, the same scope-chain lookup,
the same wire format (EValue RECORD) for ABI transfer.

OWNERSHIP (same rules as scope.h)
──────────────────────────────────
Python GC owns all entries. When a ParseResult is dropped the scope
goes with it. For cross-language transfer, call .to_record() and
serialise the result with evalue.serialise() before handing bytes to C.
C copies into its arena; Python retains its own copy.

Codric Enterprise · Ricky (Dreid) · 2026
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

from evalue import (
    EValue, EvType, EV_CERTAIN,
    lift_literal, lift_python,
    serialise as ev_serialise,
    deserialise as ev_deserialise,
)
from ir import EvNode, NK


# ─────────────────────────────────────────────
# FNV-1a — matches ev_fnv1a() in scope.c exactly
# ─────────────────────────────────────────────

def fnv1a(key: str) -> int:
    h = 0x811c9dc5
    for ch in key.encode("utf-8"):
        h = ((h ^ ch) * 0x01000193) & 0xFFFFFFFF
    return h


# ─────────────────────────────────────────────
# Entry kind — matches EvScopeKind in scope.h
# ─────────────────────────────────────────────

class SK(IntEnum):
    VAR     = 0
    FN      = 1
    CLASS   = 2
    MODULE  = 3
    BUILTIN = 4
    EXTERN  = 5   # foreign function, loaded via ffi.py


# ─────────────────────────────────────────────
# One entry
# ─────────────────────────────────────────────

@dataclass
class ScopeEntry:
    key:         str
    kind:        SK
    value:       EValue
    confidence:  int          = EV_CERTAIN
    lang:        int          = 11          # E_LANG_EVER
    anchor_id:   int          = 0
    node:        Optional[EvNode] = None    # fn / class body
    params:      List[str]    = field(default_factory=list)
    measure:     Optional[str] = None        # anchored: decreasing param
    extern_fn:   Optional[Any] = None        # SK.EXTERN: the loaded ctypes callable

    @property
    def is_fn(self)     -> bool: return self.kind == SK.FN
    @property
    def is_module(self) -> bool: return self.kind == SK.MODULE

    def describe(self) -> str:
        return (f"{self.kind.name}:{self.key} "
                f"= {self.value.describe()}@{self.confidence}/256")


# ─────────────────────────────────────────────
# The scope — wraps a plain dict for O(1) lookup
# ─────────────────────────────────────────────

class EvScope:
    """Universal map: string name → ScopeEntry.

    Mirrors EvScope in scope.h.  Uses Python dict internally
    (CPython hash map) so probe math, load factor, and resize
    are handled by the runtime.  The public API is identical.
    """

    def __init__(self, parent: Optional["EvScope"] = None,
                 name: str = "scope") -> None:
        self._map:    Dict[str, ScopeEntry] = {}
        self.parent:  Optional[EvScope]     = parent
        self.name:    str                   = name
        self.depth:   int                   = (parent.depth + 1
                                               if parent else 0)

    # ── insert / update ──

    def set(self, key: str, kind: SK, value: EValue,
            confidence: int = EV_CERTAIN, lang: int = 11,
            node: Optional[EvNode] = None,
            params: Optional[List[str]] = None) -> "EvScope":
        self._map[key] = ScopeEntry(
            key=key, kind=kind, value=value,
            confidence=confidence, lang=lang,
            node=node, params=params or [])
        return self

    def set_var(self, key: str, value: EValue,
                conf: int = EV_CERTAIN, lang: int = 11) -> "EvScope":
        return self.set(key, SK.VAR, value, conf, lang)

    def set_fn(self, name: str, node: EvNode, params: List[str],
               conf: int = EV_CERTAIN, lang: int = 11,
               measure: Optional[str] = None) -> "EvScope":
        e = self.set(name, SK.FN, EValue.void(), conf, lang,
                     node=node, params=params)
        self._map[name].measure = measure
        return e

    def set_module(self, name: str, module: "EvScope",
                   lang: int = 11) -> "EvScope":
        """Store a child scope under a name."""
        e = ScopeEntry(key=name, kind=SK.MODULE,
                       value=EValue.from_text(name),
                       lang=lang)
        e.node = module          # re-use node slot for the scope ref
        self._map[name] = e
        return self

    def set_builtin(self, name: str, value: EValue) -> "EvScope":
        return self.set(name, SK.BUILTIN, value, EV_CERTAIN, 11)

    # ── lookup — this scope only ──

    def get(self, key: str) -> Optional[ScopeEntry]:
        return self._map.get(key)

    # ── lookup — walk chain upward ──

    def lookup(self, key: str) -> Optional[ScopeEntry]:
        cur: Optional[EvScope] = self
        while cur is not None:
            e = cur.get(key)
            if e is not None:
                return e
            cur = cur.parent
        return None

    def bound_names(self) -> Set[str]:
        """Every name visible here, walking the parent chain — used
        to seed semantic analysis when continuing a session (REPL,
        embedder) across multiple run_source calls sharing one scope.
        """
        names: Set[str] = set()
        cur: Optional[EvScope] = self
        while cur is not None:
            names.update(cur._map.keys())
            cur = cur.parent
        return names

    def get_value(self, key: str) -> EValue:
        e = self.lookup(key)
        return e.value if e else EValue.void()

    def get_fn(self, name: str) -> Optional[EvNode]:
        e = self.lookup(name)
        if e and e.kind == SK.FN:
            return e.node
        return None

    def get_module(self, name: str) -> Optional["EvScope"]:
        e = self.lookup(name)
        if e and e.kind == SK.MODULE:
            return e.node   # stored in node field
        return None

    # ── delete ──

    def delete(self, key: str) -> bool:
        if key in self._map:
            del self._map[key]
            return True
        return False

    # ── iteration ──

    def entries(self) -> Iterator[ScopeEntry]:
        return iter(self._map.values())

    def __len__(self) -> int:
        return len(self._map)

    def __contains__(self, key: str) -> bool:
        return key in self._map

    # ── wire format — scope ↔ EValue(RECORD) ──

    def to_record(self) -> EValue:
        """Flatten this scope to EValue(RECORD) for ABI transfer.

        Values only — EvNode bodies travel via ir.serialise().
        Same structure as ev_scope_to_record() in scope.c.
        """
        fields: Dict[str, EValue] = {}
        for e in self.entries():
            if e.kind not in (SK.FN, SK.CLASS, SK.MODULE):
                fields[e.key] = e.value
        return EValue.from_record(fields)

    @classmethod
    def from_record(cls, rec: EValue, parent: Optional["EvScope"] = None,
                    name: str = "imported", lang: int = 11) -> "EvScope":
        """Reconstruct a scope from an EValue(RECORD).

        Same as ev_scope_from_record() in scope.c.
        """
        s = cls(parent=parent, name=name)
        if rec.ev_tag == EvType.RECORD:
            for k, v in rec.ev_record.items():
                s.set_var(k, v, lang=lang)
        return s

    # ── diagnostics ──

    def dump(self, indent: int = 0) -> None:
        pad = "  " * indent
        print(f"{pad}scope '{self.name}' (depth={self.depth}, "
              f"{len(self)} entries)")
        for e in sorted(self.entries(), key=lambda x: x.key):
            print(f"{pad}  {e.key:24} {e.kind.name:8} "
                  f"conf={e.confidence:4}/256  {e.value.describe()}")
        if self.parent:
            print(f"{pad}  ^ parent: '{self.parent.name}'")

    def stats(self) -> str:
        return (f"scope[{self.name}] depth={self.depth} "
                f"used={len(self)}")


# ─────────────────────────────────────────────
# Global scope builder — pre-loads builtins
# ─────────────────────────────────────────────

def make_global_scope() -> EvScope:
    """Create the root scope pre-populated with Ever builtins."""
    g = EvScope(name="global")

    # Mathematical constants
    g.set_var("true",  EValue.from_bool(True),   lang=11)
    g.set_var("false", EValue.from_bool(False),  lang=11)
    g.set_var("z",     EValue.void(),             lang=11)

    # Builtin markers (values are void — the interpreter handles them)
    for name in ("print", "show", "assert", "type_of",
                  "confidence_of", "anchor"):
        g.set_builtin(name, EValue.from_text(f"<builtin:{name}>"))

    return g


# ─────────────────────────────────────────────
# Evaluator — EvNode tree + EvScope → EValue
# ─────────────────────────────────────────────

E_ANCHORED_MAX_DEPTH = 512   # safety backstop, not a semantic limit
E_LOOP_MAX_ITERATIONS = 1_000_000  # backstop for while/for; ForRange
                                   # and ForIn are bounded by their
                                   # own range/length and will not
                                   # realistically hit this


def _measure_value(v: EValue) -> Optional[float]:
    """Numeric view of a measure argument, or None if it isn't one."""
    if v.ev_tag == EvType.INT:  return float(v.ev_int)
    if v.ev_tag == EvType.REAL: return v.ev_real
    return None


def _own_recursion_depth(scope: EvScope, fn_name: str) -> int:
    """How many frames of THIS SPECIFIC function are currently on the
    stack, walking the scope chain rather than trusting the shared
    `depth` counter.

    `depth` is incremented on every call regardless of which function
    is being entered, so it measures total call-stack depth across
    everything currently running — not any one function's own
    recursion. That distinction matters the moment an anchored
    function calls an ordinary helper: by the time an anchored loop
    is 5 levels deep, `depth` is 5, and a completely non-recursive
    helper called from inside it would fail `depth >= E_DEPTH_CEILING`
    despite never recursing at all — punished for its caller's depth,
    not its own. Counting frames named f"fn:{fn_name}" in the scope
    chain gives each function its own, independent count.
    """
    n = 0
    cur: Optional[EvScope] = scope
    target = f"fn:{fn_name}"
    while cur is not None:
        if cur.name == target:
            n += 1
        cur = cur.parent
    return n


def eval_node(node: EvNode, scope: EvScope,
              depth: int = 0) -> EValue:
    """Walk an IR tree, resolving names through scope.

    This is the Python-side counterpart to eval_node() in bridge_test.c.
    It bridges the gap identified in v3.4: ever.py had its own evaluator
    that bypassed the IR. Now there is one evaluation path.
    """
    from ir import E_DEPTH_CEILING

    if node is None:
        return EValue.void()

    k = node.kind

    if k == NK.VOID:  return EValue.void()
    if k == NK.BOOL:  return EValue.from_bool(node.lit_bool)
    if k == NK.INT:   return EValue.from_int(node.lit_int)
    if k == NK.REAL:  return EValue.from_real(node.lit_real)
    if k == NK.TEXT:  return EValue.from_text(node.str_val or "")

    if k == NK.VAR:
        name = node.str_val or ""
        entry = scope.lookup(name)
        if entry is None:
            return EValue.void()
        return entry.value

    if k in (NK.ADD, NK.SUB, NK.MUL, NK.DIV,
             NK.LT, NK.GT, NK.LTE, NK.GTE, NK.EQ, NK.NEQ):
        if len(node.children) < 2:
            return EValue.void()
        a = eval_node(node.children[0], scope, depth)
        b = eval_node(node.children[1], scope, depth)
        return _binop(k, a, b)

    if k == NK.IF:
        if len(node.children) < 3:
            return EValue.void()
        cond = eval_node(node.children[0], scope, depth)
        if cond.ev_tag == EvType.BOOL and cond.ev_bool:
            return eval_node(node.children[1], scope, depth)
        return eval_node(node.children[2], scope, depth)

    if k == NK.LIST:
        return EValue.from_list([eval_node(ch, scope, depth)
                                 for ch in node.children])

    if k == NK.AND:
        l = eval_node(node.children[0], scope, depth)
        if l.ev_tag != EvType.BOOL:
            return EValue.void()
        if not l.ev_bool:
            return l  # short-circuit: false and X is false
        return eval_node(node.children[1], scope, depth)

    if k == NK.OR:
        l = eval_node(node.children[0], scope, depth)
        if l.ev_tag != EvType.BOOL:
            return EValue.void()
        if l.ev_bool:
            return l  # short-circuit: true or X is true
        return eval_node(node.children[1], scope, depth)

    if k == NK.NOT:
        v = eval_node(node.children[0], scope, depth)
        if v.ev_tag != EvType.BOOL:
            return EValue.void()
        return EValue.from_bool(not v.ev_bool)

    if k == NK.INDEX:
        tgt = eval_node(node.children[0], scope, depth)
        key = eval_node(node.children[1], scope, depth)
        if tgt.ev_tag != EvType.LIST or key.ev_tag != EvType.INT:
            return EValue.void()
        idx = key.ev_int
        if idx < 0 or idx >= len(tgt.ev_list):
            return EValue.void()
        return tgt.ev_list[idx]

    if k == NK.FIELD:
        tgt = eval_node(node.children[0], scope, depth)
        if tgt.ev_tag != EvType.RECORD:
            return EValue.void()
        return tgt.ev_record.get(node.str_val, EValue.void())

    if k == NK.FOR_RANGE:
        start_v = eval_node(node.children[0], scope, depth)
        end_v   = eval_node(node.children[1], scope, depth)
        body    = node.children[2]
        step_v  = eval_node(node.children[3], scope, depth) \
                 if len(node.children) > 3 else None
        if start_v.ev_tag != EvType.INT or end_v.ev_tag != EvType.INT:
            return EValue.void()
        # NOTE: `if step_v and ...` would be wrong here — EValue
        # defines __len__ (for list/record introspection), so Python
        # falls back to it for truthiness, and a scalar EValue with
        # an empty ev_list reads as falsy even when it holds -2. Must
        # check `is not None` explicitly, never bare truthiness.
        step = step_v.ev_int if (step_v is not None and
                                 step_v.ev_tag == EvType.INT) else 1
        if step == 0:
            return EValue.void()
        result = EValue.void()
        i = start_v.ev_int
        guard = 0
        while (step > 0 and i <= end_v.ev_int) or \
              (step < 0 and i >= end_v.ev_int):
            guard += 1
            if guard > E_LOOP_MAX_ITERATIONS:
                return EValue.void()
            iter_scope = EvScope(parent=scope, name="for")
            iter_scope.set_var(node.str_val, EValue.from_int(i))
            result = eval_node(body, iter_scope, depth)
            i += step
        return result

    if k == NK.FOR_IN:
        seq = eval_node(node.children[0], scope, depth)
        body = node.children[1]
        if seq.ev_tag != EvType.LIST:
            return EValue.void()
        result = EValue.void()
        for item in seq.ev_list:
            iter_scope = EvScope(parent=scope, name="for")
            iter_scope.set_var(node.str_val, item)
            result = eval_node(body, iter_scope, depth)
        return result

    if k == NK.WHILE:
        cond, body = node.children[0], node.children[1]
        result = EValue.void()
        guard = 0
        while True:
            guard += 1
            if guard > E_LOOP_MAX_ITERATIONS:
                return EValue.void()
            c = eval_node(cond, scope, depth)
            if c.ev_tag != EvType.BOOL or not c.ev_bool:
                break
            result = eval_node(body, scope, depth)
        return result

    if k == NK.RECORD:
        vals = [eval_node(ch, scope, depth) for ch in node.children]
        return EValue.from_record(dict(zip(node.keys, vals)))

    if k == NK.DEF:
        # register the function in the current scope
        name   = node.str_val or ""
        params = node.params
        body   = node.children[0] if node.children else None
        if body:
            scope.set_fn(name, body, params)
        return EValue.void()

    if k == NK.CALL:
        name = node.str_val or ""
        entry = scope.lookup(name)
        if entry is not None and entry.kind == SK.EXTERN:
            args = [eval_node(ch, scope, depth) for ch in node.children]
            if entry.extern_fn is None:
                return EValue.void()
            return entry.extern_fn.call(args)
        if entry is None or entry.kind != SK.FN:
            # Not a user-defined function. Try the builtin registry
            # before giving up — user definitions take precedence, so
            # `def sigmoid(x) = ...` in your own program shadows the
            # built-in one, same as any other language.
            from builtins_ml import BUILTINS
            b = BUILTINS.get(name)
            if b is not None:
                args = [eval_node(ch, scope, depth) for ch in node.children]
                if len(args) != b.arity:
                    return EValue.void()
                return b.call(args)
            return EValue.void()

        # Enforce the depth ceiling (floor(pi) = 3).
        #
        # CORRECTED BACK from a change made earlier this session. That
        # change was validated against ev_interp_call() / a direct
        # body-entry probe, which skips the gate for the OUTERMOST
        # invocation entirely — it calls interp_func() directly rather
        # than going through this CALL handler at all. Under that
        # entry point, `depth+1 >= ceiling` looked correct.
        #
        # But no real .ever program calls that way. `ever f = fact(3)`
        # evaluates fact(3) as an ordinary expression: the FIRST call
        # goes through this exact handler, at depth=0, same as every
        # nested call after it. Under that — the only path real
        # programs use — the ORIGINAL check below is the one that
        # gives fact(3)=6 and fact(4)=z, matching the gold-standard
        # baselines this whole project was already built against.
        # Reverting to it, confirmed by full regression, not by a
        # second isolated probe.
        body   = entry.node
        params = entry.params
        args   = [eval_node(ch, scope, depth) for ch in node.children]

        # ── ANCHORING ────────────────────────────────────────────
        # Unanchored recursion stops at floor(pi) = 3, because the
        # system will not compute what it cannot prove terminates.
        #
        # An ANCHORED function has a parameter the semantic pass
        # proved strictly decreases in every self-call. That proof is
        # a termination argument, so the ceiling lifts: the recursion
        # is bounded by the measure itself, not by an arbitrary limit.
        #
        # The proof is static; this is the runtime half. Each call
        # checks the measure actually fell. If it ever fails to, the
        # anchor is void and the answer is z — a promise that stops
        # being kept stops being trusted.
        # Own recursion depth for THIS function specifically — not the
        # ambient `depth` shared by every call currently on the stack.
        # See _own_recursion_depth for why that distinction is load
        # bearing here.
        own_depth = _own_recursion_depth(scope, name)

        anchored = entry.measure is not None and entry.measure in params
        if anchored:
            midx = params.index(entry.measure)
            prev = scope.lookup(f"__anchor__{name}")
            cur  = args[midx] if midx < len(args) else EValue.void()
            cur_n = _measure_value(cur)
            if cur_n is None:
                return EValue.void()
            if prev is not None:
                prev_n = _measure_value(prev.value)
                if prev_n is not None and cur_n >= prev_n:
                    # measure did not decrease — anchor broken
                    return EValue.void()
            if own_depth >= E_ANCHORED_MAX_DEPTH:
                return EValue.void()
        elif own_depth >= E_DEPTH_CEILING:
            return EValue.void()

        # create a local scope for the call
        call_scope = EvScope(parent=scope, name=f"fn:{name}")
        for pname, aval in zip(params, args):
            call_scope.set_var(pname, aval)
        if anchored:
            call_scope.set_var(f"__anchor__{name}", args[midx])

        return eval_node(body, call_scope, depth + 1)

    return EValue.void()


def _binop(k: NK, a: EValue, b: EValue) -> EValue:
    """Arithmetic and comparison on EValues."""
    # numeric coercion: INT op REAL → REAL
    def _num(v: EValue) -> Optional[float]:
        if v.ev_tag == EvType.INT:  return float(v.ev_int)
        if v.ev_tag == EvType.REAL: return v.ev_real
        return None

    na, nb = _num(a), _num(b)

    if k == NK.ADD:
        if na is not None and nb is not None:
            r = na + nb
            if a.ev_tag == EvType.INT and b.ev_tag == EvType.INT:
                return EValue.from_int(int(r))
            return EValue.from_real(r)
        if a.ev_tag == EvType.TEXT and b.ev_tag == EvType.TEXT:
            return EValue.from_text((a.ev_text or "") + (b.ev_text or ""))

    if k == NK.SUB and na is not None and nb is not None:
        r = na - nb
        return (EValue.from_int(int(r))
                if a.ev_tag == EvType.INT and b.ev_tag == EvType.INT
                else EValue.from_real(r))

    if k == NK.MUL and na is not None and nb is not None:
        r = na * nb
        return (EValue.from_int(int(r))
                if a.ev_tag == EvType.INT and b.ev_tag == EvType.INT
                else EValue.from_real(r))

    if k == NK.DIV and na is not None and nb is not None and nb != 0:
        return EValue.from_real(na / nb)

    # comparisons
    cmp_map = {
        NK.LT:  lambda x,y: x < y,
        NK.GT:  lambda x,y: x > y,
        NK.LTE: lambda x,y: x <= y,
        NK.GTE: lambda x,y: x >= y,
        NK.EQ:  lambda x,y: x == y,
        NK.NEQ: lambda x,y: x != y,
    }
    if k in cmp_map and na is not None and nb is not None:
        return EValue.from_bool(cmp_map[k](na, nb))

    return EValue.void()


# ─────────────────────────────────────────────
# Demo
# ─────────────────────────────────────────────

if __name__ == "__main__":
    from ir import parse_to_ir

    print("\n=== EvScope — Python universal map ===\n")

    g = make_global_scope()
    print(f"Global scope: {len(g)} builtins pre-loaded")
    g.set_var("x",     EValue.from_int(42),    lang=11)
    g.set_var("score", EValue.from_real(98.6), lang=11)

    math_mod = EvScope(parent=g, name="Math")
    math_mod.set_var("PI", EValue.from_real(math.pi), lang=11)
    g.set_module("Math", math_mod)

    g.dump()
    print()

    # Parse and evaluate through the scope
    programs = [
        ("6 + 36",                    42),
        ("if true then 42 else 0",    42),
    ]
    for src, expected in programs:
        r = parse_to_ir(src)
        if not r.ok:
            print(f"  ✗  PARSE: {src} — {r.error}"); continue
        local = EvScope(parent=g, name="eval")
        result = eval_node(r.root, local)
        ok = (result.ev_int == expected if result.ev_tag == EvType.INT
              else False)
        print(f"  {'✓' if ok else '✗'}  {src:40} → {result.describe()}")

    # Factorial through scope
    fact_src = "def fact(n) = if n <= 1 then 1 else n * fact(n - 1)"
    r2 = parse_to_ir(fact_src)
    if r2.ok:
        local2 = EvScope(parent=g, name="fact-test")
        eval_node(r2.root, local2)   # registers fact in local2
        # now call it by building a CALL node
        from ir import EvNode, NK
        call = EvNode.fn_call("fact", [EvNode.int_lit(5)])
        result2 = eval_node(call, local2)
        print(f"  {'✓' if result2.ev_int==120 else '✗'}  "
              f"fact(5)  → {result2.describe()}")

    print()
    print(g.stats())
