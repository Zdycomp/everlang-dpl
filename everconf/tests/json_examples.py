"""The worked examples in docs/JSON.md. Each is a function that returns the
exact JSON-shaped dict the library produces. tests/test_docs.py requires the
blocks in JSON.md to equal these, so the documentation cannot drift from the
code."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from everconf import C, Unknown, MISSING_INPUT, TIMEOUT, csum, INTAKE  # noqa: E402
from everconf.adapter import handle  # noqa: E402
from everconf.profile import FINANCIAL, decide, record_of  # noqa: E402
from everconf.result import to_result  # noqa: E402

DOC = "Tenant shall indemnify Landlord for any and all claims regardless of fault."
GEMINI = {
    "overall_risk_score": 88,
    "risk_tier": "CRITICAL",
    "summary": "One unilateral indemnity.",
    "findings": [{"verbatim_text": "indemnify Landlord for any and all claims regardless of fault",
                  "category": "Unilateral Indemnification", "risk_level": "CRITICAL",
                  "recommendation": "Strike the indemnity or cap it."}],
}


def literal():
    """A value written in the program: certain."""
    return to_result(C(42), notes=[("CERTAIN_LITERAL", "written directly in the program")])


def from_an_api():
    """A value read from outside: at most INTAKE (120), so 'not sure'."""
    return to_result(C(19.99, INTAKE, source="price API", at="2026-11-13T03:00:00Z"),
                     notes=[("INTAKE_SOURCE", "read from price API")])


def unknown_poisons_a_sum():
    """One unknown input makes the sum unknown, and keeps its reason."""
    total = csum([C(5), Unknown(TIMEOUT, "fee feed did not answer"), C(3)])
    return to_result(total)


def financial_halt():
    """Strict profile: a value below the 224 the action needs stops the trade."""
    d = decide(FINANCIAL, "settle_trade", at="2026-11-13T03:00:00Z", computation="value",
               inputs={"value": record_of(C(250, 200, source="exchange feed",
                                            at="2026-11-13T02:59:59Z"))})
    return d.result


def clause_read():
    """One clause from a Gemini answer, grounded in the text and corroborated by a rule."""
    _, reply = handle({"kind": "clause", "document": DOC, "answer": GEMINI,
                       "at": "2026-11-13T03:00:00Z"})
    return reply["reads"][0]["ever"]


EXAMPLES = {
    "literal": literal,
    "from_an_api": from_an_api,
    "unknown_poisons_a_sum": unknown_poisons_a_sum,
    "financial_halt": financial_halt,
    "clause_read": clause_read,
}
