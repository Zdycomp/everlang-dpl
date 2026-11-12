"""Flare CLI: zero-ceremony build & run.

    flare run prog.fl        compile (cached) and run
    flare build prog.fl      compile to ./prog
    flare check prog.fl      parse + typecheck only, print inferred types
    flare emit prog.fl        print the generated C
    flare verify [prog.fl]   check output vs golden .expected (or whole suite);
                             --py prog.py cross-checks against CPython;
                             --gen-expected (re)writes golden files

No virtualenvs, no package manifests, no install step. One command.
"""

import difflib
import hashlib
import os
import platform
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flare.parser import parse, ParseError
from flare.infer import Inferer, CompileError
from flare.codegen import Codegen
from flare.importer import resolve_imports

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RT_DIR = os.path.join(ROOT, "rt")
CACHE = os.path.join(os.path.expanduser("~"), ".cache", "flare")


def compile_to_c(source, base_dir=None, timings=None):
    t0 = time.perf_counter()
    prog = parse(source)
    t1 = time.perf_counter()
    dep_files = []
    if base_dir is not None:
        prog, dep_files = resolve_imports(prog, base_dir)
    inferer = Inferer(prog)
    funcs, globals_ = inferer.infer()
    t2 = time.perf_counter()
    c_src = Codegen(prog, funcs, globals_, inferer.classes).gen()
    t3 = time.perf_counter()
    if timings is not None:
        timings["lex+parse"] = t1 - t0
        timings["infer"] = t2 - t1
        timings["codegen"] = t3 - t2
    return c_src, funcs, globals_, dep_files


def _cc_base_args(opt):
    """Base cc invocation. The recursion-depth counter lives in a fixed
    register on x86-64 (r15, reserved via -ffixed-r15); on other arches
    (e.g. AArch64 phones, where clang rejects global register variables)
    rt/flare_rt.h falls back to a plain global, so no flag is passed."""
    args = ["cc", "-O" + opt, "-std=gnu99"]
    if platform.machine().lower() in ("x86_64", "amd64"):
        args.append("-ffixed-r15")
    return args


def cached_build(source, base_dir, opt="2", timings=None):
    os.makedirs(CACHE, exist_ok=True)
    # cache key includes imported file contents (not just the main source)
    dep_hash = ""
    if base_dir is not None:
        prog = parse(source)
        _, dep_files = resolve_imports(prog, base_dir)
        h = hashlib.sha256()
        for f in sorted(dep_files):
            with open(f, "rb") as fh:
                h.update(fh.read())
        dep_hash = h.hexdigest()[:16]
    key = hashlib.sha256((opt + ":" + source + ":" + dep_hash).encode()).hexdigest()[:16]
    c_path = os.path.join(CACHE, key + ".c")
    exe_path = os.path.join(CACHE, key)
    if not os.path.exists(exe_path):
        t0 = time.perf_counter()
        c_src, _, _, _ = compile_to_c(source, base_dir, timings)
        with open(c_path, "w") as f:
            f.write(c_src)
        r = subprocess.run(
            _cc_base_args(opt) + ["-I", RT_DIR, c_path, "-o", exe_path, "-lm"],
            capture_output=True, text=True)
        t1 = time.perf_counter()
        if timings is not None:
            timings["cc"] = t1 - t0
        if r.returncode != 0:
            sys.stderr.write(r.stderr)
            raise CompileError("C compilation failed")
    elif timings is not None:
        # cache hit: still time the frontend stages for the report
        compile_to_c(source, base_dir, timings)
        timings["cc"] = 0.0
    return exe_path


def cmd_run(path, opt, prog_args, show_time=False):
    with open(path) as f:
        source = f.read()
    base_dir = os.path.dirname(os.path.realpath(path))
    timings = {} if show_time else None
    t0 = time.perf_counter()
    exe = cached_build(source, base_dir, opt, timings)
    t1 = time.perf_counter()
    r = subprocess.run([exe] + prog_args)
    t2 = time.perf_counter()
    if show_time:
        timings["run"] = t2 - t1
        timings["total"] = t2 - t0
        _print_timings(timings)
    return r.returncode


