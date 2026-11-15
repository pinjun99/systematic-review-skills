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

"""Check documented commands in both directions against real CLI help."""

from pathlib import Path
import re
import shlex
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = {
    "v2_runtime.py", "v2_screening.py", "v2_corrections.py",
    "workspace_lifecycle.py", "audit_policy.py", "execution_control.py",
    "prisma_flow.py",
}


class ValidatorDocumentationTests(unittest.TestCase):
    def help_text(self, script, *args):
        result = subprocess.run(
            [sys.executable, str(ROOT / ".agents" / "shared" / script), *args, "--help"],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stderr)
        return result.stdout

    def test_documented_commands_and_examples_match_help(self):
        page = (ROOT / "docs" / "validators.md").read_text(encoding="utf-8")
        sections = re.split(r"^## `([^`]+\.py)`\s*$", page, flags=re.M)
        names = sections[1::2]
        self.assertEqual(SCRIPTS, set(names))
        self.assertEqual(len(SCRIPTS), len(names))
        for script, body in zip(names, sections[2::2]):
            with self.subTest(script=script):
                help_text = self.help_text(script)
                # Only positional choices denote subcommands; option choices
                # such as --format {mermaid,svg,text} do not.
                choices = re.search(r"^  \{([^}]+)\}", help_text, re.M)
                actual = set(choices.group(1).split(",")) if choices else set()
                headings = re.findall(r"^### `([^`]+)`\s*$", body, re.M)
                self.assertEqual(actual, set(headings))
                self.assertEqual(len(actual), len(headings))
                examples = [
                    shlex.split(line)
                    for line in body.splitlines()
                    if line.startswith(f"python3 .agents/shared/{script} ")
                ]
                if script == "audit_policy.py":
                    self.assertEqual("", help_text, "Document any newly added audit CLI")
                    self.assertIn("No CLI or subcommands", body)
                    self.assertEqual([], examples)
                    continue
                self.assertTrue(help_text.startswith("usage:"))
                if actual:
                    self.assertEqual(actual, {example[2] for example in examples})
                else:
                    self.assertIn("No subcommands", body)
                    self.assertTrue(examples)
                for example in examples:
                    command = [example[2]] if actual else []
                    command_help = self.help_text(script, *command)
                    flags = {arg.split("=", 1)[0] for arg in example if arg.startswith("--")}
                    known_flags = set(re.findall(r"--[a-z][a-z-]*", command_help))
                    self.assertLessEqual(flags, known_flags, example)


if __name__ == "__main__":
    unittest.main()
