#!/usr/bin/env python3
"""syntax_test.py — Ever / Tapestry, pipeline stages 1-3 verification."""

from syntax import (
    T, Token, lex, parse, Parser, ParseError, compile_ever,
    Num, Str, Bool, Var, BinOp, If, Call, FnDef,
    Semantic, Ty, Analysis, eval_ast,
    skeleton, distinct_skeletons, distinct_shapes, Trust,
)
from ever import Defect, E_CERTAIN, E_INTAKE

passed = failed = 0


def ok(name, cond):
    global passed, failed
    if cond:
        passed += 1; print(f"  \u2713 {name}")
    else:
        failed += 1; print(f"  \u2717 {name}")


print("\n=== Ever — pipeline stages 1 through 3 ===\n")

print("1. LEXER")
toks, err = lex("def f(n) = n + 1")
ok("no error",              err is None)
ok("ends with EOF",         toks[-1].kind is T.EOF)
ok("def is a keyword",      toks[0].kind is T.KW)
ok("f is a name",           toks[1].kind is T.NAME)
ok("number recognised",     any(t.kind is T.NUM for t in toks))
ok("tokens carry position", all(t.pos >= 0 for t in toks))

toks2, _ = lex("a <= b")
ok("two-char comparison is one token",
   any(t.kind is T.CMP and t.text == "<=" for t in toks2))

toks3, _ = lex('x = "hello"')
ok("string literal lexed",  any(t.kind is T.STR for t in toks3))

toks4, _ = lex("a # this is a comment\nb")
ok("comments dropped",      len([t for t in toks4 if t.kind is T.NAME]) == 2)

toks5, _ = lex("1.5")
ok("float lexed whole",     toks5[0].text == "1.5")

_, bad = lex("a $ b")
ok("bad character is Z",    bad is not None and bad.is_z)
ok("bad character reports position", "at" in bad.reason)

toks6, _ = lex("line1\nline2\nline3")
ok("line numbers tracked",  toks6[-2].line == 3)

print("\n2. PARSER and AST")
ast, err = parse("1 + 2 * 3")
ok("parses without error",  err is None)
ok("multiplication binds tighter",
   isinstance(ast, BinOp) and ast.op == "+" and isinstance(ast.right, BinOp))

ast2, _ = parse("(1 + 2) * 3")
ok("parentheses override",  isinstance(ast2, BinOp) and ast2.op == "*")

ast3, _ = parse("1 - 2 - 3")
ok("subtraction left-associates",
   isinstance(ast3, BinOp) and isinstance(ast3.left, BinOp))

ast4, _ = parse("if n <= 1 then 1 else 2")
ok("if parsed",             isinstance(ast4, If))
ok("condition is a comparison",
   isinstance(ast4.cond, BinOp) and ast4.cond.op == "<=")

ast5, _ = parse("f(1, 2)")
ok("call parsed",           isinstance(ast5, Call) and len(ast5.args) == 2)

ast6, _ = parse("def sq(n) = n * n")
ok("definition parsed",     isinstance(ast6, FnDef))
ok("parameters captured",   ast6.params == ["n"])

_, perr = parse("1 +")
ok("incomplete expression is Z", perr is not None and perr.is_z)
ok("parse error is unbounded",   perr.defect == Defect.UNBOUNDED)

_, perr2 = parse("if n then 1")
ok("missing else is caught", perr2 is not None and perr2.is_z)

print("\nAST measures structure, not characters")
a, _ = parse("n")
b, _ = parse("n * 1")
c, _ = parse("((n))")
ok("size counts nodes",     a.size() == 1)
ok("n*1 is larger than n",  b.size() > a.size())
ok("redundant parens vanish", c.size() == a.size())
ok("depth computed",        b.depth() == 2)

d, _ = parse("if n <= 1 then 1 else n * f(n - 1)")
ok("nested depth",          d.depth() >= 4)
ok("shape erases constants", "Num" in d.shape() and "Var" in d.shape())

print("\n3. SEMANTIC ANALYSIS")
c1 = compile_ever("def f(n) = n + missing")
ok("unbound name caught before running",
   any("unbound" in e for e in c1.analysis.errors))
ok("reported exactly once",
   sum(1 for e in c1.analysis.errors if "missing" in e) == 1)

c2 = compile_ever('def g(n) = if n then "yes" else 3')
ok("branch type disagreement caught",
   any("branches disagree" in e for e in c2.analysis.errors))

c3 = compile_ever("def h(n) = n / 0")
ok("literal division by zero caught",
   any("division by a literal zero" in e for e in c3.analysis.errors))

