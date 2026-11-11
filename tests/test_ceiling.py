"""The depth contract, live in both layers (SEMANTICS §4.6, §8).

Each case runs one program through the Python front door (runtime.run_source)
and through the C interpreter (0-atom-c/tac.c: ev_lower_module, ev_interp_run,
and the OP_CALL gate), then requires the same answer from both: value and
confidence. The C side is a small driver compiled here, fed the same IR bytes
the Python side serialises, and given the same static facts (the measure) and
the same Examples and anchor, in the same order.

Unanchored recursion stops at floor(pi) = 3 call levels; an anchored recursion
with a decreasing measure may go on. C's int64 limits the anchored case to
fact(20), where Python computes fact(100); the depth rule is the same.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
sys.path.insert(0, os.path.join(_ROOT, "2-interpreter-python"))

from ir import EvNode, NK, parse_to_ir, serialise   # noqa: E402
from runtime import run_source                       # noqa: E402

ATOM = os.path.join(_ROOT, "0-atom-c")
C_SOURCES = [os.path.join(ATOM, f) for f in (
    "tac.c", "repair.c", "form.c", "form_lower.c", "scope.c",
    "ir.c", "evalue.c", "tapestry.c")]

FACT = "def fact(n) = if n <= 1 then 1 else n * fact(n - 1)"

# One driver for every case. argv: ir-file, shown-name, measure-or--1,
# examples as "arg:expect,arg:expect" or "-", anchor (0/1).
DRIVER = r"""
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "tac.h"

int main(int argc, char **argv) {
    if (argc < 6) { fprintf(stderr, "usage\n"); return 2; }
    FILE *fp = fopen(argv[1], "rb");
    if (!fp) { fprintf(stderr, "no ir\n"); return 2; }
    fseek(fp, 0, SEEK_END); long len = ftell(fp); fseek(fp, 0, SEEK_SET);
    uint8_t *buf = (uint8_t*)malloc((size_t)len);
    if (!buf || fread(buf, 1, (size_t)len, fp) != (size_t)len) return 2;
    fclose(fp);

    EvArena *a = ev_arena_new("driver");
    int32_t consumed = 0;
    EvNode *root = ev_ir_deserialise(buf, (int32_t)len, &consumed, a);
    if (!root) { printf("ERROR ir\n"); return 1; }
    EvModule *m = ev_lower_module("driver", root);
    if (!m || !m->global_body || m->lower_error) {
        printf("ERROR lower\n"); return 1;
    }

    int measure = atoi(argv[3]);
    if (measure >= 0) ev_module_set_measure(m, "fact", measure);

    if (strcmp(argv[4], "-") != 0) {
        size_t spec_len = strlen(argv[4]) + 1;
        char *spec = (char*)malloc(spec_len);
        if (!spec) return 2;
        memcpy(spec, argv[4], spec_len);
        for (char *tok = strtok(spec, ","); tok; tok = strtok(NULL, ",")) {
            long arg = 0, expect = 0;
            if (sscanf(tok, "%ld:%ld", &arg, &expect) == 2) {
                EValue av = ev_int(arg), ev = ev_int(expect);
                ev_module_example(m, "fact", &av, NULL, 1, ev);
            }
        }
        free(spec);
    }
    if (atoi(argv[5])) ev_module_anchor(m, "fact");

    ev_optimise(m->global_body);
    EvInterp *ip = ev_interp_new(m);
    EValue r = ev_interp_run(ip);
    int conf = ev_interp_ret_conf(ip);
    if (r.tag == EV_INT)
        printf("%s = %lld [%d/256]\n", argv[2], (long long)r.body.as_int, conf);
    else
        printf("%s = z [0/256]\n", argv[2]);
    ev_interp_free(ip);
    return 0;
}
"""


def _call_root(n):
    """`if true then fact(n) else def fact`: the call runs through OP_CALL in the
    global body, and the definition is lowered into the module alongside it."""
    definition = parse_to_ir(FACT).root
    call = EvNode.fn_call("fact", [EvNode.int_lit(n)])
    return EvNode(kind=NK.IF, children=[EvNode.bool_lit(True), call, definition])


class CeilingTest(unittest.TestCase):
    """The same program, the same facts, the same answer from both layers."""

    @classmethod
    def setUpClass(cls):
        cls.work = tempfile.mkdtemp(prefix="ever-ceiling-")
        cls.exe = os.path.join(cls.work, "driver")
        src = os.path.join(cls.work, "driver.c")
        with open(src, "w") as fh:
            fh.write(DRIVER)
        cc = subprocess.run(
            ["gcc", "-std=c99", "-Wall", f"-I{ATOM}", "-o", cls.exe, src]
            + C_SOURCES + ["-lm"],
            capture_output=True, text=True)
        if cc.returncode != 0:
            raise RuntimeError("driver did not compile:\n" + cc.stderr)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.work, ignore_errors=True)

    def _c(self, n, measure=-1, examples="-", anchor=0):
        """Run fact(n) in C with the given facts; return the printed line."""
        ir_path = os.path.join(self.work, f"call{n}.ir")
        with open(ir_path, "wb") as fh:
            fh.write(serialise(_call_root(n)))
        out = subprocess.run(
            [self.exe, ir_path, "d", str(measure), examples, str(anchor)],
            capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        return out.stdout.strip()

    def test_unanchored_fact_three_is_six_and_fact_four_is_z(self):
        # fact(3) needs three call levels, the last legal one; fact(4) is z
        for n, expect in ((3, "d = 6 [120/256]"), (4, "d = z [0/256]")):
            self._n = n
            py = run_source(f"{FACT}\nlet d = fact({n})\nshow d\n").format_lines()
            self.assertEqual(py, [expect])
            self.assertEqual(self._c(n), expect)

    def test_anchored_recursion_runs_past_the_ceiling_in_both_layers(self):
        # Examples (1,1) (2,2) (3,6) earn 217/256; the anchor lifts the ceiling
        # under the decreasing measure n, so fact(20) = 20! at depth 19
        program = (f"{FACT}\nexample fact(1) = 1\nexample fact(2) = 2\n"
                   "example fact(3) = 6\nanchor fact\n"
                   "let d = fact(20)\nshow d\n")
        py = run_source(program).format_lines()
        c = self._c(20, measure=0, examples="1:1,2:2,3:6", anchor=1)
        self.assertEqual(py, ["d = 2432902008176640000 [217/256]"])
        self.assertEqual(c, py[0])


if __name__ == "__main__":
    unittest.main()
