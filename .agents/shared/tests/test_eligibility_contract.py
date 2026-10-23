#!/usr/bin/env python3
"""Tests for canonical eligibility contracts and Phase 10 fidelity freeze."""

from __future__ import annotations

from contextlib import redirect_stderr
import argparse
from copy import deepcopy
import hashlib
import io
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
SHARED = ROOT / ".agents" / "shared"
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))

from eligibility_contract import (  # noqa: E402
    CONTRACT_REVIEW_DISCLOSURE,
    EligibilityContractError,
    RECORDED_DISCLOSURE,
    build_approval_receipt,
    compare_projection,
    lock_contract,
    make_file_ref,
    main as eligibility_main,
    project_contract,
    validate_approval_receipt,
    validate_contract,
)


STORE_PATH = (
    ROOT
    / ".agents"
    / "skills"
    / "systematic-review-full-text-screening"
    / "scripts"
    / "screening_store.py"
)
STORE_SPEC = importlib.util.spec_from_file_location("screening_store", STORE_PATH)
assert STORE_SPEC and STORE_SPEC.loader
screening_store = importlib.util.module_from_spec(STORE_SPEC)
STORE_SPEC.loader.exec_module(screening_store)


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


class EligibilityContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.protocol = self.root / "protocol.md"
        self.protocol.write_text(
            "# Protocol v1.2\n\n## Eligibility criteria\nApproved rules.\n",
            encoding="utf-8",
        )
        self.contract = self._contract()
        self.source = self.root / "canonical_eligibility_contract.source.json"
        self.locked_path = self.root / "canonical_eligibility_contract.json"
        write_json(self.source, self.contract)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _contract(self) -> dict:
        return {
            "schema_version": "1.0",
            "contract_type": "CANONICAL_ELIGIBILITY_CONTRACT",
            "contract_version": "1.0",
            "review_id": "SR-TEST",
            "review_title": "Test review",
            "criteria_version": "eligibility-1.0",
            "protocol_source": {
                "path": str(self.protocol),
                "section": "Eligibility criteria",
                "version": "1.2",
                "sha256": file_hash(self.protocol),
            },
            "human_review": {
                "status": "APPROVED",
                "reviewed_by": "methods-reviewer",
                "reviewed_at": "2026-01-02T00:00:00Z",
                "assertion": "The scientific eligibility meaning is correct.",
                "assurance_level": (
                    "RECORDED_NOT_INDEPENDENTLY_AUTHENTICATED"
                ),
                "identity_disclosure": CONTRACT_REVIEW_DISCLOSURE,
            },
            "clarifications": [
                {
                    "id": "CLAR-001",
                    "description": "Operational wording only.",
                    "protocol_version": "1.2",
                    "preserves_scientific_meaning": True,
                }
            ],
            "amendments": [
                {
                    "id": "AMD-001",
                    "description": "Approved design-rule amendment.",
                    "protocol_version": "1.2",
                    "approved": True,
                    "approved_by": "methods-reviewer",
                    "approved_at": "2026-01-02T00:00:00Z",
                }
            ],
            "criteria": [
                {
                    "id": "population",
                    "label": "Eligible population",
                    "scientific_meaning": {
                        "inclusion": "Children with the target condition.",
                        "exclusion": "Adults without paediatric participants.",
                    },
                    "stages": {
                        "title_abstract": {
                            "operational_question": (
                                "Is the population potentially eligible?"
                            ),
                            "inclusion_rule": (
                                "Retain children or mixed/unclear age samples."
                            ),
                            "exclusion_rule": (
                                "Exclude only explicit adult-only samples."
                            ),
                            "missing_information_action": "retain",
                            "exclusion_label": "Wrong population",
                        },
                        "full_text": {
                            "operational_question": (
                                "Does the study include the approved population?"
                            ),
                            "inclusion_rule": (
                                "Children with the target condition are eligible."
                            ),
                            "exclusion_rule": (
                                "Adult-only studies without paediatric data are "
                                "ineligible."
                            ),
                            "missing_information_action": "human_review",
                            "exclusion_label": "Wrong population",
                            "search_terms": ["participants", "age", "children"],
                        },
                    },
                    "provenance": {
                        "protocol_section": "Eligibility criteria — Population",
                        "clarification_ids": ["CLAR-001"],
                        "amendment_ids": [],
                    },
                },
                {
                    "id": "design",
                    "label": "Eligible design",
                    "scientific_meaning": {
                        "inclusion": "Randomized controlled trials.",
                        "exclusion": "Non-randomized study designs.",
                    },
                    "stages": {
                        "title_abstract": {
                            "operational_question": (
                                "Is the report potentially a randomized trial?"
                            ),
                            "inclusion_rule": (
                                "Retain explicit or possibly randomized trials."
                            ),
                            "exclusion_rule": (
                                "Exclude only an explicitly non-randomized design."
                            ),
                            "missing_information_action": "retain",
                            "exclusion_label": "Wrong study design",
                        },
                        "full_text": {
                            "operational_question": (
                                "Was allocation randomized as required?"
                            ),
                            "inclusion_rule": (
                                "The report must document randomized allocation."
                            ),
                            "exclusion_rule": (
                                "Explicit non-random allocation is ineligible."
                            ),
                            "missing_information_action": "human_review",
                            "exclusion_label": "Wrong study design",
                            "search_terms": [
                                "random",
                                "allocation",
                                "sequence generation",
                            ],
                        },
                    },
                    "provenance": {
                        "protocol_section": "Eligibility criteria — Design",
                        "clarification_ids": [],
                        "amendment_ids": ["AMD-001"],
                    },
                },
            ],
        }

    def _lock_and_artifacts(self, stage: str) -> dict:
        locked = lock_contract(str(self.source), str(self.locked_path))
        projection = project_contract(locked, stage)
        projection_path = self.root / f"{stage}_criteria.json"
        write_json(projection_path, projection)
        comparison = compare_projection(locked, projection, stage)
        comparison_path = self.root / f"{stage}_comparison.json"
        write_json(comparison_path, comparison)
        receipt = build_approval_receipt(
            make_file_ref(str(self.protocol), "protocol_source"),
            make_file_ref(str(self.locked_path), "canonical_contract"),
            make_file_ref(
                str(comparison_path), "projection_comparison"
            ),
            make_file_ref(str(projection_path), "eligibility_projection"),
            "I reviewed this projection against the protocol and approve its "
            "semantic fidelity.",
            "RECORDED_NOT_INDEPENDENTLY_AUTHENTICATED",
        )
        receipt_path = self.root / f"{stage}_approval.json"
        write_json(receipt_path, receipt)
        return {
            "locked": locked,
            "projection": projection,
            "projection_path": projection_path,
            "comparison": comparison,
            "comparison_path": comparison_path,
            "receipt": receipt,
            "receipt_path": receipt_path,
        }

    def test_validate_lock_and_deterministic_stage_projections(self) -> None:
        validate_contract(self.contract)
        locked = lock_contract(str(self.source), str(self.locked_path))
        validate_contract(locked)
        self.assertEqual(locked["lock"]["status"], "INTERNAL_LOCKED")
        title = project_contract(locked, "title_abstract")
        full = project_contract(locked, "full_text")
        self.assertEqual(
            title["criteria"][0]["missing_information_action"], "retain"
        )
        self.assertEqual(
            full["criteria"][0]["missing_information_action"], "human_review"
        )
        self.assertEqual(
            full["criteria"][0]["primary_exclusion_reason"],
            "Wrong population",
        )
        self.assertEqual(
            [item["id"] for item in title["criteria"]],
            ["population", "design"],
        )
        self.assertEqual(
            title["canonical_contract_hash"],
            full["canonical_contract_hash"],
        )
        self.assertEqual(title, project_contract(locked, "title_abstract"))

    def test_structural_comparison_reports_delta_without_semantic_claim(self) -> None:
        locked = lock_contract(str(self.source), str(self.locked_path))
        projection = project_contract(locked, "title_abstract")
        exact = compare_projection(locked, projection, "title_abstract")
        self.assertTrue(exact["structurally_equivalent"])
        self.assertFalse(exact["semantic_fidelity_claimed"])
        self.assertTrue(exact["human_semantic_approval_required"])
        changed = deepcopy(projection)
        changed["criteria"][0]["inclusion_rule"] = "Narrowed rule"
        delta = compare_projection(locked, changed, "title_abstract")
        self.assertFalse(delta["structurally_equivalent"])
        self.assertIn(
            "$.criteria[0].inclusion_rule",
            {item["path"] for item in delta["differences"]},
        )

    def test_clarification_and_amendment_provenance_is_enforced(self) -> None:
        validate_contract(self.contract)
        invalid = deepcopy(self.contract)
        invalid["criteria"][1]["provenance"]["amendment_ids"] = ["UNKNOWN"]
        with self.assertRaisesRegex(
            EligibilityContractError, "unknown IDs"
        ):
            validate_contract(invalid)
        changed = deepcopy(self.contract)
        changed["amendments"][0]["description"] = "Changed approved amendment"
        with self.assertRaisesRegex(
            EligibilityContractError, "INTERNAL_LOCKED"
        ):
            project_contract(self.contract, "full_text")
        original_source = self.root / "original_for_amendment.json"
        original_locked_path = self.root / "original_for_amendment.locked.json"
        changed_source = self.root / "changed_amendment.json"
        changed_locked_path = self.root / "changed_amendment.locked.json"
        write_json(original_source, self.contract)
        write_json(changed_source, changed)
        original_locked = lock_contract(
            str(original_source), str(original_locked_path)
        )
        changed_locked = lock_contract(
            str(changed_source), str(changed_locked_path)
        )
        original_hash = project_contract(
            original_locked, "full_text"
        )["canonical_contract_hash"]
        changed_hash = project_contract(
            changed_locked, "full_text"
        )["canonical_contract_hash"]
        self.assertNotEqual(original_hash, changed_hash)

    def test_lock_rejects_protocol_tamper_and_existing_output(self) -> None:
        self.protocol.write_text("tampered protocol", encoding="utf-8")
        with self.assertRaisesRegex(
            EligibilityContractError, "protocol source hash"
        ):
            lock_contract(str(self.source), str(self.locked_path))
        self.protocol.write_text(
            "# Protocol v1.2\n\n## Eligibility criteria\nApproved rules.\n",
            encoding="utf-8",
        )
        lock_contract(str(self.source), str(self.locked_path))
        with self.assertRaisesRegex(
            EligibilityContractError, "already locked|overwrite"
        ):
            lock_contract(str(self.source), str(self.locked_path))

    def test_unanchored_approval_is_bound_and_disclosed(self) -> None:
        artifacts = self._lock_and_artifacts("title_abstract")
        receipt = artifacts["receipt"]
        self.assertEqual(
            receipt["identity_disclosure"], RECORDED_DISCLOSURE
        )
        result = validate_approval_receipt(receipt)
        self.assertTrue(result["valid"])
        self.assertEqual(
            receipt["canonical_contract_hash"],
            artifacts["comparison"]["canonical_contract_hash"],
        )
        self.assertEqual(
            receipt["comparison_tool_version"],
            artifacts["comparison"]["tool_version"],
        )

    def test_runtime_assurance_requires_verified_external_anchor(self) -> None:
        artifacts = self._lock_and_artifacts("title_abstract")
        refs = (
            make_file_ref(str(self.protocol), "protocol_source"),
            make_file_ref(str(self.locked_path), "canonical_contract"),
            make_file_ref(
                str(artifacts["comparison_path"]), "projection_comparison"
            ),
            make_file_ref(
                str(artifacts["projection_path"]), "eligibility_projection"
            ),
        )
        with self.assertRaisesRegex(
            EligibilityContractError, "runtime_anchor"
        ):
            build_approval_receipt(
                *refs,
                "Approved.",
                "RUNTIME_VERIFIED_HUMAN",
            )
        anchor = {
            "verification_status": "VERIFIED_OUTSIDE_AGENT_WRITE_SCOPE",
            "anchor_type": "trusted-runtime-receipt",
            "anchor_id": "anchor-123",
            "verified_at": "2026-01-02T00:00:00Z",
            "evidence_sha256": "a" * 64,
        }
        receipt = build_approval_receipt(
            *refs,
            "Approved.",
            "RUNTIME_VERIFIED_HUMAN",
            anchor,
        )
        self.assertIsNone(receipt["identity_disclosure"])
        self.assertTrue(validate_approval_receipt(receipt)["valid"])

    def test_approval_detects_projection_and_receipt_tamper(self) -> None:
        artifacts = self._lock_and_artifacts("title_abstract")
        projection = deepcopy(artifacts["projection"])
        projection["criteria"][0]["label"] = "Tampered label"
        write_json(artifacts["projection_path"], projection)
        with self.assertRaisesRegex(
            EligibilityContractError, "reference hash mismatch"
        ):
            validate_approval_receipt(artifacts["receipt"])
        tampered_receipt = deepcopy(artifacts["receipt"])
        tampered_receipt["approver_assertion"] = "Changed assertion"
        with self.assertRaisesRegex(
            EligibilityContractError, "receipt hash mismatch"
        ):
            validate_approval_receipt(tampered_receipt)



    def test_phase10_initialization_rejects_hand_authored_criteria(self) -> None:
        artifacts = self._lock_and_artifacts("full_text")
        manual = deepcopy(artifacts["projection"])
        del manual["projection_type"]
        with self.assertRaisesRegex(
            ValueError, "canonical eligibility stage projection"
        ):
            screening_store.validate_criteria(manual)

    def test_cli_validate_lock_project_compare_approve_and_no_overwrite(
        self,
    ) -> None:
        validation_path = self.root / "validation.json"
        self.assertEqual(
            eligibility_main(
                [
                    "validate",
                    "--contract",
                    str(self.source),
                    "--output",
                    str(validation_path),
                ]
            ),
            0,
        )
        self.assertEqual(
            eligibility_main(
                [
                    "lock",
                    "--source",
                    str(self.source),
                    "--output",
                    str(self.locked_path),
                ]
            ),
            0,
        )
        projection_path = self.root / "cli_projection.json"
        comparison_path = self.root / "cli_comparison.json"
        receipt_path = self.root / "cli_receipt.json"
        common = ["--contract", str(self.locked_path)]
        self.assertEqual(
            eligibility_main(
                [
                    "project",
                    *common,
                    "--stage",
                    "full_text",
                    "--output",
                    str(projection_path),
                ]
            ),
            0,
        )
        self.assertEqual(
            eligibility_main(
                [
                    "compare",
                    *common,
                    "--projection",
                    str(projection_path),
                    "--stage",
                    "full_text",
                    "--output",
                    str(comparison_path),
                ]
            ),
            0,
        )
        self.assertEqual(
            eligibility_main(
                [
                    "approve",
                    "--protocol",
                    str(self.protocol),
                    *common,
                    "--comparison",
                    str(comparison_path),
                    "--projection",
                    str(projection_path),
                    "--assertion",
                    "Semantic fidelity reviewed and approved.",
                    "--assurance-level",
                    "RECORDED_NOT_INDEPENDENTLY_AUTHENTICATED",
                    "--output",
                    str(receipt_path),
                ]
            ),
            0,
        )
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertTrue(validate_approval_receipt(receipt)["valid"])
        with redirect_stderr(io.StringIO()):
            self.assertEqual(
                eligibility_main(
                    [
                        "validate",
                        "--contract",
                        str(self.source),
                        "--output",
                        str(validation_path),
                    ]
                ),
                2,
            )
    def test_full_text_fidelity_is_enforced_in_freeze_transaction(self) -> None:
        artifacts = self._lock_and_artifacts("full_text")
        database_path = self.root / "full_text.sqlite"
        screening_store.cmd_init(
            argparse.Namespace(
                db=str(database_path),
                review_id="SR-TEST",
                screening_version="screening-1.0",
                criteria=str(artifacts["projection_path"]),
                criteria_source=str(self.locked_path),
                reason="Initial version",
            )
        )
        database = sqlite3.connect(database_path)
        database.execute("PRAGMA foreign_keys = ON")
        database.execute(
            """
            INSERT INTO corpus_studies(
                screening_version, study_id, title, link_status, metadata_json
            ) VALUES ('screening-1.0', 'S001', 'Fixture', 'resolved', '{}')
            """
        )
        database.commit()
        database.close()
        screening_store.cmd_freeze_corpus(
            argparse.Namespace(
                db=str(database_path),
                screening_version="screening-1.0",
                approved_by="methods-reviewer",
                reason="Corpus and criteria approved",
                protocol_amendment_ref="",
                canonical_contract=str(self.locked_path),
                projection_comparison=str(artifacts["comparison_path"]),
                approval_receipt=str(artifacts["receipt_path"]),
            )
        )
        database = sqlite3.connect(database_path)
        database.row_factory = sqlite3.Row
        row = database.execute(
            "SELECT status, eligibility_fidelity_json "
            "FROM screening_versions WHERE screening_version = 'screening-1.0'"
        ).fetchone()
        database.close()
        self.assertEqual(row["status"], "corpus_frozen")
        fidelity = json.loads(row["eligibility_fidelity_json"])
        self.assertEqual(fidelity["status"], "APPROVED_AT_FREEZE")
        self.assertEqual(
            fidelity["approval_receipt_hash"],
            artifacts["receipt"]["receipt_hash"],
        )

    def test_failed_fidelity_freeze_rolls_back_to_draft(self) -> None:
        artifacts = self._lock_and_artifacts("full_text")
        invalid_receipt = deepcopy(artifacts["receipt"])
        invalid_receipt["approver_assertion"] = "Tampered"
        invalid_receipt_path = self.root / "invalid_approval.json"
        write_json(invalid_receipt_path, invalid_receipt)
        database_path = self.root / "rollback.sqlite"
        screening_store.cmd_init(
            argparse.Namespace(
                db=str(database_path),
                review_id="SR-TEST",
                screening_version="screening-1.0",
                criteria=str(artifacts["projection_path"]),
                criteria_source=str(self.locked_path),
                reason="Initial version",
            )
        )
        database = sqlite3.connect(database_path)
        database.execute(
            """
            INSERT INTO corpus_studies(
                screening_version, study_id, title, link_status, metadata_json
            ) VALUES ('screening-1.0', 'S001', 'Fixture', 'resolved', '{}')
            """
        )
        database.commit()
        database.close()
        with self.assertRaisesRegex(
            ValueError, "Eligibility fidelity approval failed"
        ):
            screening_store.cmd_freeze_corpus(
                argparse.Namespace(
                    db=str(database_path),
                    screening_version="screening-1.0",
                    approved_by="methods-reviewer",
                    reason="Attempted freeze",
                    protocol_amendment_ref="",
                    canonical_contract=str(self.locked_path),
                    projection_comparison=str(artifacts["comparison_path"]),
                    approval_receipt=str(invalid_receipt_path),
                )
            )
        database = sqlite3.connect(database_path)
        row = database.execute(
            "SELECT status, eligibility_fidelity_json "
            "FROM screening_versions WHERE screening_version = 'screening-1.0'"
        ).fetchone()
        database.close()
        self.assertEqual(row[0], "draft")
        self.assertIsNone(row[1])


if __name__ == "__main__":
    unittest.main()