c4 = compile_ever("def k(n) = f(n, n)", known_fns={"f": 1})
ok("arity mismatch caught",
   any("takes 1 argument" in e for e in c4.analysis.errors))

c5 = compile_ever("def ok1(n) = n * 2")
ok("clean program has no errors", c5.analysis.clean)
ok("stage reports ready",         c5.stage == "ready")
# n*2 with integer literal 2: n inferred as INT, result is INT
ok("type inferred as int (n*2 → int)",  c5.analysis.ty in (Ty.NUM, Ty.INT))

c6 = compile_ever("def fact(n) = if n <= 1 then 1 else n * fact(n - 1)")
ok("recursion detected",     c6.analysis.recursive)
ok("measure found on the AST", c6.analysis.measure == "n")
ok("self-call recorded",     "fact" in c6.analysis.calls)
ok("parameters are not free", c6.analysis.free == set())

c7 = compile_ever("def grow(n) = if n > 99 then n else grow(n + 1)")
ok("no measure for n + 1",   c7.analysis.measure is None)

c8 = compile_ever("def deep(n) = if n <= 0 then 0 else deep((n) - 1)")
ok("measure seen through parentheses", c8.analysis.measure == "n")

c9 = compile_ever("def bad(n) = n + true")
ok("bool arithmetic caught",
   any("bool" in e for e in c9.analysis.errors))

print("\nStages fail in order and say which")
ok("lex failure names lex",    compile_ever("a $ b").stage == "lex")
ok("parse failure names parse", compile_ever("1 +").stage == "parse")
ok("semantic failure names semantic",
   compile_ever("def f(n) = missing").stage == "semantic")
ok("clean names ready",        compile_ever("1 + 1").stage == "ready")

print("\n4. EXECUTION over the AST")
c10 = compile_ever("def fact(n) = if n <= 1 then 1 else n * fact(n - 1)")
fns = {c10.ast.name: c10.ast}
r = eval_ast(Call("fact", [Num(5)]), {}, fns, 0, limit=99)
ok("fact(5) computes",       r.value == 120)
# This read `r.confidence == E_CERTAIN` under the name "program
# constants are Certain", and was conflating two claims. A literal
# really is Certain -- checked just below, and it still holds. But
# `fact` is an unverified definition, and [APP] floors a result by the
# function that produced it, so a call through it comes back at INTAKE.
# The old assertion passed only because eval_ast dropped the c_f term
# from [APP] entirely, which is also why this file and abstract.py
# disagreed by 136 on the worked example in SEMANTICS.md section 8.
ok("an unverified function floors its result", r.confidence == E_INTAKE)
lit = eval_ast(BinOp("+", Num(1), Num(1)), {}, {}, 0)
ok("program constants are Certain", lit.confidence == E_CERTAIN)
trusted = eval_ast(Call("fact", [Num(5)]), {}, fns, 0, 99,
                   Trust(confidence={"fact": 217}))
ok("a verified function lifts its floor", trusted.confidence == 217)
r2 = eval_ast(Call("fact", [Num(8)]), {}, fns, 0, limit=3)
ok("depth ceiling still enforced", r2.is_z)

r3 = eval_ast(BinOp("/", Num(1), Num(0)), {}, {}, 0)
ok("division by zero is Z",  r3.is_z)
r4 = eval_ast(Var("nope"), {}, {}, 0)
ok("unbound variable is Z",  r4.is_z)
ok("unbound defect recorded", r4.defect == Defect.UNBOUND)

print("\nSkeletons: counting ideas, not strings")
prime = ["if n <= 0 then 1 else n + prime(n - 2)",
         "if n < 0 then 1 else n + prime(n - 2)",
         "if n < 1 then 1 else n + prime(n - 2)"]
k, _ = distinct_skeletons(prime)
ok("three strings, one idea",  k == 1)
ks, _ = distinct_shapes(prime)
ok("shapes are stricter than skeletons", ks >= k)

diverse = ["n * n", "(n * 3) - 2", "n + n",
           "if n <= 1 then 1 else n + f(n - 1)"]
kd, _ = distinct_skeletons(diverse)
ok("genuinely different ideas counted", kd == 4)

ok("constants collapse",   skeleton(parse("1")[0]) == skeleton(parse("99")[0]))
ok("variables collapse",   skeleton(parse("n")[0]) == skeleton(parse("x")[0]))
ok("comparisons collapse",
   skeleton(parse("n < 1")[0]) == skeleton(parse("n >= 4")[0]))
ok("arithmetic does not collapse",
   skeleton(parse("n + 1")[0]) != skeleton(parse("n * 1")[0]))

print(f"\n=== Pipeline: {passed} passed, {failed} failed ===\n")
raise SystemExit(0 if failed == 0 else 1)
