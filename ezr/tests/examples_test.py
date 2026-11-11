#!/usr/bin/env python3
"""
examples_test.py — the examples must do what they say they do.

Every example in `examples/` is a claim about the language aimed at a
person who has not read the source. Before this file existed, nothing
checked them: the gate was green while `weekly_sales.ever` printed
`total = z` under a comment promising a sum of five days, three `.ezr`
files did not parse under either runner, and `earned_trust.ever` -- the
file that actually explains the whole idea -- was a transcript nobody
re-ran.

Three sections, because the examples are reached three ways:

  RUN           `ever_cli.py run f.ever` drives runtime.run_source, the
                statement-based front door: let/ever/show, lists, loops,
                indexing. Each `.ever` file's exact stdout is pinned.

  TRANSCRIPT    `ezrun.py` drives syntax.py's eval_ast and is the only
                surface that exposes the confidence algebra -- [EXAMPLE]
                earning trust, [ANCHOR] buying depth. earned_trust.ever
                documents eleven invocations in its comments; all eleven
                are run here and pinned to the value AND the exit code.

  CORE LINEAGE  The four `.ezr` files are written in the forge's core
                (CORE.md): `let x = v in body` as an expression, list
                literals, and the show/len/head/tail builtins -- none
                of it v4.10 grammar, none of it something `eval_ast`
                understood until it was taught all three, closing the
                exact gap `5-runtime-java/differential.py` measured as
                27 divergences (now 5; see FINDINGS.md 7.4). Pinned here
                against `ezrun.py` directly -- no Java build needed to
                run them, only to cross-check them.

A new example with no entry in RUN or CORE LINEAGE fails this suite.
That is deliberate -- an unchecked example is how the last set rotted.
"""
from __future__ import annotations

import atexit
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CLI = ROOT / "2-interpreter-python" / "ever_cli.py"
EZRUN = ROOT / "2-interpreter-python" / "ezrun.py"
EXAMPLES = ROOT / "examples"
TRUST = EXAMPLES / "earned_trust.ever"
EVER_WRAPPER = ROOT / "ever"

# ── the suite's own HOME ─────────────────────────────────────────────
# `ever run` personalises its output. ever_cli.py keeps a learner
# profile at ~/.ever/profile.json, and runtime.run_source hands the
# result a `scaffold` band derived from it; for the two lowest bands
# (score <= 112) the run is prefixed with a legend line and a blank
# line. So `ever run f.ever` does not have one output -- it has one per
# band, and which one you get depends on a file outside the repository
# that every previous run has been editing.
#
# That is what broke CI, and only CI. A fresh runner starts at
# P_START = 64, so the first three examples print the legend and fail
# their pins; by the fourth the score has climbed past 112 and the rest
# pass -- `51 passed, 3 failed`, always the same three, and green again
# on a second run in the same job. A developer's machine is green from
# the start because its profile graduated long ago. Measured here:
# HOME=$(mktemp -d) reproduces CI exactly, and the real ~/.ever showed
# 490 sessions -- every test run this suite had ever done, folded into
# the developer's own profile.
#
# So the suite gets its own HOME, seeded to a band that emits no
# legend, which is the state every pin below was written against. It
# also stops the suite writing to the real one.
_SEEDED_SCORE = 146.0   # "Practitioner" (113-168); the fixed point these
                        # programs converge to, so the run cannot drift out
HOME = Path(tempfile.mkdtemp(prefix="ezr-examples-home-"))
(HOME / ".ever").mkdir()
(HOME / ".ever" / "profile.json").write_text(json.dumps({"score": _SEEDED_SCORE}))
atexit.register(shutil.rmtree, HOME, True)

ENV = {**os.environ, "HOME": str(HOME)}

passed = 0
failed = 0
#: Names of the assertions that did not hold, in order. The tally alone
#: ("51 passed, 3 failed") says a suite broke without saying where, and
#: run_all.py quotes only the tail of a failing suite -- so a failure
#: that happened early scrolled out of the report entirely. Printing the
#: names last puts them inside that tail no matter when they happened.
failures: list[str] = []


def check(label: str, got, want) -> bool:
    """Record one assertion. Returns True when it held.

    Callers gate their own "ok" line on the return value: a green line
    printed underneath a failure is the exact disease this suite exists
    to catch, and it would be absurd to reproduce it here.
    """
    global passed, failed
    if got == want:
        passed += 1
        return True
    failed += 1
    failures.append(label)
    print(f"  FAIL {label}")
    print(f"       want: {want!r}")
    print(f"       got:  {got!r}")
    return False


def run(cmd: list[str], env: dict[str, str] | None = None) -> tuple[str, int]:
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=300,
                       env=env or ENV)
    return (p.stdout + p.stderr).strip(), p.returncode


