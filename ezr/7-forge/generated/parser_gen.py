"""
parser_gen.py — GENERATED. Do not edit.

Emitted by selfgen.py from the ratified grammar. To change what this
file does, change the grammar and re-emit; an edit here is overwritten
the next time anything regenerates it, and worse, it would be a parser
that no longer matches the document it claims to implement.

Every function below corresponds to one nonterminal. Left recursion has
been turned into a loop that rebuilds the tree on each turn, which is
how left associativity survives the transformation.
"""

from contract import Fail, ParseOut
from parsers import GRAMMAR as _RULES, _matches, _sync_grammar


class _Fail(Exception):
    """Local control flow. Never escapes parse()."""
    __slots__ = ()


class _State:
    __slots__ = ("t", "i", "high")

    def __init__(self, toks):
        self.t = [x for x in toks if x.kind != "EOF"]
        self.i = 0
        self.high = 0          # furthest token reached, for diagnostics

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else None

    def want(self, sym):
        tok = self.peek()
        if tok is None or not _matches(sym, tok):
            raise _Fail()
        self.i += 1
        if self.i > self.high:
            self.high = self.i
        return tok

    def at_end(self):
        return self.i >= len(self.t)


def _act(idx, kids):
    return _RULES[idx][2](kids)



def _alt_S_0(st):
    # S -> program
    _x0 = _p_program(st)
    return _act(4, [_x0])

def _p_S(st):
    node = _alt_S_0(st)
    return node

def _alt_additive_0(st):
    # additive -> multiply
    _x0 = _p_multiply(st)
    return _act(18, [_x0])

def _rec_additive_0(st, node):
    # additive -> additive '+' multiply
    _x0 = st.want("'+'")
    _x1 = _p_multiply(st)
    return _act(16, [node, _x0, _x1])

def _rec_additive_1(st, node):
    # additive -> additive '-' multiply
    _x0 = st.want("'-'")
    _x1 = _p_multiply(st)
    return _act(17, [node, _x0, _x1])

def _p_additive(st):
    node = _alt_additive_0(st)
    while True:
        for _step in (_rec_additive_0, _rec_additive_1,):
            _m = st.i
            try:
                node = _step(st, node)
                break
            except _Fail:
                st.i = _m
        else:
            break
    return node

def _alt_arglist_0(st):
    # arglist -> expr
    _x0 = _p_expr(st)
    return _act(34, [_x0])

def _rec_arglist_0(st, node):
    # arglist -> arglist %COMMA expr
    _x0 = st.want('%COMMA')
    _x1 = _p_expr(st)
    return _act(35, [node, _x0, _x1])

def _p_arglist(st):
    node = _alt_arglist_0(st)
    while True:
        for _step in (_rec_arglist_0,):
            _m = st.i
            try:
                node = _step(st, node)
                break
            except _Fail:
                st.i = _m
        else:
            break
    return node

def _alt_atom_0(st):
    # atom -> %NAME %LPAR arglist %RPAR
    _x0 = st.want('%NAME')
    _x1 = st.want('%LPAR')
    _x2 = _p_arglist(st)
    _x3 = st.want('%RPAR')
    return _act(30, [_x0, _x1, _x2, _x3])

def _alt_atom_1(st):
    # atom -> %LPAR expr %RPAR
    _x0 = st.want('%LPAR')
    _x1 = _p_expr(st)
    _x2 = st.want('%RPAR')
    return _act(28, [_x0, _x1, _x2])

def _alt_atom_2(st):
    # atom -> %NAME %LPAR %RPAR
    _x0 = st.want('%NAME')
    _x1 = st.want('%LPAR')
    _x2 = st.want('%RPAR')
    return _act(29, [_x0, _x1, _x2])

def _alt_atom_3(st):
    # atom -> %LBRACK arglist %RBRACK
    _x0 = st.want('%LBRACK')
    _x1 = _p_arglist(st)
    _x2 = st.want('%RBRACK')
    return _act(32, [_x0, _x1, _x2])

def _alt_atom_4(st):
    # atom -> %LBRACK %RBRACK
    _x0 = st.want('%LBRACK')
    _x1 = st.want('%RBRACK')
    return _act(31, [_x0, _x1])

