#!/usr/bin/env python3
# Copyright 2026 Ooi Pin Jun
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location(
    "systematic_review_run_tests", ROOT / ".agents" / "run_tests.py"
)
run_tests = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run_tests)


class RunTestsFilterTests(unittest.TestCase):
    def test_no_filters_selects_every_test(self):
        self.assertEqual(
            [test.name for test in run_tests.select_tests([])],
            [test.name for test in run_tests.discover_python_tests()],
        )

    def test_single_filter_selects_matching_file(self):
        self.assertEqual(
            [test.name for test in run_tests.select_tests(["prisma_flow"])],
            ["test_prisma_flow.py"],
        )

    def test_multiple_filters_select_the_union(self):
        names = [test.name for test in run_tests.select_tests(["prisma_flow", "install"])]
        self.assertEqual(names, ["test_install.py", "test_prisma_flow.py"])

    def test_unmatched_filter_is_an_error(self):
        with self.assertRaises(SystemExit) as caught:
            run_tests.select_tests(["no_such_test"])
        self.assertIn("no_such_test", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
