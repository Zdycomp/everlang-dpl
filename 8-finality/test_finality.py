#!/usr/bin/env python3
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "2-interpreter-python"))
from runtime import run_source
from emit import emit


def main():
    source = "ever total = 6 * 7\nshow total\n"
    expected = run_source(source).format_lines()
    passed = failed = 0

    def check(name, condition):
        nonlocal passed, failed
        if condition:
            passed += 1
            print(f"  ✓ {name}")
        else:
            failed += 1
            print(f"  ✗ {name}")

    check("Python reference executes", expected == ["total = 42 [256/256]"])
    for target, command in (("Go", "go"), ("Rust", "rustc")):
        if not shutil.which(command):
            print(f"  ~ {target} unavailable")
            continue
        code = emit(source, target.lower())
        check(f"{target} finality emitter produces code", len(code) > 100)

    ruby = subprocess.run(["ruby", "3-dsl-ruby/ever.rb"],
                          capture_output=True, text=True)
    check("Ruby DSL executes", ruby.returncode == 0)
    java_dir = Path("/tmp/ever-finality-java")
    java_dir.mkdir(exist_ok=True)
    compile_java = subprocess.run(
        ["javac", "-d", str(java_dir), *map(str, Path("5-runtime-java/com/codric/ever").glob("*.java"))],
        capture_output=True, text=True)
    check("Java runtime compiles", compile_java.returncode == 0)
    if compile_java.returncode == 0:
        run_java = subprocess.run(["java", "-cp", str(java_dir), "com.codric.ever.EverTest"],
                                  capture_output=True, text=True)
        check("Java runtime executes", run_java.returncode == 0)

    node = subprocess.run(["node", "7-refix-node/bin/refix", "finality", "examples/compound_interest.ever"],
                          capture_output=True, text=True)
    check("Node finality coordinator executes", node.returncode == 0)
    if node.returncode == 0:
        check("Node reports signature corpus", json.loads(node.stdout)["signatures"] >= 10)

    print(f"\n=== Finality layer: {passed} passed, {failed} failed ===\n")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
