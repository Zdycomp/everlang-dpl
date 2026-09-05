"""Tests for everconf. Every claim in the README and docstrings must
be provable here — nothing shipped on the strength of it "looking
right"."""

import math
import pytest
from everconf import (C, UNKNOWN, LowConfidenceError, csum, cmean,
                      cmin_conf, sigmoid, mse, CERTAIN, INTAKE, FLOOR)


# ── construction ──

def test_literal_is_certain():
    assert C(42).confidence == CERTAIN

def test_confidence_clamped_to_range():
    assert C(1, confidence=999).confidence == CERTAIN
    assert C(1, confidence=-50).confidence == 0

def test_unknown_is_a_singleton():
    assert C(None, confidence=0).is_unknown
    assert UNKNOWN is UNKNOWN
    from everconf import _UnknownType
    # not required to be the same object — every _UnknownType delegates
    # to a fresh C(None, confidence=0), so two instances are simply
    # equal, the same way two separately-built C(None) values are
    assert _UnknownType() == UNKNOWN
    assert (_UnknownType() + 1).is_unknown

def test_unknown_repr():
    assert repr(UNKNOWN) == "UNKNOWN"
    assert repr(C(None, confidence=0)) == "UNKNOWN"

def test_unknown_has_no_truth_value():
    with pytest.raises(TypeError):
        bool(UNKNOWN)
    with pytest.raises(TypeError):
        if UNKNOWN:
            pass


# ── arithmetic: value ──

def test_add_values():
    assert (C(2) + C(3)).value == 5

def test_sub_mul_div():
    assert (C(10) - C(3)).value == 7
    assert (C(4) * C(5)).value == 20
    assert (C(10) / C(4)).value == 2.5

def test_div_by_zero_is_unknown_not_an_exception():
    r = C(1) / C(0)
    assert r.is_unknown

def test_pow():
    assert (C(2) ** C(10)).value == 1024

def test_neg():
    assert (-C(5)).value == -5
    assert (-UNKNOWN).is_unknown

def test_coerces_plain_numbers():
    assert (C(5) + 3).value == 8
    assert (3 + C(5)).value == 8
    assert (2 * C(5)).value == 10

def test_coerces_unknown_sentinel_directly():
    assert (C(5) + UNKNOWN).is_unknown
    assert (UNKNOWN + C(5)).is_unknown

def test_unknown_is_symmetric_with_bare_numbers_too():
    # UNKNOWN + 5 must work exactly as reliably as 5 + UNKNOWN — both
    # sides of every operator, not just the side that happens to be a
    # C instance already.
    assert (UNKNOWN + 5).is_unknown
    assert (5 + UNKNOWN).is_unknown
    assert (UNKNOWN - 5).is_unknown
    assert (5 - UNKNOWN).is_unknown
    assert (UNKNOWN * 5).is_unknown
    assert (5 * UNKNOWN).is_unknown
    assert (UNKNOWN / 5).is_unknown
    assert (5 / UNKNOWN).is_unknown
    assert (-UNKNOWN).is_unknown

def test_unknown_supports_methods_directly_not_just_as_an_operand():
    # UNKNOWN.unwrap(), UNKNOWN.require(), UNKNOWN.eq(...) — called ON
    # UNKNOWN itself, not passed as an argument to a C method — must
    # behave identically to calling them on C(None, confidence=0).
    assert UNKNOWN.unwrap() is None
    assert UNKNOWN.unwrap(default=-1) == -1
    with pytest.raises(LowConfidenceError):
        UNKNOWN.require()
    assert UNKNOWN.eq(C(5)).is_unknown
    assert UNKNOWN.gt(C(5)).is_unknown
    assert UNKNOWN.is_unknown

def test_rejects_uncoercible_types():
    with pytest.raises(TypeError):
        C(5) + [1, 2, 3]


# ── arithmetic: confidence ──

def test_confidence_is_min_of_operands():
    a = C(10, confidence=256)
    b = C(20, confidence=120)
    assert (a + b).confidence == 120
    assert (a * b).confidence == 120
    assert (a - b).confidence == 120

def test_confidence_never_increases():
    low = C(1, confidence=50)
    high = C(1, confidence=256)
    for _ in range(5):
        low = low + high
    assert low.confidence == 50

def test_one_unknown_poisons_a_long_chain():
    total = C(1) + C(2) + C(3) + UNKNOWN + C(4) + C(5)
    assert total.is_unknown
    assert total.confidence == 0

def test_unknown_poisons_regardless_of_position():
    assert (UNKNOWN + C(1) + C(1)).is_unknown
    assert (C(1) + UNKNOWN + C(1)).is_unknown
    assert (C(1) + C(1) + UNKNOWN).is_unknown


