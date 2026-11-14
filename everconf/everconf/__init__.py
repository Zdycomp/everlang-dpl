"""
everconf — a value that carries how much you can trust it.

    >>> from everconf import C, Unknown, MISSING_INPUT
    >>> total = C(88) + C(76) + Unknown(MISSING_INPUT, "label 3 was never recorded") + C(91)
    >>> total
    UNKNOWN(MISSING_INPUT: label 3 was never recorded)
    >>> total.confidence
    0

Two kinds of result, and nothing else:

* ``C(value, confidence)`` — a real value, with a trust score from 0 to 256.
* ``Unknown(code, reason)`` — no answer exists. It has confidence 0, a
  reason code from the registry in ``reasons.py``, and a human reason. It
  is the only way this library says "there is no answer". Null, None and
  NaN are never returned, and ``C(None)`` raises.

An Unknown poisons everything built from it. Arithmetic, comparison and
aggregates that touch one return an Unknown that keeps the origin code and
reason, plus a chain of the steps it passed through. Nothing is skipped.

    >>> a = C(10, confidence=256)   # you measured this yourself
    >>> b = C(20, confidence=120)   # this one came from an API
    >>> (a + b).confidence
    120

The result can be no more certain than its least certain input. This is
deliberately NOT a statistics library. It is a single int anyone can read at
a glance, because most pipelines don't need a posterior; they need to stop
lying when something is missing.

This is the confidence-value core of Ever, extracted as a library.
"""

from __future__ import annotations

import math
from typing import Any, Callable, Iterable, List, Sequence, Tuple, Union

from .reasons import REASONS, check_unknown_code

__version__ = "0.2.0"

CERTAIN = 256
INTAKE  = 120   # confidence for data you didn't measure yourself: an API
                # response, a file read, a model's answer
AGREE   = 180   # two independent sources that agree on the same passage
FLOOR   = 128   # the default threshold below which a value should not drive
                # an action without corroboration

# Reason codes, re-exported so callers write Unknown(MISSING_INPUT, ...).
MISSING_INPUT       = "MISSING_INPUT"
CONFLICTING_SOURCES = "CONFLICTING_SOURCES"
BELOW_THRESHOLD     = "BELOW_THRESHOLD"
TIMEOUT             = "TIMEOUT"
OUT_OF_RANGE        = "OUT_OF_RANGE"
UNVERIFIED_SOURCE   = "UNVERIFIED_SOURCE"
MALFORMED           = "MALFORMED"

NOT_RECORDED   = "not recorded"    # shown when a value has no timestamp
LITERAL_SOURCE = "literal in code"

_NULL_MESSAGE = ("null is not a value. For an answer that does not exist, "
                 "return Unknown(code, reason)")


class LowConfidenceError(Exception):
    """Raised by ``require()`` when a value must not be used for an action.

    Carries the code, the human reason, the confidence it had, and the
    threshold it failed. Catch it the way you'd catch a validation error:
    it means the pipeline correctly refused to act on a guess.
    """

    def __init__(self, message: str, *, code: str, reason: str,
                 confidence: int, threshold: int):
        super().__init__(message)
        self.code = code
        self.reason = reason
        self.confidence = confidence
        self.threshold = threshold


def _check_threshold(min_confidence: int) -> int:
    if isinstance(min_confidence, bool) or not isinstance(min_confidence, int):
        raise TypeError("min_confidence must be an int from 0 to 256")
    if not 0 <= min_confidence <= CERTAIN:
        raise ValueError("min_confidence must be from 0 to 256")
    return min_confidence


# ═══════════════════════════════════════════════
# Unknown — an answer that does not exist
# ═══════════════════════════════════════════════

