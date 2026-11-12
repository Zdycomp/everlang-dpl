#!/usr/bin/env python3
"""run_all.py — Ever / Tapestry, master test runner. Codric Enterprise 2026.

Outcome of each suite is decided by two things only, never by its output text:

  * the exit code: 0 = pass, 77 = skip (the suite did not run its checks
    because a toolchain it needs is absent), anything else = fail;
  * the REQUIRES list: if a named executable is not on PATH the suite is
    skipped without being run.

A skip is never a pass. The run exits 0 only when nothing failed AND nothing
was skipped, so the gate in CLAUDE.md (N passed / 0 skipped / 0 failed) is
enforced here, not just described. Pass --allow-skip on a machine that
genuinely lacks a toolchain: skips are still reported, but do not fail the run.
"""

import os, shutil, subprocess, sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).parent.parent

# Toolchains installed outside the system paths are named here, not guessed:
#   EVER_TOOLCHAIN_PATH=~/.jdks/jdk-25.0.4.1+1/Contents/Home/bin:~/.local/opt/kotlinc/bin:...
# Each entry is put in front of PATH for every suite, so the run sees exactly these.
for _p in reversed([p for p in os.environ.get("EVER_TOOLCHAIN_PATH", "").split(os.pathsep) if p]):
    os.environ["PATH"] = os.path.expanduser(_p) + os.pathsep + os.environ["PATH"]

# The Go suites share one build cache. Default it to build/ in the repo (gitignored,
# writable by every suite) rather than the home cache, which a sandbox may refuse:
# "failed to initialize build cache" failed three suites with no code defect. A
# GOCACHE already exported still wins.
os.environ.setdefault("GOCACHE", str(ROOT / "build" / "go-cache"))
os.makedirs(os.environ["GOCACHE"], exist_ok=True)

#: Exit code a suite uses to say "my toolchain is absent; I ran nothing".
SKIP_EXIT = 77

