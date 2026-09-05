# everconf

A value that carries how much you can trust it.

```python
from everconf import C, UNKNOWN

total = C(88) + C(76) + UNKNOWN + C(91)
# total is UNKNOWN — not 88+76+91 with the gap silently skipped
```

One missing input and the total is honestly unknown. Not a number computed by dropping the piece you didn't have — which
is what
`sum(skipna=True)` does by default, and what most pipelines do without anyone deciding to.

## The demo that's the actual point

```python
from everconf import C, UNKNOWN, sigmoid, mse

preds   = [C(0.9), C(0.2), C(0.6)]
actual  = [C(1), C(0), C(1)]
mse(preds, actual)
# C(0.07, confidence=256)

actual_with_gap = [C(1), C(0), UNKNOWN]   # one label never recorded
mse(preds, actual_with_gap)
# UNKNOWN
```

A model evaluated against partly-missing labels doesn't get to report a loss number as if it saw the whole dataset.
That's not a special case bolted on — it falls straight out of the one rule everything in this library follows: **a
result is only as trustworthy as its least trustworthy input, and one genuinely unknown input makes the whole
computation unknown.**

## Confidence, not just missing/present

Every `C` carries a trust score from 0 to 256, not just a bit for
"is this NaN."

```python
from_your_own_measurement = C(10, confidence=256)
from_a_third_party_api    = C(20, confidence=120)

(from_your_own_measurement + from_a_third_party_api).confidence
# 120 — a result can be no more certain than its weakest input
```

```python
value = risky_computation()
value.require(floor=128)   # raises LowConfidenceError if too weak
                            # to act on — before you send the email,
                            # charge the card, ship the number
```

## What this is not

Not a statistics library. No distributions, no standard deviations, no Bayesian updates. If you need that rigor, look at
[`Uncertain<T>`](https://www.microsoft.com/en-us/research/publication/uncertaint-a-first-order-type-for-uncertain-data/)
(Bornholt et al., Microsoft Research) or Julia's `Measurements.jl` — both are more sophisticated, and both require more
of you to use correctly. `everconf` trades that rigor for a single `int` anyone can read at a glance, because most
pipelines don't need a posterior distribution. They need to stop lying when something is missing.

## Install

```bash
pip install everconf
```

No dependencies. Every claim in this README is checked by the test suite — `pytest tests/` — and every code block above
is a real doctest, run and verified before each release, not typed from memory.

## Where this comes from

`everconf` is the confidence-value core of
[Ever](https://github.com/codric/tapestry) — a full language built around the same rule everywhere: arithmetic,
branching, recursion (you can't claim a computation terminates without a decreasing measure), foreign function calls
(code you can't audit can't earn full trust), and machine learning. This library is that idea, with zero switching cost,
for the one place it's most immediately useful:
a Python pipeline that shouldn't get to guess.

Codric Enterprise · Ricky (Dreid) · 2026