class Unknown:
    """No answer, with the reason. Confidence is always 0.

    ``code``   one of the Unknown codes in the registry (required)
    ``reason`` a human-readable sentence (required, non-empty)
    ``chain``  the steps it passed through, origin excluded, oldest first

    >>> Unknown(MISSING_INPUT, "no label for row 4")
    UNKNOWN(MISSING_INPUT: no label for row 4)
    """

    __slots__ = ("code", "reason", "chain")

    confidence = 0
    is_unknown = True

    def __init__(self, code: str, reason: str, chain: Iterable[str] = ()):
        check_unknown_code(code)
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("an Unknown needs a non-empty human-readable reason")
        steps = tuple(chain)
        for step in steps:
            if not isinstance(step, str) or not step:
                raise ValueError("every chain step must be a non-empty string")
        self.code = code
        self.reason = reason
        self.chain = steps

    def __repr__(self) -> str:
        return f"UNKNOWN({self.code}: {self.reason})"

    __str__ = __repr__

    def __bool__(self) -> bool:
        raise TypeError(
            "UNKNOWN has no truth value. Check `is_unknown` explicitly, "
            "the way you'd check `is None`")

    def __eq__(self, other) -> bool:
        if not isinstance(other, Unknown):
            return NotImplemented
        return (self.code, self.reason, self.chain) == (other.code, other.reason, other.chain)

    def __hash__(self) -> int:
        return hash((self.code, self.reason))

    def to_dict(self) -> dict:
        return {"state": "unknown", "code": self.code,
                "reason": self.reason, "chain": list(self.chain)}

    @classmethod
    def from_dict(cls, d: dict) -> "Unknown":
        if d.get("state") != "unknown":
            raise ValueError("not an Unknown record")
        return cls(d["code"], d["reason"], d.get("chain", []))

    def require(self, min_confidence: int = FLOOR) -> Any:
        _check_threshold(min_confidence)
        raise LowConfidenceError(
            f"no answer to act on: {self.code}: {self.reason}",
            code=self.code, reason=self.reason,
            confidence=0, threshold=min_confidence)

    # Every operation on an Unknown is poisoning, so the operator methods
    # all route through the same function as C's operators.
    def __add__(self, other):       return _poison("add", [self, _coerce(other, "add")])
    def __radd__(self, other):      return _poison("add", [_coerce(other, "add"), self])
    def __sub__(self, other):       return _poison("sub", [self, _coerce(other, "sub")])
    def __rsub__(self, other):      return _poison("sub", [_coerce(other, "sub"), self])
    def __mul__(self, other):       return _poison("mul", [self, _coerce(other, "mul")])
    def __rmul__(self, other):      return _poison("mul", [_coerce(other, "mul"), self])
    def __truediv__(self, other):   return _poison("div", [self, _coerce(other, "div")])
    def __rtruediv__(self, other):  return _poison("div", [_coerce(other, "div"), self])
    def __pow__(self, other):       return _poison("pow", [self, _coerce(other, "pow")])
    def __rpow__(self, other):      return _poison("pow", [_coerce(other, "pow"), self])
    def __neg__(self):              return _poison("neg", [self])
    def lt(self, other):            return _poison("lt", [self, _coerce(other, "lt")])
    def gt(self, other):            return _poison("gt", [self, _coerce(other, "gt")])
    def le(self, other):            return _poison("le", [self, _coerce(other, "le")])
    def ge(self, other):            return _poison("ge", [self, _coerce(other, "ge")])
    def eq(self, other):            return _poison("eq", [self, _coerce(other, "eq")])
    def ne(self, other):            return _poison("ne", [self, _coerce(other, "ne")])


# ═══════════════════════════════════════════════
# C — a value with a trust score
# ═══════════════════════════════════════════════

