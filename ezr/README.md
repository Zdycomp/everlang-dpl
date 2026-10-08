# Ever

**A language where every value carries how much you trust it, and the
runtime refuses to compute with data that isn't trusted enough.**

Data from outside — an API, a scanner, a form — enters at 120 out of
256. The execute floor is 128. So it does not silently become a
plausible wrong number: it stays below the line until something
corroborates it.

```bash
./ever examples/weekly_sales.ever
```
```
total = z [0/256]          # Thursday was never recorded
best = 610 [256/256]
third_day = 380 [256/256]
```

One command for any example in this repo — `./ever` picks the runner
by the file's own extension (`.ever` → `ever_cli.py run`, `.ezr` →
`ezrun.py`), so running a program never means knowing which of the two
lineages it's written in first. Equivalent here to
`python3 2-interpreter-python/ever_cli.py run examples/weekly_sales.ever`
directly; `./ever` is the dispatch, not a third implementation.

Not a weekly total quietly missing a day. Put a real number in
Thursday's place and the same program gives `2615` at full confidence.

## The 30-second version: evidence buys confidence

This is the part that makes Ever different from `NULL` and `NaN`, and
it is worth the thirty seconds. A definition is a *claim*, so it starts
below the floor — unverified:

```bash
cd 2-interpreter-python
python3 ezrun.py ../examples/earned_trust.ever --call 'growth(100, 3)'
```
```
133.1  @ 120/256
```

The answer is right. It is just not worth anything yet, because nothing
has checked it. Supply witnesses — cases you claim it already gets right:

| witnesses supplied | result |
|---|---|
| none | `133.1  @ 120/256` |
| `growth(100,0) = 100` | `133.1  @ 120/256` — one proves nothing |
| `+ growth(100,1) = 110` | `133.1  @ 183/256` — **clears the floor** |
| `+ growth(100,2) = 121` | `133.1  @ 217/256` |
| one of the three wrong | `133.1  @ 122/256` — back below |
| the same case three times | `133.1  @ 120/256` — one witness, thrice |
| two answers for one case | refused, exit 2 |

The value never changes. What changes is what it is *worth*, and you
change that only with evidence from outside the program. Source code
does not get to vouch for itself.

Then there is depth. Unanchored recursion stops at ⌊π⌋ = 3:

```bash
python3 ezrun.py ../examples/earned_trust.ever -d 3 --call 'growth(100, 20)'
```
```
Z(unbounded) — depth ceiling 3 exceeded
  to lift it: growth decreases n in every self-call, so it can be
  anchored -- but anchoring needs the execute floor first, and it sits
  at 120/256. 2 more passing Examples clears 128, then pass -a growth
```

The refusal tells you what would lift it. Do those two things and it
runs to 20 levels and returns `672.7499949325598  @ 217/256`.

Confidence is evidence about *correctness*, which is not termination —
a function can sit at 240/256 and still loop forever. So depth is
bought separately, with a proof that some parameter decreases.

Every number on this page is pinned by `tests/examples_test.py`.

## What's actually here

**The language** is [`2-interpreter-python/`](2-interpreter-python/README.md) —
lexer, parser, semantic pass, evaluator, REPL, CLI. That is the thing.

It has **two runners**, and they are not rivals:

| | drives | use it for |
|---|---|---|
| `ever_cli.py run` | `runtime.run_source` | v4.10's OWN surface: statements, lists-by-indexing, loops, records, externs |
| `ezrun.py` | `syntax.py`'s `eval_ast` | the confidence algebra (`[EXAMPLE]`, `[ANCHOR]`) AND the forge's core in full: `let ... in`, list literals, `show`/`len`/`head`/`tail` |

They implement overlapping but different surfaces by design, not by
accident — see `FINDINGS.md` §7.4, §7.6 and §7.11. `ezrun.py` used to
run exactly one example in this repo; it runs five now, because the
core grammar it was missing (not a design choice, just unwritten) is
implemented. `ever_cli.py run` was never asked to learn that grammar in
return — its own list-by-indexing style is what `readings.ever`
demonstrates, on purpose, beside `readings.ezr`'s builtin-based twin.

**Everything else in this tree exists to cross-check that language**,
not to be used directly:

- `0-atom-c/`, `1-phase-cpp/` — the value domain and phase engine in C and C++
- `3-dsl-ruby/`, `4-archive-sql/` — the algebra as a Ruby DSL; the audit archive
- `5-runtime-java/` — a second full implementation sharing no code, plus
  `differential.py`, which runs one corpus through both as processes
- `7-forge/` — four lexers × five parsers against a shared corpus;
  converged at generation 72 over 564,600 fuzzed programs
- `edapt/` — the same "forgive, don't guess" discipline pointed at other languages

## The honest parts

- **Two lineages share this tree.** `differential.py` measures the
  split: **128 programs, 123 agreed, 5 diverged** — down from 31 once
  `eval_ast` learned the core's binding, lists and builtins (`FINDINGS.md`
  §7.11). The 5 left are real findings, not a missing feature: a
  numeric-precision limit past 2^53, two checks Java makes at compile
  time and Python defers to runtime, and two grammar questions where
  v4.10 permits what the forge's doctrine forbids. It is red on purpose.
  Which lineage the project keeps is still an open decision — this
  closed the accidental gap between them, not the deliberate one.
- **`sum.ezr`, `trust.ezr`, `largest.ezr`, `readings.ezr`** are written in
  that other lineage and run under `ezrun.py` directly now (no Java
  build needed) — see the two-runners table above.
- **Not production-ready for anything that isn't a demonstration.**
- **Not the first system to propagate uncertainty.** `NULL` and `NaN` do
  the mechanically same thing; `Uncertain<T>` (Bornholt et al.) and
  Julia's `Measurements.jl` do it with real statistical rigor —
  distributions, not one integer. Ever trades that rigor for a number
  anyone can read at a glance, and pushes the simplification further than
  the rigorous versions bothered to: into recursion depth, into foreign
  calls, into training loops.

## Verification

```bash
python3 tests/run_all.py          # 29 suites, the gate
python3 tests/examples_test.py    # 54 — every example does what it says
ever examples/trust.ezr           # or: one command, either lineage
./run.sh                          # the layers, skipping absent toolchains
```

Measured on the last run, not transcribed:

| | |
|---|---|
| `tests/run_all.py` | 29 suites |
| `tests/examples_test.py` | 54 passed |
| `tests/test_edapt.py` | 32 passed |
| `tests/test_backends.py` | 36 passed — **3 of 5 targets** (go, js, rust); R and Kotlin skip when `Rscript`/`kotlinc` are absent |
| `5-runtime-java/differential.py` | 128 programs, 123 agreed, 5 diverged — red on purpose |

`tests/assertion_counts.py --check` runs in the gate and fails it when a
document's assertion count stops matching a real run. That check exists
because five documents once transcribed the same number and four of them
were wrong.

Codric Enterprise · Ricky (Dreid) · 2026
