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

"""Install project skills and their shared runtime using only the stdlib."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ".agents/shared/.systematic-review-skills.json"
SKILL_ROOTS = {"codex": ".agents/skills", "claude": ".claude/skills"}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_frontmatter(path: Path) -> None:
    """Check the suite's single-line YAML metadata without rewriting content."""
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---" or "---" not in lines[1:]:
        raise ValueError(f"{path}: missing YAML frontmatter")
    fields = {}
    for line in lines[1:lines.index("---", 1)]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.fullmatch(r"([a-z-]+):\s*(.*)", line)
        if not match or match[1] in fields:
            raise ValueError(f"{path}: expected unique, single-line frontmatter fields")
        value = match[2].strip()
        if value.startswith('"'):
            value = json.loads(value)
        elif value.startswith("'") and value.endswith("'"):
            value = value[1:-1].replace("''", "'")
        elif (value.startswith(tuple("'|>!&*[{")) or ": " in value
              or " #" in value or value.lower() in {"null", "true", "false", "~"}):
            raise ValueError(f"{path}: use a plain or quoted single-line scalar for {match[1]}")
        fields[match[1]] = value
    name = fields.get("name", "")
    description = fields.get("description", "")
    if (not isinstance(name, str) or len(name) > 64
            or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name)):
        raise ValueError(f"{path}: name must be lowercase-hyphen format, at most 64 characters")
    if not isinstance(description, str) or not description.strip() or len(description) > 1024:
        raise ValueError(f"{path}: description must be present and at most 1024 characters")


def source_files(directory: Path, shared: bool = False) -> list[Path]:
    if not directory.is_dir() or directory.is_symlink():
        raise ValueError(f"Missing or symlinked source directory: {directory}")
    files = []
    for path in sorted(directory.rglob("*")):
        relative = path.relative_to(directory)
        if ("__pycache__" in relative.parts or path.suffix == ".pyc"
                or (shared and relative.parts[0] == "tests")):
            continue
        if path.is_symlink():
            raise ValueError(f"Symlinked source is not supported: {path}")
        if path.is_file():
            files.append(path)
    return files


def managed_path(relative: str) -> bool:
    path = PurePosixPath(relative)
    if (path.is_absolute() or ".." in path.parts or "\\" in relative
            or path.as_posix() != relative or relative == MANIFEST):
        return False
    parts = path.parts
    return (len(parts) >= 3 and parts[:2] == (".agents", "shared")) or (
        len(parts) >= 4 and parts[0] in {".agents", ".claude"}
        and parts[1] == "skills" and parts[2].startswith("systematic-review")
    )


def checked_target(project: Path, relative: str) -> Path:
    """Reject symlinks and directory/file collisions, including with --force."""
    path = project / relative
    for entry in (path, *path.parents):
        if entry.is_symlink():
            raise ValueError(f"Refusing symlinked destination: {entry}")
        if entry == path:
            if entry.exists() and not entry.is_file():
                raise ValueError(f"Destination is not a file: {entry}")
        elif entry.exists() and not entry.is_dir():
            raise ValueError(f"Destination parent is not a directory: {entry}")
    return path


def previous_install(project: Path) -> dict[str, str]:
    path = checked_target(project, MANIFEST)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(data, dict) or data.get("schema_version") != 1
            or not isinstance(data.get("version"), str)
            or not isinstance(data.get("files"), dict)):
        raise ValueError(f"Invalid install manifest: {path}")
    for relative, sha256 in data["files"].items():
        if (not managed_path(relative) or not isinstance(sha256, str)
                or not re.fullmatch(r"[0-9a-f]{64}", sha256)):
            raise ValueError(f"Invalid install manifest entry: {relative}")
    return data["files"]


