"""Uniform workspace lifecycle for systematic-review skills.

Every material run owns exactly one directory, consumers read hash-bound
handoffs, and the current view of a review is *derived* rather than guessed
from folder existence.

What this module guarantees, and what it deliberately does not:

* **Ownership.** A run writes under ``runs/<phase-id>/<run-id>/`` and nowhere
  else. A producer can never create a consumer's run or output directory,
  because every write is checked against its own declared scope.
* **Terminal states require directory-ledger agreement.** A run is complete or
  failed only when its one terminal manifest agrees with its ledger event. New
  runs also bind their exact input provenance in ``RUN_STARTED``; a folder or
  manifest on its own asserts no terminal status.
* **Fail-closed paths.** New paths are created with ``O_EXCL`` semantics.
  Nothing is overwritten, no symlink below the root is followed, and no path
  escaping its declared root is accepted.
* **Recorded timestamps are assertions.** The vocabulary keeps that visible
  (``RECORDED_ASSERTION_UNVERIFIED``) so a Methods section cannot quietly
  upgrade a recorded string into verified provenance.

This layer is additive. It wraps the existing phase-specific manifests, SQLite
stores, locks, and schemas by reference; it never replaces or rewrites them,
and it reuses :mod:`artifact_ref` and :mod:`approval_ledger` rather than
growing a second hashing or ledger implementation.

The public lifecycle signatures remain the revision-5 interface. Later closure
briefs strengthened their shared reconciliation, provenance binding, portable
identifier namespaces, and CLI behavior without changing those signatures.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any, Dict, Iterable, List, Optional, Sequence

import approval_ledger
import artifact_ref


SCHEMA_VERSION = "systematic-review-workspace-1.0"
TOOL_VERSION = "workspace-lifecycle-1.0"

REVIEW_MANIFEST_NAME = "review_manifest.json"
INPUTS_MANIFEST_NAME = "inputs_manifest.json"
RUN_MANIFEST_NAME = "run_manifest.json"
FAILURE_MANIFEST_NAME = "failure_manifest.json"
HANDOFF_MANIFEST_NAME = "handoff_manifest.json"
REVIEW_STATE_NAME = "review_state.json"

RUNS_DIR_NAME = "runs"
OUTPUTS_DIR_NAME = "outputs"
HANDOFFS_DIR_NAME = "handoffs"
LEDGER_DIR_NAME = "ledger"
LEDGER_FILE_NAME = "execution.jsonl"
STATE_DIR_NAME = "state"

RECORD_REVIEW = "WORKSPACE_REVIEW_MANIFEST"
RECORD_INPUTS = "WORKSPACE_INPUTS_MANIFEST"
RECORD_RUN = "WORKSPACE_RUN_MANIFEST"
RECORD_FAILURE = "WORKSPACE_FAILURE_MANIFEST"
RECORD_HANDOFF = "WORKSPACE_HANDOFF_MANIFEST"
RECORD_STATE = "WORKSPACE_REVIEW_STATE"

STATUS_STARTED = "STARTED"
STATUS_COMPLETED = "COMPLETED"
STATUS_LOCKED = "LOCKED"
STATUS_FAILED = "FAILED"
TERMINAL_SUCCESS_STATUSES = (STATUS_COMPLETED, STATUS_LOCKED)
TERMINAL_STATUSES = (STATUS_COMPLETED, STATUS_LOCKED, STATUS_FAILED)

EVENT_REVIEW_INITIALIZED = "REVIEW_INITIALIZED"
EVENT_RUN_STARTED = "RUN_STARTED"
EVENT_RUN_COMPLETED = "RUN_COMPLETED"
EVENT_RUN_LOCKED = "RUN_LOCKED"
EVENT_RUN_FAILED = "RUN_FAILED"
EVENT_HANDOFF_CREATED = "HANDOFF_CREATED"
EVENT_LEGACY_RUN_REGISTERED = "LEGACY_RUN_REGISTERED"

WORKSPACE_EVENT_TYPES = (
    EVENT_REVIEW_INITIALIZED,
    EVENT_RUN_STARTED,
    EVENT_RUN_COMPLETED,
    EVENT_RUN_LOCKED,
    EVENT_RUN_FAILED,
    EVENT_HANDOFF_CREATED,
    EVENT_LEGACY_RUN_REGISTERED,
)

TERMINAL_EVENT_STATUS = {
    EVENT_RUN_COMPLETED: STATUS_COMPLETED,
    EVENT_RUN_LOCKED: STATUS_LOCKED,
    EVENT_RUN_FAILED: STATUS_FAILED,
}

# Phase status is derived, and a run still in flight is the most actionable
# fact about a phase, so it wins over an older terminal run.
PHASE_STATUS_PRECEDENCE = (
    STATUS_STARTED,
    STATUS_LOCKED,
    STATUS_COMPLETED,
    STATUS_FAILED,
)

STATE_DERIVATION = (
    "Generated from the verified append-only ledger and the terminal run "
    "manifests it names. Directory existence is never read as a status, and "
    "this file is never hand-maintained. A phase appears here only once the "
    "ledger records work for it, so a phase's absence means no run exists, "
    "not that it is ready to start. required_inputs_available reports whether "
    "every input ArtifactRef recorded by that phase's runs still verifies; it "
    "is not a readiness judgment."
)

# A recorded timestamp is a string an agent wrote. Saying so in the artifact
# keeps a later summary from calling it verified provenance.
TIMESTAMP_ASSURANCE = "RECORDED_ASSERTION_UNVERIFIED"

# Legacy artifacts are registered by reference only; their bytes and paths are
# never moved or rewritten.
LEGACY_IMPORT_DISCLOSURE = (
    "Legacy artifacts are registered by reference. Their bytes and paths are "
    "unchanged and remain owned by the phase that produced them."
)

# Reserved role. A phase contract that genuinely requires a frozen export
# corpus records it as one already-verified producer output under this role;
# the handoff then names it explicitly instead of inventing a second copy
# mechanism.
FROZEN_EXPORT_ROLE = "frozen-export-corpus"

_DEFAULT_SESSION_ID = "workspace-{0}-{1}".format(
    os.getpid(), datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
)

IDENTIFIER_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
TIMESTAMP_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")

# Exactly these entries may exist inside a run directory. Anything else means a
# run is holding something it does not own.
ALLOWED_RUN_ENTRIES = frozenset(
    {
        INPUTS_MANIFEST_NAME,
        OUTPUTS_DIR_NAME,
        RUN_MANIFEST_NAME,
        FAILURE_MANIFEST_NAME,
    }
)

# A handoff describes what a producer offers. It never carries the consumer's
# status or output location, because a producer cannot know either.
FORBIDDEN_HANDOFF_FIELDS = (
    "consumer_status",
    "consumer_run_id",
    "consumer_run_dir",
    "consumer_outputs",
    "consumer_output_dir",
    "downstream_status",
    "downstream_outputs",
    "output_path",
    "outputs",
    "run_manifest",
    "status",
    "state",
)


class WorkspaceLifecycleError(ValueError):
    """Raised when a workspace path, schema, identifier, or state is invalid.

    Subclasses ``ValueError`` so skill entry points already map it to a nonzero
    exit code with a concise stderr message.
    """


# --------------------------------------------------------------------------
# scalar validation
# --------------------------------------------------------------------------


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkspaceLifecycleError(f"{field} must be a non-empty string")
    return value


def validate_identifier(value: Any, field: str) -> str:
    """Confirm ``value`` is usable as exactly one safe path segment.

    Identifiers must not be traversal segments, contain separators, or carry
    surrounding whitespace, because every one of them is interpolated into a
    real directory name.
    """
    text = _text(value, field)
    if not IDENTIFIER_PATTERN.fullmatch(text):
        raise WorkspaceLifecycleError(
            f"{field} must match {IDENTIFIER_PATTERN.pattern} "
            f"and name exactly one path segment: {text!r}"
        )
    return text


def validate_timestamp(value: Any, field: str) -> str:
    """Confirm ``value`` is an RFC 3339 UTC timestamp, as a recorded claim."""
    text = _text(value, field)
    if not TIMESTAMP_PATTERN.fullmatch(text):
        raise WorkspaceLifecycleError(
            f"{field} must be a UTC timestamp like 2026-07-31T02:51:36Z: {text!r}"
        )
    return text


def validate_sequence_number(value: Any, field: str) -> int:
    """Confirm ``value`` is a positive ledger sequence number."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise WorkspaceLifecycleError(f"{field} must be a positive integer")
    return value


