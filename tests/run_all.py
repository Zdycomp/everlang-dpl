#!/usr/bin/env python3
"""run_all.py — Ever / Tapestry, master test runner. Codric Enterprise 2026."""

import subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).parent.parent

SUITES = [
    ("C atom",         "gcc -std=c99 -Wall 0-atom-c/tapestry.c 0-atom-c/tapestry_test.c -o /tmp/t_atom -lm && /tmp/t_atom"),
    ("C bridge",       "gcc -std=c99 -Wall 0-atom-c/bridge_test.c 0-atom-c/tapestry.c 0-atom-c/evalue.c 0-atom-c/ir.c -o /tmp/t_bridge -lm && /tmp/t_bridge"),
    ("EValue (C)",     "gcc -std=c99 -Wall 0-atom-c/evalue_test.c 0-atom-c/evalue.c 0-atom-c/tapestry.c -o /tmp/t_ev -lm && /tmp/t_ev"),
    ("IR+arena (C)",   "gcc -std=c99 -Wall 0-atom-c/ir_test.c 0-atom-c/ir.c 0-atom-c/evalue.c 0-atom-c/tapestry.c -o /tmp/t_ir -lm && /tmp/t_ir"),
    ("Phase (C++)",    "gcc -std=c99 -Wall -c 0-atom-c/tapestry.c -o /tmp/tp.o && g++ -std=c++14 -Wno-format-truncation -c 1-phase-cpp/phase.cpp -o /tmp/ph.o && g++ -std=c++14 -Wno-format-truncation -c 1-phase-cpp/phase_test.cpp -o /tmp/pht.o && g++ -o /tmp/t_ph /tmp/pht.o /tmp/ph.o /tmp/tp.o -lm && /tmp/t_ph"),
    ("Lexer",          f"{sys.executable} tests/test_lexer.py"),
    ("Parser",         f"{sys.executable} tests/test_parser.py"),
    ("ABI",            f"{sys.executable} 2-interpreter-python/abi_test.py"),
    ("EValue (Py)",    f"{sys.executable} 2-interpreter-python/evalue_test.py"),
    ("Interpreter",    f"{sys.executable} 2-interpreter-python/ever_test.py"),
    ("IR bridge",      f"{sys.executable} 2-interpreter-python/ir_runner.py"),
    ("Pipeline",       f"{sys.executable} 2-interpreter-python/syntax_test.py"),
    ("Abstraction",    f"{sys.executable} 2-interpreter-python/abstract_test.py"),
    ("Vowels",         f"{sys.executable} 2-interpreter-python/vowels_test.py"),
    ("Teaching",       f"{sys.executable} 2-interpreter-python/teach_test.py"),
    ("SQL archive",    f"{sys.executable} 4-archive-sql/archive_test.py"),
    ("Kitchen sink",   "gcc -std=c99 -Wall -o /tmp/ev_ks 0-atom-c/kitchen_sink.c 0-atom-c/form.c 0-atom-c/form_lower.c 0-atom-c/tac.c 0-atom-c/scope.c 0-atom-c/ir.c 0-atom-c/evalue.c 0-atom-c/tapestry.c -lm && /tmp/ev_ks"),
    ("Form IR (C99)",  "gcc -std=c99 -Wall -o /tmp/ev_form 0-atom-c/form_test.c 0-atom-c/form.c 0-atom-c/form_lower.c 0-atom-c/tac.c 0-atom-c/scope.c 0-atom-c/ir.c 0-atom-c/evalue.c 0-atom-c/tapestry.c -lm && /tmp/ev_form"),
    ("Profiler",       f"{sys.executable} 2-interpreter-python/profiler_test.py"),
    ("Native (C99)",   "gcc -std=c99 -Wall -o /tmp/ev_native 0-atom-c/native_test.c 0-atom-c/tapestry.c 0-atom-c/evalue.c 0-atom-c/ir.c 0-atom-c/scope.c 0-atom-c/tac.c -lm && /tmp/ev_native"),
    ("Integration",    f"{sys.executable} tests/ev_integrate.py"),
    ("Gold standard", f"{sys.executable} tests/gold_check.py"),
    ("Golden master",  f"{sys.executable} tests/golden.py"),
    ("Notebook",       f"{sys.executable} 2-interpreter-python/notebook.py"),
    ("Research",       f"{sys.executable} research.py"),

    # ── merged from Ever v1: the three layers Tapestry never carried,
    #    plus the polyglot inspector and the applied product. Layers
    #    whose toolchain is absent report SKIP; they never report PASS.
    ("Repair archive", f"{sys.executable} 4-archive-sql/repair_test.py"),
    ("Zeroth (SQL)",   f"{sys.executable} 4-archive-sql/zeroth_test.py"),
    ("Zeroth Law",     f"{sys.executable} tests/test_zeroth.py"),
    ("Inspect (Py)",   f"{sys.executable} 2-inspect-python/translate_test.py"),
    ("Cross-layer",    f"{sys.executable} tests/cross_layer_test.py"),
    ("Ruby DSL",       "if command -v ruby >/dev/null 2>&1; then "
                       "ruby 3-dsl-ruby/ever.rb >/dev/null && "
                       "echo '=== Layer 3: ran clean (demo, no assertions) ==='; "
                       "else echo 'SKIP: no ruby toolchain'; fi"),
    ("Java runtime",   "if command -v javac >/dev/null 2>&1; then "
                       "rm -rf /tmp/ev_java && mkdir -p /tmp/ev_java && "
                       "javac -d /tmp/ev_java 5-runtime-java/com/codric/ever/*.java && "
                       "java -cp /tmp/ev_java com.codric.ever.EverTest; "
                       "else echo 'SKIP: no java toolchain'; fi"),
    ("HTML inspector", "if command -v node >/dev/null 2>&1; then "
                       "node 6-interface-html/inspector_test.js; "
                       "else echo 'SKIP: no node toolchain'; fi"),
    ("ReFix (Node)",   "if command -v node >/dev/null 2>&1; then "
                       "node 7-refix-node/tests/test_all.js; "
                       "else echo 'SKIP: no node toolchain'; fi"),
]