def install(project: Path, agent: str, dry_run: bool, force: bool) -> None:
    project = project.expanduser().resolve()
    if project == ROOT:
        raise ValueError("Refusing to install into the source repository itself")
    agents = list(SKILL_ROOTS) if agent == "both" else [agent]
    skills = sorted(path for path in (ROOT / ".agents/skills").glob("systematic-review*")
                    if path.is_dir())
    if not skills:
        raise ValueError("No systematic-review skills found in the source repository")
    sources = {}
    for skill in skills:
        if not (skill / "SKILL.md").is_file():
            raise ValueError(f"Missing SKILL.md: {skill}")
        if "claude" in agents:
            validate_frontmatter(skill / "SKILL.md")
        for source in source_files(skill):
            for selected in agents:
                relative = f"{SKILL_ROOTS[selected]}/{skill.name}/{source.relative_to(skill).as_posix()}"
                sources[relative] = source
    shared = ROOT / ".agents/shared"
    for source in source_files(shared, shared=True):
        relative = f".agents/shared/{source.relative_to(shared).as_posix()}"
        if relative != MANIFEST:
            sources[relative] = source
    citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    version = re.search(r"^version: ([0-9]+\.[0-9]+\.[0-9]+)\s*$", citation, re.M)
    if not version:
        raise ValueError("Cannot read release version from CITATION.cff")

    previous = previous_install(project)
    hashes = dict(previous)
    operations = []
    conflicts = []
    prefixes = [".agents/shared/"] + [f"{SKILL_ROOTS[item]}/" for item in agents]
    stale = {relative for relative in previous if relative not in sources
             and any(relative.startswith(prefix) for prefix in prefixes)}
    for relative in sorted(set(sources) | stale):
        target = checked_target(project, relative)
        current = digest(target) if target.exists() else None
        incoming = digest(sources[relative]) if relative in sources else None
        changed = current is not None and current != incoming and current != previous.get(relative)
        if changed:
            label = "User-modified" if relative in previous else "Existing different"
            if not force:
                conflicts.append(f"{label} file: {relative}")
            else:
                print(f"FORCE {label.lower()} file: {relative}")
        if relative in stale:
            hashes.pop(relative)
            if current is not None:
                operations.append(("REMOVE", relative))
        else:
            hashes[relative] = incoming
            action = "KEEP" if current == incoming else ("UPDATE" if current else "COPY")
            operations.append((action, relative))
    if conflicts:
        raise ValueError("\n".join(conflicts) + "\nNo files written. Review changes or use --force.")

    manifest = (json.dumps({"schema_version": 1, "version": version[1], "files": hashes},
                           indent=2, sort_keys=True) + "\n").encode("utf-8")
    manifest_path = checked_target(project, MANIFEST)
    manifest_changed = not manifest_path.exists() or manifest_path.read_bytes() != manifest
    for action, relative in operations:
        print(f"{'WOULD ' if dry_run else ''}{action} {relative}")
        if dry_run or action == "KEEP":
            continue
        target = project / relative
        if action == "REMOVE":
            target.unlink()
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(sources[relative], target)
    if manifest_changed:
        print(f"{'WOULD ' if dry_run else ''}WRITE {MANIFEST}")
        if not dry_run:
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            # Replace the manifest only after every planned file operation succeeds.
            with tempfile.NamedTemporaryFile(dir=manifest_path.parent, delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(manifest)
            try:
                temporary.replace(manifest_path)
            finally:
                temporary.unlink(missing_ok=True)
    counts = {action: sum(item[0] == action for item in operations)
              for action in ("COPY", "UPDATE", "REMOVE", "KEEP")}
    print(f"{'Dry run' if dry_run else 'Installed'}: version {version[1]}, "
          f"{len(skills)} skills for {agent}; " + ", ".join(f"{key.lower()}={value}" for key, value in counts.items()))
    if dry_run:
        print("Next: rerun without --dry-run to install.")
    print(f"Open {project} and run the agent from that project root.")
    if "codex" in agents:
        print("Codex prompt: Use $systematic-review to start a review about [topic].")
    if "claude" in agents:
        print("Claude Code prompt: Use the systematic-review skill to start a review about [topic].")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--agent", choices=("codex", "claude", "both"), default="codex")
    parser.add_argument("--dry-run", action="store_true", help="Show the plan without writing files")
    parser.add_argument("--force", action="store_true", help="Replace conflicting files, including local edits")
    args = parser.parse_args()
    try:
        install(args.project_dir, args.agent, args.dry_run, args.force)
    except (OSError, ValueError) as exc:
        print(f"Install error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
