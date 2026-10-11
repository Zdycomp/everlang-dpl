# Ever (Tapestry)

A programming language where every value carries a trust level from 0 to 256.

## Install

```bash
pip install -e .
```

## Use

```bash
ever run program.ever      # execute a program
ever check program.ever    # parse + type-check only (CI/editors)
ever repl                  # interactive session
ever profile               # your proficiency profile
```

## The idea

Every value knows how much it can be trusted. A literal you wrote is
certain (256). Data from outside enters at 120 — below the execute
floor of 128, so you cannot act on it without corroboration. And `z`
is not zero; it is the honest absence of a measurement.

```ever
let hw_score = 88
ever attendance = z          # never recorded — unknown, not zero
ever total = hw_score + attendance

show total                   # total = z [0/256]
```

`total` is `z`, not `88`. An unknown poisons what it touches instead
of quietly becoming a plausible wrong number. That is the whole point.

## Language

```ever
let x = 10                   # binding
ever y = 20                  # tracked binding
z                            # the unknown

def square(n) = n * n        # function
def max2(a, b) = if a > b then a else b

if x > 5 then "big" else "small"

show x                       # print with confidence
```

Operators: `+ - * /` and `< > <= >= == !=`. Division always yields a
real. Types are checked before anything runs.

## The depth ceiling

Unanchored recursion is capped at 3 call levels — `floor(pi)`. Past
it, a call returns `z` rather than a number it has not earned the
right to compute:

```ever
def fact(n) = if n <= 1 then 1 else n * fact(n - 1)
ever a = fact(3)   # 6
ever b = fact(4)   # z [0/256]
```

## Proficiency

The semantic pass classifies which constructs you use and shifts a
score on the same 0–256 scale. It drives one thing: how much
explanation errors carry. Beginners get worked examples; fluent users
get the error and nothing else. `ever profile` shows where you are and
what to try next.

Codric Enterprise · Ricky (Dreid) · 2026
