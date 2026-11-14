"""Characterization snapshot of the Python front door.

Records what every front-door entry returns (or raises) over the 13
integration programs and a set of edge sources. The front-door refactor must
reproduce every recording exactly. Two modes:

    python3 tests/front_door_snapshot.py --record   write the baseline
    python3 tests/front_door_snapshot.py --check    compare against it

Exit 0 when the recordings match, 1 when they differ, 77 when the baseline
has not been recorded yet (run --record first).
"""

import contextlib
import dataclasses
import enum
import glob
import hashlib
import io
import json
import os
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "2-interpreter-python"))

BASELINE = os.path.join(ROOT, "tests", "front_door", "baseline.json")
SKIP_EXIT = 77

EDGE_SOURCES = [
    "", "   ", "1 +", "a $ b", "(((", "let x = ", ";;;", '"open',
    'heal (1 / zero) using ("p") fallback (3)', "def f(n) = ", "if z then",
    "[1, 2", "9@", "xs[", "example f(0) = 1", "anchor", "é中", "\x00",
    "def f(n) = missing", 'def g(n) = if n then "yes" else 3',
    "def h(n) = n / 0", "def k(n) = f(n, n)",
    "def fact(n) = if n <= 1 then 1 else n * fact(n - 1)",
    "def grow(n) = if n > 99 then n else grow(n + 1)",
    "def bad(n) = n + true", "1 + 1",
    "(" * 300 + "1" + ")" * 300,
]


# Fields that hold wall-clock time or per-process run identity. Their values
# are not behaviour, so the snapshot keeps the field and masks the value.
TIME_FIELDS = frozenset({
    "born_ms", "run_id", "ts_ms", "captured_ms", "last_seen", "ms",
    "elapsed_ns", "started",
})


def plain(x, seen=None, depth=0):
    """A deterministic, JSON-safe rendering of any result object."""
    seen = set() if seen is None else seen
    if depth > 400:
        return "<depth>"
    if x is None or isinstance(x, (bool, int, str)):
        return x
    if isinstance(x, float):
        return ("float", repr(x))
    if isinstance(x, enum.Enum):
        return {"__enum__": type(x).__name__, "value": plain(x.value, seen, depth + 1)}
    if isinstance(x, bytes):
        return {"__bytes__": x.hex()}
    if isinstance(x, (list, tuple)):
        return [plain(i, seen, depth + 1) for i in x]
    if isinstance(x, dict):
        return {str(k): plain(v, seen, depth + 1)
                for k, v in sorted(x.items(), key=lambda kv: str(kv[0]))}
    if isinstance(x, (set, frozenset)):
        return sorted((plain(i, seen, depth + 1) for i in x), key=repr)
    if callable(x) and not hasattr(x, "__dict__"):
        return {"__callable__": getattr(x, "__qualname__", "?")}
    if id(x) in seen:
        return {"__cycle__": type(x).__name__}
    seen = seen | {id(x)}
    if dataclasses.is_dataclass(x):
        names = [f.name for f in dataclasses.fields(x)]
    elif hasattr(x, "__dict__"):
        names = sorted(k for k in vars(x) if not k.startswith("__"))
    else:
        return {"__repr__": repr(x)}
    out = {"__type__": type(x).__name__}
    for name in names:
        if name in TIME_FIELDS:
            out[name] = "<time>"
        else:
            out[name] = plain(getattr(x, name), seen, depth + 1)
    return out


def _outcome(fn, src):
    """Run one entry on one source. An exception is part of the behaviour."""
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            value = fn(src)
        return {"returned": plain(value), "stdout": buf.getvalue()}
    except Exception as exc:  # noqa: BLE001 — every raise is recorded, not hidden
        return {"raised": type(exc).__name__, "message": str(exc),
                "stdout": buf.getvalue()}


def entries():
    import architecture
    import forgive
    import ir
    import runtime
    import syntax

    def run_source_isolated(src):
        import repair
        with tempfile.TemporaryDirectory(prefix="fd-snap-") as tmp:
            prev_env = os.environ.get("EVER_REPAIR_STORE")
            os.environ["EVER_REPAIR_STORE"] = tmp
            repair.use_registry(repair.RepairRegistry(archive_dir=tmp))
            try:
                return runtime.run_source(src)
            finally:
                repair.use_registry(None)
                if prev_env is None:
                    os.environ.pop("EVER_REPAIR_STORE", None)
                else:
                    os.environ["EVER_REPAIR_STORE"] = prev_env

    return {
        "parse": syntax.parse,
        "parse_forgiving": forgive.parse_forgiving,
        "compile_ever": syntax.compile_ever,
        "parse_to_ir": ir.parse_to_ir,
        "run_source": run_source_isolated,
        "compile_pipeline": architecture.compile_pipeline,
        "front_end": architecture.front_end,
    }


def corpus():
    """(key, source) pairs: the 13 integration programs, then the edge sources."""
    items = []
    for path in sorted(glob.glob(os.path.join(ROOT, "tests", "integration", "*.ever"))):
        with open(path, encoding="utf-8") as f:
            items.append((os.path.relpath(path, ROOT), f.read()))
    for i, src in enumerate(EDGE_SOURCES):
        items.append((f"edge:{i}", src))
    return items


def record():
    table = entries()
    result = {}
    for key, src in corpus():
        digest = hashlib.sha256(src.encode("utf-8", "surrogatepass")).hexdigest()
        row = {"source_sha256": digest}
        for name, fn in table.items():
            row[name] = _outcome(fn, src)
        result[key] = row
    return result


def main(argv):
    if "--record" in argv:
        data = record()
        os.makedirs(os.path.dirname(BASELINE), exist_ok=True)
        with open(BASELINE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, sort_keys=True, ensure_ascii=False)
            f.write("\n")
        print(f"front-door snapshot recorded: {len(data)} sources x {len(entries())} entries")
        return 0
    if "--check" in argv:
        if not os.path.exists(BASELINE):
            print("front-door snapshot: no baseline recorded (run --record)")
            return SKIP_EXIT
        with open(BASELINE, encoding="utf-8") as f:
            expected = json.load(f)
        actual = json.loads(json.dumps(record(), sort_keys=True, ensure_ascii=False))
        diffs = []
        for key in sorted(set(expected) | set(actual)):
            if key not in expected or key not in actual:
                diffs.append(f"{key}: present in only one side")
                continue
            for name in sorted(set(expected[key]) | set(actual[key])):
                if expected[key].get(name) != actual[key].get(name):
                    diffs.append(f"{key} / {name}: differs")
        if diffs:
            for d in diffs[:25]:
                print("FAIL", d)
            print(f"front-door snapshot: {len(diffs)} difference(s)")
            return 1
        print(f"front-door snapshot: {len(expected)} sources x {len(entries())} entries reproduce exactly")
        return 0
    print("usage: front_door_snapshot.py --record | --check")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
