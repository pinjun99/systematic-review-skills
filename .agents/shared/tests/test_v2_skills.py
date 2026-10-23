#!/usr/bin/env python3

from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[3]
SKILLS = ROOT / ".agents" / "skills"
SKILL_FILES = sorted(SKILLS.glob("systematic-review*/SKILL.md"))


class SkillStructureTests(unittest.TestCase):
    def test_coordinator_and_fourteen_phase_skills_exist(self):
        self.assertEqual(15, len(SKILL_FILES))

    def test_templates_are_fully_replaced(self):
        for path in SKILL_FILES:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("[TODO", text, path)
            self.assertRegex(text, r"\A---\nname: systematic-review")

    def test_primary_instructions_are_concise(self):
        for path in SKILL_FILES:
            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertLessEqual(len(lines), 100, path)

    def test_lifecycle_boilerplate_is_not_repeated(self):
        for path in SKILL_FILES:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("## Workspace lifecycle", text, path)
        combined = "\n".join(path.read_text(encoding="utf-8") for path in SKILL_FILES)
        self.assertLessEqual(combined.count("milestone_approval"), 2)

    def test_only_five_scheduled_milestones(self):
        coordinator = (SKILLS / "systematic-review" / "SKILL.md").read_text(encoding="utf-8")
        for milestone in ("M1", "M2", "M3", "M4", "M5"):
            self.assertIn(milestone, coordinator)
        self.assertNotRegex(coordinator, r"M[6-9]")

    def test_progressive_module_loading_is_explicit(self):
        coordinator = (SKILLS / "systematic-review" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Do not load all phase skills or method modules at once", coordinator)
        modules = (SKILLS / "systematic-review" / "references" / "method-modules.md").read_text(encoding="utf-8")
        for heading in (
            "Clinical intervention", "Observational or association",
            "AI diagnostic, prediction, or evaluation", "Preclinical and organ bath",
            "Scoping and evidence mapping"
        ):
            self.assertIn(f"## {heading}", modules)

    def test_screening_policy_does_not_require_inclusion_quotes(self):
        full_text = (SKILLS / "systematic-review-full-text-screening" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("no manufactured quotations", full_text)
        self.assertIn("one verified supporting passage", full_text)
        self.assertNotIn("all eight", full_text.lower())

    def test_every_skill_has_ui_metadata(self):
        for path in SKILL_FILES:
            metadata = path.parent / "agents" / "openai.yaml"
            self.assertTrue(metadata.is_file(), metadata)
            text = metadata.read_text(encoding="utf-8")
            self.assertIn("default_prompt:", text)


if __name__ == "__main__":
    unittest.main()
