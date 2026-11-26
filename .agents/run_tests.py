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


def select_tests(filters: Sequence[str]) -> List[Path]:
    """Return test files whose name contains any of the given filters.

    An empty filter list means every discovered test. A filter that matches
    nothing is an error so a typo cannot silently reduce coverage.
    """
    tests = discover_python_tests()
    if not filters:
        return tests

    selected = set()
    for name_filter in filters:
        matches = [test for test in tests if name_filter in test.name]
        if not matches:
            raise SystemExit(f"No test files match filter: {name_filter}")
        selected.update(matches)
    return sorted(selected)


def run(command: Sequence[str]) -> None:
    display = " ".join(command)
    print(f"[test] {display}", flush=True)
    completed = subprocess.run(command, cwd=str(ROOT), check=False)
    if completed.returncode:
        raise SystemExit(completed.returncode)


def main() -> None:
    tests = select_tests(sys.argv[1:])
    if not tests:
        raise SystemExit("No tests discovered under .agents")

    for test_file in tests:
        run([sys.executable, str(test_file)])

    print(f"REGRESSION_OK python_files={len(tests)}", flush=True)


if __name__ == "__main__":
    main()
