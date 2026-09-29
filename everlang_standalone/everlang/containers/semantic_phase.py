from ..core.particle import EParticle
from ..core.phase_engine import PhaseEngine

class PhaseSemanticEngineContainer:
    """Container 2: Phase Physics & Z-Contagion Engine"""
    @staticmethod
    def process(input_particle: EParticle, rule_particle: EParticle) -> dict:
        return PhaseEngine.collide(input_particle, rule_particle)