# ── section 1: `ever run` ────────────────────────────────────────────
#: Exact stdout. Measured, not transcribed from a comment.
RUN_OUTPUT = {
    "compound_interest.ever": [
        "after_2_years = 11236 [256/256]",
        "growth = 1236 [256/256]",
        "growth_pct = 12.36 [256/256]",
        "total_saved = 4000 [256/256]",
        'better_strategy = "contributions win" [256/256]',
    ],
    "ffi_math.ever": [
        "root = 4 [120/256]",
        "squared = 1024 [120/256]",
        "sine_at_90 = 1 [120/256]",
        "tainted = z [0/256]",
    ],
    "grade_calculator.ever": [
        "weighted = 85.35 [256/256]",
        'letter = "B" [256/256]',
        "passed = true [256/256]",
        "honors = false [256/256]",
        "attendance_bonus = z [0/256]",
        "final_with_bonus = z [0/256]",
    ],
    "readings.ever": [
        "count = 6 [256/256]",
        "sum = 63 [256/256]",
        "mean = 10.5 [256/256]",
        "hi = 19 [256/256]",
        "lo = 3 [256/256]",
        "span = 16 [256/256]",
        "missing = z [0/256]",
    ],
    "train_logistic.ever": [
        "trained_w = 0.244593 [256/256]",
        "p1 = 0.560845 [256/256]",
        "p4 = 0.726785 [256/256]",
        "loss = 0.219675 [256/256]",
        "trained_w_gap = z [0/256]",
    ],
    # Thursday is z, so the total is z -- and that is the POINT, not a
    # depth limit. `i` decreases, so the recursion itself is provable.
    "weekly_sales.ever": [
        "total = z [0/256]",
        "had_gap = z [0/256]",
        "best = 610 [256/256]",
        "third_day = 380 [256/256]",
        "missing = z [0/256]",
        "last_square = 25 [256/256]",
    ],
}

#: Definitions only -- no `show`, so `run` prints nothing. Covered by
#: the transcript below instead. Listed so the completeness check below
#: knows it is accounted for rather than forgotten.
RUN_SILENT = {"earned_trust.ever"}


def section_run() -> None:
    print("\never run — front door")
    for name, want in sorted(RUN_OUTPUT.items()):
        out, code = run([sys.executable, str(CLI), "run", str(EXAMPLES / name)])
        ok = check(f"{name} exit 0", code, 0)
        ok &= check(f"{name} output", out.splitlines(), want)
        if ok:
            print(f"  ok   {name}  ({len(want)} bindings)")

    for name in sorted(RUN_SILENT):
        out, code = run([sys.executable, str(CLI), "run", str(EXAMPLES / name)])
        ok = check(f"{name} exit 0", code, 0)
        ok &= check(f"{name} is definitions-only", out, "")
        if ok:
            print(f"  ok   {name}  (definitions only — see transcript)")


# ── section 1b: what a first-time user actually sees ─────────────────
#: The legend a brand-new profile prints ahead of the values. Nothing
#: pinned this, which is how the band dependency above stayed invisible
#: until a fresh CI runner hit it: the suite asserted one of `ever run`'s
#: outputs and never knew there were others. Pinned from a virgin HOME,
#: so a change to the scaffolding text fails here, where it is explained,
#: rather than three times over in RUN_OUTPUT.
FIRST_RUN_LEGEND = "Confidence is shown as [n/256] next to each value."


def section_first_run() -> None:
    print("\nthe first run — a profile that has earned nothing yet")
    virgin = Path(tempfile.mkdtemp(prefix="ezr-virgin-home-"))
    try:
        out, code = run([sys.executable, str(CLI), "run",
                         str(EXAMPLES / "compound_interest.ever")],
                        env={**os.environ, "HOME": str(virgin)})
        lines = out.splitlines()
        ok = check("first run exit 0", code, 0)
        ok &= check("first run is scaffolded with the legend",
                    lines[:2], [FIRST_RUN_LEGEND, ""])
        ok &= check("and the values below it are unchanged",
                    lines[2:], RUN_OUTPUT["compound_interest.ever"])
        if ok:
            print("  ok   a virgin profile is scaffolded, the values are not")
    finally:
        shutil.rmtree(virgin, ignore_errors=True)


# ── section 2: the earned_trust transcript ───────────────────────────
W0 = "growth(100, 0) = 100"
W1 = "growth(100, 1) = 110"
W2 = "growth(100, 2) = 121"
CALL = ["--call", "growth(100, 3)"]

