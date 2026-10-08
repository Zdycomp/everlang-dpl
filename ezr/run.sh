#!/usr/bin/env bash
# Ever / Tapestry — build and verify every layer
# pipefail is load bearing, not hygiene. Every layer below is run as
#     ( cd DIR && test | tail -2 ) && pass || fail
# and without it the subshell's status is tail's, which is 0 whatever
# the test did. Measured on this exact script: vowels_test.py patched
# to `raise SystemExit(1)` was reported PASSED. The only failure the
# script could ever report was one where `cd` itself failed before the
# pipe -- which is why a missing 3-dsl-ruby showed up and a failing
# test never would have.
set -u -o pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
P=0; S=0; F=0; declare -a N
have(){ command -v "$1" >/dev/null 2>&1; }
pass(){ P=$((P+1)); N+=("PASSED   $1"); }
fail(){ F=$((F+1)); N+=("FAILED   $1"); }
skip(){ S=$((S+1)); N+=("SKIPPED  $1 — $2"); printf '\n  ~ skipped: %s\n' "$2"; }

echo; echo "════════════════════════════════════════════════"
echo "EVER / TAPESTRY"; echo "Codric Enterprise"
echo "════════════════════════════════════════════════"

echo; echo "[0] C — the atom (carries T)"
if have gcc; then
  ( cd 0-atom-c && gcc -std=c99 -Wall -o tapestry_test tapestry.c tapestry_test.c -lm && ./tapestry_test | tail -2 ) && pass "Layer 0 (C)" || fail "Layer 0 (C)"
else skip "Layer 0 (C)" "gcc not found"; fi

echo; echo "[1] C++ — the phase engine"
if have gcc && have g++; then
  ( cd 1-phase-cpp \
    && gcc -std=c99 -Wall -c ../0-atom-c/tapestry.c -o tapestry.o \
    && g++ -std=c++14 -Wall -Wno-format-truncation -c phase.cpp -o phase.o \
    && g++ -std=c++14 -Wall -Wno-format-truncation -c phase_test.cpp -o phase_test.o \
    && g++ -o phase_test phase_test.o phase.o tapestry.o -lm && ./phase_test | tail -2 ) \
    && pass "Layer 1 (C++)" || fail "Layer 1 (C++)"
else skip "Layer 1 (C++)" "gcc and g++ required"; fi

echo; echo "[2] Python — the interpreter"
if have python3; then
  ( cd 2-interpreter-python && python3 ever_test.py | tail -2 ) && pass "Layer 2 (Python)" || fail "Layer 2 (Python)"
else skip "Layer 2 (Python)" "python3 not found"; fi

echo; echo "[TAC] C — Three-Address IR (EvTAC)"
if have gcc; then
  ( cd 0-atom-c && gcc -std=c99 -Wall tac_test.c tac.c scope.c ir.c evalue.c tapestry.c -o tac_test -lm && ./tac_test | tail -2 && rm -f tac_test ) && pass "TAC IR (C)" || fail "TAC IR (C)"
else skip "TAC IR (C)" "gcc not found"; fi

echo; echo "[SCOPE-C] C — universal map (EvScope)"
if have gcc; then
  ( cd 0-atom-c && gcc -std=c99 -Wall scope_test.c scope.c ir.c evalue.c tapestry.c -o scope_test -lm && ./scope_test | tail -2 && rm -f scope_test scope.o ) && pass "EvScope (C)" || fail "EvScope (C)"
else skip "EvScope (C)" "gcc not found"; fi

echo; echo "[SCOPE-PY] Python — universal map (EvScope)"
if have python3; then
  ( cd 2-interpreter-python && python3 scope_test.py | tail -2 ) && pass "EvScope (Python)" || fail "EvScope (Python)"
else skip "EvScope (Python)" "python3 not found"; fi

echo; echo "[BRIDGE] C — Hello World bridge (5 stages, 45 assertions)"
if have gcc; then
  ( cd 0-atom-c && gcc -std=c99 -Wall bridge_test.c tapestry.c evalue.c ir.c -o bridge_test -lm && ./bridge_test | tail -4 && rm -f bridge_test ) && pass "Bridge (C)" || fail "Bridge (C)"
else skip "Bridge (C)" "gcc not found"; fi

echo; echo "[IR-C] C — IR + arena allocator"
if have gcc; then
  ( cd 0-atom-c && gcc -std=c99 -Wall ir_test.c ir.c evalue.c tapestry.c -o ir_test -lm && ./ir_test | tail -2 && rm -f ir_test evalue.o ir.o ) && pass "IR + arena (C)" || fail "IR + arena (C)"
else skip "IR + arena (C)" "gcc not found"; fi

