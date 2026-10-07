"""
evalue.py — Ever / Tapestry, Python-side unified variant type

The same type system as evalue.h, expressed in Python.
A Python EValue maps 1-to-1 with the C EValue struct, so the same
value is representable identically in Python, C++, and C without
conversion loss at any boundary.

    SCALAR (inline):  Void, Bool, Int, Real, Text
    COMPOSITE (pool): Blob, List, Record

Every composite lifter produces the same record shape as its C
counterpart, so a SQL row lifted in Python is the same structure as one
lifted in C, and either can be serialised through the ABI layer and
decoded by the other side.

Codric Enterprise · Ricky (Dreid) · 2026
"""

from __future__ import annotations

import math
import re
import struct
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Dict, Iterator, List, Optional, Union


# ─────────────────────────────────────────────
# Type tags — must match ev_type in evalue.h
# ─────────────────────────────────────────────

class EvType(IntEnum):
    VOID   = 0
    BOOL   = 1
    INT    = 2
    REAL   = 3
    TEXT   = 4
    BLOB   = 5
    LIST   = 6
    RECORD = 7

EV_INLINE_MAX   = 192
EV_FIELD_NAME   = 64
EV_CERTAIN      = 256


# ─────────────────────────────────────────────
# The variant
# ─────────────────────────────────────────────

