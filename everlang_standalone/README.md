# Everlang (DPL / `everlang` v5.0.0 Standalone Package)

## Overview
**Everlang (Dynamic Phase Language / DPL)** is a quantified confidence, self-healing runtime environment operating on an 8-bit confidence scale (0–256).

### Key Features in v5.0.0:
1. **Hardened Core Engine**: Thread-safe atomic logging (`EArchive`), `NaN`/`Inf` numerical type guards (`EParticle`), and calibrated Pauli spectrum collision gates (`PhaseEngine`).
2. **Quantum Superrelativity & Entanglement**: Wave function collapse under Lorentz time dilation and non-local `EUnbound` state recovery (`EntanglementSwapSystem`).
3. **Biocomputing (new in v5)**: `everlang/biocomputing/` maps bytes to DNA and simulates strand displacement gates on the 0–256 confidence scale.
   - `QuaternaryTranslationLayer` (`quaternary.py`): base-4 encoding `A=00, T=01, C=10, G=11`; `bytes_to_DNA` / `DNA_to_bytes` round-trip bytes (4 bases per byte).
   - `BioPhaseEngine` (`dna_engine.py`): hybridization affinity score 0–256 (fraction of positions where the input base is the complement of the gate base, scaled by 256; length mismatch or empty gate scores 0). A displacement succeeds only if affinity >= 180 (about 70%) and particle confidence > 128.
   - `VibeDnaCompiler` (`vibe_compiler.py`): three `VibeChildCell`s (Child_Alpha1, Child_Beta2, Child_Omega3). `execute_vibe_pulse_cycle(cycle)` builds a 4-byte payload per cell, compiles it to DNA, decodes it back for a parity check, runs a displacement against the complementary gate (cycles 2 and 3 inject a mutated/noisy gate for Child_Beta2), then raises cell confidence by 10 on success or lowers it by 30 on failure.
4. **Multi-Threaded & Multi-Core Benchmarks**: CPU stress, 300-snippet multi-language healing, financial feed, and LLM/agent loop scripts under `benchmarks/`.

## Directory Structure
```
everlang_standalone/
├── README.md                          # Package documentation & CLI commands
├── main.py                            # CLI demo: pipeline, entanglement swap, vibe DNA compiler
├── everlang/                          # Core Framework Engine (v5.0.0)
│   ├── pipeline.py                    # EZPipeline (4-stage pipeline)
│   ├── core/                          # Particle, PhaseEngine, ExpectGate, EArchive
│   ├── containers/                    # 4 Micro-Containers (Syntax, Phase, Governor, Corpus)
│   ├── quantum/                       # Superrelativity & Entanglement Swap
│   └── biocomputing/                  # DNA / strand-displacement simulation
│       ├── quaternary.py              # QuaternaryTranslationLayer (A=00,T=01,C=10,G=11)
│       ├── dna_engine.py              # BioPhaseEngine (affinity 0-256, threshold 180)
│       └── vibe_compiler.py           # VibeChildCell, VibeDnaCompiler (pulse cycles)
├── tests/                             # Unit test suite (21 tests)
│   ├── test_everlang_core.py          # Core tests incl. 100-thread race condition stress test
│   └── test_everlang_v5.py            # Biocomputing (v5) tests
└── benchmarks/                        # Benchmark & Suite Scripts
    ├── ez_financial_feed_simulation.py
    ├── ez_autonomous_agent_loop.py
    ├── ez_llm_agent_loop.py
    ├── ez_cpu_stress_test.py
    ├── ez_300_code_healing_benchmark.py
    ├── ez_micro_containers.py
    └── ez_container_ci_service.py
```

## Running Benchmarks & Tests

All commands below are run from the `everlang_standalone/` directory. Benchmark
scripts resolve the package root relative to their own file, so they also work
when launched from any other working directory.

```bash
# Run standalone CLI demo (pipeline, entanglement swap, biocomputing)
python3 main.py

# Run unit tests (21 tests, including 100-thread concurrency test)
python3 -m unittest discover tests

# Lint
python3 -m pyflakes .

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
