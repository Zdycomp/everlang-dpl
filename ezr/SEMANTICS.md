# Ever — Operational Semantics

**Version 0.3 · Codric Enterprise · Ricky (Dreid) · 2026**

Every rule below is implemented in `2-interpreter-python/abstract.py` and
exercised by `abstract_test.py`. Where the spec and the implementation
disagree, the spec is wrong and gets fixed — not the other way round.

---

## 0. What Ever is

A language in which every binding carries **what it holds** and **how
much that binding is trusted**, and in which nothing executes below a
stated floor.

Formally: a pure, strictly-evaluated, lexically-scoped first-order
functional language over a trust-annotated value domain, with a
possibilistic chain rule and a probabilistic corroboration rule.

Ever is **not** Turing-complete by default. Unbounded recursion is a
privilege earned by proof, not a default granted on request. That is a
design commitment, not a limitation to be fixed later.

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

| Constant | Value | Derivation |
|---|---|---|
| `CERTAIN` | 256 | 4⁴, the states of a byte |
| `EXECUTE_FLOOR` | 128 | 256 / 2 |
| `PI_WARN` | 81 | ⌊256/π⌋ |
| `PI_ENUMERATE` | 25 | ⌊256/π²⌋ |
| `DEPTH_CEILING` | 3 | ⌊π⌋ |
| `ASCEND_POINTS` | 3 | ⌊π⌋ |
| `INTAKE` | 120 | what **external** data is worth before evidence |

### 1.2 Two entry points, not one

Ever distinguishes two questions that an earlier draft conflated:

| Question | Answer | Entry confidence |
|---|---|---|
| Do I know what the program **says**? | always yes | `Certain` (256) |
| Do I know this reflects **reality**? | often no | `INTAKE` (120) |

A **program constant** — a literal written in Ever source — carries no
uncertainty about its value. The author wrote `1`; it is `1`. It enters
at `Certain`.

**External data** — anything lifted through `Any` from another language,
a parser, a scanner, an API — enters at `INTAKE`, below the execute
floor.

This distinction is load-bearing. Treating source literals as external
input floored every computation in the language at 120: a verified
function given a certain argument returned the correct answer and could
not certify it, forever. Uncertainty in Ever belongs to **data from
outside** and to **whether functions are correct** — never to what the
program says about itself.

---

## 2. The two composition laws

Ever has **two** operators, drawn from **two different formalisms**, used
for **two different questions**. This is deliberate and must be stated
plainly, because silently mixing them would be an error.

### 2.1 Chain — `min`

> *What is the floor?*

```
                θ_f , θ_1 … θ_n
    ────────────────────────────────────────         [CHAIN]
    c( f(θ_1…θ_n) ) = min( c_f , c_1 , … , c_n )
```

The **possibilistic** rule (Zadeh). A result is no more trusted than its
weakest participant. This is a **bound**, not a probability, and must
never be reported as one.

Chosen over the probabilistic rule (`c_f × c_x / 256`) because chains
compose without collapsing: a ten-step computation over trusted inputs
stays usable. The cost is that `min` does not track accumulated
independent error. Ever accepts that cost and states it.

### 2.2 Corroborate — multiplicative uncertainty

> *What does the combined evidence support?*

```
              θ_a , θ_b  independent, v_a = v_b
    ─────────────────────────────────────────────    [EXCEL]
              u( a ⊕ b )  =  u(a) × u(b)
```

Equivalently `c = a + b − ⌊ab/256⌋`. Verified identical across the full
grid: **1089 / 1089**.

This is the standard rule for combining independent evidence — the
probability that both witnesses are wrong is the product of each being
wrong.

**Corroboration requires agreement on the value.** Two threads at the
same confidence holding *different* values do not corroborate; they
collide, and Expel applies.

### 2.3 Three theorems

**T1 — Z is absorbing along the chain, and inert under corroboration.**
The two composition rules of §2 are not the same operation and Z does not
behave the same way in both.

Chaining is `min` (§3.4), and `min(Z, c) = Z` for every c. A value
computed from an unknown is unknown: that is Z-contagion, and it is a
theorem rather than a rule imposed on the language.

Corroboration is `EXCEL`, which is multiplicative in uncertainty, and
there Z is the **identity**: `u(Z) = 1`, `1 × x = x`, so
`EXCEL(Z, c) = c`. A witness who knows nothing leaves what you already
had exactly as it was — correct, and what the code has always done.

This theorem previously read "Z is absorbing. `u(Z) = 1`, and
`1 × x = 1`", which is false twice over: `1 × x = x`, and the absorbing
element of `EXCEL` is `Certain`, not Z (`EXCEL(Certain, c) = Certain` for
every c, which is T3 seen from the other side). The error survived
because `research.py` shipped a function called `z_absorbs` that returned
True while actually asserting `EXCEL(0, b) == b` — the identity law under
a name promising absorption. See `FINDINGS.md` §1.

