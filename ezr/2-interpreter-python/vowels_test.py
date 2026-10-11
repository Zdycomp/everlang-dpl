#!/usr/bin/env python3
"""vowels_test.py — Ever / Tapestry, vowel operator verification."""

from vowels import (
    Spec, Candidate, Ledger, Evolver, templates,
    i_implement, i_integrate, i_isolate, i_interject, i_inject,
    o_own, o_overcome, o_obliterate, o_optimize,
    u_understand, u_undermine, u_unwrap, u_ultracode,
)
from abstract import Lambda, Closure
from ever import e_val, e_z, State, Defect, E_CERTAIN, E_INTAKE

passed = failed = 0


def ok(name, cond):
    global passed, failed
    if cond:
        passed += 1; print(f"  \u2713 {name}")
    else:
        failed += 1; print(f"  \u2717 {name}")


print("\n=== Ever — the vowel operators ===\n")

FACT = Spec("fact", ["n"], [([1], 1), ([2], 2), ([3], 6), ([4], 24)])
SUM = Spec("tri", ["n"], [([1], 1), ([2], 3), ([3], 6), ([4], 10)])

print("The search space is bounded and stated")
t = templates(["n"], "fact", 2)
ok("templates generated",        len(t) > 100)
ok("includes identity",          "n" in t)
ok("includes recursion",         any("fact(" in x for x in t))
ok("bounded, not open-ended",    len(t) < 20000)

print("\nI \u2014 IMPLEMENT: synthesis from examples alone")
fn, tried = i_implement(FACT)
ok("synthesis succeeded",        not fn.is_z)
ok("produced a closure",         isinstance(fn.value, Closure))
ok("candidates were tried",      len(tried) > 100)
ok("some satisfied the spec",    any(c.satisfies for c in tried))
ok("winner satisfies all evidence", "4/4" in u_understand(fn).value)
ok("winner is recursive",        fn.value.recursive)
ok("winner has a measure",       fn.value.measure == "n")
ok("winner clears the floor",    fn.can_execute)

lam = Lambda()
lam.define("fact", ["n"], fn.value.body)
from ever import a_anchor
lam.globals["fact"] = a_anchor(lam.globals["fact"])
r = lam.apply(lam.globals["fact"], [e_val("n", 6, E_CERTAIN)], {}, 0)
ok("synthesised function computes fact(6)=720", r.value == 720)

tri, _ = i_implement(SUM)
ok("synthesises triangular numbers too", not tri.is_z)

impossible = Spec("nope", ["n"], [([1], 7), ([2], 13), ([3], 999999)])
bad, _ = i_implement(impossible)
ok("unsatisfiable spec yields Z",  bad.is_z)
ok("Z states what it reached",     "best was" in bad.reason)

print("\nI \u2014 INTEGRATE")
a = e_val("a", 42, 200)
b = e_val("b", 42, 180)
m = i_integrate(a, b, "m")
ok("agreement corroborates",     m.confidence > 200)
ok("value preserved",            m.value == 42)
d = i_integrate(e_val("a", 1, 200), e_val("b", 2, 100), "d")
ok("disagreement is held open",  d.state == State.EQUIV)
ok("disagreement is not averaged away", "disagree" in d.reason)
ok("cannot integrate through Z",
   i_integrate(a, e_z("u", "unknown"), "m").is_z)

print("\nI \u2014 ISOLATE")
iso = i_isolate(fn, "n - 1", "dec")
ok("fragment extracted",         not iso.is_z)
ok("fragment starts unverified", iso.confidence <= E_INTAKE)
ok("extraction does not transfer trust", iso.confidence < fn.confidence)
ok("missing fragment is Z",      i_isolate(fn, "zzz", "x").is_z)

print("\nI \u2014 INTERJECT")
seen = []
obs = i_interject(fn, lambda p: seen.append(p.ident), "watch")
ok("observer fired",             len(seen) == 1)
ok("value unchanged",            obs.value is fn.value)
ok("confidence unchanged",       obs.confidence == fn.confidence)
ok("semantically invisible",     obs.anchor_id == fn.anchor_id)

print("\nI \u2014 INJECT")
inj = i_inject(fn, {"base": e_val("base", 10, 90)}, "injected")
ok("injection succeeded",        not inj.is_z)
ok("capped by weakest binding",  inj.confidence == 90)
ok("cannot exceed what was fed in", inj.confidence < fn.confidence)
ok("cannot inject into a value",
   i_inject(e_val("x", 1, 200), {}, "y").is_z)

print("\nO \u2014 OWN")
led = Ledger()
owned = o_own(fn, led)
ok("ownership anchors",          owned.anchor_id != 0)
ok("entered the ledger",         len(led.owned) == 1)
ok("cannot own a Z",             o_own(e_z("u", "unknown"), led).is_z)

print("\nO \u2014 OPTIMIZE")
best, cand = o_optimize(tried, FACT)
ok("optimisation picked a winner", not best.is_z)
ok("winner satisfies the spec",  cand.satisfies)
sat = [c for c in tried if c.satisfies]
ok("chose the best fitness",
   all(cand.fitness >= c.fitness - 1e-9 for c in sat))
