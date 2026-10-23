# User manual

This manual explains how to run the systematic-review skill collection. For a
compact input/output table, see [Outputs by step](pipeline-map.md).

## 1. Start a review

Open the repository in Codex and invoke the coordinator by name:

> Use `$systematic-review` to start a systematic review about `[topic]`.
> Identify the appropriate review type, create the protocol and review
> configuration, ask me for required decisions, and stop for M1 approval.

The coordinator selects one or more active method modules:

- clinical intervention;
- observational or association;
- AI diagnostic, prediction, or evaluation;
- preclinical or organ-bath; or
- scoping and evidence mapping.

It should load only the active module and current phase skill, not the entire
repository at once.

## 2. Resume a review

Point the coordinator to the review workspace:

> Use `$systematic-review` to resume `[workspace path]`. Validate
> `review_config.json` and the latest `phase_result.json`. Report the completed
> phase, unresolved exceptions, required human action, and next phase. Continue
> only with the next required skill.

A valid phase result uses one of these states:

| State | Meaning |
|---|---|
| `READY` | Work is valid and may move to the named next phase. |
| `NEEDS_HUMAN` | A consequential decision or unresolved exception needs a person. |
| `APPROVED` | The relevant human milestone is bound to the approved subject. |
| `SUPERSEDED` | A newer approved or corrected artifact replaces this one. |

Do not infer progress from a folder name. Validate the latest phase result and
the referenced inputs and outputs.

## 3. Invoke one phase directly

Use a phase skill directly only when its inputs are complete. A good prompt is:

> Use `$[skill-name]` with the approved inputs in `[workspace path]`. Validate
> the inputs, perform only this phase, record unresolved exceptions, write the
> phase result, and stop at the stated boundary.

Examples:

> Use `$systematic-review-title-abstract-screening` with the deduplicated corpus
> and approved eligibility criteria. Retain uncertainty, route disagreements to
> me, reconcile the counts, and stop before full-text retrieval.

> Use `$systematic-review-data-extraction` with the M3-approved included corpus.
> Pilot the extraction form, verify critical fields, route consequential
> unresolved judgments to me, and stop before synthesis planning.

## 4. Approve only five scheduled milestones

Routine work does not need constant approval. Scheduled human approval occurs
at five milestones, plus genuine scientific exceptions.

### M1 — protocol and eligibility

Approve the research question, review type, eligibility criteria, outcomes or
mapping fields, planned appraisal, synthesis plan, team declarations,
registration intent, and AI-use policy.

M1 unlocks search design. A later scientific change requires a documented
protocol amendment and targeted rework of affected records.

### M2 — final search

Approve the exact database/platform strategies after validation and appropriate
peer review. Search execution may not make a scientific change to an approved
strategy.

### M3 — study selection

Approve the included-study set, full-text exclusions with one primary reason,
retrieval exceptions, study/report linkage, and reconciled PRISMA counts.

### M4 — evidence and synthesis decisions

Approve the validated extraction dataset, applicable appraisal status, mapping
of results to synthesis groups, justified amendments, limitations, and planned
synthesis route.

### M5 — publication package

Approve the final manuscript, tables, figures, supplements, declarations, and
claim ledger only after independent quality control has cleared critical and
important findings.

## 5. Understand the evidence tiers

The workflow avoids unnecessary quotation work while requiring strong support
where mistakes would matter.

| Tier | Use |
|---|---|
| Tier 0 | Routine structured records and ordinary inclusions; no manufactured quotations. |
| Tier 1 | A decisive exclusion reason with one verified title/abstract span or full-text locator. |
| Tier 2 | Uncertain or consequential evidence, numerical results, critical design details, appraisal judgments, and major claims. |

An exclusion needs one primary reason. Once that reason is established, do not
assess every remaining criterion unless adjudication requires it.

## 6. Handle exceptions safely

Send a case to a human when it involves:

- ambiguity or reviewer disagreement;
- conflicting reports or values;
- poor text extraction or uncertain study/report linkage;
- a proposed change to eligibility or synthesis methods;
- missing evidence for a consequential judgment;
- a choice between plausible incompatible interpretations; or
- an override of an approved rule.

Do not restart an unaffected phase. Register the issue against the artifact that
owns the error, correct that artifact, and invalidate only its actual downstream
dependents.

## 7. Phase boundaries

Each skill stops before the next skill's work:

- search design does not execute searches;
- search execution does not deduplicate;
- deduplication does not screen;
- title/abstract screening does not retrieve full text;
- retrieval does not make eligibility decisions;
- full-text screening does not extract study results;
- data extraction does not choose a synthesis because of observed results;
- synthesis planning does not calculate final results;
- reporting does not perform its own independent QC; and
- independent QC does not silently edit scientific source artifacts.

If a skill is asked to cross its boundary, it should stop and name the correct
next skill.

## 8. Scientific safety rules

- Never treat an inaccessible report as scientifically excluded.
- Never require a supporting quotation for every criterion of a routine
  inclusion.
- Never silently normalize, infer, or choose between contradictory study values.
- Never convert risk-of-bias judgments into an unvalidated numerical score.
- Never change a synthesis method because of significance or effect direction.
- Never overstate certainty, causality, applicability, or recommendations.
- Never claim completion while unresolved consequential issues remain.

## 9. Useful files

| File | Purpose |
|---|---|
| `review_config.json` | Review identity, active modules, team roles, and AI policy. |
| `protocol.json` | Approved scientific methods and eligibility contract. |
| `phase_result.json` | Current phase, state, inputs, outputs, unresolved issues, and next phase. |
| Milestone approval record | Human approval bound to the exact milestone subject. |
| Screening decision records | Reviewer decisions using stable record/study IDs and evidence tiers. |
| Screening resolutions | Final decision or human route after reviewer comparison. |
| Dependency graph | Records which downstream artifacts consume a corrected source. |

Shared JSON is validated with `.agents/shared/v2_runtime.py`. Screening
resolutions use `.agents/shared/v2_screening.py`, and local issue routing
uses `.agents/shared/v2_corrections.py`.

## 10. Limits of this release

Version 0.1.0 is an early release. A person approves M1–M5 and every
consequential exception. The skills do not replace a review team, an
information specialist, or a statistician, and they do not provide medical
advice.

Paired model benchmarks are still pending. The release record in
`.agents/shared/references/v2-static-metrics.json` stays blocked until those
runs exist.

The workspace lifecycle does not implement a separate meta-analysis phase, a
living-review updater, or a post-publication archive. Structured synthesis is
guided and checked. The calculations themselves are produced with code the
review team can rerun.

Database access, paywalled full texts, and official appraisal forms are the
user's responsibility. Do not commit search exports, PDFs, or SQLite review
databases.

## 11. Where to go next

Use [Outputs by step](pipeline-map.md) to see exactly what each skill consumes,
what it produces, its completion signal, and the next skill. For background on
how a health-intervention review is conducted, see
[A–Z methods outline](systematic-review-a-to-z.md).
