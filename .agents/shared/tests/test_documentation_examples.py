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

"""Keep the fictional walkthrough executable against the shipped runtime."""

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
EXAMPLE = ROOT / "examples" / "minimal-review"
RUNTIME = ROOT / ".agents" / "shared" / "v2_runtime.py"


class MinimalReviewTests(unittest.TestCase):
    def run_runtime(self, *args):
        result = subprocess.run(
            [sys.executable, str(RUNTIME), *map(str, args)],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stderr)
        return json.loads(result.stdout)

    def test_config_and_phase_validate_with_documented_output(self):
        readme = (EXAMPLE / "README.md").read_text(encoding="utf-8")
        expected_outputs = re.findall(r"```json\n(.*?)\n```", readme, re.S)
        commands = [("validate-config", "review_config.json"),
                    ("validate-phase", "phase_result.json")]
        self.assertEqual(len(commands), len(expected_outputs))
        for (command, filename), output in zip(commands, expected_outputs):
            with self.subTest(command=command):
                value = self.run_runtime(command, EXAMPLE / filename)
                self.assertEqual(json.loads(output), value)
                self.assertEqual(
                    json.loads((EXAMPLE / filename).read_text(encoding="utf-8")), value,
                )

    def test_protocol_is_json_and_an_acceptable_approval_subject(self):
        # No protocol schema validator exists. Exercise JSON parsing and the
        # runtime's actual protocol-subject interface without approving a review.
        source = EXAMPLE / "protocol.json"
        parsed = subprocess.run(
            [sys.executable, "-m", "json.tool", str(source)],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        self.assertEqual(0, parsed.returncode, parsed.stderr)
        subject = json.loads(parsed.stdout)
        config = json.loads((EXAMPLE / "review_config.json").read_text(encoding="utf-8"))
        self.assertEqual(config["review_id"], subject["review_id"])
        self.assertEqual(config["protocol_version"], subject["protocol_version"])
        self.assertIs(True, subject["fictional"])
        self.assertEqual("DRAFT", subject["status"])
        canonical = json.dumps(
            subject, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")
        approval = {
            "milestone_id": "M1_PROTOCOL",
            "approved_by": "Fictional test reviewer",
            "approved_at": "2026-01-01T00:00:00Z",
            "assertion": "Synthetic test only; no real review approval.",
            "subject_sha256": hashlib.sha256(canonical).hexdigest(),
        }
        with tempfile.TemporaryDirectory() as directory:
            approval_path = Path(directory) / "approval.json"
            output_path = Path(directory) / "approved.json"
            approval_path.write_text(json.dumps(approval), encoding="utf-8")
            result = self.run_runtime("approve", source, approval_path, output_path)
            self.assertEqual("APPROVED", result["state"])
            self.assertEqual(approval["subject_sha256"], result["subject_sha256"])
            self.assertEqual(json.loads(output_path.read_text(encoding="utf-8")), result)


if __name__ == "__main__":
    unittest.main()
