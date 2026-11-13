"""Core arithmetic, comparison, aggregates and the module's own examples.

Stdlib only (unittest), so the library's tests need no install. Replaces the
pytest file of 0.1.0: `UNKNOWN` (a singleton with no reason) is gone, and
`unwrap(default=None)` is gone because it returned a null. Each old test's
intent is kept here with the new API.
"""

import doctest
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import everconf  # noqa: E402
from everconf import (C, Unknown, LowConfidenceError, csum, cmean, cmin_conf,  # noqa: E402
                      sigmoid, mse, CERTAIN, INTAKE, FLOOR, MISSING_INPUT,
                      OUT_OF_RANGE, MALFORMED, BELOW_THRESHOLD)


class Construction(unittest.TestCase):
    def test_literal_is_certain(self):
        self.assertEqual(C(42).confidence, CERTAIN)

    def test_confidence_clamped_to_range(self):
        self.assertEqual(C(1, confidence=999).confidence, CERTAIN)
        self.assertEqual(C(1, confidence=-50).confidence, 0)

    def test_null_is_not_a_value(self):
        with self.assertRaises(TypeError) as cm:
            C(None)
        self.assertIn("Unknown(code, reason)", str(cm.exception))

    def test_nan_and_infinity_are_not_values(self):
        with self.assertRaises(ValueError):
            C(float("nan"))
        with self.assertRaises(ValueError):
            C(float("inf"))

    def test_booleans_are_not_confidence(self):
        with self.assertRaises(TypeError):
            C(1, confidence=True)

    def test_constants(self):
        self.assertEqual((CERTAIN, INTAKE, FLOOR), (256, 120, 128))
        self.assertEqual(everconf.AGREE, 180)


class Arithmetic(unittest.TestCase):
    def test_add_values(self):
        self.assertEqual((C(2) + C(3)).value, 5)

    def test_sub_mul_div(self):
        self.assertEqual((C(10) - C(4)).value, 6)
        self.assertEqual((C(3) * C(4)).value, 12)
        self.assertEqual((C(9) / C(2)).value, 4.5)

    def test_division_by_zero_is_out_of_range_not_an_exception(self):
        r = C(1) / C(0)
        self.assertIsInstance(r, Unknown)
        self.assertEqual(r.code, OUT_OF_RANGE)
        self.assertIn("division by zero", r.reason)

    def test_overflow_is_out_of_range(self):
        r = C(10.0) ** C(400)
        self.assertIsInstance(r, Unknown)
        self.assertEqual(r.code, OUT_OF_RANGE)

    def test_pow_and_neg(self):
        self.assertEqual((C(2) ** C(10)).value, 1024)
        self.assertEqual((-C(5)).value, -5)

    def test_coerces_plain_numbers(self):
        self.assertEqual((C(2) + 3).value, 5)
        self.assertEqual((3 + C(2)).value, 5)
        self.assertEqual((10 - C(4)).value, 6)
        self.assertEqual((2 * C(4)).value, 8)
        self.assertEqual((8 / C(4)).value, 2)
        self.assertEqual((2 ** C(3)).value, 8)

    def test_uncoercible_types_raise(self):
        with self.assertRaises(TypeError):
            C(1) + object()

    def test_text_and_number_is_malformed_not_a_crash(self):
        r = C("a") + C(1)
        self.assertIsInstance(r, Unknown)
        self.assertEqual(r.code, MALFORMED)

    def test_confidence_is_min_of_operands(self):
        self.assertEqual((C(1, 120) + C(1, 200)).confidence, 120)
        self.assertEqual((C(1, 256) * C(2, 100)).confidence, 100)

    def test_confidence_never_increases_through_arithmetic(self):
        x = C(3, 90)
        for other in (C(1), C(1, 256), 7):
            self.assertLessEqual((x + other).confidence, 90)

    def test_one_unknown_poisons_a_long_chain(self):
        total = C(1)
        for i in range(50):
            total = total + C(i)
        total = total + Unknown(MISSING_INPUT, "late input")
        for _ in range(50):
            total = total * C(2)
        self.assertIsInstance(total, Unknown)
        self.assertEqual(total.code, MISSING_INPUT)

    def test_unknown_poisons_regardless_of_position(self):
        u = Unknown(MISSING_INPUT, "gap")
        self.assertIsInstance(C(5) + u, Unknown)
        self.assertIsInstance(u + C(5), Unknown)
        self.assertIsInstance(5 - u, Unknown)


class Comparison(unittest.TestCase):
    def test_explicit_comparisons_return_c_bool(self):
        self.assertEqual(C(3).lt(C(5)).value, True)
        self.assertEqual(C(3).gt(C(5)).value, False)
        self.assertEqual(C(3).le(3).value, True)
        self.assertEqual(C(3).ge(4).value, False)
        self.assertEqual(C(3).eq(3).value, True)
        self.assertEqual(C(3).ne(3).value, False)

    def test_comparison_confidence_propagates(self):
        self.assertEqual(C(3, 100).lt(C(5, 200)).confidence, 100)

    def test_comparison_with_unknown_is_unknown(self):
        self.assertIsInstance(C(3).lt(Unknown(MISSING_INPUT, "x")), Unknown)

    def test_python_equality_compares_value_only(self):
        self.assertEqual(C(5, 10), C(5, 256))
        self.assertNotEqual(C(5), C(6))

    def test_unknown_has_no_truth_value(self):
        with self.assertRaises(TypeError):
            bool(Unknown(MISSING_INPUT, "x"))
        self.assertTrue(bool(C(1)))


