#!/usr/bin/env python3
"""
Repo-wide integration wrapper (CLAUDE.md's "run_all.py" gate): runs each
phase's own test suite in its own toolchain and reports a summary.

    python3 run_all.py            # run everything
    python3 run_all.py --skip-native   # Python + SQL phases only (no g++/mvn/JDK needed)

Exits non-zero if any phase fails.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def jdk25_env():
    """5-runtime-java compiles to release 25; use a JDK 25 if one is installed."""
    for home in sorted(Path("/usr/lib/jvm").glob("java-25-*")) + [Path("/usr/lib/jvm/jdk-25")]:
        if (home / "bin" / "java").is_file():
            env = dict(os.environ, JAVA_HOME=str(home))
            env["PATH"] = f"{home / 'bin'}{os.pathsep}{env.get('PATH', '')}"
            return env
    return None


def run(name, cmd, cwd=None, env=None):
    print(f"\n=== {name} ===")
    print(f"$ {' '.join(cmd)}" + (f"  (in {cwd})" if cwd else ""))
    result = subprocess.run(cmd, cwd=cwd or ROOT, env=env)
    ok = result.returncode == 0
    print(f"--- {name}: {'PASS' if ok else 'FAIL'} (exit {result.returncode}) ---")
    return ok


def main():
    skip_native = "--skip-native" in sys.argv
    results = {}

    results["python-frontend (everlang_standalone)"] = run(
        "python-frontend (everlang_standalone)",
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
        cwd=ROOT / "everlang_standalone",
    )

    if (ROOT / "4-archive-sql").is_dir():
        results["archive-sql (4-archive-sql)"] = run(
            "archive-sql (4-archive-sql)",
            [sys.executable, "-m", "unittest", "discover", "-s", "4-archive-sql/tests", "-t", "."],
            cwd=ROOT,
        )

    if not skip_native and (ROOT / "1-phase-cpp").is_dir():
        if shutil.which("g++"):
            results["cpp-analysis (1-phase-cpp)"] = run(
                "cpp-analysis (1-phase-cpp)", ["make", "test"], cwd=ROOT / "1-phase-cpp"
            )
        else:
            print("\n=== cpp-analysis (1-phase-cpp) ===\nSKIPPED: g++ not found")

    if not skip_native and (ROOT / "5-runtime-java").is_dir():
        if shutil.which("mvn"):
            results["java-runtime (5-runtime-java)"] = run(
                "java-runtime (5-runtime-java)",
                ["mvn", "-q", "-f", "5-runtime-java/pom.xml", "test"],
                cwd=ROOT,
                env=jdk25_env(),
            )
        else:
            print("\n=== java-runtime (5-runtime-java) ===\nSKIPPED: mvn not found")

    if not skip_native and (ROOT / "6-android-kotlin").is_dir():
        if shutil.which("java"):
            results["kotlin-dna (6-android-kotlin)"] = run(
                "kotlin-dna (6-android-kotlin)",
                ["./gradlew", "--console=plain", ":core:test", ":predict:test", ":fuzz:test"],
                cwd=ROOT / "6-android-kotlin",
            )
        else:
            print("\n=== kotlin-dna (6-android-kotlin) ===\nSKIPPED: java not found")

    if not skip_native and (ROOT / "ezr").is_dir():
        results["ezr-lineage (ezr)"] = run(
            "ezr-lineage (ezr)", [sys.executable, "tests/run_all.py"], cwd=ROOT / "ezr"
        )

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for name, ok in results.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")

    if not results:
        print("  (nothing ran)")
        return 1
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
