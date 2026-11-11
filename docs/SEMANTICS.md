# Ever — Operational Semantics

**Version 0.3 · Codric Enterprise · Ricky (Dreid) · 2026**

Every rule below is implemented in `2-interpreter-python/abstract.py` and exercised by `abstract_test.py`. Where the
spec and the implementation disagree, the spec is wrong and gets fixed — not the other way round.

---

## 0. What Ever is

A language in which every binding carries **what it holds** and **how much that binding is trusted**, and in which
nothing executes below a stated floor.

Formally: a pure, strictly-evaluated, lexically-scoped first-order functional language over a trust-annotated value
domain, with a possibilistic chain rule and a probabilistic corroboration rule.

Ever is **not** Turing-complete by default. Unbounded recursion is a privilege earned by proof, not a default granted on
request. That is a design commitment, not a limitation to be fixed later.

---

## 1. Semantic domain

A **thread** is the only kind of value.

```
θ  ::=  ⟨ v , σ , c , [lo,hi] , ℓ , α , δ , g , ρ ⟩

  v   the thing held          (int | real | text | bool | closure | ⊥)
  σ   state                    Z | Confident | Certain | Equivalence
                               | Expression | Emulating | Evolved
                               | Anchored | Absent | EError
  c   confidence               0 … 256
  lo,hi  bounds                for Equivalence; otherwise lo = hi = c
  ℓ   source language
  α   anchor id                0 = unanchored
  δ   defect                   none | unbound | misbound | unbounded
                               | overbound | orphaned
  g   generation               Evolve cycles survived
  ρ   reason                   why it is untrusted, preserved always
```

**Uncertainty** is the derived quantity that the laws are stated over:

```
u(θ)  =  (256 − c(θ)) / 256          u ∈ [0,1]

u = 1  ⟺  Z          u = 0  ⟺  Certain
```

### 1.1 Scale constants

| Constant        | Value | Derivation                                      |
|-----------------|-------|-------------------------------------------------|
| `CERTAIN`       | 256   | 4⁴, the states of a byte                        |
| `EXECUTE_FLOOR` | 128   | 256 / 2                                         |
| `PI_WARN`       | 81    | ⌊256/π⌋                                         |
| `PI_ENUMERATE`  | 25    | ⌊256/π²⌋                                        |
| `DEPTH_CEILING` | 3     | ⌊π⌋                                             |
| `ASCEND_POINTS` | 3     | ⌊π⌋                                             |
| `INTAKE`        | 120   | what **external** data is worth before evidence |

### 1.2 Two entry points, not one

Ever distinguishes two questions that an earlier draft conflated:

| Question                             | Answer     | Entry confidence |
|--------------------------------------|------------|------------------|
| Do I know what the program **says**? | always yes | `Certain` (256)  |
| Do I know this reflects **reality**? | often no   | `INTAKE` (120)   |

A **program constant** — a literal written in Ever source — carries no uncertainty about its value. The author wrote
`1`; it is `1`. It enters at `Certain`.

**External data** — anything lifted through `Any` from another language, a parser, a scanner, an API — enters at
`INTAKE`, below the execute floor.

This distinction is load-bearing. Treating source literals as external input floored every computation in the language
at 120: a verified function given a certain argument returned the correct answer and could not certify it, forever.
Uncertainty in Ever belongs to **data from outside** and to **whether functions are correct** — never to what the
program says about itself.

---

## 2. The two composition laws

Ever has **two** operators, drawn from **two different formalisms**, used for **two different questions**. This is
deliberate and must be stated plainly, because silently mixing them would be an error.

### 2.1 Chain — `min`

> *What is the floor?*

```
                θ_f , θ_1 … θ_n
    ────────────────────────────────────────         [CHAIN]
    c( f(θ_1…θ_n) ) = min( c_f , c_1 , … , c_n )
```

The **possibilistic** rule (Zadeh). A result is no more trusted than its weakest participant. This is a **bound**, not a
probability, and must never be reported as one.

Chosen over the probabilistic rule (`c_f × c_x / 256`) because chains compose without collapsing: a ten-step computation
over trusted inputs stays usable. The cost is that `min` does not track accumulated independent error. Ever accepts that
cost and states it.

### 2.2 Corroborate — multiplicative uncertainty

