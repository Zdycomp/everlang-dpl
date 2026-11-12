#!/usr/bin/env python3
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / '2-interpreter-python'))
from verification_oracle import verify

#: run_all.py's convention: exit 77 means the toolchain is absent and nothing was checked.
SKIP_EXIT = 77

passed = failed = 0


def ok(name, condition):
    global passed, failed
    if condition: passed += 1; print(f"  ✓ {name}")
    else: failed += 1; print(f"  ✗ {name}")


source = 'ever total = 6 * 7\nshow total\n'

go = verify(source, 'go')
ok('Go oracle passes when go is installed',
   go.status == ('PASS' if shutil.which('go') else 'UNAVAILABLE'))
rust = verify(source, 'rust')
ok('Rust oracle passes when rustc is installed',
   rust.status == ('PASS' if shutil.which('rustc') else 'UNAVAILABLE'))
ok('a program the reference rejects is INVALID_SOURCE, not a target bug',
   verify('show nope\n', 'js').status == 'INVALID_SOURCE')

if shutil.which('node') is None:
    print(f"\nSKIP: node is not on PATH, so the JavaScript oracle cannot run")
    print(f"\n=== Verification oracle: {passed} passed, {failed} failed ===\n")
    raise SystemExit(1 if failed else SKIP_EXIT)

js = verify(source, 'js')
ok('JavaScript oracle passes', js.status == 'PASS')
ok('a target that outlives its timeout is TIMEOUT, not an exception',
   verify(source, 'js', timeout=0).status == 'TIMEOUT')

print(f"\n=== Verification oracle: {passed} passed, {failed} failed ===\n")
raise SystemExit(0 if failed == 0 else 1)
