from typing import Tuple, Dict, Any, List
from .quaternary import QuaternaryTranslationLayer
from .dna_engine import BioPhaseEngine
from ..core.particle import EParticle

class VibeChildCell:
    """
    Programmable Child Cell spawned from Cell Alpha & Beta across triadic layers:
    - Primary Layer: Mind, Body, Soul
    - Resonance Layer: Electric, Etheric, Esoteric
    """
    def __init__(self, name: str, primary_layer: str, resonance_layer: str, initial_confidence: int) -> None:
        self.name: str = name
        self.primary_layer: str = primary_layer
        self.resonance_layer: str = resonance_layer
        self.current_particle: EParticle = EParticle(f"Cell<{name}:{primary_layer}|{resonance_layer}>", initial_confidence)
        self.translator: QuaternaryTranslationLayer = QuaternaryTranslationLayer()

    def generate_vibe_payload(self, cycle: int) -> bytearray:
        """Generates 4-byte vibe payload representing state, cycle, and confidence."""
        layer_byte = (hash(self.primary_layer) + hash(self.resonance_layer)) % 256
        res_byte = (hash(self.resonance_layer) * 31) % 256
        cycle_byte = (cycle * 64) % 256
        conf_byte = self.current_particle.confidence % 256
        return bytearray([layer_byte, res_byte, cycle_byte, conf_byte])

    def compile_to_live_dna(self, cycle: int) -> Tuple[str, bytearray]:
        """Compiles raw vibe state into live biological DNA sequence."""
        vibe_bytes = self.generate_vibe_payload(cycle)
        live_dna = self.translator.bytes_to_DNA(vibe_bytes)
        return live_dna, vibe_bytes


class VibeDnaCompiler:
    """
    Unified Vibe-to-DNA Compiler executing triadic pulse cycles and strand displacement.
    """
    def __init__(self) -> None:
        self.child_cells: List[VibeChildCell] = [
            VibeChildCell("Child_Alpha1", "Mind", "Electric", 220),
            VibeChildCell("Child_Beta2", "Body", "Etheric", 185),
            VibeChildCell("Child_Omega3", "Soul", "Esoteric", 245)
        ]

    def execute_vibe_pulse_cycle(self, cycle: int) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for child in self.child_cells:
            live_dna, vibe_bytes = child.compile_to_live_dna(cycle)
            decoded_bytes = child.translator.DNA_to_bytes(live_dna)
            
            # Construct complementary target gate
            comp_map = {'A': 'T', 'T': 'A', 'C': 'G', 'G': 'C'}
            if cycle == 2 and child.name == "Child_Beta2":
                # Inject mutation for self-healing test
                target_gate = "".join([comp_map.get(b, 'A') for b in live_dna[:13]]) + "AAG"
            elif cycle == 3 and child.name == "Child_Beta2":
                # Inject severe noise for Z-lock test
                target_gate = "".join([comp_map.get(b, 'A') for b in live_dna[:10]]) + "TCA"
            else:
                target_gate = "".join([comp_map.get(b, 'A') for b in live_dna])

            engine = BioPhaseEngine(target_gate)
            dna_particle = EParticle(live_dna, child.current_particle.confidence)
            disp_result = engine.process_displacement(dna_particle)
            
            # Evolve cell confidence based on state shift
            if disp_result["gate_displaced"]:
                new_conf = min(256, child.current_particle.confidence + 10)
            else:
                new_conf = max(0, child.current_particle.confidence - 30)
            child.current_particle = EParticle(child.current_particle.value, new_conf)

            results.append({
                "cell_name": child.name,
                "layers": f"[{child.primary_layer} | {child.resonance_layer}]",
                "raw_bytes": list(vibe_bytes),
                "compiled_dna": live_dna,
                "decoded_bytes": list(decoded_bytes),
                "parity_match": (list(vibe_bytes) == list(decoded_bytes)),
                "affinity_score": disp_result["calculated_affinity"],
                "gate_displaced": disp_result["gate_displaced"],
                "status": "STATE_SHIFT_SUCCESS" if disp_result["gate_displaced"] else "GATE_LOCKED_Z",
                "evolved_confidence": new_conf
            })
        return results
