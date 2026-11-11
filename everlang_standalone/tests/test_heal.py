import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from everlang.core import heal
from everlang.core.archive import EArchive
from everlang.core.vocabulary import BY_NAME, DEFECTS, KIND_COST, VOCABULARY

REPO = Path(__file__).resolve().parents[2]
REPAIR_SQL = REPO / "ezr" / "4-archive-sql" / "repair.sql"
ARCHIVE_SQL = REPO / "ezr" / "4-archive-sql" / "archive.sql"

PY_BROKEN = "if x = 1\n    y = 2\n"
JAVA_BROKEN = "public class Heal {\n    static int f() {\n        int n = 1\n        return n\n    }\n}\n"


def _sql_block(text, table):
    start = text.index(f"INSERT OR REPLACE INTO {table}")
    return text[start:text.index(";", start)]


@unittest.skipUnless(REPAIR_SQL.exists(), "ezr/ lineage not present")
class TestVocabularyMatchesArchive(unittest.TestCase):
    def test_ever_repairs_match_repair_sql(self):
        rows = re.findall(r"\((\d+),'(\w+)',\s*(\d),\s*(\d),\s*'([^']*)'\)",
                          _sql_block(REPAIR_SQL.read_text(), "ever_repair "))
        self.assertEqual(len(rows), 7)
        for rid, name, kind, defect_id, note in rows:
            entry = VOCABULARY[int(rid) - 1]
            self.assertEqual((entry.id, entry.name, entry.kind, entry.defect, entry.note),
                             (int(rid), name, int(kind), DEFECTS[int(defect_id)], note))

    def test_costs_match_repair_kinds(self):
        rows = re.findall(r"\((\d),'(\w+)',\s*(\d+),",
                          _sql_block(REPAIR_SQL.read_text(), "ever_repair_kind"))
        self.assertEqual({int(k): int(c) for k, _, c in rows}, KIND_COST)

    def test_defect_order_matches_archive_sql(self):
        rows = re.findall(r"\((\d),'(\w+)',", _sql_block(ARCHIVE_SQL.read_text(), "ever_defect"))
        self.assertEqual(tuple(name for _, name in rows), DEFECTS)


