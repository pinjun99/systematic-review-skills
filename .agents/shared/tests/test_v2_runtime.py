#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest


SHARED = Path(__file__).resolve().parents[1]
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))

from v2_runtime import (  # noqa: E402
    V2ContractError,
    affected_refs,
    approve_milestone,
    import_v1_artifact,
    object_sha256,
    register_issue,
    resolve_issue,
    validate_decision_record,
    validate_phase_result,
    validate_review_config,
)


class ConfigTests(unittest.TestCase):
    def sample(self):
        return {
            "schema_version": "2.0",
            "review_id": "SRV2-001",
            "title": "AI in healthcare",
            "protocol_version": "1.0",
            "active_modules": ["ai_diagnostic_prediction"],
            "team_roles": {"owner": "Reviewer 1"},
            "ai_policy": {"posture": "AI_FIRST_RISK_BASED", "paid_api_authorized": False},
        }

    def test_valid_config(self):
        self.assertEqual("SRV2-001", validate_review_config(self.sample())["review_id"])

    def test_unknown_module_fails(self):
        value = self.sample()
        value["active_modules"] = ["anything_goes"]
        with self.assertRaisesRegex(V2ContractError, "unsupported module"):
            validate_review_config(value)


class EvidencePolicyTests(unittest.TestCase):
    def record(self, decision="include", tier=0, stage="full_text_screening"):
        return {
            "schema_version": "2.0",
            "record_id": "R1",
            "study_id": "S1",
            "stage": stage,
            "decision": decision,
            "primary_reason_code": "WRONG_POPULATION" if decision == "exclude" else None,
            "confidence": 0.94,
            "evidence_tier": tier,
            "eligibility_checklist": {"population": "met", "concept": "met"},
            "evidence": [],
            "reviewer": {"id": "agent-a", "type": "ai"},
        }

    def test_inclusion_needs_no_manufactured_quote(self):
        result = validate_decision_record(self.record())
        self.assertEqual([], result["evidence"])

    def test_inclusion_with_quote_is_rejected(self):
        value = self.record()
        value["evidence"] = [{"source_id": "P1", "text_span": "text", "verified": True}]
        with self.assertRaisesRegex(V2ContractError, "must not manufacture"):
            validate_decision_record(value)

    def test_full_text_exclusion_needs_one_page_cited_reason(self):
        value = self.record("exclude", 1)
        value["eligibility_checklist"]["population"] = "not_met"
        value["evidence"] = [{
            "source_id": "P1", "text_span": "Adults without the condition were enrolled.",
            "page": 4, "verified": True
        }]
        self.assertEqual("exclude", validate_decision_record(value)["decision"])

    def test_full_text_exclusion_without_locator_fails(self):
        value = self.record("exclude", 1)
        value["evidence"] = [{"source_id": "P1", "text_span": "Wrong population", "verified": True}]
        with self.assertRaisesRegex(V2ContractError, "requires a source locator"):
            validate_decision_record(value)

    def test_title_abstract_exclusion_uses_text_span_without_page(self):
        value = self.record("exclude", 1, "title_abstract_screening")
        value["evidence"] = [{"source_id": "C1", "text_span": "This mouse study", "verified": True}]
        self.assertEqual("exclude", validate_decision_record(value)["decision"])

    def test_uncertain_case_requires_tier_two(self):
        with self.assertRaisesRegex(V2ContractError, "require Tier 2"):
            validate_decision_record(self.record("uncertain", 1))


class LifecycleTests(unittest.TestCase):
    def test_ready_phase_cannot_hide_issues(self):
        value = {
            "schema_version": "2.0", "phase": "data_extraction", "state": "READY",
            "input_refs": [], "output_refs": ["dataset:1"],
            "unresolved_issue_ids": ["I1"], "next_phase": "risk_of_bias"
        }
        with self.assertRaisesRegex(V2ContractError, "cannot retain unresolved"):
            validate_phase_result(value)

    def test_milestone_approval_is_object_bound(self):
        subject = {"phase": "protocol", "version": "1.0"}
        approval = {
            "milestone_id": "M1_PROTOCOL", "approved_by": "Owner",
            "approved_at": "2026-08-03T10:00:00+08:00", "assertion": "Approved",
            "subject_sha256": object_sha256(subject)
        }
        self.assertEqual("APPROVED", approve_milestone(subject, approval)["state"])
        approval["subject_sha256"] = "0" * 64
        with self.assertRaisesRegex(V2ContractError, "not bound"):
            approve_milestone(subject, approval)


class ImportAndCorrectionTests(unittest.TestCase):
    def test_v1_import_drops_locks_and_approvals(self):
        source = {"decisions": [{"study_id": "S1", "decision": "include"}],
                  "approval": {"approved": True}, "lock": {"status": "LOCKED"}}
        result = import_v1_artifact("screening_decisions", source, source_sha256="a" * 64)
        self.assertEqual({"decisions": source["decisions"]}, result["data"])
        self.assertFalse(result["provenance"]["approval_state_imported"])

    def test_local_issue_invalidates_only_real_dependents(self):
        graph = {"study:S1": ["dataset:D1"], "dataset:D1": ["result:R1"],
                 "study:S2": ["dataset:D2"]}
        self.assertEqual(
            ["dataset:D1", "result:R1", "study:S1"],
            affected_refs("study:S1", graph),
        )
        issue = register_issue({
            "issue_id": "I1", "owner_ref": "study:S1", "finding": "Wrong unit",
            "severity": "critical"
        })
        resolved = resolve_issue(issue, corrected_ref="study:S1:v2", dependency_graph=graph)
        self.assertNotIn("dataset:D2", resolved["affected_refs"])
        self.assertEqual("RESOLVED", resolved["status"])


if __name__ == "__main__":
    unittest.main()
