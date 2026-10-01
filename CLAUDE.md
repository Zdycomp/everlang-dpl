# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo actually is

The thesis is a multi-phase, cross-platform language ecosystem — Python frontend → TAC IR → C++ analysis → Java execution runtime, SQLite-backed history — but **most of that is aspirational**. What exists today:

| Phase | Dir | Reality |
|---|---|---|
| Python runtime | `everlang_standalone/` | A working "DPL / Everlang" package: a 4-stage confidence pipeline, a quantum/entanglement module, a biocomputing (DNA) module including a real lexer/parser pair, and ~79 tests. This is the actual substance of the repo. |
| C++ analysis | `1-phase-cpp/` | One native CLI, `verify_particle` — a safety-verification gate, not a general analysis phase. |
| Java runtime | `5-runtime-java/` | One read-only JDBC auditor, `SelfHealingAudit` — not a general IR execution runtime. |
| SQL archive | `4-archive-sql/` | A real SQLite persistence layer (`SqlArchive` + `schema.sql`) reinforcing the in-process `EArchive`. |
| `2-interpreter-python/`, `SEMANTICS.md`, `tests/golden/`, `tests/gold_suite/` | — | Do not exist. Do not invent behavior for them. |

Don't assume the target architecture's generality from the thesis sentence — verify against the table above and the phase's own README before writing code that depends on a phase doing more than it currently does.

## Commands

**Run everything** (repo root):
```bash
python3 run_all.py              # all four phases' own test suites, gates on all
python3 run_all.py --skip-native  # Python + SQL only, skips g++/mvn
```

**Python** (`everlang_standalone/`, the actual package):
```bash
cd everlang_standalone
python3 main.py                          # CLI demo: pipeline, entanglement swap, DNA compiler
python3 -m unittest discover tests       # full suite (~79 tests)
python3 -m unittest tests.test_dna_sequencer -v   # a single test module
python3 -m pyflakes .                    # lint
python3 benchmarks/ez_cpu_stress_test.py          # 1M-op multi-core stress benchmark
python3 benchmarks/ez_300_code_healing_benchmark.py
```

**C++** (`1-phase-cpp/`):
```bash
cd 1-phase-cpp
make          # builds bin/verify_particle (g++ -std=c++17 -Wall -Wextra -Werror -O2)
make test     # builds + runs tests/test_verify_particle (its own main(), no framework)
make asan     # bin/verify_particle_asan, -fsanitize=address,undefined
```

**SQL** (`4-archive-sql/`):
```bash
cd /home/user/everlang-dpl && python3 -m unittest discover -s 4-archive-sql/tests -t .
```

**Java** (`5-runtime-java/`):
```bash
mvn -q -f 5-runtime-java/pom.xml package   # fat jar at target/self-healing-runtime.jar
mvn -q -f 5-runtime-java/pom.xml test
java -jar 5-runtime-java/target/self-healing-runtime.jar path/to/tapestry.db
```

A `.claude/hooks/run-tests.sh` PostToolUse hook already re-runs the Python suite + pyflakes automatically whenever a `.py` file under `everlang_standalone/` is edited, and blocks on failure.

## Architecture

### The confidence model (read this before touching `core/`)
Everything in `everlang_standalone` runs on one idea: an `EParticle` carries a `value` and a `confidence` integer **clamped to [0, 256]** (`core/particle.py`). `confidence == 0` means "Z-quarantined" (`is_z()`), the system's universal failure/dead state. `PHI` (golden ratio) and the constant `81` (a Pauli-spectrum-gap threshold) recur throughout as magic-but-intentional constants — don't "simplify" them away.