**T2 — Corroboration creates nothing.** Two witnesses agreeing does not
manufacture confidence. It multiplies two ignorances into a smaller one.
The confidence was already distributed across the witnesses.

**T3 — Certain is unreachable by combination.** `u = 0` requires some
`u_i = 0` exactly. A product of non-zero terms is never zero. Therefore
`EXCEL` caps at 255, and `Certain` must enter from outside the corpus —
at runtime, never at parse time.

---

## 3. Evaluation

Strict, left-to-right, pure. No mutation anywhere: the archive's audit
trail depends on every thread being *derived*, never overwritten.

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

**A reference never inherits an anchor.** The anchor belongs to the
binding that earned it. `θ[α:=0]` is load-bearing: without it, anchors
would propagate by mere mention and continuity would be meaningless.

### 3.3 Arithmetic

```
    Γ ⊢ e₁ ⇓ θ₁    Γ ⊢ e₂ ⇓ θ₂    σ₁ ≠ Z    σ₂ ≠ Z    τ₁ ≈ τ₂
    ──────────────────────────────────────────────────────────  [OP]
    Γ ⊢ e₁ ⊕ e₂ ⇓ ⟨ v₁ ⊕ v₂ , Confident , min(c₁,c₂) ⟩

    σᵢ = Z                                  τ₁ ≉ τ₂
    ─────────────────────────  [OP-Z]    ─────────────────────  [OP-τ]
    Γ ⊢ e₁ ⊕ e₂ ⇓ Z(δᵢ, ρᵢ)              ⇓ Z(misbound)
```

Division by zero yields `Z(misbound, "division by zero")`. There are no
exceptions in Ever; **evaluation is total**. Every expression returns a
well-formed thread.

---

## 4. Functions

### 4.1 Definition

A function is a **thread whose value is a closure**.

```
    ───────────────────────────────────────────────────  [DEF]
    Γ ⊢ def f(x̄) = e  ⇓  ⟨ ⟨f,x̄,e,Γ⟩ , Confident , 120 ⟩
```

It begins at `INTAKE`, below the execute floor, for the same reason a
literal does. A definition is a claim, not a verification.

### 4.2 Example — how a function earns confidence

Each passing Example is an independent witness at intake strength, so
Examples **corroborate under [EXCEL]**. One Example no more verifies a
function than one observation lets a binding Ascend.

```
    u_f = ((256 − 120)/256) ^ p          p = passing, t = total
    ───────────────────────────────────────────────────  [EXAMPLE]
    c_f = ⌊ 256 · (1 − u_f) · (p/t) ⌋      capped at 255
```

Observed:

| Examples passed | Confidence | |
|---|---|---|
| 1 / 1 | 120 | below floor — one case proves nothing |
| 2 / 2 | 183 | clears |
| 3 / 3 | 217 | |
| 4 / 4 | 235 | |
| 2 / 3 | 122 | a failure costs |

**A depth-exceeded Example counts as a failure.** Otherwise the ceiling
would be free.

### 4.3 Application

```
    Γ ⊢ f ⇓ θ_f    v_f = ⟨f,x̄,e,Γ_f⟩    |ā| = |x̄|
    ∀i. σ(θ_i) ≠ Z        depth ⊑ limit(θ_f)
    Γ_f[x̄ ↦ ā] ⊢ e ⇓ θ_r
    ─────────────────────────────────────────────────  [APP]
    Γ ⊢ f(ā) ⇓ ⟨ v_r , min(c_f, c̄, c_r) ⟩
```

Failure cases, all total:

| Condition | Result |
|---|---|
| `θ_f` is Z | `Z` — propagated |
| `v_f` not a closure | `Z(misbound, "not a function")` |
| arity mismatch | `Z(misbound)` |
| any argument Z | `Z` naming that argument |
| depth over limit | `DepthExceeded` — a checked halt, not a hang |

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

**[ANCHOR-⊥] is the rule that keeps the language honest.** A function can
sit at 240/256 and still loop forever. Confidence is evidence about
*correctness*, and correctness is not termination. Anchoring a recursive
function without a decreasing measure would turn "unbounded depth" into
"hangs."

### 4.5 The measure

`measure(f) = m` when some parameter `m` **strictly decreases in every
self-call**. The check is deliberately conservative and syntactic:
recognised forms are `m − k` for `k > 0` and `m / k` for `k > 1`.

When decrease cannot be proven, the answer is ⊥ and the ceiling stays at
`⌊π⌋ = 3`. **Refusing to guess is the point.** A wrong termination proof
is worse than no proof.

### 4.6 Depth

