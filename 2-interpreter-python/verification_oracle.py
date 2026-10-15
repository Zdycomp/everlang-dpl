#!/usr/bin/env python3
"""Compile/execute verification oracle for generated Ever targets."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional

from architecture import Diagnostic, SourceMap
from emit import emit, BACKENDS
from runtime import run_source


@dataclass
class OracleResult:
    target: str
    status: str
    expected: List[str]
    actual: List[str]
    diagnostics: List[Diagnostic]
    exit_code: Optional[int] = None
    stderr: str = ""

    def to_dict(self):
        result = asdict(self)
        result["diagnostics"] = [asdict(item) for item in self.diagnostics]
        return result


def _tool(target: str) -> Optional[str]:
    return shutil.which({"go": "go", "rust": "rustc", "js": "node"}.get(target, target))


def _diagnostic(target: str, text: str, source_map: Optional[SourceMap] = None):
    line = 0
    for token in text.splitlines():
        parts = token.split(":")
        for part in parts:
            if part.isdigit():
                line = max(0, int(part) - 1)
                break
    diagnostic = Diagnostic("error", f"{target.upper()}_DIAGNOSTIC", text,
                            generated_line=line, generated_column=0)
    return source_map.remap(diagnostic) if source_map else diagnostic


def verify(source: str, target: str, timeout: int = 180) -> OracleResult:
    reference = run_source(source)
    expected = reference.format_lines() if reference.ok else []
    if not reference.ok:
        # The reference rejected the program, so no target was ever asked to agree with it.
        return OracleResult(target, "INVALID_SOURCE", expected, [],
                            [Diagnostic("error", "REFERENCE", "; ".join(reference.errors))])
    if _tool(target) is None:
        return OracleResult(target, "UNAVAILABLE", expected, [], [])

    code = emit(source, target)
    ext = BACKENDS[target].ext
    try:
        with tempfile.TemporaryDirectory(prefix="ever-oracle-") as directory:
            root = Path(directory)
            path = root / f"program.{ext}"
            path.write_text(code)
            source_map = SourceMap(file=str(path), sources=["<source>"])
            for line, _ in enumerate(code.splitlines()):
                source_map.add(line, 0, 0, 0, "0")
            if target == "go":
                compile_command = ["go", "run", str(path)]
            elif target == "rust":
                binary = root / "program"
                built = subprocess.run(["rustc", "-O", "-o", str(binary), str(path)],
                                       capture_output=True, text=True, timeout=timeout)
                if built.returncode:
                    return OracleResult(target, "BUG_DETECTED", expected, [],
                                        [_diagnostic(target, built.stderr, source_map)],
                                        built.returncode, built.stderr)
                compile_command = [str(binary)]
            elif target == "js":
                compile_command = ["node", str(path)]
            else:
                return OracleResult(target, "UNAVAILABLE", expected, [], [])
            run = subprocess.run(compile_command, capture_output=True, text=True,
                                 timeout=timeout)
            actual = [line.strip() for line in run.stdout.splitlines() if line.strip()]
            if run.returncode != 0:
                return OracleResult(target, "BUG_DETECTED", expected, actual,
                                    [_diagnostic(target, run.stderr, source_map)],
                                    run.returncode, run.stderr)
            if actual != expected:
                return OracleResult(target, "BUG_DETECTED", expected, actual,
                                    [Diagnostic("error", "OUTPUT_MISMATCH",
                                                "target output differs from reference")],
                                    run.returncode, run.stderr)
            return OracleResult(target, "PASS", expected, actual, [], run.returncode, run.stderr)
    except subprocess.TimeoutExpired:
        return OracleResult(target, "TIMEOUT", expected, [],
                            [Diagnostic("error", "TIMEOUT",
                                        f"{target} did not finish within {timeout}s")])
