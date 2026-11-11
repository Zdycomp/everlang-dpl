"""Quantification Ultra Parser: a declaration whose 14 token kinds match the
grammar's shape is recognised with one list comparison and built directly;
every other line goes through the shared recursive-descent parse_statement,
so statements and diagnostics are identical to BaselineParser's."""
from operator import itemgetter

from .grammar import (
    DECLARATION_KINDS, EOF, KW_PARTICLE, NEWLINE, Declaration, ParseResult, parse_statement,
)

_SHAPE_LEN = len(DECLARATION_KINDS)
_KIND = itemgetter(0)


class QuantificationUltraParser:
    def parse(self, tokens) -> ParseResult:
        starts = getattr(tokens, "declaration_starts", None)
        if starts is not None:
            return self._parse_indexed(tokens, starts)
        return self._parse_shapes(tokens)

    @staticmethod
    def _parse_indexed(tokens, starts) -> ParseResult:
        """For a TokenStream: declarations the lexer already verified are built
        straight from their known offsets; every other line is parsed normally."""
        statements, diags = [], []
        append = statements.append
        pending = iter(starts)
        next_decl = next(pending, -1)
        i = 0
        while True:
            if i == next_decl:
                append(Declaration(tokens[i + 1][1], tokens[i + 5][1], tokens[i + 8][1],
                                   int(tokens[i + 12][1]), tokens[i][2]))
                i += _SHAPE_LEN + 1 if tokens[i + _SHAPE_LEN][0] == NEWLINE else _SHAPE_LEN
                next_decl = next(pending, -1)
                continue
            if tokens[i][0] == EOF:
                break
            node, i = parse_statement(tokens, i, diags)
            if node is not None:
                append(node)
        return ParseResult(statements, diags)

    @staticmethod
    def _parse_shapes(tokens) -> ParseResult:
        kinds = list(map(_KIND, tokens))
        statements, diags = [], []
        append = statements.append
        shape = DECLARATION_KINDS
        i = 0
        while True:
            kind = kinds[i]
            if kind == KW_PARTICLE and kinds[i:i + _SHAPE_LEN] == shape and tokens[i + 3][1] == "E":
                end = kinds[i + _SHAPE_LEN]
                if end == NEWLINE or end == EOF:
                    append(Declaration(tokens[i + 1][1], tokens[i + 5][1], tokens[i + 8][1],
                                       int(tokens[i + 12][1]), tokens[i][2]))
                    i += _SHAPE_LEN + 1 if end == NEWLINE else _SHAPE_LEN
                    continue
            elif kind == EOF:
                break
            node, i = parse_statement(tokens, i, diags)
            if node is not None:
                append(node)
        return ParseResult(statements, diags)
