#!/usr/bin/env python3
"""Validate, lock, project, compare, and approve canonical eligibility rules."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Tuple


SCHEMA_VERSION = "1.0"
TOOL_VERSION = "canonical-eligibility-contract-v1"
CONTRACT_TYPE = "CANONICAL_ELIGIBILITY_CONTRACT"
PROJECTION_TYPE = "ELIGIBILITY_STAGE_PROJECTION"
COMPARISON_TYPE = "ELIGIBILITY_STRUCTURAL_COMPARISON"
RECEIPT_TYPE = "ELIGIBILITY_PROJECTION_APPROVAL"
STAGES = {"title_abstract", "full_text"}
ASSURANCE_LEVELS = {
    "RUNTIME_VERIFIED_HUMAN",
    "RECORDED_NOT_INDEPENDENTLY_AUTHENTICATED",
}
RECORDED_DISCLOSURE = (
    "Approver identity was recorded but not independently authenticated."
)
CONTRACT_REVIEW_DISCLOSURE = (
    "Reviewer identity was recorded but not independently authenticated."
)
HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class EligibilityContractError(ValueError):
    """Raised when an eligibility artifact is invalid or cannot be verified."""


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EligibilityContractError(f"{field} must be a non-empty string")
    return value.strip()


def _identifier(value: Any, field: str) -> str:
    result = _text(value, field)
    if not ID_PATTERN.fullmatch(result):
        raise EligibilityContractError(
            f"{field} must contain only letters, digits, '.', '_', or '-'"
        )
    return result


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _canonical_hash(value: object) -> str:
    return _sha256(_canonical_bytes(value))


def _validate_hash(value: Any, field: str) -> str:
    result = _text(value, field)
    if not HASH_PATTERN.fullmatch(result):
        raise EligibilityContractError(f"{field} must be a lowercase SHA-256")
    return result


def _regular_file(path_value: str, field: str) -> Path:
    candidate = Path(_text(path_value, field))
    if not candidate.is_absolute():
        raise EligibilityContractError(f"{field} must be an absolute path")
    if candidate.is_symlink():
        raise EligibilityContractError(f"{field} must not be a symlink")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise EligibilityContractError(f"{field} does not exist: {candidate}") from exc
    if not resolved.is_file():
        raise EligibilityContractError(f"{field} must be a regular file")
    return resolved


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_json(path_value: str, field: str = "JSON file") -> Dict[str, Any]:
    path = _regular_file(path_value, field)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EligibilityContractError(f"{field} is not valid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise EligibilityContractError(f"{field} must contain a JSON object")
    return value


def _write_json_new(path_value: str, value: Dict[str, Any]) -> None:
    destination = Path(path_value)
    if destination.is_symlink():
        raise EligibilityContractError("output path must not be a symlink")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write("\n")
    except FileExistsError as exc:
        raise EligibilityContractError(
            f"refusing to overwrite existing output: {destination}"
        ) from exc


def _contract_basis(value: Dict[str, Any]) -> Dict[str, Any]:
    return {key: deepcopy(item) for key, item in value.items() if key != "lock"}


def _contract_hash(value: Dict[str, Any]) -> str:
    return _canonical_hash(_contract_basis(value))


def _validate_runtime_anchor(value: Any, field: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise EligibilityContractError(f"{field} must be an object")
    required = {
        "verification_status",
        "anchor_type",
        "anchor_id",
        "verified_at",
        "evidence_sha256",
    }
    missing = sorted(required - set(value))
    if missing:
        raise EligibilityContractError(
            f"{field} is missing: {', '.join(missing)}"
        )
    if value["verification_status"] != "VERIFIED_OUTSIDE_AGENT_WRITE_SCOPE":
        raise EligibilityContractError(
            f"{field}.verification_status must be "
            "VERIFIED_OUTSIDE_AGENT_WRITE_SCOPE"
        )
    for name in ("anchor_type", "anchor_id", "verified_at"):
        _text(value[name], f"{field}.{name}")
    _validate_hash(value["evidence_sha256"], f"{field}.evidence_sha256")
    return deepcopy(value)


def _validate_human_review(value: Any) -> None:
    if not isinstance(value, dict):
        raise EligibilityContractError("human_review must be an object")
    required = {
        "status",
        "reviewed_by",
        "reviewed_at",
        "assertion",
        "assurance_level",
    }
    missing = sorted(required - set(value))
    if missing:
        raise EligibilityContractError(
            "human_review is missing: " + ", ".join(missing)
        )
    if value["status"] != "APPROVED":
        raise EligibilityContractError("human_review.status must be APPROVED")
    for field in ("reviewed_by", "reviewed_at", "assertion"):
        _text(value[field], f"human_review.{field}")
    assurance = value["assurance_level"]
    if assurance not in ASSURANCE_LEVELS:
        raise EligibilityContractError("invalid human_review assurance_level")
    anchor = value.get("runtime_anchor")
    if assurance == "RUNTIME_VERIFIED_HUMAN":
        _validate_runtime_anchor(anchor, "human_review.runtime_anchor")
        if value.get("identity_disclosure") not in (None, ""):
            raise EligibilityContractError(
                "runtime-verified human review must not carry an unauthenticated "
                "identity disclosure"
            )
    else:
        if anchor is not None:
            raise EligibilityContractError(
                "recorded human review must not carry a runtime anchor"
            )
        if value.get("identity_disclosure") != CONTRACT_REVIEW_DISCLOSURE:
            raise EligibilityContractError(
                "recorded human review requires the mandatory identity disclosure"
            )


def _validate_provenance_records(
    records: Any, kind: str
) -> Dict[str, Dict[str, Any]]:
    if not isinstance(records, list):
        raise EligibilityContractError(f"{kind} must be an array")
    mapped: Dict[str, Dict[str, Any]] = {}
    for index, item in enumerate(records):
        if not isinstance(item, dict):
            raise EligibilityContractError(f"{kind}[{index}] must be an object")
        identifier = _identifier(item.get("id"), f"{kind}[{index}].id")
        if identifier in mapped:
            raise EligibilityContractError(f"duplicate {kind} ID: {identifier}")
        _text(item.get("description"), f"{kind}[{index}].description")
        _text(item.get("protocol_version"), f"{kind}[{index}].protocol_version")
        if kind == "clarifications":
            if item.get("preserves_scientific_meaning") is not True:
                raise EligibilityContractError(
                    f"{kind}[{index}] must explicitly preserve scientific meaning"
                )
        else:
            if item.get("approved") is not True:
                raise EligibilityContractError(
                    f"{kind}[{index}] must be an approved protocol amendment"
                )
            _text(item.get("approved_by"), f"{kind}[{index}].approved_by")
            _text(item.get("approved_at"), f"{kind}[{index}].approved_at")
        mapped[identifier] = item
    return mapped


def _validate_stage_rule(
    rule: Any, stage: str, criterion_id: str
) -> None:
    if not isinstance(rule, dict):
        raise EligibilityContractError(
            f"criterion {criterion_id} stage {stage} must be an object"
        )
    for field in (
        "operational_question",
        "inclusion_rule",
        "exclusion_rule",
        "exclusion_label",
    ):
        _text(rule.get(field), f"{criterion_id}.{stage}.{field}")
    expected_action = "retain" if stage == "title_abstract" else "human_review"
    if rule.get("missing_information_action") != expected_action:
        raise EligibilityContractError(
            f"{criterion_id}.{stage}.missing_information_action must be "
            f"{expected_action}"
        )
    if stage == "full_text":
        terms = rule.get("search_terms", [])
        if not isinstance(terms, list) or any(
            not isinstance(term, str) or not term.strip() for term in terms
        ):
            raise EligibilityContractError(
                f"{criterion_id}.full_text.search_terms must contain non-empty strings"
            )


def validate_contract(value: Dict[str, Any]) -> None:
    """Validate a canonical eligibility contract and any embedded lock."""
    if not isinstance(value, dict):
        raise EligibilityContractError("eligibility contract must be an object")
    required = {
        "schema_version",
        "contract_type",
        "contract_version",
        "review_id",
        "review_title",
        "criteria_version",
        "protocol_source",
        "human_review",
        "criteria",
        "clarifications",
        "amendments",
    }
    missing = sorted(required - set(value))
    if missing:
        raise EligibilityContractError(
            "eligibility contract is missing: " + ", ".join(missing)
        )
    if value["schema_version"] != SCHEMA_VERSION:
        raise EligibilityContractError("contract schema_version must be 1.0")
    if value["contract_type"] != CONTRACT_TYPE:
        raise EligibilityContractError("invalid contract_type")
    for field in ("contract_version", "review_id", "review_title", "criteria_version"):
        _text(value[field], field)
    protocol = value["protocol_source"]
    if not isinstance(protocol, dict):
        raise EligibilityContractError("protocol_source must be an object")
    for field in ("path", "section", "version", "sha256"):
        if field not in protocol:
            raise EligibilityContractError(f"protocol_source is missing {field}")
    protocol_path = Path(_text(protocol["path"], "protocol_source.path"))
    if not protocol_path.is_absolute():
        raise EligibilityContractError("protocol_source.path must be absolute")
    _text(protocol["section"], "protocol_source.section")
    _text(protocol["version"], "protocol_source.version")
    _validate_hash(protocol["sha256"], "protocol_source.sha256")
    _validate_human_review(value["human_review"])
    clarifications = _validate_provenance_records(
        value["clarifications"], "clarifications"
    )
    amendments = _validate_provenance_records(value["amendments"], "amendments")
    criteria = value["criteria"]
    if not isinstance(criteria, list) or not criteria:
        raise EligibilityContractError("criteria must be a non-empty array")
    criterion_ids = set()
    for index, criterion in enumerate(criteria):
        if not isinstance(criterion, dict):
            raise EligibilityContractError(f"criteria[{index}] must be an object")
        identifier = _identifier(criterion.get("id"), f"criteria[{index}].id")
        if identifier in criterion_ids:
            raise EligibilityContractError(f"duplicate criterion ID: {identifier}")
        criterion_ids.add(identifier)
        _text(criterion.get("label"), f"criteria[{index}].label")
        meaning = criterion.get("scientific_meaning")
        if not isinstance(meaning, dict):
            raise EligibilityContractError(
                f"criteria[{index}].scientific_meaning must be an object"
            )
        _text(meaning.get("inclusion"), f"{identifier}.scientific_meaning.inclusion")
        _text(meaning.get("exclusion"), f"{identifier}.scientific_meaning.exclusion")
        stages = criterion.get("stages")
        if not isinstance(stages, dict) or set(stages) != STAGES:
            raise EligibilityContractError(
                f"{identifier}.stages must contain exactly title_abstract and full_text"
            )
        for stage in sorted(STAGES):
            _validate_stage_rule(stages[stage], stage, identifier)
        provenance = criterion.get("provenance")
        if not isinstance(provenance, dict):
            raise EligibilityContractError(
                f"{identifier}.provenance must be an object"
            )
        _text(
            provenance.get("protocol_section"),
            f"{identifier}.provenance.protocol_section",
        )
        for field, known in (
            ("clarification_ids", clarifications),
            ("amendment_ids", amendments),
        ):
            identifiers = provenance.get(field)
            if not isinstance(identifiers, list) or any(
                not isinstance(item, str) for item in identifiers
            ):
                raise EligibilityContractError(
                    f"{identifier}.provenance.{field} must be an array of IDs"
                )
            if len(set(identifiers)) != len(identifiers):
                raise EligibilityContractError(
                    f"{identifier}.provenance.{field} contains duplicates"
                )
            unknown = sorted(set(identifiers) - set(known))
            if unknown:
                raise EligibilityContractError(
                    f"{identifier}.provenance.{field} has unknown IDs: {unknown}"
                )
    lock = value.get("lock")
    if lock is not None:
        if not isinstance(lock, dict):
            raise EligibilityContractError("lock must be an object")
        if lock.get("status") != "INTERNAL_LOCKED":
            raise EligibilityContractError("lock.status must be INTERNAL_LOCKED")
        if lock.get("tool_version") != TOOL_VERSION:
            raise EligibilityContractError("unsupported lock tool_version")
        _validate_hash(lock.get("source_sha256"), "lock.source_sha256")
        expected_hash = _contract_hash(value)
        if lock.get("canonical_contract_hash") != expected_hash:
            raise EligibilityContractError("canonical contract lock hash mismatch")


def lock_contract(source_path: str, output_path: str) -> Dict[str, Any]:
    """Verify the protocol source and create a new immutable contract artifact."""
    source = _regular_file(source_path, "contract source")
    value = _load_json(str(source), "contract source")
    validate_contract(value)
    if value.get("lock") is not None:
        raise EligibilityContractError("contract source is already locked")
    protocol_path = _regular_file(
        value["protocol_source"]["path"], "protocol_source.path"
    )
    protocol_hash = _file_sha256(protocol_path)
    if protocol_hash != value["protocol_source"]["sha256"]:
        raise EligibilityContractError(
            "protocol source hash does not match the canonical contract"
        )
    result = deepcopy(value)
    result["lock"] = {
        "status": "INTERNAL_LOCKED",
        "tool_version": TOOL_VERSION,
        "source_sha256": _file_sha256(source),
        "canonical_contract_hash": _contract_hash(value),
    }
    validate_contract(result)
    _write_json_new(output_path, result)
    return result


def _provenance_subset(
    records: List[Dict[str, Any]], identifiers: set
) -> List[Dict[str, Any]]:
    return [deepcopy(item) for item in records if item["id"] in identifiers]


def project_contract(value: Dict[str, Any], stage: str) -> Dict[str, Any]:
    """Deterministically generate Phase 9 or Phase 10 operational criteria."""
    validate_contract(value)
    if value.get("lock", {}).get("status") != "INTERNAL_LOCKED":
        raise EligibilityContractError(
            "projection requires an INTERNAL_LOCKED canonical contract"
        )
    if stage not in STAGES:
        raise EligibilityContractError(
            "stage must be title_abstract or full_text"
        )
    clarification_ids = {
        item
        for criterion in value["criteria"]
        for item in criterion["provenance"]["clarification_ids"]
    }
    amendment_ids = {
        item
        for criterion in value["criteria"]
        for item in criterion["provenance"]["amendment_ids"]
    }
    projection: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "projection_type": PROJECTION_TYPE,
        "projection_stage": stage,
        "tool_version": TOOL_VERSION,
        "review_id": value["review_id"],
        "review_title": value["review_title"],
        "protocol_version": value["protocol_source"]["version"],
        "criteria_version": value["criteria_version"],
        "canonical_contract_hash": _contract_hash(value),
        "protocol_source": {
            "section": value["protocol_source"]["section"],
            "version": value["protocol_source"]["version"],
            "sha256": value["protocol_source"]["sha256"],
        },
        "semantic_fidelity_status": "REQUIRES_HUMAN_APPROVAL",
        "clarification_log": _provenance_subset(
            value["clarifications"], clarification_ids
        ),
        "amendment_log": _provenance_subset(
            value["amendments"], amendment_ids
        ),
        "criteria": [],
    }
    if stage == "full_text":
        projection["automation_mode"] = "ai-exception"
    for criterion in value["criteria"]:
        rule = criterion["stages"][stage]
        projected = {
            "id": criterion["id"],
            "label": criterion["label"],
            "operational_question": rule["operational_question"],
            "inclusion_rule": rule["inclusion_rule"],
            "exclusion_rule": rule["exclusion_rule"],
            "missing_information_action": rule["missing_information_action"],
            "exclusion_label": rule["exclusion_label"],
            "canonical_scientific_meaning": deepcopy(
                criterion["scientific_meaning"]
            ),
            "provenance": deepcopy(criterion["provenance"]),
        }
        if stage == "full_text":
            projected["primary_exclusion_reason"] = rule["exclusion_label"]
            projected["search_terms"] = deepcopy(rule.get("search_terms", []))
        projection["criteria"].append(projected)
    projection["projection_hash"] = _canonical_hash(projection)
    return projection


def _differences(expected: Any, actual: Any, location: str = "$") -> List[Dict[str, Any]]:
    differences: List[Dict[str, Any]] = []
    if type(expected) is not type(actual):
        return [
            {
                "path": location,
                "kind": "type_mismatch",
                "expected": type(expected).__name__,
                "actual": type(actual).__name__,
            }
        ]
    if isinstance(expected, dict):
        expected_keys = set(expected)
        actual_keys = set(actual)
        for key in sorted(expected_keys - actual_keys):
            differences.append(
                {"path": f"{location}.{key}", "kind": "missing_key"}
            )
        for key in sorted(actual_keys - expected_keys):
            differences.append(
                {"path": f"{location}.{key}", "kind": "unexpected_key"}
            )
        for key in sorted(expected_keys & actual_keys):
            differences.extend(
                _differences(expected[key], actual[key], f"{location}.{key}")
            )
        return differences
    if isinstance(expected, list):
        if len(expected) != len(actual):
            differences.append(
                {
                    "path": location,
                    "kind": "length_mismatch",
                    "expected": len(expected),
                    "actual": len(actual),
                }
            )
        for index, (expected_item, actual_item) in enumerate(
            zip(expected, actual)
        ):
            differences.extend(
                _differences(
                    expected_item, actual_item, f"{location}[{index}]"
                )
            )
        return differences
    if expected != actual:
        differences.append(
            {
                "path": location,
                "kind": "value_mismatch",
                "expected": expected,
                "actual": actual,
            }
        )
    return differences


def compare_projection(
    value: Dict[str, Any], projection: Dict[str, Any], stage: str
) -> Dict[str, Any]:
    """Compare structure exactly while making no semantic-fidelity claim."""
    expected = project_contract(value, stage)
    differences = _differences(expected, projection)
    result = {
        "schema_version": SCHEMA_VERSION,
        "comparison_type": COMPARISON_TYPE,
        "tool_version": TOOL_VERSION,
        "stage": stage,
        "canonical_contract_hash": _contract_hash(value),
        "protocol_source_sha256": value["protocol_source"]["sha256"],
        "expected_projection_hash": expected["projection_hash"],
        "actual_projection_hash": _canonical_hash(
            {
                key: deepcopy(item)
                for key, item in projection.items()
                if key != "projection_hash"
            }
        ),
        "structurally_equivalent": not differences,
        "differences": differences,
        "semantic_fidelity_claimed": False,
        "human_semantic_approval_required": True,
    }
    result["comparison_hash"] = _canonical_hash(result)
    return result


def make_file_ref(path_value: str, role: str) -> Dict[str, Any]:
    """Create a minimal real-file reference for an approval receipt."""
    path = _regular_file(path_value, f"{role} path")
    return {
        "path": str(path),
        "role": _text(role, "role"),
        "sha256": _file_sha256(path),
    }


def _verify_file_ref(value: Any, expected_role: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise EligibilityContractError(f"{expected_role} reference must be an object")
    if value.get("role") != expected_role:
        raise EligibilityContractError(
            f"reference role must be {expected_role}"
        )
    path = _regular_file(value.get("path"), f"{expected_role} reference path")
    expected_hash = _validate_hash(
        value.get("sha256"), f"{expected_role} reference sha256"
    )
    actual_hash = _file_sha256(path)
    if actual_hash != expected_hash:
        raise EligibilityContractError(
            f"{expected_role} reference hash mismatch"
        )
    return {"path": str(path), "role": expected_role, "sha256": actual_hash}


def _validate_projection_hash(value: Dict[str, Any]) -> None:
    expected = _canonical_hash(
        {
            key: deepcopy(item)
            for key, item in value.items()
            if key != "projection_hash"
        }
    )
    if value.get("projection_hash") != expected:
        raise EligibilityContractError("projection_hash mismatch")


def _validate_comparison_hash(value: Dict[str, Any]) -> None:
    expected = _canonical_hash(
        {
            key: deepcopy(item)
            for key, item in value.items()
            if key != "comparison_hash"
        }
    )
    if value.get("comparison_hash") != expected:
        raise EligibilityContractError("comparison_hash mismatch")


def _verified_approval_components(
    protocol_ref: Dict[str, Any],
    contract_ref: Dict[str, Any],
    comparison_ref: Dict[str, Any],
    projection_ref: Dict[str, Any],
) -> Tuple[
    Dict[str, Any],
    Dict[str, Any],
    Dict[str, Any],
    Dict[str, Any],
    Dict[str, Any],
    Dict[str, Any],
    Dict[str, Any],
]:
    verified_protocol = _verify_file_ref(protocol_ref, "protocol_source")
    verified_contract = _verify_file_ref(contract_ref, "canonical_contract")
    verified_comparison = _verify_file_ref(
        comparison_ref, "projection_comparison"
    )
    verified_projection = _verify_file_ref(
        projection_ref, "eligibility_projection"
    )
    contract = _load_json(verified_contract["path"], "canonical contract")
    comparison = _load_json(
        verified_comparison["path"], "projection comparison"
    )
    projection = _load_json(
        verified_projection["path"], "eligibility projection"
    )
    validate_contract(contract)
    if contract.get("lock", {}).get("status") != "INTERNAL_LOCKED":
        raise EligibilityContractError("approval requires a locked contract")
    _validate_projection_hash(projection)
    _validate_comparison_hash(comparison)
    if comparison.get("comparison_type") != COMPARISON_TYPE:
        raise EligibilityContractError("invalid comparison_type")
    if comparison.get("tool_version") != TOOL_VERSION:
        raise EligibilityContractError("unsupported comparison tool_version")
    stage = comparison.get("stage")
    if stage not in STAGES:
        raise EligibilityContractError("comparison stage is invalid")
    expected_projection = project_contract(contract, stage)
    if projection != expected_projection:
        raise EligibilityContractError(
            "projection file is not the deterministic contract projection"
        )
    expected_comparison = compare_projection(contract, projection, stage)
    if comparison != expected_comparison:
        raise EligibilityContractError(
            "comparison file is not the deterministic structural comparison"
        )
    if not comparison["structurally_equivalent"] or comparison["differences"]:
        raise EligibilityContractError(
            "approval is blocked by structural projection differences"
        )
    if comparison["semantic_fidelity_claimed"] is not False:
        raise EligibilityContractError(
            "structural comparison must not claim semantic fidelity"
        )
    protocol_path = Path(contract["protocol_source"]["path"]).resolve()
    if Path(verified_protocol["path"]) != protocol_path:
        raise EligibilityContractError(
            "protocol reference path differs from the canonical contract"
        )
    if (
        verified_protocol["sha256"]
        != contract["protocol_source"]["sha256"]
    ):
        raise EligibilityContractError(
            "protocol reference hash differs from the canonical contract"
        )
    return (
        verified_protocol,
        verified_contract,
        verified_comparison,
        verified_projection,
        contract,
        comparison,
        projection,
    )


def build_approval_receipt(
    protocol_ref: Dict[str, Any],
    contract_ref: Dict[str, Any],
    comparison_ref: Dict[str, Any],
    projection_ref: Dict[str, Any],
    assertion: str,
    assurance_level: str,
    runtime_anchor: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a receipt binding human semantic approval to verified files."""
    (
        verified_protocol,
        verified_contract,
        verified_comparison,
        verified_projection,
        contract,
        comparison,
        projection,
    ) = _verified_approval_components(
        protocol_ref, contract_ref, comparison_ref, projection_ref
    )
    assertion_text = _text(assertion, "assertion")
    if assurance_level not in ASSURANCE_LEVELS:
        raise EligibilityContractError("invalid approval assurance_level")
    verified_anchor = None
    disclosure = RECORDED_DISCLOSURE
    if assurance_level == "RUNTIME_VERIFIED_HUMAN":
        verified_anchor = _validate_runtime_anchor(
            runtime_anchor, "runtime_anchor"
        )
        disclosure = None
    elif runtime_anchor is not None:
        raise EligibilityContractError(
            "recorded approval must not carry a runtime anchor"
        )
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "receipt_type": RECEIPT_TYPE,
        "tool_version": TOOL_VERSION,
        "stage": projection["projection_stage"],
        "protocol_ref": verified_protocol,
        "contract_ref": verified_contract,
        "comparison_ref": verified_comparison,
        "projection_ref": verified_projection,
        "protocol_source_sha256": contract["protocol_source"]["sha256"],
        "canonical_contract_hash": _contract_hash(contract),
        "comparison_hash": comparison["comparison_hash"],
        "comparison_tool_version": comparison["tool_version"],
        "projection_hash": projection["projection_hash"],
        "approver_assertion": assertion_text,
        "semantic_fidelity_responsibility": "HUMAN_APPROVER",
        "assurance_level": assurance_level,
        "runtime_anchor": verified_anchor,
        "identity_disclosure": disclosure,
    }
    receipt["receipt_hash"] = _canonical_hash(receipt)
    return receipt