```
    limit(θ_f) =  ∞    if α(θ_f) ≠ 0  ∧  measure(v_f) ≠ ⊥
                  3    otherwise
```

**Depth is earned.** Verification purchases the right to go deep.
Observed: `fact` blocked at n=8 unanchored; after 3 Examples and an
anchor, `fact(100)` computes at depth 99.

---

## 5. Conditionals

### 5.1 Known condition — lazy

```
    Γ ⊢ c ⇓ θ_c    σ_c ≠ Z    v_c = true    Γ ⊢ e₁ ⇓ θ₁
    ────────────────────────────────────────────────────  [IF-T]
    Γ ⊢ if c then e₁ else e₂ ⇓ ⟨ v₁ , min(c_c, c₁) ⟩
```

`e₂` is **not evaluated**. This is not an optimisation — it is required.
Evaluating both arms eagerly makes every recursive function
non-terminating, because the recursive arm runs even when the base case
was selected. This was found by construction, not by argument.

### 5.2 Unknown condition — eager, and it spans

```
    Γ ⊢ c ⇓ Z    Γ ⊢ e₁ ⇓ θ₁    Γ ⊢ e₂ ⇓ θ₂    v₁,v₂ numeric
    hi − lo ≤ 81
    ────────────────────────────────────────────────────  [IF-Z]
    ⇓ ⟨ Equivalence, [min(v₁,v₂), max(v₁,v₂)], min(c₁,c₂) ⟩
```

A Z condition does **not** collapse the expression. "It is one of these
two" is real information, and discarding it would be a lie in the other
direction.

π then judges the width with **no special-casing**:

| Width | Verdict |
|---|---|
| ≤ 25 | acceptable |
| 26 … 81 | must enumerate |
| > 81 | collapses to `Z(unbounded)` |

Supporting cases:

```
    v₁ = v₂                          v₁,v₂ not numeric,  v₁ ≠ v₂
    ─────────────────────  [IF-AGREE]   ──────────────────────  [IF-⊥]
    ⇓ ⟨v₁, min(c₁,c₂)⟩                  ⇓ Z(unbounded, "not spannable")
```

**[IF-AGREE] is worth noting:** when both arms give the same answer, the
unknown condition is *moot*. The result is known despite the ignorance.

**Evaluation strategy is therefore hybrid:** lazy under a known
condition, eager under an unknown one. The expense lives in the unknown
case, which is the correct place for it.

---

## 6. Guarantees

| # | Property | Status |
|---|---|---|
| **G1** | Evaluation is total — no exceptions, no undefined behavior | proven by construction |
| **G2** | Z is absorbing along the chain; the identity under `EXCEL` (T1) | algebraic |
| **G3** | Confidence never rises except via `Ascend` or `Excel` | enforced |
| **G4** | `Ascend` requires 3 aligned points | enforced |
| **G5** | `Certain` unreachable by combination (T3) | algebraic |
| **G6** | Anchored threads cross languages losslessly | tested, 5 hops |
| **G7** | Unanchored crossings lose exactly 1 per hop | tested |
| **G8** | Recursion terminates or halts at a checked ceiling | enforced |
| **G9** | No mutation | by construction |
| **G10** | Every finding classifies into 5 binding defects | 19/19 observed |
| **G11** | State and confidence never disagree — `Certain` is exactly 256 | enforced |

**Not guaranteed, and stated so:**

- **Termination in general.** Only for anchored functions with a proven
  measure. Unanchored recursion halts at the ceiling rather than
  diverging, which is a weaker but honest promise.
- **Type soundness.** Checking is dynamic. There is no static type
  system and no progress/preservation proof.
- **Confidence calibration.** Nothing asserts that a thread at 200/256
  is right 78% of the time. Confidence is an internal ordering, not a
  measured frequency. **This is the largest open claim in the language.**

---

## 7. Not yet specified

Named honestly, because scope depends on it.

| Missing | Consequence |
|---|---|
| Composite data (records, lists) | `E_TYPE_LIST` is an unimplemented enum |
| Higher-order functions | functions cannot be arguments |
| Pattern matching | only `if/then/else` |
| Static type system | dynamic tag checks only |
| Module system | one flat global namespace |
| Transpiler back-ends | anchored bodies do not yet emit Rust/Go/TS |
| Formal grammar (EBNF) | parsing is regex-based |
| Soundness proof | no progress/preservation |
| ~~Forgiveness cost~~ | *specified in §9* |

**Transpilation is the largest gap.** The decision is that an anchored
function's *body* travels into the target language, with its Examples as
the verification contract: the emitted Rust must satisfy the same
Examples to inherit the anchor. Nothing of this is built.

---

## 8. Worked example

```ever
def fact(n) = if n <= 1 then 1 else n * fact(n - 1)
```

