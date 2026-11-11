#!/usr/bin/env bash
# Runs the JVM test suites N times under fixed conditions and checks that every run
# has the same outcome digest (see tools/outcome_digest.py).
#
#   tools/determinism_check.sh            # 3 runs, --offline (needs a warm Gradle cache)
#   tools/determinism_check.sh 5          # 5 runs
#   tools/determinism_check.sh 3 online   # allow network resolution
#
# Fixed conditions: LC_ALL=C, TZ=UTC, PYTHONHASHSEED=0, no Gradle daemon, test outputs
# cleaned before every run, and every run serialised through .gradle/build.lock.
#
# Exit: 0 = deterministic and green, 1 = runs disagree, 2 = deterministic but red.
set -u
cd "$(dirname "$0")/.." || exit 1
export LC_ALL=C TZ=UTC PYTHONHASHSEED=0

RUNS="${1:-3}"
ARGS=(--no-daemon --console=plain)
[ "${2:-}" = "online" ] || ARGS+=(--offline)
TASKS=(:core:cleanTest :core:test :predict:cleanTest :predict:test :fuzz:cleanTest :fuzz:test)

mkdir -p .gradle
first=""
same=1
green=1
for r in $(seq 1 "$RUNS"); do
  log=".gradle/determinism-run$r.log"
  flock .gradle/build.lock ./gradlew "${ARGS[@]}" "${TASKS[@]}" >"$log" 2>&1
  code=$?
  line=$(python3 tools/outcome_digest.py . "$log" "$code")
  echo "run $r: $line  (log: $log)"
  digest="${line%% *}"
  [ -z "$first" ] && first="$digest"
  [ "$digest" = "$first" ] || same=0
  [ "$code" -eq 0 ] || green=0
done

if [ "$same" -ne 1 ]; then
  echo "NON-DETERMINISTIC: runs produced different digests"
  exit 1
fi
if [ "$green" -ne 1 ]; then
  echo "DETERMINISTIC BUT RED: every run failed the same way"
  exit 2
fi
echo "DETERMINISTIC AND GREEN: $RUNS/$RUNS runs, digest $first"
