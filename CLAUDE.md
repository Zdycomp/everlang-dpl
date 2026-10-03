# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo actually is

The thesis is a multi-phase, cross-platform language ecosystem — Python frontend → TAC IR → C++ analysis → Java execution runtime, SQLite-backed history — but **most of that is aspirational**. What exists today:

| Phase | Dir | Reality |
|---|---|---|
| Python runtime | `everlang_standalone/` | A working "DPL / Everlang" package: a 4-stage confidence pipeline, a quantum/entanglement module, a biocomputing (DNA) module including a real lexer/parser pair, a 6-language template generator (`transpiler/`) that also accepts user-registered languages, a DPL frontend (`frontend/`: `Supercodalexer` → `QuantificationUltraParser` → `MegaExecuter`, grammar in its README), and its unittest suite. This is the actual substance of the repo. |
| C++ analysis | `1-phase-cpp/` | One native CLI, `verify_particle` — a safety-verification gate, not a general analysis phase. Gates every `ReinforcedArchive` write, including each per-language transpiler rendering (one call per language, not a bundled multi-language blob). |
| Java runtime | `5-runtime-java/` | Two read-only JDBC auditors — `SelfHealingAudit` (repairs) and `TranspileAudit` (transpiler output) — not a general IR execution runtime. |
| SQL archive | `4-archive-sql/` | A real SQLite persistence layer (`SqlArchive` + `schema.sql`, including `transpilations` and `custom_template_versions`) reinforcing the in-process `EArchive`. |
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
python3 -m unittest discover tests       # full suite
python3 -m unittest tests.test_dna_sequencer -v   # a single test module
python3 -m pyflakes .                    # lint
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
python3 -m unittest discover -s 4-archive-sql/tests -t .   # from the repo root
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

- **`core/archive.py`** (`EArchive`): in-process, thread-locked, three responsibilities — `log_boundary_marker` (append-only event log), `emulate_repair` (the self-healing formula: `error_distance` 1–3 → `confidence = 250 - error_distance*30`; else quarantined; **this exact formula is independently re-derived by the Java auditor**, so changing it here without updating `5-runtime-java` breaks that phase's contract), `calculate_evolve_vector` (action/reaction/force physics metaphor, no-ops to 0.0 if reaction or force is 0 — indistinguishable from a genuine zero vector, a known ambiguity).
- **`biocomputing/sequencer.py`** is a genuine lexer/parser pair that deliberately does *not* silently drop invalid characters the way `quaternary.py` does.
- **`frontend/`**: the Mega stages must stay byte-identical to `baseline.py` (tokens, statements, diagnostics, results) — `tests/test_frontend.py` fuzzes this. Any grammar change goes into `frontend/grammar.py` and its README, and both implementations. The speed numbers in its README are measured; don't claim 4× end to end, it doesn't reach it.
- **`transpiler/`** (`SuperTranspiler`): plain `str.format` substitution into per-language templates — a syntax-offset generator, not a real transpiler with a source grammar. Built-in DPL values are escaped (`VALUE_ESCAPES` / `escape_dpl_value`, mirrored by `TranspileAuditor.escapeDplValue`) so DPL output reads back through `frontend/`; MegaExecuter's generated renderer applies the same table. Adding a *built-in* language to `LANGUAGE_TEMPLATES` requires the same change in `5-runtime-java`'s `TranspileAuditor`, which hardcodes the six built-ins as its independent cross-check (same duplication-on-purpose pattern as the repair formula). User languages go through `register_language` instead: each edit is a new row in SQL `custom_template_versions`, every rendering is stamped with its `template_version`, and the auditor re-renders each row from exactly that version. Templates may use only bare `{name}`/`{val}`/`{type_spec}`/`{conf}` fields, because the Java side re-implements `str.format` for that subset only.

### Cross-phase reinforcement of the self-healing Archive
`EArchive` has no persistence and no external verification. Three things reinforce it without replacing it, each through a narrow, documented contract — never by reimplementing another phase's logic:
1. **`1-phase-cpp/bin/verify_particle`**: a pre-write safety gate. Contract: `verify_particle <confidence>` with the value on stdin; prints `VALID` or `INVALID:<REASON>` (see `1-phase-cpp/README.md` for the exact table). Checks confidence bounds and value length (≤4096 bytes) — things `EParticle` itself doesn't all check (value length isn't an `EParticle` concern at all). Each per-language transpiler rendering gets its own call — the 4096-byte budget is per snippet, never a bundled multi-language blob.
2. **`4-archive-sql/archive_db.py`** (`SqlArchive`): durable SQLite persistence (`tapestry.db`, gitignored, never commit it) for boundary markers, repairs, evolved vectors, transpilations, custom transpiler templates, and anything the C++ gate rejects (`rejected_writes`). Schema in `schema.sql`, CHECK-constrained on confidence range.
3. **`5-runtime-java`**: two independent, **read-only** JDBC auditors, never writing. `SelfHealingAudit` re-derives expected `emulate_repair` outcomes from the formula above and flags drift in `repairs`. `TranspileAudit` re-renders `SuperTranspiler`'s six built-in templates (plus custom ones, by stamped version, from `custom_template_versions`) from each `transpilations` row's stored inputs and flags any mismatch against the stored `rendered_code`. Run via `java -cp target/self-healing-runtime.jar com.everlang.runtime.<ClassName> <db>` — only `SelfHealingAudit` is the jar's default entry point.

