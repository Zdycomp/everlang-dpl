#!/usr/bin/env bash
# Self-tests for run.sh: counters, skip/pass/fail, pipefail, finish() exit codes.
set -u
cd "$(dirname "${BASH_SOURCE[0]}")/.."
RUNNER_LIB=1 source ./run.sh

failures=0
check(){
  local desc="$1" got="$2" want="$3"
  if [ "$got" = "$want" ]; then echo "  ok - $desc"
  else echo "  FAIL - $desc (got '$got', want '$want')"; failures=$((failures+1)); fi
}

# --- 1. missing tool => skip counted, no pass/fail ---
have(){ return 1; }
P=0; S=0; F=0; N=()
run_suite 'x|py|Fake Py|header|.|python3|nope.py|2|python3 not found' >/dev/null
check "skip counted when python3 missing" "$S" "1"
check "no pass counted" "$P" "0"
check "no fail counted" "$F" "0"

# --- 2. fake python3: passing test increments P
TMP="$(mktemp -d)"
printf '#!/bin/sh\nexit 0\n' > "$TMP/python3"; chmod +x "$TMP/python3"
PATH="$TMP:$PATH"
have(){ command -v "$1" >/dev/null 2>&1; }
P=0; S=0; F=0; N=()
run_suite 'x|py|Fake Py|header|.|python3|nope.py|2|' >/dev/null
check "pass counted" "$P" "1"
check "fail counted" "$F" "0"

# --- 3. failing test increments F
printf '#!/bin/sh\nexit 3\n' > "$TMP/python3"
P=0; S=0; F=0; N=()
run_suite 'x|py|Failing Py|header|.|python3|nope.py|2|' >/dev/null
check "failing test counted" "$F" "1"

# --- 4. pipefail: failure after printed output is still a failure
printf '#!/bin/sh\necho line1\necho line2\nexit 5\n' > "$TMP/python3"
P=0; S=0; F=0; N=()
run_suite 'x|py|PipeFail Py|header|.|python3|nope.py|2|' >/dev/null
check "pipefail propagates test failure" "$F" "1"

# --- 5. finish() exit codes
P=1; F=1; S=0
finish >/dev/null 2>&1; rc=$?
check "finish returns 1 on failures" "$rc" "1"
P=1; F=0; S=0
finish >/dev/null 2>&1; rc=$?
check "finish returns 0 when clean" "$rc" "0"

# --- 6. summary loop guarded against empty N
P=0; F=0; S=0; N=()
finish >/dev/null 2>&1; rc=$?
check "finish safe with empty results array" "$rc" "0"

rm -rf "$TMP"
if [ "$failures" -gt 0 ]; then echo "runner self-test: $failures failure(s)"; exit 1; fi
echo "all runner self-tests passed"
exit 0
