"""Scoring a model's read: grounding, corroboration, conflict, and what was missed."""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from everconf.reads import wrap_read, CLAUSE_RULES, TONE_RULES  # noqa: E402
from everconf import MISSING_INPUT, MALFORMED, UNVERIFIED_SOURCE, CONFLICTING_SOURCES  # noqa: E402

DOC = ("Tenant shall indemnify Landlord for any and all claims regardless of fault.\n"
       "Either party may pursue mandatory binding arbitration.\n"
       "This agreement shall automatically renew for successive periods unless written notice is sent 30 days prior.")


def _has_none(value):
    if value is None:
        return True
    if isinstance(value, dict):
        return any(_has_none(v) for v in value.values())
    if isinstance(value, list):
        return any(_has_none(v) for v in value)
    return False


def finding(quote, category):
    return {"quote": quote, "category": category}


class Grounding(unittest.TestCase):
    def test_quote_not_in_document_is_unverified(self):
        env = wrap_read("clause", DOC, {"findings": [finding("Landlord owns your soul", "Unfair IP Grab")]})
        read = env["reads"][0]["ever"]
        self.assertEqual(read["state"], "unknown")
        self.assertEqual(read["reasons"][0]["code"], UNVERIFIED_SOURCE)

    def test_whitespace_is_normalised_but_words_must_match(self):
        env = wrap_read("clause", DOC, {"findings": [
            finding("indemnify   Landlord for any and all\nclaims regardless of fault",
                    "Unilateral Indemnification")]})
        self.assertEqual(env["reads"][0]["ever"]["state"], "known")

    def test_case_is_kept(self):
        env = wrap_read("clause", DOC, {"findings": [
            finding("INDEMNIFY LANDLORD", "Unilateral Indemnification")]})
        self.assertEqual(env["reads"][0]["ever"]["reasons"][0]["code"], UNVERIFIED_SOURCE)

    def test_empty_quote_and_missing_category_are_missing_input(self):
        env = wrap_read("clause", DOC, {"findings": [finding("  ", "x"), finding(DOC[:10], "")]})
        self.assertEqual([r["ever"]["reasons"][0]["code"] for r in env["reads"]],
                         [MISSING_INPUT, MISSING_INPUT])


class Scoring(unittest.TestCase):
    def test_grounded_and_corroborated_is_pretty_sure(self):
        env = wrap_read("clause", DOC, {"findings": [
            finding("indemnify Landlord for any and all claims regardless of fault",
                    "Unilateral Indemnification")]}, at="2026-11-13T03:00:00Z")
        ever = env["reads"][0]["ever"]
        self.assertEqual((ever["score"], ever["label"]), (180, "pretty sure"))
        codes = {r["code"] for r in ever["reasons"]}
        self.assertTrue({"INTAKE_SOURCE", "GROUNDED", "CORROBORATED"} <= codes)

    def test_grounded_but_no_rule_is_not_sure(self):
        env = wrap_read("clause", "The rent is due on the first.", {"findings": [
            finding("The rent is due on the first.", "Late fee")]})
        ever = env["reads"][0]["ever"]
        self.assertEqual((ever["score"], ever["label"]), (120, "not sure"))
        self.assertIn("UNCORROBORATED", {r["code"] for r in ever["reasons"]})

    def test_evidence_lists_the_words_that_drove_the_score(self):
        env = wrap_read("clause", DOC, {"findings": [
            finding("mandatory binding arbitration", "Forced Arbitration & Jury Waiver")]})
        ev = env["reads"][0]["ever"]["evidence"]
        self.assertEqual(ev[0]["phrase"], "mandatory binding arbitration")
        self.assertIn("Forced Arbitration", ev[0]["source"])
        for e in ev:
            self.assertIn(e["phrase"], DOC)

    def test_disagreeing_category_is_a_conflict_not_a_pick(self):
        env = wrap_read("clause", DOC, {"findings": [
            finding("indemnify Landlord for any and all claims regardless of fault",
                    "Forced Arbitration & Jury Waiver")]})
        ever = env["reads"][0]["ever"]
        self.assertEqual(ever["state"], "unknown")
        self.assertEqual(ever["reasons"][0]["code"], CONFLICTING_SOURCES)


