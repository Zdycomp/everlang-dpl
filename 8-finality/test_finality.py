#!/usr/bin/env python3
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
SKIP_EXIT = 77
sys.path.insert(0, str(ROOT / "2-interpreter-python"))
sys.path.insert(0, str(HERE))
from runtime import run_source
import finality


def main():
    source = "ever total = 6 * 7\nshow total\n"
    expected = [line.strip() for line in run_source(source).format_lines()]
    passed = failed = skipped = 0

    def check(name, condition):
        nonlocal passed, failed
        if condition:
            passed += 1
            print(f"  ✓ {name}")
        else:
            failed += 1
            print(f"  ✗ {name}")

    def skip(name, why):
        nonlocal skipped
        skipped += 1
        print(f"  ∼ SKIP: {name} — {why}")

    check("Python reference executes", expected == ["total = 42 [256/256]"])

    targets = finality.drive(source).get("targets", {})
    for target, label in (("go", "Go"), ("rust", "Rust")):
        data = targets.get(target, {"status": "unavailable"})
        if data["status"] == "unavailable":
            skip(f"{label} finality", "toolchain not on PATH")
        else:
            check(f"{label} compiles, runs and matches Python",
                  data["status"] == "pass" and data.get("matches_reference") is True)

    if shutil.which("ruby"):
        ruby = subprocess.run(["ruby", str(ROOT / "3-dsl-ruby" / "ever.rb")],
                              capture_output=True, text=True)
        check("Ruby DSL executes", ruby.returncode == 0)
    else:
        skip("Ruby DSL executes", "ruby not on PATH")

    if shutil.which("javac") and shutil.which("java"):
        java_src = sorted((ROOT / "5-runtime-java" / "com" / "codric" / "ever").glob("*.java"))
        with tempfile.TemporaryDirectory(prefix="ever-finality-java-") as java_dir:
            compile_java = subprocess.run(
                ["javac", "-d", java_dir, *map(str, java_src)],
                capture_output=True, text=True)
            check("Java runtime compiles", compile_java.returncode == 0)
            if compile_java.returncode == 0:
                run_java = subprocess.run(
                    ["java", "-cp", java_dir, "com.codric.ever.EverTest"],
                    capture_output=True, text=True)
                check("Java runtime executes", run_java.returncode == 0)
    else:
        skip("Java runtime", "javac or java not on PATH")

    if shutil.which("node"):
        node = subprocess.run(
            ["node", str(ROOT / "7-refix-node" / "bin" / "refix"), "finality",
             str(ROOT / "examples" / "compound_interest.ever")],
            capture_output=True, text=True)
        check("Node finality coordinator executes", node.returncode == 0)
        if node.returncode == 0:
            check("Node reports signature corpus",
                  json.loads(node.stdout)["signatures"] >= 10)
    else:
        skip("Node finality coordinator", "node not on PATH")

    print(f"\n=== Finality layer: {passed} passed, {failed} failed, "
          f"{skipped} skipped ===\n")
    if failed:
        return 1
    return SKIP_EXIT if skipped else 0


if __name__ == "__main__":
    raise SystemExit(main())
