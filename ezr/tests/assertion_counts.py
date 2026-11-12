#!/usr/bin/env python3
"""
assertion_counts.py — the assertion tables, generated from a real run.

Five documents carried assertion counts typed in by hand, and they had
drifted apart: FINDINGS.md said the Python interpreter had 81, four other
files said 83, and the suite itself says 83. A number that is transcribed
is a number that goes stale silently, because nothing fails when it does.

So: run every suite once, read the tally each one prints, and emit the
table from that. The docs cite generated output; nobody types a count.

    python3 tests/assertion_counts.py              the table, as markdown
    python3 tests/assertion_counts.py --json       machine-readable
    python3 tests/assertion_counts.py --write      splice it into FINDINGS.md
    python3 tests/assertion_counts.py --check      exit 1 if the committed
                                                   block is not what this
                                                   run produces

`--check` is the part that keeps it honest, and it is wired into
run_all.py so it runs with everything else. Generating a table nobody
compares against is the same failure one step later.

Codric Enterprise
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from run_all import SUITES  # noqa: E402  the single list of what exists

#: Every suite in this project signs off the same way:
#:     === <label>: N passed, M failed ===
#: Parsing that rather than counting `ok(...)` calls statically means the
#: number is what EXECUTED, not what was written -- a test skipped behind
#: a condition would otherwise still be counted.
TALLY = re.compile(r"===\s*(?P<label>[^:]+):\s*(?P<passed>\d+)\s+passed,"
                   r"\s*(?P<failed>\d+)\s+failed\s*===")

#: Suites that sign off some other way -- "ALL GOLD", a banner, a report --
#: are recorded as having RUN and given no number. An earlier draft of this
#: file scanned their output for any `N/M` and reported the first thing it
#: found: ev_integrate became 12, gold_check 8, notebook 6, and research
#: 1089 (which is the excel grid, not an assertion count). Four invented
#: numbers, in the script written to stop numbers being invented. There is
#: no heuristic here now: a canonical tally, or nothing.


def run(cmd: str) -> tuple[int, str]:
    p = subprocess.run(cmd, shell=True, cwd=ROOT,
                       capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


#: run_all.py lists this script as a suite so the check runs with the
#: gate. Harvesting that entry would re-enter this file, which re-reads
#: SUITES, which lists it again -- one `--check` would fan out into a
#: whole gate run per level. Skipped by name, here, rather than by
#: leaving it out of run_all.py: a check nobody runs is not a check.
SELF = Path(__file__).name


def harvest() -> list[dict]:
    rows = []
    for label, cmd in SUITES:
        if SELF in cmd:
            continue
        code, out = run(cmd)
        m = None
        for m in TALLY.finditer(out):
            pass                      # the LAST tally is the suite's own
        if m:
            rows.append({"suite": label, "reported": m.group("label").strip(),
                         "passed": int(m.group("passed")),
                         "failed": int(m.group("failed")),
                         "exit": code, "kind": "assertions"})
            continue
        rows.append({"suite": label, "reported": "", "passed": None,
                     "failed": 0 if code == 0 else 1,
                     "exit": code, "kind": "ran"})
    return rows


def markdown(rows: list[dict]) -> str:
    counted = [r for r in rows if r["kind"] == "assertions"]
    width = max(len(r["suite"]) for r in rows)
    out = ["| suite | assertions | failed |", "|---|---:|---:|"]
    for r in rows:
        n = r["passed"] if r["kind"] == "assertions" else "ran"
        out.append(f"| {r['suite']:<{width}} | {n} | {r['failed']} |")
    out.append(f"| **total** | **{sum(r['passed'] for r in counted)}** | "
               f"**{sum(r['failed'] for r in rows)}** |")
    ran = [r["suite"] for r in rows if r["kind"] == "ran"]
    if ran:
        out.append("")
        out.append(f"The total covers the {len(counted)} suites that report a "
                   f"tally. {len(ran)} more run and pass without counting "
                   f"assertions ({', '.join(ran)}); they are verified, not "
                   f"quantified, and inventing a number for them is what this "
                   f"table exists to prevent.")
    return "\n".join(out)


#: The one file that carries the generated table. Four other documents
#: used to carry their own hand-typed copies; five transcriptions of one
#: number is five chances to be wrong, and they had already diverged.
#: They now point here instead.
TARGET = ROOT / "FINDINGS.md"
BEGIN = "<!-- assertion-counts:begin -->"
END = "<!-- assertion-counts:end -->"


def splice(text: str, block: str) -> str:
    """Replace the marked region, or refuse rather than guess where it goes."""
    i, j = text.find(BEGIN), text.find(END)
    if i < 0 or j < 0 or j < i:
        raise SystemExit(f"{TARGET.name}: markers {BEGIN} / {END} not found")
    return text[:i] + BEGIN + "\n" + block + "\n" + text[j:]


def check(rows: list[dict]) -> int:
    """Exit 1 if the committed block is not what this run produces.

    An exact diff of one delimited region, not a search for numbers that
    look like counts. The earlier version matched doc labels against suite
    labels by substring and reported a single table row as three different
    suites at once -- a check that cannot be trusted is worse than none,
    because it gets silenced rather than fixed.
    """
    want = markdown(rows)
    have = TARGET.read_text()
    i, j = have.find(BEGIN), have.find(END)
    if i < 0 or j < 0:
        print(f"  {TARGET.name}: generated block missing")
        return 1
    current = have[i + len(BEGIN):j].strip("\n")
    if current == want:
        print(f"  {TARGET.name}: generated block matches this run.")
        return 0
    import difflib
    print(f"  {TARGET.name}: generated block is stale.\n")
    for line in difflib.unified_diff(current.splitlines(), want.splitlines(),
                                     "committed", "this run", lineterm=""):
        print("  " + line)
    print("\n  Run: python3 tests/assertion_counts.py --write")
    return 1


def write(rows: list[dict]) -> int:
    TARGET.write_text(splice(TARGET.read_text(), markdown(rows)))
    print(f"  {TARGET.name}: generated block updated.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    rows = harvest()
    if args.json:
        print(json.dumps(rows, indent=2))
        return 0
    if args.check:
        return check(rows)
    if args.write:
        return write(rows)
    print(markdown(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
