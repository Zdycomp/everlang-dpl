import os
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
for _path in (_HERE, os.path.join(_HERE, '..', '2-interpreter-python')):
    sys.path.insert(0, os.path.abspath(_path))

from ever import E_CERTAIN, E_INTAKE
from repair import RepairRegistry, use_registry
from runtime import run_source
from syntax import BinOp, Learn, Num, Str, eval_ast, parse


class _Archive:
    """An empty archive in a temporary directory, so learning writes there
    and never to the repo's shared 7-refix-node file."""

    def __enter__(self):
        self._dir = tempfile.TemporaryDirectory()
        self.registry = RepairRegistry(archive_dir=self._dir.name)
        use_registry(self.registry)
        return self.registry

    def __exit__(self, *exc):
        use_registry(None)
        self._dir.cleanup()


class TestLearn(unittest.TestCase):
    def test_learn_success(self):
        # learn (10) using ("strategy") fix (1)
        node = Learn(Num(10), Str("strategy"), Num(1))
        with _Archive():
            res = eval_ast(node, {}, {})
        self.assertEqual(res.value, 10)
        self.assertEqual(res.confidence, E_CERTAIN)

    def test_learn_recovery_and_archive(self):
        # learn (1/0) using ("strategy") fix (42) returns the fixture and
        # archives it under the failure it repaired.
        node = Learn(BinOp("/", Num(1), Num(0)), Str("strategy"), Num(42))
        with _Archive() as archive:
            res = eval_ast(node, {}, {})
            archived = [(r.get("failure_text"), r.get("fixture_text")) for r in archive.repairs]
        self.assertEqual(res.value, 42)
        self.assertEqual(res.confidence, E_INTAKE)
        self.assertIn(("division by zero", "42"), archived)

    def test_learn_failure(self):
        # the fixture is itself z, so nothing is learned
        primary = BinOp("/", Num(1), Num(0))
        fixture = BinOp("/", Num(1), Num(0))
        node = Learn(primary, Str("strategy"), fixture)
        with _Archive() as archive:
            res = eval_ast(node, {}, {})
        self.assertTrue(res.is_z)
        self.assertEqual(archive.repairs, [])

    def test_learning_the_same_repair_twice_archives_once(self):
        node = Learn(BinOp("/", Num(1), Num(0)), Str("s"), Num(42))
        with _Archive() as archive:
            eval_ast(node, {}, {})
            eval_ast(node, {}, {})
            self.assertEqual(len(archive.repairs), 1)

    def test_archived_text_reparses_to_the_same_tree(self):
        fixture, err = parse("2 * (3 + 4)")
        self.assertIsNone(err)
        node = Learn(BinOp("/", Num(1), Num(0)), Str("s"), fixture)
        with _Archive() as archive:
            res = eval_ast(node, {}, {})
            (text,) = [r["fixture_text"] for r in archive.repairs]
        self.assertEqual(res.value, 14)
        self.assertEqual(text, "2 * (3 + 4)")
        again, err = parse(text)
        self.assertIsNone(err)
        self.assertEqual(again.shape(), fixture.shape())

    def test_printed_source_reparses_to_the_same_tree(self):
        for src in ("2 * (3 + 4)", "1 - (2 - 3)", "(1 + 2) * (3 - 4) / 5",
                    "not (1 < 2) and 3 > 2 or false", "(if 1 < 2 then 3 else 4) * 2",
                    "f(1 + 2, g(3 * 4))", "[1 + 2, 3 * (4 - 1)][0] + 1",
                    "{a: 1 + 2, b: 3}.a * 2"):
            with self.subTest(src=src):
                node, err = parse(src)
                self.assertIsNone(err)
                again, err = parse(str(node))
                self.assertIsNone(err)
                self.assertEqual(again.shape(), node.shape())

    def test_learn_on_the_real_path(self):
        with _Archive() as archive:
            r = run_source('let d = 0\never y = learn (1 / d) using ("s") fix (42)\nshow y')
            archived = [(x.get("failure_text"), x.get("fixture_text")) for x in archive.repairs]
        self.assertTrue(r.ok, r.errors)
        self.assertEqual(r.format_lines(), [f"y = 42 [{E_INTAKE}/256]"])
        self.assertIn(("division by zero", "42"), archived)

    def test_learn_returns_the_primary_when_it_is_fine_on_the_real_path(self):
        with _Archive():
            r = run_source('ever y = learn (1) using ("s") fix (3)\nshow y')
        self.assertTrue(r.ok, r.errors)
        self.assertEqual(r.format_lines(), ["y = 1 [256/256]"])

    def test_learn_parses_with_contextual_words(self):
        node, err = parse("learn (1) using (2) fix (3)")
        self.assertIsNone(err)
        self.assertIsInstance(node, Learn)


if __name__ == "__main__":
    unittest.main()
