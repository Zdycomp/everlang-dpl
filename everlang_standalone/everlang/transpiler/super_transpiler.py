"""
SuperTranspiler: renders one (name, value, type) triple as equivalent-looking
syntax across six target languages.

This promotes the template-based generator that already existed as
benchmarks/ez_micro_containers.py::SyntaxMutatorContainer into the real
package, verbatim for the five languages it already covered (DPL, KOTLIN,
RUST, C_CLANG, GO), plus one new language (GROOVY). It does not invent a
grammar or parser for Everlang/DPL itself -- there is no SEMANTICS.md and no
textual Everlang parser to transpile *from*. This is a syntax-offset
generator: given one value, show how six different languages would declare
it, exactly as the existing benchmark already demonstrated for five of them.

Each rendered string is runnable/valid syntax in its own language (checked
by hand, not invented): Kotlin's nullable-type declaration, Rust's
Option<T>, a raw (deliberately unchecked) C pointer, Go's var declaration,
and Groovy's `as` type-coercion operator are all real language features.
"""
from typing import Dict

# DPL, KOTLIN, RUST, C_CLANG, GO are verbatim from
# benchmarks/ez_micro_containers.py::SyntaxMutatorContainer.PARADIGMS.
LANGUAGE_TEMPLATES: Dict[str, str] = {
    "DPL": "particle {name} : E<{type_spec}> = \"{val}\" @ confidence({conf})",
    "KOTLIN": "val {name}: {type_spec}? = \"{val}\"",
    "RUST": "let {name}: Option<{type_spec}> = Some(\"{val}\".to_string());",
    "C_CLANG": "const char* {name} = \"{val}\"; // Unchecked pointer",
    "GO": "var {name} string = \"{val}\"",
    # New: Groovy's `as` operator performs a real runtime type coercion,
    # mirroring the type-annotated style of the other five templates.
    "GROOVY": "def {name} = \"{val}\" as {type_spec} // confidence({conf})",
}


class SuperTranspiler:
    """Generates and offsets syntactic representations across language paradigms."""

    def __init__(self, templates: Dict[str, str] = None) -> None:
        self.templates = dict(templates) if templates is not None else dict(LANGUAGE_TEMPLATES)

    def transpile(self, name: str, val: str, type_spec: str, conf: int) -> Dict[str, str]:
        """Renders `val` (typed as `type_spec`, carrying confidence `conf`)
        into every configured target language. Pure string formatting --
        no execution, no code generation beyond template substitution."""
        offsets = {}
        for lang, template in self.templates.items():
            offsets[lang] = template.format(name=name, val=val, type_spec=type_spec, conf=conf)
        return offsets

    def compute_syntax_distance(self, pattern1: str, pattern2: str) -> int:
        """Ported verbatim from the original benchmark: a coarse structural
        distance between two rendered patterns, not a real diff metric."""
        if pattern1 == pattern2:
            return 0
        return abs(len(pattern1) - len(pattern2)) % 5 + 1
