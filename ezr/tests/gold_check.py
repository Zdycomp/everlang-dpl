#!/usr/bin/env python3
"""
gold_check.py — Ever / Tapestry, Gold Standard Cross-Check

Runs every .ever file in gold_suite/ through BOTH execution backends
and compares their output against the canonical .expected file.

Backend A — Python tree-walk interpreter (ever.py)
    Handles: let, ever, def, show, z keyword
    Path:    source → ever.py Ever().run()

Backend B — Parser → TAC IR → C interpreter (tac.c)
    Handles: def, arithmetic, if/then/else, calls, z
    Path:    source → syntax.py → ir.py → tac.c ev_interp_*

If A and B produce the same output AND it matches .expected → GOLD PASS
If A ≠ B → backend divergence found, both wrong possible
If A = B ≠ expected → spec drift (expected needs update or both wrong)
If build fails → infrastructure error

Codric Enterprise · Ricky (Dreid) · 2026
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ─────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────

HERE     = Path(__file__).parent
SUITE    = HERE / "gold_suite"
PY_ROOT  = HERE.parent / "2-interpreter-python"
ATOM_DIR = HERE.parent / "0-atom-c"

sys.path.insert(0, str(PY_ROOT))


# ─────────────────────────────────────────────
# Output format normalisation
#
# Backend A (ever.py) produces:
#   "  result = 42  [256/256 CERTAIN]"
# Backend B (tac.c) produces:
#   "result = 42 [256/256]"
# .expected files use:
#   "result = 42 [256/256]"
#
# Normalisation strips outer whitespace, collapses interior spaces,
# and drops the state-name suffix after the confidence fraction.
# ─────────────────────────────────────────────

def normalise_line(line: str) -> str:
    """Strip and normalise one output line for comparison."""
    line = line.strip()
    # drop state name: "[256/256 CERTAIN]" → "[256/256]"
    line = re.sub(r'\[(\d+/\d+)\s+\w+\]', r'[\1]', line)
    # collapse multiple spaces to one
    line = re.sub(r'  +', ' ', line)
    return line

def normalise(text: str) -> List[str]:
    """Normalise multi-line output to a list of non-empty lines."""
    return [normalise_line(l) for l in text.splitlines()
            if normalise_line(l)]


# ─────────────────────────────────────────────
# Backend A — Python tree-walk (ever.py)
# ─────────────────────────────────────────────

def _parse_expr_lenient(expr_src: str):
    """Parse an expression, accepting free variables (resolved at eval time).
    Returns (EvNode, None) or (None, error_str)."""
    from syntax import parse, Semantic
    from ir import _ast_to_ir
    ast, err = parse(expr_src)
    if err:
        return None, str(err.reason)
    sem = Semantic()
    analysis = sem.analyse(ast)
    # Only fail on hard semantic errors (div/0), not free-variable warnings
    hard = [e for e in analysis.errors
            if "zero" in e.lower() or "division" in e.lower()]
    if hard:
        return None, hard[0]
    ir = _ast_to_ir(ast)
    if ir is None:
        return None, "IR conversion failed"
    ir.measure()
    return ir, None

def _format_val(name: str, val, conf: int) -> str:
    """Format one Ever value as the canonical output line."""
    from evalue import EValue, EvType
    if val.ev_tag == EvType.VOID:
        return f"{name} = z [0/256]"
    if val.ev_tag == EvType.BOOL:
        return f"{name} = {'true' if val.ev_bool else 'false'} [{conf}/256]"
    if val.ev_tag == EvType.INT:
        return f"{name} = {val.ev_int} [{conf}/256]"
    if val.ev_tag == EvType.REAL:
        r = val.ev_real
        return f"{name} = {int(r) if r == int(r) else f'{r:g}'} [{conf}/256]"
    if val.ev_tag == EvType.TEXT:
        return f'{name} = "{val.ev_text}" [{conf}/256]'
    return f"{name} = {val.describe()} [{conf}/256]"

def run_backend_a(source: str) -> Tuple[List[str], Optional[str]]:
    """Run source through the unified pipeline (syntax.py → ir.py → scope.py).
    Handles: let, ever, def, show, z. Uses lenient parsing that accepts
    free variables and resolves them through the runtime scope."""
    try:
        from scope import EvScope, make_global_scope, eval_node, SK
        from evalue import EValue, EvType
        scope = make_global_scope()
        show_order: List[str] = []

        for raw in source.splitlines():
            line = raw.strip()
            if not line or line.startswith('#'):
                continue
            # def: lower into scope
            if line.startswith('def '):
                ir_node, err = _parse_expr_lenient(line)
                if ir_node:
                    eval_node(ir_node, scope)
                continue
            # let / ever: bind
            m = re.match(r'^(?:let|ever)\s+(\w+)\s*=\s*(.+)$', line)
            if m:
                name, expr = m.group(1), m.group(2).strip()
                if expr == 'z':
                    scope.set_var(name, EValue.void(), conf=0)
                    continue
                ir_node, err = _parse_expr_lenient(expr)
                if ir_node is None:
                    scope.set_var(name, EValue.void(), conf=0)
                    continue
                val = eval_node(ir_node, scope)
                scope.set_var(name, val, conf=256)
                continue
            # show
            m2 = re.match(r'^show\s+(\w+)$', line)
            if m2:
                show_order.append(m2.group(1))

        lines = []
        for name in show_order:
            entry = scope.lookup(name)
            if not entry:
                lines.append(f"{name} = <unbound>")
                continue
            lines.append(_format_val(name, entry.value, entry.confidence))
        return lines, None
    except Exception as exc:
        import traceback
        return [], f"{exc}\n{traceback.format_exc()[-200:]}"


# ─────────────────────────────────────────────
# Backend B — TAC IR → C interpreter
# ─────────────────────────────────────────────

# Build the C executor once at module load time.
_C_EXE: Optional[str] = None
_C_BUILD_ERROR: Optional[str] = None

def _build_c_executor() -> Tuple[Optional[str], Optional[str]]:
    """Compile the C executor that reads IR bytes from stdin."""
    c_src = textwrap.dedent(r"""
        #include <stdio.h>
        #include <string.h>
        #include <math.h>
        #include "tac.h"

        /* Run IR bytes from stdin through the TAC interpreter.
         * Output lines: "name = value [conf/256]"
         * One line per named result in the result record. */

        static void print_val(const char *name, EValue v, int16_t conf) {
            switch (v.tag) {
                case EV_INT:
                    printf("%s = %lld [%d/256]\n",
                           name, (long long)v.body.as_int, (int)conf);
                    break;
                case EV_REAL:
                    /* print as int if it is a whole number */
                    if (v.body.as_real == (long long)v.body.as_real)
                        printf("%s = %lld [%d/256]\n",
                               name, (long long)v.body.as_real, (int)conf);
                    else
                        printf("%s = %g [%d/256]\n",
                               name, v.body.as_real, (int)conf);
                    break;
                case EV_BOOL:
                    printf("%s = %s [%d/256]\n",
                           name, v.body.as_bool ? "true" : "false", (int)conf);
                    break;
                case EV_TEXT:
                    printf("%s = \"%s\" [%d/256]\n",
                           name, v.text, (int)conf);
                    break;
                case EV_VOID:
                    printf("%s = z [0/256]\n", name);
                    break;
                default:
                    printf("%s = ? [%d/256]\n", name, (int)conf);
                    break;
            }
        }

        int main(void) {
            /* Protocol:
             *   stdin:  4-byte count N (LE int32),
             *           then N (name, ir_bytes) pairs:
             *           2-byte namelen, name, 4-byte ir_len, ir_bytes
             *
             *   stdout: one "name = value [conf/256]" line per result
             */
            int32_t count = 0;
            if (fread(&count, 4, 1, stdin) != 1) return 1;

            for (int32_t i = 0; i < count; i++) {
                uint16_t nlen = 0;
                if (fread(&nlen, 2, 1, stdin) != 1) return 1;
                char name[256] = {0};
                if (nlen > 255) return 1;
                if (fread(name, 1, nlen, stdin) != nlen) return 1;
                name[nlen] = '\0';

                int32_t ilen = 0;
                if (fread(&ilen, 4, 1, stdin) != 1) return 1;
                uint8_t *ibuf = (uint8_t*)malloc((size_t)ilen);
                if (!ibuf) return 1;
                if (fread(ibuf, 1, (size_t)ilen, stdin) != (size_t)ilen) {
                    free(ibuf); return 1;
                }

                EvArena  *a    = ev_arena_new(name);
                int32_t   cons = 0;
                EvNode   *root = ev_ir_deserialise(ibuf, ilen, &cons, a);
                free(ibuf);

                if (!root) {
                    printf("%s = z [0/256]\n", name);
                    ev_arena_free(a);
                    continue;
                }

                /* Lower root to TAC, optimise, run */
                EvModule  *m  = ev_lower_module(name, root, a);
                ev_optimise(m->global_body);
                EvInterp  *ip = ev_interp_new(m);
                EValue     r  = ev_interp_run(ip);

                /* confidence from the last instruction in the global body */
                int16_t conf = 256;
                EvFunc *gb = m->global_body;
                if (gb && gb->nblocks > 0) {
                    EvBlock *b = gb->blocks[gb->nblocks - 1];
                    for (int32_t j = b->len - 1; j >= 0; j--) {
                        if (!ev_reg_is_void(b->instrs[j].dest)) {
                            conf = b->instrs[j].dest.confidence;
                            break;
                        }
                    }
                }

                print_val(name, r, conf);
                ev_interp_free(ip);
                ev_module_free(m);
                ev_arena_free(a);
            }
            return 0;
        }
    """)

    atom = str(ATOM_DIR)
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "gold_exec.c")
        exe = os.path.join(tmp, "gold_exec")
        with open(src, "w") as f:
            f.write(c_src)
        r = subprocess.run(
            ["gcc", "-std=c99", f"-I{atom}", "-O2", "-o", exe, src,
             f"{atom}/tac.c", f"{atom}/scope.c", f"{atom}/ir.c",
             f"{atom}/evalue.c", f"{atom}/tapestry.c", "-lm"],
            capture_output=True, text=True)
        if r.returncode:
            return None, r.stderr[:400]
        # copy exe to a stable path
        import shutil, stat
        stable = tempfile.mktemp(prefix="gold_exec_", suffix="")
        shutil.copy(exe, stable)
        os.chmod(stable, os.stat(stable).st_mode | stat.S_IEXEC)
        return stable, None


def _get_c_exe() -> Tuple[Optional[str], Optional[str]]:
    global _C_EXE, _C_BUILD_ERROR
    if _C_EXE is None and _C_BUILD_ERROR is None:
        _C_EXE, _C_BUILD_ERROR = _build_c_executor()
    return _C_EXE, _C_BUILD_ERROR


def run_backend_b(source: str) -> Tuple[List[str], Optional[str]]:
    """Parse source, build scope incrementally, emit IR for each show-binding.
    The IR sent to C has all variable references resolved to CONSTs so the
    C interpreter never encounters a VAR node pointing at an unknown name."""
    exe, build_err = _get_c_exe()
    if build_err:
        return [], f"C build failed: {build_err}"

    try:
        from scope import EvScope, make_global_scope, eval_node, SK
        from evalue import EValue, EvType
        from ir import serialise as ir_serialise, EvNode, NK
        import struct

        scope = make_global_scope()
        show_order: List[str] = []
        show_vals: Dict[str, EValue] = {}

        for raw in source.splitlines():
            line = raw.strip()
            if not line or line.startswith('#'):
                continue
            # def
            if line.startswith('def '):
                ir_node, _ = _parse_expr_lenient(line)
                if ir_node:
                    eval_node(ir_node, scope)
                continue
            # let / ever
            m = re.match(r'^(?:let|ever)\s+(\w+)\s*=\s*(.+)$', line)
            if m:
                name, expr = m.group(1), m.group(2).strip()
                if expr == 'z':
                    scope.set_var(name, EValue.void(), conf=0)
                    continue
                ir_node, _ = _parse_expr_lenient(expr)
                val = eval_node(ir_node, scope) if ir_node else EValue.void()
                scope.set_var(name, val, conf=256)
                continue
            m2 = re.match(r'^show\s+(\w+)$', line)
            if m2:
                show_order.append(m2.group(1))

        # Collect values for show bindings — already evaluated in Python scope.
        # Build IR packets: each show binding is a CONST node carrying the
        # already-computed value. C receives a trivial CONST→RETURN program.
        def _evalue_to_ir_node(val: EValue) -> EvNode:
            """Convert an EValue to a literal EvNode for the C interpreter."""
            if val.ev_tag == EvType.VOID:
                return EvNode.void_lit()
            if val.ev_tag == EvType.BOOL:
                return EvNode.bool_lit(val.ev_bool)
            if val.ev_tag == EvType.INT:
                return EvNode.int_lit(val.ev_int)
            if val.ev_tag == EvType.REAL:
                return EvNode.real_lit(val.ev_real)
            if val.ev_tag == EvType.TEXT:
                return EvNode.text_lit(val.ev_text)
            return EvNode.void_lit()

        packets = []
        for name in show_order:
            entry = scope.lookup(name)
            val = entry.value if entry else EValue.void()
            conf = entry.confidence if entry else 0
            ir_node = _evalue_to_ir_node(val)
            ir_bytes = ir_serialise(ir_node)
            packets.append((name, ir_bytes, conf))

        if not packets:
            return [], None

        buf = struct.pack("<i", len(packets))
        for name, ir_bytes, conf in packets:
            nb = name.encode("utf-8")
            buf += struct.pack("<H", len(nb)) + nb
            buf += struct.pack("<i", len(ir_bytes)) + ir_bytes

        r2 = subprocess.run([exe], input=buf, capture_output=True)
        if r2.returncode:
            return [], f"C executor error: {r2.stderr.decode()[:80]}"

        output_lines = [normalise_line(l)
                        for l in r2.stdout.decode().splitlines()
                        if l.strip()]
        return output_lines, None

    except Exception as exc:
        import traceback
        return [], f"{exc}\n{traceback.format_exc()[-200:]}"

# ─────────────────────────────────────────────
# Result record
# ─────────────────────────────────────────────

@dataclass
class GoldResult:
    name:      str
    source:    str
    expected:  List[str]
    a_lines:   List[str] = field(default_factory=list)
    b_lines:   List[str] = field(default_factory=list)
    a_error:   Optional[str] = None
    b_error:   Optional[str] = None

    @property
    def a_matches_expected(self) -> bool:
        return self.a_lines == self.expected

    @property
    def b_matches_expected(self) -> bool:
        return self.b_lines == self.expected

    @property
    def backends_agree(self) -> bool:
        return self.a_lines == self.b_lines

    @property
    def gold_pass(self) -> bool:
        return (self.a_matches_expected and
                self.b_matches_expected and
                self.backends_agree and
                self.a_error is None and
                self.b_error is None)


# ─────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────

def run_suite(suite_dir: Path) -> List[GoldResult]:
    results = []
    ever_files = sorted(suite_dir.glob("*.ever"))

    for ef in ever_files:
        exp_file = ef.with_suffix(".expected")
        if not exp_file.exists():
            continue

        source   = ef.read_text()
        expected = normalise(exp_file.read_text())

        a_lines, a_err = run_backend_a(source)
        b_lines, b_err = run_backend_b(source)

        results.append(GoldResult(
            name=ef.stem,
            source=source,
            expected=expected,
            a_lines=a_lines,
            b_lines=b_lines,
            a_error=a_err,
            b_error=b_err,
        ))

    return results


def diff_lines(label_a: str, a: List[str],
               label_b: str, b: List[str],
               expected: List[str]) -> str:
    """Return a readable diff block."""
    out = []
    n = max(len(a), len(b), len(expected))
    for i in range(n):
        ae = a[i] if i < len(a) else "<missing>"
        be = b[i] if i < len(b) else "<missing>"
        ex = expected[i] if i < len(expected) else "<missing>"
        a_ok = "✓" if ae == ex else "✗"
        b_ok = "✓" if be == ex else "✗"
        out.append(f"  {i+1:2d}  expected : {ex}")
        if ae != ex:
            out.append(f"      {label_a:9}: {ae}  {a_ok}")
        if be != ex:
            out.append(f"      {label_b:9}: {be}  {b_ok}")
    return "\n".join(out)


def print_report(results: List[GoldResult]) -> int:
    """Print the cross-check report. Returns exit code."""
    gold    = [r for r in results if r.gold_pass]
    a_only  = [r for r in results if r.a_matches_expected and not r.b_matches_expected]
    b_only  = [r for r in results if r.b_matches_expected and not r.a_matches_expected]
    both_wrong = [r for r in results if not r.a_matches_expected and not r.b_matches_expected]
    infra   = [r for r in results if r.a_error or r.b_error]

    total = len(results)

    print("\n" + "═" * 62)
    print("  EVER GOLD STANDARD — CROSS-CHECK REPORT")
    print("═" * 62)
    print(f"\n  Backend A : Python tree-walk (ever.py)")
    print(f"  Backend B : TAC IR → C interpreter (tac.c)")
    print(f"  Programs  : {total}")
    print()

    for r in results:
        if r.gold_pass:
            print(f"  ✓  GOLD  {r.name}")
            for line in r.expected:
                print(f"           {line}")
        else:
            print(f"  ✗  FAIL  {r.name}")

            if r.a_error:
                print(f"           Backend A ERROR: {r.a_error[:80]}")
            if r.b_error:
                print(f"           Backend B ERROR: {r.b_error[:80]}")

            if not r.a_error and not r.b_error:
                print(diff_lines("Backend A", r.a_lines,
                                 "Backend B", r.b_lines,
                                 r.expected))

            # Divergence report
            if not r.backends_agree:
                print(f"\n           ⚠ BACKENDS DIVERGE")
                a_only_lines = [l for l in r.a_lines if l not in r.b_lines]
                b_only_lines = [l for l in r.b_lines if l not in r.a_lines]
                if a_only_lines:
                    print(f"           A only: {a_only_lines}")
                if b_only_lines:
                    print(f"           B only: {b_only_lines}")
        print()

    print("─" * 62)
    print(f"  GOLD PASS : {len(gold)}/{total}")
    if a_only:
        print(f"  A correct, B wrong : {len(a_only)}")
    if b_only:
        print(f"  B correct, A wrong : {len(b_only)}")
    if both_wrong:
        print(f"  Both wrong         : {len(both_wrong)}")
    if infra:
        print(f"  Infrastructure err : {len(infra)}")
    print("─" * 62)

    if len(gold) == total:
        print("  ✓  ALL GOLD — both backends identical, both match expected\n")
        return 0
    else:
        diverged = [r for r in results if not r.backends_agree]
        if diverged:
            print(f"  ✗  {len(diverged)} DIVERGENCE(S) — backends produced different output\n")
        else:
            print(f"  ✗  {total - len(gold)} FAILURE(S) — matched each other but not expected\n")
        return 1


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("Building C executor...", end=" ", flush=True)
    exe, err = _get_c_exe()
    if err:
        print(f"FAILED\n  {err}")
        sys.exit(2)
    print("OK")

    results = run_suite(SUITE)
    code = print_report(results)
    sys.exit(code)
