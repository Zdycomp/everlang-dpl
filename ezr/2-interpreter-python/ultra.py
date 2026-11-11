#!/usr/bin/env python3
"""
ultra.py — ultra-anchored recursion.

An anchor buys depth. SEMANTICS.md 4.6: a function that is cleared and
carries a proven decreasing measure gets `limit = infinity`, because
verification purchased the right to go deep.

It did not actually get it. Removing EZR's ceiling only exposes
CPython's, and an anchored `fact` dies of RecursionError somewhere
around depth 300 -- for reasons that have nothing to do with EZR, in a
language whose own documents promise unbounded depth. That refusal is
honest (G1 holds, it returns Z) and it is still a promise unkept.

**Ultra-anchoring is anchoring that can actually be cashed.** Three
things, all required, none of them optional:

  1. anchored      cleared, recursive, decreasing measure proven. The
                   existing bar, unchanged.
  2. provisioned   the call runs in an execution context reserved to
                   deliver the depth -- its own stack, sized up front.
                   A promise of unbounded depth that the runtime cannot
                   honour is not a weaker promise, it is a false one.
  3. conserving    every thread the recursion creates is accounted for
                   when it ends: utilised, recycled, or still resident.
                   Nothing vanishes down a few thousand frames.

The third is what makes it a subsystem rather than just a bigger
stack. Depth without accounting is how you lose track of what a
computation did; the ledger is the reason the depth is safe to grant.

Codric Enterprise
"""

from __future__ import annotations

import sys
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from ever import E, E_CERTAIN, Defect, State, e_z
from physics import Subsystem, Violation, entropy, inertia

#: Reserved stack for a provisioned call. Each EZR frame costs several
#: Python frames, so this is sized for the depth, not for the source.
DEFAULT_STACK_MB = 256

#: Raised to match. Kept below what the reserved stack can carry, so
#: the limit is reached before the memory is -- a RecursionError is
#: recoverable, a segmentation fault is not.
DEFAULT_LIMIT = 150_000


@dataclass
class DeepResult:
    value: Any = None
    error: Optional[BaseException] = None
    depth_reached: int = 0

    @property
    def ok(self) -> bool:
        return self.error is None


def deep(fn: Callable, *args, stack_mb: int = DEFAULT_STACK_MB,
         limit: int = DEFAULT_LIMIT, **kwargs) -> DeepResult:
    """Run something on a thread with a stack reserved for it.

    The work happens on its own thread because a stack size can only be
    chosen when a thread is created -- the main thread's is fixed by
    the time any of this is loaded. Nothing here is concurrent: the
    caller waits, and the only reason for the thread is the stack.
    """
    out = DeepResult()

    def target() -> None:
        previous = sys.getrecursionlimit()
        sys.setrecursionlimit(limit)
        try:
            out.value = fn(*args, **kwargs)
        except BaseException as exc:            # noqa: BLE001 - relayed
            out.error = exc
        finally:
            sys.setrecursionlimit(previous)

    old_size = threading.stack_size()
    try:
        threading.stack_size(stack_mb * 1024 * 1024)
    except (ValueError, RuntimeError):
        pass                                    # take what we are given
    t = threading.Thread(target=target, name="ezr-ultra")
    t.start()
    t.join()
    try:
        threading.stack_size(old_size)
    except (ValueError, RuntimeError):
        pass
    return out


# ═════════════════════════════════════════════
# The ultra-anchor
# ═════════════════════════════════════════════

@dataclass
class UltraAnchor:
    """An anchored function, provisioned and accounted for."""
    name: str
    measure: str
    stack_mb: int = DEFAULT_STACK_MB
    limit: int = DEFAULT_LIMIT
    subsystem: Subsystem = field(default_factory=lambda: Subsystem("ultra"))
    calls: int = 0
    max_depth: int = 0

    def audit(self) -> List[Violation]:
        return self.subsystem.audit()


def qualifies(fp: E, closure: Any) -> Tuple[bool, str]:
    """Whether a thread may be ultra-anchored, and why not when it may not.

    Deliberately the same bar as anchoring plus nothing softer. An
    ultra-anchor grants more, so it cannot ask less.
    """
    if fp.is_z:
        return False, "the thread is Z"
    if fp.anchor_id == 0:
        return False, "not anchored: depth is earned, never assumed"
    measure = getattr(closure, "measure", None)
    if not getattr(closure, "recursive", False):
        return False, "not recursive: an ultra-anchor would buy nothing"
    if not measure:
        return False, ("no decreasing measure proven -- confidence is "
                       "evidence about correctness, and correctness is "
                       "not termination")
    return True, measure


def ultra_anchor(fp: E, closure: Any, stack_mb: int = DEFAULT_STACK_MB,
                 limit: int = DEFAULT_LIMIT
                 ) -> Tuple[Optional[UltraAnchor], str]:
    """Promote an anchored thread, or refuse and say why."""
    ok, why = qualifies(fp, closure)
    if not ok:
        return None, why
    ua = UltraAnchor(name=getattr(closure, "name", fp.ident), measure=why,
                     stack_mb=stack_mb, limit=limit)
    ua.subsystem.admit(fp, f"ultra-anchored on measure {why!r}")
    return ua, why


def run_ultra(ua: UltraAnchor, call: Callable, *args, **kwargs) -> E:
    """Run a call under an ultra-anchor, then audit the subsystem.

    A conservation failure is not a warning here. The whole reason the
    depth was granted is that the accounting holds, so if it does not
    hold the result is refused -- returning it anyway would be keeping
    the part of the bargain that is convenient.
    """
    res = deep(call, *args, stack_mb=ua.stack_mb, limit=ua.limit, **kwargs)
    ua.calls += 1

    if not res.ok:
        return e_z(ua.name,
                   f"ultra-anchored call failed: "
                   f"{type(res.error).__name__}: {res.error}",
                   Defect.UNBOUNDED)

    out = res.value
    if isinstance(out, E):
        ua.subsystem.admit(out, "result of an ultra-anchored call")

    broken = ua.audit()
    if broken:
        return e_z(ua.name,
                   "conservation failed under an ultra-anchor: "
                   + "; ".join(str(b) for b in broken),
                   Defect.ORPHANED)
    return out


__all__ = ["deep", "DeepResult", "UltraAnchor", "ultra_anchor", "run_ultra",
           "qualifies", "DEFAULT_STACK_MB", "DEFAULT_LIMIT"]
