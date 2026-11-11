"""Cross-language repair vocabulary, per ezr/SEMANTICS.md section 9.

Entries 1-7 are the ever_repair rows in ezr/4-archive-sql/repair.sql, copied
verbatim; tests/test_heal.py fails if the two drift. Entries 8-9 name the two
repairs edapt performs that Ever has no counterpart for.
"""
from dataclasses import dataclass
from typing import Dict, Tuple

E_CERTAIN = 256
E_EXECUTE_FLOOR = E_CERTAIN // 2
E_INTAKE = 120
E_ASCEND_POINTS = 3

PLAIN, INFERRED = 0, 1
KIND_NAMES = {PLAIN: "plain", INFERRED: "inferred"}
KIND_COST = {PLAIN: E_CERTAIN // 32, INFERRED: E_CERTAIN // 8}

DEFECTS = ("none", "unbound", "misbound", "unbounded", "overbound", "orphaned")

LANGUAGES = ("ever", "python", "javascript", "go", "rust", "java", "kotlin")


@dataclass(frozen=True)
class Repair:
    id: int
    name: str
    kind: int
    defect: str
    languages: Tuple[str, ...]
    note: str

    @property
    def cost(self) -> int:
        return KIND_COST[self.kind]


VOCABULARY: Tuple[Repair, ...] = (
    Repair(1, "trailing_comma", PLAIN, "none", ("ever",),
           "a comma before a closer separates nothing"),
    Repair(2, "stray_semicolon", PLAIN, "none", ("ever",),
           "E needs no statement terminator"),
    Repair(3, "keyword_case", PLAIN, "none", ("ever",),
           "a name spelled exactly like a keyword"),
    Repair(4, "colon_for_equals", INFERRED, "misbound", ("ever",),
           "let/ever bind with =, not :"),
    Repair(5, "equals_for_colon", INFERRED, "misbound", ("ever",),
           "fields inside { } are name: value"),
    Repair(6, "equals_for_compare", INFERRED, "misbound", ("ever", "python"),
           "= is legal only after let/ever NAME or a def parameter list"),
    Repair(7, "missing_comma", INFERRED, "unbounded", ("ever",),
           "two values adjacent inside a collection"),
    Repair(8, "missing_colon", INFERRED, "unbounded", ("python",),
           "a block header must end in ':'"),
    Repair(9, "missing_semicolon", INFERRED, "unbounded", ("javascript", "rust", "java"),
           "a simple statement must end in ';'"),
)

BY_NAME: Dict[str, Repair] = {r.name: r for r in VOCABULARY}
