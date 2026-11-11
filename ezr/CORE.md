# EZR — The Core

**Version 1.0 · Codric Enterprise · Ricky (Dreid) · 2026**

The language that sixteen independently derived front ends agree on.
Where they disagreed, this document records who settled it and on what
authority. Nothing here was decided by preference.

---

> **Which language this specifies.** This document is the forge's ratified
> core — the language `7-forge/` arbitrated and `5-runtime-java/`
> implements. It is *not* the language `ever run` (the STATEMENT surface —
> `runtime.py`, records, loops, indexing, `extern`) executes. It IS,
> since `eval_ast` (`2-interpreter-python/syntax.py`, driven by
> `ezrun.py`) learned this core's binding, list literals and its four
> builtins, the language `ezrun.py` executes — no Java build required;
> see FINDINGS.md §7.11. `5-runtime-java/differential.py` measures what
> is left: 128 programs, 123 agreed, 5 diverged — a numeric-precision
> limit, two staging differences (arity/unbound checked at compile time
> in Java, at runtime in Python), and two settled grammar questions
> (trailing comma, a trailing expression after definitions) where v4.10
> permits what this core's doctrine forbids. Read this file for what the
> forge settled; read `SEMANTICS.md` for the OTHER surface `ever run`
> executes — the two are siblings now, not a full language against a
> five-file demo.

---

## 0. What this is, and what it is not

EZR V3.0 shipped a working front end and no specification of it.
`2-interpreter-python/syntax.py` was the lexer, the parser, and — by
default — the only statement of what the language accepted. That is
stable until somebody writes a second implementation, at which point
there is nothing to check it against.

So layer 7 wrote the second implementation, and the third, and the
fourth. Four scanners, four parsers, every pairing run over the same
corpus. **Sixteen front ends agreeing is evidence about the language.
One front end agreeing with itself is evidence about nothing** — which
is SEMANTICS.md 2.2's independence requirement applied to the front end
rather than to values.

This document is **not** a new language. Every rule below was already
implied by SEMANTICS.md or PIPELINE.md, or already implemented in
`abstract.py`. What the forge did was find the seven places where the
implication had never been written down, and write them down.

---

## 1. The grammar

Stated in full in [`7-forge/GRAMMAR.ebnf`](7-forge/GRAMMAR.ebnf), which
is **emitted from the chart parser's own rule table** rather than
typed. A hand-written grammar agrees with the code on the day it is
written; an emitted one cannot disagree.

```
program        = definitions | expression ;
definitions    = definition , { definition } ;
definition     = "def" , name , "(" , [ parameters ] , ")" , "=" , expression ;
parameters     = name , { "," , name } ;

expression     = conditional | comparison ;
conditional    = "if" , expression , "then" , expression , "else" , expression ;
comparison     = additive , [ compare-op , additive ] ;
additive       = additive , add-op , multiplicative | multiplicative ;
multiplicative = multiplicative , mul-op , unary | unary ;
unary          = "-" , unary | atom ;
atom           = number | string | "true" | "false"
               | "(" , expression , ")"
               | name , "(" , [ arguments ] , ")"
               | name ;
arguments      = expression , { "," , expression } ;
```

The additive and multiplicative rules are **left-recursive on
purpose**. Associativity is then a property of the grammar rather than
of a loop somebody wrote, and the chart parser can be asked whether the
grammar is ambiguous — which is how finding 5 below was caught.

This closes the first line of SEMANTICS.md section 7:

> | Formal grammar (EBNF) | parsing is regex-based |

### 1.1 Token kinds

The table nobody had written, now measured rather than asserted — every
kind below is one all four scanners assign.

| Kind | Members |
|---|---|
| `NUM` | a number |
| `STR` | a string |
| `NAME` | a name that is not a keyword |
| `KW` | `def` `else` `false` `if` `then` `true` |
| `CMP` | `<` `>` `<=` `>=` `==` `!=` |
| `OP` | `+` `-` `*` `/` |
| `EQ` | `=` |
| `LPAR` `RPAR` `COMMA` | `(` `)` `,` |
| `EOF` | end of input |