ok("shorter beats longer at equal confidence",
   all(cand.cost <= c.cost for c in sat
       if abs(c.confidence - cand.confidence) < 1))

print("\nO \u2014 OVERCOME")
lam2 = Lambda()
lam2.define("tri", ["n"], "n * 2")
for args, want in SUM.examples:
    lam2.example("tri", args, want)
weak = lam2.globals["tri"]
ok("the weak version fails its evidence", weak.confidence == 0)
better, _ = o_overcome(weak, weak, SUM)
ok("overcome produced something better", not better.is_z)
ok("it beats the incumbent",     better.confidence > weak.confidence)
ok("reason records the improvement", "overcame" in better.reason)

strong, _ = i_implement(SUM)
lateral, _ = o_overcome(strong, strong, SUM)
ok("refuses a lateral move",     lateral.is_z)
ok("says why it refused",        "not beating" in lateral.reason)

print("\nO \u2014 OBLITERATE: supersede, never delete")
led2 = Ledger()
marker = o_obliterate(weak, better, led2)
ok("marker is an EError",        marker.state == State.ERROR)
ok("marker keeps the value",     marker.value is weak.value)
ok("marker records where it stood", marker.lo == weak.confidence)
ok("marker names its successor", better.ident in marker.reason)
ok("ledger holds the marker",    len(led2.superseded) == 1)
ok("defect is overbound",        marker.defect == Defect.OVERBOUND)

print("\nU \u2014 UNDERSTAND")
acct = u_understand(fn)
ok("account produced",           not acct.is_z)
ok("names the body",             fn.value.body in acct.value)
ok("reports the measure",        "measure=n" in acct.value)
ok("reports the evidence",       "evidence" in acct.value)
ok("understands a Z too",        "Z:" in u_understand(e_z("u", "why")).value)
ok("understands a plain value",
   "int" in u_understand(e_val("x", 5, 200)).value)

print("\nU \u2014 UNDERMINE")
atk = u_undermine(fn, FACT)
ok("attack ran",                 atk is not None)
ok("silence is reported as Z, not as proof",
   (not atk.is_z) or "not a proof" in atk.reason)
weak_lam = Lambda()
weak_lam.define("div", ["n"], "10 / n")
bad_atk = u_undermine(weak_lam.globals["div"],
                      Spec("div", ["n"], [([1], 10)]))
ok("finds division by zero",     not bad_atk.is_z)
ok("names the breaking input",   any("[0]" in b for b in bad_atk.value))
ok("cannot undermine a value",
   u_undermine(e_val("x", 1, 200), FACT).is_z)

print("\nU \u2014 UNWRAP")
parts = u_unwrap(fn)
ok("decomposed",                 len(parts) >= 3)
ok("condition extracted",        any("condition" in p.ident for p in parts))
ok("branches extracted",         any("then" in p.ident for p in parts)
                                 and any("else" in p.ident for p in parts))
ok("parts start unverified",     all(p.confidence <= E_INTAKE for p in parts))

print("\nU \u2014 ULTRACODE")
lam3 = Lambda()
lam3.define("tri", ["n"], "((n * 1) + 0) * 1")
for args, want in [([1], 1), ([2], 2)]:
    lam3.example("tri", args, want)
padded = lam3.globals["tri"]
ultra = u_ultracode(padded, Spec("tri", ["n"], [([1], 1), ([2], 2)]))
ok("compression ran",            not ultra.is_z)
ok("result is no longer",
   len(ultra.value.body.replace(" ", "")) <=
   len(padded.value.body.replace(" ", "")))
already = u_ultracode(fn, FACT)
ok("already-minimal is reported honestly",
   "minimal" in already.reason or "ultracoded" in already.reason)

print("\nThe loop")
spec2 = Spec("fact", ["n"], [([1], 1), ([2], 2), ([3], 6)])
ev = Evolver(spec2)
hist = ev.run(2)
ok("generations recorded",       len(hist) == 2)
ok("a body was produced",        hist[0].body != "")
ok("confidence earned",          hist[0].confidence > 0)
ok("ledger tracked ownership",   len(ev.ledger.owned) > 0)
ok("stability is reported honestly",
   hist[1].confidence >= hist[0].confidence)

print("\nThe consensus oracle")
ev2 = Evolver(Spec("fact", ["n"], [([1], 1), ([2], 2), ([3], 6)]))
fn2, tried2 = i_implement(ev2.spec)
ev2.satisfying = [c.body for c in tried2 if c.satisfies]
ev2.incumbent = fn2
ok("multiple independent solutions", len(ev2.satisfying) >= 3)
ok("consensus derives fact(7)",  ev2.oracle(7) == 5040)
ok("consensus derives fact(5)",  ev2.oracle(5) == 120)

ev3 = Evolver(Spec("amb", ["n"], [([1], 1), ([2], 2)]))
_, tried3 = i_implement(ev3.spec)
ev3.satisfying = [c.body for c in tried3 if c.satisfies]
disagreed = ev3.oracle(9)
ok("withholds where solutions disagree",
   disagreed is None or isinstance(disagreed, (int, float)))

print(f"\n=== Vowel operators: {passed} passed, {failed} failed ===\n")
raise SystemExit(0 if failed == 0 else 1)
