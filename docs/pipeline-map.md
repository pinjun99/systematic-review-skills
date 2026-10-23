# Outputs by step

This guide shows what each skill uses, what it produces, its completion state,
and what comes next. Read the [User manual](user-manual.md) for operating rules
and example prompts.

## Workflow at a glance

```text
systematic-review (coordinator)
  |
  +-- protocol ----------------------------- M1 approval
  +-- search design ------------------------ M2 approval
  +-- search execution
  +-- deduplication
  +-- title/abstract screening
  +-- full-text retrieval
  +-- full-text screening ------------------ M3 approval
  +-- data extraction
  +-- risk of bias (when applicable)
  +-- synthesis planning ------------------- M4 approval
  +-- structured/quantitative synthesis
  +-- certainty of evidence (when applicable)
  +-- reporting package
  +-- independent quality control
  +-- corrected reporting package ---------- M5 approval
```

## Coordinator

| Skill | Uses | Produces | Completion |
|---|---|---|---|
| `$systematic-review` | `review_config.json`, latest `phase_result.json`, active method module, approvals, and unresolved issues. | A validated progress summary and invocation of only the current phase skill. | `READY` with the next phase, or `NEEDS_HUMAN` with a specific reason. |

## Step-by-step outputs

| Step and skill | Required input | Main output | Finish state | Next skill |
|---|---|---|---|---|
| 1. `$systematic-review-protocol` | Research question, objectives, review type, team/declaration details, registration intent, and AI policy. | `review_config.json`; `protocol.json`; eligibility criterion codes; planned extraction, appraisal, and synthesis fields; M1 subject. | `APPROVED` after M1, otherwise `NEEDS_HUMAN`. | `$systematic-review-search-design` |
| 2. `$systematic-review-search-design` | M1-approved protocol, information sources, dates/languages, and sentinel records. | Exact strategies by platform; validation results; PRESS-compatible peer-review record where appropriate; export plan; M2 subject. | `APPROVED` after M2. | `$systematic-review-search-execution` |
| 3. `$systematic-review-search-execution` | M2-approved strategies, platform/interface details, and export formats. | Preserved raw exports; execution log; exact strings/dates/filters/counts; source IDs; raw-record manifest. | `READY` after count reconciliation. | `$systematic-review-deduplication` |
| 4. `$systematic-review-deduplication` | Raw-record manifest and every raw source export. | Unique screening records; duplicate groups; chosen representatives; provenance; count reconciliation. | `READY`, or `NEEDS_HUMAN` for ambiguous identity. | `$systematic-review-title-abstract-screening` |
| 5. `$systematic-review-title-abstract-screening` | Deduplicated records and M1 eligibility criterion codes. | Reviewer A records; targeted Reviewer B records; screening resolutions; retained records; exclusion reasons; counts. | `READY`, or `NEEDS_HUMAN` for disagreement/ambiguity. | `$systematic-review-full-text-retrieval` |
| 6. `$systematic-review-full-text-retrieval` | Retained records, citation metadata, DOI/identifier data, and authorized access. | Verified source files; retrieval records; stable report IDs; OCR outputs when needed; access exceptions; counts. | `READY` with explicit exceptions. | `$systematic-review-full-text-screening` |
| 7. `$systematic-review-full-text-screening` | Frozen report inventory, study/report links, readable text, and M1 criteria. | Included-study set; one primary reason per exclusion; reviewer/resolution history; retrieval exceptions; PRISMA counts; M3 subject. | `APPROVED` after M3. | `$systematic-review-data-extraction` |
| 8. `$systematic-review-data-extraction` | M3-approved included corpus, M1 protocol, active method module, and pilot rules. | Piloted form; study/report/outcome/result records; raw and normalized values; validation findings; adjudications; final extraction dataset. | `READY` after audit and dataset approval. | Risk of bias when applicable; otherwise synthesis planning. |
| 9. `$systematic-review-risk-of-bias` | Protocol requirement, official tool, frozen targets, extraction data, and reports. | Signalling answers; domain/overall judgments; Tier 2 evidence; second checks; exception resolutions; audit reconciliation. | `READY`, or `NEEDS_HUMAN` for material judgment. | `$systematic-review-synthesis-planning` |
| 10. `$systematic-review-synthesis-planning` | Protocol synthesis plan, extraction dataset, applicable appraisal, and included-result map. | Result-to-group map; compatibility checks; synthesis classifications; amendments; limitations; M4 subject. | `APPROVED` after M4. | `$systematic-review-structured-synthesis` or the approved quantitative route. |
| 11. `$systematic-review-structured-synthesis` | M4-approved groups, estimands, eligible results, and prespecified methods. | Reproducible calculations or structured synthesis; verified inputs; complete study accounting; findings and provenance. | `READY`, or `NEEDS_HUMAN` for consequential discrepancy. | Certainty when applicable; otherwise reporting. |
| 12. `$systematic-review-certainty-of-evidence` | Important outcomes, synthesis results, appraisal findings, and applicable certainty framework. | Per-outcome domain judgments, rationales, certainty labels, and Summary-of-Findings content. | `READY`, or `NEEDS_HUMAN` for consequential uncertainty. | `$systematic-review-reporting-package` |
| 13. `$systematic-review-reporting-package` | All approved upstream evidence, reporting guidance, journal requirements, and declarations. | Manuscript; tables; figures; supplements; PRISMA reconciliation; targeted claim ledger; M5 candidate package. | Candidate remains pending until QC. | `$systematic-review-independent-quality-control` |
| 14. `$systematic-review-independent-quality-control` | Complete candidate package, source artifacts, claim ledger, and dependency graph. | Independent findings; severity and owner references; local correction routes; re-audit result. | `READY` for M5 only when no critical/important finding remains. | Reporting package for corrections, then M5 approval. |

## The five approval subjects

| Milestone | Bound subject | Files unlocked |
|---|---|---|
| M1 | Protocol, eligibility, active modules, and planned methods. | Search-design inputs. |
| M2 | Exact final search strategies and execution plan. | Production search inputs. |
| M3 | Included studies, full-text exclusions, linkages, exceptions, and counts. | Extraction corpus. |
| M4 | Extraction/appraisal evidence and synthesis classifications. | Final synthesis inputs. |
| M5 | QC-cleared manuscript and publication package. | Final approved reporting package. |

Approval must be bound to the exact subject being approved. A changed subject
requires a new approval record.

## Conditional branches

- Risk of bias may be optional when the active module and approved protocol make
  appraisal inapplicable.
- Certainty assessment may be optional for scoping, evidence-mapping, or some
  preclinical reviews.
- Structured synthesis may mean meta-analysis, another quantitative method,
  synthesis without meta-analysis, or evidence mapping. The M4 decision controls
  the branch.
- Retrieval exceptions remain reported access outcomes. They are never
  converted into scientific exclusions.

## Correction route

```text
QC finding
  -> identify the owning artifact
  -> correct that artifact
  -> use the dependency graph to mark actual consumers stale
  -> regenerate only affected outputs
  -> re-audit the corrected owner and affected consumers
  -> clear for M5 when no critical or important finding remains
```

A corrected sentence does not invalidate extraction data. A corrected study
value invalidates only analyses and claims that use that value.
