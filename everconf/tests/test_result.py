"""The app's JSON shape: labels, percent, reasons, evidence, provenance."""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from everconf import C, Unknown, MISSING_INPUT, INTAKE  # noqa: E402
from everconf.result import (label_for, percent_for, to_result, provenance,  # noqa: E402
                             auto_notes)
from everconf.reasons import REASONS  # noqa: E402

SHAPE = {"value", "state", "score", "percent", "label", "reasons", "chain",
         "evidence", "provenance"}


class Labels(unittest.TestCase):
    def test_band_edges(self):
        cases = {0: "can't tell", 1: "not sure", 159: "not sure", 160: "pretty sure",
                 223: "pretty sure", 224: "very sure", 256: "very sure"}
        for score, words in cases.items():
            self.assertEqual(label_for(score), words, score)

    def test_unknown_is_always_cant_tell(self):
        self.assertEqual(label_for(256, unknown=True), "can't tell")

    def test_every_score_has_a_label(self):
        labels = {label_for(s) for s in range(0, 257)}
        self.assertEqual(labels, {"can't tell", "not sure", "pretty sure", "very sure"})

    def test_percent(self):
        self.assertEqual(percent_for(0), 0)
        self.assertEqual(percent_for(120), 47)
        self.assertEqual(percent_for(128), 50)
        self.assertEqual(percent_for(180), 70)
        self.assertEqual(percent_for(256), 100)


class Shape(unittest.TestCase):
    def test_known_value_has_the_whole_shape(self):
        r = to_result(C(3, INTAKE), notes=[("INTAKE_SOURCE", "from an API")])
        self.assertEqual(set(r), SHAPE)
        self.assertEqual(r["state"], "known")
        self.assertEqual(r["score"], 120)
        self.assertEqual(r["percent"], 47)
        self.assertEqual(r["label"], "not sure")
        self.assertEqual(r["reasons"], [{"code": "INTAKE_SOURCE", "reason": "from an API"}])

    def test_unknown_value_says_so_and_carries_its_reason(self):
        r = to_result(Unknown(MISSING_INPUT, "no label"))
        self.assertEqual(set(r), SHAPE)
        self.assertEqual(r["value"], {"unknown": True})
        self.assertEqual((r["state"], r["score"], r["percent"]), ("unknown", 0, 0))
        self.assertEqual(r["label"], "can't tell")
        self.assertEqual(r["reasons"], [{"code": "MISSING_INPUT", "reason": "no label"}])

    def test_known_value_without_a_reason_is_refused(self):
        with self.assertRaises(ValueError):
            to_result(C(1))

    def test_unknown_note_code_is_refused_as_a_note(self):
        with self.assertRaises(ValueError):
            to_result(C(1), notes=[("MISSING_INPUT", "not a note")])

    def test_note_codes_come_from_the_registry(self):
        for code, text in ((c, "x") for c in REASONS):
            if REASONS[code][0] == "note":
                to_result(C(1), notes=[(code, text)])

    def test_evidence_needs_phrase_and_source(self):
        with self.assertRaises(ValueError):
            to_result(C(1), notes=[("DERIVED", "x")], evidence=[{"phrase": "", "source": "s"}])
        with self.assertRaises(ValueError):
            to_result(C(1), notes=[("DERIVED", "x")], evidence=[{"phrase": "p"}])

    def test_value_must_be_a_json_value(self):
        bad = C(object.__new__(type("Odd", (), {})))  # any non-JSON object
        with self.assertRaises(TypeError):
            to_result(bad, notes=[("DERIVED", "x")])

    def test_serialises_with_no_null_and_no_nan(self):
        r = to_result(C(2.5), notes=[("CERTAIN_LITERAL", "written in code")])
        text = json.dumps(r, allow_nan=False)
        self.assertNotIn("null", text)


class Provenance(unittest.TestCase):
    def test_origin_first_with_each_step_confidence(self):
        a = C(10, 256, source="ledger", at="2026-11-13T01:00:00Z")
        b = C(5, 120, source="api", at="2026-11-13T02:00:00Z")
        steps = provenance(a + b)
        self.assertEqual([s["step"] for s in steps], ["input", "input", "add"])
        self.assertEqual([s["confidence"] for s in steps], [256, 120, 120])
        self.assertEqual(steps[0]["source"], "ledger")
        self.assertEqual(steps[2]["at"], "2026-11-13T02:00:00Z")

    def test_shared_inputs_are_reported_once(self):
        x = C(2, 200, source="sensor", at="t1")
        total = x
        for _ in range(20):
            total = total + x
        steps = provenance(total)
        self.assertEqual(sum(1 for s in steps if s["source"] == "sensor"), 1)

    def test_unrecorded_time_is_not_null(self):
        steps = provenance(C(1) + C(2))
        self.assertTrue(all(isinstance(s["at"], str) and s["at"] for s in steps))

    def test_unknown_provenance_names_its_code(self):
        steps = provenance(C(1) + Unknown(MISSING_INPUT, "gap"))
        self.assertEqual(steps[-1]["source"], "MISSING_INPUT")
        self.assertEqual(steps[-1]["confidence"], 0)


class AutoNotes(unittest.TestCase):
    def test_literal(self):
        self.assertEqual(auto_notes(C(1))[0][0], "CERTAIN_LITERAL")

    def test_read_from_outside(self):
        self.assertEqual(auto_notes(C(1, source="api"))[0][0], "INTAKE_SOURCE")

    def test_derived(self):
        self.assertEqual(auto_notes(C(1) + C(2))[0][0], "DERIVED")


if __name__ == "__main__":
    unittest.main(verbosity=1)
