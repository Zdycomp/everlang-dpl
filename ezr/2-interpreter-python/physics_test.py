#!/usr/bin/env python3
"""physics_test.py — EZR, the six laws and ultra-anchored recursion."""

import sys

sys.set_int_max_str_digits(200000)

from abstract import E_HARD_DEPTH, Lambda, a_anchor_fn
from audit import HOLDS, OVERSTATED, UNDERSTATED, run as run_audit
from ever import E_CERTAIN, E_ZERO, e_val, excel
from physics import (LAWS, Disposition, Subsystem, acceleration, derive_from,
                     entropy, inertia, push, temperature)
from ultra import DEFAULT_STACK_MB, deep, qualifies, run_ultra, ultra_anchor

passed = failed = 0


def ok(name, cond):
    global passed, failed
    if cond:
        passed += 1; print(f"  ✓ {name}")
    else:
        failed += 1; print(f"  ✗ {name}")


print("\n=== EZR — thermodynamics, Newton, and ultra-anchoring ===\n")

print("1. ENTROPY")
z = e_val("z", 1, E_ZERO)
certain = e_val("c", 1, E_CERTAIN)
mid = e_val("m", 1, 128)
ok("u = 1 at Z",                    entropy(z) == 1.0)
ok("u = 0 at Certain",              entropy(certain) == 0.0)
ok("u = 1/2 at the execute floor",  abs(entropy(mid) - 0.5) < 1e-9)
ok("temperature is 1 - u",          abs(temperature(mid) - 0.5) < 1e-9)

print("\n2. FIRST LAW — nothing is created or destroyed")
s = Subsystem("test")
a = s.admit(e_val("a", 1, 200))
b = s.admit(e_val("b", 1, 120))
out = derive_from(a, ident="out", confidence=120, reason="chained")
s.derive([a, b], out)
ok("inputs are marked utilised",
   all(s._index[id(x)].disposition is Disposition.UTILISED for x in (a, b)))
ok("the result is resident",
   s._index[id(out)].disposition is Disposition.RESIDENT)
ok("every thread has a disposition",
   sum(s.balance()[d.value] for d in Disposition) == len(s.entries))
ok("conservation holds",            not s.first_law())

old = s.admit(e_val("old", 1, 90))
s.supersede(old, out)
ok("a superseded thread is recycled, not removed",
   s._index[id(old)].disposition is Disposition.RECYCLED)
ok("and it is in the archive",      len(s.archive) == 1)
ok("recycled and archived agree",   not s.first_law())

print("\n3. SECOND LAW — entropy does not fall on its own")
ok("chaining raises u to the worst input",
   entropy(out) >= max(entropy(a), entropy(b)))
ok("the subsystem agrees",          not s.second_law())
bad = Subsystem("perpetual")
x = bad.admit(e_val("x", 1, 100))
y = bad.admit(e_val("y", 1, 100))
free = derive_from(x, ident="free", confidence=250, reason="from nowhere")
bad.derive([x, y], free)
ok("a free confidence gain is caught", bool(bad.second_law()))

print("\n4. THIRD LAW — Certain is unreachable by combination")
ok("excel(255, 255) stops at 255",  excel(255, 255) == 255)
ok("nothing on the grid reaches Certain",
   max(excel(p, q) for p in range(0, 256, 5) for q in range(0, 256, 5))
   < E_CERTAIN)
ok("the subsystem agrees",          not s.third_law())

print("\n5. NEWTON I — no thread moves unless acted on")
subject = e_val("subject", 1, 200)
before = (subject.confidence, subject.generation, subject.reason)
moved = push(subject, -50.0, "test")
ok("the original is untouched",
   (subject.confidence, subject.generation, subject.reason) == before)
ok("the result is a different thread", moved is not subject)
ok("and it records why it moved",   "test" in moved.reason)

print("\n6. NEWTON II — the same force, different mass")
fresh = e_val("fresh", 1, 200)
attested = e_val("attested", 1, 200)
attested.generation, attested.ascend_points, attested.anchor_id = 2, 3, 7
ok("a fresh thread has mass 1",     inertia(fresh) == 1.0)
ok("evidence is mass",              inertia(attested) > inertia(fresh))
ok("an anchor counts toward mass",  inertia(attested) == 1 + 2 + 3 + 3)
ok("a = F / m",                     acceleration(fresh, -40) == -40.0)
ok("mass resists the same force",
   abs(acceleration(attested, -40)) < abs(acceleration(fresh, -40)))
