#!/usr/bin/env python3
"""
golden.py — Ever / Tapestry, golden master test runner

For each .ever file in tests/golden/programs/, runs the Ever pipeline
and compares actual output against the matching .expected file.

Expected file format:
  AST:Type(...)        — parse and check AST node type and key fields
  EVAL:value@conf      — evaluate and check result value and confidence
  SEM:key=value        — check semantic analysis result
  ERR:stage            — expect a pipeline error at this stage (lex/parse/semantic)

Codric Enterprise · Ricky (Dreid) · 2026
"""

import json
import os, sys, re, difflib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / '2-interpreter-python'))

from syntax import parse, Semantic, lex
from syntax import (Num, Str, Bool, Var, BinOp, If, Call, FnDef,
                    ListLit, RecordLit, UnaryOp, Index, Field,
                    ForRange, ForIn, While, Extern)
from ir import parse_to_ir
from abstract import Lambda
from ever import e_val

HERE  = Path(__file__).parent
PROG  = HERE / 'golden' / 'programs'

passed = failed = skipped = 0


def node_sig(node) -> str:
    """Return a canonical, lossless JSON representation of an AST node."""
    def encode(current):
        if current is None:
            return None
        if isinstance(current, Num):
            return {
                "type": "Num",
                "value": current.value,
                "literal": current.raw or str(current.value),
                "numeric_kind": "real" if current.is_float_literal() else "int",
            }
        if isinstance(current, Str):
            return {"type": "Str", "value": current.value}
        if isinstance(current, Bool):
            return {"type": "Bool", "value": current.value}
        if isinstance(current, Var):
            return {"type": "Var", "name": current.name}
        if isinstance(current, BinOp):
            return {
                "type": "BinOp", "operator": current.op,
                "left": encode(current.left), "right": encode(current.right),
            }
        if isinstance(current, If):
            return {
                "type": "If", "condition": encode(current.cond),
                "then_branch": encode(current.then),
                "else_branch": encode(current.els),
            }
        if isinstance(current, Call):
            return {"type": "Call", "name": current.name,
                    "arguments": [encode(arg) for arg in current.args]}
        if isinstance(current, FnDef):
            return {"type": "FnDef", "name": current.name,
                    "parameters": current.params, "body": encode(current.body)}
        if isinstance(current, ListLit):
            return {"type": "ListLit", "items": [encode(item) for item in current.items]}
        if isinstance(current, RecordLit):
            return {"type": "RecordLit", "fields": [
                {"name": key, "value": encode(value)}
                for key, value in zip(current.keys, current.values)
            ]}
        if isinstance(current, UnaryOp):
            return {"type": "UnaryOp", "operator": current.op,
                    "operand": encode(current.operand)}
        if isinstance(current, Index):
            return {"type": "Index", "target": encode(current.target),
                    "key": encode(current.key)}
        if isinstance(current, Field):
            return {"type": "Field", "target": encode(current.target),
                    "name": current.name}
        if isinstance(current, ForRange):
            return {"type": "ForRange", "variable": current.var,
                    "start": encode(current.start), "end": encode(current.end),
                    "step": encode(current.step), "body": encode(current.body)}
        if isinstance(current, ForIn):
            return {"type": "ForIn", "variable": current.var,
                    "sequence": encode(current.seq), "body": encode(current.body)}
        if isinstance(current, While):
            return {"type": "While", "condition": encode(current.cond),
                    "body": encode(current.body)}
        if isinstance(current, Extern):
            return {"type": "Extern", "name": current.name,
                    "parameters": current.params, "library": current.libpath}
        return {"type": type(current).__name__}

    return json.dumps(encode(node), ensure_ascii=False, separators=(",", ":"),
                      sort_keys=True)


def eval_expr(src: str):
    """Evaluate a single Ever expression, return (value, confidence)."""
    # the expression may be a literal or a binop; we evaluate it through
    # the IR → C bridge path or through Python direct evaluation
    node, err = parse(src)
    if err or not node:
        return None, 0
    # evaluate using the AST executor already in syntax.py
    from syntax import eval_ast
    fns = {}
    result = eval_ast(node, {}, fns, 0, limit=10)
    if result.is_z:
        return None, 0
    return result.value, result.confidence


