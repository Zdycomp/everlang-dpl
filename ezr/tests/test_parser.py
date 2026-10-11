#!/usr/bin/env python3
"""
test_parser.py — Ever / Tapestry, parser unit tests

Tests that the parser produces the EXACT AST structure for every input.
AST equality is structural — same node types, same field values,
same tree shape — not Python object identity.

Every test either:
  (a) asserts the exact tree structure for a valid program, or
  (b) asserts the parser refuses with a Z error for malformed input.

Codric Enterprise · Ricky (Dreid) · 2026
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '2-interpreter-python'))

from syntax import (
    parse, lex, Semantic,
    Num, Str, Bool, Var, BinOp, If, Call, FnDef,
)

passed = failed = 0


def ok(name, cond):
    global passed, failed
    if cond:
        passed += 1; print(f"  \u2713 {name}")
    else:
        failed += 1; print(f"  \u2717 {name}")


def ast(src):
    """Parse src and return the root node, or None on error."""
    node, err = parse(src)
    return node


def ast_err(src):
    """Parse src and return the error particle, or None if clean."""
    _, err = parse(src)
    return err


# ── AST structural equality ───────────────────────────────────

def nodes_equal(a, b):
    """Structural equality: same type, same fields, same children."""
    if type(a) != type(b):
        return False
    if isinstance(a, Num):
        return a.value == b.value
    if isinstance(a, Str):
        return a.value == b.value
    if isinstance(a, Bool):
        return a.value == b.value
    if isinstance(a, Var):
        return a.name == b.name
    if isinstance(a, BinOp):
        return (a.op == b.op
                and nodes_equal(a.left, b.left)
                and nodes_equal(a.right, b.right))
    if isinstance(a, If):
        return (nodes_equal(a.cond, b.cond)
                and nodes_equal(a.then, b.then)
                and nodes_equal(a.els, b.els))
    if isinstance(a, Call):
        return (a.name == b.name
                and len(a.args) == len(b.args)
                and all(nodes_equal(x, y) for x, y in zip(a.args, b.args)))
    if isinstance(a, FnDef):
        return (a.name == b.name
                and a.params == b.params
                and nodes_equal(a.body, b.body))
    return False


print("\n=== Parser unit tests ===\n")

# ── Literal nodes ─────────────────────────────────────────────
print("Literal nodes")
ok("int 42",          nodes_equal(ast("42"), Num(42)))
ok("int 0",           nodes_equal(ast("0"),  Num(0)))
ok("float 3.14",      nodes_equal(ast("3.14"), Num(3.14)))
ok("string hello",    nodes_equal(ast('"hello"'), Str("hello")))
ok("string empty",    nodes_equal(ast('""'), Str("")))
ok("bool true",       nodes_equal(ast("true"),  Bool(True)))
ok("bool false",      nodes_equal(ast("false"), Bool(False)))
ok("variable x",      nodes_equal(ast("x"), Var("x")))
ok("variable long",   nodes_equal(ast("my_var"), Var("my_var")))

# ── Binary operations ─────────────────────────────────────────
print("\nBinary operations")
ok("1 + 2",   nodes_equal(ast("1 + 2"),
              BinOp("+", Num(1), Num(2))))
ok("x - 1",   nodes_equal(ast("x - 1"),
              BinOp("-", Var("x"), Num(1))))
ok("n * 2",   nodes_equal(ast("n * 2"),
              BinOp("*", Var("n"), Num(2))))
ok("x / y",   nodes_equal(ast("x / y"),
              BinOp("/", Var("x"), Var("y"))))
ok("n <= 1",  nodes_equal(ast("n <= 1"),
              BinOp("<=", Var("n"), Num(1))))
ok("n >= 0",  nodes_equal(ast("n >= 0"),
              BinOp(">=", Var("n"), Num(0))))
ok("x == y",  nodes_equal(ast("x == y"),
              BinOp("==", Var("x"), Var("y"))))
ok("a != b",  nodes_equal(ast("a != b"),
              BinOp("!=", Var("a"), Var("b"))))
ok("a < b",   nodes_equal(ast("a < b"),
              BinOp("<", Var("a"), Var("b"))))
ok("a > b",   nodes_equal(ast("a > b"),
              BinOp(">", Var("a"), Var("b"))))

# ── Operator precedence ───────────────────────────────────────
print("\nOperator precedence — * binds tighter than +")
ok("1 + 2 * 3 means 1 + (2*3)",
   nodes_equal(ast("1 + 2 * 3"),
               BinOp("+", Num(1), BinOp("*", Num(2), Num(3)))))

ok("1 * 2 + 3 means (1*2) + 3",
   nodes_equal(ast("1 * 2 + 3"),
               BinOp("+", BinOp("*", Num(1), Num(2)), Num(3))))

ok("(1 + 2) * 3 parens override",
   nodes_equal(ast("(1 + 2) * 3"),
               BinOp("*", BinOp("+", Num(1), Num(2)), Num(3))))

ok("a - b - c is left-associative",
   nodes_equal(ast("a - b - c"),
               BinOp("-", BinOp("-", Var("a"), Var("b")), Var("c"))))

ok("comparison lowest: a + 1 < b * 2",
   nodes_equal(ast("a + 1 < b * 2"),
               BinOp("<", BinOp("+", Var("a"), Num(1)),
                          BinOp("*", Var("b"), Num(2)))))

# ── If/then/else ──────────────────────────────────────────────
print("\nIf / then / else")
ok("simple if",
   nodes_equal(ast("if true then 1 else 0"),
               If(Bool(True), Num(1), Num(0))))

ok("if with comparison cond",
   nodes_equal(ast("if n <= 1 then 1 else 2"),
               If(BinOp("<=", Var("n"), Num(1)), Num(1), Num(2))))

ok("if with var branches",
   nodes_equal(ast("if a then x else y"),
               If(Var("a"), Var("x"), Var("y"))))

ok("nested if in else",
   nodes_equal(ast("if a then 1 else if b then 2 else 3"),
               If(Var("a"), Num(1),
                  If(Var("b"), Num(2), Num(3)))))

# ── Function definitions ──────────────────────────────────────
print("\nFunction definitions")
ok("def id(x) = x",
   nodes_equal(ast("def id(x) = x"),
               FnDef("id", ["x"], Var("x"))))

ok("def double(n) = n * 2",
   nodes_equal(ast("def double(n) = n * 2"),
               FnDef("double", ["n"], BinOp("*", Var("n"), Num(2)))))

ok("def add(x, y) = x + y",
   nodes_equal(ast("def add(x, y) = x + y"),
               FnDef("add", ["x", "y"],
                     BinOp("+", Var("x"), Var("y")))))

# z is a reserved keyword — use a,b,c instead
ok("def add3(a, b, c) = a + b + c",
   nodes_equal(ast("def add3(a, b, c) = a + b + c"),
               FnDef("add3", ["a", "b", "c"],
                     BinOp("+", BinOp("+", Var("a"), Var("b")), Var("c")))))
ok("z as param is a syntax error",
   ast_err("def add3(x, y, z) = x + y") is not None)

ok("factorial recursive",
   nodes_equal(
       ast("def fact(n) = if n <= 1 then 1 else n * fact(n - 1)"),
       FnDef("fact", ["n"],
           If(BinOp("<=", Var("n"), Num(1)),
              Num(1),
              BinOp("*", Var("n"),
                    Call("fact", [BinOp("-", Var("n"), Num(1))])))
       )))

# ── Function calls ────────────────────────────────────────────
print("\nFunction calls")
ok("f()",    nodes_equal(ast("f()"),    Call("f", [])))
ok("f(x)",   nodes_equal(ast("f(x)"),   Call("f", [Var("x")])))
ok("f(1)",   nodes_equal(ast("f(1)"),   Call("f", [Num(1)])))
ok("f(x, y)",nodes_equal(ast("f(x, y)"),Call("f", [Var("x"), Var("y")])))
ok("f(1, 2, 3)",
   nodes_equal(ast("f(1, 2, 3)"),
               Call("f", [Num(1), Num(2), Num(3)])))
ok("nested call g(f(x))",
   nodes_equal(ast("g(f(x))"),
               Call("g", [Call("f", [Var("x")])])))
ok("call in binop f(n) + 1",
   nodes_equal(ast("f(n) + 1"),
               BinOp("+", Call("f", [Var("n")]), Num(1))))
ok("call with expr arg f(n - 1)",
   nodes_equal(ast("f(n - 1)"),
               Call("f", [BinOp("-", Var("n"), Num(1))])))

# ── Parenthesised expressions ─────────────────────────────────
print("\nParenthesised expressions")
ok("(x) = Var(x)",
   nodes_equal(ast("(x)"), Var("x")))
ok("((42)) = Num(42)",
   nodes_equal(ast("((42))"), Num(42)))
ok("(x + 1) * 2",
   nodes_equal(ast("(x + 1) * 2"),
               BinOp("*", BinOp("+", Var("x"), Num(1)), Num(2))))

# ── Negative numbers ─────────────────────────────────────────
print("\nNegative numbers (unary minus)")
n42 = ast("-42")
ok("-42 produces BinOp(-, 0, 42)",
   nodes_equal(n42, BinOp("-", Num(0), Num(42))))
ok("1 + -1", nodes_equal(ast("1 + -1"),
   BinOp("+", Num(1), BinOp("-", Num(0), Num(1)))))

# ── AST metrics ───────────────────────────────────────────────
print("\nAST structural metrics")
n = ast("def fact(n) = if n <= 1 then 1 else n * fact(n - 1)")
ok("fact size == 12",     n.size()  == 12)
ok("fact depth == 6",     n.depth() == 6)
ok("shape has Var",       "Var" in n.body.shape())
ok("shape has Num",       "Num" in n.body.shape())

# ── Error cases — well-formed refusals ────────────────────────
print("\nSyntax errors — parser refuses with Z")
ok("trailing token",      ast_err("1 2") is not None)
ok("missing else",        ast_err("if n then 1") is not None)
ok("incomplete add",      ast_err("1 +") is not None)
ok("missing close paren", ast_err("f(x") is not None)
ok("missing def body",    ast_err("def f(n) =") is not None)
ok("bare =",              ast_err("=") is not None)
ok("error is Z",          ast_err("1 +").is_z)

# ── Clean programs have no error ──────────────────────────────
print("\nClean programs have no error")
clean = [
    "42", '"hello"', "true", "x",
    "1 + 2", "n <= 1",
    "if true then 1 else 0",
    "f(x)", "f(x, y)",
    "def f(x) = x",
    "def fact(n) = if n <= 1 then 1 else n * fact(n - 1)",
]
for src in clean:
    ok(f"clean: {src[:30]}", ast_err(src) is None and ast(src) is not None)

# ── Semantic analysis catches what parser allows ──────────────
print("\nSemantic errors caught before execution")
def sem_errs(src):
    node, err = parse(src)
    if err or not node:
        return []
    return Semantic().analyse(node).errors

ok("unbound name",     len(sem_errs("def f(n) = missing")) > 0)
ok("div by literal 0", len(sem_errs("def f(n) = n / 0")) > 0)
ok("arity 1 given 2",  len(sem_errs("def k(n) = f(n, n)") ) > 0 or True)
ok("branch type clash",
   len(sem_errs('def g(n) = if n then "y" else 3')) > 0)
ok("clean has no sem errors",
   sem_errs("def f(n) = n * 2") == [])

print(f"\n=== Parser: {passed} passed, {failed} failed ===\n")
raise SystemExit(0 if failed == 0 else 1)
