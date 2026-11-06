# tasks — 4Ever

Working memory. Read at session start, updated before any session reports done.
Three parts, always. Check items off as you go, not in a batch at the end.

Before adding an item, verify it is still open against the live code. Before
closing one, verify in the code that it actually is. Line numbers go stale
fast in this repo — cite the symbol, and the file, and let the number be a hint.

---

## Decisions

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
- [ ] Backends suite skips here: `Rscript` is not installed, so the gate is
      54 passed / 1 skipped / 0 failed and exits 1. `brew install r` builds gcc
      from source on this Intel Mac (no bottles) and failed with `ENOSPC`: the
      data volume is 97% full, 6.7 GiB free. The earlier "stalled pid 7751 holds
      the locks" note was wrong: that run had already died on a Homebrew
      `NameError` and the locks were free. Owner: the user. Free roughly 15 GiB
      (`brew cleanup` reclaims about 2 GiB of the 2.1 GiB cache), then
      `brew install r`, then rerun the gate.

### Finish the language: `example` and `anchor` get surface syntax (2026-10-28)

SEMANTICS.md §4.2–4.6 and the §8 worked example define how a function earns
trust (Examples) and depth (anchor). `abstract.py` implements it; the real
front door (`runtime.py` → `scope.py`) has no syntax for it and instead
treats *any* decreasing measure as anchored — depth handed out, not earned.
`example` and `anchor` are reserved keywords that nothing parses.

- [ ] Syntax: `example f(a, …) = v` and `anchor f` statements in `syntax.py`
      (AST nodes, parser, statement sequencing, Semantic pass).
- [ ] Semantics in the runtime, exactly as §4: `def` at INTAKE 120;
      [EXAMPLE] confidence; [ANCHOR-FN] / [ANCHOR-REC] / [ANCHOR-⊥];
      limit(θ_f) = ∞ only when anchored ∧ measure, else ⌊π⌋ = 3.
- [ ] Remove the auto-anchor-by-measure in `runtime.py` / `scope.py`.
- [ ] Test: §8 run as a real `.ever` program, every row of its table asserted.
- [ ] SEMANTICS.md: grammar as built (EBNF) + §7 corrected to what is truly
      missing; parser docstring updated.
- [ ] C parity: `tac.c` has no anchoring (every recursion capped at 3).
      Owner: `tac-optimizer` — tracked, not silently skipped.
- [ ] `run_all.py` green (excluding toolchain skips on this machine), ASAN clean.


- [ ] **`tests/test_ceiling.py`** — the behavioural half of the depth contract.
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

## Open questions

- `EV_ARENA_SLAB_SIZE` × `EV_ARENA_MAX_SLABS` caps a parse/execute cycle at
  4 MB with no partial release. A ceiling worth raising, or a limit worth
  asserting on so it fails loudly rather than returning NULL into a caller
  that ignores it?
- The `reason` field (`ever.py`) is prose, asserted in tests by keyword
  containment. Worth reifying into `(code, subject, detail)` so the archive can
  store *why* a crossing lost confidence, not only how much?
- `8-finality` is new since the last pass and has no entry here. What does it
  own, and what is its gate?
