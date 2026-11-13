"""Scoring a model's read of a document: clause risk, tone, motive.

A model (Gemini, through the Express server) reads a contract or a message
and returns findings. Each finding is a claim about the text, and each claim
is scored here by three checks:

1. Grounding. The quoted words must appear verbatim in the document
   (whitespace normalised, case kept). A quote that is not in the document is
   an Unknown (UNVERIFIED_SOURCE): the model is not taken at its word.
2. Source. The model is a third-party source, so a grounded read is INTAKE
   (120) at most.
3. Corroboration. A local rule (below) matches the same passage and names the
   same category. Then the read is corroborated and lifts to AGREE (180), by
   the rule in ``everconf.corroborate``. A local rule that names a different
   category is a conflict, an Unknown (CONFLICTING_SOURCES).

Every local rule match that the model did not report is also surfaced, as an
Unknown (CONFLICTING_SOURCES) in ``unchecked``. Nothing the rules found is
dropped silently.

Rules are a heuristic lexicon. They name passages to check; they are not legal
advice, and nothing here claims to be. The rule set for clauses is ported from
ClauseShield's ``src/utils/clauseAudit.ts`` (KNOWN_TRAP_PATTERNS); the one
category spelling that was wrong there ("Puntitive") is corrected here.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from . import (C, CERTAIN, CONFLICTING_SOURCES, INTAKE, MALFORMED,
               MISSING_INPUT, NOT_RECORDED, UNVERIFIED_SOURCE, Unknown,
               corroborate)
from .result import to_result

KINDS = ("clause", "tone", "motive")


@dataclass(frozen=True)
class Rule:
    rule_id: str
    category: str
    pattern: "re.Pattern[str]"


def _rule(rule_id: str, category: str, regex: str) -> Rule:
    return Rule(rule_id, category, re.compile(regex, re.IGNORECASE))


CLAUSE_RULES: Tuple[Rule, ...] = (
    _rule("indemnity", "Unilateral Indemnification",
          r"(indemnify|hold harmless|defend)[\s\S]{0,120}(unlimited|all claims|sole liability|regardless of fault|any and all)"),
    _rule("arbitration", "Forced Arbitration & Jury Waiver",
          r"(arbitration|waive.{0,30}trial by jury|class action waiver|mandatory binding arbitration)"),
    _rule("auto_renewal", "Sneaky Auto-Renewal Trap",
          r"(automatically renew|auto-renew|successive period|renewal term)[\s\S]{0,140}(written notice|certified mail|30 days prior|60 days prior)"),
    _rule("non_compete", "Overbroad Non-Compete & Restraint of Trade",
          r"(non-compete|covenant not to compete|restrictive covenant)[\s\S]{0,160}(any competitor|worldwide|similar business|12 months|24 months|2 years)"),
    _rule("ip_grab", "Unfair IP Grab & Prior Works Surrender",
          r"(work made for hire|assigns all right|prior inventions|intellectual property|moral rights)[\s\S]{0,180}(perpetual|worldwide|irrevocable|all creations|any idea)"),
    _rule("liquidated_damages", "Punitive Liquidated Damages",
          r"(liquidated damages|penalty fee|cancellation fee of \$|forfeit all deposits)"),
    _rule("unilateral_change", "Unilateral Modification Right",
          r"(right to modify|unilateral change|change terms at any time|without prior notice)"),
    _rule("gag", "Non-Disparagement Gag Clause",
          r"(disparagement|never publish|negative review|injunctive relief|gag order)"),
)

TONE_RULES: Tuple[Rule, ...] = (
    _rule("deadline", "Deadline pressure",
          r"\b(act now|right away|immediately|within (24|48|72) hours|last chance|final notice|expires? (today|tonight))\b"),
    _rule("threat", "Threat of consequences",
          r"\b(legal action|will be (sued|reported)|or else|forfeited?|penalt(y|ies) will)\b"),
    _rule("secrecy", "Request for secrecy",
          r"\b(do not (tell|share|disclose)|keep (this|it) (confidential|between us)|don'?t tell anyone)\b"),
    _rule("authority", "Appeal to authority",
          r"\b(official (notice|order|directive)|government (requires|mandates)|mandatory compliance)\b"),
    _rule("reassurance", "Reassurance",
          r"\b(don'?t worry|no risk|guaranteed|trust me|just sign)\b"),
)

RULES_BY_KIND = {"clause": CLAUSE_RULES, "tone": TONE_RULES, "motive": TONE_RULES}


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _lower_category(name: str) -> str:
    return _normalise(name).lower()


def _unknown_read(kind: str, reason_code: str, reason: str) -> dict:
    """A whole read that cannot be scored at all (bad input). Still a result."""
    u = Unknown(reason_code, reason)
    return {"kind": kind, "overall": to_result(u), "reads": [], "unchecked": []}


def _passthrough(value: Any, where: str = "model") -> Any:
    """The model's own words, returned unscored. Nothing null or empty crosses
    the boundary: a missing or empty field becomes an explicit Unknown object."""
    if value is None:
        return {"unknown": True, "code": MISSING_INPUT,
                "reason": f"the model left {where} null"}
    if isinstance(value, str) and not value.strip():
        return {"unknown": True, "code": MISSING_INPUT,
                "reason": f"the model left {where} empty"}
    if isinstance(value, dict):
        return {str(k): _passthrough(v, f"{where}.{k}") for k, v in value.items()}
    if isinstance(value, list):
        return [_passthrough(v, f"{where}[{i}]") for i, v in enumerate(value)]
    return value


def _score_finding(index: int, finding: Dict[str, Any], document: str,
                   doc_norm: str, rules: Tuple[Rule, ...], at: str) -> Tuple[dict, List[Tuple[int, int]]]:
    """Score one model finding. Returns its result and the (start, end) spans
    of the quote in the normalised document, so coverage can be checked."""
    quote = finding.get("quote")
    category = finding.get("category")
    if not isinstance(quote, str) or not _normalise(quote):
        return ({"index": index, "ever": to_result(
            Unknown(MISSING_INPUT, f"finding {index + 1} has no quoted text"))}, [])
    if not isinstance(category, str) or not _normalise(category):
        return ({"index": index, "ever": to_result(
            Unknown(MISSING_INPUT, f"finding {index + 1} names no category"))}, [])

    quote_norm = _normalise(quote)
    start = doc_norm.find(quote_norm)
    if start < 0:
        return ({"index": index, "quote": quote_norm, "ever": to_result(
            Unknown(UNVERIFIED_SOURCE,
                    f"finding {index + 1}: the quoted text was not found verbatim in the document"))}, [])
    span = (start, start + len(quote_norm))

    # The model's own claim, at the third-party ceiling.
    model_claim = C(_normalise(category), INTAKE, source="model answer", at=at)

    matches = []
    for rule in rules:
        for m in rule.pattern.finditer(quote_norm):
            matches.append((rule, m))

    evidence: List[dict] = []
    if not matches:
        value = model_claim
        notes = [("INTAKE_SOURCE", "the model's read; a third-party source is at most 120"),
                 ("GROUNDED", "the quoted text appears verbatim in the document"),
                 ("UNCORROBORATED", "no local rule matches this passage; the read rests on the model alone")]
        evidence.append({"phrase": quote_norm, "source": "model quote (no local rule matched)"})
    else:
        same = [(r, m) for r, m in matches if _lower_category(r.category) == _lower_category(category)]
        other = [r for r, _ in matches if _lower_category(r.category) != _lower_category(category)]
        if not same:
            names = sorted({r.category for r in other})
            u = Unknown(CONFLICTING_SOURCES,
                        f"finding {index + 1}: the model said {_normalise(category)!r}, "
                        f"but a local rule found {', '.join(repr(n) for n in names)} in the same passage")
            return ({"index": index, "quote": quote_norm, "ever": to_result(u)}, [span])
        # Same value as the model's claim (the rule matched it case-insensitively),
        # from a source independent of the model.
        rule_claim = C(_normalise(category), CERTAIN,
                       source=f"local rule {same[0][0].rule_id}", at=at)
        value = corroborate(model_claim, rule_claim)
        notes = [("INTAKE_SOURCE", "the model's read; a third-party source is at most 120"),
                 ("GROUNDED", "the quoted text appears verbatim in the document"),
                 ("CORROBORATED", "an independent local rule matches the same passage and agrees")]
        for r, m in same:
            evidence.append({"phrase": m.group(0), "source": f"rule: {r.category}"})

    if isinstance(value, Unknown):
        ever = to_result(value)
    else:
        ever = to_result(value, notes=notes, evidence=evidence)
    return ({"index": index, "quote": quote_norm, "ever": ever}, [span])


def wrap_read(kind: Any, document: Any, answer: Any, *, at: Optional[str] = None) -> dict:
    """Score a model's read. Always returns a dict in the app's shape; never raises
    for bad input (bad input is itself an Unknown, MALFORMED)."""
    if kind not in KINDS:
        return _unknown_read(str(kind), MALFORMED, f"kind must be one of {KINDS}")
    if not isinstance(document, str) or not _normalise(document):
        return _unknown_read(kind, MISSING_INPUT, "the document text is empty")
    if not isinstance(answer, dict):
        return _unknown_read(kind, MALFORMED, "the model's answer must be an object")
    findings = answer.get("findings", [])
    if not isinstance(findings, list):
        return _unknown_read(kind, MALFORMED, "the model's answer has no findings list")

    at_stamp = at if at is not None else NOT_RECORDED
    rules = RULES_BY_KIND[kind]
    doc_norm = _normalise(document)

    reads: List[dict] = []
    spans: List[Tuple[int, int]] = []
    for i, f in enumerate(findings):
        if not isinstance(f, dict):
            reads.append({"index": i, "ever": to_result(
                Unknown(MALFORMED, f"finding {i + 1} is not an object"))})
            continue
        res, sp = _score_finding(i, f, document, doc_norm, rules, at_stamp)
        res["model"] = _passthrough(f, f"finding {i + 1}")
        reads.append(res)
        spans.extend(sp)

    # Rule matches in the whole document that no reported quote covers.
    unchecked: List[dict] = []
    for rule in rules:
        for m in rule.pattern.finditer(doc_norm):
            covered = any(s <= m.start() and m.end() <= e for s, e in spans)
            if covered:
                continue
            u = Unknown(CONFLICTING_SOURCES,
                        f"a local rule found {rule.category!r} at {m.group(0)!r}, "
                        f"which the model did not report")
            unchecked.append({"rule": rule.rule_id, "phrase": m.group(0), "ever": to_result(u)})

    # Overall: one Unknown poisons the aggregate, with its reason kept.
    unknown_reads = [r for r in reads if r["ever"]["state"] == "unknown"]
    unknown_reads += [u for u in unchecked]
    if unknown_reads:
        first = unknown_reads[0]["ever"]["reasons"][0]
        overall_u = Unknown(first["code"], first["reason"],
                            chain=[f"{len(unknown_reads)} of {len(reads) + len(unchecked)} reads are unknown"])
        overall = to_result(overall_u)
    elif not reads:
        overall = to_result(C(0, INTAKE, source="model answer", at=at_stamp),
                            notes=[("INTAKE_SOURCE", "the model reported nothing"),
                                   ("UNCORROBORATED", "no local rule matched the document either")])
    else:
        conf = min(r["ever"]["score"] for r in reads)
        all_corr = all(any(n["code"] == "CORROBORATED" for n in r["ever"]["reasons"]) for r in reads)
        overall = to_result(
            C(len(reads), conf, source="derived from every read", at=at_stamp),
            notes=[("INTAKE_SOURCE", "the count of the model's reads"),
                   ("CORROBORATED" if all_corr else "UNCORROBORATED",
                    "every read is corroborated by a local rule" if all_corr
                    else "at least one read rests on the model alone")])

    return {
        "kind": kind,
        "document_sha256": _digest(document),
        "overall": overall,
        "reads": reads,
        "unchecked": unchecked,
    }
