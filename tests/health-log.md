# health log — Ever x ClauseShield sprint (partial; work stopped at the end of this run)

Branch `sprint/clauseshield-noll`, worktree `~/Downloads/4ever.worktrees/clauseshield`, from `fae24e8`.
Nothing is committed or pushed.

## Baseline (fae24e8, before any change)

- `python3 tests/run_all.py`: **57 passed, 0 skipped, 0 failed of 57 suites, exit 0**.
  Run with `EVER_TOOLCHAIN_PATH=/usr/local/opt/openjdk@21/bin:$HOME/.cargo/bin` and `JAVA_HOME=/usr/local/opt/openjdk@21`.
- ASan/UBSan kitchen sink (`0-atom-c/kitchen_sink.c` and the layer sources): exit 0, no sanitizer reports.
  ASan's leak check is unsupported on macOS; leaks were not checked with `leaks`.
- `tests/gold_check.py` (the "Gold standard" suite): passes inside the gate.
- `run.sh` on `fae24e8`: exit 1. Layers 0–2 and Layer 3 (Ruby), Layer 4 (SQL), Research passed. **TAC IR (C) failed** with `heal(1/0) recovers to 1 (not fallback 99)`, 86 passed and 1 failed in `0-atom-c/tac_test.c`. This failure predates the sprint, and the gate's own C tests do not run this assertion.

## Changes so far (uncommitted)

- `spec/reason_codes.tsv`: the reason-code registry (7 Unknown codes, 6 note codes).
- `everconf/`: rewritten to 0.2.0 (`Unknown(code, reason)`; no `None` in any value; `require(min_confidence)`;
  `corroborate`; JSON shape; labels; clause/tone reads; financial profile with an append-only hash-chained
  audit log and replay; stdlib HTTP adapter; zero-dependency Node client).
  - Tests: 7 Python files, 0 failures. Node adapter tests: 8/8, including an end-to-end call to the Python service.
  - Test changes: the 0.1.0 pytest file used `UNKNOWN` and `unwrap(default=None)`. `unwrap` returned a null, and
    `UNKNOWN` had no reason, so both were replaced. Each old test's intent is kept.
- `2-interpreter-python/syntax.py`: a source that fails to lex or parse now yields an `Unparsed` node instead of `None`.
  `syntax_test.py` (Pipeline): 80 passed, 0 failed.
- `tests/run_all.py`: nine new suites added (reason registry, everconf x7, Node Express client).
- `tests/test_reason_registry.py`: passes.

## Not done (blocking the sprint's Done Means)

- `2-interpreter-python/forgive.py` still returns `None` for the node on parse failure (lines ~337, ~346).
  `parse_lex_executor.py` and `syntax.distinct_skeletons` still test for `None`. `ir.py` and `emit.py` do not handle `Unparsed` yet.
- No Python no-null test for the lexer and parser paths.
- C ABI: 112 `return NULL` sites in `0-atom-c`. Not audited; none changed.
- C++ `1-phase-cpp`: not audited.
- Ruby `3-dsl-ruby/ever.rb` and Java `5-runtime-java`: parsers not checked.
- `docs/FINANCIAL_CONTINUITY.md` (plain-English spec): not written.
- Adapter is not wired into ClauseShield's `server.ts` (outside this repo).
- Consolidation report (Part 4): not written.
- The final gate run, ASan rerun, and `gold_check` rerun after the changes: not done.

## Run 2 (after the Python parser, everconf, and registry changes)

- `python3 tests/run_all.py`: **68 passed, 0 skipped, 0 failed of 68 suites, exit 0.**
  New suites: Reason registry (Python and C tables against `spec/reason_codes.tsv`),
  Reason registry (C), Lexer/parser no-null, and seven everconf files plus the Node Express client.
- ASan/UBSan kitchen sink: exit 0, no sanitizer reports.
- `tests/gold_check.py`: inside the gate, PASS, both backends identical.
- `run.sh`: not rerun after the changes. Its `TAC IR (C)` failure from the baseline is still open.

## Consolidation check (Part 4)

- **Branches.** No local `main` exists. `master` (1f6ea44) is an ancestor of `feature/heal-repair-order`, which is 8 commits ahead. PR #17 targets `main` on `everlang-dpl`.
- **Remotes.** This repo has `Zdycomp` (pointing at `claude-code-terminal-title`) and `everlang` (`zdycomp/everlang-dpl`). It has no remote for `Zdycomp/4ever`, which the brief names as the publish target. Nothing was pushed.
- **Language layers.** Per `docs/MERGE.md`, all layers from the four sources are in the branch. `everlang/main` contains `everlang_standalone/`, and every file in `~/Downloads/everlang_standalone` is present there except `benchmarks/ez_biocomputing_444_test.py`, which exists only in Downloads. That file is not merged. Its reason is not known.
- **Lexers and parsers (Part 4.2).** The only lexer and parser are in `2-interpreter-python` (`syntax.py`, `forgive.py`) and are no-null now. Ruby and Java have no lexer or parser. Their null and nil returns are listed under open items.

## Open items

- `forgive.py`, `syntax.py`, `parse_lex_executor.py`, `ir.py`, `emit.py`: done.
- C pool getters (`ev_pool_get`, `ev_pool_blob`, `ev_pool_list`, `ev_pool_record`, 4 callers) return NULL for an invalid ref. Not changed.
- The rest of the 112 C `return NULL` sites: not audited.
- `3-dsl-ruby/ever.rb` `evolve` returns nil in three places, and `5-runtime-java` `EverRuntime.java:301-302` and `EverRepair.java:79-132` return null. Not changed.
- C++ phase layer: no null returns found by grep. No boundary test added.
- `run.sh` TAC IR (C) failure from the baseline.
- `/doctor` request (separate, from the same turn): not started.
- Adapter is not wired into ClauseShield's `server.ts`, which is outside this repo.

## Decisions for Rick

- Commit policy: nothing is committed.
- `corroborate` may lift a value to 180 when two independent sources agree. Confirm this exception.
- Clause "very sure" is reachable only from a non-model source.
- Financial threshold default is 224.
- Added codes `MALFORMED` (lex and parse failures had none) and `DERIVED` (a note).
- Whether `benchmarks/ez_biocomputing_444_test.py` should be merged.

## Run 3 (front-door refactor, behaviour-preserving)

- `python3 tests/run_all.py`: **70 passed, 0 skipped, 0 failed of 70 suites, exit 0**, including
  the new Front-door snapshot suite (40 sources x 7 entries reproduce exactly).
- Snapshot baseline recorded before the refactor; mutation check confirmed it fails on a
  one-string change.
- `run.sh` and the C kitchen sink were not rerun for this change: it touches Python only.
- Open findings (not fixed, see tasks.md): recoveries dropped on the forgiving path (verified:
  `let x = [1,]` gives the strict recovery, `run_source` reports none); forgiving and strict
  ASTs differ on three valid programs with zero corrections recorded.
