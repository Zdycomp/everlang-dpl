# 4Ever — The Zeroth Law

**Codric Enterprise · Ricky (Dreid) · 2026**

> If two threads are each in equilibrium with a third, they are in
> equilibrium with each other.

Everything below was computed. Run `python3 tests/test_zeroth.py`.

---

## 1. Why there has to be a Zeroth

`FINDINGS.md` §1 gives the **First Law**: uncertainty is the conserved
quantity, and corroboration is exactly `u_result = u_a × u_b`, verified
1089/1089. §1 also gives the **Third**, and honestly reports that it
breaks — absolute zero is unreachable in finite steps, but Z is
reachable instantly by contagion.

Both of those laws are about *combination*. Neither of them establishes
that confidence is a **comparable quantity** in the first place.

Thermodynamics hit the same gap and answered it the same way. The Zeroth
Law was named last and numbered first because the three that came before
it had all quietly assumed the thing it states: that thermal equilibrium
is *transitive*. Without that, two thermometers can each agree with a
third and disagree with each other, and "temperature" is not a property
of anything — it is a reading on a particular instrument.

4Ever had the same hole. Six layers compared confidence to confidence
and no layer said what made the comparison legitimate.

---

## 2. What was already there, and why it could not carry the law

Layers 1 and 5 both defined the same predicate:

```cpp
bool PhaseEngine::sameSpectrum(const e_particle& a, const e_particle& b) {
    return std::abs((int)a.confidence - (int)b.confidence) < E_PI_WIDTH_WARN;
}
```

Two threads are "in the same spectrum" when the gap between them is
narrower than ⌊256/π⌋ = 81. That is a **tolerance relation**: reflexive
and symmetric, and *not transitive*.

The counterexample is small enough to check by hand:

| pair    | gap | within 81? |
|---------|-----|------------|
| 0 ~ 1   | 1   | yes        |
| 1 ~ 81  | 80  | yes        |
| 0 ~ 81  | 81  | **no**     |

Measured across the whole scale, exhaustively:

```
proximity |a-b| < 81: 969,840 of 4,922,897 triples break the chain  (19.7%)
```

Nearly one candidate triple in five. Not an edge case — a fifth of the
relation.

**This was not a bug in `sameSpectrum`.** Proximity is a perfectly good
answer to "are these two near each other," which is a fair question. The
defect was that nothing else existed, so the only comparison predicate
in the system was one that could not be chained — and a predicate that
cannot be chained cannot license a scale.

There was a second, quieter finding. `sameSpectrum` had exactly one
caller:

```cpp
return a.confidence == b.confidence && sameSpectrum(a, b);
```

Equal confidences have a gap of 0, which is inside any width, so the
second clause could never change the answer. The only comparison
predicate in the corpus was both non-transitive *and* inert at its only
call site.

---

## 3. The law, implemented

Equilibrium is **equality of band**:

```c
e_band_id e_band(int16_t confidence);
int e_equilibrium(const e_particle *a, const e_particle *b) {
    return e_band(a->confidence) == e_band(b->confidence);
}
```

`e_band` is a **total function** of confidence. That single fact is what
makes the law hold, because `a ~ b ⟺ f(a) = f(b)` — the kernel of a
function — is an equivalence relation by construction. Reflexivity,
symmetry and transitivity are not properties to be tested and hoped for;
they follow from `f` being a function at all.

So the thing to protect is not the relation. It is the totality and
single-valuedness of `e_band`, and that is what every layer's test
actually checks.

### The bands

Six, and every boundary is a constant the scale already had. Nothing
here is chosen.

| Band          | Range   | Boundary from                             |
|---------------|---------|-------------------------------------------|
| `Z`           | 0       | zero-absolute. Its own state, never a low band. |
| `Vestigial`   | 1–24    | below ⌊256/π²⌋ = 25 — too thin to enumerate |
| `Approaching` | 25–80   | below ⌊256/π⌋ = 81 — approaching Z         |
| `Subfloor`    | 81–127  | below 256/2 = 128 — present, may not execute |
| `Executable`  | 128–255 | cleared to execute, not verified           |
| `Certain`     | 256     | 4⁴ exactly — earned, never inferred        |

Two of those bands are singletons, and that is the point rather than an
accident:

- **Z is alone in its band.** This is the structural statement of "Z is
  not a low confidence." Under proximity, Z at 0 was in the same
  spectrum as a thread at 80 — which is exactly the laundering the
  language exists to prevent.
- **Certain is alone in its band.** 255 and 256 are *not* in
  equilibrium. Proximity said they were, with a gap of 1. This lines up
  with `FINDINGS.md` §1: Certain is formally unreachable by combination,
  so it must not be reachable by comparison either.

