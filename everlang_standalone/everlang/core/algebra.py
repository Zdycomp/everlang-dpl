"""Confidence algebra and its predictive inverses, per ezr/SEMANTICS.md.

Forward laws say what a binding is worth. The inverses say what it would
take to reach a target, so a refusal can name its cure. Every formula here
is one the spec states or one ezr's reference code already computes; the
vectors in tests/test_algebra.py are pinned from ezr's own functions.
"""
from typing import NamedTuple, Optional, Tuple

from .vocabulary import E_ASCEND_POINTS, E_CERTAIN, E_EXECUTE_FLOOR, E_INTAKE, KIND_COST

PI_ENUMERATE = 25   # §5.2: widths up to here are acceptable as a range
PI_WARN = 81        # §5.2: widths above here collapse to Z(unbounded)
DEPTH_CEILING = 3   # §4.6: recursion depth limit unless anchored


def uncertainty(c: int) -> float:
    """§1: u = (256 - c) / 256. Z (c = 0) gives 1.0; Certain gives 0.0."""
    return (E_CERTAIN - c) / E_CERTAIN


def example_confidence(passed: int, total: int) -> int:
    """§4.2 [EXAMPLE]: c = floor(256 * (1 - u) * p/t), u = ((256 - 120)/256)^p.

    Capped one short of CERTAIN. Examples corroborate; they do not chain.
    """
    if total <= 0:
        return 0
    u = ((E_CERTAIN - E_INTAKE) / E_CERTAIN) ** passed if passed else 1.0
    c = int(E_CERTAIN * (1.0 - u) * (passed / total))
    return max(0, min(E_CERTAIN - 1, c))


def witnesses_needed(passed: int, total: int, target: int = E_EXECUTE_FLOOR,
                     cap: int = 64) -> Optional[int]:
    """Inverse of §4.2: the least k in 0..cap with example_confidence(p+k, t+k) >= target.

    None when the target is out of reach within cap further passing Examples.
    """
    for k in range(cap + 1):
        if example_confidence(passed + k, total + k) >= target:
            return k
    return None


def repairs_to_floor(plain: int, inferred: int) -> int:
    """§9.2 charges: what a binding has left above the execute floor after its repairs."""
    return max(0, E_CERTAIN - plain * KIND_COST[0] - inferred * KIND_COST[1])


def inferred_repairs_left(confidence: int = E_CERTAIN) -> int:
    """Inverse of §9.2: how many more inferred repairs fit above the execute floor."""
    return max(0, (confidence - E_EXECUTE_FLOOR) // KIND_COST[1])


def sources_still_needed(distinct_sources: int) -> int:
    """Inverse of §9.6: distinct sources a repair shape still needs before it is a candidate."""
    return max(0, E_ASCEND_POINTS - distinct_sources)


def excel(a: int, b: int) -> int:
    """§2.2 corroboration, as ezr/2-interpreter-python/ever.py::excel implements it.

    Certain only when both inputs are Certain; otherwise capped at 255 (T3).
    Z (0) is the identity: excel(0, c) is c, capped.
    """
    if a >= E_CERTAIN and b >= E_CERTAIN:
        return E_CERTAIN
    v = a + b - (a * b // E_CERTAIN)
    return max(0, min(E_CERTAIN - 1, v))


def pi_collapse(width: int) -> str:
    """§5.2: an unknown condition's range is 'accept', 'enumerate', or 'collapse' to Z."""
    if width <= PI_ENUMERATE:
        return "accept"
    if width <= PI_WARN:
        return "enumerate"
    return "collapse"


def depth_limit(anchored: bool, measure_defined: bool) -> Optional[int]:
    """§4.6: the recursion limit, or None when unbounded (anchored with a measure)."""
    return None if anchored and measure_defined else DEPTH_CEILING


class Law(NamedTuple):
    name: str
    kind: str          # "law" (forward) or "inverse" (predictive)
    spec_ref: str
    formula: str


ALGEBRA: Tuple[Law, ...] = (
    Law("uncertainty", "law", "SEMANTICS.md §1", "u = (256 - c) / 256"),
    Law("example_confidence", "law", "SEMANTICS.md §4.2", "c = floor(256 * (1 - u) * p/t), u = (136/256)^p"),
    Law("witnesses_needed", "inverse", "SEMANTICS.md §4.2 (inverted; ezr/ezrun.py)",
        "least k in 0..cap with example_confidence(p+k, t+k) >= target"),
    Law("repairs_to_floor", "law", "SEMANTICS.md §9.2", "256 - 8*plain - 32*inferred, floored at 0"),
    Law("inferred_repairs_left", "inverse", "SEMANTICS.md §9.2",
        "floor((c - 128) / 32) inferred repairs"),
    Law("sources_still_needed", "inverse", "SEMANTICS.md §9.6", "max(0, 3 - distinct sources)"),
    Law("excel", "law", "SEMANTICS.md §2.2, T1/T3 (ruled: code wins)",
        "256 if both Certain, else min(255, a + b - floor(a*b/256))"),
    Law("pi_collapse", "law", "SEMANTICS.md §5.2",
        "width <= 25 accept; 26..81 enumerate; > 81 collapse to Z(unbounded)"),
    Law("depth_limit", "law", "SEMANTICS.md §4.6",
        "limit = unbounded if anchored and measure defined, else 3"),
)