@dataclass(frozen=True)
class EValue:
    """Unified variant. Immutable — Ever is pure.

    Scalars carry their value directly.
    Composites carry a Python object (bytes / list / dict).
    The ev_tag drives serialisation and cross-language routing.
    """
    ev_tag:     EvType
    ev_bool:    Optional[bool]           = None
    ev_int:     Optional[int]            = None
    ev_real:    Optional[float]          = None
    ev_text:    Optional[str]            = None
    ev_blob:    Optional[bytes]          = None
    ev_list:    Optional[List["EValue"]] = None
    ev_record:  Optional[Dict[str, "EValue"]] = None
    confidence: int = EV_CERTAIN

    # ── constructors ──

    @classmethod
    def void(cls, conf: int = EV_CERTAIN) -> "EValue":
        return cls(EvType.VOID, confidence=conf)

    @classmethod
    def from_bool(cls, v: bool, conf: int = EV_CERTAIN) -> "EValue":
        return cls(EvType.BOOL, ev_bool=bool(v), confidence=conf)

    @classmethod
    def from_int(cls, v: int, conf: int = EV_CERTAIN) -> "EValue":
        return cls(EvType.INT, ev_int=int(v), confidence=conf)

    @classmethod
    def from_real(cls, v: float, conf: int = EV_CERTAIN) -> "EValue":
        return cls(EvType.REAL, ev_real=float(v), confidence=conf)

    @classmethod
    def from_text(cls, v: str, conf: int = EV_CERTAIN) -> "EValue":
        if len(v) < EV_INLINE_MAX:
            return cls(EvType.TEXT, ev_text=v, confidence=conf)
        return cls(EvType.BLOB, ev_blob=v.encode("utf-8"), confidence=conf)

    @classmethod
    def from_blob(cls, v: bytes, conf: int = EV_CERTAIN) -> "EValue":
        return cls(EvType.BLOB, ev_blob=bytes(v), confidence=conf)

    @classmethod
    def from_list(cls, items: List["EValue"],
                  conf: int = EV_CERTAIN) -> "EValue":
        return cls(EvType.LIST, ev_list=list(items), confidence=conf)

    @classmethod
    def from_record(cls, fields: Dict[str, "EValue"],
                    conf: int = EV_CERTAIN) -> "EValue":
        return cls(EvType.RECORD, ev_record=dict(fields), confidence=conf)

    # ── predicates ──

    @property
    def is_void(self)      -> bool: return self.ev_tag == EvType.VOID
    @property
    def is_scalar(self)    -> bool: return self.ev_tag <= EvType.TEXT
    @property
    def is_composite(self) -> bool: return self.ev_tag >= EvType.BLOB

    @property
    def type_name(self) -> str:
        return self.ev_tag.name.lower()

    # ── equality — mirrors ev_equal in C ──

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, EValue):
            return NotImplemented
        if self.ev_tag != other.ev_tag:
            # INT and REAL interoperate
            if self.ev_tag == EvType.INT and other.ev_tag == EvType.REAL:
                return float(self.ev_int) == other.ev_real
            if self.ev_tag == EvType.REAL and other.ev_tag == EvType.INT:
                return self.ev_real == float(other.ev_int)
            return False
        tag = self.ev_tag
        if tag == EvType.VOID:   return True
        if tag == EvType.BOOL:   return self.ev_bool == other.ev_bool
        if tag == EvType.INT:    return self.ev_int == other.ev_int
        if tag == EvType.REAL:   return math.isclose(self.ev_real,
                                                      other.ev_real, rel_tol=1e-12)
        if tag == EvType.TEXT:   return self.ev_text == other.ev_text
        if tag == EvType.BLOB:   return self.ev_blob == other.ev_blob
        if tag == EvType.LIST:
            if len(self.ev_list) != len(other.ev_list):
                return False
            return all(a == b for a, b in zip(self.ev_list, other.ev_list))
        if tag == EvType.RECORD:
            if set(self.ev_record) != set(other.ev_record):
                return False
            return all(self.ev_record[k] == other.ev_record[k]
                       for k in self.ev_record)
        return False

    def __hash__(self) -> int:
        return hash((self.ev_tag, self.ev_int, self.ev_real,
                     self.ev_text, self.ev_blob,
                     tuple(self.ev_list or []),
                     tuple(sorted((self.ev_record or {}).items()))))

    # ── access ──

    def get(self, key: Union[str, int], default=None) -> Optional["EValue"]:
        """Uniform field/index access regardless of tag."""
        if self.ev_tag == EvType.RECORD:
            return self.ev_record.get(str(key), default)
        if self.ev_tag == EvType.LIST:
            try:
                return self.ev_list[int(key)]
            except (IndexError, TypeError, ValueError):
                return default
        return default

    def __len__(self) -> int:
        if self.ev_tag == EvType.LIST:   return len(self.ev_list)
        if self.ev_tag == EvType.RECORD: return len(self.ev_record)
        if self.ev_tag == EvType.BLOB:   return len(self.ev_blob)
        if self.ev_tag == EvType.TEXT:   return len(self.ev_text or "")
        return 0

    def __iter__(self) -> Iterator["EValue"]:
        if self.ev_tag == EvType.LIST:
            return iter(self.ev_list)
        if self.ev_tag == EvType.RECORD:
            return iter(self.ev_record.values())
        return iter([])

    # ── natural Python value ──

    @property
    def native(self) -> Any:
        """The Python value, without the EValue wrapper."""
        if self.ev_tag == EvType.VOID:   return None
        if self.ev_tag == EvType.BOOL:   return self.ev_bool
        if self.ev_tag == EvType.INT:    return self.ev_int
        if self.ev_tag == EvType.REAL:   return self.ev_real
        if self.ev_tag == EvType.TEXT:   return self.ev_text
        if self.ev_tag == EvType.BLOB:   return self.ev_blob
        if self.ev_tag == EvType.LIST:
            return [item.native for item in self.ev_list]
        if self.ev_tag == EvType.RECORD:
            return {k: v.native for k, v in self.ev_record.items()}
        return None

    # ── description ──

    def describe(self) -> str:
        if self.ev_tag == EvType.VOID:   return "nothing"
        if self.ev_tag == EvType.BOOL:   return "true" if self.ev_bool else "false"
        if self.ev_tag == EvType.INT:    return str(self.ev_int)
        if self.ev_tag == EvType.REAL:   return f"{self.ev_real:.6g}"
        if self.ev_tag == EvType.TEXT:   return f'"{self.ev_text}"'
        if self.ev_tag == EvType.BLOB:   return f"<blob {len(self.ev_blob)} bytes>"
        if self.ev_tag == EvType.LIST:
            return f"<list {len(self.ev_list)} items>"
        if self.ev_tag == EvType.RECORD:
            keys = ", ".join(list(self.ev_record)[:4])
            return "{" + keys + ("…" if len(self.ev_record) > 4 else "") + "}"
        return "?"

    def __repr__(self) -> str:
        return f"EValue({self.describe()}@{self.confidence}/256)"


