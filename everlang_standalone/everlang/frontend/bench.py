"""Baseline vs Mega throughput: `python3 -m everlang.frontend.bench [lines]`."""
import sys
import time

from .baseline import BaselineExecutor, BaselineLexer, BaselineParser
from .mega_executer import MegaExecuter
from .quantification_ultra_parser import QuantificationUltraParser
from .supercodalexer import Supercodalexer

_TYPES = ("float", "String", "Int", "Bool")


def make_program(lines: int) -> str:
    """Deterministic error-free program: nine declarations to every collision."""
    out = []
    for i in range(lines):
        if i % 10 == 9:
            out.append(f"collide p{i - 9} p{i - 8} -> c{i}")
        else:
            out.append(f'particle p{i} : E<{_TYPES[i % 4]}> = "value_{i}" @ confidence({60 + (i * 37) % 197})')
    return "\n".join(out) + "\n"


def _best(fn, arg, repeats: int):
    best, out = float("inf"), None
    for _ in range(repeats):
        t0 = time.perf_counter()
        out = fn(arg)
        best = min(best, time.perf_counter() - t0)
    return best, out


def measure(lines: int = 10_000, repeats: int = 5) -> dict:
    """Best-of-`repeats` seconds per stage for both implementations."""
    source = make_program(lines)
    timings = {}
    for label, lexer, parser, executor in (
        ("baseline", BaselineLexer(), BaselineParser(), BaselineExecutor()),
        ("mega", Supercodalexer(), QuantificationUltraParser(), MegaExecuter()),
    ):
        lex_t, (tokens, _) = _best(lexer.lex, source, repeats)
        parse_t, parsed = _best(parser.parse, tokens, repeats)
        exec_t, _ = _best(executor.execute, parsed.statements, repeats)
        timings[label] = {"lex": lex_t, "parse": parse_t, "execute": exec_t,
                          "total": lex_t + parse_t + exec_t}
    return timings


def main(argv) -> None:
    lines = int(argv[1]) if len(argv) > 1 else 10_000
    t = measure(lines)
    print(f"{lines} lines, best of 5")
    print(f"{'stage':<8} {'baseline':>11} {'mega':>11} {'speedup':>8}")
    for stage in ("lex", "parse", "execute", "total"):
        b, m = t["baseline"][stage], t["mega"][stage]
        print(f"{stage:<8} {b * 1e3:>9.2f}ms {m * 1e3:>9.2f}ms {b / m:>7.2f}x")


if __name__ == "__main__":
    main(sys.argv)
