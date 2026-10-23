#!/usr/bin/env python3
"""Tests for the uniform systematic-review workspace lifecycle primitives.

These are known-answer tests for the layer's contract: derived paths, path
containment, schema validation, duplicate identifiers and roles, symlink and
root-escape refusal, and fail-closed writes. Behavior owned by briefs 18 and 19
is asserted only as a committed stub interface.
"""

from __future__ import annotations

import contextlib
import hashlib
import inspect
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
SHARED = ROOT / ".agents" / "shared"
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))

import approval_ledger  # noqa: E402
import artifact_ref  # noqa: E402
import workspace_lifecycle as wl  # noqa: E402


LITERAL_ROOT = "/reviews/rev-a"


def ref(path: Path, role: str, *, status: str = "LOCKED") -> dict:
    return artifact_ref.make_artifact_ref(str(path), role, "1.0", status)


class PathDerivationTests(unittest.TestCase):
    """Every workspace path is derived, never assembled by a caller."""

    def test_known_answer_layout(self) -> None:
        self.assertEqual(
            wl.review_manifest_path(LITERAL_ROOT),
            Path("/reviews/rev-a/review_manifest.json"),
        )
        self.assertEqual(
            wl.ledger_path(LITERAL_ROOT),
            Path("/reviews/rev-a/ledger/execution.jsonl"),
        )
        self.assertEqual(
            wl.state_path(LITERAL_ROOT),
            Path("/reviews/rev-a/state/review_state.json"),
        )
        self.assertEqual(
            wl.phase_dir(LITERAL_ROOT, "phase-01"),
            Path("/reviews/rev-a/runs/phase-01"),
        )
        self.assertEqual(
            wl.run_dir(LITERAL_ROOT, "phase-01", "run-001"),
            Path("/reviews/rev-a/runs/phase-01/run-001"),
        )
        self.assertEqual(
            wl.run_outputs_dir(LITERAL_ROOT, "phase-01", "run-001"),
            Path("/reviews/rev-a/runs/phase-01/run-001/outputs"),
        )
        self.assertEqual(
            wl.inputs_manifest_path(LITERAL_ROOT, "phase-01", "run-001"),
            Path("/reviews/rev-a/runs/phase-01/run-001/inputs_manifest.json"),
        )
        self.assertEqual(
            wl.run_manifest_path(LITERAL_ROOT, "phase-01", "run-001"),
            Path("/reviews/rev-a/runs/phase-01/run-001/run_manifest.json"),
        )
        self.assertEqual(
            wl.failure_manifest_path(LITERAL_ROOT, "phase-01", "run-001"),
            Path("/reviews/rev-a/runs/phase-01/run-001/failure_manifest.json"),
        )

    def test_handoffs_live_outside_the_producer_run(self) -> None:
        handoff = wl.handoff_dir(
            LITERAL_ROOT, "run-001", "systematic-review-protocol", "handoff-001"
        )
        self.assertEqual(
            handoff,
            Path(
                "/reviews/rev-a/handoffs/run-001/"
                "systematic-review-protocol/handoff-001"
            ),
        )
        self.assertEqual(
            wl.handoff_manifest_path(
                LITERAL_ROOT,
                "run-001",
                "systematic-review-protocol",
                "handoff-001",
            ),
            handoff / "handoff_manifest.json",
        )
        # A producer run never contains the handoff it publishes.
        self.assertNotIn(
            str(wl.run_dir(LITERAL_ROOT, "phase-01", "run-001")), str(handoff)
        )

    def test_identifiers_must_be_one_safe_segment(self) -> None:
        for bad in ("", "  ", "..", ".", "a/b", "../x", "-leading", "x y", None):
            with self.assertRaises(wl.WorkspaceLifecycleError):
                wl.validate_identifier(bad, "phase_id")
        self.assertEqual(wl.validate_identifier("phase-01", "phase_id"), "phase-01")
        self.assertEqual(
            wl.validate_identifier("systematic-review-protocol", "skill_id"),
            "systematic-review-protocol",
        )

    def test_timestamps_and_sequences_are_validated(self) -> None:
        self.assertEqual(
            wl.validate_timestamp("2026-07-31T02:51:36Z", "created_at"),
            "2026-07-31T02:51:36Z",
        )
        for bad in ("2026-07-31", "2026-07-31T02:51:36+00:00", "now", ""):
            with self.assertRaises(wl.WorkspaceLifecycleError):
                wl.validate_timestamp(bad, "created_at")
        for bad in (0, -1, True, "1", 1.0):
            with self.assertRaises(wl.WorkspaceLifecycleError):
                wl.validate_sequence_number(bad, "start_ledger_sequence")
        self.assertEqual(wl.validate_sequence_number(1, "seq"), 1)
        self.assertRegex(wl.utc_timestamp(), r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class ContainmentTests(unittest.TestCase):
    """No path escapes its root, and no owned component may be a symlink."""

    def setUp(self) -> None:
        self.root = tempfile.mkdtemp()
        self.outside = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.addCleanup(shutil.rmtree, self.outside, True)

    def test_relative_root_is_refused(self) -> None:
        with self.assertRaises(wl.WorkspaceLifecycleError):
            wl.assert_within_root("relative/root", "runs")

    def test_upward_traversal_is_refused(self) -> None:
        for bad in ("../escape", "runs/../../escape", "./../x"):
            with self.assertRaises(wl.WorkspaceLifecycleError):
                wl.assert_within_root(self.root, bad)

    def test_absolute_path_outside_root_is_refused(self) -> None:
        with self.assertRaises(wl.WorkspaceLifecycleError) as caught:
            wl.assert_within_root(self.root, str(Path(self.outside) / "x"))
        self.assertIn("escapes declared root", str(caught.exception))

    def test_symlinked_component_below_root_is_refused(self) -> None:
        (Path(self.root) / "runs").mkdir()
        os.symlink(self.outside, str(Path(self.root) / "runs" / "phase-01"))
        with self.assertRaises(wl.WorkspaceLifecycleError) as caught:
            wl.assert_within_root(self.root, "runs/phase-01/run-001")
        self.assertIn("symlink", str(caught.exception))

    def test_a_symlinked_root_ancestor_stays_usable(self) -> None:
        # /tmp is itself a symlink on macOS; only components the workspace
        # owns are refused.
        derived = wl.run_dir(self.root, "phase-01", "run-001")
        self.assertTrue(str(derived).endswith("runs/phase-01/run-001"))

    def test_producer_may_not_write_into_another_phase(self) -> None:
        allowed = wl.assert_producer_scope(
            self.root,
            phase_id="phase-01",
            run_id="run-001",
            path="runs/phase-01/run-001/outputs/eligibility.json",
        )
        self.assertTrue(str(allowed).endswith("outputs/eligibility.json"))
        for forbidden in (
            "runs/phase-10/run-001/outputs",
            "runs/phase-01/run-002/outputs",
            "handoffs/run-001/systematic-review-protocol/handoff-001",
            "state/review_state.json",
        ):
            with self.assertRaises(wl.WorkspaceLifecycleError) as caught:
                wl.assert_producer_scope(
                    self.root,
                    phase_id="phase-01",
                    run_id="run-001",
                    path=forbidden,
                )
            self.assertIn("may not write outside its own directory", str(caught.exception))


class FailClosedWriteTests(unittest.TestCase):
    """New paths are created once, never reused, never overwritten."""

    def setUp(self) -> None:
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)

    def test_canonical_bytes_are_the_file_bytes(self) -> None:
        value = {"b": 1, "a": "é"}
        self.assertEqual(wl.canonical_bytes(value), b'{"a":"\xc3\xa9","b":1}')
        target = wl.write_new_json(self.root, "record.json", value)
        written = target.read_bytes()
        self.assertEqual(written, wl.canonical_bytes(value))
        self.assertEqual(
            hashlib.sha256(written).hexdigest(), wl.canonical_sha256(value)
        )

    def test_a_record_is_never_overwritten(self) -> None:
        wl.write_new_json(self.root, "record.json", {"a": 1})
        with self.assertRaises(wl.WorkspaceLifecycleError) as caught:
            wl.write_new_json(self.root, "record.json", {"a": 2})
        self.assertIn("never overwritten", str(caught.exception))
        self.assertEqual(
            (Path(self.root) / "record.json").read_bytes(), b'{"a":1}'
        )

    def test_a_missing_parent_is_not_conjured(self) -> None:
        with self.assertRaises(wl.WorkspaceLifecycleError) as caught:
            wl.write_new_json(self.root, "runs/phase-01/run-001/x.json", {"a": 1})
        self.assertIn("parent directory does not exist", str(caught.exception))
        self.assertFalse((Path(self.root) / "runs").exists())

    def test_a_destination_directory_is_never_reused(self) -> None:
        created = wl.create_new_directory(self.root, "runs/phase-01/run-001")
        self.assertTrue(created.is_dir())
        with self.assertRaises(wl.WorkspaceLifecycleError) as caught:
            wl.create_new_directory(self.root, "runs/phase-01/run-001")
        self.assertIn("never reused", str(caught.exception))

    def test_assert_unregistered_refuses_an_occupied_destination(self) -> None:
        wl.assert_unregistered(self.root, "runs/phase-01")
        wl.create_new_directory(self.root, "runs/phase-01")
        with self.assertRaises(wl.WorkspaceLifecycleError):
            wl.assert_unregistered(self.root, "runs/phase-01")

    def test_records_are_not_read_through_a_symlink(self) -> None:
        real = wl.write_new_json(self.root, "record.json", {"a": 1})
        link = Path(self.root) / "alias.json"
        os.symlink(str(real), str(link))
        with self.assertRaises(wl.WorkspaceLifecycleError):
            wl.read_json(str(link))
        self.assertEqual(wl.read_json(str(real)), {"a": 1})


class RecordFactory:
    """Valid records, so each test can invalidate exactly one thing."""

    @staticmethod
    def review() -> dict:
        return {
            "schema_version": wl.SCHEMA_VERSION,
            "record_type": wl.RECORD_REVIEW,
            "review_id": "review-001",
            "tool_version": wl.TOOL_VERSION,
            "created_at": "2026-07-31T02:51:36Z",
            "timestamp_assurance": wl.TIMESTAMP_ASSURANCE,
        }

    @staticmethod
    def inputs(source: dict) -> dict:
        return {
            "schema_version": wl.SCHEMA_VERSION,
            "record_type": wl.RECORD_INPUTS,
            "review_id": "review-001",
            "phase_id": "phase-01",
            "skill_id": "systematic-review",
            "run_id": "run-001",
            "inputs": [source],
            "parent_run_ids": [],
            "consumed_handoff_ids": [],
            "start_ledger_sequence": 2,
            "created_at": "2026-07-31T02:51:36Z",
            "timestamp_assurance": wl.TIMESTAMP_ASSURANCE,
        }

    @staticmethod
    def run(inputs_ref: dict, output: dict) -> dict:
        return {
            "schema_version": wl.SCHEMA_VERSION,
            "record_type": wl.RECORD_RUN,
            "review_id": "review-001",
            "phase_id": "phase-01",
            "skill_id": "systematic-review",
            "run_id": "run-001",
            "status": wl.STATUS_COMPLETED,
            "inputs_manifest": inputs_ref,
            "outputs": [output],
            "parent_run_ids": [],
            "consumed_handoff_ids": [],
            "downstream_consumers": ["systematic-review-protocol"],
            "start_ledger_sequence": 2,
            "terminal_ledger_sequence": 3,
            "created_at": "2026-07-31T02:51:36Z",
            "completed_at": "2026-07-31T02:52:41Z",
            "timestamp_assurance": wl.TIMESTAMP_ASSURANCE,
            "tool_version": wl.TOOL_VERSION,
        }

    @staticmethod
    def failure(inputs_ref: dict) -> dict:
        return {
            "schema_version": wl.SCHEMA_VERSION,
            "record_type": wl.RECORD_FAILURE,
            "review_id": "review-001",
            "phase_id": "phase-01",
            "skill_id": "systematic-review",
            "run_id": "run-001",
            "status": wl.STATUS_FAILED,
            "reason_code": "INPUT_VERIFICATION_FAILED",
            "message": "an upstream artifact changed after it was referenced",
            "inputs_manifest": inputs_ref,
            "start_ledger_sequence": 2,
            "terminal_ledger_sequence": 3,
            "created_at": "2026-07-31T02:51:36Z",
            "failed_at": "2026-07-31T02:52:41Z",
            "timestamp_assurance": wl.TIMESTAMP_ASSURANCE,
            "tool_version": wl.TOOL_VERSION,
        }

    @staticmethod
    def handoff(producer_manifest: dict, artifact: dict) -> dict:
        return {
            "schema_version": wl.SCHEMA_VERSION,
            "record_type": wl.RECORD_HANDOFF,
            "review_id": "review-001",
            "handoff_id": "handoff-001",
            "producer_phase_id": "phase-01",
            "producer_skill_id": "systematic-review",
            "producer_run_id": "run-001",
            "producer_run_manifest": producer_manifest,
            "consumer_skill": "systematic-review-protocol",
            "artifacts": [artifact],
            "frozen_export": None,
            "created_ledger_sequence": 4,
            "created_at": "2026-07-31T02:53:00Z",
            "timestamp_assurance": wl.TIMESTAMP_ASSURANCE,
            "tool_version": wl.TOOL_VERSION,
        }

    @staticmethod
    def state() -> dict:
        return {
            "schema_version": wl.SCHEMA_VERSION,
            "record_type": wl.RECORD_STATE,
            "review_id": "review-001",
            "generated_at": "2026-07-31T02:54:00Z",
            "generated_from_ledger_head": "a" * 64,
            "generated_from_ledger_entries": 4,
            "phases": {
                "phase-01": {
                    "status": wl.STATUS_COMPLETED,
                    "required_inputs_available": True,
                    "runs": ["run-001"],
                },
                "phase-10": {
                    "status": "NOT_STARTED",
                    "required_inputs_available": True,
                    "runs": [],
                },
            },
            "timestamp_assurance": wl.TIMESTAMP_ASSURANCE,
            "tool_version": wl.TOOL_VERSION,
            "derivation": "generated from the ledger and terminal manifests",
        }