# ─────────────────────────────────────────────
# Wire format — must match ev_serialise / ev_deserialise in evalue.c
# ─────────────────────────────────────────────

def serialise(v: EValue) -> bytes:
    """Python EValue → self-describing bytes.
    Same format as the C implementation so either side can decode.
    """
    tag = v.ev_tag
    if tag == EvType.VOID:
        return bytes([EvType.VOID])
    if tag == EvType.BOOL:
        return bytes([EvType.BOOL, 1 if v.ev_bool else 0])
    if tag == EvType.INT:
        # struct pack "<q" is signed int64; pass the value directly
        return bytes([EvType.INT]) + struct.pack("<q", v.ev_int)
    if tag == EvType.REAL:
        return bytes([EvType.REAL]) + struct.pack("<d", v.ev_real)
    if tag == EvType.TEXT:
        s = v.ev_text.encode("utf-8")
        return bytes([EvType.TEXT]) + struct.pack("<H", len(s)) + s
    if tag == EvType.BLOB:
        return bytes([EvType.BLOB]) + struct.pack("<i", len(v.ev_blob)) \
               + v.ev_blob
    if tag == EvType.LIST:
        out = bytes([EvType.LIST]) + struct.pack("<i", len(v.ev_list))
        for item in v.ev_list:
            out += serialise(item)
        return out
    if tag == EvType.RECORD:
        out = bytes([EvType.RECORD]) + struct.pack("<i", len(v.ev_record))
        for name, fval in v.ev_record.items():
            nb = name.encode("utf-8")[:EV_FIELD_NAME - 1]
            out += bytes([len(nb)]) + nb + serialise(fval)
        return out
    raise ValueError(f"unknown tag {tag}")


def deserialise(buf: bytes, pos: int = 0) -> tuple:
    """bytes → (EValue, bytes_consumed).
    Same wire format as the C implementation.
    """
    tag = EvType(buf[pos]); pos += 1
    if tag == EvType.VOID:
        return EValue.void(), pos
    if tag == EvType.BOOL:
        v = bool(buf[pos]); pos += 1
        return EValue.from_bool(v), pos
    if tag == EvType.INT:
        n = struct.unpack_from("<q", buf, pos)[0]; pos += 8
        return EValue.from_int(n), pos
    if tag == EvType.REAL:
        f = struct.unpack_from("<d", buf, pos)[0]; pos += 8
        return EValue.from_real(f), pos
    if tag == EvType.TEXT:
        slen = struct.unpack_from("<H", buf, pos)[0]; pos += 2
        s = buf[pos:pos+slen].decode("utf-8", errors="replace"); pos += slen
        return EValue.from_text(s), pos
    if tag == EvType.BLOB:
        blen = struct.unpack_from("<i", buf, pos)[0]; pos += 4
        return EValue.from_blob(buf[pos:pos+blen]), pos + blen
    if tag == EvType.LIST:
        count = struct.unpack_from("<i", buf, pos)[0]; pos += 4
        items = []
        for _ in range(count):
            item, pos = deserialise(buf, pos)
            items.append(item)
        return EValue.from_list(items), pos
    if tag == EvType.RECORD:
        nf = struct.unpack_from("<i", buf, pos)[0]; pos += 4
        fields = {}
        for _ in range(nf):
            nlen = buf[pos]; pos += 1
            name = buf[pos:pos+nlen].decode("utf-8", errors="replace"); pos += nlen
            fval, pos = deserialise(buf, pos)
            fields[name] = fval
        return EValue.from_record(fields), pos
    raise ValueError(f"unknown tag {tag}")


