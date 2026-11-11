"""Real repair engines behind EArchive.heal().

Ever source goes through ezr's forgive.py; Python, JavaScript, Go, Rust, Java
and Kotlin go through ezr's edapt fixers. Both live in the ezr lineage and are
loaded by path, the way ReinforcedArchive loads the SQL phase. Without them a
language is refused, never emulated.
"""
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .particle import EParticle
from .vocabulary import E_EXECUTE_FLOOR, LANGUAGES

_EZR = Path(__file__).resolve().parents[3] / "ezr"
_engines = None


def _load():
    global _engines
    if _engines is None:
        try:
            # Appended, not prepended, so nothing already importable is shadowed.
            for p in (_EZR / "2-interpreter-python", _EZR):
                if p.is_dir() and str(p) not in sys.path:
                    sys.path.append(str(p))
            import forgive
            from edapt import fixers
            _engines = (forgive, fixers)
        except ImportError:
            _engines = ()
    return _engines


@dataclass
class EngineResult:
    code: Optional[str]
    program: object
    fixes: list
    refusals: List[str]


def run(source: str, language: str) -> EngineResult:
    if language not in LANGUAGES:
        raise ValueError(f"unsupported language {language!r}; have {', '.join(LANGUAGES)}")
    engines = _load()
    if not engines:
        return EngineResult(None, None, [], [f"no repair engine for {language}: ezr/ not found at {_EZR}"])
    forgive, fixers = engines
    if language == "ever":
        node, err, corrections = forgive.parse_forgiving(source)
        return EngineResult(None, node, corrections, [] if err is None else [str(err)])
    problems = fixers.diagnose_brackets(source, language)
    if problems:
        return EngineResult(None, None, [], problems)
    result = fixers.fix(source, language)
    return EngineResult(result.code, None, result.fixes, [])


@dataclass
class Healing:
    language: str
    source_ident: str
    code: Optional[str]
    program: object
    confidence: int
    repairs: List[dict] = field(default_factory=list)
    refusals: List[str] = field(default_factory=list)

    @property
    def refused(self) -> bool:
        return bool(self.refusals)

    @property
    def runnable(self) -> bool:
        return not self.refused and self.confidence >= E_EXECUTE_FLOOR

    def particle(self) -> EParticle:
        if self.refused:
            return EParticle("Quarantined(Z)", 0)
        return EParticle(self.code if self.code is not None else self.program, self.confidence)
