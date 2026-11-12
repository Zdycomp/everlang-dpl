#!/usr/bin/env python3
"""heal_parity_test.py — one heal process, three layers, one answer.

The same cases (tests/heal_parity/cases.tsv), against the same archive
copies, run through:

  Python  runtime.run_source, the real .ever path, with the store on
  Java    RepairStore + EverRepair (5-runtime-java), the same operator
  C       the TAC interpreter, lowered and executed (0-atom-c)

Python and Java must agree on everything the process produces: the value,
its confidence, the final action, the full trace, every stored event and
every stored error. C must agree on the value, the confidence and the action.
A disagreement is a failed check: the layers do not implement the same
process, and the one that is wrong has to be fixed.

Work happens under a fresh build/heal-parity-* directory, not the system temp
directory, because some sandboxes deny that. It is removed when the run ends.

Codric Enterprise · Ricky (Dreid) · 2026
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PARITY = os.path.join(HERE, "heal_parity")
# Each run gets a fresh directory here. A fixed path broke every later run on a
# mount where the cleanup could not delete: makedirs met the last run's files.
BUILD = os.path.join(ROOT, "build")
sys.path.insert(0, os.path.join(ROOT, "2-interpreter-python"))

from repair import RepairRegistry, use_registry  # noqa: E402
from runtime import run_source                   # noqa: E402

passed = failed = 0


def ok(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✓ {name}")
    else:
        failed += 1
        print(f"  ✗ {name}")
        if detail:
            print(f"      {detail}")


def read_cases():
    with open(os.path.join(PARITY, "cases.tsv"), encoding="utf-8") as f:
        rows = [line.rstrip("\n").split("\t") for line in f.read().splitlines()[1:] if line]
    return [dict(zip(["name", "op", "expr", "strategy", "fallback", "archive"], r)) for r in rows]


def prepare_archives(prepared):
    """One directory per archive variant, each with a repairs.jsonl. The refix
    variant is the real ReFix archive, copied, never edited."""
    for name in os.listdir(os.path.join(PARITY, "archives")):
        d = os.path.join(prepared, name)
        os.makedirs(d, exist_ok=True)
        shutil.copy(os.path.join(PARITY, "archives", name, "repairs.jsonl"),
                    os.path.join(d, "repairs.jsonl"))
    refix = os.path.join(prepared, "refix")
    os.makedirs(refix, exist_ok=True)
    shutil.copy(os.path.join(ROOT, "7-refix-node", "repairs.jsonl"),
                os.path.join(refix, "repairs.jsonl"))


def _expr(expr, pre):
    """The .ever text for one primary token; adds the bindings it needs to pre.

    A token is int:N, div:A:B, nested:A:B, call:B, zvar, or a nested heal
    heal/<token>/<strategy>/<fallback>, whose fallback is itself a term."""
    if expr.startswith("heal/"):
        _, inner, strategy, fallback = expr.split("/", 3)
        return (f'heal ({_expr(inner, pre)}) using ("{strategy}") '
                f'fallback ({_fallback(fallback, pre)})')
    if expr.startswith("int:"):
        return expr[4:]
    if expr.startswith("div:"):
        _, a, _b = expr.split(":")
        pre["zero"] = "let zero = 0"
        return f"({a} / zero)"
    if expr.startswith("nested:"):
        _, a, _b = expr.split(":")
        pre["zero"] = "let zero = 0"
        return f"(({a} / zero) + 1)"
    if expr.startswith("call:"):
        pre["f"] = "def f(x) = 10 / x"
        return f"f({expr[5:]})"
    if expr == "zvar":
        pre["x"] = "let x = z"
        return "x"
    raise ValueError(expr)


def _fallback(fallback, pre):
    """A fallback is an integer, z, or a nested heal."""
    if fallback.startswith("heal/"):
        return _expr(fallback, pre)
    return fallback


def source_for(case):
    """The .ever program for one case."""
    pre = {}
    e = _expr(case["expr"], pre)
    fb = _fallback(case["fallback"], pre)
    head = "".join(line + "\n" for line in pre.values())
    if case["op"] == "heal":
        return f'{head}let res = heal ({e}) using ("{case["strategy"]}") fallback ({fb})\nshow res'
    return f'{head}let res = learn ({e}) using ("{case["strategy"]}") fix ({fb})\nshow res'


def cell(v):
    return "-" if v is None else str(v)


def read_jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def python_row(case, prepared, work):
    d = os.path.join(work, "py", case["name"])
    os.makedirs(d, exist_ok=True)
    shutil.copy(os.path.join(prepared, case["archive"], "repairs.jsonl"),
                os.path.join(d, "repairs.jsonl"))
    os.environ["EVER_REPAIR_STORE"] = d
    use_registry(RepairRegistry(archive_dir=d))
    try:
        r = run_source(source_for(case))
    finally:
        use_registry(None)
        os.environ.pop("EVER_REPAIR_STORE", None)
    line = r.format_lines()[0]
    m = re.match(r"^res = (.*) \[(\d+)/256\]$", line)
    value, conf = m.group(1), int(m.group(2))
    if value.startswith('"') and value.endswith('"'):
        value = value[1:-1]
    events = read_jsonl(os.path.join(d, "events.jsonl"))
    errors = read_jsonl(os.path.join(d, "errors.jsonl"))
    action = events[-1]["action"] if events else "-"
    return {
        "value": value, "conf": conf, "action": action,
        "trace": " ; ".join(r.heal_trace),
        "events": " ; ".join("|".join(cell(e[k]) for k in
                  ["op", "reason", "strategy", "action", "conf_in", "conf_out",
                   "fixture", "cost", "detail"]) for e in events),
        "errors": " ; ".join(f"{cell(e['message'])}|{e['confidence']}" for e in errors),
    }


def java_rows(prepared, work):
    classes = os.path.join(work, "java-classes")
    shutil.rmtree(classes, ignore_errors=True)
    os.makedirs(classes)
    sources = [os.path.join(ROOT, "5-runtime-java", "com", "codric", "ever", f)
               for f in sorted(os.listdir(os.path.join(ROOT, "5-runtime-java", "com", "codric", "ever")))
               if f.endswith(".java")]
    sources.append(os.path.join(PARITY, "java", "HealMatrix.java"))
    subprocess.run(["javac", "-Xlint:all", "-d", classes] + sources, check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out = subprocess.run(
        ["java", "-cp", classes, "HealMatrix", os.path.join(work, "prepared"),
         os.path.join(PARITY, "cases.tsv"), os.path.join(work, "java")],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True).stdout
    rows = {}
    for line in out.splitlines():
        f = line.split("\t")
        if len(f) < 7:
            continue
        rows[f[0]] = {"value": f[1], "conf": int(f[2]), "action": f[3],
                      "trace": f[4], "events": f[5], "errors": f[6]}
    return rows


def c_rows(prepared, work):
    exe = os.path.join(work, "heal_matrix")
    cc = shutil.which("clang") or shutil.which("gcc")
    if cc is None:
        raise RuntimeError("no C compiler on PATH")
    subprocess.run([cc, "-std=c99", "-Wall", "-I" + os.path.join(ROOT, "0-atom-c"),
                    "-o", exe, os.path.join(PARITY, "heal_matrix.c"),
                    os.path.join(ROOT, "0-atom-c", "scope.c"),
                    os.path.join(ROOT, "0-atom-c", "ir.c"),
                    os.path.join(ROOT, "0-atom-c", "evalue.c"),
                    os.path.join(ROOT, "0-atom-c", "tapestry.c"),
                    os.path.join(ROOT, "0-atom-c", "repair.c"), "-lm"],
                   check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    # one run over the whole file: the driver resolves each case's archive itself
    out = subprocess.run([exe, prepared, os.path.join(PARITY, "cases.tsv")],
                         check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True).stdout
    rows = {}
    for line in out.splitlines():
        f = line.split("\t")
        if len(f) == 4:
            rows[f[0]] = {"value": f[1], "conf": int(f[2]), "action": f[3]}
    return rows


def main():
    os.makedirs(BUILD, exist_ok=True)
    work = tempfile.mkdtemp(prefix="heal-parity-", dir=BUILD)
    prepared = os.path.join(work, "prepared")
    os.makedirs(prepared)
    try:
        print("\n=== Heal parity — Python, Java and C, one process ===\n")
        prepare_archives(prepared)
        cases = read_cases()

        py = {c["name"]: python_row(c, prepared, work) for c in cases}
        jv = java_rows(prepared, work)
        cv = c_rows(prepared, work)

        for c in cases:
            n = c["name"]
            p, j = py[n], jv.get(n)
            print(f"{n}  ({c['op']} {c['expr']} using {c['strategy']!r} fallback {c['fallback']} / {c['archive']})")
            ok(f"{n}: Python and Java agree on the value, confidence and action",
               j is not None and (p["value"], p["conf"], p["action"]) == (j["value"], j["conf"], j["action"]),
               f"python={p['value']}/{p['conf']}/{p['action']} java={j and (j['value'], j['conf'], j['action'])}")
            ok(f"{n}: Python and Java agree on the full trace",
               j is not None and p["trace"] == j["trace"],
               f"python: {p['trace']}\n      java:   {j and j['trace']}")
            ok(f"{n}: Python and Java store the same events",
               j is not None and p["events"] == j["events"],
               f"python: {p['events']}\n      java:   {j and j['events']}")
            ok(f"{n}: Python and Java store the same errors",
               j is not None and p["errors"] == j["errors"],
               f"python: {p['errors']}\n      java:   {j and j['errors']}")
            if c["op"] == "heal":
                k = cv.get(n)
                ok(f"{n}: C agrees on the value, confidence and action",
                   k is not None and (k["value"], k["conf"], k["action"]) == (p["value"], p["conf"], p["action"]),
                   f"python={p['value']}/{p['conf']}/{p['action']} c={k and (k['value'], k['conf'], k['action'])}")

        print(f"\n=== Heal parity: {passed} passed, {failed} failed ===\n")
        return 0 if failed == 0 else 1
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
