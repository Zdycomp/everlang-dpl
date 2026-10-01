# 1-phase-cpp — C++ Analysis / Safety Verification

## Purpose

`verify_particle` is a native CLI **pre-write safety gate**. Before the
Python-side self-healing Archive (`everlang_standalone/core/archive.py`)
persists a write into the SQL archive (`4-archive-sql/tapestry.db`, once
that phase exists), it shells out to this binary to verify that a
particle's `confidence` and `value` are well-formed. This reinforces the
Archive's data integrity with an explicit, memory-safe, compile-time-checked
gate outside the Python interpreter.

This binary is a pure validator: it never mutates state, never touches the
archive itself, and communicates only via argv, stdin, stdout, and its exit
code, per the contract below. Other phases (Python, and eventually Java)
depend on this contract **verbatim** — the exact strings and exit codes must
not change without updating all callers.

## CLI contract (verbatim)

```
verify_particle <confidence>
```

- Exactly one argv: `<confidence>`, the confidence value as text.
- The particle's `value` is supplied entirely on **stdin**, read to EOF.

Validation is performed in this order; the first failure wins:

| # | Check | stdout | exit code |
|---|-------|--------|-----------|
| 1 | `argc != 2` | `INVALID:USAGE` | 2 |
| 2 | confidence argument does not parse as a base-10 integer using the *entire* string (no leading/trailing whitespace, no trailing garbage) | `INVALID:CONFIDENCE_NOT_INTEGER` | 1 |
| 3 | parsed confidence not in `[0, 256]` inclusive | `INVALID:CONFIDENCE_OUT_OF_RANGE` | 1 |
| 4 | stdin has 0 bytes total | `INVALID:VALUE_EMPTY` | 1 |
| 5 | stdin has more than 4096 bytes available | `INVALID:VALUE_TOO_LONG` | 1 |
| 6 | otherwise | `VALID` | 0 |

Each stdout message is followed by a trailing newline.

### Examples

```bash
$ echo -n "Alpha" | ./bin/verify_particle 200
VALID                # exit 0

$ echo -n "x" | ./bin/verify_particle -1
INVALID:CONFIDENCE_OUT_OF_RANGE   # exit 1

$ echo -n "x" | ./bin/verify_particle abc
INVALID:CONFIDENCE_NOT_INTEGER    # exit 1

$ ./bin/verify_particle
INVALID:USAGE                     # exit 2
```

## Memory safety

- No dynamic allocation beyond a single fixed-size 4097-byte stack buffer
  (4096 data bytes + 1 sentinel byte used to detect stdin overflow beyond
  the 4096-byte limit).
- Every `read()` call's return value is checked explicitly; no unbounded
  loops (the stdin read loop is bounded by the fixed buffer capacity).
- No `sprintf`, `strcpy`, or `gets`.
- Integer parsing uses `strtol` with full-string validation via `endptr`
  (rejects partial parses, empty input, and out-of-range values via
  `errno == ERANGE`).

## Build

```bash
cd 1-phase-cpp
make
```

Builds `bin/verify_particle` from `src/verify_particle.cpp` with
`g++ -std=c++17 -Wall -Wextra -Werror -O2`.

## Test

```bash
cd 1-phase-cpp
make test
```

Builds `bin/verify_particle` and `tests/test_verify_particle` (a standalone
test program with its own `main()`, no external test framework), runs the
test binary, and fails the `make` invocation if any test case fails. The
test program invokes the built binary via `popen`, feeding stdin through the
pipe and capturing stdout, and asserts stdout content and exit code for each
contract case (including the 4096/4097-byte boundary and the `argc`
mismatch cases).

## Sanitizer build

```bash
cd 1-phase-cpp
make asan
```

Builds `bin/verify_particle_asan` from the same source with
`-std=c++17 -Wall -Wextra -g -O0 -fsanitize=address,undefined`, for manual
or CI sanitizer runs, e.g.:

```bash
echo -n "Alpha" | ./bin/verify_particle_asan 200
```
