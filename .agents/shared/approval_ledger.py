"""Hash-chained, append-only execution and approval ledger.

What this provides and what it does not:

* **Object binding.** An approval commits to the exact SHA-256 of the thing
  approved, a timestamp, and an itemised list. Tampering with either the object
  or the approval breaks the binding. This is real.
* **Tamper-evidence within the file.** Each entry carries the digest of its
  predecessor, so an edit to any earlier entry invalidates every later one.
  This is real, and it is cheap.
* **Authentication.** Not provided by default, and never claimed. An agent that
  can write the ledger can also rebuild the whole chain, so a valid chain
  proves only internal consistency. Authentication requires an anchor the agent
  cannot write, and until one is verified the assurance level says
  ``SELF_ASSERTED_UNAUTHENTICATED`` in the output.

Actor separation is likewise an assertion. Two different session identifiers
recorded by the same agent are two strings, not two actors. The vocabulary here
keeps that distinction visible so a Methods section cannot quietly upgrade it.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional


LEDGER_SCHEMA_VERSION = "1.0"
HASH_PATTERN = re.compile(r"[0-9a-f]{64}")
GENESIS = "0" * 64

SELF_ASSERTED = "SELF_ASSERTED_UNAUTHENTICATED"
EXTERNALLY_ANCHORED = "EXTERNALLY_ANCHORED"
ASSURANCE_LEVELS = (SELF_ASSERTED, EXTERNALLY_ANCHORED)

REQUIRED_EVENT_FIELDS = ("event_type", "actor_id", "session_id", "recorded_at")


class ApprovalLedgerError(ValueError):
    """Raised when a ledger, event, approval, or anchor is invalid."""


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ApprovalLedgerError(f"{field} must be a non-empty string")
    return value


def _hash(value: Any, field: str) -> str:
    digest = _text(value, field)
    if not HASH_PATTERN.fullmatch(digest):
        raise ApprovalLedgerError(f"{field} must be a lowercase SHA-256 digest")
    return digest


def canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_entries(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    if not path.is_file():
        raise ApprovalLedgerError(f"ledger path is not a regular file: {path}")
    entries: List[Dict[str, Any]] = []
    for number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ApprovalLedgerError(
                f"ledger line {number} is not valid JSON"
            ) from exc
    return entries


def _entry_digest(entry: Dict[str, Any]) -> str:
    return canonical_sha256(
        {key: value for key, value in entry.items() if key != "entry_sha256"}
    )


def append_event(ledger_path: str, event: Dict[str, Any]) -> Dict[str, Any]:
    """Append one event, chaining it to the current tail.

    The ledger is never rewritten: entries are appended, and each carries the
    digest of its predecessor.
    """
    if not isinstance(event, dict):
        raise ApprovalLedgerError("event must be an object")
    for field in REQUIRED_EVENT_FIELDS:
        _text(event.get(field), f"event.{field}")

    path = Path(ledger_path)
    entries = _read_entries(path)
    previous = entries[-1]["entry_sha256"] if entries else GENESIS
    entry = {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "sequence": len(entries) + 1,
        "previous_sha256": previous,
        "event": event,
    }
    entry["entry_sha256"] = _entry_digest(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
    return entry


def verify_anchor(anchor: Optional[Dict[str, Any]], ledger_path: Path) -> Dict[str, Any]:
    """Verify an anchor that is supposed to sit outside agent write scope."""
    if anchor is None:
        return {
            "assurance_level": SELF_ASSERTED,
            "authenticated": False,
            "reason": "no external anchor was supplied",
        }
    if not isinstance(anchor, dict):
        raise ApprovalLedgerError("external_anchor must be an object")
    raw_path = _text(anchor.get("path"), "external_anchor.path")
    expected = _hash(anchor.get("sha256"), "external_anchor.sha256")
    _text(anchor.get("verification_method"), "external_anchor.verification_method")

    target = Path(raw_path)
    if not target.is_absolute():
        raise ApprovalLedgerError("external_anchor.path must be absolute")
    if not target.is_file():
        return {
            "assurance_level": SELF_ASSERTED,
            "authenticated": False,
            "reason": f"anchor artifact is missing: {raw_path}",
        }
    if target.resolve().parent == ledger_path.resolve().parent:
        return {
            "assurance_level": SELF_ASSERTED,
            "authenticated": False,
            "reason": (
                "anchor sits beside the ledger, so it is inside the same write "
                "scope and anchors nothing"
            ),
        }
    if _file_sha256(target) != expected:
        return {
            "assurance_level": SELF_ASSERTED,
            "authenticated": False,
            "reason": "anchor artifact does not match its recorded digest",
        }
    if anchor.get("outside_agent_write_scope") is not True:
        return {
            "assurance_level": SELF_ASSERTED,
            "authenticated": False,
            "reason": "anchor is not declared outside agent write scope",
        }
    if anchor.get("verified_by_runtime") is not True:
        return {
            "assurance_level": SELF_ASSERTED,
            "authenticated": False,
            "reason": (
                "anchor was not issued by the runtime; a digest the agent could "
                "have written does not authenticate anything"
            ),
        }
    return {
        "assurance_level": EXTERNALLY_ANCHORED,
        "authenticated": True,
        "reason": "anchor verified against a runtime-issued artifact",
    }


def verify_ledger(
    ledger_path: str, external_anchor: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Walk the chain, recompute every digest, and report honest assurance."""
    path = Path(ledger_path)
    entries = _read_entries(path)
    previous = GENESIS
    for index, entry in enumerate(entries, start=1):
        where = f"ledger entry {index}"
        if not isinstance(entry, dict):
            raise ApprovalLedgerError(f"{where} must be an object")
        if entry.get("schema_version") != LEDGER_SCHEMA_VERSION:
            raise ApprovalLedgerError(f"{where} has an unsupported schema version")
        if entry.get("sequence") != index:
            raise ApprovalLedgerError(
                f"{where} is out of order: recorded sequence {entry.get('sequence')}"
            )
        if entry.get("previous_sha256") != previous:
            raise ApprovalLedgerError(
                f"{where} does not chain to its predecessor; the ledger was edited"
            )
        recorded = _hash(entry.get("entry_sha256"), f"{where}.entry_sha256")
        if _entry_digest(entry) != recorded:
            raise ApprovalLedgerError(f"{where} digest does not match its content")
        previous = recorded

    anchor = verify_anchor(external_anchor, path)
    return {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "entries": len(entries),
        "chain_intact": True,
        "head_sha256": previous,
        "assurance_level": anchor["assurance_level"],
        "authenticated": anchor["authenticated"],
        "assurance_reason": anchor["reason"],
        # Stated explicitly so a downstream summary cannot imply otherwise.
        "actor_separation_is_asserted_not_authenticated": not anchor["authenticated"],
    }


