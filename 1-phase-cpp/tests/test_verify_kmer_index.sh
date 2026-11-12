#!/bin/sh
# Contract test for bin/verify_kmer_index: each case checks the exact output
# line (stdout or stderr) and the exit code. Usage: test_verify_kmer_index.sh <binary>
BIN="$1"
if [ -z "$BIN" ] || [ ! -x "$BIN" ]; then
    echo "usage: $0 <path/to/verify_kmer_index>" >&2
    exit 2
fi

FAILED=0
PASSED=0

check() {
    expected_out="$1"
    expected_code="$2"
    shift 2
    actual_out=$("$BIN" "$@" 2>&1)
    actual_code=$?
    if [ "$actual_out" = "$expected_out" ] && [ "$actual_code" -eq "$expected_code" ]; then
        PASSED=$((PASSED + 1))
    else
        FAILED=$((FAILED + 1))
        echo "FAIL: verify_kmer_index $* -> '$actual_out' exit=$actual_code" \
             "(expected '$expected_out' exit=$expected_code)"
    fi
}

check "VALID" 0 11 1 10
check "VALID" 0 11 5 5
check "INVALID:AVG_KMERS_PER_POSITION_OUT_OF_RANGE" 1 11 1 11
check "INVALID:KMER_SIZE_MUST_BE_11" 1 12 1 5
check "INVALID:UNIQUE_KMERS_EMPTY" 1 11 0 5
check "INVALID:TOTAL_KMERS_LT_UNIQUE" 1 11 5 4
check "INVALID:KMER_SIZE_NOT_INTEGER" 1 x 1 5
check "INVALID:UNIQUE_KMERS_NOT_INTEGER" 1 11 1.5 5
check "INVALID:TOTAL_KMERS_NOT_INTEGER" 1 11 1 ""
check "INVALID:USAGE" 2
check "INVALID:USAGE" 2 11 1

echo "verify_kmer_index: $PASSED passed, $FAILED failed"
[ "$FAILED" -eq 0 ]
