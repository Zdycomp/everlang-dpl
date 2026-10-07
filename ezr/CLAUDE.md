# Ever / Tapestry — rules for every agent

Confidence-tracking language. 7 layers. C runtime + Python front end.
Founder: Ricky (Dreid), Codric Enterprise.

## Before you touch anything

```
python3 tests/run_all.py          # must be 29 passed / 0 failed
```

The suite count is not decoration: it was 26 here while the gate ran 28,
and the number nobody re-ran is the number that stops meaning anything.
`tests/assertion_counts.py --check` runs last in the gate and fails it
when a document's count drifts from a real run.

If it isn't green before your change, stop and say so. Don't build on red.

## Hard rules

**Finished means 100%.** Not "done except X." If you can't finish, say
which line is blocking, in one sentence. Never hand back a partial and
call it complete.

**Never weaken a test to make it pass.** If a test fails, the code is
wrong until proven otherwise. If the *test* is wrong, fix the test and
say why in the commit.

**Never execute `.ever` source with regex or line-splitting.** Use
`runtime.run_source()`. A regex shim used to live in the test harness
and it silently forced every binding's confidence to 256, destroying
z-contagion in a language whose whole point is trust tracking.

**Verify against the real path, not a convenient one.** `ev_interp_call`
skips the depth-ceiling gate that every real program hits. A fix
validated only there was wrong in production. Real programs call
functions as ordinary expressions through `OP_CALL`.

## One rule, every language

**Whatever is written in Python is written in every language the system
implements.** Not "eventually" — in the same change. A rule that holds in
one implementation and not the others is not a rule, it is that
implementation's local habit, and the whole point of having C, Python,
Ruby and Java agree is that a disagreement between them is a finding
about the language rather than a bug report against one side.

This had already rotted before anyone wrote it down. `movements`,
`witnesses_needed` and `from_examples` existed in Python and Java and in
neither C nor Ruby, and nothing anywhere reported it.

`tests/algebra_parity.py` is the enforcement: it runs the same
[EXAMPLE] ladder and the same inverse through every implementation as
processes and fails the gate when any two disagree. It is in
`run_all.py` and in `run.sh`. A language whose toolchain is absent is
skipped; a language that is present and lacks the function fails, since
that is precisely the drift being prevented.

Two honest exemptions, and only two:

- **Harness is not language.** `tests/assertion_counts.py` and
  `research.py` are tools that measure the project; they have no
  counterpart to have. The rule covers the algebra and the semantics,
  not the build.
- **A layer that structurally cannot.** `movements` needs an AST with
  call nodes, so it exists in Python, Java and the forge; Ruby is a DSL
  with no parser and C's `measure` is structural metrics (size/depth),
  not the termination measure — C has no anchoring at all. Say which
  layer cannot and why, in the commit, rather than leaving a gap that
  looks like an oversight.

When you add to the algebra, add the parity probe in the same change.
A checker that does not cover the new thing will happily report four
agreements about everything except it.

## Landmines (each of these has already caused a bug)

**Arena ownership is asymmetric.**
- `ev_module_new(name, arena)` — TAKES the arena. `ev_module_free`
  frees it. Never free it yourself.
- `ev_lower_module(...)` / `ev_lower_form_module(...)` — MINT their own.
  Your arena still holds the tree and is yours to free.

**Depth ceiling = floor(pi) = 3 CALL LEVELS.** `fact(3)`=6, `fact(4)`=z.
Check is `depth >= E_DEPTH_CEILING` in the OP_CALL handler. C and Python
must agree. `E_DEPTH_CEILING` is NOT in `tapestry.h` — local guards only.

**Z is a state, checked BEFORE arithmetic.** Reading a void's body as a
double produces a plausible wrong number. Any binop with a VOID operand
returns VOID.

**Depth is 0-based in EvNode, 1-based in EvForm and Semantic.** `6+36`
is depth 1 as a node, 2 as a form. Both correct. Don't "fix" either.

**Profiler: one observation per program.** Not per statement. Passing a
profiler into `Semantic` double-counts and inflates the score.

