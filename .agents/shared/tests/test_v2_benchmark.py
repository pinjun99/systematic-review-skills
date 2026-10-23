#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest


SHARED = Path(__file__).resolve().parents[1]
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))

from v2_benchmark import efficiency_metrics, release_gate, scientific_metrics  # noqa: E402


GOLD_PATH = Path(__file__).parent / "fixtures" / "v2" / "gold.json"


def perfect_run(gold):
    return [
        {
            "case_id": case["case_id"],
            "decision": case["decision"],
            "primary_reason_code": case.get("primary_reason_code"),
            "critical_fields": case.get("critical_fields", {}),
            "evidence_verified": True,
            "expert_judgments": case.get("expert_judgments", {}),
        }
        for case in gold
    ]


class ScientificBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gold = json.loads(GOLD_PATH.read_text(encoding="utf-8"))

    def test_gold_covers_all_modules_and_scenarios(self):
        result = scientific_metrics(self.gold, perfect_run(self.gold))
        self.assertEqual(15, result["case_count"])
        self.assertEqual([], result["critical_errors"])

    def test_false_exclusion_is_visible(self):
        run = perfect_run(self.gold)
        run[0]["decision"] = "exclude"
        result = scientific_metrics(self.gold, run)
        self.assertEqual(["CI-01"], result["false_exclusion_case_ids"])

    def test_fabricated_evidence_is_critical(self):
        run = perfect_run(self.gold)
        run[0]["fabricated_evidence"] = True
        result = scientific_metrics(self.gold, run)
        self.assertEqual("fabricated_evidence", result["critical_errors"][0]["error"])


class EfficiencyBenchmarkTests(unittest.TestCase):
    def test_all_planned_thresholds_pass(self):
        v1 = {"mandatory_context": 1000, "quotation_entries": 100,
              "approval_pauses": 15, "tokens": [1000, 1100, 900],
              "seconds": [100, 110, 90], "recomputed_records": 100,
              "phase_wide_rerun": True}
        v2 = {"mandatory_context": 550, "quotation_entries": 40,
              "approval_pauses": 5, "tokens": [650, 700, 600],
              "seconds": [65, 70, 60], "recomputed_records": 40,
              "phase_wide_rerun": False}
        result = efficiency_metrics(v1, v2)
        self.assertTrue(result["passed"])

    def test_release_requires_science_and_efficiency(self):
        gold = json.loads(GOLD_PATH.read_text(encoding="utf-8"))
        run = perfect_run(gold)
        v1 = {"mandatory_context": 1000, "quotation_entries": 100,
              "approval_pauses": 15, "tokens": [1000], "seconds": [100],
              "recomputed_records": 100, "phase_wide_rerun": True}
        v2 = {"mandatory_context": 900, "quotation_entries": 90,
              "approval_pauses": 5, "tokens": [900], "seconds": [90],
              "recomputed_records": 90, "phase_wide_rerun": False}
        result = release_gate(gold, run, run, v1, v2)
        self.assertEqual("BLOCKED", result["release_status"])


if __name__ == "__main__":
    unittest.main()
