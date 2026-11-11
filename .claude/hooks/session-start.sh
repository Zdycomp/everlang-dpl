#!/bin/bash
# Prepare all four phases so run_all.py and the PostToolUse test gate work in web sessions.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-.}"

for t in python3 g++ make mvn java jq; do
  command -v "$t" >/dev/null || echo "missing toolchain: $t" >&2
done

python3 -m pip install -q pyflakes >/dev/null 2>&1 || echo "pyflakes install failed" >&2

# bin/ is gitignored; without verify_particle the ReinforcedArchive integration tests silently skip.
make -s -C 1-phase-cpp >/dev/null || echo "1-phase-cpp build failed" >&2

# Pre-fetch Maven deps and compile so later mvn runs hit the cached container state.
mvn -q -f 5-runtime-java/pom.xml test-compile >/dev/null 2>&1 || echo "5-runtime-java compile failed" >&2

(cd everlang_standalone && python3 -m unittest discover tests 2>&1 | tail -3)