> *What does the combined evidence support?*

```
              θ_a , θ_b  independent, v_a = v_b
    ─────────────────────────────────────────────    [EXCEL]
              u( a ⊕ b )  =  u(a) × u(b)
```

Equivalently `c = a + b − ⌊ab/256⌋`. Verified identical across the full grid: **1089 / 1089**.

This is the standard rule for combining independent evidence — the probability that both witnesses are wrong is the
product of each being wrong.

**Corroboration requires agreement on the value.** Two threads at the same confidence holding *different* values do not
corroborate; they collide, and Expel applies.

### 2.3 Three theorems

**T1 — Z is absorbing.** `u(Z) = 1`, and `1 × x = 1`. Z-contagion is not a rule imposed on the language; it is what
maximum uncertainty does under multiplication.

**T2 — Corroboration creates nothing.** Two witnesses agreeing does not manufacture confidence. It multiplies two
ignorances into a smaller one. The confidence was already distributed across the witnesses.

**T3 — Certain is unreachable by combination.** `u = 0` requires some
`u_i = 0` exactly. A product of non-zero terms is never zero. Therefore
`EXCEL` caps at 255, and `Certain` must enter from outside the corpus — at runtime, never at parse time.

---

## 3. Evaluation

Strict, left-to-right, pure. No mutation anywhere: the archive's audit trail depends on every thread being *derived*,
never overwritten.

### 3.1 Literals

```
    ─────────────────────────────           [LIT]
    ⟨ n ⟩ ⇓ ⟨ n, Confident, 120 ⟩
```

### 3.2 Variables

```
    x ↦ θ ∈ Γ                    x ∉ Γ
    ─────────────  [VAR]     ─────────────────────────────  [VAR-Z]
    Γ ⊢ x ⇓ θ[α:=0]          Γ ⊢ x ⇓ Z(unbound, "never bound")
```

**A reference never inherits an anchor.** The anchor belongs to the binding that earned it. `θ[α:=0]` is load-bearing:
without it, anchors would propagate by mere mention and continuity would be meaningless.

### 3.3 Arithmetic

```
    Γ ⊢ e₁ ⇓ θ₁    Γ ⊢ e₂ ⇓ θ₂    σ₁ ≠ Z    σ₂ ≠ Z    τ₁ ≈ τ₂
    ──────────────────────────────────────────────────────────  [OP]
    Γ ⊢ e₁ ⊕ e₂ ⇓ ⟨ v₁ ⊕ v₂ , Confident , min(c₁,c₂) ⟩

    σᵢ = Z                                  τ₁ ≉ τ₂
    ─────────────────────────  [OP-Z]    ─────────────────────  [OP-τ]
    Γ ⊢ e₁ ⊕ e₂ ⇓ Z(δᵢ, ρᵢ)              ⇓ Z(misbound)
```

Division by zero yields `Z(misbound, "division by zero")`. There are no exceptions in Ever; **evaluation is total**.
Every expression returns a well-formed thread.

---

## 4. Functions

### 4.1 Definition

A function is a **thread whose value is a closure**.

```
    ───────────────────────────────────────────────────  [DEF]
    Γ ⊢ def f(x̄) = e  ⇓  ⟨ ⟨f,x̄,e,Γ⟩ , Confident , 120 ⟩
```

It begins at `INTAKE`, below the execute floor, for the same reason a literal does. A definition is a claim, not a
verification.

### 4.2 Example — how a function earns confidence

Each passing Example is an independent witness at intake strength, so Examples **corroborate under [EXCEL]**. One
Example no more verifies a function than one observation lets a binding Ascend.

```
    u_f = ((256 − 120)/256) ^ p          p = passing, t = total
    ───────────────────────────────────────────────────  [EXAMPLE]
    c_f = ⌊ 256 · (1 − u_f) · (p/t) ⌋      capped at 255
```

Observed:

| Examples passed | Confidence |                                       |
|-----------------|------------|---------------------------------------|
| 1 / 1           | 120        | below floor — one case proves nothing |
| 2 / 2           | 183        | clears                                |
| 3 / 3           | 217        |                                       |
| 4 / 4           | 235        |                                       |
| 2 / 3           | 122        | a failure costs                       |

