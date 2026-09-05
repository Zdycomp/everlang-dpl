#!/usr/bin/env python3
"""abstract_test.py — Ever / Tapestry, abstraction layer verification."""

from abstract import (
    Lambda, Closure, DepthExceeded, branch, chain, find_measure,
    a_anchor_fn, e_fn, E_DEPTH_CEILING,
)
from ever import (
    e_val, e_z, e_equiv, State, Defect,
    E_CERTAIN, E_EXECUTE_FLOOR, E_INTAKE, E_PI_WIDTH_WARN,
    E_PI_WIDTH_ENUMERATE,
)

passed = failed = 0


def ok(name, cond):
    global passed, failed
    if cond:
        passed += 1; print(f"  \u2713 {name}")
    else:
        failed += 1; print(f"  \u2717 {name}")


print("\n=== Ever — the abstraction layer ===\n")

print("Functions are threads")
L = Lambda()
f = L.define("double", ["x"], "x * 2")
ok("definition makes a thread",   f.value is not None)
ok("holds a closure",             isinstance(f.value, Closure))
ok("arity recorded",              f.value.arity() == 1)
ok("starts at intake",            f.confidence == E_INTAKE)
ok("starts below execute floor",  f.confidence < E_EXECUTE_FLOOR)
ok("non-recursive detected",      not f.value.recursive)

print("\nApplication chains by min")
r = L.apply(L.globals["double"], [e_val("x", 21, 200)], {}, 0)
ok("computes",                    r.value == 42)
ok("floors at the weakest input", r.confidence == min(E_INTAKE, 200))
r2 = L.apply(L.globals["double"], [e_val("x", 5, 40)], {}, 0)
ok("weak argument drags it down", r2.confidence == 40)
rz = L.apply(L.globals["double"], [e_z("x", "unmeasured")], {}, 0)
ok("Z argument yields Z",         rz.is_z)
ok("Z reason names the argument", "x" in rz.reason)

print("\nArity is checked")
bad = L.apply(L.globals["double"], [], {}, 0)
ok("wrong arity is Z",            bad.is_z)
ok("arity failure is misbound",   bad.defect == Defect.MISBOUND)

print("\nExamples corroborate rather than assert")
L2 = Lambda()
L2.define("sq", ["n"], "n * n")
seen = []
for a, w in [(2, 4), (3, 9), (4, 16), (5, 25)]:
    L2.example("sq", [a], w)
    seen.append(L2.globals["sq"].confidence)
ok("one example stays at intake", seen[0] == E_INTAKE)
ok("one example is below floor",  seen[0] < E_EXECUTE_FLOOR)
ok("confidence rises with evidence", seen == sorted(seen))
ok("three examples clear the floor",  seen[2] >= E_EXECUTE_FLOOR)
ok("examples never reach Certain",    seen[-1] < E_CERTAIN)

L3 = Lambda()
L3.define("wrong", ["n"], "n + 1")
for a, w in [(1, 2), (2, 3), (3, 99)]:
    L3.example("wrong", [a], w)
fp = L3.globals["wrong"]
ok("a failure lowers standing",   fp.confidence < seen[2])
ok("failure recorded in reason",  "2/3" in fp.reason)

print("\nMeasure detection")
ok("n - 1 decreases",   find_measure(["n"], "if n <= 1 then 1 else n * f(n - 1)", "f") == "n")
ok("n / 2 decreases",   find_measure(["n"], "if n < 2 then 0 else f(n / 2)", "f") == "n")
ok("n + 1 does not",    find_measure(["n"], "f(n + 1)", "f") is None)
ok("n unchanged does not", find_measure(["n"], "f(n)", "f") is None)
ok("non-recursive has none", find_measure(["n"], "n * 2", "f") is None)

print("\nDepth is earned, not assumed")
L4 = Lambda()
fd = L4.define("fact", ["n"], "if n <= 1 then 1 else n * fact(n - 1)")
ok("recursion detected",          fd.value.recursive)
ok("measure found",               fd.value.measure == "n")


def call(lam, n):
    try:
        return lam.apply(lam.globals["fact"], [e_val("n", n, 200)], {}, 0)
    except DepthExceeded:
        return None


ok("shallow call works unanchored",   call(L4, 3) is not None)
ok("shallow value correct",           call(L4, 3).value == 6)
ok("deep call blocked unanchored",    call(L4, 8) is None)

for a, w in [(1, 1), (2, 2), (3, 6)]:
    L4.example("fact", [a], w)
L4.globals["fact"] = a_anchor_fn(L4.globals["fact"])
ok("anchored",                        L4.globals["fact"].state == State.ANCHORED)
ok("anchor reason cites the measure", "measure" in L4.globals["fact"].reason)
ok("deep call works anchored",        call(L4, 8) is not None)
ok("fact(10) correct",                call(L4, 10).value == 3628800)
ok("fact(20) correct",                call(L4, 20).value == 2432902008176640000)
ok("depth exceeded the ceiling",      L4.max_depth_seen > E_DEPTH_CEILING)

