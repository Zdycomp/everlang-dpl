# SuperTranspiler v2 - Multi-Language Code Generation

Generate equivalent code in 6 languages from a single DPL particle description. Production-ready with validation, type mapping, and confidence-aware rendering.

## Installation

```bash
pip install everlang-transpiler
```

## Quick Start

```bash
# Generate Kotlin code
everlang-transpile render message "Hello World" String 200 KOTLIN

# Generate code for all 6 languages
everlang-transpile render-all counter "42" Int 180

# Show capabilities and performance
everlang-transpile stats
```

## Features

- **6-Language Support**: DPL, Kotlin, Rust, C/Clang, Go, Groovy
- **Type Mapping**: Abstract types to language-native types automatically
- **Input Validation**: Pre-flight checks prevent invalid code generation
- **Language-Specific Escaping**: Proper handling of quotes, newlines, special chars
- **Confidence-Aware Rendering**: Template variants based on confidence level
- **Template Caching**: Compile once, render many times efficiently
- **Graceful Error Handling**: Returns comments instead of exceptions

## API Usage

```python
from everlang_standalone.everlang.transpiler.super_transpiler_v2 import SuperTranspilerV2

transpiler = SuperTranspilerV2()

# Generate code across all languages
result = transpiler.transpile(
    name="message",
    val="Hello, World!",
    type_spec="String",
    conf=200
)

for lang, code in result.items():
    print(f"// {lang}")
    print(code)
```

## Language Support

| Language | Type Mapping | Notes |
|----------|--------------|-------|
| DPL | Int, String, Bool, Real, Bytes, Any | Native format |
| Kotlin | Int, String, Boolean, Double, ByteArray, Any | JVM interop |
| Rust | i64, String, bool, f64, Vec<u8>, Box<dyn Any> | Memory-safe |
| C/Clang | int, char*, int, double, unsigned char*, void* | Low-level |
| Go | int64, string, bool, float64, []byte, interface{} | Concurrency |
| Groovy | Integer, String, Boolean, Double, byte[], Object | Dynamic |

## Confidence Levels

The transpiler adjusts template variants based on confidence (0-256):

- **0-50 (Low)**: Defensive mode, wrapped in try-catch, quarantined values
- **51-200 (Medium)**: Standard templates with normal safety
- **200-256 (High)**: Optimistic mode, unchecked/trusted rendering

## Command Reference

### render
```bash
everlang-transpile render NAME VALUE TYPE CONFIDENCE LANGUAGE
```
Generate code for a specific language.
- NAME: Variable name
- VALUE: String value
- TYPE: Type specification
- CONFIDENCE: 0-256 confidence level
- LANGUAGE: Target language (DPL, KOTLIN, RUST, C_CLANG, GO, GROOVY)

### render-all
```bash
everlang-transpile render-all NAME VALUE TYPE CONFIDENCE
```
Generate code for all 6 languages simultaneously.

### stats
```bash
everlang-transpile stats
```
Display supported languages and performance metrics.

## Performance

| Operation | Throughput | Notes |
|-----------|-----------|-------|
| Single language | ~153k renders/sec | Per-language |
| All 6 languages | ~919k renders/sec | Total throughput |
| With PyPy | 765k-4.6M renders/sec | 5-10x faster |
| Cache hit | O(1) lookup | Template caching |

## Input Validation

The transpiler validates:
- ✓ Name is valid identifier
- ✓ Value length (1-4096 bytes)
- ✓ Type spec format (alphanumeric, angle brackets, commas)
- ✓ Confidence range (0-256)

Invalid input returns error comments in all languages rather than raising exceptions.

## Requirements

- Python 3.9+
- No external dependencies (pure Python)

## License

MIT

## See Also

- [everlang-dna](../biocomputing/README.md) - DNA sequence analysis
- [everlang-particles](../core/README.md) - Probabilistic state machine
- [Main Project](https://github.com/Zdycomp/everlang-dpl)
