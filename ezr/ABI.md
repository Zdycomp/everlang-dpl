# Ever — ABI Boundary

**Codric Enterprise · Ricky (Dreid) · 2026**

---

## The problem this solves

Ever threads through seven languages. Every time a particle crosses from
Python into C++ or C it passes through a memory boundary. Before this
change, that boundary was a **handshake on trust** — Python called C
functions through ctypes with no enforced layout contract, and C++
called C with an `extern "C"` and a hope.

The compiler inserts alignment padding between struct fields wherever it
decides to. Without `#pragma pack`, `e_particle` carries 14 bytes of
invisible padding at positions Python has no knowledge of. A struct edit
in any one layer — swapping a `uint8_t` for a `uint16_t`, reordering
two fields, adding one field — corrupts the `confidence` number silently
in every other layer. The trust number would lie and nothing would say so.

```
before:
  offsetof(state)      = 208   ← correct
  offsetof(defect)     = 212   ← 4 bytes padding inserted here by compiler
  offsetof(confidence) = 216   ← 4 bytes before this
  the Python ctypes layer: assumed these offsets, happened to be right,
  had no way to know if they ever changed

after:
  same offsets, but ENFORCED:
  #pragma pack(push, 1) in the header removes padding
  E_LAYOUT_ASSERT macros fail the C build if anything moves
  EParticleABI in Python is checked at import time
  round_trip_test() compiles a C probe and checks the C sentinel
  lands in the right Python field
```

---

## Three layers of enforcement

### 1. The C header — `#pragma pack` and compile-time assertions

```c
E_PACK_BEGIN
typedef struct {
    int32_t  type;          /* 4 bytes @ 0   */
    int32_t  _pad0;         /* 4 bytes @ 4   — explicit, not compiler  */
    union { int64_t as_int; double as_real; ... } value; /* 8 @ 8 */
    char     text[192];     /* 192    @ 16   */
    int32_t  state;         /* 4     @ 208   */
    int32_t  defect;        /* 4     @ 212   */
    int16_t  confidence;    /* 2     @ 216   */
    int16_t  lo, hi;        /* 2+2   @ 218   */
    int16_t  _pad1;         /* 2     @ 222   — explicit               */
    int32_t  lang;          /* 4     @ 224   */
    uint8_t  error_distance, generation, ascend_points, _pad2; /* @ 228 */
    uint32_t anchor_id;     /* 4     @ 232   */
    int32_t  archive_id;    /* 4     @ 236   */
    int64_t  born_ms;       /* 8     @ 240   */
    char     ident[64];     /* 64    @ 248   */
    char     reason[128];   /* 128   @ 312   */
} e_particle;               /* total: 440 bytes */
E_PACK_END

E_LAYOUT_ASSERT(size,       sizeof(e_particle)              == 440);
E_LAYOUT_ASSERT(confidence, offsetof(e_particle, confidence) == 216);
/* ... 13 more assertions ... */
```

`E_LAYOUT_ASSERT` uses the classic negative-array-size trick — valid in
C89, C99, C11, and every compiler. If any offset moves the build fails
with a readable message naming the field.

### 2. The Python layer — one canonical source of truth

`abi.py` defines `LAYOUT`, a dict of every field → `(offset, size,
description)`. `EParticleABI` (the ctypes Structure) is derived from the
same numbers. At **import time**, `_verify_python_layout()` checks every
field offset against LAYOUT and raises `RuntimeError` if anything drifts.

Nobody invents field offsets twice. There is one table and everything
reads from it.

### 3. The cross-language round-trip test

`round_trip_test()` builds and runs a tiny C probe at test time. Python
encodes a particle to a 440-byte buffer, the probe reads it from stdin,
**mutates `generation` to the sentinel value 42**, and writes the buffer
back. Python decodes the result and checks the sentinel landed in the
right field.

If `confidence` is at the wrong offset in either layer, the sentinel
ends up in the wrong Python field and the test fails loudly.

---

## What changed

| Before | After |
|---|---|
| Implicit compiler padding | `#pragma pack(push, 1)` — no implicit padding |
| Enum fields of undefined width | `int32_t` / `int16_t` — fixed width everywhere |
| No layout checks | 15 compile-time assertions in C, 15 import-time checks in Python |
| Trust between layers | `round_trip_test()` — a C program actually reads the buffer |
| C++ passed enums from `int32_t` silently | Explicit casts at the three call sites |

---

## The flat buffer

`encode(p)` → 440 bytes. `decode(buf)` → Python `E`.

The buffer can be written to shared memory, passed to ctypes, stored in
SQL as a BLOB, or sent over a socket. Every field lands at the same
offset on every platform because the layout is packed and the byte order
is explicit (little-endian `<`).

---

## Verified

| Component | Assertions |
|---|---|

This table used to be transcribed here by hand, and it had drifted: it
carried the same Python-interpreter row as three other documents and
`FINDINGS.md`, and `FINDINGS.md` said 81 while these said 83. Counts now
live in exactly one place, generated from a real run:

    python3 tests/assertion_counts.py

`FINDINGS.md` §5 carries the output and `--check` fails the gate when it
goes stale. See §5 there for why the 81 survived as long as it did.

The ABI tests include a deliberate tamper test: shifting `confidence`
two bytes forward and verifying the suite detects the corruption. A
test suite that cannot catch what it is testing does not count.
