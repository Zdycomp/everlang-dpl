#!/usr/bin/env python3
"""Single-machine Lex -> Parse -> Execute pipeline.

ParseLexExecutor composes the existing lexer, parser/semantic pass, and real
runtime executor. It returns every stage result in one object and stops at the
first failing stage without hiding diagnostics.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from forgive import _strip_semicolons, parse_forgiving
from runtime import run_source
from syntax import Semantic, Program, lex, Unparsed


@dataclass
class Stage:
    name: str
    status: str
    detail: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineResult:
    stages: List[Stage]
    outputs: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    recoveries: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors and all(stage.status == "passed" for stage in self.stages)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "stages": [asdict(stage) for stage in self.stages],
            "outputs": self.outputs,
            "errors": self.errors,
            "recoveries": self.recoveries,
        }


class ParseLexExecutor:
    """Run lexing, parsing, semantic validation, and execution in one process."""

    def run(self, source: str) -> PipelineResult:
        stages: List[Stage] = []
        tokens, lex_error = lex(_strip_semicolons(source)[0])
        if lex_error is not None:
            stages.append(Stage("lex", "failed", str(lex_error), {"tokens": len(tokens)}))
            return PipelineResult(stages, errors=[str(lex_error)])
        stages.append(Stage("lex", "passed", metrics={"tokens": len(tokens)}))

        node, parse_error, corrections = parse_forgiving(source)
        recoveries = [correction.line1() for correction in corrections]
        if parse_error is not None or isinstance(node, Unparsed):
            detail = str(parse_error) if parse_error is not None else "parser returned no AST"
            stages.append(Stage("parse", "failed", detail))
            return PipelineResult(stages, errors=[detail], recoveries=recoveries)
        stages.append(Stage("parse", "passed", metrics={
            "ast_type": type(node).__name__,
            "nodes": node.size(),
            "depth": node.depth(),
            "recoveries": len(corrections),
        }))

        program = node if isinstance(node, Program) else Program([node])
        analysis = Semantic(source=source).analyse_program(program)
        if not analysis.clean:
            stages.append(Stage("semantic", "failed",
                                "; ".join(analysis.errors),
                                {"statements": len(program.statements)}))
            return PipelineResult(stages, errors=list(analysis.errors),
                                  recoveries=recoveries)
        stages.append(Stage("semantic", "passed", metrics={
            "statements": len(program.statements),
            "bindings": len(analysis.bound),
            "shown": len(analysis.shown),
        }))

        result = run_source(source)
        recoveries += result.recoveries
        if not result.ok:
            stages.append(Stage("execute", "failed", "; ".join(result.errors)))
            return PipelineResult(stages, errors=list(result.errors),
                                  recoveries=recoveries)
        stages.append(Stage("execute", "passed", metrics={
            "outputs": len(result.shown),
            "recoveries": len(recoveries),
        }))
        return PipelineResult(stages, result.format_lines(),
                              recoveries=recoveries)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run Ever Lex -> Parse -> Execute in one process")
    parser.add_argument("file", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if not args.file.exists():
        parser.error(f"no such file: {args.file}")
    result = ParseLexExecutor().run(args.file.read_text())
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    else:
        for stage in result.stages:
            print(f"[{stage.status.upper()}] {stage.name}: {stage.detail or 'complete'}")
        for recovery in result.recoveries:
            print(f"note: {recovery}")
        for output in result.outputs:
            print(output)
        for error in result.errors:
            print(f"error: {error}", file=sys.stderr)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
