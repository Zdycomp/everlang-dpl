from ..core.particle import EParticle, PhiEqualizer
from ..core.archive import EArchive

class EvolveArchiveCorpusContainer:
    """Container 4: Evolution & Z-Boundary Archive"""
    def __init__(self, archive: EArchive):
        self.archive = archive

    def process(self, particle: EParticle, push_force: float, pull_force: float) -> dict:
        if particle.is_z():
            self.archive.log_boundary_marker("CorpusContainer", particle, "Quarantined_Z_Logged")
            return {"evolved": False, "reason": "Z_STATE_ARCHIVED", "particle": particle}

        balanced = PhiEqualizer.is_balanced(push_force, pull_force)
        if not balanced:
            self.archive.log_boundary_marker("CorpusContainer", particle, "Phi_Imbalance")
            return {"evolved": False, "reason": "PHI_EQUALIZER_BLOCKED", "particle": particle}

        vector = self.archive.calculate_evolve_vector(push_force, pull_force, 2.0)
        evolved_particle = EParticle(f"Evolved<{particle.value}>", min(256, particle.confidence + 30))
        
        return {
            "evolved": True,
            "vector": vector,
            "phi_balanced": True,
            "particle": evolved_particle
        }