ok("the fresh thread moves further",
   (200 - push(fresh, -40.0).confidence)
   > (200 - push(attested, -40.0).confidence))
ok("counter-evidence never goes below zero",
   push(fresh, -100000.0).confidence == E_ZERO)
ok("corroboration never reaches Certain",
   push(fresh, 100000.0).confidence < E_CERTAIN)

print("\n7. NEWTON III — every action has its record")
ok("a supersession names a replacement", s.archive[0][1] is out)
ok("nothing supersedes itself",     not s.newton_third())
self_sup = Subsystem("self")
q = self_sup.admit(e_val("q", 1, 100))
self_sup.supersede(q, q)
ok("superseding itself is caught",  bool(self_sup.newton_third()))

print("\n8. THE SUBSYSTEM AS A WHOLE")
ok("all six laws hold",             not s.audit())
ok("six laws are named",            len(LAWS) == 6)
_rep = s.report()
ok("the report names the balance",
   all(k in _rep for k in ("created", "utilised", "recycled", "resident")))
ok("and says the laws hold",        "all six hold" in _rep)
ok("a broken subsystem says so",    bool(bad.audit()))

print("\n9. ULTRA-ANCHORED RECURSION")
lam = Lambda()
lam.define("fact", ["n"], "if n <= 1 then 1 else n * fact(n - 1)")
fp = lam.globals["fact"]
ok("an unanchored function does not qualify", not qualifies(fp, fp.value)[0])
ok("and it says depth is earned",
   "earned" in qualifies(fp, fp.value)[1])

lam.define("flat", ["n"], "n + 1")
flat = lam.globals["flat"]
ok("a non-recursive function gains nothing",
   not qualifies(flat, flat.value)[0])

for arg, want in [(1, 1), (2, 2), (3, 6)]:
    lam.example("fact", [arg], want)
lam.globals["fact"] = a_anchor_fn(lam.globals["fact"])
fp = lam.globals["fact"]
ua, why = ultra_anchor(fp, fp.value)
ok("an anchored function qualifies", ua is not None)
ok("on its proven measure",          why == "n")

plain = lam.eval("fact(1000)", {}, 0, "t")
ok("depth 1000 is refused unprovisioned", plain.is_z)
ok("and the refusal is a Z, not a raise", plain.defect is not None)

lifted = run_ultra(ua, lam.eval, "fact(1000)", {}, 0, "t")
ok("and delivered under an ultra-anchor", not lifted.is_z)
ok("with the right answer",
   len(str(lifted.value)) == 2568)

near = run_ultra(ua, lam.eval, "fact(3900)", {}, 0, "t")
ok("depth 3900 computes",            not near.is_z)
over = run_ultra(ua, lam.eval, "fact(5000)", {}, 0, "t")
ok("past EZR's own ceiling it refuses", over.is_z)
ok("so the ceiling is EZR's, not CPython's", E_HARD_DEPTH == 4000)
ok("the subsystem stayed conserved",  not ua.audit())

print("\n10. DEEP EXECUTION")
res = deep(lambda: sum(range(100)))
ok("deep returns a value",          res.ok and res.value == 4950)
bad_res = deep(lambda: 1 / 0)
ok("and relays an error rather than raising",
   not bad_res.ok and isinstance(bad_res.error, ZeroDivisionError))
ok("a stack is reserved up front",  DEFAULT_STACK_MB >= 64)

print("\n11. THE VARIANCE AUDIT")
findings = run_audit(verbose=False)
over_f = [f for f in findings if f.verdict == OVERSTATED]
ok("the audit runs",                len(findings) > 10)
ok("nothing is overstated",         not over_f)
ok("every finding cites a source",  all(f.source for f in findings))
ok("and carries its evidence",      all(f.evidence for f in findings))

print(f"\n=== Physics: {passed} passed, {failed} failed ===\n")
raise SystemExit(0 if failed == 0 else 1)
