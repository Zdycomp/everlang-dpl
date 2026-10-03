# 4Ever

**Codric Enterprise · Ricky (Dreid) · 2026**

**E-verified.** One repository, eight layers, one idea:

> **Depth is earned.** Nothing gets to go deeper, travel further, or
> become a rule than its evidence has paid for.

That sentence starts as a rule about recursion and ends as a product
that fixes Gradle builds. This repo is the whole distance.

*The name carries the scale it measures on: **4** for 4⁴ = 256, the
states of a byte; **Ever** for the language; and together, for the one
promise the archive makes — nothing is ever deleted.*

```bash
python3 tests/run_all.py
```

**34 suites · 34 passed · 0 skipped · 0 failed · 1,385 counted assertions**
— macOS, 2026-09-05. Layers whose toolchain is missing report SKIP;
they never report PASS.

---

## Start here

```bash
python3 examples/anchor_demo.py
```

`fact(8)` halts unanchored. Three passing Examples and an anchor later,
`fact(20)` computes at frame 19. Then `grow`, sitting at **217/256**
with every example passing, is **refused** an anchor — because it has no
decreasing measure, and confidence proves trust, not termination.

That refusal is the thesis. Everything else is that rule at a different
scale.

---

## The scale

```
0 ─────────────────────────────────────────────────── 256
Z                        128                     Certain
unknown              execute floor              verified
```

**256** because 4⁴ — the states of a byte. **Z is not low confidence.**
It is its own state, it carries the reason it is unknown, and it is
contagious: anything touching Z becomes Z.

Every constant is derived, not chosen:

| Constant             | Value | Derivation      |
|----------------------|-------|-----------------|
| Certain              | 256   | 4⁴              |
| Execute floor        | 128   | 256 / 2         |
| Approaching-Z        | 81    | ⌊256 / π⌋       |
| Enumerate threshold  | 25    | ⌊256 / π²⌋      |
| Emulate ceiling      | 3     | ⌊π⌋             |
| Intake               | 120   | pre-evidence    |
| Repair, plain        | 8     | 256 / 32        |
| Repair, inferred     | 32    | 256 / 8         |

And Z-contagion turns out not to be a rule at all. Let
`u = (256 − confidence) / 256`. Corroboration is *exactly*
`u_result = u_a × u_b` — verified across the full grid, 1089/1089. Z has
`u = 1`, and `1 × x = 1` for every x. Z absorbs because it is the
absorbing element under multiplication. It was designed in as a
decision and turned out to be a theorem. See [`docs/FINDINGS.md`](docs/FINDINGS.md).

---

## The Zeroth Law

> If two threads are each in equilibrium with a third, they are in
> equilibrium with each other.

The First Law says what happens when evidence combines. The Zeroth says
confidence is a **comparable quantity at all** — and it is numbered
first because everything above it had quietly assumed it. Thermodynamics
did the same thing for the same reason: without transitive equilibrium,
two thermometers can each agree with a third and disagree with each
other, and temperature is not a property of anything.

4Ever had that hole. Six layers compared confidence to confidence, and
the only predicate for it was:

```cpp
std::abs(a.confidence - b.confidence) < E_PI_WIDTH_WARN   // < 81
```

Proximity. Reflexive, symmetric, and **not transitive**: `0~1` and
`1~81`, while `0!~81`. Measured over the whole scale, **969,840 of
4,922,897 candidate triples break the chain — 19.7%**. A predicate that
cannot be chained cannot license a scale.

So equilibrium is now equality of **band**, and band is a *total
function* of confidence. That one fact is the whole proof: `a ~ b ⟺
f(a) = f(b)` is an equivalence relation by construction, not by luck.

| Band          | Range   | Boundary from                         |
|---------------|---------|---------------------------------------|
| `Z`           | 0       | its own state, never a low band       |
| `Vestigial`   | 1–24    | below ⌊256/π²⌋ = 25                   |
| `Approaching` | 25–80   | below ⌊256/π⌋ = 81                    |
| `Subfloor`    | 81–127  | below 256/2 = 128                     |
| `Executable`  | 128–255 | cleared to execute, not verified      |
| `Certain`     | 256     | 4⁴ exactly                            |

Z and Certain are singletons, and that is the point: **255 and 256 are
not in equilibrium.** Proximity said they were, with a gap of 1 — which
is the same laundering `FINDINGS.md` §1 caught when `excel(250,250)`
returned 256.

**And the law travels exactly as far as an anchor does.** An unanchored
thread pays 1 confidence per language crossing. On a band floor, that
one point demotes it — two threads comparable at home are not comparable
abroad. Anchored threads cross without loss and hold their band.

> Depth is earned. So is comparability.

Stated in C, C++, Python, SQL and Java; all four testable
implementations checked against each other and **agreeing on all 257
values**. Only the archive can *refuse* — an anchored crossing that
changed band is rejected at the storage boundary. See
[`docs/ZEROTH.md`](docs/ZEROTH.md).

---

## The nine layers

Each language does the thing it is actually best at.