# ── comparisons (explicit methods, not operator overload) ──

def test_explicit_comparisons():
    assert C(5).gt(C(3)).value is True
    assert C(5).lt(C(3)).value is False
    assert C(5).ge(C(5)).value is True
    assert C(5).eq(C(5)).value is True
    assert C(5).ne(C(3)).value is True

def test_comparison_confidence_propagates():
    a = C(5, confidence=200)
    b = C(3, confidence=90)
    assert a.gt(b).confidence == 90

def test_comparison_with_unknown_is_unknown():
    assert C(5).gt(UNKNOWN).is_unknown
    assert UNKNOWN.eq(C(5)).is_unknown

def test_python_equality_is_left_alone():
    # C(5) == C(5) must behave like ordinary Python equality
    # (needed for hashing/dict/set use), NOT confidence-tracked —
    # that's what .eq() is for.
    assert C(5, confidence=256) == C(5, confidence=1)
    assert C(5) != C(6)


# ── escape hatches ──

def test_unwrap_default():
    assert C(5).unwrap() == 5

def test_require_passes_above_floor():
    assert C(5, confidence=200).require(floor=128) == 5

def test_require_raises_below_floor():
    with pytest.raises(LowConfidenceError):
        C(5, confidence=50).require(floor=128)

def test_require_default_floor_is_the_module_constant():
    assert C(5, confidence=FLOOR).require() == 5
    with pytest.raises(LowConfidenceError):
        C(5, confidence=FLOOR - 1).require()


# ── aggregates ──

def test_csum_all_present():
    assert csum([C(1), C(2), C(3)]).value == 6

def test_csum_one_unknown_poisons_total():
    r = csum([C(1), C(2), UNKNOWN, C(3)])
    assert r.is_unknown

def test_csum_coerces_plain_numbers_and_sentinel():
    assert csum([1, 2, 3]).value == 6
    assert csum([1, UNKNOWN, 3]).is_unknown

def test_cmean():
    r = cmean([C(2), C(4), C(6)])
    assert r.value == 4
    assert r.confidence == CERTAIN

def test_cmean_empty_is_unknown():
    assert cmean([]).is_unknown

def test_cmean_one_unknown_poisons_it():
    assert cmean([C(1), UNKNOWN]).is_unknown

def test_cmin_conf():
    items = [C(1, confidence=200), C(2, confidence=90), C(3, confidence=256)]
    assert cmin_conf(items) == 90

def test_cmin_conf_empty():
    assert cmin_conf([]) == 0


# ── sigmoid ──

def test_sigmoid_zero_is_half():
    assert sigmoid(0).value == pytest.approx(0.5)

def test_sigmoid_large_positive_saturates_near_one():
    assert sigmoid(100).value == pytest.approx(1.0, abs=1e-6)

def test_sigmoid_large_negative_saturates_near_zero():
    assert sigmoid(-100).value == pytest.approx(0.0, abs=1e-6)

def test_sigmoid_never_overflows():
    # must not raise even at extreme magnitude
    r = sigmoid(-10000)
    assert r.value == 0.0

def test_sigmoid_preserves_input_confidence():
    r = sigmoid(C(2, confidence=140))
    assert r.confidence == 140

def test_sigmoid_of_unknown_is_unknown():
    assert sigmoid(UNKNOWN).is_unknown


# ── mse — the headline demo, verified precisely ──

def test_mse_matches_hand_computation():
    preds   = [C(0.9), C(0.2), C(0.6)]
    actuals = [C(1),   C(0),   C(1)]
    expect  = ((0.9-1)**2 + (0.2-0)**2 + (0.6-1)**2) / 3
    r = mse(preds, actuals)
    assert r.value == pytest.approx(expect)

def test_mse_one_unmeasured_label_voids_the_whole_metric():
    preds   = [C(0.9), C(0.2), C(0.6)]
    actuals = [C(1), C(0), UNKNOWN]
    r = mse(preds, actuals)
    assert r.is_unknown, (
        "the one claim this library exists to prove: a metric "
        "computed over partly-missing data must not silently "
        "become a metric over the data you happened to have")

def test_mse_confidence_is_min_across_both_lists():
    preds   = [C(0.9, confidence=256), C(0.2, confidence=90)]
    actuals = [C(1.0, confidence=256), C(0.0, confidence=256)]
    r = mse(preds, actuals)
    assert r.confidence == 90

def test_mse_length_mismatch_is_unknown_not_a_crash():
    assert mse([C(1), C(2)], [C(1)]).is_unknown

def test_mse_empty_is_unknown():
    assert mse([], []).is_unknown


# ── module constants match what the README will claim ──

def test_constants():
    assert CERTAIN == 256
    assert 0 < INTAKE < FLOOR < CERTAIN
