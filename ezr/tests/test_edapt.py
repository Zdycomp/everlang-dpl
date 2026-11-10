#!/usr/bin/env python3
"""
test_edapt.py — every Edapt fixer proven against the real toolchain.

A "before" that genuinely fails to compile/run, and an "after" that
genuinely does — for each of the five languages Edapt supports. No
claim in fixers.py counts until it passes here.
"""

import os, shutil, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))

from edapt.fixers import fix, diagnose_brackets, detect_language

KOTLIN_BIN = "/tmp/kotlinc/bin"
if os.path.isdir(KOTLIN_BIN):
    os.environ["PATH"] += ":" + KOTLIN_BIN

_pass = _fail = 0
def ok(name, cond, detail=""):
    global _pass, _fail
    if cond: _pass += 1
    else:
        _fail += 1
        print(f"  x {name}" + (f"\n      {detail}" if detail else ""))


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True,
                          timeout=kw.pop("timeout", 60), **kw)


def compiles_python(src, tmp):
    p = os.path.join(tmp, "t.py")
    open(p, "w").write(src)
    r = run([sys.executable, "-c", f"compile(open({p!r}).read(), {p!r}, 'exec')"])
    return r.returncode == 0, r.stderr

def runs_python(src, tmp):
    p = os.path.join(tmp, "t.py")
    open(p, "w").write(src)
    r = run([sys.executable, p])
    return r.returncode == 0, r.stdout + r.stderr

def runs_node(src, tmp):
    p = os.path.join(tmp, "t.js")
    open(p, "w").write(src)
    r = run(["node", p])
    return r.returncode == 0, r.stdout + r.stderr

def runs_go(src, tmp):
    p = os.path.join(tmp, "t.go")
    open(p, "w").write(src)
    r = run(["go", "run", p], timeout=120)
    return r.returncode == 0, r.stdout + r.stderr

def compiles_rust(src, tmp):
    p = os.path.join(tmp, "t.rs")
    exe = os.path.join(tmp, "t")
    open(p, "w").write(src)
    r = run(["rustc", "-o", exe, p], timeout=180)
    return r.returncode == 0, r.stderr

def compiles_java(src, tmp, classname="T"):
    p = os.path.join(tmp, f"{classname}.java")
    open(p, "w").write(src)
    r = run(["javac", "-d", tmp, p], timeout=120)
    return r.returncode == 0, r.stderr


# ═══════════════════════════════════════════════
print("\n[python: missing colon]")
bad = "if x > 5\n    print('big')\n"
good_expect_fail = "def f(x):\n"  # sanity: compiles_python should catch real errors
with tempfile.TemporaryDirectory() as tmp:
    c0, _ = compiles_python(bad, tmp)
    ok("broken program genuinely fails to compile", c0 is False)
    result = fix(bad, "python")
    ok("fixer reports exactly one fix", len(result.fixes) == 1,
       str(result.fixes))
    c1, err1 = compiles_python(result.code, tmp)
    ok("healed program compiles", c1, err1)
    print("   ", result.fixes[0].line1())

print("\n[python: = vs == in if]")
bad = "x = 5\nif x = 5:\n    print('five')\n"
with tempfile.TemporaryDirectory() as tmp:
    c0, _ = compiles_python(bad, tmp)
    ok("broken program fails", c0 is False)
    result = fix(bad, "python")
    ok("exactly one fix reported", len(result.fixes) == 1, str(result.fixes))
    c1, err1 = compiles_python(result.code, tmp)
    ok("healed program compiles", c1, err1)
    r, out = runs_python(result.code, tmp)
    ok("healed program runs and prints correctly", r and "five" in out, out)

print("\n[python: def missing colon, multi-issue file]")
bad = "def greet(name)\n    print('hi ' + name)\n\ngreet('Rick')\n"
with tempfile.TemporaryDirectory() as tmp:
    result = fix(bad, "python")
    ok("fix found", len(result.fixes) >= 1)
    c1, err1 = compiles_python(result.code, tmp)
    ok("healed program compiles", c1, err1)
    r, out = runs_python(result.code, tmp)
    ok("healed program runs correctly", r and "hi Rick" in out, out)

