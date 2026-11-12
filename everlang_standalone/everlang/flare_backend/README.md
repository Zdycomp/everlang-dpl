# Flare backend

Flare v0.2.0 (vendored, see `FLARE_VERSION`) as everlang-dpl's execution
engine for Python-shaped snippets. Flare compiles the snippet to a native
binary with gcc and runs it; the result comes back as an `EParticle`.

## Use

```sh
# from everlang_standalone/
python3 -m everlang.flare_backend.cli run prog.fl
python3 -m everlang.flare_backend.cli --snippet 'print(1 + 2)'
```

```python
from everlang.pipeline import EZPipeline
from everlang.core.particle import EParticle

pipe = EZPipeline()
res = pipe.run_python("SNIP_001", "print(1 + 2)", EParticle("Rule<Math>", 200))
res["final_particle"]          # E<str>(val='3', conf=256/256)
res["flare_stdout"]            # '3\n'
```

## Confidence

| outcome | confidence |
|---|---|
| clean exit 0 | 256 |
| compile error, runtime error, signal death, timeout | 0 (Z-quarantined) |

No silent fallback to CPython.

## Limits (Flare v0.2.0, inherited)

Lowercase `true`/`false`, no `break`/`continue`, no `raise`, no inheritance,
no `nonlocal`, string-keyed dicts only, one statement per line. A snippet
outside that subset fails to compile and is Z — it is never silently
rewritten. `.ever` programs are unaffected: they still run through
`ezr/2-interpreter-python/runtime.py::run_source`.
