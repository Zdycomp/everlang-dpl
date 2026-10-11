#!/usr/bin/env python3
"""
ffi.py — Ever's foreign function interface. Real, not simulated:
loads an actual shared library via ctypes and calls the actual
compiled symbol.

THE ONE DESIGN QUESTION THAT MATTERS

A foreign function is code Ever did not write, cannot inspect, and
cannot verify. Every other value in this language earns its
confidence — a literal is certain because the program said so, a
computed value is only as certain as what it was built from. An FFI
call has no such lineage: Ever hands control to a compiled binary and
gets a number back with no way to audit what happened in between.

So an FFI result is never certain, by construction. It enters at
E_INTAKE (120) — the same ceiling every other piece of external data
in this language enters at — capped further by whatever confidence
its own arguments carried in. If the language can't verify a value
came from outside at all, it has no business calling it certain
either.

And if an argument is z — genuinely unmeasured — the call never
happens. C has no representation for "unknown"; passing some
placeholder number into foreign code and trusting the result back
would be exactly the failure this whole language exists to prevent.

SCOPE, STATED PLAINLY

v1 marshals double-precision floats only: arguments and return value.
That covers the honest common case (libm, and any C function shaped
like double f(double, double, ...)) and can be verified completely —
every example in this file is checked against a real compiled library,
not claimed. Integers, strings, structs, callbacks, and pointers are
real future work, not silently pretended to work today.

Codric Enterprise · Ricky (Dreid) · 2026
"""

from __future__ import annotations

import ctypes
import ctypes.util
from dataclasses import dataclass
from typing import List, Optional

from evalue import EValue, EvType

E_INTAKE = 120


class FFIError(Exception):
    pass


@dataclass
class ExternFn:
    name:    str
    libpath: str
    arity:   int
    cfunc:   ctypes.CDLL

    def call(self, args: List[EValue]) -> EValue:
        if len(args) != self.arity:
            return EValue.void()
        nums = []
        for a in args:
            if a.ev_tag == EvType.INT:
                nums.append(float(a.ev_int))
            elif a.ev_tag == EvType.REAL:
                nums.append(a.ev_real)
            else:
                # includes VOID/z: cannot marshal an unknown into a C
                # double, so the call never happens
                return EValue.void()
        try:
            result = self.cfunc(*nums)
        except Exception:
            return EValue.void()
        return EValue.from_real(float(result))

    def confidence(self, args: List[EValue], arg_confs: List[int]) -> int:
        if len(args) != self.arity:
            return 0
        for a in args:
            if a.ev_tag not in (EvType.INT, EvType.REAL):
                return 0
        cap = E_INTAKE
        return min([cap] + list(arg_confs)) if arg_confs else cap


def _resolve_library(libpath: str) -> str:
    """Accept a bare name ('m' for libm) or a full path, matching how
    ctypes.util.find_library already works for the common case."""
    found = ctypes.util.find_library(libpath)
    return found or libpath


def load_extern(name: str, params: List[str], libpath: str) -> ExternFn:
    """Load one C symbol as a double(double,...) function. Raises
    FFIError with a specific, actionable message on any failure — the
    library doesn't exist, the symbol doesn't exist, or the platform
    refuses to load it — rather than a bare ctypes traceback."""
    resolved = _resolve_library(libpath)
    try:
        lib = ctypes.CDLL(resolved)
    except OSError as exc:
        raise FFIError(f"cannot load library '{libpath}': {exc}") from exc

    try:
        raw = getattr(lib, name)
    except AttributeError as exc:
        raise FFIError(
            f"'{libpath}' has no symbol '{name}'") from exc

    raw.argtypes = [ctypes.c_double] * len(params)
    raw.restype  = ctypes.c_double

    return ExternFn(name=name, libpath=libpath, arity=len(params), cfunc=raw)