def utc_timestamp() -> str:
    """Return the current UTC time in the recorded-assertion format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def validate_unique_identifiers(
    values: Sequence[Any], field: str
) -> List[str]:
    """Validate a list of identifiers and refuse duplicates.

    Duplicates are detected case-insensitively: two identifiers differing only
    in case would collide on a case-insensitive filesystem, and a collision
    that only appears on some machines is worse than a refusal on all of them.
    """
    if not isinstance(values, (list, tuple)):
        raise WorkspaceLifecycleError(f"{field} must be a list")
    validated = [
        validate_identifier(value, f"{field}[{index}]")
        for index, value in enumerate(values)
    ]
    folded = [value.lower() for value in validated]
    duplicates = sorted({value for value in folded if folded.count(value) > 1})
    if duplicates:
        raise WorkspaceLifecycleError(
            f"{field} contains duplicate identifiers: " + ", ".join(duplicates)
        )
    return validated


# --------------------------------------------------------------------------
# path rules
# --------------------------------------------------------------------------


def _lexical_relative(target: Path, root: Path) -> Path:
    """Return ``target`` relative to ``root`` without following symlinks.

    ``os.path.normpath`` collapses ``..`` lexically, so an escaping path stops
    being relative to the root and is refused below rather than silently
    resolved through a link.
    """
    normalized = Path(os.path.normpath(str(target)))
    for base in (Path(os.path.normpath(str(root))), root.resolve()):
        try:
            return normalized.relative_to(base)
        except ValueError:
            continue
    raise WorkspaceLifecycleError(f"{target} escapes declared root {root}")


def assert_within_root(root: str, path: str) -> Path:
    """Confirm ``path`` sits inside ``root`` with no symlink below the root.

    Parent directories *above* the root may be symlinks — that keeps ordinary
    locations such as ``/tmp`` usable, matching ``artifact_ref`` — but no
    component the workspace itself owns may be one.
    """
    _text(root, "root")
    _text(path, "path")
    root_path = Path(root)
    if not root_path.is_absolute():
        raise WorkspaceLifecycleError(f"review root must be absolute: {root}")

    candidate = Path(path)
    if candidate.is_absolute():
        relative = _lexical_relative(candidate, root_path)
    else:
        if ".." in candidate.parts:
            raise WorkspaceLifecycleError(
                f"path must not traverse upward: {path}"
            )
        relative = candidate

    resolved_root = root_path.resolve()
    current = resolved_root
    for part in relative.parts:
        if part in (".", ".."):
            raise WorkspaceLifecycleError(
                f"path must not traverse upward: {path}"
            )
        current = current / part
        if current.is_symlink():
            raise WorkspaceLifecycleError(
                f"workspace path component is a symlink: {current}"
            )
    return current


def review_manifest_path(root: str) -> Path:
    """Derive ``<root>/review_manifest.json``."""
    return assert_within_root(root, REVIEW_MANIFEST_NAME)


def ledger_path(root: str) -> Path:
    """Derive ``<root>/ledger/execution.jsonl``."""
    return assert_within_root(root, f"{LEDGER_DIR_NAME}/{LEDGER_FILE_NAME}")


def state_path(root: str) -> Path:
    """Derive ``<root>/state/review_state.json``."""
    return assert_within_root(root, f"{STATE_DIR_NAME}/{REVIEW_STATE_NAME}")


def phase_dir(root: str, phase_id: str) -> Path:
    """Derive ``<root>/runs/<phase-id>``."""
    validate_identifier(phase_id, "phase_id")
    return assert_within_root(root, f"{RUNS_DIR_NAME}/{phase_id}")


def run_dir(root: str, phase_id: str, run_id: str) -> Path:
    """Derive the one directory a material run owns."""
    validate_identifier(phase_id, "phase_id")
    validate_identifier(run_id, "run_id")
    return assert_within_root(root, f"{RUNS_DIR_NAME}/{phase_id}/{run_id}")


def run_outputs_dir(root: str, phase_id: str, run_id: str) -> Path:
    """Derive ``<run-dir>/outputs`` — the only outputs a run may own."""
    return run_dir(root, phase_id, run_id) / OUTPUTS_DIR_NAME


def inputs_manifest_path(root: str, phase_id: str, run_id: str) -> Path:
    """Derive ``<run-dir>/inputs_manifest.json``."""
    return run_dir(root, phase_id, run_id) / INPUTS_MANIFEST_NAME


def run_manifest_path(root: str, phase_id: str, run_id: str) -> Path:
    """Derive ``<run-dir>/run_manifest.json`` — success only."""
    return run_dir(root, phase_id, run_id) / RUN_MANIFEST_NAME


def failure_manifest_path(root: str, phase_id: str, run_id: str) -> Path:
    """Derive ``<run-dir>/failure_manifest.json`` — failure only."""
    return run_dir(root, phase_id, run_id) / FAILURE_MANIFEST_NAME


def handoff_dir(
    root: str, producer_run_id: str, consumer_skill: str, handoff_id: str
) -> Path:
    """Derive the consumer-specific handoff directory.

    Handoffs live outside the immutable producer run so preparing one never
    mutates a locked run directory.
    """
    validate_identifier(producer_run_id, "producer_run_id")
    validate_identifier(consumer_skill, "consumer_skill")
    validate_identifier(handoff_id, "handoff_id")
    return assert_within_root(
        root,
        f"{HANDOFFS_DIR_NAME}/{producer_run_id}/{consumer_skill}/{handoff_id}",
    )


def handoff_manifest_path(
    root: str, producer_run_id: str, consumer_skill: str, handoff_id: str
) -> Path:
    """Derive ``<handoff-dir>/handoff_manifest.json``."""
    return (
        handoff_dir(root, producer_run_id, consumer_skill, handoff_id)
        / HANDOFF_MANIFEST_NAME
    )


def assert_producer_scope(
    root: str, *, phase_id: str, run_id: str, path: str
) -> Path:
    """Confirm a producer is writing only inside its own run directory.

    This is the control that stops a Phase 1 run from creating a Phase 10 run
    or output directory: a producer may prepare a *handoff* for a distant
    consumer, but the consumer's run is the consumer's to create.
    """
    owned = run_dir(root, phase_id, run_id)
    target = assert_within_root(root, path)
    try:
        target.relative_to(owned)
    except ValueError:
        raise WorkspaceLifecycleError(
            f"run {phase_id}/{run_id} may not write outside its own directory: "
            f"{target}"
        ) from None
    return target


def assert_run_directory_layout(path: str) -> Dict[str, Any]:
    """Confirm a run directory holds only what a run owns, and read its state.

    Returns the observed status. ``STARTED`` means nonterminal: the directory
    exists but no terminal manifest declares completion. Folder existence is
    never a status.
    """
    _text(path, "run_dir")
    directory = Path(path)
    if directory.is_symlink():
        raise WorkspaceLifecycleError(f"run directory must not be a symlink: {path}")
    if not directory.is_dir():
        raise WorkspaceLifecycleError(f"run directory is missing: {path}")

    entries = list(directory.iterdir())
    symlinks = sorted(entry.name for entry in entries if entry.is_symlink())
    if symlinks:
        raise WorkspaceLifecycleError(
            f"run directory {path} contains symlinks: " + ", ".join(symlinks)
        )
    unexpected = sorted(
        entry.name
        for entry in entries
        if entry.name not in ALLOWED_RUN_ENTRIES
    )
    if unexpected:
        raise WorkspaceLifecycleError(
            f"run directory {path} holds entries it does not own: "
            + ", ".join(unexpected)
        )

    outputs = directory / OUTPUTS_DIR_NAME
    if outputs.exists() and not outputs.is_dir():
        raise WorkspaceLifecycleError(f"{outputs} must be a directory")

    completed = (directory / RUN_MANIFEST_NAME).is_file()
    failed = (directory / FAILURE_MANIFEST_NAME).is_file()
    if completed and failed:
        raise WorkspaceLifecycleError(
            f"run directory {path} carries both a run and a failure manifest; "
            "terminal manifests are mutually exclusive"
        )
    return {
        "run_dir": str(directory),
        "terminal": completed or failed,
        "status": STATUS_FAILED
        if failed
        else (_terminal_status(directory) if completed else STATUS_STARTED),
        "has_inputs_manifest": (directory / INPUTS_MANIFEST_NAME).is_file(),
        "has_outputs_dir": outputs.is_dir(),
    }


def _terminal_status(directory: Path) -> str:
    manifest = read_json(str(directory / RUN_MANIFEST_NAME))
    validate_run_manifest(manifest)
    return manifest["status"]


# --------------------------------------------------------------------------
# canonical serialization and fail-closed writes
# --------------------------------------------------------------------------


def canonical_bytes(value: object) -> bytes:
    """Return the canonical serialization used for every workspace record.

    The bytes written to disk *are* this serialization, so the SHA-256 of a
    workspace JSON file equals ``artifact_ref.canonical_json_sha256`` of its
    value. That keeps one digest meaningful in both directions.
    """
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def canonical_sha256(value: object) -> str:
    """Return the canonical-JSON digest, reusing the shared implementation."""
    return artifact_ref.canonical_json_sha256(value)


def _inputs_binding_basis(value: Dict[str, Any]) -> Dict[str, Any]:
    """Return the security-relevant inputs state fixed at run start."""
    return {
        "binding_type": "WORKSPACE_INPUTS_START_BINDING",
        "schema_version": SCHEMA_VERSION,
        "review_id": value["review_id"],
        "phase_id": value["phase_id"],
        "skill_id": value["skill_id"],
        "run_id": value["run_id"],
        "inputs": value["inputs"],
        "parent_run_ids": value["parent_run_ids"],
        "consumed_handoff_ids": value["consumed_handoff_ids"],
    }


def _inputs_binding_sha256(value: Dict[str, Any]) -> str:
    """Digest the run-start provenance fields in canonical form."""
    return canonical_sha256(_inputs_binding_basis(value))


def _terminal_manifest_binding_basis(value: Dict[str, Any]) -> Dict[str, Any]:
    """Return the complete terminal assertion bound by its ledger event.

    The ledger assigns ``terminal_ledger_sequence`` when the event is appended,
    so that one field is bound by the event's actual position instead of being
    included in this pre-append basis. Copying the record generically keeps a
    later schema field from being omitted accidentally.
    """
    if not isinstance(value, dict):
        raise WorkspaceLifecycleError("terminal manifest must be an object")
    assertion = dict(value)
    assertion.pop("terminal_ledger_sequence", None)
    return {
        "binding_type": "WORKSPACE_TERMINAL_MANIFEST_BINDING",
        "schema_version": SCHEMA_VERSION,
        "terminal_manifest": assertion,
    }


def _terminal_manifest_binding_sha256(value: Dict[str, Any]) -> str:
    """Digest the complete terminal assertion in canonical form."""
    return canonical_sha256(_terminal_manifest_binding_basis(value))


def _canonical_json_artifact_ref(
    path: str, role: str, version: str, status: str, value: Dict[str, Any]
) -> Dict[str, Any]:
    """Build an ArtifactRef for a canonical JSON record before it is written."""
    payload = canonical_bytes(value)
    return {
        "schema_version": artifact_ref.SCHEMA_VERSION,
        "path": str(Path(path)),
        "role": role,
        "version": version,
        "status": status,
        "sha256": canonical_sha256(value),
        "bytes": len(payload),
    }


def create_new_directory(root: str, path: str) -> Path:
    """Create a directory that must not already exist.

    Reuse of an existing destination is a refusal, never a silent merge.
    """
    target = assert_within_root(root, path)
    try:
        target.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        raise WorkspaceLifecycleError(
            f"destination already exists and is never reused: {target}"
        ) from None
    return target


def write_new_json(root: str, path: str, value: Dict[str, Any]) -> Path:
    """Write a canonical JSON record to a path that must not already exist.

    The parent directory must exist: creating it here would let a caller
    conjure a directory it never declared.
    """
    if not isinstance(value, dict):
        raise WorkspaceLifecycleError("workspace records must be objects")
    target = assert_within_root(root, path)
    if not target.parent.is_dir():
        raise WorkspaceLifecycleError(
            f"parent directory does not exist: {target.parent}"
        )
    try:
        descriptor = os.open(
            str(target), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644
        )
    except FileExistsError:
        raise WorkspaceLifecycleError(
            f"workspace records are never overwritten: {target}"
        ) from None
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(canonical_bytes(value))
    return target


def read_json(path: str) -> Dict[str, Any]:
    """Read a workspace record without following a symlink."""
    _text(path, "path")
    target = Path(path)
    if target.is_symlink():
        raise WorkspaceLifecycleError(f"record must not be a symlink: {path}")
    if not target.is_file():
        raise WorkspaceLifecycleError(f"record is missing: {path}")
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise WorkspaceLifecycleError(f"record is not valid JSON: {path}") from exc


# --------------------------------------------------------------------------
# schema validation
# --------------------------------------------------------------------------


def _validate_envelope(value: Any, record_type: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise WorkspaceLifecycleError(f"{record_type} must be an object")
    if value.get("schema_version") != SCHEMA_VERSION:
        raise WorkspaceLifecycleError(
            f"{record_type} must declare schema_version {SCHEMA_VERSION!r}"
        )
    if value.get("record_type") != record_type:
        raise WorkspaceLifecycleError(
            f"record_type must be {record_type!r}, not "
            f"{value.get('record_type')!r}"
        )
    return value


def _validate_fields(
    value: Dict[str, Any], record_type: str, allowed: Sequence[str]
) -> None:
    """Refuse unknown keys.

    A strict whitelist is what makes "no downstream status in a handoff"
    enforceable rather than aspirational.
    """
    unknown = sorted(set(value) - set(allowed))
    if unknown:
        raise WorkspaceLifecycleError(
            f"{record_type} carries unknown fields: " + ", ".join(unknown)
        )
    missing = sorted(set(allowed) - set(value))
    if missing:
        raise WorkspaceLifecycleError(
            f"{record_type} is missing fields: " + ", ".join(missing)
        )


def validate_artifact_refs(
    value: Any, field: str, *, allow_empty: bool = False
) -> List[Dict[str, Any]]:
    """Validate a list of ArtifactRefs and refuse duplicate roles.

    Roles are how a consumer asks for an artifact by meaning rather than by
    position, so an ambiguous role set is refused outright.
    """
    if not isinstance(value, (list, tuple)):
        raise WorkspaceLifecycleError(f"{field} must be a list")
    if not value and not allow_empty:
        raise WorkspaceLifecycleError(f"{field} must not be empty")
    refs: List[Dict[str, Any]] = []
    for index, ref in enumerate(value):
        where = f"{field}[{index}]"
        if not isinstance(ref, dict):
            raise WorkspaceLifecycleError(f"{where} must be an object")
        for required in artifact_ref.REQUIRED_REF_FIELDS:
            if required not in ref:
                raise WorkspaceLifecycleError(f"{where} is missing {required}")
        digest = _text(ref.get("sha256"), f"{where}.sha256")
        if not artifact_ref.HASH_PATTERN.fullmatch(digest):
            raise WorkspaceLifecycleError(
                f"{where}.sha256 must be a lowercase SHA-256 digest"
            )
        size = ref.get("bytes")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise WorkspaceLifecycleError(
                f"{where}.bytes must be a non-negative integer"
            )
        validate_identifier(ref.get("role"), f"{where}.role")
        refs.append(ref)
    validate_unique_identifiers([ref["role"] for ref in refs], f"{field} roles")
    return refs


def validate_review_manifest(value: Any) -> Dict[str, Any]:
    """Validate ``review_manifest.json``."""
    record = _validate_envelope(value, RECORD_REVIEW)
    _validate_fields(
        record,
        RECORD_REVIEW,
        (
            "schema_version",
            "record_type",
            "review_id",
            "tool_version",
            "created_at",
            "timestamp_assurance",
        ),
    )
    validate_identifier(record["review_id"], "review_id")
    _text(record["tool_version"], "tool_version")
    validate_timestamp(record["created_at"], "created_at")
    _require_timestamp_assurance(record)
    return record


def validate_inputs_manifest(value: Any) -> Dict[str, Any]:
    """Validate ``inputs_manifest.json``.

    Inputs are recorded separately from outputs so a consumer's view of what it
    read can never be confused with what it produced.
    """
    record = _validate_envelope(value, RECORD_INPUTS)
    _validate_fields(
        record,
        RECORD_INPUTS,
        (
            "schema_version",
            "record_type",
            "review_id",
            "phase_id",
            "skill_id",
            "run_id",
            "inputs",
            "parent_run_ids",
            "consumed_handoff_ids",
            "start_ledger_sequence",
            "created_at",
            "timestamp_assurance",
        ),
    )
    _validate_run_identity(record)
    validate_artifact_refs(record["inputs"], "inputs", allow_empty=True)
    validate_unique_identifiers(record["parent_run_ids"], "parent_run_ids")
    validate_unique_identifiers(
        record["consumed_handoff_ids"], "consumed_handoff_ids"
    )
    validate_sequence_number(
        record["start_ledger_sequence"], "start_ledger_sequence"
    )
    validate_timestamp(record["created_at"], "created_at")
    _require_timestamp_assurance(record)
    return record


def validate_run_manifest(value: Any) -> Dict[str, Any]:
    """Validate ``run_manifest.json`` — the only declaration of success."""
    record = _validate_envelope(value, RECORD_RUN)
    _validate_fields(
        record,
        RECORD_RUN,
        (
            "schema_version",
            "record_type",
            "review_id",
            "phase_id",
            "skill_id",
            "run_id",
            "status",
            "inputs_manifest",
            "outputs",
            "parent_run_ids",
            "consumed_handoff_ids",
            "downstream_consumers",
            "start_ledger_sequence",
            "terminal_ledger_sequence",
            "created_at",
            "completed_at",
            "timestamp_assurance",
            "tool_version",
        ),
    )
    _validate_run_identity(record)
    if record["status"] not in TERMINAL_SUCCESS_STATUSES:
        raise WorkspaceLifecycleError(
            "run_manifest.json declares success only; status must be one of "
            + ", ".join(TERMINAL_SUCCESS_STATUSES)
        )
    validate_artifact_refs([record["inputs_manifest"]], "inputs_manifest")
    validate_artifact_refs(record["outputs"], "outputs")
    validate_unique_identifiers(record["parent_run_ids"], "parent_run_ids")
    validate_unique_identifiers(
        record["consumed_handoff_ids"], "consumed_handoff_ids"
    )
    validate_unique_identifiers(
        record["downstream_consumers"], "downstream_consumers"
    )
    start = validate_sequence_number(
        record["start_ledger_sequence"], "start_ledger_sequence"
    )
    terminal = validate_sequence_number(
        record["terminal_ledger_sequence"], "terminal_ledger_sequence"
    )
    if terminal <= start:
        raise WorkspaceLifecycleError(
            "terminal_ledger_sequence must follow start_ledger_sequence"
        )
    validate_timestamp(record["created_at"], "created_at")
    validate_timestamp(record["completed_at"], "completed_at")
    _require_timestamp_assurance(record)
    _text(record["tool_version"], "tool_version")
    return record


def validate_failure_manifest(value: Any) -> Dict[str, Any]:
    """Validate ``failure_manifest.json`` — the only declaration of failure."""
    record = _validate_envelope(value, RECORD_FAILURE)
    _validate_fields(
        record,
        RECORD_FAILURE,
        (
            "schema_version",
            "record_type",
            "review_id",
            "phase_id",
            "skill_id",
            "run_id",
            "status",
            "reason_code",
            "message",
            "inputs_manifest",
            "start_ledger_sequence",
            "terminal_ledger_sequence",
            "created_at",
            "failed_at",
            "timestamp_assurance",
            "tool_version",
        ),
    )
    _validate_run_identity(record)
    if record["status"] != STATUS_FAILED:
        raise WorkspaceLifecycleError(
            f"failure_manifest.json status must be {STATUS_FAILED!r}"
        )
    validate_identifier(record["reason_code"], "reason_code")
    _text(record["message"], "message")
    validate_artifact_refs([record["inputs_manifest"]], "inputs_manifest")
    start = validate_sequence_number(
        record["start_ledger_sequence"], "start_ledger_sequence"
    )
    terminal = validate_sequence_number(
        record["terminal_ledger_sequence"], "terminal_ledger_sequence"
    )
    if terminal <= start:
        raise WorkspaceLifecycleError(
            "terminal_ledger_sequence must follow start_ledger_sequence"
        )
    validate_timestamp(record["created_at"], "created_at")
    validate_timestamp(record["failed_at"], "failed_at")
    _require_timestamp_assurance(record)
    _text(record["tool_version"], "tool_version")
    return record


def validate_handoff_manifest(value: Any) -> Dict[str, Any]:
    """Validate ``handoff_manifest.json``.

    A handoff says what a producer offers and to whom. It never carries the
    consumer's status or output path — a producer cannot know either, and a
    field that looked authoritative would invite exactly that mistake.
    """
    if isinstance(value, dict):
        present = sorted(set(value) & set(FORBIDDEN_HANDOFF_FIELDS))
        if present:
            raise WorkspaceLifecycleError(
                "a handoff manifest never carries downstream status or output "
                "paths: " + ", ".join(present)
            )
    record = _validate_envelope(value, RECORD_HANDOFF)
    _validate_fields(
        record,
        RECORD_HANDOFF,
        (
            "schema_version",
            "record_type",
            "review_id",
            "handoff_id",
            "producer_phase_id",
            "producer_skill_id",
            "producer_run_id",
            "producer_run_manifest",
            "consumer_skill",
            "artifacts",
            "frozen_export",
            "created_ledger_sequence",
            "created_at",
            "timestamp_assurance",
            "tool_version",
        ),
    )
    validate_identifier(record["review_id"], "review_id")
    validate_identifier(record["handoff_id"], "handoff_id")
    validate_identifier(record["producer_phase_id"], "producer_phase_id")
    validate_identifier(record["producer_skill_id"], "producer_skill_id")
    validate_identifier(record["producer_run_id"], "producer_run_id")
    validate_identifier(record["consumer_skill"], "consumer_skill")
    validate_artifact_refs(
        [record["producer_run_manifest"]], "producer_run_manifest"
    )
    validate_artifact_refs(record["artifacts"], "artifacts")
    if record["frozen_export"] is not None:
        validate_artifact_refs([record["frozen_export"]], "frozen_export")
    validate_sequence_number(
        record["created_ledger_sequence"], "created_ledger_sequence"
    )
    validate_timestamp(record["created_at"], "created_at")
    _require_timestamp_assurance(record)
    _text(record["tool_version"], "tool_version")
    return record


def validate_review_state(value: Any) -> Dict[str, Any]:
    """Validate the generated ``review_state.json`` view.

    The record names its sources so a reader can tell a derived view from a
    hand-maintained one at a glance.
    """
    record = _validate_envelope(value, RECORD_STATE)
    _validate_fields(
        record,
        RECORD_STATE,
        (
            "schema_version",
            "record_type",
            "review_id",
            "generated_at",
            "generated_from_ledger_head",
            "generated_from_ledger_entries",
            "phases",
            "timestamp_assurance",
            "tool_version",
            "derivation",
        ),
    )
    validate_identifier(record["review_id"], "review_id")
    validate_timestamp(record["generated_at"], "generated_at")
    head = _text(
        record["generated_from_ledger_head"], "generated_from_ledger_head"
    )
    if not artifact_ref.HASH_PATTERN.fullmatch(head):
        raise WorkspaceLifecycleError(
            "generated_from_ledger_head must be a lowercase SHA-256 digest"
        )
    entries = record["generated_from_ledger_entries"]
    if isinstance(entries, bool) or not isinstance(entries, int) or entries < 0:
        raise WorkspaceLifecycleError(
            "generated_from_ledger_entries must be a non-negative integer"
        )
    phases = record["phases"]
    if not isinstance(phases, dict):
        raise WorkspaceLifecycleError("phases must be an object")
    for phase_id, phase in phases.items():
        validate_identifier(phase_id, "phases key")
        if not isinstance(phase, dict):
            raise WorkspaceLifecycleError(f"phases[{phase_id}] must be an object")
        _validate_fields(
            phase,
            f"phases[{phase_id}]",
            ("status", "required_inputs_available", "runs"),
        )
        if phase["status"] not in (STATUS_STARTED,) + TERMINAL_STATUSES + (
            "NOT_STARTED",
        ):
            raise WorkspaceLifecycleError(
                f"phases[{phase_id}].status is not a known status"
            )
        if not isinstance(phase["required_inputs_available"], bool):
            raise WorkspaceLifecycleError(
                f"phases[{phase_id}].required_inputs_available must be boolean"
            )
        if not isinstance(phase["runs"], list):
            raise WorkspaceLifecycleError(f"phases[{phase_id}].runs must be a list")
    _require_timestamp_assurance(record)
    _text(record["tool_version"], "tool_version")
    _text(record["derivation"], "derivation")
    return record


def _validate_run_identity(record: Dict[str, Any]) -> None:
    validate_identifier(record["review_id"], "review_id")
    validate_identifier(record["phase_id"], "phase_id")
    validate_identifier(record["skill_id"], "skill_id")
    validate_identifier(record["run_id"], "run_id")


def _require_timestamp_assurance(record: Dict[str, Any]) -> None:
    if record.get("timestamp_assurance") != TIMESTAMP_ASSURANCE:
        raise WorkspaceLifecycleError(
            f"timestamp_assurance must be {TIMESTAMP_ASSURANCE!r}; a recorded "
            "timestamp is an assertion, not verified provenance"
        )


VALIDATORS = {
    RECORD_REVIEW: validate_review_manifest,
    RECORD_INPUTS: validate_inputs_manifest,
    RECORD_RUN: validate_run_manifest,
    RECORD_FAILURE: validate_failure_manifest,
    RECORD_HANDOFF: validate_handoff_manifest,
    RECORD_STATE: validate_review_state,
}


def validate_record(value: Any) -> Dict[str, Any]:
    """Validate any workspace record by its declared ``record_type``."""
    if not isinstance(value, dict):
        raise WorkspaceLifecycleError("workspace records must be objects")
    validator = VALIDATORS.get(value.get("record_type"))
    if validator is None:
        raise WorkspaceLifecycleError(
            f"unknown record_type: {value.get('record_type')!r}"
        )
    return validator(value)


# --------------------------------------------------------------------------
# read-only verification helpers
# --------------------------------------------------------------------------


def verify_artifact_refs(
    refs: Iterable[Dict[str, Any]],
    *,
    field: str = "artifacts",
    root: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Recompute every reference, refusing missing or changed sources.

    ``root`` is optional because legacy artifacts stay where their producing
    phase left them, which may be outside the review root.
    """
    listed = list(refs)
    validate_artifact_refs(listed, field, allow_empty=True)
    try:
        return [
            artifact_ref.verify_artifact_ref(ref, root=root) for ref in listed
        ]
    except artifact_ref.ArtifactRefError as exc:
        raise WorkspaceLifecycleError(str(exc)) from exc


