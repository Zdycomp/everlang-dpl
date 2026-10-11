#!/usr/bin/env python3
"""
runtime.py — Ever / Tapestry, the real program executor.

Every prior execution of a multi-statement .ever file in this project
went through a regex line-splitter living inside test-harness code
(tests/ev_integrate.py), which also hardcoded every let/ever binding's
confidence to 256 regardless of what the initializer actually computed.
For a language whose entire premise is honest trust tracking, that was
a live correctness bug, not a shortcut — z-contagion into `ever risky =
some_uncertain_call()` was silently discarded.

This module is the real thing: a Program AST (from syntax.py's actual
grammar) executed statement by statement, with each let/ever binding's
confidence computed from what it was actually built from, and z/void
propagated instead of erased.

Codric Enterprise · Ricky (Dreid) · 2026
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional

from syntax import parse, Semantic, Program, Let, Show, FnDef, Extern
from forgive import parse_forgiving, Correction
from repair_archive import archive_corrections
from ir import _ast_to_ir, NK, EvNode, E_CERTAIN, E_INTAKE
from scope import (EvScope, make_global_scope, eval_node,
                   E_LOOP_MAX_ITERATIONS, SK)
from evalue import EValue, EvType, EV_CERTAIN

try:
    from profiler import Profiler
    _PROFILER_AVAILABLE = True
except ImportError:
    _PROFILER_AVAILABLE = False
    Profiler = None


# ─────────────────────────────────────────────
# Confidence computation
#
# eval_node (scope.py) returns a bare EValue — it does not track trust.
# Confidence lives at the SCOPE ENTRY, not the value. This mirrors that
# same recursive structure purely to compute the number that belongs
# next to it, so a let/ever binding gets the trust its initializer
# actually earned rather than a blanket 256.
# ─────────────────────────────────────────────

def eval_confidence(node: Optional[EvNode], scope: EvScope) -> int:
    """What confidence does evaluating `node` in `scope` deserve?

    Rules, matching the C TAC interpreter and the language's own
    stated corroboration model:
      - a literal constant is CERTAIN (256): the program said so
      - z is 0, by definition
      - a variable reference carries whatever its binding carries
      - a binary op is the MIN of its operands (never more certain
        than its least certain input)
      - if/then/else is the MIN of the condition and whichever branch
        is taken
      - a call to an undefined or ceiling-blocked function is 0
      - a call to a defined function is the MIN of its argument
        confidences (the function body's own trust isn't tracked
        per-instruction on the Python side; this is the honest
        approximation available without reimplementing TAC-level
        propagation here)
    """
    if node is None:
        return 0
    k = node.kind

    if k in (NK.VOID,):
        return 0
    if k == NK.Z:
        return 0
    if k in (NK.BOOL, NK.INT, NK.REAL, NK.TEXT):
        return E_CERTAIN

    if k == NK.VAR:
        entry = scope.lookup(node.str_val or "")
        return entry.confidence if entry is not None else 0

    if k in (NK.ADD, NK.SUB, NK.MUL, NK.DIV,
             NK.LT, NK.GT, NK.LTE, NK.GTE, NK.EQ, NK.NEQ):
        if len(node.children) < 2:
            return 0
        return min(eval_confidence(node.children[0], scope),
                   eval_confidence(node.children[1], scope))

    if k == NK.IF:
        if len(node.children) < 3:
            return 0
        cond_val  = eval_node(node.children[0], scope)
        cond_conf = eval_confidence(node.children[0], scope)
        branch = node.children[1] if (cond_val.ev_tag == EvType.BOOL
                                      and cond_val.ev_bool) \
                 else node.children[2]
        return min(cond_conf, eval_confidence(branch, scope))

    if k in (NK.LIST, NK.RECORD):
        if not node.children:
            return E_CERTAIN
        return min(eval_confidence(ch, scope) for ch in node.children)

    if k == NK.AND:
        l_val  = eval_node(node.children[0], scope)
        l_conf = eval_confidence(node.children[0], scope)
        if l_val.ev_tag != EvType.BOOL:
            return 0
        if not l_val.ev_bool:
            return l_conf     # short-circuit: only the left was consulted
        return min(l_conf, eval_confidence(node.children[1], scope))

    if k == NK.OR:
        l_val  = eval_node(node.children[0], scope)
        l_conf = eval_confidence(node.children[0], scope)
        if l_val.ev_tag != EvType.BOOL:
            return 0
        if l_val.ev_bool:
            return l_conf     # short-circuit
        return min(l_conf, eval_confidence(node.children[1], scope))

    if k == NK.NOT:
        return eval_confidence(node.children[0], scope)

    if k == NK.INDEX:
        tgt = eval_node(node.children[0], scope)
        key = eval_node(node.children[1], scope)
        key_conf = eval_confidence(node.children[1], scope)
        if tgt.ev_tag != EvType.LIST or key.ev_tag != EvType.INT:
            return 0
        idx = key.ev_int
        if idx < 0 or idx >= len(tgt.ev_list):
            return 0
        # Deliberately NOT folding in the confidence of the whole
        # container here. That figure is the MIN across every element
        # (days' overall confidence is 0 because thu=z lives in it
        # somewhere) — using it would make reading days[0] (mon, fully
        # certain) inherit uncertainty from thu, an unrelated element
        # this read never touches. A void container is already caught
        # by the ev_tag check above; what's left is the ONE element
        # actually read, and the key that picked it.
        elem_conf = tgt.ev_list[idx].confidence
        return min(key_conf, elem_conf)

    if k == NK.FIELD:
        tgt = eval_node(node.children[0], scope)
        if tgt.ev_tag != EvType.RECORD:
            return 0
        field_val = tgt.ev_record.get(node.str_val)
        if field_val is None:
            return 0
        # same reasoning as INDEX: only this field's own confidence,
        # not the record's aggregate across every other field
        return field_val.confidence

    if k in (NK.FOR_RANGE, NK.FOR_IN):
        # Mirrors eval_node's own driving loop exactly, so "which
        # iteration is last" always agrees between the two — computing
        # confidence for a DIFFERENT iteration than the one whose
        # value was actually shown would be worse than not tracking
        # confidence at all.
        is_range = (k == NK.FOR_RANGE)
        if is_range:
            start_v = eval_node(node.children[0], scope)
            end_v   = eval_node(node.children[1], scope)
            body    = node.children[2]
            step_v  = eval_node(node.children[3], scope) \
                     if len(node.children) > 3 else None
            bounds_conf = min(eval_confidence(node.children[0], scope),
                              eval_confidence(node.children[1], scope))
            if start_v.ev_tag != EvType.INT or end_v.ev_tag != EvType.INT:
                return 0
            step = step_v.ev_int if (step_v is not None and
                                     step_v.ev_tag == EvType.INT) else 1
            if step == 0:
                return 0
            last_conf = 0
            i = start_v.ev_int
            guard = 0
            while (step > 0 and i <= end_v.ev_int) or \
                  (step < 0 and i >= end_v.ev_int):
                guard += 1
                if guard > E_LOOP_MAX_ITERATIONS:
                    return 0
                iter_scope = EvScope(parent=scope, name="for")
                iter_scope.set_var(node.str_val, EValue.from_int(i))
                last_conf = eval_confidence(body, iter_scope)
                i += step
            return min(bounds_conf, last_conf) if last_conf else 0
        else:
            seq = eval_node(node.children[0], scope)
            body = node.children[1]
            seq_conf = eval_confidence(node.children[0], scope)
            if seq.ev_tag != EvType.LIST:
                return 0
            last_conf = 0
            for item in seq.ev_list:
                iter_scope = EvScope(parent=scope, name="for")
                iter_scope.set_var(node.str_val, item)
                last_conf = eval_confidence(body, iter_scope)
            return min(seq_conf, last_conf) if last_conf else 0

    if k == NK.WHILE:
        cond, body = node.children[0], node.children[1]
        last_conf = 0
        guard = 0
        while True:
            guard += 1
            if guard > E_LOOP_MAX_ITERATIONS:
                return 0
            c_val  = eval_node(cond, scope)
            c_conf = eval_confidence(cond, scope)
            if c_val.ev_tag != EvType.BOOL or not c_val.ev_bool:
                break
            last_conf = min(c_conf, eval_confidence(body, scope))
        return last_conf

    if k == NK.CALL:
        name = node.str_val or ""
        entry = scope.lookup(name)
        if entry is not None and entry.kind == SK.EXTERN:
            if entry.extern_fn is None:
                return 0
            args  = [eval_node(ch, scope) for ch in node.children]
            confs = [eval_confidence(ch, scope) for ch in node.children]
            result = entry.extern_fn.call(args)
            if result.ev_tag == EvType.VOID:
                return 0
            return entry.extern_fn.confidence(args, confs)
        if entry is None:
            from builtins_ml import BUILTINS
            b = BUILTINS.get(name)
            if b is None:
                return 0
            args  = [eval_node(ch, scope) for ch in node.children]
            confs = [eval_confidence(ch, scope) for ch in node.children]
            if len(args) != b.arity:
                return 0
            result = b.call(args)
            if result.ev_tag == EvType.VOID:
                return 0
            return b.conf(args, confs)
        confs = [eval_confidence(ch, scope) for ch in node.children]
        # a call that will hit the depth ceiling or fail resolves to
        # z at evaluation; approximate its confidence as 0 up front
        # rather than double-walk the recursive call here.
        result = eval_node(node, scope)
        if result.ev_tag == EvType.VOID:
            return 0
        # [APP] is min(c_f, c_args, c_result), and the c_f term was not
        # here. A function's own confidence had nowhere to land: nothing
        # anywhere read ScopeEntry.confidence for an SK.FN entry, so a
        # function believed at 1/256 still handed back answers at
        # 256/256. Measured before the fix, on this exact path:
        #
        #   def dbl(n) = n * 2   with dbl's entry forced to 1/256
        #   dbl(21)  ->  42 @ 256      [APP] wants min(1, 256) = 1
        #
        # Including it is a no-op for every program that does not set a
        # function's confidence, since definitions still enter at
        # CERTAIN -- but it is what makes earned confidence mean
        # anything, and it is what SEMANTICS.md 4.3 actually says.
        return min([entry.confidence] + confs)

    return 0


# ─────────────────────────────────────────────
# Program result
# ─────────────────────────────────────────────

@dataclass
class ShownValue:
    name:       str
    value:      EValue
    confidence: int
    is_fn:      bool = False
    params:     Optional[List[str]] = None

@dataclass
class ProgramResult:
    shown:       List[ShownValue] = field(default_factory=list)
    errors:      List[str]        = field(default_factory=list)
    recoveries:  List[str]        = field(default_factory=list)
    proficiency: Optional[int]    = None
    scaffold:    Optional[str]    = None
    scope:       Optional[EvScope] = None

    @property
    def ok(self) -> bool:
        return not self.errors

    def format_lines(self) -> List[str]:
        out = []
        for sv in self.shown:
            if sv.is_fn:
                # A function is bound as SK.FN and carries no EValue,
                # so the value formatter used to render it as z. It is
                # not unknown — it is a definition. Show it as one.
                params = ", ".join(sv.params or [])
                out.append(f"{sv.name} = def {sv.name}({params}) "
                           f"[{sv.confidence}/256]")
            else:
                out.append(_format_value(sv.name, sv.value, sv.confidence))
        return out


def _format_value(name: str, val: EValue, conf: int) -> str:
    if val.ev_tag == EvType.VOID:
        return f"{name} = z [0/256]"
    if val.ev_tag == EvType.BOOL:
        return f"{name} = {'true' if val.ev_bool else 'false'} [{conf}/256]"
    if val.ev_tag == EvType.INT:
        return f"{name} = {val.ev_int} [{conf}/256]"
    if val.ev_tag == EvType.REAL:
        r = val.ev_real
        shown = int(r) if r == int(r) else f"{r:g}"
        return f"{name} = {shown} [{conf}/256]"
    if val.ev_tag == EvType.TEXT:
        return f'{name} = "{val.ev_text}" [{conf}/256]'
    return f"{name} = {val.describe()} [{conf}/256]"


# ─────────────────────────────────────────────
# THE EXECUTOR
# ─────────────────────────────────────────────

def run_source(source: str, profiler: Optional["Profiler"] = None,
              scope: Optional[EvScope] = None) -> ProgramResult:
    """Parse and execute a full .ever source string for real: through
    the actual grammar (syntax.py), the actual semantic pass (with
    Program-level scope threading), and the actual evaluator
    (scope.py's eval_node) — with genuine per-binding confidence.

    This is the function a CLI, a REPL, or an embedder should call.
    It is not a test harness; it is the language's real front door.
    """
    result = ProgramResult()
    # E forgives what it safely can (trailing commas, a stray ';',
    # colon/equals confusion, keyword case, a lone '=' meant as '==')
    # and reports exactly what it assumed. Only a genuinely ambiguous
    # program still refuses — see forgive.py for the boundary.
    node, perr, result.corrections = parse_forgiving(source)

    # SEMANTICS.md §9: every repair E performs is archived as a
    # (Failure, Fixture) pair, unconditionally. Archive failure never
    # blocks execution — the language must run on a read-only fs.
    if result.corrections:
        try:
            archive_corrections(
                result.corrections,
                source_ident=getattr(scope, "origin", "runtime.run_program"))
        except Exception:
            pass
    if perr is not None:
        result.errors.append(str(perr))
        return result
    if node is None:
        return result

    # Recoveries: punctuation E fixed rather than failing on. Full/
    # guided bands get the teaching line; everyone else gets the
    # one-line note; nobody sees the raw text swallowed silently —
    # forgiving a mistake is not the same as hiding that one happened.
    for rec in getattr(node, "_recoveries", []):
        line = (rec.teach if (profiler and profiler.scaffold_level()
                              in ("full", "guided")) else rec.message)
        result.recoveries.append(f"line {rec.line}: {line}")

    # Normalise: a single bare statement (no let/ever/show) still
    # comes back unwrapped from parse() for backward compatibility.
    # Wrap it here so the executor has one code path.
    prog = node if isinstance(node, Program) else Program([node])

    # NOTE: no profiler passed in. Semantic.analyse() calls observe()
    # once per statement, which would count a 14-line program as 14
    # sessions and inflate the score. Without a profiler it still
    # attaches an Observation to each Analysis; we fold those into ONE
    # observation per program below.
    sem = Semantic(source=source)
    preexisting = scope.bound_names() if scope is not None else None
    pa = sem.analyse_program(prog, preexisting=preexisting)
    if not pa.clean:
        result.errors.extend(pa.errors)
        return result

    g = scope if scope is not None else make_global_scope()

    for stmt in prog.statements:
        cls = type(stmt).__name__

        if cls == "FnDef":
            fn_ir = _ast_to_ir(stmt)
            if fn_ir is not None:
                eval_node(fn_ir, g)
                # Attach the termination proof the semantic pass found.
                # A function with a strictly-decreasing parameter is
                # ANCHORED: its recursion is bounded by the measure, so
                # the floor(pi)=3 ceiling does not apply to it.
                measure = Semantic._measure(stmt)
                if measure:
                    e = g.lookup(stmt.name)
                    if e is not None:
                        e.measure = measure
            continue

        if cls == "Extern":
            from ffi import load_extern, FFIError
            try:
                fn = load_extern(stmt.name, stmt.params, stmt.libpath)
            except FFIError as exc:
                result.errors.append(str(exc))
                continue
            g.set(stmt.name, SK.EXTERN, EValue.void(), confidence=EV_CERTAIN)
            g.lookup(stmt.name).extern_fn = fn
            g.lookup(stmt.name).params = list(stmt.params)
            continue

        if cls == "Let":
            expr_ir = _ast_to_ir(stmt.value)
            if expr_ir is None:
                g.set_var(stmt.name, EValue.void(), conf=0)
                continue
            val  = eval_node(expr_ir, g)
            conf = eval_confidence(expr_ir, g)
            # Sync the tracked confidence ONTO the value itself, not
            # just onto the scope entry. Confidence lives in two
            # places: ScopeEntry.confidence (what `show` reads) and
            # EValue.confidence (what travels WITH the value once it
            # leaves the entry — into a list, a record, an argument).
            # Those two only matched by coincidence for a certain
            # literal; `thu = z` showed the gap directly: the entry
            # tracked confidence 0 correctly, but the raw EValue.void()
            # defaults its own .confidence to 256, so `thu` embedded in
            # a list and read back via indexing reported certain. Every
            # binding is resynced here so nothing downstream that reads
            # confidence off a value directly — not through a scope
            # entry — inherits a stale default.
            if val.confidence != conf:
                val = replace(val, confidence=conf)
            g.set_var(stmt.name, val, conf=conf)
            continue

        if cls == "Show":
            entry = g.lookup(stmt.name)
            val  = entry.value if entry is not None else EValue.void()
            conf = entry.confidence if entry is not None else 0
            is_fn = bool(entry is not None and getattr(entry, "is_fn", False))
            result.shown.append(ShownValue(
                stmt.name, val, conf,
                is_fn=is_fn,
                params=list(entry.params) if is_fn else None))
            continue

        # bare trailing expression statement: evaluate, don't show
        expr_ir = _ast_to_ir(stmt)
        if expr_ir is not None:
            eval_node(expr_ir, g)

    result.scope = g
    if profiler is not None and pa.statements:
        # fold the whole program's construct mix into one profiler
        # observation rather than one per statement, so a five-line
        # beginner program and a five-line advanced one are compared
        # as programs, not diluted per line.
        try:
            from profiler import Observation
            combined = Observation()
            for a in pa.statements:
                if a.observation:
                    for key, n in a.observation.counts.items():
                        combined.note(key, n)
                    combined.max_depth = max(combined.max_depth,
                                             a.observation.max_depth)
            p = profiler.observe(combined)
            result.proficiency = p.rounded
            result.scaffold    = p.scaffold
        except Exception:
            pass

    return result


if __name__ == "__main__":
    demo = """
    let a = 6
    ever b = 36
    ever sum = a + b
    ever unknown = z
    ever poisoned = sum + unknown
    show sum
    show unknown
    show poisoned
    """
    r = run_source(demo)
    if not r.ok:
        print("errors:", r.errors)
    else:
        for line in r.format_lines():
            print(line)
