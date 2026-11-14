# Financial Continuity Profile

*A plain-English spec for people who run exchanges, payment systems, and settlement desks. No programming knowledge is needed to read this.*

## The problem it solves

Software that moves money often receives a number it cannot fully trust: a price from a feed that timed out, a fee that was never filled in, a balance from a source that disagrees with another. In many systems, a missing or broken number quietly becomes a zero, or is skipped, and the trade goes through anyway. The loss is found later, if at all.

The Financial Continuity Profile makes that impossible by design. When a number cannot be trusted, the system does not guess. It stops the action, and it writes down exactly why.

## The three rules

1. **An unknown is never silently used.** An "unknown" is a first-class answer. It says *that* there is no answer, *why* (a short code and a sentence a person can read), and *what led to it*. Anything built on an unknown is also unknown, and keeps the original reason.

2. **In strict mode, an unknown stops the action.** No trade is placed. No settlement is made. The system still returns the full explanation, so an operator can see what happened and fix it.

3. **Every decision is written down and can be checked again.** Each decision records the inputs, how trustworthy the inputs were, the threshold that applied, and the outcome. The record is append-only and chained, so an edit or a deleted line is detectable.

## What "trust" means here

Every value carries a score from 0 to 256, shown to people as words:

| Score | Words | Meaning in practice |
|---|---|---|
| 224 to 256 | very sure | Usable for a strict action. The strict threshold is 224. |
| 160 to 223 | pretty sure | Enough to show, not enough for a strict action. |
| 1 to 159 | not sure | Show with a warning only. |
| 0 | can't tell | An unknown. Strict mode stops the action. |

A value read from outside the system (a feed, an API, a document, a model) starts at most at 120, "not sure". Only a value the system can verify from a non-model source can reach "very sure". Confidence can fall through a calculation. It can rise only when two independent sources agree, and then only to 180 ("pretty sure").

## Provenance: where every number came from

Each value keeps its history: each step that produced it, where that step's input came from, when it was recorded, and its confidence at that step. Someone reviewing a settlement can see, for example, that a price came from the exchange feed at 02:59:59 with confidence 256, that a fee came from a fee schedule that timed out, and that the total is therefore unknown.

## The audit log

- **One line per decision.** Each line contains the decision's time stamp (supplied by the caller, never read from the system clock), the action, the inputs, the confidence, the threshold, the outcome, the reasons, and the full explanation.
- **Append-only.** New decisions are added to the end. Existing lines are never rewritten. The program refuses to add to a log that has already been altered.
- **Chained.** Each line carries a fingerprint (a SHA-256 hash) of the line before it. Editing, deleting, or reordering any line breaks the chain from that point on. A verification step reports the first broken line.
- **What the chain does not catch.** Deleting the last line leaves every remaining fingerprint valid, so an
  empty tail cannot be detected from the file alone. Keep the latest fingerprint somewhere else (for
  example, in the institution's own records) and compare against it. An editor who recalculates
  fingerprints is caught by replay, not by the chain.

## Deterministic replay

Given the same inputs and the same time stamp, the system always produces the same confidence and the same decision. An auditor can take a log and recompute every decision from its recorded inputs. If any recorded decision cannot be reproduced exactly, the replay reports which line and which field differs. This also catches someone who edits a line and recalculates its fingerprint: the chain still checks, but the replayed decision does not match what was written.

## A worked example

A settlement desk needs to net a trade's fee against its price.

1. The price arrives from the exchange feed: 250, certain (256).
2. The fee arrives from the fee service, which times out. The system records an unknown: *TIMEOUT, fee service did not answer*.
3. The net is computed. Because the fee is unknown, the net is unknown. The reason, *fee service did not answer*, is kept.
4. The strict profile decides: **HALT**. The trade does not settle. The explanation is returned to the desk, and the decision is appended to the log.
5. When the fee service answers, the desk sends the request again. The new decision is recorded beside the old one. Neither is changed.

## What this profile does not do

- It does not decide whether a trade is wise, legal, or permitted. It decides only whether the numbers it was given are trustworthy enough to act on.
- It does not make a feed trustworthy. If a feed reports wrong numbers with full confidence, the profile will act on them. Confidence describes how a value was obtained, not whether the source is honest.
- It does not replace the controls a regulated institution is required to have. It is one layer that makes missing data visible.
- The threshold of 224 is a default. An institution chooses its own threshold, and should record that choice.

## Who decides what

Choosing the threshold, deciding which sources count as "verified", and deciding what a HALT should trigger (an alert, a manual review, a rollback) are business and compliance decisions. The profile supplies the mechanism and the record. The institution supplies the policy.

## Where it lives

- Library: `everconf/` (`profile.py` for decisions and the log; `result.py` for the explanation format).
- Format of the explanation: `everconf/docs/JSON.md`.
- Tests that prove the three rules, the chain, and replay: `everconf/tests/test_profile.py`.