class Requirement(unittest.TestCase):
    def test_require_returns_value_at_or_above_threshold(self):
        self.assertEqual(C(7, 128).require(128), 7)
        self.assertEqual(C(7).require(), 7)

    def test_require_raises_below_threshold_with_reason(self):
        with self.assertRaises(LowConfidenceError) as cm:
            C(7, 120).require(min_confidence=128)
        self.assertEqual(cm.exception.code, BELOW_THRESHOLD)
        self.assertEqual(cm.exception.confidence, 120)
        self.assertEqual(cm.exception.threshold, 128)

    def test_require_on_unknown_raises_with_its_code(self):
        with self.assertRaises(LowConfidenceError) as cm:
            Unknown(MISSING_INPUT, "no label").require(0)
        self.assertEqual(cm.exception.code, MISSING_INPUT)
        self.assertEqual(cm.exception.confidence, 0)

    def test_threshold_is_validated(self):
        with self.assertRaises(ValueError):
            C(1).require(300)
        with self.assertRaises(TypeError):
            C(1).require(0.5)


class Aggregates(unittest.TestCase):
    def test_csum_all_present(self):
        self.assertEqual(csum([C(1), C(2, 120), 3]).value, 6)
        self.assertEqual(csum([C(1), C(2, 120), 3]).confidence, 120)

    def test_csum_one_unknown_poisons_total_and_keeps_reason(self):
        r = csum([C(1), Unknown(MISSING_INPUT, "gap"), C(3)])
        self.assertIsInstance(r, Unknown)
        self.assertEqual(r.reason, "gap")

    def test_csum_empty_is_zero(self):
        self.assertEqual(csum([]).value, 0)

    def test_cmean(self):
        self.assertEqual(cmean([C(1), C(2), C(3)]).value, 2)

    def test_cmean_empty_is_missing_input(self):
        r = cmean([])
        self.assertIsInstance(r, Unknown)
        self.assertEqual(r.code, MISSING_INPUT)

    def test_cmean_one_unknown_poisons_it(self):
        self.assertIsInstance(cmean([C(1), Unknown(MISSING_INPUT, "x")]), Unknown)

    def test_cmin_conf(self):
        self.assertEqual(cmin_conf([C(1, 200), C(2, 120)]), 120)
        self.assertEqual(cmin_conf([]), 0)
        self.assertEqual(cmin_conf([C(1), Unknown(MISSING_INPUT, "x")]), 0)

    def test_sigmoid_zero_is_half(self):
        self.assertAlmostEqual(sigmoid(0).value, 0.5)

    def test_sigmoid_saturates_without_overflow(self):
        self.assertAlmostEqual(sigmoid(1000).value, 1.0)
        self.assertAlmostEqual(sigmoid(-1000).value, 0.0)

    def test_sigmoid_preserves_confidence(self):
        self.assertEqual(sigmoid(C(0, 99)).confidence, 99)

    def test_sigmoid_of_unknown_is_unknown(self):
        self.assertIsInstance(sigmoid(Unknown(MISSING_INPUT, "x")), Unknown)

    def test_mse_matches_hand_computation(self):
        r = mse([C(0.9), C(0.2), C(0.6)], [C(1), C(0), C(1)])
        self.assertAlmostEqual(r.value, (0.01 + 0.04 + 0.16) / 3)
        self.assertEqual(r.confidence, CERTAIN)

    def test_mse_one_unmeasured_label_voids_the_metric(self):
        r = mse([C(0.9), C(0.2), C(0.6)],
                [C(1), C(0), Unknown(MISSING_INPUT, "label 3 never recorded")])
        self.assertIsInstance(r, Unknown)
        self.assertEqual(r.reason, "label 3 never recorded")

    def test_mse_confidence_is_min_across_both_lists(self):
        r = mse([C(1, 200), C(2, 256)], [C(1, 256), C(2, 90)])
        self.assertEqual(r.confidence, 90)

    def test_mse_length_mismatch_is_malformed_not_a_crash(self):
        r = mse([C(1)], [C(1), C(2)])
        self.assertIsInstance(r, Unknown)
        self.assertEqual(r.code, MALFORMED)

    def test_mse_empty_is_missing_input(self):
        r = mse([], [])
        self.assertIsInstance(r, Unknown)
        self.assertEqual(r.code, MISSING_INPUT)


class ModuleExamples(unittest.TestCase):
    def test_module_docstring_examples_run(self):
        failures, _ = doctest.testmod(everconf, verbose=False)
        self.assertEqual(failures, 0)

    def test_submodule_docstring_examples_run(self):
        import everconf.reads as reads
        import everconf.result as result
        for mod in (reads, result):
            failures, _ = doctest.testmod(mod, verbose=False)
            self.assertEqual(failures, 0, mod.__name__)


if __name__ == "__main__":
    unittest.main(verbosity=1)