**A depth-exceeded Example counts as a failure.** Otherwise the ceiling would be free.

### 4.3 Application

```
    Γ ⊢ f ⇓ θ_f    v_f = ⟨f,x̄,e,Γ_f⟩    |ā| = |x̄|
    ∀i. σ(θ_i) ≠ Z        depth ⊑ limit(θ_f)
    Γ_f[x̄ ↦ ā] ⊢ e ⇓ θ_r
    ─────────────────────────────────────────────────  [APP]
    Γ ⊢ f(ā) ⇓ ⟨ v_r , min(c_f, c̄, c_r) ⟩
```

Failure cases, all total:

| Condition           | Result                                       |
|---------------------|----------------------------------------------|
| `θ_f` is Z          | `Z` — propagated                             |
| `v_f` not a closure | `Z(misbound, "not a function")`              |
| arity mismatch      | `Z(misbound)`                                |
| any argument Z      | `Z` naming that argument                     |
| depth over limit    | `DepthExceeded` — a checked halt, not a hang |

### 4.4 Anchoring a function

```
    cleared(θ_f)    ¬recursive(v_f)
    ────────────────────────────────────  [ANCHOR-FN]
    anchor θ_f ⇓ θ_f[σ:=Anchored, α:=fresh]

    cleared(θ_f)    recursive(v_f)    measure(v_f) = m
    ─────────────────────────────────────────────────  [ANCHOR-REC]
    anchor θ_f ⇓ θ_f[σ:=Anchored, α:=fresh, depth:=∞]

    recursive(v_f)    measure(v_f) = ⊥
    ─────────────────────────────────────────────────  [ANCHOR-⊥]
    anchor θ_f ⇓ Z(unbounded, "confidence proves trust, not termination")
```

**[ANCHOR-⊥] is the rule that keeps the language honest.** A function can sit at 240/256 and still loop forever.
Confidence is evidence about *correctness*, and correctness is not termination. Anchoring a recursive function without a
decreasing measure would turn "unbounded depth" into
"hangs."

### 4.5 The measure

`measure(f) = m` when some parameter `m` **strictly decreases in every self-call**. The check is deliberately
conservative and syntactic:
recognised forms are `m − k` for `k > 0` and `m / k` for `k > 1`.

When decrease cannot be proven, the answer is ⊥ and the ceiling stays at
`⌊π⌋ = 3`. **Refusing to guess is the point.** A wrong termination proof is worse than no proof.

### 4.6 Depth

```
    limit(θ_f) =  ∞    if α(θ_f) ≠ 0  ∧  measure(v_f) ≠ ⊥
                  3    otherwise
```

**Depth is earned.** Verification purchases the right to go deep. Observed: `fact` blocked at n=8 unanchored; after 3
Examples and an anchor, `fact(100)` computes at depth 99.

---

## 5. Conditionals and Healing


### 5.1 Known condition — lazy

```
    Γ ⊢ c ⇓ θ_c    σ_c ≠ Z    v_c = true    Γ ⊢ e₁ ⇓ θ₁
    ────────────────────────────────────────────────────  [IF-T]
    Γ ⊢ if c then e₁ else e₂ ⇓ ⟨ v₁ , min(c_c, c₁) ⟩
```

`e₂` is **not evaluated**. This is not an optimisation — it is required. Evaluating both arms eagerly makes every
recursive function non-terminating, because the recursive arm runs even when the base case was selected. This was found
by construction, not by argument.

### 5.2 Unknown condition — eager, and it spans

```
    Γ ⊢ c ⇓ Z    Γ ⊢ e₁ ⇓ θ₁    Γ ⊢ e₂ ⇓ θ₂    v₁,v₂ numeric
    hi − lo ≤ 81
    ────────────────────────────────────────────────────  [IF-Z]
    ⇓ ⟨ Equivalence, [min(v₁,v₂), max(v₁,v₂)], min(c₁,c₂) ⟩
```

A Z condition does **not** collapse the expression. "It is one of these two" is real information, and discarding it
would be a lie in the other direction.

π then judges the width with **no special-casing**:

| Width   | Verdict                     |
|---------|-----------------------------|
| ≤ 25    | acceptable                  |
| 26 … 81 | must enumerate              |
| > 81    | collapses to `Z(unbounded)` |

