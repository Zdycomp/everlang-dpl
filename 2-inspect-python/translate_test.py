#!/usr/bin/env python3
"""translate_test.py — Ever Layer 2 verification."""

from translate import (
    Translator, detect, ELang, EState, EParticle,
    e_z, e_confident, e_certain, e_equivalence,
    E_CERTAIN, E_ZERO, E_PI_WIDTH_WARN, E_PI_WIDTH_ENUMERATE,
    E_EMULATE_CEILING,
)

passed = failed = 0

def ok(name, cond):
    global passed, failed
    if cond:
        passed += 1; print(f"  \u2713 {name}")
    else:
        failed += 1; print(f"  \u2717 {name}")

T = Translator()

print("\n=== Ever Layer 2 (Python) — the translator ===\n")

print("Constants agree with Layer 0")
ok("Certain is 256",           E_CERTAIN == 256)
ok("pi warn is 81",            E_PI_WIDTH_WARN == 81)
ok("pi squared is 25",         E_PI_WIDTH_ENUMERATE == 25)
ok("emulate ceiling is 3",     E_EMULATE_CEILING == 3)

print("\nLanguage detection")
ok("detects C",      detect('#include <stdio.h>\nint main(){return 0;}') == ELang.C)
ok("detects C++",    detect('#include <iostream>\nusing std::cout;') == ELang.CPP)
ok("detects Python", detect('def f(x: int) -> int:\n    return x') == ELang.PYTHON)
ok("detects Ruby",   detect('def greet\n  puts "hi"\nend') == ELang.RUBY)
ok("detects SQL",    detect('SELECT id, name FROM users WHERE id = ?') == ELang.SQL)
ok("detects Java",   detect('public class A { public static void main(String[] a){} }') == ELang.JAVA)
ok("detects HTML",   detect('<!DOCTYPE html>\n<html lang="en"></html>') == ELang.HTML)

print("\nC inspector")
c_bad = T.translate('int add(int x, int y) { return x + y }', "add.c", ELang.C)
ok("catches missing semicolon", any("semicolon" in e.message for e in c_bad.errors))
c_unsafe = T.translate('#include <stdio.h>\nint main(){ char b[8]; gets(b); return 0; }', "u.c", ELang.C)
ok("catches gets buffer overflow", any("gets" in e.message for e in c_unsafe.errors))
c_good = T.translate('#include <stdio.h>\nint main(void) {\n    return 0;\n}', "ok.c", ELang.C)
ok("clean C scores above 128", c_good.particle.confidence > 128)

print("\nC++ inspector")
cpp_leak = T.translate('#include <iostream>\nclass A {};\nint main(){ A* a = new A(); return 0; }', "l.cpp", ELang.CPP)
ok("catches new without delete", any("new without delete" in e.message for e in cpp_leak.errors))
cpp_virt = T.translate('#include <iostream>\nclass B { public: virtual void f(); };', "v.cpp", ELang.CPP)
ok("catches missing virtual dtor", any("virtual destructor" in e.message for e in cpp_virt.errors))
cpp_raii = T.translate('#include <memory>\nclass C {};\nint main(){ auto p = std::unique_ptr<C>(new C()); return 0; }', "r.cpp", ELang.CPP)
ok("rewards RAII", any("RAII" in p.message for p in cpp_raii.patterns))

print("\nPython inspector")
py_colon = T.translate('def broken(x)\n    return x', "b.py", ELang.PYTHON)
ok("catches missing colon", any("colon" in e.message for e in py_colon.errors))
py_mut = T.translate('def f(items=[]):\n    return items', "m.py", ELang.PYTHON)
ok("catches mutable default", any("mutable default" in e.message for e in py_mut.errors))
py_eval = T.translate('def run(s):\n    return eval(s)', "e.py", ELang.PYTHON)
ok("catches eval", any("eval" in e.message for e in py_eval.errors))
py_good = T.translate('def add(x: int, y: int) -> int:\n    return x + y', "g.py", ELang.PYTHON)
ok("typed python scores high", py_good.particle.confidence > 150)
ok("rewards annotations", any("annotated" in p.message for p in py_good.patterns))

print("\nRuby inspector")
rb_end = T.translate('def greet\n  puts "hi"', "e.rb", ELang.RUBY)
ok("catches missing end", any("missing end" in e.message for e in rb_end.errors))
rb_glob = T.translate('$count = 0\ndef bump\n  $count += 1\nend', "g.rb", ELang.RUBY)
ok("catches global variable", any("global" in e.message for e in rb_glob.errors))
rb_good = T.translate('class Point\n  attr_reader :x\n  def initialize(x)\n    @x = x.freeze\n  end\nend', "p.rb", ELang.RUBY)
ok("clean ruby scores above 128", rb_good.particle.confidence > 128)
ok("rewards attr_reader", any("accessor" in p.message for p in rb_good.patterns))

