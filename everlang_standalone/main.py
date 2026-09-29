import json
from everlang.core.particle import EParticle
from everlang.pipeline import EZPipeline
from everlang.quantum.entanglement import EntanglementSwapSystem

def main():
    print("==========================================================================")
    print("      EVERLANG / DPL STANDALONE CORE RUNTIME SYSTEM (v1.0.0)")
    print("==========================================================================")
    
    pipeline = EZPipeline()
    rule_particle = EParticle("FinancialComplianceRule", 220)

    test_snippets = [
        ("SNIP_001", "val accountBalance = 1000", "Kotlin"),
        ("SNIP_002", "let raw_ptr = INVALID_MEM_REF", "Rust"),
        ("SNIP_003", "const char* ptr = BAD_POINTER;", "Clang_C")
    ]

    results = []
    for snip_id, code, lang in test_snippets:
        out = pipeline.run(snip_id, code, lang, rule_particle)
        results.append({
            "id": out["snippet_id"],
            "lang": out["lang"],
            "examine": out["examine_status"],
            "phase": out["phase_outcome"],
            "pi_governor": out["pi_governor_status"],
            "evolved": out["evolved"],
            "final_conf": out["final_particle"].confidence
        })

    print("\n[Pipeline Execution Results Across Multi-Language Constructs]")
    print(json.dumps(results, indent=2))

    # Test Quantum Entanglement Swap
    swap_system = EntanglementSwapSystem(pipeline.archive)
    cell_alpha_z = EParticle("CellAlpha_Z", 0)
    cell_beta = EParticle("CellBeta_Anchor", 256)
    
    swap_res = swap_system.execute_entanglement_swap(cell_alpha_z, cell_beta, velocity_c=0.95)
    print("\n[Quantum Entanglement Swap Result (Relativistic v = 0.95c)]")
    print(f"Outcome      : {swap_res['outcome']}")
    print(f"Lorentz γ    : {swap_res['gamma_factor']:.2f}")
    print(f"Fidelity     : {swap_res['fidelity']}%")
    print(f"Restored     : {swap_res['particle']}")

if __name__ == "__main__":
    main()