echo; echo "[IR-PY] Python — IR bridge"
if have python3; then
  ( cd 2-interpreter-python && python3 ir_runner.py | tail -2 ) && pass "IR bridge (Python)" || fail "IR bridge (Python)"
else skip "IR bridge (Python)" "python3 not found"; fi

echo; echo "[EV-C] C — unified variant type (EValue)"
if have gcc; then
  ( cd 0-atom-c && gcc -std=c99 -Wall evalue_test.c evalue.c tapestry.c -o evalue_test -lm && ./evalue_test | tail -2 && rm -f evalue_test evalue.o ) && pass "EValue (C)" || fail "EValue (C)"
else skip "EValue (C)" "gcc not found"; fi

echo; echo "[EV-PY] Python — unified variant type (EValue)"
if have python3; then
  ( cd 2-interpreter-python && python3 evalue_test.py | tail -2 ) && pass "EValue (Python)" || fail "EValue (Python)"
else skip "EValue (Python)" "python3 not found"; fi

echo; echo "[ABI] ABI boundary (packed layout, round-trip through C)"
if have python3 && have gcc; then
  ( cd 2-interpreter-python && python3 abi_test.py | tail -2 ) && pass "ABI boundary" || fail "ABI boundary"
else skip "ABI boundary" "python3 and gcc required"; fi

echo; echo "[UNIT] Unit tests (lexer + parser + golden master)"
if have python3; then
  ( python3 tests/test_lexer.py | tail -2 && python3 tests/test_parser.py | tail -2 && python3 tests/golden.py | tail -2 ) && pass "Unit tests" || fail "Unit tests"
else skip "Unit tests" "python3 not found"; fi

echo; echo "[T] Python — teaching layer (Code for Dummies)"
if have python3; then
  ( cd 2-interpreter-python && python3 teach_test.py | tail -2 ) && pass "Teaching" || fail "Teaching"
else skip "Teaching" "python3 not found"; fi

echo; echo "[2a] Python — pipeline (lexer, parser, AST, semantic)"
if have python3; then
  ( cd 2-interpreter-python && python3 syntax_test.py | tail -2 ) && pass "Pipeline" || fail "Pipeline"
else skip "Pipeline" "python3 not found"; fi

echo; echo "[2b] Python — abstraction (functions, recursion)"
if have python3; then
  ( cd 2-interpreter-python && python3 abstract_test.py | tail -2 ) && pass "Abstraction" || fail "Abstraction"
else skip "Abstraction" "python3 not found"; fi

echo; echo "[2b+] Python — the runner (ezrun: entry points, Examples, anchoring)"
if have python3; then
  ( cd 2-interpreter-python && python3 ezrun_test.py | tail -2 ) && pass "Runner" || fail "Runner"
else skip "Runner" "python3 not found"; fi

echo; echo "[2c] Python — vowel operators (I O U, synthesis)"
if have python3; then
  ( cd 2-interpreter-python && python3 vowels_test.py | tail -2 ) && pass "Vowels" || fail "Vowels"
else skip "Vowels" "python3 not found"; fi

echo; echo "[2d] Python — notebook batch (13 cells)"
if have python3; then
  ( cd 2-interpreter-python && python3 notebook.py | tail -6 ) && pass "Notebook" || fail "Notebook"
else skip "Notebook" "python3 not found"; fi

echo; echo "[PARITY] one rule, every language (C, Python, Ruby, Java)"
if have python3; then
  ( python3 tests/algebra_parity.py | tail -2 ) && pass "Algebra parity" || fail "Algebra parity"
else skip "Algebra parity" "python3 not found"; fi

echo; echo "[3] Ruby — the DSL"
if have ruby; then
  ( cd 3-dsl-ruby && ruby ever.rb | tail -2 ) && pass "Layer 3 (Ruby)" || fail "Layer 3 (Ruby)"
else skip "Layer 3 (Ruby)" "ruby not found (macOS: brew install ruby)"; fi

echo; echo "[4] SQL — the archive"
if have python3; then
  ( cd 4-archive-sql && python3 archive_test.py | tail -2 ) && pass "Layer 4 (SQL)" || fail "Layer 4 (SQL)"
else skip "Layer 4 (SQL)" "python3 required"; fi

echo; echo "[R] Research team"
if have python3; then
  python3 research.py | tail -22 && pass "Research" || fail "Research"
else skip "Research" "python3 required"; fi

echo; echo "════════════════════════════════════════════════"
echo "SUMMARY"; echo "════════════════════════════════════════════════"
for n in "${N[@]}"; do printf '  %s\n' "$n"; done
printf '\n  verified %d   skipped %d   failed %d\n\n' "$P" "$S" "$F"
[ "$F" -gt 0 ] && exit 1
exit 0