def _workspace_record_type(path: str) -> Optional[str]:
    """Return a recognized workspace record type, independent of filename."""
    try:
        value = read_json(path)
    except (OSError, ValueError, WorkspaceLifecycleError):
        return None
    if not isinstance(value, dict):
        return None
    record_type = value.get("record_type")
    return record_type if record_type in VALIDATORS else None


def _containing_workspace(path: str) -> Optional[Dict[str, str]]:
    """Find the nearest initialized review containing a resolved artifact."""
    candidate = Path(path).resolve()
    current = candidate if candidate.is_dir() else candidate.parent
    for directory in (current, *current.parents):
        manifest = directory / REVIEW_MANIFEST_NAME
        if not manifest.is_file():
            continue
        try:
            review = validate_review_manifest(read_json(str(manifest)))
        except (OSError, ValueError, WorkspaceLifecycleError):
            continue
        return {"root": str(directory.resolve()), "review_id": review["review_id"]}
    return None


def assert_outputs_owned(
    root: str, *, phase_id: str, run_id: str, outputs: Iterable[Dict[str, Any]]
) -> List[Path]:
    """Confirm every declared output lives inside this run's ``outputs/``."""
    owned = run_outputs_dir(root, phase_id, run_id)
    resolved: List[Path] = []
    for index, ref in enumerate(outputs):
        declared = _text(ref.get("path"), f"outputs[{index}].path")
        candidate = Path(declared)
        target = (
            assert_within_root(root, declared)
            if candidate.is_absolute()
            else assert_within_root(root, str(Path(root) / candidate))
        )
        try:
            target.relative_to(owned)
        except ValueError:
            raise WorkspaceLifecycleError(
                f"outputs[{index}] is not owned by run {phase_id}/{run_id}: "
                f"{target}"
            ) from None
        resolved.append(target)
    return resolved


