#!/usr/bin/env python3
"""test_backends.py — every transpiler target must agree with Ever.

Compiles each integration program to Go, Rust, Kotlin and JavaScript, runs the
result, and diffs it against what Ever itself produced. A backend that
merely compiles proves nothing; a backend that computes 88 where Ever
says z has broken the one guarantee the language makes.

Targets whose toolchain isn't installed are skipped and reported as
skipped — never as passing. Toolchains are found on PATH (run_all.py puts
EVER_TOOLCHAIN_PATH in front of it).

Ever runs and emits in the main thread, because run_source keeps per-run
state. Only the compile-and-run subprocesses go to a thread pool, and the
results are printed in the same fixed order as a sequential run. Every
toolchain gets the job's own temporary directory, Java's included, so no
compiler writes to the system temp directory.
"""

import os, re, shutil, subprocess, sys, tempfile, threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "2-interpreter-python"))

from runtime import run_source
from emit import emit, BACKENDS

WORKERS = max(1, min(6, os.cpu_count() or 2))
# Each kotlinc is a JVM of several hundred megabytes: two at a time.
KOTLIN_SLOTS = threading.BoundedSemaphore(2)


def have(cmd):
    return shutil.which(cmd) is not None

TOOLS = {
    "go":     ("go",      lambda: have("go")),
    "rust":   ("rustc",   lambda: have("rustc")),
    "kotlin": ("kotlinc", lambda: have("kotlinc") and have("java")),
    "js":     ("node",    lambda: have("node")),
}


def job_env(tmp):
    """The environment for one job: its own temp directory, Java's included."""
    env = dict(os.environ)
    env["TMPDIR"] = tmp
    env["JAVA_OPTS"] = (env.get("JAVA_OPTS", "") + f" -Djava.io.tmpdir={tmp}").strip()
    return env


def error_text(stderr):
    """The compiler's own error, without the JVM's JAVA_TOOL_OPTIONS banner,
    which would otherwise be the first line and hide the real message."""
    lines = [l for l in stderr.splitlines()
             if l.strip() and not l.startswith("Picked up ")]
    return "\n".join(lines)[:300] or stderr[:300]


def run_target(target, code, tmp):
    """Compile+run emitted code, return stdout lines."""
    ext = BACKENDS[target].ext
    src = os.path.join(tmp, f"prog.{ext}")
    with open(src, "w") as f:
        f.write(code)
    env = job_env(tmp)

    def run(cmd, timeout):
        return subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout, env=env)

    if target == "go":
        r = run(["go", "run", src], 180)
    elif target == "rust":
        exe = os.path.join(tmp, "prog")
        c = run(["rustc", "-O", "-o", exe, src], 240)
        if c.returncode:
            return None, error_text(c.stderr)
        r = run([exe], 120)
    elif target == "kotlin":
        jar = os.path.join(tmp, "prog.jar")
        with KOTLIN_SLOTS:
            c = run(["kotlinc", src, "-include-runtime", "-d", jar], 600)
        if c.returncode:
            return None, error_text(c.stderr)
        r = run(["java", f"-Djava.io.tmpdir={tmp}", "-jar", jar], 180)
    elif target == "js":
        r = run(["node", src], 120)
    else:
        return None, "unknown target"

    if r.returncode:
        return None, error_text(r.stderr)
    return [l.strip() for l in r.stdout.splitlines() if l.strip()], None


def run_kotlin_batch(codes):
    """Every Kotlin program in one kotlinc call, each in its own package, then
    each main run on its own. Starting kotlinc's JVM costs more than compiling a
    program, so this pays it once. If the batch does not compile, each program is
    compiled alone, so the failure is reported against the program that caused it."""
    with tempfile.TemporaryDirectory() as tmp:
        env = job_env(tmp)
        srcs = []
        for i, code in enumerate(codes):
            path = os.path.join(tmp, f"Prog{i}.kt")
            with open(path, "w") as f:
                f.write(f"package ev{i}\n\n{code}")
            srcs.append(path)
        jar = os.path.join(tmp, "all.jar")
        c = subprocess.run(["kotlinc", *srcs, "-include-runtime", "-d", jar],
                           capture_output=True, text=True, timeout=900, env=env)
        if c.returncode:
            results = []
            for code in codes:
                with tempfile.TemporaryDirectory() as one:
                    results.append(run_target("kotlin", code, one))
            return results
        results = []
        for i in range(len(codes)):
            r = subprocess.run(["java", f"-Djava.io.tmpdir={tmp}", "-cp", jar, f"ev{i}.Prog{i}Kt"],
                               capture_output=True, text=True, timeout=180, env=env)
            if r.returncode:
                results.append((None, error_text(r.stderr)))
            else:
                results.append(([l.strip() for l in r.stdout.splitlines() if l.strip()], None))
        return results


def norm(lines):
    return [re.sub(r"\s+", " ", l).strip() for l in lines]


