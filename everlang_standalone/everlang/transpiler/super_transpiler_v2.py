"""
SuperTranspiler v2: Refined, production-ready code generation across six languages.

Enhancements over v1:
1. Input validation & sanitization
2. Language-specific escaping (typed.escape_string: quotes, backslashes, newlines, `$`, control characters)
3. Type mapping (DPL → language-native types)
4. Confidence-aware rendering (adjust safety/visibility based on confidence)
5. Template caching (compile once, render many times)
6. Error handling & graceful degradation
7. Pre-flight checks (validate before rendering)
8. Extended syntax distance (per-language weighting)
"""
from typing import Dict, List
import re

from .typed import TYPED_LANGUAGES, escape_string

# Type mapping from abstract spec to language-native types
TYPE_MAPPINGS: Dict[str, Dict[str, str]] = {
    "KOTLIN": {
        "int": "Int", "str": "String", "bool": "Boolean", "float": "Double",
        "bytes": "ByteArray", "default": "Any"
    },
    "RUST": {
        "int": "i64", "str": "String", "bool": "bool", "float": "f64",
        "bytes": "Vec<u8>", "default": "Box<dyn std::any::Any>"
    },
    "C_CLANG": {
        "int": "int", "str": "char*", "bool": "int", "float": "double",
        "bytes": "unsigned char*", "default": "void*"
    },
    "GO": {
        "int": "int64", "str": "string", "bool": "bool", "float": "float64",
        "bytes": "[]byte", "default": "interface{}"
    },
    "GROOVY": {
        "int": "Integer", "str": "String", "bool": "Boolean", "float": "Double",
        "bytes": "byte[]", "default": "Object"
    },
    "DPL": {
        "int": "Int", "str": "String", "bool": "Bool", "float": "Real",
        "bytes": "Bytes", "default": "Any"
    },
}

