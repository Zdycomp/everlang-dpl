#!/usr/bin/env python3
"""
ever_cli.py — Ever / Tapestry, the command-line entry point.

Before this file, there was no way to run a .ever file. Every
execution path in this project went through test-harness internals.
This is the real front door: `ever run program.ever`.

Codric Enterprise · Ricky (Dreid) · 2026
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from runtime import run_source
from profiler import Profiler

PROFILE_PATH = Path.home() / ".ever" / "profile.json"


def _scaffold_note(scaffold: str) -> str:
    notes = {
        "full":    "Every value below shows its confidence out of 256 "
                   "— how much the program trusts what it just "
                   "computed. 256 means certain; lower means built "
                   "from something uncertain, like z.",
        "guided":  "Confidence is shown as [n/256] next to each value.",
    }
    return notes.get(scaffold, "")


def cmd_run(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if not path.exists():
        print(f"error: no such file: {path}", file=sys.stderr)
        return 1

    source = path.read_text()

    profiler = None
    if not args.no_profile:
        PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        profiler = Profiler(path=PROFILE_PATH)

    result = run_source(source, profiler=profiler)

    if result.corrections:
        lvl = result.scaffold or "full"
        if lvl in ("full", "guided"):
            for c in result.corrections:
                print(f"E: {c.full() if lvl=='full' else c.line1()}")
            print()
        elif lvl == "hints":
            print(f"E: {len(result.corrections)} thing(s) assumed "
                 f"({', '.join(c.line1() for c in result.corrections[:2])}"
                 f"{'...' if len(result.corrections) > 2 else ''})")
        elif args.explain:
            for c in result.corrections:
                print(f"E: {c.line1()}")

    if not result.ok:
        for e in result.errors:
            print(f"error: {e}", file=sys.stderr)
        return 1

    for r in result.recoveries:
        print(f"note: {r}")

    if args.quiet:
        for sv in result.shown:
            from runtime import _format_value
            line = _format_value(sv.name, sv.value, sv.confidence)
            # strip the trailing [n/256] for quiet mode
            print(line.split(" [")[0])
    else:
        # --explain always explains, whatever the band. Otherwise the
        # note appears only for bands that want scaffolding.
        note = (_scaffold_note("full") if args.explain
                else _scaffold_note(result.scaffold or ""))
        if note:
            print(note)
            print()
        for line in result.format_lines():
            print(line)

    if profiler is not None:
        profiler.save()

    return 0


def cmd_build(args: argparse.Namespace) -> int:
    """Transpile a .ever program to Go, Rust, R, or Kotlin."""
    from emit import emit, BACKENDS
    path = Path(args.file)
    if not path.exists():
        print(f"error: no such file: {path}", file=sys.stderr)
        return 1
    try:
        code = emit(path.read_text(), args.target)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    ext = BACKENDS[args.target].ext
    out = Path(args.output) if args.output else path.with_suffix("." + ext)
    out.write_text(code)
    print(f"wrote {out}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    """Parse and type-check without running — for editors/CI."""
    path = Path(args.file)
    if not path.exists():
        print(f"error: no such file: {path}", file=sys.stderr)
        return 1
    from syntax import parse, Semantic, Program

    source = path.read_text()
    node, perr = parse(source)
    if perr is not None:
        print(f"parse error: {perr}", file=sys.stderr)
        return 1
    prog = node if isinstance(node, Program) else Program([node])
    pa = Semantic(source=source).analyse_program(prog)
    if not pa.clean:
        for e in pa.errors:
            print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"OK — {len(prog.statements)} statement(s), "
          f"{len(pa.bound)} binding(s), {len(pa.shown)} shown")
    return 0


def cmd_profile(args: argparse.Namespace) -> int:
    if not PROFILE_PATH.exists():
        print("No profile yet — run a program first.")
        return 0
    p = Profiler(path=PROFILE_PATH)
    print(p.report())
    return 0


def cmd_repl(args: argparse.Namespace) -> int:
    profiler = None
    if not args.no_profile:
        PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        profiler = Profiler(path=PROFILE_PATH)

    from scope import make_global_scope
    g = make_global_scope()
    print("Ever REPL — one statement per line "
         "(let/ever/show/def, or a bare expression). Ctrl-D to exit.")
    while True:
        try:
            line = input("ever> ")
        except EOFError:
            print()
            break
        if not line.strip():
            continue

        result = run_source(line, profiler=profiler, scope=g)
        if not result.ok:
            for e in result.errors:
                print(f"error: {e}")
            continue
        for l in result.format_lines():
            print(l)

    if profiler is not None:
        profiler.save()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ever", description="Ever / Tapestry — a confidence-tracking "
                                 "programming language.")
    sub = p.add_subparsers(dest="command", required=True)

    pr = sub.add_parser("run", help="run a .ever file")
    pr.add_argument("file")
    pr.add_argument("--no-profile", action="store_true",
                    help="don't read or update the proficiency profile")
    pr.add_argument("--quiet", action="store_true",
                    help="print values only, no confidence readout")
    pr.add_argument("--explain", action="store_true",
                    help="show a one-line note on what confidence means "
                         "(only shown at Novice/Learner proficiency)")
    pr.set_defaults(func=cmd_run)

    pc = sub.add_parser("check", help="parse and type-check without running")
    pc.add_argument("file")
    pc.set_defaults(func=cmd_check)

    pb = sub.add_parser("build", help="transpile to Go, Rust, R, or Kotlin")
    pb.add_argument("file")
    pb.add_argument("--target", "-t", required=True,
                    choices=["go", "rust", "r", "kotlin", "js"])
    pb.add_argument("--output", "-o")
    pb.set_defaults(func=cmd_build)

    pp = sub.add_parser("profile", help="show your proficiency profile")
    pp.set_defaults(func=cmd_profile)

    pl = sub.add_parser("repl", help="interactive Ever session")
    pl.add_argument("--no-profile", action="store_true")
    pl.set_defaults(func=cmd_repl)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except BrokenPipeError:
        # `ever run x | head` closes the pipe early. Exit quietly
        # instead of dumping a traceback.
        try:
            sys.stdout.close()
        except Exception:
            pass
        return 0
    except KeyboardInterrupt:
        print()
        return 130


if __name__ == "__main__":
    sys.exit(main())
