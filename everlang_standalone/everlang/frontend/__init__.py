from typing import List, NamedTuple

from .baseline import BaselineExecutor, BaselineLexer, BaselineParser
from .grammar import Collision, Declaration, Diagnostic, ParseResult, Token
from .mega_executer import MegaExecuter
from .quantification_ultra_parser import QuantificationUltraParser
from .results import CollisionResult, DeclarationResult, ExecutionResult
from .supercodalexer import Supercodalexer


class FrontendResult(NamedTuple):
    tokens: list
    statements: list
    execution: ExecutionResult
    diagnostics: List[Diagnostic]


def compile_and_run(source: str, transpiler=None, archive=None) -> FrontendResult:
    """Supercodalexer -> QuantificationUltraParser -> MegaExecuter. Diagnostics
    from all three stages are merged in source order. With `archive`, renderings
    come from the archive's own transpiler (via transpile_and_archive), so
    `transpiler` is not used; register custom languages on the archive."""
    tokens, lex_diags = Supercodalexer().lex(source)
    parsed = QuantificationUltraParser().parse(tokens)
    execution = MegaExecuter(transpiler=transpiler, archive=archive).execute(parsed.statements)
    diags = sorted(lex_diags + parsed.diagnostics + execution.diagnostics, key=lambda d: (d.line, d.col))
    return FrontendResult(tokens, parsed.statements, execution, diags)


__all__ = [
    "Supercodalexer", "QuantificationUltraParser", "MegaExecuter", "compile_and_run",
    "BaselineLexer", "BaselineParser", "BaselineExecutor",
    "Token", "Declaration", "Collision", "Diagnostic", "ParseResult",
    "DeclarationResult", "CollisionResult", "ExecutionResult", "FrontendResult",
]
