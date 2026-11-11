# Ever — The Four Stages

**Codric Enterprise · Ricky (Dreid) · 2026**

```
 1. Lexer (Tokenization) ────► [ Tokens ]
      │
      ▼
 2. Parser (Grammar)     ────► [ Abstract Syntax Tree (AST) ]
      │
      ▼
 3. Type Checker / Semantic Analyzer
      │
      ▼
 4. Execution Engine ────────► ( Interpreter OR Compiler )
```

Ever was at stage 4 without stages 1–3. It walked **strings**. That
worked, and it cost three specific things.

---

## What the missing AST was costing

| Cost | Why |
|---|---|
| `ultracode` measured characters, not structure | `n * 1` and `n` looked like different amounts of program |
| Transpilation was impossible | you cannot emit Rust from a regex |
| Nothing could ask "is this spec expressible in my grammar" | there was no grammar to ask about |

That third one is exactly the gap cell 7 of the notebook batch exposed.

---

## Every stage returns E<T>

A lexing error is not an exception. It is a **Z** carrying a defect class
and a source position. Evaluation being total is a property of the whole
pipeline or it is not a property at all.

```
compile_ever("a $ b")      → stage "lex",      Z(misbound)
compile_ever("1 +")        → stage "parse",    Z(unbounded)
compile_ever("def f(n)=x") → stage "semantic", ["unbound name 'x'"]
compile_ever("1 + 1")      → stage "ready"
```

---

## 1. Lexer

Produces typed tokens carrying position and line. Handles two-character
comparisons as single tokens, drops comments, tracks line numbers through
newlines, and refuses unknown characters with a position rather than
silently skipping them.

## 2. Parser — the grammar, written down

```
program   := fndef | expr
fndef     := 'def' NAME '(' params ')' '=' expr
expr      := ifexpr | compare
ifexpr    := 'if' expr 'then' expr 'else' expr
compare   := additive [ CMP additive ]
additive  := multiply { ('+' | '-') multiply }
multiply  := atom { ('*' | '/') atom }
atom      := NUM | STR | 'true' | 'false'
           | NAME '(' args ')' | NAME | '(' expr ')'
```

Recursive descent, left-associative, comparison lowest. **This is the
whole language.** Anything not derivable here is outside the grammar, and
being able to say that precisely is the point of writing it down.

### The AST measures structure

```
n           → 1 node
n * 1       → 3 nodes      ← ultracode can now see this is larger
((n))       → 1 node       ← redundant parens vanish
```

## 3. Semantic analyzer

Scope resolution, arity checking and type inference, **before a single
value is computed**. Ever used to discover an unbound name at evaluation
time. That is not wrong, but it is late: a defect only surfaced on the
input that reached it. Now the binding is checked whether or not that
branch ever runs.

| Caught before execution | Example |
|---|---|
| unbound names | `def f(n) = n + missing` |
| branch type disagreement | `def g(n) = if n then "yes" else 3` |
| literal division by zero | `def h(n) = n / 0` |
| arity mismatch | `def k(n) = f(n, n)` when `f` takes 1 |
| bool arithmetic | `def bad(n) = n + true` |

**The measure is now structural.** Finding the decreasing parameter used
to be a regex; on the AST it sees through parentheses and nesting:
`deep((n) - 1)` is recognised where the string version missed it.

## 4. Execution over the AST

Same semantics as before — chain by min, Z absorbs, a Z condition spans
both branches, branches lazy under a known condition — now walking a tree
instead of splitting text.

---

## The payoff: cell 7, finally settled

The notebook batch asked for the first four primes. Synthesis returned
three "independent" candidates:

```
if n <= 0 then 1 else n + prime(n - 2)
if n <  0 then 1 else n + prime(n - 2)
if n <  1 then 1 else n + prime(n - 2)
```

On **strings** these are three different solutions agreeing with each
other, so consensus read 100% and the answer came back at **235/256** —
above the execute floor, and wrong from n=5 onward.

On the **AST**, collapsing constants and comparison operators:

```
skeleton → if (V CMP K) then K else (V + CALL((V - K)))
```

**One idea. Three hats.** One solution cannot corroborate itself.

Consensus now counts ideas rather than strings:

| Spec | Result before | Result now |
|---|---|---|
| first four primes | 235/256, executable | **1/256, refused** |
| factorial, 4 examples | 235/256 | 235/256 |
| triangular, 4 examples | 235/256 | 235/256 |

The overfit is rejected and the genuine solutions are untouched. That is
the AST paying for itself on the first problem it was pointed at.

---

## Verified

| Component | Assertions |
|---|---|

This table used to be transcribed here by hand, and it had drifted: it
carried the same Python-interpreter row as three other documents and
`FINDINGS.md`, and `FINDINGS.md` said 81 while these said 83. Counts now
live in exactly one place, generated from a real run:

    python3 tests/assertion_counts.py

`FINDINGS.md` §5 carries the output and `--check` fails the gate when it
goes stale. See §5 there for why the 81 survived as long as it did.

## What stage 4 still does not have

**A compiler.** The right-hand branch of the diagram — `Interpreter OR
Compiler` — is still only the left one. The AST now makes the right one
possible: emitters from AST to Rust, Go, TypeScript are a tractable job
where before they were not. That, plus the Examples as the verification
contract, is what "an anchored function's body travels" actually
requires.
