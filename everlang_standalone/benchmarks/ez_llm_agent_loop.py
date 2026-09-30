import os
import sys

# Ensure the package root (parent of the benchmarks/ dir) is importable,
# regardless of the current working directory the script is launched from.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from everlang.pipeline import EZPipeline
from everlang.core.particle import EParticle

class SimulatedLLMGenerator:
    """Simulates an LLM generating code payloads across different prompt requests.
    Introduces common LLM code failure modes:
    1. Missing imports / syntax drift
    2. Severe hallucinations (unhandled null pointers)
    3. Clean, high-quality code
    """
    def __init__(self):
        self.prompt_templates = [
            {
                "prompt": "Write a Python function to parse JSON with fallback.",
                "lang": "Python",
                "code": "ERROR: missing import json",
                "type": "MISSING_IMPORT"
            },
            {
                "prompt": "Write a Kotlin data class and parser for order ticks.",
                "lang": "Kotlin",
                "code": "ERROR: deprecated syntax drift",
                "type": "SYNTAX_DRIFT"
            },
            {
                "prompt": "Write a C function to manipulate raw memory pointers directly.",
                "lang": "Clang_C",
                "code": "BAD_POINTER: void* ptr = NULL; *ptr = 0xDEADBEEF;",
                "type": "MEMORY_UNSAFE"
            },
            {
                "prompt": "Write a Rust function to validate risk exposure limits.",
                "lang": "Rust",
                "code": "fn check_risk(exposure: f64) -> bool { exposure < 1_000_000.0 }",
                "type": "CLEAN"
            },
            {
                "prompt": "Write a Python pandas rolling mean calculation.",
                "lang": "Python",
                "code": "import pandas as pd\ndef rolling_avg(df): return df['price'].rolling(window=5).mean()",
                "type": "CLEAN"
            }
        ]

    def generate_response(self, task_idx: int) -> dict:
        return self.prompt_templates[task_idx % len(self.prompt_templates)]

def run_llm_agent_loop():
    print("=" * 80)
    print("      LLM CODE GENERATOR + EVERLANG DPL AUTONOMOUS HEALING LOOP")
    print("=" * 80)

    llm = SimulatedLLMGenerator()
    pipeline = EZPipeline()

    rule_particle = EParticle("VerifySafetyAndSyntax", 256)

    telemetry = {
        "total_prompts": 0,
        "clean_executions": 0,
        "emulate_auto_repairs": 0,
        "z_quarantines": 0
    }

    for i in range(5):
        llm_output = llm.generate_response(i)
        telemetry["total_prompts"] += 1
        
        prompt = llm_output["prompt"]
        lang = llm_output["lang"]
        raw_code = llm_output["code"]
        gen_type = llm_output["type"]
        task_id = f"LLM_GEN_{i+1:03d}"

        print(f"\n[Task {task_id}] LLM Prompt: '{prompt}'")
        print(f"  • Target Language : {lang}")
        print(f"  • LLM Anomaly     : {gen_type}")

        # Execute through Everlang DPL Pipeline
        result = pipeline.run(task_id, raw_code, lang, rule_particle)
        
        examine_status = result["examine_status"]
        final_conf = result["final_particle"].confidence

        if examine_status == "NORMALIZED":
            telemetry["clean_executions"] += 1
            print(f"  • Pipeline Stage  : NORMALIZED ──► EXCEL Phase (Confidence: {final_conf}/256)")
            print("  └─► STATUS: CLEAN. Generated code verified and executed.")
        elif examine_status == "EMULATED_REPAIR":
            telemetry["emulate_auto_repairs"] += 1
            print(f"  • Pipeline Stage  : EMULATED_REPAIR ──► Pattern borrowed from EArchive (Confidence: {final_conf}/256)")
            print("  └─► STATUS: AUTO-REPAIRED. LLM syntax/import error healed without crashing.")
        elif examine_status == "QUARANTINED_Z":
            telemetry["z_quarantines"] += 1
            print(f"  • Pipeline Stage  : QUARANTINED_Z ──► Quarantined at position 0 (Confidence: {final_conf}/256)")
            print("  └─► STATUS: ISOLATED AT Z. Memory unsafe code blocked. Agent loop uninterrupted.")

    print("\n" + "=" * 80)
    print("                 LLM AUTONOMOUS AGENT TELEMETRY SUMMARY")
    print("=" * 80)
    print(f" Total LLM Code Prompts  : {telemetry['total_prompts']}")
    print(f" Clean Executions        : {telemetry['clean_executions']}")
    print(f" Emulate Auto-Repairs    : {telemetry['emulate_auto_repairs']}")
    print(f" Quarantined at Z (Floor): {telemetry['z_quarantines']}")
    print(" Agent Loop Resilience   : 100.0% (Zero unhandled crashes)")
    print("=" * 80)

if __name__ == "__main__":
    run_llm_agent_loop()
