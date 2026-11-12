#!/usr/bin/env python3
"""abi_test.py — Ever / Tapestry, ABI boundary verification suite.

If any test in this file fails, a field moved between layers and data
will corrupt silently. Fix the struct before committing.
"""

import ctypes
import struct

from abi import (
    EParticleABI, LAYOUT, PACK_FMT,
    E_PARTICLE_SIZE, E_IDENT_MAX, E_REASON_MAX, E_TEXT_MAX,
    encode, decode, round_trip_test,
)
from ever import e_val, e_z, e_equiv, a_anchor, State, Defect, Lang

passed = failed = 0


def ok(name, cond):
    global passed, failed
    if cond:
        passed += 1; print(f"  \u2713 {name}")
    else:
        failed += 1; print(f"  \u2717 {name}")


print("\n=== Ever \u2014 ABI boundary ===\n")

print("The layout contract")
ok("sizeof(EParticleABI) == 440",
   ctypes.sizeof(EParticleABI) == E_PARTICLE_SIZE)
ok("_pack_ = 1 enforced",
   EParticleABI._pack_ == 1)
ok("PACK_FMT matches the size",
   struct.calcsize(PACK_FMT) == E_PARTICLE_SIZE)

print("\nEvery canonical offset is honoured in Python")
field_map = {
    "type":       EParticleABI.type,
    "value":      EParticleABI.value_int,
    "text":       EParticleABI.text,
    "state":      EParticleABI.state,
    "defect":     EParticleABI.defect,
    "confidence": EParticleABI.confidence,
    "lo":         EParticleABI.lo,
    "hi":         EParticleABI.hi,
    "lang":       EParticleABI.lang,
    "anchor_id":  EParticleABI.anchor_id,
    "archive_id": EParticleABI.archive_id,
    "born_ms":    EParticleABI.born_ms,
    "ident":      EParticleABI.ident,
    "reason":     EParticleABI.reason,
}
for fname, (want_off, want_sz, _) in LAYOUT.items():
    if fname.startswith("_"):
        continue
    fld = field_map.get(fname)
    if fld is None:
        continue
    ok(f"{fname:12} @ {want_off:4d}", fld.offset == want_off)

print("\nExplicit padding is visible and zero")
# verify padding bytes in a freshly encoded buffer are zero
p = e_val("pad_test", 1, 200, Lang.C)
buf = encode(p)
ok("_pad0 bytes (4..7) are zero",    all(b == 0 for b in buf[4:8]))
ok("_pad1 bytes (222..223) are zero", all(b == 0 for b in buf[222:224]))
ok("_pad2 byte  (231) is zero",       buf[231] == 0)

print("\nEncode/decode round trip — every field")
orig = e_val("rt_test", 77, 210, Lang.PYTHON)
buf  = encode(orig)
back = decode(buf)
ok("value preserved",      back.value == 77)
ok("confidence preserved", back.confidence == 210)
ok("state preserved",      back.state == State.CONFIDENT)
ok("lang preserved",       back.lang == Lang.PYTHON)
ok("ident preserved",      back.ident == "rt_test")

orig2 = e_z("z_test", "unverified")
buf2  = encode(orig2)
back2 = decode(buf2)
ok("Z state preserved",    back2.state == State.Z)
ok("Z reason preserved",   back2.reason == "unverified")

eq = e_equiv("eq_test", 100, 180, Lang.SQL)
bufeq = encode(eq)
backeq = decode(bufeq)
ok("Equivalence lo preserved", backeq.lo == 100)
ok("Equivalence hi preserved", backeq.hi == 180)

# float round-trip
import math
fv = e_val("pi_test", math.pi, 150, Lang.PYTHON)
buf_f = encode(fv); back_f = decode(buf_f)
ok("float round-trip",    abs(back_f.value - math.pi) < 1e-9)

# bool round-trip
bv = e_val("bool_test", True, 200, Lang.PYTHON)
buf_b = encode(bv); back_b = decode(buf_b)
ok("bool True preserved",  back_b.value == True)
bv2 = e_val("bool2",  False, 200, Lang.PYTHON)
ok("bool False preserved", decode(encode(bv2)).value == False)

# text round-trip
tv = e_val("txt_test", "Codric", 180, Lang.PYTHON)
buf_t = encode(tv); back_t = decode(buf_t)
ok("text preserved",       back_t.value == "Codric")

# anchor round-trip
anc = a_anchor(e_val("anc_test", 500, 220, Lang.PYTHON), 7001)
buf_a = encode(anc); back_a = decode(buf_a)
ok("anchor_id preserved",  back_a.anchor_id == 7001)

