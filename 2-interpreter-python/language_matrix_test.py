#!/usr/bin/env python3
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from emit import BACKENDS
from language_matrix import LANGUAGES, ADAPTERS, detect_path, manifest

passed = failed = 0

def ok(name, condition):
    global passed, failed
    if condition: passed += 1; print(f"  ✓ {name}")
    else: failed += 1; print(f"  ✗ {name}")

ok('all requested languages represented', set(LANGUAGES) == set(ADAPTERS))
ok('every language has an adapter role', all(a.role for a in ADAPTERS.values()))
ok('every language has extensions', all(a.extensions for a in ADAPTERS.values()))
native = {a.native_backend for a in ADAPTERS.values() if a.native_backend}
ok('native backends name a real emitter', bool(native) and native <= set(BACKENDS))
ok('Dockerfile detection works', detect_path(Path('Dockerfile')).name == 'Dockerfile')
ok('TypeScript detection works', detect_path(Path('app.ts')).name == 'TypeScript')
ok('manifest is JSON serializable', json.dumps(list(manifest())))
print(f"\n=== Language matrix: {passed} passed, {failed} failed ===\n")
raise SystemExit(0 if failed == 0 else 1)
