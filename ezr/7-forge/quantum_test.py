#!/usr/bin/env python3
"""quantum_test.py — EZR / Tapestry, layer 7, the rhyming realm.

Checks the generator's own claims before it checks anything it makes:
that the collapse is a function of the phrase and nothing else, that a
program is addressable rather than sequential, and that the rhyme rule
is a constraint the scanners are actually held to.

Then it does what the forge does — every lexer against every parser,
over the generated set, under the laws.
"""

import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from contract import Num, Prog, Var                                   # noqa
from forge import Forge, build_pairs
from lexers import LEXERS
from quantum import (Couplet, Realm, couplet, emit, fnv1a, foot,      # noqa
                     law_rhyme, observe, rhymes, skeleton_of, stanzas)

passed = failed = 0


def ok(name, cond):
    global passed, failed
    if cond:
        passed += 1; print(f"  ✓ {name}")
    else:
        failed += 1; print(f"  ✗ {name}")


def raises(fn):
    """True when `fn` refuses. Totality is a property of the front
    ends, not of this generator -- a bad call here should fail loudly
    rather than collapse to some plausible default."""
    try:
        fn()
    except Exception:
        return True
    return False


print("\n=== EZR — layer 7, the quantum realm ===\n")

PHRASE = "entangle the parser"
realm = Realm(PHRASE)


print("1. THE COLLAPSE")

# Published FNV-1a 64-bit vectors. If these drift the whole corpus
# drifts with them, silently, which is the one failure mode a
# deterministic generator cannot be allowed to have.
ok("fnv1a('') is the offset basis",
   fnv1a(b"") == 0xCBF29CE484222325)
ok("fnv1a('a') matches the published vector",
   fnv1a(b"a") == 0xAF63DC4C8601EC8C)
ok("fnv1a('foobar') matches the published vector",
   fnv1a(b"foobar") == 0x85944171F73967E8)
ok("collapse stays in range",
   all(0 <= realm.collapse(f"addr{i}", 7) < 7 for i in range(200)))
ok("collapse is a function of the address",
   realm.collapse("2/cond", 100) == realm.collapse("2/cond", 100))
ok("a different address is a different site",
   realm.collapse("2/cond", 1000) != realm.collapse("2/then", 1000))
ok("a different phrase is a different realm",
   Realm("other").collapse("2/cond", 1000) !=
   realm.collapse("2/cond", 1000))
ok("an empty superposition is refused",
   raises(lambda: realm.collapse("x", 0)))


print("\n2. ADDRESSABILITY")

# The point of the address space: stanza 9 does not depend on stanzas
# 0..8 having been generated first. A seeded RNG cannot say this.
fresh = Realm(PHRASE)
warmed = Realm(PHRASE)
for i in range(9):
    warmed.program(f"{i}:0")
ok("a stanza does not depend on its predecessors",
   fresh.program("9:0") == warmed.program("9:0"))
ok("a subtree is regenerable on its own",
   fresh.expr("9:0/c", 2, ()).sexp() ==
   Realm(PHRASE).expr("9:0/c", 2, ()).sexp())
ok("depth bounds the tree",
   Realm(PHRASE, depth=1).expr("0", 1, ()).height() <= 3)


print("\n3. DETERMINISM ACROSS PROCESSES")

# `hash()` is salted per process. If anything in the path reached for
# it, these two runs would differ and every claim above would be a
# claim about one interpreter start.
def _run(seed):
    env = dict(os.environ, PYTHONHASHSEED=seed)
    return subprocess.run(
        [sys.executable, "-c",
         "import quantum;"
         "r=quantum.Realm('entangle the parser');"
         "print(''.join(r.program(f'{i}:0') for i in range(6)))"],
        cwd=os.path.dirname(os.path.abspath(__file__)),
        env=env, capture_output=True, text=True).stdout


a, b = _run("0"), _run("12345")
ok("PYTHONHASHSEED does not change the corpus", a == b and bool(a.strip()))


print("\n4. THE RHYMING RULE")

