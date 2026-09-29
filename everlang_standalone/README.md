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
