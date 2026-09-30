from typing import Dict, Any, Union
from ..core.particle import EParticle

class BioPhaseEngine:
    """
    Simulates physical DNA strand displacement gates using 
    Everlang's 8-bit kinetic confidence mapping (0-256).
    Enforces a default 180/256 (70%) self-healing threshold for strand displacement.
    """
    def __init__(self, target_gate_sequence: str) -> None:
        self.gate_sequence: str = str(target_gate_sequence).upper().strip()
        
    def calculate_hybridization_affinity(self, input_seq: str) -> int:
        """
        Calculates binding affinity as an 8-bit score (0-256).
        Perfect complementary match = 256. Mismatches drop the score.
        """
        complement_map = {'A': 'T', 'T': 'A', 'C': 'G', 'G': 'C'}
        input_cleaned = str(input_seq).upper().strip()
        
        if len(input_cleaned) != len(self.gate_sequence) or len(self.gate_sequence) == 0:
            return 0
            
        matches = 0
        for i, base in enumerate(input_cleaned):
            if complement_map.get(base) == self.gate_sequence[i]:
                matches += 1
                
        return int((matches / len(self.gate_sequence)) * 256)

    def process_displacement(self, input_particle: EParticle) -> Dict[str, Any]:
        """
        Executes a wave function state shift if the incoming strand 
        has enough kinetic confidence to displace the current gate.
        """
        affinity = self.calculate_hybridization_affinity(str(input_particle.value))
        
        # Self-healing threshold: Require at least 70% match (~180/256 confidence)
        HEALING_THRESHOLD = 180 
        
        success = (affinity >= HEALING_THRESHOLD) and (input_particle.confidence > 128)
        
        return {
            "input_evaluated": input_particle,
            "calculated_affinity": affinity,
            "gate_displaced": success,
            "status": "COLLISION_SUCCESS (State Shifted)" if success else "COLLISION_REFLECTED (Gate Locked)"
        }
