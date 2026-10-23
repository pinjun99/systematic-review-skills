#!/usr/bin/env python3
"""Known-answer tests for the finite-population screening audit policy.

The sizing figures below were derived independently during the assurance
review and are reproduced here as fixed expectations, so a future change to the
arithmetic cannot pass silently.
"""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path
import sys
import unittest


SHARED = Path(__file__).resolve().parents[1]
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))

from audit_policy import (  # noqa: E402
    AuditPolicyError,
    DETECTION_SCOPE,
    ENRICHED_SCOPE,
    OUTCOME_ACCEPT,
    OUTCOME_DISABLE,
    OUTCOME_EXPAND,
    PROBABILITY_SCOPE,
    assert_not_a_production_claim,
    challenge_set_result,
    classify_legacy_audit,
    detection_only_result,
    evaluate_two_stage,
    frozen_permutation,
    plan_audit,
    probability_zero_found,
    sample_size_exact,
    select_seeded_sample,
    upper_bound_undetected,
    validate_policy,
)


def policy(**overrides):
    value = {
        "schema_version": "1.0",
        "policy_version": "audit-1.0",
        "seed": "REVIEW-1-PHASE9-AUDIT",
        "unit": "CITATION_RECORD",
        "alpha": 0.05,
        "stage_alpha": {"stage_1": 0.03, "stage_2": 0.02},
        "first_unacceptable_missed_records": 3,
        "maximum_tolerated_missed_records": 2,
        "high_risk_strata": ["NO_ABSTRACT", "NON_ENGLISH"],
        "high_risk_items": [],
        "confirmation_fraction": 0.1,
    }
    value.update(overrides)
    return value


class ExactSizingTests(unittest.TestCase):
    """Known answers. These numbers are the reason for exact arithmetic."""

    def test_headline_case_matches_the_reviewed_figure(self):
        self.assertEqual(5684, sample_size_exact(9000, 3, 0.05))

    def test_sizing_table(self):
        cases = {1: 8550, 2: 6988, 3: 5684, 10: 2329}
        for first_unacceptable, expected in cases.items():
            self.assertEqual(
                expected,
                sample_size_exact(9000, first_unacceptable, 0.05),
                f"first_unacceptable={first_unacceptable}",
            )

    def test_ruling_out_one_bad_item_needs_95_percent_of_the_population(self):
        self.assertEqual(8550, sample_size_exact(9000, 1, 0.05))
        self.assertEqual(Fraction(8550, 9000), Fraction(95, 100))

    def test_small_population_is_affordable(self):
        self.assertEqual(316, sample_size_exact(500, 3, 0.05))

    def test_returned_size_is_minimal(self):
        n = sample_size_exact(9000, 3, 0.05)
        self.assertLessEqual(probability_zero_found(9000, 3, n), Fraction(5, 100))
        self.assertGreater(
            probability_zero_found(9000, 3, n - 1), Fraction(5, 100)
        )

    def test_infinite_population_approximation_would_be_wrong(self):
        """Rule-of-three style sizing overshoots; exactness is not cosmetic."""
        approximate = 2330  # ceil(9000 * (1 - 0.05 ** (1 / 10)))
        self.assertEqual(2329, sample_size_exact(9000, 10, 0.05))
        self.assertNotEqual(approximate, sample_size_exact(9000, 10, 0.05))

    def test_impossible_hypothesis_needs_no_sample(self):
        self.assertEqual(0, sample_size_exact(2, 5, 0.05))
        self.assertEqual(0, sample_size_exact(0, 3, 0.05))

    def test_alpha_must_be_a_probability(self):
        for bad in (0, 1, -0.1, 1.5, True):
            with self.assertRaises(AuditPolicyError):
                sample_size_exact(100, 3, bad)


class UpperBoundTests(unittest.TestCase):
    def test_zero_errors_at_the_planned_size_meets_the_tolerance(self):
        n = sample_size_exact(9000, 3, 0.05)
        self.assertEqual(2, upper_bound_undetected(9000, n, 0, 0.05))

    def test_a_census_leaves_nothing_undetected(self):
        self.assertEqual(0, upper_bound_undetected(100, 100, 0, 0.05))

    def test_bound_grows_with_observed_errors(self):
        clean = upper_bound_undetected(100, 50, 0, 0.05)
        dirty = upper_bound_undetected(100, 50, 2, 0.05)
        self.assertEqual(4, clean)
        self.assertGreater(dirty, clean)

    def test_cannot_observe_more_errors_than_records(self):
        with self.assertRaisesRegex(AuditPolicyError, "more errors than"):
            upper_bound_undetected(100, 10, 11, 0.05)