class SchemaTests(unittest.TestCase):
    """Every record is validated against a strict whitelist."""

    def setUp(self) -> None:
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        source = Path(self.root) / "protocol.json"
        source.write_text('{"protocol":true}', encoding="utf-8")
        self.source_ref = ref(source, "approved-protocol")
        inputs_file = Path(self.root) / "inputs_manifest.json"
        inputs_file.write_text('{"inputs":true}', encoding="utf-8")
        self.inputs_ref = ref(inputs_file, "inputs-manifest")
        output = Path(self.root) / "eligibility.json"
        output.write_text('{"eligibility":true}', encoding="utf-8")
        self.output_ref = ref(output, "approved-eligibility-contract")

    def test_valid_records_validate(self) -> None:
        self.assertEqual(
            wl.validate_review_manifest(RecordFactory.review())["review_id"],
            "review-001",
        )
        wl.validate_inputs_manifest(RecordFactory.inputs(self.source_ref))
        wl.validate_run_manifest(
            RecordFactory.run(self.inputs_ref, self.output_ref)
        )
        wl.validate_failure_manifest(RecordFactory.failure(self.inputs_ref))
        wl.validate_handoff_manifest(
            RecordFactory.handoff(self.inputs_ref, self.output_ref)
        )
        wl.validate_review_state(RecordFactory.state())

    def test_validate_record_dispatches_and_refuses_unknown_types(self) -> None:
        self.assertEqual(
            wl.validate_record(RecordFactory.review())["record_type"],
            wl.RECORD_REVIEW,
        )
        with self.assertRaises(wl.WorkspaceLifecycleError):
            wl.validate_record({"record_type": "SOMETHING_ELSE"})
        with self.assertRaises(wl.WorkspaceLifecycleError):
            wl.validate_record(["not", "an", "object"])

    def test_schema_version_and_record_type_are_enforced(self) -> None:
        record = RecordFactory.review()
        record["schema_version"] = "1.0"
        with self.assertRaises(wl.WorkspaceLifecycleError):
            wl.validate_review_manifest(record)
        record = RecordFactory.review()
        record["record_type"] = wl.RECORD_RUN
        with self.assertRaises(wl.WorkspaceLifecycleError):
            wl.validate_review_manifest(record)

    def test_unknown_and_missing_fields_are_refused(self) -> None:
        record = RecordFactory.review()
        record["extra"] = True
        with self.assertRaises(wl.WorkspaceLifecycleError) as caught:
            wl.validate_review_manifest(record)
        self.assertIn("unknown fields", str(caught.exception))
        record = RecordFactory.review()
        del record["created_at"]
        with self.assertRaises(wl.WorkspaceLifecycleError) as caught:
            wl.validate_review_manifest(record)
        self.assertIn("missing fields", str(caught.exception))

    def test_a_recorded_timestamp_must_declare_it_is_an_assertion(self) -> None:
        record = RecordFactory.review()
        record["timestamp_assurance"] = "VERIFIED"
        with self.assertRaises(wl.WorkspaceLifecycleError) as caught:
            wl.validate_review_manifest(record)
        self.assertIn("assertion", str(caught.exception))

    def test_terminal_manifests_carry_mutually_exclusive_statuses(self) -> None:
        record = RecordFactory.run(self.inputs_ref, self.output_ref)
        record["status"] = wl.STATUS_FAILED
        with self.assertRaises(wl.WorkspaceLifecycleError) as caught:
            wl.validate_run_manifest(record)
        self.assertIn("declares success only", str(caught.exception))

        record = RecordFactory.run(self.inputs_ref, self.output_ref)
        record["status"] = wl.STATUS_LOCKED
        self.assertEqual(
            wl.validate_run_manifest(record)["status"], wl.STATUS_LOCKED
        )

        failure = RecordFactory.failure(self.inputs_ref)
        failure["status"] = wl.STATUS_COMPLETED
        with self.assertRaises(wl.WorkspaceLifecycleError):
            wl.validate_failure_manifest(failure)

    def test_ledger_sequences_must_advance(self) -> None:
        record = RecordFactory.run(self.inputs_ref, self.output_ref)
        record["terminal_ledger_sequence"] = 2
        with self.assertRaises(wl.WorkspaceLifecycleError) as caught:
            wl.validate_run_manifest(record)
        self.assertIn("must follow", str(caught.exception))

    def test_a_handoff_never_carries_downstream_status_or_outputs(self) -> None:
        for field, value in (
            ("consumer_status", "COMPLETED"),
            ("downstream_status", "COMPLETED"),
            ("outputs", []),
            ("output_path", "/reviews/rev-a/runs/phase-10/run-001/outputs"),
            ("consumer_run_id", "run-010"),
            ("status", "COMPLETED"),
        ):
            record = RecordFactory.handoff(self.inputs_ref, self.output_ref)
            record[field] = value
            with self.assertRaises(wl.WorkspaceLifecycleError) as caught:
                wl.validate_handoff_manifest(record)
            self.assertIn("never carries downstream status", str(caught.exception))

    def test_a_handoff_may_carry_one_frozen_export(self) -> None:
        record = RecordFactory.handoff(self.inputs_ref, self.output_ref)
        record["frozen_export"] = self.source_ref
        self.assertEqual(
            wl.validate_handoff_manifest(record)["frozen_export"]["role"],
            "approved-protocol",
        )

    def test_state_is_declared_as_a_generated_view(self) -> None:
        record = RecordFactory.state()
        record["phases"]["phase-01"]["status"] = "PROBABLY_DONE"
        with self.assertRaises(wl.WorkspaceLifecycleError):
            wl.validate_review_state(record)
        record = RecordFactory.state()
        record["generated_from_ledger_head"] = "not-a-digest"
        with self.assertRaises(wl.WorkspaceLifecycleError):
            wl.validate_review_state(record)


class DuplicateIdentifierTests(unittest.TestCase):
    """Ambiguous identifiers and roles are refused, never resolved."""

    def setUp(self) -> None:
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        first = Path(self.root) / "a.json"
        first.write_text('{"a":1}', encoding="utf-8")
        second = Path(self.root) / "b.json"
        second.write_text('{"b":2}', encoding="utf-8")
        self.first = first
        self.second = second

    def test_duplicate_artifact_roles_are_refused(self) -> None:
        refs = [ref(self.first, "dataset"), ref(self.second, "dataset")]
        with self.assertRaises(wl.WorkspaceLifecycleError) as caught:
            wl.validate_artifact_refs(refs, "outputs")
        self.assertIn("duplicate identifiers", str(caught.exception))

    def test_roles_differing_only_in_case_are_refused(self) -> None:
        refs = [ref(self.first, "Dataset"), ref(self.second, "dataset")]
        with self.assertRaises(wl.WorkspaceLifecycleError):
            wl.validate_artifact_refs(refs, "outputs")

    def test_distinct_roles_are_accepted(self) -> None:
        refs = [ref(self.first, "dataset"), ref(self.second, "codebook")]
        self.assertEqual(len(wl.validate_artifact_refs(refs, "outputs")), 2)

    def test_duplicate_run_and_handoff_identifiers_are_refused(self) -> None:
        with self.assertRaises(wl.WorkspaceLifecycleError):
            wl.validate_unique_identifiers(["run-001", "run-001"], "parent_run_ids")
        with self.assertRaises(wl.WorkspaceLifecycleError):
            wl.validate_unique_identifiers(
                ["handoff-001", "HANDOFF-001"], "consumed_handoff_ids"
            )
        self.assertEqual(
            wl.validate_unique_identifiers(["run-001", "run-002"], "parent_run_ids"),
            ["run-001", "run-002"],
        )

    def test_duplicate_parents_are_refused_inside_a_manifest(self) -> None:
        record = RecordFactory.inputs(ref(self.first, "source"))
        record["parent_run_ids"] = ["run-000", "run-000"]
        with self.assertRaises(wl.WorkspaceLifecycleError):
            wl.validate_inputs_manifest(record)

    def test_a_malformed_reference_is_refused(self) -> None:
        good = ref(self.first, "dataset")
        broken = dict(good)
        del broken["bytes"]
        with self.assertRaises(wl.WorkspaceLifecycleError):
            wl.validate_artifact_refs([broken], "outputs")
        broken = dict(good, sha256="NOTAHASH")
        with self.assertRaises(wl.WorkspaceLifecycleError):
            wl.validate_artifact_refs([broken], "outputs")
        broken = dict(good, role="not a role")
        with self.assertRaises(wl.WorkspaceLifecycleError):
            wl.validate_artifact_refs([broken], "outputs")
        with self.assertRaises(wl.WorkspaceLifecycleError):
            wl.validate_artifact_refs([], "outputs")


class VerificationTests(unittest.TestCase):
    """Sources are recomputed; a directory never asserts a status."""

    def setUp(self) -> None:
        self.root = tempfile.mkdtemp()
        self.outside = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.addCleanup(shutil.rmtree, self.outside, True)
        self.run = wl.create_new_directory(self.root, "runs/phase-01/run-001")
        self.outputs = wl.create_new_directory(
            self.root, "runs/phase-01/run-001/outputs"
        )
        self.artifact = self.outputs / "eligibility.json"
        self.artifact.write_text('{"eligibility":true}', encoding="utf-8")
        self.artifact_ref = ref(self.artifact, "approved-eligibility-contract")
        self.inputs_file = self.run / "inputs_manifest.json"
        self.inputs_file.write_text('{"inputs":true}', encoding="utf-8")
        self.inputs_ref = ref(self.inputs_file, "inputs-manifest")
        # Reading a run's *status* reconciles the directory with the ledger, so
        # those tests need a real review rather than a hand-built directory.
        self.review = str(Path(self.root) / "review")
        wl.initialize_review(self.review, review_id="review-001")

    def real_run(self, run_id: str = "run-01-001") -> dict:
        started = wl.start_run(
            self.review,
            phase_id="phase-01",
            skill_id="systematic-review",
            run_id=run_id,
            inputs=[],
        )
        artifact = Path(started["outputs_dir"]) / "eligibility.json"
        artifact.write_text('{"eligibility":true}', encoding="utf-8")
        started["output_ref"] = ref(artifact, "approved-eligibility-contract")
        return started

    def test_a_changed_source_is_refused(self) -> None:
        wl.verify_artifact_refs([self.artifact_ref], root=self.root)
        self.artifact.write_text('{"eligibility":false}', encoding="utf-8")
        with self.assertRaises(wl.WorkspaceLifecycleError) as caught:
            wl.verify_artifact_refs([self.artifact_ref], root=self.root)
        self.assertIn("hash mismatch", str(caught.exception))

    def test_a_missing_source_is_refused(self) -> None:
        self.artifact.unlink()
        with self.assertRaises(wl.WorkspaceLifecycleError):
            wl.verify_artifact_refs([self.artifact_ref], root=self.root)

    def test_a_symlinked_source_is_refused(self) -> None:
        real = Path(self.outside) / "real.json"
        real.write_text('{"real":true}', encoding="utf-8")
        link = self.outputs / "alias.json"
        os.symlink(str(real), str(link))
        aliased = dict(ref(real, "aliased"), path=str(link))
        with self.assertRaises(wl.WorkspaceLifecycleError) as caught:
            wl.verify_artifact_refs([aliased], root=self.root)
        self.assertIn("symlink", str(caught.exception))

    def test_a_source_outside_the_declared_root_is_refused(self) -> None:
        stray = Path(self.outside) / "stray.json"
        stray.write_text('{"stray":true}', encoding="utf-8")
        with self.assertRaises(wl.WorkspaceLifecycleError) as caught:
            wl.verify_artifact_refs([ref(stray, "stray")], root=self.root)
        self.assertIn("escapes declared root", str(caught.exception))
        # Legacy artifacts stay where their phase left them, so an explicit
        # unrooted verification is still available.
        self.assertTrue(
            wl.verify_artifact_refs([ref(stray, "stray")])[0]["verified"]
        )

    def test_outputs_must_be_owned_by_their_run(self) -> None:
        wl.assert_outputs_owned(
            self.root,
            phase_id="phase-01",
            run_id="run-001",
            outputs=[self.artifact_ref],
        )
        foreign = dict(
            self.artifact_ref,
            path=str(Path(self.root) / "runs/phase-10/run-001/outputs/x.json"),
        )
        with self.assertRaises(wl.WorkspaceLifecycleError) as caught:
            wl.assert_outputs_owned(
                self.root,
                phase_id="phase-01",
                run_id="run-001",
                outputs=[foreign],
            )
        self.assertIn("not owned by run", str(caught.exception))

    def test_an_empty_directory_is_never_complete(self) -> None:
        layout = wl.assert_run_directory_layout(str(self.run))
        self.assertFalse(layout["terminal"])
        self.assertEqual(layout["status"], wl.STATUS_STARTED)
        started = self.real_run()
        with self.assertRaises(wl.WorkspaceLifecycleError) as caught:
            wl.read_terminal_manifest(started["run_dir"])
        self.assertIn("nonterminal", str(caught.exception))

    def test_a_run_directory_holds_only_what_it_owns(self) -> None:
        (self.run / "phase-10").mkdir()
        with self.assertRaises(wl.WorkspaceLifecycleError) as caught:
            wl.assert_run_directory_layout(str(self.run))
        self.assertIn("does not own", str(caught.exception))

    def test_both_terminal_manifests_at_once_are_refused(self) -> None:
        wl.write_new_json(
            self.root,
            "runs/phase-01/run-001/run_manifest.json",
            RecordFactory.run(self.inputs_ref, self.artifact_ref),
        )
        wl.write_new_json(
            self.root,
            "runs/phase-01/run-001/failure_manifest.json",
            RecordFactory.failure(self.inputs_ref),
        )
        with self.assertRaises(wl.WorkspaceLifecycleError) as caught:
            wl.assert_run_directory_layout(str(self.run))
        self.assertIn("mutually exclusive", str(caught.exception))

    def test_a_terminal_manifest_declares_completion(self) -> None:
        started = self.real_run()
        wl.complete_run(started["run_dir"], outputs=[started["output_ref"]])
        layout = wl.assert_run_directory_layout(started["run_dir"])
        self.assertTrue(layout["terminal"])
        self.assertEqual(layout["status"], wl.STATUS_COMPLETED)
        manifest = wl.assert_successful_producer(started["run_dir"])
        self.assertEqual(manifest["run_id"], "run-01-001")

    def test_a_failed_producer_may_not_feed_a_consumer(self) -> None:
        started = self.real_run()
        wl.fail_run(
            started["run_dir"], reason_code="PILOT_REJECTED", message="rejected"
        )
        with self.assertRaises(wl.WorkspaceLifecycleError) as caught:
            wl.assert_successful_producer(started["run_dir"])
        self.assertIn("did not succeed", str(caught.exception))

    def test_a_symlinked_run_directory_is_refused(self) -> None:
        link = Path(self.root) / "runs" / "phase-02"
        os.symlink(self.outside, str(link))
        with self.assertRaises(wl.WorkspaceLifecycleError) as caught:
            wl.assert_run_directory_layout(str(link))
        self.assertIn("symlink", str(caught.exception))

    def test_a_handoff_is_addressed_to_exactly_one_consumer(self) -> None:
        manifest = RecordFactory.handoff(self.inputs_ref, self.artifact_ref)
        self.assertEqual(
            wl.assert_consumer_match(manifest, "systematic-review-protocol"),
            "systematic-review-protocol",
        )
        with self.assertRaises(wl.WorkspaceLifecycleError) as caught:
            wl.assert_consumer_match(manifest, "systematic-review-search-design")
        self.assertIn("addressed to", str(caught.exception))


