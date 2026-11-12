#!/usr/bin/env bash
# Self-tests for run.sh: counters, skip/pass/fail, pipefail, finish() exit codes.
set -u
cd "$(dirname "${BASH_SOURCE[0]}")/.."
RUNNER_LIB=1 source ./run.sh

# Sets SCRATCH to a fresh directory the sandbox allows: the system temp directory,
# else build/runner in the project. Exits rather than leave SCRATCH empty, which
# would send cp to /. Call it directly, never as $(scratch_dir): an exit inside a
# command substitution ends only the subshell, and the caller carries on with "".
scratch_dir(){
  local d=""
  d="$(mktemp -d "${TMPDIR:-/tmp}/ever-runner.XXXXXX" 2>/dev/null)" || d=""
  if [ -z "$d" ]; then
    mkdir -p build/runner && d="$(mktemp -d build/runner/run.XXXXXX 2>/dev/null)" || d=""
  fi
  if [ -z "$d" ] || [ ! -d "$d" ]; then
    echo "runner: no scratch directory could be created" >&2
    exit 1
  fi
  SCRATCH="$d"
}

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
scratch_dir; TMP="$SCRATCH"
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

# --- 7. finish() fails a run that only skipped
P=1; F=0; S=1
finish >/dev/null 2>&1; rc=$?
check "finish returns 1 when only skips occurred" "$rc" "1"

# --- 8. real C row: payload parses, gcc builds, binary runs (no fakes)
scratch_dir; CDIR="$SCRATCH"
cp 0-atom-c/tapestry.h 0-atom-c/tapestry.c 0-atom-c/tapestry_test.c "$CDIR/"
P=0; S=0; F=0; N=()
run_suite "0|c|Layer 0 (C)|header|$CDIR|gcc|tapestry.c tapestry_test.c::tapestry_test::tapestry_test|2|" >/dev/null
check "real C row passes through run_suite" "$P" "1"
check "real C row not counted as failed" "$F" "0"
rm -rf "$CDIR"

# --- 9. no scratch directory: the self-test stops before it acts on an empty path.
# A child run with mktemp broken must end at the first scratch_dir, not carry on.
# EVER_RUNNER_CHILD keeps the child from running this section: if scratch_dir ever
# regressed, the child would otherwise spawn a child of its own, without end.
if [ -z "${EVER_RUNNER_CHILD:-}" ]; then
  mkdir -p "$TMP/nomktemp"
  printf '#!/bin/sh\nexit 1\n' > "$TMP/nomktemp/mktemp"; chmod +x "$TMP/nomktemp/mktemp"
  out="$(EVER_RUNNER_CHILD=1 PATH="$TMP/nomktemp:$PATH" bash "${BASH_SOURCE[0]}" 2>&1)"; rc=$?
  check "self-test exits 1 when no scratch directory can be made" "$rc" "1"
  case "$out" in *"no scratch directory could be created"*) said=yes;; *) said=no;; esac
  check "and says why" "$said" "yes"
  case "$out" in *"- pass counted"*) acted=yes;; *) acted=no;; esac
  check "and runs no check that needs the directory" "$acted" "no"
fi

rm -rf "$TMP"
if [ "$failures" -gt 0 ]; then echo "runner self-test: $failures failure(s)"; exit 1; fi
echo "all runner self-tests passed"
exit 0
