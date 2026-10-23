#!/usr/bin/env python3
"""Shared contracts and deterministic validation for Systematic Review V2.

The runtime deliberately validates scientific boundaries, not every working
file.  Skills write ordinary JSON while this module enforces the common
lifecycle, evidence tiers, milestone approvals, safe V1 imports, and local
correction propagation.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "2.0"
STATES = {"READY", "NEEDS_HUMAN", "APPROVED", "SUPERSEDED"}
EVIDENCE_TIERS = {0, 1, 2}
MODULES = {
    "clinical_intervention",
    "observational_association",
    "ai_diagnostic_prediction",
    "preclinical_organ_bath",
    "scoping_evidence_mapping",
}
PHASES = (
    "protocol",
    "search_design",
    "search_execution",
    "deduplication",
    "title_abstract_screening",
    "full_text_retrieval",
    "full_text_screening",
    "data_extraction",
    "risk_of_bias",
    "synthesis_planning",
    "structured_synthesis",
    "certainty_of_evidence",
    "reporting_package",
    "independent_quality_control",
)
MILESTONES = {
    "M1_PROTOCOL": "protocol",
    "M2_SEARCH": "search_design",
    "M3_SELECTION": "full_text_screening",
    "M4_EVIDENCE": "synthesis_planning",
    "M5_PUBLICATION": "reporting_package",
}


class V2ContractError(ValueError):
    """Raised when a V2 artifact violates a shared contract."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def object_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _mapping(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise V2ContractError(f"{where} must be an object")
    return value


