#!/usr/bin/env python3
"""ever_test.py — Ever / Tapestry interpreter verification."""

from ever import (
    Ever, E, Lang, State, Defect,
    a_any, a_anchor, a_assimilate, a_ascend, a_apply2all, a_autodidact,
    e_z, e_val, e_equiv, combine, excel,
    E_CERTAIN, E_ZERO, E_EXECUTE_FLOOR, E_PI_WIDTH_WARN,
    E_PI_WIDTH_ENUMERATE, E_EMULATE_CEILING, E_ASCEND_POINTS, E_INTAKE,
)

passed = failed = 0


def ok(name, cond):
    global passed, failed
    if cond:
        passed += 1; print(f"  \u2713 {name}")
    else:
        failed += 1; print(f"  \u2717 {name}")


print("\n=== Ever / Tapestry — the interpreter ===\n")

print("Constants agree with the C atom")
ok("Certain is 256",          E_CERTAIN == 256)
ok("execute floor is 128",    E_EXECUTE_FLOOR == 128)
ok("pi warn is 81",           E_PI_WIDTH_WARN == 81)
ok("pi squared is 25",        E_PI_WIDTH_ENUMERATE == 25)
ok("emulate ceiling is 3",    E_EMULATE_CEILING == 3)
ok("ascend points is 3",      E_ASCEND_POINTS == 3)

print("\nThe thread carries T")
n = e_val("count", 42, 180)
ok("holds its value",         n.value == 42)
ok("knows its type",          n.type_name() == "int")
ok("carries confidence",      n.confidence == 180)
ok("text type",               e_val("s", "hi", 150).type_name() == "text")
ok("real type",               e_val("r", 1.5, 150).type_name() == "real")
ok("bool type",               e_val("b", True, 150).type_name() == "bool")
ok("Z holds nothing",         e_z("x").value is None)

print("\nA1 ANY")
ok("lifts int",               a_any("x", "42").value == 42)
ok("lifts real",              a_any("y", "3.14").type_name() == "real")
ok("lifts text",              a_any("s", '"hello"').value == "hello")
ok("lifts bool",              a_any("b", "true").value is True)
for word in ("null", "nil", "None", "undefined", "nullptr"):
    ok(f"{word} lifts to Z",  a_any("n", word).is_z)
ok("unterminated is unbounded",
   a_any("s", '"oops').defect == Defect.UNBOUNDED)
ok("intake below floor",      a_any("x", "42").confidence < E_EXECUTE_FLOOR)

print("\nA2 ASSIMILATE")
py = e_val("total", 99, 200, Lang.PYTHON)
rs = a_assimilate(py, Lang.RUST)
ok("payload survives",        rs.value == 99)
ok("language changed",        rs.lang == Lang.RUST)
ok("unanchored pays 1",       rs.confidence == 199)
ok("Z does not translate",    a_assimilate(e_z("u"), Lang.GO).is_z)
ok("same language identity",  a_assimilate(py, Lang.PYTHON).confidence == 200)

print("\nA3 ANCHOR")
anc = a_anchor(py, 7001)
ok("anchor set",              anc.is_anchored)
ok("state is ANCHORED",       anc.state == State.ANCHORED)
h = anc
for lang in (Lang.RUST, Lang.SWIFT, Lang.JAVA, Lang.GO, Lang.TS):
    h = a_assimilate(h, lang)
ok("five hops, no loss",      h.confidence == 200)
ok("anchor held",             h.anchor_id == 7001)
ok("payload held",            h.value == 99)
d = py
for lang in (Lang.RUST, Lang.SWIFT, Lang.JAVA, Lang.GO, Lang.TS):
    d = a_assimilate(d, lang)
ok("unanchored drifts 5",     d.confidence == 195)
ok("anchoring is the difference", h.confidence > d.confidence)
ok("cannot anchor a Z",       a_anchor(e_z("u")).is_z)

print("\nA4 ASCEND")
base = e_val("parse", 1, 150)
ev = e_val("e", 1, 160)
s1 = a_ascend(base, ev)
ok("one point no lift",       s1.confidence == 150)
s2 = a_ascend(s1, ev)
s3 = a_ascend(s2, ev)
ok("three points lift",       s3.confidence > 150)
ok("matches excel",           s3.confidence == excel(150, 160))
ok("generation advanced",     s3.generation == 1)
ok("points reset",            s3.ascend_points == 0)
ok("disagreement resets",     a_ascend(s1, e_val("f", 1, 40)).ascend_points == 0)
ok("disagreement no lower",   a_ascend(s1, e_val("f", 1, 40)).confidence == 150)
ok("Z cannot ascend",         a_ascend(e_z("u"), ev).is_z)

print("\nA5 APPLY2ALL")
def halve(p):
    q = E(**{**p.__dict__}); q.confidence = p.confidence // 2
    q.lo = q.hi = q.confidence; return q