Supporting cases:

```
    v₁ = v₂                          v₁,v₂ not numeric,  v₁ ≠ v₂
    ─────────────────────  [IF-AGREE]   ──────────────────────  [IF-⊥]
    ⇓ ⟨v₁, min(c₁,c₂)⟩                  ⇓ Z(unbounded, "not spannable")
```

**[IF-AGREE] is worth noting:** when both arms give the same answer, the unknown condition is *moot*. The result is
known despite the ignorance.

**Evaluation strategy is therefore hybrid:** lazy under a known condition, eager under an unknown one. The expense lives
in the unknown case, which is the correct place for it.

---

## 6. Guarantees

| #       | Property                                                       | Status                 |
|---------|----------------------------------------------------------------|------------------------|
| **G1**  | Evaluation is total — no exceptions, no undefined behavior     | proven by construction |
| **G2**  | Z is absorbing (T1)                                            | algebraic              |
| **G3**  | Confidence never rises except via `Ascend` or `Excel`          | enforced               |
| **G4**  | `Ascend` requires 3 aligned points                             | enforced               |
| **G5**  | `Certain` unreachable by combination (T3)                      | algebraic              |
| **G6**  | Anchored threads cross languages losslessly                    | tested, 5 hops         |
| **G7**  | Unanchored crossings lose exactly 1 per hop                    | tested                 |
| **G8**  | Recursion terminates or halts at a checked ceiling             | enforced               |
| **G9**  | No mutation                                                    | by construction        |
| **G10** | Every finding classifies into 5 binding defects                | 19/19 observed         |
| **G11** | State and confidence never disagree — `Certain` is exactly 256 | enforced               |

**Not guaranteed, and stated so:**

- **Termination in general.** Only for anchored functions with a proven measure. Unanchored recursion halts at the
  ceiling rather than diverging, which is a weaker but honest promise.
- **Type soundness.** Checking is dynamic. There is no static type system and no progress/preservation proof.
- **Confidence calibration.** Nothing asserts that a thread at 200/256 is right 78% of the time. Confidence is an
  internal ordering, not a measured frequency. **This is the largest open claim in the language.**

---

## 7. Not yet specified

Named honestly, because scope depends on it.

| Missing                         | Consequence                                |
|---------------------------------|--------------------------------------------|
| Element and field types         | not tracked: `xs[i]` and `r.f` are `ANY`   |
| Higher-order functions          | functions cannot be arguments              |
| Pattern matching                | only `if/then/else`                        |
| Static type system              | dynamic tag checks only                    |
| Module system                   | one flat global namespace                  |
| Transpiler back-ends            | anchored bodies do not yet emit Rust/Go/TS |
| Formal grammar proof            | documented in §10; no proof it matches     |
| Soundness proof                 | no progress/preservation                   |

**Transpilation is the largest gap.** The decision is that an anchored function's *body* travels into the target
language, with its Examples as the verification contract: the emitted Rust must satisfy the same Examples to inherit the
anchor. Nothing of this is built.

---

## 8. Worked example

```ever
def fact(n) = if n <= 1 then 1 else n * fact(n - 1)
```

| Step                         | Result                                          |
|------------------------------|-------------------------------------------------|
| `[DEF]`                      | thread at 120/256, recursive, measure `n` found |
| `fact(3)`                    | 6 — depth 3, within ⌊π⌋                         |
| `fact(8)`                    | **blocked** — DepthExceeded at ceiling 3        |
| Examples `(1,1) (2,2) (3,6)` | 217/256 by `[EXAMPLE]`                          |
| `[ANCHOR-REC]`               | Anchored, depth := ∞ on measure `n`             |
| `fact(100)`                  | computes, depth 99                              |

Every value returns at **217/256** — the chain rule flooring on `fact`
itself, which is exactly right: *a result is only as trustworthy as the function that produced it.* The literals `1` in
the base case are program constants at `Certain` and do not drag the floor down.

An earlier draft floored this at 120 by treating source literals as external input. That made every computation in the
language permanently unexecutable. The fix was one localised change at the entry points, not a rebuild; four tests
failed and all four had been asserting the defect.

---

## 9. Repair: the named process

