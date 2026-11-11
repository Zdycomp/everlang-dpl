#!/usr/bin/env python3
"""
ezrun.py — run an Ever core program, with evidence.

Two runners live in this directory and they are not rivals:

  ever_cli.py   `ever run f.ever` -- the front door. Drives
                runtime.run_source: statements, records, loops,
                indexing, externs, the builtins, the profiler.
  ezrun.py      this file. Drives syntax.py's eval_ast, and is the
                only surface anywhere that exposes the confidence
                algebra -- [EXAMPLE] earning trust, [ANCHOR] buying
                depth. Without it, eval_ast is reachable only by
                importing the module, and a language feature you can
                only use by importing the implementation is not
                shipped.

    ezrun.py program.ever                 run it
    ezrun.py program.ever --call 'f(3)'   run it, then evaluate a call
    ezrun.py -e '1 + 1'                   run one expression
    echo '1 + 1' | ezrun.py -             read from stdin
    ezrun.py p.ever -x 'f(1) = 1' -a f    earn confidence, then depth

## What this runs, exactly

eval_ast evaluates seven node kinds: numbers, text, booleans, variable
references, binary operators, if/then/else, and calls to functions the
program defines. That is the whole of it. A list literal parses and
then comes back Z("cannot evaluate ListLit"); `len`, `head` and `tail`
live in builtins_ml and are reachable from the scope/IR path, not from
here; `let x = v in body` is not v4.10 grammar at all (the statement
form `let x = v` is, and eval_ast has no case for it either).

None of that is this runner hiding a smaller language behind a bigger
promise -- it is the boundary of the evaluator it drives, and the
boundary is where `5-runtime-java/differential.py` reads 31 divergences
against the Java runtime, which implements the forge's CORE.md instead.
See ezr/CORE.md for which lineage is which.

## Entry points

v4.10's parser returns a bare node for single-statement source and
Program(statements) otherwise, and it permits a bare expression as the
LAST statement of a run of definitions. So:

  * a program that is (or ends in) an expression is evaluated;
  * a program of definitions that defines `main()` has `main()` called;
  * otherwise `--call` names the expression to evaluate.

`main()` is a convention of *this runner*, not a rule of the language.
Nothing in the grammar knows about it.

## Depth

`--depth` defaults to 100 rather than to floor(pi) = 3. Worth being
plain about: the earned-depth rule is anchoring, and `--anchor` now
ships it, so the ceiling and the way past it arrive together. 3 remains
available as `-d 3`, which is what the anchoring tests use.

Codric Enterprise
"""

from __future__ import annotations

import argparse
import sys
from typing import Dict, List, Optional

from ever import E, E_CERTAIN, E_EXECUTE_FLOOR, E_INTAKE
from syntax import (Call, E_HARD_DEPTH, FnDef, Program, Semantic, Trust,
                    compile_ever, eval_ast)

EXIT_OK = 0
EXIT_REFUSED = 1        # the program ran and produced Z
EXIT_BAD_INPUT = 2      # could not read it, or it did not compile


def definitions(node) -> Dict[str, object]:
    """The function table a program defines.

    v3.0's syntax.py exported this; v4.10's does not, so the runner
    carries it. Kept tiny and local rather than added to syntax.py:
    which functions a *runner* wants to call is a runner's business.
    """
    if isinstance(node, Program):
        return {d.name: d for d in node.statements if isinstance(d, FnDef)}
    if isinstance(node, FnDef):
        return {node.name: node}
    return {}


