import math
import json
from typing import Dict, Any, List, Tuple

class EParticle:
    def __init__(self, value: Any, confidence: int):
        self.value = value
        self.confidence = max(0, min(256, confidence))
    
    def is_z(self) -> bool:
        return self.confidence == 0

# 1. Micro-Container 1: SyntaxMutator (Syntactic Morphology Generator)
class SyntaxMutatorContainer:
    """Generates and offsets syntactic representations across language paradigms."""
    
    PARADIGMS = {
        "DPL": "particle {name} : E<{type_spec}> = \"{val}\" @ confidence({conf})",
        "KOTLIN": "val {name}: {type_spec}? = \"{val}\"",
        "RUST": "let {name}: Option<{type_spec}> = Some(\"{val}\".to_string());",
        "C_CLANG": "const char* {name} = \"{val}\"; // Unchecked pointer",
        "GO": "var {name} string = \"{val}\""
    }

    def generate_syntactic_offsets(self, name: str, val: str, type_spec: str, conf: int) -> Dict[str, str]:
        offsets = {}
        for lang, template in self.PARADIGMS.items():
            offsets[lang] = template.format(name=name, val=val, type_spec=type_spec, conf=conf)
        return offsets

    def compute_syntax_distance(self, pattern1: str, pattern2: str) -> int:
        if pattern1 == pattern2: return 0
        return abs(len(pattern1) - len(pattern2)) % 5 + 1


# 2. Micro-Container 2: PhaseSemanticEngine (Semantic & Phase Collision Generator)
class PhaseSemanticEngineContainer:
    """Generates semantic trust transformations using EZ phase arithmetic."""

    PHI = 1.61803398875

    def process_collision(self, p1: EParticle, p2: EParticle) -> Dict[str, Any]:
        if p1.is_z() or p2.is_z():
            return {"outcome": "Z_CONTAGION", "particle": EParticle("Quarantined(Z)", 0), "reason": "Touching Z-state"}
        
        c1, c2 = p1.confidence, p2.confidence
        ratio = max(c1, c2) / max(1.0, float(min(c1, c2)))

        # 1. Expel check: ratio > 2 * phi (~3.236)
        if ratio > 2 * self.PHI:
            survivor = p1 if c1 >= c2 else p2
            expelled = p2 if c1 >= c2 else p1
            return {
                "outcome": "EXPELLED",
                "survivor": survivor,
                "expelled_boundary": expelled,
                "reason": f"Confidence ratio {ratio:.2f} > 2*phi ({2*self.PHI:.2f})"
            }

        # 2. Excel constructive phase arithmetic
        gap = abs(c1 - c2)
        if gap < 81:
            elevated = min(256, int(c1 + c2 - (c1 * c2 / 256.0)))
            fused_val = f"({p1.value} ⊕ {p2.value})"
            return {
                "outcome": "EXCEL",
                "particle": EParticle(fused_val, elevated),
                "reason": f"Constructive phase elevation: {c1} + {c2} -> {elevated}"
            }
        
        return {"outcome": "NEUTRAL", "particle": p1, "reason": "Outside interaction spectrum"}


# 3. Micro-Container 3: ContractGovernor (Expect & Range Bound Generator)
class ContractGovernorContainer:
    """Generates contract definitions, pi range width checks, and fallback handlers."""

    def evaluate_pi_acceptable(self, range_min: float, range_max: float) -> Dict[str, Any]:
        width = abs(range_max - range_min)
        if width <= 25.0:
            status = "ACCEPTABLE"
        elif width <= 81.0:
            status = "WIDE_ENUMERATE"
        else:
            status = "APPROACHING_Z"
        
        return {
            "range": [range_min, range_max],
            "width": width,
            "status": status,
            "passed": status == "ACCEPTABLE"
        }

    def enforce_expect_gate(self, particle: EParticle, min_conf: int, fallback: str) -> Dict[str, Any]:
        passed = (not particle.is_z()) and (particle.confidence >= min_conf)
        if passed:
            return {"gate_status": "PASSED", "particle": particle}
        
        if fallback == "orZ":
            return {"gate_status": "FALLBACK_Z", "particle": EParticle("Quarantined(Z)", 0)}
        elif fallback == "orThrow":
            return {"gate_status": "HALTED_EXCEPTION", "error": f"Expect Gate Failed: confidence {particle.confidence} < {min_conf}"}
        else: # orArchive
            return {"gate_status": "ARCHIVED_MARKER", "particle": EParticle("EError(Boundary)", 0)}


