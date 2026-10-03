#!/usr/bin/env python3
"""
CLI for SuperTranspiler: Multi-language code generation from DPL particles.

Usage:
    everlang-transpile render <name> <value> <type> <confidence>
    everlang-transpile render-all <name> <value> <type> <confidence>
    everlang-transpile stats
    everlang-transpile config <file.toml|file.json> [--confidence N] [--language LANG]
"""
import sys
import argparse
import json
import re
from typing import Iterator, List, Optional, Tuple
from .super_transpiler import SuperTranspiler
from .super_transpiler_v2 import SuperTranspilerV2
from .typed import infer


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

    print(f"Particle: {name} : {type_spec} = {value!r} @ confidence({conf})")
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


def flatten_config(data, prefix: str = "") -> Iterator[Tuple[str, object]]:
    """Yields (name, value) for every leaf of a parsed config. Nested tables
    join their keys with '_'; a list of tables is indexed (`modules_0_enabled`).
    Names are made identifiers: other characters become '_', and a leading
    digit gets a '_' prefix."""
    if isinstance(data, dict):
        for key, value in data.items():
            yield from flatten_config(value, f"{prefix}_{key}" if prefix else str(key))
    elif isinstance(data, list) and data and all(isinstance(item, dict) for item in data):
        for index, item in enumerate(data):
            yield from flatten_config(item, f"{prefix}_{index}")
    else:
        name = re.sub(r"[^A-Za-z0-9_]", "_", prefix)
        yield ("_" + name if name[:1].isdigit() else name), data


def load_config(path: str):
    if path.endswith(".json"):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    try:
        import tomllib
    except ImportError:  # Python < 3.11
        raise ValueError("reading TOML needs Python 3.11+ (tomllib); convert the file to JSON") from None
    with open(path, "rb") as f:
        return tomllib.load(f)


def transpile_config(path: str, conf: int, language: Optional[str] = None) -> int:
    """Renders every leaf of a TOML or JSON config: strings through the string
    templates, numbers, booleans and lists with native types (transpile_typed).
    A leaf neither path accepts is reported on stderr and skipped; returns 1 if
    any was skipped."""
    try:
        data = load_config(path)
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    transpiler = SuperTranspiler()
    skipped: List[str] = []
    seen = set()
    for name, value in flatten_config(data):
        if name in seen:
            skipped.append(f"{name}: duplicate name after flattening")
            continue
        seen.add(name)
        try:
            kind = "Str" if isinstance(value, str) else infer(value).kind
            rendered = transpiler.transpile_value(name, value, None, conf)
        except ValueError as exc:
            skipped.append(f"{name}: {exc}")
            continue
        if language is not None:
            if language.upper() not in rendered:
                print(f"Error: Language '{language}' not supported", file=sys.stderr)
                return 1
            print(rendered[language.upper()])
            continue
        print(f"# {name}  ({kind})")
        for lang, code in rendered.items():
            print(f"{lang:<8} {code}")
        print()
    for problem in skipped:
        print(f"skipped {problem}", file=sys.stderr)
    return 1 if skipped else 0


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
  everlang-transpile config node.toml --confidence 200
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

    # Config subcommand (typed values)
    config_parser = subparsers.add_parser(
        "config", help="Render every value of a TOML/JSON config, keeping numbers, booleans and lists typed")
    config_parser.add_argument("path", help="Path to a .toml or .json file")
    config_parser.add_argument("--confidence", type=int, default=200, help="Confidence for every value (default 200)")
    config_parser.add_argument("--language", help="Print only this language's renderings")

    args = parser.parse_args()

    try:
        if args.command == "render":
            render_to_language(args.name, args.value, args.type, args.confidence, args.language)
        elif args.command == "render-all":
            render_all_languages(args.name, args.value, args.type, args.confidence)
        elif args.command == "stats":
            show_stats()
        elif args.command == "config":
            return transpile_config(args.path, args.confidence, args.language)
        else:
            parser.print_help()
            return 1
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main_transpile() or 0)
