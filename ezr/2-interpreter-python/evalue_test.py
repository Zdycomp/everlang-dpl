#!/usr/bin/env python3
"""evalue_test.py — Ever / Tapestry, Python-side unified variant tests."""

import math
from evalue import (
    EValue, EvType, EV_CERTAIN,
    serialise, deserialise,
    lift_literal, lift_sql_row, lift_html_element, lift_python,
)

passed = failed = 0
def ok(name, cond):
    global passed, failed
    if cond: passed += 1; print(f"  \u2713 {name}")
    else:    failed += 1; print(f"  \u2717 {name}")

print("\n=== EValue — Python unified variant type ===\n")

print("Scalars")
ok("void tag",         EValue.void().ev_tag == EvType.VOID)
ok("bool true",        EValue.from_bool(True).ev_bool is True)
ok("bool false",       EValue.from_bool(False).ev_bool is False)
ok("int 42",           EValue.from_int(42).ev_int == 42)
ok("int negative",     EValue.from_int(-99).ev_int == -99)
ok("real pi",          abs(EValue.from_real(math.pi).ev_real - math.pi) < 1e-12)
ok("text inline",      EValue.from_text("Codric").ev_text == "Codric")
ok("text long → blob", EValue.from_text("x"*200).ev_tag == EvType.BLOB)
ok("blob",             EValue.from_blob(b"\x01\x02").ev_blob == b"\x01\x02")

print("\nEquality")
ok("int == int",       EValue.from_int(1) == EValue.from_int(1))
ok("int != int",       EValue.from_int(1) != EValue.from_int(2))
ok("int-real interop", EValue.from_int(3) == EValue.from_real(3.0))
ok("int-real neq",     EValue.from_int(3) != EValue.from_real(3.1))
ok("text ==",          EValue.from_text("a") == EValue.from_text("a"))
ok("text !=",          EValue.from_text("a") != EValue.from_text("b"))
ok("void == void",     EValue.void() == EValue.void())
ok("void != int",      EValue.void() != EValue.from_int(0))

print("\nComposites")
lst = EValue.from_list([EValue.from_int(10), EValue.from_int(20),
                        EValue.from_text("hi")])
ok("list tag",         lst.ev_tag == EvType.LIST)
ok("list len",         len(lst) == 3)
ok("list[0]",          lst.get(0) == EValue.from_int(10))
ok("list[2]",          lst.get(2) == EValue.from_text("hi"))
ok("list OOB",         lst.get(99) is None)

lst2 = EValue.from_list([EValue.from_int(10), EValue.from_int(20),
                         EValue.from_text("hi")])
ok("equal lists",      lst == lst2)
lst3 = EValue.from_list([EValue.from_int(10)])
ok("unequal lists",    lst != lst3)

rec = EValue.from_record({
    "name": EValue.from_text("Alice"),
    "age":  EValue.from_int(30),
    "ok":   EValue.from_bool(True),
})
ok("record tag",       rec.ev_tag == EvType.RECORD)
ok("record len",       len(rec) == 3)
ok("record get name",  rec.get("name") == EValue.from_text("Alice"))
ok("record get age",   rec.get("age") == EValue.from_int(30))
ok("record missing",   rec.get("zzz") is None)

rec2 = EValue.from_record({
    "name": EValue.from_text("Alice"),
    "age":  EValue.from_int(30),
    "ok":   EValue.from_bool(True),
})
ok("equal records",    rec == rec2)
rec3 = EValue.from_record({"name": EValue.from_text("Bob")})
ok("unequal records",  rec != rec3)

nested = EValue.from_record({
    "items": EValue.from_list([EValue.from_int(1), EValue.from_int(2)])
})
ok("nested list in record", nested.get("items").ev_tag == EvType.LIST)
ok("nested get[1]",    nested.get("items").get(1) == EValue.from_int(2))

print("\nWire format — round-trip every type")
cases = [
    EValue.void(), EValue.from_bool(True), EValue.from_bool(False),
    EValue.from_int(42), EValue.from_int(-1), EValue.from_int(0),
    EValue.from_real(math.pi), EValue.from_real(-0.0),
    EValue.from_text("Codric"), EValue.from_text(""),
    EValue.from_blob(b"\x00\xff\xfe"), lst, rec, nested,
]
for v in cases:
    buf = serialise(v)
    back, consumed = deserialise(buf)
    ok(f"rt {v.ev_tag.name:8} {v.describe()[:18]}", v == back and consumed == len(buf))

print("\nLifters — same structure from different languages")
ok("int literal",    lift_literal("42").ev_tag == EvType.INT)
ok("real literal",   lift_literal("3.14").ev_tag == EvType.REAL)
ok("bool true lit",  lift_literal("true").ev_bool is True)
ok("bool False lit", lift_literal("False").ev_bool is False)
ok("str literal",    lift_literal('"hi"').ev_text == "hi")
ok("null → void",    lift_literal("null").ev_tag == EvType.VOID)
ok("nil → void",     lift_literal("nil").ev_tag == EvType.VOID)
ok("None → void",    lift_literal("None").ev_tag == EvType.VOID)

row = lift_sql_row(["id","name","score"],["1","Alice","98.6"])
ok("SQL row is record",     row.ev_tag == EvType.RECORD)
ok("SQL id → int",          row.get("id").ev_tag == EvType.INT)
ok("SQL name → text",       row.get("name").ev_text == "Alice")
ok("SQL score → real",      row.get("score").ev_tag == EvType.REAL)
ok("SQL id value",          row.get("id").ev_int == 1)

elem = lift_html_element("h1", {"class":"header", "id":"title"})
ok("HTML is record",        elem.ev_tag == EvType.RECORD)
ok("HTML tag field",        elem.get("tag").ev_text == "h1")
ok("HTML attrs is record",  elem.get("attrs").ev_tag == EvType.RECORD)
ok("HTML class attr",       elem.get("attrs").get("class").ev_text == "header")
ok("HTML children is list", elem.get("children").ev_tag == EvType.LIST)

ok("Python int",    lift_python(42).ev_int == 42)
ok("Python float",  lift_python(3.14).ev_tag == EvType.REAL)
ok("Python bool",   lift_python(True).ev_bool is True)
ok("Python str",    lift_python("hi").ev_text == "hi")
ok("Python bytes",  lift_python(b"\x00").ev_blob == b"\x00")
ok("Python list",   lift_python([1,2,3]).ev_tag == EvType.LIST)
ok("Python dict",   lift_python({"a":1}).ev_tag == EvType.RECORD)
ok("Python None",   lift_python(None).ev_tag == EvType.VOID)
ok("Python nested", lift_python([1,{"a":2}]).get(1).ev_tag == EvType.RECORD)

print("\n.native — back to Python values")
ok("int native",    EValue.from_int(5).native == 5)
ok("text native",   EValue.from_text("x").native == "x")
ok("list native",   lift_python([1,2]).native == [1,2])
ok("record native", lift_python({"k":"v"}).native == {"k":"v"})
ok("void native",   EValue.void().native is None)

print("\n.describe — teaching layer integration")
ok("void describe",   EValue.void().describe() == "nothing")
ok("bool describe",   EValue.from_bool(True).describe() == "true")
ok("int describe",    EValue.from_int(42).describe() == "42")
ok("text describe",   EValue.from_text("Codric").describe() == '"Codric"')
ok("list describe",   "list" in lst.describe())
ok("record describe", "name" in rec.describe())

print(f"\n=== EValue Python: {passed} passed, {failed} failed ===\n")
raise SystemExit(0 if failed == 0 else 1)
