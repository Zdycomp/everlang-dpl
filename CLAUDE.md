# 4Ever / Everlang (DPL) — Project DNA

**Thesis:** a multi-phase, cross-platform language ecosystem: Python frontend → Three-Address-Code (TAC) IR → C++ analysis phase → Java execution runtime, with SQLite-backed history.

## Repo reality vs. target architecture
| Phase | Target dir | Status in this repo |
|---|---|---|
| Python frontend (lexer, parser, checker, validator, evaluator) | `2-interpreter-python/` | **Not at the root yet.** The ExR lineage's frontend is `ezr/2-interpreter-python/`. `everlang_standalone/` (DPL v5.0 runtime: `core/`, `containers/`, `quantum/`, `biocomputing/`, `pipeline.py`) is the Python frontend's current home; `biocomputing/sequencer.py` is a lexer/parser pair (`DnaLexer`/`DnaParser`) in its own right. |
| C++ analysis / safety verification | `1-phase-cpp/` | **Present.** `verify_particle`: a native CLI safety gate (confidence range, value-length bounds) that `ReinforcedArchive` shells out to before persisting a write. See `1-phase-cpp/README.md` for the exact CLI contract. |
| Java execution runtime | `5-runtime-java/` | **Present, narrow scope.** `SelfHealingAudit`: a read-only JDBC auditor that re-derives expected `emulate_repair` outcomes from the documented formula and flags drift from what's persisted in `tapestry.db`. It is not (yet) a general IR execution runtime — see `5-runtime-java/README.md`. |
| SQL archive / `tapestry.db` | `4-archive-sql/` | **Present.** `archive_db.py`'s `SqlArchive` persists boundary markers, repairs, evolved vectors, and rejected writes into SQLite per `schema.sql`. `core/archive.py`'s in-process `EArchive` is unchanged and still the only Archive everlang_standalone depends on directly; `everlang/core/reinforced_archive.py`'s `ReinforcedArchive` is the opt-in bridge that reinforces it with the C++ and SQL phases (falls back to plain `EArchive` behavior if either is unavailable). |
| Specs | `ezr/SEMANTICS.md`, `ezr/CORE.md`, `ezr/ABI.md`, `ezr/PIPELINE.md` | Present under `ezr/` (ExR lineage). Do not invent semantics beyond them. |
| Golden tests / `run_all.py` | `ezr/tests/golden/`, `ezr/tests/gold_suite/` | Present under `ezr/`. Root `run_all.py` runs each phase's suite (Python, SQL, C++, Java) and the ezr lineage's 29-suite gate (`ezr/tests/run_all.py`). |

Toolchains available in the cloud env: python3.11, gcc/g++, java/javac, maven/gradle (Maven Central is reachable). Create a target directory only when the user asks for that phase.

## Cross-phase contract: reinforcing the self-healing Archive
`EArchive` (Python, in-process, no persistence) is reinforced — not replaced — by two independent backend phases, wired together by `everlang/core/reinforced_archive.py::ReinforcedArchive`:
1. **C++ safety gate** (`1-phase-cpp/bin/verify_particle`): every write is checked natively (confidence in [0,256], value non-empty and ≤4096 bytes) before being trusted. Contract: `verify_particle <confidence>` with the value on stdin; prints `VALID` or `INVALID:<REASON>` (see `1-phase-cpp/README.md`).
2. **SQL persistence** (`4-archive-sql/archive_db.py::SqlArchive`): durable SQLite storage (`tapestry.db`, gitignored) for boundary markers, repairs, evolved vectors, and anything the C++ gate rejected (`rejected_writes`).
3. **Java audit** (`5-runtime-java`'s `SelfHealingAudit`): independent, read-only; re-derives expected repair outcomes from the same formula as `EArchive.emulate_repair` and flags any row in `tapestry.db` that doesn't match.

Both the C++ and SQL legs are optional at runtime — if either is missing/unbuilt, `ReinforcedArchive` degrades to plain `EArchive` behavior rather than failing. Run `python3 run_all.py` (or `--skip-native` for Python+SQL only) to exercise all four phases together.

## Rules (non-negotiable)
1. **Boundary awareness.** Identify the target phase before writing code. Never bleed Python interpretation rules into C++ or vice versa; phases communicate only through the IR and documented file/CLI contracts.
2. **Tests gate every change.** Run `python3 run_all.py` from the repo root (all suites must pass). `--skip-native` runs the Python+SQL legs only, if g++/mvn aren't available.
3. **TAC preservation.** Changes to `ir.py`, `tac.c`, or any optimizer must keep basic blocks well-formed (single entry, terminator-ended, valid jump targets) and evaluation frames consistent.
4. **No invented features.** Behavior must trace to `ezr/SEMANTICS.md` or existing code/README. Memory-safety (ownership, lifetimes, bounds) must be explicit at compile time.
5. **Stay minimal and match surrounding style.**

## Multi-agent team (`.claude/agents/`)
Delegate to the agent that owns the phase; for cross-phase changes, start with `architect`.
