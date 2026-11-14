# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses [semantic versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-11-14

### Added

- `examples/minimal-review/`: a fictional review configuration, protocol and
  phase result, with a walkthrough and a test that runs its commands (#15).
- `docs/validators.md`, a reference for the shared validator CLIs, checked
  against `--help` (#15).
- `docs/method-modules.md`, the files a new method module must update (#15).
- A test that fails on broken relative Markdown links and heading anchors (#12).
- A synthetic mixed benchmark fixture with one failing and one passing gate (#16).
- Apache-2.0 headers on the shared Python modules, with a test (#11).

### Changed

- `python3 .agents/run_tests.py` now runs every test module. Stale
  expectations about removed behaviour were deleted, and the rest still run (#13).
- `release_gate()` reports `promotion_allowed: false`. It stays false until
  real paired model runs can be verified (#16).
- The quick start explains how to install the skills and use them from
  Claude Code (#15).

### Fixed

- Repository links in CONTRIBUTING, CITATION, SECURITY and the README pointed
  at a non-existent repository (#14).
- `.gitignore` now also covers PubMed, Web of Science and EndNote exports (#11).

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

[0.2.0]: https://github.com/pinjun99/systematic-review-skills/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/pinjun99/systematic-review-skills/releases/tag/v0.1.0