# 4. Micro-Container 4: EvolveArchiveCorpus (Evolution & Corpus Vector Generator)
class EvolveArchiveCorpusContainer:
    """Generates autonomous evolution vectors and maintains EArchive boundary markers."""

    def __init__(self):
        self.boundary_markers: List[Dict[str, Any]] = []

    def record_boundary(self, context: str, reason: str, particle: EParticle):
        self.boundary_markers.append({
            "context": context,
            "reason": reason,
            "conf": particle.confidence,
            "val": str(particle.value)
        })

    def compute_evolution_vector(self, action_success: bool, reaction_data: float, force: float) -> Dict[str, Any]:
        PHI = 1.61803398875
        if not action_success or force <= 0 or reaction_data <= 0:
            return {"evolved": False, "reason": "Force loop incomplete"}
        
        action_val = 1.0 if action_success else 0.0
        evo_vector = action_val / (reaction_data / force)
        
        push_force = force
        pull_reaction = reaction_data
        is_balanced = abs((push_force / pull_reaction) - PHI) < 1.0

        return {
            "evolved": True,
            "evolution_vector": round(evo_vector, 4),
            "phi_balanced": is_balanced,
            "formula": "action / (reaction / force)"
        }


def run_micro_containers_demo():
    mutator = SyntaxMutatorContainer()
    phase_engine = PhaseSemanticEngineContainer()
    governor = ContractGovernorContainer()
    corpus = EvolveArchiveCorpusContainer()

    print("=== EZ MICRO-CONTAINERS GENERATION & SYNTAX/SEMANTIC OFFSET SUITE ===")
    
    # 1. Syntax Generator
    offsets = mutator.generate_syntactic_offsets("txRate", "0.025", "float", 190)
    print("\n[Container 1: SyntaxMutator Output]")
    print(json.dumps(offsets, indent=2))

    # 2. Phase Engine Generator
    p1 = EParticle("MarketFeed", 180)
    p2 = EParticle("RiskRules", 120)
    collision = phase_engine.process_collision(p1, p2)
    print("\n[Container 2: PhaseSemanticEngine Output]")
    res_part = collision.get('particle')
    val_str = res_part.value if res_part else "N/A"
    conf_val = res_part.confidence if res_part else 0
    print(f"Outcome: {collision['outcome']}, Fused Value: {val_str}, Trust: {conf_val}/256")

    # 3. Contract Governor Generator
    pi_check = governor.evaluate_pi_acceptable(10.0, 28.5)
    gate_res = governor.enforce_expect_gate(p2, 150, "orZ")
    print("\n[Container 3: ContractGovernor Output]")
    print(f"Pi Range Status: {pi_check['status']} (Width: {pi_check['width']})")
    print(f"Gate Enforcement: {gate_res['gate_status']}")

    # 4. Evolution Corpus Generator
    corpus.record_boundary("BoundaryTest", "Unverified range", p2)
    evo = corpus.compute_evolution_vector(True, 0.5, 3.0)
    print("\n[Container 4: EvolveArchiveCorpus Output]")
    print(f"Evolved Vector: {evo['evolution_vector']}, Phi Balanced: {evo['phi_balanced']}")
    print(f"Archived Markers: {len(corpus.boundary_markers)}")

if __name__ == "__main__":
    run_micro_containers_demo()