print("\n[python: does NOT touch valid keyword-argument =]")
clean = "def f(x=1, y=2):\n    return x + y\n\nprint(f(x=3))\n"
with tempfile.TemporaryDirectory() as tmp:
    result = fix(clean, "python")
    ok("kwarg default = untouched", len(result.fixes) == 0, str(result.fixes))
    c0, _ = compiles_python(clean, tmp)
    ok("original already compiled (sanity)", c0)


# ═══════════════════════════════════════════════
print("\n[javascript: semicolon-free code is left alone]")
clean = "let x = 5\nlet y = 10\nconsole.log(x + y)\n"
with tempfile.TemporaryDirectory() as tmp:
    r0, out0 = runs_node(clean, tmp)
    ok("original runs via ASI (sanity)", r0 and "15" in out0, out0)
    result = fix(clean, "javascript")
    ok("nothing is appended to a file written without semicolons",
       result.code == clean and not result.fixes, str(result.fixes))

print("\n[javascript: a missing semicolon in a file that uses them]")
bad = "let x = 5;\nlet y = 10\nconsole.log(x + y);\n"
with tempfile.TemporaryDirectory() as tmp:
    result = fix(bad, "javascript")
    ok("exactly the one missing terminator is found",
       [f.line for f in result.fixes] == [2], str(result.fixes))
    r1, out1 = runs_node(result.code, tmp)
    ok("healed program still runs and computes correctly",
       r1 and "15" in out1, out1)

print("\n[javascript: genuinely broken without ASI rescue]")
bad = ("let arr = [1, 2, 3]\n"
      "(function() { console.log('boom') })()\n")
with tempfile.TemporaryDirectory() as tmp:
    r0, out0 = runs_node(bad, tmp)
    ok("this shape genuinely fails without a semicolon", r0 is False, out0)
    result = fix(bad, "javascript")
    ok("only the swallowed line is healed",
       [f.line for f in result.fixes] == [1], str(result.fixes))
    r1, out1 = runs_node(result.code, tmp)
    ok("healed version runs", r1, out1)


# ═══════════════════════════════════════════════
print("\n[go: bracket diagnosis, not silent guess]")
bad = "package main\n\nimport \"fmt\"\n\nfunc main() {\n\tfmt.Println(\"hi\"\n}\n"
problems = diagnose_brackets(bad, "go")
ok("unclosed paren is reported", any("never closed" in p for p in problems),
   str(problems))
with tempfile.TemporaryDirectory() as tmp:
    result = fix(bad, "go")
    ok("go fixer does not guess a closing paren (reports, doesn't invent)",
       result.code == bad)


# ═══════════════════════════════════════════════
print("\n[rust: missing semicolon]")
bad = ('fn main() {\n'
      '    let x = 5\n'
      '    let y = 10;\n'
      '    println!("{}", x + y);\n'
      '}\n')
with tempfile.TemporaryDirectory() as tmp:
    c0, _ = compiles_rust(bad, tmp)
    ok("broken program fails to compile", c0 is False)
    result = fix(bad, "rust")
    ok("fixer found the missing semicolon", len(result.fixes) >= 1,
       str(result.fixes))
    c1, err1 = compiles_rust(result.code, tmp)
    ok("healed program compiles", c1, err1)


# ═══════════════════════════════════════════════
print("\n[java: missing semicolon]")
bad = ('public class T {\n'
      '    public static void main(String[] args) {\n'
      '        int x = 5\n'
      '        int y = 10;\n'
      '        System.out.println(x + y);\n'
      '    }\n'
      '}\n')
with tempfile.TemporaryDirectory() as tmp:
    c0, _ = compiles_java(bad, tmp)
    ok("broken program fails to compile", c0 is False)
    result = fix(bad, "java")
    ok("fixer found the missing semicolon", len(result.fixes) >= 1,
       str(result.fixes))
    c1, err1 = compiles_java(result.code, tmp)
    ok("healed program compiles", c1, err1)