Two operators. `heal (e) using (s) fallback (f)` repairs `e` when it fails. `learn (e) using (s) fix (f)` archives a
fix for it. Both run one process, the **repair cycle**, in three named phases, in this order. Each phase writes one
trace line (`heal_order.py`), and every layer that claims the process must write the same lines.

**1. EVALUATE.** Run the primary in a cause frame.
- Confidence at or above the execute floor (128): **KEEP**. The order stops here.
- A z: it is named by the *first failure* noted inside the frame. The vocabulary is closed:

  | Reason | Raised by |
  |---|---|
  | `division by zero` | `/` with a zero divisor |
  | `declared unknown` | a `z` literal |
  | `<name> was never bound` | an unbound variable or unknown function |
  | `operands do not combine` | an operator given two values it cannot combine |
  | `depth ceiling reached` | a call past the recursion ceiling, or past an anchor's limit |
  | `anchor broken` | an anchored call whose measure did not decrease |
  | `wrong number of arguments` | a builtin given the wrong arity |
  | `unverified` | nothing in the frame named the failure |

- A value below the floor, not z: reason `low confidence`.

**2. PLAN.** Choose before running anything. Look up the archive by `(reason, strategy)`: a repair tied to this
strategy first, then an untied (wildcard) one. None found, or one whose cost is not below the base, gives **FALLBACK**.
Otherwise **SUBSTITUTE** with that fixture. The base is 120 for a z and the primary's own confidence otherwise. A plain
repair costs 8; an inferred one costs 32.

**3. EXECUTE.** Run the chosen action and record its outcome.
- SUBSTITUTE carries `min(base, fixture confidence) − cost`, and only if that is above zero.
- A chosen repair that cannot run (unparsable, evaluates to z, or leaves no confidence) is **FAILED**: the result is z,
  never the fallback. Its reason is handed to the enclosing evaluation.
- `learn` archives `(reason, fixture, strategy)` only when the fixture reaches the floor. Only text strategies archive.