| Step | Result |
|---|---|
| `[DEF]` | thread at 120/256, recursive, measure `n` found |
| `fact(3)` | 6 — depth 3, within ⌊π⌋ |
| `fact(8)` | **blocked** — DepthExceeded at ceiling 3 |
| Examples `(1,1) (2,2) (3,6)` | 217/256 by `[EXAMPLE]` |
| `[ANCHOR-REC]` | Anchored, depth := ∞ on measure `n` |
| `fact(100)` | computes, depth 99 |

Every value returns at **217/256** — the chain rule flooring on `fact`
itself, which is exactly right: *a result is only as trustworthy as the
function that produced it.* The literals `1` in the base case are program
constants at `Certain` and do not drag the floor down.

An earlier draft floored this at 120 by treating source literals as
external input. That made every computation in the language permanently
unexecutable. The fix was one localised change at the entry points, not
a rebuild; four tests failed and all four had been asserting the defect.

---

*297 assertions across C, C++, Python and SQL, plus 70 on the
abstraction layer. Codric Enterprise, 2026.*

---

## 9. Forgiveness

E does not refuse a program over a misplaced comma. Until now that
behaviour lived only in `forgive.py` and was priced nowhere — the
implementation counted repairs and never charged for them. This section
defines the rule the implementations are measured against.

### 9.1 Failure and Fixture

A healing is **two things, never one**:

- **Failure** — the problem. What the source actually said.
- **Fixture** — the solution. What E bound in its place.

Both are archived, every time, unconditionally. A Fixture recorded
without its Failure is an invention: the record shows code E wrote with
no evidence of what provoked it. A Failure recorded without a Fixture is
a refusal, not a repair. Neither half is archived alone, and the archive
enforces this rather than trusting it — `repair` rejects an empty
`failure_text` or `fixture_text` outright.

Nothing is deleted. A repair later proved wrong stays as a boundary
marker, the same as an `EError`.

### 9.2 Two kinds, two prices

| Kind | What happens | Cost |
|---|---|---|
| **plain** | noise removed; one reading was possible | `E_REPAIR_PLAIN` = 8 |
| **inferred** | structure supplied; intent was assumed | `E_REPAIR_INFERRED` = 32 |

Both are derived from `E_CERTAIN` (256): `256/32` and `256/8`.

Charging one rate for both would assert that deleting a stray semicolon
and inventing a comma carry equal risk. They do not. A trailing comma
could only have meant one thing. An inserted comma is a claim about what
the author intended, and it is a claim E is usually — not always — right
about.

The consequence falls out rather than being tuned: **four inferred
repairs land a binding at exactly `E_EXECUTE_FLOOR` (128).** The fifth
puts it beneath the floor, where it must not run unexamined. A program
needing five guesses about its structure is not a program with typos.

### 9.3 The seven repairs

| # | Repair | Kind | Defect |
|---|---|---|---|
| 1 | `trailing_comma` | plain | none |
| 2 | `stray_semicolon` | plain | none |
| 3 | `keyword_case` | plain | none |
| 4 | `colon_for_equals` | inferred | misbound |
| 5 | `equals_for_colon` | inferred | misbound |
| 6 | `equals_for_compare` | inferred | misbound |
| 7 | `missing_comma` | inferred | unbounded |

Enumerated in `ever_repair` so a second implementation is measured
against the table, not against Python's error wording.

### 9.4 What is never healed

Missing closing bracket, unterminated string, wrong bracket kind,
closing the wrong opener, missing `def` body. Guessing where these end
is guessing structure, not fixing a slip. E explains them and refuses.

### 9.5 Fixture form

`fixture_text` is prose, for a human reading the archive.
`fixture_form` is the same solution as a structured token edit.

Prose cannot be replayed, so a repair whose `fixture_form` is `NULL`
counts toward nothing. This column is the gate on §9.6, and it is the
only reason any of it is possible.

### 9.6 Rules derived from the archive

A Failure shape that has resolved to the **same** `fixture_form` across
`E_ASCEND_POINTS` (3) *distinct sources* is a candidate rule. Distinct
sources, not total count: ten repairs in one file is one author's habit.

A candidate is not a rule. It is born as `proposed` at `E_INTAKE` (120),
beneath the execute floor, healing nothing. It is then **replayed
against every repair already archived**. If admitting it would change
the outcome of any prior recorded repair, it is `rejected` — and kept,
with the reason.

Only a rule that agrees with the entire archive may rise to the floor
and be `admitted`. The archive enforces both conditions: a rule cannot
be `admitted` below 128, and cannot be `admitted` with
`replay_agreed < replay_total`.

No threshold here is new. `E_ASCEND_POINTS`, `E_INTAKE` and
`E_EXECUTE_FLOOR` were already constants; this section spends them
rather than inventing rates beside them.
