"""Typed values: numbers, booleans and lists rendered as native literals in
every built-in language, instead of being quoted into string templates.

`TypedValue` is the transpiler's intermediate representation of one value: a
kind (`Int`, `Float`, `Bool`, or `List<Str|Int|Float|Bool>`) plus its items.
Scalar items hold the value's canonical literal text (`str(int)`,
`repr(float)`, `true`/`false`); `Str` list items hold the raw string. Plain
string scalars are not a typed kind: they keep rendering through
`SuperTranspiler.transpile`'s string templates.

`dpl_literal()` is the canonical text of the whole value. It is what a DPL
declaration carries after `=`, what `everlang.frontend` parses back, and what
the SQL archive stores in `transpilations.val` for a typed row, so
5-runtime-java's TranspileAuditor can re-render the row from it. That auditor
duplicates every rule in this file on purpose, as its independent check.
"""
import math
import re
from typing import Dict, NamedTuple, Tuple

STR, INT, FLOAT, BOOL = "Str", "Int", "Float", "Bool"
SCALAR_KINDS = (INT, FLOAT, BOOL)
LIST_KINDS = tuple(f"List<{k}>" for k in (STR, INT, FLOAT, BOOL))
VALUE_KINDS = SCALAR_KINDS + LIST_KINDS

# Symmetric, so every value's negation is representable and `-N` is always a
# valid literal (most of the targets cannot write -9223372036854775808 directly).
INT_LIMIT = 2 ** 63 - 1

_INT_TEXT = re.compile(r"-?[0-9]+")
_FLOAT_TEXT = re.compile(r"-?[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")

TYPED_LANGUAGES = ("DPL", "KOTLIN", "RUST", "C_CLANG", "GO", "GROOVY")

NATIVE_TYPES: Dict[str, Dict[str, str]] = {
    "KOTLIN": {STR: "String", INT: "Long", FLOAT: "Double", BOOL: "Boolean"},
    "RUST": {STR: "String", INT: "i64", FLOAT: "f64", BOOL: "bool"},
    "C_CLANG": {STR: "char*", INT: "long long", FLOAT: "double", BOOL: "bool"},
    "GO": {STR: "string", INT: "int64", FLOAT: "float64", BOOL: "bool"},
    "GROOVY": {STR: "String", INT: "Long", FLOAT: "Double", BOOL: "Boolean"},
}

DEFAULT_TYPE_SPECS = {INT: "Int", FLOAT: "Float", BOOL: "Bool"}


class TypedValue(NamedTuple):
    kind: str
    items: Tuple[str, ...]

    @property
    def is_list(self) -> bool:
        return self.kind.startswith("List<")

    @property
    def element_kind(self) -> str:
        return self.kind[5:-1] if self.is_list else self.kind

    def to_python(self):
        convert = _TO_PYTHON[self.element_kind]
        values = [convert(item) for item in self.items]
        return values if self.is_list else values[0]

    def dpl_literal(self) -> str:
        if not self.is_list:
            return self.items[0]
        if self.element_kind == STR:
            return "[" + ", ".join('"' + escape_string("DPL", s) + '"' for s in self.items) + "]"
        return "[" + ", ".join(self.items) + "]"


_TO_PYTHON = {STR: str, INT: int, FLOAT: float, BOOL: lambda text: text == "true"}


def canonical_int(value: int) -> str:
    if not -INT_LIMIT <= value <= INT_LIMIT:
        raise ValueError(f"integer {value} is outside the 64-bit range ±{INT_LIMIT}")
    return str(value)


def canonical_float(value: float) -> str:
    if not math.isfinite(value):
        raise ValueError(f"float {value!r} is not finite; only finite numbers have a literal in every target")
    return repr(value)


def _scalar(value) -> Tuple[str, str]:
    # bool before int: bool is an int subclass.
    if isinstance(value, bool):
        return BOOL, "true" if value else "false"
    if isinstance(value, int):
        return INT, canonical_int(value)
    if isinstance(value, float):
        return FLOAT, canonical_float(value)
    if isinstance(value, str):
        return STR, value
    raise ValueError(f"unsupported value type {type(value).__name__}")


