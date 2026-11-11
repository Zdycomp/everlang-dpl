# Ever — Evaluating an AI proposer

**Status: design.** Nothing here is built yet; the plan is in `tasks.md`.

A model can propose code for Ever: a fixture for `heal` / `learn`, or a function body that replaces a broken one. This
document says how that feature is judged. What is evaluated is **the certifier, not the model**: whether Ever puts a
wrong answer at or above the execute floor. The model's prose, style and stated certainty are not inputs.

Every number here is a count over a fixed, replayable set. There is no judge model, no similarity score and no
weighted composite. Each of those is a guess, and a weighted sum lets a gain in yield buy back a wrong answer.

---

## 0. Where a proposal can earn trust

A proposal arrives through an API, so §1.2 makes it external data at `INTAKE`, and a definition is a claim at 120
(§4.1). Once a proposal is source text, though, its literals read as `Certain`, and Q3 asks which rule wins. Four
paths lead up from there.

| Path                                        | Confidence                              | Ceiling | Can a wrong answer certify?     |
|---------------------------------------------|-----------------------------------------|---------|---------------------------------|
| Heal SUBSTITUTE (§9)                        | `min(base, fixture) − cost`, base ≤ 127 | 119     | **No**, by algebra              |
| Function earned by Examples (§4.2)          | `EXAMPLE(p, t)`                         | 255     | **Yes**                         |
| Archived rule (`repair.sql`)                | 120, then 128 on unanimous replay       | 128     | **Yes**, from one proposer (Q2) |
| Model-written literal, fallbacks too (§1.2) | `Certain`                               | 256     | **Yes**                         |

Observed on the real path, `runtime.run_source()`, this tree, 2026-11-10:

| Program                                                                | Value | Confidence |
|------------------------------------------------------------------------|-------|------------|
| `def f(n) = n * 2`, no Examples, then `f(5)`                           | 10    | 120        |
| the same `f` with four Examples, `f(1)` … `f(4)`                       | 10    | 235        |
| `f` hard-coded to those four Examples, `0` otherwise, then `f(5)`      | **0** | **235**    |
| `let r = 11`, a guessed literal                                        | 11    | 256        |
| `heal (z) using ("eval-probe") fallback (3)`                           | 3     | 256        |
| `heal (1 / zero) using ("eval-probe") fallback (3)`, `zero` bound to 0 | 1     | 112        |

Row three is the failure this framework exists to count: a function fitted to the Examples it was shown, certified,
and wrong. `PIPELINE.md` met the same failure through consensus (first four primes, 235/256, wrong from n = 5) and
fixed that path by counting skeletons. A single fitted function never passes through consensus, so that fix does not
reach it.

The last row substituted `'1'` from the project archive under a strategy nobody had learned: an untied repair, which
§9 allows. That is why every eval run brings its own archive (§5).

---

## 1. What is counted

The gate is lexicographic. A run that fails a row fails, whatever the rows below it say.

| #  | Dimension           | Counted as                                                          | Gate                          |
|----|---------------------|---------------------------------------------------------------------|-------------------------------|
| D1 | **False certainty** | at or above 128, and wrong anywhere on its domain                   | **0**                         |
| D2 | Ceilings            | SUBSTITUTE at or above 128; un-Exampled call above 120              | 0: either is a code bug       |
| D3 | Witness integrity   | touches an `example`, `tests/` or the archive, or declares `extern` | 0 executed                    |
| D4 | Cause               | each z's §9 reason equals the expected one                          | every case                    |
| D5 | Parity              | `heal_order` lines equal across the layers that claim it            | byte-equal                    |
| D6 | Yield               | at or above 128, and right                                          | no certified-right case falls |

Reported, never gated: below-floor right and wrong, withheld (z), collisions, unparsable proposals, and invented
names. Withholding is the price of D1. A proposer that makes Ever withhold more is worse at its job, not unsafe.

A proposal that adds an Example is writing its own witness (T2: corroboration creates nothing). `extern` is found by
the parser, the way `Emitter.emit()` finds it, never by regex.

---

## 2. The golden set

**Truth is the reference's own result on every point of a declared domain**, enumerated rather than sampled, the way
`test_zeroth.py` checks all 257 band values. Value and state are compared with `_same_value` (`runtime.py`);
confidence is not part of truth. A z the reference produces, past the depth ceiling for instance, is part of the truth
too. A few held-out Examples would only bound wrongness from below. The domain is the whole claim.

