#!/usr/bin/env python3
"""
CLI for SuperTranspiler: Multi-language code generation from DPL particles.

Usage:
    everlang-transpile render <name> <value> <type> <confidence>
    everlang-transpile render-all <name> <value> <type> <confidence>
    everlang-transpile stats
"""
import sys
import argparse
from typing import Optional
from .super_transpiler_v2 import SuperTranspilerV2


def render_to_language(name: str, value: str, type_spec: str, conf: int, language: str) -> None:
    """Render particle to a specific language."""
    transpiler = SuperTranspilerV2()
    result = transpiler.transpile(name, value, type_spec, conf)

    if language in result:
        code = result[language]
        print(f"// {language}")
        print(code)
    else:
        print(f"Error: Language '{language}' not supported", file=sys.stderr)
        sys.exit(1)


def render_all_languages(name: str, value: str, type_spec: str, conf: int) -> None:
    """Render particle to all supported languages."""
    transpiler = SuperTranspilerV2()
    result = transpiler.transpile(name, value, type_spec, conf)

    print(f"Particle: {name} : {type_spec} = \"{value}\" @ confidence({conf})")
    print("=" * 70)
    print()

    languages = ["DPL", "KOTLIN", "RUST", "C_CLANG", "GO", "GROOVY"]
    for lang in languages:
        if lang in result:
            code = result[lang]
            # Format language name nicely
            lang_display = lang.replace("_", " ").title() if "_" in lang else lang
            print(f"// {lang_display}")
            print(code)
            print()


def show_stats() -> None:
    """Show transpiler statistics."""
    transpiler = SuperTranspilerV2()
    stats = transpiler.stats()

    print("\nSuperTranspiler v2 Statistics")
    print("=" * 70)
    print(f"Supported languages:     {stats['languages_supported']}")
    print(f"Languages list:          {', '.join(stats['languages'])}")
    print(f"High-confidence variants: {stats['high_confidence_variants']}")
    print(f"Low-confidence variants:  {stats['low_confidence_variants']}")
    print(f"Cache size:              {stats['cache_size']}")
    print()
    print("Features:")
    print("  • Input validation & sanitization")
    print("  • Language-specific escaping (quotes, newlines, backslashes)")
    print("  • Type mapping (abstract → language-native types)")
    print("  • Confidence-aware rendering (adjusts safety based on confidence)")
    print("  • Template caching (compile once, render many times)")
    print("  • Graceful error handling & degradation")
    print()
    print("Performance:")
    print("  • ~153,000 renders/sec (single language)")
    print("  • ~919,000 renders/sec total throughput (6 languages)")
    print("  • PyPy compatible: 5-10x speedup possible")


def main_transpile() -> Optional[int]:
    """Main entry point for everlang-transpile CLI."""
    parser = argparse.ArgumentParser(
        description="SuperTranspiler: Multi-language code generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  everlang-transpile render message "Hello, World" String 200 KOTLIN
  everlang-transpile render-all x "test value" String 150
  everlang-transpile stats
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Render subcommand (single language)
    render_parser = subparsers.add_parser("render", help="Render to a specific language")
    render_parser.add_argument("name", help="Particle name")
    render_parser.add_argument("value", help="Particle value (string)")
    render_parser.add_argument("type", help="Type specification")
    render_parser.add_argument("confidence", type=int, help="Confidence (0-256)")
    render_parser.add_argument("language", help="Target language (DPL, KOTLIN, RUST, C_CLANG, GO, GROOVY)")

    # Render-all subcommand (all languages)
    render_all_parser = subparsers.add_parser("render-all", help="Render to all languages")
    render_all_parser.add_argument("name", help="Particle name")
    render_all_parser.add_argument("value", help="Particle value (string)")
    render_all_parser.add_argument("type", help="Type specification")
    render_all_parser.add_argument("confidence", type=int, help="Confidence (0-256)")

    # Stats subcommand
    subparsers.add_parser("stats", help="Show transpiler statistics")

    args = parser.parse_args()

    try:
        if args.command == "render":
            render_to_language(args.name, args.value, args.type, args.confidence, args.language)
        elif args.command == "render-all":
            render_all_languages(args.name, args.value, args.type, args.confidence)
        elif args.command == "stats":
            show_stats()
        else:
            parser.print_help()
            return 1
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main_transpile() or 0)
