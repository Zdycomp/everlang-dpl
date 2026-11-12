#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / '2-interpreter-python'))
from parse_lex_executor import ParseLexExecutor
from runtime import run_source

passed = failed = 0

def ok(name, condition):
    global passed, failed
    if condition: passed += 1; print(f"  ✓ {name}")
    else: failed += 1; print(f"  ✗ {name}")

pipeline = ParseLexExecutor()
result = pipeline.run('ever total = 6 * 7\nshow total\n')
ok('lex stage passes', result.stages[0].name == 'lex' and result.stages[0].status == 'passed')
ok('parse stage passes', result.stages[1].name == 'parse' and result.stages[1].status == 'passed')
ok('semantic stage passes', result.stages[2].name == 'semantic' and result.stages[2].status == 'passed')
ok('execute stage passes', result.stages[3].name == 'execute' and result.stages[3].status == 'passed')
ok('output is preserved', result.outputs == ['total = 42 [256/256]'])
ok('all three functions run in one pipeline', result.ok)

bad = pipeline.run('ever broken = 1 +\n')
ok('bad input retains lex stage', bad.stages[0].status == 'passed')
ok('bad input stops at parse', bad.stages[1].status == 'failed' and len(bad.stages) == 2)

for healed in ('ever x = 5\nSHOW x\n', 'ever x = 5;\nshow x\n'):
    via_pipeline = pipeline.run(healed)
    via_front_door = run_source(healed)
    ok(f'pipeline accepts what run_source accepts: {healed.splitlines()[1]!r}',
       via_pipeline.ok == via_front_door.ok and via_pipeline.ok)
    ok('pipeline reports the healing as a recovery', len(via_pipeline.recoveries) >= 1)

print(f"\n=== ParseLexExecutor: {passed} passed, {failed} failed ===\n")
raise SystemExit(0 if failed == 0 else 1)
