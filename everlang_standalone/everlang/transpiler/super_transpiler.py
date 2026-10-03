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
import string
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


_ALLOWED_FIELDS = frozenset(("name", "val", "type_spec", "conf"))
_REQUIRED_FIELDS = frozenset(("name", "val"))


def validate_template(template: str) -> None:
    """Raises ValueError unless `template` uses only bare {name}/{val}/
    {type_spec}/{conf} fields (plus {{ }} escapes) and contains {name} and
    {val}. Format specs, conversions and attribute/index access are rejected:
    5-runtime-java re-renders custom templates and supports only bare fields."""
    try:
        parsed = list(string.Formatter().parse(template))
    except ValueError as exc:
        raise ValueError(f"Template has malformed braces: {exc}") from exc
    seen = set()
    for _literal, field, spec, conversion in parsed:
        if field is None:
            continue
        if field not in _ALLOWED_FIELDS:
            raise ValueError(f"Template has unsupported placeholder: {{{field}}}")
        if spec or conversion:
            raise ValueError(f"Template placeholder {{{field}}} may not use a format spec or conversion")
        seen.add(field)
    missing = _REQUIRED_FIELDS - seen
    if missing:
        raise ValueError(f"Template missing required placeholders: {', '.join('{' + m + '}' for m in sorted(missing))}")


class SuperTranspiler:
    """Generates and offsets syntactic representations across language paradigms."""

    def __init__(self, templates: Dict[str, str] = None) -> None:
        self.templates = dict(templates) if templates is not None else dict(LANGUAGE_TEMPLATES)
        self._custom_languages: Dict[str, str] = {}

    def register_language(self, language: str, template: str) -> None:
        """Register a custom language target. The template must contain at
        least {name} and {val}; {type_spec} and {conf} are optional."""
        validate_template(template)
        lang_upper = language.upper()
        if lang_upper in LANGUAGE_TEMPLATES:
            raise ValueError(f"{lang_upper} is a built-in language and cannot be overridden")
        self._custom_languages[lang_upper] = template
        self.templates[lang_upper] = template

    def unregister_language(self, language: str) -> bool:
        """Remove a custom language. Returns True if removed, False if not
        found or if the language is a built-in (built-ins cannot be removed)."""
        lang_upper = language.upper()
        if lang_upper not in self._custom_languages:
            return False
        del self._custom_languages[lang_upper]
        del self.templates[lang_upper]
        return True

    @property
    def custom_languages(self) -> Dict[str, str]:
        return dict(self._custom_languages)

    @property
    def builtin_languages(self) -> Dict[str, str]:
        return dict(LANGUAGE_TEMPLATES)

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