# ═══════════════════════════════════════════════
# Valid code must come back untouched. Each case below is a shape real
# code uses that an earlier fixer edited, broke or refused
# (found by everlang_standalone/tests/heal_bench.py).
print("\n[no false positives on valid code]")
VALID = {
    "python": [
        ("docstring line starting with a keyword",
         'def f():\n    """Fill\n    for missing values.\n    if not simplified\n    """\n    return 1\n'),
        ("one-line if body", "for x in range(3):\n    if not x: continue\n    print(x)\n"),
        ("trailing comment after the colon", 'if __name__ == "__main__":  # entry\n    pass\n'),
        ("comprehension spread over lines",
         "xs = [a\n      for a in range(9)\n      if a % 2]\n"),
        ("keyword argument in a condition", "def f(x=0):\n    return x\nif f(x=1):\n    pass\n"),
        ("brackets and = inside strings", 'if x == ")=(":\n    y = "]"\n' .replace("if x", "x = 1\nif x")),
    ],
    "javascript": [
        ("object literal", "const o = {\n  a: f(1),\n  has16m: level >= 3\n};\n"),
        ("chained call", "const r = fetch(u)\n  .then(x => x.json());\n"),
        ("regex and template with brackets",
         "const a = s.replace(/[\"'(]/g, `\\\\'`);\nconst b = `x ${ `y(` } z`;\n"),
        ("statement ending on an operator word", "var d = new\nFoo();\n"),
    ],
    "rust": [
        ("attribute", '#![doc(html_root_url = "https://docs.rs/x")]\nfn main() {}\n'),
        ("tail expression is the block value", "fn f() -> u32 {\n    g()\n}\n"),
        ("string continued over lines", 'const S: &str = "\\\nf failed";\n'),
        ("struct literal and match arm",
         "fn f() -> P {\n    match 1 {\n        _ => g()\n    };\n    P {\n        a: 1,\n        b: h(2)\n    }\n}\n"),
    ],
    "java": [
        ("statement spread over lines",
         'class T {\n    void f() {\n        System.out.println("T=" + g()\n                + 1);\n        boolean m = a == b\n                && c;\n    }\n}\n'),
        ("trailing comment after the semicolon", "class T {\n    int x = f();  // extra safe\n}\n"),
        ("text block", 'class T {\n    String s = """\n        VALUES (1, \'a\')\n        x = y(\n        """;\n}\n'),
    ],
    "go": [("rune and raw string holding brackets", "package main\nvar a = '('\nvar b = `)}`\n")],
    "kotlin": [("line separator inside a string", 'val s = "a b\u0085c"\n')],
}
for lang, cases in VALID.items():
    for name, src in cases:
        result = fix(src, lang)
        ok(f"{lang}: {name} untouched", result.code == src and not result.fixes,
           str([f.line1() for f in result.fixes]))
        ok(f"{lang}: {name} not refused", diagnose_brackets(src, lang) == [],
           str(diagnose_brackets(src, lang)))

print("\n[fixes land ahead of a trailing comment]")
result = fix("if x > 5  # big\n    pass\n", "python")
ok("python colon goes before the comment", result.code.startswith("if x > 5:  # big"), result.code)
result = fix("class T {\n    int x = 5  // five\n}\n", "java")
ok("java semicolon goes before the comment", "int x = 5;  // five" in result.code, result.code)

print("\n[unterminated string: reported, never edited (SEMANTICS 9.4)]")
for lang, src in (("python", 'if keep == "last:\n    pass\n'),
                  ("javascript", 'var res = ", lastI = 0\n')):
    ok(f"{lang}: reported", any("never closed" in p for p in diagnose_brackets(src, lang)))
    ok(f"{lang}: left alone", fix(src, lang).code == src)


# ═══════════════════════════════════════════════
print("\n[language detection]")
ok("detects .py",  detect_language("foo.py")  == "python")
ok("detects .js",  detect_language("foo.js")  == "javascript")
ok("detects .go",  detect_language("foo.go")  == "go")
ok("detects .rs",  detect_language("foo.rs")  == "rust")
ok("detects .java",detect_language("foo.java")== "java")
ok("detects .kt",  detect_language("foo.kt")  == "kotlin")
ok("unknown ext returns None", detect_language("foo.xyz") is None)


print(f"\n{'='*54}")
print(f"=== Edapt: {_pass} passed, {_fail} failed ===")
print(f"{'='*54}\n")
sys.exit(0 if _fail == 0 else 1)