**`everlang_standalone/everlang/core/reinforced_archive.py`** (`ReinforcedArchive`) is the bridge: same public API as `EArchive` (`log_boundary_marker`, `emulate_repair`, `calculate_evolve_vector`) plus `transpile_and_archive(name, val, type_spec, conf)`, which runs `SuperTranspiler` and reinforces each of its renderings (built-in and custom) the same way, plus `register_language`/`unregister_language`, which persist custom templates to SQL and reload them on init. Every write still goes to the in-process archive (or the transpiler, which is always purely in-process) unconditionally — zero behavior change for existing callers — and is *additionally* run through the C++ gate and persisted via SQL when both are available. Locates the C++ binary and the SQL module by path relative to the repo root; imports `archive_db.py` by file path under a dedicated module name (not a bare `import archive_db` after a `sys.path` insert — that's silently defeated if anything else already registered a module of that name in `sys.modules`). Both backends are optional: missing or failing, `ReinforcedArchive` degrades to plain in-process behavior rather than raising. Every SQL write is wrapped so a `sqlite3` error disables SQL reinforcement for that instance rather than propagating.

## Rules

1. **Boundary awareness.** Identify which phase a change targets before writing code. Phases communicate only through the documented CLI/file contracts above (exact strings, exit codes, schema) — never by one phase importing or reimplementing another's logic.
2. **The test gate is `python3 run_all.py`**, not just the Python suite. Changes to `EArchive.emulate_repair`'s formula specifically require updating `5-runtime-java`'s `RepairAuditor`, since it duplicates that formula on purpose as an independent check.
3. **No invented features.** Behavior must trace to an existing phase's README/code (there is no `SEMANTICS.md`). If you need a feature a phase's README doesn't describe, add it there first.
4. **C++ memory safety is explicit, not implicit**: no dynamic allocation beyond fixed-size buffers, every syscall return checked, no `sprintf`/`strcpy`/`gets`. Run `make asan` after any change to `1-phase-cpp/src/`.
5. **Stay minimal and match surrounding style** — this codebase has a consistent (if idiosyncratic) physics/biology metaphor; don't rename `EArchive`, `EParticle`, `PhaseEngine`, etc. to more "conventional" names.

## Multi-agent team (`.claude/agents/`)

Delegate to the agent that owns the phase; start with `architect` for anything crossing phase boundaries. `ir-tac-engineer` owns `ir.py`/`tac.c`/`form*.c`, none of which exist yet.