class C:
    """A value with a trust score from 0 to 256.

    >>> C(42)                      # a literal you wrote: certain
    C(42, confidence=256)
    >>> C(42, confidence=120)      # something you read from outside
    C(42, confidence=120)
    >>> C(None)                    # null is not a value
    Traceback (most recent call last):
    ...
    TypeError: null is not a value. For an answer that does not exist, return Unknown(code, reason)
    """

    __slots__ = ("value", "confidence", "source", "at", "_op", "_inputs")

    is_unknown = False

    def __init__(self, value: Any, confidence: int = CERTAIN, *,
                 source: str = LITERAL_SOURCE, at: str = NOT_RECORDED):
        if value is None:
            raise TypeError(_NULL_MESSAGE)
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("NaN and infinity are not values; "
                             "return Unknown(OUT_OF_RANGE, reason) instead")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            raise TypeError("confidence must be a number from 0 to 256")
        self.value = value
        self.confidence = max(0, min(CERTAIN, int(confidence)))
        self.source = source
        self.at = at
        self._op = "input"
        self._inputs: Tuple[Any, ...] = ()

    @classmethod
    def _derived(cls, value: Any, confidence: int, op: str,
                 inputs: Sequence[Any]) -> "C":
        c = cls.__new__(cls)
        c.value = value
        c.confidence = max(0, min(CERTAIN, int(confidence)))
        c.source = f"derived by {op}"
        known = [i for i in inputs if isinstance(i, C)]
        stamped = len(known) == len(inputs) and all(i.at != NOT_RECORDED for i in known)
        c.at = max(i.at for i in known) if stamped and known else NOT_RECORDED
        c._op = op
        c._inputs = tuple(inputs)
        return c

    def __repr__(self) -> str:
        return f"C({self.value!r}, confidence={self.confidence})"

    def __bool__(self) -> bool:
        return bool(self.value)

    # Ordinary `==`/hash compare the VALUE only, the way anyone reading
    # `computed == C(5)` in a test would expect. Confidence-tracked
    # comparison is the explicit .eq() method, and the two stay different.
    def __eq__(self, other) -> bool:
        if isinstance(other, C):
            return self.value == other.value
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.value)

    # ── arithmetic: value combines normally, confidence is min() ──
    def __add__(self, other):       return _lift("add", [self, _coerce(other, "add")], lambda v: v[0] + v[1])
    def __radd__(self, other):      return _lift("add", [_coerce(other, "add"), self], lambda v: v[0] + v[1])
    def __sub__(self, other):       return _lift("sub", [self, _coerce(other, "sub")], lambda v: v[0] - v[1])
    def __rsub__(self, other):      return _lift("sub", [_coerce(other, "sub"), self], lambda v: v[0] - v[1])
    def __mul__(self, other):       return _lift("mul", [self, _coerce(other, "mul")], lambda v: v[0] * v[1])
    def __rmul__(self, other):      return _lift("mul", [_coerce(other, "mul"), self], lambda v: v[0] * v[1])
    def __truediv__(self, other):   return _lift("div", [self, _coerce(other, "div")], lambda v: v[0] / v[1])
    def __rtruediv__(self, other):  return _lift("div", [_coerce(other, "div"), self], lambda v: v[0] / v[1])
    def __pow__(self, other):       return _lift("pow", [self, _coerce(other, "pow")], lambda v: v[0] ** v[1])
    def __rpow__(self, other):      return _lift("pow", [_coerce(other, "pow"), self], lambda v: v[0] ** v[1])
    def __neg__(self):              return _lift("neg", [self], lambda v: -v[0])

    # ── comparisons: also confidence-tracked, return a C(bool) ──
    def lt(self, other):  return _lift("lt", [self, _coerce(other, "lt")], lambda v: v[0] <  v[1])
    def gt(self, other):  return _lift("gt", [self, _coerce(other, "gt")], lambda v: v[0] >  v[1])
    def le(self, other):  return _lift("le", [self, _coerce(other, "le")], lambda v: v[0] <= v[1])
    def ge(self, other):  return _lift("ge", [self, _coerce(other, "ge")], lambda v: v[0] >= v[1])
    def eq(self, other):  return _lift("eq", [self, _coerce(other, "eq")], lambda v: v[0] == v[1])
    def ne(self, other):  return _lift("ne", [self, _coerce(other, "ne")], lambda v: v[0] != v[1])

    def require(self, min_confidence: int = FLOOR) -> Any:
        """Return the value if its confidence is at least ``min_confidence``.

        Below the threshold it raises LowConfidenceError. The value can still
        be displayed (``result.to_result``), just not used for an action.
        """
        _check_threshold(min_confidence)
        if self.confidence < min_confidence:
            reason = f"confidence {self.confidence} is below the required {min_confidence}"
            raise LowConfidenceError(reason, code=BELOW_THRESHOLD, reason=reason,
                                     confidence=self.confidence, threshold=min_confidence)
        return self.value


