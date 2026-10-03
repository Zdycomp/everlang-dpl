#!/usr/bin/env python3
"""Layer 8 finality drive.

Python remains the semantic reference. Rust and Go are release targets. This
runner emits both, compiles/runs every available target, and compares output
against Python so finality means agreement, not merely compilation.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "2-interpreter-python"))
from emit import emit  # noqa: E402
from runtime import run_source  # noqa: E402


def run_target(target: str, source: str, temp: Path):
    code = emit(source, target)
    ext = "go" if target == "go" else "rs"
    src = temp / f"program.{ext}"
    src.write_text(code)
    if target == "go":
        command = ["go", "run", str(src)]
    else:
        binary = temp / "program"
        built = subprocess.run(["rustc", "-O", "-o", str(binary), str(src)],
                               capture_output=True, text=True, timeout=180)
        if built.returncode:
            return False, [], built.stderr[-1000:]
        command = [str(binary)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=180)
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return result.returncode == 0, lines, result.stderr[-1000:]


def drive(source: str):
    reference = run_source(source)
    expected = [line.strip() for line in reference.format_lines()]
    report = {"reference_ok": reference.ok, "expected": expected, "targets": {}}
    if not reference.ok:
        report["errors"] = reference.errors
        return report
    with tempfile.TemporaryDirectory(prefix="ever-finality-") as directory:
        temp = Path(directory)
        for target in ("go", "rust"):
            available = shutil.which(target if target == "go" else "rustc") is not None
            if not available:
                report["targets"][target] = {"status": "unavailable"}
                continue
            try:
                ok, actual, error = run_target(target, source, temp)
                report["targets"][target] = {
                    "status": "pass" if ok and actual == expected else "fail",
                    "output": actual,
                    "matches_reference": actual == expected,
                    "error": error,
                }
            except Exception as exc:
                report["targets"][target] = {"status": "error", "error": str(exc)}
    report["finality"] = all(
        data.get("status") == "pass"
        for data in report["targets"].values()
        if data.get("status") != "unavailable"
    )
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run Ever's Rust/Go finality drive")
    parser.add_argument("file", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if not args.file.exists():
        parser.error(f"no such file: {args.file}")
    report = drive(args.file.read_text())
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"Finality reference: {'pass' if report['reference_ok'] else 'fail'}")
        for target, data in report.get("targets", {}).items():
            print(f"{target}: {data['status']}")
        print(f"Finality: {'pass' if report.get('finality') else 'fail'}")
    return 0 if report.get("finality", False) else 1


if __name__ == "__main__":
    raise SystemExit(main())
