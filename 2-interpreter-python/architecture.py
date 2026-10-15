"""Blueprint pipeline: tolerant front-end, canonical IR, source maps, feedback loop.

This module coordinates existing Ever components. It does not replace the
reference parser or emitters; it gives them explicit contracts for diagnostics,
source mapping, and bounded self-correction.
"""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field, is_dataclass, asdict
from enum import Enum
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from syntax import lex, parse, Node
from emit import emit


class CorrectionStatus(str, Enum):
    GENERATION = "GENERATION"
    EXECUTION = "EXECUTION"
    DIAGNOSTICS = "DIAGNOSTICS"
    REFLECTION = "REFLECTION"
    REFINEMENT = "REFINEMENT"
    CONVERGED = "CONVERGED"
    BUG_DETECTED = "BUG_DETECTED"
    OPTIMIZATION_ONLY = "OPTIMIZATION_ONLY"
    STALLED = "STALLED"
    EXHAUSTED = "EXHAUSTED"


@dataclass(frozen=True)
class CSTNode:
    kind: str
    text: str = ""
    start: int = 0
    end: int = 0
    children: Tuple["CSTNode", ...] = ()
    error: bool = False
    missing: bool = False


@dataclass(frozen=True)
class Diagnostic:
    level: str
    code: str
    message: str
    generated_line: int = 0
    generated_column: int = 0
    node_id: Optional[str] = None
    original_line: Optional[int] = None
    original_column: Optional[int] = None


@dataclass(frozen=True)
class IRNode:
    node_id: str
    kind: str
    fields: Dict[str, Any] = field(default_factory=dict)
    children: Tuple["IRNode", ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.node_id,
            "kind": self.kind,
            "fields": self.fields,
            "children": [child.to_dict() for child in self.children],
        }


@dataclass(frozen=True)
class SourceMapping:
    generated_line: int
    generated_column: int
    original_line: int
    original_column: int
    node_id: str


@dataclass
class SourceMap:
    version: int = 3
    file: str = ""
    sources: List[str] = field(default_factory=list)
    names: List[str] = field(default_factory=list)
    mappings: List[SourceMapping] = field(default_factory=list)

    def add(self, generated_line: int, generated_column: int,
            original_line: int, original_column: int, node_id: str) -> None:
        self.mappings.append(SourceMapping(
            generated_line, generated_column, original_line,
            original_column, node_id))

    def locate(self, generated_line: int, generated_column: int) -> Optional[SourceMapping]:
        candidates = [m for m in self.mappings
                      if m.generated_line == generated_line
                      and m.generated_column <= generated_column]
        return max(candidates, key=lambda m: m.generated_column) if candidates else None

    def remap(self, diagnostic: Diagnostic) -> Diagnostic:
        """Map a generated diagnostic back to source and IR coordinates."""
        mapping = self.locate(diagnostic.generated_line, diagnostic.generated_column)
        if mapping is None:
            return diagnostic
        return Diagnostic(
            level=diagnostic.level, code=diagnostic.code,
            message=diagnostic.message,
            generated_line=diagnostic.generated_line,
            generated_column=diagnostic.generated_column,
            node_id=mapping.node_id,
            original_line=mapping.original_line,
            original_column=mapping.original_column,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "file": self.file,
            "sources": self.sources,
            "names": self.names,
            "mappings": encode_vlq_mappings(self.mappings),
            "x_nodeMappings": [asdict(mapping) for mapping in self.mappings],
        }


@dataclass
class PipelineResult:
    source: str
    cst: CSTNode
    ir: Optional[IRNode]
    diagnostics: List[Diagnostic]
    generated: Dict[str, str]
    source_maps: Dict[str, SourceMap]


@dataclass
class CorrectionCycle:
    cycle: int
    status: CorrectionStatus
    diagnostics: List[Diagnostic] = field(default_factory=list)
    changed: bool = False


def _cst_from_source(source: str) -> CSTNode:
    lines = source.splitlines(keepends=True)
    children = []
    offset = 0
    for line in lines:
        children.append(CSTNode("ERROR", line, offset, offset + len(line), error=True))
        offset += len(line)
    if not children:
        children.append(CSTNode("ERROR", "", 0, 0, error=True))
    return CSTNode("SOURCE_WITH_ERRORS", source, 0, len(source),
                   tuple(children), error=True)


def _ir_from_ast(node: Optional[Node], path: str = "0") -> Optional[IRNode]:
    if node is None:
        return None
    fields: Dict[str, Any] = {}
    children: List[IRNode] = []
    for name, value in vars(node).items():
        if isinstance(value, Node):
            child = _ir_from_ast(value, f"{path}.{name}")
            if child:
                children.append(child)
        elif isinstance(value, list) and value and all(isinstance(item, Node) for item in value):
            for index, item in enumerate(value):
                child = _ir_from_ast(item, f"{path}.{name}[{index}]")
                if child:
                    children.append(child)
        elif not name.startswith("_"):
            fields[name] = value
    return IRNode(f"{path}:{type(node).__name__}", type(node).__name__, fields,
                  tuple(children))