**Rules that follow from the process.**
- *The first failure is the cause.* Later z's are its consequences. A branch that never ran names nothing: `if true
  then 4 else 1 / zero` has no failure. An `if` on a z condition runs its else arm, so the condition's failure, which
  comes first, is the cause.
- *Frames absorb.* The primary, strategy, fixture and fallback each run in their own frame. A failure a heal absorbs does
  not reach an enclosing heal. A heal that yields z hands its reason up.
- *Probes are not events.* A confidence re-read runs in a frame of its own and traces, counts and archives nothing. It
  still names its failures, so it reaches the same repair and the same answer.
- *A repair is trusted only at the floor.* A plain repair of a z is 112. An enclosing heal does not trust 112 and names
  its own primary `low confidence`. Repairs do not stack their way past the floor.
- *Naming reaches through calls.* A failure inside a function body is named where it happened, so `heal (f(0))` and
  `learn (f(0))` act on `division by zero`.

**Known limits, stated so they are not mistaken for guarantees.**
- Causes live in evaluation, not in values. `let x = z` then `heal (x)` names `unverified`, because the z in `x` has
  lost where it came from.
- The Java layer (`EverRepair.java`) does not model user functions. Its call case is the callee's z, which claims less
  than the Python and C layers do for a failure inside a call.
- The C layer (`tac.c`) names causes as this section does, through cause frames in the lowered code. It does not
  implement `learn` yet, and it does not raise `operands do not combine`, because its operators do not check operand
  types.

---

## 10. Grammar as built

The block below is the grammar of the Python parser in `2-interpreter-python/syntax.py`. `run_source()`, the front door for the CLI, REPL and embedders, calls `forgive.parse_forgiving()` first. That rewrites the source and token stream, then hands them to this parser. The note under the block covers what the rewrite adds.

In the block, `"x"` is a keyword or punctuation token, `NAME`, `NUM` and `STR` are token classes, `{ }` repeats, `[ ]` is optional and `( )` groups. `heal`, `using`, `fallback` and `fix` are NAME tokens matched by text (see Notes).

```ebnf
(* Tokens. Spaces, tabs, newlines and #-comments are skipped. *)
NUM        = digit { digit } [ "." digit { digit } ] ;      (* "1" is an int, "1.0" a real *)
STR        = '"' { any character but '"' or newline } '"' ;
NAME       = ( letter | "_" ) { letter | digit | "_" } ;    (* never a keyword *)

(* Statements. Newlines separate nothing; an expr statement must come last. *)
program    = { statement } ;
statement  = fndef | letstmt | showstmt | externstmt | example | anchor | expr ;

fndef      = "def" NAME "(" [ NAME { "," NAME } ] ")" "=" expr ;
letstmt    = ( "let" | "ever" ) NAME "=" expr ;
showstmt   = "show" NAME ;
externstmt = "extern" NAME "(" [ NAME { "," NAME } ] ")" "from" STR ;
example    = "example" NAME "(" [ expr { "," expr } ] ")" "=" expr ;
anchor     = "anchor" NAME ;

(* Expressions, loosest binding first. *)
expr       = ifexpr | healexpr | learnexpr | forexpr | whileexpr | orexpr ;
ifexpr     = "if" expr "then" expr "else" expr ;
healexpr   = "heal" "(" expr ")" "using" "(" expr ")" "fallback" "(" expr ")" ;
learnexpr  = "learn" "(" expr ")" "using" "(" expr ")" "fix" "(" expr ")" ;
forexpr    = "for" NAME ( "in" expr "do" expr
                        | "=" expr "to" expr [ "by" expr ] "do" expr ) ;
whileexpr  = "while" expr "do" expr ;

orexpr     = andexpr { "or" andexpr } ;
andexpr    = notexpr { "and" notexpr } ;
notexpr    = "not" notexpr | compare ;
compare    = additive [ cmpop additive ] ;                  (* one comparison, no chaining *)
cmpop      = "<" | ">" | "<=" | ">=" | "==" | "!=" ;
additive   = multiply { ( "+" | "-" ) multiply } ;
multiply   = unary { ( "*" | "/" ) unary } ;
unary      = "-" unary | postfix ;                          (* -x is 0 - x *)
postfix    = primary { "[" expr "]" | "." NAME } ;
primary    = NUM | STR | "true" | "false" | "z"
           | NAME [ "(" [ expr { "," expr } ] ")" ]         (* call, or variable *)
           | list
           | record
           | "(" expr ")" ;
list       = "[" [ expr { "," expr } ] "]" ;
record     = "{" [ field { "," field } ] "}" ;
field      = NAME ":" expr ;
```

**Beyond the block.** The parser itself accepts missing or trailing commas in list, record, call and `def` parameter lists, and `=` where a record wants `:`. Only `forgive.py`, which `run_source` runs first, accepts: keyword case (`Let x = 1`); `=` where `==` is meant (`if 1 = 1 then ...`); `:` where `=` is meant after `let` or `ever`; a stray `;`; and missing or trailing commas in `example` and `extern` argument lists.

**Notes**

- **Keywords are reserved.** Every word in `KEYWORDS` is a keyword and cannot be a name, parameter or record key. `expect`, `ascend`, `assimilate` and `equiv` are reserved, but no rule uses them. `heal`, `using`, `fallback` and `fix` are not reserved: they are NAME tokens, and `heal (` opens a heal form only when `using` follows the matching `)`.
- **`example` and `anchor` are statements, not expressions.** `let y = anchor f` is a parse error.
- **The `=` of an Example is not a comparison.** `example f(x) = v` takes one `=`; `example f(x) == v` is a parse error.
- **Newlines separate nothing.** An expression continues onto the next line when the next token can extend it: `let x = 1` followed by `-2` is `1 - 2`, and `let g = f` followed by `(2)` is the call `f(2)`.
- **An expression statement must come last.** `1` followed by `let x = 2` is a parse error.
- **`if`, `heal`, `learn`, `for` and `while` cannot be operands** unless parenthesised. `1 + if ...` is a parse error; `1 + (if ...)` parses.
- **Loop bodies are expressions.** `show` and `let` are statements, so `for i = 1 to 3 do show i` is a parse error (`unexpected show at line 1`).
- **Parsing is not the whole gate.** The semantic pass runs after the parser and rejects, among other things, unbound names and a literal zero divisor, even inside `heal`. `heal (1 / 0) using ("p") fallback (3)` parses, then fails with `division by a literal zero`.

---

*297 assertions across C, C++, Python and SQL, plus 70 on the abstraction layer. Codric Enterprise, 2026.*