---

### 1.2 The builtins

Four names the language provides, and no others. They are called like
any function and lex as ordinary names, not keywords — `show` sat in
the incumbent's reserved list for years, among the thirteen words
reserved against a syntax that did not exist, and had to be *un*reserved
to become callable.

| | | |
|---|---|---|
| `show(x)` | prints `x` with its confidence, returns `x` unchanged | the only way a program has of being observed from outside |
| `len(xs)` | how many | |
| `head(xs)` | the first | `head([])` is a refusal, not an exception and not a silent empty answer |
| `tail(xs)` | the rest | same |

Each obeys the chain rule: a result is no more trusted than the
argument it came from. `show` returns its argument so it composes
anywhere — `show(total([1,2,3]))` is `total([1,2,3])` with a side
effect, not a statement you have to hoist out.

**They are part of the core because a list you cannot take apart is not
a list.** Adding the literal without the accessors would have delivered
a data structure that could be built and never used, which is not a
feature, and the auditor now checks that the set stays exactly these
four rather than drifting.

## 2. The seven rulings

Each was open, in the sense that independent implementations answered
differently or the answer existed nowhere. Each is now closed, with the
authority that closed it.

| # | Question | Ruling | Settled by |
|---|---|---|---|
| 1 | which kind carries a bare `<` | `CMP` | doctrine |
| 2 | defect for an unclosed string | `unbounded` | doctrine |
| 3 | which words are reserved | the six the grammar uses | doctrine |
| 4 | several definitions per text | yes | coverage gap |
| 5 | a trailing expression after them | no | law `unambiguous` |
| 6 | chained comparison `a < b < c` | no | doctrine |
| 7 | trailing comma in a list | no | consensus 16/16 |

### 2.1 Arbitration has an order, and a vote is not the top of it

1. **Doctrine.** SEMANTICS.md or PIPELINE.md already says. A vote
   cannot overturn a published document, so this tier runs before
   anybody is counted.
2. **Coverage.** Stage 4 demonstrably holds something stages 1–3 cannot
   express. **Consensus is blind to this**: all four front ends can
   agree, sincerely and unanimously, on a limitation that the rest of
   the language does not have, and a vote would then write that
   limitation into the specification.
3. **Finding.** One of the laws settles it. A law violation is evidence
   about the language, not about one implementation, so it outranks a
   vote among implementations that might share the defect.
4. **Consensus.** VOWELS.md's oracle, unchanged: at least ⌊π⌋ = 3
   agreeing and at least two thirds of those that answered.

Below all four it **withholds**. Inventing an answer there would teach
the corpus a fact nobody verified, which is the one thing the language
exists to prevent.

### 2.2 The rulings, in full

**1 — a bare `<` is `CMP`.** The four scanners split two-two before a
single test was written: the master-regex and trie scanners inherited
the incumbent's table, where `<` sits under `OP`; the hand scanner and
the DFA put it under `CMP`, because both decide `<` and `<=` in the
same branch. Consensus **withheld** — two against two is below ⌊π⌋ = 3.
Doctrine settled it: PIPELINE.md prints `compare := additive [ CMP
additive ]`, so a bare `<` that scans as `OP` cannot satisfy the rule
the project already published.

**2 — an unclosed string is `unbounded`, not `misbound`.** PIPELINE.md
classifies running out of input (`1 +`) as `Z(unbounded)` and an
illegal character (`a $ b`) as `Z(misbound)`. A string with no closing
quote ran out of input. The incumbent reported `misbound`, and its own
guard for the case —

```python
if kind is T.STR and not text.endswith('"'):
```

— **can never fire**, because the pattern `"[^"\n]*"` requires the
closing quote in order to match at all. Three of the four new scanners
found `unbounded` independently; doctrine agreed with them.

