# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses [semantic versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2026-11-18

### Added

- A Python 3.10+ standard-library installer at `.agents/install.py` for Codex,
  Claude Code, or both, with shared validators always at `.agents/shared/` (#18).
- Dry-run previews, conflict checks, explicit force replacement, and a versioned
  file-hash manifest for upgrades that preserve local changes by default (#18).
- Installer regression tests covering layouts, conflicts, upgrades, frontmatter,
  and validator execution from a target project (#18).
- A Python 3.10+ standard-library PRISMA 2020 flow renderer for Mermaid, SVG,
  and text, reusing derived-count verification with optional source and
  exclusion-reason breakdowns, a fictional example, and regression tests (#19).
- An optional "other methods" column on the PRISMA 2020 flow diagram for
  websites, organisations, and citation searching, contributed by
  Golden007-prog. Diagrams without that block stay byte-identical (#23).

### Changed

- Reporting step 8 now directs agents to render the PRISMA figure from derived
  counts; the CLI reference documents its input, validation, and exit codes (#19).
- Installation and quick-start documentation now use the installer and explain
  native project skill discovery for both agents (#18).

### Fixed

- The citation paragraph in the README still named version 0.1.0 after the
  0.2.0 release; it now matches the released version, as does the stale
  version line in the user manual.

### Security

- GitHub Actions in `.github/workflows/tests.yml` are pinned to commit SHAs
  (`actions/checkout` v4.4.0 and `actions/setup-python` v5.6.0) (#1).

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

[Unreleased]: https://github.com/pinjun99/systematic-review-skills/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/pinjun99/systematic-review-skills/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/pinjun99/systematic-review-skills/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/pinjun99/systematic-review-skills/releases/tag/v0.1.0
