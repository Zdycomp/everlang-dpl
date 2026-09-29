from ..core.particle import EParticle
from ..core.archive import EArchive
from .superrelativity import TrueSuperrelativityEngine

class EntanglementSwapSystem:
    """4-Layer Subatomic Spin System & Non-Local Entanglement Swap (Omega / EUnbound)"""
    def __init__(self, archive: EArchive):
        self.archive = archive

    def execute_entanglement_swap(self, cell_alpha_particle: EParticle, cell_beta_particle: EParticle, velocity_c: float) -> dict:
        gamma = TrueSuperrelativityEngine.calculate_lorentz_factor(velocity_c)
        
        # If Alpha is in Z-quarantine, non-local Beta entanglement restores phase symmetry
        if cell_alpha_particle.is_z():
            restored_confidence = int(cell_beta_particle.confidence * (gamma / gamma))
            restored_particle = EParticle(f"EUnbound<Ω>({cell_alpha_particle.value} ⟷ {cell_beta_particle.value})", restored_confidence)
            self.archive.calculate_evolve_vector(restored_confidence, 1.0, gamma)
            return {
                "outcome": "NON_LOCAL_SWAP_RESTORED",
                "particle": restored_particle,
                "fidelity": 100.0,
                "gamma_factor": gamma
            }
        
        return {
            "outcome": "STABLE_ENTANGLED_STATE",
            "particle": cell_alpha_particle,
            "fidelity": 100.0,
            "gamma_factor": gamma
        }