**3 — six reserved words, not nineteen.** The incumbent reserves 19;
the grammar reaches 6. The other 13 — `anchor` `ascend` `assimilate`
`by` `equiv` `ezr` `example` `expect` `learn` `let` `show` `to` `z` —
appear in no rule, so they reserve names against a syntax that does not
exist. `def area(to) = to * 2` failed to parse for no semantic reason.
PIPELINE.md settles it directly: *"This is the whole language. Anything
not derivable here is outside the grammar."*

**4 — several definitions in one text.** All sixteen front ends refused
`def f(n) = n` followed by `def g(n) = n + 1`, unanimously, and the
unanimity was wrong. `abstract.py`'s `Lambda.globals` is a dictionary;
the probe defines `double` and `triple`, holds both, and evaluates
`double(4) = 8` and `triple(4) = 12`. SEMANTICS.md 7 calls the
namespace it is missing a module system for *"one flat global
namespace"* — a namespace the runtime already populates and the grammar
could not address. That is a gap in the **grammar**, and no number of
parsers agreeing changes it.

**5 — no trailing expression after the definitions.** Closing gap 4 the
obvious way — `program := definitions [ expression ]` — makes the
grammar **ambiguous**, and the chart parser said so on the third
generation. `def f(n) = 1 - 1` has two derivations: a body of `1 - 1`,
or a body of `1` followed by the expression `- 1` under prefix minus.
The three deterministic parsers resolve it greedily and never mention
it; only a parser driven by the written grammar can report that the
grammar itself does not decide. Dropping the trailing expression
removes the ambiguity and still closes gap 4, which was about holding
several definitions and never about a trailing expression.

**6 — chained comparison does not parse.** `compare := additive [ CMP
additive ]`: the brackets are optional-once, not repeated.

**7 — no trailing comma.** All sixteen refused it and no document
contradicts them, so this one is genuinely a consensus ruling — the
only one of the seven.

---

## 3. Two defects the laws caught

Not questions about the language; straightforward bugs, found because
the properties were stated universally rather than case by case.

**A conditional is not an operand.** The Pratt and shunting-yard
parsers both handled `if` in operand position, because that is where a
table-driven parser naturally puts a prefix construct. So both accepted
`if a then 1 else 2 != 3` as a comparison whose *left side* was the
conditional. PIPELINE.md puts `ifexpr` as an alternative of `expr`, not
a member of `atom`, so a conditional is never an operand — on the left
or the right. `1 + if a then 2 else 3` is outside the grammar;
`(if a then 1 else 2) != 3` is inside it, and parentheses are the only
thing that makes a conditional an atom.

**The incumbent discarded everything after a definition.**
`syntax.py`'s `program()` returned from the definition branch without
checking that it had reached the end of the input, while the
expression branch checked. So `1 2` was refused and

```
def f(n) = n ) ) )
def f(n) = n garbage
```

both came back `stage="ready"` with the tail silently dropped. All
sixteen forge front ends refuse those texts; the incumbent did not,
and the asymmetry between its own two branches is what gives it away.
Fixed in `2-interpreter-python/syntax.py`; its 212 assertions pass
unchanged, so no test had been asserting the defect.

**The DFA scanner raised on a bare `.`.** A `.` reaching the table in
start position is in no row, so the lookup raised `KeyError` instead of
refusing. Found by the fuzzer inside `let9.1`. SEMANTICS.md G1 says
evaluation is total — *"no exceptions, no undefined behavior"* — and a
scanner that raises makes that a property of whoever remembered to
catch it. It now refuses with `misbound`.

**The trie scanner used `$` as its end-of-token marker.** `$` is a
character a source text may contain, so a `$` in the input walked into
the marker, and the next character indexed a tuple:
`TypeError: tuple indices must be integers`. Found at generation 7 on
`false =$= 35`, which is to say: found because the fuzz budget doubles
after every clean generation, and the seventh generation was the first
one big enough. The fix is a sentinel that cannot collide with the
alphabet it indexes, not a guard against the one character that
happened to break it.

---

## 4. The laws

Stated over all inputs, which is the only kind of statement a fuzzer
can attack.

