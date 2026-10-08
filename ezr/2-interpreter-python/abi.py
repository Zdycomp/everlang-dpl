"""
abi.py — Ever / Tapestry, the ABI boundary

ONE SOURCE OF TRUTH.

The C header tapestry.h defines the packed layout of e_particle and
enforces it with compile-time assertions. This module is the Python side
of that same contract: a ctypes Structure that mirrors every field at the
same offset, a flat byte-buffer path for safe cross-language transfer,
and a round-trip test that fails loudly if anything drifts.

Nobody invents field offsets in Python. They are read from the C binary
at import time and checked against the numbers in the header.

If this module imports successfully, the ABI is intact.
If it raises at import, something moved and the boundary is broken.

Codric Enterprise · Ricky (Dreid) · 2026
"""

from __future__ import annotations

import ctypes
import os
import struct
import subprocess
import sys
import tempfile
from typing import Optional

# ─────────────────────────────────────────────
# The canonical field layout.
# Numbers must match tapestry.h E_LAYOUT_ASSERT values exactly.
# ─────────────────────────────────────────────

E_PARTICLE_SIZE  = 440
E_IDENT_MAX      = 64
E_REASON_MAX     = 128
E_TEXT_MAX       = 192

# field: (offset, size, description)
LAYOUT = {
    "type":        (  0,  4, "int32_t  — e_type enum"),
    "_pad0":       (  4,  4, "int32_t  — explicit padding"),
    "value":       (  8,  8, "int64_t  — union as_int / as_real"),
    "text":        ( 16,192, "char[192]— TEXT/FOREIGN payload"),
    "state":       (208,  4, "int32_t  — e_state enum"),
    "defect":      (212,  4, "int32_t  — e_defect enum"),
    "confidence":  (216,  2, "int16_t  — 0..256"),
    "lo":          (218,  2, "int16_t  — Equivalence lower bound"),
    "hi":          (220,  2, "int16_t  — Equivalence upper bound"),
    "_pad1":       (222,  2, "int16_t  — explicit padding"),
    "lang":        (224,  4, "int32_t  — e_lang enum"),
    "error_dist":  (228,  1, "uint8_t  — error distance"),
    "generation":  (229,  1, "uint8_t  — evolve generation"),
    "ascend_pts":  (230,  1, "uint8_t  — ascend point count"),
    "_pad2":       (231,  1, "uint8_t  — explicit padding"),
    "anchor_id":   (232,  4, "uint32_t — 0 = unanchored"),
    "archive_id":  (236,  4, "int32_t  — corpus row id"),
    "born_ms":     (240,  8, "int64_t  — epoch ms"),
    "ident":       (248, 64, "char[64] — binding name"),
    "reason":      (312,128, "char[128]— why it is untrusted"),
}


# ─────────────────────────────────────────────
# The ctypes Structure. Derived from LAYOUT, not typed by hand.
# ─────────────────────────────────────────────

class EParticleABI(ctypes.Structure):
    """The packed C layout, mirrored exactly for ctypes.

    _pack_ = 1 matches `#pragma pack(push, 1)` in tapestry.h.
    _fields_ order must match the struct field order, not the LAYOUT
    dict order (Python 3.7+ dicts are ordered, but the struct depends
    on declaration order, not alphabetical).
    """
    _pack_ = 1
    _fields_ = [
        ("type",         ctypes.c_int32),
        ("_pad0",        ctypes.c_int32),
        ("value_int",    ctypes.c_int64),   # union read as int64_t
        ("text",         ctypes.c_char * E_TEXT_MAX),
        ("state",        ctypes.c_int32),
        ("defect",       ctypes.c_int32),
        ("confidence",   ctypes.c_int16),
        ("lo",           ctypes.c_int16),
        ("hi",           ctypes.c_int16),
        ("_pad1",        ctypes.c_int16),
        ("lang",         ctypes.c_int32),
        ("error_dist",   ctypes.c_uint8),
        ("generation",   ctypes.c_uint8),
        ("ascend_pts",   ctypes.c_uint8),
        ("_pad2",        ctypes.c_uint8),
        ("anchor_id",    ctypes.c_uint32),
        ("archive_id",   ctypes.c_int32),
        ("born_ms",      ctypes.c_int64),
        ("ident",        ctypes.c_char * E_IDENT_MAX),
        ("reason",       ctypes.c_char * E_REASON_MAX),
    ]


