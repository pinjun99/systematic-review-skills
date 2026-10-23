#!/usr/bin/env python3

from __future__ import annotations

from pathlib import Path
import sys
import unittest


SHARED = Path(__file__).resolve().parents[1]
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))

from v2_runtime import V2ContractError  # noqa: E402
from v2_screening import resolve_screening  # noqa: E402


def decision(record_id, reviewer_id, decision, reason=None, reviewer_type="ai"):
    tier = 0 if decision == "include" else (2 if decision == "uncertain" else 1)
    evidence = [] if tier == 0 else [{
        "source_id": "PDF-1", "text_span": "The experiment was conducted in vivo.",
        "page": 3, "verified": True
    }]
    return {
        "schema_version": "2.0", "record_id": record_id, "study_id": "S1",
        "stage": "full_text_screening", "decision": decision,
        "primary_reason_code": reason, "confidence": 0.97,
        "evidence_tier": tier,
        "eligibility_checklist": {"experimental_model": "not_met" if decision == "exclude" else "met"},
        "evidence": evidence,
        "reviewer": {"id": reviewer_id, "type": reviewer_type},
    }


class ScreeningResolutionTests(unittest.TestCase):
    def test_routine_inclusion_needs_one_ai(self):
        result = resolve_screening(decision("A", "agent-a", "include"))
        self.assertEqual("ROUTINE_AI_INCLUSION", result["route"])
        self.assertEqual("READY", result["state"])

    def test_exclusion_needs_second_ai(self):
        result = resolve_screening(decision("A", "agent-a", "exclude", "WRONG_MODEL"))
        self.assertEqual("SECOND_AI_REQUIRED", result["route"])
        self.assertEqual("NEEDS_HUMAN", result["state"])

    def test_matching_exclusions_are_accepted(self):
        a = decision("A", "agent-a", "exclude", "WRONG_MODEL")
        b = decision("B", "agent-b", "exclude", "WRONG_MODEL")
        result = resolve_screening(a, b)
        self.assertEqual("TWO_AI_EXCLUSION_AGREEMENT", result["route"])
        self.assertEqual("exclude", result["final_decision"])

    def test_reason_disagreement_routes_to_human(self):
        a = decision("A", "agent-a", "exclude", "WRONG_MODEL")
        b = decision("B", "agent-b", "exclude", "WRONG_POPULATION")
        result = resolve_screening(a, b)
        self.assertEqual("NEEDS_HUMAN", result["state"])

    def test_human_adjudication_resolves_disagreement(self):
        a = decision("A", "agent-a", "exclude", "WRONG_MODEL")
        b = decision("B", "agent-b", "include")
        human = decision("H", "reviewer-1", "exclude", "WRONG_MODEL", "human")
        result = resolve_screening(a, b, human)
        self.assertEqual("HUMAN_ADJUDICATION", result["route"])
        self.assertEqual("exclude", result["final_decision"])

    def test_same_reviewer_cannot_fill_both_roles(self):
        a = decision("A", "agent-a", "exclude", "WRONG_MODEL")
        b = decision("B", "agent-a", "exclude", "WRONG_MODEL")
        with self.assertRaisesRegex(V2ContractError, "must be distinct"):
            resolve_screening(a, b)


if __name__ == "__main__":
    unittest.main()
