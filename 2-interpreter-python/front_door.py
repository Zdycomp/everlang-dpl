"""The Python front door: lex, optionally heal, parse, and guard recursion.

The rules every entry shares live here and nowhere else:

* a source that fails is an Unparsed node plus an error Z, never None;
* nesting past the Python stack is a parse failure with a reason, never a crash.

Two modes, chosen by the caller and never by a default:

* heal=False  the strict grammar: lex, then parse the tokens as written;
* heal=True   the forgiving front door: strip semicolons, heal the tokens,
              then parse the healed tokens.

Four public entries are thin adapters over it: syntax.parse, syntax.compile_ever,
forgive.parse_forgiving and architecture.front_end. ir.parse_to_ir and runtime.run_source
reach it through parse and parse_forgiving. Their output is pinned by
tests/front_door_snapshot.py.
"""

from dataclasses import dataclass, field
from typing import List, Optional

from syntax import E, Defect, Node, ParseError, Parser, Token, Unparsed, e_z, lex
from forgive import _strip_semicolons
from forgive import heal as heal_tokens

NESTED_TOO_DEEP = "expression nested too deeply to parse"


@dataclass
class FrontResult:
    node: Node                  # never None: Unparsed when the source fails
    error: Optional[E]          # None when the source parsed
    corrections: list           # healing and semicolon corrections; [] when strict
    stage: str                  # "lex", "parse" or "ready"
    tokens: List[Token] = field(default_factory=list)  # tokens as lexed, before healing
    recoveries: list = field(default_factory=list)     # the strict parser's recoveries


def front_door(src: str, heal: bool) -> FrontResult:
    """Run the front door on one source. `heal` is required: no caller gets a
    silent default."""
    if not isinstance(heal, bool):
        raise TypeError("front_door needs heal=True or heal=False, stated by the caller")

    semicolon_corrections: list = []
    text = src
    if heal:
        text, semicolon_corrections = _strip_semicolons(src)

    toks, lex_error = lex(text)
    if lex_error is not None:
        return FrontResult(Unparsed("lex", lex_error.reason), lex_error,
                           semicolon_corrections, "lex", toks)

    corrections = list(semicolon_corrections)
    parse_tokens = toks
    if heal:
        parse_tokens, healed = heal_tokens(toks)
        corrections = semicolon_corrections + healed

    try:
        parser = Parser(parse_tokens)
        node = parser.program()
    except ParseError as exc:
        reason = str(exc)
        return FrontResult(Unparsed("parse", reason),
                           e_z("parse", reason, Defect.UNBOUNDED),
                           corrections, "parse", toks)
    except RecursionError:
        return FrontResult(Unparsed("parse", NESTED_TOO_DEEP),
                           e_z("parse", NESTED_TOO_DEEP, Defect.UNBOUNDED),
                           corrections, "parse", toks)

    return FrontResult(node, None, corrections, "ready", toks, list(parser.recoveries))