class FrozenSelectionTests(unittest.TestCase):
    def setUp(self):
        self.population = [f"REC{index:03d}" for index in range(50)]

    def test_selection_is_deterministic(self):
        first = select_seeded_sample(self.population, 10, "seed-a")
        second = select_seeded_sample(list(reversed(self.population)), 10, "seed-a")
        self.assertEqual(first, second)

    def test_a_different_seed_selects_differently(self):
        self.assertNotEqual(
            select_seeded_sample(self.population, 10, "seed-a"),
            select_seeded_sample(self.population, 10, "seed-b"),
        )

    def test_expansion_extends_the_same_permutation(self):
        ordering = frozen_permutation(self.population, "seed-a")
        small = select_seeded_sample(self.population, 10, "seed-a")
        large = select_seeded_sample(self.population, 20, "seed-a")
        self.assertEqual(small, large[:10])
        self.assertEqual(ordering[:20], large)

    def test_duplicate_identifiers_are_refused(self):
        with self.assertRaisesRegex(AuditPolicyError, "duplicate"):
            frozen_permutation(["A", "A"], "seed")


class PolicyValidationTests(unittest.TestCase):
    def test_valid_policy(self):
        value = policy()
        self.assertIs(value, validate_policy(value))

    def test_off_by_one_tolerance_is_refused(self):
        with self.assertRaisesRegex(AuditPolicyError, "supports K-1"):
            validate_policy(policy(maximum_tolerated_missed_records=3))

    def test_stage_alphas_cannot_exceed_the_total(self):
        with self.assertRaisesRegex(AuditPolicyError, "spend it"):
            validate_policy(
                policy(alpha=0.05, stage_alpha={"stage_1": 0.04, "stage_2": 0.03})
            )

    def test_stage_two_must_tighten(self):
        with self.assertRaisesRegex(AuditPolicyError, "smaller than stage_1"):
            validate_policy(
                policy(stage_alpha={"stage_1": 0.02, "stage_2": 0.03})
            )


class TwoStageTests(unittest.TestCase):
    def setUp(self):
        self.population = [f"EX{index:04d}" for index in range(400)]
        self.high_risk = self.population[:12]
        self.policy = policy(high_risk_items=list(self.high_risk))
        self.plan = plan_audit(self.policy, self.population)

    def observations(self, *, stage_1_errors=0, stage_2_errors=0, stage=1):
        records = [
            {
                "item_id": item,
                "verdict": "CORRECT",
                "role": "CENSUS",
                "reviewer_id": "HUMAN-1",
            }
            for item in self.plan["census_items"]
        ]
        items = (
            self.plan["stage_1_items"] if stage == 1 else self.plan["stage_2_items"]
        )
        errors = stage_1_errors if stage == 1 else stage_2_errors
        for index, item in enumerate(items):
            record = {
                "item_id": item,
                "verdict": "CORRECT",
                "role": "SAMPLE",
                "reviewer_id": "HUMAN-1",
            }
            if index < errors:
                record["verdict"] = "FALSE_EXCLUSION"
                record["second_reviewer_id"] = "HUMAN-2"
            elif item in set(self.plan["confirmation_items"]):
                record["second_reviewer_id"] = "HUMAN-2"
            records.append(record)
        return records

    def test_plan_splits_census_from_probability_sample(self):
        self.assertEqual(400, self.plan["population_size"])
        self.assertEqual(12, self.plan["census_size"])
        self.assertEqual(388, self.plan["remainder_size"])
        self.assertEqual(
            sample_size_exact(388, 3, 0.03), self.plan["stage_1_size"]
        )
        self.assertGreater(self.plan["stage_2_size"], self.plan["stage_1_size"])
        self.assertEqual(PROBABILITY_SCOPE, self.plan["inference_scope"])

    def test_clean_stage_one_accepts_under_its_own_alpha(self):
        result = evaluate_two_stage(
            self.policy, self.population, self.observations()
        )
        self.assertEqual(OUTCOME_ACCEPT, result["outcome"])
        self.assertEqual(1, result["stage"])
        self.assertEqual(0.03, result["alpha_spent"])
        self.assertLessEqual(
            result["upper_bound_undetected"],
            result["maximum_tolerated_missed_records"],
        )

    def test_an_error_forces_expansion_to_stage_two(self):
        result = evaluate_two_stage(
            self.policy, self.population, self.observations(stage_1_errors=1)
        )
        self.assertEqual(OUTCOME_EXPAND, result["outcome"])
        self.assertIsNone(result["upper_bound_undetected"])
        self.assertTrue(result["pending_stage_2_items"])
        # Expansion may only take the next frozen entries.
        expected = [
            item
            for item in self.plan["stage_2_items"]
            if item not in set(self.plan["stage_1_items"])
        ]
        self.assertEqual(sorted(expected), result["pending_stage_2_items"])

    def test_stage_two_with_errors_disables_automation(self):
        result = evaluate_two_stage(
            self.policy,
            self.population,
            self.observations(stage_2_errors=3, stage=2),
        )
        self.assertEqual(2, result["stage"])
        self.assertEqual(OUTCOME_DISABLE, result["outcome"])
        self.assertGreater(
            result["upper_bound_undetected"],
            result["maximum_tolerated_missed_records"],
        )

    def test_uncertain_counts_as_an_error(self):
        records = self.observations()
        target = self.plan["stage_1_items"][0]
        for record in records:
            if record["item_id"] == target:
                record["verdict"] = "UNCERTAIN"
                record["second_reviewer_id"] = "HUMAN-2"
        result = evaluate_two_stage(self.policy, self.population, records)
        self.assertEqual(OUTCOME_EXPAND, result["outcome"])

    def test_census_and_sample_are_reported_separately(self):
        records = self.observations()
        for record in records:
            if record["role"] == "CENSUS":
                record["verdict"] = "FALSE_EXCLUSION"
                record["second_reviewer_id"] = "HUMAN-2"
                break
        result = evaluate_two_stage(self.policy, self.population, records)
        self.assertEqual(1, len(result["census_errors"]))
        self.assertEqual([], result["remainder_errors"])
        self.assertFalse(result["combined_unweighted_rate_reported"])
        self.assertEqual(DETECTION_SCOPE, result["census_scope"])
        self.assertTrue(result["census_is_not_an_estimate"])

    def test_incomplete_census_is_refused(self):
        records = [
            record
            for record in self.observations()
            if record["item_id"] != self.plan["census_items"][0]
        ]
        with self.assertRaisesRegex(AuditPolicyError, "census is incomplete"):
            evaluate_two_stage(self.policy, self.population, records)

    def test_incomplete_stage_one_is_refused(self):
        records = [
            record
            for record in self.observations()
            if record["item_id"] != self.plan["stage_1_items"][0]
        ]
        with self.assertRaisesRegex(AuditPolicyError, "stage 1 sample is incomplete"):
            evaluate_two_stage(self.policy, self.population, records)

    def test_a_suspected_error_needs_a_second_human(self):
        records = self.observations()
        records[-1]["verdict"] = "FALSE_EXCLUSION"
        with self.assertRaisesRegex(AuditPolicyError, "second_reviewer_id"):
            evaluate_two_stage(self.policy, self.population, records)

    def test_the_second_human_must_be_a_different_person(self):
        records = self.observations()
        records[-1]["verdict"] = "FALSE_EXCLUSION"
        records[-1]["second_reviewer_id"] = records[-1]["reviewer_id"]
        with self.assertRaisesRegex(AuditPolicyError, "not a gold standard"):
            evaluate_two_stage(self.policy, self.population, records)

    def test_confirmation_review_must_use_a_distinct_reviewer(self):
        records = self.observations()
        records[-1]["second_reviewer_id"] = records[-1]["reviewer_id"]
        with self.assertRaisesRegex(AuditPolicyError, "distinct second reviewer"):
            evaluate_two_stage(self.policy, self.population, records)

    def test_confirmation_subset_is_prespecified_and_required(self):
        self.assertEqual(
            self.plan["confirmation_items"],
            self.plan["stage_1_items"][: self.plan["confirmation_size"]],
        )
        self.assertGreater(self.plan["confirmation_size"], 0)
        records = self.observations()
        target = self.plan["confirmation_items"][0]
        for record in records:
            if record["item_id"] == target:
                record.pop("second_reviewer_id")
        with self.assertRaisesRegex(AuditPolicyError, "confirmation sample"):
            evaluate_two_stage(self.policy, self.population, records)

    def test_high_risk_item_outside_the_population_is_refused(self):
        with self.assertRaisesRegex(AuditPolicyError, "absent from the population"):
            plan_audit(policy(high_risk_items=["NOT-IN-POPULATION"]), self.population)


