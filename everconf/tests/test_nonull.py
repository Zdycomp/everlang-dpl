"""The No-Null Standard, proved at the library's boundaries.

* an Unknown is well-formed or it cannot be built (code, reason, confidence 0)
* poisoning carries the origin's code and reason through nested math
* the reason chain survives serialisation, byte for byte
* a seeded fuzz over operations and reads never yields None, NaN or an
  empty value, and never raises where the spec says it must return an Unknown
"""

import json
import math
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from everconf import (C, Unknown, csum, cmean, mse, corroborate, agree,  # noqa: E402
                      sigmoid, MISSING_INPUT, TIMEOUT, UNVERIFIED_SOURCE,
                      CONFLICTING_SOURCES, MALFORMED, OUT_OF_RANGE, CERTAIN, INTAKE)
from everconf.reads import wrap_read  # noqa: E402
from everconf.result import to_result  # noqa: E402
from everconf.reasons import REASONS  # noqa: E402
from everconf.adapter import handle  # noqa: E402


def no_null(value, where="$"):
    """Fail on None, NaN or infinity anywhere in a JSON-shaped value."""
    if value is None:
        raise AssertionError(f"null at {where}")
    if isinstance(value, float) and not math.isfinite(value):
        raise AssertionError(f"non-finite number at {where}")
    if isinstance(value, dict):
        for k, v in value.items():
            no_null(v, f"{where}.{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            no_null(v, f"{where}[{i}]")


class UnknownIsWellFormed(unittest.TestCase):
    def test_requires_a_registry_code(self):
        for bad in ("NULL", "missing", "", None, "MISSING_INPUT "):
            with self.assertRaises(ValueError, msg=repr(bad)):
                Unknown(bad, "a reason")

    def test_a_note_code_cannot_be_an_unknown(self):
        with self.assertRaises(ValueError):
            Unknown("GROUNDED", "a reason")

    def test_requires_a_human_reason(self):
        for bad in ("", "   ", None, 42):
            with self.assertRaises(ValueError, msg=repr(bad)):
                Unknown(MISSING_INPUT, bad)

    def test_confidence_is_always_zero_and_there_is_no_value(self):
        u = Unknown(TIMEOUT, "the feed did not answer")
        self.assertEqual(u.confidence, 0)
        self.assertTrue(u.is_unknown)
        self.assertFalse(hasattr(u, "value"))

    def test_every_registry_unknown_code_is_accepted(self):
        for code, (kind, _) in REASONS.items():
            if kind == "unknown":
                self.assertEqual(Unknown(code, "x").code, code)


class PoisoningCarriesReasons(unittest.TestCase):
    def test_origin_code_and_reason_survive_nested_math(self):
        origin = Unknown(MISSING_INPUT, "label 3 was never recorded")
        expr = ((C(1) + origin) * C(2) - C(3)) / C(4)
        self.assertIsInstance(expr, Unknown)
        self.assertEqual(expr.code, MISSING_INPUT)
        self.assertEqual(expr.reason, "label 3 was never recorded")
        self.assertGreaterEqual(len(expr.chain), 3)
        self.assertTrue(any("add" in step for step in expr.chain))
        self.assertTrue(any("div" in step for step in expr.chain))

    def test_two_unknowns_keep_both_and_the_first_is_the_origin(self):
        a = Unknown(TIMEOUT, "feed A timed out")
        b = Unknown(UNVERIFIED_SOURCE, "feed B unverified")
        r = a + b
        self.assertEqual(r.code, TIMEOUT)
        self.assertTrue(any("UNVERIFIED_SOURCE" in step and "feed B" in step for step in r.chain))

    def test_aggregates_keep_the_chain(self):
        r = csum([C(1), Unknown(TIMEOUT, "slow"), C(2)])
        self.assertEqual(r.code, TIMEOUT)
        r = cmean([C(1), Unknown(TIMEOUT, "slow")])
        self.assertEqual(r.code, TIMEOUT)
        self.assertIn("poisoned", " ".join(r.chain))

    def test_mse_keeps_its_gap(self):
        r = mse([C(1)], [Unknown(MISSING_INPUT, "label never recorded")])
        self.assertEqual(r.reason, "label never recorded")

    def test_sigmoid_keeps_its_reason(self):
        r = sigmoid(Unknown(OUT_OF_RANGE, "overflow upstream"))
        self.assertEqual(r.code, OUT_OF_RANGE)

    def test_operations_that_cannot_answer_name_their_code(self):
        self.assertEqual((C(1) / C(0)).code, OUT_OF_RANGE)
        self.assertEqual(cmean([]).code, MISSING_INPUT)
        self.assertEqual(mse([C(1)], [C(1), C(2)]).code, MALFORMED)
        self.assertEqual(agree(C(1), C(2)).code, CONFLICTING_SOURCES)

    def test_nan_from_arithmetic_is_out_of_range(self):
        r = C(1e308) * C(1e308)
        self.assertIsInstance(r, Unknown)
        self.assertEqual(r.code, OUT_OF_RANGE)


class ReasonChainSurvivesSerialisation(unittest.TestCase):
    def test_unknown_round_trips_through_json(self):
        r = (C(1) + Unknown(MISSING_INPUT, "no fee schedule")) * C(2)
        wire = json.dumps(r.to_dict(), sort_keys=True)
        back = Unknown.from_dict(json.loads(wire))
        self.assertEqual(back, r)
        self.assertEqual(back.chain, r.chain)
        self.assertEqual(json.dumps(back.to_dict(), sort_keys=True), wire)

    def test_from_dict_refuses_a_known_value(self):
        with self.assertRaises(ValueError):
            Unknown.from_dict({"state": "known", "code": "MISSING_INPUT", "reason": "x"})

    def test_result_shape_keeps_the_chain_on_the_wire(self):
        r = csum([C(1), Unknown(TIMEOUT, "slow feed")])
        wire = json.loads(json.dumps(to_result(r)))
        self.assertEqual(wire["reasons"][0], {"code": "TIMEOUT", "reason": "slow feed"})
        self.assertEqual(wire["chain"], list(r.chain))
        no_null(wire)


class Corroboration(unittest.TestCase):
    def test_two_intake_sources_that_agree_reach_agree(self):
        self.assertEqual(corroborate(C("x", INTAKE), C("x", INTAKE)).confidence, 180)

    def test_certain_agreement_stays_certain(self):
        self.assertEqual(corroborate(C("x"), C("x")).confidence, CERTAIN)

    def test_a_weak_source_does_not_lift(self):
        self.assertEqual(corroborate(C("x", 100), C("x", 200)).confidence, 100)

    def test_disagreement_is_an_unknown_not_a_pick(self):
        r = corroborate(C("tenant"), C("landlord"))
        self.assertEqual(r.code, CONFLICTING_SOURCES)
        self.assertIn("tenant", r.reason)

    def test_never_above_certain(self):
        self.assertLessEqual(corroborate(C(1, 256), C(1, 256)).confidence, CERTAIN)


class FuzzNoNullEscapes(unittest.TestCase):
    """Seeded, so the same run happens every time."""

    def _random_scalar(self, rng):
        return rng.choice([0, 1, -3, 2.5, 1e308, "text", "", True, False])

    def _random_value(self, rng):
        k = rng.random()
        if k < 0.6:
            return C(self._random_scalar(rng) if rng.random() < 0.9 else rng.randint(-5, 5),
                     rng.randint(0, CERTAIN))
        if k < 0.8:
            return Unknown(rng.choice([MISSING_INPUT, TIMEOUT, OUT_OF_RANGE, MALFORMED]),
                           f"fuzz reason {rng.randint(0, 999)}")
        return rng.randint(-9, 9)

    def test_operations_never_return_null_or_raise_unexpectedly(self):
        rng = random.Random(20261113)
        ops = [lambda a, b: a + b, lambda a, b: a - b, lambda a, b: a * b,
               lambda a, b: a / b, lambda a, b: a ** b, lambda a, b: a.lt(b),
               lambda a, b: csum([a, b]), lambda a, b: mse([a], [b]),
               lambda a, b: corroborate(a, b), lambda a, b: agree(a, b)]
        for _ in range(1500):
            a = self._random_value(rng)
            b = self._random_value(rng)
            a = a if isinstance(a, (C, Unknown)) else C(a)
            b = b if isinstance(b, (C, Unknown)) else C(b)
            op = rng.choice(ops)
            try:
                r = op(a, b)
            except TypeError:
                # only the documented refusal: a non-number operand, not a value
                continue
            self.assertIsNotNone(r)
            if isinstance(r, C):
                self.assertIsNotNone(r.value)
                self.assertFalse(isinstance(r.value, float) and not math.isfinite(r.value))
            else:
                self.assertIsInstance(r, Unknown)
                self.assertTrue(r.reason)
            no_null(to_result(r, notes=[("DERIVED", "fuzz")]) if isinstance(r, C)
                    else to_result(r))

    def test_reads_never_return_null_for_hostile_input(self):
        rng = random.Random(7)
        junk = [None, 0, "", [], {}, {"findings": None}, {"findings": [None]},
                {"findings": [{"quote": None}]}, {"findings": [{"quote": "", "category": "x"}]},
                {"findings": [{"quote": "nope", "category": "x"}]}]
        for _ in range(300):
            kind = rng.choice(["clause", "tone", "motive", "bogus", None])
            doc = rng.choice(["", "   ", "Pay within 24 hours or else.", None, 5])
            answer = rng.choice(junk)
            env = wrap_read(kind, doc, answer)
            no_null(env)
            self.assertIn("overall", env)

    def test_adapter_never_returns_null_for_hostile_bodies(self):
        rng = random.Random(11)
        bodies = [None, 1, "x", [], {}, {"kind": "clause"}, {"kind": "clause", "answer": {}},
                  {"kind": "clause", "document": "x", "answer": {"findings": 3}},
                  {"kind": "tone", "document": "x", "answer": {}, "at": ""}]
        for _ in range(100):
            bodies.append({"kind": rng.choice(["clause", "tone", "x"]),
                           "document": rng.choice(["", "a b c", None]),
                           "answer": {"risk_tier": rng.choice([None, "", "HIGH"]),
                                      "overall_risk_score": rng.choice([None, 200, 50]),
                                      "findings": [{"quote": rng.choice([None, "a"]),
                                                    "category": rng.choice([None, "", "k"])}]}})
        for body in bodies:
            status, reply = handle(body)
            self.assertIn(status, (200, 400))
            no_null(reply)


if __name__ == "__main__":
    unittest.main(verbosity=1)
