import unittest
from pathlib import Path

from everlang.core import algebra as A
from everlang.core.vocabulary import E_CERTAIN, E_EXECUTE_FLOOR, E_INTAKE

REPO = Path(__file__).resolve().parents[2]
EZR_RUNTIME = REPO / "ezr" / "2-interpreter-python" / "ezrun.py"

# (passed, total) -> ezr/ezrun.confidence_from_examples, pinned
EXAMPLE_VECTORS = [((0, 0), 0), ((1, 1), 120), ((2, 2), 183), ((2, 3), 122),
                   ((1, 3), 40), ((0, 2), 0), ((2, 5), 73), ((1, 9), 13), ((8, 8), 254)]
# (passed, total) -> ezr/ezrun.witnesses_needed(p, t, 128, 64), pinned
WITNESS_VECTORS = [((0, 0), 2), ((1, 1), 1), ((2, 2), 0), ((3, 3), 0), ((2, 3), 1),
                   ((1, 3), 2), ((0, 2), 3), ((2, 5), 2), ((1, 9), 8)]


class TestLaws(unittest.TestCase):
    def test_uncertainty_endpoints(self):
        self.assertEqual(A.uncertainty(0), 1.0)
        self.assertEqual(A.uncertainty(E_CERTAIN), 0.0)
        self.assertEqual(A.uncertainty(E_INTAKE), 136 / 256)

    def test_example_confidence_matches_ezr(self):
        for (p, t), want in EXAMPLE_VECTORS:
            with self.subTest(p=p, t=t):
                self.assertEqual(A.example_confidence(p, t), want)

    def test_example_confidence_is_capped_below_certain(self):
        self.assertLess(A.example_confidence(500, 500), E_CERTAIN)

    def test_repairs_to_floor(self):
        self.assertEqual(A.repairs_to_floor(0, 0), 256)
        self.assertEqual(A.repairs_to_floor(0, 4), E_EXECUTE_FLOOR)
        self.assertEqual(A.repairs_to_floor(0, 5), 96)
        self.assertEqual(A.repairs_to_floor(40, 40), 0)


class TestInverses(unittest.TestCase):
    def test_witnesses_needed_matches_ezr(self):
        for (p, t), want in WITNESS_VECTORS:
            with self.subTest(p=p, t=t):
                self.assertEqual(A.witnesses_needed(p, t), want)

    def test_witnesses_needed_is_the_least_sufficient_k(self):
        for p in range(6):
            for t in range(p, 9):
                k = A.witnesses_needed(p, t)
                if k is None:
                    continue
                self.assertGreaterEqual(A.example_confidence(p + k, t + k), E_EXECUTE_FLOOR)
                if k > 0:
                    self.assertLess(A.example_confidence(p + k - 1, t + k - 1), E_EXECUTE_FLOOR)

    def test_unreachable_target_is_none(self):
        self.assertIsNone(A.witnesses_needed(0, 9, target=E_CERTAIN, cap=64))

    def test_inferred_repairs_left(self):
        self.assertEqual(A.inferred_repairs_left(), 4)
        self.assertEqual(A.inferred_repairs_left(96), 0)

    def test_sources_still_needed(self):
        self.assertEqual(A.sources_still_needed(0), 3)
        self.assertEqual(A.sources_still_needed(3), 0)

    def test_pi_collapse_boundaries(self):
        self.assertEqual([A.pi_collapse(w) for w in (0, 25, 26, 81, 82)],
                         ["accept", "accept", "enumerate", "enumerate", "collapse"])

    def test_depth_limit(self):
        self.assertEqual(A.depth_limit(anchored=False, measure_defined=True), 3)
        self.assertEqual(A.depth_limit(anchored=True, measure_defined=False), 3)
        self.assertIsNone(A.depth_limit(anchored=True, measure_defined=True))


@unittest.skipUnless(EZR_RUNTIME.exists(), "ezr/ lineage not present")
class TestAgainstEzr(unittest.TestCase):
    def test_ezr_agrees_on_every_vector(self):
        import sys
        sys.path.insert(0, str(EZR_RUNTIME.parent))
        from ezrun import confidence_from_examples, witnesses_needed
        for (p, t), _ in EXAMPLE_VECTORS:
            self.assertEqual(A.example_confidence(p, t), confidence_from_examples(p, t))
        for (p, t), _ in WITNESS_VECTORS:
            self.assertEqual(A.witnesses_needed(p, t), witnesses_needed(p, t, E_EXECUTE_FLOOR, 64))


if __name__ == "__main__":
    unittest.main()
