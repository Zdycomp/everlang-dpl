# tasks — 4Ever

Working memory. Read at session start, updated before any session reports done.
Three parts, always. Check items off as you go, not in a batch at the end.

Before adding an item, verify it is still open against the live code. Before
closing one, verify in the code that it actually is. Line numbers go stale
fast in this repo — cite the symbol, and the file, and let the number be a hint.

---

## Decisions

- [x] **R is no longer a target.** Ricky's call, 2026-11-09: the backends are
  Go, Rust, Kotlin and JavaScript; finality stays Go and Rust. `REmitter` and
  its `BACKENDS` row are gone from `emit.py`, `ever build` no longer offers
  `-t r`, and `test_backends.py` no longer looks for `Rscript` — it was the
  last skip in the gate. R stays in `language_matrix.py` as a language the
  inspector recognises (`compatibility`, no backend), like Julia or MATLAB.
  Backends: 68 passed, 0 failed, 0 skipped. — 2026-11-09
- [x] **A verdict is an exit code, not a string.** `tests/run_all.py` decides a
  suite by exit status (`SKIP_EXIT` 77 = skip) and by the REQUIRES preflight,
  never by output text. Earlier it classified with `if "SKIP:" in out`, which
  recorded `test_zeroth.py` as SKIP while it exited 0 having proved C, Python
  and SQL agree on all 257 band values, and downgraded genuinely failing suites
  to SKIP whenever their output mentioned the word. — closed 2026-10
- [x] **Skips are not free.** The run exits 0 only when nothing failed AND
  nothing was skipped. `--allow-skip` is the explicit opt-out for a machine
  that genuinely lacks a toolchain; `EVER_TOOLCHAIN_PATH` is how a toolchain
  outside the system paths gets found instead of skipped. — closed 2026-10
- [x] **The ceiling constant is pinned by test, not by a shared header.**
  `tests/test_invariants.py:CEILING_SITES` reads `E_DEPTH_CEILING` /
  `E_EMULATE_CEILING` out of all ten sites across C, Python and Ruby and
  requires them equal — replication stays deliberate, agreement stays proved.
- [x] Ownership boundaries are enforced by agent, not by convention:
  `tac-optimizer` / `test-engineer` / `memory-safety` own disjoint file sets.
- [x] **Every repair runs evaluate → plan → execute**, identically in every
  layer, with a trace line per phase. See `CLAUDE.md`; parity across Python,
  Java and C is held by `tests/heal_parity_test.py`.
- [x] **A failure is named by its first cause, in the frame that ran it.** The
  primary, strategy, fixture and fallback each run in a cause frame; the first
  failure noted inside is the reason, and a probe runs in its own frame so a
  re-read reaches the same answer. Replaces a static tree walk that could not
  see through function calls. The named process is `docs/SEMANTICS.md` §9. — 2026-11-03

## Action items

### Front door: one deep module, behaviour preserved (2026-11-13)

Candidate from the architecture review, decided in the grilling loop (Q1–Q9).
Design: `2-interpreter-python/front_door.py`, `front_door(src, heal: bool)` with no
default, returning `FrontResult`. The six public entries are adapters over it.
Semantic analysis stays with callers. `compile_ever` is deleted in a later change.

- [x] Characterization snapshot recorded before any code moved: `tests/front_door_snapshot.py`,
      baseline `tests/front_door/baseline.json` (40 sources x 7 entries: 13 integration
      programs, 27 edge sources; exceptions recorded as results). Deterministic across
      separate processes once wall-clock fields (`born_ms`, `run_id`, `ts_ms`, ...) are masked.
- [x] Mutation check: a one-string change to the lex-stage name fails the snapshot
      (18 differences); restored, it passes.
- [x] `front_door.py` written. Deviation from the approved Q6 shape: `FrontResult` also
      carries `tokens` and `recoveries`. Without them `compile_ever` and `parse` can't
      reproduce today's output exactly. Approved shape kept: `node`, `error`, `corrections`, `stage`.
- [x] `syntax.parse`, `syntax.compile_ever`, `forgive.parse_forgiving`,
      `architecture.front_end` are adapters over the front door. `ir.parse_to_ir` and
      `runtime.run_source` contain no parsing of their own: they reach the front door
      through `parse` and `parse_forgiving`, so they are unchanged.