def infer(value) -> TypedValue:
    """The TypedValue for a Python bool, int, float, or a non-empty list/tuple
    of one of those (or of str). Raises ValueError for anything else,
    including a plain str (render those with SuperTranspiler.transpile)."""
    if isinstance(value, TypedValue):
        validate(value)
        return value
    if isinstance(value, (list, tuple)):
        if not value:
            raise ValueError("an empty list has no element type")
        kinds, items = set(), []
        for element in value:
            if isinstance(element, (list, tuple, dict)):
                raise ValueError("lists hold strings, numbers or booleans, not other lists or tables")
            kind, item = _scalar(element)
            kinds.add(kind)
            items.append(item)
        if len(kinds) > 1:
            raise ValueError(f"list values must all be the same kind, found {', '.join(sorted(kinds))}")
        return TypedValue(f"List<{kinds.pop()}>", tuple(items))
    kind, item = _scalar(value)
    if kind == STR:
        raise ValueError("plain strings render through transpile(); typed values are numbers, booleans and lists")
    return TypedValue(kind, (item,))


def validate(value: TypedValue) -> None:
    """Raises ValueError unless every item is in its kind's canonical form."""
    if value.kind not in VALUE_KINDS:
        raise ValueError(f"unknown value kind {value.kind!r}")
    if not value.items or (not value.is_list and len(value.items) != 1):
        raise ValueError(f"{value.kind} needs {'at least one item' if value.is_list else 'exactly one item'}")
    for item in value.items:
        if not isinstance(item, str):
            raise ValueError(f"{value.kind} item {item!r} is not text")
        kind = value.element_kind
        if kind == INT and not (_INT_TEXT.fullmatch(item) and canonical_int(int(item)) == item):
            raise ValueError(f"{item!r} is not a canonical Int literal")
        if kind == FLOAT and not (_FLOAT_TEXT.fullmatch(item) and canonical_float(float(item)) == item):
            raise ValueError(f"{item!r} is not a canonical Float literal (expected repr(float))")
        if kind == BOOL and item not in ("true", "false"):
            raise ValueError(f"{item!r} is not true or false")


def escape_string(language: str, text: str) -> str:
    """Escapes `text` for a double-quoted literal in `language`: backslash,
    double quote, newline and carriage return everywhere; `$` for Kotlin and
    Groovy (string templates); every other control character except tab in
    each language's own numeric escape; and, in C, each `?` that follows a `?`
    so no trigraph can form. DPL leaves other control characters raw, which its
    grammar allows."""
    out = []
    prev = ""
    for ch in text:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "$" and language in ("KOTLIN", "GROOVY"):
            out.append("\\$")
        elif ch == "?" and prev == "?" and language == "C_CLANG":
            out.append("\\?")
        elif ch < " " and ch != "\t" and language != "DPL":
            code = ord(ch)
            if language == "C_CLANG":
                out.append(f"\\{code:03o}")
            elif language in ("RUST", "GO"):
                out.append(f"\\x{code:02x}")
            else:
                out.append(f"\\u{code:04x}")
        else:
            out.append(ch)
        prev = ch
    return "".join(out)


def _literal(language: str, kind: str, item: str) -> str:
    if kind == STR:
        quoted = '"' + escape_string(language, item) + '"'
        return quoted + ".to_string()" if language == "RUST" else quoted
    if kind == INT and language in ("KOTLIN", "GROOVY"):
        return item + "L"
    if kind == FLOAT and language == "GROOVY":
        return item + "d"
    return item


def render_typed(language: str, name: str, value: TypedValue, type_spec: str, conf: int) -> str:
    """One built-in language's declaration of `value` with its native type."""
    if language == "DPL":
        return f"particle {name} : E<{type_spec}> = {value.dpl_literal()} @ confidence({conf})"
    kind = value.element_kind
    native = NATIVE_TYPES[language][kind]
    literals = [_literal(language, kind, item) for item in value.items]
    if not value.is_list:
        lit = literals[0]
        if language == "KOTLIN":
            return f"val {name}: {native}? = {lit}"
        if language == "RUST":
            return f"let {name}: Option<{native}> = Some({lit});"
        if language == "C_CLANG":
            return f"const {native} {name} = {lit};"
        if language == "GO":
            return f"var {name} {native} = {lit}"
        return f"{native} {name} = {lit} // confidence({conf})"
    joined = ", ".join(literals)
    if language == "KOTLIN":
        return f"val {name}: List<{native}>? = listOf({joined})"
    if language == "RUST":
        return f"let {name}: Option<Vec<{native}>> = Some(vec![{joined}]);"
    if language == "C_CLANG":
        return f"const {native} {name}[{len(literals)}] = {{{joined}}};"
    if language == "GO":
        return f"var {name} []{native} = []{native}{{{joined}}}"
    return f"List<{native}> {name} = [{joined}] // confidence({conf})"


def default_type_spec(value: TypedValue) -> str:
    return "List" if value.is_list else DEFAULT_TYPE_SPECS[value.kind]
