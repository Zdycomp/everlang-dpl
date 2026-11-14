"""Financial continuity: strict decisions, an append-only audit log, and replay."""

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from everconf import C, Unknown, MISSING_INPUT, TIMEOUT  # noqa: E402
from everconf.profile import (DEFAULT, FINANCIAL, HALT, ALLOW, DISPLAY_ONLY,  # noqa: E402
                              GENESIS, AuditLog, AuditError, decide, record_of, replay)

T0 = "2026-11-13T03:00:00Z"


def trade_decision(value, at=T0, profile=FINANCIAL):
    return decide(profile, "settle_trade", at=at, computation="value",
                  inputs={"value": record_of(value)})


class StrictDecisions(unittest.TestCase):
    def test_confident_value_is_allowed(self):
        d = trade_decision(C(250, 256, source="exchange feed", at=T0))
        self.assertEqual(d.outcome, ALLOW)
        self.assertEqual(d.confidence, 256)

    def test_unknown_is_a_hard_stop_with_full_explanation(self):
        d = decide(FINANCIAL, "settle_trade", at=T0, computation="csum", inputs={"items": [
            record_of(C(5, 256, source="ledger", at=T0)),
            record_of(Unknown(TIMEOUT, "fee feed did not answer"))]})
        self.assertEqual(d.outcome, HALT)
        self.assertEqual(d.confidence, 0)
        self.assertIn("TIMEOUT", d.reason)
        self.assertEqual(d.result["reasons"][0], {"code": "TIMEOUT", "reason": "fee feed did not answer"})
        self.assertTrue(d.result["chain"])

    def test_value_below_the_financial_threshold_halts(self):
        d = trade_decision(C(250, 200, source="api", at=T0))
        self.assertEqual(d.threshold, 224)
        self.assertEqual(d.outcome, HALT)
        self.assertIn("224", d.reason)

    def test_default_profile_displays_but_does_not_act(self):
        d = trade_decision(Unknown(MISSING_INPUT, "x"), profile=DEFAULT)
        self.assertEqual(d.outcome, DISPLAY_ONLY)
        d2 = trade_decision(C(1, 100, source="api", at=T0), profile=DEFAULT)
        self.assertEqual(d2.outcome, DISPLAY_ONLY)

    def test_decision_needs_its_own_timestamp_from_the_caller(self):
        with self.assertRaises(ValueError):
            decide(FINANCIAL, "settle", at="", computation="value",
                   inputs={"value": record_of(C(1))})

    def test_unknown_computation_is_refused(self):
        with self.assertRaises(ValueError):
            decide(FINANCIAL, "settle", at=T0, computation="eval", inputs={})

    def test_recorded_inputs_are_json_safe(self):
        d = trade_decision(C(250, 256, source="feed", at=T0))
        json.dumps(d.to_record(), allow_nan=False)


