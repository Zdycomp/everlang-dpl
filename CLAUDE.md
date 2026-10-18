# 4Ever — rules for every agent

Confidence-tracking language. 8 layers, C runtime through a Node CLI.
Founder: Ricky (Dreid), Codric Enterprise.

## Before you touch anything

```
python3 tests/run_all.py          # must be 34 passed / 0 skipped / 0 failed
```

If it isn't green before your change, stop and say so. Don't build on red.

## Hard rules

**Finished means 100%.** Not "done except X." If you can't finish, say which line is blocking, in one sentence. Never
hand back a partial and call it complete.

**Never weaken a test to make it pass.** If a test fails, the code is wrong until proven otherwise. If the *test* is
wrong, fix the test and say why in the commit.

**Never execute `.ever` source with regex or line-splitting.** Use
`runtime.run_source()`. A regex shim used to live in the test harness and it silently forced every binding's confidence
to 256, destroying z-contagion in a language whose whole point is trust tracking.

**Verify against the real path, not a convenient one.** `ev_interp_call`
skips the depth-ceiling gate that every real program hits. A fix validated only there was wrong in production. Real
programs call functions as ordinary expressions through `OP_CALL`.

**Never compare confidence with proximity.** `|a - b| < 81` is a tolerance
relation: reflexive, symmetric, and *not* transitive (0~1 and 1~81 while
0!~81 — 969,840 of 4,922,897 triples break the chain). Use `e_equilibrium`
/ `equilibrium()` / band equality. `sameSpectrum` still exists and is still
correct for "are these two near each other"; it is not a comparison. See
`docs/ZEROTH.md`.

**`e_band` must stay total and single-valued.** Every property the Zeroth
Law has follows from band being a function — reflexivity, symmetry and
transitivity are not tested-and-hoped-for, they are consequences. If you
touch the boundaries, the law is what you are editing, and four layers plus
the SQL trigger have to agree afterwards: `python3 tests/test_zeroth.py`.

## Landmines (each of these has already caused a bug)

**Arena ownership is asymmetric.**

- `ev_module_new(name, arena)` — TAKES the arena. `ev_module_free`
  frees it. Never free it yourself.
- `ev_lower_module(...)` / `ev_lower_form_module(...)` — MINT their own. Your arena still holds the tree and is yours to
  free.

**Depth ceiling = floor (pi) = 3 CALL LEVELS.** `fact(3)`=6, `fact(4)`=z. Check is `depth >= E_DEPTH_CEILING` in the
OP_CALL handler. C and Python must agree. `E_DEPTH_CEILING` is NOT in `tapestry.h` — local guards only.

**Z is a state, checked BEFORE arithmetic.** Reading a void's body as a double produces a plausible wrong number. Any
binop with a VOID operand returns VOID.

**Depth is 0-based in EvNode, 1-based in EvForm and Semantic.** `6+36`
is depth 1 as a node, 2 as a form. Both correct. Don't "fix" either.

**Profiler: one observation per program.** Not per statement. Passing a profiler into `Semantic` double-counts and
inflates the score.

**Depth is tracked per function name, not by a shared counter.** An anchored function recursing deep, calling an
ordinary non-recursive helper, must not make that helper inherit the caller's elevated depth and spuriously hit the
ceiling. `_own_recursion_depth()` in `scope.py`
walks the scope chain counting frames named `f"fn:{name}"` — it does not trust the `depth` int parameter for this. If
depth tracking is ever ported to the C interpreter (currently unanchored, flat ceiling of 3, no `measure` field at all),
this per-function design has to be there from the start or the exact bug comes back.

**Postfix chains (`[]`, `.`) count as continuing a value, not ending one.** `forgive.py`'s comma-healing must never fire
between `xs` and
`[i]`, or between `xs[0]` and `[1]` — check `_completes_value()` before touching that logic.

**Transpilers refuse `extern`/FFI outright, all four, no exceptions.**
FFI runs through Python's `ctypes`; none of the five backends know about it. Silently dropping an `extern` statement is
worse than refusing — the CALL survives into the emitted code, and for a name that happens to already exist as a
target-language builtin (R's own
`sqrt()`, for instance) it can appear to work by coincidence while every other extern fails. `emit.py`'s
`Emitter.emit()` checks for any
`Extern` statement and raises before emitting anything.

