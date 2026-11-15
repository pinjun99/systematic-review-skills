# shared contracts

Read this file only when creating, importing, or validating JSON. The
deterministic source of truth is `.agents/shared/v2_runtime.py`.

## Evidence tiers

- Tier 0: structured record only. Use for routine inclusions and operational
  records. `evidence` must be empty.
- Tier 1: one decisive, verified text span. Full-text exclusions also require a
  page, section, table, figure, or paragraph locator.
- Tier 2: precise verified evidence for uncertain or consequential records.

## Core artifact shapes

`review_config` contains `schema_version`, `review_id`, `title`,
`protocol_version`, `active_modules`, `team_roles`, and `ai_policy`.

`phase_result` contains `schema_version`, `phase`, `state`, `input_refs`,
`output_refs`, `unresolved_issue_ids`, and `next_phase`.

`decision_record` contains `schema_version`, stable IDs, `stage`, `decision`,
`primary_reason_code`, `confidence`, `evidence_tier`, a compact
`eligibility_checklist`, `evidence`, and reviewer provenance.

`screening_resolution` contains the study and stage, contributing reviewer record IDs, route, state, final decision, primary reason, and final evidence. Create it with `.agents/shared/v2_screening.py`.

`milestone_approval` contains `milestone_id`, `approved_by`, `approved_at`,
`assertion`, and `subject_sha256`. Only M1–M5 are scheduled approvals.

## PRISMA renderer input

`.agents/shared/prisma_flow.py` accepts an object containing `flow_counts`,
the unchanged derived envelope returned by `assurance_chain.derive_prisma_counts`:
`schema_version`, `derived`, `counts`, `derivation`, `sources`, and
`derivation_sha256`. `assurance_chain.verify_derived_prisma` owns its verification;
a bare count dictionary is not a derived envelope.

Optional sibling fields are `records_by_source` (an array of
`{"source": "Databases", "count": 12}`) and `reports_excluded_reasons` (an array of
`{"reason": "Wrong population", "count": 2}`). Their non-negative integer counts
must sum to `records_identified` and `reports_excluded`, respectively. Use one
primary reason per excluded report.

For new reviews with other identification methods, add an optional sibling
`other_methods` object. It takes `records_by_source`, `reports_sought`,
`reports_not_retrieved`, `reports_assessed`, `reports_excluded`,
`reports_excluded_reasons`, `reports_included`, and `studies_included`.
Keep the database and register counts in the unchanged `flow_counts` envelope.
Count each included report once across the two paths, and count only additional
unique studies in `other_methods.studies_included`. The renderer checks the
other-methods arithmetic and combines the supplied inclusion totals. It cannot
deduplicate the input or verify provenance for the optional block. See the
[CLI reference](../../../../docs/validators.md#prisma_flowpy) for an example.

## Lifecycle

- `READY`: validated and may progress without a scheduled approval.
- `NEEDS_HUMAN`: blocked by a scientific exception or milestone.
- `APPROVED`: the relevant milestone subject has human approval.
- `SUPERSEDED`: retained for history but no longer current.

Formatting-only changes do not invalidate scientific approval. Scientific
changes create a new subject hash and invalidate only affected dependents.

## Commands

```bash
python .agents/shared/v2_runtime.py validate-config review_config.json
python .agents/shared/v2_runtime.py validate-decision decision.json
python .agents/shared/v2_runtime.py validate-phase phase_result.json
python .agents/shared/v2_runtime.py approve subject.json approval.json approved.json
python .agents/shared/v2_runtime.py import-v1 screening_decisions v1.json SHA256 imported.json
```
