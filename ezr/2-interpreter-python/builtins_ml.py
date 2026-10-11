#!/usr/bin/env python3
"""
builtins_ml.py — sigmoid, MSE, and the primitives that let them mean
something in a language where every value carries a trust level.

WHY THESE AREN'T JUST FUNCTIONS

A sigmoid or an MSE dropped into any other language is a pure number
cruncher: feed it floats, get a float back, and if half your training
set is missing data, you get a plausible-looking wrong answer, silently.
That is exactly the failure Ever exists to prevent.

So every primitive here follows the same two rules as the rest of the
language:
  1. z is contagious. If one input is genuinely unmeasured, the model
     built from it does not get to claim a number — the whole
     computation is z, not a number computed from a stand-in.
  2. Confidence is honest. dot() and mse() are aggregates: their
     result is only as trustworthy as the LEAST trustworthy element
     that went into it, same rule as list/record construction.

Concretely: if one label in a training set was never recorded, `mse`
over that set is z — not "the mse of the 9 points we did have." A
model trained on partly-unmeasured data does not get to report a loss
number as if it learned from all of it.

Codric Enterprise · Ricky (Dreid) · 2026
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

from evalue import EValue, EvType


@dataclass(frozen=True)
class Builtin:
    arity: int
    # (args: List[EValue]) -> EValue
    call: Callable[[List[EValue]], EValue]
    # (args: List[EValue], confs: List[int]) -> int
    conf: Callable[[List[EValue], List[int]], int]
    doc: str


def _num(v: EValue) -> Optional[float]:
    if v.ev_tag == EvType.INT:  return float(v.ev_int)
    if v.ev_tag == EvType.REAL: return v.ev_real
    return None


def _list_of_nums(v: EValue) -> Optional[List[float]]:
    if v.ev_tag != EvType.LIST:
        return None
    out = []
    for item in v.ev_list:
        n = _num(item)
        if n is None:
            return None
        out.append(n)
    return out


# ═══════════════════════════════════════════════
# exp — foundation for sigmoid
# ═══════════════════════════════════════════════

def _exp_call(args: List[EValue]) -> EValue:
    x = _num(args[0])
    if x is None:
        return EValue.void()
    try:
        return EValue.from_real(math.exp(x))
    except OverflowError:
        return EValue.void()

def _exp_conf(args: List[EValue], confs: List[int]) -> int:
    if _num(args[0]) is None:
        return 0
    return confs[0]


# ═══════════════════════════════════════════════
# sigmoid — the activation. 1 / (1 + e^-x)
#
# Bounded to (0, 1) by construction — the same shape as a normalized
# confidence value, which is precisely why this function belongs in
# a trust-tracking language rather than a coincidence worth ignoring.
# ═══════════════════════════════════════════════

def _sigmoid_call(args: List[EValue]) -> EValue:
    x = _num(args[0])
    if x is None:
        return EValue.void()
    try:
        return EValue.from_real(1.0 / (1.0 + math.exp(-x)))
    except OverflowError:
        return EValue.from_real(0.0 if x < 0 else 1.0)

def _sigmoid_conf(args: List[EValue], confs: List[int]) -> int:
    if _num(args[0]) is None:
        return 0
    # a pure transform of one input: it can be no more certain than
    # the value it was handed, and squashing it doesn't manufacture
    # additional trust
    return confs[0]


# ═══════════════════════════════════════════════
# dot — weighted sum. The one operation every linear model is built
# from: dot(weights, inputs) is a single neuron's pre-activation.
# ═══════════════════════════════════════════════

def _dot_call(args: List[EValue]) -> EValue:
    a, b = _list_of_nums(args[0]), _list_of_nums(args[1])
    if a is None or b is None or len(a) != len(b):
        return EValue.void()
    return EValue.from_real(sum(x * y for x, y in zip(a, b)))

def _dot_conf(args: List[EValue], confs: List[int]) -> int:
    a, b = args[0], args[1]
    if a.ev_tag != EvType.LIST or b.ev_tag != EvType.LIST:
        return 0
    if len(a.ev_list) != len(b.ev_list) or len(a.ev_list) == 0:
        return 0
    if _list_of_nums(a) is None or _list_of_nums(b) is None:
        return 0
    pair_confs = [min(x.confidence, y.confidence)
                 for x, y in zip(a.ev_list, b.ev_list)]
    return min(pair_confs)


# ═══════════════════════════════════════════════
# mse — mean squared error. predicted and actual must be equal-length
# numeric lists. Any unmeasured PAIR poisons the whole figure — a loss
# number computed by skipping the point you couldn't measure is a
# number about a dataset you didn't have, not the one you claimed.
# ═══════════════════════════════════════════════

def _mse_call(args: List[EValue]) -> EValue:
    p, a = _list_of_nums(args[0]), _list_of_nums(args[1])
    if p is None or a is None or len(p) != len(a) or len(p) == 0:
        return EValue.void()
    sq = [(pi - ai) ** 2 for pi, ai in zip(p, a)]
    return EValue.from_real(sum(sq) / len(sq))

def _mse_conf(args: List[EValue], confs: List[int]) -> int:
    p, a = args[0], args[1]
    if p.ev_tag != EvType.LIST or a.ev_tag != EvType.LIST:
        return 0
    if len(p.ev_list) != len(a.ev_list) or len(p.ev_list) == 0:
        return 0
    if _list_of_nums(p) is None or _list_of_nums(a) is None:
        return 0
    pair_confs = [min(x.confidence, y.confidence)
                 for x, y in zip(p.ev_list, a.ev_list)]
    return min(pair_confs)


BUILTINS: dict = {
    "exp":     Builtin(1, _exp_call,     _exp_conf,
                       "e raised to the power of x"),
    "sigmoid": Builtin(1, _sigmoid_call, _sigmoid_conf,
                       "the logistic activation, squashed to (0, 1)"),
    "dot":     Builtin(2, _dot_call,     _dot_conf,
                       "the dot product of two equal-length lists"),
    "mse":     Builtin(2, _mse_call,     _mse_conf,
                       "mean squared error between predicted and actual"),
}
