# Ever — The Vowel Operators

**Codric Enterprise · Ricky (Dreid) · 2026**

```
A   operates on trust        Any · Assimilate · Anchor · Ascend
                             Apply2All · Auto-Didact
E   the thread itself        the noun everything else acts on
I   INTRODUCTION             brings code into being      — synthesis
O   OWNERSHIP                takes control of what is    — selection
U   UNDERSTANDING            deconstructs and attacks    — criticism
```

I, O and U close a loop, and the loop is what makes the system
self-generating rather than merely self-checking.

```
    understand  →  undermine  →  implement  →  integrate
         ↑                                          │
         │                                          ↓
    own  ←  obliterate  ←  optimize  ←  ultracode
```

---

## I — Introduction

| Operator | Signature | Does | Refuses to |
|---|---|---|---|
| **implement** | `Spec → E<Closure>` | Synthesises a function from Examples alone | Return anything that fails a single example |
| **integrate** | `E × E → E` | Merges two threads; agreement corroborates | Average a disagreement into a comfortable middle |
| **isolate** | `E × frag → E` | Lifts a sub-expression out for independent test | Transfer the parent's trust to the fragment |
| **interject** | `E × obs → E` | Places an observer in the path | Alter value or confidence — it is semantically invisible |
| **inject** | `E × env → E` | Substitutes bindings into captured scope | Exceed the weakest injected binding |

**`implement` is the self-generating core.** Given only Examples and no
body, it searches a bounded grammar for a function that reproduces every
one of them.

Verified: from `fact(1)=1, fact(2)=2, fact(3)=6, fact(4)=24` it searched
816 candidates, 10 satisfied, and returned

```ever
if n < 1 then 1 else n * fact(n - 1)
```

at **235/256**, anchored, computing `fact(6) = 720`. From
`1, 3, 6, 10` it independently derived triangular numbers.

**The bound is the honest part.** The grammar is small and stated:
arithmetic to depth 2 and single recursion. What it cannot reach is
therefore also stated. It is not a general program synthesiser and does
not claim to be.

---

## O — Ownership

| Operator | Signature | Does | Refuses to |
|---|---|---|---|
| **own** | `E × Ledger → E` | Anchors and records accountability | Own anything uncleared |
| **overcome** | `E × E × Spec → E` | Re-synthesises to *beat* the incumbent | Ship a lateral move |
| **obliterate** | `E × E × Ledger → E` | **Supersedes** — marks and archives | Delete anything, ever |
| **optimize** | `[Cand] × Spec → E` | Selects by confidence per unit complexity | Prefer a longer program that does the same work |

**`obliterate` never deletes.** Conservation is a law in Ever, not a
preference, so the strongest available operation is supersession with the
record kept. The superseded thread becomes an `EError` boundary marker
recording where the previous best stood and what replaced it.

**`overcome` refuses lateral moves.** Emulate borrows a neighbour's
pattern at a discount; overcome re-synthesises and keeps the result only
if it strictly beats what was there. Verified: it replaced a broken
`n * 2` at 0/256 with a synthesised `if n < 0 then 0 else n + tri(n-1)`
at 235/256, and correctly *declined* when asked to improve on an already
optimal function.

---

## U — Understanding

| Operator | Signature | Does | Refuses to |
|---|---|---|---|
| **understand** | `E → E<report>` | Derives a structural account | — |
| **undermine** | `E × Spec → E` | Attacks it; reports what breaks | Call silence a proof |
| **unwrap** | `E → [E]` | Decomposes into constituents | Carry trust into the parts |
| **ultracode** | `E × Spec → E` | Compresses to the shortest satisfying form | Claim compression it did not achieve |

**`undermine` is the critic, and without it nothing evolves.** A system
that cannot be surprised only ever confirms itself. It returns **Z** when
nothing breaks the thread, because *no counterexample found* is not a
proof of correctness and must not be dressed as one.

**`ultracode` is minimum description length.** The shortest program that
reproduces the evidence assumes least, and assuming least is what
generalises.

---

## The loop: self-generating, ever-evolving

Each generation understands the incumbent, attacks it, synthesises
against the spec, compresses, and keeps the winner only if it beats what
stood before.

**The mechanism that makes it evolutionary rather than repetitive:** a
deterministic search re-run returns the same answer forever. The only
thing that can change the next generation is a changed specification. So
**every counterexample becomes a new Example the next generation must
satisfy.** Criticism does not merely score the work — it writes the next
spec.

### The consensus oracle

New probes need a ground truth, and asking the incumbent is circular: the
probes that matter are exactly the ones that broke it.

So the oracle polls **every candidate that satisfied the known
examples**. These were derived independently and agree on everything
verified so far; where they also agree on a new input, that agreement is
corroboration in precisely the sense the language already defines. The
bar is the same one used everywhere else: at least ⌊π⌋ = 3 agreeing, and
at least two-thirds of those that answered.

Verified: from three examples the system independently derived
`fact(7) = 5040` and `fact(5) = 120` by consensus among ten
independently synthesised programs.

**Where they disagree, it withholds.** Inventing an expected answer would
teach the corpus a fact nobody verified, which is the one thing Ever
exists to prevent.

### Honest convergence

The loop **converges and says so**. Given a spec it can already satisfy
optimally, it reports *"incumbent held; no improvement found"* rather
than churning to look busy. Ever-evolving means it evolves when there is
room — not that it manufactures change when there is none.

---

## Container

Every layer, every toolchain, one image:

```bash
docker compose run --rm verify     # all layers, including Ruby and Java
docker compose run --rm evolve     # the self-generating loop
docker compose run --rm research   # conservation law, ratios, defects
docker compose up live             # localhost:8088/ever-live.html
```

The image **verifies itself at build time**. If any layer fails, the
build fails. An image that ships without its own tests passing ships a
claim instead of a result.

---

## What is verified

| Component | Assertions |
|---|---|

This table used to be transcribed here by hand, and it had drifted: it
carried the same Python-interpreter row as three other documents and
`FINDINGS.md`, and `FINDINGS.md` said 81 while these said 83. Counts now
live in exactly one place, generated from a real run:

    python3 tests/assertion_counts.py

`FINDINGS.md` §5 carries the output and `--check` fails the gate when it
goes stale. See §5 there for why the 81 survived as long as it did.

Layer 3 (Ruby) and Layer 5 (Java) verify inside the container, which is
the reason the container exists.

## What is not claimed

- **General program synthesis.** The grammar is bounded and stated.
- **Correctness proofs.** `undermine` finds counterexamples; it does not
  prove their absence.
- **Unbounded self-improvement.** The loop converges and reports
  convergence honestly.
