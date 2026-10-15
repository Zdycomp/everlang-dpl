#!/usr/bin/env python3
"""test_zeroth.py — the Zeroth Law, across every layer that states it.

Each layer already checks the law for itself. That is not enough. A law
that five layers each hold privately is five laws, and the whole point
of the Zeroth is that confidence means the same thing everywhere it
travels — so the check that matters is agreement.

This compiles the C atom, runs the Java runtime, loads the SQL archive
and imports the Python interpreter, asks all four for the band of every
confidence from 0 to 256, and refuses to pass unless all four agree on
all 257.

Layers whose toolchain is missing report SKIP. They never report PASS.
"""

import os
import subprocess
import sqlite3
import sys
import shutil
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "2-interpreter-python"))

from ever import e_band, excel, Band, E_CERTAIN     # noqa: E402

passed = failed = skipped = 0
SCALE = list(range(0, E_CERTAIN + 1))


def ok(name, cond):
    global passed, failed
    if cond:
        passed += 1; print(f"  ✓ {name}")
    else:
        failed += 1; print(f"  ✗ {name}")


def skip(name, why):
    global skipped
    skipped += 1
    print(f"  ∼ SKIP: {name} — {why}")


print("\n=== 4Ever — the Zeroth Law across the layers ===\n")

# ── Python, the reference ────────────────────────────────────────
print("Layer 2 · Python — the reference reading")
py = {c: e_band(c).name.upper() for c in SCALE}
ok("band is total on 0..256",   len(py) == 257)
ok("six distinct bands used",   len(set(py.values())) == 6)
ok("Z alone at 0",              [c for c in SCALE if py[c] == "Z"] == [0])
ok("Certain alone at 256",
   [c for c in SCALE if py[c] == "CERTAIN"] == [E_CERTAIN])

# ── The law itself, exhaustively ─────────────────────────────────
print("\nThe law: reflexive, symmetric, transitive")
ok("reflexive over all 257 values",
   all(py[a] == py[a] for a in SCALE))
ok("symmetric over all 66,049 pairs",
   all((py[a] == py[b]) == (py[b] == py[a]) for a in SCALE for b in SCALE))
ok("transitive over every triple",
   all(py[a] == py[c]
       for a in SCALE for b in SCALE if py[a] == py[b]
       for c in SCALE if py[b] == py[c]))

# The relation the law replaces. Measured, so the difference is a
# number rather than an opinion.
W = 81
near = lambda a, b: abs(a - b) < W
cand = sum(1 for a in SCALE for b in SCALE if near(a, b)
             for c in SCALE if near(b, c))
viol = sum(1 for a in SCALE for b in SCALE if near(a, b)
             for c in SCALE if near(b, c) and not near(a, c))
print(f"\n  proximity |a-b| < {W}: {viol:,} of {cand:,} triples break the chain"
      f"  ({100.0 * viol / cand:.1f}%)")
ok("proximity is reflexive",     all(near(a, a) for a in SCALE))
ok("proximity is symmetric",
   all(near(a, b) == near(b, a) for a in SCALE for b in SCALE))
ok("proximity is NOT transitive", viol > 0)
ok("so proximity cannot carry the law", viol == 969_840)

# ── Layer 0 · C ──────────────────────────────────────────────────
print("\nLayer 0 · C — the atom")
c_bands = None
if not shutil.which("cc") and not shutil.which("gcc"):
    skip("C atom", "no C toolchain")
else:
    tmp = tempfile.mkdtemp(prefix="zeroth_")
    src = os.path.join(tmp, "probe.c")
    with open(src, "w") as f:
        f.write('#include <stdio.h>\n#include "tapestry.h"\n'
                'int main(void){int c;for(c=0;c<=E_CERTAIN;c++)'
                'printf("%d %s\\n",c,e_band((int16_t)c));return 0;}\n'
                .replace('e_band((int16_t)c)',
                         'e_band_name(e_band((int16_t)c))'))
    exe = os.path.join(tmp, "probe")
    build = subprocess.run(
        ["cc", "-std=c99", "-I", os.path.join(ROOT, "0-atom-c"),
         src, os.path.join(ROOT, "0-atom-c", "tapestry.c"), "-o", exe, "-lm"],
        capture_output=True, text=True)
    if build.returncode != 0:
        ok("C probe builds", False)
        print(build.stderr[:400])
    else:
        out = subprocess.run([exe], capture_output=True, text=True).stdout
        c_bands = {}
        for line in out.strip().split("\n"):
            k, v = line.split(" ", 1)
            c_bands[int(k)] = v.strip().upper()
        ok("C reports a band for all 257 values", len(c_bands) == 257)
    shutil.rmtree(tmp, ignore_errors=True)