def entry_node(ast):
    """What this program evaluates on its own, or None if it says nothing.

    Two shapes, because v4.10's parser has two. Single-statement source
    comes back unwrapped -- `1 + 1` is a BinOp, not a Program of one --
    and a run of definitions may end in a bare expression, which the
    parser permits only in last position. Either is an entry point. A
    program whose last statement is a definition is not one, and needs
    --call or a main().

    Anything else that is not a FnDef is handed to eval_ast rather than
    filtered out here, even the node kinds eval_ast cannot evaluate. A
    `[1, 2]` that comes back "cannot evaluate ListLit" has told the
    truth about where the boundary is; the same program reported as
    "defines nothing and does not say what to run" would not have.
    """
    if isinstance(ast, Program):
        last = ast.statements[-1] if ast.statements else None
        return None if isinstance(last, FnDef) else last
    return None if isinstance(ast, FnDef) else ast


def _read(path: str) -> Optional[str]:
    """Source text, or None with the reason already reported.

    A missing file is a refusal with a sentence, not a traceback. The
    old entry point raised FileNotFoundError straight at the user, in a
    project whose first guarantee is that things do not raise.
    """
    if path == "-":
        return sys.stdin.read()
    try:
        with open(path) as fh:
            return fh.read()
    except IsADirectoryError:
        print(f"ezrun: {path} is a directory, not a program",
              file=sys.stderr)
    except FileNotFoundError:
        print(f"ezrun: no such file: {path}", file=sys.stderr)
    except OSError as exc:
        print(f"ezrun: cannot read {path}: {exc.strerror}", file=sys.stderr)
    return None


def _report_compile(c, where: str) -> None:
    """Say what the pipeline refused, and at which stage."""
    if c.error is not None:
        print(f"ezrun: {where}: {c.stage}: {c.error.reason}", file=sys.stderr)
        return
    for msg in (c.analysis.errors if c.analysis else []):
        print(f"ezrun: {where}: semantic: {msg}", file=sys.stderr)


def _show(result: E, quiet: bool, requirement: str = "") -> None:
    if result.is_z:
        defect = result.defect.name.lower() if result.defect else "unknown"
        print(f"Z({defect}) — {result.reason}", file=sys.stderr)
        if requirement:
            # A refusal states what the language will not do. This line
            # states what would make it willing, which is the same
            # computation read the other way round.
            print(f"       to lift it: {requirement}", file=sys.stderr)
        return
    if quiet:
        print(result.value)
    else:
        print(f"{result.value}  @ {result.confidence}/{E_CERTAIN}")


def confidence_from_examples(passed: int, total: int) -> int:
    """[EXAMPLE], SEMANTICS.md 4.2.

    u_f = ((256 - 120)/256) ** p, then c_f = floor(256 * (1 - u_f) * p/t),
    capped one short of CERTAIN. Each passing Example is an independent
    witness at intake strength, so Examples corroborate rather than
    chain: 1/1 is 120 and still below the floor, 2/2 clears at 183, 3/3
    is 217. A failure scales the result by the share that held.
    """
    if total <= 0:
        return 0
    u = ((E_CERTAIN - E_INTAKE) / E_CERTAIN) ** passed if passed else 1.0
    c = int(E_CERTAIN * (1.0 - u) * (passed / total))
    return max(0, min(E_CERTAIN - 1, c))


def witnesses_needed(passed: int, total: int,
                     target: int = E_EXECUTE_FLOOR,
                     cap: int = 64) -> Optional[int]:
    """[EXAMPLE], solved for the missing evidence instead of the score.

    `confidence_from_examples` runs the rule forwards: given p of t
    witnesses, here is what you are worth. This runs the same rule
    backwards: you are worth 120 and you need 128, so how many more
    passing witnesses is that? The answer is 1, and that is a sentence
    somebody can act on -- unlike "below the execute floor", which is
    the same fact with the actionable half deleted.

    Nothing is inverted analytically because nothing needs to be: the
    forward rule is monotone in k and saturates one short of CERTAIN, so
    walking k up from 0 finds the least sufficient k or establishes
    there is none. A failure already recorded cannot be withdrawn, so
    the answer accounts for it -- 1 of 9 needs eight more, not one.

    None means the target is unreachable from here within `cap` further
    witnesses, which is itself worth saying plainly.
    """
    for k in range(cap + 1):
        if confidence_from_examples(passed + k, total + k) >= target:
            return k
    return None


