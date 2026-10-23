#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
MODULES_PATH = ROOT / ".agents" / "shared" / "references" / "v2-method-modules.json"


class MethodModuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.value = json.loads(MODULES_PATH.read_text(encoding="utf-8"))
        cls.modules = cls.value["modules"]

    def test_known_portfolio_is_complete(self):
        self.assertEqual(
            {
                "clinical_intervention", "observational_association",
                "ai_diagnostic_prediction", "preclinical_organ_bath",
                "scoping_evidence_mapping"
            },
            set(self.modules),
        )

    def test_each_module_has_executable_method_fields(self):
        for name, module in self.modules.items():
            self.assertTrue(module["eligibility_fields"], name)
            self.assertTrue(module["critical_extraction_fields"], name)
            self.assertTrue(module["synthesis_options"], name)
            self.assertIn(module["risk_of_bias"], {
                "REQUIRED_WHEN_RESULTS_ARE_SYNTHESIZED", "PROTOCOL_DECISION",
                "NOT_REQUIRED_BY_DEFAULT"
            })

    def test_scoping_does_not_force_appraisal_or_grade(self):
        module = self.modules["scoping_evidence_mapping"]
        self.assertEqual("NOT_REQUIRED_BY_DEFAULT", module["risk_of_bias"])
        self.assertEqual("NOT_REQUIRED_BY_DEFAULT", module["certainty"])

    def test_organ_bath_preserves_experimental_details(self):
        fields = set(self.modules["preclinical_organ_bath"]["critical_extraction_fields"])
        self.assertTrue({"bath_conditions", "concentration", "unit", "normalization"} <= fields)


if __name__ == "__main__":
    unittest.main()
