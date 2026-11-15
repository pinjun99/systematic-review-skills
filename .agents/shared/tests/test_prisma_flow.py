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

"""Exercise PRISMA rendering with generated, source-backed flow counts."""

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[3]
SHARED = ROOT / ".agents" / "shared"
sys.path.insert(0, str(SHARED))

from artifact_ref import canonical_json_sha256, make_artifact_ref
from assurance_chain import derive_prisma_counts
from prisma_flow import FORMATS, render


class PrismaFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        documents = {
            "PHASE8_DEDUPLICATION": {
                "records_imported": 123, "duplicate_records_removed": 12},
            "PHASE9_SCREENING": {
                "expected_phase8_records": 108, "excluded_title_abstract": 60,
                "retained_for_full_text": 48},
            "PHASE10_RETRIEVAL": {
                "reports_not_retrieved": 5, "reports_assessed": 43},
            "PHASE10_SCREENING": {
                "excluded_reports": 32, "included_reports": 11, "included_studies": 9},
        }
        sources = []
        for role, document in documents.items():
            path = self.folder / f"{role}.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            sources.append({"role": role, "document": document,
                            "ref": make_artifact_ref(str(path), role, "1", "LOCKED")})
        self.document = {"flow_counts": derive_prisma_counts(sources, adjustments=[{
            "count": "records_removed_other_reasons", "value": 3,
            "reason": "Fictional adjustment", "approved_by": "Test fixture",
            "approved_at": "2026-01-01",
        }])}

    def with_breakdowns(self):
        value = copy.deepcopy(self.document)
        value["records_by_source"] = [
            {"source": "Databases", "count": 100},
            {"source": "Registers", "count": 23},
        ]
        value["reports_excluded_reasons"] = [
            {"reason": "Duration < 5 & missing outcome", "count": 30},
            {"reason": 'Wrong "design"', "count": 2},
        ]
        return value

    def rehash(self, document):
        block = document["flow_counts"]
        block["derivation_sha256"] = canonical_json_sha256(
            {key: value for key, value in block.items() if key != "derivation_sha256"})

    def cli(self, *args):
        return subprocess.run([sys.executable, str(SHARED / "prisma_flow.py"),
                               *map(str, args)], cwd=ROOT,
                              text=True, capture_output=True, check=False)

    def test_reconciling_input_renders_all_formats_and_counts(self):
        labels = (
            "Records identified from:", "Records removed before screening:",
            "Duplicate records removed", "Records screened", "Records excluded",
            "Reports sought for retrieval", "Reports not retrieved",
            "Reports assessed for eligibility", "Reports excluded:",
            "Studies included in review", "Reports of included studies",
        )
        for document in (self.document, self.with_breakdowns()):
            for format in FORMATS:
                with self.subTest(format=format, breakdowns=len(document) > 1):
                    result = render(document, format)
                    # SVG may wrap a label across multiple text elements.
                    visible = " ".join(ET.fromstring(result).itertext()) if format == "svg" else result
                    for label in labels:
                        self.assertIn(label, visible)
                    for count in document["flow_counts"]["counts"].values():
                        self.assertIn(f"(n = {count})", visible)
                    for phase in ("Identification", "Screening", "Included"):
                        self.assertIn(phase, visible)

    def test_svg_escapes_text_and_has_flow_arrows(self):
        result = render(self.with_breakdowns(), "svg")
        root = ET.fromstring(result)
        self.assertEqual("{http://www.w3.org/2000/svg}svg", root.tag)
        self.assertIn("&lt;", result)
        self.assertIn("&amp;", result)
        self.assertIn("Duration < 5 & missing outcome", " ".join(root.itertext()))
        arrows = [node for node in root.iter() if node.get("marker-end")]
        self.assertEqual(8, len(arrows))

    def test_mermaid_escapes_untrusted_labels(self):
        document = self.with_breakdowns()
        document["records_by_source"][0]["source"] = 'DB"][evil] <script> & # `'
        result = render(document)
        self.assertNotIn('<script>', result)
        self.assertNotIn('"][evil]', result)
        self.assertIn('#34;', result)
        self.assertIn('#38;', result)

    def test_deterministic_and_does_not_mutate_input(self):
        document = self.with_breakdowns()
        original = copy.deepcopy(document)
        for format in FORMATS:
            self.assertEqual(render(document, format), render(copy.deepcopy(document), format))
        self.assertEqual(original, document)

    def test_optional_details_are_omitted_without_invented_counts(self):
        for format in FORMATS:
            result = render(self.document, format)
            self.assertNotIn("Duration", result)
            self.assertNotIn("Databases (n =", result)
            self.assertNotIn("Registers (n =", result)
            self.assertNotIn("automation", result)
            self.assertNotIn("Reason 1", result)

    def test_each_broken_identity_is_named(self):
        cases = (
            ("records_identified", "records_screened"),
            ("records_excluded", "reports_sought"),
            ("reports_not_retrieved", "reports_assessed"),
            ("reports_excluded", "reports_included"),
            ("studies_included", "studies_included"),
        )
        for key, identity in cases:
            document = copy.deepcopy(self.document)
            document["flow_counts"]["counts"][key] += 10
            self.rehash(document)
            for format in FORMATS:
                with self.subTest(identity=identity, format=format):
                    with self.assertRaisesRegex(ValueError, identity):
                        render(document, format)

    def test_hand_entered_counts_and_tampering_are_refused(self):
        for block in (self.document["flow_counts"]["counts"], {"derived": False}):
            with self.assertRaisesRegex(ValueError, "manually entered"):
                render({"flow_counts": block})
        document = copy.deepcopy(self.document)
        document["flow_counts"]["counts"]["records_identified"] += 1
        with self.assertRaisesRegex(ValueError, "derivation hash mismatch"):
            render(document)
        source = Path(document["flow_counts"]["sources"][0]["ref"]["path"])
        source.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "artifact hash mismatch"):
            render(self.document)

    def test_breakdowns_must_sum_to_the_corresponding_total(self):
        for key, total in (("records_by_source", "records_identified"),
                           ("reports_excluded_reasons", "reports_excluded")):
            document = self.with_breakdowns()
            document[key][0]["count"] += 1
            with self.assertRaisesRegex(ValueError, f"{key}.*{total}"):
                render(document)

    def test_invalid_breakdown_shapes_and_counts_are_refused(self):
        for name, label in (("records_by_source", "source"),
                            ("reports_excluded_reasons", "reason")):
            for entries in (None, {}, [1], [{label: "", "count": 0}],
                            [{label: "x", "count": True}],
                            [{label: "x", "count": -1}],
                            [{label: "x", "count": 1.5}],
                            [{label: "x\x00", "count": 0}]):
                with self.subTest(name=name, entries=entries):
                    document = copy.deepcopy(self.document)
                    document[name] = entries
                    with self.assertRaisesRegex(ValueError, name):
                        render(document)

    def test_empty_breakdowns_and_zero_counts(self):
        document = copy.deepcopy(self.document)
        document["flow_counts"]["counts"] = dict.fromkeys(document["flow_counts"]["counts"], 0)
        self.rehash(document)
        document.update(records_by_source=[], reports_excluded_reasons=[])
        for format in FORMATS:
            self.assertIn("n = 0", render(document, format))

    def test_long_details_fit_svg_height(self):
        document = self.with_breakdowns()
        document["reports_excluded_reasons"][0]["reason"] = "Long reason " * 80
        result = ET.fromstring(render(document, "svg"))
        short = ET.fromstring(render(self.with_breakdowns(), "svg"))
        self.assertGreater(int(result.get("height")), int(short.get("height")))
        for node in result.iter("{http://www.w3.org/2000/svg}text"):
            self.assertLess(float(node.get("y")), int(result.get("height")))

    def test_cli_stdout_file_help_and_usage_codes(self):
        source = self.folder / "input.json"
        source.write_text(json.dumps(self.document), encoding="utf-8")
        result = self.cli(source)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(render(self.document), result.stdout)
        self.assertEqual("", result.stderr)
        for format in FORMATS:
            output = self.folder / f"flow.{format}"
            result = self.cli(source, "--format", format, "--output", output)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual("", result.stdout)
            self.assertEqual(render(self.document, format), output.read_text(encoding="utf-8"))
        self.assertEqual(0, self.cli("--help").returncode)
        self.assertEqual(2, self.cli().returncode)
        self.assertEqual(2, self.cli(source, "--format", "pdf").returncode)

    def test_cli_validation_and_io_errors_are_json_and_preserve_output(self):
        source = self.folder / "input.json"
        output = self.folder / "existing.svg"
        output.write_text("preserve", encoding="utf-8")
        for value in ('{', '[]', '{"flow_counts": {"derived": false}}',
                      '{"flow_counts": {"sources": null}}'):
            source.write_text(value, encoding="utf-8")
            result = self.cli(source, "--output", output)
            self.assertEqual(1, result.returncode, result.stderr)
            self.assertIn("error", json.loads(result.stderr))
            self.assertEqual("", result.stdout)
            self.assertEqual("preserve", output.read_text(encoding="utf-8"))
        result = self.cli(self.folder / "missing.json")
        self.assertEqual(1, result.returncode)
        self.assertIn("error", json.loads(result.stderr))
        source.write_text(json.dumps(self.document), encoding="utf-8")
        result = self.cli(source, "--output", self.folder)
        self.assertEqual(1, result.returncode)
        self.assertIn("error", json.loads(result.stderr))

    def test_bundled_fictional_example_renders(self):
        path = ROOT / "examples" / "minimal-review" / "prisma_flow_counts.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        self.assertIs(True, document["fictional"])
        self.assertEqual(1, document["flow_counts"]["counts"]["studies_included"])
        self.assertEqual(1, document["flow_counts"]["counts"]["reports_included"])
        for format in FORMATS:
            result = self.cli(path, "--format", format)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(render(document, format), result.stdout)


if __name__ == "__main__":
    unittest.main()