# ── Layer 4 · SQL ────────────────────────────────────────────────
print("\nLayer 4 · SQL — the archive")
sql_bands = None
tmpdb = tempfile.mktemp(suffix=".db")
try:
    con = sqlite3.connect(tmpdb)
    aq = os.path.join(ROOT, "4-archive-sql")
    con.executescript(open(os.path.join(aq, "archive.sql")).read())
    con.executescript(open(os.path.join(aq, "zeroth.sql")).read())
    sql_bands = {c: n.upper() for c, n in
                 con.execute("SELECT confidence, band_name FROM v_band")}
    ok("SQL reports a band for all 257 values", len(sql_bands) == 257)

    con.execute("INSERT INTO anchor (anchor_id, ident, pinned_at, pinned_conf, note) "
                "VALUES (7001, 'law', 1, 128, 'zeroth law')")
    con.execute("INSERT INTO thread (archive_id, ident, state_id, type_id, lang_id, "
                "confidence, lo, hi, born_ms, reason, anchor_id) "
                "VALUES (901, 'law', 1, 1, 0, 128, 128, 128, 1, 'zeroth law', 7001)")
    con.commit()

    def sql_accepts(before, after):
        try:
            con.execute("INSERT INTO crossing (anchor_id, thread_id, from_lang, to_lang, "
                        "conf_before, conf_after, crossed_ms) VALUES (7001, 901, 0, 5, ?, ?, 1)",
                        (before, after))
            return True
        except sqlite3.DatabaseError:
            return False
        finally:
            con.rollback()

    ok("an anchored step is refused by SQL exactly where Python changes band",
       all(sql_accepts(c, c + 1) == (py[c] == py[c + 1]) for c in range(E_CERTAIN)))
    con.close()
finally:
    if os.path.exists(tmpdb):
        os.remove(tmpdb)

# ── Layer 5 · Java ───────────────────────────────────────────────
print("\nLayer 5 · Java — the runtime")
java_bands = None
if not (shutil.which("javac") and shutil.which("java")):
    skip("Java runtime", "no java toolchain")
else:
    tmp = tempfile.mkdtemp(prefix="zeroth_java_")
    probe = os.path.join(tmp, "BandProbe.java")
    with open(probe, "w") as f:
        f.write(
            "import com.codric.ever.EParticle;\n"
            "import com.codric.ever.EverRuntime;\n"
            "public class BandProbe {\n"
            "  public static void main(String[] a){\n"
            "    for (int c = 0; c <= EParticle.CERTAIN; c++)\n"
            "      System.out.println(c + \" \" + EverRuntime.band(c));\n"
            "  }\n}\n")
    jroot = os.path.join(ROOT, "5-runtime-java")
    build = subprocess.run(
        ["javac", "-d", tmp,
         os.path.join(jroot, "com", "codric", "ever", "EParticle.java"),
         os.path.join(jroot, "com", "codric", "ever", "EverRuntime.java"),
         probe],
        capture_output=True, text=True)
    if build.returncode != 0:
        ok("Java probe builds", False)
        print(build.stderr[:400])
    else:
        out = subprocess.run(["java", "-cp", tmp, "BandProbe"],
                             capture_output=True, text=True).stdout
        java_bands = {}
        for line in out.strip().split("\n"):
            k, v = line.split(" ", 1)
            java_bands[int(k)] = v.strip().upper()
        ok("Java reports a band for all 257 values", len(java_bands) == 257)
    shutil.rmtree(tmp, ignore_errors=True)

# ── Agreement — the only check that actually matters ─────────────
print("\nAgreement — one law, or four opinions")

layers = [("C", c_bands), ("SQL", sql_bands), ("Java", java_bands)]
present = [(n, b) for n, b in layers if b]

for name, other in present:
    diffs = [c for c in SCALE if other[c] != py[c]]
    ok(f"Python and {name} agree on all 257 values", not diffs)
    if diffs:
        for c in diffs[:6]:
            print(f"      confidence {c}: Python {py[c]} vs {name} {other[c]}")

if len(present) >= 2:
    names = [n for n, _ in present]
    all_agree = all(present[0][1][c] == b[c] for c in SCALE for _, b in present)
    ok(f"all of {', '.join(['Python'] + names)} agree on every boundary",
       all_agree)
else:
    skip("full cross-layer agreement", "fewer than two other layers built")