# ─────────────────────────────────────────────
# Lifters — source language → EValue
# ─────────────────────────────────────────────

NULLS = {"null", "nil", "None", "NULL", "undefined", "nullptr", ""}

def lift_literal(literal: str, conf: int = 120) -> EValue:
    """Any source language literal → EValue at intake confidence."""
    s = literal.strip()
    if s in NULLS:
        return EValue.void(conf)
    if s in ("true", "True"):
        return EValue.from_bool(True, conf)
    if s in ("false", "False"):
        return EValue.from_bool(False, conf)
    # quoted string
    if len(s) >= 2 and s[0] in ('"', "'") and s[-1] == s[0]:
        return EValue.from_text(s[1:-1], conf)
    # integer
    try:
        return EValue.from_int(int(s), conf)
    except ValueError:
        pass
    # real
    try:
        return EValue.from_real(float(s), conf)
    except ValueError:
        pass
    return EValue.from_text(s, conf)


def lift_sql_row(cols: List[str], vals: List[str],
                 conf: int = EV_CERTAIN) -> EValue:
    """SQL column names + values → EValue(RECORD).
    Identical structure to ev_from_sql_row in evalue.c.
    """
    return EValue.from_record(
        {col: lift_literal(val) if val is not None else EValue.void()
         for col, val in zip(cols, vals)},
        conf=conf)


def lift_html_element(tag: str, attrs: Dict[str, str],
                      children: Optional[List[EValue]] = None,
                      conf: int = EV_CERTAIN) -> EValue:
    """HTML element → EValue(RECORD) with tag/attrs/children fields.
    Identical structure to ev_from_html_element in evalue.c.
    """
    return EValue.from_record({
        "tag":      EValue.from_text(tag),
        "attrs":    EValue.from_record(
                        {k: EValue.from_text(v) for k, v in attrs.items()}),
        "children": EValue.from_list(children or []),
    }, conf=conf)


def lift_python(v: Any, conf: int = EV_CERTAIN) -> EValue:
    """Python native value → EValue.
    This is the bridge from the Ever interpreter's Python values to the
    unified type.
    """
    if v is None:           return EValue.void(conf)
    if isinstance(v, bool): return EValue.from_bool(v, conf)
    if isinstance(v, int):  return EValue.from_int(v, conf)
    if isinstance(v, float):return EValue.from_real(v, conf)
    if isinstance(v, str):  return EValue.from_text(v, conf)
    if isinstance(v, bytes):return EValue.from_blob(v, conf)
    if isinstance(v, list):
        return EValue.from_list([lift_python(x) for x in v], conf)
    if isinstance(v, dict):
        return EValue.from_record(
            {str(k): lift_python(vv) for k, vv in v.items()}, conf)
    return EValue.from_text(str(v), conf)


# ─────────────────────────────────────────────
# Demo
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("\n=== EValue — Python unified variant type ===\n")

    cases = [
        ("int",    EValue.from_int(42)),
        ("real",   EValue.from_real(3.14159)),
        ("bool",   EValue.from_bool(True)),
        ("text",   EValue.from_text("Codric")),
        ("void",   EValue.void()),
    ]
    for name, v in cases:
        buf = serialise(v)
        back, _ = deserialise(buf)
        mark = "✓" if v == back else "✗"
        print(f"  {mark}  {name:6} {v.describe()!r:20} wire={len(buf)}B")

    row = lift_sql_row(["id","name","score"], ["1","Alice","98.6"])
    print(f"\n  SQL row  : {row.describe()}")
    print(f"    name   : {row.get('name').describe()}")
    print(f"    score  : {row.get('score').describe()}")

    elem = lift_html_element("h1", {"class":"header","id":"title"})
    print(f"\n  HTML <h1>: {elem.describe()}")
    print(f"    class  : {elem.get('attrs').get('class').describe()}")

    lst = lift_python([10, 20, "Codric", True])
    print(f"\n  Python list: {lst.describe()}")
    for i, item in enumerate(lst):
        print(f"    [{i}] {item.describe()}")
    print()
