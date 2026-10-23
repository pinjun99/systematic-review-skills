# Systematic Review Skills

An AI-assisted, human-governed skill collection for conducting a systematic
review from protocol to publication package. The workflow carries routine
steps and keeps scientific decisions, milestone approvals, and consequential
exceptions with a person.

The maintainer is Ooi Pin Jun, a pharmacist and researcher
([@pinjun99](https://github.com/pinjun99)).

## Status

**Early stage, version 0.1.0.** The skills, validators, and automated tests
are in place. The scientific release benchmark has not been run on paired
model executions, so this suite is not yet a validated substitute for an
experienced review team. See [limitations](#limitations).

A person approves five milestones (M1–M5) and every consequential exception.
Read the outputs against the source reports before anyone relies on them.

**This software does not provide medical advice.** It does not diagnose,
treat, or recommend care for any person. A manuscript produced with these
skills is a research report. Clinical decisions need the judgement of a
qualified professional.

## Read these first

1. **[User manual](docs/user-manual.md)** — how to start, resume, approve, and
   move between skills.
2. **[Outputs by step](docs/pipeline-map.md)** — the input, output, completion
   state, and next skill for every step.
3. **[A–Z methods outline](docs/systematic-review-a-to-z.md)** — background
   reading on how a health-intervention systematic review is conducted.

## Quick start

Open this repository in Codex and begin with the coordinator skill:

> Use `$systematic-review` to start a new review about `[topic]`. Create the
> protocol and review configuration, ask me only for required scientific
> decisions, and stop for M1 approval before search design.

To resume an existing review:

> Use `$systematic-review` to resume the review in `[workspace path]`. Validate
> `review_config.json` and the latest `phase_result.json`, tell me the current
> state and unresolved exceptions, then invoke only the next required skill.

You may also invoke a phase skill directly when its required inputs are ready:

> Use `$systematic-review-search-design` with the approved protocol in
> `[workspace path]`. Prepare the final search strategies and stop for M2
> approval. Do not execute the searches.

The skills are Markdown instructions. They are written and tested for Codex.
Another agent can read the same files; that path is not covered by the test
suite.

## Install

Clone this repository so its `.agents/skills/` directory is available inside
your project. To use the collection across projects, copy the individual
folders from `.agents/skills/` into your user-level skills directory.

The tests and validators use the Python 3.12 standard library. CI runs on
Python 3.12.

## Validate

After installing or changing the collection, run:

```bash
python3 .agents/run_tests.py
```

## How the workflow is organized

The coordinator loads only the skill needed for the current phase. Human review
is concentrated at five milestones:

| Milestone | Human approval |
|---|---|
| M1 | Protocol, eligibility criteria, review type, and planned methods |
| M2 | Final search strategies before production searching |
| M3 | Final study selection after full-text screening |
| M4 | Evidence dataset, appraisal status, and synthesis decisions |
| M5 | Final publication package after independent quality control |

The workflow supports clinical intervention, observational or association, AI
diagnostic/prediction/evaluation, preclinical or organ-bath, and scoping or
evidence-mapping reviews. Only the method module needed for the current review
is loaded.

## Every skill: what it teaches, uses, and produces

| Skill | What it teaches or guides | What it uses | Main result |
|---|---|---|---|
| `$systematic-review` | How to coordinate the complete review, resume safely, use evidence tiers, and pause only at real decisions. | `review_config.json`, the latest `phase_result.json`, active method module, and unresolved issues. | A validated progress decision and the correct next phase skill. |
| `$systematic-review-protocol` | How to turn a question into operational eligibility criteria and prespecified methods. | Research question, objectives, team roles, conflicts, funding, registration intent, and AI-use policy. | `review_config.json`, `protocol.json`, planned field sets, and the M1 approval subject. |
| `$systematic-review-search-design` | How to build reproducible, database-specific, sensitive searches and peer-review them. | M1-approved protocol, criteria, sources, dates, languages, and sentinel records. | Exact final strategies, validation/peer-review record, export plan, and M2 approval subject. |
| `$systematic-review-search-execution` | How to execute an approved strategy without silently changing it. | M2-approved strategies, platforms, interfaces, and export requirements. | Preserved raw exports, execution log, source IDs, and reconciled raw-record manifest. |
| `$systematic-review-deduplication` | How to distinguish duplicate records from multiple reports and preserve provenance. | Raw-record manifest and all source exports. | Unique screening records, duplicate groups, provenance, and reconciled counts. |
| `$systematic-review-title-abstract-screening` | How to screen conservatively with one primary AI, targeted independent checking, and human exception routing. | Deduplicated records and M1 eligibility criterion codes. | Validated reviewer decisions, final screening resolutions, retained records, and counts. |
| `$systematic-review-full-text-retrieval` | How to retrieve exact reports lawfully, verify identity, and report access failures without treating them as exclusions. | Records retained after title/abstract screening and available DOI/citation metadata. | Verified full texts, retrieval records, OCR where needed, access exceptions, and reconciled counts. |
| `$systematic-review-full-text-screening` | How to decide study-level eligibility using decisive page-cited evidence for exclusions. | Frozen report corpus, linked reports/studies, and M1 eligibility criteria. | Included studies, one reason per exclusion, exception history, PRISMA counts, and M3 approval subject. |
| `$systematic-review-data-extraction` | How to pilot an extraction form, preserve raw and normalized values, verify critical fields, and adjudicate exceptions. | M1 protocol/method module and the M3-approved included corpus. | Validated study, method, outcome, and result dataset ready for appraisal or synthesis planning. |
| `$systematic-review-risk-of-bias` | How to apply the correct official appraisal tool without converting judgments into a quality score. | Protocol, included studies, extraction data, frozen targets, and source reports. | Reconciled study/result-level judgments with evidence and resolved exceptions. |
| `$systematic-review-synthesis-planning` | How to map every result, assess compatibility, and choose a prespecified synthesis route without reacting to significance. | Extraction dataset, applicable appraisal results, and protocol synthesis plan. | Classified synthesis groups, amendments/limitations, and the M4 approval subject. |
| `$systematic-review-structured-synthesis` | How to conduct meta-analysis, other quantitative synthesis, synthesis without meta-analysis, or evidence mapping reproducibly. | M4-approved classifications, estimands, eligible results, and prespecified methods. | Verified synthesis results with complete study accounting and provenance. |
| `$systematic-review-certainty-of-evidence` | How to assess certainty per important outcome and distinguish no evidence from very-low-certainty evidence. | Protocol outcomes, synthesis results, appraisal findings, and applicable certainty framework. | Evidence-backed certainty judgments and Summary-of-Findings content when applicable. |
| `$systematic-review-reporting-package` | How to draft a restrained, traceable manuscript and reconcile every consequential claim and number. | Approved protocol, study selection, extraction, appraisal, synthesis, and certainty outputs. | Manuscript, tables, figures, supplements, declarations, claim ledger, and M5 candidate package. |
| `$systematic-review-independent-quality-control` | How to audit high-consequence content independently and correct only the real dependents of an error. | Complete reporting candidate, source artifacts, claim ledger, and dependency graph. | QC findings, local correction routes, re-audit state, and clearance for M5 approval. |

## Core operating rules

- Use stable study and report identifiers from search results through reporting.
- Treat retrieval failure as an access outcome, never a scientific exclusion.
- Use routine structured evidence for ordinary records and precise source
  locations for exclusions, uncertainty, numerical results, and major claims.
- When reviewers disagree or evidence is ambiguous, route the case to a human.
- Never choose eligibility or synthesis methods because of effect direction or
  statistical significance.
- Hash milestone subjects and final datasets; ordinary drafts do not need to be
  locked.
- A local correction invalidates only the artifacts that actually depend on it.

## Limitations

- **Benchmark still open.** `.agents/shared/references/v2-static-metrics.json`
  records `BLOCKED_PENDING_MODEL_BENCHMARK`.
  `.agents/shared/references/v2-baseline.json` records
  `"promotion_allowed": false`. Do not describe the suite as release-ready.
- **Human oversight is required.** The five milestones and the exception rules
  are the safety mechanism. An error that nobody notices can still pass.
- **No medical advice.** Outputs are research drafts. They are not clinical
  recommendations.
- **No statistics package.** Structured synthesis tells the team how to
  calculate a prespecified analysis and how to check it. This repository does
  not ship a meta-analysis library. The workspace lifecycle also has no
  separate meta-analysis phase, living-review updater, or post-publication
  archive.
- **No database access and no official forms.** You bring your own access to
  bibliographic databases and paywalled full texts, and you use the current
  official appraisal instruments you are allowed to use. Those instruments are
  not bundled here.
- **Review files stay local.** Search exports, PDFs, and SQLite databases can
  contain licensed text or personal data. `.gitignore` excludes `.env*`,
  `*.pdf`, `*.sqlite`, and `*.ris`. Keep them out of this repository.
- **One maintainer, early code.** Expect rough edges, and expect the methods
  outline in `docs/systematic-review-a-to-z.md` to be background rather than a
  substitute for a methods handbook.

## Contributing

Please read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request,
and the [Code of Conduct](CODE_OF_CONDUCT.md) in every community space. Report
vulnerabilities privately, as described in [SECURITY.md](SECURITY.md).

Contributions are licensed under the Apache License, Version 2.0. Run
`python3 .agents/run_tests.py` before you ask for review. Do not change
eligibility or synthesis methods because of an observed result.

## Citation

If you use this software, please cite Ooi Pin Jun (2026), *Systematic Review
Skills*, version 0.1.0. Machine-readable metadata is in
[CITATION.cff](CITATION.cff).

```bibtex
@software{ooi2026systematic_review_skills,
  author  = {Ooi, Pin Jun},
  title   = {Systematic Review Skills},
  year    = {2026},
  version = {0.1.0},
  license = {Apache-2.0},
  url     = {https://github.com/pinjun99/Systematic_Review}
}
```

## Licence

Copyright 2026 Ooi Pin Jun.

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) and
[NOTICE](NOTICE). You may use, modify, and distribute this software under
those terms. The licence is granted on an "AS IS" basis, without warranty.

## Repository layout

```text
.agents/skills/          coordinator and 14 phase skills
.agents/shared/          validators, screening, corrections, and benchmarks
.agents/run_tests.py     standard-library test runner
.github/workflows/       GitHub Actions test workflow
docs/user-manual.md      operating instructions
docs/pipeline-map.md     inputs and outputs for every step
docs/systematic-review-a-to-z.md
                         background methods outline
CONTRIBUTING.md          how to propose a change
CITATION.cff             citation metadata
```

Start with `$systematic-review`. Use a phase skill directly only when you
already have its approved inputs.