**Depth is tracked per function name, not by a shared counter.** An
anchored function recursing deep, calling an ordinary non-recursive
helper, must not make that helper inherit the caller's elevated depth
and spuriously hit the ceiling. `_own_recursion_depth()` in `scope.py`
walks the scope chain counting frames named `f"fn:{name}"` — it does
not trust the `depth` int parameter for this. If depth tracking is
ever ported to the C interpreter (currently unanchored, flat ceiling
of 3, no `measure` field at all), this per-function design has to be
there from the start or the exact bug comes back.

**Postfix chains (`[]`, `.`) count as continuing a value, not ending
one.** `forgive.py`'s comma-healing must never fire between `xs` and
`[i]`, or between `xs[0]` and `[1]` — check `_completes_value()` before
touching that logic.

**Transpilers refuse `extern`/FFI outright, all four, no exceptions.**
FFI runs through Python's `ctypes`; none of the five backends know
about it. Silently dropping an `extern` statement is worse than
refusing — the CALL survives into the emitted code, and for a name
that happens to already exist as a target-language builtin (R's own
`sqrt()`, for instance) it can appear to work by coincidence while
every other extern fails. `emit.py`'s `Emitter.emit()` checks for any
`Extern` statement and raises before emitting anything.

**`and`/`or` must never route through the generic binop() runtime
helper.** That helper receives both operands already evaluated, so it
cannot short-circuit — and Ever's own semantics say a short-circuited
side was never consulted, so its confidence must not count. Routing
"and"/"or" through the generic path shipped silently: `true and false`
transpiled to Go, compiled, and ran, producing `z` instead of `false`
— no error anywhere, because the runtime `op()` function had no case
for "and"/"or" and fell through to its default. Every backend now
generates real short-circuiting code for and/or (see `Emitter.logic()`
and each subclass's override) instead of calling a shared helper.
Any new backend must do the same, or the exact bug returns silently.

**Indexing (`xs[i]`) must read the ELEMENT's own confidence, not the
container's aggregate.** A list's overall confidence is the min across
every element (so one `z` in a five-item list makes the whole list
read as untrusted) — but indexing into element 0 of that list should
report element 0's own confidence, not the whole list's. Conflating
these was a real bug in the Python reference (`days[2]` inheriting
`z`-confidence from an unrelated `thu` elsewhere in the same list) and
had to be fixed in every transpiler backend's `vindex`/`vfield`
identically. Check this exact distinction in any new backend.

**FFI results are never certain.** They enter at `E_INTAKE` (120),
capped further by argument confidence — Ever can't audit a foreign
function, so it doesn't get to claim certainty. A `z` argument means
the call never happens at all; C has no way to represent "unknown."

**Pool composites are BY REFERENCE.** INT/REAL/BOOL/TEXT/VOID are inline
(by value). BLOB/LIST/RECORD hold a `pool_ref` index — copying the
EValue copies the handle. Use `ev_pool_clear()` for bulk teardown.

**C99 only.** No `strnlen`. No `&ev_int(3)` (not an lvalue) — use named
temporaries. `E_INTAKE` needs a local `#ifndef` guard.

## The IR is structural, not syntactic

11 closed form kinds (ATOM, REFERENCE, APPLICATION, BRANCH, SEQUENCE,
BINDING, ABSTRACTION, AGGREGATE, ACCESS, ANNOTATION, DEFECT). The
operator is DATA (`EvRole`, open enum). The shape is TYPE (`EvFormKind`,
closed). New surface syntax should cost ZERO changes to `form.c`,
`form_lower.c`, or any pass. If you're adding a form kind, you're
probably wrong.

## Verify before you report done

```
python3 tests/run_all.py
gcc -std=c99 -g -fsanitize=address,undefined -o /tmp/t \
  0-atom-c/kitchen_sink.c 0-atom-c/form.c 0-atom-c/form_lower.c \
  0-atom-c/tac.c 0-atom-c/scope.c 0-atom-c/ir.c 0-atom-c/evalue.c \
  0-atom-c/tapestry.c -lm && /tmp/t
```

ASAN must report zero errors AND zero leaks.
