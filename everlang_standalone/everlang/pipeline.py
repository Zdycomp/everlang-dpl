from .core.particle import EParticle
from .core.archive import EArchive
from .containers.syntax_mutator import SyntaxMutatorContainer
from .containers.semantic_phase import PhaseSemanticEngineContainer
from .containers.governor import ContractGovernorContainer
from .containers.corpus import EvolveArchiveCorpusContainer

class EZPipeline:
    """The 4-Stage Pipeline: EXAMINE -> EVALUATE -> EXECUTE -> ARCHIVE

    EXAMINE is SyntaxMutatorContainer, which classifies a code snippet by its
    markers (ERROR/INVALID -> repair, BAD_POINTER/CRASH -> quarantine,
    otherwise normalized) and attaches the language's syntax offset. It does
    not run DnaSequencer.
    """
    def __init__(self):
        self.archive = EArchive()
        self.c1 = SyntaxMutatorContainer(self.archive)
        self.c2 = PhaseSemanticEngineContainer()
        self.c3 = ContractGovernorContainer()
        self.c4 = EvolveArchiveCorpusContainer(self.archive)

    def run(self, snippet_id: str, code_snippet: str, lang: str, rule_particle: EParticle) -> dict:
        # Stage 1: EXAMINE
        res_c1 = self.c1.process(snippet_id, code_snippet, lang)
        p1 = res_c1["particle"]

        # Stage 2: EVALUATE
        res_c2 = self.c2.process(p1, rule_particle)
        p2 = res_c2["particle"]

        # Stage 3: EXECUTE
        res_c3 = self.c3.process(p2)
        p3 = res_c3["particle"]

        # Stage 4: ARCHIVE
        res_c4 = self.c4.process(p3, push_force=5.0, pull_force=5.0)
        
        return {
            "snippet_id": snippet_id,
            "lang": lang,
            "examine_status": res_c1["status"],
            "phase_outcome": res_c2["outcome"],
            "pi_governor_status": res_c3["pi_status"],
            "evolved": res_c4["evolved"],
            "final_particle": res_c4["particle"]
        }