cps = stanzas(realm, 12)
made = [c for c in cps if c.ok]
ok("the set produced couplets", len(made) >= 6)
ok("both members of every couplet rhyme",
   all(rhymes(c.first, c.second, realm.k) for c in made))
ok("a couplet never rhymes with itself",
   all(skeleton_of(c.first) != skeleton_of(c.second) for c in made))
ok("the recorded foot is the foot",
   all(foot(c.first, realm.k) == c.foot for c in made))
ok("the answering line is the least nonce that answers",
   all(all(foot(realm.program(f"{c.index}:{n}"), realm.k) != c.foot
           or skeleton_of(realm.program(f"{c.index}:{n}")) ==
           skeleton_of(c.first)
           for n in range(1, c.tries))
       for c in made))

withheld = [c for c in cps if not c.ok]
ok("withholding is reported, not dropped",
   all(c.withheld and c.second is None for c in withheld))
ok("a footless line is the reason it withholds",
   all(foot(c.first, realm.k) is None or "within" in c.withheld
       for c in withheld))

# A foot shorter than the program is a weaker constraint, so it must
# never be harder to satisfy. This catches a search that accidentally
# depends on k rather than being parameterised by it.
short = Realm(PHRASE, k=2)
ok("a shorter foot withholds no more often",
   len([c for c in stanzas(short, 12) if c.ok]) >= len(made))


print("\n5. THE RHYME LAW")

ok("the law holds over the set",
   all(not law_rhyme(c, realm.k) for c in made))

# Inject a scanner that reads a different ending, and check the law
# says so. Without this the law could be vacuously true.
class _Truncating:
    """A scanner that drops the last token. Honest-looking, wrong."""
    def __call__(self, src):
        out = LEXERS["L1-regex-master"](src)
        if out.ok and len(out.toks) > 2:
            out.toks = out.toks[:-2] + out.toks[-1:]
        return out


rigged = dict(LEXERS)
rigged["L9-truncating"] = _Truncating()
ok("a scanner that reads a different ending is caught",
   any(law_rhyme(c, realm.k, rigged) for c in made))
ok("and the violation names the scanner",
   any("L9-truncating" in v
       for c in made for v in law_rhyme(c, realm.k, rigged)))


print("\n6. THE MATRIX OVER THE SET")

pairs = build_pairs()
forge = Forge(budget=0, verbose=False)
ok("twenty pairings", len(pairs) == 20)

lines = [ln for c in made for ln in c.lines()]
ok("the set is not empty", len(lines) >= 12)

crashes = []
splits = []
for line in lines:
    verdicts = {}
    for p in pairs:
        r = forge.run_one(p, line)
        if r.crash:
            crashes.append((p.name, line, r.crash))
        verdicts.setdefault(r.verdict, []).append(p.name)
    if len(verdicts) > 1:
        splits.append((line, verdicts))

ok("no pairing raises on a generated line", not crashes)
ok("every pairing reads every line the same way", not splits)
ok("every generated line is accepted",
   all(not forge.run_one(pairs[0], ln).verdict.startswith("FAIL")
       for ln in lines))


print("\n7. OBSERVATION AND EMISSION")

rep = observe(Realm(PHRASE, depth=2), 4)
ok("a clean realm reports converged", rep.clean)
ok("the report counts what it read",
   rep.pairs == 20 and rep.lines == rep.couplets * 2)
ok("the summary states the phrase", PHRASE in rep.summary())

with tempfile.TemporaryDirectory() as td:
    path = emit(realm, cps, os.path.join(td, "realm.ezr"))
    text = open(path).read()
    ok("the set writes to disk", os.path.exists(path))
    ok("every emitted line is there",
       all(c.first in text and c.second in text for c in made))
    ok("a withheld couplet is minuted, not omitted",
       all(f"couplet {c.index} withheld" in text for c in withheld))
    body = [ln for ln in text.splitlines()
            if ln.strip() and not ln.startswith("#")]
    ok("what was written still scans",
       all(LEXERS["L1-regex-master"](ln).ok for ln in body))

print(f"\n=== Quantum realm: {passed} passed, {failed} failed ===\n")
raise SystemExit(0 if failed == 0 else 1)
