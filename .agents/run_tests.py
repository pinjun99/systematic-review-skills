#!/usr/bin/env python3
"""Run the systematic-review tests without third-party dependencies."""

from pathlib import Path
import subprocess
import sys
from typing import List, Sequence


ROOT = Path(__file__).resolve().parent.parent
AGENTS_ROOT = ROOT / ".agents"


def discover_python_tests() -> List[Path]:
    return sorted(AGENTS_ROOT.rglob("test_*.py"))


def discover_node_tests() -> List[Path]:
    matches = []
    return sorted(set(matches))


def run(command: Sequence[str]) -> None:
    display = " ".join(command)
    print(f"[test] {display}", flush=True)
    completed = subprocess.run(command, cwd=str(ROOT), check=False)
    if completed.returncode:
        raise SystemExit(completed.returncode)


def main() -> None:
    python_tests = discover_python_tests()
    node_tests = discover_node_tests()
    if not python_tests and not node_tests:
        raise SystemExit("No tests discovered under .agents")

    for test_file in python_tests:
        run([sys.executable, str(test_file)])
    for test_file in node_tests:
        run(["node", "--test", str(test_file)])

    print(
        "REGRESSION_OK "
        f"python_files={len(python_tests)} node_files={len(node_tests)}",
        flush=True,
    )


if __name__ == "__main__":
    main()
