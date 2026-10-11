"""Thin runner for the IR test — avoids shell heredoc escaping."""
from ir import parse_to_ir, EvNode, NK, serialise, deserialise
p=f=0
def ok(n,c):
    global p,f
    if c: p+=1
    else: f+=1
cases=[
    "1","1 + 2","if true then 1 else 0",
    "def f(x) = x * 2",
    "def fact(n) = if n <= 1 then 1 else n * fact(n - 1)",
]
for src in cases:
    r=parse_to_ir(src)
    ok(src, r.ok and r.root is not None and len(r.to_bytes())>0)
bad=parse_to_ir("def f(n) = missing")
ok("bad", not bad.ok)
fn=EvNode.fn_def("fact",["n"],EvNode.int_lit(1))
fn.measure()
buf=serialise(fn); back,pos=deserialise(buf)
ok("rt", pos==len(buf) and back.kind==NK.DEF)
print(f"=== IR Python bridge: {p} passed, {f} failed ===")