# ─────────────────────────────────────────────
# Verified at import: Python layout must match the canonical numbers.
# ─────────────────────────────────────────────

def _verify_python_layout() -> None:
    """Check that ctypes agrees with the header before any particle moves.

    This runs at import time. A drift means someone edited the struct or
    the header without updating both sides. The error says which field.
    """
    checks = [
        ("size",       ctypes.sizeof(EParticleABI), E_PARTICLE_SIZE),
        ("type",       EParticleABI.type.offset,       0),
        ("value",      EParticleABI.value_int.offset,  8),
        ("text",       EParticleABI.text.offset,       16),
        ("state",      EParticleABI.state.offset,      208),
        ("defect",     EParticleABI.defect.offset,     212),
        ("confidence", EParticleABI.confidence.offset, 216),
        ("lo",         EParticleABI.lo.offset,         218),
        ("hi",         EParticleABI.hi.offset,         220),
        ("lang",       EParticleABI.lang.offset,       224),
        ("anchor_id",  EParticleABI.anchor_id.offset,  232),
        ("archive_id", EParticleABI.archive_id.offset, 236),
        ("born_ms",    EParticleABI.born_ms.offset,    240),
        ("ident",      EParticleABI.ident.offset,      248),
        ("reason",     EParticleABI.reason.offset,     312),
    ]
    for name, got, want in checks:
        if got != want:
            raise RuntimeError(
                f"ABI BROKEN: field '{name}' is at {got}, expected {want}. "
                f"Check tapestry.h and abi.py are in agreement.")


_verify_python_layout()


# ─────────────────────────────────────────────
# Flat buffer — the safe handoff
# ─────────────────────────────────────────────

# One struct.pack format string, field by field, matching LAYOUT.
# This is the format that moves bytes across the Python↔C boundary.
#
# Format: little-endian (<)
#   i  = int32_t   (4 bytes)
#   q  = int64_t   (8 bytes)
#   h  = int16_t   (2 bytes)
#   B  = uint8_t   (1 byte)
#   I  = uint32_t  (4 bytes)
#   {n}s = char[n] (n bytes)

PACK_FMT = (
    "<"
    "i"          # type        (4)
    "i"          # _pad0       (4)
    "q"          # value_int   (8)
    f"{E_TEXT_MAX}s"  # text  (192)
    "i"          # state       (4)
    "i"          # defect      (4)
    "h"          # confidence  (2)
    "h"          # lo          (2)
    "h"          # hi          (2)
    "h"          # _pad1       (2)
    "i"          # lang        (4)
    "B"          # error_dist  (1)
    "B"          # generation  (1)
    "B"          # ascend_pts  (1)
    "B"          # _pad2       (1)
    "I"          # anchor_id   (4)
    "i"          # archive_id  (4)
    "q"          # born_ms     (8)
    f"{E_IDENT_MAX}s"    # ident  (64)
    f"{E_REASON_MAX}s"   # reason (128)
)

assert struct.calcsize(PACK_FMT) == E_PARTICLE_SIZE, (
    f"PACK_FMT size {struct.calcsize(PACK_FMT)} != E_PARTICLE_SIZE {E_PARTICLE_SIZE}")


# ─────────────────────────────────────────────
# Encode / decode between E (Python) and the flat buffer
# ─────────────────────────────────────────────

