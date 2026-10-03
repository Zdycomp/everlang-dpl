#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "2-interpreter-python"))
from architecture import (CorrectionStatus, compile_pipeline, correction_loop)


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

    result = compile_pipeline("ever total = 6 * 7\nshow total\n", ["go", "rust"])
    ok("front end builds a CST", result.cst.kind == "SOURCE")
    ok("canonical IR exists", result.ir is not None)
    ok("targets emit", set(result.generated) == {"go", "rust"})
    ok("source maps emit", set(result.source_maps) == {"go", "rust"})
    ok("VLQ mappings emit", all(isinstance(m.to_dict()["mappings"], str)
                                 for m in result.source_maps.values()))

    bad = compile_pipeline("ever broken = 1 +\n", ["go"])
    ok("parse failure becomes diagnostic", any(d.code == "PARSE" for d in bad.diagnostics))
    ok("parse failure preserves CST error", bad.cst.error)

    cycles = correction_loop("ever total = 6 * 7\nshow total\n", "go",
                             lambda code, target: [], max_cycles=3)
    ok("verification converges", cycles[-1].status == CorrectionStatus.CONVERGED)
    ok("cycle cap is bounded", len(cycles) <= 3)

    stalled = correction_loop("ever broken = 1 +\n", "go",
                              lambda code, target: [], max_cycles=2)
    ok("unrepairable input stalls", stalled[-1].status == CorrectionStatus.STALLED)

    print(f"\n=== Architecture: {passed} passed, {failed} failed ===\n")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
