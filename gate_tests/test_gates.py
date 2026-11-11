import importlib.util
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
EZR = ROOT / "ezr"


def _load_ezr_suites():
    spec = importlib.util.spec_from_file_location("ezr_run_all", EZR / "tests" / "run_all.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.SUITES


EZR_SUITES = _load_ezr_suites()


def _require(*tools):
    missing = [t for t in tools if shutil.which(t) is None]
    if missing:
        pytest.skip(f"toolchain absent: {', '.join(missing)}")


def _run(cmd, cwd, shell=False):
    r = subprocess.run(cmd, cwd=cwd, shell=shell, capture_output=True, text=True, timeout=900)
    assert r.returncode == 0, f"exit {r.returncode}\n{(r.stdout + r.stderr)[-4000:]}"


def test_cpp_verify_particle():
    _require("make", "g++")
    _run(["make", "test"], ROOT / "1-phase-cpp")


def test_java_self_healing_audit():
    _require("mvn")
    version = subprocess.run(["mvn", "-v"], capture_output=True, text=True).stdout
    found = re.search(r"Java version: (\d+)", version)
    if found and int(found.group(1)) < 25:
        pytest.fail(f"Maven runs on JDK {found.group(1)}; 5-runtime-java needs JDK 25. Point JAVA_HOME at a JDK 25.")
    _run(["mvn", "-q", "-f", "5-runtime-java/pom.xml", "test"], ROOT)


def test_everlang_pyflakes():
    if importlib.util.find_spec("pyflakes") is None:
        pytest.skip("pyflakes not installed")
    _run([sys.executable, "-m", "pyflakes", "everlang_standalone"], ROOT)


@pytest.mark.parametrize(
    "command", [cmd for _, cmd in EZR_SUITES], ids=[label for label, _ in EZR_SUITES]
)
def test_ezr_suite(command):
    if command.startswith(("gcc", "g++")):
        _require("gcc", "g++")
    _run(command, EZR, shell=True)


def test_ezr_java_runtime():
    _require("javac", "java")
    layer = EZR / "5-runtime-java"
    _run(["bash", "build.sh"], layer)
    _run(["java", "-cp", "out", "com.codric.ezr.RuntimeTest"], layer)


def test_ezr_kitchen_sink_sanitizers(tmp_path):
    _require("gcc")
    exe = tmp_path / "kitchen_sink_asan"
    sources = [
        f"0-atom-c/{name}.c"
        for name in ("kitchen_sink", "form", "form_lower", "tac", "scope", "ir", "evalue", "tapestry")
    ]
    # Without -fno-sanitize-recover, UBSan reports a finding and the program still exits 0.
    _run(
        ["gcc", "-std=c99", "-g", "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
         "-o", str(exe), *sources, "-lm"],
        EZR,
    )
    _run([str(exe)], EZR)
