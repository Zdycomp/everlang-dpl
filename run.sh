#!/usr/bin/env bash
# 4Ever — build and verify every layer
set -u
set -o pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
P=0; S=0; F=0; declare -a N=()
have(){ command -v "$1" >/dev/null 2>&1; }
pass(){ P=$((P+1)); N+=("PASSED   $1"); }
fail(){ F=$((F+1)); N+=("FAILED   $1"); }
skip(){ S=$((S+1)); N+=("SKIPPED  $1 — $2"); printf '\n  ~ skipped: %s\n' "$2"; }

run_py_test(){ # dir script name tail_lines
  local dir="$1" script="$2" name="$3" tail="${4:-2}"
  ( cd "$dir" && python3 "$script" | tail -"$tail" ) && pass "$name" || fail "$name"
}

run_c_test(){ # name dir sources output artifacts tail_lines
  local name="$1" dir="$2" src="$3" out="$4" art="$5" tail="${6:-2}"
  ( cd "$dir" && trap "rm -f $art" EXIT \
      && gcc -std=c99 -Wall $src -o "$out" -lm \
      && ./"$out" | tail -"$tail" ) && pass "$name" || fail "$name"
}

run_raw_test(){ # name dir cmd tail
  local name="$1" dir="$2" cmd="$3" tail="${4:-2}"
  ( cd "$dir" && eval "$cmd" ) | tail -"$tail" && pass "$name" || fail "$name"
}

require_ok(){ local t; for t in "$@"; do have "$t" || return 1; done; }


# Suite table: key|kind(py|c|raw)|name|header|dir|require|payload|tail|skip_message
# kind c payload: "sources::output::artifacts"; kind raw payload: shell command (eval'd in dir)
SUITES=(
'0|c|Layer 0 (C)|C — the atom (carries T)|0-atom-c|gcc|tapestry.c tapestry_test.c::tapestry_test::tapestry_test|2|'
'1|raw|Layer 1 (C++)|C++ — the phase engine|1-phase-cpp|gcc g++|gcc -std=c99 -Wall -c ../0-atom-c/tapestry.c -o tapestry.o && g++ -std=c++14 -Wall -Wno-format-truncation -c phase.cpp -o phase.o && g++ -std=c++14 -Wall -Wno-format-truncation -c phase_test.cpp -o phase_test.o && trap "rm -f tapestry.o phase.o phase_test.o phase_test" EXIT && g++ -o phase_test phase_test.o phase.o tapestry.o -lm && ./phase_test|2|gcc and g++ required'
'2|py|Layer 2 (Python)|Python — the interpreter|2-interpreter-python|python3|ever_test.py|2|'
'tac|c|TAC IR (C)|C — Three-Address IR (EvTAC)|0-atom-c|gcc|tac_test.c tac.c scope.c ir.c evalue.c tapestry.c::tac_test::tac_test|2|'
'scope-c|c|EvScope (C)|C — universal map (EvScope)|0-atom-c|gcc|scope_test.c scope.c ir.c evalue.c tapestry.c::scope_test::scope_test scope.o|2|'
'scope-py|py|EvScope (Python)|Python — universal map (EvScope)|2-interpreter-python|python3|scope_test.py|2|'
'bridge|c|Bridge (C)|C — Hello World bridge (5 stages, 45 assertions)|0-atom-c|gcc|bridge_test.c tapestry.c evalue.c ir.c::bridge_test::bridge_test|4|'
'ir-c|c|IR + arena (C)|C — IR + arena allocator|0-atom-c|gcc|ir_test.c ir.c evalue.c tapestry.c::ir_test::ir_test evalue.o ir.o|2|'
'ir-py|py|IR bridge (Python)|Python — IR bridge|2-interpreter-python|python3|ir_runner.py|2|'
'ev-c|c|EValue (C)|C — unified variant type (EValue)|0-atom-c|gcc|evalue_test.c evalue.c tapestry.c::evalue_test::evalue_test evalue.o|2|'
'ev-py|py|EValue (Python)|Python — unified variant type (EValue)|2-interpreter-python|python3|evalue_test.py|2|'
'abi|raw|ABI boundary|ABI boundary (packed layout, round-trip through C)|2-interpreter-python|python3 gcc|python3 abi_test.py|2|python3 and gcc required'
'unit|raw|Unit tests|Unit tests (lexer + parser + golden master)|.|python3|python3 "$ROOT/tests/test_lexer.py" && python3 "$ROOT/tests/test_parser.py" && python3 "$ROOT/tests/golden.py"|2|'
'teach|py|Teaching|Python — teaching layer (Code for Dummies)|2-interpreter-python|python3|teach_test.py|2|'
'2a|py|Pipeline|Python — pipeline (lexer, parser, AST, semantic)|2-interpreter-python|python3|syntax_test.py|2|'
'2b|py|Abstraction|Python — abstraction (functions, recursion)|2-interpreter-python|python3|abstract_test.py|2|'
'2c|py|Vowels|Python — vowel operators (I O U, synthesis)|2-interpreter-python|python3|vowels_test.py|2|'
'2d|py|Notebook|Python — notebook batch (13 cells)|2-interpreter-python|python3|notebook.py|6|'
'3|raw|Layer 3 (Ruby)|Ruby — the DSL|3-dsl-ruby|ruby|ruby ever.rb|2|ruby not found (macOS: brew install ruby)'
'4|py|Layer 4 (SQL)|SQL — the archive|4-archive-sql|python3|archive_test.py|2|'
'r|raw|Research|Research team|.|python3|python3 research.py|22|'
)

run_suite(){
  local row="$1"; shift
  local key kind name header dir req payload tail msg
  IFS='|' read -r key kind name header dir req payload tail msg <<<"$row"
  if [ $# -gt 0 ]; then
    local f m=1
    for f in "$@"; do case "$key" in "$f"*) m=0 ;; esac; done
    [ "$m" -eq 1 ] && return 0
  fi
  echo; echo "[$key] $header"
  case "$kind" in
    py) if require_ok python3; then run_py_test "$dir" "$payload" "$name" "$tail"
        else skip "$name" "${msg:-python3 not found}"; fi ;;
    c)  if require_ok gcc; then
          local src out art; IFS=':' read -r src out art <<<"$payload"
          run_c_test "$name" "$dir" "$src" "$out" "$art" "$tail"
        else skip "$name" "gcc not found"; fi ;;
    *)  if require_ok $req; then run_raw_test "$name" "$dir" "$payload" "$tail"
        else skip "$name" "${msg:-$req required}"; fi ;;
  esac
}

finish(){
  echo; echo "════════════════"
  echo "SUMMARY"; echo "════════"
  if [ "${#N[@]}" -gt 0 ]; then
    local n; for n in "${N[@]}"; do printf '  %s\n' "$n"; done
  fi
  printf '\n  verified %d   skipped %d   failed %d\n\n' "$P" "$S" "$F"
  [ "$F" -gt 0 ] && return 1
  return 0
}

main(){
  echo; echo "════════════════"
  echo "EVER / TAPESTRY"; echo "Codric Enterprise"
  echo "════════════════════════════════════════"
  local row
  for row in "${SUITES[@]}"; do run_suite "$row" "$@"; done
  finish
}

if [ "${RUNNER_LIB:-0}" = "1" ]; then
  return 0 2>/dev/null || true
fi
main "$@"