print("\nSQL inspector")
sql_del = T.translate('DELETE FROM users', "d.sql", ELang.SQL)
ok("catches DELETE without WHERE", any("without WHERE" in e.message for e in sql_del.errors))
sql_star = T.translate('SELECT * FROM accounts WHERE id = 1', "s.sql", ELang.SQL)
ok("catches SELECT star", any("SELECT *" in e.message for e in sql_star.errors))
sql_join = T.translate('SELECT a.id FROM a JOIN b', "j.sql", ELang.SQL)
ok("catches JOIN without ON", any("cartesian" in e.message for e in sql_join.errors))
sql_good = T.translate(
    'CREATE TABLE particle (\n  id INTEGER PRIMARY KEY,\n  confidence INTEGER NOT NULL\n);\n'
    'CREATE INDEX idx_conf ON particle(confidence);', "c.sql", ELang.SQL)
ok("clean SQL scores above 128", sql_good.particle.confidence > 128)
ok("rewards index", any("index" in p.message for p in sql_good.patterns))

print("\nJava inspector")
java_null = T.translate('public class A { void f(){ String s = null; s.length(); } }', "n.java", ELang.JAVA)
ok("catches unguarded null", any("null used without a guard" in e.message for e in java_null.errors))
java_eq = T.translate('public class B { boolean f(String s){ return s == "x"; } }', "q.java", ELang.JAVA)
ok("catches string ==", any("compared with ==" in e.message for e in java_eq.errors))
java_good = T.translate(
    'public class C {\n  private final int v;\n'
    '  public C(int v) { this.v = v; }\n'
    '  public void go() { try { work(); } catch (Exception e) { log(e); } }\n}', "c.java", ELang.JAVA)
ok("clean java scores above 128", java_good.particle.confidence > 128)
ok("rewards exception handling", any("exception handled" in p.message for p in java_good.patterns))

print("\nHTML inspector (hand written)")
html_img = T.translate('<img src="a.jpg">', "i.html", ELang.HTML)
ok("catches img without alt", any("without alt" in e.message for e in html_img.errors))
html_blank = T.translate('<a href="x" target="_blank">go</a>', "a.html", ELang.HTML)
ok("catches target blank no noopener", any("noopener" in e.message for e in html_blank.errors))
html_unclosed = T.translate('<div><p>text</div>', "u.html", ELang.HTML)
ok("catches unclosed tag", any("unclosed" in e.message for e in html_unclosed.errors))
html_good = T.translate(
    '<!DOCTYPE html>\n<html lang="en">\n<body>\n<main>\n'
    '<img src="a.jpg" alt="a">\n</main>\n</body>\n</html>', "g.html", ELang.HTML)
ok("clean html scores above 128", html_good.particle.confidence > 128)
ok("rewards semantic structure", any("semantic" in p.message for p in html_good.patterns))

print("\nEmulate ceiling")
wreck = T.translate(
    'SELECT * FROM a JOIN b;\nDELETE FROM c;\nDROP TABLE d;\nUPDATE e SET x=1;', "w.sql", ELang.SQL)
ok("beyond ceiling returns to Z", wreck.particle.state == EState.Z)
ok("Z carries its reason", "ceiling" in wreck.particle.reason)
ok("Z is not cleared", not wreck.particle.is_cleared)
ok("Z cannot execute", not wreck.particle.can_execute)

three = T.translate('int f(){ char b[4]; gets(b); return 0 }', "t.c", ELang.C)
ok("within ceiling stays emulatable", three.emulatable or three.error_distance <= E_EMULATE_CEILING)

print("\nParticle semantics")
z = e_z("ocr", "not run")
ok("Z confidence zero", z.confidence == 0)
ok("Z not cleared", not z.is_cleared)
cert = e_certain("verified", ELang.C)
ok("Certain is 256", cert.confidence == E_CERTAIN)
ok("Certain can execute", cert.can_execute)
ok("degree over 256 becomes Certain", e_confident("x", 300, ELang.C).state == EState.CERTAIN)
ok("degree under 1 becomes Z", e_confident("x", 0, ELang.C).state == EState.Z)
ok("nothing static reaches Certain", py_good.particle.confidence < E_CERTAIN)

print("\nEquivalence and pi")
narrow = e_equivalence("sev", 100, 115, ELang.RUBY)
ok("width computed", narrow.width == 15)
ok("width 15 acceptable", narrow.pi_status() == "ACCEPTABLE")
ok("width 26 enumerate", e_equivalence("s", 100, 126, ELang.RUBY).pi_status() == "ENUMERATE")
ok("width 150 approaching Z", e_equivalence("s", 50, 200, ELang.RUBY).pi_status() == "APPROACHING_Z")
ok("reversed bounds corrected", e_equivalence("s", 200, 50, ELang.RUBY).lo == 50)

print("\nSerialization round trip with Layer 0 format")
p = e_confident("parsed_amount", 180, ELang.PYTHON)
line = p.serialize()
back = EParticle.deserialize(line)
ok("twelve fields emitted", len(line.split("|")) == 12)
ok("confidence survives", back.confidence == 180)
ok("ident survives", back.ident == "parsed_amount")
ok("lang survives", back.lang == ELang.PYTHON)
ok("state survives", back.state == EState.CONFIDENT)

print(f"\n=== Layer 2: {passed} passed, {failed} failed ===\n")
raise SystemExit(0 if failed == 0 else 1)
