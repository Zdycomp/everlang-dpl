"""
ir.py — Ever / Tapestry, Python-side IR

The Python parser emits EvNode trees. The C execution engine consumes them.
Neither side knows what language the other is written in — they communicate
through the wire format defined in ir.h.

OWNERSHIP RULES (same rules as ir.h, stated in Python terms)
─────────────────────────────────────────────────────────────
RULE 1: The parser owns the EvNode tree until the caller calls result.free().
RULE 2: The ABI boundary copies data. Python never passes a reference into a
        buffer it still owns to C. C never writes into Python-managed memory.
RULE 3: One result per parse. The result carries everything its nodes need.
        When the caller is done with the result, it drops the reference and
        Python GC reclaims it. No manual free required on the Python side.
RULE 4: Cross-language transfer goes through serialise() → deserialise().
        No shared mutable state between Python and C at any point.

This module also fixes the deferred import that was the first platform
exposure: `from ever import e_equiv, E_PI_WIDTH_WARN` was called inside
eval_ast() at execution time. Those values are now constants in this module,
imported once at parse time, and the parser never touches the runtime.

Codric Enterprise · Ricky (Dreid) · 2026
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Dict, List, Optional, Tuple

# ─────────────────────────────────────────────
# Ever constants — imported HERE, not inside eval functions.
# The parser needs these to decide on widths; the runtime does not
# need to re-import them.
# ─────────────────────────────────────────────

E_PI_WIDTH_WARN      = 81
E_PI_WIDTH_ENUMERATE = 25
E_CERTAIN            = 256
E_EXECUTE_FLOOR      = 128
E_INTAKE             = 120
E_DEPTH_CEILING      = 3


# ─────────────────────────────────────────────
# Node kinds — must match EvNodeKind in ir.h exactly
# ─────────────────────────────────────────────

class NK(IntEnum):
    VOID   = 0;  BOOL  = 1;  INT   = 2;  REAL = 3;  TEXT  = 4
    VAR    = 10; DEF   = 11; CALL  = 12
    ADD    = 20; SUB   = 21; MUL   = 22; DIV  = 23
    LT     = 24; GT    = 25; LTE   = 26; GTE  = 27; EQ = 28; NEQ = 29
    IF     = 30
    LIST   = 40; RECORD = 41
    INDEX  = 42; FIELD  = 43
    AND    = 60; OR = 61; NOT = 62
    FOR_RANGE = 70; FOR_IN = 71; WHILE = 72
    Z      = 50; ANCHOR = 51; ASSM = 52
    ERR    = 99


OP_STR: Dict[str, NK] = {
    "+": NK.ADD, "-": NK.SUB, "*": NK.MUL, "/": NK.DIV,
    "<": NK.LT,  ">": NK.GT,  "<=": NK.LTE, ">=": NK.GTE,
    "==": NK.EQ, "!=": NK.NEQ,
}

NK_NAMES = {v: k for k, v in NK.__members__.items()}


# ─────────────────────────────────────────────
# EvNode — platform-independent IR node
# ─────────────────────────────────────────────

@dataclass
class EvNode:
    """Platform-independent IR node.

    All children are EvNodes. No platform objects, no GC handles, no
    runtime imports. This class can be serialised to bytes and sent to C
    without knowing anything about the C runtime.
    """
    kind:        NK
    line:        int                        = 1
    lit_bool:    Optional[bool]             = None
    lit_int:     Optional[int]              = None
    lit_real:    Optional[float]            = None
    str_val:     Optional[str]              = None   # text, var name, fn name
    params:      List[str]                  = field(default_factory=list)
    children:    List["EvNode"]             = field(default_factory=list)
    keys:        List[str]                  = field(default_factory=list)
    error:       Optional[str]              = None
    # structural metrics, filled after parsing
    size:        int                        = 0
    depth:       int                        = 0

    # ── constructors ──

    @classmethod
    def void_lit(cls, line: int = 1) -> "EvNode":
        return cls(NK.VOID, line=line)

    @classmethod
    def bool_lit(cls, v: bool, line: int = 1) -> "EvNode":
        return cls(NK.BOOL, line=line, lit_bool=v)

    @classmethod
    def int_lit(cls, v: int, line: int = 1) -> "EvNode":
        return cls(NK.INT, line=line, lit_int=v)

    @classmethod
    def real_lit(cls, v: float, line: int = 1) -> "EvNode":
        return cls(NK.REAL, line=line, lit_real=v)

    @classmethod
    def text_lit(cls, v: str, line: int = 1) -> "EvNode":
        return cls(NK.TEXT, line=line, str_val=v)

    @classmethod
    def var(cls, name: str, line: int = 1) -> "EvNode":
        return cls(NK.VAR, line=line, str_val=name)

    @classmethod
    def fn_def(cls, name: str, params: List[str],
               body: "EvNode", line: int = 1) -> "EvNode":
        return cls(NK.DEF, line=line, str_val=name,
                   params=list(params), children=[body])

    @classmethod
    def fn_call(cls, name: str, args: List["EvNode"],
                line: int = 1) -> "EvNode":
        return cls(NK.CALL, line=line, str_val=name,
                   children=list(args))

    @classmethod
    def binop(cls, op: str, left: "EvNode", right: "EvNode",
              line: int = 1) -> "EvNode":
        return cls(OP_STR[op], line=line, children=[left, right])

    @classmethod
    def if_node(cls, cond: "EvNode", then: "EvNode",
                els: "EvNode", line: int = 1) -> "EvNode":
        return cls(NK.IF, line=line, children=[cond, then, els])

    @classmethod
    def err(cls, msg: str, line: int = 1) -> "EvNode":
        return cls(NK.ERR, line=line, error=msg)

    # ── structural metrics ──

    def measure(self) -> None:
        """Compute size and depth. Must be called after the tree is built."""
        self.size = 1
        self.depth = 0
        for ch in self.children:
            ch.measure()
            self.size += ch.size
            self.depth = max(self.depth, ch.depth + 1)

    def shape(self) -> str:
        """Structure with constants — replaced skeleton() string hacks."""
        if self.kind in (NK.INT, NK.REAL): return "Num"
        if self.kind == NK.BOOL:           return "Bool"
        if self.kind == NK.TEXT:           return "Str"
        if self.kind == NK.VAR:            return "Var"
        if self.kind in (NK.DEF, NK.CALL):
            inner = ",".join(c.shape() for c in self.children)
            return f"{NK_NAMES[self.kind]}({self.str_val},{inner})"
        inner = " ".join(c.shape() for c in self.children)
        return f"({NK_NAMES.get(self.kind, '?')} {inner})"

    def skeleton(self) -> str:
        """Structure with constants AND comparison operators erased.

        Same semantics as ev_node_skeleton() in ir.c — the fix that
        correctly classified the notebook cell-7 overfitting problem.
        Now at the IR level so the C synthesiser can use it too.
        """
        CMPS = {NK.LT, NK.GT, NK.LTE, NK.GTE, NK.EQ, NK.NEQ}
        if self.kind in (NK.INT, NK.REAL, NK.BOOL, NK.TEXT): return "K"
        if self.kind == NK.VAR: return "V"
        if self.kind in CMPS:
            rhs = self.children[1].skeleton() if len(self.children) > 1 else "K"
            return f"(V CMP {rhs})"
        if self.kind == NK.CALL:
            inner = ",".join(c.skeleton() for c in self.children)
            return f"CALL({self.str_val},{inner})"
        inner = " ".join(c.skeleton() for c in self.children)
        return f"({NK_NAMES.get(self.kind,'?')} {inner})"


# ─────────────────────────────────────────────
# Wire format — identical to ir.c ev_ir_serialise / ev_ir_deserialise
# ─────────────────────────────────────────────

def serialise(n: EvNode) -> bytes:
    """EvNode → bytes. Same format as C ev_ir_serialise.

    OWNERSHIP: the bytes object is fully owned by Python. The caller
    must keep a reference to it for as long as C might be reading from
    a pointer into it — or better, use the arena-copy path in abi.py.
    """
    out = bytes([n.kind]) + struct.pack("<i", n.line)

    if n.kind == NK.BOOL:
        out += bytes([1 if n.lit_bool else 0])
    elif n.kind == NK.INT:
        out += struct.pack("<q", n.lit_int)
    elif n.kind == NK.REAL:
        out += struct.pack("<d", n.lit_real)
    elif n.kind in (NK.TEXT, NK.VAR, NK.CALL, NK.ANCHOR, NK.ASSM):
        s = (n.str_val or "").encode("utf-8")
        out += struct.pack("<H", len(s)) + s
    elif n.kind == NK.ERR:
        s = (n.error or "").encode("utf-8")
        out += struct.pack("<H", len(s)) + s
    elif n.kind == NK.DEF:
        s = (n.str_val or "").encode("utf-8")
        out += struct.pack("<H", len(s)) + s
        out += struct.pack("<i", len(n.params))
        for p in n.params:
            pb = p.encode("utf-8")
            out += struct.pack("<H", len(pb)) + pb

    out += struct.pack("<i", len(n.children))
    for ch in n.children:
        out += serialise(ch)
    return out


def deserialise(buf: bytes, pos: int = 0) -> Tuple[EvNode, int]:
    """bytes → (EvNode, bytes_consumed). Same format as C ev_ir_deserialise."""
    kind = NK(buf[pos]); pos += 1
    line = struct.unpack_from("<i", buf, pos)[0]; pos += 4

    n = EvNode(kind=kind, line=line)

    if kind == NK.BOOL:
        n.lit_bool = bool(buf[pos]); pos += 1
    elif kind == NK.INT:
        n.lit_int = struct.unpack_from("<q", buf, pos)[0]; pos += 8
    elif kind == NK.REAL:
        n.lit_real = struct.unpack_from("<d", buf, pos)[0]; pos += 8
    elif kind in (NK.TEXT, NK.VAR, NK.CALL, NK.ANCHOR, NK.ASSM):
        slen = struct.unpack_from("<H", buf, pos)[0]; pos += 2
        n.str_val = buf[pos:pos+slen].decode("utf-8", errors="replace"); pos += slen
    elif kind == NK.ERR:
        slen = struct.unpack_from("<H", buf, pos)[0]; pos += 2
        n.error = buf[pos:pos+slen].decode("utf-8", errors="replace"); pos += slen
    elif kind == NK.DEF:
        slen = struct.unpack_from("<H", buf, pos)[0]; pos += 2
        n.str_val = buf[pos:pos+slen].decode("utf-8", errors="replace"); pos += slen
        np = struct.unpack_from("<i", buf, pos)[0]; pos += 4
        for _ in range(np):
            plen = struct.unpack_from("<H", buf, pos)[0]; pos += 2
            n.params.append(buf[pos:pos+plen].decode("utf-8", errors="replace"))
            pos += plen

    nc = struct.unpack_from("<i", buf, pos)[0]; pos += 4
    for _ in range(nc):
        # deserialise returns absolute pos after the child; advance by that
        child, new_pos = deserialise(buf, pos)
        n.children.append(child)
        pos = new_pos   # new_pos is absolute, not relative

    return n, pos


# ─────────────────────────────────────────────
# The parse result — owns the tree
# ─────────────────────────────────────────────

@dataclass
class ParseResult:
    """A completed parse. The tree and all its nodes are owned here.

    OWNERSHIP: The ParseResult owns the tree. Callers may read from it
    freely. When the caller drops the reference, Python GC reclaims
    everything. No manual free required on the Python side.

    For cross-language transfer, call .to_bytes() and pass the bytes to C.
    C must copy into its arena before the Python caller drops the bytes.
    """
    root:       Optional[EvNode] = None
    error:      Optional[str]    = None
    error_line: int              = 0
    node_count: int              = 0
    src_tag:    str              = ""

    @property
    def ok(self) -> bool:
        return self.root is not None and self.error is None

    def to_bytes(self) -> Optional[bytes]:
        """Serialise the tree to the cross-language wire format.

        The returned bytes are fully Python-owned. Pass them to C only
        if C will copy them into its own arena before this method's
        return value could be GC'd.
        """
        if not self.root:
            return None
        return serialise(self.root)

    def distinct_skeletons(self, bodies: List[str]) -> Tuple[int, Dict[str, int]]:
        """Count genuinely distinct program skeletons.

        Replaces the string-based distinct_skeletons() in syntax.py.
        Now works through EvNodes so 'if n < 1 ...' and 'if n <= 0 ...'
        correctly count as one idea.
        """
        from .syntax import parse
        counts: Dict[str, int] = {}
        for b in bodies:
            node, err = parse(b)
            if node is None:
                continue
            ir = _ast_to_ir(node)
            if ir:
                sk = ir.skeleton()
                counts[sk] = counts.get(sk, 0) + 1
        return len(counts), counts


def _ast_to_ir(ast_node) -> Optional[EvNode]:
    """Convert syntax.py AST nodes to EvNode IR.

    This is the bridge that makes the Python parser's output compatible
    with the C execution engine. Called once per parse result; the
    resulting EvNode tree is what gets serialised and transmitted.
    """
    try:
        from .syntax import (
            Num, Str, Bool, Var, BinOp, If, Call, FnDef, ZLit,
            ListLit, RecordLit, UnaryOp, Index, Field,
            ForRange, ForIn, While
        )
    except ImportError:
        from syntax import (
            Num, Str, Bool, Var, BinOp, If, Call, FnDef, ZLit,
            ListLit, RecordLit, UnaryOp, Index, Field,
            ForRange, ForIn, While
        )

    if ast_node is None:
        return None

    t = type(ast_node).__name__

    if t == "Num":
        v = ast_node.value
        if v == int(v):
            return EvNode.int_lit(int(v))
        return EvNode.real_lit(v)

    if t == "Str":
        return EvNode.text_lit(ast_node.value)

    if t == "Bool":
        return EvNode.bool_lit(ast_node.value)

    if t == "ListLit":
        n = EvNode(kind=NK.LIST)
        n.children = [_ast_to_ir(i) for i in ast_node.items]
        return n

    if t == "RecordLit":
        n = EvNode(kind=NK.RECORD)
        n.children = [_ast_to_ir(v) for v in ast_node.values]
        n.keys = list(ast_node.keys)
        return n

    if t == "UnaryOp":
        n = EvNode(kind=NK.NOT)
        n.children = [_ast_to_ir(ast_node.operand)]
        return n

    if t == "Index":
        n = EvNode(kind=NK.INDEX)
        n.children = [_ast_to_ir(ast_node.target), _ast_to_ir(ast_node.key)]
        return n

    if t == "Field":
        n = EvNode(kind=NK.FIELD)
        n.children = [_ast_to_ir(ast_node.target)]
        n.str_val = ast_node.name
        return n

    if t == "ForRange":
        n = EvNode(kind=NK.FOR_RANGE)
        n.str_val = ast_node.var
        step_ir = _ast_to_ir(ast_node.step) if ast_node.step else None
        n.children = [_ast_to_ir(ast_node.start), _ast_to_ir(ast_node.end),
                     _ast_to_ir(ast_node.body)]
        if step_ir is not None:
            n.children.append(step_ir)
        return n

    if t == "ForIn":
        n = EvNode(kind=NK.FOR_IN)
        n.str_val = ast_node.var
        n.children = [_ast_to_ir(ast_node.seq), _ast_to_ir(ast_node.body)]
        return n

    if t == "While":
        n = EvNode(kind=NK.WHILE)
        n.children = [_ast_to_ir(ast_node.cond), _ast_to_ir(ast_node.body)]
        return n

    if t == "BinOp" and ast_node.op in ("and", "or"):
        n = EvNode(kind=(NK.AND if ast_node.op == "and" else NK.OR))
        n.children = [_ast_to_ir(ast_node.left), _ast_to_ir(ast_node.right)]
        return n

    if t == "ZLit":
        n = EvNode.void_lit()
        n.kind = NK.Z
        return n

    if t == "Var":
        return EvNode.var(ast_node.name)

    if t == "BinOp":
        left  = _ast_to_ir(ast_node.left)
        right = _ast_to_ir(ast_node.right)
        if left and right and ast_node.op in OP_STR:
            return EvNode.binop(ast_node.op, left, right)
        return EvNode.err(f"unknown op {ast_node.op}")

    if t == "If":
        cond  = _ast_to_ir(ast_node.cond)
        then  = _ast_to_ir(ast_node.then)
        els   = _ast_to_ir(ast_node.els)
        if cond and then and els:
            return EvNode.if_node(cond, then, els)

    if t == "Call":
        args = [_ast_to_ir(a) for a in ast_node.args]
        if all(a is not None for a in args):
            return EvNode.fn_call(ast_node.name, args)

    if t == "FnDef":
        body = _ast_to_ir(ast_node.body)
        if body:
            return EvNode.fn_def(ast_node.name, ast_node.params, body)

    return EvNode.err(f"cannot convert {t}")


def parse_to_ir(src: str, tag: str = "source") -> ParseResult:
    """Parse Ever source → ParseResult containing an EvNode tree.

    This is the clean entry point that replaces calling compile_ever()
    and then eval_ast() separately. The parser runs entirely here;
    the execution engine receives only the EvNode tree and constants.

    Platform independence: this function imports only standard library
    modules and Ever constants. It does not import the runtime (ever.py
    abstract.py, vowels.py). The runtime receives the tree; it does not
    participate in producing it.
    """
    try:
        from .syntax import parse, Semantic
    except ImportError:
        from syntax import parse, Semantic

    r = ParseResult(src_tag=tag)
    ast, err = parse(src)
    if err:
        r.error      = err.reason
        r.error_line = getattr(err, "lo", 0)
        return r

    sem = Semantic()
    analysis = sem.analyse(ast)
    if analysis.errors:
        r.error      = "; ".join(analysis.errors)
        r.error_line = 1
        return r

    ir = _ast_to_ir(ast)
    if ir is None:
        r.error = "AST to IR conversion failed"
        return r

    ir.measure()
    r.root       = ir
    r.node_count = ir.size
    return r