def _text(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise V2ContractError(f"{where} must be non-empty text")
    return value.strip()


def _string_list(value: Any, where: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(v, str) or not v for v in value):
        raise V2ContractError(f"{where} must be a list of non-empty strings")
    return value


def _iso_datetime(value: Any, where: str) -> str:
    text = _text(value, where)
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V2ContractError(f"{where} must be an ISO-8601 datetime") from exc
    return text


def validate_review_config(value: Any) -> dict[str, Any]:
    config = copy.deepcopy(_mapping(value, "review_config"))
    if config.get("schema_version") != SCHEMA_VERSION:
        raise V2ContractError("review_config.schema_version must be 2.0")
    _text(config.get("review_id"), "review_config.review_id")
    _text(config.get("title"), "review_config.title")
    _text(config.get("protocol_version"), "review_config.protocol_version")
    modules = set(_string_list(config.get("active_modules"), "review_config.active_modules"))
    if not modules or not modules <= MODULES:
        raise V2ContractError("review_config.active_modules contains an unsupported module")
    roles = _mapping(config.get("team_roles"), "review_config.team_roles")
    _text(roles.get("owner"), "review_config.team_roles.owner")
    policy = _mapping(config.get("ai_policy"), "review_config.ai_policy")
    if policy.get("posture") != "AI_FIRST_RISK_BASED":
        raise V2ContractError("review_config.ai_policy.posture must be AI_FIRST_RISK_BASED")
    if policy.get("paid_api_authorized") not in {True, False}:
        raise V2ContractError("paid_api_authorized must be boolean")
    return config


def validate_evidence_ref(value: Any, tier: int, *, stage: str) -> dict[str, Any]:
    if tier not in EVIDENCE_TIERS:
        raise V2ContractError("evidence tier must be 0, 1, or 2")
    ref = copy.deepcopy(_mapping(value, "evidence_ref"))
    _text(ref.get("source_id"), "evidence_ref.source_id")
    _text(ref.get("text_span"), "evidence_ref.text_span")
    if ref.get("verified") is not True:
        raise V2ContractError("evidence_ref.verified must be true")
    locator_fields = ("page", "section", "table", "figure", "paragraph")
    has_locator = any(ref.get(field) not in {None, ""} for field in locator_fields)
    if tier == 1 and stage == "full_text_screening" and not has_locator:
        raise V2ContractError("full-text Tier 1 evidence requires a source locator")
    if tier == 2 and not has_locator:
        raise V2ContractError("Tier 2 evidence requires a precise source locator")
    return ref


def validate_decision_record(value: Any) -> dict[str, Any]:
    record = copy.deepcopy(_mapping(value, "decision_record"))
    if record.get("schema_version") != SCHEMA_VERSION:
        raise V2ContractError("decision_record.schema_version must be 2.0")
    _text(record.get("record_id"), "decision_record.record_id")
    _text(record.get("study_id"), "decision_record.study_id")
    stage = _text(record.get("stage"), "decision_record.stage")
    if stage not in {"title_abstract_screening", "full_text_screening"}:
        raise V2ContractError("decision_record.stage is unsupported")
    decision = record.get("decision")
    if decision not in {"include", "exclude", "uncertain"}:
        raise V2ContractError("decision must be include, exclude, or uncertain")
    tier = record.get("evidence_tier")
    if tier not in EVIDENCE_TIERS:
        raise V2ContractError("decision_record.evidence_tier must be 0, 1, or 2")
    checklist = _mapping(record.get("eligibility_checklist"), "eligibility_checklist")
    if not checklist:
        raise V2ContractError("eligibility_checklist cannot be empty")
    if any(v not in {"met", "not_met", "unclear", "not_assessed"} for v in checklist.values()):
        raise V2ContractError("eligibility_checklist contains an invalid status")
    if decision == "include" and tier != 0:
        raise V2ContractError("routine included records use Tier 0 evidence")
    if decision == "exclude":
        if tier < 1:
            raise V2ContractError("exclusions require at least Tier 1 evidence")
        _text(record.get("primary_reason_code"), "primary_reason_code")
    if decision == "uncertain" and tier != 2:
        raise V2ContractError("uncertain decisions require Tier 2 evidence")
    evidence = record.get("evidence", [])
    if not isinstance(evidence, list):
        raise V2ContractError("decision_record.evidence must be a list")
    if tier == 0 and evidence:
        raise V2ContractError("Tier 0 records must not manufacture quotations")
    if tier > 0 and len(evidence) != 1:
        raise V2ContractError("screening decisions require one decisive evidence item")
    for ref in evidence:
        validate_evidence_ref(ref, tier, stage=stage)
    confidence = record.get("confidence")
    if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        raise V2ContractError("confidence must be between 0 and 1")
    reviewer = _mapping(record.get("reviewer"), "decision_record.reviewer")
    _text(reviewer.get("id"), "decision_record.reviewer.id")
    if reviewer.get("type") not in {"ai", "human"}:
        raise V2ContractError("reviewer.type must be ai or human")
    return record


def validate_phase_result(value: Any) -> dict[str, Any]:
    result = copy.deepcopy(_mapping(value, "phase_result"))
    if result.get("schema_version") != SCHEMA_VERSION:
        raise V2ContractError("phase_result.schema_version must be 2.0")
    phase = result.get("phase")
    if phase not in PHASES:
        raise V2ContractError("phase_result.phase is unsupported")
    state = result.get("state")
    if state not in STATES:
        raise V2ContractError("phase_result.state is unsupported")
    _string_list(result.get("input_refs", []), "phase_result.input_refs")
    _string_list(result.get("output_refs", []), "phase_result.output_refs")
    issues = _string_list(result.get("unresolved_issue_ids", []), "unresolved_issue_ids")
    if state == "READY" and issues:
        raise V2ContractError("READY phase results cannot retain unresolved issues")
    next_phase = result.get("next_phase")
    if next_phase is not None and next_phase not in PHASES:
        raise V2ContractError("phase_result.next_phase is unsupported")
    return result


def approve_milestone(subject: Any, approval: Any) -> dict[str, Any]:
    approval = copy.deepcopy(_mapping(approval, "milestone_approval"))
    milestone = approval.get("milestone_id")
    if milestone not in MILESTONES:
        raise V2ContractError("milestone_approval.milestone_id is unsupported")
    _text(approval.get("approved_by"), "milestone_approval.approved_by")
    _iso_datetime(approval.get("approved_at"), "milestone_approval.approved_at")
    _text(approval.get("assertion"), "milestone_approval.assertion")
    expected = object_sha256(subject)
    if approval.get("subject_sha256") != expected:
        raise V2ContractError("milestone approval is not bound to this subject")
    approval["schema_version"] = SCHEMA_VERSION
    approval["state"] = "APPROVED"
    return approval


V1_IMPORT_FIELDS = {
    "bibliographic_records": {"records", "source_files"},
    "pdf_sources": {"reports", "files"},
    "study_report_links": {"studies", "reports", "links"},
    "screening_decisions": {"decisions"},
    "exclusion_reasons": {"exclusions"},
    "extraction_dataset": {"studies", "fields", "rows"},
}


def import_v1_artifact(kind: str, value: Any, *, source_sha256: str) -> dict[str, Any]:
    if kind not in V1_IMPORT_FIELDS:
        raise V2ContractError("unsupported V1 import kind")
    source_sha256 = _text(source_sha256, "source_sha256")
    if len(source_sha256) != 64 or any(c not in "0123456789abcdef" for c in source_sha256):
        raise V2ContractError("source_sha256 must be a lowercase SHA-256")
    payload = _mapping(value, "V1 artifact")
    allowed = V1_IMPORT_FIELDS[kind]
    imported = {key: copy.deepcopy(payload[key]) for key in allowed if key in payload}
    if not imported:
        raise V2ContractError("V1 artifact contains no importable scientific data")
    return {
        "schema_version": SCHEMA_VERSION,
        "import_kind": kind,
        "provenance": {
            "source_system": "SYSTEMATIC_REVIEW_V1",
            "source_sha256": source_sha256,
            "approval_state_imported": False,
        },
        "data": imported,
        "conflicts": [],
        "state": "READY",
    }


def register_issue(value: Any) -> dict[str, Any]:
    issue = copy.deepcopy(_mapping(value, "issue"))
    _text(issue.get("issue_id"), "issue.issue_id")
    owner = _text(issue.get("owner_ref"), "issue.owner_ref")
    _text(issue.get("finding"), "issue.finding")
    severity = issue.get("severity")
    if severity not in {"routine", "important", "critical"}:
        raise V2ContractError("issue.severity is unsupported")
    issue.update({"status": "OPEN", "affected_refs": [owner]})
    return issue


def affected_refs(owner_ref: str, dependency_graph: Any) -> list[str]:
    owner_ref = _text(owner_ref, "owner_ref")
    graph = _mapping(dependency_graph, "dependency_graph")
    for key, values in graph.items():
        _text(key, "dependency_graph key")
        _string_list(values, f"dependency_graph.{key}")
    seen = {owner_ref}
    queue = [owner_ref]
    while queue:
        current = queue.pop(0)
        for dependent in graph.get(current, []):
            if dependent not in seen:
                seen.add(dependent)
                queue.append(dependent)
    return sorted(seen)


def resolve_issue(issue: Any, *, corrected_ref: str, dependency_graph: Any) -> dict[str, Any]:
    result = copy.deepcopy(_mapping(issue, "issue"))
    if result.get("status") != "OPEN":
        raise V2ContractError("only OPEN issues can be resolved")
    corrected_ref = _text(corrected_ref, "corrected_ref")
    affected = affected_refs(result["owner_ref"], dependency_graph)
    result.update(
        {
            "status": "RESOLVED",
            "corrected_ref": corrected_ref,
            "affected_refs": affected,
            "stale_refs": [ref for ref in affected if ref != result["owner_ref"]],
        }
    )
    return result


def _read_json(path: str) -> Any:
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: str, value: Any) -> None:
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("validate-config", "validate-decision", "validate-phase"):
        command = sub.add_parser(name)
        command.add_argument("input")
    approve = sub.add_parser("approve")
    approve.add_argument("subject")
    approve.add_argument("approval")
    approve.add_argument("output")
    importer = sub.add_parser("import-v1")
    importer.add_argument("kind", choices=sorted(V1_IMPORT_FIELDS))
    importer.add_argument("input")
    importer.add_argument("source_sha256")
    importer.add_argument("output")
    affected = sub.add_parser("affected")
    affected.add_argument("owner_ref")
    affected.add_argument("graph")
    args = parser.parse_args(argv)
    if args.command == "validate-config":
        value = validate_review_config(_read_json(args.input))
    elif args.command == "validate-decision":
        value = validate_decision_record(_read_json(args.input))
    elif args.command == "validate-phase":
        value = validate_phase_result(_read_json(args.input))
    elif args.command == "approve":
        value = approve_milestone(_read_json(args.subject), _read_json(args.approval))
        _write_json(args.output, value)
    elif args.command == "import-v1":
        value = import_v1_artifact(args.kind, _read_json(args.input), source_sha256=args.source_sha256)
        _write_json(args.output, value)
    else:
        value = affected_refs(args.owner_ref, _read_json(args.graph))
    print(json.dumps(value, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
