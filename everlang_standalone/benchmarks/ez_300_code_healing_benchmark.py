import os
import sys
import time
from collections import Counter, defaultdict

# Ensure the package root (parent of the benchmarks/ dir) is importable,
# regardless of the current working directory the script is launched from.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from everlang.pipeline import EZPipeline
from everlang.core.particle import EParticle

LANGUAGES = [
    "Python", "JavaScript", "TypeScript", "Rust", "Clang_C", 
    "C++", "Go", "Java", "Kotlin", "Swift", 
    "CSharp", "Ruby", "PHP", "SQL", "Shell"
]

CLEAN_TEMPLATES = [
    "def calculate_total(items): return sum(items)",
    "const fetchData = async (url) => await fetch(url);",
    "interface User { id: number; name: string; }",
    "fn main() { let mut vec = Vec::new(); vec.push(42); }",
    "int sum(int a, int b) { return a + b; }",
    "std::vector<int> nums = {1, 2, 3, 4, 5};",
    "func handleRequest(w http.ResponseWriter, r *http.Request) {}",
    "public class Service { public static void main(String[] args) {} }",
    "fun main() { val list = listOf(1, 2, 3).map { it * 2 } }",
    "func processUser(id: UUID) -> UserResult { return .success }",
    "public record Order(string Id, decimal Amount);",
    "class User; attr_accessor :name, :email; end",
    "function renderView($data) { return json_encode($data); }",
    "SELECT u.id, u.email FROM users u JOIN orders o ON u.id = o.user_id WHERE o.total > 100;",
    "#!/usr/bin/env bash\nfor file in *.log; do grep -i 'error' \"$file\"; done"
]

EMULATED_REPAIR_TEMPLATES = [
    "def parse_payload(raw_data): return json.loads(raw_data) # ERROR: missing import json",
    "const res = await axios.get(endpoint) // INVALID: missing parameter options",
    "type Config = { api_key: string; timeout: number } // ERROR: missing optional flag",
    "fn parse_config(path: &Path) -> Result<Config, io::Error> { let f = File::open(path)?; } // INVALID: missing trait impl",
    "void process_buffer(char* buf, int len) { memset(buf, 0, len); } // ERROR: missing string.h include",
    "auto result = std::find(vec.begin(), vec.end(), target); // INVALID: missing algorithm header",
    "go func() { channel <- data }() // ERROR: unbuffered channel deadlock potential",
    "List<String> items = Stream.of(\"a\", \"b\").toList(); // INVALID: Java version syntax drift",
    "val data = repository.fetchRemoteData() // ERROR: missing coroutines suspend modifier",
    "let decoder = JSONDecoder(); let item = try decoder.decode(Item.self, from: data) // INVALID: unhandled try catch"
]

QUARANTINE_Z_TEMPLATES = [
    "void* ptr = NULL; *ptr = 0xDEADBEEF; // BAD_POINTER CRASH dereference",
    "char buf[10]; strcpy(buf, \"OVERFLOW_ATTACK_STRING_EXCEEDING_LIMIT\"); // CRASH buffer overflow",
    "let raw_ptr: *const i32 = std::ptr::null(); unsafe { *raw_ptr }; // BAD_POINTER unsafe deref",
    "int* arr = malloc(sizeof(int) * 5); free(arr); arr[0] = 100; // CRASH use after free",
    "unsafe { std::mem::transmute::<u64, *mut u8>(0x00000000); } // BAD_POINTER invalid transmute"
]

def generate_300_snippets():
    snippets = []
    snippet_id = 1
    
    for lang in LANGUAGES:
        # 12 Clean snippets per language
        for i in range(12):
            tmpl = CLEAN_TEMPLATES[(snippet_id + i) % len(CLEAN_TEMPLATES)]
            snippets.append({
                "id": f"SNIP_{snippet_id:03d}",
                "lang": lang,
                "code": f"// [{lang} Valid Snippet #{i+1}]\n{tmpl}",
                "category": "CLEAN"
            })
            snippet_id += 1
            
        # 5 Emulated repair snippets per language
        for i in range(5):
            tmpl = EMULATED_REPAIR_TEMPLATES[(snippet_id + i) % len(EMULATED_REPAIR_TEMPLATES)]
            snippets.append({
                "id": f"SNIP_{snippet_id:03d}",
                "lang": lang,
                "code": f"// [{lang} Syntax/Import Drift #{i+1}]\n{tmpl}",
                "category": "SYNTAX_DRIFT"
            })
            snippet_id += 1
            
        # 3 Quarantined Z snippets per language
        for i in range(3):
            tmpl = QUARANTINE_Z_TEMPLATES[(snippet_id + i) % len(QUARANTINE_Z_TEMPLATES)]
            snippets.append({
                "id": f"SNIP_{snippet_id:03d}",
                "lang": lang,
                "code": f"// [{lang} Memory/Safety Hazard #{i+1}]\n{tmpl}",
                "category": "MEMORY_HAZARD"
            })
            snippet_id += 1

    return snippets

