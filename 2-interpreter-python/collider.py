#!/usr/bin/env python3
"""Four-lane Ever execution collider.

Each lane runs a complete lex -> parse -> semantic -> execute cycle in its own
process. Processes avoid Python's GIL and make the measured rate a real
throughput measurement rather than a thread-scheduling estimate.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List

from runtime import run_source

LANES = ("alpha", "beta", "gamma", "delta")


@dataclass
class LaneResult:
    lane: str
    ok: bool
    outputs: List[str]
    errors: List[str]
    elapsed_ns: int


def execute_lane(job: tuple[str, str, int]) -> LaneResult:
    lane, source, sequence = job
    started = time.perf_counter_ns()
    result = run_source(source)
    return LaneResult(
        lane=f"{lane}-{sequence}",
        ok=result.ok,
        outputs=result.format_lines(),
        errors=list(result.errors),
        elapsed_ns=time.perf_counter_ns() - started,
    )


def collide(source: str, rounds: int = 1, workers: int = 4) -> Dict[str, Any]:
    """Run four independent lanes and return quantified results.

    ``rounds`` repeats the same source through all four lanes. The default
    always creates exactly four executions. ``workers`` controls process
    parallelism and is capped at four so the collider remains four-wide.
    """
    if rounds < 1:
        raise ValueError("rounds must be at least 1")
    if workers < 1:
        raise ValueError("workers must be at least 1")

    jobs = [(lane, source, sequence)
            for sequence in range(rounds) for lane in LANES]
    started = time.perf_counter_ns()
    with ProcessPoolExecutor(max_workers=min(4, workers)) as pool:
        results = list(pool.map(execute_lane, jobs))
    elapsed_ns = max(1, time.perf_counter_ns() - started)

    output_signatures = {tuple(result.outputs) for result in results}
    errors = [error for result in results for error in result.errors]
    executions = len(results)
    output_lines = sum(len(result.outputs) for result in results)
    seconds = elapsed_ns / 1_000_000_000

    return {
        "lanes": len(LANES),
        "rounds": rounds,
        "workers": min(4, workers),
        "executions": executions,
        "output_lines": output_lines,
        "agreement": len(output_signatures) == 1 and not errors,
        "errors": errors,
        "elapsed_seconds": seconds,
        "executions_per_second": executions / seconds,
        "output_lines_per_second": output_lines / seconds,
        "results": [asdict(result) for result in results],
    }


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Ever four-wide collider")
    parser.add_argument("file", type=Path)
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if not args.file.exists():
        parser.error(f"no such file: {args.file}")
    report = collide(args.file.read_text(), args.rounds, args.workers)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"Collider: {report['lanes']} lanes x {report['rounds']} rounds")
        print(f"Agreement: {report['agreement']}")
        print(f"Executions: {report['executions']}")
        print(f"Output lines: {report['output_lines']}")
        print(f"Rate: {report['executions_per_second']:.2f} executions/s, "
              f"{report['output_lines_per_second']:.2f} output lines/s")
        for result in report["results"]:
            for line in result["outputs"]:
                print(f"[{result['lane']}] {line}")
    return 0 if report["agreement"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
