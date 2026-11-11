#!/usr/bin/env python3
"""
algebra_parity.py — one rule, every language, or the gate fails.

The standing rule for this project is that anything written in Python is
written in every language the system implements. A rule like that decays
the moment nobody checks it: `movements`, `witnesses_needed` and
`from_examples` all existed in Python and Java and in nothing else, and
nothing anywhere said so.

So this runs the SAME [EXAMPLE] ladder and the SAME inverse through every
implementation that has one — C, Python, Ruby, Java — as processes, and
fails if any two disagree. Not "each has a function of that name": the
same inputs, the same numbers out.

    python3 tests/algebra_parity.py          check them
    python3 tests/algebra_parity.py -v       print every vector

A language whose toolchain is absent is SKIPPED, the way run.sh skips a
layer it cannot build — a missing compiler is not a disagreement. But a
language that is PRESENT and lacks the function is a failure, because
that is exactly the drift the rule exists to prevent.

Codric Enterprise
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "2-interpreter-python"))

#: The probe. Chosen to hit every branch of the rule: nothing, the
#: single witness that is still short, the two that clear the floor, a
#: partial failure, and a tally so lopsided the target is far away.
LADDER = [(p, p) for p in range(0, 9)] + [(2, 3), (1, 3), (0, 2), (2, 5), (1, 9)]
NEEDED = [(0, 0), (1, 1), (2, 2), (3, 3), (2, 3), (1, 3), (0, 2), (2, 5), (1, 9)]

FLOOR = 128
CAP = 64


def _fmt(ladder, needed) -> str:
    return (" ".join(str(x) for x in ladder) + " | "
            + " ".join(str(x) for x in needed))


def python_vectors() -> str:
    from ezrun import confidence_from_examples, witnesses_needed
    lad = [confidence_from_examples(p, t) for p, t in LADDER]
    ned = [witnesses_needed(p, t, FLOOR, CAP) for p, t in NEEDED]
    return _fmt(lad, [-1 if n is None else n for n in ned])


def c_vectors(tmp: Path) -> str | None:
    if not shutil.which("gcc"):
        return None
    src = tmp / "probe.c"
    src.write_text(
        '#include <stdio.h>\n#include "tapestry.h"\nint main(void){\n'
        + "".join(f'  printf("%d ", e_confidence_from_examples({p}, {t}));\n'
                  for p, t in LADDER)
        + '  printf("| ");\n'
        + "".join(f'  printf("%d ", e_witnesses_needed({p}, {t}, {FLOOR}, {CAP}));\n'
                  for p, t in NEEDED)
        + '  printf("\\n");\n  return 0;\n}\n')
    exe = tmp / "probe"
    atom = ROOT / "0-atom-c"
    r = subprocess.run(["gcc", "-std=c99", "-Wall", f"-I{atom}",
                        str(atom / "tapestry.c"), str(src), "-o", str(exe), "-lm"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return f"DID NOT BUILD: {r.stderr.strip().splitlines()[:2]}"
    out = subprocess.run([str(exe)], capture_output=True, text=True).stdout
    return " ".join(out.split())


def ruby_vectors() -> str | None:
    if not shutil.which("ruby"):
        return None
    lib = ROOT / "3-dsl-ruby" / "ever.rb"
    script = (
        f'require_relative "{lib.with_suffix("")}"\n'
        f'lad = {[list(x) for x in LADDER]!r}.map {{ |p, t| EZR.from_examples(p, t) }}\n'
        f'ned = {[list(x) for x in NEEDED]!r}.map {{ |p, t| '
        f'EZR.witnesses_needed(p, t, {FLOOR}, {CAP}) || -1 }}\n'
        'puts (lad + ["|"] + ned).join(" ")\n')
    r = subprocess.run(["ruby", "-e", script], capture_output=True, text=True)
    if r.returncode != 0:
        return f"DID NOT RUN: {r.stderr.strip().splitlines()[:2]}"
    return " ".join(r.stdout.split())


def java_vectors(tmp: Path) -> str | None:
    if not shutil.which("javac"):
        return None
    layer = ROOT / "5-runtime-java"
    out = layer / "out"
    if not out.is_dir():
        b = subprocess.run(["bash", str(layer / "build.sh")],
                           capture_output=True, text=True)
        if b.returncode != 0 or not out.is_dir():
            return f"DID NOT BUILD: {b.stderr.strip().splitlines()[:2]}"
    src = tmp / "Probe.java"
    src.write_text(
        "import com.codric.ezr.Laws;\npublic final class Probe {\n"
        "  public static void main(String[] a) {\n"
        "    StringBuilder s = new StringBuilder();\n"
        + "".join(f'    s.append(Laws.fromExamples({p}, {t})).append(" ");\n'
                  for p, t in LADDER)
        + '    s.append("| ");\n'
        + "".join(f'    s.append(Laws.witnessesNeeded({p}, {t}, {FLOOR}, {CAP}))'
                  f'.append(" ");\n' for p, t in NEEDED)
        + "    System.out.println(s.toString().trim());\n  }\n}\n")
    r = subprocess.run(["javac", "-cp", str(out), "-d", str(tmp), str(src)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return f"DID NOT BUILD: {r.stderr.strip().splitlines()[:2]}"
    # JAVA_TOOL_OPTIONS prints a banner on every JVM start and would land
    # in the captured output. Removed, not emptied -- an empty value still
    # prints the banner. Same reason 5-runtime-java/ezr does it.
    env = {k: v for k, v in __import__("os").environ.items()
           if k != "JAVA_TOOL_OPTIONS"}
    p = subprocess.run(["java", "-cp", f"{out}:{tmp}", "Probe"],
                       capture_output=True, text=True, env=env)
    if p.returncode != 0:
        return f"DID NOT RUN: {p.stderr.strip().splitlines()[:2]}"
    return " ".join(p.stdout.split())


def main() -> int:
    verbose = "-v" in sys.argv or "--verbose" in sys.argv
    print("\n=== [EXAMPLE] parity — one rule, every language ===\n")

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        got = {
            "python (ever/ezrun)": python_vectors(),
            "c (0-atom-c)":        c_vectors(tmp),
            "ruby (3-dsl-ruby)":   ruby_vectors(),
            "java (5-runtime)":    java_vectors(tmp),
        }

    ref = got["python (ever/ezrun)"]
    agreed = skipped = failed = 0
    for name, vec in got.items():
        if vec is None:
            print(f"  ~ {name:<22} skipped, toolchain absent")
            skipped += 1
            continue
        if vec == ref:
            print(f"  \u2713 {name:<22} agrees")
            agreed += 1
        else:
            print(f"  \u2717 {name:<22} DISAGREES")
            print(f"      python : {ref}")
            print(f"      {name.split()[0]:<7}: {vec}")
            failed += 1
        if verbose:
            print(f"      {vec}")

    print(f"\n  {agreed} agreed, {skipped} skipped, {failed} disagreed\n")
    if failed:
        print("  A disagreement here is one rule with two answers. Fix the")
        print("  implementation, never the probe.\n")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
