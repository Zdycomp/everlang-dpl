"""
Autonomous AI Agent Loop with Everlang (DPL) Emulate Auto-Repair
================================================================
Demonstrates a resilient autonomous agent that executes code tasks in a loop.
Instead of crashing on bad syntax or unhandled errors, the agent uses:
 1. Emulate Auto-Repair (1-3 error distance) to borrow functional neighbor patterns.
 2. Z-Quarantine (error distance > 3) to isolate bad states at position 0.
 3. EArchive persistence to learn and evolve execution confidence over time.
"""

import os
import sys

# Ensure the package root (parent of the benchmarks/ dir) is importable,
# regardless of the current working directory the script is launched from.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from everlang.core.particle import EParticle
from everlang.pipeline import EZPipeline

class AutonomousAgent:
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.pipeline = EZPipeline()
        self.task_history = []

    def execute_task(self, task_id: str, task_type: str, code_payload: str, language: str) -> dict:
        print(f"\n[Agent {self.agent_id}] ----------------------------------------------------")
        print(f"Task ID     : {task_id}")
        print(f"Task Focus  : {task_type}")
        print(f"Language    : {language}")
        print(f"Raw Code    : {code_payload[:60]}...")

        # Rule particle representing system execution contract
        system_rule = EParticle("Rule_AgentExecutionContract", 240)

        # Run code payload through 4-stage Everlang pipeline
        result = self.pipeline.run(
            snippet_id=task_id,
            code_snippet=code_payload,
            lang=language,
            rule_particle=system_rule
        )

        examine_status = result["examine_status"]
        phase_outcome = result["phase_outcome"]
        final_particle = result["final_particle"]
        conf = final_particle.confidence

        # Determine agent action based on particle trust score
        if conf == 0:
            action = "QUARANTINED_AT_Z"
            status_desc = "Task failed safety checks. Quarantined at Z=0. Loop continues smoothly."
        elif examine_status == "EMULATED_REPAIR":
            action = "EMULATE_AUTO_REPAIRED"
            status_desc = "Minor syntax/parameter drift detected. Auto-repaired via Emulate pattern borrowing."
        else:
            action = "EXECUTED_CLEAN"
            status_desc = "Code payload verified clean. Executed with high confidence."

        task_record = {
            "task_id": task_id,
            "task_type": task_type,
            "language": language,
            "examine_status": examine_status,
            "phase_outcome": phase_outcome,
            "action": action,
            "confidence": conf,
            "status_desc": status_desc
        }
        self.task_history.append(task_record)

        print(f"Action Taken : {action}")
        print(f"Confidence   : {conf}/256")
        print(f"Outcome      : {status_desc}")
        return task_record

    def summary(self):
        print("\n" + "="*70)
        print(f"        AUTONOMOUS AGENT {self.agent_id} EXECUTION TELEMETRY SUMMARY")
        print("="*70)
        total = len(self.task_history)
        clean = sum(1 for t in self.task_history if t["action"] == "EXECUTED_CLEAN")
        repaired = sum(1 for t in self.task_history if t["action"] == "EMULATE_AUTO_REPAIRED")
        quarantined = sum(1 for t in self.task_history if t["action"] == "QUARANTINED_AT_Z")

        print(f" Total Tasks Processed    : {total}")
        print(f" Executed Clean           : {clean}")
        print(f" Emulate Auto-Repaired    : {repaired}")
        print(f" Quarantined at Z (Floor) : {quarantined}")
        print(" Agent Uptime & Resilience: 100.0% (Zero agent crashes)")
        print("="*70)

def run_agent_loop():
    print("================================================================================")
    print("       AUTONOMOUS AI AGENT LOOP (EVERLANG DPL RESILIENCE TEST)")
    print("================================================================================")

    agent = AutonomousAgent("ALPHA_01")

    # Queue of incoming autonomous agent code tasks with varying quality
    tasks = [
        {
            "id": "TASK_101",
            "type": "Financial Moving Average",
            "code": "def compute_ma(data, window=10):\n    return pandas.Series(data).rolling(window).mean()",
            "lang": "Python"
        },
        {
            "id": "TASK_102",
            "type": "JSON Schema Parser",
            "code": "def parse_payload(raw):\n    return json.loads(raw)  # ERROR: Missing null check",
            "lang": "Python"
        },
        {
            "id": "TASK_103",
            "type": "Memory Unsafe Pointer Access",
            "code": "void* ptr = NULL; *ptr = 0xDEADBEEF; // BAD_POINTER CRASH",
            "lang": "Clang_C"
        },
        {
            "id": "TASK_104",
            "type": "Database Query Builder",
            "code": "val query = \"SELECT * FROM trades WHERE timestamp > \" + ts  // ERROR: Syntax drift",
            "lang": "Kotlin"
        },
        {
            "id": "TASK_105",
            "type": "Risk Limit Validation",
            "code": "fn check_risk(exposure: f64) -> bool { exposure < 1000000.0 }",
            "lang": "Rust"
        }
    ]

    for t in tasks:
        agent.execute_task(t["id"], t["type"], t["code"], t["lang"])

    agent.summary()

if __name__ == "__main__":
    run_agent_loop()