**`and`/`or` must never route through the generic binop () runtime helper.** That helper receives both operands already
evaluated, so it cannot short-circuit — and Ever's own semantics say a short-circuited side was never consulted, so its
confidence must not count. Routing
"and"/"or" through the generic path shipped silently: `true and false`
transpiled to Go, compiled, and ran, producing `z` instead of `false`
— no error anywhere, because the runtime `op()` function had no case for "and"/"or" and fell through to its default.
Every backend now generates real short-circuiting code for and/or (see `Emitter.logic()`
and each subclass's override) instead of calling a shared helper. Any new backend must do the same, or the exact bug
returns silently.

**Indexing (`xs[i]`) must read the ELEMENT's own confidence, not the container's aggregate.** A list's overall
confidence is the min across every element (so one `z` in a five-item list makes the whole list read as untrusted) — but
indexing into element 0 of that list should report element 0's own confidence, not the whole list's. Conflating these
was a real bug in the Python reference (`days[2]` inheriting
`z`-confidence from an unrelated `thu` elsewhere in the same list) and had to be fixed in every transpiler backend's
`vindex`/`vfield`
identically. Check this exact distinction in any new backend.

**FFI results are never certain.** They enter at `E_INTAKE` (120), capped further by argument confidence — Ever can't
audit a foreign function, so it doesn't get to claim certainty. A `z` argument means the call never happens at all; C
has no way to represent "unknown."

**Pool composites are BY REFERENCE.** INT/REAL/BOOL/TEXT/VOID are inline (by value). BLOB/LIST/RECORD hold a `pool_ref`
index — copying the EValue copies the handle. Use `ev_pool_clear()` for bulk teardown.

**C99 only.** No `strnlen`. No `&ev_int(3)` (not an lvalue) — use named temporaries. `E_INTAKE` needs a local `#ifndef`
guard.

## The IR is structural, not syntactic

11 closed form kinds (ATOM, REFERENCE, APPLICATION, BRANCH, SEQUENCE, BINDING, ABSTRACTION, AGGREGATE, ACCESS,
ANNOTATION, DEFECT). The operator is DATA (`EvRole`, open enum). The shape is TYPE (`EvFormKind`, closed). New surface
syntax should cost ZERO changes to `form.c`,
`form_lower.c`, or any pass. If you're adding a form kind, you're probably wrong.

## Every repair runs evaluate → plan → execute

Any heal, learn, or archive-backed repair runs three phases, in this order, identically in every layer:

1. **Evaluate.** Read the primary. Confidence at or above the execute floor: keep it and stop.
2. **Plan.** Look up the archived repair for the failure reason before running anything. The strategy selects among them: a repair tied to that strategy first, then a wildcard (an archived repair with no `strategy`). A repair tied to another strategy is never a candidate. `learn` archives its repair under its own `using (…)` strategy. No repair, or one that cannot add trust (cost ≥ base), means the fallback.
3. **Execute.** Run the chosen action. A repair that was chosen but cannot run (unparsable or `z` fixture) gives `z`, never the fallback. A repaired `0` or `false` is a success: branch on the outcome, never on the value's truthiness.

Each phase writes a trace line: `heal_order.py` (`run_source(...).heal_trace`, `ever run --trace`), `OP_REPAIR_STATE` and `ev_interp_heal_trace` (C), `refix accept` (ReFix). A confidence re-read of a repair node is a probe: it must not trace or archive (`heal_order.probing()`).

## Verify before you report done

The gate is `0 failed, 0 skipped`. A skip is a gap, and gaps are fixed, not reported as done. Toolchains installed
outside the system paths are named in `EVER_TOOLCHAIN_PATH` (colon-separated bin directories), which the runner puts
in front of `PATH`. The heal process is checked across layers by `tests/heal_parity_test.py`: Python, Java and C must
agree on every case, so a change to the repair process is verified in all three.

```
EVER_TOOLCHAIN_PATH=... python3 tests/run_all.py
gcc -std=c99 -g -fsanitize=address,undefined -o /tmp/t \
  0-atom-c/kitchen_sink.c 0-atom-c/form.c 0-atom-c/form_lower.c \
  0-atom-c/tac.c 0-atom-c/scope.c 0-atom-c/ir.c 0-atom-c/evalue.c \
  0-atom-c/tapestry.c -lm && /tmp/t
```

ASAN must report zero errors AND zero leaks.