#: (label, extra argv, expected stdout, expected exit)
TRANSCRIPT = [
    ("[DEF] a definition is a claim",
     CALL, "133.1  @ 120/256", 0),
    ("one witness is not enough",
     CALL + ["-x", W0], "133.1  @ 120/256", 0),
    ("two hold — 183 clears the floor",
     CALL + ["-x", W0, "-x", W1], "133.1  @ 183/256", 0),
    ("three hold",
     CALL + ["-x", W0, "-x", W1, "-x", W2], "133.1  @ 217/256", 0),
    ("two of three — 122 is back below",
     CALL + ["-x", W0, "-x", W1, "-x", "growth(100, 2) = 999"],
     "133.1  @ 122/256", 0),
    ("one case thrice is one witness",
     CALL + ["-x", W0, "-x", W0, "-x", W0], "133.1  @ 120/256", 0),
    ("[APP] evidence does not launder the caller",
     ["-x", W0, "-x", W1, "-x", W2], "133.1  @ 120/256", 0),
]

#: These two assert on a prefix, because the message carries a long
#: explanatory tail that is the point of the inversion work and is not
#: worth pinning character-for-character.
TRANSCRIPT_PREFIX = [
    ("contradictory evidence is refused",
     CALL + ["-x", W0, "-x", "growth(100, 0) = 999"],
     "ezrun: --example 'growth(100, 0) = 999':", 2),
    ("depth ceiling 3 stops 20 periods",
     ["-d", "3", "--call", "growth(100, 20)"],
     "Z(unbounded) — depth ceiling 3 exceeded", 1),
]

ANCHORED = ("anchoring buys the depth",
            ["-d", "3", "--call", "growth(100, 20)",
             "-x", W0, "-x", W1, "-x", W2, "-a", "growth"],
            "672.7499949325598  @ 217/256", 0)


def section_transcript() -> None:
    print("\nezrun — the confidence algebra (earned_trust.ever)")
    for label, extra, want, want_code in TRANSCRIPT + [ANCHORED]:
        out, code = run([sys.executable, str(EZRUN), str(TRUST)] + extra)
        ok = check(f"{label} exit", code, want_code)
        ok &= check(f"{label} value", out, want)
        if ok:
            print(f"  ok   {label}  ->  {want}")

    for label, extra, prefix, want_code in TRANSCRIPT_PREFIX:
        out, code = run([sys.executable, str(EZRUN), str(TRUST)] + extra)
        ok = check(f"{label} exit", code, want_code)
        ok &= check(f"{label} message", out.startswith(prefix), True)
        if ok:
            print(f"  ok   {label}  ->  exit {want_code}")


# ── section 2b: the counterfactual ───────────────────────────────────
def section_counterfactual() -> None:
    """`total = z` alone does not pin the lesson.

    weekly_sales.ever returns z because Thursday was never recorded.
    But it ALSO returned z, for years, because `i` counted UP: no
    decreasing measure, so the depth ceiling of floor(pi) = 3 stopped
    it on the third day. Two different causes, byte-identical output --
    which is exactly why nothing caught the broken version.

    So pin the counterfactual too. Fill Thursday in and the sum must
    complete. A counting-up version still returns z here, and fails.
    """
    print("\ncounterfactual — z for the RIGHT reason")
    src = (EXAMPLES / "weekly_sales.ever").read_text()
    assert "let thu = z" in src, "weekly_sales.ever no longer has a z Thursday"
    filled = src.replace("let thu = z", "let thu = 500")

    tmp = HERE / "_weekly_sales_filled.ever"
    try:
        tmp.write_text(filled)
        out, code = run([sys.executable, str(CLI), "run", str(tmp)])
        ok = check("filled-in Thursday exit 0", code, 0)
        ok &= check("filled-in Thursday completes the sum",
                    out.splitlines()[0], "total = 2615 [256/256]")
        if ok:
            print("  ok   thu = 500  ->  total = 2615 [256/256]")
            print("       (a counting-up sum_from returns z — the ceiling bites)")
    finally:
        tmp.unlink(missing_ok=True)


# ── section 3: nothing goes unchecked ────────────────────────────────
# ── section 4: the core lineage, via ezrun.py directly ───────────────
#: Exact stdout, one line per `show`/print. `trust.ezr` and `readings.ezr`
#: use the core's `show(expr)` builtin, which prints as a side effect and
#: also returns its argument -- so `main() = show(describe(30))` prints
#: the value once from inside show() and once more as ezrun's own
#: top-level result line. Two identical lines is correct, not a dupe.
CORE_LINEAGE_OUTPUT = {
    "trust.ezr": [
        "big  @ 120/256",
        "big  @ 120/256",
    ],
    "largest.ezr": [
        "42  @ 120/256",
    ],
    "readings.ezr": [
        "6  @ 256/256",
        "63  @ 120/256",
        "10.5  @ 120/256",
        "19  @ 120/256",
        "3  @ 120/256",
        "16  @ 120/256",
    ],
    "sum.ezr": [
        "15  @ 120/256",
    ],
}


