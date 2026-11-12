#!/usr/bin/env python3
"""
test_edapt.py — every Edapt fixer proven against the real toolchain.

A "before" that genuinely fails to compile/run, and an "after" that
genuinely does — for each language Edapt supports. A valid program that
merely looks like a mistake must come back unchanged. A section whose
toolchain is missing reports SKIP and never PASS; the run exits 77 when
anything was skipped.
"""

import os, shutil, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from edapt.fixers import fix, diagnose_brackets, detect_language

SKIP_EXIT = 77
_pass = _fail = _skip = 0


def ok(name, cond, detail=""):
    global _pass, _fail
    if cond:
        _pass += 1
    else:
        _fail += 1
        print(f"  x {name}" + (f"\n      {detail}" if detail else ""))


def skip(name, why):
    global _skip
    _skip += 1
    print(f"  ~ SKIP: {name} — {why}")


def have(*tools):
    return all(shutil.which(t) for t in tools)


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


def python_section():
    print("\n[python: missing colon]")
    bad = "if x > 5\n    print('big')\n"
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

    print("\n[python: = vs == with a trailing comment]")
    bad = "x = 5\nif x = 5:  # set\n    print('five')\n"
    with tempfile.TemporaryDirectory() as tmp:
        result = fix(bad, "python")
        ok("the comment is kept and the = is fixed",
           result.code == "x = 5\nif x == 5:  # set\n    print('five')\n",
           repr(result.code))
        r, out = runs_python(result.code, tmp)
        ok("healed program runs and prints correctly", r and "five" in out, out)

    print("\n[python: = inside grouping parens]")
    bad = "x = 5\nif (x = 5):\n    print('paren')\n"
    with tempfile.TemporaryDirectory() as tmp:
        result = fix(bad, "python")
        ok("one fix in the grouped condition", len(result.fixes) == 1,
           str(result.fixes))
        r, out = runs_python(result.code, tmp)
        ok("healed program runs and prints correctly", r and "paren" in out, out)

    print("\n[python: def missing colon, multi-issue file]")
    bad = "def greet(name)\n    print('hi ' + name)\n\ngreet('Rick')\n"
    with tempfile.TemporaryDirectory() as tmp:
        result = fix(bad, "python")
        ok("fix found", len(result.fixes) >= 1)
        c1, err1 = compiles_python(result.code, tmp)
        ok("healed program compiles", c1, err1)
        r, out = runs_python(result.code, tmp)
        ok("healed program runs correctly", r and "hi Rick" in out, out)

    print("\n[python: does NOT touch valid code that looks like a mistake]")
    valid = {
        "kwarg default": "def f(x=1, y=2):\n    return x + y\n\nprint(f(x=3))\n",
        "kwarg in condition":
            "def f(x=1):\n    return x\n\nif f(x=3):\n    print('three')\n",
        "one-line compound statement":
            "x = 1\nif x: print('one')\n",
        "continuation for in a comprehension":
            "xs = [\n    x\n    for x in range(3)\n]\nprint(xs)\n",
        "string literal containing ==":
            "msg = 'a=b'\nif msg == 'a=b':\n    print('same')\n",
        "header with a trailing comment":
            "x = 1\nif x:  # check\n    print('x')\n",
        "docstring line beginning with a keyword":
            'def f():\n    """\nwhile the loop runs, for each item\n    """\n'
            '    return 1\n\nprint(f())\n',
        "lambda default inside grouping parens":
            "if (lambda x=1: x)():\n    print('yes')\n",
    }
    for name, src in valid.items():
        with tempfile.TemporaryDirectory() as tmp:
            result = fix(src, "python")
            ok(f"{name}: no fix reported", len(result.fixes) == 0,
               str(result.fixes))
            ok(f"{name}: code unchanged", result.code == src, repr(result.code))
            c0, err0 = compiles_python(src, tmp)
            ok(f"{name}: original compiles (sanity)", c0, err0)


def bracket_section():
    print("\n[brackets: inside string literals is not structure]")
    ok("python: bracket in a string",
       diagnose_brackets('print("(")\n', "python") == [])
    ok("python: bracket in a multi-line docstring",
       diagnose_brackets('def f():\n    """\n    (\n    """\n    return 1\n',
                         "python") == [])
    ok("javascript: bracket in a string",
       diagnose_brackets('console.log("(")\n', "javascript") == [])
    ok("go: bracket in a string",
       diagnose_brackets('fmt.Println("(")\n', "go") == [])
    ok("unclosed bracket outside a string is still reported",
       any("never closed" in p
           for p in diagnose_brackets('print("(" + x(\n', "python")))


