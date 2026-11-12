#!/usr/bin/env python3
"""translate_test.py — Ever Layer 2 verification."""

from translate import (
    Translator, detect, ELang, EState, EParticle,
    e_z, e_confident, e_certain, e_equivalence,
    E_CERTAIN, E_ZERO, E_PI_WIDTH_WARN, E_PI_WIDTH_ENUMERATE,
    E_EMULATE_CEILING,
)
from language_support import ExtendedLanguage
from pathlib import Path

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

X = ExtendedLanguage

print("\nExtended language detection")
ok("detects bare SELECT statement", detect("SELECT NOW();") == ELang.SQL)
ok("detects Dockerfile", detect("FROM alpine\nRUN echo hi") == X.DOCKERFILE)
ok("detects C#", detect("using System;\npublic class P {\n  public static void Main() { Console.WriteLine(1); }\n}") == X.CSHARP)
ok("detects Clojure", detect("(ns my.app)\n(defn f [x] x)") == X.CLOJURE)
ok("detects CSS", detect("p { color: red !important; }") == X.CSS)
ok("detects Dart", detect("import 'dart:async';\nFuture<void> run() async {}") == X.DART)
ok("detects Elixir", detect("defmodule M do\n  def f, do: 1\nend") == X.ELIXIR)
ok("detects Emacs Lisp", detect("(defun f (x) (* x 2))") == X.EMACS_LISP)
ok("detects Haskell", detect("module Main where\nmain = print 1") == X.HASKELL)
ok("detects JavaScript", detect("function f(x) {\n  return x;\n}") == X.JAVASCRIPT)
ok("detects Kotlin", detect("fun main() {\n  println(1)\n}") == X.KOTLIN)
ok("detects MATLAB", detect("%% run\nfunction y = f(x)\n  y = 2*x;\nend\n") == X.MATLAB)
ok("detects Perl", detect("my $x = 5;\nprint $x;") == X.PERL)
ok("detects PHP", detect("<?php\necho 1;") == X.PHP)
ok("detects PowerShell", detect("Write-Host $name") == X.POWERSHELL)
ok("detects Swift", detect("func f() -> Int {\n  return 1\n}") == X.SWIFT)
ok("detects TeX", detect("\\documentclass{article}\n\\begin{document}\nHi\n\\end{document}") == X.TEX)
ok("detects Vue", detect('<template><p v-if="ok">hi</p></template>') == X.VUE)

print("\nEver source is never claimed by a foreign detector")
EVER_PROGRAMS = [
    "let x = 5",
    "let x = 5;",
    "let our = 2",
    "let x = 5\n# my answer is 5",
    "let nsteps = 10\nshow nsteps",
    "let defnames = 2\nshow defnames",
    "let ns = 3\nshow ns",
    "let namespace = 3\nshow namespace",
    "let total = 4\n# data rate = 5 percent",
    "let total = 5\nshow costs $total",
    "def param(x) = x * 2\nlet y = param(3)\nshow y",
    "let x = 5\n# using a fixed rate;",
    "let ADD = 2\nADD * 3",
    "let select = 1\nshow select",
    "let x = 5  # done; move on",
    "let x = 5\n# const x = 1 is old",
    "let x = 5 # the end of it",
    "my cat is fat",
]
for src in EVER_PROGRAMS:
    ok(f"stays Ever: {src[:32]!r}", detect(src) == ELang.EVER)

ROOT = Path(__file__).resolve().parent.parent
corpus = sorted(p for d in ("examples", "tests/gold_suite")
                for p in (ROOT / d).rglob("*.ever") if "node_modules" not in p.parts)
ok(f"corpus is present ({len(corpus)} .ever files)", len(corpus) > 0)
stray = [p.name for p in corpus if detect(p.read_text(encoding="utf-8")) != ELang.EVER]
ok("every shipped .ever file detects as EVER", not stray)

print("\nNo inspector for Ever source")
ever = T.translate("let x = 5", "e.ever")
ok("Ever source is Z", ever.particle.state == EState.Z)
ok("Ever Z names its language", "no inspector for EVER" in ever.particle.reason)
ok("empty input is Z", T.translate("").particle.state == EState.Z)
ok("explicit EVER is Z", T.translate("let x = 5", lang=ELang.EVER).particle.state == EState.Z)
ok("Ever report renders", isinstance(ever.report(), str))

print("\nExtended languages translate and report")
perl = T.translate("my $x = 5;\nprint $x;", "p.pl")
ok("Perl report names the language", "language   : Perl" in perl.report())
ok("prose translates to Z", T.translate("my cat is fat").particle.state == EState.Z)
ok("JavaScript eval is an error", any("eval" in e.message for e in
   T.translate("function f(x) { return eval(x); }", lang=X.JAVASCRIPT).errors))
ok("JavaScript eval is not executable", not T.translate(
   "function f(x) { return eval(x); }", lang=X.JAVASCRIPT).particle.can_execute)
ok("explicit LUA dispatch reports loadstring", any("dynamic code loading" in e.message for e in
   T.translate("local x = 5\nloadstring(s)()", lang=X.LUA).errors))
ok("extended particle repr renders", isinstance(repr(e_confident("x", 100, X.PERL)), str))

print("\nLanguage value spaces")
ok("ELang and ExtendedLanguage values are disjoint",
   not ({int(m) for m in ELang} & {int(m) for m in X}))

print("\nInspector regressions")
fk = T.translate("CREATE TABLE c (id INTEGER PRIMARY KEY, p INTEGER REFERENCES parent(id) "
                 "ON UPDATE CASCADE);", "fk.sql", ELang.SQL)
ok("ON UPDATE CASCADE is not an UPDATE without WHERE", not any("without WHERE" in e.message for e in fk.errors))
ok("real UPDATE without WHERE is flagged", any("without WHERE" in e.message for e in
   T.translate("UPDATE t SET x = 1", "u.sql", ELang.SQL).errors))
leak = T.translate('#include <stdlib.h>\nint main(void) {\n  char *p = malloc(4);\n'
                   '  return 0;\n} // free later\n', "leak.c", ELang.C)
ok("free in a comment does not hide a leak", any("malloc" in e.message for e in leak.errors))
paired = T.translate('#include <stdlib.h>\nint main(void) {\n  char *p = malloc(4);\n'
                     '  free(p);\n  return 0;\n}', "paired.c", ELang.C)
ok("paired free clears the leak check", not any("malloc" in e.message for e in paired.errors))
html_slash = T.translate("<div class='a/b'>hello", "s.html", ELang.HTML)
ok("slash inside an attribute still reports unclosed tag", any("unclosed <div>" in e.message
   for e in html_slash.errors))
html_br = T.translate("<p>one<br />two</p>", "b.html", ELang.HTML)
ok("self-closing br is not unclosed", not any("unclosed" in e.message for e in html_br.errors))

print(f"\n=== Layer 2: {passed} passed, {failed} failed ===\n")
raise SystemExit(0 if failed == 0 else 1)
