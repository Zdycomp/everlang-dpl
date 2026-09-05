#!/usr/bin/env python3
"""anchor_demo.py — depth is earned.

The one idea the whole Codric stack is built on, run rather than
described. Everything printed below is computed at run time.

    python3 examples/anchor_demo.py
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "2-interpreter-python"))

from abstract import (Lambda, DepthExceeded, a_anchor_fn,   # noqa: E402
                      E_DEPTH_CEILING)
from ever import e_val, State, Defect                        # noqa: E402


def call(lam, name, n):
    """Apply a function, reporting a depth halt as a halt, not a hang."""
    try:
        return lam.apply(lam.globals[name], [e_val("n", n, 200)], {}, 0)
    except DepthExceeded:
        return None


def line(label, text):
    print(f"  {label:<34} {text}")


print("\n" + "═" * 66)
print("  Depth is earned")
print("═" * 66)

# ── 1. Unanchored ────────────────────────────────────────────────
L = Lambda()
L.define("fact", ["n"], "if n <= 1 then 1 else n * fact(n - 1)")

print("\n1. Unanchored — the ceiling is ⌊π⌋ = %d\n" % E_DEPTH_CEILING)
line("def", "fact(n) = if n <= 1 then 1 else n * fact(n - 1)")
line("recursion detected", L.globals["fact"].value.recursive)
line("measure found", repr(L.globals["fact"].value.measure))

r3 = call(L, "fact", 3)
line("fact(3)", f"{r3.value}   — inside the ceiling")
r8 = call(L, "fact", 8)
line("fact(8)", "DepthExceeded — a checked halt, not a hang"
     if r8 is None else r8.value)

# ── 2. Earning the anchor ────────────────────────────────────────
print("\n2. Three Examples, then an anchor\n")
for arg, want in [(1, 1), (2, 2), (3, 6)]:
    L.example("fact", [arg], want)
    line(f"example fact({arg})", f"= {want}   ✓")

L.globals["fact"] = a_anchor_fn(L.globals["fact"])
line("state", L.globals["fact"].state.name)
line("reason", L.globals["fact"].reason)

# ── 3. Anchored ──────────────────────────────────────────────────
print("\n3. Anchored — the ceiling is gone\n")
for n in (8, 10, 20):
    got = call(L, "fact", n)
    line(f"fact({n})", got.value if got else "DepthExceeded")
line("deepest frame reached", L.max_depth_seen)
line("old ceiling", E_DEPTH_CEILING)

# ── 4. The rule that keeps it honest ─────────────────────────────
print("\n4. Confidence does not buy depth\n")
G = Lambda()
G.define("grow", ["n"], "if n > 99 then n else grow(n + 1)")
for arg, want in [(100, 100), (150, 150), (200, 200)]:
    G.example("grow", [arg], want)

g = G.globals["grow"]
line("def", "grow(n) = if n > 99 then n else grow(n + 1)")
line("every example passes", g.is_cleared)
line("confidence", f"{g.confidence}/256")
line("measure found", repr(g.value.measure))

refused = a_anchor_fn(g)
line("anchor →", "Z" if refused.is_z else "anchored")
line("defect", refused.defect.name if refused.is_z else "—")
line("reason", refused.reason)

print("\n" + "═" * 66)
print("  A function can sit high and still loop forever. Confidence is")
print("  evidence about correctness, and correctness is not termination.")
print("═" * 66 + "\n")

# Everything above is an assertion about the runtime, so assert it.
assert r3.value == 6
assert r8 is None
assert call(L, "fact", 20).value == 2432902008176640000
assert L.max_depth_seen > E_DEPTH_CEILING
assert refused.is_z and refused.defect == Defect.UNBOUNDED
assert L.globals["fact"].state == State.ANCHORED
print("  all demo claims asserted — ok\n")
