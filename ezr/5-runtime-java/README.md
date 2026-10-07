# Layer 5 — the Java runtime

A second implementation of EZR's core, in a language that shares nothing
with the first one.

```bash
./build.sh                              # javac, no build tool, no deps
./ezr ../examples/sum.ezr               # 15  @ 256/256
./ezr -e 'let x = 5 in x + 1'           # 6   @ 256/256
echo 'def main() = 6 * 7' | ./ezr -     # 42  @ 256/256

env -u JAVA_TOOL_OPTIONS java -cp out com.codric.ezr.RuntimeTest
python3 differential.py                 # both runners, one corpus
```

Exit codes match `2-interpreter-python/ezrun.py`: **0** a value,
**1** a refusal (`Z`), **2** input that would not compile.

---

## Why a second runtime

The four lexers and five parsers in `7-forge/` are all Python. They
disagree usefully because they are built on different principles, but
they share an interpreter, a float type, a string type, and a set of
habits. A rule that is wrong in a way Python papers over is wrong in all
nine of them at once.

Java shares none of that. It has static types where Python has none, a
`java.lang.Thread` where EZR has a thread of its own, no `repr`, no
truthiness beyond `boolean`, and it throws where CPython returns. Every
one of those differences is a place a silent assumption can surface —
and three of them did.

This layer is checked in two directions, which answer different
questions:

| Check | Asks | Where |
|---|---|---|
| `RuntimeTest.java` | does Java match **SEMANTICS.md**? | 98 assertions |
| `differential.py` | does Java match **the Python runner**? | 108 programs |

Both are needed. A rule can be implemented consistently in both and still
be wrong against the spec; a rule can be right in the spec and
mis-transcribed on one side. `run.sh` runs each as its own layer, `[5]`
and `[5b]`.

---

## What it is not

**It is not a transpiler target.** SEMANTICS.md §7 calls transpilation
the largest gap and specifies the contract — an anchored function's body
travels, with its Examples as the verification contract. None of that is
built, here or anywhere. This layer runs EZR source directly; it does not
emit Java from EZR.

**It does not grant earned depth.** SEMANTICS.md §4.6 says an anchored
function with a proven measure recurses without bound. Anchoring lives in
layer 2's `abstract.py` `Lambda`, not in the AST evaluator, and the
Python AST evaluator has exactly the same seam and says so in
`ezrun.py`'s own docstring. What layer 5 has is the checked halt (G8):
past the limit a call returns `Z(unbounded)` rather than recursing.
`Semantic.measure()` finds the decreasing parameter, so the analysis is
here; the privilege it would buy is not.

**It is not the whole language.** It implements what `GRAMMAR.ebnf`
defines and what `ezrun.py` runs. Records, modules and pattern matching
are missing from EZR itself, not just from this layer.

---

## The files

| File | |
|---|---|
| `Particle.java` | the value domain — SEMANTICS.md §1, and the scale constants |
| `Laws.java` | chain (`min`), corroborate (multiplicative uncertainty), assimilate (G6/G7) |
| `Lexer.java` | the scanner, from the token table in `GRAMMAR.ebnf` |
| `Ast.java` | the node set `7-forge/contract.py` fixes, as a sealed interface |
| `Parser.java` | recursive descent over `GRAMMAR.ebnf` |
| `Semantic.java` | stage 3 — scope, arity, types, the measure |
| `Eval.java` | stage 4 — the evaluator |
| `Ezr.java` | the runner, and the exit codes |
| `RuntimeTest.java` | 98 assertions against SEMANTICS.md |
| `differential.py` | the two runners over one corpus |

### Why the value is called `Particle`

SEMANTICS.md calls it a **thread**. A Java class named `Thread` in this
package would shadow `java.lang.Thread` for every file in the package —
legal, and exactly the sort of trap this layer exists to find rather than
create. So it takes the name the C atom gives the same struct,
`e_particle`. The C layer and the Java layer agree; the document uses the
older word.

### Why the AST is a sealed interface

`switch` over a sealed type is checked for exhaustiveness at compile
time. That makes half of **G1 — evaluation is total** a property the
compiler enforces: add a node kind without handling it in `Eval` and this
layer stops building. The Python interpreter cannot make that check.
Getting a guarantee enforced by a different mechanism is most of the
argument for writing the second implementation in a different language.

---

## What building it found

Three things, all in code that was already passing its own tests.

**1. A dead guard in the production lexer.** `syntax.py` carried a check
for an unterminated string that could never fire: its regex
`"[^"\n]*"` only matches when a closing quote exists, so the guard's
condition was never true. A lone `"` fell through to "unexpected
character" and was classified `misbound`.

The forge had already settled this — `unterminated_string_defect =
'unbounded'`, by doctrine, recorded in `GRAMMAR.ebnf` — and all four
forge lexers implement it. The ruling had never been carried back into
the lexer the runner actually uses. Java, written from the grammar rather
than from `syntax.py`, implemented the ratified answer and the
differential harness surfaced the split immediately. Fixed in
`syntax.py`; five implementations now agree.

**2. Rendering is not specified, and the incumbent is inconsistent.**
EZR prints a bare string unquoted — `"hello"` runs to `hello` — and
prints the same string quoted inside a list, `['a', 'b']`. That came from
formatting lists through CPython's `repr`; it was inherited rather than
chosen. Java reproduces it rather than quietly fixing it, because
arbitration **withholds** here: no document specifies rendering, no law
settles it, and two implementations is below the ⌊π⌋ = 3 that consensus
needs. When arbitration withholds, the incumbent stands and the
disagreement gets written down. See FINDINGS.md §7.

**3. "Equivalently" was hiding a rounding rule.** SEMANTICS.md §2.2 says
`u(a⊕b) = u(a)×u(b)` is "equivalently `c = a + b − ⌊ab/256⌋`", verified
1089/1089, without saying which way the scale rounds. It is the
**ceiling**: 120 corroborated with 120 is 183.75 exactly and the integer
form gives 184. Under `floor` the two forms differ on 507 of those 1089
cells. The claim is true; the word "equivalently" was carrying a
convention that is now pinned by an assertion rather than left to be
rediscovered.

---

## What agreeing does and does not prove

108 programs is a corpus, not a proof. The two runners agreeing means no
counterexample was found in the region the corpus covers — the same thing
the forge's 564,600 programs mean, and no more. `undermine` in VOWELS.md
returns **Z** for exactly this reason.

The harness separates two things on purpose:

- **The language** — the value, the exit code, which stage refused, and
  which of the five binding defects it was. These must match. A mismatch
  is a divergence and fails the layer.
- **The wording** — the prose of the refusal. Twelve cases differ here
  and are reported, not failed. Two runners with different names for
  themselves and different phrasing for the same refusal are not a
  disagreement about EZR.

Holding two implementations to identical error prose would be testing the
error messages. Holding them to the same answer and the same
classification is testing the language.
