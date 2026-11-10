"""heal_order.py — the evaluate → plan → execute order for every repair.

Every heal, learn and archive-backed repair runs these three phases, in
this order. The same order is implemented in the Python reference (the
scope evaluator and the syntax reference), in the C TAC interpreter, in the
Java runtime (EverRepair.java), and in the ReFix accept flow. Each phase
writes one line to the trace.

  EVALUATE  read the primary. Trusted: keep it and stop. Otherwise a
            repair is needed: record the error, the reason and the base
            confidence.
  PLAN      pick the repair before running anything. No archived repair,
            or one that cannot add trust, means the fallback.
  EXECUTE   run the chosen action. A repair that was chosen but could not
            run gives z, never the fallback. Every outcome is one of the
            actions below, and is written to the store's events table.

When the environment variable EVER_REPAIR_STORE names a directory, errors
and events are appended there, in the same tables and field names the Java
RepairStore reads and writes (errors.jsonl, events.jsonl). Without it, the
trace is the only record, as before.

Quick by construction: one registry lookup, at most one fixture
evaluation, and one trace line and one store line per phase. Nothing is
searched.
"""

import hashlib
import json
import os
import time
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Deque, Dict, Iterator, List, Optional

from ever import E_EXECUTE_FLOOR
from repair import recovery_base, repair_confidence, strategy_key

KEEP = "KEEP"                # the primary is trusted; no repair ran
SUBSTITUTE = "SUBSTITUTE"    # the archived fixture ran and its value is trusted
FALLBACK = "FALLBACK"        # no usable repair; the fallback ran
FAILED = "FAILED"            # a repair was chosen but could not run: z
LEARNED = "LEARNED"          # learn archived a new repair

TRACE_LIMIT = 1000
STORE_ENV = "EVER_REPAIR_STORE"


@dataclass(frozen=True)
class Assessment:
    """Everything one heal or learn knows about itself, from EVALUATE to EXECUTE.

    A heal nested in this one's strategy or fallback runs between its PLAN and
    its EXECUTE, so nothing about this heal may live in the module: its number
    in the trace (`n`) and the strategy, fixture and cost its outcome is about
    (`about`, filled by plan() or set_context()) travel with the assessment."""
    op: str
    is_z: bool
    conf: int
    reason: str
    base: int
    n: int = 0
    about: Dict[str, Any] = field(default_factory=dict, compare=False)


@dataclass(frozen=True)
class Plan:
    action: str                 # SUBSTITUTE or FALLBACK
    fixture: Optional[str]
    cost: int
    why: str


_trace: Deque[str] = deque(maxlen=TRACE_LIMIT)
_count = [0]
_probing = [0]
_store: List[Optional[Path]] = [None]
_run = ["py-run"]
_seq = [0]


def begin() -> None:
    """Start a fresh trace. Called once per program run."""
    _trace.clear()
    _count[0] = 0
    _run[0] = f"py-{int(time.time() * 1000):x}"
    env = os.environ.get(STORE_ENV)
    _store[0] = Path(env) if env else None
    if _store[0] is not None:
        _store[0].mkdir(parents=True, exist_ok=True)


def drain() -> List[str]:
    """Return the trace for the run that just finished and clear it."""
    out = list(_trace)
    _trace.clear()
    return out


@contextmanager
def probing() -> Iterator[None]:
    """A confidence re-read of a repair node. It runs the node again only to
    read its confidence, so it must not trace, count, or archive: the repair
    already ran once in this evaluation. It does name its failures, in a frame
    of its own, so the re-run reaches the same repair and the same answer."""
    _probing[0] += 1
    try:
        with cause_frame():
            yield
    finally:
        _probing[0] -= 1


def quiet() -> bool:
    """True inside a probe: side effects (trace, archive) are suppressed."""
    return _probing[0] > 0


_cause: List[Optional[str]] = [None]   # the first failure in the innermost frame


def note(reason: str) -> None:
    """A z-producing operation failed here. Inside a frame the first failure
    noted is the cause: a later z is a consequence of it, not a second cause."""
    if _cause[0] is None:
        _cause[0] = reason


@contextmanager
def cause_frame() -> Iterator[List[Optional[str]]]:
    """Evaluate a primary, or a sub-evaluation a heal absorbs, in its own frame.
    The block yields a one-item list; after the block it holds the first failure
    noted inside, or None. Failures inside the frame do not reach the enclosing
    frame: the enclosing evaluation never saw them fail, the heal did."""
    outer = _cause[0]
    _cause[0] = None
    found: List[Optional[str]] = [None]
    try:
        yield found
    finally:
        found[0] = _cause[0]
        _cause[0] = outer


