# Ever — Notebook Batch Results

**13 cells, most of them wrong on purpose. Codric Enterprise · 2026**

Every cell stated what *should* happen before Ever saw it. Ever then ran
for real. Producing the right answer for the wrong reason scores as a
miss; refusing when refusing was correct scores as a hit.

## Final: 13/13 — but the first run was 10/12

The number that matters is not the final one. It is what the misses were.

| | first run | after fixes |
|---|---|---|
| synthesis | 5/6 | 7/7 |
| inspection | 5/6 | 6/6 |
| **overall** | **10/12** | **13/13** |

Six cells also crashed on the first attempt — **my harness bug**, an
`EState` import that does not exist. Not Ever's failure, and worth
separating from the two that were.

---

## What Ever got right unprompted

| Cell | Task | Result |
|---|---|---|
| 1 | Spec claiming `f(2)=4` **and** `f(2)=5` | **REFUSED** — 816 candidates, none satisfied |
| 2 | Factorial from 4 examples | `if n < 1 then 1 else n * fact(n-1)` @ 235/256 |
| 10 | Triangular numbers from 4 examples | `if n < 0 then 0 else n + tri(n-1)` @ 235/256 |
| 12 | `1, 4, 9, 17` — the 17 breaks the squares | **REFUSED** |
| 3 | Broken C | missing semicolon + `gets()` overflow, 18/256 |
| 6 | Broken Python | mutable default, `eval`, bare except → **Z** |
| 8 | Broken Java | unguarded null, `==` on strings → 3/256 |
| 9 | Broken Ruby | missing `end`, global, bare rescue → **Z** |
| 11 | Broken HTML | no alt, unlabelled input, `target=_blank` → **Z** |

Refusing cells 1 and 12 is the harder half of that list. A synthesiser
that always returns *something* is worse than useless on a contradictory
spec.

---

## Miss 1 — a real Ever bug, now fixed

**Cell 4, broken SQL.** Ever caught the injection, the `SELECT *`, the
unguarded `DROP`, and the `JOIN` without `ON`. It **missed
`DELETE FROM sessions`** — the most destructive statement in the sample.

Cause: the inspector tested for `WHERE` across the **entire input**
rather than per statement. A `WHERE` in an unrelated `SELECT` masked
every unbounded `DELETE` in the file.

```python
# before — one WHERE anywhere clears the whole file
if DELETE|UPDATE in code and WHERE not in code: flag()

# after — per statement
for stmt in code.split(";"):
    if DELETE|UPDATE in stmt and WHERE not in stmt: flag()
```

Now catches 5 of 5. This is exactly the class of defect the batch exists
to surface: a rule that looks right, passes its own unit test, and fails
on realistic input.

---

## Miss 2 — not a bug. The important finding.

**Cell 7, the first four primes.** Ever returned:

```ever
if n < 0 then 1 else n + prime(n - 2)
```

which produces `2, 3, 5, 7, 10, 13, 17, 21`.

It fits all four examples **exactly** and diverges at n=5. And it
reported **235/256** — above the execute floor — for a function that is
wrong everywhere past the evidence.

**My expectation was the thing that was wrong.** Nothing in the spec said
*prime*. Four points were given and a function fitting four points was
returned. The failure was not that Ever answered; it was that its
confidence did not reflect how little four points determine.

### The fix: measure agreement beyond the evidence

Ever already had the mechanism. After synthesis, poll every candidate
that satisfied the same examples on inputs **nobody supplied**. Where
they agree, the evidence determined the shape. Where they scatter, it did
not, and confidence must say so.

```
consensus = agreement among satisfying solutions on unseen inputs
confidence = fit × consensus
```

Measured:

| Spec | Satisfying | Agreement | Confidence |
|---|---|---|---|
| `g(2)=6` — one example | 34 | 38% | 235 → **45** |
| `h(1)=2, h(2)=4` | 32 | 55% | 235 → **100** |
| `sq(1)=1, sq(2)=4` | 5 | 80% | 235 → **146** |
| `fact`, 4 examples | 10 | 100% | **235** |

One example now caps at 45/256 — far below the floor — because 34
different functions fit it and they agree barely a third of the time.
That is the correct report.

### Where the fix does not reach, stated plainly

It did **not** rescue cell 7. The three satisfying candidates were:

```
if n <= 0 then 1 else n + prime(n - 2)
if n <  0 then 1 else n + prime(n - 2)
if n <  1 then 1 else n + prime(n - 2)
```

The *same wrong formula* with trivially different base cases. They agree
because the grammar can only express one shape here.

**Consensus measures agreement among what the grammar can say, not
correctness.** When the grammar cannot express the intended function,
every candidate is the same wrong thing and they all agree confidently.
That is a limitation of bounded synthesis, not a defect to patch, and it
is the honest boundary of the current system.

---

## Cell 13, added because of cell 7

A single example, `g(2)=6`. Ever fits it and **caps below the execute
floor**. Fitting one point is not knowledge, and the language now says so
in the only currency it has.

---

## For the refinement layer

Three things these results say about what needs building:

1. **Fit and generalisation are different quantities, and only fit was
   being measured.** Consensus is a start; a hold-out split would be
   stronger.
2. **Grammar coverage bounds everything.** No amount of confidence
   machinery rescues a spec the grammar cannot express. Expanding the
   grammar and *detecting when a spec is outside it* are separate jobs
   and both are missing.
3. **Rules that pass unit tests still fail on realistic input.** The SQL
   bug survived 56 passing archive assertions. Adversarial batches like
   this one find what unit tests do not.

---

## Persistence

Every cell run is archived to `archive/notebook.db` with its expectation,
its result, and its verdict — so the next batch can be compared against
this one rather than against memory.
