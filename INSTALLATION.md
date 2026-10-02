# Everlang Installation & CLI Tools

This document describes how to install everlang and use the three reusable command-line tools.

## Installation

### From Source

```bash
git clone https://github.com/Zdycomp/everlang-dpl.git
cd everlang-dpl
pip install -e .
```

This installs everlang in development mode and makes the three CLI tools available:
- `everlang` - Main demo CLI
- `everlang-dna` - DNA analysis tool
- `everlang-transpile` - Code generation tool
- `everlang-particles` - Particle framework tool

### PyPI (Future)

Once published to PyPI, install with:

```bash
pip install everlang
```

Or individual tools:

```bash
pip install everlang-dna          # DNA analysis: ~39k seqs/sec
pip install everlang-transpiler   # Code generation: ~919k renders/sec
pip install everlang-particles    # Probabilistic state machine
```

## CLI Tools

### 1. everlang-dna: DNA Sequence Analysis

Analyze, validate, and explore DNA sequences using DnaSequencer with lexer/parser.

```bash
# Validate a DNA sequence
everlang-dna validate ATCGATCGATCGATCG

# Analyze and tokenize a sequence
everlang-dna analyze ATCGATCGATCGATCG

# Show tool statistics and performance metrics
everlang-dna stats
```

**Performance**: ~39,000 sequences/sec (or 5-10x faster with PyPy)

### 2. everlang-transpile: Multi-Language Code Generation

Generate equivalent code in 6 languages from a single DPL particle description.

```bash
# Generate Kotlin code for a particle
everlang-transpile render message "Hello World" String 200 KOTLIN

# Generate code for all supported languages
everlang-transpile render-all counter "42" Int 180

# Show supported languages and performance metrics
everlang-transpile stats
```

**Supported Languages**:
- DPL (Everlang native)
- Kotlin
- Rust
- C/Clang
- Go
- Groovy

**Performance**: ~153,000 renders/sec per language (~919k total throughput)

### 3. everlang-particles: Probabilistic State Machine

Create and manipulate particles with confidence-based state transitions.

```bash
# Create a particle and inspect it
everlang-particles create my_var "test_value" 200

# Test particle collision (state transitions)
everlang-particles collide 200 180

# Test self-healing repair mechanism
everlang-particles repair 2

# Show framework statistics
everlang-particles stats
```

**Confidence Scale**:
- 0: Z-quarantined (failure state)
- 1-80: Low confidence (defensive)
- 81-200: Medium confidence (normal)
- 201-256: High confidence (optimistic)

## Architecture

The three tools are part of a multi-phase language ecosystem:

```
Input Code
    ↓
Python Frontend (everlang_standalone/)
  • DnaSequencer (lexer/parser for DNA analysis)
  • SuperTranspiler v2 (6-language code generator)
  • EParticle + PhaseEngine (confidence model)
    ↓
C++ Analysis Phase (1-phase-cpp/)
  • verify_particle: Safety gate for particles
    ↓
SQL Archive (4-archive-sql/)
  • tapestry.db: Durable logging & history
    ↓
Java Runtime (5-runtime-java/)
  • SelfHealingAudit: Repair mechanism auditor
  • TranspileAudit: Code generation verifier
```

## Development

Run the test suite:

```bash
cd everlang-dpl
python3 run_all.py              # All phases (Python, SQL, C++, Java)
python3 run_all.py --skip-native  # Python + SQL only
```

Run benchmarks:

```bash
cd everlang_standalone

# DNA Sequencer benchmarks
python3 benchmarks/ez_cpu_stress_test.py
python3 benchmarks/ez_10000_vocabulary_grammar_benchmark.py

# GRCh38 genomics matching (real-time sequence queries)
python3 benchmarks/grch38_realtime_demo.py

# Code healing (self-repair mechanism)
python3 benchmarks/ez_300_code_healing_benchmark.py

# Comprehensive performance suite
python3 benchmarks/comprehensive_suite.py

# PyPy compatibility check
python3 benchmarks/pypy_compatibility_check.py
```

## Next Steps

See [SEMANTICS_PLAN.md](SEMANTICS_PLAN.md) for the roadmap:

### Current: Ship Reusable Tools ✓
- DnaSequencer (DNA analysis)
- SuperTranspiler (code generation)
- EParticle + PhaseEngine (probabilistic state machine)

### Future: Full Language (2-3 months)
1. Define Everlang syntax (SEMANTICS.md)
2. Build parser (2-interpreter-python/)
3. Implement IR/lowering (ir.py, tac.c)
4. Build executor (5-runtime-java)

## References

- [SEMANTICS_PLAN.md](SEMANTICS_PLAN.md) - Language roadmap and design philosophy
- [CLAUDE.md](CLAUDE.md) - Architecture, multi-phase contracts, rules
- [everlang_standalone/README.md](everlang_standalone/README.md) - Python package details
