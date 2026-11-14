"""The reason-code registry.

Every Unknown carries one code from this table, and every note on a known
value carries one too. The table is mirrored from ``spec/reason_codes.tsv``
at the repository root, which is the source of truth for every layer.
``tests/test_reason_registry.py`` fails if this file and the spec disagree.

Unknown codes say why an answer does not exist. Note codes say why a known
value is trusted the way it is. Nothing here is free text; the human reason
is a separate field on the value.
"""

from __future__ import annotations

from typing import Dict, Tuple

# code -> (kind, meaning)
REASONS: Dict[str, Tuple[str, str]] = {
    "MISSING_INPUT": ("unknown",
        "A value needed for the answer was not supplied, or there was nothing to compute over."),
    "CONFLICTING_SOURCES": ("unknown",
        "Two sources that should agree do not, and nothing settles which one is right."),
    "BELOW_THRESHOLD": ("unknown",
        "A value exists but its confidence is under the floor the caller required to act on it."),
    "TIMEOUT": ("unknown",
        "The source did not answer in time, so no answer exists."),
    "OUT_OF_RANGE": ("unknown",
        "The operation has no defined result here: division by zero, overflow, NaN or infinity."),
    "UNVERIFIED_SOURCE": ("unknown",
        "The claimed answer could not be checked against its source, so it is not taken as given."),
    "MALFORMED": ("unknown",
        "The input does not have the shape the operation needs: bad syntax, mismatched lengths, a wrong type."),
    "INTAKE_SOURCE": ("note",
        "The value came from outside the program (a file, an API, a model). Its confidence is at most INTAKE (120)."),
    "GROUNDED": ("note",
        "The quoted text appears verbatim in the document it was read from."),
    "CORROBORATED": ("note",
        "A rule independent of the source matches the same passage and agrees with it."),
    "UNCORROBORATED": ("note",
        "No independent rule matches. The read rests on its source alone."),
    "CERTAIN_LITERAL": ("note",
        "A value written directly in the program or the call. Its confidence is CERTAIN (256)."),
    "DERIVED": ("note",
        "Computed from its inputs. Its confidence is the least of them, unless a stated rule says otherwise."),
}

UNKNOWN_CODES = frozenset(c for c, (kind, _) in REASONS.items() if kind == "unknown")
NOTE_CODES = frozenset(c for c, (kind, _) in REASONS.items() if kind == "note")


def check_unknown_code(code: str) -> str:
    """Return ``code`` if it names an Unknown in the registry, else raise."""
    if code not in UNKNOWN_CODES:
        raise ValueError(
            f"{code!r} is not an Unknown reason code; "
            f"valid codes are {sorted(UNKNOWN_CODES)}")
    return code


def check_note_code(code: str) -> str:
    if code not in NOTE_CODES:
        raise ValueError(
            f"{code!r} is not a note code; valid codes are {sorted(NOTE_CODES)}")
    return code
