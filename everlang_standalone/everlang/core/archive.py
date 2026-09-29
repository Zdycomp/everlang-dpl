import threading
from .particle import EParticle

class EArchive:
    def __init__(self):
        self._lock = threading.Lock()
        self.boundary_markers = []
        self.examples = []
        self.evolved_vectors = []

    def log_boundary_marker(self, context: str, particle: EParticle, reason: str):
        with self._lock:
            self.boundary_markers.append({
                "context": context,
                "value": particle.value,
                "confidence": particle.confidence,
                "reason": reason
            })

    def emulate_repair(self, failing_signature: str, error_distance: int) -> EParticle:
        with self._lock:
            if 1 <= error_distance <= 3:
                borrowed_conf = 250 - (error_distance * 30)
                repaired_value = f"EmulatedPattern<{failing_signature}>"
                return EParticle(repaired_value, borrowed_conf)
            return EParticle("Quarantined(Z)", 0)

    def calculate_evolve_vector(self, action_success: float, reaction_data: float, force: float) -> float:
        with self._lock:
            if reaction_data == 0 or force == 0:
                return 0.0
            vector = action_success / (reaction_data / force)
            self.evolved_vectors.append(vector)
            return vector
