# lessons — 4Ever

Every entry is a bug that shipped green, or a correction from Ricky. Three
parts, always: **What broke · Why it wasn't caught · The rule now.**

An entry without the test that would have caught it is not finished. When a
lesson hardens into a rule every agent must follow, promote it into
`CLAUDE.md`'s Landmines and leave a pointer here.

---

## A patch written against a stale copy nearly overwrote a month of work

**What broke.** Nothing shipped — this one was caught on the way in, and it is
filed because the near-miss is the lesson. A session read `tests/run_all.py`,
went away while the machine was unreachable, and came back with a full
replacement file reconstructed from what it had read. In the interval the
harness had been rewritten: 34 suites had become 55, a REQUIRES preflight and
`--allow-skip` had been added, and the exit-code classification the patch was
written to introduce was already there and better. Committing the
reconstruction would have deleted 21 suites and three features while reporting
itself as a fix.

**Why it wasn't caught.** It nearly wasn't. The only thing that caught it was
staging the live file and diffing before writing — the patch's own anchors
(`if "SKIP:" in out`, `return 0 if not failures else 1`) were no longer in the
file, which is what a safe patcher reports as an abort and a blind overwrite
reports as success. A rewrite carries no such signal: it matches nothing
because it replaces everything.

**The rule now.** Read the live file before changing it, and edit in place.
When a change is big enough to want a rewrite, diff the rewrite against the
live file first and state what it drops. Promoted to `CLAUDE.md` › Workflow.
— 2026-10

## The harness read prose as a verdict

**What broke.** `tests/run_all.py` classified a suite with
`if "SKIP:" in out` — a substring search over the suite's own output.
`tests/test_zeroth.py` exits 0 having proved C, Python and SQL agree on all
257 band values, prints "1 skipped" for a toolchain it could not reach, and
was therefore recorded as SKIP. The same rule ran the other way: a genuinely
failing suite whose output mentioned `SKIP:` anywhere was downgraded from
FAIL to SKIP, and `return 0 if not failures else 1` then dropped it out of the
exit code entirely.

**Why it wasn't caught.** The harness is the thing that catches everything
else; nothing tests it. It printed a scorecard that looked right, and a run
with skips exited 0 — green over red, for as long as nobody counted the
column. Automation of this shape doesn't fail at launch, it fails quietly
three weeks later.

**The rule now.** A verdict is an exit code, never a string: 0 pass,
`SKIP_EXIT` (77) skip, anything else fail — plus a REQUIRES preflight that
skips a suite whose toolchain is absent instead of running it and reading the
wreckage. Skips are not free: the run exits 0 only when nothing failed and
nothing was skipped, with `--allow-skip` as the explicit opt-out and
`EVER_TOOLCHAIN_PATH` as the way a toolchain outside the system paths gets
found rather than skipped. — fixed 2026-10

## Validated against the convenient path, not the real one

**What broke.** The OP_CALL depth gate was changed to
`depth + 1 >= E_DEPTH_CEILING` and validated against `ev_interp_call()` — an
entry point that calls `interp_func()` directly and so skips the very gate
under test. No real `.ever` program enters that way; every call, including the
first, is an ordinary expression through `OP_CALL`. Corrected back to plain
`depth >= E_DEPTH_CEILING` and confirmed by full regression.

**Why it wasn't caught.** The probe was isolated and it passed. There is still
no test that distinguishes `ev_interp_call` from the `OP_CALL` path, so the
convenient entry point remains callable and unguarded — the revert and its
reasoning live in a comment above the gate, which explains the past to a reader
and constrains nothing that runs. `tests/test_invariants.py:CEILING_SITES` now
pins the ceiling *constant* across all ten sites, which is the replication half
of the problem; the *comparison* is still untested, `>=` in C against `>` in
`abstract.py`.

**The rule now.** Verify through the real pipeline — a top-level call via
`ev_interp_run`. In `CLAUDE.md` › Hard rules. Open item: `tests/test_ceiling.py`
in `tasks.md`, which turns the comment into a test. — 2026-09

## A regex shim in the harness silently made everything certain

**What broke.** A test harness executed `.ever` source by regex and
line-splitting instead of `runtime.run_source()`. It forced every binding's
confidence to 256 — destroying z-contagion in a language whose entire thesis
is trust tracking — while the suite stayed green.

**Why it wasn't caught.** The assertions checked values, and the values were
right. Confidence was the thing being destroyed, and nothing asserted on it.

**The rule now.** Never execute `.ever` source with regex or line-splitting.
Promoted to `CLAUDE.md` › Hard rules.

## Dropping a statement is worse than refusing the program

**What broke.** Transpiler backends silently dropped `extern`/FFI statements.
The CALL survived into the emitted code, and for a name that already exists as
a target-language builtin — R's own `sqrt()` — it appeared to work by
coincidence while every other extern failed outright.

**Why it wasn't caught.** Coincidental success is indistinguishable from
success at the assertion level. One backend, one name, and the output was
correct.

**The rule now.** `Emitter.emit()` raises on any `Extern` before emitting a
line. Note the coupling: the scan covers `prog.statements` only, which is
complete because `syntax.py` admits `Extern` at top level alone. Loosen the
grammar and this check stops seeing it, with nothing pinning that dependency.
Promoted to `CLAUDE.md` › Landmines.

## and/or through the generic helper could not short-circuit

**What broke.** `and`/`or` routed through the generic binop runtime helper,
which receives both operands already evaluated. `true and false` transpiled to
Go, compiled, ran, and produced `z` instead of `false` — no error anywhere,
because the runtime `op()` had no case for and/or and fell through to its
default.

