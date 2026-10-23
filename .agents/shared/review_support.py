#!/usr/bin/env python3
"""Deterministic Phase 1→6 review-support classification and gate."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional


SCHEMA_VERSION = "1.0"
TOOL_VERSION = "review-support-gate-v1"
END_TO_END = "END_TO_END_SUPPORTED"
PARTIAL = "PARTIAL_PIPELINE_ONLY"
UNSUPPORTED = "UNSUPPORTED_DOWNSTREAM_BRANCH"
ASSURANCE_LEVELS = {
    "RUNTIME_VERIFIED_HUMAN",
    "RECORDED_NOT_INDEPENDENTLY_AUTHENTICATED",
}


class SupportGateError(ValueError):
    """Raised when a support artifact or authorization is invalid."""


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SupportGateError(f"{field} must be a non-empty string")
    return value.strip()


def _normalise_question_type(value: str) -> str:
    return " ".join(re.split(r"[\s_/-]+", _text(value, "question_type").lower()))


def _canonical_framework(value: str) -> str:
    raw = _text(value, "framework")
    if raw == "PICo":
        return "PICo"
    key = re.sub(r"[^a-z0-9]", "", raw.lower())
    known = {
        "picost": "PICOST",
        "peco": "PECO",
        "pecot": "PECOT",
        "pird": "PIRD",
        "cocopop": "CoCoPop",
        "spider": "SPIDER",
        "prognosis": "PROGNOSIS",
        "prognostic": "PROGNOSIS",
    }
    return known.get(key, raw)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _canonical_hash(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _mapping(question_type: str, framework: str) -> Dict[str, Any]:
    is_intervention = any(
        term in question_type for term in ("intervention", "treatment effect", "effectiveness")
    )
    if framework == "PICOST" and is_intervention:
        return {
            "support_status": END_TO_END,
            "last_guaranteed_supported_phase": "PHASE_18",
            "unsupported_capabilities": [],
            "evidence_dependent_conditions": [
                {
                    "condition": "META_ANALYSIS_PLANNED",
                    "effect": "STOP_AT_DEFERRED_PHASE_14_BRANCH",
                    "required_external_capability": (
                        "Validated meta-analysis execution is required before "
                        "Phase 15 can continue."
                    ),
                }
            ],
        }
    if framework in {"PECO", "PECOT", "PIRD"}:
        return {
            "support_status": PARTIAL,
            "last_guaranteed_supported_phase": "PHASE_13_PLANNING",
            "unsupported_capabilities": [
                "Design-appropriate synthesis execution after Phase 13",
                "Design-appropriate certainty assessment after synthesis",
            ],
            "evidence_dependent_conditions": [],
        }
    if framework in {"CoCoPop", "PROGNOSIS"} or question_type in {
        "prevalence",
        "incidence",
        "prognosis",
        "prognostic",
    }:
        return {
            "support_status": PARTIAL,
            "last_guaranteed_supported_phase": "PHASE_11",
            "unsupported_capabilities": [
                "Validated Phase 12 risk-of-bias branch for this review type",
                "Validated Phase 13 and later synthesis and certainty branch",
            ],
            "evidence_dependent_conditions": [],
        }
    if framework in {"PICo", "SPIDER"}:
        return {
            "support_status": PARTIAL,
            "last_guaranteed_supported_phase": "PHASE_10",
            "unsupported_capabilities": [
                "Validated Phase 11 extraction schema for qualitative synthesis",
                "Validated Phase 12 and later qualitative appraisal, synthesis, "
                "and certainty branch",
            ],
            "evidence_dependent_conditions": [],
        }
    return {
        "support_status": UNSUPPORTED,
        "last_guaranteed_supported_phase": "PHASE_5",
        "unsupported_capabilities": [
            "Numbered downstream pipeline for this custom or unknown framework"
        ],
        "evidence_dependent_conditions": [],
    }


def _support_basis(value: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "schema_version": value["schema_version"],
        "tool_version": value["tool_version"],
        "question_type": value["question_type"],
        "framework": value["framework"],
        "support_status": value["support_status"],
        "last_guaranteed_supported_phase": value[
            "last_guaranteed_supported_phase"
        ],
        "unsupported_capabilities": value["unsupported_capabilities"],
        "evidence_dependent_conditions": value["evidence_dependent_conditions"],
    }


def classify_support(
    question_type: str,
    framework: str,
    evidence_conditions: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return the deterministic support classification artifact."""
    normal_question = _normalise_question_type(question_type)
    canonical_framework = _canonical_framework(framework)
    mapped = _mapping(normal_question, canonical_framework)
    conditions = deepcopy(mapped["evidence_dependent_conditions"])
    if evidence_conditions is not None:
        if not isinstance(evidence_conditions, dict):
            raise SupportGateError("evidence_conditions must be an object")
        if evidence_conditions:
            conditions.append(
                {
                    "condition": "OBSERVED_REVIEW_CONDITIONS",
                    "details": deepcopy(evidence_conditions),
                }
            )
    requires_approval = mapped["support_status"] != END_TO_END
    artifact = {
        "schema_version": SCHEMA_VERSION,
        "tool_version": TOOL_VERSION,
        "question_type": normal_question,
        "framework": canonical_framework,
        "support_status": mapped["support_status"],
        "last_guaranteed_supported_phase": mapped[
            "last_guaranteed_supported_phase"
        ],
        "unsupported_capabilities": deepcopy(mapped["unsupported_capabilities"]),
        "evidence_dependent_conditions": conditions,
        "authorization_requirement": {
            "required": requires_approval,
            "default_action": (
                "REJECT_PHASE_6_CONTINUATION"
                if requires_approval
                else "ALLOW_PHASE_6_CONTINUATION"
            ),
            "authorized": not requires_approval,
            "approval_receipt_hash": None,
        },
    }
    artifact["support_artifact_hash"] = _canonical_hash(_support_basis(artifact))
    validate_support_artifact(artifact)
    return artifact