# ═══════════════════════════════════════════════
# The shared rules: coerce, lift, poison
# ═══════════════════════════════════════════════

def _coerce(x: Any, op: str) -> Union[C, Unknown]:
    if isinstance(x, (C, Unknown)):
        return x
    if x is None:
        raise TypeError(_NULL_MESSAGE)
    if isinstance(x, (int, float, bool, str)):
        return C(x)
    raise TypeError(
        f"can't use {x!r} ({type(x).__name__}) in a confidence expression "
        f"({op}); wrap it in C(...) first")


def _poison(op: str, operands: Sequence[Union[C, Unknown]]) -> Unknown:
    unknowns = [x for x in operands if isinstance(x, Unknown)]
    first = unknowns[0]
    chain: List[str] = list(first.chain)
    chain.append(f"{op}: poisoned by {first.code}")
    for other in unknowns[1:]:
        chain.append(f"{op}: also {other.code}: {other.reason}")
        chain.extend(other.chain)
    return Unknown(first.code, first.reason, chain=chain)


def _lift(op: str, operands: Sequence[Union[C, Unknown]],
          compute: Callable[[List[Any]], Any]) -> Union[C, Unknown]:
    if any(isinstance(x, Unknown) for x in operands):
        return _poison(op, operands)
    try:
        v = compute([x.value for x in operands])
    except ZeroDivisionError:
        return Unknown(OUT_OF_RANGE, f"{op}: division by zero")
    except OverflowError:
        return Unknown(OUT_OF_RANGE, f"{op}: the result is too large to represent")
    except TypeError as exc:
        return Unknown(MALFORMED, f"{op}: these values cannot be combined ({exc})")
    if isinstance(v, float) and not math.isfinite(v):
        return Unknown(OUT_OF_RANGE, f"{op}: the result is not a finite number")
    conf = min(x.confidence for x in operands)
    return C._derived(v, conf, op, operands)


# ═══════════════════════════════════════════════
# Aggregates — same rule as everywhere else: confidence is the min
# across every element, and one Unknown poisons the whole aggregate.
# ═══════════════════════════════════════════════

def csum(items: Iterable[Union[C, Unknown, int, float]]) -> Union[C, Unknown]:
    """Sum. One Unknown anywhere makes the total Unknown, with every
    Unknown's reason kept in the chain. The empty sum is 0."""
    total: Union[C, Unknown] = C(0)
    for x in items:
        total = total + _coerce(x, "sum")
    return total


def cmean(items: Iterable[Union[C, Unknown, int, float]]) -> Union[C, Unknown]:
    values = [_coerce(x, "mean") for x in items]
    if not values:
        return Unknown(MISSING_INPUT, "the mean of no values is not defined")
    total = csum(values)
    if isinstance(total, Unknown):
        return _poison("mean", [total])
    return _lift("mean", [total, C(len(values))], lambda v: v[0] / v[1])


def cmin_conf(items: Iterable[Union[C, Unknown]]) -> int:
    """The confidence of the least trustworthy item. An Unknown counts as 0."""
    confs = [x.confidence for x in items]
    return min(confs) if confs else 0


def agree(a: Union[C, Unknown], b: Union[C, Unknown]) -> Union[C, Unknown]:
    """Two readings of the same thing. Equal values agree, and the result's
    confidence is the lower of the two. Different values are an Unknown
    (CONFLICTING_SOURCES): nothing here settles which one is right."""
    if isinstance(a, Unknown) or isinstance(b, Unknown):
        return _poison("agree", [a, b])
    if a.value != b.value:
        return Unknown(CONFLICTING_SOURCES, f"{a.value!r} and {b.value!r} disagree")
    return C._derived(a.value, min(a.confidence, b.confidence), "agree", [a, b])


