#!/usr/bin/env python3
"""
CLI for DnaSequencer: DNA sequence analysis with confidence-based error correction.

Usage:
    everlang-dna analyze <sequence>
    everlang-dna validate <sequence>
    everlang-dna stats
"""
import sys
import argparse
from typing import Optional
from .sequencer import DnaLexer, DnaParser, DnaSyntaxError


def analyze_sequence(sequence: str) -> int:
    """Analyze a DNA sequence. Returns the process exit status."""
    lexer = DnaLexer(sequence)
    tokens = lexer.tokenize()
    parser = DnaParser(tokens)
    try:
        pairs = parser.parse()
    except DnaSyntaxError as e:
        print(f"Error analyzing sequence: {e}", file=sys.stderr)
        return 1
    codons = parser.codons()
    valid_count = sum(1 for t in tokens if t.valid)

    print("\nDNA Sequence Analysis")
    print("=" * 60)
    print(f"Input:            {sequence}")
    print(f"Length:           {len(lexer.cleaned_sequence)} bp")
    print(f"Valid tokens:     {valid_count}")
    print(f"Error tokens:     {len(tokens) - valid_count}")
    print(f"Base pairs:       {len(pairs)}")
    print(f"Codons detected:  {len(codons)}")

    if codons:
        print("\nFirst 5 codons:")
        for i, codon in enumerate(codons[:5]):
            print(f"  [{i}] {''.join(p.base for p in codon.pairs)} @ {codon.start_index}")
    return 0


def validate_sequence(sequence: str) -> bool:
    """Validate a DNA sequence using the same normalization as DnaLexer
    (uppercase, whitespace ignored). Returns True if it is valid, non-empty DNA."""
    lexer = DnaLexer(sequence)
    lexer.tokenize()
    cleaned = lexer.cleaned_sequence
    errors = lexer.errors()
    valid = bool(cleaned) and not errors

    print("\nDNA Sequence Validation")
    print("=" * 60)
    print(f"Sequence:      {cleaned}")
    print(f"Length:        {len(cleaned)} bp")
    print(f"Valid:         {'✓' if valid else '✗'}")

    if not cleaned:
        print("Empty sequence")
    elif errors:
        print(f"Invalid chars: {', '.join(sorted({t.base for t in errors}))}")
        print(f"Positions:     {', '.join(str(t.index) for t in errors)}")
    else:
        print("\nComposition:")
        for base in sorted("ATCG"):
            count = cleaned.count(base)
            print(f"  {base}: {count:>5} ({count / len(cleaned) * 100:>5.1f}%)")
    return valid


def show_stats() -> None:
    """Show sequencer statistics."""
    print("\nDnaSequencer Statistics")
    print("=" * 60)
    print("Available operations:")
    print("  - Tokenization: Convert raw DNA sequence to typed tokens")
    print("  - Parsing: Convert tokens to structured Watson-Crick base pairs")
    print("  - Codon detection: Identify coding triplets")
    print("  - Error recovery: Continue parsing on invalid input")
    print()
    print("Performance:")
    print("  - DnaSequencer: ~34k sequences/sec at 12 bp, ~3.3k at 100 bp (~0.2 Mbp/sec)")
    print("  - UltraFastDnaSequencer: ~100k sequences/sec at 12 bp, ~11.6k at 100 bp (~0.4 Mbp/sec)")
    print("  - Much slower than plain str operations or Biopython; see biocomputing/README.md")


def main_dna() -> Optional[int]:
    """Main entry point for everlang-dna CLI."""
    parser = argparse.ArgumentParser(
        description="DnaSequencer: DNA sequence analysis tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  everlang-dna analyze ATCGATCGATCGATCG
  everlang-dna validate ATCGATCGATCGATCG
  everlang-dna stats
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Analyze subcommand
    analyze_parser = subparsers.add_parser("analyze", help="Analyze a DNA sequence")
    analyze_parser.add_argument("sequence", help="DNA sequence (A/T/C/G)")

    # Validate subcommand
    validate_parser = subparsers.add_parser("validate", help="Validate a DNA sequence")
    validate_parser.add_argument("sequence", help="DNA sequence to validate")

    # Stats subcommand
    subparsers.add_parser("stats", help="Show DnaSequencer statistics")

    args = parser.parse_args()

    if args.command == "analyze":
        return analyze_sequence(args.sequence)
    elif args.command == "validate":
        return 0 if validate_sequence(args.sequence) else 1
    elif args.command == "stats":
        show_stats()
    else:
        parser.print_help()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main_dna() or 0)
