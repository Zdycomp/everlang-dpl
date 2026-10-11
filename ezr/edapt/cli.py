#!/usr/bin/env python3
"""edapt — fix common mistakes across Python, JS, Go, Rust, Java, Kotlin."""
from __future__ import annotations
import argparse, sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from edapt.fixers import fix, diagnose_brackets, detect_language, LANGUAGES


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="edapt")
    p.add_argument("file")
    p.add_argument("--lang", choices=sorted(LANGUAGES))
    p.add_argument("--write", action="store_true",
                   help="apply fixes to the file in place")
    p.add_argument("-o", "--output")
    args = p.parse_args(argv)

    path = Path(args.file)
    if not path.exists():
        print(f"error: no such file: {path}", file=sys.stderr)
        return 1

    lang = args.lang or detect_language(str(path))
    if lang is None:
        print(f"error: can't detect language from '{path.suffix}'; "
             f"pass --lang", file=sys.stderr)
        return 1

    src = path.read_text()
    result = fix(src, lang)
    problems = diagnose_brackets(src, lang)

    for c in result.fixes:
        print(f"edapt: {c.line1()}")
        print(f"   {c.reason}")
    for pr in problems:
        print(f"edapt: unresolved — {pr}")
        print("   this changes program structure, so edapt reports it "
             "instead of guessing")

    if not result.fixes and not problems:
        print(f"edapt: {path} looks clean")
        return 0

    if args.write or args.output:
        out = Path(args.output) if args.output else path
        out.write_text(result.code)
        print(f"\nwrote {out}")
    elif result.fixes:
        print("\n(pass --write to apply)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