def _verify_receipt(value: Dict[str, Any], receipt: Dict[str, Any]) -> None:
    required = {
        "schema_version",
        "receipt_type",
        "support_artifact_hash",
        "approver_assertion",
        "approved_by",
        "approved_at",
        "assurance_level",
        "missing_downstream_methods",
        "external_tooling_or_expertise",
        "registration_limitation",
        "unsupported_protocol_methods",
        "receipt_hash",
    }
    missing = sorted(required - set(receipt))
    if missing:
        raise SupportGateError(
            "continuation_authorization is missing: " + ", ".join(missing)
        )
    if receipt["schema_version"] != SCHEMA_VERSION:
        raise SupportGateError("approval receipt schema_version must be 1.0")
    if receipt["receipt_type"] != "REVIEW_SUPPORT_CONTINUATION_APPROVAL":
        raise SupportGateError("invalid approval receipt_type")
    expected_support_hash = _canonical_hash(_support_basis(value))
    if receipt["support_artifact_hash"] != expected_support_hash:
        raise SupportGateError("approval receipt is bound to another support artifact")
    assurance = receipt["assurance_level"]
    if assurance not in ASSURANCE_LEVELS:
        raise SupportGateError("invalid approval assurance_level")
    if assurance == "RUNTIME_VERIFIED_HUMAN":
        raise SupportGateError(
            "RUNTIME_VERIFIED_HUMAN cannot be self-issued by this file-based "
            "tool; use a trusted runtime adapter"
        )
    if receipt.get("runtime_anchor") is not None:
        raise SupportGateError(
            "file-based approval must not carry a runtime authentication claim"
        )
    missing_methods = receipt["missing_downstream_methods"]
    if (
        not isinstance(missing_methods, list)
        or not all(isinstance(item, str) and item for item in missing_methods)
        or set(missing_methods) != set(value["unsupported_capabilities"])
    ):
        raise SupportGateError(
            "approval must enumerate every unsupported downstream capability"
        )
    external = receipt["external_tooling_or_expertise"]
    if not isinstance(external, list) or not external or not all(
        isinstance(item, str) and item.strip() for item in external
    ):
        raise SupportGateError(
            "approval must identify external tooling or expertise"
        )
    _text(receipt["registration_limitation"], "registration_limitation")
    controls = receipt["unsupported_protocol_methods"]
    if not isinstance(controls, list) or len(controls) != len(missing_methods):
        raise SupportGateError("unsupported_protocol_methods are incomplete")
    for method, control in zip(missing_methods, controls):
        if control != {
            "method": method,
            "status": "NOT_SUPPORTED_BY_THIS_WORKFLOW",
        }:
            raise SupportGateError("unsupported protocol method control is invalid")
    receipt_without_hash = {
        key: deepcopy(item)
        for key, item in receipt.items()
        if key != "receipt_hash"
    }
    if receipt["receipt_hash"] != _canonical_hash(receipt_without_hash):
        raise SupportGateError("approval receipt hash mismatch")


