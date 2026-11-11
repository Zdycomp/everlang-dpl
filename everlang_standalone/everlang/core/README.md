# EParticle + PhaseEngine - Probabilistic State Machine Framework

A production-ready probabilistic state machine based on the EParticle confidence model. Enables sophisticated state transitions, self-healing error correction, and entanglement-based recovery.

## Installation

```bash
pip install everlang   # provides the everlang-particles command
```

## Quick Start

```bash
# Create a particle
everlang-particles create my_var "test_value" 200

# Test particle collision (state transitions)
everlang-particles collide 200 180

# Test self-healing repair
everlang-particles repair 2

# Show framework capabilities
everlang-particles stats
```

## Core Concepts

### EParticle
A particle represents a value with an associated confidence level (0-256):

```python
from everlang_standalone.everlang.core.particle import EParticle

# Create a particle
p = EParticle("test_value", 200)

# Access properties
print(p.value)       # "test_value"
print(p.confidence)  # 200
print(p.is_z())      # False (not Z-quarantined)
```

**Confidence Levels:**
- 0: Z-quarantined (failure/dead state)
- 1-80: Low confidence (defensive mode)
- 81-200: Medium confidence (normal operation)
- 201-256: High confidence (optimistic mode)

### PhaseEngine
State transition engine that determines particle interaction outcomes:

```python
from everlang_standalone.everlang.core.phase_engine import PhaseEngine

engine = PhaseEngine()

# Collision between two particles
p1 = EParticle("value1", 200)
p2 = EParticle("value2", 180)
result = engine.collide(p1, p2)
```

**Collision Rules:**
1. **Z_CONTAGION**: Either particle is Z → result is Z-quarantined
2. **EXCEL**: Confidence gap < 81 → constructive fusion (weighted average)
3. **EXPEL**: High ratio (>2φ) with stronger ≥81 → weaker particle discarded
4. **REPEL**: Default → both particles unchanged

### Self-Healing Archive
Automatic error correction using the repair formula:

```python
from everlang_standalone.everlang.core.archive import EArchive

archive = EArchive()

# Simulate repair
particle = EParticle("value", 50)
repaired = archive.emulate_repair(particle, error_distance=2)

# Repair formula: 250 - error_distance * 30
# error_distance=2 → confidence = 250 - 2*30 = 190
```

**Repair Behavior:**
- Error distance 0: No repair needed
- Error distance 1-3: Apply formula → 250 - distance*30
- Error distance >3: Z-quarantine (confidence = 0)

### Entanglement Swap
Restore Z-quarantined particles from anchored non-quarantined particles:

```python
from everlang_standalone.everlang.quantum.entanglement import EntanglementSwapSystem

# Swap entangled particles to recover quarantined one
# (Advanced usage - see quantum module)
```

## API Usage

```python
from everlang_standalone.everlang.core.particle import EParticle
from everlang_standalone.everlang.core.phase_engine import PhaseEngine
from everlang_standalone.everlang.core.archive import EArchive

# Create particles
p1 = EParticle("data1", 220)
p2 = EParticle("data2", 190)

# Collide them: collide() returns a dict with outcome, reason and the resulting particle
result = PhaseEngine.collide(p1, p2)
fused = result["particle"]
print(f"{result['outcome']}: confidence={fused.confidence}, value={fused.value}")

# Repair on error: takes a failing signature and an error distance (1-3)
archive = EArchive()
repaired = archive.emulate_repair("ParseError_01", error_distance=1)
print(f"Repaired: confidence={repaired.confidence}")

# Log to archive: (context, particle, reason)
archive.log_boundary_marker("collision_test", fused, result["reason"])
```

## Command Reference

### create
```bash
everlang-particles create NAME VALUE CONFIDENCE
```
Create and display a particle.
- NAME: Label for the particle
- VALUE: String value
- CONFIDENCE: 0-256 confidence level

### collide
```bash
everlang-particles collide CONF1 CONF2
```
Test particle collision with given confidence values.
- CONF1: First particle's confidence
- CONF2: Second particle's confidence
Shows resulting confidence and transition rule applied.

### repair
```bash
everlang-particles repair ERROR_DISTANCE
```
Test self-healing repair mechanism.
- ERROR_DISTANCE: 0-3 error distance
Shows repair formula and resulting confidence.

### stats
```bash
everlang-particles stats
```
Display framework capabilities, confidence scale, transitions, and repair mechanics.

## Physics Metaphor

The framework uses physics-inspired constants:

- **φ (Golden Ratio)** ≈ 1.618: Used in collision ratio thresholds
- **81**: Pauli spectrum gap threshold for EXCEL vs EXPEL decision
- **256**: Maximum confidence (quantum state normalization)

## Performance

| Operation | Time | Notes |
|-----------|------|-------|
| Particle creation | O(1) | <1µs |
| Collision check | O(1) | <1µs |
| Repair calculation | O(1) | <1µs |
| Archive logging | O(1) amortized | Append-only |

## Use Cases

1. **Probabilistic State Machines**: Model systems with uncertainty
2. **Confidence-Based Logic**: Make decisions based on reliability
3. **Automated Error Recovery**: Self-healing without external intervention
4. **Multi-Agent Systems**: Particle interactions represent agent coordination
5. **Quantum-Inspired Computing**: Entanglement and wave-function collapse concepts

## Requirements

- Python 3.9+
- No external dependencies (pure Python)

## License

MIT

## See Also

- [everlang-dna](../biocomputing/README.md) - DNA sequence analysis
- [everlang-transpile](../transpiler/README.md) - Multi-language code generation
- [Main Project](https://github.com/Zdycomp/everlang-dpl)