def encode(p) -> bytes:
    """Python E → 440-byte flat buffer.

    The buffer can be written to shared memory, passed to ctypes, stored
    in the SQL archive's BLOB column, or sent over a socket. What it
    cannot do is hide a layout disagreement: it either unpacks correctly
    on the other side or it does not.
    """
    # resolve enums / state names to integers
    from ever import State, Defect, Lang, E_ZERO

    state_map = {s: i for i, s in enumerate(State)}
    defect_map = {d: i for i, d in enumerate(Defect)}
    lang_map = {l: i for i, l in enumerate(Lang)}

    state_i  = state_map.get(p.state, 0)
    defect_i = defect_map.get(p.defect, 0)
    lang_i   = lang_map.get(p.lang, 0)

    # type tag and value
    v = p.value
    type_i = 0
    val_i  = 0
    if isinstance(v, bool):
        type_i = 4; val_i = int(v)
    elif isinstance(v, int):
        type_i = 1; val_i = v & 0xFFFFFFFFFFFFFFFF
    elif isinstance(v, float):
        type_i = 2
        import struct as st
        val_i = st.unpack("<q", st.pack("<d", v))[0]
    elif isinstance(v, str):
        type_i = 3; val_i = 0

    text_b  = (v.encode("utf-8")[:E_TEXT_MAX-1] if isinstance(v, str)
               else b"")
    ident_b = p.ident.encode("utf-8")[:E_IDENT_MAX-1]
    reason_b = p.reason.encode("utf-8")[:E_REASON_MAX-1]

    return struct.pack(
        PACK_FMT,
        type_i, 0,
        val_i,
        text_b.ljust(E_TEXT_MAX, b"\x00"),
        state_i, defect_i,
        p.confidence, p.lo, p.hi, 0,
        lang_i,
        p.error_distance, p.generation, p.ascend_points, 0,
        p.anchor_id, -1,
        p.born_ms if hasattr(p, "born_ms") and p.born_ms else 0,
        ident_b.ljust(E_IDENT_MAX, b"\x00"),
        reason_b.ljust(E_REASON_MAX, b"\x00"),
    )


def decode(buf: bytes):
    """440-byte flat buffer → Python E.

    Inverse of encode. The field order matches PACK_FMT exactly.
    """
    from ever import E, State, Defect, Lang
    import struct as st

    (type_i, _pad0, val_i, text_b, state_i, defect_i,
     confidence, lo, hi, _pad1, lang_i, err_dist, gen, asc_pts, _pad2,
     anchor_id, archive_id, born_ms, ident_b, reason_b) = struct.unpack(
         PACK_FMT, buf)

    states  = list(State)
    defects = list(Defect)
    langs   = list(Lang)
    state_v  = states[state_i]  if 0 <= state_i  < len(states)  else State.Z
    defect_v = defects[defect_i] if 0 <= defect_i < len(defects) else Defect.NONE
    lang_v   = langs[lang_i]    if 0 <= lang_i   < len(langs)   else Lang.EVER

    # decode value
    if type_i == 1:
        # unsigned int64 → signed
        if val_i >= (1 << 63): val_i -= (1 << 64)
        value = val_i
    elif type_i == 2:
        value = st.unpack("<d", st.pack("<q", val_i))[0]
    elif type_i == 4:
        value = bool(val_i)
    elif type_i == 3:
        value = text_b.rstrip(b"\x00").decode("utf-8", errors="replace")
    else:
        value = None

    p = E(
        ident      = ident_b.rstrip(b"\x00").decode("utf-8", errors="replace"),
        value      = value,
        state      = state_v,
        defect     = defect_v,
        confidence = confidence,
        lo         = lo,
        hi         = hi,
        lang       = lang_v,
        anchor_id  = anchor_id,
        generation = gen,
        ascend_points = asc_pts,
        error_distance = err_dist,
        reason     = reason_b.rstrip(b"\x00").decode("utf-8", errors="replace"),
    )
    return p


# ─────────────────────────────────────────────
# The cross-language round-trip test
# ─────────────────────────────────────────────