| Law | Requires |
|---|---|
| `total` | no scanner and no parser ever raises |
| `agreement` | all sixteen reach one verdict |
| `unambiguous` | no text has two trees |
| `roundtrip` | printing a tree and reading it back is the identity |
| `determinism` | the same text twice gives the same answer |
| `position` | every refusal points inside the text it refused |
| `token-stream` | one `EOF`, last; positions never go backwards |

A **verdict** is the tree when the text is accepted, otherwise the
stage and the binding defect. The *position* of a refusal is
deliberately not part of it: a chart parser reports the furthest column
its grammar reached and a recursive-descent parser reports the token it
choked on. Both are honest, they are not the same number, and neither
is a claim about the language. Position is still checked — it must land
inside the text — it just does not decide whether two front ends agree.

---

## 5. What is not claimed

- **Semantics are untouched.** The forge settles stages 1–3. Every rule
  in SEMANTICS.md — the chain rule, corroboration, anchoring, the
  execute floor — is exactly as it was. The four layers keep their own
  sides of the line.
- **No new language features.** Multi-definition is the one place the
  grammar grew, and it grew to reach a capability the runtime already
  had and a document already named. Everything else the forge did was
  subtract, correct, or write down.
- **Convergence is a statement about a search, not a proof.** No
  counterexample was found; that is not a proof that none exists.
  `undermine` in VOWELS.md returns **Z** for exactly this reason, and
  the same honesty applies here. The search that stands behind this
  document: **520,600 programs**, generated and mutated, run through
  all sixteen front ends, over **61 generations**, of which **60 were
  clean** — the one that was not is generation 0, before any question
  had been settled.

  That search came in two parts, and they asked different things.
  Convergence came first: 250,600 programs over 16 generations, the
  budget doubling after every clean one, ending on 15 consecutive
  clean generations at 25,000 each. Then 85 exploration cycles of
  6,000 programs each, on seed bases disjoint from the convergence
  run, rotating the fuzzer's nesting ceiling from 3 up to **8** — the
  convergence run never generated a program deeper than 5, so the
  grammar's deep end had gone untested no matter how many programs it
  drew. Nothing was found: no golden failure, no law violation, no
  divergence, and not one new counterexample promoted in any cycle.
  `7-forge/ledger.json` is the full record.
- **The gaps SEMANTICS.md 7 still names remain open.** Composite data,
  higher-order functions, pattern matching, a static type system, a
  module system, transpiler back-ends, a soundness proof. The formal
  grammar is the one line of that table this work crosses off.

---

## 6. The loop, closed

Through section 5 the forge could find a defect, classify it, and carry
a counterexample forever — and a person still wrote every fix. Two
pieces close that.

### 6.1 The grammar writes a parser

`grammar_doc.py` emits `GRAMMAR.ebnf` *from* the parser's rule table, so
the document cannot drift from the code. `selfgen.py` emits a working
parser *from* those same rules, so the code cannot drift from the
document either. The output is Python source on disk — direct left
recursion turned into a loop that still builds a left-associated tree,
alternatives ordered longest-first with local backtracking — and it is
then loaded and registered as a fifth parser.

**Sixteen front ends became twenty.** The generated parser is judged
exactly like the hand-written four: same corpus, same laws, same fuzz.
That is the entire point of it. A generated parser agreeing with four
independently hand-written ones is evidence that the stated grammar
really does describe what the implementations do; a generated parser
disagreeing is a sharper finding than any other the forge can make,
because exactly one of two things must then be wrong — the grammar is
not what the parsers implement, or a parser is not what the grammar
says.

Observed: agreement on the whole corpus and on 24,000 fuzzed programs
at nesting depths 3 through 8, no divergence.

### 6.2 A front end repairs itself

`repair.py` runs detect → localise → synthesise → verify → adopt →
record, with nobody in the loop.

**What decides the repair is not a guess.** When one front end raises,
the others are still standing there with an answer, so the repair asks
them. At least ⌊π⌋ = 3 agreeing and two thirds of those that answered —
the same rule VOWELS.md uses for its oracle and section 2.1 uses for
arbitration, pointed at the implementation rather than the
specification. Where they do not agree it **withholds**.

