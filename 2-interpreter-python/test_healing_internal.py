import os
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
for _path in (_HERE, os.path.join(_HERE, '..', '2-interpreter-python')):
    sys.path.insert(0, os.path.abspath(_path))

from ever import E_CERTAIN, E_INTAKE, e_val
from repair import E_REPAIR_PLAIN, RepairRegistry, use_registry
from runtime import run_source
from syntax import BinOp, Call, Heal, Num, Semantic, Str, eval_ast, parse


class _Archive:
    """Points the evaluators at an in-memory archive for one test. The
    repo's shared 7-refix-node file is never read or written."""

    def __init__(self, records):
        self.records = records

    def __enter__(self):
        self._dir = tempfile.TemporaryDirectory()
        self.registry = RepairRegistry(archive_dir=self._dir.name)
        self.registry.repairs = list(self.records)
        use_registry(self.registry)
        return self.registry

    def __exit__(self, *exc):
        use_registry(None)
        self._dir.cleanup()


DIVIDE_BY_ZERO = {"failure_text": "division by zero", "fixture_text": "1", "kind": 0}


class TestHealing(unittest.TestCase):
    def test_heal_success(self):
        # heal (10) using ("strategy") fallback (1)
        node = Heal(Num(10), Str("strategy"), Num(1))
        with _Archive([DIVIDE_BY_ZERO]):
            res = eval_ast(node, {}, {})
        self.assertEqual(res.value, 10)
        self.assertEqual(res.confidence, E_CERTAIN)

    def test_heal_recovery(self):
        # heal (1/0) using ("strategy") fallback (99): the archived repair
        # for "division by zero" is the fixture 1, not the fallback.
        node = Heal(BinOp("/", Num(1), Num(0)), Str("strategy"), Num(99))
        with _Archive([DIVIDE_BY_ZERO]):
            res = eval_ast(node, {}, {})
        self.assertEqual(res.value, 1)
        self.assertEqual(res.confidence, E_INTAKE - E_REPAIR_PLAIN)
        self.assertEqual(res.lo, res.confidence)
        self.assertEqual(res.hi, res.confidence)

    def test_heal_fallback(self):
        # heal (nonexistent()) using ("strategy") fallback (42), no repair held
        node = Heal(Call("nonexistent", []), Str("strategy"), Num(42))
        with _Archive([]):
            res = eval_ast(node, {}, {})
        self.assertEqual(res.value, 42)

    def test_recovery_does_not_touch_the_callers_binding(self):
        env = {"x": e_val("x", 99, 200)}
        node = Heal(BinOp("/", Num(1), Num(0)), Str("s"), Num(42))
        archive = [{"failure_text": "division by zero", "fixture_text": "x", "kind": 0}]
        with _Archive(archive):
            res = eval_ast(node, env, {})
        self.assertEqual(res.value, 99)
        self.assertEqual(res.confidence, min(E_INTAKE, 200) - E_REPAIR_PLAIN)
        self.assertEqual(env["x"].confidence, 200)

    def test_unparsable_archived_fixture_is_z_not_the_fallback(self):
        node = Heal(BinOp("/", Num(1), Num(0)), Str("s"), Num(42))
        archive = [{"failure_text": "division by zero", "fixture_text": "1 +", "kind": 0}]
        with _Archive(archive):
            res = eval_ast(node, {}, {})
        self.assertTrue(res.is_z)
        self.assertIn("unparsable", res.reason)

    def test_real_path_healthy_primary(self):
        with _Archive([]):
            r = run_source('ever y = heal (5) using ("s") fallback (7)\nshow y')
        self.assertTrue(r.ok, r.errors)
        self.assertEqual(r.format_lines(), ["y = 5 [256/256]"])

    def test_real_path_falls_back_without_a_repair(self):
        with _Archive([]):
            r = run_source('let d = 0\never y = heal (1 / d) using ("s") fallback (7)\nshow y')
        self.assertTrue(r.ok, r.errors)
        self.assertEqual(r.format_lines(), ["y = 7 [256/256]"])

    def test_real_path_recovers_with_the_ast_confidence(self):
        with _Archive([DIVIDE_BY_ZERO]):
            r = run_source('let d = 0\never y = heal (1 / d) using ("s") fallback (7)\nshow y')
        self.assertTrue(r.ok, r.errors)
        self.assertEqual(r.format_lines(), [f"y = 1 [{E_INTAKE - E_REPAIR_PLAIN}/256]"])

    def test_real_path_heal_inside_arithmetic(self):
        with _Archive([]):
            r = run_source('let d = 0\never y = (heal (1 / d) using ("s") fallback (7)) + 1\nshow y')
        self.assertTrue(r.ok, r.errors)
        self.assertEqual(r.format_lines(), ["y = 8 [256/256]"])

    def test_bare_heal_parses_to_the_expression(self):
        node, err = parse('heal (1) using ("s") fallback (2)')
        self.assertIsNone(err)
        self.assertIsInstance(node, Heal)
        with _Archive([]):
            self.assertEqual(eval_ast(node, {}, {}).value, 1)

    def test_heal_is_still_a_name(self):
        r = run_source("let heal = 3\nshow heal")
        self.assertTrue(r.ok, r.errors)
        self.assertEqual(r.format_lines(), ["heal = 3 [256/256]"])

    def test_heal_without_using_is_a_call(self):
        node, err = parse("heal(1)")
        self.assertIsNone(err)
        self.assertIsInstance(node, Call)

    def test_using_and_fallback_are_still_names(self):
        r = run_source("let using = 4\nlet fallback = using + 1\nshow fallback")
        self.assertTrue(r.ok, r.errors)
        self.assertEqual(r.format_lines(), ["fallback = 5 [256/256]"])

    def test_capitalised_fallback_is_still_a_name(self):
        r = run_source("ever Fallback = 3\nshow Fallback")
        self.assertTrue(r.ok, r.errors)
        self.assertEqual(r.format_lines(), ["Fallback = 3 [256/256]"])

    def test_unbound_name_inside_heal_is_reported(self):
        node, err = parse('heal (q) using ("s") fallback (1)')
        self.assertIsNone(err)
        analysis = Semantic().analyse(node)
        self.assertFalse(analysis.clean)
        self.assertTrue(any("q" in message for message in analysis.errors), analysis.errors)


