# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses [semantic versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-10-22

First public release.

### Added

- A coordinator skill and fourteen phase skills, from protocol through
  independent quality control.
- Shared validators for review configuration, screening decisions, corrections,
  audit policy, execution control, and the workspace lifecycle.
- A user manual, a pipeline map, and an A–Z methods outline.
- A GitHub Actions workflow that runs `python3 .agents/run_tests.py`.
- Community files: contributing guide, code of conduct, security policy,
  citation metadata, and issue and pull-request templates.

### Notes

- The scientific release benchmark is still pending paired model runs.
  `promotion_allowed` remains false.
- `python3 .agents/run_tests.py` runs every `test_*.py` module under `.agents/`
  except two modules that do not match the lean tree. See the comment in
  `.agents/run_tests.py`.
- This release replaces the previous private licence. Public terms are the
  Apache License, Version 2.0. Copyright 2026 Ooi Pin Jun.