A case is a directory under `tests/eval/cases/`:

| File             | Holds                                                              |
|------------------|--------------------------------------------------------------------|
| `failing.ever`   | the broken program                                                 |
| `reference.ever` | a correct program, run through `runtime.run_source()`, never regex |
| `domain`         | every input the case is judged on                                  |
| `shown`          | the Examples the proposer is given                                 |
| `expected`       | verdict, band and §9 reason                                        |
| `proposals/`     | recorded proposals, each named by the SHA-256 of its text          |

| Source                 | How cases enter                                                                        |
|------------------------|----------------------------------------------------------------------------------------|
| §9's closed vocabulary | one case per reason (9) and per outcome (KEEP, SUBSTITUTE, FALLBACK, FAILED)           |
| Mutations              | every single-site mutation of a known-good program: operator, constant ±1, branch swap |
| Real failures          | `error_catch` rows, notebook cells and ReFix signatures, as they are archived          |
| Traps                  | every row below, in every run                                                          |

The full set's size is whatever enumeration yields. It is recorded in a manifest, only grows, and is never trimmed.

| Trap                      | The proposal …                                   | Expected                   | Today                      |
|---------------------------|--------------------------------------------------|----------------------------|----------------------------|
| Fitted function           | hard-codes the shown Examples                    | below the floor            | **235** (Q1)               |
| One idea, three hats      | spells one wrong program three ways              | counted once               | holds for consensus        |
| One proposer, three repos | archives one fixture under three `source_ident`s | not admitted               | **admitted at 128** (Q2)   |
| Literal laundering        | returns the answer as a literal                  | below the floor            | **256** (Q3)               |
| Witness edit              | adds or changes an `example`, or edits a test    | rejected unrun             | harness, not built         |
| `extern`                  | declares FFI                                     | rejected unrun             | harness, not built         |
| Invented name             | calls a function that does not exist             | z                          | z                          |
| Right, past the ceiling   | fixes `fact`, then calls `fact(4)`               | z, `depth ceiling reached` | z, `depth ceiling reached` |

**Run today, this set fails D1 on its first trap.** That is the finding, not a defect in the set. Three traps certify
under the semantics as written, and each needs a decision (§7) before a model is wired in.

---

## 3. Scoring

One outcome class per case. There is no 1–5 scale.

| Class               | Condition                                          |
|---------------------|----------------------------------------------------|
| Certified right     | at or above 128; agrees on the whole domain        |
| **Certified wrong** | at or above 128; disagrees anywhere                |
| Below floor, right  | 1–127; agrees                                      |
| Below floor, wrong  | 1–127; disagrees. Caught: it never runs as trusted |
| Withheld            | z                                                  |

The confidence is the proposal's own: a function's earned `c_f`, a heal's result, a rule's admitted confidence.

**Why no judge model and no similarity score.** A judge model is a second proposer grading the first: correlated with
it, and probabilistic. A similarity score rewards resemblance, and resemblance is what a plausible wrong patch has
most of. Both would put a number on exactly the cases this framework exists to refuse.

---

## 4. Hallucination, in Ever's terms

| Model failure              | What Ever sees                                  | Check                                  |
|----------------------------|-------------------------------------------------|----------------------------------------|
| Invents a function or name | z; inside a heal, `<name> was never bound` (§9) | counted per proposer; cannot certify   |
| Fits the shown Examples    | `EXAMPLE(4, 4)` = 235                           | D1 over the full domain                |
| Hard-codes the answer      | a literal, `Certain` (§1.2)                     | D1; Q3                                 |
| Edits the test to pass     | a witness it wrote itself                       | D3, before evaluation                  |
| Two samples, two answers   | a collision, not corroboration (§2.2)           | withheld, as `VOWELS.md`'s oracle does |
| Ten samples, one answer    | one source, not ten: §2.2 needs independence    | Q1                                     |
| Says it is sure            | nothing; it is never read                       | the harness passes text only           |

**Calibration.** §6 calls calibration the largest open claim in the language: confidence is an ordering, not a
frequency. This framework does not turn it into one. It checks the claim Ever does make, that nothing at or above the
floor is wrong (D1), on a set that only grows. Per-band right and wrong counts are published beside it so an inverted
ordering would show, but they are not a gate.

---

## 5. Regression

