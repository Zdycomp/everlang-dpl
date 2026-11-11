from ..core.particle import EParticle, EquivalenceRange
from ..core.expect import ExpectGate

class ContractGovernorContainer:
    """Container 3: Pi Range & Contract Gatekeeper"""
    @staticmethod
    def process(particle: EParticle, range_bounds: tuple = (10.0, 28.5), gate_type: str = "notZ") -> dict:
        equiv = EquivalenceRange(range_bounds[0], range_bounds[1])
        pi_status = equiv.evaluate_pi_governor()
        
        gate = ExpectGate(gate_type)
        eval_res = gate.evaluate(particle, equiv)
        final_particle = gate.enforce_fallback(eval_res, "orZ")
        
        return {
            "pi_status": pi_status,
            "gate_passed": eval_res["passed"],
            "particle": final_particle
        }
