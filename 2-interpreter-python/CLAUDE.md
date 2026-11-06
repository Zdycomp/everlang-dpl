# Python interpreter landmines (2-interpreter-python)

**Profiler: one observation per program.** Not per statement. Passing a profiler into `Semantic` double-counts and
inflates the score.

**Postfix chains (`[]`, `.`) count as continuing a value, not ending one.** `forgive.py`'s comma-healing must never fire
between `xs` and
`[i]`, or between `xs[0]` and `[1]` — check `_completes_value()` before touching that logic.

**A probe may not change what an expression computes, only what it records.** `heal_order.probing()` opens its own
cause frame; it must not silence `note()`. A probe that drops a failure re-runs the heal into a different repair and
reports the probe's answer. `TestCauseNaming` in `tests/test_healing.py` checks the displayed confidence for this.

**`heal (` and `learn (` are never calls to `forgive.py`.** `_heal_form_at` mirrors `Parser._heal_ahead`; `) using` is
never a missing comma. See `TestHealFormsAreNotCalls`.