class LockedSignatureTests(unittest.TestCase):
    """The eight locked signatures are committed exactly as contracted."""

    EXPECTED = {
        "initialize_review": "(root: str, *, review_id: str) -> dict",
        "start_run": (
            "(root: str, *, phase_id: str, skill_id: str, run_id: str, "
            "inputs: list[dict], parent_run_ids: list[str] = ()) -> dict"
        ),
        "complete_run": (
            "(run_dir: str, *, outputs: list[dict], status: str = 'COMPLETED', "
            "downstream_consumers: list[str] = ()) -> dict"
        ),
        "fail_run": "(run_dir: str, *, reason_code: str, message: str) -> dict",
        "create_handoff": (
            "(root: str, *, producer_run_id: str, consumer_skill: str, "
            "handoff_id: str, artifacts: list[dict]) -> dict"
        ),
        "verify_handoff": "(path: str, *, consumer_skill: str) -> dict",
        "register_legacy_run": (
            "(root: str, *, phase_id: str, skill_id: str, run_id: str, "
            "artifacts: list[dict], legacy_status: str) -> dict"
        ),
        "generate_review_state": "(root: str) -> dict",
    }

    @staticmethod
    def rendered(name: str) -> str:
        """Render a signature the way the contract writes it.

        ``from __future__ import annotations`` keeps annotations as strings, so
        ``inspect`` quotes them. Unquoting only the annotations leaves string
        *defaults* such as ``'COMPLETED'`` quoted, which is what the contract
        shows.
        """
        text = str(inspect.signature(getattr(wl, name)))
        text = re.sub(r": '([^']*)'", r": \1", text)
        return re.sub(r"-> '([^']*)'", r"-> \1", text)

    def test_signatures_match_the_contract(self) -> None:
        for name, expected in self.EXPECTED.items():
            self.assertEqual(self.rendered(name), expected, f"{name} drifted")

    def test_no_locked_signature_is_still_a_stub(self) -> None:
        """Briefs 17-19 are complete: all eight are implemented."""
        self.assertFalse(
            hasattr(wl, "_stub"), "the stub helper should be gone once unused"
        )
        for name in self.EXPECTED:
            source = inspect.getsource(getattr(wl, name))
            self.assertNotIn("_stub(", source, f"{name} is still a stub")
            self.assertNotIn(
                "NotImplementedError", source, f"{name} is still unimplemented"
            )


class CliHarness(unittest.TestCase):
    """A fresh initialized review plus CLI helpers, shared by the suites."""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.workspace = str(Path(self.tmp) / "review")
        evidence = Path(self.tmp) / "evidence"
        evidence.mkdir()
        self.protocol = evidence / "protocol.json"
        self.protocol.write_text('{"protocol":true}', encoding="utf-8")
        self.cli("init-review", "--root", self.workspace, "--review-id", "review-001")

    def cli(self, *argv: str) -> dict:
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = wl.main(list(argv))
        self.assertEqual(code, 0, f"{argv} failed: {stderr.getvalue()}")
        return json.loads(stdout.getvalue())

    def refused(self, *argv: str) -> str:
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = wl.main(list(argv))
        self.assertEqual(code, 2, f"{argv} unexpectedly succeeded")
        return stderr.getvalue()

    def ledger_lines(self) -> int:
        path = Path(self.workspace) / "ledger" / "execution.jsonl"
        return len([line for line in path.read_text().splitlines() if line.strip()])

    def start(self, phase: str = "phase-01", run: str = "run-001") -> dict:
        return self.cli(
            "start-run",
            "--root", self.workspace,
            "--phase-id", phase,
            "--skill-id", "systematic-review",
            "--run-id", run,
            "--input", f"approved-protocol={self.protocol}",
        )

    def produce(self, started: dict, name: str = "eligibility.json") -> Path:
        artifact = Path(started["outputs_dir"]) / name
        artifact.write_text(f'{{"artifact":"{name}"}}', encoding="utf-8")
        return artifact

    def phase_directories(self) -> list:
        runs = Path(self.workspace) / "runs"
        return sorted(p.name for p in runs.iterdir()) if runs.is_dir() else []


