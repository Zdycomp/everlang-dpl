#!/usr/bin/env bash
# Compile the EZR Java runtime. No build tool, no dependencies — the other
# layers build with a single compiler invocation too, and layer 5 has no
# reason to be the one that needs Maven.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p out
env -u JAVA_TOOL_OPTIONS javac -Xlint:all -d out com/codric/ezr/*.java
echo "built: $(ls out/com/codric/ezr/*.class | wc -l | tr -d ' ') classes in out/"
