#!/bin/bash
# Verify toolchains and baseline tests on session start (web sessions).
set -u
cd "${CLAUDE_PROJECT_DIR:-.}"
for t in python3 g++ javac; do command -v "$t" >/dev/null || echo "missing toolchain: $t"; done
python3 -m pip install -q pyflakes >/dev/null 2>&1 || true
if [ -d everlang_standalone ]; then
  (cd everlang_standalone && python3 -m unittest discover tests 2>&1 | tail -3)
fi
exit 0
