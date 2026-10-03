"""Textbook reference implementation of the DPL frontend: the yardstick the
Mega stages are measured against, and the oracle they must agree with."""
import string
from typing import List

from ..core.phase_engine import PhaseEngine
from ..core.particle import EParticle
from ..transpiler import SuperTranspiler
from .grammar import (
    ARROW, EOF, ERROR, IDENT, INT, KEYWORDS, NEWLINE, STRING, SYMBOLS,
    Diagnostic, ParseResult, Token, parse_statement,
)
from .results import (
    CollisionResult, DeclarationResult, ExecutionResult,
    already_bound, bad_string, clamped, unbound, unexpected_char,
)

_IDENT_START = frozenset(string.ascii_letters + "_")
_IDENT_CHARS = frozenset(string.ascii_letters + string.digits + "_")
_DIGITS = frozenset(string.digits)


class BaselineLexer:
    def lex(self, source: str):
        src = source.replace("\r\n", "\n")
        toks: List[Token] = []
        diags: List[Diagnostic] = []
        i, n, line, line_start = 0, len(src), 1, 0
        while i < n:
            c = src[i]
            col = i - line_start + 1
            if c == "\n":
                toks.append(Token(NEWLINE, "\n", line, col))
                i += 1
                line += 1
                line_start = i
            elif c == " " or c == "\t":
                i += 1
            elif c == "#":
                while i < n and src[i] != "\n":
                    i += 1
            elif c in _IDENT_START:
                j = i + 1
                while j < n and src[j] in _IDENT_CHARS:
                    j += 1
                text = src[i:j]
                toks.append(Token(KEYWORDS.get(text, IDENT), text, line, col))
                i = j
            elif c in _DIGITS:
                j = i + 1
                while j < n and src[j] in _DIGITS:
                    j += 1
                toks.append(Token(INT, src[i:j], line, col))
                i = j
            elif c == '"':
                i = self._string(src, i, n, line, col, toks, diags)
            elif c == "-" and i + 1 < n and src[i + 1] == ">":
                toks.append(Token(ARROW, "->", line, col))
                i += 2
            elif c in SYMBOLS:
                toks.append(Token(SYMBOLS[c], c, line, col))
                i += 1
            else:
                toks.append(Token(ERROR, c, line, col))
                diags.append(unexpected_char(c, line, col))
                i += 1
        toks.append(Token(EOF, "", line, n - line_start + 1))
        return toks, diags

    @staticmethod
    def _string(src, i, n, line, col, toks, diags) -> int:
        j = i + 1
        chars = []
        bad = closed = False
        while j < n:
            d = src[j]
            if d == '"':
                closed = True
                j += 1
                break
            if d == "\n":
                break
            if d == "\\":
                if j + 1 >= n or src[j + 1] == "\n":
                    break
                escaped = src[j + 1]
                if escaped == '"' or escaped == "\\":
                    chars.append(escaped)
                else:
                    bad = True
                j += 2
                continue
            chars.append(d)
            j += 1
        if closed and not bad:
            toks.append(Token(STRING, "".join(chars), line, col))
        else:
            toks.append(Token(ERROR, src[i:j], line, col))
            diags.append(bad_string(closed, line, col))
        return j


class BaselineParser:
    def parse(self, tokens) -> ParseResult:
        statements, diags = [], []
        i = 0
        while tokens[i][0] != EOF:
            node, i = parse_statement(tokens, i, diags)
            if node is not None:
                statements.append(node)
        return ParseResult(statements, diags)


class BaselineExecutor:
    def __init__(self, transpiler: SuperTranspiler = None, archive=None) -> None:
        self._transpiler = transpiler or SuperTranspiler()
        self._archive = archive

    def execute(self, statements) -> ExecutionResult:
        self._result = ExecutionResult()
        for node in statements:
            getattr(self, "visit_" + type(node).__name__)(node)
        return self._result

    def visit_Declaration(self, node) -> None:
        env = self._result.particles
        if node.name in env:
            self._result.diagnostics.append(already_bound(node.name, node.line))
            return
        particle = EParticle(node.value, node.confidence)
        if particle.confidence != node.confidence:
            self._result.diagnostics.append(clamped(node.name, node.confidence, particle.confidence, node.line))
        env[node.name] = particle
        if self._archive is not None:
            renderings = self._archive.transpile_and_archive(node.name, node.value, node.type_spec, particle.confidence)
        else:
            renderings = self._transpiler.transpile(node.name, node.value, node.type_spec, particle.confidence)
        self._result.declarations.append(
            DeclarationResult(node.name, node.type_spec, node.value, particle.confidence, renderings))

    def visit_Collision(self, node) -> None:
        env = self._result.particles
        missing = [name for name in (node.left, node.right) if name not in env]
        for name in missing:
            self._result.diagnostics.append(unbound(name, node.line))
        if missing:
            return
        if node.target is not None and node.target in env:
            self._result.diagnostics.append(already_bound(node.target, node.line))
            return
        outcome = PhaseEngine.collide(env[node.left], env[node.right])
        particle = outcome["particle"]
        if self._archive is not None:
            self._archive.log_boundary_marker(f"collide {node.left} {node.right}", particle, outcome["reason"])
        self._result.collisions.append(CollisionResult(
            node.left, node.right, node.target, outcome["outcome"], outcome["reason"],
            particle.value, particle.confidence))
        if node.target is not None:
            env[node.target] = particle