The repair grammar is small and stated, because an unbounded repair
space is how a self-modifying system talks itself into anything:

| | |
|---|---|
| **R1 totality shield** | a component that raises is made to refuse, with the defect class the others agree on — restoring G1 |
| **R2 regenerate** | the generated parser is re-emitted from the current grammar |

R1 does not claim to fix the logic that raised. It restores a *stated
guarantee* and pins the input that exposed it permanently in the
corpus, so the root cause stays visible and stays findable. What stops
is the language violating its own G1 while nobody is looking.

**Adoption requires that nothing else moves.** A candidate is adopted
only if it fixes the defect *and* every input already known produces an
identical verdict afterwards. That is what keeps a shield from becoming
a way to make failures disappear: a candidate that alters a passing
case is rejected, and the rejection is recorded.

Nothing is deleted — a shielded component keeps the original callable
on `_unshielded`, and `repairs.json` records what raised, what the
witnesses agreed the answer should be, and the input that exposed it.

**Two things it refuses to do**, both verified in the test suite:
it will not repair when the survivors disagree, and it will not repair
when the survivors *accept* the input — a shield can turn a crash into
a refusal, but it cannot synthesise a parse tree, and pretending
otherwise would teach the corpus a fact nobody verified.

`selfheal.py` demonstrates the whole thing end to end on a real defect:
the trie scanner's `$` sentinel, the bug the fuzzer actually found at
generation 7, put back deliberately. Detected, localised to the right
component, target taken from fifteen surviving witnesses, shielded,
verified against the full regression set, adopted. It runs as part of
`run.sh`, so the claim that the loop closes is checked rather than
asserted.

---

## 7. Which front end is which

Two front ends now exist, and they are not the same thing.

| | |
|---|---|
| `2-interpreter-python/syntax.py` | **EZR V3.0's front end.** Still `program := fndef \| expr` — one definition per text. One fix applied: it now checks for end of input in both branches. |
| `7-forge/` | **The reference front end for the core.** Four scanners and four parsers, all sixteen pairings agreeing on the grammar in section 1. |

So `syntax.py` refuses a two-definition text and the core accepts one.
**Adopting the core grammar in `syntax.py` is the obvious next step and
is not done here** — it would be a change to the seed's own parser
rather than a finding about the language, and it belongs in its own
change with the pipeline's 63 assertions re-derived against the new
rules.

---

## 8. The laws, and how far they reach

Five of the six were already here, which is not a flourish -- it is
what the algebra turns out to be once you write down what it does.
`2-interpreter-python/physics.py` checks them; it did not invent them.

**How far they reach, stated before the table, because the heading
above used to overstate it.** Five of these are *properties of the
existing algebra*: they describe what the chain rule, `obliterate` and
the confidence bounds already do, and `physics.py` verifies that they
still hold. They are not a layer the evaluator was rewritten to run
under. Newton II is a *facility* -- implemented and tested, and with no
caller in either evaluator, so nothing is yet moved by force during
ordinary evaluation. `Subsystem` is enforced at runtime in exactly one
place, `ultra.py`, where the accounting is the precondition for
granting depth.

That distinction matters enough to be checked rather than remembered,
so `audit.py` now probes it: a law claimed as enforced must have a
caller outside the tests, and one claimed as a property must verify.
This section previously read "the laws the language runs under", which
was true of neither category.

| Law | Already in EZR as |
|---|---|
| **Thermodynamics I** — nothing is created or destroyed | `obliterate` supersedes and archives; conservation is a law here, not a preference (VOWELS.md) |
| **Thermodynamics II** — entropy never spontaneously falls | G3. Uncertainty is `u = (256 − c)/256`, the chain rule takes the *minimum* confidence, so `u` of a derived thread is the *maximum* `u` of its inputs. Ascend and Excel are the work done from outside |
| **Thermodynamics III** — absolute zero is unreachable | T3. `u = 0` needs some `u_i = 0` exactly, and a product of non-zero terms is never zero, so Excel caps at 255 and `Certain` must enter from outside |
| **Newton I** — inertia | G9. No mutation; every thread is derived, never overwritten |
| **Newton III** — action and reaction | every supersession writes exactly one boundary marker saying where the previous best stood |