def validate_support_artifact(value: Dict[str, Any]) -> None:
    """Validate classification, deterministic mapping, and any receipt."""
    if not isinstance(value, dict):
        raise SupportGateError("review support artifact must be an object")
    required = {
        "schema_version",
        "tool_version",
        "question_type",
        "framework",
        "support_status",
        "last_guaranteed_supported_phase",
        "unsupported_capabilities",
        "evidence_dependent_conditions",
        "authorization_requirement",
        "support_artifact_hash",
    }
    missing = sorted(required - set(value))
    if missing:
        raise SupportGateError("review support artifact is missing: " + ", ".join(missing))
    if value["schema_version"] != SCHEMA_VERSION:
        raise SupportGateError("review support schema_version must be 1.0")
    if value["tool_version"] != TOOL_VERSION:
        raise SupportGateError("unsupported review support tool_version")
    question = _normalise_question_type(value["question_type"])
    framework = _canonical_framework(value["framework"])
    if question != value["question_type"] or framework != value["framework"]:
        raise SupportGateError("question_type or framework is not canonical")
    expected = _mapping(question, framework)
    if value["support_artifact_hash"] != _canonical_hash(_support_basis(value)):
        raise SupportGateError("support_artifact_hash mismatch")
    for field in (
        "support_status",
        "last_guaranteed_supported_phase",
        "unsupported_capabilities",
    ):
        if value[field] != expected[field]:
            raise SupportGateError(f"{field} conflicts with deterministic support map")
    conditions = value["evidence_dependent_conditions"]
    if not isinstance(conditions, list):
        raise SupportGateError("evidence_dependent_conditions must be an array")
    expected_conditions = {
        _canonical_hash(item) for item in expected["evidence_dependent_conditions"]
    }
    actual_conditions = {
        _canonical_hash(item) for item in conditions if isinstance(item, dict)
    }
    if len(actual_conditions) != len(conditions) or not expected_conditions.issubset(
        actual_conditions
    ):
        raise SupportGateError("required evidence-dependent conditions are missing")
    requirement = value["authorization_requirement"]
    if not isinstance(requirement, dict):
        raise SupportGateError("authorization_requirement must be an object")
    expected_required = value["support_status"] != END_TO_END
    if requirement.get("required") is not expected_required:
        raise SupportGateError("authorization requirement conflicts with support status")
    expected_default = (
        "REJECT_PHASE_6_CONTINUATION"
        if expected_required
        else "ALLOW_PHASE_6_CONTINUATION"
    )
    if requirement.get("default_action") != expected_default:
        raise SupportGateError("invalid authorization default_action")
    authorized = requirement.get("authorized")
    receipt_hash = requirement.get("approval_receipt_hash")
    receipt = value.get("continuation_authorization")
    if not expected_required:
        if authorized is not True or receipt_hash is not None or receipt is not None:
            raise SupportGateError(
                "end-to-end support must not contain a continuation approval"
            )
        return
    if authorized is False:
        if receipt_hash is not None or receipt is not None:
            raise SupportGateError("unauthorized artifact must not contain a receipt")
        return
    if authorized is not True or not isinstance(receipt, dict):
        raise SupportGateError("authorized continuation requires a receipt")
    _verify_receipt(value, receipt)
    if receipt_hash != receipt["receipt_hash"]:
        raise SupportGateError("authorization_requirement receipt hash mismatch")


def authorize_continuation(
    value: Dict[str, Any], approval: Dict[str, Any]
) -> Dict[str, Any]:
    """Bind an explicit informed approval to a partial/unsupported artifact."""
    validate_support_artifact(value)
    if value["support_status"] == END_TO_END:
        return deepcopy(value)
    if value["authorization_requirement"]["authorized"]:
        raise SupportGateError("continuation is already authorized")
    if not isinstance(approval, dict):
        raise SupportGateError("approval must be an object")
    required = {
        "support_artifact_hash",
        "approver_assertion",
        "approved_by",
        "approved_at",
        "assurance_level",
        "missing_downstream_methods",
        "external_tooling_or_expertise",
        "registration_limitation",
    }
    missing = sorted(required - set(approval))
    if missing:
        raise SupportGateError("approval is missing: " + ", ".join(missing))
    support_hash = value["support_artifact_hash"]
    if approval["support_artifact_hash"] != support_hash:
        raise SupportGateError("approval does not bind this review support artifact")
    _text(approval["approver_assertion"], "approver_assertion")
    _text(approval["approved_by"], "approved_by")
    _text(approval["approved_at"], "approved_at")
    assurance = approval["assurance_level"]
    if assurance not in ASSURANCE_LEVELS:
        raise SupportGateError("invalid approval assurance_level")
    missing_methods = approval["missing_downstream_methods"]
    if not isinstance(missing_methods, list) or not all(
        isinstance(item, str) and item for item in missing_methods
    ):
        raise SupportGateError("missing_downstream_methods must be strings")
    if set(missing_methods) != set(
        value["unsupported_capabilities"]
    ):
        raise SupportGateError(
            "approval must enumerate every unsupported downstream capability"
        )
    external = approval["external_tooling_or_expertise"]
    if not isinstance(external, list) or not external:
        raise SupportGateError(
            "approval must identify external tooling or expertise"
        )
    registration_limitation = _text(
        approval["registration_limitation"], "registration_limitation"
    )
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "receipt_type": "REVIEW_SUPPORT_CONTINUATION_APPROVAL",
        "support_artifact_hash": support_hash,
        "approver_assertion": approval["approver_assertion"].strip(),
        "approved_by": approval["approved_by"].strip(),
        "approved_at": approval["approved_at"].strip(),
        "assurance_level": assurance,
        "missing_downstream_methods": list(missing_methods),
        "external_tooling_or_expertise": list(external),
        "registration_limitation": registration_limitation,
        "unsupported_protocol_methods": [
            {
                "method": method,
                "status": "NOT_SUPPORTED_BY_THIS_WORKFLOW",
            }
            for method in missing_methods
        ],
    }
    if assurance == "RUNTIME_VERIFIED_HUMAN":
        raise SupportGateError(
            "RUNTIME_VERIFIED_HUMAN cannot be self-issued by this file-based "
            "tool; use a trusted runtime adapter"
        )
    if approval.get("runtime_anchor") is not None:
        raise SupportGateError(
            "file-based approval must not carry a runtime authentication claim"
        )
    receipt["receipt_hash"] = _canonical_hash(receipt)
    result = deepcopy(value)
    result["authorization_requirement"]["authorized"] = True
    result["authorization_requirement"]["approval_receipt_hash"] = receipt[
        "receipt_hash"
    ]
    result["continuation_authorization"] = receipt
    validate_support_artifact(result)
    return result


