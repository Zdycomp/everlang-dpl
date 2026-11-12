#!/usr/bin/env python3
"""cross_layer_test.py — Ever cross-layer agreement.

Layer 2 (Python) and Layer 6 (hand HTML, run headless under node) must
produce identical particles for identical input. If the translator and
the browser disagree, the instrument is lying to somebody, and it does
not matter which one is right.
"""

import atexit
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)          # tests/ lives one level under the repo root
sys.path.insert(0, os.path.join(ROOT, "2-inspect-python"))

from translate import Translator, EState  # noqa: E402

CASES = [
    'int add(int x, int y) { return x + y }',
    'def collect(items=[]):\n    items.append(1)\n    return items',
    'def add(x: int, y: int) -> int:\n    return x + y',
    'DELETE FROM users',
    'public class A { void f(){ String s = null; s.length(); } }',
    '<img src="a.jpg">',
    'def greet\n  puts "hi"',
    'SELECT * FROM a JOIN b;\nDELETE FROM c;\nDROP TABLE d;\nUPDATE e SET x = 1;',
    '#include <iostream>\nclass A { public: virtual void f(); };',
    '<!DOCTYPE html>\n<html lang="en"><body><main>'
    '<img src="a.jpg" alt="a"></main></body></html>',
]

DRIVER = r"""
const fs = require('fs');
const html = fs.readFileSync(process.argv[2], 'utf8');
let js = html.slice(html.indexOf('<script>') + 8,
                    html.lastIndexOf('</script>'));
js = js.slice(0, js.indexOf('/* \u2500\u2500 rendering \u2500\u2500 */'));
js += '\nmodule.exports = { detect, inspect, score };\n';
fs.writeFileSync(process.argv[4], js);
const L6 = require(process.argv[4]);
const cases = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const out = cases.map(c => {
  const lang = L6.detect(c);
  const f = L6.inspect(c, lang);
  const errors = f.filter(x => x.kind === 'error');
  const patterns = f.filter(x => x.kind === 'pattern');
  const s = L6.score(errors, patterns);
  return { lang, state: s.state, confidence: s.confidence,
           errors: errors.length, patterns: patterns.length };
});
process.stdout.write(JSON.stringify(out));
"""

LANG_NAME = {0: "C", 1: "C++", 2: "Python", 3: "Ruby", 4: "SQL",
             5: "Java", 6: "HTML", 7: "Ever"}

passed = failed = 0

def ok(name, cond):
    global passed, failed
    if cond:
        passed += 1; print(f"  \u2713 {name}")
    else:
        failed += 1; print(f"  \u2717 {name}")


print("\n=== Ever — cross-layer agreement ===\n")

WORK = tempfile.mkdtemp(prefix="ever-cross-")
atexit.register(shutil.rmtree, WORK, True)
CASES_PATH = os.path.join(WORK, "ever_cases.json")
DRIVER_PATH = os.path.join(WORK, "ever_driver.js")
X_PATH = os.path.join(WORK, "ever_x.js")
with open(CASES_PATH, "w") as fh:
    json.dump(CASES, fh)
with open(DRIVER_PATH, "w") as fh:
    fh.write(DRIVER)

proc = subprocess.run(
    ["node", DRIVER_PATH,
     os.path.join(ROOT, "6-interface-html", "inspector.html"),
     CASES_PATH, X_PATH],
    capture_output=True, text=True)

if proc.returncode != 0:
    print("node driver failed:\n", proc.stderr)
    raise SystemExit(1)

l6 = json.loads(proc.stdout)
t = Translator()

print("Layer 2 (Python) against Layer 6 (hand HTML, headless)\n")
print(f"  {'case':<6}{'Layer 2':<28}{'Layer 6':<28}agree")
print("  " + "-" * 68)

for i, case in enumerate(CASES):
    tr = t.translate(case, ident=f"case_{i}")
    py_lang  = LANG_NAME[int(tr.lang)]
    py_state = "Z" if tr.particle.state == EState.Z else "Confident"
    py_conf  = tr.particle.confidence

    js = l6[i]
    agree = (py_lang == js["lang"]
             and py_state == js["state"]
             and py_conf == js["confidence"]
             and len(tr.errors) == js["errors"]
             and len(tr.patterns) == js["patterns"])

    a = f"{py_lang} {py_state} {py_conf}/256 e{len(tr.errors)}p{len(tr.patterns)}"
    b = f"{js['lang']} {js['state']} {js['confidence']}/256 " \
        f"e{js['errors']}p{js['patterns']}"
    mark = "\u2713" if agree else "\u2717"
    print(f"  {i:<6}{a:<28}{b:<28}{mark}")

    ok(f"case {i} agrees across layers", agree)

print()
ok("every case agreed", failed == 0)

print(f"\n=== Cross-layer: {passed} passed, {failed} failed ===\n")
raise SystemExit(0 if failed == 0 else 1)
