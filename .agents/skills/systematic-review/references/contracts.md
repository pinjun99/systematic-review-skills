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
