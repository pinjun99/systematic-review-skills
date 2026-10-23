"""Phase 13 -> 18 assurance chain: generated handoffs, derived PRISMA counts,
PRESS status, and complete Phase 18 protection.

Every link binds real upstream files by recomputed SHA-256 and carries a
machine-generated payload. Nothing in this module accepts a transcribed number:
a consumer either verifies the producer's artifacts or refuses.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from artifact_ref import (
    ArtifactRefError,
    canonical_json_sha256,
    make_artifact_ref,
    verify_artifact_ref,
)


CHAIN_SCHEMA_VERSION = "2.0"
HASH_PATTERN = re.compile(r"[0-9a-f]{64}")

PRESS_COMPLETED = "PRESS_COMPLETED"
PRESS_WAIVED = "APPROVED_WITH_PRESS_WAIVER"
PRESS_UNAVAILABLE = "PRESS_UNAVAILABLE"
PRESS_PENDING = "AWAITING_PRESS"
PRESS_STATUSES = (PRESS_COMPLETED, PRESS_WAIVED, PRESS_UNAVAILABLE, PRESS_PENDING)
PRESS_EXECUTABLE = (PRESS_COMPLETED, PRESS_WAIVED)

PRESS_LIMITATION_TEXT = (
    "The principal search strategy did not complete independent external peer "
    "review (PRESS). Search sensitivity may therefore be lower than an "
    "externally reviewed strategy would achieve."
)

# (flow count, source role, field in that source document)
PRISMA_DERIVATIONS: Tuple[Tuple[str, str, str], ...] = (
    ("records_identified", "PHASE8_DEDUPLICATION", "records_imported"),
    ("duplicates_removed", "PHASE8_DEDUPLICATION", "duplicate_records_removed"),
    ("records_screened", "PHASE9_SCREENING", "expected_phase8_records"),
    ("records_excluded", "PHASE9_SCREENING", "excluded_title_abstract"),
    ("reports_sought", "PHASE9_SCREENING", "retained_for_full_text"),
    ("reports_not_retrieved", "PHASE10_RETRIEVAL", "reports_not_retrieved"),
    ("reports_assessed", "PHASE10_RETRIEVAL", "reports_assessed"),
    ("reports_excluded", "PHASE10_SCREENING", "excluded_reports"),
    ("reports_included", "PHASE10_SCREENING", "included_reports"),
    ("studies_included", "PHASE10_SCREENING", "included_studies"),
)
ADJUSTMENT_ONLY_COUNTS = ("records_removed_other_reasons",)
FLOW_COUNT_KEYS = tuple(name for name, _, _ in PRISMA_DERIVATIONS) + ADJUSTMENT_ONLY_COUNTS


class ChainError(ValueError):
    """Raised when a chain link, derivation, or gate refuses.

    Subclasses ``ValueError`` so skill entry points map it to exit 1.
    """


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ChainError(f"{field} must be a non-empty string")
    return value


def _integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ChainError(f"{field} must be a non-negative integer")
    return value


def _object(value: Any, field: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ChainError(f"{field} must be an object")
    return value


# --------------------------------------------------------------------------
# Chain links
# --------------------------------------------------------------------------


def build_chain_link(
    *,
    producer: str,
    consumer: str,
    review_id: str,
    sources: Sequence[Dict[str, Any]],
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    """Bind a machine-generated payload to the verified files it came from."""
    _text(producer, "producer")
    _text(consumer, "consumer")
    _text(review_id, "review_id")
    if not sources:
        raise ChainError("a chain link needs at least one source artifact")
    verified = [verify_artifact_ref(dict(ref)) for ref in sources]
    stripped = [
        {key: value for key, value in ref.items() if key != "resolved_path"}
        for ref in verified
    ]
    link = {
        "schema_version": CHAIN_SCHEMA_VERSION,
        "producer_phase": producer,
        "consumer_phase": consumer,
        "review_id": review_id,
        "generated": True,
        "sources": stripped,
        "payload": payload,
        "payload_sha256": canonical_json_sha256(payload),
    }
    link["chain_sha256"] = canonical_json_sha256(
        {key: value for key, value in link.items() if key != "chain_sha256"}
    )
    return link


def verify_chain_link(link: Dict[str, Any], *, consumer: Optional[str] = None) -> Dict[str, Any]:
    """Recompute every source hash and the payload digest. Trusts nothing."""
    _object(link, "chain link")
    if link.get("schema_version") != CHAIN_SCHEMA_VERSION:
        raise ChainError(
            f"chain link schema {link.get('schema_version')!r} is not supported; "
            f"schema {CHAIN_SCHEMA_VERSION} is required"
        )
    if link.get("generated") is not True:
        raise ChainError(
            "chain link is not machine-generated; manual handoffs are refused"
        )
    if consumer is not None and link.get("consumer_phase") != consumer:
        raise ChainError(
            f"chain link targets {link.get('consumer_phase')!r}, not {consumer!r}"
        )
    sources = link.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ChainError("chain link sources must be a non-empty array")
    for ref in sources:
        # Present one error type to callers: an altered source file is a broken
        # chain link, not a bare artifact problem the caller must also catch.
        try:
            verify_artifact_ref(ref)
        except ArtifactRefError as exc:
            raise ChainError(f"chain link source failed verification: {exc}") from exc
    payload = _object(link.get("payload"), "chain link payload")
    recorded_payload = _text(link.get("payload_sha256"), "payload_sha256")
    if canonical_json_sha256(payload) != recorded_payload:
        raise ChainError("chain link payload hash mismatch")
    recorded_chain = _text(link.get("chain_sha256"), "chain_sha256")
    recomputed = canonical_json_sha256(
        {key: value for key, value in link.items() if key != "chain_sha256"}
    )
    if recomputed != recorded_chain:
        raise ChainError("chain link hash mismatch")
    return payload


def locked_source_ref(path: str, role: str, version: str) -> Dict[str, Any]:
    """Make a verified reference to a locked upstream package file."""
    return make_artifact_ref(path, role, version, "LOCKED")


# --------------------------------------------------------------------------
# PRISMA counts
# --------------------------------------------------------------------------


def _adjustment_total(adjustments: Sequence[Dict[str, Any]], count: str) -> Tuple[int, List[Dict[str, Any]]]:
    total = 0
    applied: List[Dict[str, Any]] = []
    for index, adjustment in enumerate(adjustments):
        where = f"adjustments[{index}]"
        _object(adjustment, where)
        if _text(adjustment.get("count"), f"{where}.count") != count:
            continue
        for field in ("reason", "approved_by", "approved_at"):
            _text(adjustment.get(field), f"{where}.{field}")
        value = _integer(adjustment.get("value"), f"{where}.value")
        total += value
        applied.append(dict(adjustment))
    return total, applied


def derive_prisma_counts(
    sources: Sequence[Dict[str, Any]],
    *,
    adjustments: Sequence[Dict[str, Any]] = (),
) -> Dict[str, Any]:
    """Derive every PRISMA flow count from canonical Phase 8-10 documents.

    ``sources`` entries are ``{"role", "ref", "document"}`` where ``ref`` is a
    verified artifact reference to the file and ``document`` is its parsed
    content. No count may be supplied directly; the only human input is an
    explicitly approved adjustment, which is recorded with its rationale.
    """
    by_role: Dict[str, Dict[str, Any]] = {}
    for index, source in enumerate(sources):
        where = f"sources[{index}]"
        _object(source, where)
        role = _text(source.get("role"), f"{where}.role")
        ref = _object(source.get("ref"), f"{where}.ref")
        verify_artifact_ref(ref)
        document = _object(source.get("document"), f"{where}.document")
        if role in by_role:
            raise ChainError(f"duplicate PRISMA source role: {role}")
        by_role[role] = {"ref": ref, "document": document}

    counts: Dict[str, int] = {}
    derivation: List[Dict[str, Any]] = []
    for name, role, field in PRISMA_DERIVATIONS:
        entry = by_role.get(role)
        if entry is None:
            raise ChainError(f"PRISMA source {role} is required for {name}")
        document = entry["document"]
        if field not in document:
            raise ChainError(f"{role} document has no {field} for {name}")
        value = _integer(document[field], f"{role}.{field}")
        adjusted, applied = _adjustment_total(adjustments, name)
        counts[name] = value + adjusted
        derivation.append(
            {
                "count": name,
                "source_role": role,
                "source_field": field,
                "source_value": value,
                "adjustments": applied,
                "value": counts[name],
                "rule": f"{role}.{field}"
                + ("" if not applied else " + approved adjustments"),
            }
        )
    for name in ADJUSTMENT_ONLY_COUNTS:
        adjusted, applied = _adjustment_total(adjustments, name)
        counts[name] = adjusted
        derivation.append(
            {
                "count": name,
                "source_role": "APPROVED_ADJUSTMENT",
                "source_field": None,
                "source_value": 0,
                "adjustments": applied,
                "value": adjusted,
                "rule": "approved adjustments only",
            }
        )

    validate_prisma_identities(counts)
    derived = {
        "schema_version": CHAIN_SCHEMA_VERSION,
        "derived": True,
        "counts": counts,
        "derivation": derivation,
        "sources": [
            {"role": role, "ref": entry["ref"]} for role, entry in sorted(by_role.items())
        ],
    }
    derived["derivation_sha256"] = canonical_json_sha256(
        {key: value for key, value in derived.items() if key != "derivation_sha256"}
    )
    return derived


def validate_prisma_identities(counts: Dict[str, int]) -> None:
    for key in FLOW_COUNT_KEYS:
        _integer(counts.get(key), f"flow_counts.{key}")
    if counts["records_screened"] != (
        counts["records_identified"]
        - counts["duplicates_removed"]
        - counts["records_removed_other_reasons"]
    ):
        raise ChainError("PRISMA records_screened does not reconcile with its sources")
    if counts["reports_sought"] != counts["records_screened"] - counts["records_excluded"]:
        raise ChainError("PRISMA reports_sought does not reconcile with its sources")
    if counts["reports_assessed"] != counts["reports_sought"] - counts["reports_not_retrieved"]:
        raise ChainError("PRISMA reports_assessed does not reconcile with its sources")
    if counts["reports_included"] != counts["reports_assessed"] - counts["reports_excluded"]:
        raise ChainError("PRISMA reports_included does not reconcile with its sources")
    if counts["studies_included"] > counts["reports_included"]:
        raise ChainError("studies_included cannot exceed reports_included")


def verify_derived_prisma(value: Any) -> Dict[str, int]:
    """Accept only a derived PRISMA object; refuse hand-entered counts."""
    block = _object(value, "flow_counts")
    if block.get("derived") is not True:
        raise ChainError(
            "flow_counts must be generated by derive_prisma_counts from canonical "
            "Phase 8-10 sources; manually entered counts are refused"
        )
    if block.get("schema_version") != CHAIN_SCHEMA_VERSION:
        raise ChainError("flow_counts schema is not supported")
    recorded = _text(block.get("derivation_sha256"), "flow_counts.derivation_sha256")
    recomputed = canonical_json_sha256(
        {key: value for key, value in block.items() if key != "derivation_sha256"}
    )
    if recomputed != recorded:
        raise ChainError("flow_counts derivation hash mismatch")
    for source in block.get("sources", []):
        verify_artifact_ref(_object(source, "flow_counts.sources[]").get("ref"))
    counts = _object(block.get("counts"), "flow_counts.counts")
    validate_prisma_identities(counts)
    return counts


# --------------------------------------------------------------------------
# PRESS
# --------------------------------------------------------------------------


def validate_press_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a versioned PRESS record and its hash bindings."""
    _object(record, "press_record")
    _text(record.get("press_version"), "press_record.press_version")
    status = _text(record.get("status"), "press_record.status")
    if status not in PRESS_STATUSES:
        raise ChainError(f"unsupported PRESS status: {status}")

    reviewed = _object(record.get("reviewed_strategy"), "press_record.reviewed_strategy")
    verify_artifact_ref(reviewed)
    final = _object(record.get("final_strategy"), "press_record.final_strategy")
    verify_artifact_ref(final)

    if status == PRESS_COMPLETED:
        reviewer = _object(record.get("reviewer"), "press_record.reviewer")
        for field in ("role", "expertise", "review_date"):
            _text(reviewer.get(field), f"press_record.reviewer.{field}")
        independence = _object(
            reviewer.get("independence"), "press_record.reviewer.independence"
        )
        if independence.get("independent_of_strategy_author") is not True:
            raise ChainError(
                "PRESS_COMPLETED requires an asserted independent reviewer"
            )
        # An assertion is not authentication; the assurance level says so.
        assurance = _text(
            independence.get("assurance_level"),
            "press_record.reviewer.independence.assurance_level",
        )
        if assurance != "SELF_ASSERTED_UNAUTHENTICATED" and not independence.get(
            "runtime_anchor"
        ):
            raise ChainError(
                "an independence assurance above self-assertion needs a runtime anchor"
            )
        if not isinstance(record.get("findings"), list) or not record["findings"]:
            raise ChainError("PRESS_COMPLETED requires recorded findings")
        for field in ("responses", "modifications"):
            if not isinstance(record.get(field), list):
                raise ChainError(f"press_record.{field} must be an array")
        if not isinstance(record.get("re_review_required"), bool):
            raise ChainError("press_record.re_review_required must be a boolean")
        if record["re_review_required"] and reviewed["sha256"] == final["sha256"]:
            raise ChainError(
                "re-review was required but the final strategy is unchanged"
            )

    if status == PRESS_WAIVED:
        waiver = _object(record.get("waiver"), "press_record.waiver")
        for field in ("rationale", "approved_by", "approved_at"):
            _text(waiver.get(field), f"press_record.waiver.{field}")

    return record