# ── The combination operator, every pair ────────────────────────
print("\nExcel — the combination operator, every pair of confidences")
py_excel = {(a, b): excel(a, b) for a in SCALE for b in SCALE}
ok("Excel reaches Certain only when both inputs are Certain",
   all((py_excel[(a, b)] == E_CERTAIN) == (a == E_CERTAIN and b == E_CERTAIN)
       for a in SCALE for b in SCALE))

c_excel = None
if not shutil.which("cc") and not shutil.which("gcc"):
    skip("C Excel", "no C toolchain")
else:
    tmp = tempfile.mkdtemp(prefix="zeroth_excel_")
    src = os.path.join(tmp, "excel.c")
    with open(src, "w") as f:
        f.write('#include <stdio.h>\n#include "tapestry.h"\n'
                'int main(void){int a,b;for(a=0;a<=E_CERTAIN;a++)'
                'for(b=0;b<=E_CERTAIN;b++)'
                'printf("%d %d %d\\n",a,b,'
                '(int)e_excel_formula((int16_t)a,(int16_t)b));'
                'return 0;}\n')
    exe = os.path.join(tmp, "excel")
    build = subprocess.run(
        ["cc", "-std=c99", "-I", os.path.join(ROOT, "0-atom-c"),
         src, os.path.join(ROOT, "0-atom-c", "tapestry.c"), "-o", exe, "-lm"],
        capture_output=True, text=True)
    if build.returncode != 0:
        ok("C Excel probe builds", False)
        print(build.stderr[:400])
    else:
        out = subprocess.run([exe], capture_output=True, text=True).stdout
        c_excel = {}
        for line in out.strip().split("\n"):
            a, b, v = (int(x) for x in line.split())
            c_excel[(a, b)] = v
        ok("C reports Excel for all 66,049 pairs", len(c_excel) == 257 * 257)
    shutil.rmtree(tmp, ignore_errors=True)

java_excel = None
if not (shutil.which("javac") and shutil.which("java")):
    skip("Java Excel", "no java toolchain")
else:
    tmp = tempfile.mkdtemp(prefix="zeroth_excel_java_")
    probe = os.path.join(tmp, "ExcelProbe.java")
    with open(probe, "w") as f:
        f.write(
            "import com.codric.ever.EParticle;\n"
            "public class ExcelProbe {\n"
            "  public static void main(String[] a){\n"
            "    for (int x = 0; x <= EParticle.CERTAIN; x++)\n"
            "      for (int y = 0; y <= EParticle.CERTAIN; y++)\n"
            "        System.out.println(x + \" \" + y + \" \" + EParticle.excelFormula(x, y));\n"
            "  }\n}\n")
    jdir = os.path.join(ROOT, "5-runtime-java", "com", "codric", "ever")
    build = subprocess.run(
        ["javac", "-d", tmp,
         os.path.join(jdir, "EParticle.java"),
         os.path.join(jdir, "EverRuntime.java"),
         probe],
        capture_output=True, text=True)
    if build.returncode != 0:
        ok("Java Excel probe builds", False)
        print(build.stderr[:400])
    else:
        out = subprocess.run(["java", "-cp", tmp, "ExcelProbe"],
                             capture_output=True, text=True).stdout
        java_excel = {}
        for line in out.strip().split("\n"):
            a, b, v = (int(x) for x in line.split())
            java_excel[(a, b)] = v
        ok("Java reports Excel for all 66,049 pairs", len(java_excel) == 257 * 257)
    shutil.rmtree(tmp, ignore_errors=True)

for name, other in (("C", c_excel), ("Java", java_excel)):
    if other is None:
        continue
    diffs = [(a, b) for a in SCALE for b in SCALE
             if other[(a, b)] != py_excel[(a, b)]]
    ok(f"Python and {name} agree on Excel for all 66,049 pairs", not diffs)
    for a, b in diffs[:6]:
        print(f"      excel({a}, {b}): Python {py_excel[(a, b)]} vs {name} {other[(a, b)]}")

# The boundaries themselves, printed so a reader can check them by eye.
print("\n  The six bands, as every layer reports them:")
edges = [c for c in SCALE if c == 0 or py[c] != py[c - 1]]
for i, lo in enumerate(edges):
    hi = (edges[i + 1] - 1) if i + 1 < len(edges) else E_CERTAIN
    span = f"{lo}" if lo == hi else f"{lo}..{hi}"
    print(f"    {py[lo]:<12} {span}")

print(f"\n=== Zeroth Law: {passed} passed, {failed} failed, "
      f"{skipped} skipped ===\n")
if failed:
    raise SystemExit(1)
# A layer that did not run is a skip, never a pass. 77 tells run_all.py so.
raise SystemExit(77 if skipped else 0)