class ScopeLabelTests(unittest.TestCase):
    def test_challenge_output_is_not_a_production_claim(self):
        result = challenge_set_result({"joint_false_exclusion_rate": 0.02})
        self.assertEqual(ENRICHED_SCOPE, result["estimand_scope"])
        self.assertFalse(result["production_error_rate_estimate"])
        self.assertFalse(result["manuscript_performance_claim_authorized"])
        with self.assertRaisesRegex(AuditPolicyError, "production error rate"):
            assert_not_a_production_claim(result)

    def test_detection_output_is_not_an_error_rate(self):
        result = detection_only_result({"audited": 20, "discrepancies": 2})
        self.assertEqual("2.0", result["audit_output_schema_version"])
        self.assertEqual(DETECTION_SCOPE, result["estimand_scope"])
        self.assertFalse(result["error_rate_estimate"])
        with self.assertRaises(AuditPolicyError):
            assert_not_a_production_claim(result)

    def test_legacy_without_inference_is_detection_only(self):
        legacy = classify_legacy_audit(
            {"audit_policy": {"seed": "s", "minimum_fraction": 0.2}}
        )
        self.assertEqual(DETECTION_SCOPE, legacy["estimand_scope"])
        self.assertEqual("1.0-legacy", legacy["audit_output_schema_version"])
        self.assertFalse(legacy["error_rate_estimate"])

    def test_legacy_with_valid_inference_keeps_its_scope(self):
        legacy = classify_legacy_audit(
            {
                "audit_policy": {
                    "alpha": 0.05,
                    "first_unacceptable_missed_records": 3,
                }
            }
        )
        self.assertEqual(PROBABILITY_SCOPE, legacy["estimand_scope"])

    def test_a_probability_result_may_be_reported(self):
        """Only the seeded remainder sample carries a reportable inference."""
        assert_not_a_production_claim({"estimand_scope": PROBABILITY_SCOPE})


if __name__ == "__main__":
    unittest.main()
