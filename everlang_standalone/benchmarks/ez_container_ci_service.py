import json
import math
from typing import Dict, Any, List

class EParticle:
    def __init__(self, name: str, value: Any, confidence: int):
        self.name = name
        self.value = value
        self.confidence = max(0, min(256, confidence))

    def is_z(self) -> bool:
        return self.confidence == 0

class SyntaxMutatorContainer:
    """Micro-Container 1: Normalizes multi-language ASTs into E-particles and handles Emulate syntax repairs."""
    def process_commit(self, raw_code: str, language: str) -> Dict[str, Any]:
        # Calculate mock error distance based on syntax drift keywords
        error_distance = 0
        if "null" in raw_code or "Option::None" in raw_code or "NULL" in raw_code:
            error_distance = 2
        elif "invalid" in raw_code or "err" in raw_code:
            error_distance = 4

        status = "NORMALIZED"
        discounted_conf = 200
        if 1 <= error_distance <= 3:
            status = "EMULATED_REPAIR"
            discounted_conf = max(1, 200 - (error_distance * 30))
        elif error_distance > 3:
            status = "QUARANTINED_Z"
            discounted_conf = 0

        particle = EParticle(
            name=f"{language}_commit",
            value=raw_code.strip(),
            confidence=discounted_conf
        )
        return {
            "status": status,
            "error_distance": error_distance,
            "particle": particle
        }

class PhaseSemanticEngineContainer:
    """Micro-Container 2: Performs Pauli Exclusion & Phase Collisions (Excel/Expel/Repel)."""
    def collide(self, particle_a: EParticle, particle_b: EParticle) -> Dict[str, Any]:
        if particle_a.is_z() or particle_b.is_z():
            return {
                "outcome": "Z_CONTAGION",
                "particle": EParticle("Quarantined_Pair", "Z_CONTAGION", 0)
            }

        a, b = particle_a.confidence, particle_b.confidence
        ratio = max(a, b) / max(1, min(a, b))
        phi = (1 + math.sqrt(5)) / 2  # 1.618033...

        if ratio > (2 * phi):
            # Expel weaker particle
            survivor = particle_a if a >= b else particle_b
            return {
                "outcome": "EXPELLED_WEAKER",
                "particle": EParticle(f"Expelled_Survivor({survivor.name})", survivor.value, survivor.confidence)
            }

        # Excel constructive phase synthesis: min(256, A + B - (A * B / 256))
        elevated_conf = min(256, int(a + b - (a * b / 256)))
        fused_value = f"({particle_a.value} ⊕ {particle_b.value})"
        return {
            "outcome": "EXCEL_SYNTHESIS",
            "particle": EParticle("Fused_Build_Asset", fused_value, elevated_conf)
        }

class ContractGovernorContainer:
    """Micro-Container 3: Enforces Pi Range Governors and Expect Gates."""
    def enforce_contracts(self, particle: EParticle, range_width: float, min_conf: int) -> Dict[str, Any]:
        # Evaluate pi governor threshold
        pi_status = "ACCEPTABLE"
        if range_width > 81:
            pi_status = "APPROACHING_Z"
        elif range_width > 25:
            pi_status = "WIDE_ENUMERATE"

        # Gate check
        if pi_status == "APPROACHING_Z" or particle.confidence < min_conf:
            return {
                "gate_passed": False,
                "pi_status": pi_status,
                "action": "GATE_REJECTED_OR_Z",
                "particle": EParticle(particle.name, "QUARANTINED_AT_EXPECT", 0)
            }

        return {
            "gate_passed": True,
            "pi_status": pi_status,
            "action": "GATE_PASSED",
            "particle": particle
        }

