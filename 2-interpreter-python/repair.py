# repair.py — Ever's self-healing registry
#
# Interfaces with the ReFix archive to map failures to fixtures.
# Confidence cost is derived from the repair kind.

import json
import os
from typing import Optional, Tuple, Dict, List, Any
from ever import E_ZERO, E_INTAKE

# Constants mirrored from 7-refix-node/src/constants.js
E_REPAIR_PLAIN = 8
E_REPAIR_INFERRED = 32
KIND_PLAIN = 0
KIND_INFERRED = 1


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
        """
        Look up a fixture based on the failure reason and strategy.
        Returns (fixture_text, cost) or None.
        """
        # Simple strategy: exact match on failure reason
        # More complex strategies can be implemented here.
        for r in self.repairs:
            if r.get('failure_text') == failure_reason and isinstance(r.get('fixture_text'), str):
                kind = r.get('kind', KIND_PLAIN)
                cost = E_REPAIR_PLAIN if kind == KIND_PLAIN else E_REPAIR_INFERRED
                return r['fixture_text'], cost

        return None

    def archive_repair(self, failure_text: str, fixture_text: str, kind: int = KIND_PLAIN):
        """Record a repair once. Re-learning a repair already held does nothing."""
        record = {
            'v': 1,
            'archived_ms': 0, # Simplified for Python impl
            'failure_text': failure_text,
            'fixture_text': fixture_text,
            'kind': kind,
        }
        if any(r.get('failure_text') == failure_text
               and r.get('fixture_text') == fixture_text
               and r.get('kind', KIND_PLAIN) == kind for r in self.repairs):
            return
        self.repairs.append(record)
        try:
            with open(self.repairs_path, 'a') as f:
                f.write(json.dumps(record) + '\n')
        except OSError as exc:
            self.warnings.append(f"{self.repairs_path}: {exc}")


_active: Optional[RepairRegistry] = None


def get_registry() -> RepairRegistry:
    """The registry the evaluators consult, built on first use."""
    global _active
    if _active is None:
        _active = RepairRegistry()
    return _active


def use_registry(registry: Optional[RepairRegistry]) -> None:
    """Replace the registry the evaluators consult. None restores the default archive on next use."""
    global _active
    _active = registry