# Regression programs for defects that shipped in the emitted runtimes
# and that the integration corpus never exercised. Kept inline rather
# than added to tests/integration/, because ev_integrate.py and
# gold_check.py also read that directory and pair every .ever with a
# canonical .expected file.
REGRESSIONS = {
    # TEXT's only defined operator is '+'. Everything else fell through
    # to the numeric path, where a text value's number is 0: "ab"+"cd"
    # came out as 0 (Go) / NaN (JS), and "ab"=="ab" answered true at
    # 256/256 where Ever answers z.
    "text_ops": 'ever cat = "ab" + "cd"\n'
                'ever same = "ab" == "ab"\n'
                'ever diff = "ab" == "zz"\n'
                'show cat\nshow same\nshow diff\n',

    # A branch can never be more certain than the condition that chose
    # it. cond() returned the taken branch untouched, so this reported
    # 256/256 where Ever reports 0/256.
    "cond_confidence": 'ever c = if z then 1 else 2\n'
                       'ever u = z\n'
                       'ever t = if u then "a" else "b"\n'
                       'ever n = if true then 1 else 2\n'
                       'show c\nshow t\nshow n\n',

    # Ever allows re-binding; Go's :=, JS's const and Kotlin's val each
    # allow it once, so this emitted code that would not compile.
    "rebinding": 'let x = 1\never x = x + 1\never x = x * 10\nshow x\n',

    # Every backend interpolated the raw text between quotes, and Go
    # built the literal with repr() then replaced ' with ", so
    # "it's fine" became "it"s fine".
    "quoting": 'ever s = "it\'s fine"\n'
               'ever d = "cost $5"\n'
               'show s\nshow d\n',
}


def main():
    programs = sorted((ROOT / "tests" / "integration").glob("*.ever"))
    targets = [t for t in BACKENDS if TOOLS[t][1]()]
    skipped = [t for t in BACKENDS if not TOOLS[t][1]()]

    print(f"\n=== Backend agreement: {len(programs)} programs "
          f"x {len(targets)} targets ===\n")
    for t in skipped:
        print(f"  ~ SKIP {t} ({TOOLS[t][0]} not installed)")

    # (label, source, regression): an integration program that Ever itself
    # cannot run, or that a backend declines to emit, is a skip; a
    # regression program in either state is a failure.
    cases = [(p.stem, p.read_text(), False) for p in programs]
    cases += [(label, src, True) for label, src in REGRESSIONS.items()]

    npass = nfail = nskip = 0
    jobs = []          # (label, target, code, expected), in print order
    for label, src, regression in cases:
        ref = run_source(src)
        if not ref.ok:
            if regression:
                print(f"  x FAIL {label:22} Ever itself errors: {ref.errors}")
                nfail += 1
            else:
                print(f"  ~ SKIP {label} (Ever itself errors)")
                nskip += 1
            continue
        expected = norm(ref.format_lines())
        for target in targets:
            try:
                code = emit(src, target)
            except NotImplementedError as exc:
                if regression:
                    print(f"  x FAIL {label:22} {target:7} emit: {exc}")
                    nfail += 1
                else:
                    print(f"  ~ SKIP {label:22} {target:7} ({exc})")
                    nskip += 1
                continue
            except Exception as exc:
                print(f"  x FAIL {label:22} {target:7} emit: {exc}")
                nfail += 1
                continue
            jobs.append((label, target, code, expected))

    def compile_and_run(job):
        _, target, code, _ = job
        with tempfile.TemporaryDirectory() as tmp:
            return run_target(target, code, tmp)

    kotlin = [i for i, j in enumerate(jobs) if j[1] == "kotlin"]
    others = [i for i, j in enumerate(jobs) if j[1] != "kotlin"]
    outcomes = [None] * len(jobs)
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        batch = pool.submit(run_kotlin_batch, [jobs[i][2] for i in kotlin]) if kotlin else None
        futures = {i: pool.submit(compile_and_run, jobs[i]) for i in others}
        for i, f in futures.items():
            outcomes[i] = f.result()
        if batch is not None:
            for i, result in zip(kotlin, batch.result()):
                outcomes[i] = result

    for (label, target, _, expected), (got, err) in zip(jobs, outcomes):
        if err:
            print(f"  x FAIL {label:22} {target:7} {err.splitlines()[0][:70]}")
            nfail += 1
            continue
        if norm(got) != expected:
            print(f"  x FAIL {label:22} {target:7} output differs")
            for g, exp in zip(norm(got), expected):
                if g != exp:
                    print(f"        ever: {exp}")
                    print(f"        {target:4}: {g}")
                    break
            nfail += 1
            continue
        print(f"  . OK   {label:22} {target}")
        npass += 1

    print(f"\n{'-'*54}")
    print(f"  {npass} passed  {nfail} failed"
          + (f"  ({len(skipped)} target(s) skipped)" if skipped else "")
          + (f"  ({nskip} comparison(s) skipped)" if nskip else ""))
    print(f"{'-'*54}\n")
    if nfail:
        return 1
    # Skipped comparisons are never a pass. 77 tells run_all.py so.
    return 77 if (skipped or nskip) else 0


if __name__ == "__main__":
    sys.exit(main())
