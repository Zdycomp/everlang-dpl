#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "2-interpreter-python"))
from architecture import (CorrectionStatus, Diagnostic, SourceMap,
                          compile_pipeline, correction_loop)


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
    explicit = SourceMap(file="program.go", sources=["<source>"])
    explicit.add(3, 0, 1, 0, "0.statements[0]:Let")
    explicit.add(3, 4, 2, 2, "0.statements[1]:Show")
    at_start = explicit.remap(Diagnostic("error", "X", "m", 3, 0))
    ok("a column maps to the mapping at or before it",
       at_start.node_id == "0.statements[0]:Let" and at_start.original_line == 1)
    later = explicit.remap(Diagnostic("error", "X", "m", 3, 5))
    ok("a later column maps to the nearest mapping before it",
       later.node_id == "0.statements[1]:Show" and later.original_line == 2
       and later.original_column == 2)

    mapped = result.source_maps["go"].remap(Diagnostic("error", "COMPILE", "bad", 0, 0))
    ok("pipeline diagnostics point at the IR root", mapped.node_id == result.ir.node_id)

    bad = compile_pipeline("ever broken = 1 +\n", ["go"])
    ok("parse failure becomes diagnostic", any(d.code == "PARSE" for d in bad.diagnostics))
    ok("parse failure preserves CST error", bad.cst.error)
    ok("parse failure has no IR node to point at",
       all(d.node_id is None for d in bad.diagnostics if d.code == "PARSE"))
    ok("error lines are errors, not missing tokens",
       all(c.error and not c.missing for c in bad.cst.children))

    cycles = correction_loop("ever total = 6 * 7\nshow total\n", "go",
                             lambda code, target: [], max_cycles=3)
    ok("verification converges", cycles[-1].status == CorrectionStatus.CONVERGED)
    ok("cycle cap is bounded", len(cycles) <= 3)

    stalled = correction_loop("ever broken = 1 +\n", "go",
                              lambda code, target: [], max_cycles=2)
    ok("unrepairable input stalls", stalled[-1].status == CorrectionStatus.STALLED)

    def always_fails(code, target):
        return [Diagnostic("error", "RUN", "boom")]

    endless = correction_loop("ever total = 6 * 7\nshow total\n", "go",
                              always_fails, lambda code, diags: code + "\n",
                              max_cycles=2)
    ok("a failing cycle that is refined is BUG_DETECTED",
       endless[0].status == CorrectionStatus.BUG_DETECTED and endless[0].changed)
    ok("running out of budget is EXHAUSTED, not an open refinement",
       [c.status for c in endless] == [CorrectionStatus.BUG_DETECTED,
                                       CorrectionStatus.EXHAUSTED])

    unchanged = correction_loop("ever total = 6 * 7\nshow total\n", "go",
                                always_fails, lambda code, diags: code, max_cycles=3)
    ok("a failing cycle that cannot be refined is STALLED",
       [c.status for c in unchanged] == [CorrectionStatus.STALLED])

    print(f"\n=== Architecture: {passed} passed, {failed} failed ===\n")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