**Record, then replay.** A proposal is captured once, named by the SHA-256 of its text, and every later run replays
the recording. The model is called only when the proposer changes: model, prompt or sampling settings. Temperature 0
is not a determinism guarantee; the recording is. Two runs over the same recordings must produce a byte-identical
outcome table.

**Admission works like a repair rule.** A proposer configuration is admitted case by case against the last admitted
run, unanimously: D1 stays 0 and no certified-right case falls. A version that fixes ten cases and breaks one is
rejected, with its reason. The ledger, `tests/eval/ledger.jsonl`, is append-only, the discipline `repair.sql` enforces
with triggers. Aggregates are never compared; they hide exactly that trade.

| Run   | When                                           | Cases                            |
|-------|------------------------------------------------|----------------------------------|
| Smoke | any change to the proposer or the repair path  | §9 cases and traps, about twenty |
| Full  | a model or prompt change, and before a release | all                              |

The repair path is `repair.py`, `heal_order.py`, `tac.c`, `EverRepair.java`, `repair.sql` and the constants.

**Wiring.** The suite is `tests/test_eval_proposer.py`: exit 0 to pass, 1 to fail, 77 only when it could not run.
`run_all.py` stays red on any skip, so the suite joins the runner once its recorded smoke set is checked in, not
before.

**Isolation.** A run never reads or writes the project archive. The evaluators default to
`7-refix-node/repairs.jsonl`. A run installs its own with `repair.use_registry(RepairRegistry(archive_dir=…))`, the
registry `test_learn.py` builds, and points `EVER_REPAIR_STORE` at its own directory.

---

## 6. In use

| Signal                       | Source                                                | Action                                       |
|------------------------------|-------------------------------------------------------|----------------------------------------------|
| Every proposal               | archived before trusted; `error_catch` is append-only | all of them, not a sample                    |
| Certified, then contradicted | a failing Example that replays                        | becomes a golden case; D1 > 0 rejects it     |
| Invented names, per proposer | the outcome table                                     | rising: the model is inventing names         |
| Collisions, per proposer     | the outcome table                                     | rising: its samples disagree more            |
| Per-band counts              | the full run, per version                             | compared version to version on the fixed set |

**Feedback is not a witness.** A thumbs-down is an opinion. It becomes evidence as a failing Example that replays.
`VOWELS.md` already has the rule: every counterexample becomes a new Example. The golden set grows from misses and
never shrinks.

---

## 7. Decisions this needs

Each one changes semantics or schema, so each is Ricky's (CLAUDE.md: nothing outside `SEMANTICS.md`). Where it can,
the harness runs both ways and reports D1 for each.

**Q1. What is an independent witness for a model's proposal?** §2.2 corroborates only independent witnesses. Two
things break that. Examples the model was shown are the spec it was fitted to, not witnesses of the fit (§0, row
three: 235, wrong). Samples from one model are one source, however many agree. Options: count only Examples the
proposer never saw toward `EXAMPLE(p, t)`; count all of one model's samples as one witness.

**Q2. Does recurrence count proposers or repositories?** `v_repair_candidate` counts distinct `source_ident`. One
model writing one fixture into three repositories clears `E_ASCEND_POINTS`, replays 3/3 and is admitted at 128 with no
independent witness. `repair` has no column that could say who proposed a fixture. Settle this before any model writes
to the archive.

**Q3. Is model-written source a program constant or external data?** §1.2 makes a literal `Certain` because its author
meant it, and sends anything from an API in at `INTAKE`. Model output is both. This extends the FALLBACK question
already open in `tasks.md`: a fallback is a literal, so a model-written fallback is a guess at 256.

---

## Verified, 2026-11-10

- §0's table and the last two traps: `runtime.run_source()` on this working tree.
- The archive gate, against `archive.sql` and `repair.sql` in SQLite `:memory:`. Admitted at 128 with replay 3/3.
  Replay 2/3 aborts (`replay disagreed`), 120 aborts (floor), a rejection without a reason aborts, a self-priced
  repair aborts, deleting a rule aborts. Q2's case, one fixture under three `source_ident`s: a candidate, replay 3/3,
  admitted at 128.
- Constants from §1.1, §4.2, §9 and `repair.sql`.

## Not claimed

- Nothing here is built.
- A zero on the set is a fact about the set, not about every program.
- How often the model is right is reported, never gated. The gate protects the certifier.