|   | Layer                  | Language | Role                                                     | Verified            |
|---|------------------------|----------|----------------------------------------------------------|---------------------|
| 0 | `0-atom-c`             | C        | The particle. C owns memory, so C owns the atom.          | 107 · 98 · 70       |
| 1 | `1-phase-cpp`          | C++      | The phase engine. What happens when two particles meet.   | 61                  |
| 2 | `2-interpreter-python` | Python   | The language. Lexer, parser, semantics, evaluator, REPL.  | 91 · 74 · 83 · 79 … |
| 2 | `2-inspect-python`     | Python   | The polyglot source inspector. Any language → particles.  | 62                  |
| 3 | `3-dsl-ruby`           | Ruby     | The DSL. Where Ever becomes a language you write.         | runs clean          |
| 4 | `4-archive-sql`        | SQL      | The archive. C² is a join, not a loop.                    | 56 · 55 · 37        |
| 5 | `5-runtime-java`       | Java     | The runtime. Guardrails that travel into someone's build. | 86                  |
| 6 | `6-interface-html`     | hand HTML| The interface. No framework, no CDN, no build step.       | 39                  |
| 7 | `7-refix-node`         | Node     | **ReFix.** The idea, pointed at somebody else's Gradle.   | 17                  |
| 8 | `8-finality`           | Python + Go/Rust | Finality drive. Reference agreement for release targets. | 7 + toolchain status |

Cross-layer agreement: **11/11**. Python and the browser produce
identical particles for identical input — because an instrument you
cannot inspect is not an instrument, it is a claim.

---

## Layer 7 — what the idea is for

ReFix matches Gradle build errors against a signature corpus, archives
every accepted repair as a `(Failure, Fixture)` pair, and synthesizes a
new rule **only** when the same fixture recurs across `E_ASCEND_POINTS = 3`
*distinct sources* and then replays against the entire archive without
changing a single prior outcome.

```
refix scan <build.log>              — what signatures match?
refix accept <build.log> <src-id>   — archive matches as accepted repairs
refix candidates                    — fixtures that cleared the threshold
refix propose                       — attempt admission; replay-gated
refix rules                         — admitted & rejected rules
```

Three distinct sources, not three rows: ten repairs in one repository is
one habit, not a rule. A rule is born at intake (120), below the execute
floor, and rises to 128 only by surviving replay. **A rejected rule is
kept forever with its reason.**

That is `[ANCHOR-⊥]` again. `fact` had to pass three Examples before it
earned unbounded depth; a fixture has to recur across three independent
sources before it earns rulehood. Same gate, seven layers apart.

The archive lives as append-only JSONL so one developer needs no
database to start — and as [`4-archive-sql/repair.sql`](4-archive-sql/repair.sql)
for when it outgrows one machine. Nine triggers enforce in the database
exactly what `src/archive.js` enforces in JavaScript, because an
invariant that holds in only one implementation is not an invariant, it
is a convention.

---

## What is not claimed

- **General program synthesis.** `implement` searches a bounded grammar
  — arithmetic to depth 2 and single recursion — and the bound is
  stated so what it cannot reach is stated too.
- **Correctness proofs.** `undermine` finds counterexamples. It returns
  **Z** when it finds none, because *no counterexample found* is not a
  proof and must not be dressed as one.
- **Unbounded self-improvement.** The loop converges and reports
  convergence rather than churning to look busy.
- **φ governing the corpus.** 1 of 6 ratios lands near φ, which is what
  chance would give. φ earns its place as the output equalizer, applied
  deliberately — not as a law the corpus obeys.
- **Production readiness.** Not for anything that isn't a demonstration.
- **A trained ReFix corpus.** The archive starts empty. Users build the
  moat.

---

## Documentation

| Document                                       | What it holds                                                 |
|------------------------------------------------|---------------------------------------------------------------|
| [`docs/SEMANTICS.md`](docs/SEMANTICS.md)       | Operational semantics. The `[ANCHOR-⊥]` rule lives in §4.4.   |
| [`docs/VOWELS.md`](docs/VOWELS.md)             | The I/O/U operators and the self-generating loop.             |
| [`docs/FINDINGS.md`](docs/FINDINGS.md)         | Research results. Conservation, the φ audit, defect profile.  |
| [`docs/PIPELINE.md`](docs/PIPELINE.md)         | Lexer → parser → checker → execution. Every stage returns E<T>. |
| [`docs/ABI.md`](docs/ABI.md)                   | The 440-byte particle, field by field.                        |
| [`docs/TEACHING.md`](docs/TEACHING.md)         | How the corpus learns.                                        |
| [`docs/ZEROTH.md`](docs/ZEROTH.md)             | **The Zeroth Law — why comparison is legitimate at all.**      |
| [`docs/MERGE.md`](docs/MERGE.md)               | What was merged from where, and the six defects it found.     |
| [`docs/TEAM.md`](docs/TEAM.md)                 | Running the seven-agent dev team.                             |

---

## Also in here

- **`everconf/`** — the confidence value as a plain Python library, no
  language required. `mse(preds, actual)` with one missing label returns
  UNKNOWN, not the loss of the points you happened to have.
- **`edapt/`** — the same "forgive, don't guess" discipline pointed at
  Python, JavaScript, Go, Rust and Java.
- **`examples/`** — six real programs, including a 1D logistic
  regression trained by gradient descent and checked bit-for-bit
  against an independent implementation. Make one training label `z`
  and the trained weight correctly comes back unknown.

---

## Provenance

Merged 2026-09-05 from `tapestry/` (base), `ever/` (layers 3, 5, and the
inspector), and `refix2/` (layer 7). `ReVision-FINAL/` contained no
source — only an interrupted Gradle wrapper download — and contributed
nothing.

The merge found and fixed six defects, five of them the same class:
*extent not delimited*, which `FINDINGS.md` §3 already named as the
highest-value defect class in the corpus. It also promoted the Java
runtime from "written, not executed" to **78 passing assertions**, and
wrote the `repair.sql` that ReFix had been citing for a file that did
not exist. All of it is recorded in [`docs/MERGE.md`](docs/MERGE.md),
including what is still missing.
