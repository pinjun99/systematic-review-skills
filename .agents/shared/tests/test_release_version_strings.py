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

"""Keep every published version string in step with CITATION.cff."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[3]


def cited_version():
    """Return the version CITATION.cff declares, without quoting a literal."""
    text = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    match = re.search(r"^version:\s*([0-9]+\.[0-9]+\.[0-9]+)\s*$", text, re.M)
    if match is None:
        raise AssertionError("CITATION.cff declares no X.Y.Z version")
    return match.group(1)


class ReleaseVersionTests(unittest.TestCase):
    def test_published_strings_match_citation(self):
        version = cited_version()
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        manual = (ROOT / "docs" / "user-manual.md").read_text(encoding="utf-8")
        expected = [
            (readme, rf"\*\*Early stage, version {re.escape(version)}\.\*\*"),
            (readme, rf"Skills\*, version {re.escape(version)}\."),
            (readme, rf"version = \{{{re.escape(version)}\}}"),
            (manual, rf"Version {re.escape(version)} is an early release\."),
        ]
        for text, pattern in expected:
            with self.subTest(pattern=pattern):
                self.assertIsNotNone(
                    re.search(pattern, text, re.M),
                    f"published text drifted from CITATION.cff version {version}",
                )


if __name__ == "__main__":
    unittest.main()
