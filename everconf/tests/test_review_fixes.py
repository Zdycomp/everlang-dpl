"""Regression checks for the CodeRabbit review of PR #18. Each test fails on the
code as it was before the fix."""

import os
import shutil
import sys
import tempfile
import threading
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "..", "2-interpreter-python"))

from everconf import C, Unknown, MISSING_INPUT, mse, OUT_OF_RANGE  # noqa: E402
from everconf.profile import (FINANCIAL, AuditLog, AuditError, decide,  # noqa: E402
                              record_of, from_record)
from everconf.reads import wrap_read  # noqa: E402

T0 = "2026-11-13T03:00:00Z"


class AuditFixes(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="everconf-review-")
        self.path = os.path.join(self.dir, "log.jsonl")
        self.log = AuditLog(self.path)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_a_corroborated_value_keeps_its_operation_through_a_record(self):
        from everconf import corroborate
        v = corroborate(C("x", 120, source="a", at=T0), C("x", 256, source="b", at=T0))
        restored = from_record(record_of(v))
        self.assertEqual(restored._op, "corroborate")
        self.assertEqual(restored.confidence, v.confidence)

    def test_an_unknown_keeps_its_chain_through_a_record(self):
        u = Unknown(MISSING_INPUT, "gap", chain=["add: poisoned by MISSING_INPUT"])
        self.assertEqual(from_record(record_of(u)).chain, u.chain)

    def test_a_decision_is_not_changed_by_later_edits_to_its_inputs(self):
        inputs = {"value": record_of(C(250, 256, source="feed", at=T0))}
        d = decide(FINANCIAL, "settle", at=T0, computation="value", inputs=inputs)
        before = d.to_record()["inputs"]["value"]["confidence"]
        inputs["value"]["confidence"] = 0          # edit the nested input after the decision
        self.assertEqual(d.inputs["value"]["confidence"], before)

    def test_an_unterminated_final_record_is_reported_and_blocks_appends(self):
        self.log.append(decide(FINANCIAL, "settle", at=T0, computation="value",
                               inputs={"value": record_of(C(1, 256, source="f", at=T0))}))
        with open(self.path, "a", encoding="utf-8") as f:
            f.write('{"seq":2,"partial')           # an interrupted write, no newline
        report = self.log.verify()
        self.assertFalse(report["ok"])
        with self.assertRaises(AuditError):
            self.log.append(decide(FINANCIAL, "settle", at=T0, computation="value",
                                   inputs={"value": record_of(C(1, 256, source="f", at=T0))}))

    def test_concurrent_appends_keep_one_chain(self):
        def writer():
            for _ in range(10):
                self.log.append(decide(FINANCIAL, "settle", at=T0, computation="value",
                                       inputs={"value": record_of(C(1, 256, source="f", at=T0))}))
        threads = [threading.Thread(target=writer) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        report = self.log.verify()
        self.assertTrue(report["ok"], report["problems"][:3])
        self.assertEqual(report["records"], 80)


class ReadCoverage(unittest.TestCase):
    def test_a_quote_covers_only_matches_of_its_own_category(self):
        doc = "mandatory binding arbitration and a penalty fee"
        env = wrap_read("clause", doc, {"findings": [
            {"quote": doc, "category": "Forced Arbitration & Jury Waiver"}]})
        self.assertIn("liquidated_damages", {u["rule"] for u in env["unchecked"]})


class MseOverflow(unittest.TestCase):
    def test_a_mean_too_large_to_represent_is_an_unknown(self):
        r = mse([C(10 ** 400)], [C(0)])
        self.assertIsInstance(r, Unknown)
        self.assertEqual(r.code, OUT_OF_RANGE)


class IrRefusesAFailedSource(unittest.TestCase):
    def test_an_unparsed_source_is_refused_by_lowering(self):
        import ir
        import syntax
        with self.assertRaises(ValueError):
            ir._ast_to_ir(syntax.Unparsed("parse", "unexpected end of input"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
