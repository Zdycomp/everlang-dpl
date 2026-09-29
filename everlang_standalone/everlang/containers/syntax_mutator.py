from ..core.particle import EParticle
from ..core.archive import EArchive

class SyntaxMutatorContainer:
    """Container 1: Morphological Grammar & Error Distance Generator"""
    def __init__(self, archive: EArchive):
        self.archive = archive

    def process(self, snippet_id: str, code_snippet: str, lang: str) -> dict:
        if "ERROR" in code_snippet or "INVALID" in code_snippet:
            error_distance = 2
            emulated = self.archive.emulate_repair(snippet_id, error_distance)
            return {
                "status": "EMULATED_REPAIR",
                "particle": emulated,
                "error_distance": error_distance,
                "lang": lang
            }
        elif "BAD_POINTER" in code_snippet or "CRASH" in code_snippet:
            return {
                "status": "QUARANTINED_Z",
                "particle": EParticle("Quarantined(Z)", 0),
                "error_distance": 5,
                "lang": lang
            }
        else:
            return {
                "status": "NORMALIZED",
                "particle": EParticle(f"NormalizedCode<{lang}>", 220),
                "error_distance": 0,
                "lang": lang
            }