- **`core/phase_engine.py`** (`PhaseEngine.collide`): the core state-transition logic between two particles. In order: `Z_CONTAGION` (either is Z) → `EXCEL` (confidence gap < 81, constructive fusion) → `EXPEL` (ratio > 2·φ and the stronger one is ≥81, weaker one discarded) → `REPEL` (fallthrough).
- **`core/archive.py`** (`EArchive`): in-process, thread-locked, three responsibilities — `log_boundary_marker` (append-only event log), `emulate_repair` (the self-healing formula: `error_distance` 1–3 → `confidence = 250 - error_distance*30`; else quarantined; **this exact formula is independently re-derived by the Java auditor**, so changing it here without updating `5-runtime-java` breaks that phase's contract), `calculate_evolve_vector` (action/reaction/force physics metaphor, no-ops to 0.0 if reaction or force is 0 — indistinguishable from a genuine zero vector, a known ambiguity).
- **`core/expect.py`** (`ExpectGate`): a contract-style assertion gate (`notZ`, `minConfidence`, `piAcceptable`) with fallback handling.
- **`pipeline.py`** (`EZPipeline`): wires four `containers/` stages — `SyntaxMutatorContainer` → `PhaseSemanticEngineContainer` → `ContractGovernorContainer` → `EvolveArchiveCorpusContainer` — into one `EXAMINE → EVALUATE → EXECUTE → ARCHIVE` pass over a code snippet + language tag.
- **`quantum/`**: `TrueSuperrelativityEngine` (Lorentz factor, time dilation, wave-function collapse) and `EntanglementSwapSystem`, which uses it to restore a Z-quarantined particle's confidence from a non-quarantined "anchor" particle, logging the recovery through `EArchive.calculate_evolve_vector`.
- **`biocomputing/`**: an independent sub-world using the same confidence scale for DNA. `quaternary.py` (byte↔DNA base-4 codec, `A=00,T=01,C=10,G=11`), `dna_engine.py` (`BioPhaseEngine`: hybridization affinity 0–256, displacement needs affinity ≥180 *and* confidence >128), `vibe_compiler.py` (`VibeDnaCompiler`: three fixed child cells running numbered "pulse cycles" that encode/decode/mutate DNA and adjust confidence by ±10/−30 per cycle), and **`sequencer.py`** — a genuine lexer/parser pair (`DnaLexer` → `BaseToken`s, `DnaParser` → Watson-Crick `BasePair`s and `Codon` triplets) that deliberately does *not* silently drop invalid characters the way `quaternary.py` does — it's the pattern to follow if you ever build the Python frontend's real lexer/parser.

### Cross-phase reinforcement of the self-healing Archive
`EArchive` has no persistence and no external verification. Three things reinforce it without replacing it, each through a narrow, documented contract — never by reimplementing another phase's logic:
1. **`1-phase-cpp/bin/verify_particle`**: a pre-write safety gate. Contract: `verify_particle <confidence>` with the value on stdin; prints `VALID` or `INVALID:<REASON>` (see `1-phase-cpp/README.md` for the exact table). Checks confidence bounds and value length (≤4096 bytes) — things `EParticle` itself doesn't all check (value length isn't an `EParticle` concern at all).
2. **`4-archive-sql/archive_db.py`** (`SqlArchive`): durable SQLite persistence (`tapestry.db`, gitignored, never commit it) for boundary markers, repairs, evolved vectors, and anything the C++ gate rejects (`rejected_writes`). Schema in `schema.sql`, CHECK-constrained on confidence range.
3. **`5-runtime-java`**'s `SelfHealingAudit`: independent, **read-only** JDBC auditor; re-derives expected `emulate_repair` outcomes from the formula above and flags drift in `tapestry.db`. Never writes.

**`everlang_standalone/everlang/core/reinforced_archive.py`** (`ReinforcedArchive`) is the bridge: same public API as `EArchive`, every write still goes to the in-process archive unconditionally (zero behavior change for existing callers), and is *additionally* run through the C++ gate and persisted via SQL when both are available. Locates the C++ binary and the SQL module by path relative to the repo root; imports `archive_db.py` by file path under a dedicated module name (not a bare `import archive_db` after a `sys.path` insert — that's silently defeated if anything else already registered a module of that name in `sys.modules`). Both backends are optional: missing or failing, `ReinforcedArchive` degrades to plain `EArchive` behavior rather than raising. Every SQL write is wrapped so a `sqlite3` error disables SQL reinforcement for that instance rather than propagating.

## Rules

1. **Boundary awareness.** Identify which phase a change targets before writing code. Phases communicate only through the documented CLI/file contracts above (exact strings, exit codes, schema) — never by one phase importing or reimplementing another's logic.
2. **The test gate is `python3 run_all.py`**, not just the Python suite. Changes to `EArchive.emulate_repair`'s formula specifically require updating `5-runtime-java`'s `RepairAuditor`, since it duplicates that formula on purpose as an independent check.
3. **No invented features.** Behavior must trace to an existing phase's README/code (there is no `SEMANTICS.md`). If you need a feature a phase's README doesn't describe, add it there first.
4. **C++ memory safety is explicit, not implicit**: no dynamic allocation beyond fixed-size buffers, every syscall return checked, no `sprintf`/`strcpy`/`gets`. Run `make asan` after any change to `1-phase-cpp/src/`.
5. **Stay minimal and match surrounding style** — this codebase has a consistent (if idiosyncratic) physics/biology metaphor; don't rename `EArchive`, `EParticle`, `PhaseEngine`, etc. to more "conventional" names.

## Multi-agent team (`.claude/agents/`)

| Agent | Owns |
|---|---|
| `architect` | Cross-phase changes, contract design between phases |
| `python-frontend` | `everlang_standalone/` (lexer/parser work, e.g. `biocomputing/sequencer.py`, belongs here too) |
| `ir-tac-engineer` | `ir.py`, `tac.c`, `form*.c` — none of this exists yet |
| `cpp-analysis` | `1-phase-cpp/` |
| `java-runtime` | `5-runtime-java/` |
| `archive-sql` | `4-archive-sql/` |
| `test-engineer` | Test suites, `run_all.py` |
| `memory-safety-auditor` | ASan/UBSan on C++, concurrency/exception review on Python (this is how the three real bugs in `reinforced_archive.py`'s first draft were found and fixed — a race on rejection-reason attribution, uncaught `sqlite3` exceptions mid-write, and the `sys.modules` import-caching issue) |

Delegate to the agent that owns the phase; start with `architect` for anything crossing phase boundaries.