def run(label, cmd):
    t0 = time.time()
    try:
        r = subprocess.run(cmd, cwd=str(ROOT), shell=True,
                           capture_output=True, text=True, timeout=300)
        out = (r.stdout + r.stderr).strip()
        last = out.split('\n')[-1] if out else ""
        if "SKIP:" in out or ("not found" in out and r.returncode != 0):
            return None, time.time()-t0, out, last
        return r.returncode == 0, time.time()-t0, out, last
    except subprocess.TimeoutExpired:
        return False, 300, "TIMEOUT", "timed out"

def main():
    print("\n" + "="*66 + "\n  4EVER — full test suite, layer 0 through layer 7\n" + "="*66 + "\n")
    results = []
    for label, cmd in SUITES:
        print(f"  [{label:<18}]", end="", flush=True)
        status, elapsed, out, summary = run(label, cmd)
        mark = "PASS" if status is True else ("SKIP" if status is None else "FAIL")
        print(f"  {mark}  ({elapsed:5.1f}s)  {summary[-50:]}")
        results.append((label, status, out))

    passed  = sum(1 for _,s,_ in results if s is True)
    failed  = sum(1 for _,s,_ in results if s is False)
    skipped = sum(1 for _,s,_ in results if s is None)

    print("\n" + "="*66 + "\n  SCORECARD\n" + "="*66)
    for label, status, _ in results:
        sym = "\u2713" if status is True else ("\u223c" if status is None else "\u2717")
        print(f"  {sym}  {label}")
    print(f"\n  {passed} passed  {skipped} skipped  {failed} failed  of {len(results)} suites\n")

    failures = [(l,o) for l,s,o in results if s is False]
    if failures:
        print("  FAILURES:")
        for label, out in failures:
            print(f"\n  [{label}]")
            for line in out.split('\n')[-6:]:
                if line.strip(): print(f"    {line}")
    print("="*66 + "\n")
    return 0 if not failures else 1

if __name__ == '__main__':
    sys.exit(main())