# long ident truncated cleanly, not corrupted
long_name = "x" * 100
lp = e_val(long_name, 1, 200, Lang.PYTHON)
buf_l = encode(lp); back_l = decode(buf_l)
ok("ident truncated to E_IDENT_MAX-1",  len(back_l.ident) <= E_IDENT_MAX)
ok("ident not corrupted",               back_l.ident.startswith("x"))

print("\nBuffer is exactly the right size")
for p_i in [orig, orig2, eq, fv, bv, tv]:
    buf_i = encode(p_i)
    ok(f"encode({p_i.ident!r}) == {E_PARTICLE_SIZE}",
       len(buf_i) == E_PARTICLE_SIZE)

print("\nCross-language: Python \u2192 C \u2192 Python")
try:
    ok("round-trip through C", round_trip_test())
except Exception as exc:
    ok(f"round-trip through C: {exc}", False)

print("\nThe failure mode: prove it fails when the layout drifts")
# tamper with a buffer: move confidence two bytes forward
p_good = e_val("tamper", 42, 200, Lang.PYTHON)
buf_good = bytearray(encode(p_good))
# zero out the real confidence and write it two bytes later
buf_good[216] = 0; buf_good[217] = 0   # wipe real field
buf_good[218] = 200 & 0xFF             # write into lo
buf_bad = bytes(buf_good)
back_bad = decode(buf_bad)
ok("tampered buffer produces wrong confidence",
   back_bad.confidence != 200)
ok("tampered buffer shows the drift",
   back_bad.confidence == 0)
ok("tampered buffer shifts the value into lo",
   back_bad.lo != 0)

print("\nSigned int64: value_int is packed 'q', so the whole range must fit")
# Every negative integer used to raise struct.error out of encode():
# the int branch masked to UNSIGNED 64-bit and handed the result to a
# SIGNED 'q' field, so -1 arrived as 2**64-1. Nothing in this file had
# ever encoded a negative number, which is exactly why it shipped.
for _v in (-1, -2, -42, -1000, -(2 ** 31), -(2 ** 62)):
    try:
        ok(f"negative int {_v} round-trips", decode(encode(
            e_val("neg", _v, 200, Lang.PYTHON))).value == _v)
    except Exception as _exc:
        ok(f"negative int {_v} round-trips ({type(_exc).__name__})", False)
ok("INT64_MIN round-trips",
   decode(encode(e_val("min", -(2 ** 63), 200, Lang.PYTHON))).value == -(2 ** 63))
ok("INT64_MAX round-trips",
   decode(encode(e_val("max", 2 ** 63 - 1, 200, Lang.PYTHON))).value == 2 ** 63 - 1)

print("\nborn_ms survives the boundary")
# decode() unpacked born_ms and then never passed it to E(), so every
# decoded particle was re-stamped with the decode time: provenance lost,
# and encode(decode(x)) != encode(x).
_prov = e_val("prov", 42, 200, Lang.PYTHON)
ok("born_ms preserved through the ABI", decode(encode(_prov)).born_ms == _prov.born_ms)
ok("encode is idempotent across a decode",
   encode(decode(encode(_prov))) == encode(_prov))

print("\nText fields truncate on a CHARACTER boundary, not a byte boundary")
# The limits are in bytes; the unit is a character. Slicing encoded
# UTF-8 at a fixed byte count split the last character in half, and
# decode()'s errors="replace" brought it home as U+FFFD — silent
# corruption, and an unstable round trip. "Extent not delimited" again.
for _label, _particle in (
        ("text",   e_val("t", "\u00e9" * 120, 200, Lang.PYTHON)),
        ("ident",  e_val("\u00e9" * 40, 1, 200, Lang.PYTHON)),
        ("reason", e_z("r", "\u00e9" * 80)),
        ("emoji",  e_val("t", "\U0001F3AF" * 80, 200, Lang.PYTHON)),
):
    _b1 = encode(_particle)
    _q  = decode(_b1)
    _seen = (_q.ident or "") + (_q.reason or "") + (
        _q.value if isinstance(_q.value, str) else "")
    ok(f"{_label}: buffer stays {E_PARTICLE_SIZE} bytes", len(_b1) == E_PARTICLE_SIZE)
    ok(f"{_label}: no U+FFFD introduced", "\ufffd" not in _seen)
    ok(f"{_label}: round trip is stable", encode(_q) == _b1)

print(f"\n=== ABI boundary: {passed} passed, {failed} failed ===\n")
raise SystemExit(0 if failed == 0 else 1)
