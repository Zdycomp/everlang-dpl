"""The reason-code registry is one file, spec/reason_codes.tsv, and every layer
that carries codes must agree with it: same codes, same kinds, same meanings.

Exit 0 on agreement, 1 on any drift. Layers are added here as they gain codes.
"""

import csv
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "everconf"))

from everconf.reasons import REASONS  # noqa: E402

SPEC = os.path.join(ROOT, "spec", "reason_codes.tsv")

REQUIRED_UNKNOWN = {"MISSING_INPUT", "CONFLICTING_SOURCES", "BELOW_THRESHOLD",
                    "TIMEOUT", "OUT_OF_RANGE", "UNVERIFIED_SOURCE"}


def load_spec():
    with open(SPEC, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    return {r["code"]: (r["kind"], r["meaning"]) for r in rows}, rows


def main() -> int:
    problems = []
    spec, rows = load_spec()

    if [r for r in rows if not r["code"] or not r["kind"] or not r["meaning"]]:
        problems.append("spec has a row with an empty field")
    if len(spec) != len(rows):
        problems.append("spec has a duplicate code")

    for code, (kind, meaning) in spec.items():
        if kind not in ("unknown", "note"):
            problems.append(f"{code}: kind must be unknown or note, not {kind!r}")

    missing_required = REQUIRED_UNKNOWN - {c for c, (k, _) in spec.items() if k == "unknown"}
    if missing_required:
        problems.append(f"spec lacks required unknown codes: {sorted(missing_required)}")

    if set(spec) != set(REASONS):
        problems.append(f"everconf has {sorted(set(REASONS) ^ set(spec))} differently from the spec")
    for code in set(spec) & set(REASONS):
        if REASONS[code] != spec[code]:
            problems.append(f"{code}: everconf says {REASONS[code]}, spec says {spec[code]}")

    # The C table, read from its source: one entry per code, same kind and meaning.
    import re
    with open(os.path.join(ROOT, "0-atom-c", "reason.h"), encoding="utf-8") as f:
        header = f.read()
    entries = re.findall(r'\{"([A-Z_]+)",\s*([01]),\s*"((?:[^"\\]|\\.)*)"\}', header)
    c_table = {code: ("unknown" if flag == "1" else "note", meaning) for code, flag, meaning in entries}
    if len(entries) != len(spec):
        problems.append(f"C table has {len(entries)} entries, spec has {len(spec)}")
    if set(c_table) != set(spec):
        problems.append(f"C table and spec differ on {sorted(set(c_table) ^ set(spec))}")
    for code in set(c_table) & set(spec):
        if c_table[code] != spec[code]:
            problems.append(f"C: {code} says {c_table[code]}, spec says {spec[code]}")

    if problems:
        for p in problems:
            print("FAIL", p)
        print(f"reason registry: {len(problems)} problem(s)")
        return 1
    unknown = sum(1 for k, _ in spec.values() if k == "unknown")
    print(f"reason registry: {len(spec)} codes ({unknown} unknown, {len(spec) - unknown} note), "
          f"everconf and C agree with spec/reason_codes.tsv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