def press_execution_gate(record: Dict[str, Any]) -> Dict[str, Any]:
    """Permit search execution only for completed or approved-waiver PRESS."""
    validate_press_record(record)
    status = record["status"]
    if status not in PRESS_EXECUTABLE:
        raise ChainError(
            f"search execution refused: PRESS status {status} is not "
            f"{' or '.join(PRESS_EXECUTABLE)}"
        )
    return {
        "status": status,
        "limitation_required": status != PRESS_COMPLETED,
        "external_review_completed": status == PRESS_COMPLETED,
    }


def press_limitation_claim(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Return the mandatory LIMITATION claim when PRESS did not complete."""
    validate_press_record(record)
    if record["status"] == PRESS_COMPLETED:
        return None
    return {
        "claim_id": "CLAIM-PRESS-LIMITATION",
        "section": "Discussion",
        "claim_type": "LIMITATION",
        "text": PRESS_LIMITATION_TEXT,
        "source_ids": ["PRESS:" + record["press_version"]],
        "verification": "VERIFIED",
        "press_status": record["status"],
    }


def check_press_limitation(
    record: Dict[str, Any], claim_ledger: Sequence[Dict[str, Any]]
) -> None:
    """Phase 18 check: a non-completed PRESS must surface in the manuscript."""
    required = press_limitation_claim(record)
    if required is None:
        return
    for claim in claim_ledger:
        if not isinstance(claim, dict):
            continue
        if claim.get("claim_type") != "LIMITATION":
            continue
        if "PRESS:" + record["press_version"] in (claim.get("source_ids") or []):
            return
    raise ChainError(
        f"PRESS status {record['status']} requires a LIMITATION claim citing "
        f"PRESS:{record['press_version']}; the claim ledger has none"
    )


# --------------------------------------------------------------------------
# Phase 18 protected set
# --------------------------------------------------------------------------


def derive_protected_set(
    *,
    reporting_package_ref: Dict[str, Any],
    control: Dict[str, Any],
    artifact_register: Sequence[Dict[str, Any]],
    source_registry: Sequence[Dict[str, Any]],
    supplied: Optional[Sequence[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Derive the complete Phase 18 protected set and refuse omissions.

    The caller never hand-assembles the list. Every locked control package,
    every present artifact, every ``INTERNAL_LOCKED`` source, and the reporting
    package itself must be present, verifiable, and mutually consistent.
    """
    required: Dict[str, Dict[str, Any]] = {}

    def add(ref: Any, role: str, where: str) -> None:
        entry = _object(ref, where)
        path = _text(entry.get("path"), f"{where}.path")
        existing = required.get(path)
        candidate = {**entry, "role": entry.get("role", role)}
        if existing is not None:
            if existing.get("sha256") != candidate.get("sha256"):
                raise ChainError(
                    f"conflicting hashes for protected path {path}"
                )
            if existing.get("role") != candidate.get("role"):
                raise ChainError(f"conflicting roles for protected path {path}")
            return
        required[path] = candidate

    add(reporting_package_ref, "REPORTING_PACKAGE", "reporting_package_ref")
    for key, entry in sorted(_object(control, "control").items()):
        ref = _object(entry, f"control.{key}").get("ref")
        if ref is None:
            raise ChainError(
                f"control.{key} has no artifact reference; Phase 18 cannot "
                "protect a package it cannot locate"
            )
        add(ref, f"CONTROL_{key.upper()}", f"control.{key}.ref")
    for index, artifact in enumerate(artifact_register):
        where = f"artifact_register[{index}]"
        entry = _object(artifact, where)
        if entry.get("status") != "PRESENT":
            continue
        add(entry.get("ref"), "ARTIFACT", f"{where}.ref")
    for index, source in enumerate(source_registry):
        where = f"source_registry[{index}]"
        entry = _object(source, where)
        if entry.get("source_class") != "INTERNAL_LOCKED":
            continue
        ref = entry.get("ref")
        if ref is None:
            raise ChainError(
                f"{where} is INTERNAL_LOCKED but has no verifiable local artifact"
            )
        add(ref, "INTERNAL_LOCKED_SOURCE", f"{where}.ref")

    for path, ref in sorted(required.items()):
        verify_artifact_ref(ref)

    derived = sorted(required.values(), key=lambda ref: ref["path"])
    if supplied is not None:
        supplied_paths = set()
        for index, ref in enumerate(supplied):
            entry = _object(ref, f"protected_files[{index}]")
            supplied_paths.add(_text(entry.get("path"), f"protected_files[{index}].path"))
        missing = sorted(set(required) - supplied_paths)
        if missing:
            raise ChainError(
                "protected_files omits required artifacts: " + ", ".join(missing[:5])
            )
        extra = sorted(supplied_paths - set(required))
        if extra:
            raise ChainError(
                "protected_files lists artifacts absent from the reporting "
                "package: " + ", ".join(extra[:5])
            )
    return {
        "schema_version": CHAIN_SCHEMA_VERSION,
        "derived": True,
        "protected_files": derived,
        "count": len(derived),
        "protected_set_sha256": canonical_json_sha256(derived),
    }
