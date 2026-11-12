"""CLI entry point for the Flare backend.

    python3 -m everlang.flare_backend.cli run prog.fl
    python3 -m everlang.flare_backend.cli --snippet 'print(1 + 2)'

Program stdout goes to stdout unchanged; the DPL verdict (exit code and
confidence) goes to stderr so output stays pipeable. Exit code mirrors the
program's: 0 on a clean run, 1 on compile/runtime failure (Z).
"""

import sys

from .executor import FlareExecutor


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    snippet = None
    path = None
    opt = "2"
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--snippet":
            i += 1
            if i >= len(argv):
                print("error: --snippet needs a value", file=sys.stderr)
                return 2
            snippet = argv[i]
        elif a.startswith("--opt="):
            opt = a.split("=", 1)[1]
        elif a == "run":
            pass
        elif a.endswith(".fl"):
            path = a
        else:
            print("error: unknown argument: %s" % a, file=sys.stderr)
            return 2
        i += 1
    if snippet is None and path is None:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    try:
        ex = FlareExecutor()
    except FileNotFoundError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1
    if path is not None:
        res = ex.run_file(path, opt=opt)
    else:
        res = ex.run(snippet, opt=opt)
    sys.stdout.write(res.stdout)
    sys.stdout.flush()
    conf = res.particle.confidence
    if res.ok:
        print("[flare] exit=0 confidence=%d/256 (%.3fs)" % (conf, res.elapsed_s),
              file=sys.stderr)
        return 0
    print("[flare] Z-quarantined confidence=0/256: %s" % (res.error or "failed"),
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
