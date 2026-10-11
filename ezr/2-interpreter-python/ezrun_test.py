#!/usr/bin/env python3
"""
ezrun_test.py — Ever / Tapestry, the runner and the confidence algebra.

This suite exists because of how ezrun broke. It was ported onto the
v4.10 tree and nothing ran it, so when v4.10's parser turned out to
hand back `Program(statements)` where the older one handed back
`Prog(defs, expr)`, every single invocation started answering

    ezrun: -e defines nothing and does not say what to run.

and the 25-suite gate stayed green through all of it. A runner with no
test is a runner nobody notices the death of.

So every assertion below drives ezrun as a PROCESS, over argv and
stdin, exactly as a person would. Importing the module and calling
`run()` would re-create the original blind spot: `run()` was never the
broken part.

The one exception is the last section, which imports runtime directly
because what it checks -- that a function's own confidence reaches its
result -- has no CLI surface on the `ever run` path at all.

Codric Enterprise
"""

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EZRUN = HERE / "ezrun.py"

p = f = 0


def ok(name, cond):
    global p, f
    if cond:
        p += 1
        print(f"  ✓ {name}")
    else:
        f += 1
        print(f"  ✗ {name}")


def run(*args, stdin=""):
    r = subprocess.run([sys.executable, str(EZRUN), *args],
                       input=stdin, capture_output=True, text=True)
    return r.stdout.strip(), r.stderr.strip(), r.returncode


def says(label, expect, *args, stdin="", code=0):
    out, err, rc = run(*args, stdin=stdin)
    got = out or err.splitlines()[0] if (out or err) else ""
    ok(f"{label}: {expect}",
       got == expect and rc == code)
    if got != expect or rc != code:
        print(f"      got {got!r} exit={rc}, wanted {expect!r} exit={code}")


print("\n=== ezrun — the runner and its confidence algebra ===\n")

print("Expressions evaluate and report their confidence")
says("1 + 1",            "2  @ 256/256", "-e", "1 + 1")
says("2 * 3 + 4",        "10  @ 256/256", "-e", "2 * 3 + 4")
says("if 1 < 2 ...",     "10  @ 256/256", "-e", "if 1 < 2 then 10 else 20")
says("string +",         "ab  @ 256/256", "-e", '"a" + "b"')
says("--quiet drops it", "2", "-e", "1 + 1", "-q")

print("\nA refusal is a refusal at the exit code too")
# ezrun -e 'head([])' once printed Z and exited 0, so anything
# scripting it read a refusal as a success. Exit codes are part of the
# contract, not decoration.
#
# This used to run '[1, 2]' as the refusing example, from when
# eval_ast had no case for ListLit and any list literal came back
# Z("cannot evaluate ListLit") -- a refusal by accident of what wasn't
# implemented yet, not by what the expression means. Now that list
# literals evaluate for real ('[1, 2]' -> '[1, 2]  @ 256/256', exit 0),
# that expression no longer refuses, so the test moved to the actual
# case the comment above has named all along.
_, _, rc = run("-e", "head([])")
ok("Z exits 1 (refused)", rc == 1)
_, _, rc = run("-e", "x")
ok("will-not-compile exits 2", rc == 2)
_, _, rc = run("no_such_file.ever")
ok("missing file exits 2", rc == 2)
out, err, rc = run("no_such_file.ever")
ok("missing file says so, no traceback",
   "no such file" in err and "Traceback" not in err)

print("\nEntry points")
says("main() is called", "42  @ 120/256", "-",
     stdin="def dbl(n) = n * 2\ndef main() = dbl(21)")
says("--call names one", "49  @ 120/256", "-", "--call", "sq(7)",
     stdin="def sq(n) = n * n")
says("a trailing expression is one", "42  @ 120/256", "-",
     stdin="def f(n) = n + 1\nf(41)")
out, err, rc = run("-", stdin="def f(n) = n")
ok("definitions alone refuse to guess",
   "does not say what to run" in err and rc == 2)

