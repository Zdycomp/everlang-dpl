# repair.py — Ever's self-healing registry
#
# Interfaces with the ReFix archive to map failures to fixtures.
# Confidence cost is derived from the repair kind.

import json
import os
from typing import Optional, Tuple, Dict, List, Any
from ever import E_ZERO, E_INTAKE
from evalue import EvType

# Constants mirrored from 7-refix-node/src/constants.js
E_REPAIR_PLAIN = 8
E_REPAIR_INFERRED = 32
KIND_PLAIN = 0
KIND_INFERRED = 1


def strategy_key(strategy: Any) -> Optional[str]:
    """The text a strategy matches on, or None when it has no text.

    Accepts a runtime EValue (text in `ev_text`), a syntax-reference E (text
    in `value`), or a plain str. Only text strategies can match a tied repair;
    anything else matches wildcard repairs only.
    """
    if isinstance(strategy, str):
        return strategy
    if getattr(strategy, 'ev_tag', None) is EvType.TEXT:
        return strategy.ev_text
    value = getattr(strategy, 'value', None)
    if isinstance(value, str) and getattr(strategy, 'state', None) is not None:
        from ever import State
        if strategy.state is not State.Z:
            return value
    return None


def recovery_base(primary_is_z: bool, primary_conf: int) -> int:
    """The most confidence a substituted value may carry before its cost."""
    return E_INTAKE if primary_is_z else primary_conf


def repair_confidence(base: int, value_conf: int, cost: int) -> int:
    return max(E_ZERO, min(base, value_conf) - cost)


class RepairRegistry:
    def __init__(self, archive_dir: Optional[str] = None):
        if archive_dir is None:
            # Default to the project root's 7-refix-node folder
            self.archive_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '7-refix-node'))
        else:
            self.archive_dir = archive_dir
        self.repairs_path = os.path.join(self.archive_dir, 'repairs.jsonl')
        self.rules_path = os.path.join(self.archive_dir, 'rules.jsonl')
        self.repairs: List[Dict] = []
        self.rules: List[Dict] = []
        self.warnings: List[str] = []
        self.load_archive()

    def load_archive(self):
        """Load repairs and rules from JSONL files. A missing file is empty,
        and a malformed line is skipped with a warning, never raised."""
        self.repairs = self._read_records(self.repairs_path)
        self.rules = self._read_records(self.rules_path)

    def _read_records(self, path: str) -> List[Dict]:
        try:
            with open(path, 'r') as f:
                lines = f.readlines()
        except FileNotFoundError:
            return []
        except OSError as exc:
            self.warnings.append(f"{path}: {exc}")
            return []
        records: List[Dict] = []
        for number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                self.warnings.append(f"{path}:{number}: {exc.msg}")
                continue
            if isinstance(record, dict):
                records.append(record)
            else:
                self.warnings.append(f"{path}:{number}: not a JSON object")
        return records

    def find_repair(self, failure_reason: str, strategy: Any) -> Optional[Tuple[str, int]]:
        """Look up the repair for a failure reason under a strategy.

        A repair with a `strategy` matches only that strategy. A repair without
        one (every ReFix archive entry, and every entry written before strategies
        existed) matches any strategy. An exact strategy match wins over a
        wildcard; the first matching entry of each kind wins. Returns
        (fixture_text, cost) or None.
        """
        key = strategy_key(strategy)
        exact = wildcard = None
        for r in self.repairs:
            if r.get('failure_text') != failure_reason or not isinstance(r.get('fixture_text'), str):
                continue
            tied = r.get('strategy')
            if tied is None:
                if wildcard is None:
                    wildcard = r
            elif key is not None and tied == key and exact is None:
                exact = r
        chosen = exact if exact is not None else wildcard
        if chosen is None:
            return None
        kind = chosen.get('kind', KIND_PLAIN)
        cost = E_REPAIR_PLAIN if kind == KIND_PLAIN else E_REPAIR_INFERRED
        return chosen['fixture_text'], cost

    def archive_repair(self, failure_text: str, fixture_text: str, kind: int = KIND_PLAIN,
                       strategy: Optional[str] = None):
        """Record a repair once. Re-learning a repair already held does nothing.
        A strategy ties the repair to that strategy; None makes it a wildcard."""
        record = {
            'v': 1,
            'archived_ms': 0, # Simplified for Python impl
            'failure_text': failure_text,
            'fixture_text': fixture_text,
            'kind': kind,
        }
        if strategy is not None:
            record['strategy'] = strategy
        if any(r.get('failure_text') == failure_text
               and r.get('fixture_text') == fixture_text
               and r.get('kind', KIND_PLAIN) == kind
               and r.get('strategy') == strategy for r in self.repairs):
            return
        self.repairs.append(record)
        try:
            with open(self.repairs_path, 'a') as f:
                f.write(json.dumps(record) + '\n')
        except OSError as exc:
            self.warnings.append(f"{self.repairs_path}: {exc}")


_active: Optional[RepairRegistry] = None


def get_registry() -> Optional[RepairRegistry]:
    """The registry the evaluators consult, built on first use."""
    global _active
    if _active is None:
        _active = RepairRegistry()
    return _active


def use_registry(registry: Optional[RepairRegistry]) -> None:
    """Replace the registry the evaluators consult. None restores the default archive on next use."""
    global _active
    _active = registry