---

## 4. The law under translation

This is where the Zeroth Law stops being bookkeeping and says something.

`a_assimilate` carries a thread into another language. An anchored
thread crosses without loss. An unanchored one pays **1 confidence per
crossing**, so drift is visible rather than silent.

One point of confidence is usually nothing. It is not nothing when the
thread is standing on the lowest value of its band:

```
  edge thread at 128 (Executable, the band floor)
    unanchored → 127 → Subfloor.   band changed.  equilibrium lost.
    anchored   → 128 → Executable. band held.     equilibrium survives.
```

Two threads that were comparable at home are not comparable abroad —
and nothing in the old code could have detected that, because the old
comparison predicate had no notion of a boundary to cross.

So:

> **The Zeroth Law survives assimilation exactly for anchored threads.**

Which is the same sentence the language has been saying at every other
scale. `fact` earns unbounded depth by passing three Examples and
proving a decreasing measure. A fixture earns rulehood by recurring
across three distinct sources and surviving replay. And a thread earns
the right to mean the same thing in another language by being anchored.

**Depth is earned. So is comparability.**

Verified end to end through the real operator, not a model of it —
`0-atom-c/tapestry_test.c` builds the edge thread, anchors it, runs both
through `a_assimilate`, and checks the bands on the far side.

---

## 5. What each layer contributes

The law is stated in four languages, and the point of stating it four
times is that they can be checked against each other.

| Layer            | Adds                                                                    |
|------------------|-------------------------------------------------------------------------|
| 0 · C            | `e_band`, `e_equilibrium`, `e_equilibrium_survives_crossing`. The atom owns the scale, so it owns the law. |
| 1 · C++          | `PhaseEngine::equilibrium`. `sameSpectrum` kept and re-documented as proximity. |
| 2 · Python       | `Band`, `e_band`, `E.band`, `same_spectrum` — the reference reading.    |
| 4 · SQL          | `ever_band`, `v_band_drift`, `v_at_risk`, and four triggers.            |
| 5 · Java         | `EverRuntime.Band`, `band`, `equilibrium`.                              |

**Only Layer 4 can refuse.** Everywhere else the law is a predicate a
caller may forget to consult. In the archive it is a constraint at the
storage boundary:

- an **anchored crossing that changed band** is refused — the Zeroth Law
  form of `trg_anchor_holds`, and the stronger claim, because what must
  be preserved is comparability, not merely the number
- a confidence outside 0..256 is refused — it has no band, so it cannot
  be compared to anything
- `UPDATE` and `DELETE` on `ever_band` are refused — editing a boundary
  to overlap its neighbour would silently destroy transitivity in every
  view above it

An **unanchored** crossing that changes band is *allowed*, and lands in
`v_band_drift` naming both bands. Drift that is recorded is the design.
Drift that is silent is the failure.

`v_at_risk` names the threads sitting exactly on a band floor,
unanchored — one hop from demotion. Naming them is cheaper than
discovering them.

---

## 6. Verified

```
python3 tests/test_zeroth.py
```

| Check                                            | Result       |
|--------------------------------------------------|--------------|
| band total on 0..256                             | 257 / 257    |
| reflexive                                        | all 257      |
| symmetric                                        | all 66,049 pairs |
| transitive                                       | every triple |
| proximity is *not* transitive                    | 969,840 / 4,922,897 |
| Python and C agree                               | 257 / 257    |
| Python and SQL agree                             | 257 / 257    |
| Python and Java agree                            | 257 / 257    |
| all four agree on every boundary                 | yes          |
| `pauliCollision` unchanged by the switch         | all 66,049 pairs |

Per-layer assertion counts: C 107 (was 88), C++ 61 (was 50), Java 86
(was 78), SQL-zeroth 37, cross-layer 18.

Agreement is the check that matters. A law five layers each hold
privately is five laws.

---

## 7. What is not claimed

- **That the boundaries are optimal.** They are *derived* — every one is
  a constant the scale already used — which is a weaker and more honest
  claim than "correct." Whether ⌊256/π⌋ is the right place for a
  comparability boundary is unmeasured, and it joins the open questions
  rather than pretending to be settled.
- **That six bands is the right number.** It is the number the existing
  constants produce. A corpus large enough to measure band occupancy
  might argue for more or fewer.
- **That proximity should be deleted.** It answers a real question and
  it is kept, tested, and now correctly labelled. The defect was never
  that proximity existed; it was that nothing else did.
- **That this rescues the Third Law.** It does not. `FINDINGS.md` §1 is
  still right that the thermodynamic analogy holds for the First and
  breaks for the Third. The Zeroth holds because it was *built* to hold,
  not because the analogy carried it there.
