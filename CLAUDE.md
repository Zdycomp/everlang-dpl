# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo actually is

The thesis is a multi-phase, cross-platform language ecosystem — Python frontend → TAC IR → C++ analysis → Java execution runtime, SQLite-backed history — but **most of that is aspirational**. What exists today:

| Phase | Dir | Reality |
|---|---|---|
| Python frontend (lexer, parser, checker, validator, evaluator) | `2-interpreter-python/` | **Not at the root yet.** The ExR lineage's frontend is `ezr/2-interpreter-python/`. `everlang_standalone/` (DPL v5.0 runtime: `core/`, `containers/`, `quantum/`, `biocomputing/`, `pipeline.py`) is the Python frontend's current home; `biocomputing/sequencer.py` is a lexer/parser pair (`DnaLexer`/`DnaParser`) in its own right. |
| C++ analysis / safety verification | `1-phase-cpp/` | **Present.** `verify_particle`: a native CLI safety gate (confidence range, value-length bounds) that `ReinforcedArchive` shells out to before persisting a write. See `1-phase-cpp/README.md` for the exact CLI contract. |
| Java execution runtime | `5-runtime-java/` | **Present, narrow scope.** `SelfHealingAudit`: a read-only JDBC auditor that re-derives expected `emulate_repair` outcomes from the documented formula and flags drift from what's persisted in `tapestry.db`. It is not (yet) a general IR execution runtime — see `5-runtime-java/README.md`. |
| SQL archive / `tapestry.db` | `4-archive-sql/` | **Present.** `archive_db.py`'s `SqlArchive` persists boundary markers, repairs, evolved vectors, and rejected writes into SQLite per `schema.sql`. `core/archive.py`'s in-process `EArchive` is unchanged and still the only Archive everlang_standalone depends on directly; `everlang/core/reinforced_archive.py`'s `ReinforcedArchive` is the opt-in bridge that reinforces it with the C++ and SQL phases (falls back to plain `EArchive` behavior if either is unavailable). |
| Kotlin DNA port + Android app | `6-android-kotlin/` | **Present.** Gradle project: `core` (Kotlin port of `everlang_standalone/everlang/biocomputing`, checked against Python golden vectors), `predict` (order-k base predictor), `fuzz` (port of `tests/fuzz_harness.py`), and `app` (Android; included only when `local.properties` has `sdk.dir` or with `-Pandroid`, never compiled in the cloud env). `tools/determinism_check.sh` runs the JVM suites N times and requires identical outcome digests. |
| Specs | `ezr/SEMANTICS.md`, `ezr/CORE.md`, `ezr/ABI.md`, `ezr/PIPELINE.md` | Present under `ezr/` (ExR lineage). Do not invent semantics beyond them. |
| Golden tests / `run_all.py` | `ezr/tests/golden/`, `ezr/tests/gold_suite/` | Present under `ezr/`. Root `run_all.py` runs each phase's suite (Python, SQL, C++, Java, Kotlin) and the ezr lineage's 29-suite gate (`ezr/tests/run_all.py`). |

Toolchains available in the cloud env: python3.11, gcc/g++, java/javac, maven/gradle (Maven Central is reachable). Create a target directory only when the user asks for that phase.

Two JDKs are needed. `5-runtime-java` compiles with `--release 25`, and the `6-android-kotlin` build (Gradle 8.14.3, Kotlin plugin 2.2.0) fails to configure on JDK 25. Keep JDK 21 as the system default and install `openjdk-25-jdk-headless` alongside it. The options and the plan to reach one JDK are in `docs/adr/ADR-001-jdk-21-vs-25.md`.

## Commands
- Full gate (repo root): `python3 run_all.py`; Python+SQL only: `python3 run_all.py --skip-native`. `run_all.py` runs `5-runtime-java` on a JDK 25 when one is installed (`/usr/lib/jvm/java-25-*`); the container's `JAVA_HOME` is JDK 21 and fails with class file version 69.
- Kotlin phase (from `6-android-kotlin/`): `./gradlew :core:test :predict:test :fuzz:test`; determinism: `tools/determinism_check.sh 3`.
- ezr lineage gate (29 suites, must read 29 passed / 0 failed): `python3 ezr/tests/run_all.py`.
- Single Python test (from `everlang_standalone/`): `python3 -m unittest tests.test_algebra.TestLaws.test_uncertainty_endpoints`.
- Single Java test: `mvn -f 5-runtime-java/pom.xml test -Dtest=SelfHealingAuditIntegrationTest`.
- C++ phase: `make -C 1-phase-cpp test` (`make asan` for the sanitizer build).
- Cross-language parity: `python3 ezr/tests/algebra_parity.py`.
- Self-heal benchmark on real code (needs network, takes minutes, not in `run_all.py`): `python3 everlang_standalone/tests/heal_bench.py [language ...]`. Exits 1 if heal breaks, refuses or changes a valid file. Fixer regressions: `python3 ezr/tests/test_edapt.py`.

