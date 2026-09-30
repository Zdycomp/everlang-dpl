import math

PHI = 1.61803398875

class EParticle:
    def __init__(self, value, confidence):
        self.value = value
        try:
            conf_float = float(confidence)
            if math.isnan(conf_float) or math.isinf(conf_float):
                self.confidence = 0
            else:
                self.confidence = max(0, min(256, int(conf_float)))
        except (ValueError, TypeError):
            self.confidence = 0  # Default to Z-quarantine on invalid type

    def is_z(self) -> bool:
        return self.confidence == 0

    def __repr__(self):
        return f"E<{type(self.value).__name__}>(val={self.value!r}, conf={self.confidence}/256)"

class EquivalenceRange:
    def __init__(self, min_val: float, max_val: float):
        try:
            self.min_val = float(min_val)
            self.max_val = float(max_val)
            if not (math.isfinite(self.min_val) and math.isfinite(self.max_val)):
                self.width = 999.0  # Force APPROACHING_Z on NaN/Inf bounds
            else:
                self.width = abs(self.max_val - self.min_val)
        except (ValueError, TypeError):
            self.width = 999.0

    def evaluate_pi_governor(self) -> str:
        if self.width <= 25.0:
            return "ACCEPTABLE"
        elif self.width <= 81.0:
            return "WIDE_ENUMERATE"
        else:
            return "APPROACHING_Z"

class PhiEqualizer:
    @staticmethod
    def is_balanced(push_force: float, pull_force: float, tolerance: float = 0.5) -> bool:
        try:
            pf = float(push_force)
            pl = float(pull_force)
            if math.isnan(pf) or math.isinf(pf) or math.isnan(pl) or math.isinf(pl):
                return False
            return abs(pf - pl) <= tolerance
        except (ValueError, TypeError):
            return False
