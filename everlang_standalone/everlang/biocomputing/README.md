# DnaSequencer - DNA Sequence Analysis Tool

A pure-Python DNA sequence lexer/parser: tokens, Watson-Crick pairs, codons and GC content, with every invalid character reported rather than dropped. A teaching and design exercise, not a replacement for Biopython or seqkit, which are orders of magnitude faster (see Performance).

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

- **Lexer/Parser Pattern**: the compiler front-end design applied to a DNA string
- **Quaternary Encoding**: Efficient 2-bit per base representation (A=0, T=1, C=2, G=3)
- **Error Recovery**: Continues parsing on invalid input, marking ERROR tokens
- **Watson-Crick Pairs**: Automatically identifies complementary base pairs
- **Codon Detection**: Finds coding triplets and reading frames
- **Speed**: about 0.2 Mbp/s (`DnaSequencer`) to 0.4 Mbp/s (`UltraFastDnaSequencer`); see Performance

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

Measured on CPython 3.11 in the project's CI container, random A/C/G/T input, one
`run()` per sequence (lexing and parsing together):

| Implementation | 12 bp | 100 bp | 1 Mbp |
|---|---|---|---|
| `DnaSequencer` | ~34k seqs/s | ~3.3k seqs/s | ~4.5 s (0.22 Mbp/s) |
| `UltraFastDnaSequencer` | ~100k seqs/s | ~11.6k seqs/s | ~2.8 s (0.36 Mbp/s) |

For comparison, reverse-complementing and validating 1 Mbp with plain
`str.translate` takes about 9 ms and Biopython's `reverse_complement` about 2 ms.
This module builds token and pair objects for every base, which is what costs the
time; use it to learn or to get per-base diagnostics, not for bulk sequence work.
PyPy speedups have not been measured here.

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