def cmd_verify(path, py_path=None, gen_expected=False):
    """Run a program and check its output matches the golden file (or CPython).

    Returns (passed: bool, detail: str). Golden files live next to the source
    as <name>.expected and are the frozen source of truth.
    Files named test_err_*.fl are expected to FAIL: their .expected holds the
    expected stderr text, and the gate passes when the program exits nonzero
    with that text on stderr (clean error, never a raw crash).
    """
    with open(path) as f:
        source = f.read()
    base_dir = os.path.dirname(os.path.realpath(path))
    exe = cached_build(source, base_dir, "2")
    r = subprocess.run([exe], capture_output=True, text=True)
    base = os.path.basename(path)
    expect_fail = base.startswith("test_err_")
    exp_path = os.path.splitext(path)[0] + ".expected"
    if gen_expected:
        with open(exp_path, "w") as f:
            f.write(r.stderr if expect_fail else r.stdout)
        return True, "wrote %s (verify its contents by hand!)" % exp_path
    if expect_fail:
        if r.returncode == 0:
            return False, "expected failure but exited 0"
        if r.returncode < 0:
            return False, "died by signal %d (anchor breached!)" % (-r.returncode)
        if not os.path.exists(exp_path):
            return False, "no golden file %s" % exp_path
        with open(exp_path) as f:
            expected_err = f.read().strip()
        if expected_err in r.stderr:
            return True, "clean failure as expected: %s" % expected_err
        return False, "wrong stderr:\n%s" % r.stderr
    if r.returncode != 0:
        return False, "program crashed (exit %d): %s" % (r.returncode, r.stderr.strip())
    actual = r.stdout
    if py_path:
        pr = subprocess.run(["python3", py_path], capture_output=True, text=True)
        expected = pr.stdout
        label = "CPython " + py_path
    else:
        if not os.path.exists(exp_path):
            return False, "no golden file %s (use --gen-expected to create)" % exp_path
        with open(exp_path) as f:
            expected = f.read()
        label = exp_path
    if actual == expected:
        return True, "output matches %s" % label
    diff = "".join(difflib.unified_diff(
        expected.splitlines(True), actual.splitlines(True),
        "expected", "actual"))
    return False, "MISMATCH vs %s:\n%s" % (label, diff)


def cmd_verify_suite(py_map=None, gen_expected=False):
    """Run every tests/*.fl golden test. py_map: {fl_path: py_path} for cross-checks."""
    py_map = py_map or {}
    test_dir = os.path.join(ROOT, "tests")
    files = sorted(f for f in os.listdir(test_dir) if f.endswith(".fl"))
    passed, failed = 0, []
    for f in files:
        path = os.path.join(test_dir, f)
        ok, detail = cmd_verify(path, py_map.get(path), gen_expected)
        if ok:
            passed += 1
            print("PASS %s" % f)
        else:
            failed.append(f)
            print("FAIL %s: %s" % (f, detail))
    print("%d/%d passed" % (passed, len(files)))
    return 0 if not failed else 1


def _print_timings(timings):
    sys.stderr.write("stage timings (s):\n")
    for stage in ("lex+parse", "infer", "codegen", "cc", "run", "total"):
        if stage in timings:
            tag = " (cached)" if stage == "cc" and timings[stage] == 0.0 else ""
            sys.stderr.write("  %-10s %8.4f%s\n" % (stage, timings[stage], tag))
    sys.stderr.write("stage timings (s):\n")
    for stage in ("lex+parse", "infer", "codegen", "cc", "run", "total"):
        if stage in timings:
            tag = " (cached)" if stage == "cc" and timings[stage] == 0.0 else ""
            sys.stderr.write("  %-10s %8.4f%s\n" % (stage, timings[stage], tag))