def enforce_phase6_gate(value: Dict[str, Any]) -> Dict[str, Any]:
    """Return Phase 6 controls or reject unsupported continuation."""
    validate_support_artifact(value)
    status = value["support_status"]
    if status == END_TO_END:
        return {
            "schema_version": SCHEMA_VERSION,
            "gate_version": TOOL_VERSION,
            "allowed": True,
            "mode": "NORMAL_CONTINUATION",
            "support_status": status,
            "last_guaranteed_supported_phase": value[
                "last_guaranteed_supported_phase"
            ],
            "evidence_dependent_conditions": deepcopy(
                value["evidence_dependent_conditions"]
            ),
            "protocol_method_controls": [],
            "registration_limitation": None,
            "approval_receipt_hash": None,
        }
    requirement = value["authorization_requirement"]
    if requirement["authorized"] is not True:
        raise SupportGateError(
            f"Phase 6 continuation rejected by default: {status}; explicit "
            "hash-bound informed approval is required"
        )
    receipt = value["continuation_authorization"]
    return {
        "schema_version": SCHEMA_VERSION,
        "gate_version": TOOL_VERSION,
        "allowed": True,
        "mode": (
            "AUTHORIZED_PARTIAL_CONTINUATION"
            if status == PARTIAL
            else "AUTHORIZED_UNSUPPORTED_BRANCH_CONTINUATION"
        ),
        "support_status": status,
        "last_guaranteed_supported_phase": value[
            "last_guaranteed_supported_phase"
        ],
        "missing_downstream_methods": deepcopy(
            receipt["missing_downstream_methods"]
        ),
        "protocol_method_controls": deepcopy(
            receipt["unsupported_protocol_methods"]
        ),
        "external_tooling_or_expertise": deepcopy(
            receipt["external_tooling_or_expertise"]
        ),
        "registration_limitation": receipt["registration_limitation"],
        "approval_receipt_hash": receipt["receipt_hash"],
        "approval_assurance_level": receipt["assurance_level"],
        "identity_disclosure": (
            None
            if receipt["assurance_level"] == "RUNTIME_VERIFIED_HUMAN"
            else "Approver identity was recorded but not independently authenticated."
        ),
    }


def _load_json(path: str) -> Dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise SupportGateError(f"{path} must contain a JSON object")
    return value


def _write_json_new(path: str, value: Dict[str, Any]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write("\n")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    classify = subparsers.add_parser("classify")
    classify.add_argument("--question-type", required=True)
    classify.add_argument("--framework", required=True)
    classify.add_argument("--evidence-conditions")
    classify.add_argument("--output", required=True)

    authorize = subparsers.add_parser("authorize")
    authorize.add_argument("--support", required=True)
    authorize.add_argument("--approval", required=True)
    authorize.add_argument("--output", required=True)

    enforce = subparsers.add_parser("enforce-phase6")
    enforce.add_argument("--support", required=True)
    enforce.add_argument("--output", required=True)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "classify":
            conditions = (
                _load_json(args.evidence_conditions)
                if args.evidence_conditions
                else None
            )
            result = classify_support(
                args.question_type,
                args.framework,
                conditions,
            )
        elif args.command == "authorize":
            result = authorize_continuation(
                _load_json(args.support),
                _load_json(args.approval),
            )
        else:
            result = enforce_phase6_gate(_load_json(args.support))
        _write_json_new(args.output, result)
        return 0
    except (OSError, json.JSONDecodeError, SupportGateError) as exc:
        print(f"review-support error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
