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

"""Exercise installation, conflict checks, and upgrades in isolated projects."""

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
INSTALLER = ROOT / ".agents/install.py"
MANIFEST = ".agents/shared/.systematic-review-skills.json"
SKILL = "systematic-review/SKILL.md"
RUNTIME = ".agents/shared/v2_runtime.py"


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.project = self.base / "project with spaces"

    def run_install(self, *args, installer=INSTALLER, project=None, success=True):
        result = subprocess.run(
            [sys.executable, str(installer), str(project or self.project), *args],
            cwd=self.base, capture_output=True, text=True, check=False,
        )
        if success:
            self.assertEqual(0, result.returncode, result.stderr)
        else:
            self.assertNotEqual(0, result.returncode, result.stdout)
            self.assertIn("Install error:", result.stderr)
        return result

    def source_copy(self):
        source = self.base / "source"
        (source / ".agents").mkdir(parents=True)
        shutil.copy2(INSTALLER, source / ".agents/install.py")
        shutil.copy2(ROOT / "CITATION.cff", source / "CITATION.cff")
        for directory in ("skills", "shared"):
            shutil.copytree(
                ROOT / ".agents" / directory, source / ".agents" / directory,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "tests"),
            )
        return source

    def manifest(self):
        return json.loads((self.project / MANIFEST).read_text(encoding="utf-8"))

    def snapshot(self):
        return {path.relative_to(self.project).as_posix(): path.read_bytes()
                for path in self.project.rglob("*") if path.is_file()}

    def assert_layout(self, agent):
        folder = ".agents" if agent == "codex" else ".claude"
        source = ROOT / ".agents/skills"
        expected = sorted(path.name for path in source.glob("systematic-review*") if path.is_dir())
        actual = sorted(path.name for path in (self.project / folder / "skills").iterdir())
        self.assertEqual(expected, actual)
        for name in expected:
            for path in (source / name).rglob("*"):
                if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                    copied = self.project / folder / "skills" / path.relative_to(source)
                    self.assertEqual(path.read_bytes(), copied.read_bytes())
        self.assertTrue((self.project / RUNTIME).is_file())
        self.assertFalse((self.project / ".agents/shared/tests").exists())
        self.assertFalse(list(self.project.rglob("__pycache__")))
        self.assertFalse(list(self.project.rglob("*.pyc")))
        manifest = self.manifest()
        self.assertEqual("0.2.0", manifest["version"])
        installed = self.snapshot()
        self.assertEqual(set(installed) - {MANIFEST}, set(manifest["files"]))
        for relative, sha256 in manifest["files"].items():
            self.assertEqual(hashlib.sha256(installed[relative]).hexdigest(), sha256)

    def test_codex_default_layout(self):
        result = self.run_install()
        self.assert_layout("codex")
        self.assertFalse((self.project / ".claude").exists())
        self.assertIn("Use $systematic-review", result.stdout)

    def test_claude_layout(self):
        result = self.run_install("--agent", "claude")
        self.assert_layout("claude")
        self.assertFalse((self.project / ".agents/skills").exists())
        self.assertIn("Use the systematic-review skill", result.stdout)

    def test_both_layouts(self):
        self.run_install("--agent", "both")
        self.assert_layout("codex")
        self.assert_layout("claude")

    def test_dry_run_writes_nothing(self):
        result = self.run_install("--agent", "both", "--dry-run")
        self.assertFalse(self.project.exists())
        self.assertIn("WOULD COPY", result.stdout)
        self.assertIn("WOULD WRITE " + MANIFEST, result.stdout)
        self.run_install()
        before = self.snapshot()
        self.run_install("--agent", "both", "--dry-run")
        self.assertEqual(before, self.snapshot())

    def test_modified_file_blocks_entire_install(self):
        self.run_install()
        (self.project / RUNTIME).write_text("local edit", encoding="utf-8")
        before = self.snapshot()
        result = self.run_install("--agent", "both", success=False)
        self.assertIn("User-modified file: " + RUNTIME, result.stderr)
        self.assertEqual(before, self.snapshot())
        self.assertFalse((self.project / ".claude").exists())

    def test_untracked_conflict_blocks_install(self):
        target = self.project / ".agents/skills" / SKILL
        target.parent.mkdir(parents=True)
        target.write_text("existing skill", encoding="utf-8")
        before = self.snapshot()
        result = self.run_install(success=False)
        self.assertIn("Existing different file:", result.stderr)
        self.assertEqual(before, self.snapshot())

    def test_force_overwrites_modified_file(self):
        self.run_install()
        (self.project / RUNTIME).write_text("local edit", encoding="utf-8")
        before = self.snapshot()
        self.run_install("--force", "--dry-run")
        self.assertEqual(before, self.snapshot())
        result = self.run_install("--force")
        self.assertIn("FORCE user-modified file:", result.stdout)
        self.assertEqual((ROOT / RUNTIME).read_bytes(), (self.project / RUNTIME).read_bytes())

    def test_upgrade_replaces_unmodified_files_and_removes_obsolete_files(self):
        source = self.source_copy()
        installer = source / ".agents/install.py"
        obsolete = source / ".agents/shared/obsolete.txt"
        obsolete.write_text("old release", encoding="utf-8")
        self.run_install(installer=installer)
        runtime = source / RUNTIME
        runtime.write_bytes(runtime.read_bytes() + b"\n# New release\n")
        citation = source / "CITATION.cff"
        citation.write_text(citation.read_text().replace("version: 0.2.0", "version: 0.3.0"))
        obsolete.unlink()
        unrelated = self.project / ".agents/shared/local.txt"
        unrelated.write_text("keep me", encoding="utf-8")
        result = self.run_install(installer=installer)
        self.assertIn("UPDATE " + RUNTIME, result.stdout)
        self.assertEqual(runtime.read_bytes(), (self.project / RUNTIME).read_bytes())
        self.assertFalse((self.project / ".agents/shared/obsolete.txt").exists())
        self.assertNotIn(".agents/shared/obsolete.txt", self.manifest()["files"])
        self.assertEqual("keep me", unrelated.read_text())
        self.assertEqual("0.3.0", self.manifest()["version"])

    def test_modified_obsolete_file_requires_force(self):
        source = self.source_copy()
        installer = source / ".agents/install.py"
        obsolete = source / ".agents/shared/obsolete.txt"
        obsolete.write_text("original", encoding="utf-8")
        self.run_install(installer=installer)
        target = self.project / ".agents/shared/obsolete.txt"
        target.write_text("local edit", encoding="utf-8")
        obsolete.unlink()
        self.run_install(installer=installer, success=False)
        self.assertEqual("local edit", target.read_text())
        self.run_install("--force", installer=installer)
        self.assertFalse(target.exists())

    def test_agent_switch_preserves_previous_manifest_entries(self):
        self.run_install()
        previous = self.manifest()["files"]
        self.run_install("--agent", "claude")
        self.assertTrue(set(previous).issubset(self.manifest()["files"]))
        before = self.snapshot()
        self.run_install("--agent", "both")
        self.assertEqual(before, self.snapshot())

    def test_installed_validator_runs_from_project(self):
        self.run_install("--agent", "claude")
        config = self.project / "review_config.json"
        shutil.copy2(ROOT / "examples/minimal-review/review_config.json", config)
        result = subprocess.run(
            [sys.executable, str(self.project / RUNTIME), "validate-config", str(config)],
            cwd=self.project, capture_output=True, text=True, check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(json.loads(config.read_text()), json.loads(result.stdout))

    def test_refuses_source_repository_even_with_force_or_alias(self):
        for flags in ((), ("--force",), ("--dry-run",)):
            result = self.run_install(*flags, project=ROOT, success=False)
            self.assertIn("source repository itself", result.stderr)
        alias = self.base / "alias"
        alias.symlink_to(ROOT, target_is_directory=True)
        self.run_install(project=alias, success=False)

    def test_invalid_claude_frontmatter_is_reported_without_writes(self):
        source = self.source_copy()
        skill = source / ".agents/skills" / SKILL
        original = skill.read_text(encoding="utf-8")
        for metadata in (
            "name: Bad_Name\ndescription: Valid description",
            "name: " + "a" * 65 + "\ndescription: Valid description",
            "name: systematic-review",
            "name: systematic-review\ndescription: " + "a" * 1025,
        ):
            with self.subTest(metadata=metadata[:80]):
                skill.write_text("---\n" + metadata + "\n---\nBody\n", encoding="utf-8")
                result = self.run_install("--agent", "claude", installer=source / ".agents/install.py", success=False)
                self.assertIn("SKILL.md:", result.stderr)
                self.assertFalse(self.project.exists())
        skill.write_text(original, encoding="utf-8")

    def test_symlink_destination_is_not_followed(self):
        outside = self.base / "outside"
        outside.mkdir()
        self.project.mkdir()
        (self.project / ".agents").symlink_to(outside, target_is_directory=True)
        result = self.run_install("--force", success=False)
        self.assertIn("symlinked destination", result.stderr)
        self.assertEqual([], list(outside.iterdir()))

    def test_invalid_manifest_is_not_overwritten(self):
        self.run_install()
        manifest = self.project / MANIFEST
        data = self.manifest()
        data["files"]["../../outside"] = "a" * 64
        manifest.write_text(json.dumps(data), encoding="utf-8")
        before = self.snapshot()
        self.run_install("--force", success=False)
        self.assertEqual(before, self.snapshot())

    def test_file_in_place_of_destination_directory_is_reported(self):
        self.project.mkdir()
        (self.project / ".agents").write_text("keep", encoding="utf-8")
        result = self.run_install(success=False)
        self.assertIn("not a directory", result.stderr)
        self.assertEqual("keep", (self.project / ".agents").read_text())


if __name__ == "__main__":
    unittest.main()