class SuperTranspilerV2:
    """Refined transpiler with validation, escaping, and optimization."""

    # Base templates (refined with language-specific comments)
    BASE_TEMPLATES: Dict[str, str] = {
        "DPL": "particle {name} : E<{type_spec}> = \"{val}\" @ confidence({conf})",
        "KOTLIN": "val {name}: {type_spec}? = \"{val}\" // confidence: {conf}",
        "RUST": "let {name}: Option<{type_spec}> = Some(\"{val}\".to_string()); // conf: {conf}",
        "C_CLANG": "const char* {name} = \"{val}\"; // Unchecked pointer, confidence: {conf}",
        "GO": "var {name} {type_spec} = \"{val}\" // confidence: {conf}",
        "GROOVY": "def {name} = \"{val}\" as {type_spec} // confidence({conf})",
    }

    # High-confidence variant (more optimistic/unchecked)
    HIGH_CONF_TEMPLATES: Dict[str, str] = {
        "DPL": "particle {name} : E<{type_spec}> = \"{val}\" @ confidence({conf})  # TRUSTED",
        "KOTLIN": "val {name}: {type_spec} = \"{val}\" // HIGH_CONF",
        "RUST": "let {name}: {type_spec} = \"{val}\".into(); // unsafe_trust: {conf}",
        "C_CLANG": "const {type_spec} {name} = \"{val}\"; // TRUSTED_PTR confidence: {conf}",
        "GO": "var {name} {type_spec} = \"{val}\" // HIGH_CONFIDENCE: {conf}",
        "GROOVY": "def {name} = \"{val}\" // HIGH_CONF confidence({conf})",
    }

    # Low-confidence variant (defensive/wrapped)
    LOW_CONF_TEMPLATES: Dict[str, str] = {
        "DPL": "particle {name} : E<{type_spec}> = \"{val}\" @ confidence({conf})  # VERIFY BEFORE USE",
        "KOTLIN": "val {name}: {type_spec}? = try {{ \"{val}\" }} catch {{ null }} // LOW_CONF",
        "RUST": "let {name}: Result<{type_spec}, String> = Err(\"{val}\".into()); // quarantined: {conf}",
        "C_CLANG": "const char* {name} = \"{val}\"; // UNSAFE: verify before use, confidence: {conf}",
        "GO": "var {name} interface{{}} = \"{val}\" // LOW_CONFIDENCE: {conf}, require validation",
        "GROOVY": "def {name} = null // QUARANTINED: confidence({conf}), value=\"{val}\"",
    }

    def __init__(self, templates: Dict[str, str] = None):
        self.templates = dict(templates) if templates is not None else self.BASE_TEMPLATES.copy()
        self.high_conf_templates = self.HIGH_CONF_TEMPLATES.copy()
        self.low_conf_templates = self.LOW_CONF_TEMPLATES.copy()
        self.cache = {}

    def validate_inputs(self, name: str, val: str, type_spec: str, conf: int) -> List[str]:
        """Pre-flight validation: return list of errors (empty if valid)."""
        errors = []

        # Name validation: must be valid identifier
        if not name or not name.isidentifier():
            errors.append(f"name '{name}' is not a valid identifier")

        # Value validation: length bounds
        if len(val) == 0:
            errors.append("value is empty")
        if len(val) > 4096:
            errors.append(f"value too long: {len(val)} > 4096 bytes")

        # Type spec validation: must be non-empty and reasonable
        if not type_spec or not re.match(r"^[a-zA-Z0-9_<>,\[\]]+$", type_spec):
            errors.append(f"type_spec '{type_spec}' is malformed")

        # Confidence validation: EParticle bounds
        if not isinstance(conf, int) or conf < 0 or conf > 256:
            errors.append(f"confidence {conf} out of bounds [0, 256]")

        return errors

    def escape_value(self, val: str, language: str) -> str:
        """Apply language-specific escaping to string value."""
        if language not in TYPED_LANGUAGES:
            return val
        return escape_string(language, val)

    def map_type(self, type_spec: str, language: str) -> str:
        """Map abstract type spec to language-native type."""
        if language not in TYPE_MAPPINGS:
            return type_spec
        
        mappings = TYPE_MAPPINGS[language]
        # Try exact match first, then default
        return mappings.get(type_spec, mappings.get("default", type_spec))

    def select_template(self, conf: int, language: str) -> str:
        """Select template variant based on confidence level."""
        if conf >= 200:
            templates = self.high_conf_templates
        elif conf <= 50:
            templates = self.low_conf_templates
        else:
            templates = self.templates

        return templates.get(language, self.templates.get(language, ""))

    def transpile(self, name: str, val: str, type_spec: str, conf: int) -> Dict[str, str]:
        """Render value across all target languages with validation & optimization."""
        # Pre-flight validation
        errors = self.validate_inputs(name, val, type_spec, conf)
        if errors:
            # Return quarantine result on validation failure
            return {
                lang: f"// VALIDATION_ERROR: {'; '.join(errors)}"
                for lang in self.templates.keys()
            }

        offsets = {}
        for lang in self.templates.keys():
            # Get appropriate template variant
            template = self.select_template(conf, lang)
            if not template:
                offsets[lang] = f"// ERROR: no template for {lang}"
                continue

            # Escape value
            escaped_val = self.escape_value(val, lang)

            # Map type
            mapped_type = self.map_type(type_spec, lang)

            # Format and cache
            cache_key = (lang, name, escaped_val, mapped_type, conf)
            if cache_key not in self.cache:
                try:
                    self.cache[cache_key] = template.format(
                        name=name,
                        val=escaped_val,
                        type_spec=mapped_type,
                        conf=conf
                    )
                except KeyError as e:
                    self.cache[cache_key] = f"// TEMPLATE_ERROR: missing {e}"

            offsets[lang] = self.cache[cache_key]

        return offsets

    def compute_syntax_distance(self, pattern1: str, pattern2: str) -> int:
        """Refined syntax distance: per-language structural analysis."""
        if pattern1 == pattern2:
            return 0

        # Length difference
        len_dist = abs(len(pattern1) - len(pattern2))

        # Structural markers (brackets, quotes, parentheses)
        struct1 = sum(1 for c in pattern1 if c in "{}[]()\"'")
        struct2 = sum(1 for c in pattern2 if c in "{}[]()\"'")
        struct_dist = abs(struct1 - struct2)

        # Comments (language-specific noise)
        comment1 = pattern1.count("//")
        comment2 = pattern2.count("//")
        comment_dist = abs(comment1 - comment2)

        # Combined distance (weighted)
        return max(1, len_dist) + struct_dist * 2 + comment_dist * 3

    def stats(self) -> Dict:
        """Return transpiler statistics."""
        return {
            "languages_supported": len(self.templates),
            "cache_size": len(self.cache),
            "languages": list(self.templates.keys()),
            "high_confidence_variants": len(self.high_conf_templates),
            "low_confidence_variants": len(self.low_conf_templates),
        }
