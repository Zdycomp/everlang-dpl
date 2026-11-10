import json
import os
import sys
import tempfile
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
for _path in (_HERE, os.path.join(_HERE, '..', '2-interpreter-python')):
    sys.path.insert(0, os.path.abspath(_path))

import forgive
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


class TestCauseNaming(unittest.TestCase):
    """A z is named by the first failure that happened under it: in the
    expression, inside a called function, or inside a repair an inner heal
    absorbed. A branch that never ran names nothing."""

    RECORDS = [{"failure_text": "division by zero", "fixture_text": "1", "kind": 0}]

    def test_failure_inside_a_called_function_is_named(self):
        with _Archive(self.RECORDS):
            r = run_source('def f(x) = 10 / x\nlet r = heal (f(0)) using ("plain") fallback (5)\nshow r')
        self.assertTrue(r.ok, r.errors)
        self.assertEqual(r.format_lines(), [f"r = 1 [{E_INTAKE - E_REPAIR_PLAIN}/256]"])
        self.assertIn("heal#1 evaluate: z, reason 'division by zero', base 120", r.heal_trace)

    def test_learn_through_a_call_archives_the_named_cause(self):
        with _Archive([]) as reg:
            r = run_source('def f(x) = 10 / x\nlet a = learn (f(0)) using ("plain") fix (7)\nshow a')
            self.assertTrue(r.ok, r.errors)
            self.assertEqual(reg.repairs[-1].get("failure_text"), "division by zero")
            self.assertEqual(reg.repairs[-1].get("fixture_text"), "7")

    def test_a_branch_that_never_ran_names_nothing(self):
        with _Archive(self.RECORDS):
            r = run_source('let zero = 0\nlet r = heal (if true then 4 else 1 / zero) using ("plain") fallback (5)\nshow r')
        self.assertTrue(r.ok, r.errors)
        self.assertEqual(r.format_lines(), ["r = 4 [256/256]"])

    def test_a_declared_unknown_is_named(self):
        with _Archive([{"failure_text": "declared unknown", "fixture_text": "9", "kind": 0}]):
            r = run_source('let r = heal (z) using ("plain") fallback (5)\nshow r')
        self.assertTrue(r.ok, r.errors)
        self.assertEqual(r.format_lines(), [f"r = 9 [{E_INTAKE - E_REPAIR_PLAIN}/256]"])

    def test_a_repair_absorbed_by_an_inner_heal_is_not_the_outer_cause(self):
        # the inner heal absorbs the division and its repair is below the execute
        # floor, so the outer heal sees low confidence, not a division by zero
        with _Archive(self.RECORDS):
            r = run_source('let zero = 0\nlet r = heal ((heal (1 / zero) using ("plain") fallback (3)) + 1) using ("plain") fallback (5)\nshow r')
        self.assertTrue(r.ok, r.errors)
        self.assertIn("heal#2 evaluate: confidence 112/256, reason 'low confidence', base 112", r.heal_trace)
        self.assertEqual(r.format_lines(), ["r = 5 [256/256]"])


class TestHealFormsAreNotCalls(unittest.TestCase):
    """forgive.py heals missing commas inside calls and collections. A heal form
    is neither: `heal (` is not a call, and `) using` is not two items."""

    def test_nested_heal_gets_no_comma_inserted(self):
        node, err, corrections = forgive.parse_forgiving(
            'let q = heal (heal (1) using ("p") fallback (3)) using ("p") fallback (50)\nshow q')
        self.assertIsNone(err)
        self.assertEqual(corrections, [])

    def test_heal_forms_inside_a_list_get_no_comma_inserted(self):
        node, err, corrections = forgive.parse_forgiving(
            'let xs = [heal (1) using ("p") fallback (3), heal (2) using ("p") fallback (4)]\nshow xs')
        self.assertIsNone(err)
        self.assertEqual(corrections, [])

    def test_two_heal_forms_side_by_side_still_need_their_comma(self):
        node, err, corrections = forgive.parse_forgiving(
            'let xs = [heal (1) using ("p") fallback (3) heal (2) using ("p") fallback (4)]')
        self.assertIsNone(err)
        self.assertEqual([c.became for c in corrections], ["',' inserted"])

    def test_nested_heal_runs_on_the_real_path(self):
        # the inner repair is 112, below the execute floor of 128, so the outer
        # heal does not trust it and takes its fallback
        with _Archive([DIVIDE_BY_ZERO]):
            r = run_source('let zero = 0\nlet q = heal (heal (1 / zero) using ("plain") fallback (3)) using ("plain") fallback (50)\nshow q')
        self.assertTrue(r.ok, r.errors)
        self.assertEqual(r.format_lines(), ["q = 50 [256/256]"])


class TestNestedHealsKeepTheirOwnRecord(unittest.TestCase):
    """Each heal's trace lines and store records belong to that heal. A heal
    nested in another's fallback or strategy runs between the outer heal's
    PLAN and EXECUTE; it must not rename or re-describe the outer one."""

    SOURCE = ('let zero = 0\n'
              'let r = heal (z) using ("p") fallback '
              '(heal (1 / zero) using ("p") fallback (7))\n'
              'show r')

    def _run(self):
        with _Archive([DIVIDE_BY_ZERO]), tempfile.TemporaryDirectory() as store, \
                mock.patch.dict(os.environ, {"EVER_REPAIR_STORE": store}):
            result = run_source(self.SOURCE)
            with open(os.path.join(store, "events.jsonl"), encoding="utf-8") as f:
                events = [json.loads(line) for line in f]
        self.assertTrue(result.ok, result.errors)
        return result, events

    def test_each_heal_has_exactly_its_own_execute_line(self):
        result, _ = self._run()
        outer = [t for t in result.heal_trace if t.startswith("heal#1 ")]
        inner = [t for t in result.heal_trace if t.startswith("heal#2 ")]
        self.assertEqual([t.split(":")[0] for t in outer],
                         ["heal#1 evaluate", "heal#1 plan", "heal#1 execute"])
        self.assertEqual([t.split(":")[0] for t in inner],
                         ["heal#2 evaluate", "heal#2 plan", "heal#2 execute"])
        self.assertIn("FALLBACK", outer[-1])
        self.assertIn("SUBSTITUTE", inner[-1])

    def test_each_heal_writes_its_own_event(self):
        _, events = self._run()
        # the inner heal finishes first
        self.assertEqual([(e["action"], e["reason"], e["conf_in"]) for e in events],
                         [("SUBSTITUTE", "division by zero", 0),
                          ("FALLBACK", "declared unknown", 0)])
        inner, outer = events
        self.assertEqual((inner["strategy"], inner["fixture"], inner["cost"]),
                         ("p", "1", E_REPAIR_PLAIN))
        self.assertEqual((outer["strategy"], outer["fixture"], outer["cost"]),
                         ("p", None, 0))


if __name__ == "__main__":
    unittest.main()