print("\nAnchoring refuses what it cannot justify")
L5 = Lambda()
L5.define("spin", ["n"], "if n < 0 then 0 else spin(n + 1)")
for a, w in [(0, 0), (1, 0), (2, 0)]:
    L5.example("spin", [a], w)
spin_thread = L5.globals["spin"]
ok("failing examples keep the definition",
   isinstance(spin_thread.value, Closure))
ok("failing examples drop it to Z",     spin_thread.is_z)
sp = a_anchor_fn(spin_thread)
ok("no measure means no anchor",        sp.is_z)

# a function that IS verified but has no decreasing measure
L5b = Lambda()
L5b.define("grow", ["n"], "if n > 99 then n else grow(n + 1)")
ok("no measure found for n + 1",        L5b.globals["grow"].value.measure is None)
for a, w in [(100, 100), (150, 150), (200, 200)]:
    L5b.example("grow", [a], w)
gp = L5b.globals["grow"]
ok("verified despite no measure",       gp.is_cleared)
gr = a_anchor_fn(gp)
ok("verified but unproven cannot anchor", gr.is_z)
ok("refusal names termination",         "termination" in gr.reason)
ok("refusal is unbounded defect",       gr.defect == Defect.UNBOUNDED)

L6 = Lambda()
L6.define("f", ["n"], "if n <= 1 then 1 else n * f(n - 1)")
unverified = a_anchor_fn(L6.globals["f"])
ok("intake alone is cleared but weak",  L6.globals["f"].confidence == E_INTAKE)
ok("anchoring at intake still succeeds", not unverified.is_z)

print("\nBranching on a known condition is lazy")
L7 = Lambda()
L7.define("safe", ["n"], "if n <= 0 then 0 else 100 / n")
ok("base case avoids the else branch",
   L7.apply(L7.globals["safe"], [e_val("n", 0, 200)], {}, 0).value == 0)
ok("live case takes the else branch",
   L7.apply(L7.globals["safe"], [e_val("n", 4, 200)], {}, 0).value == 25)

print("\nBranching on a Z condition spans both")
lo = e_val("a", 10, 200)
hi = e_val("b", 40, 180)
sp = branch(e_z("c", "sensor offline"), lambda: lo, lambda: hi, "r")
ok("spans rather than collapsing", not sp.is_z)
ok("state is Equivalence",         sp.state == State.EQUIV)
ok("lower bound held",             sp.lo == 10)
ok("upper bound held",             sp.hi == 40)
ok("width computed",               sp.width == 30)
ok("pi judges it",                 sp.pi_status() == "ENUMERATE")
ok("confidence floors at weaker",  sp.confidence == 180)
ok("reason names the condition",   "c" in sp.reason)

narrow = branch(e_z("c", "?"), lambda: e_val("a", 10, 200),
                lambda: e_val("b", 20, 200), "r")
ok("narrow span is acceptable",    narrow.pi_status() == "ACCEPTABLE")

wide = branch(e_z("c", "?"), lambda: e_val("a", 0, 200),
              lambda: e_val("b", 500, 200), "r")
ok("span past pi collapses to Z",  wide.is_z)
ok("collapse cites pi",            "pi threshold" in wide.reason)

agree = branch(e_z("c", "?"), lambda: e_val("a", "yes", 200),
               lambda: e_val("b", "yes", 190), "r")
ok("agreeing branches make the condition moot", not agree.is_z)
ok("agreement takes the value",    agree.value == "yes")

textual = branch(e_z("c", "?"), lambda: e_val("a", "x", 200),
                 lambda: e_val("b", "y", 200), "r")
ok("unspannable types yield Z",    textual.is_z)
ok("unspannable is unbounded",     textual.defect == Defect.UNBOUNDED)

zbranch = branch(e_z("c", "?"), lambda: e_z("a", "also unknown"),
                 lambda: e_val("b", 5, 200), "r")
ok("Z branch under Z condition is Z", zbranch.is_z)

print("\nThe chain rule")
ok("min over participants",
   chain([e_val("a", 1, 200), e_val("b", 2, 150), e_val("c", 3, 180)]) == 150)
ok("empty chain is zero",          chain([]) == 0)

print("\nEver stays pure")
L8 = Lambda()
L8.define("g", ["x"], "x + 1")
before = L8.globals["g"].confidence
L8.apply(L8.globals["g"], [e_val("x", 1, 200)], {}, 0)
ok("application does not mutate the function",
   L8.globals["g"].confidence == before)

print("\nLexical capture")
L9 = Lambda()
L9.globals["base"] = e_val("base", 100, 200)
L9.define("addbase", ["x"], "x + base")
ok("captures the enclosing binding",
   L9.apply(L9.globals["addbase"], [e_val("x", 5, 200)], {}, 0).value == 105)

print("\nUnbound names")
L10 = Lambda()
L10.define("h", ["x"], "x + nosuch")
res = L10.apply(L10.globals["h"], [e_val("x", 1, 200)], {}, 0)
ok("unbound name is Z",            res.is_z)
ok("unbound defect recorded",      res.defect == Defect.UNBOUND)

print(f"\n=== Abstraction layer: {passed} passed, {failed} failed ===\n")
raise SystemExit(0 if failed == 0 else 1)
