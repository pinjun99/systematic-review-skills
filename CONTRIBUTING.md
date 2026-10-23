# Contributing

Thank you for helping improve Systematic Review Skills. The maintainer is
Ooi Pin Jun ([@pinjun99](https://github.com/pinjun99)).

This project guides systematic reviews. A change to a skill can change what an
agent does with someone else's evidence, so please keep scientific behaviour
explicit.

## Ways to help

- Correct a skill, validator, or document, and add or update a test when the
  behaviour is mechanical.
- Improve the examples and the user manual.
- Report a bug with fictional study data only.

Please open an issue before a large change, especially one that touches
eligibility, screening decisions, appraisal, synthesis, or certainty.

## Scientific boundaries

- Do not change eligibility, a synthesis method, or an interpretation because a
  result was significant or pointed in a particular direction.
- Keep human approval at M1–M5, and route genuine ambiguity to a person.
- Treat a failure to retrieve a report as an access outcome. Do not turn it
  into a scientific exclusion.
- Do not present the workflow as release-ready while
  `.agents/shared/references/v2-baseline.json` has `"promotion_allowed": false`.
- Use fictional or already-public examples. Do not commit search exports,
  PDFs, SQLite databases, or files matching `.env*`.

## Setup

You need Python 3.12 (the version used in CI). The tests use the standard
library only.

```bash
git clone https://github.com/pinjun99/Systematic_Review.git
cd Systematic_Review
python3 .agents/run_tests.py
```

The command runs every `test_*.py` module under `.agents/` except two modules
that do not describe the lean tree. The reason is recorded in
`.agents/run_tests.py`.

## Changing a skill

Skills live in `.agents/skills/systematic-review*/SKILL.md`.

- Keep the primary `SKILL.md` at or under 100 lines. `test_v2_skills.py`
  enforces that limit.
- Do not add a `## Workspace lifecycle` section to a skill. The lean suite
  forbids that heading.
- Keep front matter (`name`, `description`) and `agents/openai.yaml` intact.
- Put long examples in a reference file next to the skill, and point to that
  file from the workflow steps.
- Preserve stable study and report identifiers in any example.

## Pull requests

Use the pull-request template. Describe the scientific effect, and confirm that
`python3 .agents/run_tests.py` passes.

By submitting a contribution, you agree that it is licensed under the Apache
License, Version 2.0, the same terms as the rest of this repository.

## Conduct and security

Please follow the [Code of Conduct](CODE_OF_CONDUCT.md). Report security issues
privately, as described in [SECURITY.md](SECURITY.md).