def _alt_atom_5(st):
    # atom -> %NUM
    _x0 = st.want('%NUM')
    return _act(24, [_x0])

def _alt_atom_6(st):
    # atom -> %STR
    _x0 = st.want('%STR')
    return _act(25, [_x0])

def _alt_atom_7(st):
    # atom -> 'true'
    _x0 = st.want("'true'")
    return _act(26, [_x0])

def _alt_atom_8(st):
    # atom -> 'false'
    _x0 = st.want("'false'")
    return _act(27, [_x0])

def _alt_atom_9(st):
    # atom -> %NAME
    _x0 = st.want('%NAME')
    return _act(33, [_x0])

def _p_atom(st):
    for _alt in (_alt_atom_0, _alt_atom_1, _alt_atom_2, _alt_atom_3, _alt_atom_4, _alt_atom_5, _alt_atom_6, _alt_atom_7, _alt_atom_8, _alt_atom_9,):
        _m = st.i
        try:
            node = _alt(st)
            break
        except _Fail:
            st.i = _m
    else:
        raise _Fail()
    return node

def _alt_compare_0(st):
    # compare -> additive %CMP additive
    _x0 = _p_additive(st)
    _x1 = st.want('%CMP')
    _x2 = _p_additive(st)
    return _act(14, [_x0, _x1, _x2])

def _alt_compare_1(st):
    # compare -> additive
    _x0 = _p_additive(st)
    return _act(15, [_x0])

def _p_compare(st):
    for _alt in (_alt_compare_0, _alt_compare_1,):
        _m = st.i
        try:
            node = _alt(st)
            break
        except _Fail:
            st.i = _m
    else:
        raise _Fail()
    return node

def _alt_deflist_0(st):
    # deflist -> fndef
    _x0 = _p_fndef(st)
    return _act(2, [_x0])

def _rec_deflist_0(st, node):
    # deflist -> deflist fndef
    _x0 = _p_fndef(st)
    return _act(3, [node, _x0])

def _p_deflist(st):
    node = _alt_deflist_0(st)
    while True:
        for _step in (_rec_deflist_0,):
            _m = st.i
            try:
                node = _step(st, node)
                break
            except _Fail:
                st.i = _m
        else:
            break
    return node

def _alt_expr_0(st):
    # expr -> ifexpr
    _x0 = _p_ifexpr(st)
    return _act(9, [_x0])

def _alt_expr_1(st):
    # expr -> letexpr
    _x0 = _p_letexpr(st)
    return _act(10, [_x0])

def _alt_expr_2(st):
    # expr -> compare
    _x0 = _p_compare(st)
    return _act(11, [_x0])

def _p_expr(st):
    for _alt in (_alt_expr_0, _alt_expr_1, _alt_expr_2,):
        _m = st.i
        try:
            node = _alt(st)
            break
        except _Fail:
            st.i = _m
    else:
        raise _Fail()
    return node

def _alt_fndef_0(st):
    # fndef -> 'def' %NAME %LPAR params %RPAR %EQ expr
    _x0 = st.want("'def'")
    _x1 = st.want('%NAME')
    _x2 = st.want('%LPAR')
    _x3 = _p_params(st)
    _x4 = st.want('%RPAR')
    _x5 = st.want('%EQ')
    _x6 = _p_expr(st)
    return _act(6, [_x0, _x1, _x2, _x3, _x4, _x5, _x6])

def _alt_fndef_1(st):
    # fndef -> 'def' %NAME %LPAR %RPAR %EQ expr
    _x0 = st.want("'def'")
    _x1 = st.want('%NAME')
    _x2 = st.want('%LPAR')
    _x3 = st.want('%RPAR')
    _x4 = st.want('%EQ')
    _x5 = _p_expr(st)
    return _act(5, [_x0, _x1, _x2, _x3, _x4, _x5])

def _p_fndef(st):
    for _alt in (_alt_fndef_0, _alt_fndef_1,):
        _m = st.i
        try:
            node = _alt(st)
            break
        except _Fail:
            st.i = _m
    else:
        raise _Fail()
    return node