def validate_approval_binding(
    approval: Dict[str, Any],
    *,
    object_sha256: str,
    ledger_verification: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Bind an approval to an exact object and separate actors.

    Separation of producer and approver is checked, and reported as an
    assertion unless the ledger verification carries a verified anchor.
    """
    if not isinstance(approval, dict):
        raise ApprovalLedgerError("approval must be an object")
    expected = _hash(object_sha256, "object_sha256")
    recorded = _hash(approval.get("object_sha256"), "approval.object_sha256")
    if recorded != expected:
        raise ApprovalLedgerError(
            f"approval targets a different object: recorded {recorded}, "
            f"actual {expected}"
        )
    _text(approval.get("approved_by"), "approval.approved_by")
    _text(approval.get("approved_at"), "approval.approved_at")
    _text(approval.get("assertion"), "approval.assertion")

    items = approval.get("approved_items")
    if not isinstance(items, dict) or not items:
        raise ApprovalLedgerError("approval.approved_items must be a non-empty object")
    unapproved = sorted(key for key, value in items.items() if value is not True)
    if unapproved:
        raise ApprovalLedgerError(f"approval items must be true: {unapproved}")

    producer = _text(approval.get("producer_session_id"), "approval.producer_session_id")
    approver = _text(approval.get("approver_session_id"), "approval.approver_session_id")
    if producer == approver:
        raise ApprovalLedgerError(
            "the producing session cannot approve its own object; a lock that "
            "accepts self-approval records an untrue claim"
        )

    authenticated = bool(ledger_verification and ledger_verification.get("authenticated"))
    return {
        "object_sha256": expected,
        "approved_by": approval["approved_by"],
        "producer_session_id": producer,
        "approver_session_id": approver,
        "separation": "DISTINCT_SESSIONS_ASSERTED",
        "assurance_level": EXTERNALLY_ANCHORED if authenticated else SELF_ASSERTED,
        "authenticated": authenticated,
        "disclosure": (
            "Approval is bound to the object hash and recorded in an append-only "
            "ledger. "
            + (
                "Actor separation is anchored to a runtime-issued artifact."
                if authenticated
                else "Actor separation is asserted and not independently "
                "authenticated."
            )
        ),
    }