def section_core_lineage() -> None:
    print("\ncore lineage — ezrun.py, no Java build required")
    for name, want in sorted(CORE_LINEAGE_OUTPUT.items()):
        out, code = run([sys.executable, str(EZRUN), str(EXAMPLES / name)])
        ok = check(f"{name} exit 0", code, 0)
        ok &= check(f"{name} output", out.splitlines(), want)
        if ok:
            print(f"  ok   {name}  ({len(want)} line(s))")


def section_completeness() -> None:
    print("\ncoverage")
    on_disk = {p.name for p in EXAMPLES.glob("*.ever")}
    accounted = set(RUN_OUTPUT) | RUN_SILENT
    check("every examples/*.ever is pinned above", on_disk, accounted)
    if on_disk == accounted:
        print(f"  ok   all {len(on_disk)} .ever examples are pinned")
    else:
        for name in sorted(on_disk - accounted):
            print(f"       unpinned: {name}  (add it to RUN_OUTPUT)")
        for name in sorted(accounted - on_disk):
            print(f"       pinned but missing from disk: {name}")

    ezr_on_disk = {p.name for p in EXAMPLES.glob("*.ezr")}
    ezr_accounted = set(CORE_LINEAGE_OUTPUT)
    check("every examples/*.ezr is pinned above", ezr_on_disk, ezr_accounted)
    if ezr_on_disk == ezr_accounted:
        print(f"  ok   all {len(ezr_on_disk)} .ezr examples are pinned")
    else:
        for name in sorted(ezr_on_disk - ezr_accounted):
            print(f"       unpinned: {name}  (add it to CORE_LINEAGE_OUTPUT)")
        for name in sorted(ezr_accounted - ezr_on_disk):
            print(f"       pinned but missing from disk: {name}")


# ── section 5: the unified `ever` wrapper's dispatch itself ──────────
def section_unified_wrapper() -> None:
    """Not a re-run of every pinned case -- this proves the DISPATCH
    logic in `ever` (extension routing, and the empty-output fallback),
    which nothing else here exercises. The examples above already pin
    every runner's actual output; duplicating that through a second
    entry point would test the same evaluators twice and the new code
    not at all.
    """
    print("\nthe unified `ever` wrapper — one command, either lineage")

    out, code = run([sys.executable, str(EVER_WRAPPER),
                     str(EXAMPLES / "weekly_sales.ever")])
    ok = check("ever picks ever_cli.py run for .ever", code, 0)
    ok &= check("ever .ever output matches RUN_OUTPUT",
               out.splitlines(), RUN_OUTPUT["weekly_sales.ever"])
    if ok:
        print("  ok   .ever -> ever_cli.py run")

    out, code = run([sys.executable, str(EVER_WRAPPER),
                     str(EXAMPLES / "trust.ezr")])
    ok = check("ever picks ezrun.py for .ezr", code, 0)
    ok &= check("ever .ezr output matches CORE_LINEAGE_OUTPUT",
               out.splitlines(), CORE_LINEAGE_OUTPUT["trust.ezr"])
    if ok:
        print("  ok   .ezr -> ezrun.py")

    # earned_trust.ever: v4.10's own runner exits 0 with NO output (no
    # top-level `show`, and `main()` is ezrun's convention, not the
    # grammar's) -- the one case that needs the fallback, which is why
    # it was picked as the flagship demo in the first place.
    out, code = run([sys.executable, str(EVER_WRAPPER), str(TRUST)])
    ok = check("ever falls back to ezrun.py on empty ever_cli.py output",
              code, 0)
    ok &= check("ever earned_trust.ever output", out.strip(),
               "133.1  @ 120/256")
    if ok:
        print("  ok   .ever with no top-level show -> falls back to ezrun.py")

    out, code = run([sys.executable, str(EVER_WRAPPER), "no_such.ever"])
    ok = check("ever: missing file exit", code, 1)
    ok &= check("ever: missing file message names the file",
               out.strip(), "ever: no such file: no_such.ever")
    if ok:
        print("  ok   missing file -> exit 1, names the file")


def main() -> int:
    section_run()
    section_first_run()
    section_transcript()
    section_counterfactual()
    section_core_lineage()
    section_unified_wrapper()
    section_completeness()
    if failures:
        print("\nfailed assertions, in order:")
        for label in failures:
            print(f"  x  {label}")
    print(f"\n=== Examples: {passed} passed, {failed} failed ===")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
