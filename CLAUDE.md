# 4Ever / Everlang (DPL) — Project DNA

**Thesis:** a multi-phase, cross-platform language ecosystem: Python frontend → Three-Address-Code (TAC) IR → C++ analysis phase → Java execution runtime, with SQLite-backed history.

## Repo reality vs. target architecture
| Phase | Target dir | Status in this repo |
|---|---|---|
| Python frontend (lexer, parser, checker, validator, evaluator) | `2-interpreter-python/` | **Not present yet.** Only `everlang_standalone/` (DPL v3.0 runtime: `core/`, `containers/`, `quantum/`, `biocomputing/`, `pipeline.py`) exists. |
| C++ analysis / safety verification | `1-phase-cpp/` | Not present |
| Java execution runtime | `5-runtime-java/` | Not present |
| SQL archive / `tapestry.db` | `4-archive-sql/` | Not present (`core/archive.py` `EArchive` is the in-process logger) |
| Specs | `SEMANTICS.md` | Not present — do not invent semantics; ask the user or add the file first |
| Golden tests / `run_all.py` | `tests/golden/`, `tests/gold_suite/` | Not present. Current tests: `everlang_standalone/tests/` |

Toolchains available in the cloud env: python3.11, gcc/g++, java/javac. Create a target directory only when the user asks for that phase.

## Rules (non-negotiable)
1. **Boundary awareness.** Identify the target phase before writing code. Never bleed Python interpretation rules into C++ or vice versa; phases communicate only through the IR and documented file/CLI contracts.
2. **Tests gate every change.** Run `cd everlang_standalone && python3 -m unittest discover tests` (42 tests must pass). When `run_all.py` and the golden suites exist, they are the gate for every feature.
3. **TAC preservation.** Changes to `ir.py`, `tac.c`, or any optimizer must keep basic blocks well-formed (single entry, terminator-ended, valid jump targets) and evaluation frames consistent.
4. **No invented features.** Behavior must trace to `SEMANTICS.md` (once present) or existing code/README. Memory-safety (ownership, lifetimes, bounds) must be explicit at compile time.
5. **Stay minimal and match surrounding style.**

## Commands
```bash
cd everlang_standalone
python3 main.py
python3 -m unittest discover tests
python3 -m pyflakes .        # if installed
python3 benchmarks/ez_cpu_stress_test.py
```

## Multi-agent team (`.claude/agents/`)
| Agent | Owns |
|---|---|
| `architect` | Orchestrator: routes work by phase, guards boundaries, reviews cross-phase contracts |
| `python-frontend` | Python lexer/parser/checker/validator/evaluator; `everlang_standalone/` today |
| `ir-tac-engineer` | `ir.py`, `tac.c`, `form*.c`, optimizer passes, basic-block validity |
| `cpp-analysis` | `1-phase-cpp/` analysis & safety verification |
| `java-runtime` | `5-runtime-java/` execution runtime |
| `archive-sql` | `4-archive-sql/`, `tapestry.db` schema and telemetry |
| `test-engineer` | unit/golden/gold_suite tests and `run_all.py` |
| `memory-safety-auditor` | ASAN/UBSan, leaks, lifetime/ownership review |

Delegate to the agent that owns the phase; for cross-phase changes, start with `architect`.
