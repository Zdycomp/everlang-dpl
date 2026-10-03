"""Result types and diagnostic wording shared by the baseline and Mega stages,
so both produce byte-identical output for the same program."""
from dataclasses import dataclass, field
from typing import Any, Dict, List, NamedTuple, Optional

from ..core.particle import EParticle
from .grammar import Diagnostic


class DeclarationResult(NamedTuple):
    name: str
    type_spec: str
    value: str
    confidence: int
    renderings: Dict[str, str]


class CollisionResult(NamedTuple):
    left: str
    right: str
    target: Optional[str]
    outcome: str
    reason: str
    value: Any
    confidence: int


@dataclass
class ExecutionResult:
    declarations: List[DeclarationResult] = field(default_factory=list)
    collisions: List[CollisionResult] = field(default_factory=list)
    particles: Dict[str, EParticle] = field(default_factory=dict)
    diagnostics: List[Diagnostic] = field(default_factory=list)


def unexpected_char(c: str, line: int, col: int) -> Diagnostic:
    hint = ("did you mean '->'?" if c == "-"
            else "DPL uses letters, digits, '_', quotes, and the symbols : < > = @ ( ) ->")
    return Diagnostic("lex", "error", line, col, f"unexpected character {c!r}", hint)


def bad_string(closed: bool, line: int, col: int) -> Diagnostic:
    if not closed:
        return Diagnostic("lex", "error", line, col, "unterminated string",
                          "close the string with '\"' before the end of the line")
    return Diagnostic("lex", "error", line, col, "unknown escape sequence in string",
                      "only \\\" and \\\\ are allowed inside strings")


def already_bound(name: str, line: int) -> Diagnostic:
    return Diagnostic("execute", "error", line, 1, f"'{name}' is already bound",
                      "pick a new name; particles cannot be rebound")


def unbound(name: str, line: int) -> Diagnostic:
    return Diagnostic("execute", "error", line, 1, f"'{name}' is not bound",
                      f"declare it first with `particle {name} : E<Type> = \"...\" @ confidence(N)`")


def clamped(name: str, declared: int, actual: int, line: int) -> Diagnostic:
    return Diagnostic("execute", "warning", line, 1,
                      f"confidence {declared} for '{name}' clamped to {actual}",
                      "confidence ranges from 0 to 256")