# (label, command, executables that must be on PATH)
SUITES = [
    ("C atom",         "gcc -std=c99 -Wall 0-atom-c/tapestry.c 0-atom-c/tapestry_test.c -o $EVER_TMP/t_atom -lm && $EVER_TMP/t_atom", ("gcc",)),
    ("C bridge",       "gcc -std=c99 -Wall 0-atom-c/bridge_test.c 0-atom-c/tapestry.c 0-atom-c/evalue.c 0-atom-c/ir.c -o $EVER_TMP/t_bridge -lm && $EVER_TMP/t_bridge", ("gcc",)),
    ("EValue (C)",     "gcc -std=c99 -Wall 0-atom-c/evalue_test.c 0-atom-c/evalue.c 0-atom-c/tapestry.c -o $EVER_TMP/t_ev -lm && $EVER_TMP/t_ev", ("gcc",)),
    ("IR+arena (C)",   "gcc -std=c99 -Wall 0-atom-c/ir_test.c 0-atom-c/ir.c 0-atom-c/evalue.c 0-atom-c/tapestry.c -o $EVER_TMP/t_ir -lm && $EVER_TMP/t_ir", ("gcc",)),
    ("Phase (C++)",    "gcc -std=c99 -Wall -c 0-atom-c/tapestry.c -o $EVER_TMP/tp.o && g++ -std=c++14 -Wno-format-truncation -c 1-phase-cpp/phase.cpp -o $EVER_TMP/ph.o && g++ -std=c++14 -Wno-format-truncation -c 1-phase-cpp/phase_test.cpp -o $EVER_TMP/pht.o && g++ -o $EVER_TMP/t_ph $EVER_TMP/pht.o $EVER_TMP/ph.o $EVER_TMP/tp.o -lm && $EVER_TMP/t_ph", ("gcc", "g++")),
    ("Lexer",          f"{sys.executable} tests/test_lexer.py", ()),
    ("Parser",         f"{sys.executable} tests/test_parser.py", ()),
    ("ABI",            f"{sys.executable} 2-interpreter-python/abi_test.py", ()),
    ("EValue (Py)",    f"{sys.executable} 2-interpreter-python/evalue_test.py", ()),
    ("Interpreter",    f"{sys.executable} 2-interpreter-python/ever_test.py", ()),
    ("Scope (Py)",     f"{sys.executable} 2-interpreter-python/scope_test.py", ()),
    ("IR bridge",      f"{sys.executable} 2-interpreter-python/ir_runner.py", ()),
    ("Pipeline",       f"{sys.executable} 2-interpreter-python/syntax_test.py", ()),
    ("Abstraction",    f"{sys.executable} 2-interpreter-python/abstract_test.py", ()),
    ("Backends",       f"{sys.executable} tests/test_backends.py", ()),
    ("Vowels",         f"{sys.executable} 2-interpreter-python/vowels_test.py", ()),
    ("Teaching",       f"{sys.executable} 2-interpreter-python/teach_test.py", ()),
    ("Checker",        f"{sys.executable} 2-interpreter-python/checker_test.py", ()),
    ("Collider",       f"{sys.executable} tests/test_collider.py", ()),
    ("SQL archive",    f"{sys.executable} 4-archive-sql/archive_test.py", ()),
    ("Kitchen sink",   "gcc -std=c99 -Wall -o $EVER_TMP/ev_ks 0-atom-c/kitchen_sink.c 0-atom-c/form.c 0-atom-c/form_lower.c 0-atom-c/tac.c 0-atom-c/repair.c 0-atom-c/scope.c 0-atom-c/ir.c 0-atom-c/evalue.c 0-atom-c/tapestry.c -lm && $EVER_TMP/ev_ks", ("gcc",)),
    ("Form IR (C99)",  "gcc -std=c99 -Wall -o $EVER_TMP/ev_form 0-atom-c/form_test.c 0-atom-c/form.c 0-atom-c/form_lower.c 0-atom-c/tac.c 0-atom-c/repair.c 0-atom-c/scope.c 0-atom-c/ir.c 0-atom-c/evalue.c 0-atom-c/tapestry.c -lm && $EVER_TMP/ev_form", ("gcc",)),
    ("Profiler",       f"{sys.executable} 2-interpreter-python/profiler_test.py", ()),
    ("Native (C99)",   "gcc -std=c99 -Wall -o $EVER_TMP/ev_native 0-atom-c/native_test.c 0-atom-c/tapestry.c 0-atom-c/evalue.c 0-atom-c/ir.c 0-atom-c/scope.c 0-atom-c/tac.c 0-atom-c/repair.c -lm && $EVER_TMP/ev_native", ("gcc",)),
    ("CFG (C99)",      "gcc -std=c99 -Wall -o $EVER_TMP/cfg_test 0-atom-c/cfg_test.c 0-atom-c/cfg.c 0-atom-c/ir.c 0-atom-c/evalue.c 0-atom-c/tapestry.c -lm && $EVER_TMP/cfg_test", ("gcc",)),
    ("Tac / HEAL (C99)", "gcc -std=c99 -Wall -o $EVER_TMP/tac_test 0-atom-c/tac_test.c 0-atom-c/tac.c 0-atom-c/repair.c 0-atom-c/form.c 0-atom-c/form_lower.c 0-atom-c/scope.c 0-atom-c/ir.c 0-atom-c/evalue.c 0-atom-c/tapestry.c -lm && $EVER_TMP/tac_test", ("gcc",)),
    ("Scope (C99)",    "gcc -std=c99 -Wall -o $EVER_TMP/scope_test 0-atom-c/scope_test.c 0-atom-c/scope.c 0-atom-c/ir.c 0-atom-c/evalue.c 0-atom-c/tapestry.c -lm && $EVER_TMP/scope_test", ("gcc",)),
    ("Integration",    f"{sys.executable} tests/ev_integrate.py", ()),
    ("Gold standard", f"{sys.executable} tests/gold_check.py", ()),
    ("Golden master",  f"{sys.executable} tests/golden.py", ()),
    ("Notebook",       f"{sys.executable} 2-interpreter-python/notebook.py", ()),
    ("Research",       f"{sys.executable} research.py", ()),
    ("Runner (run.sh)", "bash tests/test_runner.sh", ("bash",)),

    # ── merged from Ever v1: the three layers Tapestry never carried,
    #    plus the polyglot inspector and the applied product.
    ("Repair archive", f"{sys.executable} 4-archive-sql/repair_test.py", ()),
    ("Zeroth (SQL)",   f"{sys.executable} 4-archive-sql/zeroth_test.py", ()),
    ("Zeroth Law",     f"{sys.executable} tests/test_zeroth.py", ()),
    ("Inspect (Py)",   f"{sys.executable} 2-inspect-python/translate_test.py", ()),
    ("Extended languages", f"{sys.executable} 2-inspect-python/language_support_test.py", ()),
    ("Language matrix", f"{sys.executable} 2-interpreter-python/language_matrix_test.py", ()),
    ("ParseLexExecutor", f"{sys.executable} tests/test_parse_lex_executor.py", ()),
    ("Verification oracle", f"{sys.executable} tests/test_verification_oracle.py", ()),
    ("Cross-layer",    f"{sys.executable} tests/cross_layer_test.py", ()),
    ("Ruby DSL",       "ruby 3-dsl-ruby/ever.rb >/dev/null", ("ruby",)),
    ("Java runtime",   "rm -rf $EVER_TMP/ev_java && mkdir -p $EVER_TMP/ev_java && "
                       "javac -d $EVER_TMP/ev_java 5-runtime-java/com/codric/ever/*.java && "
                       "java -cp $EVER_TMP/ev_java com.codric.ever.EverTest", ("javac", "java")),
    ("Repair suite (Java)", "rm -rf $EVER_TMP/ev_java_repair && mkdir -p $EVER_TMP/ev_java_repair && "
                       "javac -d $EVER_TMP/ev_java_repair 5-runtime-java/com/codric/ever/*.java && "
                       "java -cp $EVER_TMP/ev_java_repair com.codric.ever.RepairSuite run", ("javac", "java")),
    ("Heal parity (Py/C/Java)", f"{sys.executable} tests/heal_parity_test.py", ("javac", "java", "gcc")),
    ("HTML inspector", "node 6-interface-html/inspector_test.js", ("node",)),
    ("ReFix (Node)",   "node 7-refix-node/tests/test_all.js", ("node",)),
    ("Finality (Rust/Go)", f"{sys.executable} 8-finality/test_finality.py", ()),
    ("Architecture",    f"{sys.executable} tests/test_architecture.py", ()),
    ("Healing (tests)", f"{sys.executable} tests/test_healing.py", ()),
    ("Healing (internal)", f"{sys.executable} 2-interpreter-python/test_healing_internal.py", ()),
    ("Learn",           f"{sys.executable} 2-interpreter-python/test_learn.py", ()),
    ("RAG/MCP",        f"{sys.executable} tests/test_rag_mcp.py", ()),
    ("Invariants",     f"{sys.executable} tests/test_invariants.py", ()),
    ("Anchor (SEMANTICS §8)", f"{sys.executable} tests/test_anchor.py", ()),
    ("Depth ceiling (Py vs C)", f"{sys.executable} tests/test_ceiling.py", ("gcc",)),
]


