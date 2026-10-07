#!/usr/bin/env python3
"""scope_test.py — Ever / Tapestry, Python scope verification."""

import math
from ir import parse_to_ir, EvNode, NK
from scope import (EvScope, ScopeEntry, SK, fnv1a,
                    make_global_scope, eval_node)
from evalue import EValue, EvType, EV_CERTAIN, serialise, deserialise

p = f = 0
def ok(n, c):
    global p, f
    if c: p += 1; print(f"  \u2713 {n}")
    else: f += 1; print(f"  \u2717 {n}")

print("\n=== EvScope — Python universal map ===\n")

print("FNV-1a hash (matches scope.c)")
ok("fnv1a non-zero",        fnv1a("x") != 0)
ok("fnv1a deterministic",   fnv1a("hello") == fnv1a("hello"))
ok("fnv1a distinct",        fnv1a("abc") != fnv1a("def"))
ok("fnv1a empty",           fnv1a("") != 0)
# Exact value match with C implementation (FNV-1a 32-bit)
ok("fnv1a('x') == C value", fnv1a("x") == 0xfd0c5087)

print("\nLifecycle")
g = EvScope(name="global")
ok("created",          g is not None)
ok("depth 0",          g.depth == 0)
ok("len 0",            len(g) == 0)
ok("parent None",      g.parent is None)
ok("name set",         g.name == "global")

print("\nInsert and lookup — VAR")
g.set_var("x",     EValue.from_int(42))
g.set_var("y",     EValue.from_real(3.14))
g.set_var("flag",  EValue.from_bool(True))
g.set_var("name",  EValue.from_text("Codric"))

e = g.get("x")
ok("get x",           e is not None)
ok("x value = 42",    e and e.value.ev_int == 42)
ok("x kind = VAR",    e and e.kind == SK.VAR)
ok("x conf = 256",    e and e.confidence == EV_CERTAIN)

ok("get y real",      g.get("y") and abs(g.get("y").value.ev_real - 3.14) < 1e-9)
ok("get flag bool",   g.get("flag") and g.get("flag").value.ev_bool is True)
ok("get name text",   g.get("name") and g.get("name").value.ev_text == "Codric")
ok("get missing",     g.get("zzz") is None)
ok("lookup missing",  g.lookup("zzz") is None)
ok("len = 4",         len(g) == 4)

print("\nUpdate")
g.set_var("x", EValue.from_int(99))
ok("x updated to 99", g.get("x").value.ev_int == 99)
ok("len still 4",     len(g) == 4)

print("\nFunction entries — SK.FN")
body = EvNode.binop("*", EvNode.var("n"), EvNode.var("n"))
g.set_fn("square", body, ["n"])
e_fn = g.get("square")
ok("get square",      e_fn is not None)
ok("kind = FN",       e_fn and e_fn.kind == SK.FN)
ok("node = body",     e_fn and e_fn.node is body)
ok("params = ['n']",  e_fn and e_fn.params == ["n"])
ok("get_fn returns",  g.get_fn("square") is body)
ok("get_fn missing",  g.get_fn("nope") is None)

print("\nModule entries — SK.MODULE")
math_mod = EvScope(parent=g, name="Math")
math_mod.set_var("PI", EValue.from_real(math.pi))
g.set_module("Math", math_mod)
e_m = g.get("Math")
ok("get Math",        e_m is not None)
ok("kind = MODULE",   e_m and e_m.kind == SK.MODULE)
ok("get_module",      g.get_module("Math") is math_mod)
ok("module PI",       abs(g.get_module("Math").get_value("PI").ev_real - math.pi) < 1e-9)

print("\nScope chain — local inherits global")
local = EvScope(parent=g, name="fn:add")
ok("depth = 1",       local.depth == 1)
ok("parent = global", local.parent is g)
local.set_var("a", EValue.from_int(10))
local.set_var("b", EValue.from_int(32))
ok("lookup a local",  local.lookup("a").value.ev_int == 10)
ok("lookup x chain",  local.lookup("x").value.ev_int == 99)
local.set_var("x", EValue.from_int(0))
ok("shadow x = 0",    local.lookup("x").value.ev_int == 0)
ok("global x = 99",   g.get("x").value.ev_int == 99)
ok("get_value b",     local.get_value("b").ev_int == 32)
ok("get_value void",  local.get_value("zzz").ev_tag == EvType.VOID)