class Coverage(unittest.TestCase):
    def test_rule_hits_the_model_missed_are_surfaced(self):
        env = wrap_read("clause", DOC, {"findings": [
            finding("indemnify Landlord for any and all claims regardless of fault",
                    "Unilateral Indemnification")]})
        rules = {u["rule"] for u in env["unchecked"]}
        self.assertIn("arbitration", rules)
        self.assertIn("auto_renewal", rules)
        for u in env["unchecked"]:
            self.assertEqual(u["ever"]["reasons"][0]["code"], CONFLICTING_SOURCES)

    def test_overall_is_poisoned_by_any_unknown_read(self):
        env = wrap_read("clause", DOC, {"findings": [
            finding("indemnify Landlord for any and all claims regardless of fault",
                    "Unilateral Indemnification")]})
        self.assertEqual(env["overall"]["state"], "unknown")
        self.assertTrue(env["overall"]["chain"])

    def test_clean_document_with_no_reports_is_not_sure(self):
        env = wrap_read("clause", "Rent is due on the first.", {"findings": []})
        self.assertEqual(env["overall"]["label"], "not sure")
        self.assertEqual(env["overall"]["value"], 0)

    def test_overall_of_all_grounded_corroborated_reads_is_the_min(self):
        doc = "Tenant shall indemnify Landlord for any and all claims regardless of fault."
        env = wrap_read("clause", doc, {"findings": [
            finding("indemnify Landlord for any and all claims regardless of fault",
                    "Unilateral Indemnification")]})
        self.assertEqual(env["overall"]["state"], "known")
        self.assertEqual(env["overall"]["score"], 180)


class Bad(unittest.TestCase):
    def test_bad_kind(self):
        env = wrap_read("mood", DOC, {"findings": []})
        self.assertEqual(env["overall"]["reasons"][0]["code"], MALFORMED)
        self.assertEqual(env["reads"], [])

    def test_empty_document(self):
        env = wrap_read("clause", "   ", {"findings": []})
        self.assertEqual(env["overall"]["reasons"][0]["code"], MISSING_INPUT)

    def test_answer_not_an_object(self):
        env = wrap_read("clause", DOC, ["nope"])
        self.assertEqual(env["overall"]["reasons"][0]["code"], MALFORMED)

    def test_findings_not_a_list(self):
        env = wrap_read("clause", DOC, {"findings": "many"})
        self.assertEqual(env["overall"]["reasons"][0]["code"], MALFORMED)

    def test_model_nulls_are_passed_through_as_unknowns_not_null(self):
        env = wrap_read("clause", DOC, {"findings": [{"quote": None, "category": "x",
                                                      "recommendation": None}]})
        json.dumps(env, allow_nan=False)
        self.assertEqual(env["reads"][0]["model"]["recommendation"]["code"], MISSING_INPUT)
        self.assertEqual(env["reads"][0]["model"]["quote"]["unknown"], True)
        self.assertFalse(_has_none(env))


class Document(unittest.TestCase):
    def test_document_digest_is_stable_and_binds_the_read(self):
        a = wrap_read("clause", DOC, {"findings": []})
        b = wrap_read("clause", DOC, {"findings": []})
        c = wrap_read("clause", DOC + " ", {"findings": []})
        self.assertEqual(a["document_sha256"], b["document_sha256"])
        self.assertEqual(len(a["document_sha256"]), 64)
        self.assertNotEqual(a["document_sha256"], c["document_sha256"])


class Rules(unittest.TestCase):
    def test_eight_clause_rules_ported_from_the_app(self):
        self.assertEqual(len(CLAUSE_RULES), 8)

    def test_every_rule_compiles_and_names_a_category(self):
        for r in CLAUSE_RULES + TONE_RULES:
            self.assertTrue(r.category.strip())
            r.pattern.search("")


if __name__ == "__main__":
    unittest.main(verbosity=1)
