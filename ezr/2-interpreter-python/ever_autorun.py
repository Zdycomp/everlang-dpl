#!/usr/bin/env python3
"""Run Ever (.ever) programs unattended and report each result as one JSON line.

Usage:
    python3 ever_autorun.py [--timeout SECONDS] PATH [PATH ...]

PATH may be a .ever file or a directory, searched recursively for .ever files.
Each program runs through runtime.run_source (the same front door as
`ever run`), with the profiler off so no ~/.ever state is written and nothing
prompts. One JSON object per program on stdout:

    {"file": ..., "status": "ok" | "error" | "timeout" | "unreadable",
     "shown": [{"name": ..., "value": ..., "confidence": ...}],
     "errors": [...], "recoveries": [...]}

Exit status: 0 if every program is "ok", 1 otherwise, 2 on bad arguments.
"""
import argparse
import json
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from runtime import run_source  # noqa: E402


class _Timeout(Exception):
    pass


def _alarm(signum, frame):
    raise _Timeout()


def find_programs(paths):
    """Expand directories to their .ever files; keep explicit files as given."""
    for p in paths:
        path = Path(p)
        if path.is_dir():
            yield from sorted(path.rglob("*.ever"))
        else:
            yield path


def run_one(path: Path, timeout: int) -> dict:
    record = {"file": str(path), "status": "ok", "shown": [],
              "errors": [], "recoveries": []}
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        record.update(status="unreadable", errors=[str(exc)])
        return record

    # SIGALRM is Unix-only; without it the timeout is not enforced.
    armed = hasattr(signal, "SIGALRM")
    if armed:
        signal.signal(signal.SIGALRM, _alarm)
        signal.alarm(timeout)
    try:
        result = run_source(source, profiler=None)
    except _Timeout:
        record.update(status="timeout", errors=[f"exceeded {timeout}s"])
        return record
    except Exception as exc:  # an interpreter crash is a result, not a stop
        record.update(status="error", errors=[f"{type(exc).__name__}: {exc}"])
        return record
    finally:
        if armed:
            signal.alarm(0)

    record["shown"] = [{"name": sv.name, "value": str(sv.value),
                        "confidence": sv.confidence} for sv in result.shown]
    record["errors"] = list(result.errors)
    record["recoveries"] = list(result.recoveries)
    if not result.ok:
        record["status"] = "error"
    return record


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--timeout", type=int, default=30,
                    help="seconds allowed per program (default 30)")
    args = ap.parse_args(argv)
    if args.timeout <= 0:
        ap.error("--timeout must be positive")

    programs = list(find_programs(args.paths))
    if not programs:
        print("ever_autorun: no .ever files found", file=sys.stderr)
        return 2

    all_ok = True
    for path in programs:
        record = run_one(path, args.timeout)
        all_ok &= record["status"] == "ok"
        print(json.dumps(record, ensure_ascii=False), flush=True)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
