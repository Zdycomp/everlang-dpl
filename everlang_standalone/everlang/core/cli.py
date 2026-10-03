#!/usr/bin/env python3
"""
CLI for EParticle + PhaseEngine: Probabilistic state machine framework.

Usage:
    everlang-particles create <name> <value> <confidence>
    everlang-particles collide <p1_conf> <p2_conf>
    everlang-particles repair <error_distance>
    everlang-particles stats
"""
import sys
import argparse
from typing import Optional
from .particle import EParticle
from .phase_engine import PhaseEngine
from .archive import EArchive


def create_particle(name: str, value: str, confidence: int) -> None:
    """Create and display a particle."""
    try:
        particle = EParticle(value, confidence)
        print("\nCreated particle:")
        print(f"  Label:      {name}")
        print(f"  Value:      {particle.value}")
        print(f"  Confidence: {particle.confidence}")
        print(f"  Z-quarantined: {particle.is_z()}")
        print()
    except ValueError as e:
        print(f"Error creating particle: {e}", file=sys.stderr)
        sys.exit(1)


def test_collision(conf1: int, conf2: int) -> None:
    """Test particle collision with given confidence values."""
    try:
        p1 = EParticle("value1", conf1)
        p2 = EParticle("value2", conf2)

        engine = PhaseEngine()
        result = engine.collide(p1, p2)

        print("\nParticle Collision Test")
        print("=" * 60)
        print(f"P1: confidence={conf1}")
        print(f"P2: confidence={conf2}")
        print()
        particle = result["particle"]
        print("Result:")
        print(f"  Outcome:    {result['outcome']}")
        print(f"  Value:      {particle.value}")
        print(f"  Confidence: {particle.confidence}")
        print(f"  Reason:     {result['reason']}")
        print()
    except Exception as e:
        print(f"Error in collision: {e}", file=sys.stderr)
        sys.exit(1)


def test_repair(error_distance: int) -> None:
    """Test self-healing repair mechanism."""
    try:
        if error_distance < 0 or error_distance > 3:
            print("Error: error_distance must be 0-3", file=sys.stderr)
            sys.exit(1)

        particle = EParticle("value", 50)
        if error_distance == 0:
            repaired = particle
        else:
            repaired = EArchive().emulate_repair("cli_repair", error_distance)

        print("\nSelf-Healing Repair Test")
        print("=" * 60)
        print(f"Original:      confidence={particle.confidence}")
        print(f"Error distance: {error_distance}")
        print(f"Repaired:      confidence={repaired.confidence}")
        print()
        if error_distance == 0:
            print("  (No errors: no repair needed)")
        else:
            expected_conf = max(0, 250 - error_distance * 30)
            print(f"  Repair formula: 250 - {error_distance}*30 = {expected_conf}")
        print()
    except Exception as e:
        print(f"Error in repair: {e}", file=sys.stderr)
        sys.exit(1)


def show_stats() -> None:
    """Show EParticle + PhaseEngine statistics."""
    print("\nEParticle Framework Statistics")
    print("=" * 60)
    print("Confidence Scale:")
    print("  • 0:   Z-quarantined (failure state)")
    print("  • 1-80:   Low confidence (defensive mode)")
    print("  • 81-200: Medium confidence (normal mode)")
    print("  • 201-256: High confidence (optimistic mode)")
    print()
    print("Phase Transitions (CollideRule):")
    print("  • Z_CONTAGION:  Either particle is Z → quarantine")
    print("  • EXCEL:        Low gap (<81) → constructive fusion")
    print("  • EXPEL:        High ratio (>2φ) → weaker discarded")
    print("  • REPEL:        Default → both unchanged")
    print()
    print("Self-Healing Formula:")
    print("  • Error distance 1-3: confidence = 250 - distance*30")
    print("  • Error distance >3:  confidence = 0 (Z-quarantined)")
    print()
    print("Entanglement Swap:")
    print("  • Restore Z-quarantined particles from anchor")
    print("  • Uses calculated_evolve_vector for state recovery")
    print()
    print("Performance:")
    print("  • Particle creation: O(1)")
    print("  • Collision check: O(1)")
    print("  • Repair calculation: O(1)")
    print("  • Archive logging: O(1) amortized")


def main_particles() -> Optional[int]:
    """Main entry point for everlang-particles CLI."""
    parser = argparse.ArgumentParser(
        description="EParticle: Probabilistic state machine framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  everlang-particles create my_particle "test value" 200
  everlang-particles collide 200 180
  everlang-particles repair 2
  everlang-particles stats
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Create subcommand
    create_parser = subparsers.add_parser("create", help="Create and display a particle")
    create_parser.add_argument("name", help="Particle name")
    create_parser.add_argument("value", help="Particle value")
    create_parser.add_argument("confidence", type=int, help="Confidence (0-256)")

    # Collide subcommand
    collide_parser = subparsers.add_parser("collide", help="Test particle collision")
    collide_parser.add_argument("confidence1", type=int, help="First particle confidence")
    collide_parser.add_argument("confidence2", type=int, help="Second particle confidence")

    # Repair subcommand
    repair_parser = subparsers.add_parser("repair", help="Test self-healing repair")
    repair_parser.add_argument("error_distance", type=int, help="Error distance (0-3)")

    # Stats subcommand
    subparsers.add_parser("stats", help="Show framework statistics")

    args = parser.parse_args()

    try:
        if args.command == "create":
            create_particle(args.name, args.value, args.confidence)
        elif args.command == "collide":
            test_collision(args.confidence1, args.confidence2)
        elif args.command == "repair":
            test_repair(args.error_distance)
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
    sys.exit(main_particles() or 0)