class EvolveArchiveCorpusContainer:
    """Micro-Container 4: Calculates Evolution Force Vectors and Maintains EArchive."""
    def __init__(self):
        self.archive_boundary_markers = []
        self.evolved_vectors = []

    def process_evolution_and_archive(self, result: Dict[str, Any], action: float, reaction: float, force: float):
        particle = result.get("particle")
        if particle is None or particle.is_z():
            self.archive_boundary_markers.append({
                "context": result.get("action", "FAILURE_OR_Z"),
                "reason": "Quarantined at Zero floor"
            })
            return {"evolved": False, "reason": "Z_STATE_ARCHIVED"}

        # Phi equalizer check: Push == Pull (simulated balance check)
        is_phi_balanced = abs(action - reaction) <= 0.5
        
        # Calculate evolution vector: Action / (Reaction / Force)
        if force > 0 and reaction > 0:
            vector = action / (reaction / force)
        else:
            vector = 0.0

        if is_phi_balanced and vector > 0:
            self.evolved_vectors.append(vector)
            return {
                "evolved": True,
                "vector": round(vector, 4),
                "phi_balanced": True,
                "final_confidence": particle.confidence
            }
        else:
            self.archive_boundary_markers.append({
                "context": "PHI_IMBALANCE",
                "reason": f"Push/Pull mismatch (|{action} - {reaction}| > 0.5)"
            })
            return {
                "evolved": False,
                "vector": round(vector, 4),
                "phi_balanced": False,
                "reason": "PHI_EQUALIZER_BLOCKED"
            }

class EZContainerCIService:
    """Orchestrates all 4 micro-containers into a Continuous Integration Service."""
    def __init__(self):
        self.c1 = SyntaxMutatorContainer()
        self.c2 = PhaseSemanticEngineContainer()
        self.c3 = ContractGovernorContainer()
        self.c4 = EvolveArchiveCorpusContainer()

    def run_ci_pipeline(self, commit_batch: List[Dict[str, Any]]) -> Dict[str, Any]:
        results = []
        for idx, commit in enumerate(commit_batch):
            commit_id = f"BUILD_{idx+1:03d}"
            
            # Stage 1: Syntax Mutation & Emulation
            c1_out = self.c1.process_commit(commit["code"], commit["lang"])
            p1 = c1_out["particle"]

            # Stage 2: Semantic Phase Collision with reference build rule
            ref_particle = EParticle("Rule_Asset", "Verify_Safety", 210)
            c2_out = self.c2.collide(p1, ref_particle)
            p2 = c2_out["particle"]

            # Stage 3: Contract Governance (& Pi Width evaluation)
            c3_out = self.c3.enforce_contracts(p2, range_width=commit["range_width"], min_conf=150)
            p3 = c3_out["particle"]

            # Stage 4: Evolution & Corpus Archiving
            c4_out = self.c4.process_evolution_and_archive(
                c3_out,
                action=commit["action_force"],
                reaction=commit["reaction_force"],
                force=commit["applied_force"]
            )

            results.append({
                "commit_id": commit_id,
                "lang": commit["lang"],
                "c1_syntax": c1_out["status"],
                "c2_phase": c2_out["outcome"],
                "c3_gate": c3_out["action"],
                "c3_pi_status": c3_out["pi_status"],
                "c4_evolution": c4_out,
                "final_particle_confidence": p3.confidence
            })

        return {
            "total_commits": len(commit_batch),
            "pipeline_runs": results,
            "total_boundary_markers_archived": len(self.c4.archive_boundary_markers),
            "total_evolved_vectors": len(self.c4.evolved_vectors),
            "evolved_vectors": self.c4.evolved_vectors
        }

if __name__ == "__main__":
    service = EZContainerCIService()
    
    test_batch = [
        # Commit 1: High quality DPL code
        {"code": "particle audit : E<string> = 'Valid'", "lang": "DPL", "range_width": 12.0, "action_force": 3.0, "reaction_force": 3.0, "applied_force": 6.0},
        # Commit 2: Kotlin with null drift -> triggers Emulate
        {"code": "val x: String? = null", "lang": "Kotlin", "range_width": 18.5, "action_force": 2.5, "reaction_force": 2.5, "applied_force": 5.0},
        # Commit 3: Rust code with wide margin -> triggers WIDE_ENUMERATE
        {"code": "let range = 0..100;", "lang": "Rust", "range_width": 45.0, "action_force": 4.0, "reaction_force": 4.0, "applied_force": 8.0},
        # Commit 4: C Clang with severe invalid syntax -> Quarantined Z
        {"code": "void* p = invalid_ptr;", "lang": "Clang_C", "range_width": 95.0, "action_force": 1.0, "reaction_force": 5.0, "applied_force": 2.0},
        # Commit 5: Go channel code -> Phi Imbalance
        {"code": "ch <- msg", "lang": "Go", "range_width": 15.0, "action_force": 5.0, "reaction_force": 2.0, "applied_force": 4.0}
    ]

    report = service.run_ci_pipeline(test_batch)
    print(json.dumps(report, indent=2))