print("\n[DEF] — a definition enters below the execute floor")
# A definition is a claim, not a verification. 120 < 128, so an answer
# that came through an unverified function is not cleared to act on.
says("unverified call is intake", "42  @ 120/256", "-",
     stdin="def dbl(n) = n * 2\ndef main() = dbl(21)")
says("a literal is still certain", "42  @ 256/256", "-e", "42")

print("\n[EXAMPLE] — evidence earns confidence")
FACT = "def fact(n) = if n <= 1 then 1 else n * fact(n - 1)"
E1, E2, E3 = "fact(1) = 1", "fact(2) = 2", "fact(3) = 6"
says("0 examples: 120", "6  @ 120/256", "-", "--call", "fact(3)", stdin=FACT)
says("1 example:  120", "6  @ 120/256", "-", "--call", "fact(3)",
     "-x", E1, stdin=FACT)
says("2 examples: 183", "6  @ 183/256", "-", "--call", "fact(3)",
     "-x", E1, "-x", E2, stdin=FACT)
says("3 examples: 217", "6  @ 217/256", "-", "--call", "fact(3)",
     "-x", E1, "-x", E2, "-x", E3, stdin=FACT)
# A failure scales the result by the share that held: 2 of 3, not 3.
says("2 of 3 held:  122", "6  @ 122/256", "-", "--call", "fact(3)",
     "-x", E1, "-x", E2, "-x", "fact(3) = 99", stdin=FACT)
out, err, rc = run("-", "--call", "fact(3)", "-x", "fact(1)", stdin=FACT)
ok("a malformed example is rejected, not ignored",
   "expected 'call = value'" in err and rc == 2)

print("\n[EXAMPLE] — a witness repeated is still one witness")
# T2: corroboration creates nothing. Before this was checked, the SAME
# case stated three times walked 120 -> 183 -> 217, exactly as three
# distinct cases would: real confidence bought with no new evidence.
says("the same case 3x stays at 120", "6  @ 120/256", "-", "--call",
     "fact(3)", "-x", E1, "-x", E1, "-x", E1, stdin=FACT)
says("whitespace does not make a new witness", "6  @ 120/256", "-",
     "--call", "fact(3)", "-x", E1, "-x", "fact( 1 ) = 1", stdin=FACT)
says("distinct cases still ladder", "6  @ 183/256", "-", "--call",
     "fact(3)", "-x", E1, "-x", E2, stdin=FACT)
out, err, rc = run("-", "--call", "fact(3)", "-x", E1,
                   "-x", "fact(1) = 99", stdin=FACT)
ok("evidence that contradicts itself is refused",
   "contradicts itself" in err and rc == 2)

print("\n[ANCHOR] — evidence plus a measure earns depth")
out, err, rc = run("-", "-d", "3", "--call", "fact(20)",
                   "-x", E1, "-x", E2, "-x", E3, stdin=FACT)
ok("unanchored stops at the ceiling",
   "depth ceiling 3 exceeded" in err and rc == 1)
says("anchored recurses past it", "2432902008176640000  @ 217/256",
     "-", "-d", "3", "--call", "fact(20)",
     "-x", E1, "-x", E2, "-x", E3, "-a", "fact", stdin=FACT)
out, err, rc = run("-", "-d", "3", "--call", "fact(3)", "-a", "fact",
                   stdin=FACT)
ok("anchoring an unverified function is refused",
   "below the execute floor" in err and rc == 1)
LOOP = "def loop(n) = if n < 0 then 0 else loop(n)"
out, err, rc = run("-", "--call", "loop(-1)",
                   "-x", "loop(-1) = 0", "-x", "loop(-2) = 0",
                   "-x", "loop(-3) = 0", "-a", "loop", stdin=LOOP)
ok("confidence proves trust, not termination",
   "confidence proves trust, not termination" in err
   and "strictly decreases in every self-call" in err and rc == 1)