def _needs(passed: int, total: int) -> str:
    """The requirement clause for a thread short of the execute floor."""
    k = witnesses_needed(passed, total)
    if k is None:
        return (f"no number of further witnesses within reason clears "
                f"{E_EXECUTE_FLOOR} from {passed} of {total}")
    if k == 0:
        return "nothing further is needed"
    return (f"{k} more passing Example{'s' if k > 1 else ''} clears "
            f"{E_EXECUTE_FLOOR}")


def _why_no_measure(fn) -> str:
    """The requirement clause for a function that cannot be anchored.

    Semantic.movements has just computed how every parameter moves. A
    refusal that says "no decreasing measure" is that computation with
    its useful half thrown away; this puts it back.
    """
    moves = Semantic.movements(fn)
    if moves is None:
        return (f"{fn.name} does not call itself, so it has no measure "
                f"to prove and needs no anchor")
    parts = [f"{k} {', '.join(v)}" for k, v in moves.items()]
    return ("anchoring needs one parameter that strictly decreases in "
            "every self-call; here " + "; ".join(parts))


def _split_example(text: str) -> Optional[tuple]:
    """`f(1) = 1` into ('f(1)', '1'). Splits on the first `=` that is not
    part of `==`, `<=`, `>=` or `!=`, so an expected value may compare."""
    for i, ch in enumerate(text):
        if ch != "=":
            continue
        if i + 1 < len(text) and text[i + 1] == "=":
            continue
        if i and text[i - 1] in "=<>!":
            continue
        return text[:i].strip(), text[i + 1:].strip()
    return None


