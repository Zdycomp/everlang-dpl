# The merge — what came from where, and what it cost

**Codric Enterprise · Ricky (Dreid) · 2026**

Four directories became one repository on 2026-09-05. This file records
what was taken from each, what was left behind, what broke on the way,
and what is still missing. Provenance is part of the corpus: a claim
whose origin is not recorded is a claim nobody can check.

---

## The four sources

| Source            | What it was                                        | Verdict                    |
|-------------------|----------------------------------------------------|----------------------------|
| `tapestry/`       | Ever v2 — the language, the 440-byte atom, the docs | **base of the merge**      |
| `ever/`           | Ever v1 — seven layers, one per language            | **three layers salvaged**  |
| `refix2/`         | ReFix v2 — the applied product, Gradle repair       | **layer 7**                |
| `ReVision-FINAL/` | an interrupted Gradle wrapper download              | **nothing to merge**       |

`ReVision-FINAL` contains no source. Its entire tree is
`gradle/wrapper/dists/gradle-9.6.0-bin/` holding a `.zip.part`, a
`.lck`, and four IDE metadata files. It is the Android project ReFix
was pointed at, not a project in its own right. Recorded here so the
absence is deliberate rather than an oversight.

---

## Layer by layer

The two Ever generations both numbered their layers 0–6 and meant
different things by the numbers. Tapestry is the successor everywhere
the two overlap, so Tapestry's numbering won and Ever v1 contributed
only where Tapestry had nothing.

| Layer                  | From        | Why that one won                                                                                             |
|------------------------|-------------|--------------------------------------------------------------------------------------------------------------|
| `0-atom-c`             | tapestry    | v2 particle: payload, anchor id, defect class. 11,941 lines against v1's 617. v1's atom is a strict subset.   |
| `1-phase-cpp`          | tapestry    | 50 assertions against v1's 28, and it links against the v2 atom.                                              |
| `2-interpreter-python` | tapestry    | The actual language — lexer, parser, semantic pass, evaluator, five compile targets. v1 had no interpreter.   |
| `2-inspect-python`     | **ever v1** | A different tool wearing the same layer number: a polyglot *source inspector*. Tapestry never had one.         |
| `3-dsl-ruby`           | **ever v1** | Tapestry has no Ruby layer at all.                                                                            |
| `4-archive-sql`        | tapestry    | 20,134 bytes against v1's 18,650, and v2 stores payload and anchor. v1's `archive_test.sql` came along too.   |
| `5-runtime-java`       | **ever v1** | Tapestry's `5-runtime-java/` was an empty directory. v1's is a working runtime.                               |
| `6-interface-html`     | **both**    | Tapestry's `ever-live` and `ever-start` consoles; v1's `inspector.html` and the headless test that scores it. |
| `7-refix-node`         | **refix2**  | New layer. The first thing in the stack aimed at somebody else's build.                                       |

Also carried over whole: `everconf/`, `edapt/`, `examples/`,
`research.py`, and the nine documents now in `docs/`.

Excluded from the copy: `.git`, `.venv`, `.history`, `.idea`,
`.vscode`, `__pycache__`, `.DS_Store`, compiled `.o` / `.class`
artifacts, and the generated `.db` files, which the suites rebuild.

---

## Six defects found during the merge

The merge was treated as an inspection. Everything below was found by
running the thing, not by reading it.

**1. `tests/gold_check.py` — missing `#include <stdlib.h>`.**
The generated C executor called `malloc` with no declaration. Under
clang's default C99 rules that is an error, not a warning, so the Gold
standard suite failed to build and Tapestry ran 24/25, not 25/25.
One line. Fixed; the suite is 25/25.

**2–5. Four delimiter defects in the `ever/` working tree.**

| File                          | Defect                                              |
|-------------------------------|-----------------------------------------------------|
| `0-core-c/ever.h`             | stray `/*` after `e_cap(...)`, and a trailing `/`   |
| `2-translate-python/*.py`     | `""""""` where the docstring wanted `"""`           |
| `cross_layer_test.py`         | `""` opening and closing the module docstring       |
| `cross_layer_test.py`         | `r""` opening the embedded JavaScript driver        |

Every one of them is the same defect class: **extent not delimited**.
`FINDINGS.md` §3 puts `unbounded` at 84.2% of the corpus and calls it
"the single highest-value defect class to target." It was also 100% of
what had rotted in the working tree.

