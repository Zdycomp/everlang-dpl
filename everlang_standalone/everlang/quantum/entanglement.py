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
            # Non-local swap recovers the anchor particle's confidence. Confidence is
            # already a 0-256 bounded integer, so no scaling is needed (previously an
            # identity multiply by gamma/gamma, which was always 1.0 and misleading).
            restored_confidence = cell_beta_particle.confidence
            restored_particle = EParticle(f"EUnbound<Ω>({cell_alpha_particle.value} ⟷ {cell_beta_particle.value})", restored_confidence)
            # Evolution vector follows the same action/(reaction/force) contract as
            # EArchive.calculate_evolve_vector: action=restored confidence, reaction=1.0.
            # Previously the raw confidence was passed as action_success, producing a
            # nonsensical vector of restored_confidence * gamma.
            self.archive.calculate_evolve_vector(restored_confidence / 256.0, 1.0, gamma)
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
