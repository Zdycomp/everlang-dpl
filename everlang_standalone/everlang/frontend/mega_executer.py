"""MegaExecuter: same semantics and output as BaselineExecutor, with direct type
dispatch instead of per-node getattr, and every language's template compiled
into one generated f-string function instead of a str.format call per language."""
import string
from typing import Callable, Dict, Tuple

from ..core.particle import EParticle
from ..core.phase_engine import PhaseEngine
from ..transpiler import VALUE_ESCAPES, SuperTranspiler, TypedValue
from ..transpiler.typed import NEEDS_ESCAPE_ANY
from .grammar import Collision, Declaration
from .results import (
    CollisionResult, DeclarationResult, ExecutionResult, already_bound, clamped, unbound,
)


_FIELDS = frozenset(("name", "val", "type_spec", "conf"))
_COMPILED: Dict[Tuple[Tuple[str, str], ...], Callable] = {}
_COMPILED_MAX = 64  # each custom-template edit is a new key; bound the cache


def _fstring_source(template: str, val_expr: str = "val"):
    """Python source for an f-string equal to template.format(name=, val=,
    type_spec=, conf=), or None if the template uses anything but bare fields.
    Literal text goes through repr(), and only the four whitelisted names (with
    `val` replaced by the generator's own `val_expr`) can appear inside braces,
    so no template content is ever evaluated as code."""
    try:
        parts = list(string.Formatter().parse(template))
    except ValueError:
        return None
    body = []
    for literal, field, spec, conversion in parts:
        body.append(literal.replace("{", "{{").replace("}", "}}"))
        if field is not None:
            if field not in _FIELDS or spec or conversion:
                return None
            body.append("{" + (val_expr if field == "val" else field) + "}")
    return "f" + repr("".join(body))


def compile_renderer(templates: Dict[str, str]) -> Callable[[str, str, str, int], Dict[str, str]]:
    """One function rendering every language at once, cached per template set.
    A template that can't be expressed as a plain f-string keeps str.format.
    `val` must be a str. When it contains nothing any built-in language would
    escape (nearly always), the generated function skips every escaper."""
    key = tuple(templates.items())
    renderer = _COMPILED.get(key)
    if renderer is not None:
        return renderer
    namespace = {"_needs_escape": NEEDS_ESCAPE_ANY.search}
    plain, escaped = [], []
    for idx, (lang, template) in enumerate(key):
        escape = VALUE_ESCAPES.get(lang)
        for entries, val_expr in ((plain, "val"), (escaped, f"_esc{idx}(val)" if escape is not None else "val")):
            expr = _fstring_source(template, val_expr)
            if expr is None:
                namespace[f"_fmt{idx}"] = template.format
                expr = f"_fmt{idx}(name=name, val={val_expr}, type_spec=type_spec, conf=conf)"
            entries.append(f"{lang!r}: {expr}")
        if escape is not None:
            namespace[f"_esc{idx}"] = escape
    source = "def render(name, val, type_spec, conf):\n"
    if plain != escaped:
        source += "    if _needs_escape(val) is None:\n        return {" + ", ".join(plain) + "}\n"
    source += "    return {" + ", ".join(escaped) + "}\n"
    exec(compile(source, "<mega-renderer>", "exec"), namespace)
    if len(_COMPILED) >= _COMPILED_MAX:
        _COMPILED.clear()
    renderer = _COMPILED[key] = namespace["render"]
    return renderer


class MegaExecuter:
    def __init__(self, transpiler: SuperTranspiler = None, archive=None) -> None:
        self._transpiler = transpiler or SuperTranspiler()
        self._archive = archive

    def execute(self, statements) -> ExecutionResult:
        result = ExecutionResult()
        env = result.particles
        decls_append = result.declarations.append
        diags_append = result.diagnostics.append
        archive = self._archive
        render = compile_renderer(self._transpiler.templates)

        for node in statements:
            if type(node) is Declaration:
                name, type_spec, value, declared, line = node
                if name in env:
                    diags_append(already_bound(name, line))
                    continue
                if type(value) is TypedValue:
                    particle = EParticle(value.to_python(), declared)
                    conf = particle.confidence
                    if conf != declared:
                        diags_append(clamped(name, declared, conf, line))
                    env[name] = particle
                    if archive is None:
                        renderings = self._transpiler.transpile_typed(name, value, type_spec, conf)
                    else:
                        renderings = archive.transpile_typed_and_archive(name, value, type_spec, conf)
                    decls_append(DeclarationResult(name, type_spec, value, conf, renderings))
                    continue
                particle = EParticle(value, declared)
                conf = particle.confidence
                if conf != declared:
                    diags_append(clamped(name, declared, conf, line))
                env[name] = particle
                if archive is None:
                    renderings = render(name, value, type_spec, conf)
                else:
                    renderings = archive.transpile_and_archive(name, value, type_spec, conf)
                decls_append(DeclarationResult(name, type_spec, value, conf, renderings))
            elif type(node) is Collision:
                self._collide(node, env, result)
        return result

    def _collide(self, node, env, result) -> None:
        left, right, target, line = node
        missing = [n for n in (left, right) if n not in env]
        for n in missing:
            result.diagnostics.append(unbound(n, line))
        if missing:
            return
        if target is not None and target in env:
            result.diagnostics.append(already_bound(target, line))
            return
        outcome = PhaseEngine.collide(env[left], env[right])
        particle = outcome["particle"]
        if self._archive is not None:
            self._archive.log_boundary_marker(f"collide {left} {right}", particle, outcome["reason"])
        result.collisions.append(CollisionResult(
            left, right, target, outcome["outcome"], outcome["reason"], particle.value, particle.confidence))
        if target is not None:
            env[target] = particle
