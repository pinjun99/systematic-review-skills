#!/usr/bin/env python3
"""Evaluate Systematic Review V2 scientific and efficiency release gates."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any


CRITICAL_FLAGS = {
    "fabricated_evidence",
    "eligibility_drift",
    "wrong_critical_value_or_unit",
    "reversed_effect_direction",
    "unsupported_primary_conclusion",
    "silent_protocol_deviation",
}
REQUIRED_MODULES = {
    "clinical_intervention",
    "observational_association",
    "ai_diagnostic_prediction",
    "preclinical_organ_bath",
    "scoping_evidence_mapping",
}
REQUIRED_SCENARIOS = {
    "straightforward",
    "ambiguous",
    "conflicting",
    "missing_information",
    "multi_report",
    "poor_text_extraction",
}


class BenchmarkError(ValueError):
    pass


def _index(records: list[dict[str, Any]], label: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        case_id = record.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            raise BenchmarkError(f"{label} record has no case_id")
        if case_id in result:
            raise BenchmarkError(f"duplicate {label} case_id: {case_id}")
        result[case_id] = record
    return result


def validate_gold(gold: list[dict[str, Any]]) -> None:
    _index(gold, "gold")
    modules = {case.get("module") for case in gold}
    scenarios = {case.get("scenario") for case in gold}
    if not REQUIRED_MODULES <= modules:
        raise BenchmarkError("gold fixture does not cover every V2 module")
    if not REQUIRED_SCENARIOS <= scenarios:
        raise BenchmarkError("gold fixture does not cover every required scenario")


def scientific_metrics(
    gold: list[dict[str, Any]], candidate: list[dict[str, Any]]
) -> dict[str, Any]:
    validate_gold(gold)
    expected = _index(gold, "gold")
    actual = _index(candidate, "candidate")
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    false_exclusions: list[str] = []
    critical_errors: list[dict[str, str]] = []
    exclusion_total = exclusion_correct = 0
    critical_fields_total = critical_fields_correct = 0
    evidence_total = evidence_correct = 0
    judgment_total = judgment_correct = 0

    for case_id, gold_case in expected.items():
        run = actual.get(case_id)
        if run is None:
            continue
        gold_decision = gold_case.get("decision")
        decision = run.get("decision")
        if decision == "exclude" and gold_decision != "exclude":
            false_exclusions.append(case_id)
        if gold_decision == "exclude" and decision == "exclude":
            exclusion_total += 1
            exclusion_correct += run.get("primary_reason_code") == gold_case.get("primary_reason_code")
        for flag in sorted(CRITICAL_FLAGS):
            if run.get(flag) is True:
                critical_errors.append({"case_id": case_id, "error": flag})
        expected_fields = gold_case.get("critical_fields", {})
        actual_fields = run.get("critical_fields", {})
        for field, expected_value in expected_fields.items():
            critical_fields_total += 1
            critical_fields_correct += actual_fields.get(field) == expected_value
        if gold_case.get("evidence_required"):
            evidence_total += 1
            evidence_correct += run.get("evidence_verified") is True
        for field, expected_value in gold_case.get("expert_judgments", {}).items():
            judgment_total += 1
            judgment_correct += run.get("expert_judgments", {}).get(field) == expected_value

    return {
        "case_count": len(expected),
        "missing_case_ids": missing,
        "extra_case_ids": extra,
        "false_exclusion_case_ids": false_exclusions,
        "critical_errors": critical_errors,
        "primary_exclusion_reason_accuracy": (
            exclusion_correct / exclusion_total if exclusion_total else 1.0
        ),
        "critical_field_accuracy": (
            critical_fields_correct / critical_fields_total if critical_fields_total else 1.0
        ),
        "evidence_fidelity": evidence_correct / evidence_total if evidence_total else 1.0,
        "expert_judgment_agreement": judgment_correct / judgment_total if judgment_total else 1.0,
    }


def scientific_gate(candidate: dict[str, Any], v1: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    if candidate["missing_case_ids"]:
        reasons.append("candidate is missing benchmark cases")
    if candidate["false_exclusion_case_ids"]:
        reasons.append("candidate falsely excluded at least one study")
    if candidate["critical_errors"]:
        reasons.append("candidate produced a critical error")
    if candidate["primary_exclusion_reason_accuracy"] < 0.95:
        reasons.append("primary exclusion reason accuracy is below 95%")
    if candidate["critical_field_accuracy"] < 1.0:
        reasons.append("critical field accuracy is below 100%")
    if candidate["evidence_fidelity"] < 1.0:
        reasons.append("evidence fidelity is below 100%")
    if candidate["expert_judgment_agreement"] < v1["expert_judgment_agreement"]:
        reasons.append("expert judgment agreement is below V1")
    if len(candidate["critical_errors"]) > len(v1["critical_errors"]):
        reasons.append("candidate has more critical errors than V1")
    return {"passed": not reasons, "reasons": reasons}


def _median(values: Any, where: str) -> float:
    if not isinstance(values, list) or not values:
        raise BenchmarkError(f"{where} must be a non-empty list")
    return float(statistics.median(values))


def _reduction(v1: float, v2: float) -> float:
    if v1 <= 0:
        raise BenchmarkError("V1 comparison values must be positive")
    return (v1 - v2) / v1


def efficiency_metrics(v1: dict[str, Any], v2: dict[str, Any]) -> dict[str, Any]:
    metrics = {
        "context_reduction": _reduction(v1["mandatory_context"], v2["mandatory_context"]),
        "quotation_reduction": _reduction(v1["quotation_entries"], v2["quotation_entries"]),
        "approval_pauses": v2["approval_pauses"],
        "token_reduction": _reduction(
            _median(v1["tokens"], "v1.tokens"), _median(v2["tokens"], "v2.tokens")
        ),
        "time_reduction": _reduction(
            _median(v1["seconds"], "v1.seconds"), _median(v2["seconds"], "v2.seconds")
        ),
        "recomputation_reduction": _reduction(
            v1["recomputed_records"], v2["recomputed_records"]
        ),
        "phase_wide_rerun": bool(v2.get("phase_wide_rerun")),
    }
    reasons = []
    thresholds = {
        "context_reduction": 0.40,
        "quotation_reduction": 0.50,
        "token_reduction": 0.30,
        "time_reduction": 0.30,
        "recomputation_reduction": 0.50,
    }
    for field, threshold in thresholds.items():
        if metrics[field] < threshold:
            reasons.append(f"{field} is below {threshold:.0%}")
    if metrics["approval_pauses"] > 5:
        reasons.append("approval pauses exceed five")
    if metrics["phase_wide_rerun"]:
        reasons.append("a local correction triggered a phase-wide rerun")
    metrics["passed"] = not reasons
    metrics["reasons"] = reasons
    return metrics


def release_gate(
    gold: list[dict[str, Any]],
    v1_run: list[dict[str, Any]],
    v2_run: list[dict[str, Any]],
    v1_efficiency: dict[str, Any],
    v2_efficiency: dict[str, Any],
) -> dict[str, Any]:
    v1_science = scientific_metrics(gold, v1_run)
    v2_science = scientific_metrics(gold, v2_run)
    science_gate = scientific_gate(v2_science, v1_science)
    efficiency = efficiency_metrics(v1_efficiency, v2_efficiency)
    return {
        "release_status": "PASS" if science_gate["passed"] and efficiency["passed"] else "BLOCKED",
        "scientific_gate": science_gate,
        "scientific_metrics": {"v1": v1_science, "v2": v2_science},
        "efficiency_gate": efficiency,
    }


def _load(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", required=True)
    parser.add_argument("--v1-run", required=True)
    parser.add_argument("--v2-run", required=True)
    parser.add_argument("--v1-efficiency", required=True)
    parser.add_argument("--v2-efficiency", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    result = release_gate(
        _load(args.gold), _load(args.v1_run), _load(args.v2_run),
        _load(args.v1_efficiency), _load(args.v2_efficiency)
    )
    rendered = json.dumps(result, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["release_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