def javascript_section():
    print("\n[javascript: missing semicolons]")
    if not have("node"):
        skip("javascript section", "node not on PATH")
        return
    bad = "let x = 5\nlet y = 10\nconsole.log(x + y)\n"
    with tempfile.TemporaryDirectory() as tmp:
        r0, out0 = runs_node(bad, tmp)
        ok("original runs OK via ASI", r0 and "15" in out0, out0)
        result = fix(bad, "javascript")
        ok("fixer found the missing terminators", len(result.fixes) >= 2,
           str(result.fixes))
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
        r1, out1 = runs_node(result.code, tmp)
        ok("healed version runs", r1, out1)

    print("\n[javascript: leading-dot chain is one statement]")
    chain = ("const items = [1, 2]\n"
             "const total = items\n"
             "  .map(x => x * 2)\n"
             "console.log(total)\n")
    with tempfile.TemporaryDirectory() as tmp:
        r0, out0 = runs_node(chain, tmp)
        ok("original chain runs", r0 and "[ 2, 4 ]" in out0, out0)
        result = fix(chain, "javascript")
        ok("the items line still gets its semicolon",
           "const items = [1, 2];\n" in result.code, result.code)
        ok("the chained line is not split",
           "const total = items\n  .map(" in result.code, result.code)
        r1, out1 = runs_node(result.code, tmp)
        ok("healed chain runs and prints the same result",
           r1 and out1 == out0, out1)


def go_section():
    print("\n[go: bracket diagnosis, not silent guess]")
    bad = "package main\n\nimport \"fmt\"\n\nfunc main() {\n\tfmt.Println(\"hi\"\n}\n"
    problems = diagnose_brackets(bad, "go")
    ok("unclosed paren is reported", any("never closed" in p for p in problems),
       str(problems))
    result = fix(bad, "go")
    ok("go fixer does not guess a closing paren (reports, doesn't invent)",
       result.code == bad)


def rust_section():
    print("\n[rust: missing semicolon]")
    if not have("rustc"):
        skip("rust section", "rustc not on PATH")
        return
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


def java_section():
    print("\n[java: missing semicolon]")
    if not have("javac", "java"):
        skip("java section", "javac or java not on PATH")
        return
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

    print("\n[java: leading-dot chain is valid and untouched]")
    chain = ('public class T {\n'
             '    public static void main(String[] args) {\n'
             '        String s = new StringBuilder()\n'
             '            .append("ok")\n'
             '            .toString();\n'
             '        System.out.println(s);\n'
             '    }\n'
             '}\n')
    with tempfile.TemporaryDirectory() as tmp:
        c0, err0 = compiles_java(chain, tmp)
        ok("original chain compiles (sanity)", c0, err0)
        result = fix(chain, "java")
        ok("no fix reported for the valid chain", len(result.fixes) == 0,
           str(result.fixes))
        ok("chain code unchanged", result.code == chain, result.code)


def kotlin_section():
    print("\n[kotlin: no rewrite, no idiomatic semicolons]")
    kt = "fun main() {\n    println(\"hi\")\n}\n"
    ok("kotlin code unchanged", fix(kt, "kotlin").code == kt)


def cli_section():
    print("\n[cli: exit status reports what was left undone]")
    cli = [sys.executable, "-B", "-m", "edapt.cli"]
    with tempfile.TemporaryDirectory() as tmp:
        unclosed = os.path.join(tmp, "unclosed.js")
        open(unclosed, "w").write("foo(\n  1,\n")
        r = run(cli + [unclosed], cwd=str(ROOT))
        ok("unclosed bracket exits 1", r.returncode == 1, r.stdout + r.stderr)

        fixable = os.path.join(tmp, "fixable.py")
        open(fixable, "w").write("if x > 5\n    print('big')\n")
        r = run(cli + [fixable], cwd=str(ROOT))
        ok("fix not applied exits 1", r.returncode == 1, r.stdout + r.stderr)
        r = run(cli + [fixable, "--write"], cwd=str(ROOT))
        ok("fix applied with --write exits 0", r.returncode == 0,
           r.stdout + r.stderr)

        clean = os.path.join(tmp, "clean.py")
        open(clean, "w").write("print('clean')\n")
        r = run(cli + [clean], cwd=str(ROOT))
        ok("clean file exits 0", r.returncode == 0, r.stdout + r.stderr)


def detection_section():
    print("\n[language detection]")
    ok("detects .py",  detect_language("foo.py")  == "python")
    ok("detects .js",  detect_language("foo.js")  == "javascript")
    ok("detects .go",  detect_language("foo.go")  == "go")
    ok("detects .rs",  detect_language("foo.rs")  == "rust")
    ok("detects .java",detect_language("foo.java")== "java")
    ok("detects .kt",  detect_language("foo.kt")  == "kotlin")
    ok("unknown ext returns None", detect_language("foo.xyz") is None)


def main():
    python_section()
    bracket_section()
    javascript_section()
    go_section()
    rust_section()
    java_section()
    kotlin_section()
    cli_section()
    detection_section()

    print(f"\n{'='*54}")
    print(f"=== Edapt: {_pass} passed, {_fail} failed, {_skip} skipped ===")
    print(f"{'='*54}\n")
    if _fail:
        return 1
    return SKIP_EXIT if _skip else 0


if __name__ == "__main__":
    sys.exit(main())