def _earn(fns, examples: List[str], anchors: List[str], depth: int,
          where: str) -> tuple:
    """Turn Examples into confidence and anchors into earned depth.

    Neither is source syntax. The forge settled the reserved words at
    eight, and SEMANTICS.md states both as operations on a thread rather
    than as things a program says about itself -- so they arrive the way
    a verification harness would supply them, from outside the program.
    """
    trust = Trust()
    tally: Dict[str, List[int]] = {}
    #: canonical call source -> the answer already claimed for it.
    seen: Dict[str, object] = {}

    for spec in examples:
        parts = _split_example(spec)
        if parts is None:
            print(f"ezrun: --example {spec!r}: expected 'call = value'",
                  file=sys.stderr)
            return None, EXIT_BAD_INPUT
        call_src, want_src = parts
        cc = compile_ever(call_src, {k: len(v.params) for k, v in fns.items()})
        wc = compile_ever(want_src)
        if not cc.ok or not wc.ok:
            bad = call_src if not cc.ok else want_src
            print(f"ezrun: --example {spec!r}: {bad!r} does not compile",
                  file=sys.stderr)
            return None, EXIT_BAD_INPUT

        name = _called_name(cc.ast)
        if name is None or name not in fns:
            print(f"ezrun: --example {spec!r}: names no defined function",
                  file=sys.stderr)
            return None, EXIT_BAD_INPUT

        # An Example is checked at the confidence earned so far, which is
        # how the third Example is allowed to be the one that clears the
        # floor. A depth-exceeded Example counts as a failure; otherwise
        # the ceiling would be free.
        got = eval_ast(cc.ast, {}, dict(fns), 0, depth, trust)
        want = eval_ast(wc.ast, {}, {}, 0, depth, Trust())
        ok = (not got.is_z) and (not want.is_z) and got.value == want.value

        # [EXAMPLE] multiplies uncertainty across INDEPENDENT witnesses,
        # and the same case stated twice is one witness, not two. Before
        # this check it was two: measured, `-x 'growth(100, 0) = 100'`
        # repeated three times took the function from 120 to 183 to 217,
        # exactly as three distinct cases would -- real confidence bought
        # with no new evidence, which is the one thing T2 says the
        # algebra must never allow. Keyed on the AST's own rendering, so
        # `f(1,2)` and `f( 1 , 2 )` are correctly the same witness and
        # `f(1)` and `f(2)` are correctly not.
        key = str(cc.ast)
        if key in seen:
            if seen[key] != want.value:
                print(f"ezrun: --example {spec!r}: {key} was already "
                      f"given {seen[key]!r} as its answer. Evidence that "
                      f"contradicts itself is not evidence.",
                      file=sys.stderr)
                return None, EXIT_BAD_INPUT
            continue
        seen[key] = want.value

        p, t = tally.get(name, [0, 0])
        tally[name] = [p + (1 if ok else 0), t + 1]
        trust.confidence[name] = confidence_from_examples(*tally[name])

    for name in anchors:
        fn = fns.get(name)
        if fn is None:
            print(f"ezrun: --anchor {name}: not defined in {where}",
                  file=sys.stderr)
            return None, EXIT_BAD_INPUT
        conf = trust.of(name)
        if conf < E_EXECUTE_FLOOR:
            # [ANCHOR-FN] requires a cleared thread. Anchoring an
            # unverified function would grant depth on no evidence.
            # The refusal carries the requirement: the same rule that
            # produced `conf` also answers how much more it would take.
            p_t = tally.get(name, [0, 0])
            print(f"ezrun: --anchor {name}: refused, {conf}/256 is below "
                  f"the execute floor ({E_EXECUTE_FLOOR}). "
                  f"{_needs(p_t[0], p_t[1])}.", file=sys.stderr)
            return None, EXIT_REFUSED
        measure = Semantic._measure(fn) if _recursive(fn) else ""
        if measure is None:
            # [ANCHOR-BOT], the rule that keeps the language honest: a
            # function can sit at 240/256 and still loop forever. Saying
            # only that is the refusal at its least useful, though --
            # the search that just failed knows exactly which parameter
            # went the wrong way.
            print(f"ezrun: --anchor {name}: refused, confidence proves "
                  f"trust, not termination. {_why_no_measure(fn)}.",
                  file=sys.stderr)
            return None, EXIT_REFUSED
        trust.anchored.add(name)

    return (trust, tally), EXIT_OK


def _lift(result: E, fns, trust: Trust, tally: Dict[str, List[int]]) -> str:
    """What would turn this refusal into an answer, or "" if nothing here
    can say.

    Only the depth ceiling is answered for now, because it is the only
    runtime refusal whose cure is a thing the language already models.
    `1 / 0` has no requirement to state -- there is no evidence that
    makes dividing by zero work, and inventing a suggestion for it would
    be worse than silence.
    """
    if not result.is_z or "depth ceiling" not in (result.reason or ""):
        return ""
    fn = fns.get(result.ident)
    if fn is None:
        return ""
    if result.ident in trust.anchored:
        return (f"{result.ident} is anchored already and still ran out of "
                f"depth at {E_HARD_DEPTH}; its measure decreases too slowly "
                f"for this input")
    measure = Semantic._measure(fn)
    if measure is None:
        return _why_no_measure(fn)
    conf = trust.of(result.ident)
    if conf < E_EXECUTE_FLOOR:
        p_t = tally.get(result.ident, [0, 0])
        return (f"{result.ident} decreases {measure} in every self-call, so "
                f"it can be anchored -- but anchoring needs the execute "
                f"floor first, and it sits at {conf}/256. "
                f"{_needs(p_t[0], p_t[1])}, then pass -a {result.ident}")
    return (f"{result.ident} decreases {measure} in every self-call and "
            f"sits at {conf}/256, above the floor. Pass -a {result.ident} "
            f"to buy the depth")


def _called_name(ast) -> Optional[str]:
    node = entry_node(ast)
    return node.name if isinstance(node, Call) else None


