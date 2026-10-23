#!/usr/bin/env python3
"""Register and resolve local V2 issues without phase-wide invalidation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from v2_runtime import register_issue, resolve_issue


def load(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path: str, value) -> None:
    Path(path).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    register = sub.add_parser("register")
    register.add_argument("issue")
    register.add_argument("output")
    resolve = sub.add_parser("resolve")
    resolve.add_argument("issue")
    resolve.add_argument("corrected_ref")
    resolve.add_argument("dependency_graph")
    resolve.add_argument("output")
    args = parser.parse_args()
    if args.command == "register":
        result = register_issue(load(args.issue))
    else:
        result = resolve_issue(
            load(args.issue), corrected_ref=args.corrected_ref,
            dependency_graph=load(args.dependency_graph)
        )
    write(args.output, result)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
