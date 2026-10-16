#!/usr/bin/env python3
"""Pack, inspect, and certify deterministic Axioval MCS containers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from . import mcs_archive
except ImportError:
    import mcs_archive


def add_definitions_option(command: argparse.ArgumentParser) -> None:
    command.add_argument(
        "--definitions",
        action="append",
        default=[],
        type=Path,
        metavar="PATH",
        help=(
            "a definitions package (.mcs archive or package directory) a rule "
            "set may resolve its uncarried definitionPackages from; repeatable"
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(prog="mcs.py")
    commands = parser.add_subparsers(dest="command", required=True)
    pack = commands.add_parser("pack", help="evaluate and create an MCS container")
    pack.add_argument("package_dir", type=Path)
    pack.add_argument("output", type=Path)
    pack.add_argument(
        "--repository-root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    pack.add_argument("--force", action="store_true")
    add_definitions_option(pack)
    for name in ("verify", "inspect"):
        command = commands.add_parser(name, help=f"{name} an MCS container")
        command.add_argument("file", type=Path)
        if name == "verify":
            add_definitions_option(command)
    args = parser.parse_args()
    try:
        if args.command == "pack":
            result = mcs_archive.pack(
                args.package_dir,
                args.output,
                args.repository_root,
                args.force,
                args.definitions,
            )
        elif args.command == "verify":
            result = mcs_archive.verify(args.file, args.definitions)
        else:
            result = mcs_archive.inspect(args.file)
    except mcs_archive.MCSError as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
