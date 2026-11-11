import math

class TrueSuperrelativityEngine:
    @staticmethod
    def calculate_lorentz_factor(v_ratio: float) -> float:
        v_ratio = min(0.999999, max(0.0, v_ratio))
        return 1.0 / math.sqrt(1.0 - (v_ratio ** 2))

    @staticmethod
    def calculate_dilated_proper_time(dt_observer: float, gamma: float) -> float:
        return dt_observer / gamma

    @staticmethod
    def wave_function_collapse(psi_amplitude: float) -> int:
        prob = min(1.0, max(0.0, psi_amplitude ** 2))
        return int(prob * 256)
