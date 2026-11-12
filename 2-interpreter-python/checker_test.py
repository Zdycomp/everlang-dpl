#!/usr/bin/env python3
"""checker_test.py — Layer 2, the polyglot checker's own suite.

checker.py is 716 lines and had no direct test of its own. That is how
an accidental editor edit split the C++ marker tuple into

    "vector<", "" "   " "" "cout"

which adjacent-string-literal concatenation collapses to the single
marker "   cout". Every suite stayed green while C++ that carried
`cout` and nothing else was classified as C.

detect() is the first decision the whole layer makes — every inspector
downstream is chosen by it — so it is the thing most worth pinning.
"""

from checker import (ELang, detect, classify, Translator, E_CERTAIN,
                     DEFECT_UNBOUND, DEFECT_UNBOUNDED, DEFECT_MISBOUND,
                     DEFECT_OVERBOUND, DEFECT_ORPHANED)

passed = failed = 0


def ok(name, cond):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✓ {name}")
    else:
        failed += 1
        print(f"  ✗ {name}")


print("\nLanguage detection — one sample per supported language")

CASES = [
    ("C, with include",   ELang.C,
     '#include <stdio.h>\nint main(void){ printf("hi"); return 0; }'),
    ("C, bare function",  ELang.C,
     'int add(int a, int b) {\n    return a + b;\n}'),
    ("C++ via iostream",  ELang.CPP,
     '#include <iostream>\nint main(){ std::cout << "hi"; }'),
    ("C++ via vector<",   ELang.CPP,
     '#include <vector>\nstd::vector<int> v;'),
    ("C++ via namespace", ELang.CPP,
     '#include "x.h"\nusing namespace std;\nint main(){ cout << 1; }'),
    ("C++ via class",     ELang.CPP,
     '#include <cstdio>\nclass Foo { int x; };'),
    ("Python",            ELang.PYTHON, 'def f(x):\n    return x + 1'),
    ("Ruby",              ELang.RUBY,
     'def greet(name)\n  puts "hi #{name}"\nend'),
    ("SQL",               ELang.SQL,
     'SELECT id, name FROM users WHERE active = 1;'),
    ("Java",              ELang.JAVA,
     'public class Main {\n  public static void main(String[] a) {}\n}'),
    ("HTML",              ELang.HTML,
     '<!DOCTYPE html>\n<html><body><p>hi</p></body></html>'),
    ("Ever",              ELang.EVER, 'let a = 1\never b = a + 2\nshow b'),
]

for label, want, src in CASES:
    ok(f"{label} → {want.name}", detect(src) is want)

print("\nThe regression: `cout` alone must still say C++")
# The marker existed precisely for translation units that pull a
# catch-all header and use an unqualified `cout`. With the tuple split,
# the marker became "   cout" and this came back as C.
ok("#include + bare cout → CPP",
   detect('#include <bits/stdc++.h>\nint main(){ cout << "hi"; }') is ELang.CPP)
ok("cout marker is intact, not space-padded",
   detect('#include <x.h>\nint f(){cout<<1;}') is ELang.CPP)
ok("an include with no C++ marker is still C",
   detect('#include <stdio.h>\nint f(void){ return 0; }') is ELang.C)

print("\ndetect() is total — it always returns an ELang, never raises")
for odd in ("", "   ", "\n\n", "\x00", "}{)(", "#include", "select",
            "é✓\U0001F3AF", "a" * 10000):
    try:
        ok(f"detect({odd[:14]!r}) returns an ELang",
           isinstance(detect(odd), ELang))
    except Exception as exc:
        ok(f"detect({odd[:14]!r}) raised {type(exc).__name__}", False)

print("\nclassify() lands every finding in one of the five buckets")
BUCKETS = {DEFECT_UNBOUND, DEFECT_UNBOUNDED, DEFECT_MISBOUND,
           DEFECT_OVERBOUND, DEFECT_ORPHANED}
for msg in ("unreachable code after return",
            "variable used before assignment",
            "loop has no exit condition",
            "result discarded",
            "something nobody has ever said",
            ""):
    ok(f"classify({msg[:28]!r}) ∈ the five buckets",
       classify(msg) in BUCKETS)

print("\nTranslator runs each language end to end and yields a particle")
for label, want, src in CASES:
    try:
        t = Translator().translate(src, ident=label)
        ok(f"translate: {label} yields a particle", t.particle is not None)
        ok(f"translate: {label} agrees with detect()", t.lang is want)
        ok(f"translate: {label} confidence on scale",
           0 <= t.particle.confidence <= E_CERTAIN)
        ok(f"translate: {label} report() renders", isinstance(t.report(), str))
    except Exception as exc:
        ok(f"translate: {label} raised {type(exc).__name__}: {exc}", False)

print("\nThe two layer-2 detectors must agree with each other")
# checker.py and 2-inspect-python/translate.py are 94% the same file:
# two copies of detect() with no test comparing them. When the C++
# marker tuple was split in checker.py, translate.py still had the
# intact copy — the layers silently disagreed and nothing noticed.
# Pin them together so the next drift is loud.
import importlib.util as _ilu
import os as _os

_here = _os.path.dirname(_os.path.abspath(__file__))
_tp = _os.path.join(_here, "..", "2-inspect-python", "translate.py")
_spec = _ilu.spec_from_file_location("_translate_peer", _tp)
_peer = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_peer)

for label, _want, src in CASES:
    ok(f"checker and translate agree on {label}",
       detect(src).name == _peer.detect(src).name)
ok("checker and translate agree on bare cout",
   detect('#include <bits/stdc++.h>\nint main(){ cout << 1; }').name
   == _peer.detect('#include <bits/stdc++.h>\nint main(){ cout << 1; }').name)

print(f"\n=== Layer 2 (checker): {passed} passed, {failed} failed ===\n")
raise SystemExit(0 if failed == 0 else 1)