class LifecycleCliTests(CliHarness):
    """End-to-end CLI behavior: nothing is inferred from a directory."""

    def test_a_run_reaches_a_terminal_manifest(self) -> None:
        started = self.start()
        artifact = self.produce(started)
        completed = self.cli(
            "complete-run",
            "--run-dir", started["run_dir"],
            "--output", f"approved-eligibility-contract={artifact}",
            "--consumer", "systematic-review-protocol",
        )
        self.assertEqual(completed["status"], wl.STATUS_COMPLETED)
        self.assertTrue(Path(completed["run_manifest"]).is_file())
        inspected = self.cli("inspect-run", "--run-dir", started["run_dir"])
        self.assertEqual(inspected["status"], wl.STATUS_COMPLETED)
        self.assertEqual(
            inspected["output_roles"], ["approved-eligibility-contract"]
        )
        state = self.cli("generate-state", "--root", self.workspace)
        self.assertEqual(
            state["phases"]["phase-01"],
            {
                "status": wl.STATUS_COMPLETED,
                "required_inputs_available": True,
                "runs": ["run-001"],
            },
        )

    def test_a_producer_creates_only_its_own_run_directory(self) -> None:
        started = self.start()
        run = Path(started["run_dir"])
        self.assertEqual(
            sorted(entry.name for entry in run.iterdir()),
            ["inputs_manifest.json", "outputs"],
        )
        runs_root = Path(self.workspace) / "runs"
        self.assertEqual([p.name for p in runs_root.iterdir()], ["phase-01"])
        self.assertFalse((Path(self.workspace) / "handoffs").exists())

    def test_an_interrupted_run_stays_nonterminal(self) -> None:
        started = self.start()
        self.assertEqual(started["status"], wl.STATUS_STARTED)
        self.assertFalse((Path(started["run_dir"]) / "run_manifest.json").exists())
        inspected = self.cli("inspect-run", "--run-dir", started["run_dir"])
        self.assertEqual(inspected["status"], wl.STATUS_STARTED)
        self.assertFalse(inspected["terminal"])
        state = self.cli("generate-state", "--root", self.workspace)
        self.assertEqual(state["phases"]["phase-01"]["status"], wl.STATUS_STARTED)

    def test_an_empty_folder_is_never_completion(self) -> None:
        stray = Path(self.workspace) / "runs" / "phase-09" / "run-999"
        stray.mkdir(parents=True)
        message = self.refused("inspect-run", "--run-dir", str(stray))
        self.assertIn("no inputs manifest", message)
        message = self.refused("generate-state", "--root", self.workspace)
        self.assertIn("no ledger entry", message)
        self.assertFalse(
            (Path(self.workspace) / "state" / "review_state.json").exists()
        )

    def test_explicit_failure_is_terminal_and_keeps_its_evidence(self) -> None:
        started = self.start()
        failed = self.cli(
            "fail-run",
            "--run-dir", started["run_dir"],
            "--reason-code", "INPUT_VERIFICATION_FAILED",
            "--message", "an upstream export was withdrawn",
        )
        self.assertEqual(failed["status"], wl.STATUS_FAILED)
        self.assertTrue(Path(failed["failure_manifest"]).is_file())
        self.assertTrue(
            (Path(started["run_dir"]) / "inputs_manifest.json").is_file()
        )
        artifact = self.produce(started)
        message = self.refused(
            "complete-run",
            "--run-dir", started["run_dir"],
            "--output", f"approved-eligibility-contract={artifact}",
        )
        self.assertIn("already carries a terminal manifest", message)
        state = self.cli("generate-state", "--root", self.workspace)
        self.assertEqual(state["phases"]["phase-01"]["status"], wl.STATUS_FAILED)

    def test_a_terminal_manifest_is_written_exactly_once(self) -> None:
        started = self.start()
        artifact = self.produce(started)
        self.cli(
            "complete-run",
            "--run-dir", started["run_dir"],
            "--output", f"approved-eligibility-contract={artifact}",
        )
        before = Path(started["run_dir"], "run_manifest.json").read_bytes()
        message = self.refused(
            "complete-run",
            "--run-dir", started["run_dir"],
            "--output", f"approved-eligibility-contract={artifact}",
        )
        self.assertIn("a correction is a new run", message)
        self.assertEqual(
            Path(started["run_dir"], "run_manifest.json").read_bytes(), before
        )

    def test_a_mutated_output_is_caught_after_completion(self) -> None:
        started = self.start()
        artifact = self.produce(started)
        self.cli(
            "complete-run",
            "--run-dir", started["run_dir"],
            "--output", f"approved-eligibility-contract={artifact}",
        )
        self.cli("generate-state", "--root", self.workspace)
        artifact.write_text('{"eligibility":"tampered"}', encoding="utf-8")
        self.assertIn(
            "hash mismatch",
            self.refused("inspect-run", "--run-dir", started["run_dir"]),
        )
        self.assertIn(
            "hash mismatch",
            self.refused("generate-state", "--root", self.workspace),
        )

    def test_completion_refuses_an_output_it_does_not_own(self) -> None:
        started = self.start()
        outside = Path(self.tmp) / "evidence" / "stray.json"
        outside.write_text('{"stray":true}', encoding="utf-8")
        self.assertIn(
            "escapes declared root",
            self.refused(
                "complete-run",
                "--run-dir", started["run_dir"],
                "--output", f"stray-output={outside}",
            ),
        )

        # Inside the review, but produced by a different run.
        neighbour = self.start(phase="phase-02", run="run-002")
        borrowed = self.produce(neighbour, "neighbour.json")
        self.assertIn(
            "not owned by run",
            self.refused(
                "complete-run",
                "--run-dir", started["run_dir"],
                "--output", f"borrowed-output={borrowed}",
            ),
        )
        self.assertFalse((Path(started["run_dir"]) / "run_manifest.json").exists())

    def test_start_run_verifies_inputs_before_creating_anything(self) -> None:
        stale = Path(self.tmp) / "evidence" / "stale.json"
        stale.write_text('{"v":1}', encoding="utf-8")
        refs = [artifact_ref.make_artifact_ref(str(stale), "stale-input", "1.0", "X")]
        stale.write_text('{"v":2}', encoding="utf-8")
        refs_file = Path(self.tmp) / "refs.json"
        refs_file.write_text(json.dumps(refs), encoding="utf-8")
        before = self.ledger_lines()
        message = self.refused(
            "start-run",
            "--root", self.workspace,
            "--phase-id", "phase-02",
            "--skill-id", "systematic-review-protocol",
            "--run-id", "run-001",
            "--inputs-file", str(refs_file),
        )
        self.assertIn("hash mismatch", message)
        self.assertFalse((Path(self.workspace) / "runs" / "phase-02").exists())
        self.assertEqual(self.ledger_lines(), before)

    def test_a_run_id_is_never_reused(self) -> None:
        self.start()
        before = self.ledger_lines()
        message = self.refused(
            "start-run",
            "--root", self.workspace,
            "--phase-id", "phase-01",
            "--skill-id", "systematic-review",
            "--run-id", "run-001",
            "--input", f"approved-protocol={self.protocol}",
        )
        self.assertIn("never reused", message)
        # A refused start records nothing: a spurious RUN_STARTED would leave
        # the ledger claiming a run that does not exist.
        self.assertEqual(self.ledger_lines(), before)

    def test_completion_refuses_a_stale_output_reference(self) -> None:
        started = self.start()
        artifact = self.produce(started)
        refs = [
            artifact_ref.make_artifact_ref(
                str(artifact), "approved-eligibility-contract", "1.0", "X"
            )
        ]
        artifact.write_text('{"eligibility":"changed"}', encoding="utf-8")
        refs_file = Path(self.tmp) / "outputs.json"
        refs_file.write_text(json.dumps(refs), encoding="utf-8")
        message = self.refused(
            "complete-run",
            "--run-dir", started["run_dir"],
            "--outputs-file", str(refs_file),
        )
        self.assertIn("hash mismatch", message)
        self.assertFalse((Path(started["run_dir"]) / "run_manifest.json").exists())

    def test_completion_refuses_an_input_that_changed_mid_run(self) -> None:
        started = self.start()
        artifact = self.produce(started)
        self.protocol.write_text('{"protocol":"amended"}', encoding="utf-8")
        message = self.refused(
            "complete-run",
            "--run-dir", started["run_dir"],
            "--output", f"approved-eligibility-contract={artifact}",
        )
        self.assertIn("hash mismatch", message)
        self.assertIn("protocol.json", message)
        self.assertFalse((Path(started["run_dir"]) / "run_manifest.json").exists())

    def test_a_removed_terminal_manifest_conflicts_with_the_ledger(self) -> None:
        started = self.start()
        artifact = self.produce(started)
        self.cli(
            "complete-run",
            "--run-dir", started["run_dir"],
            "--output", f"approved-eligibility-contract={artifact}",
        )
        (Path(started["run_dir"]) / "run_manifest.json").unlink()
        message = self.refused("generate-state", "--root", self.workspace)
        self.assertIn("disagrees with the ledger", message)

    def test_regenerated_state_is_deterministic(self) -> None:
        started = self.start()
        artifact = self.produce(started)
        self.cli(
            "complete-run",
            "--run-dir", started["run_dir"],
            "--output", f"approved-eligibility-contract={artifact}",
        )
        first = self.cli("generate-state", "--root", self.workspace)
        second = self.cli("generate-state", "--root", self.workspace)
        del first["generated_at"], second["generated_at"]
        self.assertEqual(first, second)
        written = (Path(self.workspace) / "state" / "review_state.json").read_bytes()
        self.assertEqual(json.loads(written)["review_id"], "review-001")

    def test_state_is_generated_not_hand_maintained(self) -> None:
        self.start()
        state_file = Path(self.workspace) / "state" / "review_state.json"
        self.cli("generate-state", "--root", self.workspace)
        state_file.write_text('{"phases":{"phase-01":"done"}}', encoding="utf-8")
        regenerated = self.cli("generate-state", "--root", self.workspace)
        self.assertEqual(
            regenerated["phases"]["phase-01"]["status"], wl.STATUS_STARTED
        )
        self.assertEqual(json.loads(state_file.read_text()), regenerated)

    def test_a_tampered_ledger_is_refused(self) -> None:
        self.start()
        ledger = Path(self.workspace) / "ledger" / "execution.jsonl"
        with ledger.open("a", encoding="utf-8") as stream:
            stream.write('{"forged": true}\n')
        self.assertIn(
            "ledger is not intact",
            self.refused("generate-state", "--root", self.workspace),
        )

    def test_a_review_must_be_initialized_before_a_run(self) -> None:
        elsewhere = str(Path(self.tmp) / "not-a-review")
        self.assertIn(
            "not an initialized review",
            self.refused(
                "start-run",
                "--root", elsewhere,
                "--phase-id", "phase-01",
                "--skill-id", "systematic-review",
                "--run-id", "run-001",
                "--input", f"approved-protocol={self.protocol}",
            ),
        )
        self.assertIn(
            "already exists",
            self.refused(
                "init-review", "--root", self.workspace, "--review-id", "review-002"
            ),
        )

    def test_refusal_exits_nonzero_as_a_real_process(self) -> None:
        module = str(SHARED / "workspace_lifecycle.py")
        missing = str(Path(self.tmp) / "review" / "runs" / "phase-01" / "absent")
        completed = subprocess.run(
            [sys.executable, module, "inspect-run", "--run-dir", missing],
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("workspace-lifecycle error", completed.stderr)
        ok = subprocess.run(
            [sys.executable, module, "generate-state", "--root", self.workspace],
            capture_output=True,
            text=True,
        )
        self.assertEqual(ok.returncode, 0, ok.stderr)


class RevisionElevenTerminalBindingTests(CliHarness):
    """Revision 11: every new terminal assertion has one ledger witness."""

    def ledger_event(self, event_type: str, run_id: str) -> dict:
        entries = [
            json.loads(line)
            for line in (Path(self.workspace) / "ledger" / "execution.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        ]
        return next(
            entry["event"]
            for entry in entries
            if entry["event"].get("event_type") == event_type
            and entry["event"].get("run_id") == run_id
        )

    def test_new_terminal_statuses_and_legacy_registration_are_bound(self) -> None:
        completed = self.start(phase="phase-01", run="run-completed")
        completed_output = self.produce(completed, "completed.json")
        self.cli(
            "complete-run", "--run-dir", completed["run_dir"],
            "--output", f"dataset={completed_output}",
        )
        completed_manifest = json.loads(
            Path(completed["run_dir"], wl.RUN_MANIFEST_NAME).read_text()
        )
        completed_event = self.ledger_event(wl.EVENT_RUN_COMPLETED, "run-completed")
        self.assertTrue(completed_event["terminal_manifest_binding_sha256"])
        self.assertEqual(
            completed_event["terminal_manifest_binding_sha256"],
            wl._terminal_manifest_binding_sha256(completed_manifest),
        )
        self.assertTrue(
            self.cli("inspect-run", "--run-dir", completed["run_dir"])
            ["terminal_manifest_bound"]
        )

        locked = self.start(phase="phase-02", run="run-locked")
        locked_output = self.produce(locked, "locked.json")
        self.cli(
            "complete-run", "--run-dir", locked["run_dir"],
            "--status", "LOCKED", "--output", f"dataset={locked_output}",
        )
        locked_event = self.ledger_event(wl.EVENT_RUN_LOCKED, "run-locked")
        self.assertTrue(locked_event["terminal_manifest_binding_sha256"])
        self.assertTrue(
            self.cli("inspect-run", "--run-dir", locked["run_dir"])
            ["terminal_manifest_bound"]
        )

        failed = self.start(phase="phase-03", run="run-failed")
        self.cli(
            "fail-run", "--run-dir", failed["run_dir"],
            "--reason-code", "UPSTREAM_REJECTED", "--message", "rejected",
        )
        failed_manifest = json.loads(
            Path(failed["run_dir"], wl.FAILURE_MANIFEST_NAME).read_text()
        )
        failed_event = self.ledger_event(wl.EVENT_RUN_FAILED, "run-failed")
        self.assertEqual(
            failed_event["terminal_manifest_binding_sha256"],
            wl._terminal_manifest_binding_sha256(failed_manifest),
        )
        self.assertTrue(
            self.cli("inspect-run", "--run-dir", failed["run_dir"])
            ["terminal_manifest_bound"]
        )

        legacy_source = Path(self.tmp) / "legacy-bound.json"
        legacy_source.write_text('{"legacy":true}', encoding="utf-8")
        legacy = self.cli(
            "register-legacy-run", "--root", self.workspace,
            "--phase-id", "phase-09",
            "--skill-id", "systematic-review-title-abstract-screening",
            "--run-id", "run-legacy-bound", "--legacy-status", "LOCKED",
            "--artifact", f"dataset={legacy_source}",
        )
        legacy_event = self.ledger_event(wl.EVENT_RUN_LOCKED, "run-legacy-bound")
        self.assertTrue(legacy_event["terminal_manifest_binding_sha256"])
        self.assertTrue(
            self.cli("inspect-run", "--run-dir", legacy["run_dir"])
            ["terminal_manifest_bound"]
        )

    def test_substituted_foreign_and_owned_outputs_are_refused_by_all_readers(self) -> None:
        started = self.start(phase="phase-01", run="run-producer")
        approved = self.produce(started, "approved.json")
        draft = self.produce(started, "draft.json")
        foreign = Path(self.tmp) / "foreign.json"
        foreign.write_text('{"foreign":true}', encoding="utf-8")
        self.cli(
            "complete-run", "--run-dir", started["run_dir"],
            "--status", "LOCKED", "--output", f"dataset={approved}",
        )
        published = self.cli(
            "create-handoff", "--root", self.workspace,
            "--producer-run-id", "run-producer",
            "--consumer-skill", "systematic-review-protocol",
            "--handoff-id", "handoff-boundary",
            "--artifact", f"dataset={approved}",
        )
        manifest_path = Path(started["run_dir"]) / wl.RUN_MANIFEST_NAME
        original = json.loads(manifest_path.read_text(encoding="utf-8"))

        for label, replacement, ownership_message in (
            ("foreign", foreign, "escapes declared root"),
            ("owned-draft", draft, "terminal manifest binding mismatch"),
        ):
            with self.subTest(label=label):
                mutated = dict(original)
                mutated["outputs"] = [
                    artifact_ref.make_artifact_ref(
                        str(replacement), "dataset", "1.0", "REFERENCED"
                    )
                ]
                manifest_path.write_bytes(wl.canonical_bytes(mutated))
                self.assertIn(
                    ownership_message,
                    self.refused("inspect-run", "--run-dir", started["run_dir"]),
                )
                self.assertIn(
                    ownership_message,
                    self.refused("generate-state", "--root", self.workspace),
                )
                self.assertIn(
                    ownership_message,
                    self.refused(
                        "create-handoff", "--root", self.workspace,
                        "--producer-run-id", "run-producer",
                        "--consumer-skill", "systematic-review-protocol",
                        "--handoff-id", f"handoff-{label}",
                        "--artifact", f"dataset={replacement}",
                    ),
                )
                for argv in (
                    (
                        "verify-handoff", "--path", published["handoff_dir"],
                        "--consumer-skill", "systematic-review-protocol",
                    ),
                    (
                        "start-run", "--root", self.workspace,
                        "--phase-id", "phase-02",
                        "--skill-id", "systematic-review-protocol",
                        "--run-id", f"consumer-{label}",
                        "--input", f"handoff={published['handoff_manifest']}",
                    ),
                ):
                    message = self.refused(*argv)
                    self.assertTrue(
                        any(
                            fragment in message
                            for fragment in (
                                "hash mismatch",
                                "not owned by run",
                                "terminal manifest binding mismatch",
                            )
                        ),
                        f"{argv[0]} refused for an unrelated reason: {message}",
                    )
                manifest_path.write_bytes(wl.canonical_bytes(original))


class HandoffAndLegacyTests(CliHarness):
    """A handoff addresses one consumer and creates nothing for it."""

    def completed_producer(
        self,
        phase: str = "phase-01",
        run: str = "run-001",
        roles: tuple = ("approved-eligibility-contract",),
    ) -> tuple:
        started = self.start(phase=phase, run=run)
        produced = {role: self.produce(started, f"{role}.json") for role in roles}
        outputs: list = []
        for role, path in produced.items():
            outputs += ["--output", f"{role}={path}"]
        self.cli("complete-run", "--run-dir", started["run_dir"], *outputs)
        return started, produced

    def handoff(self, *, consumer: str, handoff_id: str, role: str, path: Path,
                producer: str = "run-001") -> dict:
        return self.cli(
            "create-handoff",
            "--root", self.workspace,
            "--producer-run-id", producer,
            "--consumer-skill", consumer,
            "--handoff-id", handoff_id,
            "--artifact", f"{role}={path}",
        )

    # -- one producer, several consumers ---------------------------------

    def test_one_producer_routes_to_two_distant_consumers(self) -> None:
        _, produced = self.completed_producer()
        artifact = produced["approved-eligibility-contract"]

        near = self.handoff(
            consumer="systematic-review-protocol",
            handoff_id="handoff-to-phase-02",
            role="approved-eligibility-contract",
            path=artifact,
        )
        far = self.handoff(
            consumer="systematic-review-full-text-retrieval",
            handoff_id="handoff-to-phase-10",
            role="approved-eligibility-contract",
            path=artifact,
        )

        self.assertTrue(
            near["handoff_dir"].endswith(
                "handoffs/run-001/systematic-review-protocol/handoff-to-phase-02"
            )
        )
        self.assertTrue(
            far["handoff_dir"].endswith(
                "handoffs/run-001/systematic-review-full-text-retrieval/"
                "handoff-to-phase-10"
            )
        )
        for report, consumer in (
            (near, "systematic-review-protocol"),
            (far, "systematic-review-full-text-retrieval"),
        ):
            verified = self.cli(
                "verify-handoff",
                "--path", report["handoff_dir"],
                "--consumer-skill", consumer,
            )
            self.assertTrue(verified["verified"])
            self.assertEqual(verified["producer_run_id"], "run-001")
            self.assertEqual(verified["producer_status"], wl.STATUS_COMPLETED)

    def test_a_handoff_creates_nothing_for_its_consumer(self) -> None:
        _, produced = self.completed_producer()
        before = self.phase_directories()
        report = self.handoff(
            consumer="systematic-review-full-text-retrieval",
            handoff_id="handoff-to-phase-10",
            role="approved-eligibility-contract",
            path=produced["approved-eligibility-contract"],
        )
        # No consumer run, no consumer outputs, nothing but the manifest.
        self.assertEqual(self.phase_directories(), before)
        self.assertEqual(
            sorted(p.name for p in Path(report["handoff_dir"]).iterdir()),
            ["handoff_manifest.json"],
        )
        manifest = json.loads(
            Path(report["handoff_manifest"]).read_text(encoding="utf-8")
        )
        for forbidden in wl.FORBIDDEN_HANDOFF_FIELDS:
            self.assertNotIn(forbidden, manifest)

    # -- refusals ---------------------------------------------------------

    def test_a_consumer_mismatch_is_refused(self) -> None:
        _, produced = self.completed_producer()
        report = self.handoff(
            consumer="systematic-review-protocol",
            handoff_id="handoff-002",
            role="approved-eligibility-contract",
            path=produced["approved-eligibility-contract"],
        )
        self.assertIn(
            "addressed to",
            self.refused(
                "verify-handoff",
                "--path", report["handoff_dir"],
                "--consumer-skill", "systematic-review-full-text-retrieval",
            ),
        )

    def test_a_stale_source_invalidates_a_handoff(self) -> None:
        _, produced = self.completed_producer()
        artifact = produced["approved-eligibility-contract"]
        report = self.handoff(
            consumer="systematic-review-protocol",
            handoff_id="handoff-002",
            role="approved-eligibility-contract",
            path=artifact,
        )
        artifact.write_text('{"artifact":"tampered"}', encoding="utf-8")
        self.assertIn(
            "hash mismatch",
            self.refused(
                "verify-handoff",
                "--path", report["handoff_dir"],
                "--consumer-skill", "systematic-review-protocol",
            ),
        )
        # And a new handoff cannot be minted from the changed source either.
        self.assertIn(
            "hash mismatch",
            self.refused(
                "create-handoff",
                "--root", self.workspace,
                "--producer-run-id", "run-001",
                "--consumer-skill", "systematic-review-full-text-retrieval",
                "--handoff-id", "handoff-010",
                "--artifact", f"approved-eligibility-contract={artifact}",
            ),
        )

    def test_a_nonterminal_producer_cannot_hand_off(self) -> None:
        self.start()
        self.assertIn(
            "nonterminal",
            self.refused(
                "create-handoff",
                "--root", self.workspace,
                "--producer-run-id", "run-001",
                "--consumer-skill", "systematic-review-protocol",
                "--handoff-id", "handoff-002",
                "--artifact", "approved-protocol=" + str(self.protocol),
            ),
        )
        self.assertFalse((Path(self.workspace) / "handoffs").exists())

    def test_a_failed_producer_cannot_hand_off(self) -> None:
        started = self.start()
        artifact = self.produce(started)
        self.cli(
            "fail-run",
            "--run-dir", started["run_dir"],
            "--reason-code", "PILOT_REJECTED",
            "--message", "the pilot was rejected by the reviewer",
        )
        self.assertIn(
            "did not succeed",
            self.refused(
                "create-handoff",
                "--root", self.workspace,
                "--producer-run-id", "run-001",
                "--consumer-skill", "systematic-review-protocol",
                "--handoff-id", "handoff-002",
                "--artifact", f"approved-eligibility-contract={artifact}",
            ),
        )

    def test_a_duplicate_handoff_id_is_refused(self) -> None:
        _, produced = self.completed_producer()
        artifact = produced["approved-eligibility-contract"]
        self.handoff(
            consumer="systematic-review-protocol",
            handoff_id="handoff-002",
            role="approved-eligibility-contract",
            path=artifact,
        )
        # Same id, different consumer: still a duplicate.
        self.assertIn(
            "already used",
            self.refused(
                "create-handoff",
                "--root", self.workspace,
                "--producer-run-id", "run-001",
                "--consumer-skill", "systematic-review-full-text-retrieval",
                "--handoff-id", "handoff-002",
                "--artifact", f"approved-eligibility-contract={artifact}",
            ),
        )

    def test_a_handoff_may_only_offer_what_the_producer_locked(self) -> None:
        started, produced = self.completed_producer()
        smuggled = Path(started["outputs_dir"]) / "never-declared.json"
        smuggled.write_text('{"smuggled":true}', encoding="utf-8")
        self.assertIn(
            "is not an output locked by run",
            self.refused(
                "create-handoff",
                "--root", self.workspace,
                "--producer-run-id", "run-001",
                "--consumer-skill", "systematic-review-protocol",
                "--handoff-id", "handoff-002",
                "--artifact", f"smuggled-artifact={smuggled}",
            ),
        )

    def test_a_run_id_is_unique_across_phases(self) -> None:
        """F10: refused at creation, not at publication.

        The old publication-time ambiguity refusal came too late — the work was
        already done. It is retained as defence in depth and checked directly
        below, because start-run now makes it unreachable through the CLI.
        """
        self.completed_producer(phase="phase-01", run="run-001")
        self.assertIn(
            "unique across every phase",
            self.refused(
                "start-run", "--root", self.workspace,
                "--phase-id", "phase-02",
                "--skill-id", "systematic-review-protocol",
                "--run-id", "run-001",
                "--input", f"approved-protocol={self.protocol}",
            ),
        )
        self.assertFalse((Path(self.workspace) / "runs" / "phase-02").exists())

        # Defence in depth: the resolver still refuses ambiguity if a duplicate
        # ever reaches the filesystem by some other route.
        stray = Path(self.workspace) / "runs" / "phase-02" / "run-001"
        stray.mkdir(parents=True)
        with self.assertRaises(wl.WorkspaceLifecycleError) as caught:
            wl._locate_producer_run(self.workspace, "run-001")
        self.assertIn("ambiguous", str(caught.exception))

    def test_a_moved_handoff_is_refused(self) -> None:
        _, produced = self.completed_producer()
        report = self.handoff(
            consumer="systematic-review-protocol",
            handoff_id="handoff-002",
            role="approved-eligibility-contract",
            path=produced["approved-eligibility-contract"],
        )
        moved = Path(report["handoff_dir"]).parent / "handoff-renamed"
        Path(report["handoff_dir"]).rename(moved)
        self.assertIn(
            "moved or renamed",
            self.refused(
                "verify-handoff",
                "--path", str(moved),
                "--consumer-skill", "systematic-review-protocol",
            ),
        )

    def test_a_frozen_export_corpus_is_named_not_copied(self) -> None:
        _, produced = self.completed_producer(
            roles=("approved-eligibility-contract", wl.FROZEN_EXPORT_ROLE)
        )
        corpus = produced[wl.FROZEN_EXPORT_ROLE]
        before = corpus.read_bytes()
        report = self.handoff(
            consumer="systematic-review-data-extraction",
            handoff_id="handoff-011",
            role=wl.FROZEN_EXPORT_ROLE,
            path=corpus,
        )
        self.assertTrue(report["frozen_export"])
        verified = self.cli(
            "verify-handoff",
            "--path", report["handoff_dir"],
            "--consumer-skill", "systematic-review-data-extraction",
        )
        self.assertEqual(verified["frozen_export_role"], wl.FROZEN_EXPORT_ROLE)
        # Named by reference; no second copy was made.
        self.assertEqual(corpus.read_bytes(), before)
        self.assertEqual(
            sorted(p.name for p in Path(report["handoff_dir"]).iterdir()),
            ["handoff_manifest.json"],
        )

    # -- F8: handoffs are ledger-bound and consumer-bound ------------------

    def published(self) -> tuple:
        _, produced = self.completed_producer()
        artifact = produced["approved-eligibility-contract"]
        report = self.handoff(
            consumer="systematic-review-protocol",
            handoff_id="handoff-real",
            role="approved-eligibility-contract",
            path=artifact,
        )
        return report, artifact

    def test_a_cloned_handoff_has_no_ledger_entry(self) -> None:
        """F8a: every other check is satisfied by a faithful copy."""
        report, _ = self.published()
        clone = Path(report["handoff_dir"]).parent / "handoff-cloned"
        shutil.copytree(report["handoff_dir"], clone)
        manifest = json.loads((clone / "handoff_manifest.json").read_text())
        manifest["handoff_id"] = "handoff-cloned"
        (clone / "handoff_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")),
            encoding="utf-8",
        )
        self.assertIn(
            "has no ledger entry",
            self.refused(
                "verify-handoff", "--path", str(clone),
                "--consumer-skill", "systematic-review-protocol",
            ),
        )

    def test_a_run_may_not_consume_another_consumers_handoff(self) -> None:
        """F8b: consumer identity is bound when a run starts."""
        report, _ = self.published()
        message = self.refused(
            "start-run", "--root", self.workspace,
            "--phase-id", "phase-08",
            "--skill-id", "systematic-review-deduplication",
            "--run-id", "run-08-001",
            "--input", f"upstream-handoff={report['handoff_manifest']}",
        )
        self.assertIn("addressed to", message)
        self.assertFalse((Path(self.workspace) / "runs" / "phase-08").exists())

    def test_the_addressed_consumer_may_start_and_records_the_handoff(self) -> None:
        report, _ = self.published()
        started = self.cli(
            "start-run", "--root", self.workspace,
            "--phase-id", "phase-07a",
            "--skill-id", "systematic-review-protocol",
            "--run-id", "run-07a-001",
            "--input", f"upstream-handoff={report['handoff_manifest']}",
        )
        recorded = json.loads(
            (Path(started["run_dir"]) / "inputs_manifest.json").read_text()
        )
        self.assertEqual(recorded["consumed_handoff_ids"], ["handoff-real"])

    def test_a_handoff_manifest_written_by_hand_is_refused(self) -> None:
        report, _ = self.published()
        manifest = json.loads(Path(report["handoff_manifest"]).read_text())
        forged_dir = (
            Path(self.workspace) / "handoffs" / "run-001"
            / "systematic-review-full-text-retrieval" / "handoff-forged"
        )
        forged_dir.mkdir(parents=True)
        manifest["handoff_id"] = "handoff-forged"
        manifest["consumer_skill"] = "systematic-review-full-text-retrieval"
        (forged_dir / "handoff_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")),
            encoding="utf-8",
        )
        self.assertIn(
            "has no ledger entry",
            self.refused(
                "verify-handoff", "--path", str(forged_dir),
                "--consumer-skill", "systematic-review-full-text-retrieval",
            ),
        )

    def test_a_real_handoff_id_reused_under_another_consumer_is_refused(self) -> None:
        """Placement is self-consistent here, so only the ledger catches it.

        The manifest sits at a path that matches its own fields, so the
        placement check passes. Only the recorded HANDOFF_CREATED event knows
        which consumer this id was actually published to.
        """
        report, _ = self.published()
        manifest = json.loads(Path(report["handoff_manifest"]).read_text())
        manifest["consumer_skill"] = "systematic-review-full-text-retrieval"
        redirected = (
            Path(self.workspace) / "handoffs" / manifest["producer_run_id"]
            / "systematic-review-full-text-retrieval" / manifest["handoff_id"]
        )
        redirected.mkdir(parents=True)
        (redirected / "handoff_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")),
            encoding="utf-8",
        )
        message = self.refused(
            "verify-handoff", "--path", str(redirected),
            "--consumer-skill", "systematic-review-full-text-retrieval",
        )
        self.assertIn("the ledger says", message)
        self.assertIn("consumer_skill", message)

    def test_a_duplicated_handoff_event_is_refused(self) -> None:
        report, _ = self.published()
        wl.append_workspace_event(
            self.workspace, wl.EVENT_HANDOFF_CREATED,
            {"review_id": "review-001", "handoff_id": "handoff-real",
             "producer_phase_id": "phase-01", "producer_run_id": "run-001",
             "consumer_skill": "systematic-review-protocol"},
        )
        self.assertIn(
            "created more than once",
            self.refused(
                "verify-handoff", "--path", report["handoff_dir"],
                "--consumer-skill", "systematic-review-protocol",
            ),
        )

    def test_a_handoff_sequence_that_disagrees_with_the_ledger_is_refused(self) -> None:
        report, _ = self.published()
        target = Path(report["handoff_manifest"])
        manifest = json.loads(target.read_text())
        manifest["created_ledger_sequence"] = manifest["created_ledger_sequence"] + 7
        target.write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")),
            encoding="utf-8",
        )
        self.assertIn(
            "created_ledger_sequence",
            self.refused(
                "verify-handoff", "--path", report["handoff_dir"],
                "--consumer-skill", "systematic-review-protocol",
            ),
        )

    # -- F13: a handoff is bound to the review it sits in -------------------

    def second_review(self) -> dict:
        """A complete, legitimate second review built only through the CLI.

        Nothing here is forged. That is the point: F13 needed no forgery.
        """
        other = str(Path(self.tmp) / "review-two")
        self.cli("init-review", "--root", other, "--review-id", "review-002")
        source = Path(self.tmp) / "evidence" / "other-protocol.json"
        source.write_text('{"other":true}', encoding="utf-8")
        started = self.cli(
            "start-run", "--root", other,
            "--phase-id", "phase-01",
            "--skill-id", "systematic-review",
            "--run-id", "run-002-001",
            "--input", f"approved-protocol={source}",
        )
        artifact = Path(started["outputs_dir"]) / "other.json"
        artifact.write_text('{"artifact":"other"}', encoding="utf-8")
        self.cli(
            "complete-run", "--run-dir", started["run_dir"],
            "--output", f"approved-eligibility-contract={artifact}",
        )
        report = self.cli(
            "create-handoff", "--root", other,
            "--producer-run-id", "run-002-001",
            "--consumer-skill", "systematic-review-protocol",
            "--handoff-id", "handoff-002-001",
            "--artifact", f"approved-eligibility-contract={artifact}",
        )
        return {"root": other, "handoff": report}

    def test_a_run_may_not_consume_another_reviews_handoff(self) -> None:
        """F13: a review is a closed evidence boundary."""
        other = self.second_review()
        # It is a genuine handoff — in its own review.
        self.cli(
            "verify-handoff", "--path", other["handoff"]["handoff_manifest"],
            "--consumer-skill", "systematic-review-protocol",
        )
        message = self.refused(
            "start-run", "--root", self.workspace,
            "--phase-id", "phase-06",
            "--skill-id", "systematic-review-protocol",
            "--run-id", "run-06-001",
            "--input",
            f"upstream-handoff={other['handoff']['handoff_manifest']}",
        )
        self.assertIn("belongs to review", message)
        self.assertNotIn("phase-06", self.phase_directories())
        self.assertEqual(self.ledger_lines(), 1)

    def test_a_foreign_handoff_copied_into_this_review_is_refused(self) -> None:
        """Placement is satisfied by the copy; the local ledger is not."""
        other = self.second_review()
        destination = (
            Path(self.workspace) / "handoffs" / "run-002-001"
            / "systematic-review-protocol" / "handoff-002-001"
        )
        destination.mkdir(parents=True)
        (destination / "handoff_manifest.json").write_bytes(
            Path(other["handoff"]["handoff_manifest"]).read_bytes()
        )
        for argv in (
            ("verify-handoff", "--path", str(destination),
             "--consumer-skill", "systematic-review-protocol"),
            ("start-run", "--root", self.workspace,
             "--phase-id", "phase-06",
             "--skill-id", "systematic-review-protocol",
             "--run-id", "run-06-001",
             "--input",
             f"upstream-handoff={destination / 'handoff_manifest.json'}"),
        ):
            self.assertIn(
                "records review", self.refused(*argv), f"{argv[0]} accepted it"
            )

    def test_a_manifest_outside_a_handoffs_tree_is_not_a_handoff(self) -> None:
        """The root is derived structurally, so placement alone is not enough."""
        report, _ = self.published()
        # Same three trailing segments, so the placement check passes.
        stray = (
            Path(self.tmp) / "elsewhere" / "run-001"
            / "systematic-review-protocol" / "handoff-real"
        )
        stray.mkdir(parents=True)
        (stray / "handoff_manifest.json").write_bytes(
            Path(report["handoff_manifest"]).read_bytes()
        )
        self.assertIn(
            "must be <root>/handoffs/",
            self.refused(
                "verify-handoff", "--path", str(stray),
                "--consumer-skill", "systematic-review-protocol",
            ),
        )

    def test_a_producer_outside_the_handoffs_review_is_refused(self) -> None:
        """A handoff may not name a producer in someone else's review."""
        other = self.second_review()
        report, _ = self.published()
        manifest_path = Path(report["handoff_manifest"])
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["producer_run_manifest"] = artifact_ref.make_artifact_ref(
            str(Path(other["root"]) / "runs" / "phase-01" / "run-002-001"
                / "run_manifest.json"),
            "producer-run-manifest", "1.0", "INTERNAL_LOCKED",
        )
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")),
            encoding="utf-8",
        )
        self.assertIn(
            "names a producer outside its own review",
            self.refused(
                "verify-handoff", "--path", report["handoff_manifest"],
                "--consumer-skill", "systematic-review-protocol",
            ),
        )

    def test_outside_evidence_still_enters_by_legacy_registration(self) -> None:
        """The refusal has a documented route, and it still works."""
        other = self.second_review()
        external = (
            Path(other["root"]) / "runs" / "phase-01" / "run-002-001"
            / "outputs" / "other.json"
        )
        registered = self.cli(
            *self.register_legacy(
                phase="phase-07b", run="imported-run-001", path=external,
                role="external-corpus",
            )
        )
        self.assertEqual(registered["status"], wl.STATUS_LOCKED)
        self.assertIn(
            "LEGACY_RUN_REGISTERED",
            (Path(self.workspace) / "ledger" / "execution.jsonl").read_text(),
        )
        self.cli("generate-state", "--root", self.workspace)

    # -- legacy registration ---------------------------------------------

    def legacy_sources(self) -> dict:
        legacy = Path(self.tmp) / "legacy-phase-09"
        legacy.mkdir()
        sources = {}
        for role, name in (
            ("screening-decisions", "decisions.csv"),
            ("screening-lock", "lock.json"),
        ):
            path = legacy / name
            path.write_text(f"legacy {name}\n", encoding="utf-8")
            sources[role] = path
        return sources

    def test_legacy_sources_are_registered_without_being_touched(self) -> None:
        sources = self.legacy_sources()
        before = {
            role: (path.read_bytes(), path.stat().st_mtime_ns, str(path))
            for role, path in sources.items()
        }
        artifacts: list = []
        for role, path in sources.items():
            artifacts += ["--artifact", f"{role}={path}"]
        report = self.cli(
            "register-legacy-run",
            "--root", self.workspace,
            "--phase-id", "phase-09",
            "--skill-id", "systematic-review-title-abstract-screening",
            "--run-id", "legacy-run-001",
            "--legacy-status", "LOCKED",
            *artifacts,
        )
        self.assertEqual(report["status"], wl.STATUS_LOCKED)
        self.assertEqual(report["registered_artifacts"], 2)

        for role, path in sources.items():
            self.assertEqual(path.read_bytes(), before[role][0], f"{role} bytes")
            self.assertEqual(
                path.stat().st_mtime_ns, before[role][1], f"{role} mtime"
            )
            self.assertTrue(path.exists(), f"{role} was moved")

        # The wrapper owns no bytes, so it has no outputs directory, and the
        # manifest points back at the original locations.
        run = Path(report["run_dir"])
        self.assertEqual(
            sorted(p.name for p in run.iterdir()),
            ["inputs_manifest.json", "run_manifest.json"],
        )
        manifest = json.loads((run / "run_manifest.json").read_text())
        recorded = sorted(ref["path"] for ref in manifest["outputs"])
        self.assertEqual(recorded, sorted(before[r][2] for r in sources))

        state = self.cli("generate-state", "--root", self.workspace)
        self.assertEqual(state["phases"]["phase-09"]["status"], wl.STATUS_LOCKED)

    def test_a_registered_legacy_run_can_feed_a_consumer(self) -> None:
        sources = self.legacy_sources()
        self.cli(
            "register-legacy-run",
            "--root", self.workspace,
            "--phase-id", "phase-09",
            "--skill-id", "systematic-review-title-abstract-screening",
            "--run-id", "legacy-run-001",
            "--legacy-status", "LOCKED",
            "--artifact", f"screening-decisions={sources['screening-decisions']}",
        )
        report = self.handoff(
            consumer="systematic-review-full-text-retrieval",
            handoff_id="handoff-legacy-010",
            role="screening-decisions",
            path=sources["screening-decisions"],
            producer="legacy-run-001",
        )
        verified = self.cli(
            "verify-handoff",
            "--path", report["handoff_dir"],
            "--consumer-skill", "systematic-review-full-text-retrieval",
        )
        self.assertEqual(verified["producer_status"], wl.STATUS_LOCKED)
        self.assertEqual(verified["artifact_roles"], ["screening-decisions"])

    def test_registration_refuses_a_reused_destination_and_a_bad_status(self) -> None:
        sources = self.legacy_sources()
        arguments = {
            "phase_id": "phase-09",
            "skill_id": "systematic-review-title-abstract-screening",
            "run_id": "legacy-run-001",
            "artifacts": [
                artifact_ref.make_artifact_ref(
                    str(sources["screening-lock"]), "screening-lock", "1.0", "LOCKED"
                )
            ],
        }
        with self.assertRaises(wl.WorkspaceLifecycleError) as caught:
            wl.register_legacy_run(
                self.workspace, legacy_status=wl.STATUS_FAILED, **arguments
            )
        self.assertIn("legacy_status must be one of", str(caught.exception))

        wl.register_legacy_run(
            self.workspace, legacy_status=wl.STATUS_LOCKED, **arguments
        )
        with self.assertRaises(wl.WorkspaceLifecycleError) as caught:
            wl.register_legacy_run(
                self.workspace, legacy_status=wl.STATUS_LOCKED, **arguments
            )
        self.assertIn("never reused", str(caught.exception))

    def test_only_a_legacy_run_may_name_artifacts_it_did_not_write(self) -> None:
        started, produced = self.completed_producer()
        neighbour, borrowed = self.completed_producer(
            phase="phase-02", run="run-002", roles=("neighbour-output",)
        )
        manifest_path = Path(started["run_dir"]) / "run_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["outputs"] = [
            artifact_ref.make_artifact_ref(
                str(borrowed["neighbour-output"]),
                "approved-eligibility-contract",
                "1.0",
                "REFERENCED",
            )
        ]
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        message = self.refused("generate-state", "--root", self.workspace)
        self.assertIn("not owned by run", message)

    # -- F12: both run creators enforce identifier uniqueness --------------

    def register_legacy(self, *, phase: str, run: str, path: Path,
                        role: str = "screening-lock") -> list:
        return [
            "register-legacy-run", "--root", self.workspace,
            "--phase-id", phase,
            "--skill-id", "systematic-review-title-abstract-screening",
            "--run-id", run,
            "--legacy-status", "LOCKED",
            "--artifact", f"{role}={path}",
        ]

    def test_legacy_registration_refuses_a_run_id_used_by_a_started_run(self) -> None:
        """F12: the other creator of a run directory obeys the same rule."""
        sources = self.legacy_sources()
        self.completed_producer(phase="phase-01", run="run-001")
        before = self.ledger_lines()
        message = self.refused(
            *self.register_legacy(
                phase="phase-09", run="run-001", path=sources["screening-lock"]
            )
        )
        self.assertIn("unique across every phase", message)
        # A refusal leaves nothing behind: no directory, no event.
        self.assertNotIn("phase-09", self.phase_directories())
        self.assertEqual(self.ledger_lines(), before)
        # The producer stays resolvable, which is the harm F10 named.
        self.assertEqual(
            wl._locate_producer_run(self.workspace, "run-001")["phase_id"],
            "phase-01",
        )

    def test_a_started_run_refuses_a_run_id_used_by_a_legacy_run(self) -> None:
        """The reverse direction: the directory arm covers it. Assert it."""
        sources = self.legacy_sources()
        self.cli(
            *self.register_legacy(
                phase="phase-09", run="legacy-run-001",
                path=sources["screening-lock"],
            )
        )
        message = self.refused(
            "start-run", "--root", self.workspace,
            "--phase-id", "phase-01",
            "--skill-id", "systematic-review",
            "--run-id", "legacy-run-001",
            "--input", f"approved-protocol={self.protocol}",
        )
        self.assertIn("unique across every phase", message)
        self.assertNotIn("phase-01", self.phase_directories())

    def test_a_run_id_differing_only_in_case_is_refused_by_both_creators(self) -> None:
        """O2: every other identifier folds case; run identifiers now do too."""
        sources = self.legacy_sources()
        self.completed_producer(phase="phase-01", run="run-001")

        self.assertIn(
            "unique across every phase",
            self.refused(
                "start-run", "--root", self.workspace,
                "--phase-id", "phase-02",
                "--skill-id", "systematic-review",
                "--run-id", "RUN-001",
                "--input", f"approved-protocol={self.protocol}",
            ),
        )
        self.assertIn(
            "unique across every phase",
            self.refused(
                *self.register_legacy(
                    phase="phase-09", run="Run-001",
                    path=sources["screening-lock"],
                )
            ),
        )
        self.assertEqual(self.phase_directories(), ["phase-01"])

    def test_the_ledger_arm_binds_legacy_registration_too(self) -> None:
        """A deleted directory does not free its id for either creator."""
        sources = self.legacy_sources()
        started, _ = self.completed_producer(phase="phase-01", run="run-001")
        shutil.rmtree(started["run_dir"])
        message = self.refused(
            *self.register_legacy(
                phase="phase-09", run="run-001", path=sources["screening-lock"]
            )
        )
        self.assertIn("already recorded in the ledger", message)

    def test_the_ledger_arm_folds_case_too(self) -> None:
        """Both arms fold, not just the one a live directory reaches first."""
        sources = self.legacy_sources()
        started, _ = self.completed_producer(phase="phase-01", run="run-001")
        shutil.rmtree(started["run_dir"])
        for argv in (
            ("start-run", "--root", self.workspace,
             "--phase-id", "phase-02",
             "--skill-id", "systematic-review",
             "--run-id", "RUN-001",
             "--input", f"approved-protocol={self.protocol}"),
            tuple(self.register_legacy(
                phase="phase-09", run="Run-001", path=sources["screening-lock"]
            )),
        ):
            self.assertIn(
                "already recorded in the ledger",
                self.refused(*argv),
                f"{argv[0]} accepted a case variant of a retired id",
            )

    def test_a_fresh_legacy_registration_still_succeeds(self) -> None:
        sources = self.legacy_sources()
        self.completed_producer(phase="phase-01", run="run-001")
        registered = self.cli(
            *self.register_legacy(
                phase="phase-09", run="legacy-run-001",
                path=sources["screening-lock"],
            )
        )
        self.assertEqual(registered["status"], wl.STATUS_LOCKED)
        self.assertEqual(
            sources["screening-lock"].read_text(encoding="utf-8"),
            "legacy lock.json\n",
        )
        self.cli("generate-state", "--root", self.workspace)


