# lessons — 4Ever

Every entry is a bug that shipped green, or a correction from Ricky. Three
parts, always: **What broke · Why it wasn't caught · The rule now.**

An entry without the test that would have caught it is not finished. When a
lesson hardens into a rule every agent must follow, promote it into
`CLAUDE.md`'s Landmines and leave a pointer here.

---

## Changing a failure convention from NULL to a sentinel left dead guards that crashed, and the gate could not see it

**What broke.** The pool getters in `0-atom-c/evalue.c` stopped returning NULL for a bad
ref and started returning a static Unknown composite, so the callers' `if (!l) return 0`
guards became dead code. `ev_list_push` and `ev_record_set` then called `realloc` on the
static sentinel and aborted, and `ev_equal` reported two dangling refs as equal.
`distinct_shapes` and `ir.distinct_skeletons` still tested `is not None`, so a failed parse
was counted as a shape. The same change had also left a doubled `@dataclass` on `Unparsed`
and dropped one from `ZLit`. A reviewer found all of it; the suites were green throughout.

**Why it wasn't caught.** The new tests checked the getters, not the callers, so the one
caller that was updated (`scope.c`) passed and the others were never exercised. The
fuzz test for no-null parsing checked `None` only in the functions it called directly.
`run.sh` also failed `TAC IR (C)` at baseline while the gate was green, because the gate
did not run that assertion.

**The rule now.** When a function's failure convention changes (NULL to a sentinel, `None`
to a node), grep every caller for the old test and convert it in the same change, and add a
regression case that calls each mutator on a bad ref. Consumers of a parse result check
`isinstance(node, Unparsed)`, never `is None`. Run `run.sh` as well as the gate before
calling a change done. Test: `0-atom-c/unknown_composite_test.c` (mutators, equality,
serialise) and `tests/test_no_null_parse.py` (`distinct_shapes`). — 2026-11-13

## A branch switch in the shared checkout erased a day of uncommitted work

**What broke.** On 2026-11-10 at 08:56 something on the Mac switched
`~/Downloads/4ever` from `feature/heal-repair-order` (1f14e49, Nov 9) to
`claude/coderabbit-autofix-5d0` (1f6ea44, Oct 15). Every uncommitted change was
dropped: the dead-code pass, the SEMANTICS and tasks edits, and the R removal.
Most came back from a security-guidance turn baseline (`ff729eb`, kept as
`rescue/turn-baseline-2026-11-09`) and a backup of `tasks.md`. The R removal
was never in any object and had to be redone.

**Why it wasn't caught.** Several agents (the Moto G session, Cowork, a
CodeRabbit autofix, Paradev workspaces) shared one working tree, and the work
lived only there. Git protects commits, not a shared folder. No test can see a
checkout switch; the gate ran green on the old branch too (cross-layer 11/11).

**The rule now.** One worktree per agent, on its own branch. Only Ricky works
in the main checkout, and it stays on the working branch. Commit at every
checkpoint; a snapshot plugin is a backstop, not the plan. Check: `git reflog
-3` at session start must show no checkout you did not make.

---

## The optimiser unbound function parameters

**What broke.** `ev_pass_dead_regs` turned a parameter's LOAD in block 0 into
a NOP whenever its register had no use. That LOAD is where `interp_func` binds
the argument — it scans block 0 for a LOAD named after each parameter — and
every reference in the body emits a LOAD of its own, so the binding LOAD
usually has no register use. `def dbl(n) = if 1 < 2 then n * 2 else n; dbl(21)`
returned 42 unoptimised and z optimised. `fact` kept working only because its
own condition `n <= 1` reads `n` in block 0.

**Why it wasn't caught.** `ks_pipeline_optimiser_safety` compares optimised
against unoptimised on three global-body expressions — no function, no
parameter. The recursion suites do optimise functions, but every one reads its
parameter in the entry block. Found by the dead-code pass's probe, which ran a
function through `OP_CALL` with a constant condition.

**The rule now.** A pass that deletes instructions must know which ones the
interpreter reads by name rather than by register: block-0 parameter LOADs are
kept (`_is_param_load`, `tac.c`). The test that catches it is the hand-off in
tasks.md: `dbl(21)` through `ev_interp_run`, optimised vs not. — 2026-11-07

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

## A throwaway probe wrote into the real ReFix archive

**What broke.** A review script ran `learn (1/zero) using ("p") fix (4)`
through `runtime.run_source()` with no registry set. `RepairRegistry()`
defaults to `7-refix-node/`, so the learn appended two repairs to the tracked
`7-refix-node/repairs.jsonl`. The next Java run failed `RepairSuite`: "the
ReFix archive loads (3 records, no warnings)" found 5. Restored from HEAD.