if __name__ == "__main__":
    unittest.main()


class TestStrategy(unittest.TestCase):
    """The strategy selects among archived repairs: a repair tied to it first,
    then a wildcard. A tied repair for another strategy is never a candidate."""

    RECORDS = [
        {"failure_text": "division by zero", "fixture_text": "1", "kind": 0, "strategy": "plain"},
        {"failure_text": "division by zero", "fixture_text": "2", "kind": 0, "strategy": "other"},
        {"failure_text": "division by zero", "fixture_text": "3", "kind": 0},
    ]

    def _heal(self, strategy):
        src = (f'let zero = 0\n'
               f'let res = heal (1 / zero) using ("{strategy}") fallback (50)\n'
               f'show res')
        return run_source(src).format_lines()

    def test_tied_strategy_wins_over_the_wildcard(self):
        with _Archive(self.RECORDS):
            self.assertIn("res = 1", self._heal("plain")[0])
            self.assertIn("res = 2", self._heal("other")[0])

    def test_unmatched_strategy_takes_the_wildcard(self):
        with _Archive(self.RECORDS):
            self.assertIn("res = 3", self._heal("nope")[0])

    def test_without_a_wildcard_an_unmatched_strategy_falls_back(self):
        with _Archive(self.RECORDS[:2]):
            self.assertIn("res = 50", self._heal("nope")[0])

    def test_learn_archives_under_its_strategy(self):
        with _Archive([]) as reg:
            run_source('let zero = 0\nlet res = learn (1 / zero) using ("plain") fix (7)\nshow res')
            self.assertEqual(reg.repairs[-1].get("strategy"), "plain")
            self.assertIn("res = 7", self._heal("plain")[0])
            self.assertIn("res = 50", self._heal("nope")[0])
