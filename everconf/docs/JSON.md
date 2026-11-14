# everconf JSON shape

Every result the app receives has this shape. `value` is never null: an unknown result says so in `value` (`{"unknown": true}`), and always carries at least one reason.

| field | meaning |
|---|---|
| `value` | the value, or `{"unknown": true}` |
| `state` | `known` or `unknown` |
| `score` | confidence, 0 to 256 |
| `percent` | score / 256, rounded half up, 0 to 100 |
| `label` | `very sure` (224+), `pretty sure` (160 to 223), `not sure` (1 to 159), `can't tell` (0 or unknown) |
| `reasons` | `[{code, reason}]`, never empty. Codes come from `spec/reason_codes.tsv` |
| `chain` | unknown only: the steps the unknown passed through, oldest first |
| `evidence` | `[{phrase, source}]`: the words or phrases that drove the score |
| `provenance` | every step that produced the value, origin first, each with its own confidence |

Reads from a model (`clause`, `tone`, `motive`) come back as an envelope: `kind`, `document_sha256`, `overall`, `reads` (one per model finding, each with `quote`, `ever`, and the model's own `model` text), and `unchecked` (rule matches the model did not report).

## Labels

Score bands on the 0 to 256 scale:

- 224 to 256: **very sure**. Reachable from a non-model source only. A model's read is at most 180.
- 160 to 223: **pretty sure**. A grounded model read that a local rule corroborates (180).
- 1 to 159: **not sure**. A grounded model read with no corroboration (120), or a value below the threshold.
- 0, or any unknown: **can't tell**.

## A value you wrote in the program

`C(42)` is certain. The `notes` say why, and `provenance` shows its one step.

```json example=literal
{
  "value": 42,
  "state": "known",
  "score": 256,
  "percent": 100,
  "label": "very sure",
  "reasons": [
    {
      "code": "CERTAIN_LITERAL",
      "reason": "written directly in the program"
    }
  ],
  "chain": [],
  "evidence": [],
  "provenance": [
    {
      "step": "input",
      "source": "literal in code",
      "at": "not recorded",
      "confidence": 256
    }
  ]
}
```

## A value read from outside

A reading from an API is at most `INTAKE` (120), which reads as **not sure**. `percent` is 120/256, rounded: 47.

```json example=from_an_api
{
  "value": 19.99,
  "state": "known",
  "score": 120,
  "percent": 47,
  "label": "not sure",
  "reasons": [
    {
      "code": "INTAKE_SOURCE",
      "reason": "read from price API"
    }
  ],
  "chain": [],
  "evidence": [],
  "provenance": [
    {
      "step": "input",
      "source": "price API",
      "at": "2026-11-13T03:00:00Z",
      "confidence": 120
    }
  ]
}
```

## An unknown that poisons a sum

One `Unknown` in a sum makes the whole sum `state: unknown`, with `value: {"unknown": true}`. The origin's code and reason are kept, and `chain` records the step that carried it.

```json example=unknown_poisons_a_sum
{
  "value": {
    "unknown": true
  },
  "state": "unknown",
  "score": 0,
  "percent": 0,
  "label": "can't tell",
  "reasons": [
    {
      "code": "TIMEOUT",
      "reason": "fee feed did not answer"
    }
  ],
  "chain": [
    "add: poisoned by TIMEOUT",
    "add: poisoned by TIMEOUT"
  ],
  "evidence": [],
  "provenance": [
    {
      "step": "unknown",
      "source": "TIMEOUT",
      "at": "not recorded",
      "confidence": 0
    }
  ]
}
```

## A strict decision that halts

Under the financial profile a 200-confidence value is below the 224 a settlement needs. The outcome is `HALT` (in the audit log's `outcome` field), and the full explanation is still returned.

```json example=financial_halt
{
  "value": 250,
  "state": "known",
  "score": 200,
  "percent": 78,
  "label": "pretty sure",
  "reasons": [
    {
      "code": "INTAKE_SOURCE",
      "reason": "read from exchange feed"
    }
  ],
  "chain": [],
  "evidence": [],
  "provenance": [
    {
      "step": "input",
      "source": "exchange feed",
      "at": "2026-11-13T02:59:59Z",
      "confidence": 200
    }
  ]
}
```

## One clause read from Gemini

A clause the model quoted, checked against the document (`GROUNDED`), and corroborated by the local rule that names the same category (`CORROBORATED`). The score is 180, which reads as **pretty sure**. `evidence` lists the words the rule matched. `model` is the model's own text, unscored.

```json example=clause_read
{
  "value": "Unilateral Indemnification",
  "state": "known",
  "score": 180,
  "percent": 70,
  "label": "pretty sure",
  "reasons": [
    {
      "code": "INTAKE_SOURCE",
      "reason": "the model's read; a third-party source is at most 120"
    },
    {
      "code": "GROUNDED",
      "reason": "the quoted text appears verbatim in the document"
    },
    {
      "code": "CORROBORATED",
      "reason": "an independent local rule matches the same passage and agrees"
    }
  ],
  "chain": [],
  "evidence": [
    {
      "phrase": "indemnify Landlord for any and all claims regardless of fault",
      "source": "rule: Unilateral Indemnification"
    }
  ],
  "provenance": [
    {
      "step": "input",
      "source": "model answer",
      "at": "2026-11-13T03:00:00Z",
      "confidence": 120
    },
    {
      "step": "input",
      "source": "local rule indemnity",
      "at": "2026-11-13T03:00:00Z",
      "confidence": 256
    },
    {
      "step": "corroborate",
      "source": "derived by corroborate",
      "at": "2026-11-13T03:00:00Z",
      "confidence": 180
    }
  ]
}
```