- [x] Snapshot reproduces exactly after the refactor (40 sources x 7 entries).
- [x] Affected suites green: Pipeline 80/0, Interpreter 83/0, EvScope 72/0, Parser 75/0,
      Lexer 91/0, Architecture 18/0, ParseLexExecutor 12/0, no-null parse, ceiling, anchor, healing, registry.
- [x] Full gate (`tests/run_all.py`) with the snapshot suite registered: 70 passed, 0 skipped, 0 failed, exit 0 (2026-11-13).
- [ ] Deferred (Q9): delete `compile_ever` and its `syntax_test.py` inputs, in a later change.

Findings, not fixed (Q2: behaviour preserved; each needs its own decision):
- [ ] **Recoveries are dropped on the forgiving path.** `parse_forgiving` never sets
      `node._recoveries`, so `run_source` (which reads it at `runtime.py` ~456) reports
      none. Verified: `let x = [1,]` and `show x` gives the strict parser's `trailing comma
      in a list` recovery, and `run_source(...).recoveries == []`. Pre-existing: the
      original `parse_forgiving` also did not attach recoveries.
- [ ] **Forgiving and strict ASTs differ on three valid programs** with zero corrections
      recorded: `tests/integration/09_zero_confidence.ever`, `11_kitchen_sink.ever`,
      `12_logic_loops.ever`. Cause not yet found. Preserved by the snapshot.

### Sprint: Ever x ClauseShield — No-Null, Financial Continuity, everconf (2026-11-13)

Worktree `~/Downloads/4ever.worktrees/clauseshield`, branch `sprint/clauseshield-noll`
from `fae24e8`. The main checkout is not touched: its working tree has 135 tracked
paths missing from disk (`0-atom-c/` … `8-finality/` among them) and 27 uncommitted
changes that belong to Ricky.

Decisions (mine, for Rick to redirect):
- **Unknown is Ever's z made explicit.** Confidence 0, a reason code from the
  registry, a human reason, and the chain of reasons it carried. Null is banned at
  every boundary: no Python `None`, no C `NULL`, no JSON `null`.
- **Reason registry is one file**, `spec/reason_codes.tsv`. The six codes from the
  brief, plus `MALFORMED` (added: lex and parse failures had no code, and none of
  the six fits them). Every layer's table is checked against the file by a test.
- **`everconf` changes shape.** `UNKNOWN` (a singleton with no reason) becomes
  `Unknown(code, reason, chain)`. `unwrap(default=None)` goes, because it returns
  a null. Breaking for 0.1.0 (Beta); the README says so.
- **JSON result shape.** `value` is always present and never null. An unknown
  result carries `"value": {"unknown": true}`, `score` 0, `percent` 0,
  `label` "can't tell", and at least one reason.
- **Label bands** (score on 0–256): 224+ "very sure", 160–223 "pretty sure",
  1–159 "not sure", 0 "can't tell". Gemini's read is third-party (INTAKE 120), so
  "very sure" is reachable only from a non-model source.
- **Clause-read score** = min(grounding, source, corroboration). Grounding: the
  quoted phrase appears verbatim in the document (256), else Unknown
  `UNVERIFIED_SOURCE`. Source: 120. Corroboration: 192 when a local trap rule
  (ported from `ClauseShield/src/utils/clauseAudit.ts`) matches the same passage
  and its category agrees, else 120.
- **Financial profile** is a strict mode in `everconf`: any Unknown is a hard stop
  for an action and still returns the full explanation. The audit log is
  append-only JSONL with a hash chain. Replay is checked by running the same
  inputs twice.
- **Commits.** Committed as `e4934b7`, rebased onto `everlang/feature/heal-repair-order`
  as `b22d6fd`, pushed to `everlang` as PR #18 (based on PR #17's branch). Later fixes are
  uncommitted until Rick approves.

Action items (checked as they close, each with the test that proves it):
- [x] Baseline on `fae24e8`: `run_all.py` and the ASan/UBSan kitchen sink, recorded in
      `tests/health-log.md`. `run.sh` failed `TAC IR (C)` at baseline; fixed by the
      archive-path change in `0-atom-c/tac_test.c`.
- [x] `spec/reason_codes.tsv`, with `tests/test_reason_registry.py` checking the C table,
      `everconf` and the spec against each other. The C++ and Ruby layers have no reason
      table, so the parity test does not cover them.
- [x] `everconf` 0.2.0: `Unknown`, `require(min_confidence)`, poisoning, serialisation,
      no `None` in any value (`everconf/tests/`, run by the gate).
- [x] `everconf`: JSON shape, plain-words labels, clause-read scorer. Examples in
      `everconf/docs/JSON.md`, checked by `everconf/tests/test_docs.py`.
- [x] `everconf`: financial profile (strict mode, provenance, hash-chained audit log,
      replay). Spec: `docs/FINANCIAL_CONTINUITY.md`.
- [x] Adapter for the Express server: loopback HTTP service and Node client, tested end
      to end (`everconf/adapters/express/wrap.test.mjs`).
- [x] Python lexer and parser: `parse`, `parse_forgiving`, `compile_ever` and `front_end`
      return `Unparsed` instead of `None`. `distinct_shapes` and `ir.distinct_skeletons`
      skip failed parses. Regression check in `tests/test_no_null_parse.py`.
- [x] C pool getters (`ev_pool_get/blob/list/record`) return a typed Unknown composite,
      never NULL. `ev_list_push`, `ev_record_set`, `ev_equal` and `ev_serialise` refuse
      unknown composites. Checked by `0-atom-c/unknown_composite_test.c`.
- [~] Ruby `3-dsl-ruby/ever.rb`: `evolve` returns a Z with a reason, not nil. Checked by the
      gate's Ruby DSL suite (`ruby 3-dsl-ruby/ever.rb`).
- [ ] Java: `5-runtime-java/com/codric/ever/EverRuntime.java:301-302` and
      `EverRepair.java:79-132` still return null. Open.
- [ ] C ABI beyond the pool getters: the other `return NULL` sites in `0-atom-c` (112 in
      total) are not audited. Open.
- [ ] C++ `1-phase-cpp`: grep finds no `nullptr`/`NULL` returns in `phase.cpp` or
      `phase.hpp`. No boundary test yet. Open.
- [~] Consolidation: see `tests/health-log.md`. Local `main` does not exist; `master` is an
      ancestor of `feature/heal-repair-order`. One Downloads file is not in the repo
      (`benchmarks/ez_biocomputing_444_test.py`). Open: decide whether to merge it.
- [~] `tests/health-log.md`: final summary, updated as the last step of each run.

Open for Rick: commit policy above; whether clause reads should ever reach
"very sure" by a route other than a non-model source.

### Evaluate an AI proposer (2026-11-10): design only, `docs/EVALUATION.md`

The harness is not blocked. Wiring any model in is blocked on Evaluation
Q1–Q3 under Open questions.

- [x] Design: dimensions, golden set, scoring, regression gate, use. Its §0
      table and the gate checks ran on the real path (`run_source`;
      `archive.sql` + `repair.sql` in SQLite `:memory:`).
- [ ] Harness: `tests/eval/cases/` layout, record and replay by SHA-256, its
      own `RepairRegistry` via `repair.use_registry` and its own
      `EVER_REPAIR_STORE` — owner: test-engineer
- [ ] Smoke set: one case per §9 reason and outcome, plus the eight traps —
      owner: test-engineer
- [ ] Mutation enumerator over known-good programs; truth by `_same_value`
      on a declared domain
- [ ] Witness and `extern` checks, by the parser, before evaluation
- [ ] Append-only `tests/eval/ledger.jsonl`; admission case by case against
      the last admitted run
- [ ] `tests/test_eval_proposer.py` (exit 0/1/77) joins `run_all.py` once its
      recorded smoke set is checked in, not before
- [ ] Verify: two runs over the same recordings give a byte-identical outcome
      table

### Syntax across every archive (2026-11-10)

- [x] `4-archive-sql/syntax_universal.sql`: attaches tapestry, repair, zeroth
      and notebook read-only and unions every syntax event into `temp.v_syntax`,
      each row tagged with its basis (`stage` > `term` > `defect`). Checked on
      the real archives (321 rows: the C, Ruby and SQL inspections) and on copies
      with one injected row per basis (325, near-misses "thereof"/"complex"
      excluded). Not run through the `sqlite3` CLI itself here; the SQL ran on
      SQLite 3.37.2 via Python.
- [ ] **4ever does not archive its own syntax errors.** `compile_ever`
      (`syntax.py`) names `lex` and `parse` failures, but nothing writes them to
      `error_catch`; only ReFix does, as `build`. Until it does, the `stage`
      basis is always empty.

### Dead-code elimination after constant folding (2026-11-07) — owner: tac-optimizer

Found on reading: there is no folding in `form_lower.c` — it only lowers.
Folding and dead-register removal are TAC passes in `tac.c` (`ev_optimise`),
which every module from either lowering path goes through. The missing piece is
the control-flow half: a folded condition still leaves its JUMP_IF and the arm
it can never take. The pass goes in `tac.c` beside its siblings; `form_lower.c`
and `form.c` need no change, and no form kind is added.

- [x] `ev_pass_dead_code` in `tac.c`: a JUMP_IF whose condition is a CONST in
      the same block becomes a JUMP to the arm the interpreter would take
      (one truthiness helper shared with OP_JUMP_IF, z → unknown arm); blocks
      unreachable from block 0 are cleared. HEAL is never folded.
- [x] Run order in `ev_optimise`: fold → dead code → dead regs → conf prop.
- [x] Verify: optimised vs unoptimised agree on value, tag AND confidence for
      folded true/false/z/text conditions, nested and N-arm branches, through
      both lowering paths and through a function called via `OP_CALL`
      (`ev_interp_run`, not `ev_interp_call`). 18 programs, 68 checks, all
      agree; the scratch probe also showed the pass absent on the old tac.c.
- [x] Gate: kitchen sink (`ks_pipeline_optimiser_safety`) and every suite in
      `run_all.py`; ASAN + UBSan zero errors, zero leaks. Same as baseline:
      49 pass, 0 fail, 6 skip — the skips are javac/Go/Rust/Kotlin absent on
      the machine that ran it, and none of those suites link `tac.c`.
- [x] Scratch comes from the function arena, not calloc, so
      `test_invariants.py`'s raw-allocation count for `tac.c` is unchanged.
- [x] Found while verifying, fixed in the same file: `ev_pass_dead_regs` removed
      a parameter's binding LOAD in block 0, so `def dbl(n) = if 1 < 2 then n*2
      else n` returned z once optimised. See lessons.md.
- [~] Hand-off to test-engineer (owns `kitchen_sink.c`): add to
      `ks_pipeline_optimiser_safety` (1) form-path cases `if 2 < 1 then 42 else
      7`, `if z then 1 else 2`, a 3-arm match on `false` — compare tag, value
      AND the result's confidence, optimised vs not, and assert the optimised
      global body has no JUMP_IF left; (2) `def dbl(n) = if 1 < 2 then n * 2
      else n; dbl(21)` through `ev_interp_run` — expected 42, got z before the
      dead-regs fix. Today the suite compares tag and int only, on the node
      path only, so neither bug could fail it.
      Done 2026-11-09: the suite now compares the confidence as well, and
      `ks_pipeline_optimiser_param_load` runs `dbl(21)` through `ev_interp_run`,
      optimised and not (42 at INTAKE). Still open: the form-path cases in (1).

### Integration suite: Backend B cannot carry function confidence (2026-11-08, closed 2026-11-09)

- The spec makes a function's result 120/256 (§4.1, §4.3). `tests/integration/`
  `{06,07,08,11,13}.expected` still say `[256/256]` on function results. Backend A
  (`tests/ev_integrate.py`, the Python evaluator) now computes 120, so it fails them.
- Backend B does not run the program in C. It evaluates in Python and sends literal
  values to C, and IR literals carry no confidence (`2-interpreter-python/ir.py`
  `EvNode`, `serialise`). B therefore prints 256 for every non-z value, and updating
  the .expected files makes B fail.
- Decided 2026-11-09: carry confidence on IR literals. Wire format: a uint16 after
  `line` for BOOL, INT, REAL and TEXT (`ir.py` `_LITERAL_KINDS`, `ir.c`
  `is_literal_kind`). C lowering uses it (`ev_emit_const_conf`). Constant folding
  takes the least confidence of its operands, and a branch on a literal with an
  earned confidence is not folded. B sends each binding's earned confidence. The
  five `.expected` files changed on function-result confidence only (20 lines).
  Integration: ALL GOLD, with Backend A == B == expected.
- Sandbox note, not a repo change: the sandbox refuses the Xcode `xcrun` cache under
  `/var/folders`, so `gcc` fails with "couldn't create cache file". The gate runs
  with a `gcc`/`g++` shim in `$TMPDIR/cc-shim` that calls the Command Line Tools
  clang with `-isysroot`. A machine without that sandbox does not need it.

### Named repair process: heal and learn through calls (2026-11-03)

- [x] forgive.py treats `heal (` as a call and `) using` as two items, so
      `heal (heal (1) using …)` and `[heal (1) using …]` were mangled before the
      strict parser ran. `_heal_form_at` and `_HEAL_WORDS` fix it. Owner:
      2-interpreter-python.
- [x] Python: a z is named by the first failure in its frame; `heal (f(0))` and
      `learn (f(0))` act on `division by zero`. `scope.py` `_primary_assessment`,
      `_settle`; `heal_order.py` `note`, `cause_frame`.
- [x] `docs/SEMANTICS.md` §9 written: the three phases, the reason vocabulary, the
      frame and probe rules, and the known limits.
- [x] `tests/test_healing.py`: `TestCauseNaming` (5) and `TestHealFormsAreNotCalls`
      (4). Its `__main__` guard sat mid-file, so `TestStrategy` (4) never ran as a
      script; the guard is last now and all 28 run.
- [x] **C names causes through calls, as §9 says.** The single `last_failure`
      slot is gone. The cause is a frame, as in `scope.py`: `OP_CAUSE_OPEN` and
      `OP_CAUSE_CLOSE` bracket each heal's primary, `OP_NOTE` names a z literal
      and an unbound name, and `OP_SETTLE` hands a z heal's reason up. The
      strategy and fallback run in dropped frames. Before the fix,
      `heal (f(0))` gave FALLBACK `5` in C and SUBSTITUTE `1 [112/256]` in
      Python. Now both give `1 [112/256]`. `tac.c`, `tac.h`, `tac_test.c` (87 pass,
      3 new), ASAN/UBSan clean, zero leaks on the Tac and kitchen-sink suites. — 2026-11-03
- [x] Parity matrix: `call:0` rows in `cases.tsv` (`call_div_plain_all`,
      `call_div_plain_empty`), `heal_matrix.c` and `HealMatrix.java`. Python, C
      and Java agree. Java has no user functions, so its call case is the
      callee's z, a weaker claim than the other two layers make. — 2026-11-03
- [ ] `learn` in the C layer is not implemented (`heal_matrix.c` skips it); §9
      describes it for all layers. Owner: `tac-optimizer`.
- [x] `ever run` no longer crashes when `~/.ever/profile.json` is not writable: the
      save goes through `ever_cli._save_profile`, which warns on stderr and keeps
      the result. `profiler_test.py` section 12 (2 checks) pins it. — 2026-11-04
- [x] `kotlinc` 2.4.21 is installed (`brew install --ignore-dependencies kotlin`).
      Homebrew's `kotlin` formula depends on the latest `openjdk`, which is
      arm64-only; this Mac is x86_64 and already has `openjdk@21`, so kotlinc runs
      with `JAVA_HOME=/usr/local/opt/openjdk@21`. — 2026-11-04
- [x] Full regression gate has all toolchains and no skips. On 2026-11-06,
      `python3 tests/run_all.py` reported 55 passed / 0 skipped / 0 failed.
      Rust 1.99.1 is exposed from `~/.cargo/bin` through `EVER_TOOLCHAIN_PATH`.
      R 4.6.2 was downloaded from CRAN, verified against its published SHA1
      and Apple Developer ID signature, and installed in user space because
      the system installer requires interactive admin authorization. A local
      `~/.local/bin/Rscript` launcher runs the verified framework at
      `~/.local/opt/r-4.6.2/R.framework`; set `R_HOME` to its `Resources`
      directory and include `~/.local/bin` in `EVER_TOOLCHAIN_PATH`. A fresh
      VS Code shell may omit that variable: the plain invocation in this
      session skipped Rust and R (53 passed / 2 skipped). Exposing
      `~/.cargo/bin:~/.local/bin` in `PATH` and `EVER_TOOLCHAIN_PATH`, with
      `R_HOME=~/.local/opt/r-4.6.2/R.framework/Resources`, restored the full
      55 passed / 0 skipped / 0 failed gate. Focused results: Backends 85/0/0;
      Finality 8/0/0. The Java suites also need
      `EVER_TOOLCHAIN_PATH=/usr/local/opt/openjdk@21/bin`: `/usr/bin/java` is a
      stub, and without it they fail ("Unable to locate a Java Runtime"),
      not skip. Rerun 2026-11-06 with that set: 55 passed / 0 skipped / 0 failed.
      The C kitchen-sink ASan/UBSan build exits 0 with no sanitizer reports.
  - [x] Confirm the existing Rust toolchain runs from `~/.cargo/bin`.
  - [x] Install the verified CRAN R runtime in user space.
  - [x] Run the focused Backends and Finality suites with zero skips.
  - [x] Rerun the full gate; do not use `--allow-skip`.

### Finish the language: `example` and `anchor` get surface syntax (2026-10-28)

SEMANTICS.md §4.2–4.6 and the §8 worked example define how a function earns
trust (Examples) and depth (anchor). `abstract.py` implements it; the real
front door (`runtime.py` → `scope.py`) has no syntax for it and instead
treats *any* decreasing measure as anchored — depth handed out, not earned.
`example` and `anchor` are reserved keywords that nothing parses.

  Design, 2026-11-08 (Python front door first; C parity is its own line below):
  - `syntax.py`: `Example(name, args, expect)` and `Anchor(name)` statements,
    parsed in `statement()`, sequenced in `program()`, checked in the Semantic
    pass (bound name, arity). `Semantic._recursive(fn)` sits beside `_measure`.
  - `scope.py`: `ScopeEntry` gains `examples_passed`, `examples_failed`,
    `recursive`, `refusal`. `def` binds at `E_INTAKE` (120). A call to a
    function at confidence 0 is z. Anchored iff `anchor_id != 0` and the measure
    is a parameter (§4.6): the measure alone no longer lifts the ceiling.
  - `runtime.py`: `example` runs the call through `eval_node`; a z or a wrong
    value is a failure (§4.2, formula exact). `anchor` refuses an uncleared
    function (below `E_EXECUTE_FLOOR`) and a recursive one with no measure
    (§4.4), each as z with a reason.
  - `runtime.eval_confidence`: a user-function call is min(c_f, args, result).
- [x] Syntax: `example f(a, …) = v` and `anchor f` statements in `syntax.py`
      (AST nodes, parser, statement sequencing, Semantic pass). — 2026-11-08
- [x] Semantics in the runtime, exactly as §4: `def` at INTAKE 120;
      [EXAMPLE] confidence; [ANCHOR-FN] / [ANCHOR-REC] / [ANCHOR-⊥];
      limit(θ_f) = ∞ only when anchored ∧ measure, else ⌊π⌋ = 3.
      `runtime.py` `_run_example` / `_run_anchor`; `scope.py` call path. — 2026-11-08
- [x] Remove the auto-anchor-by-measure in `runtime.py` / `scope.py`. — 2026-11-08
- [x] Test: §8 run as a real `.ever` program, every row of its table asserted.
      `tests/test_anchor.py` (14 checks), gate suite "Anchor (SEMANTICS §8)". — 2026-11-08
- [x] SEMANTICS.md: grammar as built (EBNF) + §7 corrected to what is truly
      missing; parser docstring updated. — closed 2026-11-09: §10 (EBNF, notes,
      forgive.py), §7 rows corrected, loop docstrings say `do`.
- [x] C parity: `tac.c` now runs the call gate per function (`gated_call`, shared
      by `OP_CALL`, `ev_interp_call` and `ev_module_example`): an unanchored
      function nests floor(pi) activations of itself, an anchored one may recurse
      while its measure strictly decreases, and `EV_MAX_DEPTH` is 512 to match
      scope.py's backstop. `ev_module_set_measure`, `ev_module_example` and
      `ev_module_anchor` carry §4.2 and §4.4. Checked live by
      `tests/test_ceiling.py`. Limits: C compares scalars in Examples, not lists or
      records, and int64 caps the anchored case at fact(20) where Python computes
      fact(100). — closed 2026-11-09
- [x] `run_all.py` green: 56 passed, 0 skipped, 0 failed, 2026-11-09. Kitchen sink
      ASan/UBSan clean, 0 leaks by the macOS `leaks` tool. Call results are capped at
      INTAKE in C (`OP_CALL`, `ev_emit_call`) and in every transpiler, so the
      Backends suite is green on the 120 rule and the per-function depth guard. The
      gate runs with the gcc shim described in the Integration item.


- [x] **`tests/test_ceiling.py`** — the behavioural half of the depth contract.
  Closed 2026-11-09: each case runs one program through `run_source` and through the
  C interpreter (`ev_lower_module`, the OP_CALL gate, `ev_interp_run`), and requires
  the same value and confidence. Unanchored fact(3) = 6 and fact(4) = z; anchored
  fact(20) = 20! at 217/256, with Examples and the anchor fed to both layers. The
  gate runs it as "Depth ceiling (Py vs C)".
  Original note follows.
  `test_invariants.py` pins the *constant* at every site; nothing pins the
  *comparison*. `tac.c` gates on `depth >= E_DEPTH_CEILING` (in the OP_CALL
  case) while `abstract.py` gates on `depth >`, reconciled only by the
  0-based/1-based convention `CLAUDE.md` documents. Run one `.ever` program —
  `fact(3)`=6, `fact(4)`=z — through the Python evaluator and the C interpreter
  via `ev_interp_run` (never `ev_interp_call`, which skips the gate) and
  require the same answer from both. Owner: `test-engineer`.
- [ ] **Repair invariants are still twinned by hand.** `repair_test.py`'s
  docstring promises "every `refuses(...)` case below has a matching throw in
  `7-refix-node/src/archive.js`" — a promise in prose, with nothing reading
  both files. Either make the correspondence mechanical (enumerate the throws
  and the refuses, require a bijection) or demote it in the docstring from an
  invariant to a convention. Its own words: "If an invariant only holds in one
  of the two implementations, it is not an invariant, it is a convention."
  Owner: `test-engineer`.

### Review of the staged heal_order change (2026-11-07)

Gate, Linux VM with JDK 21, Go, Rust, Kotlin added: 54 passed / 1 skipped
(Backends: no Rscript) / 0 failed. Notebook failed once with `sqlite3
disk I/O error` writing `archive/notebook.db` on the VM's folder mount; with
the DB in /tmp it passes. ASan/UBSan kitchen sink: 33/0, no reports. The two
new `TestNestedHealsKeepTheirOwnRecord` tests fail against HEAD's
`heal_order.py`/`scope.py`/`syntax.py` and pass now, so they catch the bug.

- [x] Unstage both `7-refix-node/{signatures,tests}/oracleJdk-27.jdk` trees — done in
      942ded9: unstaged, `*.jdk/` ignored, 38M copies left on disk.
      (772 files, a full JDK twice) before committing; they are already gone
      from disk. `signatures/` is in package.json `files`, so it would also
      ship to npm. Add `*.jdk/` to `.gitignore`.
- [x] `repair.py` `get_registry() -> Optional[RepairRegistry]` is wrong: it
      never returns None, and `scope.py:698` / `syntax.py:1722` call
      `.archive_repair` on it directly. Revert to `-> RepairRegistry`.
- [x] `heal_parity/cases.tsv` has nested heals. A primary or fallback may be
      `heal/<expr>/<strategy>/<fallback>`, the fallback part recursive; Python
      (`_expr`, `_fallback`), Java (`nestedHeal`) and C (`nested_heal`) build it.
      Nine cases: a heal in a fallback that substitutes, falls back, keeps, goes
      two deep, never runs, or calls `f(0)`; and a heal as the primary that the
      outer heal keeps, or does not trust at 112. Existing 24 cases build the
      same source as before. Against HEAD's `heal_order.py`/`scope.py`/
      `syntax.py` the new cases fail 10 Python-vs-Java checks (trace, events);
      now Python and Java agree on all nine. heal_matrix under ASan/UBSan: 31
      rows, no reports. — 2026-11-07
- [x] `heal_parity_test.py` works in a fresh `build/heal-parity-*` per run. The
      fixed `build/heal-parity` made every rerun die in `os.makedirs` wherever
      the previous cleanup could not delete.
- [x] **C reports the inner heal's action when a heal runs in a fallback.**
      Owner: `tac-optimizer`. Failing: `heal_parity_test.py`, 5 checks, e.g.
      `fb_heal_substitute: C agrees on the value, confidence and action` —
      expected `1/112/FALLBACK` (Python and Java), got `1/112/SUBSTITUTE`.
      Same in `fb_heal_fallback`, `fb_heal_keep` (got KEEP), `fb_heal_two_deep`,
      `fb_heal_call`. Value and confidence agree. Cause: `OP_RECOVERY` sets
      `ip->heal_action` for the outer heal, then the fallback block runs the
      inner heal, which overwrites it; `ev_interp_heal_trace` returns the last
      write. The lowered branch reads `OP_REPAIR_STATE` right after
      `OP_RECOVERY`, so results are unaffected; only the reported outcome is
      wrong. — closed 2026-11-08: `OP_REPAIR_RESTORE` (`tac.c`, `tac.h`) is
      emitted at the end of a heal's fallback arm and records this heal's
      outcome (FALLBACK) again, so the last write is the outer heal's.
      `heal_parity_test.py` exits 0.
- [x] `notebook.py` `ARCHIVE` is hard-coded; allow an env override so the
      suite can run where the repo sits on a mount sqlite cannot lock.
- [ ] Root `probe.ever`, `probe_inferred.ever`, `heal_*.ever` are tracked
      scratch, referenced nowhere.

## Closed since the last pass — verified in the code

- [x] `ev_lower_module` no longer accepts an arena it discards. Signature is
  `ev_lower_module(const char *name, EvNode *root)`; the `(void)arena;` and the
  landmine it forced are both gone.
- [x] The dead-register pass guards all three register reads symmetrically —
  `ins->args[ai]` now gets the same `ev_reg_is_void` check as `src0`/`src1`,
  so a void call argument can no longer credit register 0 silently.
- [x] The layer-4 suites no longer destroy their own subject. `archive_test.py`,
  `repair_test.py` and `zeroth_test.py` each build into a `tempfile.mkdtemp`
  directory instead of opening with `os.remove(DB)` — they now run where the
  repo's `.db` files are not deletable, which is how they failed before.

- [x] **Go suites no longer depend on the home build cache.** Backends (17
  checks), Verification oracle (1) and Finality (1) failed with `failed to
  initialize build cache at ~/Library/Caches/go-build` under the sandbox, which
  refuses that path. `tests/run_all.py` now defaults `GOCACHE` to `build/go-cache`
  (gitignored) unless one is exported. With `GOCACHE` writable the three suites
  passed: Backends 85/0/0, oracle 5/0/0, finality 8/0/0. — closed 2026-11-08
  Gate on 2026-11-08, no environment overrides: 55 passed, 0 skipped, 0 failed.

## Open questions

- Form path drops a confidence annotation at run time: an ATOM or
  `ANN_CONF` with `confidence = 50` sets it on the returned EvReg copy in
  `form_lower.c`, not on the emitted instruction, so `9@50 + 1` runs as 256.
  Same before and after the dead-code pass. Is the instruction meant to carry
  it (then `ev_emit_const`'s dest needs the value), or is ANN_CONF static-only?

- `EV_ARENA_SLAB_SIZE` × `EV_ARENA_MAX_SLABS` caps a parse/execute cycle at
  4 MB with no partial release. A ceiling worth raising, or a limit worth
  asserting on so it fails loudly rather than returning NULL into a caller
  that ignores it?
- The `reason` field (`ever.py`) is prose, asserted in tests by keyword
  containment. Worth reifying into `(code, subject, detail)` so the archive can
  store *why* a crossing lost confidence, not only how much?
- `8-finality` is new since the last pass and has no entry here. What does it
  own, and what is its gate?
- FALLBACK carries the fallback literal's own confidence: `heal (z) using
  ("p") fallback (5)` is `5 [256/256]`, and an enclosing heal KEEPs it. §9
  says repairs never stack past the floor but is silent on FALLBACK. Is a
  declared fallback meant to read as certain? (All three layers agree today.)

- Should CLAUDE.md's verify block use `leaks` on macOS? AddressSanitizer's leak
  check is unsupported here (`detect_leaks is not supported on this platform`),
  so the ASan command shows no errors but not no leaks. `MallocStackLogging=1
  leaks --atExit -- ./ks` reports 0 leaks for the kitchen sink on 2026-11-08, and
  `1 leak for 64 total leaked bytes` on a deliberate leak, so it detects leaks here.

- Evaluation Q1 (`docs/EVALUATION.md` §7): what is an independent witness for a
  model's proposal? `f` hard-coded to its four Examples returns `0` for `f(5)`
  at 235 (`run_source`, 2026-11-10). Count only Examples the proposer never
  saw? Count one model's samples as one witness?
- Evaluation Q2: recurrence counts `source_ident`, not proposers. One fixture
  archived under three sources by one model is admitted at 128 (checked against
  `archive.sql` + `repair.sql` in SQLite `:memory:`), and `repair` has no column
  that names a proposer. Settle before any model writes to the archive.
- Evaluation Q3: is model-written source a program constant (`Certain`, §1.2)
  or external data (`INTAKE`)? Extends the FALLBACK question above: a
  model-written fallback is a guess at 256.
