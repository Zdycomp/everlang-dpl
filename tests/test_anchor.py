"""Examples and anchors through the real front door (SEMANTICS §4, §8).

Every row of the §8 worked example is asserted against `run_source`, which is
the language's own entry point: parser, Semantic pass, evaluator. Each rule of
§4 that §8 does not exercise has its own case: refusal of an uncleared
function, refusal of a recursive function with no measure (ANCHOR-⊥), Examples
that count against a function, a refused anchor that cannot be revived, and the
static checks on the two new statements.
"""

import math
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
for _path in (_HERE, os.path.join(_HERE, '..', '2-interpreter-python')):
    sys.path.insert(0, os.path.abspath(_path))

from evalue import EvType
from runtime import run_source

FACT = "def fact(n) = if n <= 1 then 1 else n * fact(n - 1)\n"
EXAMPLES_123 = ("example fact(1) = 1\n"
                "example fact(2) = 2\n"
                "example fact(3) = 6\n")


def shown(result, name):
    """The ShownValue for `show name`."""
    found = [sv for sv in result.shown if sv.name == name]
    assert len(found) == 1, f"expected one show of {name}, got {len(found)}"
    return found[0]


class SectionEightTest(unittest.TestCase):
    """SEMANTICS §8, row by row, as one .ever program per row."""

    def test_definition_begins_at_intake_with_its_measure(self):
        # [DEF]: a thread at 120/256, recursive, measure n found
        r = run_source(FACT)
        e = r.scope.lookup("fact")
        self.assertEqual(e.confidence, 120)
        self.assertTrue(e.recursive)
        self.assertEqual(e.measure, "n")
        self.assertEqual(e.anchor_id, 0)

    def test_fact_three_is_within_the_ceiling(self):
        # fact(3) = 6: depth 3, within floor(pi)
        r = run_source(FACT + "let a = fact(3)\nshow a\n")
        self.assertEqual(r.errors, [])
        self.assertEqual(shown(r, "a").value.ev_int, 6)

    def test_fact_eight_is_blocked_at_the_ceiling(self):
        # fact(8): DepthExceeded at ceiling 3, so z
        r = run_source(FACT + "let b = fact(8)\nshow b\n")
        self.assertEqual(shown(r, "b").value.ev_tag, EvType.VOID)

    def test_three_examples_earn_217(self):
        # Examples (1,1) (2,2) (3,6): 217/256 by [EXAMPLE]
        r = run_source(FACT + EXAMPLES_123 + "let c = fact(3)\nshow c\n")
        e = r.scope.lookup("fact")
        self.assertEqual((e.examples_passed, e.examples_failed), (3, 0))
        self.assertEqual(e.confidence, 217)
        # every value returns at 217/256, the function's floor
        self.assertEqual(shown(r, "c").value.ev_int, 6)
        self.assertEqual(shown(r, "c").confidence, 217)

    def test_anchor_lets_fact_one_hundred_compute(self):
        # [ANCHOR-REC]: anchored, depth := infinity on measure n
        # fact(100) computes at depth 99
        r = run_source(FACT + EXAMPLES_123 + "anchor fact\nlet d = fact(100)\nshow d\n")
        self.assertEqual(r.errors, [])
        e = r.scope.lookup("fact")
        self.assertNotEqual(e.anchor_id, 0)
        self.assertEqual(e.measure, "n")
        self.assertEqual(shown(r, "d").value.ev_int, math.factorial(100))
        self.assertEqual(shown(r, "d").confidence, 217)


class AnchorRulesTest(unittest.TestCase):
    """The rules of §4 that the §8 example does not reach."""

    def test_a_measure_and_examples_do_not_anchor(self):
        # the measure is a termination fact; depth is earned by `anchor`
        r = run_source(FACT + EXAMPLES_123 + "let b = fact(8)\nshow b\n")
        self.assertEqual(r.scope.lookup("fact").anchor_id, 0)
        self.assertEqual(shown(r, "b").value.ev_tag, EvType.VOID)

    def test_an_uncleared_function_refuses_its_anchor(self):
        # ANCHOR-FN needs cleared(θ_f): below the execute floor, refused
        r = run_source("def f(n) = n + 1\nanchor f\nlet v = f(1)\nshow v\n")
        e = r.scope.lookup("f")
        self.assertTrue(e.refused)
        self.assertEqual(e.reason, "cannot anchor an unverified function")
        self.assertEqual(e.anchor_id, 0)
        self.assertEqual(shown(r, "v").value.ev_tag, EvType.VOID)

    def test_a_recursive_function_with_no_measure_refuses_its_anchor(self):
        # ANCHOR-⊥: cleared, but recursion has no decreasing measure
        defn = ("def loop(n) = if n <= 0 then 0 else loop(n + 1)\n"
                "example loop(0) = 0\n"
                "example loop(0) = 0\n")
        # without the anchor, 2/2 Examples clear the floor at 183
        self.assertEqual(run_source(defn).scope.lookup("loop").confidence, 183)
        r = run_source(defn + "anchor loop\n")
        e = r.scope.lookup("loop")
        self.assertEqual(e.examples_passed, 2)
        self.assertTrue(e.refused)                   # the refusal leaves it z
        self.assertIn("confidence proves trust, not termination", e.reason)
        self.assertEqual(e.anchor_id, 0)

    def test_wrong_and_depth_exceeded_examples_count_against_it(self):
        # a wrong value and a call past the ceiling are both failures
        r = run_source(FACT + "example fact(3) = 7\nexample fact(8) = 40320\n")
        e = r.scope.lookup("fact")
        self.assertEqual((e.examples_passed, e.examples_failed), (0, 2))
        self.assertEqual(e.confidence, 0)

    def test_a_refused_function_is_not_revived_by_examples(self):
        src = ("def f(n) = n + 1\nanchor f\n"
               "example f(1) = 2\nexample f(2) = 3\n"
               "let v = f(1)\nshow v\n")
        r = run_source(src)
        e = r.scope.lookup("f")
        self.assertTrue(e.refused)
        self.assertEqual(e.examples_passed + e.examples_failed, 0)
        self.assertEqual(shown(r, "v").value.ev_tag, EvType.VOID)


class StaticChecksTest(unittest.TestCase):
    """The Semantic pass refuses what cannot be an Example or an anchor."""

    def test_example_arity_is_checked(self):
        r = run_source(FACT + "example fact(1, 2) = 1\n")
        self.assertIn("example fact takes 1 argument(s), got 2", r.errors)

    def test_example_of_an_unknown_function_is_refused(self):
        r = run_source("example nope(1) = 1\n")
        self.assertEqual(r.errors, ["example references unknown function 'nope'"])

    def test_anchor_of_an_unknown_function_is_refused(self):
        r = run_source("anchor nope\n")
        self.assertEqual(r.errors, ["anchor references unknown function 'nope'"])

    def test_the_equals_of_an_example_is_not_a_stray_comparison(self):
        # forgive.py rewrites a stray = to ==; an Example's = is legitimate
        r = run_source(FACT + "example fact(3) = 6\n")
        self.assertEqual(r.errors, [])
        self.assertEqual(r.scope.lookup("fact").examples_passed, 1)


if __name__ == "__main__":
    unittest.main()
