#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "2-interpreter-python"))

from collider import LANES, collide


def main():
    passed = failed = 0

    def ok(name, condition):
        nonlocal passed, failed
        if condition:
            passed += 1
            print(f"  ✓ {name}")
        else:
            failed += 1
            print(f"  ✗ {name}")

    source = "ever total = 6 * 7\nshow total\n"
    report = collide(source)
    ok("four lanes", report["lanes"] == 4)
    ok("one round produces four executions", report["executions"] == 4)
    ok("all lanes agree", report["agreement"])
    ok("maximum output is preserved", report["output_lines"] == 4)
    ok("each lane is represented", {
        item["lane"].split("-")[0] for item in report["results"]
    } == set(LANES))
    ok("throughput is quantified", report["executions_per_second"] > 0)
    ok("output throughput is quantified", report["output_lines_per_second"] > 0)

    many = collide(source, rounds=3)
    ok("rounds scale executions", many["executions"] == 12)
    ok("rounds preserve agreement", many["agreement"])

    try:
        collide(source, rounds=0)
    except ValueError:
        ok("zero rounds rejected", True)
    else:
        ok("zero rounds rejected", False)

    print(f"\n=== Collider: {passed} passed, {failed} failed ===\n")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