res, halt = a_apply2all([e_val("a", 1, 200), e_val("b", 2, 180)], halve)
ok("all transformed",         halt == -1 and res[0].confidence == 100)
res, halt = a_apply2all(
    [e_val("a", 1, 200), e_z("b"), e_val("c", 3, 160)], halve)
ok("halts at Z",              halt == 1)
ok("past halt untouched",     res[2].confidence == 160)

print("\nA6 AUTO-DIDACT")
hist = [e_val("o", i, c) for i, c in enumerate((170, 175, 180, 178))]
rule = a_autodidact(hist, "conf")
ok("rule derived",            rule.is_cleared)
ok("rule holds mean",         rule.value == 175)
ok("rule records spread",     rule.lo == 170 and rule.hi == 180)
ok("under three refuses",     a_autodidact(hist[:2], "x").is_z)
ok("scattered refuses",
   a_autodidact([e_val("o", 1, c) for c in (20, 240, 60, 200)], "s").is_z)
drule = a_autodidact(
    [e_z("d", "a", Defect.UNBOUND), e_z("d", "b", Defect.UNBOUND),
     e_z("d", "c", Defect.UNBOUND), e_val("d", 1, 180)], "rec")
ok("recurring defect is a rule", drule.value == "unbound")

print("\nArithmetic propagates confidence")
a, b = e_val("a", 10, 200), e_val("b", 3, 150)
ok("result is weaker input",  combine(a, b, "*", "c").confidence == 150)
ok("value computed",          combine(a, b, "*", "c").value == 30)
ok("Z operand yields Z",      combine(a, e_z("u"), "+", "c").is_z)
ok("Z names the binding",     "u" in combine(a, e_z("u"), "+", "c").reason)
ok("div by zero is Z",        combine(a, e_val("z", 0, 200), "/", "c").is_z)
ok("type mismatch is misbound",
   combine(a, e_val("s", "x", 200), "-", "c").defect == Defect.MISBOUND)

print("\nEquivalence and pi")
ok("width computed",          e_equiv("s", 100, 115).width == 15)
ok("15 acceptable",           e_equiv("s", 100, 115).pi_status() == "ACCEPTABLE")
ok("26 enumerate",            e_equiv("s", 100, 126).pi_status() == "ENUMERATE")
ok("150 approaching Z",       e_equiv("s", 50, 200).pi_status() == "APPROACHING_Z")
ok("reversed corrected",      e_equiv("s", 200, 50).lo == 50)

print("\nPrograms execute")
p1 = Ever().run('let x = 10\nlet y = 3\never z = x * y\nshow z')
ok("arithmetic over program constants executes",
   any("z = 30" in o for o in p1.output))

p2 = Ever().run('''
let x = 200
ascend x by 125
ascend x by 130
ascend x by 128
show x
''')
ok("value and confidence are different things",
   any("x = 200" in o and "/256" in o for o in p2.output))
ok("ascended past the floor",
   any(int(o.split("[")[1].split("/")[0]) >= 128
       for o in p2.output if "[" in o))

p3 = Ever().run('z secret "not provided"\never leak = secret + 1\nshow leak')
ok("Z contagion in a program", any("Z" in o for o in p3.output))
ok("reason names the binding", any("secret" in o for o in p3.output))

p4 = Ever().run('''
anchor total = 500
assimilate total to RUST
assimilate total to SWIFT
assimilate total to GO
show total
''')
ok("anchored constant crosses losslessly",
   any("256/256" in o for o in p4.output))
ok("anchor mark shown",        any("\u2693" in o for o in p4.output))

p4b = Ever().run('''
let loose = 500
assimilate loose to RUST
assimilate loose to SWIFT
assimilate loose to GO
show loose
''')
ok("unanchored drifts one per hop",
   any("253/256" in o for o in p4b.output))

p5 = Ever().run('z sensor "not read"\nexpect sensor >= 200\nshow sensor')
ok("expect blocks on unknown data", p5.blocked > 0)
ok("blocked reported",         any("BLOCKED" in o for o in p5.output))
p5b = Ever().run('let a = 100\nexpect a >= 200\nshow a')
ok("a program constant passes the gate", p5b.blocked == 0)

p6 = Ever().run('let q = 5\nshow nosuch')
ok("unbound name reported",    any("never bound" in o for o in p6.output))

p7 = Ever().run('let x = 1\nthis is not ever')
ok("parse error reported",     any("cannot parse" in o for o in p7.output))

print("\nArchive keeps what failed")
p8 = Ever().run('z a "one"\nz b "two"\nlet c = 5')
ok("archive holds the Zs",     len(p8.archive) == 2)
ok("cleared not archived",     all(not x.is_cleared for x in p8.archive))

print("\nSerialization")
line = a_anchor(e_val("t", 99, 200), 7001).serialize()
ok("sixteen fields",           len(line.split("|")) == 16)
ok("carries the payload",      "99" in line)
ok("carries the anchor",       "7001" in line)

print(f"\n=== Interpreter: {passed} passed, {failed} failed ===\n")
raise SystemExit(0 if failed == 0 else 1)