@unittest.skipUnless(REPAIR_SQL.exists(), "ezr/ lineage not present")
class TestHeal(unittest.TestCase):
    def setUp(self):
        self.archive = EArchive()

    def test_python_heal_compiles(self):
        with self.assertRaises(SyntaxError):
            compile(PY_BROKEN, "<broken>", "exec")
        h = self.archive.heal(PY_BROKEN, "python", "py/a")
        compile(h.code, "<healed>", "exec")
        self.assertEqual(h.code, "if x == 1:\n    y = 2\n")
        self.assertEqual([r["fixture_form"] for r in h.repairs], ["COLON_APPEND", "EQ_TO_CMP"])
        self.assertEqual(h.confidence, 192)
        self.assertTrue(h.runnable)
        first = h.repairs[0]
        self.assertEqual((first["conf_before"], first["conf_after"]), (256, 224))
        self.assertEqual(first["line_text"], "if x = 1")
        self.assertTrue(first["failure_text"] and first["fixture_text"])

    @unittest.skipUnless(shutil.which("javac"), "javac not installed")
    def test_java_heal_compiles(self):
        h = self.archive.heal(JAVA_BROKEN, "java", "java/a")
        self.assertEqual([r["name"] for r in h.repairs], ["missing_semicolon", "missing_semicolon"])
        env = {k: v for k, v in os.environ.items() if k != "JAVA_TOOL_OPTIONS"}
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "Heal.java"
            src.write_text(JAVA_BROKEN)
            broken = subprocess.run(["javac", str(src)], capture_output=True, env=env)
            src.write_text(h.code)
            healed = subprocess.run(["javac", str(src)], capture_output=True, text=True, env=env)
        self.assertNotEqual(broken.returncode, 0)
        self.assertEqual(healed.returncode, 0, healed.stderr)

    def test_go_and_kotlin_are_left_alone(self):
        for lang, src in (("go", "package main\nfunc main() {}\n"), ("kotlin", "fun main() { println(1) }\n")):
            h = self.archive.heal(src, lang, f"{lang}/a")
            self.assertEqual((h.code, h.confidence, h.repairs), (src, 256, []))

    def test_four_inferred_repairs_land_on_the_floor(self):
        four = self.archive.heal("let a = [1 2 3 4 5]", "ever", "ever/four")
        five = self.archive.heal("let a = [1 2 3 4 5 6]", "ever", "ever/five")
        self.assertEqual((four.confidence, four.runnable), (128, True))
        self.assertEqual((five.confidence, five.runnable), (96, False))
        self.assertIsNotNone(four.program)
        self.assertIsNone(four.code)

    def test_unclosed_bracket_is_refused_not_guessed(self):
        h = self.archive.heal("print((1, 2)\n", "python", "py/unclosed")
        self.assertTrue(h.refused)
        self.assertEqual((h.confidence, h.code, h.repairs), (0, None, []))
        self.assertEqual(h.particle().value, "Quarantined(Z)")
        marker = self.archive.boundary_markers[-1]
        self.assertEqual(marker["context"], "heal:python:py/unclosed")
        self.assertIn("never closed", marker["reason"])

    def test_unhealable_ever_is_refused(self):
        h = self.archive.heal("let x = [1, 2", "ever", "ever/open")
        self.assertTrue(h.refused)
        self.assertEqual(h.particle().confidence, 0)

    def test_missing_engine_refuses_instead_of_emulating(self):
        with mock.patch.object(heal, "_engines", ()):
            h = self.archive.heal(PY_BROKEN, "python", "py/none")
        self.assertTrue(h.refused)
        self.assertIn("no repair engine", h.refusals[0])

    def test_unknown_language_is_an_error(self):
        with self.assertRaises(ValueError):
            self.archive.heal("x", "cobol", "c/a")

    def test_emitted_names_are_in_the_vocabulary(self):
        self.archive.heal(PY_BROKEN, "python", "py/a")
        self.archive.heal("let a = [1, 2,]; let b = 1 = 1", "ever", "ever/a")
        for r in self.archive.repairs:
            self.assertIn(r["language"], BY_NAME[r["name"]].languages)


@unittest.skipUnless(REPAIR_SQL.exists(), "ezr/ lineage not present")
class TestRecurrenceAndRules(unittest.TestCase):
    def setUp(self):
        self.archive = EArchive()

    def test_same_fix_across_languages_is_admitted(self):
        self.archive.heal("if a = 1:\n    pass\n", "python", "py/one")
        self.archive.heal("while b = 2:\n    pass\n", "python", "py/two")
        self.archive.heal("def f(x) = if x = 1 then 2 else 3", "ever", "ever/one")
        [candidate] = self.archive.repair_candidates()
        self.assertEqual((candidate["name"], candidate["fixture_form"]), ("equals_for_compare", "EQ_TO_CMP"))
        self.assertEqual((candidate["distinct_sources"], candidate["distinct_languages"]), (3, 2))
        [rule] = self.archive.propose_rules()
        self.assertEqual((rule["status"], rule["confidence"]), ("admitted", 128))
        self.assertEqual(rule["replay_agreed"], rule["replay_total"])

    def test_one_source_repeating_is_not_a_candidate(self):
        self.archive.heal("let a = [1 2]\nlet b = [3 4]\nlet c = [5 6]", "ever", "ever/same")
        self.assertEqual(self.archive.repair_candidates(), [])

    def test_disagreeing_forms_are_rejected_and_kept(self):
        for ident in ("e/1", "e/2", "e/3"):
            self.archive.heal("let a = [1 2]", "ever", ident)
        self.archive.heal("let n = 1\nlet a = [n 2]", "ever", "e/4")
        [rule] = self.archive.propose_rules()
        self.assertEqual((rule["status"], rule["confidence"]), ("rejected", 120))
        self.assertEqual(rule["rejected_why"], "replay disagreed: 1 of 4 prior repairs would change")
        self.assertEqual(self.archive.rules, [rule])


if __name__ == "__main__":
    unittest.main()