The committed tree was clean — `git diff` showed the corruption existed
only in the working copy, so four of the five were repaired by restoring
from `HEAD` rather than by hand-patching. The `gold_check.py` fix is a
real code change and is the only source edit the merge made to a
previously-passing file.

**6. ReFix cited two things that do not exist.**
`7-refix-node/README.md` says the mechanism "ports from Ever/Tapestry
`SEMANTICS.md` §9 and `4-archive-sql/repair.sql`."

- `SEMANTICS.md` has eight sections. There is no §9.
- No `repair.sql` existed in either Ever generation.
- Neither `archive.sql` contained the string `repair` anywhere.

The citation was aspirational. Rather than delete it, the merge made it
true — see below.

---

## What the merge added

**`4-archive-sql/repair.sql`** — the file ReFix was citing, written.

ReFix keeps its archive as append-only JSONL so one developer needs no
database to begin. `repair.sql` is that same contract expressed in the
archive layer's own language: the shape the archive takes when the
JSONL outgrows one machine. It is not a translation of the JavaScript;
it is the same invariants enforced one layer lower, where a careless
caller cannot skip them.

Nine triggers, each matching a throw in `7-refix-node/src/archive.js`:

| The database refuses                          | Because                                            |
|-----------------------------------------------|----------------------------------------------------|
| a repair with either half empty               | a repair is a pair                                  |
| a cost that was supplied rather than derived  | a caller pricing its own repair is how a corpus drifts |
| a `conf_after` ≠ `max(0, conf_before − cost)` | the arithmetic is not a free field                  |
| confidence rising through a repair            | fixing a thing does not make the archive surer of it |
| a rule admitted below `E_EXECUTE_FLOOR`       | 128 is the floor for everything else too            |
| a rule admitted when replay disagreed         | a generalisation that rewrites history is not one   |
| a rejection carrying no reason                | a rejection without a reason teaches nothing        |
| `DELETE` on a repair or a rule                | the archive is the product                          |
| `UPDATE` on a repair                          | append-only means append-only                       |

**`4-archive-sql/repair_test.py`** — 55 assertions, and most of them
assert a *refusal*. If an invariant holds in only one of the two
implementations it is not an invariant, it is a convention.

**`tests/run_all.py`** now runs all eight layers. The four suites that
need a toolchain the host may not have (`ruby`, `javac`, `node`) test
for it first and report **SKIP**. They never report PASS on a missing
toolchain, which was the failure mode Ever v1's README went out of its
way to avoid.

---

## What the merge promoted from written to executed

Ever v1's README carried this, honestly:

> Written but **not yet executed** — the container had no toolchain for
> them. […] Layer 3 · Ruby. Layer 5 · Java. […] Those two layers are
> Confident, not Certain.

This host has both. They were run.

- **Layer 5 · Java — 78 passed, 0 failed.** First execution. The
  largest single block of assertions Ever v1 had never counted.
- **Layer 3 · Ruby — runs clean, exit 0.** But `ever.rb` is a
  demonstration script with no assertions in it, so it earns "executes
  without error" and nothing stronger. Calling that a passing suite
  would be exactly the fudge the v1 README refused to make.

---

## Not re-verified on this host

Three toolchains are absent here — `go`, `rustc`, `Rscript`, `kotlinc` — so
`tests/test_backends.py` re-verified **12 cases against JavaScript and skipped
four targets**. The Go / Rust / R / Kotlin results stand as the project's prior
claim, not as something this merge re-ran. `docker` is absent too, so the
container-only paths in `VOWELS.md` were not exercised.

Recorded because the difference between *verified here* and *verified once,
elsewhere* is the entire subject of the software.

---

## Still missing

Carried forward unresolved, from the sources' own open-questions lists:

1. **`SEMANTICS.md` §9 is still unwritten.** `repair.sql` now exists, so
   the citation resolves to real code — but the *semantics* of repair
   have no formal section. The rules are currently only readable as
   JavaScript, SQL triggers, and this file.
2. **Emulate's 30-per-error discount is still a placeholder** — v1 open
   question 1, never measured against a corpus.
3. **Anchored bodies still do not transpile** — `SEMANTICS.md` §7 calls
   this the largest gap, and the merge did not close it.
4. **ReFix has no `apply` command.** v0 archives fixtures; it does not
   edit files. When apply ships, revert lives in the same record.
5. **The ReFix archive starts empty.** There is no trained corpus and
   the merge did not manufacture one.
6. **Layers 5 and 6 are still on the v1 atom**, not the v2 particle —
   `FINDINGS.md` §5 flagged this and it remains true.
