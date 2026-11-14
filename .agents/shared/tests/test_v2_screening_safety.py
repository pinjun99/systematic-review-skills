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

from pathlib import Path
import sys
import unittest


SHARED = Path(__file__).resolve().parents[1]
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))

from v2_runtime import V2ContractError  # noqa: E402
from v2_screening import resolve_screening  # noqa: E402


def record(record_id, reviewer_id, reviewer_type, decision, reason=None):
    tier = 2 if decision == "uncertain" else 1
    return {
        "schema_version": "2.0", "record_id": record_id, "study_id": "S1",
        "stage": "full_text_screening", "decision": decision,
        "primary_reason_code": reason, "confidence": 0.9,
        "evidence_tier": tier,
        "eligibility_checklist": {"model": "unclear" if decision == "uncertain" else "not_met"},
        "evidence": [{"source_id": "P1", "text_span": "Decisive text", "page": 2, "verified": True}],
        "reviewer": {"id": reviewer_id, "type": reviewer_type},
    }


class ScreeningSafetyTests(unittest.TestCase):
    def test_two_humans_cannot_masquerade_as_two_ai_reviewers(self):
        a = record("A", "human-a", "human", "exclude", "WRONG_MODEL")
        b = record("B", "human-b", "human", "exclude", "WRONG_MODEL")
        with self.assertRaisesRegex(V2ContractError, "must be AI"):
            resolve_screening(a, b)

    def test_uncertain_human_adjudication_remains_unresolved(self):
        a = record("A", "agent-a", "ai", "exclude", "WRONG_MODEL")
        b = record("B", "agent-b", "ai", "exclude", "WRONG_POPULATION")
        human = record("H", "human-a", "human", "uncertain")
        result = resolve_screening(a, b, human)
        self.assertEqual("NEEDS_HUMAN", result["state"])
        self.assertEqual("HUMAN_UNRESOLVED", result["route"])
        self.assertIsNone(result["final_decision"])


if __name__ == "__main__":
    unittest.main()
