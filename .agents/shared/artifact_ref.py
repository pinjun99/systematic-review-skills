"""ArtifactRef v2 — real-file verification for cross-phase handoffs.

Every reference commits to the bytes of a real regular file. Verification
recomputes the digest instead of trusting the recorded value, rejects symlinks,
and refuses any path that escapes its declared root.

Canonical-JSON digests are available separately and are only ever computed over
values, never presented as file hashes.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


SCHEMA_VERSION = "2.0"
HASH_PATTERN = re.compile(r"[0-9a-f]{64}")
_READ_CHUNK = 1024 * 1024

REQUIRED_REF_FIELDS = ("path", "role", "version", "status", "sha256", "bytes")


class ArtifactRefError(ValueError):
    """Raised when a reference cannot be built or verified.

    Subclasses ``ValueError`` so existing skill entry points already map it to a
    nonzero exit code with a concise stderr message.
    """


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ArtifactRefError(f"{field} must be a non-empty string")
    return value


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(_READ_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_file(path: str, *, reject_symlink: bool = True) -> str:
    """Return the SHA-256 of an absolute regular file.

    The final path component must not be a symlink when ``reject_symlink`` is
    set. Parent directories may still be symlinks, which keeps ordinary
    locations such as ``/tmp`` usable.
    """
    _text(path, "path")
    candidate = Path(path)
    if not candidate.is_absolute():
        raise ArtifactRefError(f"artifact path must be absolute: {path}")
    if reject_symlink and candidate.is_symlink():
        raise ArtifactRefError(f"artifact path must not be a symlink: {path}")
    if not candidate.exists():
        raise ArtifactRefError(f"artifact file is missing: {path}")
    if not candidate.is_file():
        raise ArtifactRefError(f"artifact path is not a regular file: {path}")
    return _digest(candidate)


def canonical_json_sha256(value: object) -> str:
    """Return the SHA-256 of a canonical JSON serialization of ``value``."""
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def make_artifact_ref(
    path: str, role: str, version: str, status: str
) -> Dict[str, Any]:
    """Build a reference committing to the current bytes of ``path``."""
    _text(role, "role")
    _text(version, "version")
    _text(status, "status")
    digest = sha256_file(path)
    return {
        "schema_version": SCHEMA_VERSION,
        "path": str(Path(path)),
        "role": role,
        "version": version,
        "status": status,
        "sha256": digest,
        "bytes": Path(path).stat().st_size,
    }


def relative_ref(ref: Dict[str, Any], root: str) -> Dict[str, Any]:
    """Return ``ref`` with its path rewritten relative to ``root``.

    Producers store relative paths so a handoff directory stays verifiable
    after it is moved or copied. ``verify_artifact_ref`` resolves them against
    the root supplied by the consumer.
    """
    resolved_root = Path(root).resolve()
    target = Path(ref["path"]).resolve()
    try:
        relative = target.relative_to(resolved_root)
    except ValueError as exc:
        raise ArtifactRefError(
            f"artifact {ref['path']} is outside declared root {root}"
        ) from exc
    return {**ref, "path": relative.as_posix()}


def verify_artifact_ref(
    ref: Dict[str, Any], *, root: Optional[str] = None
) -> Dict[str, Any]:
    """Recompute and confirm a reference. Never trusts the recorded digest."""
    if not isinstance(ref, dict):
        raise ArtifactRefError("artifact reference must be an object")
    for field in REQUIRED_REF_FIELDS:
        if field not in ref:
            raise ArtifactRefError(f"artifact reference is missing {field}")
    recorded = _text(ref.get("sha256"), "sha256")
    if not HASH_PATTERN.fullmatch(recorded):
        raise ArtifactRefError("sha256 must be a lowercase SHA-256 digest")
    declared = _text(ref.get("path"), "path")

    candidate = Path(declared)
    if candidate.is_absolute():
        target = candidate
    else:
        if root is None:
            raise ArtifactRefError(
                f"relative artifact path needs a root: {declared}"
            )
        if ".." in candidate.parts:
            raise ArtifactRefError(
                f"artifact path must not traverse upward: {declared}"
            )
        target = Path(root) / candidate

    if target.is_symlink():
        raise ArtifactRefError(
            f"artifact path must not be a symlink: {declared}"
        )
    if not target.exists() or not target.is_file():
        raise ArtifactRefError(f"artifact file is missing: {declared}")

    resolved = target.resolve()
    if root is not None:
        resolved_root = Path(root).resolve()
        try:
            resolved.relative_to(resolved_root)
        except ValueError as exc:
            raise ArtifactRefError(
                f"artifact {declared} escapes declared root {root}"
            ) from exc

    actual = _digest(resolved)
    if actual != recorded:
        raise ArtifactRefError(
            f"artifact hash mismatch for {declared}: "
            f"recorded {recorded}, actual {actual}"
        )
    recorded_size = ref.get("bytes")
    if not isinstance(recorded_size, int) or isinstance(recorded_size, bool):
        raise ArtifactRefError(f"bytes must be an integer for {declared}")
    size = resolved.stat().st_size
    if size != recorded_size:
        raise ArtifactRefError(
            f"artifact size mismatch for {declared}: "
            f"recorded {recorded_size}, actual {size}"
        )
    return {**ref, "verified": True, "resolved_path": str(resolved)}


def _tree_entry(ref: Dict[str, Any]) -> Dict[str, Any]:
    declared = _text(ref.get("path"), "path")
    candidate = Path(declared)
    if candidate.is_absolute():
        raise ArtifactRefError(
            f"tree entries must use paths relative to the root: {declared}"
        )
    if ".." in candidate.parts:
        raise ArtifactRefError(f"tree entry must not traverse upward: {declared}")
    digest = _text(ref.get("sha256"), "sha256")
    if not HASH_PATTERN.fullmatch(digest):
        raise ArtifactRefError(f"tree entry {declared} has a malformed sha256")
    size = ref.get("bytes")
    if not isinstance(size, int) or isinstance(size, bool):
        raise ArtifactRefError(f"tree entry {declared} needs an integer bytes")
    return {"path": candidate.as_posix(), "sha256": digest, "bytes": size}


def canonical_tree_hash(root: str, entries: List[Dict[str, Any]]) -> str:
    """Hash a set of relative artifact references deterministically.

    The digest covers path, content hash, and size for every entry, ordered by
    path. It deliberately excludes ``root`` so a handoff directory that is
    moved or copied still verifies. Duplicate paths are refused because they
    would make the set ambiguous.
    """
    _text(root, "root")
    normalized = [_tree_entry(ref) for ref in entries]
    paths = [entry["path"] for entry in normalized]
    duplicates = sorted({path for path in paths if paths.count(path) > 1})
    if duplicates:
        raise ArtifactRefError("duplicate tree entries: " + ", ".join(duplicates))
    normalized.sort(key=lambda entry: entry["path"])
    return canonical_json_sha256(
        {"artifact_tree": SCHEMA_VERSION, "entries": normalized}
    )


def verify_tree(
    root: str, entries: Iterable[Dict[str, Any]], expected_tree_sha256: str
) -> List[Dict[str, Any]]:
    """Verify every entry against ``root`` and confirm the tree digest."""
    listed = list(entries)
    verified = [verify_artifact_ref(ref, root=root) for ref in listed]
    actual = canonical_tree_hash(root, listed)
    expected = _text(expected_tree_sha256, "tree_sha256")
    if actual != expected:
        raise ArtifactRefError(
            f"artifact tree hash mismatch: recorded {expected}, actual {actual}"
        )
    return verified