## Cross-phase contract: reinforcing the self-healing Archive
`EArchive` (Python, in-process, no persistence) is reinforced — not replaced — by two independent backend phases, wired together by `everlang/core/reinforced_archive.py::ReinforcedArchive`:
1. **C++ safety gate** (`1-phase-cpp/bin/verify_particle`): every write is checked natively (confidence in [0,256], value non-empty and ≤4096 bytes) before being trusted. Contract: `verify_particle <confidence>` with the value on stdin; prints `VALID` or `INVALID:<REASON>` (see `1-phase-cpp/README.md`).
2. **SQL persistence** (`4-archive-sql/archive_db.py::SqlArchive`): durable SQLite storage (`tapestry.db`, gitignored) for boundary markers, repairs, evolved vectors, and anything the C++ gate rejected (`rejected_writes`).
3. **Java audit** (`5-runtime-java`'s `SelfHealingAudit`): independent, read-only; re-derives expected repair outcomes from the same formula as `EArchive.emulate_repair` and flags any row in `tapestry.db` that doesn't match.

Both the C++ and SQL legs are optional at runtime — if either is missing/unbuilt, `ReinforcedArchive` degrades to plain `EArchive` behavior rather than failing. Run `python3 run_all.py` (or `--skip-native` for Python+SQL only) to exercise all four phases together.

**Real self-heal (`EArchive.heal`, per `ezr/SEMANTICS.md` §9).** `everlang/core/heal.py` runs ezr's `forgive.py` on Ever source and ezr's edapt fixers on Python, JavaScript, Go, Rust, Java and Kotlin; without `ezr/` a language is refused, never emulated. Every repair is archived as a Failure/Fixture pair charged 8 (plain) or 32 (inferred) from 256; §9.4 cases (unclosed brackets, unterminated strings) are refused as boundary markers. `repair_candidates()` and `propose_rules()` admit a rule at 128 only when 3 distinct sources agree and replay is unanimous. Vocabulary ids 1–7 in `everlang/core/vocabulary.py` must match `ezr/4-archive-sql/repair.sql` (`tests/test_heal.py` checks). `emulate_repair` is unchanged because the Java audit re-derives its formula.

## Rules (non-negotiable)
1. **Boundary awareness.** Identify the target phase before writing code. Never bleed Python interpretation rules into C++ or vice versa; phases communicate only through the IR and documented file/CLI contracts.
2. **Tests gate every change.** Run `python3 run_all.py` from the repo root (all six legs must pass). `--skip-native` runs the Python+SQL legs only, if g++/mvn aren't available. Don't build on red.
2a. **Hooks.** `.claude/hooks/run-tests.sh` runs after each Write/Edit of a Python file under `everlang_standalone/` and blocks on test or pyflakes failures. `.claude/hooks/session-start.sh` checks toolchains and runs the `everlang_standalone` unit tests.
3. **TAC preservation.** Changes to `ir.py`, `tac.c`, or any optimizer must keep basic blocks well-formed (single entry, terminator-ended, valid jump targets) and evaluation frames consistent.
4. **No invented features.** Behavior must trace to `ezr/SEMANTICS.md` or existing code/README. Memory-safety (ownership, lifetimes, bounds) must be explicit at compile time.
5. **Stay minimal and match surrounding style.**
6. **Terse replies.** No explanations, recaps or narration. Do the work; report the result in one line.

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

- **`core/archive.py`** (`EArchive`): in-process, thread-locked, three responsibilities — `log_boundary_marker` (append-only event log), `emulate_repair` (the self-healing formula: `error_distance` 1–3 → `confidence = 250 - error_distance*30`; else quarantined; **this exact formula is independently re-derived by the Java auditor**, so changing it here without updating `5-runtime-java` breaks that phase's contract), `calculate_evolve_vector` (action/reaction/force physics metaphor, no-ops to 0.0 if reaction or force is 0 — indistinguishable from a genuine zero vector, a known ambiguity).
- **`biocomputing/sequencer.py`** is a genuine lexer/parser pair that deliberately does *not* silently drop invalid characters the way `quaternary.py` does.
- **`frontend/`**: the Mega stages must stay byte-identical to `baseline.py` (tokens, statements, diagnostics, results) — `tests/test_frontend.py` fuzzes this. Any grammar change goes into `frontend/grammar.py` and its README, and both implementations. A quoted value is a string (string templates); a number, `true`/`false` or `[list]` value is a `TypedValue` (typed rendering). The speed numbers in its README are measured; don't claim 4× end to end, it doesn't reach it.
- **`transpiler/`** (`SuperTranspiler`): plain `str.format` substitution into per-language templates — a syntax-offset generator, not a real transpiler with a source grammar. Every built-in language's `{val}` is escaped for its own string literal (`VALUE_ESCAPES`, built on `typed.escape_string`; DPL's `escape_dpl_value`; mirrored by `TranspileAuditor` / `TypedValueRenderer.escapeString`), so DPL output reads back through `frontend/` and the generated code compiles; MegaExecuter's generated renderer applies the same table, skipping the escapers for a value that needs none. Adding a *built-in* language to `LANGUAGE_TEMPLATES` requires the same change in `5-runtime-java`'s `TranspileAuditor`, which hardcodes the six built-ins as its independent cross-check (same duplication-on-purpose pattern as the repair formula). User languages go through `register_language` instead: each edit is a new row in SQL `custom_template_versions`, every rendering is stamped with its `template_version`, and the auditor re-renders each row from exactly that version. Templates may use only bare `{name}`/`{val}`/`{type_spec}`/`{conf}` fields, because the Java side re-implements `str.format` for that subset only. Numbers, booleans and lists go through `transpile_typed` (`transpiler/typed.py`, `TypedValue`) instead: native types and literals in the six built-ins only, archived with a `value_kind` and the value's canonical DPL literal as `val`, and re-rendered by Java's `TypedValueRenderer`, which duplicates `typed.py`'s type tables and escapes on purpose. Any change to `typed.py`'s output needs the same change there; `tests/test_typed_transpiler.py` runs the built jar against Python-written rows to catch drift.

### Cross-phase reinforcement of the self-healing Archive
`EArchive` has no persistence and no external verification. Three things reinforce it without replacing it, each through a narrow, documented contract — never by reimplementing another phase's logic:
1. **`1-phase-cpp/bin/verify_particle`**: a pre-write safety gate. Contract: `verify_particle <confidence>` with the value on stdin; prints `VALID` or `INVALID:<REASON>` (see `1-phase-cpp/README.md` for the exact table). Checks confidence bounds and value length (≤4096 bytes) — things `EParticle` itself doesn't all check (value length isn't an `EParticle` concern at all). Each per-language transpiler rendering gets its own call — the 4096-byte budget is per snippet, never a bundled multi-language blob.
2. **`4-archive-sql/archive_db.py`** (`SqlArchive`): durable SQLite persistence (`tapestry.db`, gitignored, never commit it) for boundary markers, repairs, evolved vectors, transpilations, custom transpiler templates, and anything the C++ gate rejects (`rejected_writes`). Schema in `schema.sql`, CHECK-constrained on confidence range.
3. **`5-runtime-java`**: two independent, **read-only** JDBC auditors, never writing. `SelfHealingAudit` re-derives expected `emulate_repair` outcomes from the formula above and flags drift in `repairs`. `TranspileAudit` re-renders `SuperTranspiler`'s six built-in templates (plus custom ones, by stamped version, from `custom_template_versions`, and typed rows, by `value_kind`) from each `transpilations` row's stored inputs and flags any mismatch against the stored `rendered_code`. Run via `java -cp target/self-healing-runtime.jar com.everlang.runtime.<ClassName> <db>` — only `SelfHealingAudit` is the jar's default entry point.

