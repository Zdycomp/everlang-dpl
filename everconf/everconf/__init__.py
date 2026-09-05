"""
everconf — a value that carries how much you can trust it.

    >>> from everconf import C, UNKNOWN
    >>> total = C(88) + C(76) + UNKNOWN + C(91)
    >>> total
    UNKNOWN
    >>> total.confidence
    0

One missing input and the total is honestly UNKNOWN — not a number
computed by silently skipping the piece you didn't have. Every other
number-with-missing-data tool in Python either drops the NaN (pandas
.sum(skipna=True), the default) or propagates a bare NaN with no way
to say WHY, or how much of the rest of your pipeline was still solid.
C tracks both: the value, and a 0–256 trust score that only degrades,
never inflates, as data moves through your program.

    >>> a = C(10, confidence=256)   # you measured this yourself
    >>> b = C(20, confidence=120)   # this one came from an API
    >>> (a + b).confidence
    120

The result can be no more certain than its least certain input. This
is deliberately NOT a statistics library — no distributions, no
standard deviations, no Bayesian updates. If you need that, look at
`Uncertain<T>` (Bornholt et al., MSR) or Julia's Measurements.jl —
both are more rigorous and both require more of you to use correctly.
C trades that rigor for a single int anyone can read at a glance,
because most pipelines don't need a posterior, they need to stop
lying when something is missing.

This is the confidence-value core of Ever (github.com/<org>/tapestry),
a full language built around the same rule, extracted here as a
library so the idea costs nothing to try.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Optional, Union

CERTAIN = 256
INTAKE  = 120   # suggested confidence for data you didn't measure
                # yourself — an API response, a file read, user input
FLOOR   = 128   # suggested threshold below which a value shouldn't
                # drive an action without corroboration


class _UnknownType:
    """Sentinel used only at the API boundary (so `x is UNKNOWN` reads
    cleanly and `UNKNOWN` has a clean repr before it's coerced). Every
    actual behaviour — arithmetic, comparisons, unwrap, require — is
    delegated to a real C(None, confidence=0), so the two are
    indistinguishable in practice from either side of an operator:
    `UNKNOWN + 5` and `5 + UNKNOWN` and `C(5) + UNKNOWN` all take the
    identical path.
    """

    def __repr__(self) -> str:
        return "UNKNOWN"

    def _as_c(self) -> "C":
        return C(None, confidence=0)

    def __bool__(self) -> bool:
        raise TypeError(
            "UNKNOWN has no truth value — check `is UNKNOWN` explicitly, "
            "the way you'd check `is None`")

    def __getattr__(self, name: str):
        # ordinary method calls (unwrap, require, eq, gt, ...) — not
        # reached for dunder methods invoked implicitly by operators,
        # which Python looks up on the type and are defined explicitly
        # below instead
        return getattr(self._as_c(), name)

    def __eq__(self, other) -> bool:
        return self._as_c() == other

    def __hash__(self) -> int:
        return hash(self._as_c())

    def __add__(self, other):  return self._as_c() + other
    def __radd__(self, other): return self._as_c().__radd__(other)
    def __sub__(self, other):  return self._as_c() - other
    def __rsub__(self, other): return self._as_c().__rsub__(other)
    def __mul__(self, other):  return self._as_c() * other
    def __rmul__(self, other): return self._as_c().__rmul__(other)
    def __truediv__(self, other):  return self._as_c() / other
    def __rtruediv__(self, other): return self._as_c().__rtruediv__(other)
    def __pow__(self, other):  return self._as_c() ** other
    def __neg__(self):         return self._as_c()


UNKNOWN = _UnknownType()


def _coerce(x: Any) -> "C":
    if isinstance(x, C):
        return x
    if x is UNKNOWN:
        return C(None, confidence=0)
    if isinstance(x, (int, float, bool, str)):
        return C(x)
    raise TypeError(
        f"can't use {x!r} ({type(x).__name__}) in a confidence "
        f"expression — wrap it in C(...) or UNKNOWN first")


@dataclass(frozen=True, eq=False)
class C:
    """A value with a trust score from 0 to 256.

    >>> C(42)                      # a literal you wrote: certain
    C(42, confidence=256)
    >>> C(42, confidence=120)      # something you read from outside
    C(42, confidence=120)
    """

    value:      Any
    confidence: int = CERTAIN

    def __post_init__(self):
        if self.value is None and self.confidence != 0:
            # internal invariant: only UNKNOWN represents "no value",
            # and UNKNOWN is always confidence 0
            object.__setattr__(self, "confidence", 0)
        c = max(0, min(CERTAIN, int(self.confidence)))
        object.__setattr__(self, "confidence", c)

    # ── the one thing that makes this worth using ──
    @property
    def is_unknown(self) -> bool:
        return self.value is None

    def __repr__(self) -> str:
        if self.is_unknown:
            return "UNKNOWN"
        return f"C({self.value!r}, confidence={self.confidence})"

    def __bool__(self) -> bool:
        if self.is_unknown:
            raise TypeError(
                "UNKNOWN has no truth value — check `.is_unknown` "
                "explicitly, the way you'd check `is None`")
        return bool(self.value)

    # Ordinary `==`/hash compare the VALUE only, ignoring confidence —
    # matching what anyone reading `computed == C(5)` in a test or an
    # `if x in seen_values` check would already expect. Confidence-
    # tracked equality is the explicit .eq() method below; the two are
    # deliberately different operations; `==` is not confidence-aware
    # on purpose, so it keeps behaving like every other Python value.
    def __eq__(self, other) -> bool:
        if isinstance(other, C):
            return self.value == other.value
        if other is UNKNOWN:
            return self.is_unknown
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.value)

    # ── arithmetic: value combines normally, confidence is min() ──
    def _binop(self, other: Any, fn: Callable[[Any, Any], Any]) -> "C":
        o = _coerce(other)
        if self.is_unknown or o.is_unknown:
            return C(None, confidence=0)
        try:
            v = fn(self.value, o.value)
        except (TypeError, ZeroDivisionError):
            return C(None, confidence=0)
        return C(v, confidence=min(self.confidence, o.confidence))

    def __add__(self, other):  return self._binop(other, lambda a, b: a + b)
    def __radd__(self, other): return _coerce(other).__add__(self)
    def __sub__(self, other):  return self._binop(other, lambda a, b: a - b)
    def __rsub__(self, other): return _coerce(other).__sub__(self)
    def __mul__(self, other):  return self._binop(other, lambda a, b: a * b)
    def __rmul__(self, other): return _coerce(other).__mul__(self)
    def __truediv__(self, other):
        return self._binop(other, lambda a, b: a / b)
    def __rtruediv__(self, other):
        return _coerce(other).__truediv__(self)
    def __pow__(self, other):  return self._binop(other, lambda a, b: a ** b)

    def __neg__(self) -> "C":
        if self.is_unknown:
            return self
        return C(-self.value, confidence=self.confidence)

    # ── comparisons: also confidence-tracked, return a C(bool) ──
    def _cmp(self, other: Any, fn: Callable[[Any, Any], bool]) -> "C":
        o = _coerce(other)
        if self.is_unknown or o.is_unknown:
            return C(None, confidence=0)
        return C(fn(self.value, o.value),
                 confidence=min(self.confidence, o.confidence))

    def lt(self, other):  return self._cmp(other, lambda a, b: a <  b)
    def gt(self, other):  return self._cmp(other, lambda a, b: a >  b)
    def le(self, other):  return self._cmp(other, lambda a, b: a <= b)
    def ge(self, other):  return self._cmp(other, lambda a, b: a >= b)
    def eq(self, other):  return self._cmp(other, lambda a, b: a == b)
    def ne(self, other):  return self._cmp(other, lambda a, b: a != b)

    # Python's own __eq__/__lt__ etc. are left alone (needed for
    # hashing, sorting, and sane dict/set behaviour) — the confidence-
    # tracked comparisons are the explicit .lt()/.eq()/... methods
    # above, exactly so `c1 == c2` for two C values still means what
    # every Python programmer already expects it to mean.

    def unwrap(self, default: Any = None) -> Any:
        """Escape hatch: get the raw value, or `default` if unknown.
        Named loudly on purpose — every other operation in this
        library keeps you honest about missing data; this one lets
        you choose to stop being honest, so it should never be
        reached for by accident."""
        return default if self.is_unknown else self.value

    def require(self, floor: int = FLOOR) -> Any:
        """Get the raw value, but raise if confidence is below `floor`.
        For the moment you're about to DO something with a value —
        send an email, charge a card — and want the type system-ish
        guarantee that it wasn't built from too much guesswork."""
        if self.is_unknown or self.confidence < floor:
            raise LowConfidenceError(
                f"confidence {0 if self.is_unknown else self.confidence} "
                f"is below the required floor of {floor}")
        return self.value


class LowConfidenceError(Exception):
    """Raised by C.require() when a value isn't trustworthy enough
    to act on. Catch this the way you'd catch a validation error —
    it means the pipeline correctly refused to guess."""


# ═══════════════════════════════════════════════
# Aggregates — same rule as everywhere else: confidence is the min
# across every element, and one UNKNOWN poisons the whole aggregate.
# ═══════════════════════════════════════════════

def csum(items: Iterable[Union["C", Any]]) -> "C":
    """Sum a sequence of C values (or plain numbers/UNKNOWN, coerced
    automatically). One UNKNOWN anywhere in the sequence makes the
    total UNKNOWN — this is the whole point, and the one place a
    library like this earns its keep over `sum()` + a NaN check."""
    total = C(0)
    for x in items:
        total = total + x
    return total


def cmean(items: Iterable[Union["C", Any]]) -> "C":
    items = list(items)
    if not items:
        return C(None, confidence=0)
    total = csum(items)
    if total.is_unknown:
        return total
    return C(total.value / len(items), confidence=total.confidence)


def cmin_conf(items: Iterable["C"]) -> int:
    """The confidence of the least trustworthy item — the number that
    would gate an aggregate if you built one by hand."""
    confs = [c.confidence for c in items]
    return min(confs) if confs else 0


def sigmoid(x: Union["C", Any]) -> "C":
    """The logistic activation, confidence-tracked. Bounded to (0, 1)
    by construction — the same shape as a normalized confidence
    value, which is why this belongs here rather than being a
    coincidence to ignore."""
    c = _coerce(x)
    if c.is_unknown:
        return c
    try:
        v = 1.0 / (1.0 + math.exp(-c.value))
    except OverflowError:
        v = 0.0 if c.value < 0 else 1.0
    return C(v, confidence=c.confidence)


def mse(predicted: Iterable[Union["C", Any]],
       actual: Iterable[Union["C", Any]]) -> "C":
    """Mean squared error, confidence-tracked. If one label in your
    training set was never recorded, this is UNKNOWN — not the mse
    of the points you happened to have. A model can't honestly claim
    to have learned from data it didn't have.

    >>> from everconf import C, UNKNOWN, mse
    >>> mse([C(0.9), C(0.2), C(0.6)], [C(1), C(0), C(1)])
    C(0.07, confidence=256)
    >>> mse([C(0.9), C(0.2), C(0.6)], [C(1), C(0), UNKNOWN])
    UNKNOWN
    """
    p = [_coerce(x) for x in predicted]
    a = [_coerce(x) for x in actual]
    if len(p) != len(a) or len(p) == 0:
        return C(None, confidence=0)
    sq_errors = []
    for pi, ai in zip(p, a):
        if pi.is_unknown or ai.is_unknown:
            return C(None, confidence=0)
        sq_errors.append((pi.value - ai.value) ** 2)
    return C(sum(sq_errors) / len(sq_errors), confidence=cmin_conf(p + a))