class LedgerReconciliationTests(CliHarness):
    """Finding F7: a status is never read from a manifest alone."""

    def forge_terminal_manifest(self, started: dict, status: str = "LOCKED") -> Path:
        """Write a schema-valid terminal manifest with no matching ledger event."""
        artifact = self.produce(started)
        forged = {
            "schema_version": wl.SCHEMA_VERSION,
            "record_type": wl.RECORD_RUN,
            "review_id": "review-001",
            "phase_id": "phase-01",
            "skill_id": "systematic-review",
            "run_id": "run-001",
            "status": status,
            "inputs_manifest": artifact_ref.make_artifact_ref(
                str(Path(started["run_dir"]) / "inputs_manifest.json"),
                "inputs-manifest", "1.0", "INTERNAL_LOCKED",
            ),
            "outputs": [
                artifact_ref.make_artifact_ref(
                    str(artifact), "approved-eligibility-contract", "1.0", "REFERENCED"
                )
            ],
            "parent_run_ids": [],
            "consumed_handoff_ids": [],
            "downstream_consumers": [],
            "start_ledger_sequence": 2,
            "terminal_ledger_sequence": 3,
            "created_at": "2026-07-31T00:00:00Z",
            "completed_at": "2026-07-31T00:00:01Z",
            "timestamp_assurance": wl.TIMESTAMP_ASSURANCE,
            "tool_version": wl.TOOL_VERSION,
        }
        # It really is schema-valid; only the ledger disagrees.
        wl.validate_run_manifest(forged)
        target = Path(started["run_dir"]) / "run_manifest.json"
        target.write_text(
            json.dumps(forged, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")),
            encoding="utf-8",
        )
        return target

    def test_every_status_reader_refuses_a_forged_terminal_manifest(self) -> None:
        started = self.start()
        artifact = Path(started["outputs_dir"]) / "eligibility.json"
        self.forge_terminal_manifest(started)

        for argv in (
            ("inspect-run", "--run-dir", started["run_dir"]),
            ("create-handoff", "--root", self.workspace,
             "--producer-run-id", "run-001",
             "--consumer-skill", "systematic-review-protocol",
             "--handoff-id", "handoff-forged",
             "--artifact", f"approved-eligibility-contract={artifact}"),
            ("generate-state", "--root", self.workspace),
        ):
            message = self.refused(*argv)
            self.assertIn(
                "disagrees with the ledger", message, f"{argv[0]} accepted a forgery"
            )
        self.assertFalse((Path(self.workspace) / "handoffs").exists())

    def test_verify_handoff_refuses_a_producer_forged_after_publication(self) -> None:
        started = self.start()
        artifact = self.produce(started)
        self.cli(
            "complete-run", "--run-dir", started["run_dir"],
            "--output", f"approved-eligibility-contract={artifact}",
        )
        report = self.cli(
            "create-handoff", "--root", self.workspace,
            "--producer-run-id", "run-001",
            "--consumer-skill", "systematic-review-protocol",
            "--handoff-id", "handoff-001",
            "--artifact", f"approved-eligibility-contract={artifact}",
        )
        self.cli(
            "verify-handoff", "--path", report["handoff_dir"],
            "--consumer-skill", "systematic-review-protocol",
        )
        # The producer's terminal manifest is replaced after the fact.
        manifest = Path(started["run_dir"]) / "run_manifest.json"
        record = json.loads(manifest.read_text())
        record["terminal_ledger_sequence"] = record["terminal_ledger_sequence"] + 5
        manifest.write_text(
            json.dumps(record, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")),
            encoding="utf-8",
        )
        self.assertIn(
            "hash mismatch",
            self.refused(
                "verify-handoff", "--path", report["handoff_dir"],
                "--consumer-skill", "systematic-review-protocol",
            ),
        )

    def test_a_run_directory_with_no_ledger_entry_is_refused(self) -> None:
        """A copied or restored run directory is not a run."""
        started = self.start()
        artifact = self.produce(started)
        self.cli(
            "complete-run", "--run-dir", started["run_dir"],
            "--output", f"approved-eligibility-contract={artifact}",
        )
        # Copy the finished run to a new id, as a restore or a duplication would.
        copied = Path(started["run_dir"]).parent / "run-copied"
        shutil.copytree(started["run_dir"], copied)
        for name in ("inputs_manifest.json", "run_manifest.json"):
            record = json.loads((copied / name).read_text())
            record["run_id"] = "run-copied"
            (copied / name).write_text(
                json.dumps(record, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":")),
                encoding="utf-8",
            )
        for argv in (
            ("inspect-run", "--run-dir", str(copied)),
            ("generate-state", "--root", self.workspace),
        ):
            self.assertIn(
                "no ledger entry", self.refused(*argv), f"{argv[0]} accepted a copy"
            )

    def test_a_skill_id_that_disagrees_with_the_ledger_is_refused(self) -> None:
        started = self.start()
        artifact = self.produce(started)
        self.cli(
            "complete-run", "--run-dir", started["run_dir"],
            "--output", f"approved-eligibility-contract={artifact}",
        )
        inputs = Path(started["run_dir"]) / "inputs_manifest.json"
        record = json.loads(inputs.read_text())
        record["skill_id"] = "systematic-review-protocol"
        inputs.write_text(
            json.dumps(record, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")),
            encoding="utf-8",
        )
        for argv in (
            ("inspect-run", "--run-dir", started["run_dir"]),
            ("generate-state", "--root", self.workspace),
        ):
            self.assertIn("the ledger says", self.refused(*argv), argv[0])

    def test_contradictory_ledger_events_about_one_run_are_refused(self) -> None:
        """Observation O1: the event authority may not contradict itself."""
        started = self.start()
        self.forge_terminal_manifest(started)
        wl.append_workspace_event(
            self.workspace, wl.EVENT_RUN_LOCKED,
            {"review_id": "review-001", "phase_id": "phase-01",
             # started as systematic-review; terminated as something else
             "skill_id": "systematic-review-protocol", "run_id": "run-001"},
        )
        for argv in (
            ("inspect-run", "--run-dir", started["run_dir"]),
            ("generate-state", "--root", self.workspace),
        ):
            self.assertIn("but it started as", self.refused(*argv), argv[0])

    def test_a_legacy_run_may_not_terminate_against_its_registration(self) -> None:
        source = Path(self.tmp) / "legacy.json"
        source.write_text('{"legacy":true}', encoding="utf-8")
        self.cli(
            "register-legacy-run", "--root", self.workspace,
            "--phase-id", "phase-09",
            "--skill-id", "systematic-review-title-abstract-screening",
            "--run-id", "legacy-run-001", "--legacy-status", "LOCKED",
            "--artifact", f"screening-lock={source}",
        )
        self.cli("generate-state", "--root", self.workspace)
        # A second, contradictory terminal event for the same registration.
        run_dir = str(Path(self.workspace) / "runs/phase-09/legacy-run-001")
        ledger = Path(self.workspace) / "ledger" / "execution.jsonl"
        entries = [
            json.loads(line)
            for line in ledger.read_text().splitlines()
            if line.strip()
        ]
        kept = [
            e for e in entries
            if e["event"].get("run_id") != "legacy-run-001"
            or e["event"]["event_type"] != wl.EVENT_RUN_LOCKED
        ]
        self.assertEqual(len(kept), len(entries) - 1)
        # Rebuild the chain without the LOCKED event, then record COMPLETED.
        ledger.unlink()
        for entry in kept:
            wl.append_workspace_event(
                self.workspace, entry["event"]["event_type"],
                {k: v for k, v in entry["event"].items()
                 if k not in ("event_type", "schema_version", "tool_version",
                              "recorded_at", "identity_assurance", "actor_id",
                              "session_id")},
            )
        wl.append_workspace_event(
            self.workspace, wl.EVENT_RUN_COMPLETED,
            {"review_id": "review-001", "phase_id": "phase-09",
             "skill_id": "systematic-review-title-abstract-screening",
             "run_id": "legacy-run-001"},
        )
        self.assertIn(
            "was registered as", self.refused("inspect-run", "--run-dir", run_dir)
        )

    def event(self, kind: str, **fields) -> None:
        base = {"review_id": "review-001", "phase_id": "phase-01",
                "skill_id": "systematic-review", "run_id": "run-001"}
        wl.append_workspace_event(self.workspace, kind, {**base, **fields})

    def test_a_run_may_not_start_twice_in_the_ledger(self) -> None:
        self.start()
        self.event(wl.EVENT_RUN_STARTED)
        self.assertIn(
            "started more than once",
            self.refused("generate-state", "--root", self.workspace),
        )

    def test_a_terminal_event_for_a_run_that_never_started_is_refused(self) -> None:
        self.start()
        self.event(wl.EVENT_RUN_COMPLETED, run_id="run-never-started")
        self.assertIn(
            "which was never started",
            self.refused("generate-state", "--root", self.workspace),
        )

    def test_a_run_may_not_terminate_twice_in_the_ledger(self) -> None:
        started = self.start()
        artifact = self.produce(started)
        self.cli(
            "complete-run", "--run-dir", started["run_dir"],
            "--output", f"approved-eligibility-contract={artifact}",
        )
        self.event(wl.EVENT_RUN_LOCKED)
        self.assertIn(
            "more than one terminal ledger event",
            self.refused("generate-state", "--root", self.workspace),
        )

    def test_an_event_from_another_review_is_refused(self) -> None:
        self.start()
        self.event(wl.EVENT_RUN_COMPLETED, review_id="review-002")
        self.assertIn(
            "belongs to review",
            self.refused("generate-state", "--root", self.workspace),
        )

    def alter_terminal(self, run_dir: str, name: str, field: str, value) -> None:
        target = Path(run_dir) / name
        record = json.loads(target.read_text())
        record[field] = value
        target.write_text(
            json.dumps(record, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")),
            encoding="utf-8",
        )

    def test_an_altered_terminal_manifest_identity_is_refused(self) -> None:
        """F9: status agreement is not identity agreement."""
        cases = (
            ("review_id", "review-999"),
            ("phase_id", "phase-99"),
            ("run_id", "run-999"),
            ("skill_id", "systematic-review-protocol"),
            # Schema-valid but not what the ledger recorded: start stays below
            # terminal, so only the reconciliation can catch it.
            ("start_ledger_sequence", 1),
            ("terminal_ledger_sequence", 999),
        )
        for field, value in cases:
            with self.subTest(field=field):
                harness = LedgerReconciliationTests(self._testMethodName)
                harness.setUp()
                self.addCleanup(shutil.rmtree, harness.tmp, True)
                started = harness.start()
                artifact = harness.produce(started)
                harness.cli(
                    "complete-run", "--run-dir", started["run_dir"],
                    "--output", f"approved-eligibility-contract={artifact}",
                )
                harness.alter_terminal(
                    started["run_dir"], "run_manifest.json", field, value
                )
                for argv in (
                    ("inspect-run", "--run-dir", started["run_dir"]),
                    ("generate-state", "--root", harness.workspace),
                ):
                    self.assertIn(
                        "terminal manifest for",
                        harness.refused(*argv),
                        f"{argv[0]} accepted an altered {field}",
                    )

    def test_an_altered_failure_manifest_identity_is_refused(self) -> None:
        """O4: brief 27 specified both manifest kinds; only one was covered."""
        cases = (
            ("review_id", "review-999"),
            ("phase_id", "phase-99"),
            ("run_id", "run-999"),
            ("skill_id", "systematic-review-protocol"),
            ("start_ledger_sequence", 1),
            ("terminal_ledger_sequence", 999),
        )
        for field, value in cases:
            with self.subTest(field=field):
                harness = LedgerReconciliationTests(self._testMethodName)
                harness.setUp()
                self.addCleanup(shutil.rmtree, harness.tmp, True)
                started = harness.start()
                harness.cli(
                    "fail-run", "--run-dir", started["run_dir"],
                    "--reason-code", "PILOT_REJECTED", "--message", "rejected",
                )
                harness.alter_terminal(
                    started["run_dir"], "failure_manifest.json", field, value
                )
                for argv in (
                    ("inspect-run", "--run-dir", started["run_dir"]),
                    ("generate-state", "--root", harness.workspace),
                ):
                    self.assertIn(
                        "terminal manifest for",
                        harness.refused(*argv),
                        f"{argv[0]} accepted an altered {field}",
                    )

    # -- F14: the committed inputs-manifest hash is recomputed ---------------

    def rewrite_inputs_manifest(self, run_dir: str, **changes) -> None:
        """Edit a run's inputs manifest after the fact, ledger untouched."""
        target = Path(run_dir) / "inputs_manifest.json"
        record = json.loads(target.read_text())
        record.update(changes)
        target.write_text(
            json.dumps(record, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")),
            encoding="utf-8",
        )

    def test_a_rewritten_inputs_manifest_is_refused_by_every_reader(self) -> None:
        """F14: a recorded hash that nothing recomputes is not a control."""
        started = self.start()
        artifact = self.produce(started)
        self.cli(
            "complete-run", "--run-dir", started["run_dir"],
            "--output", f"approved-eligibility-contract={artifact}",
        )
        report = self.cli(
            "create-handoff", "--root", self.workspace,
            "--producer-run-id", "run-001",
            "--consumer-skill", "systematic-review-protocol",
            "--handoff-id", "handoff-001",
            "--artifact", f"approved-eligibility-contract={artifact}",
        )
        planted = Path(self.tmp) / "evidence" / "planted.json"
        planted.write_text('{"planted":true}', encoding="utf-8")
        self.rewrite_inputs_manifest(
            started["run_dir"],
            inputs=[
                artifact_ref.make_artifact_ref(
                    str(planted), "planted-evidence", "1.0", "REFERENCED"
                )
            ],
            parent_run_ids=["run-never-existed"],
        )
        for argv in (
            ("inspect-run", "--run-dir", started["run_dir"]),
            ("generate-state", "--root", self.workspace),
            ("create-handoff", "--root", self.workspace,
             "--producer-run-id", "run-001",
             "--consumer-skill", "systematic-review-deduplication",
             "--handoff-id", "handoff-002",
             "--artifact", f"approved-eligibility-contract={artifact}"),
            ("verify-handoff", "--path", report["handoff_manifest"],
             "--consumer-skill", "systematic-review-protocol"),
        ):
            self.assertIn(
                "hash mismatch",
                self.refused(*argv),
                f"{argv[0]} accepted a rewritten inputs manifest",
            )

    def test_a_failed_runs_inputs_manifest_is_verified_too(self) -> None:
        started = self.start()
        self.cli(
            "fail-run", "--run-dir", started["run_dir"],
            "--reason-code", "PILOT_REJECTED", "--message", "rejected",
        )
        self.rewrite_inputs_manifest(started["run_dir"], inputs=[])
        for argv in (
            ("inspect-run", "--run-dir", started["run_dir"]),
            ("generate-state", "--root", self.workspace),
        ):
            self.assertIn("hash mismatch", self.refused(*argv), argv[0])

    def test_a_terminal_manifest_may_not_revise_lineage(self) -> None:
        """Lineage is fixed when the run starts; completion restates it."""
        for field, value in (
            ("parent_run_ids", ["run-invented"]),
            ("consumed_handoff_ids", ["handoff-invented"]),
        ):
            with self.subTest(field=field):
                harness = LedgerReconciliationTests(self._testMethodName)
                harness.setUp()
                self.addCleanup(shutil.rmtree, harness.tmp, True)
                started = harness.start()
                artifact = harness.produce(started)
                harness.cli(
                    "complete-run", "--run-dir", started["run_dir"],
                    "--output", f"approved-eligibility-contract={artifact}",
                )
                harness.alter_terminal(
                    started["run_dir"], "run_manifest.json", field, value
                )
                for argv in (
                    ("inspect-run", "--run-dir", started["run_dir"]),
                    ("generate-state", "--root", harness.workspace),
                ):
                    self.assertIn(
                        "the inputs manifest records",
                        harness.refused(*argv),
                        f"{argv[0]} accepted revised {field}",
                    )

    def test_a_terminal_manifest_may_not_point_at_another_runs_inputs(self) -> None:
        neighbour = self.locked_run("phase-02", "run-002")
        started = self.start()
        artifact = self.produce(started)
        self.cli(
            "complete-run", "--run-dir", started["run_dir"],
            "--output", f"approved-eligibility-contract={artifact}",
        )
        self.alter_terminal(
            started["run_dir"], "run_manifest.json", "inputs_manifest",
            artifact_ref.make_artifact_ref(
                str(Path(neighbour["run_dir"]) / "inputs_manifest.json"),
                "inputs-manifest", "1.0", "INTERNAL_LOCKED",
            ),
        )
        self.assertIn(
            "not to this run's own inputs_manifest.json",
            self.refused("inspect-run", "--run-dir", started["run_dir"]),
        )

    def test_a_registered_legacy_runs_inputs_manifest_still_verifies(self) -> None:
        """The legacy writer creates both files in one call; it must pass."""
        source = Path(self.tmp) / "legacy-evidence.json"
        source.write_text('{"legacy":true}', encoding="utf-8")
        registered = self.cli(
            "register-legacy-run", "--root", self.workspace,
            "--phase-id", "phase-09",
            "--skill-id", "systematic-review-title-abstract-screening",
            "--run-id", "legacy-run-001", "--legacy-status", "LOCKED",
            "--artifact", f"screening-lock={source}",
        )
        self.assertEqual(
            self.cli("inspect-run", "--run-dir", registered["run_dir"])["status"],
            wl.STATUS_LOCKED,
        )
        self.cli("generate-state", "--root", self.workspace)

    def test_a_run_recording_another_review_is_refused(self) -> None:
        started = self.start()
        inputs = Path(started["run_dir"]) / "inputs_manifest.json"
        record = json.loads(inputs.read_text())
        record["review_id"] = "review-999"
        inputs.write_text(
            json.dumps(record, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")),
            encoding="utf-8",
        )
        self.assertIn(
            "this review is",
            self.refused("inspect-run", "--run-dir", started["run_dir"]),
        )

    def locked_run(self, phase: str, run: str) -> dict:
        started = self.start(phase=phase, run=run)
        artifact = self.produce(started)
        self.cli(
            "complete-run", "--run-dir", started["run_dir"],
            "--output", f"approved-eligibility-contract={artifact}",
            "--status", "LOCKED",
        )
        return started

    def test_a_run_id_stays_used_after_its_directory_is_deleted(self) -> None:
        """The ledger remembers. Deleting a directory does not free its id."""
        started = self.locked_run("phase-01", "run-01-001")
        shutil.rmtree(started["run_dir"])
        message = self.refused(
            "start-run", "--root", self.workspace,
            "--phase-id", "phase-02",
            "--skill-id", "systematic-review-protocol",
            "--run-id", "run-01-001",
        )
        self.assertIn("already recorded in the ledger", message)

    def test_a_parent_that_does_not_exist_is_refused(self) -> None:
        """F11: a correction may not claim lineage that never happened."""
        message = self.refused(
            "start-run", "--root", self.workspace,
            "--phase-id", "phase-16-17",
            "--skill-id", "systematic-review-reporting-package",
            "--run-id", "run-16-17-002",
            "--parent-run-id", "run-parent-does-not-exist",
        )
        self.assertIn("does not exist in this review", message)
        self.assertFalse((Path(self.workspace) / "runs" / "phase-16-17").exists())

    def test_a_run_may_not_be_its_own_parent(self) -> None:
        self.assertIn(
            "cannot be its own parent",
            self.refused(
                "start-run", "--root", self.workspace,
                "--phase-id", "phase-16-17",
                "--skill-id", "systematic-review-reporting-package",
                "--run-id", "run-16-17-002",
                "--parent-run-id", "run-16-17-002",
            ),
        )

    def test_a_parent_still_in_flight_is_refused(self) -> None:
        self.start(phase="phase-16-17", run="run-16-17-001")
        self.assertIn(
            "not terminal",
            self.refused(
                "start-run", "--root", self.workspace,
                "--phase-id", "phase-16-17",
                "--skill-id", "systematic-review-reporting-package",
                "--run-id", "run-16-17-002",
                "--parent-run-id", "run-16-17-001",
            ),
        )

    def test_a_correction_from_a_locked_parent_is_allowed(self) -> None:
        self.locked_run("phase-16-17", "run-16-17-001")
        started = self.cli(
            "start-run", "--root", self.workspace,
            "--phase-id", "phase-16-17",
            "--skill-id", "systematic-review",
            "--run-id", "run-16-17-002",
            "--parent-run-id", "run-16-17-001",
        )
        recorded = json.loads(
            (Path(started["run_dir"]) / "inputs_manifest.json").read_text()
        )
        self.assertEqual(recorded["parent_run_ids"], ["run-16-17-001"])

    def test_a_retry_from_a_failed_parent_is_allowed(self) -> None:
        failed = self.start(phase="phase-09", run="run-09-001")
        self.cli(
            "fail-run", "--run-dir", failed["run_dir"],
            "--reason-code", "PILOT_REJECTED", "--message", "rejected",
        )
        started = self.cli(
            "start-run", "--root", self.workspace,
            "--phase-id", "phase-09",
            "--skill-id", "systematic-review",
            "--run-id", "run-09-002",
            "--parent-run-id", "run-09-001",
        )
        recorded = json.loads(
            (Path(started["run_dir"]) / "inputs_manifest.json").read_text()
        )
        self.assertEqual(recorded["parent_run_ids"], ["run-09-001"])

    def test_the_reconciliation_has_exactly_one_implementation(self) -> None:
        source = inspect.getsource(wl)
        self.assertEqual(
            source.count("def reconcile_run_with_ledger("), 1
        )
        # Every command that reads a status routes through it.
        for name in ("read_terminal_manifest", "inspect_run", "generate_review_state"):
            self.assertIn(
                "reconcile_run_with_ledger",
                inspect.getsource(getattr(wl, name)),
                f"{name} reads a status without reconciling",
            )
        self.assertIn(
            "read_terminal_manifest",
            inspect.getsource(wl.assert_successful_producer),
        )

    def test_normal_states_are_unaffected(self) -> None:
        interrupted = self.start(phase="phase-01", run="run-001")
        self.assertEqual(
            self.cli("inspect-run", "--run-dir", interrupted["run_dir"])["status"],
            wl.STATUS_STARTED,
        )
        failed = self.start(phase="phase-02", run="run-002")
        self.cli(
            "fail-run", "--run-dir", failed["run_dir"],
            "--reason-code", "PILOT_REJECTED", "--message", "rejected",
        )
        self.assertEqual(
            self.cli("inspect-run", "--run-dir", failed["run_dir"])["status"],
            wl.STATUS_FAILED,
        )
        legacy_source = Path(self.tmp) / "legacy.json"
        legacy_source.write_text('{"legacy":true}', encoding="utf-8")
        registered = self.cli(
            "register-legacy-run", "--root", self.workspace,
            "--phase-id", "phase-09",
            "--skill-id", "systematic-review-title-abstract-screening",
            "--run-id", "legacy-run-001", "--legacy-status", "LOCKED",
            "--artifact", f"screening-lock={legacy_source}",
        )
        # A registered legacy run stays a verifiable producer.
        published = self.cli(
            "create-handoff", "--root", self.workspace,
            "--producer-run-id", "legacy-run-001",
            "--consumer-skill", "systematic-review-full-text-retrieval",
            "--handoff-id", "handoff-legacy",
            "--artifact", f"screening-lock={legacy_source}",
        )
        self.assertTrue(
            self.cli(
                "verify-handoff", "--path", published["handoff_dir"],
                "--consumer-skill", "systematic-review-full-text-retrieval",
            )["verified"]
        )
        self.assertEqual(registered["status"], wl.STATUS_LOCKED)

    def test_the_self_asserted_ledger_limit_is_unchanged(self) -> None:
        """Writing both sides still succeeds. The fix never claimed otherwise."""
        started = self.start()
        manifest_path = self.forge_terminal_manifest(started)
        forged = json.loads(manifest_path.read_text(encoding="utf-8"))
        wl.append_workspace_event(
            self.workspace, wl.EVENT_RUN_LOCKED,
            {"review_id": "review-001", "phase_id": "phase-01",
             "skill_id": "systematic-review", "run_id": "run-001",
             "terminal_manifest_binding_sha256":
                 wl._terminal_manifest_binding_sha256(forged)},
        )
        state = self.cli("generate-state", "--root", self.workspace)
        self.assertEqual(state["phases"]["phase-01"]["status"], wl.STATUS_LOCKED)
        verification = approval_ledger.verify_ledger(
            str(wl.ledger_path(self.workspace))
        )
        self.assertEqual(
            verification["assurance_level"], approval_ledger.SELF_ASSERTED
        )
        self.assertFalse(verification["authenticated"])

class RevisionTenClosureTests(CliHarness):
    """Adversarial CLI regressions for the revision-10 closure boundary."""

    def locked_handoff(self, handoff_id: str = "handoff-r10") -> tuple:
        started = self.start(phase="phase-01", run="run-producer")
        artifact = self.produce(started)
        self.cli(
            "complete-run", "--run-dir", started["run_dir"],
            "--output", f"approved-contract={artifact}", "--status", "LOCKED",
        )
        published = self.cli(
            "create-handoff", "--root", self.workspace,
            "--producer-run-id", "run-producer",
            "--consumer-skill", "systematic-review-protocol",
            "--handoff-id", handoff_id,
            "--artifact", f"approved-contract={artifact}",
        )
        return started, artifact, published

    def historical_started(self, phase: str, run: str) -> dict:
        event = wl.append_workspace_event(
            self.workspace, wl.EVENT_RUN_STARTED,
            {"review_id": "review-001", "phase_id": phase,
             "skill_id": "systematic-review", "run_id": run},
        )
        target = wl.run_dir(self.workspace, phase, run)
        wl.create_new_directory(self.workspace, str(target))
        wl.create_new_directory(self.workspace, str(target / "outputs"))
        inputs = {
            "schema_version": wl.SCHEMA_VERSION,
            "record_type": wl.RECORD_INPUTS,
            "review_id": "review-001", "phase_id": phase,
            "skill_id": "systematic-review", "run_id": run,
            "inputs": [ref(self.protocol, "approved-protocol")],
            "parent_run_ids": [], "consumed_handoff_ids": [],
            "start_ledger_sequence": event["sequence"],
            "created_at": wl.utc_timestamp(),
            "timestamp_assurance": wl.TIMESTAMP_ASSURANCE,
        }
        wl.write_new_json(
            self.workspace, str(target / wl.INPUTS_MANIFEST_NAME), inputs
        )
        return {"run_dir": str(target), "inputs": inputs}

    def test_inputs_provenance_is_bound_at_start(self) -> None:
        mutations = (
            ("inputs", lambda r, p: r.update(inputs=[ref(p, "planted")])),
            ("parents", lambda r, _p: r.update(
                parent_run_ids=["run-never-existed"])),
            ("handoffs", lambda r, _p: r.update(
                consumed_handoff_ids=["handoff-never-published"])),
        )
        for index, (field, mutate) in enumerate(mutations, 1):
            with self.subTest(field=field):
                root = str(Path(self.tmp) / f"binding-{index}")
                self.cli("init-review", "--root", root,
                         "--review-id", f"review-binding-{index}")
                started = self.cli(
                    "start-run", "--root", root, "--phase-id", "phase-01",
                    "--skill-id", "systematic-review", "--run-id", f"run-{index}",
                    "--input", f"protocol={self.protocol}",
                )
                planted = Path(self.tmp) / f"planted-{index}.json"
                planted.write_text('{"planted":true}', encoding="utf-8")
                manifest = Path(started["run_dir"]) / wl.INPUTS_MANIFEST_NAME
                record = json.loads(manifest.read_text())
                mutate(record, planted)
                manifest.write_text(
                    json.dumps(record, sort_keys=True, separators=(",", ":"))
                )
                output = self.produce(started, f"out-{index}.json")
                ledger = Path(root) / "ledger" / "execution.jsonl"
                before = len(ledger.read_text().splitlines())
                message = self.refused(
                    "complete-run", "--run-dir", started["run_dir"],
                    "--output", f"result={output}",
                )
                self.assertIn("inputs changed after RUN_STARTED", message)
                self.assertEqual(len(ledger.read_text().splitlines()), before)
                self.assertFalse(
                    (Path(started["run_dir"]) / wl.RUN_MANIFEST_NAME).exists()
                )

    def test_deleted_handoff_id_stays_used_case_insensitively(self) -> None:
        _started, artifact, published = self.locked_handoff("Handoff-R10")
        shutil.rmtree(published["handoff_dir"])
        before = self.ledger_lines()
        for handoff_id in ("Handoff-R10", "handoff-r10"):
            message = self.refused(
                "create-handoff", "--root", self.workspace,
                "--producer-run-id", "run-producer",
                "--consumer-skill", "systematic-review-protocol",
                "--handoff-id", handoff_id,
                "--artifact", f"approved-contract={artifact}",
            )
            self.assertIn("ledger", message)
            self.assertEqual(self.ledger_lines(), before)

    def test_phase_case_is_refused_by_both_run_creators(self) -> None:
        self.start(phase="phase-06", run="run-006")
        source = Path(self.tmp) / "legacy.json"
        source.write_text('{"legacy":true}', encoding="utf-8")
        before = self.ledger_lines()
        self.assertIn("case-collides", self.refused(
            "start-run", "--root", self.workspace, "--phase-id", "PHASE-06",
            "--skill-id", "systematic-review", "--run-id", "run-007"))
        self.assertIn("case-collides", self.refused(
            "register-legacy-run", "--root", self.workspace,
            "--phase-id", "PHASE-06", "--skill-id", "systematic-review",
            "--run-id", "legacy-007", "--legacy-status", "LOCKED",
            "--artifact", f"legacy={source}"))
        self.assertEqual(self.ledger_lines(), before)

    def test_parent_must_still_have_its_reconciled_terminal_record(self) -> None:
        parent = self.start(phase="phase-01", run="run-parent")
        output = self.produce(parent)
        self.cli("complete-run", "--run-dir", parent["run_dir"],
                 "--output", f"result={output}", "--status", "LOCKED")
        (Path(parent["run_dir"]) / wl.RUN_MANIFEST_NAME).unlink()
        before = self.ledger_lines()
        message = self.refused(
            "start-run", "--root", self.workspace, "--phase-id", "phase-02",
            "--skill-id", "systematic-review", "--run-id", "run-child",
            "--parent-run-id", "run-parent",
        )
        self.assertIn("disagrees with the ledger", message)
        self.assertEqual(self.ledger_lines(), before)

    def test_symlinked_phase_is_refused_by_run_and_handoff_readers(self) -> None:
        started, _artifact, published = self.locked_handoff()
        phase = Path(self.workspace) / "runs" / "phase-01"
        actual = Path(self.tmp) / "moved-phase"
        phase.rename(actual)
        phase.symlink_to(actual, target_is_directory=True)
        self.assertIn("symlink", self.refused(
            "inspect-run", "--run-dir", started["run_dir"]))
        self.assertIn("symlink", self.refused(
            "verify-handoff", "--path", published["handoff_dir"],
            "--consumer-skill", "systematic-review-protocol"))

    def test_handoff_content_and_review_boundary_are_enforced(self) -> None:
        _started, _artifact, published = self.locked_handoff()
        original = Path(published["handoff_manifest"])
        renamed = original.with_name("renamed-record.json")
        original.rename(renamed)
        before = self.ledger_lines()
        message = self.refused(
            "start-run", "--root", self.workspace, "--phase-id", "phase-02",
            "--skill-id", "systematic-review-search-design",
            "--run-id", "wrong-consumer", "--input", f"handoff={renamed}")
        self.assertIn("addressed to", message)
        self.assertEqual(self.ledger_lines(), before)

        other = str(Path(self.tmp) / "other-review")
        self.cli("init-review", "--root", other, "--review-id", "review-002")
        other_raw = Path(other) / "raw.json"
        other_raw.write_text('{"raw":true}', encoding="utf-8")
        message = self.refused(
            "start-run", "--root", self.workspace, "--phase-id", "phase-03",
            "--skill-id", "systematic-review", "--run-id", "cross-review",
            "--input", f"raw={other_raw}")
        self.assertIn("belongs to review", message)
        self.assertIn("legacy registration", message)
        self.assertEqual(self.ledger_lines(), before)

    def test_raw_inputs_and_root_aliases_remain_valid(self) -> None:
        self.start(phase="phase-01", run="external-raw")
        same = Path(self.workspace) / "same-review.json"
        same.write_text('{"same":true}', encoding="utf-8")
        self.cli(
            "start-run", "--root", self.workspace, "--phase-id", "phase-02",
            "--skill-id", "systematic-review", "--run-id", "same-review",
            "--input", f"same={same}")

        started, _artifact, published = self.locked_handoff("alias-handoff")
        if str(Path(self.workspace).resolve()) == self.workspace:
            self.skipTest("temporary root has no equivalent path alias")
        self.assertTrue(self.cli(
            "inspect-run", "--run-dir", str(Path(started["run_dir"]).resolve())
        )["verified"])
        self.assertTrue(self.cli(
            "verify-handoff", "--path", str(Path(published["handoff_dir"]).resolve()),
            "--consumer-skill", "systematic-review-protocol")["verified"])

    def test_completed_and_legacy_parents_remain_valid(self) -> None:
        parent = self.start(phase="phase-01", run="completed-parent")
        output = self.produce(parent)
        self.cli("complete-run", "--run-dir", parent["run_dir"],
                 "--output", f"result={output}")
        self.cli(
            "start-run", "--root", self.workspace, "--phase-id", "phase-02",
            "--skill-id", "systematic-review", "--run-id", "completed-child",
            "--parent-run-id", "completed-parent")

        source = Path(self.tmp) / "legacy-parent.json"
        source.write_text('{"legacy":true}', encoding="utf-8")
        self.cli(
            "register-legacy-run", "--root", self.workspace,
            "--phase-id", "phase-03", "--skill-id", "systematic-review",
            "--run-id", "legacy-parent", "--legacy-status", "LOCKED",
            "--artifact", f"legacy={source}")
        child = self.cli(
            "start-run", "--root", self.workspace, "--phase-id", "phase-04",
            "--skill-id", "systematic-review", "--run-id", "legacy-child",
            "--parent-run-id", "legacy-parent")
        inputs = json.loads((Path(child["run_dir"]) /
                             wl.INPUTS_MANIFEST_NAME).read_text())
        self.assertEqual(inputs["parent_run_ids"], ["legacy-parent"])

    def test_historical_terminal_reads_and_unbound_inflight_only_fails(self) -> None:
        old = self.historical_started("phase-01", "old-inflight")
        output = Path(old["run_dir"]) / "outputs" / "old.json"
        output.write_text('{"old":true}', encoding="utf-8")
        self.assertIn("predates RUN_STARTED input binding", self.refused(
            "complete-run", "--run-dir", old["run_dir"],
            "--output", f"result={output}"))
        self.cli("fail-run", "--run-dir", old["run_dir"],
                 "--reason-code", "HISTORICAL_RETRY_REQUIRED",
                 "--message", "retry under binding")
        self.assertEqual(self.cli(
            "inspect-run", "--run-dir", old["run_dir"])["status"],
            wl.STATUS_FAILED)

        terminal_old = self.historical_started("phase-02", "old-terminal")
        artifact = Path(terminal_old["run_dir"]) / "outputs" / "locked.json"
        artifact.write_text('{"locked":true}', encoding="utf-8")
        terminal = wl.append_workspace_event(
            self.workspace, wl.EVENT_RUN_LOCKED,
            {"review_id": "review-001", "phase_id": "phase-02",
             "skill_id": "systematic-review", "run_id": "old-terminal"})
        record = {
            "schema_version": wl.SCHEMA_VERSION, "record_type": wl.RECORD_RUN,
            "review_id": "review-001", "phase_id": "phase-02",
            "skill_id": "systematic-review", "run_id": "old-terminal",
            "status": wl.STATUS_LOCKED,
            "inputs_manifest": ref(Path(terminal_old["run_dir"]) /
                                   wl.INPUTS_MANIFEST_NAME,
                                   "inputs-manifest", status="INTERNAL_LOCKED"),
            "outputs": [ref(artifact, "result")], "parent_run_ids": [],
            "consumed_handoff_ids": [], "downstream_consumers": [],
            "start_ledger_sequence": terminal_old["inputs"]["start_ledger_sequence"],
            "terminal_ledger_sequence": terminal["sequence"],
            "created_at": terminal_old["inputs"]["created_at"],
            "completed_at": wl.utc_timestamp(),
            "timestamp_assurance": wl.TIMESTAMP_ASSURANCE,
            "tool_version": wl.TOOL_VERSION,
        }
        wl.write_new_json(self.workspace, str(Path(terminal_old["run_dir"]) /
                          wl.RUN_MANIFEST_NAME), record)
        self.assertEqual(self.cli(
            "inspect-run", "--run-dir", terminal_old["run_dir"])["status"],
            wl.STATUS_LOCKED)


if __name__ == "__main__":
    unittest.main()
