from .particle import EParticle, PHI

class PhaseEngine:
    @staticmethod
    def collide(particle_a: EParticle, particle_b: EParticle) -> dict:
        # 1. Z-Contagion check
        if particle_a.is_z() or particle_b.is_z():
            return {
                "outcome": "Z_CONTAGION",
                "particle": EParticle("Quarantined(Z)", 0),
                "reason": "Z-Contagion triggered: zero-absolute touch"
            }

        conf_a = particle_a.confidence
        conf_b = particle_b.confidence
        gap = abs(conf_a - conf_b)
        ratio = (max(conf_a, conf_b) / max(1, min(conf_a, conf_b)))

        # 2. Pauli Spectrum Gap Check (< 81) - Constructive Interference Phase
        if gap < 81:
            # Excel constructive phase arithmetic
            fused_conf = min(256, int(conf_a + conf_b - (conf_a * conf_b / 256.0)))
            fused_value = f"({particle_a.value} ⊕ {particle_b.value})"
            return {
                "outcome": "EXCEL",
                "particle": EParticle(fused_value, fused_conf),
                "reason": "Constructive phase interference elevated trust"
            }

        # 3. Expel Check (Ratio > 2 * Phi AND high confidence dominance)
        if ratio > (2 * PHI) and max(conf_a, conf_b) >= 81:
            survivor = particle_a if conf_a >= conf_b else particle_b
            weaker = particle_b if conf_a >= conf_b else particle_a
            return {
                "outcome": "EXPEL",
                "particle": survivor,
                "archived_marker": weaker,
                "reason": f"Expelled weaker particle (Ratio {ratio:.2f} > 2*phi)"
            }

        # 4. Repel (Outside spectrum alignment)
        return {
            "outcome": "REPEL",
            "particle": EParticle("Domain_Boundary", 0),
            "archived_marker": (particle_a, particle_b),
            "reason": "Opposite zones created domain boundary"
        }
