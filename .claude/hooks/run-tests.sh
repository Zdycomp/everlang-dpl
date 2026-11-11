#!/bin/bash
# PostToolUse(Write|Edit): run the test gate when a Python file under everlang_standalone/ changes.
set -u
f=$(jq -r '.tool_response.filePath // .tool_input.file_path // empty')
case "$f" in
  */everlang_standalone/*.py) ;;
  *) exit 0 ;;
esac
cd "${CLAUDE_PROJECT_DIR:-.}/everlang_standalone" || exit 0
out=$(python3 -m unittest discover tests 2>&1; python3 -m pyflakes "$f" 2>&1)
if echo "$out" | grep -qE 'FAILED|Error|error|imported but unused|undefined name'; then
  jq -n --arg r "Test gate failed after editing $f:
$out" '{decision:"block", reason:$r}'
fi
exit 0