def validate_approval_receipt(value: Dict[str, Any]) -> Dict[str, Any]:
    """Recompute all bound file and logical hashes in an approval receipt."""
    if not isinstance(value, dict):
        raise EligibilityContractError("approval receipt must be an object")
    if value.get("schema_version") != SCHEMA_VERSION:
        raise EligibilityContractError("approval receipt schema_version must be 1.0")
    if value.get("receipt_type") != RECEIPT_TYPE:
        raise EligibilityContractError("invalid approval receipt_type")
    if value.get("tool_version") != TOOL_VERSION:
        raise EligibilityContractError("unsupported approval tool_version")
    supplied_hash = _validate_hash(value.get("receipt_hash"), "receipt_hash")
    expected_hash = _canonical_hash(
        {
            key: deepcopy(item)
            for key, item in value.items()
            if key != "receipt_hash"
        }
    )
    if supplied_hash != expected_hash:
        raise EligibilityContractError("approval receipt hash mismatch")
    assurance = value.get("assurance_level")
    if assurance not in ASSURANCE_LEVELS:
        raise EligibilityContractError("invalid approval assurance_level")
    if assurance == "RUNTIME_VERIFIED_HUMAN":
        _validate_runtime_anchor(value.get("runtime_anchor"), "runtime_anchor")
        if value.get("identity_disclosure") is not None:
            raise EligibilityContractError(
                "runtime-verified approval must not carry unauthenticated disclosure"
            )
    else:
        if value.get("runtime_anchor") is not None:
            raise EligibilityContractError(
                "recorded approval must not carry a runtime anchor"
            )
        if value.get("identity_disclosure") != RECORDED_DISCLOSURE:
            raise EligibilityContractError(
                "recorded approval requires the mandatory disclosure"
            )
    _text(value.get("approver_assertion"), "approver_assertion")
    if value.get("semantic_fidelity_responsibility") != "HUMAN_APPROVER":
        raise EligibilityContractError(
            "semantic fidelity responsibility must remain with the human approver"
        )
    components = _verified_approval_components(
        value.get("protocol_ref"),
        value.get("contract_ref"),
        value.get("comparison_ref"),
        value.get("projection_ref"),
    )
    contract = components[4]
    comparison = components[5]
    projection = components[6]
    expected_links = {
        "stage": projection["projection_stage"],
        "protocol_source_sha256": contract["protocol_source"]["sha256"],
        "canonical_contract_hash": _contract_hash(contract),
        "comparison_hash": comparison["comparison_hash"],
        "comparison_tool_version": comparison["tool_version"],
        "projection_hash": projection["projection_hash"],
    }
    for field, expected in expected_links.items():
        if value.get(field) != expected:
            raise EligibilityContractError(
                f"approval receipt binding mismatch for {field}"
            )
    return {
        "valid": True,
        "receipt_hash": supplied_hash,
        "stage": value["stage"],
        "assurance_level": assurance,
        "identity_disclosure": value.get("identity_disclosure"),
        "contract_file_sha256": components[1]["sha256"],
        "comparison_file_sha256": components[2]["sha256"],
        "projection_file_sha256": components[3]["sha256"],
    }