**Why it wasn't caught.** The script was not a suite, so nothing isolated it.
The suites isolate themselves (`_Archive`, `use_registry`); an ad-hoc run
gets the default, which is a file in the repo. `RepairSuite`'s record count
caught it, one run later.

**The rule now.** Any run of `.ever` source that can `learn`, inside a suite
or not, first calls `use_registry(RepairRegistry(archive_dir=<temp dir>))` and
sets `EVER_REPAIR_STORE` to a temp dir. The test that catches a breach is
`RepairSuite`'s ReFix record count. — 2026-11-07

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

## Three Go suites failed on the sandbox's cache, not on the code

**What broke.** Backends (17 checks), Verification oracle (1) and Finality (1)
failed with `failed to initialize build cache at ~/Library/Caches/go-build`.
The gate counted them as code failures. With `GOCACHE` on a writable directory
the same three suites pass: 85/0, 5/0, 8/0.

**Why it wasn't caught.** The Go toolchain wrote to the home cache, and the
sandbox refuses that path. Nothing in `run_all.py` gave the toolchains their own
writable state, so one tree was green on one machine and red on another, and the
suites reported the sandbox as a defect in the code.

**The rule now.** `run_all.py` sets `GOCACHE` to `build/go-cache` (gitignored,
inside the repo) unless one is exported. A suite's verdict is about the code:
any state a toolchain writes goes under the repo's `build/` or the run's temp
directory. The test that catches a regression is the gate itself, run where the
home cache is not writable. — 2026-11-08

## A heal's trace reported the outcome of a heal inside its fallback

**What broke.** Five C checks in `heal_parity_test.py` (`fb_heal_substitute`,
`fb_heal_fallback`, `fb_heal_keep`, `fb_heal_two_deep`, `fb_heal_call`) reported
the inner heal's action for an outer heal that fell back. Python and Java report
FALLBACK. Value and confidence were already right.

**Why it wasn't caught.** The outer outcome was written when its repair began
(`OP_RECOVERY`), before the fallback ran. The inner heal then wrote its own
outcome, and the trace returns the last write. The nested cases were added the
same day and caught it, but only once the action was compared; value and
confidence had passed.

**The rule now.** A heal's outcome is written again after its fallback arm has
run (`OP_REPAIR_RESTORE`, `tac.c`). Any heal form is tested with a heal nested in
its fallback (`cases.tsv`, `fb_heal_*`). — 2026-11-08

## An integration backend that cannot carry confidence cannot fail on it

**What broke.** Integration Backend B evaluates in Python and sends literal values
to C, and IR literals carry no confidence, so every non-z value printed `[256/256]`.
Backend A hardcoded 256 for every `let`. When function results moved to 120, both
kept matching the old `.expected` files, and the suite did not notice.

**Why it wasn't caught.** The expected confidence and the harness's confidence were
both 256, so the comparison agreed with itself. Nothing had changed a confidence
rule until now, so no run could have shown the gap.

**The rule now.** A harness that prints a confidence prints what the runtime earned:
`ev_interp_ret_conf` in C, `eval_confidence` in Python, never a constant. A backend
that cannot carry confidence must say so in its output, not print 256. The test
that catches a regression is the Integration suite. Fixed 2026-11-09: IR literals
carry their confidence, and Backend B sends the one the binding earned. — 2026-11-09

## A convenience entry point skipped the call gate

**What broke.** Moving the depth rule from one shared counter to a per-function count
(SEMANTICS §4.6) left `ev_interp_call` calling `interp_func` directly. Its outermost
activation was never counted, so fact(4) came back 24 where the gate says z.
`ks_recursion_ceiling` in `kitchen_sink.c` caught it on its one assertion.

**Why it wasn't caught.** Nothing checked which path a call took. The kitchen sink
asserted the answer, and `CLAUDE.md` already warned that this entry point skips the gate.

**The rule now.** Every entry into the interpreter passes one gate, `gated_call`, which
`OP_CALL`, `ev_interp_call` and `ev_module_example` all use. `tests/test_ceiling.py`
requires the same answer through `run_source` and through the C interpreter. — 2026-11-09

## A backstop smaller than the reference silently capped a recursion

**What broke.** C's hard backstop on call depth was 8, Python's anchored backstop is 512.
An anchored fact(20) ran in Python and came back z in C. No test had an anchored
recursion deeper than 8, so the two layers were never compared past that depth.

**Why it wasn't caught.** The unit tests and the integration programs stopped at fact(4)
or fact(8), where both layers agree whatever the backstop is.

**The rule now.** A backstop matches the reference layer's value, and a parity test runs
one case past the smaller layer's limit. `tests/test_ceiling.py` runs fact(20) in both
layers for that reason. — 2026-11-09
