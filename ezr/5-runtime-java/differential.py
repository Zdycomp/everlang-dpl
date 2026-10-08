#!/usr/bin/env python3
"""Run one corpus through both runners and compare.

The Java runtime is a second implementation of EZR. That is only worth
something if something checks it, and checking it against its own idea of
the rules is not a check -- `RuntimeTest.java` and `abstract_test.py` can
both pass while the two languages quietly disagree about what `10 - 3 - 2`
means.

So: every program below goes through `2-interpreter-python/ezrun.py` and
through `5-runtime-java/ezr`, as *processes*, over the same stdin and
argv. Value, confidence and exit code must match. Anything else is a
divergence, and a divergence means the language was never specified at
that point -- the same finding the forge reports when two parsers split.

This deliberately shells out rather than importing. Importing `syntax.py`
and calling `eval_ast` is what let an entire unreachable feature set pass
87 assertions; the runners are the surface a person actually meets.

    python3 differential.py            # run the corpus
    python3 differential.py -v         # print every case, not just failures
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY_RUNNER = ROOT / "2-interpreter-python" / "ezrun.py"
JAVA_RUNNER = HERE / "ezr"

# ── the corpus ────────────────────────────────────────────────────────
#
# Every line is a program both runners must agree on. Grouped by what each
# group is actually probing, because a corpus nobody can read is a corpus
# nobody extends.

EXPRESSIONS = [
    # arithmetic and the shape of a number
    "1 + 1",
    "2 * 3",
    "10 - 3",
    "10 - 3 - 2",
    "100 / 4",
    "4 / 2",
    "1 / 2",
    "2 + 3 * 4",
    "(2 + 3) * 4",
    "0 - 5",
    "-5",
    "-5 + 10",
    "2 * -3",
    "1.5 + 1.5",
    "0.1 + 0.2",
    "7 / 2",
    "9 / 3",
    "1000000 * 1000000",
    # past 2^53, where a long cast and scientific notation both start
    # lying. Nothing in the corpus reached here until anchoring made
    # deep recursion cheap enough to produce numbers this big.
    "1000000000000000 * 1000",
    "1000000000000000000 + 1",
    "0 - 1000000000000000000",
    "1000000000000000000 * 10",
    # precedence and associativity, where independent parsers usually split
    "1 + 2 + 3",
    "1 - 2 + 3",
    "2 * 3 + 4 * 5",
    "100 / 10 / 2",
    "1 + 2 * 3 - 4 / 2",
    "((1 + 2)) * ((3))",
    # comparison
    "1 < 2",
    "2 < 1",
    "1 <= 1",
    "2 >= 3",
    "1 == 1",
    "1 != 1",
    "1 + 1 == 2",
    "3 * 3 > 8",
    # text
    '"hello"',
    '"a" + "b"',
    '"" + "x"',
    '"a" == "a"',
    '"a" != "b"',
    # booleans
    "true",
    "false",
    "true == true",
    "true != false",
    # lists and the builtins
    "[]",
    "[1]",
    "[1, 2, 3]",
    "[1 + 1, 2 * 2]",
    '["a", "b"]',
    "len([])",
    "len([1, 2, 3])",
    "head([1, 2, 3])",
    "tail([1, 2, 3])",
    "len(tail([1, 2, 3]))",
    "head(tail([1, 2, 3]))",
    # let
    "let x = 5 in x + 1",
    "let x = 1 in let y = 2 in x + y",
    "let x = 2 in x * x",
    'let s = "a" in s + "b"',
    "let xs = [1, 2, 3] in len(xs)",
    # conditionals, known condition
    "if true then 1 else 2",
    "if false then 1 else 2",
    "if 1 < 2 then 10 else 20",
    "if 2 < 1 then 10 else 20",
    'if true then "yes" else "no"',
    # refusals -- these must refuse *the same way* in both
    "1 / 0",
    "head([])",
    "tail([])",
    "len(3)",
    "nope(1)",
    "x",
    "head(1)",
    "len([1], [2])",
    "show(1, 2)",
]

PROGRAMS = [
    # name, source, entry (None means main())
    ("identity", "def main() = 42", None),
    ("one call", "def dbl(n) = n * 2\ndef main() = dbl(21)", None),
    ("two defs", "def a(n) = n + 1\ndef b(n) = a(n) * 2\ndef main() = b(3)", None),
    ("forward", "def main() = g(4)\ndef g(n) = n * n", None),
    ("recursion", "def f(n) = if n <= 1 then 1 else n * f(n - 1)\ndef main() = f(5)", None),
    (
        "sum a list",
        "def total(xs) = if len(xs) == 0 then 0 "
        "else head(xs) + total(tail(xs))\n"
        "def main() = total([1, 2, 3, 4, 5])",
        None,
    ),
    ("let inside", "def f(n) = let d = n * 2 in d + 1\ndef main() = f(10)", None),
    ("higher arity", "def add3(a, b, c) = a + b + c\ndef main() = add3(1, 2, 3)", None),
    ("text out", 'def greet(n) = "hi " + n\ndef main() = greet("you")', None),
    ("--call", "def sq(n) = n * n", "sq(7)"),
    ("--call deep", "def f(n) = if n <= 0 then 0 else 1 + f(n - 1)", "f(20)"),
    ("arity wrong", "def f(n) = n\ndef main() = f(1, 2)", None),
    ("unbound", "def f(n) = n + missing\ndef main() = f(1)", None),
    ("no main", "def f(n) = n", None),
    ("deep halt", "def f(n) = f(n - 1)", "f(500)"),
]

BAD_INPUT = [
    "1 +",
    "((((",
    '"',
    "a $ b",
    "def",
    "let in",
    "]]]",
    "if",
    "a < b < c",
    "f(1,)",
    "def f(n) = n\n1 + 1",
    "def f(n = n",
    '"ab" * 2',
    "true + true",
    "1 / 0 + 1",
]


@dataclass
class Result:
    out: str
    err: str
    code: int

    def stage(self) -> str | None:
        """Which stage refused: lex, parse or semantic."""
        for line in self.err.splitlines():
            for s in ("lex:", "parse:", "semantic:"):
                if s in line:
                    return s[:-1]
        return None

    def defect(self) -> str | None:
        """The binding defect of a runtime refusal: Z(unbound) -> unbound."""
        for line in self.err.splitlines():
            if line.startswith("Z(") and ")" in line:
                return line[2 : line.index(")")]
        return None

    def language(self) -> tuple:
        """What the LANGUAGE did, which is what the two must agree on:
        the value, the exit code, which stage refused, and which of the five
        binding defects it was.

        Deliberately not the wording. The two runners are different programs
        with different names for themselves and different phrasing for the
        same refusal, and holding them to identical prose would be testing
        the error messages rather than the semantics. Where they should be
        held together is here: same answer, same classification.
        """
        return (self.out.strip(), self.code, self.stage(), self.defect())

    def wording(self) -> str:
        """The prose, normalised only for the runners' own names."""
        return (
            self.err.replace("ezrun:", "RUNNER:")
            .replace("ezr:", "RUNNER:")
            .replace("<stdin>", "-")
            .strip()
        )