def cmd_build(path, opt, out):
    with open(path) as f:
        source = f.read()
    base_dir = os.path.dirname(os.path.realpath(path))
    c_src, _, _, _ = compile_to_c(source, base_dir)
    out = out or os.path.splitext(os.path.basename(path))[0]
    tmp_c = out + ".c"
    with open(tmp_c, "w") as f:
        f.write(c_src)
    r = subprocess.run(_cc_base_args(opt) + ["-I", RT_DIR, tmp_c, "-o", out, "-lm"],
                       capture_output=True, text=True)
    os.remove(tmp_c)
    if r.returncode != 0:
        sys.stderr.write(r.stderr)
        raise CompileError("C compilation failed")
    print("built %s" % out)


def cmd_check(path):
    with open(path) as f:
        source = f.read()
    base_dir = os.path.dirname(os.path.realpath(path))
    prog = parse(source)
    prog, _ = resolve_imports(prog, base_dir)
    funcs, globals_ = Inferer(prog).infer()
    print("globals: %s" % {k: _fmt(t) for k, t in globals_.items()})
    for name, fi in funcs.items():
        print("def %s(%s) -> %s" % (
            name,
            ", ".join("%s: %s" % (p, _fmt(t)) for p, t in zip(fi["params"], fi["param_types"])),
            _fmt(fi["ret"])))


def _fmt(t):
    if isinstance(t, tuple):
        return "list[%s]" % _fmt(t[1])
    return t


def cmd_emit(path):
    with open(path) as f:
        source = f.read()
    base_dir = os.path.dirname(os.path.realpath(path))
    c_src, _, _, _ = compile_to_c(source, base_dir)
    sys.stdout.write(c_src)


def main(argv):
    if len(argv) < 2:
        print(__doc__.strip())
        return 2
    cmd = argv[1]
    if cmd in ("--version", "-V"):
        print("0.2.0")
        return 0
    if cmd == "verify":
        # flare verify [path.fl] [--py path.py] [--gen-expected]
        path, py_path, gen = None, None, False
        rest = argv[2:]
        i = 0
        while i < len(rest):
            a = rest[i]
            if a == "--gen-expected":
                gen = True
            elif a == "--py":
                i += 1
                py_path = rest[i]
            elif a.endswith(".fl"):
                path = a
            else:
                print("unknown verify arg: %s" % a)
                return 2
            i += 1
        try:
            if path:
                ok, detail = cmd_verify(path, py_path, gen)
                print(("PASS" if ok else "FAIL") + " " + detail)
                return 0 if ok else 1
            py_map = {}
            return cmd_verify_suite(py_map, gen)
        except (ParseError, CompileError, SyntaxError) as e:
            sys.stderr.write("error: %s\n" % e)
            return 1
    if len(argv) < 3:
        print(__doc__.strip())
        return 2
    path = argv[2]
    opt = "2"
    out = None
    show_time = False
    prog_args = []
    for a in argv[3:]:
        if a.startswith("--opt="):
            opt = a.split("=", 1)[1]
        elif a == "--time":
            show_time = True
        elif a.startswith("-o"):
            out = a[2:] or None
        elif a.startswith("-"):
            print("unknown flag: %s" % a)
            return 2
        else:
            prog_args.append(a)
    try:
        if cmd == "run":
            return cmd_run(path, opt, prog_args, show_time)
        if cmd == "build":
            cmd_build(path, opt, out)
            return 0
        if cmd == "check":
            cmd_check(path)
            return 0
        if cmd == "emit":
            cmd_emit(path)
            return 0
        print("unknown command: %s" % cmd)
        return 2
    except (ParseError, CompileError, SyntaxError) as e:
        sys.stderr.write("error: %s\n" % e)
        return 1
    except FileNotFoundError:
        sys.stderr.write("error: no such file: %s\n" % path)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