def verify_approval_bundle(
    contract_path: str,
    comparison_path: str,
    receipt_path: str,
    stage: str,
) -> Dict[str, Any]:
    """Verify a supplied bundle and require its paths and stage to match."""
    if stage not in STAGES:
        raise EligibilityContractError("invalid approval bundle stage")
    contract = _regular_file(contract_path, "canonical contract")
    comparison = _regular_file(comparison_path, "projection comparison")
    receipt = _load_json(receipt_path, "approval receipt")
    result = validate_approval_receipt(receipt)
    if receipt["stage"] != stage:
        raise EligibilityContractError(
            f"approval receipt is for {receipt['stage']}, not {stage}"
        )
    if Path(receipt["contract_ref"]["path"]) != contract:
        raise EligibilityContractError(
            "approval receipt is bound to another canonical contract path"
        )
    if Path(receipt["comparison_ref"]["path"]) != comparison:
        raise EligibilityContractError(
            "approval receipt is bound to another comparison path"
        )
    result["contract_path"] = str(contract)
    result["comparison_path"] = str(comparison)
    result["projection_path"] = receipt["projection_ref"]["path"]
    result["protocol_path"] = receipt["protocol_ref"]["path"]
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    command = commands.add_parser("validate")
    command.add_argument("--contract", required=True)
    command.add_argument("--output", required=True)

    command = commands.add_parser("lock")
    command.add_argument("--source", required=True)
    command.add_argument("--output", required=True)

    command = commands.add_parser("project")
    command.add_argument("--contract", required=True)
    command.add_argument("--stage", choices=sorted(STAGES), required=True)
    command.add_argument("--output", required=True)

    command = commands.add_parser("compare")
    command.add_argument("--contract", required=True)
    command.add_argument("--projection", required=True)
    command.add_argument("--stage", choices=sorted(STAGES), required=True)
    command.add_argument("--output", required=True)

    command = commands.add_parser("approve")
    command.add_argument("--protocol", required=True)
    command.add_argument("--contract", required=True)
    command.add_argument("--comparison", required=True)
    command.add_argument("--projection", required=True)
    command.add_argument("--assertion", required=True)
    command.add_argument(
        "--assurance-level", choices=sorted(ASSURANCE_LEVELS), required=True
    )
    command.add_argument("--runtime-anchor")
    command.add_argument("--output", required=True)

    # Consumers verify the whole bundle against the real files rather than
    # trusting a criteria file's own recorded hashes.
    command = commands.add_parser("verify-bundle")
    command.add_argument("--contract", required=True)
    command.add_argument("--comparison", required=True)
    command.add_argument("--approval", required=True)
    command.add_argument("--stage", choices=sorted(STAGES), required=True)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "validate":
            contract = _load_json(args.contract, "canonical contract")
            validate_contract(contract)
            result = {
                "schema_version": SCHEMA_VERSION,
                "tool_version": TOOL_VERSION,
                "valid": True,
                "canonical_contract_hash": _contract_hash(contract),
                "locked": contract.get("lock", {}).get("status")
                == "INTERNAL_LOCKED",
            }
        elif args.command == "verify-bundle":
            result = verify_approval_bundle(
                args.contract, args.comparison, args.approval, args.stage
            )
        elif args.command == "lock":
            lock_contract(args.source, args.output)
            return 0
        elif args.command == "project":
            result = project_contract(
                _load_json(args.contract, "canonical contract"), args.stage
            )
        elif args.command == "compare":
            result = compare_projection(
                _load_json(args.contract, "canonical contract"),
                _load_json(args.projection, "eligibility projection"),
                args.stage,
            )
        else:
            runtime_anchor = (
                _load_json(args.runtime_anchor, "runtime anchor")
                if args.runtime_anchor
                else None
            )
            result = build_approval_receipt(
                make_file_ref(args.protocol, "protocol_source"),
                make_file_ref(args.contract, "canonical_contract"),
                make_file_ref(args.comparison, "projection_comparison"),
                make_file_ref(args.projection, "eligibility_projection"),
                args.assertion,
                args.assurance_level,
                runtime_anchor,
            )
        if args.command == "verify-bundle":
            # A verifier reports; it does not create artifacts.
            print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
        else:
            _write_json_new(args.output, result)
        return 0
    except (EligibilityContractError, OSError, json.JSONDecodeError) as exc:
        print(f"eligibility-contract error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