print("\nDelete")
ds = EvScope(name="del")
ds.set_var("a", EValue.from_int(1))
ds.set_var("b", EValue.from_int(2))
ds.set_var("c", EValue.from_int(3))
ok("delete b",        ds.delete("b"))
ok("b gone",          ds.get("b") is None)
ok("a still live",    ds.get("a") is not None)
ok("delete missing",  not ds.delete("zzz"))
ok("len = 2",         len(ds) == 2)
ds.set_var("b", EValue.from_int(99))
ok("re-insert b=99",  ds.get("b").value.ev_int == 99)

print("\nBulk insert (100 entries)")
bulk = EvScope(name="bulk")
for i in range(100):
    bulk.set_var(f"var_{i}", EValue.from_int(i))
ok("100 inserted",    len(bulk) == 100)
all_ok = all(bulk.get(f"var_{i}") and
              bulk.get(f"var_{i}").value.ev_int == i
              for i in range(100))
ok("all 100 correct", all_ok)

print("\nWire format — scope ↔ EValue(RECORD)")
ws = EvScope(name="wire")
ws.set_var("id",    EValue.from_int(7))
ws.set_var("name",  EValue.from_text("Alice"))
ws.set_var("score", EValue.from_real(98.6))
rec = ws.to_record()
ok("to_record RECORD",   rec.ev_tag == EvType.RECORD)
ok("to_record has id",   rec.get("id") is not None and rec.get("id").ev_int == 7)
ok("to_record has name", rec.get("name") and rec.get("name").ev_text == "Alice")
ws2 = EvScope.from_record(rec, name="wire2")
ok("from_record id",     ws2.get_value("id").ev_int == 7)
ok("from_record name",   ws2.get_value("name").ev_text == "Alice")
ok("from_record score",  abs(ws2.get_value("score").ev_real - 98.6) < 1e-9)
# serialise through evalue wire format
buf = serialise(rec)
back_rec, pos = deserialise(buf)
ok("EValue wire serialise",  pos == len(buf))
ws3 = EvScope.from_record(back_rec, name="wire3")
ok("C→wire→Python id",   ws3.get_value("id").ev_int == 7)

print("\neval_node through scope")
ev_g = make_global_scope()
ev_g.set_var("x", EValue.from_int(6))
ev_g.set_var("y", EValue.from_int(36))

for src, expected, label in [
    ("6 + 36",                 42,  "literal add"),
    ("if true then 42 else 0", 42,  "if true"),
    ("if false then 0 else 42",42,  "if false"),
]:
    r = parse_to_ir(src)
    ok(f"parse {label}", r.ok)
    if r.ok:
        result = eval_node(r.root, EvScope(parent=ev_g))
        ok(f"eval {label} = {expected}",
           result.ev_tag == EvType.INT and result.ev_int == expected)

# define and call a function through the scope
fact_scope = EvScope(parent=ev_g, name="fact-test")
r2 = parse_to_ir("def fact(n) = if n <= 1 then 1 else n * fact(n - 1)")
ok("parse fact", r2.ok)
eval_node(r2.root, fact_scope)  # registers fact
ok("fact registered",  "fact" in fact_scope)

for n_val, expected in [(1,1),(2,2),(3,6)]:
    call = EvNode.fn_call("fact", [EvNode.int_lit(n_val)])
    result = eval_node(call, fact_scope, depth=0)
    ok(f"fact({n_val}) = {expected}",
       result.ev_tag == EvType.INT and result.ev_int == expected)

# depth ceiling enforced
call4 = EvNode.fn_call("fact", [EvNode.int_lit(4)])
r4 = eval_node(call4, fact_scope, depth=0)
ok("fact(4) void (depth ceiling)", r4.ev_tag == EvType.VOID)

print("\nBuiltin scope")
bg = make_global_scope()
ok("true pre-loaded",  bg.get("true") and bg.get("true").value.ev_bool is True)
ok("false pre-loaded", bg.get("false") and bg.get("false").value.ev_bool is False)
ok("z pre-loaded",     bg.get("z") and bg.get("z").value.ev_tag == EvType.VOID)
ok("print builtin",    bg.get("print") and bg.get("print").kind == SK.BUILTIN)

print(f"\n=== EvScope Python: {p} passed, {f} failed ===\n")
raise SystemExit(0 if f == 0 else 1)
