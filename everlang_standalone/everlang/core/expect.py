from .particle import EParticle, EquivalenceRange

class ExpectGate:
    def __init__(self, contract_type: str, threshold: int = 180):
        self.contract_type = contract_type
        self.threshold = threshold

    def evaluate(self, particle: EParticle, equiv_range: EquivalenceRange = None) -> dict:
        if self.contract_type == "notZ":
            passed = not particle.is_z()
        elif self.contract_type == "minConfidence":
            passed = particle.confidence >= self.threshold
        elif self.contract_type == "piAcceptable":
            if equiv_range is None:
                passed = False
            else:
                passed = equiv_range.evaluate_pi_governor() == "ACCEPTABLE"
        else:
            passed = False

        return {
            "gate": self.contract_type,
            "passed": passed,
            "particle": particle
        }

    def enforce_fallback(self, evaluation: dict, fallback_handler: str):
        if evaluation["passed"]:
            return evaluation["particle"]

        if fallback_handler == "orZ":
            return EParticle("Quarantined(Z)", 0)
        elif fallback_handler == "orThrow":
            raise ValueError(f"ExpectGate[{self.contract_type}] violated for {evaluation['particle']}")
        elif fallback_handler == "orArchive":
            return EParticle("Archived_EError", 0)
        return EParticle("Quarantined(Z)", 0)