def _recursive(fn) -> bool:
    def walk(n) -> bool:
        if isinstance(n, Call) and n.name == fn.name:
            return True
        return any(walk(k) for k in n.children())
    return walk(fn.body)


def run(src: str, call: Optional[str] = None, depth: int = 100,
        quiet: bool = False, where: str = "<input>",
        examples: Optional[List[str]] = None,
        anchors: Optional[List[str]] = None) -> int:
    c = compile_ever(src)
    if not c.ok:
        _report_compile(c, where)
        return EXIT_BAD_INPUT

    fns = definitions(c.ast)
    arity = {k: len(v.params) for k, v in fns.items()}

    earned, code = _earn(fns, examples or [], anchors or [], depth, where)
    if earned is None:
        return code
    trust, tally = earned

    # A program that ends in an expression is its own entry point.
    node = entry_node(c.ast) if call is None else None
    if node is not None:
        result = eval_ast(node, {}, dict(fns), 0, depth, trust)
        _show(result, quiet, _lift(result, fns, trust, tally))
        # A Z is a refusal on this path too. Returning OK here meant
        # `ezrun -e 'head([])'` printed Z and exited 0, so anything
        # scripting it read a refusal as a success.
        return EXIT_REFUSED if result.is_z else EXIT_OK

    # Definitions only. `definitions()` already has the table, so there
    # is nothing to register by walking the tree -- and walking it is
    # not harmless: eval_ast has no Program case, so the call that used
    # to sit here returned Z("cannot evaluate Program") and the result
    # was discarded, which is how it went unnoticed.
    entry = call
    if entry is None:
        if "main" in fns and not fns["main"].params:
            entry = "main()"
        else:
            names = ", ".join(sorted(fns)) or "nothing"
            print(f"ezrun: {where} defines {names} and does not say what to "
                  f"run.\n       Define main(), or pass --call 'expr'.",
                  file=sys.stderr)
            return EXIT_BAD_INPUT

    cc = compile_ever(entry, arity)
    if not cc.ok:
        _report_compile(cc, f"--call {entry!r}")
        return EXIT_BAD_INPUT

    result = eval_ast(cc.ast, {}, dict(fns), 0, depth, trust)
    _show(result, quiet, _lift(result, fns, trust, tally))
    return EXIT_REFUSED if result.is_z else EXIT_OK


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="ezrun", description="Run an EZR program.",
        epilog="A file of definitions needs an entry point: define "
               "main(), or pass --call.")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("file", nargs="?", help="program to run, or - for stdin")
    src.add_argument("-e", "--eval", metavar="EXPR",
                     help="run one expression instead of a file")
    ap.add_argument("-c", "--call", metavar="EXPR",
                    help="what to evaluate once the definitions are loaded")
    ap.add_argument("-d", "--depth", type=int, default=100,
                    help="recursion ceiling (default 100; see the module "
                         "docstring on why this is not 3)")
    ap.add_argument("-q", "--quiet", action="store_true",
                    help="print the value alone, without its confidence")
    ap.add_argument("-x", "--example", metavar="CASE", action="append",
                    default=[],
                    help="evidence, as 'f(1) = 1'. Repeatable. Passing "
                         "cases raise the function's confidence by "
                         "[EXAMPLE]: 1/1 is 120, 2/2 clears the floor at "
                         "183, 3/3 is 217")
    ap.add_argument("-a", "--anchor", metavar="NAME", action="append",
                    default=[],
                    help="anchor a function, which buys depth. Refused "
                         "unless it has cleared the execute floor and, if "
                         "recursive, has a decreasing measure")
    args = ap.parse_args(argv)

    if args.eval is not None:
        return run(args.eval, args.call, args.depth, args.quiet, "-e",
                   args.example, args.anchor)

    text = _read(args.file)
    if text is None:
        return EXIT_BAD_INPUT
    return run(text, args.call, args.depth, args.quiet, args.file,
               args.example, args.anchor)


if __name__ == "__main__":
    sys.exit(main())