def _alt_ifexpr_0(st):
    # ifexpr -> 'if' expr 'then' expr 'else' expr
    _x0 = st.want("'if'")
    _x1 = _p_expr(st)
    _x2 = st.want("'then'")
    _x3 = _p_expr(st)
    _x4 = st.want("'else'")
    _x5 = _p_expr(st)
    return _act(13, [_x0, _x1, _x2, _x3, _x4, _x5])

def _p_ifexpr(st):
    node = _alt_ifexpr_0(st)
    return node

def _alt_letexpr_0(st):
    # letexpr -> 'let' %NAME %EQ expr 'in' expr
    _x0 = st.want("'let'")
    _x1 = st.want('%NAME')
    _x2 = st.want('%EQ')
    _x3 = _p_expr(st)
    _x4 = st.want("'in'")
    _x5 = _p_expr(st)
    return _act(12, [_x0, _x1, _x2, _x3, _x4, _x5])

def _p_letexpr(st):
    node = _alt_letexpr_0(st)
    return node

def _alt_multiply_0(st):
    # multiply -> unary
    _x0 = _p_unary(st)
    return _act(21, [_x0])

def _rec_multiply_0(st, node):
    # multiply -> multiply '*' unary
    _x0 = st.want("'*'")
    _x1 = _p_unary(st)
    return _act(19, [node, _x0, _x1])

def _rec_multiply_1(st, node):
    # multiply -> multiply '/' unary
    _x0 = st.want("'/'")
    _x1 = _p_unary(st)
    return _act(20, [node, _x0, _x1])

def _p_multiply(st):
    node = _alt_multiply_0(st)
    while True:
        for _step in (_rec_multiply_0, _rec_multiply_1,):
            _m = st.i
            try:
                node = _step(st, node)
                break
            except _Fail:
                st.i = _m
        else:
            break
    return node

def _alt_params_0(st):
    # params -> %NAME
    _x0 = st.want('%NAME')
    return _act(7, [_x0])

def _rec_params_0(st, node):
    # params -> params %COMMA %NAME
    _x0 = st.want('%COMMA')
    _x1 = st.want('%NAME')
    return _act(8, [node, _x0, _x1])

def _p_params(st):
    node = _alt_params_0(st)
    while True:
        for _step in (_rec_params_0,):
            _m = st.i
            try:
                node = _step(st, node)
                break
            except _Fail:
                st.i = _m
        else:
            break
    return node

def _alt_program_0(st):
    # program -> deflist
    _x0 = _p_deflist(st)
    return _act(0, [_x0])

def _alt_program_1(st):
    # program -> expr
    _x0 = _p_expr(st)
    return _act(1, [_x0])

def _p_program(st):
    for _alt in (_alt_program_0, _alt_program_1,):
        _m = st.i
        try:
            node = _alt(st)
            break
        except _Fail:
            st.i = _m
    else:
        raise _Fail()
    return node

def _alt_unary_0(st):
    # unary -> '-' unary
    _x0 = st.want("'-'")
    _x1 = _p_unary(st)
    return _act(22, [_x0, _x1])

def _alt_unary_1(st):
    # unary -> atom
    _x0 = _p_atom(st)
    return _act(23, [_x0])

def _p_unary(st):
    for _alt in (_alt_unary_0, _alt_unary_1,):
        _m = st.i
        try:
            node = _alt(st)
            break
        except _Fail:
            st.i = _m
    else:
        raise _Fail()
    return node


def parse(toks) -> ParseOut:
    """Entry point. Signature matches every hand-written parser."""
    _sync_grammar()
    st = _State(toks)
    try:
        node = _p_S(st)
    except _Fail:
        node = None
    if node is None or not st.at_end():
        # Report the furthest point the grammar reached, which is a more
        # useful place than wherever the last alternative happened to die.
        bad = st.t[min(st.high, len(st.t) - 1)] if st.t else None
        return ParseOut(fail=Fail("parse", "unbounded",
                                  bad.pos if bad else 0,
                                  bad.line if bad else 1))
    return ParseOut(ast=node)

