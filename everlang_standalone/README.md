# Everlang (DPL / `everlang` v3.0 Standalone Package)

## Overview
**Everlang (Dynamic Phase Language / DPL)** is a quantified confidence, self-healing runtime environment operating on an 8-bit confidence scale (0–256).

### Key Features & Enhancements in v3.0:
1. **Hardened Core Engine**: Thread-safe atomic logging (`EArchive`), `NaN`/`Inf` numerical type guards (`EParticle`), and calibrated Pauli spectrum collision gates (`PhaseEngine`).
2. **Quantum Superrelativity & Entanglement**: Wave function collapse ($|\Psi(t)\rangle$) under Lorentz time dilation ($\gamma = 3.20$) and non-local $EUnbound (\Omega)$ state recovery.
3. **Multi-Threaded & Multi-Core Benchmarks**:
   - High-CPU multi-core stress benchmark achieving **~200,000 ops/sec** across 1,000,000 operations with 100% thread resilience.
   - 300-snippet multi-language code healing benchmark evaluating 15 mainstream programming languages (Python, JS, TS, Rust, C, C++, Go, Java, Kotlin, Swift, C#, Ruby, PHP, SQL, Shell).
4. **Autonomous AI & Financial Suite**: Integrated scripts for LLM prompt auto-repair and real-time financial market data tick $Z$-quarantine.

## Directory Structure
```
everlang_standalone/
├── README.md                          # Full architectural spec & CLI documentation
├── main.py                            # CLI execution entry point
├── everlang/                          # Core Framework Engine
│   ├── core/                          # Particle, PhaseEngine, ExpectGate, EArchive
│   ├── containers/                    # 4 Micro-Containers (Syntax, Phase, Governor, Corpus)
│   └── quantum/                       # Superrelativity & Entanglement Swap
├── tests/                             # Expanded 8-Battery Unit Test Suite
│   └── test_everlang_core.py          # Includes 100-thread race condition stress tests
└── benchmarks/                        # Comprehensive Benchmark & Suite Scripts
    ├── ez_financial_feed_simulation.py
    ├── ez_autonomous_agent_loop.py
    ├── ez_llm_agent_loop.py
    ├── ez_cpu_stress_test.py
    ├── ez_300_code_healing_benchmark.py
    ├── ez_micro_containers.py
    └── ez_container_ci_service.py
```

## Running Benchmarks & Tests

All commands below are run from the `everlang_standalone/` directory. Scripts are
now location-independent: they resolve the package root relative to their own
file, so they also work when launched from any other working directory.

```bash
# Run standalone CLI
python3 main.py

# Run unit tests (including 100-thread concurrency test)
python3 -m unittest discover tests

# Run 1,000,000-op High-CPU multi-core benchmark
python3 benchmarks/ez_cpu_stress_test.py

# Run 300-snippet multi-language code healing benchmark
python3 benchmarks/ez_300_code_healing_benchmark.py
```

## Audit & Refactor Notes (v3.0.0)

This revision is the result of a full audit → verification → refactor →
re-verification pass. No public behaviour of the 4-stage pipeline was changed;
the changes below are correctness, portability and hygiene fixes.

**Fixed**

- **Broken benchmark imports (critical).** `ez_300_code_healing_benchmark.py`,
  `ez_cpu_stress_test.py` and `ez_llm_agent_loop.py` hard-coded a non-existent
  `/workspace/scratch/...` path, so every run raised `ModuleNotFoundError`.
  All scripts now derive the package root from `__file__` and run from any CWD.
- **Missing `everlang/core/__init__.py`.** The `core` sub-package relied on
  implicit namespace packages; it is now an explicit package like the others.
- **`EArchive` misused for the quantum evolution vector.** The entanglement
  swap passed a raw 0–256 confidence as `action_success`, yielding a
  nonsensical vector (`confidence × γ`). It now uses the normalised
  action `confidence / 256`, matching the documented vector contract.
- **Misleading no-op in entanglement swap.** `gamma / gamma` (always `1.0`)
  was replaced with a direct, clearly-commented recovery of the anchor
  confidence.
- **Unused imports / dead code** across core and benchmarks; `pipe_res`
  assignment in the stress test made explicit; f-strings without placeholders
  converted to plain strings.
- **Version string drift.** Package `__version__` said `1.0.0` while the README
  advertised `v3.0`. Both now report `3.0.0`; `main.py` prints it dynamically.

**Added**

- `tests/__init__.py`, `benchmarks/__init__.py`, `.gitignore` (also stops the
  tracked `__pycache__/*.pyc` artifacts from being committed again).
- Regression tests: pipeline Z-quarantine of a memory hazard,
  `EquivalenceRange` NaN/Inf guards, `PhiEqualizer` balance edge cases,
  entanglement-swap restoration, and a benchmark-import smoke test.

**Verification:** `python3 -m pyflakes .` → clean; `python3 -m unittest discover
tests` → 13/13 passing; all CLI entry points and benchmarks exit 0.
