# DnaSequencer - DNA Sequence Analysis Tool

Fast, production-ready DNA sequence analysis with lexer/parser and confidence-based validation.

## Installation

```bash
pip install everlang   # provides the everlang-dna command
```

## Quick Start

```bash
# Validate a DNA sequence
everlang-dna validate ATCGATCGATCGATCG

# Analyze and tokenize a sequence
everlang-dna analyze ATCGATCGATCGATCG

# Show performance metrics
everlang-dna stats
```

## Features

- **Lexer/Parser Pattern**: Proven design used in production DNA analysis
- **Quaternary Encoding**: Efficient 2-bit per base representation (A=0, T=1, C=2, G=3)
- **Error Recovery**: Continues parsing on invalid input, marking ERROR tokens
- **Watson-Crick Pairs**: Automatically identifies complementary base pairs
- **Codon Detection**: Finds coding triplets and reading frames
- **High Performance**: ~39,000 sequences/sec (optimized) or 5-10x faster with PyPy

## API Usage

```python
from everlang_standalone.everlang.biocomputing.sequencer import DnaLexer, DnaParser

# Tokenize a sequence
sequence = "ATCGATCGATCG"
lexer = DnaLexer(sequence)
tokens = lexer.tokenize()

# Parse into structured codons
parser = DnaParser(tokens)
codons = parser.parse()

for codon in codons:
    print(codon)
```

## Performance

| Operation | Throughput | Notes |
|-----------|-----------|-------|
| Tokenization | ~39k seqs/sec | Ultra-fast tuple-based |
| Parsing | ~39k seqs/sec | Single pass |
| With PyPy | 195-390k seqs/sec | 5-10x faster |

## Command Reference

### validate
```bash
everlang-dna validate SEQUENCE
```
Check if a sequence contains valid DNA bases (A, T, C, G).
- Shows composition statistics
- Reports invalid characters and positions
- Exit code 0 if valid, 1 if invalid

### analyze
```bash
everlang-dna analyze SEQUENCE
```
Tokenize and parse a DNA sequence.
- Shows token count and error tokens
- Displays detected codons
- Reports parsing statistics

### stats
```bash
everlang-dna stats
```
Display tool capabilities and performance metrics.

## Requirements

- Python 3.9+
- No external dependencies (pure Python)

## License

MIT

## See Also

- [everlang-transpile](../transpiler/README.md) - Multi-language code generation
- [everlang-particles](../core/README.md) - Probabilistic state machine
- [Main Project](https://github.com/Zdycomp/everlang-dpl)