**Why it wasn't caught.** It compiled and it ran. Ever's semantics say a
short-circuited side was never consulted and its confidence must not count —
a rule about what *didn't* happen, which no assertion was watching.

**The rule now.** Every backend generates real short-circuiting code in
`Emitter.logic()` and its overrides. Any new backend does the same or the bug
returns silently. Promoted to `CLAUDE.md` › Landmines.

## Indexing inherited the container's confidence

**What broke.** `days[2]` reported `z`-confidence inherited from an unrelated
`thu` elsewhere in the same list. A list's aggregate is the min across
elements; indexing into one element must report that element's own confidence.
The two were conflated in the Python reference and in every backend's
`vindex`/`vfield`.

**Why it wasn't caught.** Both numbers are plausible confidences, and the
aggregate is correct — for the list. Nothing compared element-level against
container-level on the same value.

**The rule now.** Check that exact distinction in any new backend. Promoted to
`CLAUDE.md` › Landmines.

## The healer broke heal forms it was meant to repair

**What broke.** `forgive.py` treats `name (` as a call, and inserts a missing
comma between two values inside a call or a list. `heal (` is a call to the
lexer, and `) using` is two items to a list. So `heal (heal (1) using ("p")
fallback (3)) using ("p") fallback (50)` failed to parse with "expected RPAR,
found ,", and `[heal (1) using …, …]` was rewritten into different items.

**Why it wasn't caught.** Every heal test had one heal, at top level, and
`forgive.py`'s own tests never named `heal`. The strict parser accepted each
form alone; the bug was in the front door that runs before it, which only
composition exposes.

**The rule now.** A new surface form is tested composed with the healing layer:
inside another form and inside a list. `TestHealFormsAreNotCalls` in
`tests/test_healing.py`. `_heal_form_at` mirrors `Parser._heal_ahead`; keep them
the same rule.

## A parity matrix proves agreement only on the cases it holds

**What broke.** A z reached from a called function, `heal (f(0))` with
`f(x) = 10 / x`, gave `FALLBACK` in Python and in C. Both were wrong, in the
same way: the reason was `unverified`, so no repair was found. The parity gate
was green, because agreement was the only thing it checked and the cases never
included a call.

**Why it wasn't caught.** `tests/heal_parity/cases.tsv` covers expression-level
causes only. Agreement between two wrong answers passes, and nothing in the
gate says "this case is a function call, and C has not been checked on one".

**The rule now.** A layer may only be said to implement a rule that the parity
matrix has cases for. `docs/SEMANTICS.md` §9 names the gap, and `tasks.md` holds
it open (owner `tac-optimizer`) until a call case exists and C agrees. — 2026-11-03

## A test file's `__main__` guard sat between two test classes

**What broke.** `tests/test_healing.py` had `if __name__ == "__main__":
unittest.main()` above `class TestStrategy`. Run as a script, `unittest.main()`
exits before `TestStrategy` is defined, so its 4 tests never ran. The file
reported 15 tests, and the gate counted it green.

**Why it wasn't caught.** The file's count looked plausible. Nothing compared the
tests run against the tests written.

**The rule now.** The `__main__` guard is the last statement of a test file. Check
the count with `python3 tests/test_healing.py -v` whenever a class is added. The
runner should compare collected tests with run tests; that is not built yet.
— 2026-11-03

## A probe that suppressed failure naming changed the answer it probed

**What broke.** The first version of cause naming made `note()` a no-op inside a
probe. A confidence re-read of `heal (1 / zero)` then re-ran the heal without its
cause and reported `fallback 3 [256/256]`, while the real evaluation gave
`1 [112/256]`. The displayed value was the probe's.

**Why it wasn't caught.** It was caught before it shipped, by a probe program
printing `q = 1 [256/256]` where the trace said `SUBSTITUTE 112`. The value and
the trace disagreed, and the disagreement was the signal.

**The rule now.** A probe may not change what an expression computes, only what
it records. `probing()` now opens its own cause frame instead of silencing
`note()`. `TestCauseNaming.test_failure_inside_a_called_function_is_named` asserts
the displayed confidence, which goes through the probe, so it would catch a
regression. — 2026-11-03

## A probe measured an undefined function, then a registry with no repairs

**What broke.** Nothing shipped. The first C probe of `heal (f(0))` never put
`f` in the module, so the call hit an undefined name and fell back. It then
loaded no archive at all. Both results looked like the fallback the probe was
meant to explain, and the conclusion drawn from them, "C does not name through
calls", was right for a reason the probe did not show.

**Why it wasn't caught.** The probe printed only the answer. It did not print
the setup it depended on: how many functions the module had, or whether the
registry held the repair.

**The rule now.** A probe prints its preconditions beside its answer: the
function count, the repairs loaded, and a control case that must succeed (here,
the direct `10 / 0`, which substitutes `1 [112/256]`). `0-atom-c/tac_test.c`
`CAUSE NAMING` now asserts the same behaviour without the probe. — 2026-11-03

## A suite that deletes its subject cannot run everywhere

**What broke.** The three layer-4 suites each opened with `os.remove(DB)` on a
database inside the repo. On any machine where those files are not deletable —
a sandbox, a read-only mount, a checkout owned by another user — all three
died at line one with `PermissionError`, in the one layer whose stated schema
invariant is that nothing is ever deleted.

**Why it wasn't caught.** It passed on the author's machine, which is the only
machine it ever ran on. The failure is environmental, so no assertion could
have seen it; only running somewhere else could.

**The rule now.** A suite builds its fixtures in `tempfile.mkdtemp`, never in
the repo. All three now do. — fixed 2026-10
