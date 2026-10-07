#!/usr/bin/env python3
"""
test_backends.py — every transpiler target must agree with Ever.

Compiles each integration program to Go, Rust, R, and Kotlin, runs the
result, and diffs it against what Ever itself produced. A backend that
merely compiles proves nothing; a backend that computes 88 where Ever
says z has broken the one guarantee the language makes.

Targets whose toolchain isn't installed are skipped and reported as
skipped — never as passing.
"""

import os, re, shutil, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "2-interpreter-python"))

from runtime import run_source
from emit import emit, BACKENDS

KOTLIN_BIN = "/tmp/kotlinc/bin"
if os.path.isdir(KOTLIN_BIN):
    os.environ["PATH"] = os.environ["PATH"] + ":" + KOTLIN_BIN


def have(cmd):
    return shutil.which(cmd) is not None

TOOLS = {
    "go":     ("go",      lambda: have("go")),
    "rust":   ("rustc",   lambda: have("rustc")),
    "r":      ("Rscript", lambda: have("Rscript")),
    "kotlin": ("kotlinc", lambda: have("kotlinc") and have("java")),
    "js":     ("node",    lambda: have("node")),
}


def run_target(target, code, tmp):
    """Compile+run emitted code, return stdout lines."""
    ext = BACKENDS[target].ext
    src = os.path.join(tmp, f"prog.{ext}")
    with open(src, "w") as f:
        f.write(code)

    if target == "go":
        r = subprocess.run(["go", "run", src], capture_output=True,
                           text=True, timeout=180)
    elif target == "rust":
        exe = os.path.join(tmp, "prog")
        c = subprocess.run(["rustc", "-O", "-o", exe, src],
                           capture_output=True, text=True, timeout=240)
        if c.returncode:
            return None, c.stderr[:300]
        r = subprocess.run([exe], capture_output=True, text=True, timeout=120)
    elif target == "r":
        r = subprocess.run(["Rscript", src], capture_output=True,
                           text=True, timeout=180)
    elif target == "kotlin":
        jar = os.path.join(tmp, "prog.jar")
        c = subprocess.run(["kotlinc", src, "-include-runtime", "-d", jar],
                           capture_output=True, text=True, timeout=600)
        if c.returncode:
            return None, c.stderr[:300]
        r = subprocess.run(["java", "-jar", jar], capture_output=True,
                           text=True, timeout=180)
    elif target == "js":
        r = subprocess.run(["node", src], capture_output=True,
                           text=True, timeout=120)
    else:
        return None, "unknown target"

    if r.returncode:
        return None, r.stderr[:300]
    return [l.strip() for l in r.stdout.splitlines() if l.strip()], None


def norm(lines):
    return [re.sub(r"\s+", " ", l).strip() for l in lines]


def main():
    programs = sorted((ROOT / "tests" / "integration").glob("*.ever"))
    targets = [t for t in BACKENDS if TOOLS[t][1]()]
    skipped = [t for t in BACKENDS if not TOOLS[t][1]()]

    print(f"\n=== Backend agreement: {len(programs)} programs "
          f"x {len(targets)} targets ===\n")
    for t in skipped:
        print(f"  ~ SKIP {t} ({TOOLS[t][0]} not installed)")

    npass = nfail = 0
    for prog in programs:
        src = prog.read_text()
        ref = run_source(src)
        if not ref.ok:
            print(f"  ~ SKIP {prog.stem} (Ever itself errors)")
            continue
        expected = norm(ref.format_lines())

        for target in targets:
            try:
                code = emit(src, target)
            except NotImplementedError as e:
                print(f"  ~ SKIP {prog.stem:22} {target:7} ({e})")
                continue
            except Exception as e:
                print(f"  x FAIL {prog.stem:22} {target:7} emit: {e}")
                nfail += 1
                continue

            with tempfile.TemporaryDirectory() as tmp:
                got, err = run_target(target, code, tmp)

            if err:
                print(f"  x FAIL {prog.stem:22} {target:7} {err.splitlines()[0][:70]}")
                nfail += 1
                continue
            if norm(got) != expected:
                print(f"  x FAIL {prog.stem:22} {target:7} output differs")
                for g, e in zip(norm(got), expected):
                    if g != e:
                        print(f"        ever: {e}")
                        print(f"        {target:4}: {g}")
                        break
                nfail += 1
                continue
            print(f"  . OK   {prog.stem:22} {target}")
            npass += 1

    print(f"\n{'-'*54}")
    print(f"  {npass} passed  {nfail} failed"
          + (f"  ({len(skipped)} target(s) skipped)" if skipped else ""))
    print(f"{'-'*54}\n")
    return 0 if nfail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