def front_end(source: str) -> Tuple[CSTNode, Optional[Node], List[Diagnostic]]:
    tokens, lex_error = lex(source)
    if lex_error:
        return _cst_from_source(source), None, [Diagnostic(
            "error", "LEX", str(lex_error))]
    ast, parse_error = parse(source)
    if parse_error:
        return _cst_from_source(source), None, [Diagnostic(
            "error", "PARSE", str(parse_error))]
    return CSTNode("SOURCE", source, 0, len(source)), ast, []


def _vlq(value: int) -> str:
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
    value = ((-value) << 1 | 1) if value < 0 else (value << 1)
    out = []
    while True:
        digit = value & 31
        value >>= 5
        if value:
            digit |= 32
        out.append(alphabet[digit])
        if not value:
            return "".join(out)


def encode_vlq_mappings(mappings: Iterable[SourceMapping]) -> str:
    """Encode line mappings using the Source Map Revision 3 VLQ alphabet."""
    by_line: Dict[int, List[SourceMapping]] = {}
    for mapping in mappings:
        by_line.setdefault(mapping.generated_line, []).append(mapping)
    if not by_line:
        return ""
    segments: List[str] = []
    previous_source = previous_original_line = previous_original_column = 0
    for line in range(max(by_line) + 1):
        line_segments = []
        previous_generated_column = 0
        for mapping in sorted(by_line.get(line, []), key=lambda item: item.generated_column):
            fields = [
                mapping.generated_column - previous_generated_column,
                0 - previous_source,
                mapping.original_line - previous_original_line,
                mapping.original_column - previous_original_column,
            ]
            line_segments.append("".join(_vlq(value) for value in fields))
            previous_generated_column = mapping.generated_column
            previous_source = 0
            previous_original_line = mapping.original_line
            previous_original_column = mapping.original_column
        segments.append(",".join(line_segments))
    return ";".join(segments)


def compile_pipeline(source: str, targets: Iterable[str] = ()) -> PipelineResult:
    cst, ast, diagnostics = front_end(source)
    ir = _ir_from_ast(ast)
    generated: Dict[str, str] = {}
    source_maps: Dict[str, SourceMap] = {}
    if ir is not None:
        for target in targets:
            try:
                code = emit(source, target)
            except Exception as exc:
                diagnostics.append(Diagnostic("error", "EMIT", str(exc), node_id=ir.node_id))
                continue
            generated[target] = code
            mapping = SourceMap(file=f"program.{target}", sources=["<source>"])
            for line_number, _ in enumerate(code.splitlines()):
                mapping.add(line_number, 0, 0, 0, ir.node_id)
            source_maps[target] = mapping
    return PipelineResult(source, cst, ir, diagnostics, generated, source_maps)


def correction_loop(source: str, target: str,
                    execute: Callable[[str, str], List[Diagnostic]],
                    refine: Optional[Callable[[str, List[Diagnostic]], Optional[str]]] = None,
                    max_cycles: int = 3) -> List[CorrectionCycle]:
    if max_cycles < 1:
        raise ValueError("max_cycles must be at least 1")
    current = source
    history: List[CorrectionCycle] = []
    for cycle in range(max_cycles):
        compiled = compile_pipeline(current, [target])
        diagnostics = list(compiled.diagnostics)
        if not diagnostics and target in compiled.generated:
            diagnostics.extend(execute(compiled.generated[target], target))
        if not diagnostics:
            history.append(CorrectionCycle(cycle, CorrectionStatus.CONVERGED))
            return history
        replacement = refine(current, diagnostics) if refine else None
        changed = replacement is not None and replacement != current
        history.append(CorrectionCycle(cycle, CorrectionStatus.BUG_DETECTED, diagnostics, changed))
        if not changed:
            history[-1].status = CorrectionStatus.STALLED
            return history
        current = replacement
    # The budget ran out with the last refinement never re-verified.
    history[-1].status = CorrectionStatus.EXHAUSTED
    return history


def pipeline_json(result: PipelineResult) -> str:
    return json.dumps({
        "cst": asdict(result.cst),
        "ir": result.ir.to_dict() if result.ir else None,
        "diagnostics": [asdict(item) for item in result.diagnostics],
        "generated": result.generated,
        "source_maps": {key: value.to_dict() for key, value in result.source_maps.items()},
    }, indent=2, sort_keys=True)