print("\nRefusals carry the requirement that lifts them")
# The same algebra read backwards. Forward it answers "what are you
# worth"; backwards it answers "what are you missing" -- and the second
# is the only half a person can act on.
from ezrun import witnesses_needed                             # noqa: E402
ok("0 of 0 needs 2 witnesses", witnesses_needed(0, 0) == 2)
ok("1 of 1 needs 1 more",      witnesses_needed(1, 1) == 1)
ok("2 of 3 needs 1 more",      witnesses_needed(2, 3) == 1)
ok("1 of 9 needs 8 more",      witnesses_needed(1, 9) == 8)
ok("already clear needs none", witnesses_needed(3, 3) == 0)

out, err, rc = run("-", "-d", "3", "--call", "fact(20)", stdin=FACT)
ok("the ceiling says how to earn past it",
   "2 more passing Examples clears 128" in err
   and "then pass -a fact" in err and rc == 1)

out, err, rc = run("-", "-d", "3", "--call", "fact(20)",
                   "-x", E1, "-x", E2, stdin=FACT)
ok("once over the floor it says only anchor it",
   "sits at 183/256, above the floor" in err
   and "Pass -a fact" in err and rc == 1)

# Following its own advice has to actually work, or the advice is a
# nicer-sounding dead end.
out, err, rc = run("-", "-d", "3", "--call", "fact(20)",
                   "-x", E1, "-x", E2, "-a", "fact", stdin=FACT)
ok("and doing what it says succeeds",
   out.strip() == "2432902008176640000  @ 183/256" and rc == 0)

UP = "def up(a, i, n) = if i >= n then 0 else i + up(a, i + 1, n)"
out, err, rc = run("-", "-d", "3", "--call", "up(0, 0, 9)", stdin=UP)
ok("a function that cannot be anchored is told which way its parameters go",
   "i increases by 1" in err and "n unchanged" in err and rc == 1)

out, err, rc = run("-", "--call", "loop(-1)", "-x", "loop(-1) = 0",
                   "-x", "loop(-2) = 0", "-x", "loop(-3) = 0",
                   "-a", "loop", stdin=LOOP)
ok("an anchor refusal names the parameter that never moves",
   "n unchanged" in err and rc == 1)

out, err, rc = run("-", "-d", "3", "--call", "fact(3)", "-a", "fact",
                   stdin=FACT)
ok("anchoring below the floor says how far short it is",
   "2 more passing Examples clears 128" in err and rc == 1)

# 1 / 0 has no requirement to state. Inventing one would be worse than
# silence, so the line is absent rather than vague.
out, err, rc = run("-e", "1 / 0 + 1")
ok("a refusal with no cure stays quiet", "to lift it" not in err)

print("\n[APP] — c_f on the real path (runtime.run_source)")
# The runner above drives syntax.py's eval_ast. `ever run` drives
# runtime.run_source, and the c_f term of min(c_f, c_args, c_result)
# was missing there too: nothing anywhere read ScopeEntry.confidence
# for a function, so a function believed at 1/256 handed back answers
# at 256/256. There is no CLI flag for this yet, so it is checked by
# lowering the entry directly -- which is exactly what an --example
# flag on `ever run` would do.
sys.path.insert(0, str(HERE))
from runtime import eval_confidence, run_source, _ast_to_ir   # noqa: E402
from scope import make_global_scope, eval_node                # noqa: E402
from syntax import compile_ever                               # noqa: E402

g = make_global_scope()
res = run_source("def dbl(n) = n * 2\nlet answer = dbl(21)\nshow answer",
                 scope=g)
ok("the program runs", res.ok and res.format_lines() == ["answer = 42 [256/256]"])

ir = _ast_to_ir(compile_ever("dbl(21)").ast)
ok("value is right", eval_node(ir, g).ev_int == 42)
ok("certain while dbl is certain", eval_confidence(ir, g) == 256)

g.lookup("dbl").confidence = 1
ok("dbl at 1/256 floors the answer to 1", eval_confidence(ir, g) == 1)
ok("the value itself does not move", eval_node(ir, g).ev_int == 42)

print(f"\n=== ezrun: {p} passed, {f} failed ===\n")
raise SystemExit(0 if f == 0 else 1)