**`everlang_standalone/everlang/core/reinforced_archive.py`** (`ReinforcedArchive`) is the bridge: same public API as `EArchive` (`log_boundary_marker`, `emulate_repair`, `calculate_evolve_vector`) plus `transpile_and_archive(name, val, type_spec, conf)`, which runs `SuperTranspiler` and reinforces each of its renderings (built-in and custom) the same way, and `transpile_typed_and_archive` for typed values, plus `register_language`/`unregister_language`, which persist custom templates to SQL and reload them on init. Every write still goes to the in-process archive (or the transpiler, which is always purely in-process) unconditionally — zero behavior change for existing callers — and is *additionally* run through the C++ gate and persisted via SQL when both are available. Locates the C++ binary and the SQL module by path relative to the repo root; imports `archive_db.py` by file path under a dedicated module name (not a bare `import archive_db` after a `sys.path` insert — that's silently defeated if anything else already registered a module of that name in `sys.modules`). Both backends are optional: missing or failing, `ReinforcedArchive` degrades to plain in-process behavior rather than raising. Every SQL write is wrapped so a `sqlite3` error disables SQL reinforcement for that instance rather than propagating.

## Rules

1. **Boundary awareness.** Identify which phase a change targets before writing code. Phases communicate only through the documented CLI/file contracts above (exact strings, exit codes, schema) — never by one phase importing or reimplementing another's logic.
2. **The test gate is `python3 run_all.py`**, not just the Python suite. Changes to `EArchive.emulate_repair`'s formula specifically require updating `5-runtime-java`'s `RepairAuditor`, since it duplicates that formula on purpose as an independent check.
3. **No invented features.** Behavior must trace to an existing phase's README/code (there is no `SEMANTICS.md`). If you need a feature a phase's README doesn't describe, add it there first.
4. **C++ memory safety is explicit, not implicit**: no dynamic allocation beyond fixed-size buffers, every syscall return checked, no `sprintf`/`strcpy`/`gets`. Run `make asan` after any change to `1-phase-cpp/src/`.
5. **Stay minimal and match surrounding style** — this codebase has a consistent (if idiosyncratic) physics/biology metaphor; don't rename `EArchive`, `EParticle`, `PhaseEngine`, etc. to more "conventional" names.

## Multi-agent team (`.claude/agents/`)

Delegate to the agent that owns the phase; start with `architect` for anything crossing phase boundaries. `ir-tac-engineer` owns `ir.py`/`tac.c`/`form*.c`, none of which exist yet.