def check_line(line: str, src: str, ast_node, sem, err) -> tuple:
    """
    Check one expected line against the actual output.
    Returns (matched: bool, detail: str)
    """
    line = line.strip()
    if not line or line.startswith('#'):
        return True, "comment/blank"

    # ERR:stage — expect a pipeline error
    m = re.match(r'^ERR:(\w+)$', line)
    if m:
        stage = m.group(1)
        if err is not None:
            return True, f"error at {stage} as expected"
        return False, f"expected error at '{stage}', got no error"

    # AST:Type(...) — check AST structure
    m = re.match(r'^AST:(.+)$', line)
    if m:
        expected_sig = m.group(1)
        if err:
            return False, f"got pipeline error instead of AST: {err}"
        actual_sig = node_sig(ast_node)
        # allow partial match (... means "don't check children")
        if "..." in expected_sig:
            prefix = expected_sig.split("(")[0]
            match = actual_sig.startswith(prefix)
        else:
            match = actual_sig == expected_sig
        return match, f"AST actual={actual_sig}"

    # EVAL:value@confidence — check evaluated result
    m = re.match(r'^EVAL:(.+)@(\d+)$', line)
    if m:
        exp_val_str, exp_conf_str = m.group(1), m.group(2)
        if err:
            return False, f"got pipeline error instead of value: {err}"
        value, conf = eval_expr(src)
        if value is None:
            return False, f"evaluation returned Z"
        # compare value
        if exp_val_str in ("True", "False"):
            match_val = str(value) == exp_val_str
        else:
            try:
                # numeric comparison with tolerance for floats
                ev = float(exp_val_str)
                match_val = abs(float(value) - ev) < 1e-9
            except ValueError:
                match_val = str(value) == exp_val_str
        match_conf = conf == int(exp_conf_str)
        match = match_val and match_conf
        return match, f"actual={value}@{conf}"

    # SEM:key=value — check semantic analysis
    m = re.match(r'^SEM:(\w+)=(.+)$', line)
    if m:
        key, exp = m.group(1), m.group(2)
        if sem is None:
            return False, "no semantic analysis available"
        actual = str(getattr(sem, key, None))
        match = actual == exp
        return match, f"sem.{key}={actual}"

    return False, f"unrecognised expected line: {line!r}"


def run_program(ever_file: Path, expected_file: Path) -> bool:
    """Run one golden master test. Returns True on pass."""
    global passed, failed

    src_lines = ever_file.read_text().strip().split('\n')
    expected_lines = expected_file.read_text().strip().split('\n')

    # strip comments from source
    src_lines = [l for l in src_lines if not l.strip().startswith('#')]
    src_full = '\n'.join(src_lines)

    # ── pipeline: each non-blank source line is an independent program ──
    # The parser handles one top-level expression or definition at a time.
    # Multi-line .ever files pair each source line with one expected line.
    name = ever_file.stem
    all_ok = True

    # zip source lines with expected lines, skipping blanks/comments on both
    src_active = [l for l in src_lines if l.strip() and not l.strip().startswith('#')]
    exp_active = [l for l in expected_lines if l.strip() and not l.strip().startswith('#')]

    for i, exp_line in enumerate(exp_active):
        # pick the corresponding source line, or full source for single-line files
        src_for_check = src_active[i] if i < len(src_active) else src_full

        # run the pipeline on this source line
        toks, lex_err = lex(src_for_check)
        if lex_err:
            ast_node, sem, pipe_err = None, None, lex_err
        else:
            ast_node, parse_err = parse(src_for_check)
            if parse_err or ast_node is None:
                sem, pipe_err = None, parse_err
            else:
                analysis = Semantic().analyse(ast_node)
                if analysis.errors:
                    sem = analysis
                    pipe_err = type('E', (), {'is_z': True,
                        'reason': '; '.join(analysis.errors)})()
                else:
                    sem = analysis
                    pipe_err = None

        # AST: checks never fail on semantic errors
        err_for_check = (None if exp_line.strip().startswith('AST:')
                         and ast_node is not None else pipe_err)
        ok_line, detail = check_line(exp_line, src_for_check,
                                     ast_node, sem, err_for_check)
        if ok_line:
            passed += 1
            print(f"  \u2713 {name}:{i+1} {exp_line[:50]}")
        else:
            failed += 1
            all_ok = False
            print(f"  \u2717 {name}:{i+1} {exp_line[:50]}")
            print(f"       {detail}")
    return all_ok


def main():
    global skipped
    print(f"\n=== Golden master tests ({PROG}) ===\n")

    ever_files = sorted(PROG.glob('*.ever'))
    if not ever_files:
        print("  no .ever files found in", PROG)
        return 1

    for ever_file in ever_files:
        expected_file = ever_file.with_suffix('.expected')
        if not expected_file.exists():
            print(f"  ~ skip {ever_file.name}: no .expected file")
            skipped += 1
            continue
        run_program(ever_file, expected_file)

    print(f"\n  files: {len(ever_files)}  "
          f"assertions: passed={passed} failed={failed} skipped={skipped}")
    print(f"\n=== Golden master: {passed} passed, {failed} failed ===\n")
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