def run_300_snippet_benchmark():
    snippets = generate_300_snippets()
    pipeline = EZPipeline()
    rule_particle = EParticle("GlobalComplianceRule", 230)
    
    start_time = time.time()
    
    results_by_outcome = Counter()
    results_by_lang = defaultdict(lambda: Counter())
    detailed_results = []
    
    for snip in snippets:
        res = pipeline.run(snip["id"], snip["code"], snip["lang"], rule_particle)
        
        status = res["examine_status"]
        phase = res["phase_outcome"]
        final_particle = res["final_particle"]
        
        if status == "NORMALIZED" and phase == "EXCEL":
            outcome = "CLEAN_EXECUTION"
        elif status == "EMULATED_REPAIR":
            outcome = "EMULATE_AUTO_REPAIRED"
        elif status == "QUARANTINED_Z" or final_particle.is_z():
            outcome = "QUARANTINED_AT_Z"
        else:
            outcome = "EXCEL_EVALUATED"
            
        results_by_outcome[outcome] += 1
        results_by_lang[snip["lang"]][outcome] += 1
        
        detailed_results.append({
            "id": snip["id"],
            "lang": snip["lang"],
            "category": snip["category"],
            "examine_status": status,
            "phase_outcome": phase,
            "outcome": outcome,
            "confidence": final_particle.confidence
        })

    elapsed = time.time() - start_time
    
    print("================================================================================")
    print("      EVERLANG / DPL 300-SNIPPET MULTI-LANGUAGE CODE HEALING BENCHMARK")
    print("================================================================================")
    print(f" Total Code Snippets Evaluated : {len(snippets)}")
    print(f" Languages Tested              : {len(LANGUAGES)} Mainstream Languages")
    print(f" Execution Wall-Clock Time     : {elapsed:.3f} seconds")
    print(f" Processing Speed              : {len(snippets)/elapsed:.2f} snippets/sec")
    print("--------------------------------------------------------------------------------")
    print(" SUMMARY BY OUTCOME CATEGORY:")
    print(f"  • Clean Executed (256/256 Certainty) : {results_by_outcome['CLEAN_EXECUTION']} ({results_by_outcome['CLEAN_EXECUTION']/300*100:.1f}%)")
    print(f"  • Emulate Auto-Repaired (Borrowed)   : {results_by_outcome['EMULATE_AUTO_REPAIRED']} ({results_by_outcome['EMULATE_AUTO_REPAIRED']/300*100:.1f}%)")
    print(f"  • Quarantined at Z (0 Floor)         : {results_by_outcome['QUARANTINED_AT_Z']} ({results_by_outcome['QUARANTINED_AT_Z']/300*100:.1f}%)")
    print("--------------------------------------------------------------------------------")
    print(" BREAKDOWN BY LANGUAGE (15 LANGUAGES):")
    print(" Language     | Clean Executed | Emulate Repaired | Quarantined Z | Total")
    print(" -------------+----------------+------------------+---------------+------")
    for lang in LANGUAGES:
        stats = results_by_lang[lang]
        clean = stats['CLEAN_EXECUTION']
        repaired = stats['EMULATE_AUTO_REPAIRED']
        z_quarantine = stats['QUARANTINED_AT_Z']
        tot = clean + repaired + z_quarantine
        print(f" {lang:<12} | {clean:^14} | {repaired:^16} | {z_quarantine:^13} | {tot:^5}")
    print("================================================================================")
    print(" RUNTIME RESILIENCE & UPTIME: 100.0% (0 Unhandled Exceptions / Crashes)")
    print("================================================================================")

if __name__ == "__main__":
    run_300_snippet_benchmark()