def reconcile_run_with_ledger(
    run_dir: str,
    *,
    context: Optional[Dict[str, Any]] = None,
    ledger_runs: Optional[Dict[tuple, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """The single definition of terminality: directory and ledger must agree.

    A run is terminal only when its directory carries exactly one terminal
    manifest *and* the append-only ledger records the matching terminal event.
    Disagreement is refused, never resolved.

    This exists exactly once, and every command that reads a run's status goes
    through it. Two implementations drifted apart once already: manifest-only
    checking let a hand-written `run_manifest.json` publish a handoff that
    verified cleanly while derived state refused it.

    It authenticates nothing. An agent that can write the workspace can write
    both the manifest and the ledger entry, and ``verify_ledger`` still reports
    ``SELF_ASSERTED_UNAUTHENTICATED``. What it removes is accidental and
    one-sided forgery: a copied run directory, a restored backup, a session
    that wrote the file instead of calling ``complete-run``.
    """
    context = context or _load_run_context(run_dir)
    phase_id, run_id = context["phase_id"], context["run_id"]
    review_id = _require_review(context["root"])["review_id"]
    if ledger_runs is None:
        ledger_runs = _ledger_run_index(context["root"], review_id)
    if context["inputs"]["review_id"] != review_id:
        raise WorkspaceLifecycleError(
            f"run {phase_id}/{run_id} records review "
            f"{context['inputs']['review_id']!r}, this review is {review_id!r}"
        )

    recorded = ledger_runs.get((phase_id, run_id))
    if recorded is None:
        raise WorkspaceLifecycleError(
            f"run {phase_id}/{run_id} has no ledger entry; a directory this "
            "layer never started is not a run"
        )
    layout = context["layout"]
    observed = layout["status"] if layout["terminal"] else None
    if recorded["terminal_status"] != observed:
        raise WorkspaceLifecycleError(
            f"run {phase_id}/{run_id} disagrees with the ledger: manifests say "
            f"{layout['status']}, the ledger says "
            f"{recorded['terminal_status'] or STATUS_STARTED}"
        )
    if context["inputs"]["skill_id"] != recorded["skill_id"]:
        raise WorkspaceLifecycleError(
            f"run {phase_id}/{run_id} records skill "
            f"{context['inputs']['skill_id']!r}, the ledger says "
            f"{recorded['skill_id']!r}"
        )
    binding = recorded["inputs_binding_sha256"]
    inputs_bound_at_start = binding is not None
    terminal_manifest_bound = False
    if binding is not None:
        observed_binding = _inputs_binding_sha256(context["inputs"])
        if observed_binding != binding:
            raise WorkspaceLifecycleError(
                f"hash mismatch: run {phase_id}/{run_id} inputs changed after "
                "RUN_STARTED; "
                f"ledger binds {binding}, current manifest hashes to "
                f"{observed_binding}"
            )
    if observed is not None:
        # Status agreement is not identity agreement. Everything the terminal
        # manifest asserts about itself is otherwise unchecked, so a completed
        # run could be re-labelled with a different skill or fabricated
        # sequences and still reconcile.
        failed = observed == STATUS_FAILED
        name = FAILURE_MANIFEST_NAME if failed else RUN_MANIFEST_NAME
        validator = validate_failure_manifest if failed else validate_run_manifest
        terminal = validator(read_json(str(Path(run_dir) / name)))
        for field in ("review_id", "phase_id", "run_id", "skill_id"):
            if terminal[field] != context["inputs"][field]:
                raise WorkspaceLifecycleError(
                    f"terminal manifest for {phase_id}/{run_id} records {field} "
                    f"{terminal[field]!r}, the run records "
                    f"{context['inputs'][field]!r}"
                )
        for field, expected in (
            ("start_ledger_sequence", recorded["start_sequence"]),
            ("terminal_ledger_sequence", recorded["terminal_sequence"]),
        ):
            if terminal[field] != expected:
                raise WorkspaceLifecycleError(
                    f"terminal manifest for {phase_id}/{run_id} records {field} "
                    f"{terminal[field]!r}, the ledger says {expected!r}"
                )
        # The inputs manifest is the anchor of every comparison above, so it is
        # itself verified. A recorded hash that nothing recomputes is not a
        # control: without this, a locked run's record of what it read, what it
        # descended from, and what it consumed stays editable after the fact.
        anchor = terminal["inputs_manifest"]
        declared = Path(anchor["path"])
        expected_path = Path(run_dir) / INPUTS_MANIFEST_NAME
        if declared.resolve() != expected_path.resolve():
            raise WorkspaceLifecycleError(
                f"terminal manifest for {phase_id}/{run_id} commits to "
                f"{declared}, not to this run's own {INPUTS_MANIFEST_NAME}"
            )
        verify_artifact_refs([anchor], field="inputs_manifest")
        if not failed:
            # Lineage and consumption are fixed when the run starts. A terminal
            # manifest restates them; it never revises them.
            for field in ("parent_run_ids", "consumed_handoff_ids"):
                if terminal[field] != context["inputs"][field]:
                    raise WorkspaceLifecycleError(
                        f"terminal manifest for {phase_id}/{run_id} records "
                        f"{field} {terminal[field]!r}, the inputs manifest "
                        f"records {context['inputs'][field]!r}"
                    )
            verify_artifact_refs(terminal["outputs"], field="outputs")
            if not recorded["legacy"]:
                assert_outputs_owned(
                    context["root"],
                    phase_id=phase_id,
                    run_id=run_id,
                    outputs=terminal["outputs"],
                )
        terminal_binding = recorded["terminal_manifest_binding_sha256"]
        if terminal_binding is None:
            if recorded["terminal_manifest_binding_required"]:
                raise WorkspaceLifecycleError(
                    f"terminal event for {phase_id}/{run_id} requires a "
                    "terminal manifest binding"
                )
        else:
            observed_terminal_binding = _terminal_manifest_binding_sha256(
                terminal
            )
            if observed_terminal_binding != terminal_binding:
                raise WorkspaceLifecycleError(
                    f"terminal manifest binding mismatch for {phase_id}/{run_id}: "
                    f"ledger binds {terminal_binding}, current manifest hashes "
                    f"to {observed_terminal_binding}"
                )
            terminal_manifest_bound = True
    return {
        "phase_id": phase_id,
        "run_id": run_id,
        "status": layout["status"],
        "terminal": layout["terminal"],
        "legacy": recorded["legacy"],
        "inputs_bound_at_start": inputs_bound_at_start,
        "terminal_manifest_bound": terminal_manifest_bound,
        "start_ledger_sequence": recorded["start_sequence"],
        "terminal_ledger_sequence": recorded["terminal_sequence"],
    }


def read_terminal_manifest(path: str) -> Dict[str, Any]:
    """Read and validate a run directory's terminal manifest.

    Refuses a nonterminal run rather than inferring completion from the
    directory's existence or contents, and refuses a terminal manifest the
    ledger does not corroborate.
    """
    context = _load_run_context(path)
    layout = context["layout"]
    if not layout["terminal"]:
        raise WorkspaceLifecycleError(
            f"run {path} is nonterminal; a directory without a terminal "
            "manifest never means complete"
        )
    reconcile_run_with_ledger(path, context=context)
    directory = Path(path)
    if layout["status"] == STATUS_FAILED:
        return validate_failure_manifest(
            read_json(str(directory / FAILURE_MANIFEST_NAME))
        )
    return validate_run_manifest(read_json(str(directory / RUN_MANIFEST_NAME)))


def assert_successful_producer(path: str) -> Dict[str, Any]:
    """Confirm a producer run terminated successfully.

    A handoff may only come from a terminal, successful producer: offering a
    consumer the outputs of a failed or in-flight run is exactly the silent
    stale-evidence failure this layer exists to prevent.
    """
    manifest = read_terminal_manifest(path)
    if manifest["status"] not in TERMINAL_SUCCESS_STATUSES:
        raise WorkspaceLifecycleError(
            f"producer run {path} did not succeed: status {manifest['status']}"
        )
    return manifest


def assert_consumer_match(manifest: Dict[str, Any], consumer_skill: str) -> str:
    """Confirm a handoff was addressed to exactly this consumer."""
    validate_identifier(consumer_skill, "consumer_skill")
    recorded = validate_handoff_manifest(manifest)["consumer_skill"]
    if recorded != consumer_skill:
        raise WorkspaceLifecycleError(
            f"handoff is addressed to {recorded!r}, not {consumer_skill!r}"
        )
    return recorded


def assert_unregistered(root: str, path: str) -> Path:
    """Confirm a destination is free before anything is created there."""
    target = assert_within_root(root, path)
    if target.exists():
        raise WorkspaceLifecycleError(
            f"destination already exists and is never reused: {target}"
        )
    return target


# --------------------------------------------------------------------------
# ledger and generated-view writing
# --------------------------------------------------------------------------


def actor_identity() -> Dict[str, str]:
    """Return the recorded actor and session for ledger events.

    Both are strings this process wrote, so they are labelled as asserted. The
    existing ledger already refuses to call an unanchored identity
    authenticated, and this layer does not pretend otherwise.
    """
    session = os.environ.get("SR_WORKSPACE_SESSION_ID") or _DEFAULT_SESSION_ID
    actor = os.environ.get("SR_WORKSPACE_ACTOR_ID") or "SELF_ASSERTED_UNSPECIFIED"
    return {"actor_id": actor, "session_id": session}


def append_workspace_event(
    root: str, event_type: str, fields: Dict[str, Any]
) -> Dict[str, Any]:
    """Append one workspace event through the existing append-only ledger.

    The ledger is the event authority. Nothing here reimplements chaining or
    hashing; the event is written by ``approval_ledger.append_event``.
    """
    if event_type not in WORKSPACE_EVENT_TYPES:
        raise WorkspaceLifecycleError(f"unknown workspace event: {event_type!r}")
    event = {
        "event_type": event_type,
        "schema_version": SCHEMA_VERSION,
        "tool_version": TOOL_VERSION,
        "recorded_at": utc_timestamp(),
        "identity_assurance": approval_ledger.SELF_ASSERTED,
        **actor_identity(),
        **fields,
    }
    try:
        return approval_ledger.append_event(str(ledger_path(root)), event)
    except approval_ledger.ApprovalLedgerError as exc:
        raise WorkspaceLifecycleError(str(exc)) from exc


def read_ledger_events(root: str) -> List[Dict[str, Any]]:
    """Verify the ledger chain, then return this layer's events in order."""
    path = ledger_path(root)
    try:
        approval_ledger.verify_ledger(str(path))
    except approval_ledger.ApprovalLedgerError as exc:
        raise WorkspaceLifecycleError(f"ledger is not intact: {exc}") from exc
    if not path.is_file():
        raise WorkspaceLifecycleError(f"ledger is missing: {path}")
    entries: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        if entry.get("event", {}).get("event_type") in WORKSPACE_EVENT_TYPES:
            entries.append(entry)
    return entries


def write_generated_json(root: str, path: str, value: Dict[str, Any]) -> Path:
    """Replace a *generated* view atomically.

    This is the single workspace file that may be rewritten, because it is
    derived: every byte of it comes from the verified ledger and terminal
    manifests. Records that assert something — manifests — are never
    rewritten, which is why they use :func:`write_new_json` instead.
    """
    if not isinstance(value, dict):
        raise WorkspaceLifecycleError("workspace records must be objects")
    target = assert_within_root(root, path)
    if not target.parent.is_dir():
        raise WorkspaceLifecycleError(
            f"parent directory does not exist: {target.parent}"
        )
    descriptor, temporary = tempfile.mkstemp(
        dir=str(target.parent), prefix=".generating-", suffix=".json"
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(canonical_bytes(value))
        os.replace(temporary, str(target))
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    return target


def _require_review(root: str) -> Dict[str, Any]:
    """Confirm the root is an initialized review before anything is written."""
    manifest = review_manifest_path(root)
    if not manifest.is_file():
        raise WorkspaceLifecycleError(
            f"{root} is not an initialized review; run init-review first"
        )
    return validate_review_manifest(read_json(str(manifest)))


def _require_nonterminal(path: str) -> Dict[str, Any]:
    """Confirm a run is ledger-backed, intact, and still nonterminal."""
    context = _load_run_context(path)
    reconciliation = reconcile_run_with_ledger(path, context=context)
    if context["layout"]["terminal"]:
        raise WorkspaceLifecycleError(
            f"run {path} already carries a terminal manifest "
            f"({context['layout']['status']}); a terminal state is written "
            "exactly once and a correction is a new run"
        )
    context["reconciliation"] = reconciliation
    return context


def _root_from_run_dir(path: str) -> Path:
    """Recover the review root from a run directory, structurally."""
    _text(path, "run_dir")
    directory = Path(path)
    if not directory.is_absolute():
        raise WorkspaceLifecycleError(f"run directory must be absolute: {path}")
    parts = directory.parts
    if len(parts) < 4 or parts[-3] != RUNS_DIR_NAME:
        raise WorkspaceLifecycleError(
            f"run directory must be <root>/{RUNS_DIR_NAME}/<phase-id>/<run-id>: "
            f"{path}"
        )
    return directory.parent.parent.parent


def _root_from_handoff_dir(path: str) -> Path:
    """Recover the review root from a handoff directory, structurally.

    Which review's ledger judges a handoff is decided by where the handoff sits,
    not by a field inside it. Deriving the root from the manifest's own
    ``producer_run_manifest`` path let the record nominate the authority that
    checks it, so a handoff published in one review satisfied every check while
    a run in another review consumed it.

    Mirrors :func:`_root_from_run_dir`. A manifest outside a
    ``handoffs/<producer-run-id>/<consumer-skill>/<handoff-id>/`` tree is not a
    handoff at all.
    """
    _text(path, "handoff_dir")
    directory = Path(path)
    if not directory.is_absolute():
        raise WorkspaceLifecycleError(
            f"handoff directory must be absolute: {path}"
        )
    parts = directory.parts
    if len(parts) < 5 or parts[-4] != HANDOFFS_DIR_NAME:
        raise WorkspaceLifecycleError(
            f"handoff directory must be <root>/{HANDOFFS_DIR_NAME}/"
            f"<producer-run-id>/<consumer-skill>/<handoff-id>: {path}"
        )
    return directory.parent.parent.parent.parent


def _load_run_context(path: str) -> Dict[str, Any]:
    """Read a run's identity and confirm the directory agrees with it."""
    directory = Path(path)
    root = _root_from_run_dir(path)
    assert_within_root(str(root), str(directory))
    phase_id = directory.parent.name
    run_id = directory.name
    layout = assert_run_directory_layout(path)
    if not layout["has_inputs_manifest"]:
        raise WorkspaceLifecycleError(
            f"run {path} has no inputs manifest; it was not started through "
            "this lifecycle"
        )
    inputs = validate_inputs_manifest(
        read_json(str(directory / INPUTS_MANIFEST_NAME))
    )
    if inputs["phase_id"] != phase_id or inputs["run_id"] != run_id:
        raise WorkspaceLifecycleError(
            f"run directory {path} does not match its recorded identity "
            f"{inputs['phase_id']}/{inputs['run_id']}"
        )
    return {
        "root": str(root),
        "phase_id": phase_id,
        "run_id": run_id,
        "layout": layout,
        "inputs": inputs,
    }


# --------------------------------------------------------------------------
# locked public signatures
#
# Brief 17 materialized these as contract stubs, brief 18 implemented the run
# lifecycle and derived state, and brief 19 implemented handoffs and legacy
# registration. All eight are now real.
# --------------------------------------------------------------------------


def initialize_review(root: str, *, review_id: str) -> dict:
    """Create a review root with its ledger and manifest.

    Only the workspace skeleton is created. No phase directory is created
    here: a phase directory appears when that phase actually starts a run.
    """
    validate_identifier(review_id, "review_id")
    root_path = Path(root)
    if not root_path.is_absolute():
        raise WorkspaceLifecycleError(f"review root must be absolute: {root}")
    if root_path.is_symlink():
        raise WorkspaceLifecycleError(f"review root must not be a symlink: {root}")
    manifest_target = assert_unregistered(root, REVIEW_MANIFEST_NAME)
    root_path.mkdir(parents=True, exist_ok=True)
    for name in (LEDGER_DIR_NAME, STATE_DIR_NAME):
        assert_within_root(root, name).mkdir(exist_ok=True)

    record = {
        "schema_version": SCHEMA_VERSION,
        "record_type": RECORD_REVIEW,
        "review_id": review_id,
        "tool_version": TOOL_VERSION,
        "created_at": utc_timestamp(),
        "timestamp_assurance": TIMESTAMP_ASSURANCE,
    }
    validate_review_manifest(record)
    write_new_json(root, REVIEW_MANIFEST_NAME, record)
    entry = append_workspace_event(
        root, EVENT_REVIEW_INITIALIZED, {"review_id": review_id}
    )
    return {
        "review_id": review_id,
        "root": str(root_path),
        "review_manifest": str(manifest_target),
        "ledger": str(ledger_path(root)),
        "ledger_sequence": entry["sequence"],
    }


def start_run(root: str, *, phase_id: str, skill_id: str, run_id: str,
              inputs: list[dict], parent_run_ids: list[str] = ()) -> dict:
    """Verify and bind every input, then create this run's directory."""
    review = _require_review(root)
    validate_identifier(phase_id, "phase_id")
    validate_identifier(skill_id, "skill_id")
    validate_identifier(run_id, "run_id")
    parents = validate_unique_identifiers(list(parent_run_ids), "parent_run_ids")

    _assert_phase_id_consistent(root, review["review_id"], phase_id)
    target = run_dir(root, phase_id, run_id)
    assert_unregistered(root, str(target))
    _assert_run_id_unused(root, review["review_id"], phase_id, run_id)
    _assert_parents_resolve(root, review["review_id"], run_id, parents)
    verified = verify_artifact_refs(list(inputs), field="inputs")

    consumed_ids = set()
    current_root = str(Path(root).resolve())
    for entry in verified:
        resolved_path = entry["resolved_path"]
        containing = _containing_workspace(resolved_path)
        if containing is not None and containing["root"] != current_root:
            raise WorkspaceLifecycleError(
                f"input {entry['path']!r} belongs to review "
                f"{containing['review_id']!r}, an initialized workspace; "
                "workspace-managed evidence "
                "from another review enters only through legacy registration"
            )
        if _workspace_record_type(resolved_path) != RECORD_HANDOFF:
            continue
        checked = verify_handoff(resolved_path, consumer_skill=skill_id)
        if checked["review_id"] != review["review_id"]:
            raise WorkspaceLifecycleError(
                f"handoff {checked['handoff_id']!r} belongs to review "
                f"{checked['review_id']!r}, this review is "
                f"{review['review_id']!r}"
            )
        consumed_ids.add(checked["handoff_id"])
    consumed = sorted(consumed_ids)

    binding_source = {
        "review_id": review["review_id"],
        "phase_id": phase_id,
        "skill_id": skill_id,
        "run_id": run_id,
        "inputs": list(inputs),
        "parent_run_ids": parents,
        "consumed_handoff_ids": consumed,
    }
    binding = _inputs_binding_sha256(binding_source)
    entry = append_workspace_event(
        root,
        EVENT_RUN_STARTED,
        {
            "review_id": review["review_id"],
            "phase_id": phase_id,
            "skill_id": skill_id,
            "run_id": run_id,
            "inputs_binding_sha256": binding,
            "terminal_manifest_binding_required": True,
        },
    )
    create_new_directory(root, str(target))
    create_new_directory(root, str(target / OUTPUTS_DIR_NAME))

    record = {
        "schema_version": SCHEMA_VERSION,
        "record_type": RECORD_INPUTS,
        **binding_source,
        "start_ledger_sequence": entry["sequence"],
        "created_at": utc_timestamp(),
        "timestamp_assurance": TIMESTAMP_ASSURANCE,
    }
    validate_inputs_manifest(record)
    write_new_json(root, str(target / INPUTS_MANIFEST_NAME), record)
    return {
        "review_id": review["review_id"],
        "phase_id": phase_id,
        "skill_id": skill_id,
        "run_id": run_id,
        "run_dir": str(target),
        "outputs_dir": str(target / OUTPUTS_DIR_NAME),
        "inputs_verified": len(verified),
        "start_ledger_sequence": entry["sequence"],
        "status": STATUS_STARTED,
    }


def complete_run(run_dir: str, *, outputs: list[dict],
                 status: str = "COMPLETED",
                 downstream_consumers: list[str] = ()) -> dict:
    """Write the one immutable terminal success manifest.

    Every declared output is re-hashed and must live inside this run's own
    ``outputs/``. Recorded inputs are re-verified too: an upstream artifact
    that changed while the run was in flight means the run's evidence is no
    longer what it claimed, and completing on it would launder stale evidence
    into the chain.
    """
    if status not in TERMINAL_SUCCESS_STATUSES:
        raise WorkspaceLifecycleError(
            "a successful run is " + " or ".join(TERMINAL_SUCCESS_STATUSES)
        )
    context = _require_nonterminal(run_dir)
    root = context["root"]
    inputs = context["inputs"]
    if not context["reconciliation"]["inputs_bound_at_start"]:
        raise WorkspaceLifecycleError(
            "run predates RUN_STARTED input binding and may fail, but may not "
            "complete; retry it as a new run"
        )
    consumers = validate_unique_identifiers(
        list(downstream_consumers), "downstream_consumers"
    )

    verify_artifact_refs(inputs["inputs"], field="inputs")
    verified = verify_artifact_refs(list(outputs), field="outputs")
    if not verified:
        raise WorkspaceLifecycleError(
            "a successful run must declare at least one verified output"
        )
    assert_outputs_owned(
        root,
        phase_id=context["phase_id"],
        run_id=context["run_id"],
        outputs=verified,
    )

    completed_at = utc_timestamp()
    record = {
        "schema_version": SCHEMA_VERSION,
        "record_type": RECORD_RUN,
        "review_id": inputs["review_id"],
        "phase_id": context["phase_id"],
        "skill_id": inputs["skill_id"],
        "run_id": context["run_id"],
        "status": status,
        "inputs_manifest": artifact_ref.make_artifact_ref(
            str(Path(run_dir) / INPUTS_MANIFEST_NAME),
            "inputs-manifest",
            "1.0",
            "INTERNAL_LOCKED",
        ),
        "outputs": list(outputs),
        "parent_run_ids": inputs["parent_run_ids"],
        "consumed_handoff_ids": inputs["consumed_handoff_ids"],
        "downstream_consumers": consumers,
        "start_ledger_sequence": inputs["start_ledger_sequence"],
        "created_at": inputs["created_at"],
        "completed_at": completed_at,
        "timestamp_assurance": TIMESTAMP_ASSURANCE,
        "tool_version": TOOL_VERSION,
    }
    entry = append_workspace_event(
        root,
        EVENT_RUN_COMPLETED if status == STATUS_COMPLETED else EVENT_RUN_LOCKED,
        {
            "review_id": inputs["review_id"],
            "phase_id": context["phase_id"],
            "skill_id": inputs["skill_id"],
            "run_id": context["run_id"],
            "terminal_manifest_binding_sha256": (
                _terminal_manifest_binding_sha256(record)
            ),
        },
    )
    record["terminal_ledger_sequence"] = entry["sequence"]
    validate_run_manifest(record)
    written = write_new_json(root, str(Path(run_dir) / RUN_MANIFEST_NAME), record)
    return {
        "run_dir": str(Path(run_dir)),
        "run_manifest": str(written),
        "status": status,
        "outputs_verified": len(verified),
        "terminal_ledger_sequence": entry["sequence"],
    }


def fail_run(run_dir: str, *, reason_code: str,
             message: str) -> dict:
    """Write the one immutable terminal failure manifest.

    A failed run keeps its directory and its inputs manifest. Nothing is
    deleted, because the record of what was attempted is itself evidence.
    """
    validate_identifier(reason_code, "reason_code")
    _text(message, "message")
    context = _require_nonterminal(run_dir)
    root = context["root"]
    inputs = context["inputs"]

    failed_at = utc_timestamp()
    record = {
        "schema_version": SCHEMA_VERSION,
        "record_type": RECORD_FAILURE,
        "review_id": inputs["review_id"],
        "phase_id": context["phase_id"],
        "skill_id": inputs["skill_id"],
        "run_id": context["run_id"],
        "status": STATUS_FAILED,
        "reason_code": reason_code,
        "message": message,
        "inputs_manifest": artifact_ref.make_artifact_ref(
            str(Path(run_dir) / INPUTS_MANIFEST_NAME),
            "inputs-manifest",
            "1.0",
            "INTERNAL_LOCKED",
        ),
        "start_ledger_sequence": inputs["start_ledger_sequence"],
        "created_at": inputs["created_at"],
        "failed_at": failed_at,
        "timestamp_assurance": TIMESTAMP_ASSURANCE,
        "tool_version": TOOL_VERSION,
    }
    entry = append_workspace_event(
        root,
        EVENT_RUN_FAILED,
        {
            "review_id": inputs["review_id"],
            "phase_id": context["phase_id"],
            "skill_id": inputs["skill_id"],
            "run_id": context["run_id"],
            "reason_code": reason_code,
            "terminal_manifest_binding_sha256": (
                _terminal_manifest_binding_sha256(record)
            ),
        },
    )
    record["terminal_ledger_sequence"] = entry["sequence"]
    validate_failure_manifest(record)
    written = write_new_json(
        root, str(Path(run_dir) / FAILURE_MANIFEST_NAME), record
    )
    return {
        "run_dir": str(Path(run_dir)),
        "failure_manifest": str(written),
        "status": STATUS_FAILED,
        "reason_code": reason_code,
        "terminal_ledger_sequence": entry["sequence"],
    }


def inspect_run(run_dir: str, *, verify: bool = True) -> Dict[str, Any]:
    """Report one run's real state without writing anything.

    ``verify`` re-hashes the run's declared artifacts. It defaults to on so a
    routine inspection cannot quietly report a run whose outputs have since
    changed; turn it off to diagnose a run that is already known to be broken.
    """
    context = _load_run_context(run_dir)
    reconciliation = None
    if verify:
        # A status read without the ledger is a status the directory asserted
        # about itself.
        reconciliation = reconcile_run_with_ledger(run_dir, context=context)
    inputs = context["inputs"]
    report = {
        "run_dir": str(Path(run_dir)),
        "review_id": inputs["review_id"],
        "phase_id": context["phase_id"],
        "skill_id": inputs["skill_id"],
        "run_id": context["run_id"],
        "status": context["layout"]["status"],
        "terminal": context["layout"]["terminal"],
        "input_roles": sorted(ref["role"] for ref in inputs["inputs"]),
        "output_roles": [],
        "verified": False,
        "terminal_manifest_bound": (
            reconciliation["terminal_manifest_bound"] if reconciliation else False
        ),
    }
    if context["layout"]["terminal"] and context["layout"]["status"] != STATUS_FAILED:
        manifest = validate_run_manifest(
            read_json(str(Path(run_dir) / RUN_MANIFEST_NAME))
        )
        report["output_roles"] = sorted(ref["role"] for ref in manifest["outputs"])
        report["downstream_consumers"] = manifest["downstream_consumers"]
    if verify:
        verify_artifact_refs(inputs["inputs"], field="inputs")
        report["verified"] = True
    return report


def _assert_phase_id_consistent(
    root: str, review_id: str, phase_id: str
) -> None:
    """Refuse a phase spelling that case-folds to an existing namespace."""
    folded = phase_id.lower()
    _scan_run_directories(root)  # validates the entire directory namespace
    runs_root = assert_within_root(root, RUNS_DIR_NAME)
    existing = {
        phase.name
        for phase in runs_root.iterdir()
        if phase.name.lower() == folded
    } if runs_root.is_dir() else set()
    existing.update(
        phase
        for phase, _run in _ledger_run_index(root, review_id)
        if phase.lower() == folded
    )
    conflicts = sorted(name for name in existing if name != phase_id)
    if conflicts:
        raise WorkspaceLifecycleError(
            f"phase id {phase_id!r} case-collides with existing phase "
            + ", ".join(repr(name) for name in conflicts)
        )


def _assert_run_id_unused(
    root: str, review_id: str, phase_id: str, run_id: str
) -> None:
    """Run identifiers are unique across every phase of a review.

    ``create_handoff`` resolves a producer by run ID alone, so a duplicate makes
    that producer permanently unresolvable. Refusing it at publication time is
    too late — the work is already done by then.

    Every operation that creates a run directory calls this. Enforcing it on one
    of two creators enforces nothing: a duplicate registered through the other
    makes the producer equally unresolvable.

    Comparison folds case, like every other identifier this layer refuses
    duplicates of. Two run IDs differing only in case are one identifier on a
    case-insensitive filesystem and two confusable provenance records on any
    filesystem.
    """
    folded = run_id.lower()
    for existing_phase, existing_run in _scan_run_directories(root):
        if existing_run.lower() == folded:
            raise WorkspaceLifecycleError(
                f"run id {run_id!r} already exists in {existing_phase} as "
                f"{existing_run!r}; run identifiers are unique across every "
                "phase of a review"
            )
    for existing_phase, existing_run in _ledger_run_index(root, review_id):
        if existing_run.lower() == folded:
            raise WorkspaceLifecycleError(
                f"run id {run_id!r} is already recorded in the ledger under "
                f"{existing_phase} as {existing_run!r}"
            )


def _assert_parents_resolve(
    root: str, review_id: str, run_id: str, parents: Sequence[str]
) -> None:
    """A parent must name a real terminal run in this review.

    Unresolved parents let a correction claim lineage that never existed, which
    is the opposite of what the parent link is for.
    """
    if not parents:
        return
    ledger_runs = _ledger_run_index(root, review_id)
    directories = _scan_run_directories(root)
    by_run = {run: phase for phase, run in directories}
    for parent in parents:
        if parent == run_id:
            raise WorkspaceLifecycleError(
                f"run {run_id!r} cannot be its own parent"
            )
        phase = by_run.get(parent)
        if phase is None:
            raise WorkspaceLifecycleError(
                f"parent run {parent!r} does not exist in this review; a run "
                "may not claim lineage that never happened"
            )
        recorded = ledger_runs.get((phase, parent))
        if recorded is None or recorded["terminal_status"] is None:
            raise WorkspaceLifecycleError(
                f"parent run {parent!r} is not terminal; a run may descend from "
                "a completed, locked, or failed run, not from one still in "
                "flight"
            )
        reconciliation = reconcile_run_with_ledger(
            directories[(phase, parent)], ledger_runs=ledger_runs
        )
        if not reconciliation["terminal"]:
            raise WorkspaceLifecycleError(
                f"parent run {parent!r} is not terminal"
            )


def _locate_producer_run(root: str, producer_run_id: str) -> Dict[str, Any]:
    """Find a producer run by run ID alone, refusing ambiguity.

    The locked signature identifies a producer by run ID without a phase, so a
    run ID reused across two phases is genuinely ambiguous here. Guessing would
    be worse than refusing.
    """
    validate_identifier(producer_run_id, "producer_run_id")
    matches = [
        (phase_id, path)
        for (phase_id, run_id), path in _scan_run_directories(root).items()
        if run_id == producer_run_id
    ]
    if not matches:
        raise WorkspaceLifecycleError(
            f"no run named {producer_run_id!r} exists in {root}"
        )
    if len(matches) > 1:
        phases = ", ".join(sorted(phase for phase, _ in matches))
        raise WorkspaceLifecycleError(
            f"run id {producer_run_id!r} is ambiguous; it exists in {phases}"
        )
    phase_id, path = matches[0]
    return {"phase_id": phase_id, "run_dir": path}


def _assert_handoff_id_unused(
    root: str, review_id: str, handoff_id: str
) -> None:
    """Refuse a handoff ID already used anywhere in this review."""
    folded = handoff_id.lower()
    if folded in _ledger_handoff_index(root, review_id):
        raise WorkspaceLifecycleError(
            f"handoff id {handoff_id!r} is already used and recorded in the ledger"
        )
    handoffs_root = assert_within_root(root, HANDOFFS_DIR_NAME)
    if not handoffs_root.is_dir():
        return
    for producer in sorted(handoffs_root.iterdir()):
        if producer.is_symlink() or not producer.is_dir():
            raise WorkspaceLifecycleError(f"{producer} is not a handoff directory")
        for consumer in sorted(producer.iterdir()):
            if consumer.is_symlink() or not consumer.is_dir():
                raise WorkspaceLifecycleError(
                    f"{consumer} is not a handoff directory"
                )
            for existing in sorted(consumer.iterdir()):
                if existing.name.lower() == folded:
                    raise WorkspaceLifecycleError(
                        f"handoff id {handoff_id!r} is already used at {existing}"
                    )


def create_handoff(root: str, *, producer_run_id: str,
                   consumer_skill: str, handoff_id: str,
                   artifacts: list[dict]) -> dict:
    """Publish a consumer-specific handoff outside the producer run.

    A producer may prepare a handoff for a distant consumer — a Phase 1 output
    that Phase 10 will need — but it creates nothing for that consumer beyond
    the handoff itself. No consumer run, no consumer output directory, and no
    field in which a consumer's status could be recorded.

    The offered artifacts must be ones this producer actually locked, so a
    handoff can never introduce evidence the producer never declared.
    """
    review = _require_review(root)
    validate_identifier(consumer_skill, "consumer_skill")
    validate_identifier(handoff_id, "handoff_id")
    located = _locate_producer_run(root, producer_run_id)
    producer_dir = located["run_dir"]
    producer = assert_successful_producer(producer_dir)
    if producer["review_id"] != review["review_id"]:
        raise WorkspaceLifecycleError(
            f"producer run belongs to review {producer['review_id']!r}, not "
            f"{review['review_id']!r}"
        )

    offered = validate_artifact_refs(list(artifacts), "artifacts")
    declared = {
        (ref["role"], ref["path"], ref["sha256"]) for ref in producer["outputs"]
    }
    for index, ref in enumerate(offered):
        if (ref["role"], ref["path"], ref["sha256"]) not in declared:
            raise WorkspaceLifecycleError(
                f"artifacts[{index}] with role {ref['role']!r} is not an output "
                f"locked by run {producer_run_id}"
            )
    verify_artifact_refs(offered, field="artifacts")

    _assert_handoff_id_unused(root, review["review_id"], handoff_id)
    target = handoff_dir(root, producer_run_id, consumer_skill, handoff_id)
    assert_unregistered(root, str(target))

    frozen = next(
        (ref for ref in offered if ref["role"] == FROZEN_EXPORT_ROLE), None
    )
    entry = append_workspace_event(
        root,
        EVENT_HANDOFF_CREATED,
        {
            "review_id": review["review_id"],
            "handoff_id": handoff_id,
            "producer_phase_id": located["phase_id"],
            "producer_run_id": producer_run_id,
            "consumer_skill": consumer_skill,
        },
    )
    create_new_directory(root, str(target))
    record = {
        "schema_version": SCHEMA_VERSION,
        "record_type": RECORD_HANDOFF,
        "review_id": review["review_id"],
        "handoff_id": handoff_id,
        "producer_phase_id": located["phase_id"],
        "producer_skill_id": producer["skill_id"],
        "producer_run_id": producer_run_id,
        "producer_run_manifest": artifact_ref.make_artifact_ref(
            str(Path(producer_dir) / RUN_MANIFEST_NAME),
            "producer-run-manifest",
            "1.0",
            "INTERNAL_LOCKED",
        ),
        "consumer_skill": consumer_skill,
        "artifacts": list(offered),
        "frozen_export": frozen,
        "created_ledger_sequence": entry["sequence"],
        "created_at": utc_timestamp(),
        "timestamp_assurance": TIMESTAMP_ASSURANCE,
        "tool_version": TOOL_VERSION,
    }
    validate_handoff_manifest(record)
    written = write_new_json(
        root, str(target / HANDOFF_MANIFEST_NAME), record
    )
    return {
        "handoff_id": handoff_id,
        "handoff_dir": str(target),
        "handoff_manifest": str(written),
        "producer_phase_id": located["phase_id"],
        "producer_run_id": producer_run_id,
        "consumer_skill": consumer_skill,
        "artifact_roles": sorted(ref["role"] for ref in offered),
        "frozen_export": bool(frozen),
        "created_ledger_sequence": entry["sequence"],
    }


def verify_handoff(path: str, *, consumer_skill: str) -> dict:
    """Verify a handoff for exactly one named consumer.

    Read-only. Confirms the manifest matches where it actually sits, that the
    producer is still terminal and successful, and that every referenced
    artifact still hashes to what the producer committed to. A consumer that
    reads a handoff without this is trusting a filename.
    """
    _text(path, "path")
    candidate = Path(path)
    if not candidate.is_absolute():
        raise WorkspaceLifecycleError(f"handoff path must be absolute: {path}")
    manifest_path = (
        candidate / HANDOFF_MANIFEST_NAME if candidate.is_dir() else candidate
    )
    placed = manifest_path.parent
    # Derive authority from placement and reject below-root symlinks before
    # reading the manifest they point at.
    root = str(_root_from_handoff_dir(str(placed)))
    assert_within_root(root, str(manifest_path))
    record = validate_handoff_manifest(read_json(str(manifest_path)))
    assert_consumer_match(record, consumer_skill)

    expected = (
        (record["handoff_id"], placed.name),
        (record["consumer_skill"], placed.parent.name),
        (record["producer_run_id"], placed.parent.parent.name),
    )
    for recorded, actual in expected:
        if recorded != actual:
            raise WorkspaceLifecycleError(
                f"handoff manifest records {recorded!r} but sits at {actual!r}; "
                "it was moved or renamed"
            )

    # A record never nominates the review authority that checks it.
    reconcile_handoff_with_ledger(root, record)

    producer_dir = str(Path(record["producer_run_manifest"]["path"]).parent)
    try:
        assert_within_root(root, producer_dir)
    except WorkspaceLifecycleError as exc:
        raise WorkspaceLifecycleError(
            f"handoff at {placed} names a producer outside its own review "
            "or through an invalid path: "
            f"{producer_dir}: {exc}"
        ) from None
    verify_artifact_refs(
        [record["producer_run_manifest"]], field="producer_run_manifest"
    )
    producer = assert_successful_producer(producer_dir)
    if producer["run_id"] != record["producer_run_id"]:
        raise WorkspaceLifecycleError(
            f"handoff names producer {record['producer_run_id']!r} but its "
            f"manifest belongs to {producer['run_id']!r}"
        )
    verified = verify_artifact_refs(record["artifacts"], field="artifacts")
    return {
        "handoff_id": record["handoff_id"],
        "handoff_manifest": str(manifest_path),
        "review_id": record["review_id"],
        "consumer_skill": record["consumer_skill"],
        "producer_phase_id": record["producer_phase_id"],
        "producer_skill_id": record["producer_skill_id"],
        "producer_run_id": record["producer_run_id"],
        "producer_status": producer["status"],
        "artifact_roles": sorted(ref["role"] for ref in verified),
        "frozen_export_role": (
            record["frozen_export"]["role"] if record["frozen_export"] else None
        ),
        "verified": True,
    }


def register_legacy_run(root: str, *, phase_id: str, skill_id: str,
                        run_id: str, artifacts: list[dict],
                        legacy_status: str) -> dict:
    """Register existing locked artifacts by reference only.

    The sources are never moved, copied, or rewritten — they stay exactly where
    the phase that produced them left them, and this creates only a wrapper run
    that points at them. That is why the wrapper has no ``outputs/``: it owns no
    bytes.

    Registration is optional. A legacy artifact needs it only when it must enter
    the workspace-managed chain as a verifiable producer.
    """
    review = _require_review(root)
    validate_identifier(phase_id, "phase_id")
    validate_identifier(skill_id, "skill_id")
    validate_identifier(run_id, "run_id")
    if legacy_status not in TERMINAL_SUCCESS_STATUSES:
        raise WorkspaceLifecycleError(
            "legacy_status must be one of " + ", ".join(TERMINAL_SUCCESS_STATUSES)
        )

    _assert_phase_id_consistent(root, review["review_id"], phase_id)
    target = run_dir(root, phase_id, run_id)
    assert_unregistered(root, str(target))
    # A legacy registration creates a run directory, so the same identifier rule
    # binds it. Without this, F10's harm returns through the other door: both
    # runs sharing the ID become permanently unresolvable to create_handoff.
    _assert_run_id_unused(root, review["review_id"], phase_id, run_id)
    refs = validate_artifact_refs(list(artifacts), "artifacts")
    verified = verify_artifact_refs(refs, field="artifacts")
    for index, ref in enumerate(verified):
        resolved = Path(ref["resolved_path"])
        try:
            resolved.relative_to(target)
        except ValueError:
            continue
        raise WorkspaceLifecycleError(
            f"artifacts[{index}] is inside the wrapper run at {resolved}; a "
            "legacy artifact is registered where it already lives"
        )

    inputs_record = {
        "schema_version": SCHEMA_VERSION,
        "record_type": RECORD_INPUTS,
        "review_id": review["review_id"],
        "phase_id": phase_id,
        "skill_id": skill_id,
        "run_id": run_id,
        "inputs": [],
        "parent_run_ids": [],
        "consumed_handoff_ids": [],
        "start_ledger_sequence": 1,
        "created_at": utc_timestamp(),
        "timestamp_assurance": TIMESTAMP_ASSURANCE,
    }
    validate_inputs_manifest(inputs_record)
    legacy_binding_source = {
        "review_id": review["review_id"],
        "phase_id": phase_id,
        "skill_id": skill_id,
        "run_id": run_id,
        "inputs": [],
        "parent_run_ids": [],
        "consumed_handoff_ids": [],
    }
    started = append_workspace_event(
        root,
        EVENT_LEGACY_RUN_REGISTERED,
        {
            "review_id": review["review_id"],
            "phase_id": phase_id,
            "skill_id": skill_id,
            "run_id": run_id,
            "legacy_status": legacy_status,
            "inputs_binding_sha256": _inputs_binding_sha256(
                legacy_binding_source
            ),
            "terminal_manifest_binding_required": True,
        },
    )
    inputs_record["start_ledger_sequence"] = started["sequence"]
    inputs_ref = _canonical_json_artifact_ref(
        str(target / INPUTS_MANIFEST_NAME),
        "inputs-manifest",
        "1.0",
        "INTERNAL_LOCKED",
        inputs_record,
    )

    run_record = {
        "schema_version": SCHEMA_VERSION,
        "record_type": RECORD_RUN,
        "review_id": review["review_id"],
        "phase_id": phase_id,
        "skill_id": skill_id,
        "run_id": run_id,
        "status": legacy_status,
        "inputs_manifest": inputs_ref,
        "outputs": list(refs),
        "parent_run_ids": [],
        "consumed_handoff_ids": [],
        "downstream_consumers": [],
        "start_ledger_sequence": started["sequence"],
        "created_at": inputs_record["created_at"],
        "completed_at": utc_timestamp(),
        "timestamp_assurance": TIMESTAMP_ASSURANCE,
        "tool_version": TOOL_VERSION,
    }
    terminal = append_workspace_event(
        root,
        EVENT_RUN_LOCKED if legacy_status == STATUS_LOCKED else EVENT_RUN_COMPLETED,
        {
            "review_id": review["review_id"],
            "phase_id": phase_id,
            "skill_id": skill_id,
            "run_id": run_id,
            "terminal_manifest_binding_sha256": (
                _terminal_manifest_binding_sha256(run_record)
            ),
        },
    )
    run_record["terminal_ledger_sequence"] = terminal["sequence"]
    create_new_directory(root, str(target))
    validate_inputs_manifest(inputs_record)
    write_new_json(root, str(target / INPUTS_MANIFEST_NAME), inputs_record)
    validate_run_manifest(run_record)
    written = write_new_json(root, str(target / RUN_MANIFEST_NAME), run_record)
    return {
        "review_id": review["review_id"],
        "phase_id": phase_id,
        "skill_id": skill_id,
        "run_id": run_id,
        "run_dir": str(target),
        "run_manifest": str(written),
        "status": legacy_status,
        "registered_artifacts": len(refs),
        "artifact_roles": sorted(ref["role"] for ref in refs),
        "disclosure": LEGACY_IMPORT_DISCLOSURE,
        "start_ledger_sequence": started["sequence"],
        "terminal_ledger_sequence": terminal["sequence"],
    }


def _ledger_run_index(root: str, review_id: str) -> Dict[tuple, Dict[str, Any]]:
    """Fold the verified ledger into one unambiguous record per run."""
    index: Dict[tuple, Dict[str, Any]] = {}
    phase_spellings: Dict[str, str] = {}
    run_spellings: Dict[str, tuple] = {}
    for entry in read_ledger_events(root):
        event = entry["event"]
        kind = event["event_type"]
        if event.get("review_id") != review_id:
            raise WorkspaceLifecycleError(
                f"ledger sequence {entry['sequence']} belongs to review "
                f"{event.get('review_id')!r}, not {review_id!r}"
            )
        if kind in (EVENT_REVIEW_INITIALIZED, EVENT_HANDOFF_CREATED):
            continue
        phase_id = event["phase_id"]
        run_id = event["run_id"]
        phase_folded = phase_id.lower()
        prior_phase = phase_spellings.setdefault(phase_folded, phase_id)
        if prior_phase != phase_id:
            raise WorkspaceLifecycleError(
                f"ledger phase ids {prior_phase!r} and {phase_id!r} "
                "differ only in case"
            )
        key = (phase_id, run_id)
        if kind in (EVENT_RUN_STARTED, EVENT_LEGACY_RUN_REGISTERED):
            prior_run = run_spellings.setdefault(run_id.lower(), key)
            if prior_run != key:
                raise WorkspaceLifecycleError(
                    f"ledger run ids {prior_run[1]!r} and {run_id!r} are "
                    "duplicates under case-folding"
                )
            if key in index:
                raise WorkspaceLifecycleError(
                    f"run {key[0]}/{key[1]} was started more than once in the "
                    "ledger"
                )
            binding = event.get("inputs_binding_sha256")
            if binding is not None:
                binding = _text(binding, "inputs_binding_sha256")
                if not artifact_ref.HASH_PATTERN.fullmatch(binding):
                    raise WorkspaceLifecycleError(
                        "inputs_binding_sha256 must be a lowercase SHA-256 digest"
                    )
            required = event.get("terminal_manifest_binding_required")
            if required is not None and not isinstance(required, bool):
                raise WorkspaceLifecycleError(
                    "terminal_manifest_binding_required must be boolean"
                )
            index[key] = {
                "skill_id": event["skill_id"],
                "start_sequence": entry["sequence"],
                "terminal_status": None,
                "terminal_sequence": None,
                "legacy": kind == EVENT_LEGACY_RUN_REGISTERED,
                "legacy_status": event.get("legacy_status"),
                "inputs_binding_sha256": binding,
                "terminal_manifest_binding_required": required is True,
                "terminal_manifest_binding_sha256": None,
            }
            continue
        record = index.get(key)
        if record is None:
            raise WorkspaceLifecycleError(
                f"ledger sequence {entry['sequence']} terminates run "
                f"{key[0]}/{key[1]}, which was never started"
            )
        if record["terminal_status"] is not None:
            raise WorkspaceLifecycleError(
                f"run {key[0]}/{key[1]} has more than one terminal ledger event"
            )
        if event.get("skill_id") != record["skill_id"]:
            raise WorkspaceLifecycleError(
                f"ledger sequence {entry['sequence']} terminates run "
                f"{key[0]}/{key[1]} as skill {event.get('skill_id')!r}, but it "
                f"started as {record['skill_id']!r}"
            )
        terminal_status = TERMINAL_EVENT_STATUS[kind]
        if record["legacy"] and terminal_status != record["legacy_status"]:
            raise WorkspaceLifecycleError(
                f"legacy run {key[0]}/{key[1]} was registered as "
                f"{record['legacy_status']!r} but the ledger terminates it as "
                f"{terminal_status!r}"
            )
        terminal_binding = event.get("terminal_manifest_binding_sha256")
        if terminal_binding is not None:
            terminal_binding = _text(
                terminal_binding, "terminal_manifest_binding_sha256"
            )
            if not artifact_ref.HASH_PATTERN.fullmatch(terminal_binding):
                raise WorkspaceLifecycleError(
                    "terminal_manifest_binding_sha256 must be a lowercase "
                    "SHA-256 digest"
                )
        if record["terminal_manifest_binding_required"] and terminal_binding is None:
            raise WorkspaceLifecycleError(
                f"ledger sequence {entry['sequence']} terminates marked run "
                f"{key[0]}/{key[1]} without a terminal manifest binding"
            )
        record["terminal_status"] = terminal_status
        record["terminal_sequence"] = entry["sequence"]
        record["terminal_manifest_binding_sha256"] = terminal_binding
    return index


def _ledger_handoff_index(root: str, review_id: str) -> Dict[str, Dict[str, Any]]:
    """Fold the verified ledger into one record per published handoff.

    A handoff manifest is a file a producer wrote. Without this, copying one to
    a new identifier produces something that verifies, because every other
    check — schema, placement, hashes, consumer, producer terminality — is
    satisfied by the copy.
    """
    index: Dict[str, Dict[str, Any]] = {}
    for entry in read_ledger_events(root):
        event = entry["event"]
        if event["event_type"] != EVENT_HANDOFF_CREATED:
            continue
        if event.get("review_id") != review_id:
            raise WorkspaceLifecycleError(
                f"ledger sequence {entry['sequence']} belongs to review "
                f"{event.get('review_id')!r}, not {review_id!r}"
            )
        handoff_id = event["handoff_id"]
        folded = handoff_id.lower()
        if folded in index:
            existing = index[folded]["handoff_id"]
            if existing == handoff_id:
                raise WorkspaceLifecycleError(
                    f"handoff {handoff_id!r} was created more than once in "
                    "the ledger"
                )
            raise WorkspaceLifecycleError(
                f"handoff {handoff_id!r} duplicates ledger handoff "
                f"{existing!r} under case-folding"
            )
        index[folded] = {
            "handoff_id": handoff_id,
            "producer_phase_id": event["producer_phase_id"],
            "producer_run_id": event["producer_run_id"],
            "consumer_skill": event["consumer_skill"],
            "created_sequence": entry["sequence"],
        }
    return index


def reconcile_handoff_with_ledger(
    root: str, manifest: Dict[str, Any]
) -> Dict[str, Any]:
    """Confirm the ledger records this exact handoff's creation.

    The one implementation of handoff binding, mirroring
    :func:`reconcile_run_with_ledger` for runs.
    """
    review_id = _require_review(root)["review_id"]
    if manifest["review_id"] != review_id:
        raise WorkspaceLifecycleError(
            f"handoff records review {manifest['review_id']!r}, this review is "
            f"{review_id!r}"
        )
    recorded = _ledger_handoff_index(root, review_id).get(
        manifest["handoff_id"].lower()
    )
    if recorded is None:
        raise WorkspaceLifecycleError(
            f"handoff {manifest['handoff_id']!r} has no ledger entry; a manifest "
            "this layer never published is not a handoff"
        )
    for field, key in (
        ("handoff_id", "handoff_id"),
        ("producer_phase_id", "producer_phase_id"),
        ("producer_run_id", "producer_run_id"),
        ("consumer_skill", "consumer_skill"),
    ):
        if manifest[field] != recorded[key]:
            raise WorkspaceLifecycleError(
                f"handoff {manifest['handoff_id']!r} records {field} "
                f"{manifest[field]!r}, the ledger says {recorded[key]!r}"
            )
    if manifest["created_ledger_sequence"] != recorded["created_sequence"]:
        raise WorkspaceLifecycleError(
            f"handoff {manifest['handoff_id']!r} records created_ledger_sequence "
            f"{manifest['created_ledger_sequence']!r}, the ledger says "
            f"{recorded['created_sequence']!r}"
        )
    return recorded


def _scan_run_directories(root: str) -> Dict[tuple, str]:
    """List the run directories that actually exist on disk."""
    runs_root = assert_within_root(root, RUNS_DIR_NAME)
    found: Dict[tuple, str] = {}
    phase_spellings: Dict[str, str] = {}
    run_spellings: Dict[str, tuple] = {}
    if not runs_root.is_dir():
        return found
    for phase in sorted(runs_root.iterdir()):
        if phase.is_symlink() or not phase.is_dir():
            raise WorkspaceLifecycleError(
                f"{phase} is not a phase directory this layer created"
            )
        validate_identifier(phase.name, "phase_id")
        prior_phase = phase_spellings.setdefault(phase.name.lower(), phase.name)
        if prior_phase != phase.name:
            raise WorkspaceLifecycleError(
                f"phase directories {prior_phase!r} and {phase.name!r} "
                "differ only in case"
            )
        for run in sorted(phase.iterdir()):
            if run.is_symlink() or not run.is_dir():
                raise WorkspaceLifecycleError(
                    f"{run} is not a run directory this layer created"
                )
            validate_identifier(run.name, "run_id")
            key = (phase.name, run.name)
            prior_run = run_spellings.setdefault(run.name.lower(), key)
            if prior_run != key:
                raise WorkspaceLifecycleError(
                    f"ambiguous run directories {prior_run[0]}/{prior_run[1]} and "
                    f"{phase.name}/{run.name} duplicate one run id under "
                    "case-folding"
                )
            found[key] = str(run)
    return found


def generate_review_state(root: str) -> dict:
    """Derive the current view from the ledger and terminal manifests.

    Nothing here trusts a directory. Every run must be reconciled three ways —
    ledger event, directory, terminal manifest — and any disagreement is
    refused rather than resolved, because a state file that quietly picks a
    winner is how stale evidence gets used.
    """
    review = _require_review(root)
    review_id = review["review_id"]
    ledger_runs = _ledger_run_index(root, review_id)
    directories = _scan_run_directories(root)

    orphan_events = sorted(set(ledger_runs) - set(directories))
    if orphan_events:
        raise WorkspaceLifecycleError(
            "the ledger records runs with no directory: "
            + ", ".join(f"{phase}/{run}" for phase, run in orphan_events)
        )
    orphan_dirs = sorted(set(directories) - set(ledger_runs))
    if orphan_dirs:
        raise WorkspaceLifecycleError(
            "these run directories have no ledger entry: "
            + ", ".join(f"{phase}/{run}" for phase, run in orphan_dirs)
        )

    phases: Dict[str, Dict[str, Any]] = {}
    for key in sorted(directories):
        phase_id, run_id = key
        recorded = ledger_runs[key]
        path = directories[key]
        context = _load_run_context(path)
        # One reconciliation implementation, shared with every command that
        # reads a run's status.
        reconcile_run_with_ledger(path, context=context, ledger_runs=ledger_runs)
        observed = context["layout"]["status"]

        inputs_available = True
        try:
            verify_artifact_refs(context["inputs"]["inputs"], field="inputs")
        except WorkspaceLifecycleError:
            inputs_available = False
        phase = phases.setdefault(
            phase_id,
            {"status": observed, "required_inputs_available": True, "runs": []},
        )
        phase["runs"].append(run_id)
        phase["required_inputs_available"] = (
            phase["required_inputs_available"] and inputs_available
        )
        phase["status"] = min(
            (phase["status"], observed), key=PHASE_STATUS_PRECEDENCE.index
        )

    verification = approval_ledger.verify_ledger(str(ledger_path(root)))
    record = {
        "schema_version": SCHEMA_VERSION,
        "record_type": RECORD_STATE,
        "review_id": review_id,
        "generated_at": utc_timestamp(),
        "generated_from_ledger_head": verification["head_sha256"],
        "generated_from_ledger_entries": verification["entries"],
        "phases": phases,
        "timestamp_assurance": TIMESTAMP_ASSURANCE,
        "tool_version": TOOL_VERSION,
        "derivation": STATE_DERIVATION,
    }
    validate_review_state(record)
    write_generated_json(root, f"{STATE_DIR_NAME}/{REVIEW_STATE_NAME}", record)
    return record


# --------------------------------------------------------------------------
# command line
# --------------------------------------------------------------------------


def _refs_from_pairs(pairs: Sequence[str], *, flag: str) -> List[Dict[str, Any]]:
    """Build ArtifactRefs from ``ROLE=PATH`` arguments by hashing now."""
    refs: List[Dict[str, Any]] = []
    for pair in pairs:
        role, separator, path = pair.partition("=")
        if not separator or not role or not path:
            raise WorkspaceLifecycleError(f"{flag} expects ROLE=PATH: {pair!r}")
        validate_identifier(role, f"{flag} role")
        try:
            refs.append(
                artifact_ref.make_artifact_ref(
                    str(Path(path).absolute()), role, "1.0", "REFERENCED"
                )
            )
        except artifact_ref.ArtifactRefError as exc:
            raise WorkspaceLifecycleError(str(exc)) from exc
    return refs


def _collect_refs(
    pairs: Sequence[str], manifest: Optional[str], *, flag: str
) -> List[Dict[str, Any]]:
    refs = _refs_from_pairs(pairs or (), flag=flag)
    if manifest:
        loaded = read_json(manifest)
        if not isinstance(loaded, list):
            raise WorkspaceLifecycleError(
                f"{manifest} must contain a JSON array of ArtifactRefs"
            )
        refs.extend(loaded)
    return refs


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="workspace-lifecycle",
        description="Producer-owned run lifecycle for systematic-review skills.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    command = commands.add_parser("init-review")
    command.add_argument("--root", required=True)
    command.add_argument("--review-id", required=True)

    command = commands.add_parser("start-run")
    command.add_argument("--root", required=True)
    command.add_argument("--phase-id", required=True)
    command.add_argument("--skill-id", required=True)
    command.add_argument("--run-id", required=True)
    command.add_argument("--input", action="append", metavar="ROLE=PATH")
    command.add_argument("--inputs-file", help="JSON array of ArtifactRefs")
    command.add_argument("--parent-run-id", action="append")

    command = commands.add_parser("complete-run")
    command.add_argument("--run-dir", required=True)
    command.add_argument("--output", action="append", metavar="ROLE=PATH")
    command.add_argument("--outputs-file", help="JSON array of ArtifactRefs")
    command.add_argument(
        "--status", choices=list(TERMINAL_SUCCESS_STATUSES), default=STATUS_COMPLETED
    )
    command.add_argument("--consumer", action="append", metavar="SKILL_ID")

    command = commands.add_parser("fail-run")
    command.add_argument("--run-dir", required=True)
    command.add_argument("--reason-code", required=True)
    command.add_argument("--message", required=True)

    command = commands.add_parser("inspect-run")
    command.add_argument("--run-dir", required=True)
    command.add_argument("--no-verify", action="store_true")

    command = commands.add_parser("generate-state")
    command.add_argument("--root", required=True)

    command = commands.add_parser("create-handoff")
    command.add_argument("--root", required=True)
    command.add_argument("--producer-run-id", required=True)
    command.add_argument("--consumer-skill", required=True)
    command.add_argument("--handoff-id", required=True)
    command.add_argument("--artifact", action="append", metavar="ROLE=PATH")
    command.add_argument("--artifacts-file", help="JSON array of ArtifactRefs")

    command = commands.add_parser("verify-handoff")
    command.add_argument("--path", required=True)
    command.add_argument("--consumer-skill", required=True)

    command = commands.add_parser("register-legacy-run")
    command.add_argument("--root", required=True)
    command.add_argument("--phase-id", required=True)
    command.add_argument("--skill-id", required=True)
    command.add_argument("--run-id", required=True)
    command.add_argument("--artifact", action="append", metavar="ROLE=PATH")
    command.add_argument("--artifacts-file", help="JSON array of ArtifactRefs")
    command.add_argument(
        "--legacy-status", choices=list(TERMINAL_SUCCESS_STATUSES), required=True
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "init-review":
            result = initialize_review(
                str(Path(args.root).absolute()), review_id=args.review_id
            )
        elif args.command == "start-run":
            result = start_run(
                str(Path(args.root).absolute()),
                phase_id=args.phase_id,
                skill_id=args.skill_id,
                run_id=args.run_id,
                inputs=_collect_refs(
                    args.input, args.inputs_file, flag="--input"
                ),
                parent_run_ids=args.parent_run_id or [],
            )
        elif args.command == "complete-run":
            result = complete_run(
                str(Path(args.run_dir).absolute()),
                outputs=_collect_refs(
                    args.output, args.outputs_file, flag="--output"
                ),
                status=args.status,
                downstream_consumers=args.consumer or [],
            )
        elif args.command == "fail-run":
            result = fail_run(
                str(Path(args.run_dir).absolute()),
                reason_code=args.reason_code,
                message=args.message,
            )
        elif args.command == "inspect-run":
            result = inspect_run(
                str(Path(args.run_dir).absolute()), verify=not args.no_verify
            )
        elif args.command == "create-handoff":
            result = create_handoff(
                str(Path(args.root).absolute()),
                producer_run_id=args.producer_run_id,
                consumer_skill=args.consumer_skill,
                handoff_id=args.handoff_id,
                artifacts=_collect_refs(
                    args.artifact, args.artifacts_file, flag="--artifact"
                ),
            )
        elif args.command == "verify-handoff":
            result = verify_handoff(
                str(Path(args.path).absolute()),
                consumer_skill=args.consumer_skill,
            )
        elif args.command == "register-legacy-run":
            result = register_legacy_run(
                str(Path(args.root).absolute()),
                phase_id=args.phase_id,
                skill_id=args.skill_id,
                run_id=args.run_id,
                artifacts=_collect_refs(
                    args.artifact, args.artifacts_file, flag="--artifact"
                ),
                legacy_status=args.legacy_status,
            )
        else:
            result = generate_review_state(str(Path(args.root).absolute()))
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    except (
        WorkspaceLifecycleError,
        artifact_ref.ArtifactRefError,
        approval_ledger.ApprovalLedgerError,
        OSError,
        json.JSONDecodeError,
    ) as exc:
        print(f"workspace-lifecycle error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
