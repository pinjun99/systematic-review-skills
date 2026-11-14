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

"""Tests for the shipped workspace registry and producer/consumer lifecycle.

Registry tests check ownership, terminal outputs, and consumer routes.
Integration tests exercise real handoffs, corrections, and input integrity.
Lean skills omit the former lifecycle sections and command examples.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
SHARED = ROOT / ".agents" / "shared"
SKILLS = ROOT / ".agents" / "skills"
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))

import artifact_ref  # noqa: E402
import workspace_lifecycle as wl  # noqa: E402


REGISTRY_PATH = SHARED / "references" / "workspace-adoption.json"
REGISTRY = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))

# Brief 20 adopts phases 1 through 10. Brief 21 adds the rest; this list is a
# subset assertion so a later brief extends the registry without editing it.
BRIEF_20_SKILLS = (
    "systematic-review",
    "systematic-review-protocol",
    "systematic-review-search-design",
    "systematic-review-search-execution",
    "systematic-review-deduplication",
    "systematic-review-title-abstract-screening",
    "systematic-review-full-text-retrieval",
    "systematic-review-full-text-screening",
)

BRIEF_21_SKILLS = (
    "systematic-review-data-extraction",
    "systematic-review-risk-of-bias",
    "systematic-review-synthesis-planning",
    "systematic-review-structured-synthesis",
    "systematic-review-certainty-of-evidence",
    "systematic-review-reporting-package",
    "systematic-review-independent-quality-control",
)

# Phase 14 meta-analysis and Phases 19-20 are deferred. Nothing in this layer
# may represent them, because a representation implies the branch exists.
DEFERRED_PHASES = ("phase-14", "phase-19", "phase-20")

REQUIRED_ENTRY_FIELDS = (
    "phase_id",
    "skill_id",
    "phases",
    "material_run",
    "advisory_examples",
    "terminal_status",
    "owned_outputs",
    "consumers",
)


def skill_text(skill_id: str) -> str:
    return (SKILLS / skill_id / "SKILL.md").read_text(encoding="utf-8")


class RegistryTests(unittest.TestCase):
    """The registry is the machine-readable half of the contract."""

    def test_envelope(self) -> None:
        self.assertEqual(REGISTRY["schema_version"], wl.SCHEMA_VERSION)
        self.assertTrue(REGISTRY["tool_version"])
        self.assertIn(20, REGISTRY["adopted_briefs"])

    def test_every_brief_20_skill_is_registered_once(self) -> None:
        registered = REGISTRY["skills"]
        for skill_id in BRIEF_20_SKILLS:
            self.assertIn(skill_id, registered, f"{skill_id} is not adopted")
            self.assertEqual(registered[skill_id]["skill_id"], skill_id)
        self.assertEqual(
            len(registered), len(set(registered)), "duplicate registry keys"
        )

    def test_identifiers_are_valid_workspace_identifiers(self) -> None:
        phases = []
        for skill_id, entry in REGISTRY["skills"].items():
            wl.validate_identifier(entry["phase_id"], "phase_id")
            wl.validate_identifier(entry["skill_id"], "skill_id")
            phases.append(entry["phase_id"])
            roles = [output["role"] for output in entry["owned_outputs"]]
            self.assertTrue(roles, f"{skill_id} declares no owned output")
            wl.validate_unique_identifiers(roles, f"{skill_id} roles")
        wl.validate_unique_identifiers(phases, "phase_id")

    def test_entries_are_complete_and_well_formed(self) -> None:
        for skill_id, entry in REGISTRY["skills"].items():
            for field in REQUIRED_ENTRY_FIELDS:
                self.assertIn(field, entry, f"{skill_id} is missing {field}")
            self.assertIn(
                entry["terminal_status"], wl.TERMINAL_SUCCESS_STATUSES, skill_id
            )
            self.assertTrue(entry["material_run"].strip(), skill_id)
            self.assertTrue(entry["advisory_examples"], skill_id)
            for output in entry["owned_outputs"]:
                self.assertTrue(output["description"].strip(), output["role"])

    def test_a_skill_id_names_a_real_skill(self) -> None:
        for skill_id in REGISTRY["skills"]:
            self.assertTrue((SKILLS / skill_id).is_dir(), skill_id)
            self.assertTrue((SKILLS / skill_id / "SKILL.md").is_file(), skill_id)

    def test_consumers_are_real_skills_with_honest_adoption_flags(self) -> None:
        registered = set(REGISTRY["skills"])
        for skill_id, entry in REGISTRY["skills"].items():
            owned = {output["role"] for output in entry["owned_outputs"]}
            seen = []
            for consumer in entry["consumers"]:
                target = consumer["consumer_skill"]
                self.assertTrue((SKILLS / target).is_dir(), target)
                self.assertNotEqual(target, skill_id, "a skill cannot consume itself")
                seen.append(target)
                self.assertTrue(consumer["artifact_roles"], f"{skill_id}->{target}")
                for role in consumer["artifact_roles"]:
                    self.assertIn(
                        role, owned, f"{skill_id} routes {role}, which it does not own"
                    )
                self.assertEqual(
                    consumer["consumer_adopted"],
                    target in registered,
                    f"{skill_id}->{target} adoption flag disagrees with the registry",
                )
            self.assertEqual(len(seen), len(set(seen)), f"{skill_id} duplicate consumer")

    def test_no_registry_entry_names_a_downstream_directory(self) -> None:
        """A producer declares routes, never paths belonging to a consumer."""
        blob = json.dumps(REGISTRY)
        for phase in (entry["phase_id"] for entry in REGISTRY["skills"].values()):
            self.assertNotIn(f"runs/{phase}", blob)

    def test_all_fifteen_v1_skills_are_registered_exactly_once(self) -> None:
        registered = REGISTRY["skills"]
        for skill_id in BRIEF_20_SKILLS + BRIEF_21_SKILLS:
            self.assertIn(skill_id, registered, f"{skill_id} is not adopted")
        on_disk = sorted(
            path.name
            for path in SKILLS.iterdir()
            if (path / "SKILL.md").is_file()
            and not path.name.startswith("systematic-review-v2")
        )
        self.assertEqual(sorted(registered), on_disk, "registry and skills differ")
        self.assertEqual(len(registered), 15)
        self.assertEqual(REGISTRY["adopted_briefs"], [20, 21])

    def test_no_deferred_phase_is_represented(self) -> None:
        """Representing Phase 14 or 19-20 would imply the branch exists."""
        blob = json.dumps(REGISTRY)
        for entry in REGISTRY["skills"].values():
            self.assertNotIn(entry["phase_id"], DEFERRED_PHASES)
        for phase in DEFERRED_PHASES:
            self.assertNotIn(f"runs/{phase}", blob)
            for skill_id in REGISTRY["skills"]:
                self.assertNotIn(f"runs/{phase}", skill_text(skill_id), skill_id)

        plan = REGISTRY["skills"]["systematic-review-synthesis-planning"]
        deferred = plan["deferred_branches"]
        self.assertIn("META_ANALYSIS_PLANNED", deferred)
        self.assertIn("no handoff", deferred)
        self.assertIn("deferred", deferred)
        routed = {consumer["consumer_skill"] for consumer in plan["consumers"]}
        self.assertEqual(
            routed,
            {
                "systematic-review-structured-synthesis",
                "systematic-review-certainty-of-evidence",
            },
            "Phase 13 routes only to branches that exist",
        )

    def test_sqlite_locks_are_terminal_output_roles(self) -> None:
        """Phase 11 and 12 keep their stores; the wrapper references them."""
        for skill_id, store, lock in (
            (
                "systematic-review-data-extraction",
                "extraction-store",
                "extraction-dataset-lock",
            ),
            (
                "systematic-review-risk-of-bias",
                "risk-of-bias-store",
                "risk-of-bias-lock",
            ),
        ):
            entry = REGISTRY["skills"][skill_id]
            roles = {output["role"] for output in entry["owned_outputs"]}
            self.assertIn(store, roles, f"{skill_id} store is not a terminal output")
            self.assertIn(lock, roles, f"{skill_id} lock is not a terminal output")
            self.assertEqual(entry["terminal_status"], wl.STATUS_LOCKED, skill_id)

    def test_correction_branches_create_new_runs(self) -> None:
        for skill_id in (
            "systematic-review-reporting-package",
            "systematic-review-independent-quality-control",
        ):
            entry = REGISTRY["skills"][skill_id]
            branch = entry["correction_branch"]
            self.assertIn("NEW run", branch, skill_id)
            self.assertIn("parent_run_ids", branch, skill_id)
        preserved = REGISTRY["skills"]["systematic-review-reporting-package"][
            "correction_branch"
        ]
        self.assertIn("byte-for-byte", preserved)

    def test_phase_18_is_declared_read_only_toward_its_inputs(self) -> None:
        entry = REGISTRY["skills"]["systematic-review-independent-quality-control"]
        self.assertTrue(entry["read_only_toward_inputs"])
        for output in entry["owned_outputs"]:
            description = output["description"]
            self.assertTrue(
                "New versioned" in description or "never overwritten" in description,
                f"{output['role']} does not declare itself a new versioned output",
            )
        roles = {output["role"] for output in entry["owned_outputs"]}
        self.assertEqual(
            roles, {"audit-register", "correction-register", "qc-package-lock"}
        )


class SkillDocumentationTests(unittest.TestCase):
    """Skills must not instruct producers to write into consumer directories."""

    def test_no_skill_instructs_a_producer_to_create_a_consumer_directory(self) -> None:
        others = {
            entry["phase_id"] for entry in REGISTRY["skills"].values()
        }
        for skill_id, entry in REGISTRY["skills"].items():
            section = skill_text(skill_id)
            self.assertNotIn("mkdir", section, f"{skill_id} tells a producer to mkdir")
            for foreign in others - {entry["phase_id"]}:
                self.assertNotIn(
                    f"runs/{foreign}/{foreign}",
                    section,
                    f"{skill_id} writes into {foreign}",
                )
            # Any run directory the skill assigns to must be its own.
            for assigned in re.findall(r"RUN=\$REVIEW/runs/([\w.-]+)/", section):
                self.assertEqual(assigned, entry["phase_id"], skill_id)


class FixtureHarness(unittest.TestCase):
    """Shared harness for driving real chains. Holds no tests of its own."""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.review = str(Path(self.tmp) / "review")
        wl.initialize_review(self.review, review_id="review-001")

    def entry(self, skill_id: str) -> dict:
        return REGISTRY["skills"][skill_id]

    def run_phase(self, skill_id: str, *, inputs=(), suffix: str = "001",
                  parent_run_ids=()) -> dict:
        entry = self.entry(skill_id)
        phase = entry["phase_id"]
        run_id = "run-" + phase[len("phase-"):] + "-" + suffix
        started = wl.start_run(
            self.review,
            phase_id=phase,
            skill_id=skill_id,
            run_id=run_id,
            inputs=list(inputs),
            parent_run_ids=list(parent_run_ids),
        )
        outputs = []
        for output in entry["owned_outputs"]:
            path = Path(started["outputs_dir"]) / f"{output['role']}.json"
            path.write_text(
                json.dumps({"role": output["role"], "phase": phase}), encoding="utf-8"
            )
            outputs.append(
                artifact_ref.make_artifact_ref(
                    str(path), output["role"], "1.0", "REFERENCED"
                )
            )
        wl.complete_run(
            started["run_dir"],
            outputs=outputs,
            status=entry["terminal_status"],
            downstream_consumers=[
                consumer["consumer_skill"] for consumer in entry["consumers"]
            ],
        )
        return {
            "run_id": run_id,
            "phase_id": phase,
            "run_dir": started["run_dir"],
            "outputs": {ref["role"]: ref for ref in outputs},
        }

    def publish(self, produced: dict, *, consumer: str, handoff_id: str,
                roles) -> dict:
        return wl.create_handoff(
            self.review,
            producer_run_id=produced["run_id"],
            consumer_skill=consumer,
            handoff_id=handoff_id,
            artifacts=[produced["outputs"][role] for role in roles],
        )

    def phases_on_disk(self) -> list:
        runs = Path(self.review) / "runs"
        return sorted(p.name for p in runs.iterdir()) if runs.is_dir() else []

    def consume(self, handoff: dict, *, consumer: str) -> list:
        """What a consumer feeds into its own start-run."""
        verified = wl.verify_handoff(handoff["handoff_dir"], consumer_skill=consumer)
        self.assertTrue(verified["verified"])
        manifest = wl.read_json(handoff["handoff_manifest"])
        inputs = list(manifest["artifacts"])
        inputs.append(
            artifact_ref.make_artifact_ref(
                handoff["handoff_manifest"], "upstream-handoff", "1.0", "INTERNAL_LOCKED"
            )
        )
        return inputs


class EarlyChainFixture(FixtureHarness):
    """Phases 1-10: chained delivery and one producer feeding two consumers."""

    def test_phase_08_to_09_to_10a_chain(self) -> None:
        dedup = self.run_phase("systematic-review-deduplication")
        to_screening = self.publish(
            dedup,
            consumer="systematic-review-title-abstract-screening",
            handoff_id="handoff-08-001",
            roles=["screening-ready-citation-set"],
        )
        self.assertEqual(self.phases_on_disk(), ["phase-08"])

        screening = self.run_phase(
            "systematic-review-title-abstract-screening",
            inputs=self.consume(
                to_screening, consumer="systematic-review-title-abstract-screening"
            ),
        )
        consumed = wl.read_json(
            str(Path(screening["run_dir"]) / "inputs_manifest.json")
        )
        self.assertEqual(consumed["consumed_handoff_ids"], ["handoff-08-001"])
        self.assertEqual(self.phases_on_disk(), ["phase-08", "phase-09"])

        to_retrieval = self.publish(
            screening,
            consumer="systematic-review-full-text-retrieval",
            handoff_id="handoff-09-001",
            roles=["phase-10-full-text-handoff"],
        )
        retrieval = self.run_phase(
            "systematic-review-full-text-retrieval",
            inputs=self.consume(
                to_retrieval, consumer="systematic-review-full-text-retrieval"
            ),
        )
        self.assertEqual(
            self.phases_on_disk(), ["phase-08", "phase-09", "phase-10a"]
        )

        state = wl.generate_review_state(self.review)
        self.assertEqual(
            sorted(state["phases"]), ["phase-08", "phase-09", "phase-10a"]
        )
        for phase in state["phases"].values():
            self.assertIn(phase["status"], wl.TERMINAL_SUCCESS_STATUSES)
            self.assertTrue(phase["required_inputs_available"])
        self.assertTrue(Path(retrieval["run_dir"], "run_manifest.json").is_file())

    # -- fixture 2: one producer, a near and a distant consumer ------------

    def test_one_locked_contract_routes_to_two_consumers_independently(self) -> None:
        protocol = self.run_phase("systematic-review-protocol")
        bundle = [
            "canonical-eligibility-contract",
            "eligibility-projection-comparison",
            "eligibility-approval-receipt",
        ]
        near = self.publish(
            protocol,
            consumer="systematic-review-title-abstract-screening",
            handoff_id="handoff-06-to-09",
            roles=bundle,
        )
        far = self.publish(
            protocol,
            consumer="systematic-review-full-text-screening",
            handoff_id="handoff-06-to-10b",
            roles=bundle,
        )

        # The producer created neither consumer's run nor output directory.
        self.assertEqual(self.phases_on_disk(), ["phase-06"])
        for published in (near, far):
            self.assertEqual(
                sorted(p.name for p in Path(published["handoff_dir"]).iterdir()),
                ["handoff_manifest.json"],
            )

        # Each consumer is addressed exactly, and neither can read the other's.
        wl.verify_handoff(
            near["handoff_dir"],
            consumer_skill="systematic-review-title-abstract-screening",
        )
        wl.verify_handoff(
            far["handoff_dir"],
            consumer_skill="systematic-review-full-text-screening",
        )
        with self.assertRaises(wl.WorkspaceLifecycleError):
            wl.verify_handoff(
                near["handoff_dir"],
                consumer_skill="systematic-review-full-text-screening",
            )

        # The consumer creates its own run when it starts, not before.
        self.run_phase(
            "systematic-review-title-abstract-screening",
            inputs=self.consume(
                near, consumer="systematic-review-title-abstract-screening"
            ),
        )
        self.assertEqual(self.phases_on_disk(), ["phase-06", "phase-09"])

        state = wl.generate_review_state(self.review)
        self.assertEqual(sorted(state["phases"]), ["phase-06", "phase-09"])
        self.assertEqual(state["phases"]["phase-06"]["status"], wl.STATUS_LOCKED)

    def test_a_distant_handoff_survives_until_its_consumer_runs(self) -> None:
        """A Phase 6 artifact Phase 10b needs may be published early."""
        protocol = self.run_phase("systematic-review-protocol")
        far = self.publish(
            protocol,
            consumer="systematic-review-full-text-screening",
            handoff_id="handoff-06-to-10b",
            roles=["canonical-eligibility-contract"],
        )
        # Phases 7 through 10a happen in between; the handoff still verifies.
        self.run_phase("systematic-review-deduplication")
        verified = wl.verify_handoff(
            far["handoff_dir"],
            consumer_skill="systematic-review-full-text-screening",
        )
        self.assertEqual(verified["producer_run_id"], protocol["run_id"])
        self.assertEqual(verified["producer_status"], wl.STATUS_LOCKED)
        self.assertNotIn("phase-10b", self.phases_on_disk())


class LateChainFixture(FixtureHarness):
    """Phases 11-18, including the correction and re-audit branches."""

    def test_phase_11_fans_out_to_12_and_13(self) -> None:
        extraction = self.run_phase("systematic-review-data-extraction")
        to_rob = self.publish(
            extraction,
            consumer="systematic-review-risk-of-bias",
            handoff_id="handoff-11-to-12",
            roles=["extraction-dataset-lock", "extraction-store"],
        )
        to_plan = self.publish(
            extraction,
            consumer="systematic-review-synthesis-planning",
            handoff_id="handoff-11-to-13",
            roles=["extraction-dataset-lock"],
        )
        # One locked dataset, two independent routes, nothing created for either.
        self.assertEqual(self.phases_on_disk(), ["phase-11"])

        self.run_phase(
            "systematic-review-risk-of-bias",
            inputs=self.consume(to_rob, consumer="systematic-review-risk-of-bias"),
        )
        self.run_phase(
            "systematic-review-synthesis-planning",
            inputs=self.consume(
                to_plan, consumer="systematic-review-synthesis-planning"
            ),
        )
        self.assertEqual(
            self.phases_on_disk(), ["phase-11", "phase-12", "phase-13"]
        )
        state = wl.generate_review_state(self.review)
        for phase in state["phases"].values():
            self.assertEqual(phase["status"], wl.STATUS_LOCKED)

    def test_phase_13_routes_only_branches_that_exist(self) -> None:
        plan = self.run_phase("systematic-review-synthesis-planning")
        to_structured = self.publish(
            plan,
            consumer="systematic-review-structured-synthesis",
            handoff_id="handoff-13-to-13b",
            roles=["synthesis-plan-v1", "analysis-dataset-lock"],
        )
        self.publish(
            plan,
            consumer="systematic-review-certainty-of-evidence",
            handoff_id="handoff-13-to-15",
            roles=["synthesis-plan-v1", "synthesis-classification"],
        )
        # The deferred meta-analysis branch gets no handoff and no directory.
        self.assertEqual(self.phases_on_disk(), ["phase-13"])
        published = sorted(
            path.name
            for path in (Path(self.review) / "handoffs" / plan["run_id"]).iterdir()
        )
        self.assertEqual(
            published,
            [
                "systematic-review-certainty-of-evidence",
                "systematic-review-structured-synthesis",
            ],
        )
        for phase in DEFERRED_PHASES:
            self.assertFalse((Path(self.review) / "runs" / phase).exists(), phase)

        self.run_phase(
            "systematic-review-structured-synthesis",
            inputs=self.consume(
                to_structured, consumer="systematic-review-structured-synthesis"
            ),
        )
        self.assertEqual(self.phases_on_disk(), ["phase-13", "phase-13b"])

    def test_phase_15_to_16_to_18_chain(self) -> None:
        certainty = self.run_phase("systematic-review-certainty-of-evidence")
        to_reporting = self.publish(
            certainty,
            consumer="systematic-review-reporting-package",
            handoff_id="handoff-15-to-16",
            roles=["certainty-package", "summary-of-findings"],
        )
        reporting = self.run_phase(
            "systematic-review-reporting-package",
            inputs=self.consume(
                to_reporting, consumer="systematic-review-reporting-package"
            ),
        )
        to_audit = self.publish(
            reporting,
            consumer="systematic-review-independent-quality-control",
            handoff_id="handoff-16-to-18",
            roles=["reporting-package-lock", "phase-18-input"],
        )
        audit = self.run_phase(
            "systematic-review-independent-quality-control",
            inputs=self.consume(
                to_audit, consumer="systematic-review-independent-quality-control"
            ),
        )
        self.assertEqual(
            self.phases_on_disk(), ["phase-15", "phase-16-17", "phase-18"]
        )
        self.assertTrue(Path(audit["run_dir"], "run_manifest.json").is_file())
        state = wl.generate_review_state(self.review)
        self.assertEqual(state["phases"]["phase-18"]["runs"], ["run-18-001"])

    def test_a_correction_creates_new_runs_and_never_mutates_a_locked_one(self) -> None:
        reporting = self.run_phase("systematic-review-reporting-package")
        to_audit = self.publish(
            reporting,
            consumer="systematic-review-independent-quality-control",
            handoff_id="handoff-16-to-18",
            roles=["reporting-package-lock", "phase-18-input"],
        )
        audit = self.run_phase(
            "systematic-review-independent-quality-control",
            inputs=self.consume(
                to_audit, consumer="systematic-review-independent-quality-control"
            ),
        )
        corrections = self.publish(
            audit,
            consumer="systematic-review-reporting-package",
            handoff_id="handoff-18-to-16",
            roles=["correction-register", "qc-package-lock"],
        )

        original_reporting = Path(reporting["run_dir"], "run_manifest.json").read_bytes()
        original_audit = Path(audit["run_dir"], "run_manifest.json").read_bytes()

        # Revision mode: a NEW run that names the superseded one as its parent.
        revised = self.run_phase(
            "systematic-review-reporting-package",
            suffix="002",
            parent_run_ids=[reporting["run_id"]],
            inputs=self.consume(
                corrections, consumer="systematic-review-reporting-package"
            ),
        )
        to_reaudit = self.publish(
            revised,
            consumer="systematic-review-independent-quality-control",
            handoff_id="handoff-16-002-to-18",
            roles=["reporting-package-lock", "phase-18-input"],
        )
        reaudit = self.run_phase(
            "systematic-review-independent-quality-control",
            suffix="002",
            parent_run_ids=[audit["run_id"]],
            inputs=self.consume(
                to_reaudit, consumer="systematic-review-independent-quality-control"
            ),
        )

        # Neither locked predecessor changed by a single byte.
        self.assertEqual(
            Path(reporting["run_dir"], "run_manifest.json").read_bytes(),
            original_reporting,
        )
        self.assertEqual(
            Path(audit["run_dir"], "run_manifest.json").read_bytes(), original_audit
        )

        for new_run, parent in (
            (revised, reporting["run_id"]),
            (reaudit, audit["run_id"]),
        ):
            manifest = wl.read_json(str(Path(new_run["run_dir"]) / "run_manifest.json"))
            self.assertEqual(manifest["parent_run_ids"], [parent])

        # A locked run cannot be re-completed to absorb the correction.
        with self.assertRaises(wl.WorkspaceLifecycleError) as caught:
            wl.complete_run(
                reporting["run_dir"],
                outputs=list(reporting["outputs"].values()),
                status=wl.STATUS_LOCKED,
            )
        self.assertIn("a correction is a new run", str(caught.exception))

        state = wl.generate_review_state(self.review)
        self.assertEqual(
            state["phases"]["phase-16-17"]["runs"], ["run-16-17-001", "run-16-17-002"]
        )
        self.assertEqual(
            state["phases"]["phase-18"]["runs"], ["run-18-001", "run-18-002"]
        )

    def test_phase_18_cannot_complete_after_editing_an_audited_input(self) -> None:
        """Read-only is enforced, not merely documented."""
        reporting = self.run_phase("systematic-review-reporting-package")
        to_audit = self.publish(
            reporting,
            consumer="systematic-review-independent-quality-control",
            handoff_id="handoff-16-to-18",
            roles=["reporting-package-lock", "manuscript"],
        )
        inputs = self.consume(
            to_audit, consumer="systematic-review-independent-quality-control"
        )
        entry = self.entry("systematic-review-independent-quality-control")
        started = wl.start_run(
            self.review,
            phase_id=entry["phase_id"],
            skill_id=entry["skill_id"],
            run_id="run-18-001",
            inputs=inputs,
        )
        outputs = []
        for output in entry["owned_outputs"]:
            path = Path(started["outputs_dir"]) / f"{output['role']}.json"
            path.write_text(json.dumps({"role": output["role"]}), encoding="utf-8")
            outputs.append(
                artifact_ref.make_artifact_ref(
                    str(path), output["role"], "1.0", "REFERENCED"
                )
            )

        # The auditor edits the manuscript it was auditing.
        audited = Path(reporting["outputs"]["manuscript"]["path"])
        audited.write_text(
            json.dumps({"role": "manuscript", "edited_by": "the auditor"}),
            encoding="utf-8",
        )

        with self.assertRaises(wl.WorkspaceLifecycleError) as caught:
            wl.complete_run(
                started["run_dir"], outputs=outputs, status=wl.STATUS_LOCKED
            )
        self.assertIn("hash mismatch", str(caught.exception))
        self.assertFalse(
            (Path(started["run_dir"]) / "run_manifest.json").exists(),
            "an audit that edited its input must not reach a terminal state",
        )


if __name__ == "__main__":
    unittest.main()