def _emit(a: Assessment, phase: str, text: str) -> None:
    if _probing[0] == 0:
        _trace.append(f"{a.op}#{a.n} {phase}: {text}")


def _write(table: str, record: dict) -> None:
    """Append one record to the store. Never inside a probe, never without a store."""
    if quiet() or _store[0] is None:
        return
    with open(_store[0] / table, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def _next_id(prefix: str) -> str:
    _seq[0] += 1
    return f"{prefix}-{_run[0]}-{_seq[0]}"


def _fingerprint(reason: str) -> str:
    return hashlib.sha256(reason.encode("utf-8")).hexdigest()[:16]


def _event(op: str, reason: str, strategy: Optional[str], action: str,
           conf_in: int, conf_out: int, fixture: Optional[str], cost: int,
           detail: str) -> None:
    _write("events.jsonl", {
        "v": 1, "event_id": _next_id("evt"), "ts_ms": int(time.time() * 1000),
        "run_id": _run[0], "op": op, "ident": "", "reason": reason,
        "strategy": strategy, "action": action, "conf_in": conf_in,
        "conf_out": conf_out, "fixture": fixture, "cost": cost, "detail": detail,
    })


def trusted(conf: int) -> bool:
    """The EVALUATE gate: a primary at or above the execute floor is kept."""
    return conf >= E_EXECUTE_FLOOR


def evaluate(op: str, is_z: bool, conf: int, reason: str) -> Assessment:
    """EVALUATE. Call once per heal or learn, before the strategy is read."""
    n = 0
    if _probing[0] == 0:
        _count[0] += 1
        n = _count[0]
    a = Assessment(op, is_z, conf, reason, recovery_base(is_z, conf), n,
                   {"strategy": None, "fixture": None, "cost": 0})
    state = "z" if is_z else f"confidence {conf}/256"
    _emit(a, "evaluate", f"{state}, reason '{reason}', base {a.base}")
    if not quiet():
        if reason:
            _write("errors.jsonl", {
                "v": 1, "error_id": _next_id("err"),
                "captured_ms": int(time.time() * 1000), "run_id": _run[0],
                "lang": "EVER", "source_ident": "", "stage": "runtime",
                "message": reason, "context": "", "fingerprint": _fingerprint(reason),
                "confidence": conf,
            })
    return a


def keep(a: Assessment, conf: int) -> None:
    """EVALUATE found a trusted primary: the order stops here."""
    _emit(a, "execute", f"{KEEP} → confidence {conf}/256")
    _event(a.op, "", None, KEEP, conf, conf, None, 0, "")


def plan(a: Assessment, registry, strategy) -> Plan:
    """PLAN. Choose the repair, or the fallback, before running anything.
    The strategy selects among the archived repairs for the reason: a repair
    tied to this strategy first, then an untied (wildcard) one."""
    key = strategy_key(strategy)
    under = f" under strategy '{key}'" if key is not None else " (strategy has no text)"
    hit = registry.find_repair(a.reason, strategy)
    if hit is None:
        p = Plan(FALLBACK, None, 0, f"no archived repair for '{a.reason}'{under}")
    else:
        fixture, cost = hit
        if a.base - cost <= 0:
            p = Plan(FALLBACK, None, cost,
                     f"repair costs {cost} against base {a.base}: "
                     f"it cannot add trust")
        else:
            p = Plan(SUBSTITUTE, fixture, cost,
                     f"archived fixture '{fixture}', cost {cost}{under}")
    _emit(a, "plan", f"{p.action} — {p.why}")
    a.about.update(strategy=key, fixture=p.fixture, cost=p.cost)
    return p


def substituted_confidence(a: Assessment, p: Plan, value_conf: int) -> int:
    """The EXECUTE confidence of a substituted value. Zero means it failed."""
    return repair_confidence(a.base, value_conf, p.cost)


def set_context(a: Assessment, strategy: Optional[str], fixture: Optional[str],
                cost: int) -> None:
    """For learn, which plans nothing: record the strategy, fixture and cost the
    outcome is about, before finish()."""
    a.about.update(strategy=strategy, fixture=fixture, cost=cost)


def finish(a: Assessment, action: str, conf: int, detail: str = "") -> None:
    """EXECUTE. Record what the order actually did."""
    tail = f" · {detail}" if detail else ""
    _emit(a, "execute", f"{action} → confidence {conf}/256{tail}")
    _event(a.op, a.reason, a.about["strategy"], action, a.conf, conf,
           a.about["fixture"], a.about["cost"], detail)