**Newton II is the one genuinely new thing**, and it is marked as
defined rather than discovered because `F = ma` had no counterpart in
the existing rules. Inertia is accumulated evidence —
`m = 1 + generation + ascend_points + (⌊π⌋ if anchored)` — and the same
force moves a well-attested thread less than a fresh one. Observed: a
force of −40 takes a fresh thread from 200 to 160, and an anchored one
with three Ascend points from 200 to 195. A function that has survived
three Examples and earned an anchor should not be knocked over by the
push that flattens something defined a moment ago, and until now
nothing in the language said so.

### 8.1 The subsystem

`Subsystem` is the closed accounting: every thread admitted has exactly
one of four dispositions at every moment, and the four exhaust the
possibilities — **created**, **utilised** (consumed deriving something
else), **recycled** (superseded, and archived), **resident**. Nothing
leaves without a record. That is what makes the first law checkable
rather than merely stated, and it is why a conservation failure can
refuse a result instead of being noticed later.

### 8.2 Ultra-anchored recursion

An anchor buys depth: SEMANTICS.md 4.6 gives a cleared function with a
proven measure `limit = ∞`. **It did not actually get it.** Removing
EZR's ceiling only exposes CPython's, and an anchored `fact` died of
`RecursionError` around depth 300 — for reasons having nothing to do
with EZR, in a language whose own documents promise unbounded depth.

Ultra-anchoring is anchoring that can be cashed. Three things, all
required:

1. **anchored** — the existing bar, unchanged. Depth is earned.
2. **provisioned** — the call runs in an execution context reserved to
   deliver that depth, its own stack sized up front. A promise the
   runtime cannot honour is not a weaker promise, it is a false one.
3. **conserving** — every thread the recursion creates is accounted
   for when it ends. Depth without accounting is how you lose track of
   what a computation did; the ledger is why the depth is safe to grant.

Observed: `fact(1000)` refused unprovisioned, 2,568 digits under an
ultra-anchor. `fact(3900)` computes. `fact(5000)` refuses — **at EZR's
own stated ceiling of 4,000, not at CPython's stack.** The limit is the
language's now, for the language's reasons.

---

## 9. Finding the variances

Both of the last two real bugs sat in stage 4, where the forge does not
look. `2-interpreter-python/audit.py` is that check written down so it
happens every run rather than when somebody thinks to look.

It reads the claims out of the documents — including SEMANTICS.md
section 7's table, row by row, as it currently stands — and tests each
one against the code. Variance is reported in both directions:

| | |
|---|---|
| **OVERSTATED** | the documents promise something the code does not do. The dangerous kind: somebody is relying on it. Fails the run |
| **UNDERSTATED** | the code does something the documents deny. Cheaper, but still false, and it hides finished work from whoever is deciding what to build next. Reported, does not fail |
| **UNDECIDED** | no probe can settle it. Said plainly rather than counted as a pass — an auditor reporting a clean bill because it could not run is worse than no auditor |

It found three understatements immediately, and all three were true:
lists, higher-order functions and the formal grammar were all listed as
missing while working. **Higher-order functions had been listed missing
for as long as SEMANTICS.md existed and worked the whole time.**
Section 7 has been corrected against what the probes actually
establish, and the auditor now reports zero overstated, zero
understated, one undecided — the soundness proof, which no test here
can settle.

---

## 10. What the emitted grammar makes possible

PIPELINE.md ends by naming what stage 4 does not have:

> **A compiler.** The right-hand branch of the diagram — `Interpreter
> OR Compiler` — is still only the left one.

An emitter is a printer with a different target, and `roundtrip` is
already the law that a printer must satisfy. The core now has a written
grammar, a canonical tree, a printer verified against sixteen readers,
and a corpus that says what every one of them must produce. That is the
input a back-end needs.
