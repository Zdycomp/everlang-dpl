import os
import sys

# Ensure the package root (parent of the benchmarks/ dir) is importable,
# regardless of the current working directory the script is launched from.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from everlang.core.particle import EParticle
from everlang.pipeline import EZPipeline

def run_financial_feed_simulation():
    pipeline = EZPipeline()
    
    print("=" * 80)
    print("   REAL-TIME FINANCIAL DATA FEED SIMULATION (DPL / EVERLANG STANDALONE)")
    print("=" * 80)
    
    # Define financial market tick streams
    market_ticks = [
        {
            "id": "TICK_001_NYSE_AAPL",
            "symbol": "AAPL",
            "lang": "DPL",
            "code": "particle aaplQuote : E<float> = \"228.50\" @ confidence(240)",
            "rule_confidence": 230
        },
        {
            "id": "TICK_002_CORRUPTED_FEED",
            "symbol": "AAPL",
            "lang": "Clang_C",
            "code": "double* badPrice = BAD_POINTER; *badPrice = -999.00;",
            "rule_confidence": 200
        },
        {
            "id": "TICK_003_OPTIONS_VOLATILITY",
            "symbol": "NVDA",
            "lang": "Kotlin",
            "code": "val nvdaIV: OptionSpread? = INVALID_SYNTAX_PADDING",
            "rule_confidence": 220
        },
        {
            "id": "TICK_004_ANOMALOUS_FLASH_SPREAD",
            "symbol": "NVDA",
            "lang": "Rust",
            "code": "let anomalySpread: Option<Spread> = CRASH_FLASH_SPREAD;",
            "rule_confidence": 180
        },
        {
            "id": "TICK_005_NASDAQ_AGGR",
            "symbol": "AAPL",
            "lang": "DPL",
            "code": "particle nasdaqAggr : E<string> = \"NASDAQ_AAPL_228.50\" @ confidence(250)",
            "rule_confidence": 240
        },
        {
            "id": "TICK_006_ORDER_IMBALANCE",
            "symbol": "TSLA",
            "lang": "Go",
            "code": "var orderBookImbalance string = \"BUY_15000_SELL_1200\"",
            "rule_confidence": 210
        }
    ]

    feed_results = []
    
    for tick in market_ticks:
        rule_particle = EParticle(
            value=f"RuleValidator_{tick['symbol']}",
            confidence=tick["rule_confidence"]
        )
        
        # Process through 4-Stage EZ Pipeline
        res = pipeline.run(
            snippet_id=tick["id"],
            code_snippet=tick["code"],
            lang=tick["lang"],
            rule_particle=rule_particle
        )
        res["symbol"] = tick["symbol"]
        feed_results.append(res)
        
        print(f"\n[Processing {tick['id']} ({tick['symbol']})]")
        print(f"  • Language / Source : {tick['lang']}")
        print(f"  • EXAMINE Status    : {res['examine_status']}")
        print(f"  • EVALUATE Phase    : {res['phase_outcome']}")
        print(f"  • Pi Governor       : {res['pi_governor_status']}")
        print(f"  • Autonomous Evolve : {res['evolved']}")
        print(f"  • Final Confidence  : {res['final_particle'].confidence}/256")
        
        if res['final_particle'].confidence == 0:
            print("  └─► QUARANTINED AT Z (Zero-Absolute Floor). Bad tick isolated without system crash.")
        elif res['examine_status'] == "EMULATED_REPAIR":
            print("  └─► AUTO-REPAIRED VIA EMULATE. Pattern borrowed from EArchive neighbor.")
        else:
            print("  └─► CLEARED & EXECUTED. High-trust trade match committed.")

    summary = {
        "total_ticks_processed": len(market_ticks),
        "quarantined_z_ticks": sum(1 for r in feed_results if r['final_particle'].confidence == 0),
        "emulated_repaired_ticks": sum(1 for r in feed_results if r['examine_status'] == "EMULATED_REPAIR"),
        "cleared_execution_ticks": sum(1 for r in feed_results if r['final_particle'].confidence > 0),
        "archive_boundary_markers": len(pipeline.archive.boundary_markers)
    }

    print("\n" + "=" * 80)
    print("                      FINANCIAL FEED SIMULATION SUMMARY")
    print("=" * 80)
    print(f" Total Market Ticks Processed : {summary['total_ticks_processed']}")
    print(f" Quarantined Ticks (Z-State)  : {summary['quarantined_z_ticks']} (Bad quotes isolated)")
    print(f" Emulated Repairs             : {summary['emulated_repaired_ticks']} (Auto-repaired tick structures)")
    print(f" Cleared Executions           : {summary['cleared_execution_ticks']} (High-trust trade matches)")
    print(f" Boundary Markers in Archive  : {summary['archive_boundary_markers']} (Permanent memory additions)")
    print("=" * 80)

if __name__ == "__main__":
    run_financial_feed_simulation()
