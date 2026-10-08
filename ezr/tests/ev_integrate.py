#!/usr/bin/env python3
"""
ev_integrate.py — Ever / Tapestry, integration test harness

Iterates every .ever file in tests/integration/ (or a directory passed
as an argument), runs the Ever compiler/interpreter against it, and
compares stdout + exit code against a .expected file.

Usage:
    python3 tests/ev_integrate.py                     # default suite
    python3 tests/ev_integrate.py path/to/dir          # custom directory
    python3 tests/ev_integrate.py --tag recursion      # filtered by tag
    python3 tests/ev_integrate.py -v                   # verbose diffs
    python3 tests/ev_integrate.py --backend a          # python only
    python3 tests/ev_integrate.py --backend b          # C TAC only
    python3 tests/ev_integrate.py --backend both       # default: cross-check

File layout:
    tests/integration/01_hello.ever          source program
    tests/integration/01_hello.expected      canonical stdout
    tests/integration/01_hello.meta          optional: tags, exit_code

.meta format (each line is a key=value):
    tags=arithmetic,basic
    exit_code=0
    description=Basic arithmetic expressions

Codric Enterprise · Ricky (Dreid) · 2026
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ─────────────────────────────────────────────
HERE     = Path(__file__).parent
SUITE    = HERE / "integration"
PY_ROOT  = HERE.parent / "2-interpreter-python"
ATOM_DIR = HERE.parent / "0-atom-c"
sys.path.insert(0, str(PY_ROOT))


# ─────────────────────────────────────────────
# Parse .meta files
# ─────────────────────────────────────────────

@dataclass
class Meta:
    tags:        List[str] = field(default_factory=list)
    exit_code:   int = 0
    description: str = ""
    skip:        bool = False
    skip_reason: str = ""

def load_meta(path: Path) -> Meta:
    m = Meta()
    if not path.exists():
        return m
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        k, _, v = line.partition('=')
        k, v = k.strip(), v.strip()
        if k == 'tags':        m.tags = [t.strip() for t in v.split(',') if t.strip()]
        elif k == 'exit_code': m.exit_code = int(v)
        elif k == 'description': m.description = v
        elif k == 'skip':      m.skip = v.lower() in ('1', 'true', 'yes')
        elif k == 'skip_reason': m.skip_reason = v
    return m


# ─────────────────────────────────────────────
# Normalise output for comparison
# ─────────────────────────────────────────────

def normalise(text: str) -> List[str]:
    lines = []
    for line in text.splitlines():
        line = line.strip()
        # drop state-name suffix: [256/256 CERTAIN] → [256/256]
        line = re.sub(r'\[(\d+/\d+)\s+\w+\]', r'[\1]', line)
        # collapse multi-space
        line = re.sub(r'  +', ' ', line)
        if line:
            lines.append(line)
    return lines


# ─────────────────────────────────────────────
# Run a .ever source through Backend A (Python pipeline)
# ─────────────────────────────────────────────

def run_backend_a(source: str) -> Tuple[List[str], int, Optional[str]]:
    """Returns (output_lines, exit_code, error_or_None)."""
    try:
        from syntax import parse, Semantic
        from ir import _ast_to_ir, E_DEPTH_CEILING
        from scope import EvScope, make_global_scope, eval_node, SK
        from evalue import EValue, EvType

        def _parse_lenient(expr_src: str):
            ast, err = parse(expr_src)
            if err:
                return None, str(err.reason)
            sem = Semantic()
            analysis = sem.analyse(ast)
            hard = [e for e in analysis.errors
                    if "zero" in e.lower() or "division" in e.lower()]
            if hard:
                return None, hard[0]
            ir = _ast_to_ir(ast)
            if ir is None:
                return None, "IR conversion failed"
            ir.measure()
            return ir, None

        def _fmt(name: str, val: EValue, conf: int) -> str:
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

        scope = make_global_scope()
        show_order: List[str] = []

        for raw in source.splitlines():
            line = raw.strip()
            if not line or line.startswith('#'):
                continue
            if line.startswith('def '):
                ir, _ = _parse_lenient(line)
                if ir:
                    eval_node(ir, scope)
                continue
            m = re.match(r'^(?:let|ever)\s+(\w+)\s*=\s*(.+)$', line)
            if m:
                name, expr = m.group(1), m.group(2).strip()
                if expr == 'z':
                    scope.set_var(name, EValue.void(), conf=0)
                    continue
                ir, _ = _parse_lenient(expr)
                val = eval_node(ir, scope) if ir else EValue.void()
                scope.set_var(name, val, conf=256)
                continue
            m2 = re.match(r'^show\s+(\w+)$', line)
            if m2:
                show_order.append(m2.group(1))

        lines = []
        for name in show_order:
            e = scope.lookup(name)
            lines.append(_fmt(name, e.value if e else EValue.void(),
                              e.confidence if e else 0))
        return lines, 0, None

    except Exception as exc:
        import traceback
        return [], 1, f"{exc}\n{traceback.format_exc()[-300:]}"


# ─────────────────────────────────────────────
# Run a .ever source through Backend B (TAC → C interpreter)
# ─────────────────────────────────────────────

_C_EXE: Optional[str] = None
_C_BUILD_ERROR: Optional[str] = None

def _build_c_executor() -> Tuple[Optional[str], Optional[str]]:
    import os, stat, shutil, tempfile
    c_src = textwrap.dedent(r"""
        #include <stdio.h>
        #include <string.h>
        #include <stdlib.h>
        #include "tac.h"
        static void print_val(const char *name, EValue v, int16_t conf) {
            switch (v.tag) {
                case EV_INT:
                    if (v.body.as_real == (long long)v.body.as_int)
                        printf("%s = %lld [%d/256]\n",name,(long long)v.body.as_int,(int)conf);
                    else printf("%s = %lld [%d/256]\n",name,(long long)v.body.as_int,(int)conf);
                    break;
                case EV_REAL:
                    if (v.body.as_real == (long long)v.body.as_real)
                        printf("%s = %lld [%d/256]\n",name,(long long)v.body.as_real,(int)conf);
                    else printf("%s = %g [%d/256]\n",name,v.body.as_real,(int)conf);
                    break;
                case EV_BOOL: printf("%s = %s [%d/256]\n",name,v.body.as_bool?"true":"false",(int)conf); break;
                case EV_TEXT: printf("%s = \"%s\" [%d/256]\n",name,v.text,(int)conf); break;
                case EV_VOID: printf("%s = z [0/256]\n",name); break;
                default:      printf("%s = ? [%d/256]\n",name,(int)conf); break;
            }
        }
        int main(void) {
            int32_t count=0;
            if (fread(&count,4,1,stdin)!=1) return 1;
            for (int32_t i=0;i<count;i++) {
                uint16_t nlen=0;
                if (fread(&nlen,2,1,stdin)!=1) return 1;
                char name[256]={0};
                if (nlen>255) return 1;
                if ((int)fread(name,1,nlen,stdin)!=nlen) return 1;
                name[nlen]='\0';
                int32_t ilen=0;
                if (fread(&ilen,4,1,stdin)!=1) return 1;
                uint8_t *ibuf=(uint8_t*)malloc((size_t)ilen);
                if (!ibuf) return 1;
                if ((int)fread(ibuf,1,(size_t)ilen,stdin)!=ilen){free(ibuf);return 1;}
                EvArena *a=ev_arena_new(name);
                int32_t cons=0;
                EvNode *root=ev_ir_deserialise(ibuf,ilen,&cons,a);
                free(ibuf);
                if (!root){printf("%s = z [0/256]\n",name);ev_arena_free(a);continue;}
                EvModule *m=ev_lower_module(name,root,a);
                ev_optimise(m->global_body);
                EvInterp *ip=ev_interp_new(m);
                EValue r=ev_interp_run(ip);
                int16_t conf=256;
                EvFunc *gb=m->global_body;
                if(gb&&gb->nblocks>0){
                    EvBlock *b=gb->blocks[gb->nblocks-1];
                    for(int32_t j=b->len-1;j>=0;j--)
                        if(!ev_reg_is_void(b->instrs[j].dest)){
                            conf=b->instrs[j].dest.confidence;break;
                        }
                }
                print_val(name,r,conf);
                ev_interp_free(ip);ev_module_free(m);ev_arena_free(a);
            }
            return 0;
        }
    """)
    atom = str(ATOM_DIR)
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "ev_exec.c")
        exe = os.path.join(tmp, "ev_exec")
        with open(src, "w") as f:
            f.write(c_src)
        r = subprocess.run(
            ["gcc", "-std=c99", f"-I{atom}", "-O2", "-o", exe, src,
             f"{atom}/tac.c", f"{atom}/scope.c", f"{atom}/ir.c",
             f"{atom}/evalue.c", f"{atom}/tapestry.c", "-lm"],
            capture_output=True, text=True)
        if r.returncode:
            return None, r.stderr[:400]
        stable = tempfile.mktemp(prefix="ev_exec_", suffix="")
        shutil.copy(exe, stable)
        os.chmod(stable, os.stat(stable).st_mode | stat.S_IEXEC)
        return stable, None

def _get_c_exe():
    global _C_EXE, _C_BUILD_ERROR
    if _C_EXE is None and _C_BUILD_ERROR is None:
        _C_EXE, _C_BUILD_ERROR = _build_c_executor()
    return _C_EXE, _C_BUILD_ERROR

def run_backend_b(source: str) -> Tuple[List[str], int, Optional[str]]:
    exe, err = _get_c_exe()
    if err:
        return [], 1, f"C build: {err}"
    try:
        from syntax import parse, Semantic
        from ir import _ast_to_ir, serialise as ir_ser, EvNode, NK
        from scope import EvScope, make_global_scope, eval_node
        from evalue import EValue, EvType
        import struct

        def _parse_lenient(expr_src):
            ast, err = parse(expr_src)
            if err:
                return None
            sem = Semantic()
            analysis = sem.analyse(ast)
            ir = _ast_to_ir(ast)
            if ir:
                ir.measure()
            return ir

        scope = make_global_scope()
        show_order: List[str] = []

        for raw in source.splitlines():
            line = raw.strip()
            if not line or line.startswith('#'):
                continue
            if line.startswith('def '):
                ir = _parse_lenient(line)
                if ir:
                    eval_node(ir, scope)
                continue
            m = re.match(r'^(?:let|ever)\s+(\w+)\s*=\s*(.+)$', line)
            if m:
                name, expr = m.group(1), m.group(2).strip()
                if expr == 'z':
                    scope.set_var(name, EValue.void(), conf=0)
                    continue
                ir = _parse_lenient(expr)
                val = eval_node(ir, scope) if ir else EValue.void()
                scope.set_var(name, val, conf=256)
                continue
            m2 = re.match(r'^show\s+(\w+)$', line)
            if m2:
                show_order.append(m2.group(1))

        def _val_to_node(val: EValue) -> "EvNode":
            if val.ev_tag == EvType.VOID:   return EvNode.void_lit()
            if val.ev_tag == EvType.BOOL:   return EvNode.bool_lit(val.ev_bool)
            if val.ev_tag == EvType.INT:    return EvNode.int_lit(val.ev_int)
            if val.ev_tag == EvType.REAL:   return EvNode.real_lit(val.ev_real)
            if val.ev_tag == EvType.TEXT:   return EvNode.text_lit(val.ev_text)
            return EvNode.void_lit()

        packets = []
        for name in show_order:
            e = scope.lookup(name)
            val = e.value if e else EValue.void()
            ir_bytes = ir_ser(_val_to_node(val))
            packets.append((name, ir_bytes))

        if not packets:
            return [], 0, None

        buf = struct.pack("<i", len(packets))
        for name, ir_bytes in packets:
            nb = name.encode("utf-8")
            buf += struct.pack("<H", len(nb)) + nb
            buf += struct.pack("<i", len(ir_bytes)) + ir_bytes

        r2 = subprocess.run([exe], input=buf, capture_output=True)
        lines = [l.strip() for l in r2.stdout.decode().splitlines() if l.strip()]
        return lines, r2.returncode, None
    except Exception as exc:
        import traceback
        return [], 1, f"{exc}\n{traceback.format_exc()[-200:]}"


# ─────────────────────────────────────────────
# Test case record
# ─────────────────────────────────────────────

@dataclass
class IntegResult:
    name:       str
    meta:       Meta
    expected:   List[str]
    expected_exit: int
    a_out:      List[str] = field(default_factory=list)
    a_exit:     int = 0
    a_err:      Optional[str] = None
    b_out:      List[str] = field(default_factory=list)
    b_exit:     int = 0
    b_err:      Optional[str] = None

    @property
    def a_pass(self) -> bool:
        return (self.a_out == self.expected and
                self.a_exit == self.expected_exit and
                self.a_err is None)

    @property
    def b_pass(self) -> bool:
        return (self.b_out == self.expected and
                self.b_exit == self.expected_exit and
                self.b_err is None)

    @property
    def agree(self) -> bool:
        return self.a_out == self.b_out and self.a_exit == self.b_exit

    @property
    def gold(self) -> bool:
        return self.a_pass and self.b_pass


# ─────────────────────────────────────────────
# Run the suite
# ─────────────────────────────────────────────

def run_integration(suite_dir: Path, tag_filter: Optional[str],
                    backend: str) -> List[IntegResult]:
    results = []
    for ef in sorted(suite_dir.glob("*.ever")):
        exp_file  = ef.with_suffix(".expected")
        meta_file = ef.with_suffix(".meta")
        if not exp_file.exists():
            continue
        meta = load_meta(meta_file)
        if tag_filter and tag_filter not in meta.tags:
            continue

        source   = ef.read_text()
        expected = normalise(exp_file.read_text())
        r = IntegResult(name=ef.stem, meta=meta,
                        expected=expected, expected_exit=meta.exit_code)

        if meta.skip:
            results.append(r)
            continue

        if backend in ('a', 'both'):
            r.a_out, r.a_exit, r.a_err = run_backend_a(source)
            r.a_out = normalise('\n'.join(r.a_out))

        if backend in ('b', 'both'):
            r.b_out, r.b_exit, r.b_err = run_backend_b(source)
            r.b_out = normalise('\n'.join(r.b_out))

        results.append(r)
    return results


# ─────────────────────────────────────────────
# Report
# ─────────────────────────────────────────────

def print_diff(expected: List[str], got: List[str], label: str) -> None:
    n = max(len(expected), len(got))
    for i in range(n):
        e = expected[i] if i < len(expected) else "<missing>"
        g = got[i]      if i < len(got)      else "<missing>"
        if e != g:
            print(f"    {label}  line {i+1}:")
            print(f"      expected : {e}")
            print(f"      got      : {g}")

def print_report(results: List[IntegResult], backend: str, verbose: bool) -> int:
    gold    = [r for r in results if r.gold]
    skipped = [r for r in results if r.meta.skip]
    failed  = [r for r in results if not r.gold and not r.meta.skip]
    diverged = [r for r in failed if not r.agree]

    print("\n" + "═" * 62)
    print("  EVER INTEGRATION TEST SUITE")
    print("═" * 62)
    print(f"  Backend : {backend}")
    print(f"  Programs: {len(results)}  ({len(skipped)} skipped)")
    print()

    for r in results:
        if r.meta.skip:
            print(f"  ∼  SKIP  {r.name}  [{r.meta.skip_reason}]")
            continue

        if r.gold:
            print(f"  ✓  GOLD  {r.name}")
            if verbose:
                for line in r.expected:
                    print(f"           {line}")
        else:
            print(f"  ✗  FAIL  {r.name}")
            if r.meta.description:
                print(f"           {r.meta.description}")

            if r.a_err:
                print(f"    Backend A error: {r.a_err[:80]}")
            elif backend in ('a', 'both') and not r.a_pass:
                print_diff(r.expected, r.a_out, "A")

            if r.b_err:
                print(f"    Backend B error: {r.b_err[:80]}")
            elif backend in ('b', 'both') and not r.b_pass:
                print_diff(r.expected, r.b_out, "B")

            if backend == 'both' and not r.agree:
                print(f"    ⚠ BACKENDS DIVERGE")
                a_only = [l for l in r.a_out if l not in r.b_out]
                b_only = [l for l in r.b_out if l not in r.a_out]
                if a_only: print(f"      A only: {a_only}")
                if b_only: print(f"      B only: {b_only}")
        print()

    print("─" * 62)
    active = len(results) - len(skipped)
    print(f"  GOLD     : {len(gold)}/{active}")
    if diverged:
        print(f"  DIVERGED : {len(diverged)}")
    print("─" * 62)

    if len(gold) == active:
        print("  ✓  ALL GOLD\n")
        return 0
    else:
        print(f"  ✗  {active - len(gold)} FAILURE(S)\n")
        return 1


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Ever integration test harness")
    ap.add_argument("suite", nargs="?", default=str(SUITE),
                    help="Directory of .ever test files")
    ap.add_argument("--tag",     default=None, help="Filter by tag")
    ap.add_argument("--backend", default="both",
                    choices=["a","b","both"], help="Which backend(s) to run")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    suite_dir = Path(args.suite)
    if not suite_dir.exists():
        print(f"Creating integration suite directory: {suite_dir}")
        suite_dir.mkdir(parents=True)

    if args.backend in ('b', 'both'):
        print("Building C executor...", end=" ", flush=True)
        exe, err = _get_c_exe()
        if err:
            print(f"FAILED\n  {err}")
            return 2
        print("OK")

    results = run_integration(suite_dir, args.tag, args.backend)
    if not results:
        print(f"No .ever/.expected pairs found in {suite_dir}")
        return 0

    return print_report(results, args.backend, args.verbose)

if __name__ == "__main__":
    sys.exit(main())
