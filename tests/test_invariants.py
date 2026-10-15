#!/usr/bin/env python3
"""test_invariants.py — three rules the repo states in prose, checked by machine.

1. Arena rule (0-atom-c/ir.h, RULE 1): every allocation goes through the
   arena. The C core still has direct malloc/calloc/realloc sites. They are
   named below, one count per file, so the exception list cannot grow
   silently: a new raw allocation fails this test until it is reviewed,
   added here, and named in ir.h.

2. Depth ceiling (CLAUDE.md, "Depth ceiling = floor(pi) = 3"): every layer
   that defines the constant defines it as 3. C and Python must agree, and
   so must the other layers that carry it.

3. Extern refusal (CLAUDE.md, "Transpilers refuse extern/FFI outright"):
   an extern that is not at top level does not parse, so it cannot reach an
   emitter silently; a top-level extern is refused by every backend.
"""

import re, sys, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "2-interpreter-python"))

from emit import BACKENDS, emit          # noqa: E402
from syntax import parse                  # noqa: E402

# ── 1. Arena rule ────────────────────────────────────────────────
# Direct allocation sites outside the tests, per file. Each one is an
# exception to ir.h RULE 1 and is named there:
#   ir.c       the arena's own slabs (the implementation of the rule)
#   evalue.c   pool composites: blob, list, record storage (RULE 5 legacy)
#   scope.c    scope slot tables
#   tac.c      interpreter frames and state, pass scratch, named-slot buffers
ALLOWED_RAW_ALLOCATIONS = {
    "ir.c": 3,
    "evalue.c": 8,
    "scope.c": 2,
    "tac.c": 9,
}
RAW_ALLOC = re.compile(r"\b(malloc|calloc|realloc)\s*\(")


class TestArenaRule(unittest.TestCase):
    def test_raw_allocations_match_the_named_exceptions(self):
        found = {}
        for path in sorted((ROOT / "0-atom-c").glob("*.c")):
            if path.name.endswith("_test.c") or path.name == "kitchen_sink.c":
                continue
            text = path.read_text()
            # ignore comments so a note that mentions calloc is not a site
            text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
            text = re.sub(r"//[^\n]*", "", text)
            n = len(RAW_ALLOC.findall(text))
            if n:
                found[path.name] = n
        self.assertEqual(found, ALLOWED_RAW_ALLOCATIONS,
                         "a raw allocation was added or removed: review it "
                         "against ir.h RULE 1 and update this list")


# ── 2. Depth ceiling ─────────────────────────────────────────────
# (file, pattern) pairs. Each pattern captures the value the file gives the
# constant. A layer that stops defining it is caught by the count below.
CEILING_SITES = [
    ("0-atom-c/tac.c",               r"#define\s+E_DEPTH_CEILING\s+(\d+)"),
    ("0-atom-c/kitchen_sink.c",      r"#define\s+E_DEPTH_CEILING\s+(\d+)"),
    ("0-atom-c/tapestry.h",          r"#define\s+E_EMULATE_CEILING\s+(\d+)"),
    ("2-interpreter-python/abstract.py", r"^E_DEPTH_CEILING\s*=\s*(\d+)"),
    ("2-interpreter-python/ir.py",       r"^E_DEPTH_CEILING\s*=\s*(\d+)"),
    ("2-interpreter-python/ever.py",     r"^E_EMULATE_CEILING\s*=\s*(\d+)"),
    ("2-interpreter-python/checker.py",  r"^E_EMULATE_CEILING\s*=\s*(\d+)"),
    ("2-inspect-python/translate.py",    r"^E_EMULATE_CEILING\s*=\s*(\d+)"),
    ("5-runtime-java/com/codric/ever/EParticle.java",
                                     r"EMULATE_CEILING\s*=\s*(\d+)"),
    ("3-dsl-ruby/ever.rb",           r"EMULATE_CEILING\s*=\s*(\d+)"),
]


class TestDepthCeiling(unittest.TestCase):
    def test_every_layer_says_three(self):
        values = {}
        for rel, pattern in CEILING_SITES:
            text = (ROOT / rel).read_text()
            m = re.search(pattern, text, flags=re.M)
            self.assertIsNotNone(m, f"{rel} no longer defines the ceiling")
            values[rel] = int(m.group(1))
        self.assertEqual(set(values.values()), {3}, values)

    def test_the_constant_is_floor_pi(self):
        import math
        self.assertEqual(int(math.pi), 3)


# ── 3. Extern refusal ────────────────────────────────────────────
EXTERN_NESTED = 'def f(x) = extern g(x) from "libm"\never y = f(1)\n'
EXTERN_TOP = 'extern sqrt(x) from "libm"\never y = sqrt(4)\n'


class TestExternRefusal(unittest.TestCase):
    def test_extern_inside_a_function_body_does_not_parse(self):
        _, err = parse(EXTERN_NESTED)
        self.assertIsNotNone(err, "an extern inside a def body parsed; "
                             "emit.py's top-level check would no longer see it")

    def test_top_level_extern_is_refused_by_every_backend(self):
        for target in sorted(BACKENDS):
            with self.subTest(target=target):
                with self.assertRaises(NotImplementedError):
                    emit(EXTERN_TOP, target)


if __name__ == "__main__":
    unittest.main()
