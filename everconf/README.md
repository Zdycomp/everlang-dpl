# everconf

A value that carries how much you can trust it. Zero dependencies.

```python
from everconf import C, Unknown, MISSING_INPUT

total = C(88) + C(76) + Unknown(MISSING_INPUT, "label 3 was never recorded") + C(91)
# UNKNOWN(MISSING_INPUT: label 3 was never recorded) — not 255 with the gap skipped
```

Two kinds of result, and nothing else:

- `C(value, confidence)`: a real value with a trust score from 0 to 256.
- `Unknown(code, reason)`: no answer exists. Confidence is always 0, and it has a reason code from the registry and a human-readable reason.

Null, `None`, and `NaN` are never returned. `C(None)` raises. An Unknown poisons every computation built from it, and keeps the origin's code and reason.

## Version 0.2.0: breaking changes from 0.1.0

- `UNKNOWN` (a singleton with no reason) is gone. Use `Unknown(code, reason)`.
- `unwrap(default=None)` is gone. It returned a null. Use `.require(min_confidence)`, or read `.value` on a `C` you already checked.
- `C(None)` raises `TypeError`.
- `require(floor=...)` is now `require(min_confidence=...)`.

## Confidence

```python
from everconf import C, INTAKE

measured = C(10, confidence=256)      # you measured this yourself
from_api = C(20, confidence=INTAKE)   # 120: read from outside
(measured + from_api).confidence      # 120 — no more certain than its weakest input
```

Confidence only falls through a calculation, with one exception: `corroborate(a, b)`. When two independent sources of at least 120 agree, the result is at least 180. The exception is recorded in the provenance as `corroborate`.

## Gates

```python
value.require(min_confidence=128)   # raises LowConfidenceError below 128
```

Below the threshold a value can still be displayed (`everconf.result.to_result`), but it must not drive an action.

## The app result shape

`everconf.result.to_result` and the adapter return one JSON shape: `value`, `state`, `score`, `percent`, `label`, `reasons`, `chain`, `evidence`, `provenance`. See `docs/JSON.md` for the field list and worked examples.

## Reads from a model

`everconf.reads.wrap_read(kind, document, answer)` scores a model's clause, tone, or motive read. Each quote must appear verbatim in the document, or it is Unknown. Each read lists the words that drove its score. Local rules that the model did not report are surfaced as Unknown, not dropped.

## Financial profile

`everconf.profile`: a strict profile that halts any action on an unknown, an append-only hash-chained audit log, and deterministic replay. See `docs/FINANCIAL_CONTINUITY.md` for the plain-English spec.

## Adapter for the Express server

```bash
python3 -m everconf.adapter --port 8787        # loopback only
```

`adapters/express/everconf-wrap.mjs` is a zero-dependency Node client. A timeout, an unreachable service, or a bad reply comes back as an Unknown in the same shape.

## Tests

Standard library only. From the repository root: `python3 everconf/tests/test_everconf.py` (and the other files in `everconf/tests/`), and `node --test everconf/adapters/express/wrap.test.mjs`.

## Install

```bash
pip install everconf
```

## What this is not

Not a statistics library. No distributions, no standard deviations, no Bayesian updates. It is one int anyone can read at a glance, because most pipelines don't need a posterior. They need to stop lying when something is missing.

Licensed MIT. Confidence-value core of Ever.
