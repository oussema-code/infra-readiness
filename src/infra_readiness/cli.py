"""Validate configuration or execute checks and produce reports."""

import argparse
import asyncio
import json
from pathlib import Path
import sys

from .config import ConfigError, load_config
from .models import exit_code
from .report import document, readable, write_json
from .runner import run_checks


def main(argv=None):
    parser = argparse.ArgumentParser(description="Infrastructure readiness tooling")
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="validate configuration without network requests")
    validate.add_argument("config", type=Path)
    run = commands.add_parser("run", help="execute bounded checks and report evidence")
    run.add_argument("config", type=Path)
    run.add_argument("--json", type=Path, dest="json_path", help="write a JSON report, or use - for JSON on stdout")
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
    except ConfigError as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 3
    if args.command == "run":
        if args.json_path is not None and args.json_path.resolve() == args.config.resolve():
            print("Report error: JSON output must not overwrite configuration", file=sys.stderr)
            return 3
        try:
            results = asyncio.run(run_checks(config))
        except KeyboardInterrupt:
            print("Checks interrupted", file=sys.stderr)
            return 130
        if args.json_path == Path("-"):
            print(json.dumps(document(results), indent=2))
            return exit_code(results)
        print(readable(results))
        if args.json_path is not None:
            try:
                write_json(args.json_path, results)
            except OSError:
                print("Report error: cannot write JSON report", file=sys.stderr)
                return 3
        return exit_code(results)
    print(f"Valid configuration: {len(config.checks)} checks, concurrency {config.concurrency}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