def classify(returncode):
    """True for pass, None for skip (exit SKIP_EXIT), False for fail."""
    if returncode == SKIP_EXIT:
        return None
    return returncode == 0


def run(label, cmd, requires, work):
    missing = [tool for tool in requires if shutil.which(tool) is None]
    if missing:
        reason = f"missing toolchain: {', '.join(missing)}"
        return None, 0.0, reason, reason

    t0 = time.time()
    try:
        result = subprocess.run(cmd, cwd=str(ROOT), shell=True,
                                env={**os.environ, "EVER_TMP": work},
                                capture_output=True, text=True, timeout=300)
        output = (result.stdout + result.stderr).strip()
        summary = output.split('\n')[-1] if output else ""
        return (classify(result.returncode),
                time.time() - t0, output, summary)
    except subprocess.TimeoutExpired:
        return False, 300, "TIMEOUT", "timed out"


def status_mark(status):
    return "PASS" if status is True else ("SKIP" if status is None else "FAIL")


def status_symbol(status):
    return "✓" if status is True else ("∼" if status is None else "✗")


def print_failures(results):
    failures = [(label, output) for label, status, output in results
                if status is False]
    if not failures:
        return
    print("  FAILURES:")
    for label, output in failures:
        print(f"\n  [{label}]")
        for line in output.split('\n')[-6:]:
            if line.strip():
                print(f"    {line}")


def main(argv):
    allow_skip = "--allow-skip" in argv
    print("\n" + "=" * 66 +
          "\n  4EVER — full test suite, layer 0 through layer 8\n" +
          "=" * 66 + "\n")
    results = []
    work = tempfile.mkdtemp(prefix="ever-run-")
    try:
        for label, cmd, requires in SUITES:
            print(f"  [{label:<18}]", end="", flush=True)
            status, elapsed, output, summary = run(label, cmd, requires, work)
            print(f"  {status_mark(status)}  ({elapsed:5.1f}s)  {summary[-50:]}")
            results.append((label, status, output))
    finally:
        shutil.rmtree(work, ignore_errors=True)

    passed = sum(status is True for _, status, _ in results)
    failed = sum(status is False for _, status, _ in results)
    skipped = sum(status is None for _, status, _ in results)

    print("\n" + "=" * 66 + "\n  SCORECARD\n" + "=" * 66)
    for label, status, _ in results:
        print(f"  {status_symbol(status)}  {label}")
    print(f"\n  {passed} passed  {skipped} skipped  {failed} failed  of {len(results)} suites\n")

    print_failures(results)
    print("=" * 66 + "\n")

    if failed:
        return 1
    if skipped and not allow_skip:
        print("  Skips are not passes: rerun with the toolchain installed,"
              " or pass --allow-skip.\n")
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
