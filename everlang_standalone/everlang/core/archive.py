import threading
import time
from . import heal as heal_engine
from .heal import Healing
from .particle import EParticle
from .vocabulary import BY_NAME, E_ASCEND_POINTS, E_CERTAIN, E_EXECUTE_FLOOR, E_INTAKE

class EArchive:
    def __init__(self):
        self._lock = threading.Lock()
        self.boundary_markers = []
        self.examples = []
        self.evolved_vectors = []
        self.repairs = []
        self.rules = []

    def log_boundary_marker(self, context: str, particle: EParticle, reason: str):
        with self._lock:
            self.boundary_markers.append({
                "context": context,
                "value": particle.value,
                "confidence": particle.confidence,
                "reason": reason
            })

    def emulate_repair(self, failing_signature: str, error_distance: int) -> EParticle:
        with self._lock:
            if 1 <= error_distance <= 3:
                borrowed_conf = 250 - (error_distance * 30)
                repaired_value = f"EmulatedPattern<{failing_signature}>"
                return EParticle(repaired_value, borrowed_conf)
            return EParticle("Quarantined(Z)", 0)

    def calculate_evolve_vector(self, action_success: float, reaction_data: float, force: float) -> float:
        with self._lock:
            if reaction_data == 0 or force == 0:
                return 0.0
            vector = action_success / (reaction_data / force)
            self.evolved_vectors.append(vector)
            return vector

    def heal(self, source: str, language: str, source_ident: str,
             confidence: int = E_CERTAIN) -> Healing:
        result = heal_engine.run(source, language)
        lines = source.splitlines()
        conf = max(0, min(E_CERTAIN, int(confidence)))
        now_ms = int(time.time() * 1000)
        records = []
        for fix in result.fixes:
            name = getattr(fix, "name", "")
            entry = BY_NAME.get(name)
            if entry is None or language not in entry.languages or fix.kind != entry.kind:
                raise KeyError(f"heal: the {language} engine emitted {name!r} (kind {fix.kind}), "
                               f"which the vocabulary does not list that way for {language}")
            if not (fix.form and fix.what and fix.became):
                raise ValueError(f"heal: {name} at line {fix.line} is missing half of its Failure/Fixture pair")
            # Charges accumulate (SEMANTICS.md 9.2): four inferred repairs land at exactly 128.
            before, conf = conf, max(0, conf - entry.cost)
            records.append({
                "language": language,
                "source_ident": source_ident,
                "repair_id": entry.id,
                "name": entry.name,
                "kind": entry.kind,
                "defect": entry.defect,
                "line_no": fix.line,
                "line_text": lines[fix.line - 1] if 0 < fix.line <= len(lines) else "",
                "failure_text": fix.what,
                "fixture_text": fix.became,
                "fixture_form": fix.form,
                "reason": fix.reason,
                "cost": entry.cost,
                "conf_before": before,
                "conf_after": conf,
                "archived_ms": now_ms,
            })
        with self._lock:
            self.repairs.extend(records)
        if result.refusals:
            self.log_boundary_marker(f"heal:{language}:{source_ident}",
                                     EParticle("Quarantined(Z)", 0), "; ".join(result.refusals))
            conf = 0
        return Healing(language, source_ident, result.code, result.program, conf,
                       records, result.refusals)

    def repair_candidates(self):
        with self._lock:
            groups = {}
            for r in self.repairs:
                key = (r["repair_id"], r["fixture_form"])
                g = groups.setdefault(key, {
                    "repair_id": r["repair_id"], "name": r["name"],
                    "fixture_form": r["fixture_form"], "seen": 0,
                    "sources": set(), "languages": set(),
                    "first_ms": r["archived_ms"], "last_ms": r["archived_ms"],
                })
                g["seen"] += 1
                g["sources"].add(r["source_ident"])
                g["languages"].add(r["language"])
                g["first_ms"] = min(g["first_ms"], r["archived_ms"])
                g["last_ms"] = max(g["last_ms"], r["archived_ms"])
        candidates = []
        for key in sorted(groups):
            g = groups[key]
            if len(g["sources"]) >= E_ASCEND_POINTS:
                candidates.append({
                    "repair_id": g["repair_id"], "name": g["name"],
                    "fixture_form": g["fixture_form"], "seen": g["seen"],
                    "distinct_sources": len(g["sources"]),
                    "distinct_languages": len(g["languages"]),
                    "first_ms": g["first_ms"], "last_ms": g["last_ms"],
                })
        return candidates

    def propose_rules(self):
        candidates = self.repair_candidates()
        now_ms = int(time.time() * 1000)
        decided = []
        with self._lock:
            for c in candidates:
                priors = [r["fixture_form"] for r in self.repairs if r["repair_id"] == c["repair_id"]]
                total = len(priors)
                agreed = sum(1 for form in priors if form == c["fixture_form"])
                if agreed != total:
                    status, conf = "rejected", E_INTAKE
                    why = f"replay disagreed: {total - agreed} of {total} prior repairs would change"
                else:
                    status, conf, why = "admitted", E_EXECUTE_FLOOR, ""
                rule = {
                    "repair_id": c["repair_id"], "name": c["name"],
                    "fixture_form": c["fixture_form"], "derived_from": c["seen"],
                    "status": status, "confidence": conf,
                    "replay_total": total, "replay_agreed": agreed,
                    "rejected_why": why, "proposed_ms": now_ms, "decided_ms": now_ms,
                }
                self.rules.append(rule)
                decided.append(rule)
        return decided