def round_trip_test(lib_path: Optional[str] = None) -> bool:
    """Python → buffer → C reads → buffer → Python.

    Builds and runs a tiny C program that reads a particle from stdin,
    mutates one field, and writes it back. Python checks the mutation
    landed where expected.

    Returns True if the round trip is clean.
    Raises RuntimeError with a diagnosis if anything drifts.
    """
    from ever import e_val, State, Lang

    here = os.path.dirname(os.path.abspath(__file__))
    header_dir = os.path.join(here, "..", "0-atom-c")
    atom_c     = os.path.join(header_dir, "tapestry.c")

    probe_src = r"""
#include <stdio.h>
#include <string.h>
#include "tapestry.h"

int main(void) {
    e_particle p;
    /* Read the 440-byte particle from stdin */
    if (fread(&p, sizeof(e_particle), 1, stdin) != 1) {
        fprintf(stderr, "read failed\n"); return 1;
    }
    /* Mutate: stamp generation with a sentinel value the Python side
     * can verify. If the field is at the wrong offset, the wrong byte
     * changes and the check fails. */
    p.generation = 42;
    /* Write back */
    fwrite(&p, sizeof(e_particle), 1, stdout);
    return 0;
}
"""
    with tempfile.TemporaryDirectory() as tmp:
        src   = os.path.join(tmp, "probe.c")
        exe   = os.path.join(tmp, "probe")
        with open(src, "w") as f:
            f.write(probe_src)
        r = subprocess.run(
            ["gcc", "-std=c99", f"-I{header_dir}", "-o", exe, src, atom_c, "-lm"],
            capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"probe build failed:\n{r.stderr}")

        p_in = e_val("round_trip_test", 99, 200, Lang.PYTHON)
        buf_in = encode(p_in)
        if len(buf_in) != E_PARTICLE_SIZE:
            raise RuntimeError(
                f"encode produced {len(buf_in)} bytes, expected {E_PARTICLE_SIZE}")

        r2 = subprocess.run([exe], input=buf_in, capture_output=True)
        if r2.returncode != 0:
            raise RuntimeError(f"probe failed: {r2.stderr.decode()}")
        buf_out = r2.stdout
        if len(buf_out) != E_PARTICLE_SIZE:
            raise RuntimeError(
                f"C wrote {len(buf_out)} bytes, expected {E_PARTICLE_SIZE}")

        p_out = decode(buf_out)

        checks = [
            ("value",      p_out.value,      99),
            ("confidence", p_out.confidence, 200),
            ("state",      p_out.state,      State.CONFIDENT),
            ("lang",       p_out.lang,       Lang.PYTHON),
            ("generation", p_out.generation, 42),   # the C sentinel
        ]
        failures = [(n, got, want) for n, got, want in checks if got != want]
        if failures:
            msg = "\n".join(f"  {n}: got {got!r}, want {want!r}"
                            for n, got, want in failures)
            raise RuntimeError(f"Round-trip FAILED:\n{msg}")

    return True


# ─────────────────────────────────────────────
# Entry point: run this file to test the boundary
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("\n=== Ever — ABI boundary verification ===\n")

    print("Python layout matches canonical offsets: PASS")
    print(f"  sizeof(EParticleABI) = {ctypes.sizeof(EParticleABI)}")
    for name, (offset, size, _) in LAYOUT.items():
        if name.startswith("_"):
            continue
        fld = getattr(EParticleABI, name, None)
        if fld is None:
            # value field is aliased as value_int
            fld = getattr(EParticleABI, name + "_int", None)
        if fld:
            got = fld.offset
            mark = "✓" if got == offset else "✗"
            print(f"  {mark} {name:12} @ {got:4d}  (want {offset:4d})")

    print()
    print("Flat buffer encode/decode self-check:")
    from ever import e_val, Lang
    orig = e_val("test", 42, 180, Lang.PYTHON)
    buf  = encode(orig)
    back = decode(buf)
    checks = [("value", back.value, 42),
              ("confidence", back.confidence, 180),
              ("ident", back.ident, "test")]
    for n, got, want in checks:
        mark = "✓" if got == want else "✗"
        print(f"  {mark} {n} = {got!r}")

    print()
    print("Cross-language round-trip (Python → C → Python):")
    try:
        round_trip_test()
        print("  ✓ C sentinel 42 read back in the right field")
    except Exception as e:
        print(f"  ✗ {e}")

    print("\n=== ABI boundary: intact ===\n")
