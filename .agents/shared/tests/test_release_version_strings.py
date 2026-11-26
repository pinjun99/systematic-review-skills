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

"""Keep published version strings and CHANGELOG links in step."""

from itertools import pairwise
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[3]
REPO_URL = "https://github.com/pinjun99/systematic-review-skills"
RELEASE_LABEL = r"Unreleased|[0-9]+\.[0-9]+\.[0-9]+"


def cited_version():
    """Return the version CITATION.cff declares, without quoting a literal."""
    text = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    match = re.search(r"^version:\s*([0-9]+\.[0-9]+\.[0-9]+)\s*$", text, re.M)
    if match is None:
        raise AssertionError("CITATION.cff declares no X.Y.Z version")
    return match.group(1)


def changelog_headings_and_references(text=None):
    """Return the release headings and release-label link references.

    A reference counts by its label whatever follows the URL, so a
    definition with a title still counts as a definition of that label.
    """
    if text is None:
        text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    headings = re.findall(r"^## \[([^\]]+)\]", text, re.M)
    references = re.findall(
        rf"^ {{0,3}}\[({RELEASE_LABEL})\]:[ \t]*<?([^\s>]+)>?", text, re.M
    )
    return headings, references


def version_key(label):
    return tuple(int(part) for part in label.split("."))


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

    def test_changelog_headings_have_matching_links(self):
        headings, references = changelog_headings_and_references()
        self.assertTrue(headings, "CHANGELOG.md has no release headings")
        self.assertEqual(
            len(headings), len(set(headings)), "duplicate CHANGELOG headings"
        )
        for label in headings:
            with self.subTest(heading=label):
                self.assertRegex(label, rf"^(?:{RELEASE_LABEL})$")

        labels = [label for label, _ in references]
        for label in headings:
            with self.subTest(heading=label):
                self.assertEqual(
                    labels.count(label),
                    1,
                    f"## [{label}] needs exactly one [{label}]: reference",
                )
        for label in labels:
            with self.subTest(reference=label):
                self.assertIn(
                    label, headings, f"[{label}]: reference has no heading"
                )

        self.assertEqual(headings[0], "Unreleased")
        versions = headings[1:]
        self.assertTrue(versions, "CHANGELOG.md has no released version")
        self.assertEqual(
            versions,
            sorted(versions, key=version_key, reverse=True),
            "released headings are not newest first",
        )

        urls = {}
        for label, url in references:
            urls.setdefault(label, url)  # Markdown uses the first definition
        expected = {"Unreleased": f"{REPO_URL}/compare/v{versions[0]}...HEAD"}
        for newer, older in pairwise(versions):
            expected[newer] = f"{REPO_URL}/compare/v{older}...v{newer}"
        expected[versions[-1]] = f"{REPO_URL}/releases/tag/v{versions[-1]}"
        for label, url in expected.items():
            with self.subTest(reference=label):
                self.assertEqual(urls.get(label), url)

    def test_titled_reference_counts_as_a_definition(self):
        text = (
            "## [0.3.0] - 2026-01-01\n\n"
            '[0.3.0]: https://example.org/wrong "Release"\n'
            f"[0.3.0]: {REPO_URL}/releases/tag/v0.3.0\n"
        )
        _, references = changelog_headings_and_references(text)
        self.assertEqual(
            references,
            [
                ("0.3.0", "https://example.org/wrong"),
                ("0.3.0", f"{REPO_URL}/releases/tag/v0.3.0"),
            ],
        )

    def test_newest_changelog_release_matches_citation(self):
        headings, _ = changelog_headings_and_references()
        released = [label for label in headings if label != "Unreleased"]
        self.assertTrue(released, "CHANGELOG.md has no released version")
        self.assertEqual(released[0], cited_version())


if __name__ == "__main__":
    unittest.main()