def corroborate(a: Union[C, Unknown], b: Union[C, Unknown]) -> Union[C, Unknown]:
    """Two independent sources reporting the same value.

    This is the one place confidence can rise, and only by a fixed rule:

    * different values: Unknown (CONFLICTING_SOURCES), nothing settles it;
    * either source below INTAKE: the lower confidence, no lift (a weak
      source does not become strong by agreeing with another weak one);
    * otherwise: at least AGREE (180), never above CERTAIN. A value both
      sources hold at CERTAIN stays CERTAIN.

    Every other operation in this library can only lower confidence. This
    exception is recorded in the provenance as op "corroborate".
    """
    if isinstance(a, Unknown) or isinstance(b, Unknown):
        return _poison("corroborate", [a, b])
    if a.value != b.value:
        return Unknown(CONFLICTING_SOURCES, f"{a.value!r} and {b.value!r} disagree")
    low = min(a.confidence, b.confidence)
    if low < INTAKE:
        conf = low
    else:
        conf = min(CERTAIN, max(AGREE, low))
    return C._derived(a.value, conf, "corroborate", [a, b])


def sigmoid(x: Union[C, Unknown, int, float]) -> Union[C, Unknown]:
    """The logistic activation, confidence-tracked. Bounded to (0, 1)."""
    c = _coerce(x, "sigmoid")
    if isinstance(c, Unknown):
        return _poison("sigmoid", [c])
    try:
        v = 1.0 / (1.0 + math.exp(-c.value))
    except OverflowError:
        v = 0.0 if c.value < 0 else 1.0
    except TypeError as exc:
        return Unknown(MALFORMED, f"sigmoid: {exc}")
    return C._derived(v, c.confidence, "sigmoid", [c])


def mse(predicted: Iterable[Union[C, Unknown, int, float]],
        actual: Iterable[Union[C, Unknown, int, float]]) -> Union[C, Unknown]:
    """Mean squared error, confidence-tracked. If one label was never
    recorded, the result is Unknown: a model can't honestly claim to have
    learned from data it didn't have.

    >>> mse([C(0.9), C(0.2), C(0.6)], [C(1), C(0), C(1)])
    C(0.07, confidence=256)
    >>> mse([C(0.9), C(0.2), C(0.6)], [C(1), C(0), Unknown(MISSING_INPUT, "label 3 not recorded")])
    UNKNOWN(MISSING_INPUT: label 3 not recorded)
    """
    p = [_coerce(x, "mse") for x in predicted]
    a = [_coerce(x, "mse") for x in actual]
    if not p and not a:
        return Unknown(MISSING_INPUT, "mse of no points is not defined")
    if len(p) != len(a):
        return Unknown(MALFORMED,
                       f"predicted and actual differ in length ({len(p)} vs {len(a)})")
    unknowns = [x for x in p + a if isinstance(x, Unknown)]
    if unknowns:
        return _poison("mse", unknowns)
    try:
        sq = [(pi.value - ai.value) ** 2 for pi, ai in zip(p, a)]
    except OverflowError:
        return Unknown(OUT_OF_RANGE, "mse: a squared error is too large to represent")
    except TypeError as exc:
        return Unknown(MALFORMED, f"mse: these values cannot be combined ({exc})")
    try:
        mean = sum(sq) / len(sq)
    except OverflowError:
        return Unknown(OUT_OF_RANGE, "mse: the mean is too large to represent")
    if not math.isfinite(mean):
        return Unknown(OUT_OF_RANGE, "mse: the result is not a finite number")
    return C._derived(mean, cmin_conf(p + a), "mse", p + a)


__all__ = [
    "C", "Unknown", "LowConfidenceError", "REASONS",
    "csum", "cmean", "cmin_conf", "agree", "corroborate", "sigmoid", "mse",
    "CERTAIN", "INTAKE", "AGREE", "FLOOR",
    "MISSING_INPUT", "CONFLICTING_SOURCES", "BELOW_THRESHOLD", "TIMEOUT",
    "OUT_OF_RANGE", "UNVERIFIED_SOURCE", "MALFORMED",
    "NOT_RECORDED", "LITERAL_SOURCE",
    "__version__",
]
