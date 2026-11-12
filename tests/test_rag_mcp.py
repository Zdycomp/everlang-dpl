#!/usr/bin/env python3
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / '2-interpreter-python'))
from rag_index import build, search


def main():
    passed = failed = 0

    def ok(name, condition):
        nonlocal passed, failed
        if condition:
            passed += 1; print(f'  ✓ {name}')
        else:
            failed += 1; print(f'  ✗ {name}')

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory) / 'repo'; root.mkdir()
        (root / 'main.py').write_text('def repair_failure():\n    return "archive"\n')
        (root / 'notes.md').write_text('MCP and RAG repair archive\n')
        db = Path(directory) / 'index.sqlite'
        counts = build(root, db)
        ok('RAG indexes source and docs', counts['files'] == 2 and counts['chunks'] == 2)
        hits = search(db, 'repair')
        ok('RAG retrieves indexed evidence', len(hits) == 2)

        proc = subprocess.Popen(
            [sys.executable, '2-interpreter-python/mcp_server.py'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        messages = [
            {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {}},
            {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list', 'params': {}},
        ]
        for message in messages:
            proc.stdin.write(json.dumps(message) + '\n')
        proc.stdin.close()
        output = [json.loads(line) for line in proc.stdout]
        proc.wait()
        ok('MCP initialize responds', output[0]['result']['serverInfo']['name'] == 'ever-rag')
        ok('MCP exposes read-only search tool', any(
            tool['name'] == 'search_repository' for tool in output[1]['result']['tools']))

    print(f'\n=== RAG/MCP: {passed} passed, {failed} failed ===\n')
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
