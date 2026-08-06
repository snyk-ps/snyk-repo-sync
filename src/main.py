"""Entry point for the CLI."""

import argparse
import sys

from commands.worker import register_worker_commands


def build_parser() -> argparse.ArgumentParser:
    """Build the root argument parser."""
    parser = argparse.ArgumentParser(
        description="Queue-driven worker for repository lifecycle sync.",
    )
    subparsers = parser.add_subparsers(dest="command")
    register_worker_commands(subparsers)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if hasattr(args, "func"):
        return args.func(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