class Log(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="everconf-log-")
        self.path = os.path.join(self.dir, "decisions.jsonl")
        self.log = AuditLog(self.path)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _three(self):
        self.log.append(trade_decision(C(250, 256, source="feed", at=T0)))
        self.log.append(decide(FINANCIAL, "settle", at="2026-11-13T03:00:01Z",
                               computation="csum", inputs={"items": [
                                   record_of(C(5, 120, source="api", at=T0)),
                                   record_of(Unknown(MISSING_INPUT, "no fee"))]}))
        self.log.append(trade_decision(C(250, 200, source="api", at=T0)))

    def test_entries_are_chained_and_numbered(self):
        self._three()
        entries = self.log.entries()
        self.assertEqual([e["seq"] for e in entries], [1, 2, 3])
        self.assertEqual(entries[0]["prev_hash"], GENESIS)
        self.assertEqual(entries[1]["prev_hash"], entries[0]["hash"])
        self.assertEqual(entries[2]["prev_hash"], entries[1]["hash"])

    def test_every_entry_records_inputs_confidence_threshold_and_outcome(self):
        self._three()
        for e in self.log.entries():
            for field in ("inputs", "confidence", "threshold", "outcome", "result", "at"):
                self.assertIn(field, e)

    def test_intact_log_verifies(self):
        self._three()
        report = self.log.verify()
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["records"], 3)

    def test_append_never_rewrites_existing_bytes(self):
        self._three()
        with open(self.path, "rb") as f:
            before = f.read()
        self.log.append(trade_decision(C(1, 256, source="feed", at=T0)))
        with open(self.path, "rb") as f:
            after = f.read()
        self.assertTrue(after.startswith(before))
        self.assertGreater(len(after), len(before))

    def test_an_edited_line_is_found(self):
        self._three()
        lines = open(self.path, encoding="utf-8").read().split("\n")
        lines[1] = lines[1].replace('"outcome":"HALT"', '"outcome":"ALLOW"', 1)
        open(self.path, "w", encoding="utf-8").write("\n".join(lines))
        report = self.log.verify()
        self.assertFalse(report["ok"])
        self.assertEqual(report["problems"][0][0], 2)

    def test_a_deleted_line_is_found(self):
        self._three()
        lines = open(self.path, encoding="utf-8").read().split("\n")
        del lines[1]
        open(self.path, "w", encoding="utf-8").write("\n".join(lines))
        self.assertFalse(self.log.verify()["ok"])

    def test_a_recomputed_hash_still_fails_replay(self):
        """Someone who rewrites a line and fixes its hash passes verify() but
        not replay(): the recomputed decision disagrees with what they wrote."""
        from everconf.profile import _hash_of
        self._three()
        entries = self.log.entries()
        entries[0]["confidence"] = 999
        entries[0]["hash"] = _hash_of(entries[0])
        out = []
        for i, e in enumerate(entries):
            if i:
                e["prev_hash"] = entries[i - 1]["hash"]
                e["hash"] = _hash_of(e)
            out.append(json.dumps(e, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
        open(self.path, "w", encoding="utf-8").write("\n".join(out) + "\n")
        self.assertTrue(self.log.verify()["ok"])
        self.assertIn((1, "confidence"), replay(self.path)["mismatches"])

    def test_append_refuses_to_extend_a_broken_log(self):
        self._three()
        text = open(self.path, encoding="utf-8").read().replace('"seq":1', '"seq":7', 1)
        open(self.path, "w", encoding="utf-8").write(text)
        with self.assertRaises(AuditError):
            self.log.append(trade_decision(C(1, 256, source="feed", at=T0)))


class Replay(unittest.TestCase):
    def test_replay_reproduces_every_recorded_decision(self):
        d = tempfile.mkdtemp(prefix="everconf-replay-")
        try:
            log = AuditLog(os.path.join(d, "a.jsonl"))
            log.append(trade_decision(C(250, 256, source="feed", at=T0)))
            log.append(decide(FINANCIAL, "settle", at=T0, computation="mse", inputs={
                "predicted": [record_of(C(0.9)), record_of(C(0.2))],
                "actual": [record_of(C(1)), record_of(Unknown(MISSING_INPUT, "gap"))]}))
            r = replay(log.path)
            self.assertEqual(r, {"records": 2, "mismatches": []})
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_same_inputs_give_byte_identical_logs(self):
        """No clock is read, so two runs over the same inputs write the same bytes."""
        outputs = []
        for _ in range(2):
            d = tempfile.mkdtemp(prefix="everconf-det-")
            try:
                log = AuditLog(os.path.join(d, "x.jsonl"))
                log.append(trade_decision(C(250, 256, source="feed", at=T0)))
                log.append(decide(FINANCIAL, "settle", at=T0, computation="cmean", inputs={
                    "items": [record_of(C(2, 150, source="api", at=T0)),
                              record_of(C(4, 256, source="feed", at=T0))]}))
                outputs.append(open(log.path, "rb").read())
            finally:
                shutil.rmtree(d, ignore_errors=True)
        self.assertEqual(outputs[0], outputs[1])

    def test_same_inputs_give_the_same_decision_in_memory(self):
        inputs = {"items": [record_of(C(3, 200, source="a", at=T0)),
                            record_of(C(4, 180, source="b", at=T0))]}
        a = decide(FINANCIAL, "x", at=T0, computation="csum", inputs=inputs)
        b = decide(FINANCIAL, "x", at=T0, computation="csum", inputs=inputs)
        self.assertEqual(a.to_record(), b.to_record())

    def test_unknown_profile_in_a_log_is_a_mismatch_not_a_crash(self):
        d = tempfile.mkdtemp(prefix="everconf-prof-")
        try:
            log = AuditLog(os.path.join(d, "p.jsonl"))
            log.append(trade_decision(C(1, 256, source="feed", at=T0)))
            r = replay(log.path, profiles={"default": DEFAULT})
            self.assertEqual(r["mismatches"], [(1, "profile is not known to this replay")])
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=1)