def run(cmd: list[str], stdin: str = "") -> Result:
    p = subprocess.run(cmd, input=stdin, capture_output=True, text=True)
    return Result(p.stdout, p.stderr, p.returncode)


def py(*args: str, stdin: str = "") -> Result:
    return run([sys.executable, str(PY_RUNNER), *args], stdin)


def java(*args: str, stdin: str = "") -> Result:
    return run([str(JAVA_RUNNER), *args], stdin)


def main() -> int:
    verbose = "-v" in sys.argv or "--verbose" in sys.argv

    if not JAVA_RUNNER.exists():
        print("differential: no Java runner; run ./build.sh first")
        return 2
    if not PY_RUNNER.exists():
        print(f"differential: no Python runner at {PY_RUNNER}")
        return 2

    agree = 0
    splits: list[tuple[str, Result, Result]] = []
    reworded: list[str] = []

    def compare(label: str, p: Result, j: Result) -> None:
        nonlocal agree
        if p.language() != j.language():
            splits.append((label, p, j))
            return
        agree += 1
        if p.wording() != j.wording():
            reworded.append(label)
        if verbose:
            shown = p.out.strip() or (p.err.strip().splitlines() or [""])[0]
            print(f"  ok    {label:<34} {shown}  [{p.code}]")

    print("EZR — differential: Python runner against Java runner")
    print()

    print(f"  expressions ({len(EXPRESSIONS)})")
    for src in EXPRESSIONS:
        compare(src, py("-e", src), java("-e", src))

    print(f"  programs ({len(PROGRAMS)})")
    for name, src, entry in PROGRAMS:
        args = ["-"] if entry is None else ["-", "--call", entry]
        compare(name, py(*args, stdin=src), java(*args, stdin=src))

    print(f"  input that should not compile ({len(BAD_INPUT)})")
    for src in BAD_INPUT:
        compare(repr(src), py("-e", src), java("-e", src))

    print(f"  the examples ({len(list((ROOT / 'examples').glob('*.ezr')))})")
    for f in sorted((ROOT / "examples").glob("*.ezr")):
        compare(f.name, py(str(f)), java(str(f)))

    print("  evidence, earned depth, and what lifts a refusal (15)")
    FACT = "def fact(n) = if n <= 1 then 1 else n * fact(n - 1)"
    LOOP = "def loop(n) = if n < 0 then 0 else loop(n)"
    UP = "def up(a, i, n) = if i >= n then 0 else i + up(a, i + 1, n)"
    E1, E2, E3 = "fact(1) = 1", "fact(2) = 2", "fact(3) = 6"
    for label, src, extra in [
        ("no evidence", FACT, ["--call", "fact(3)"]),
        ("1 example", FACT, ["--call", "fact(3)", "-x", E1]),
        ("2 examples", FACT, ["--call", "fact(3)", "-x", E1, "-x", E2]),
        ("3 examples", FACT,
         ["--call", "fact(3)", "-x", E1, "-x", E2, "-x", E3]),
        ("a failing example", FACT,
         ["--call", "fact(3)", "-x", E1, "-x", E2, "-x", "fact(3) = 99"]),
        ("anchored buys depth", FACT,
         ["-d", "3", "--call", "fact(20)", "-x", E1, "-x", E2, "-x", E3,
          "-a", "fact"]),
        ("anchor unverified", FACT,
         ["-d", "3", "--call", "fact(3)", "-a", "fact"]),
        ("anchor without measure", LOOP,
         ["--call", "loop(-1)", "-x", "loop(-1) = 0", "-x", "loop(-2) = 0",
          "-x", "loop(-3) = 0", "-a", "loop"]),
        # Witness independence. Both runners once counted the same case
        # three times as three witnesses (120 -> 183 -> 217), and the
        # corpus did not reach it because every case here was distinct.
        ("the same witness 3x", FACT,
         ["--call", "fact(3)", "-x", E1, "-x", E1, "-x", E1]),
        ("whitespace is not a witness", FACT,
         ["--call", "fact(3)", "-x", E1, "-x", "fact( 1 ) = 1"]),
        ("evidence contradicting itself", FACT,
         ["--call", "fact(3)", "-x", E1, "-x", "fact(1) = 99"]),
        # Refusals that carry the requirement lifting them. The harness
        # compares the language, not the prose -- but a split in WHICH
        # requirement is named would be a real divergence, and these are
        # the cases where the two could drift apart.
        ("ceiling names the evidence owed", FACT, ["-d", "3", "--call", "fact(20)"]),
        ("ceiling names only the anchor", FACT,
         ["-d", "3", "--call", "fact(20)", "-x", E1, "-x", E2]),
        ("ceiling on an unanchorable function", UP,
         ["-d", "3", "--call", "up(0, 0, 9)"]),
        ("following the advice succeeds", FACT,
         ["-d", "3", "--call", "fact(20)", "-x", E1, "-x", E2, "-a", "fact"]),
    ]:
        compare(label, py("-", *extra, stdin=src),
                java("-", *extra, stdin=src))

    print(f"  depth limits")
    for d in ("1", "3", "5", "50"):
        src = "def f(n) = if n <= 0 then 0 else 1 + f(n - 1)"
        compare(
            f"--depth {d}",
            py("-", "-d", d, "--call", "f(10)", stdin=src),
            java("-", "-d", d, "--call", "f(10)", stdin=src),
        )

    total = agree + len(splits)
    print()
    if splits:
        print(f"  {len(splits)} DIVERGENCE(S) — the two runners disagree:")
        print()
        for label, p, j in splits:
            print(f"    {label}")
            print(f"      python : out={p.out.strip()!r} err={p.err.strip()!r} exit={p.code}")
            print(f"      java   : out={j.out.strip()!r} err={j.err.strip()!r} exit={j.code}")
            print()
        print("  A divergence is a finding, not a bug report against one side.")
        print("  Where two independent implementations split, the language was")
        print("  never specified at that point.")

    if reworded:
        print(f"  {len(reworded)} case(s) agreed on the language and differ only in wording:")
        print(
            f"    {', '.join(reworded[:8])}"
            + (f", and {len(reworded) - 8} more" if len(reworded) > 8 else "")
        )
        print("  Not a divergence. Two runners, two sets of words, one answer.")
        print()

    print(f"  {total} programs, {agree} agreed, {len(splits)} diverged")
    print("  differential OK" if not splits else "  differential FAILED")
    return 1 if splits else 0


if __name__ == "__main__":
    raise SystemExit(main())
