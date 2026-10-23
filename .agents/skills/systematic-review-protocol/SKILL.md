---
name: systematic-review-protocol
description: Create or amend a systematic-review protocol, review configuration, eligibility criteria, method-module selection, synthesis plan, and M1 approval subject. Use at the start of a new review or when a scientific protocol amendment is required. Do not execute searches or screen records.
---

# Protocol

Define the scientific contract once so downstream skills do not reinterpret it.

## Workflow

1. Translate the question into explicit objectives and select the smallest set
   of applicable method modules.
2. Define inclusion and exclusion criteria in operational language. Give each
   criterion a stable code and precedence order for primary exclusion reasons.
3. Prespecify information sources, outcomes or mapping fields, appraisal
   approach when applicable, synthesis groups, effect measures, subgroup rules,
   missing-data handling, and protocol-amendment policy.
4. Record authorship, conflicts, funding, registration intent, and AI-use policy.
5. Create `review_config.json`, `protocol.json`, and the planned extraction,
   appraisal, and synthesis field sets. Keep them in one M1 approval subject.
6. Validate `review_config.json` with `.agents/shared/v2_runtime.py`.
7. Present a readable protocol summary and obtain M1 human approval.

Read [protocol-modules.md](references/protocol-modules.md) and apply the matching entry in `.agents/shared/references/v2-method-modules.json` only for the active module. Use the shared contracts referenced by `systematic-review`; do not
copy lifecycle instructions into this skill.

## Scientific boundaries

- Do not promise unsupported review methods.
- Make appraisal and certainty optional for scoping or preclinical reviews
  unless justified by their objectives.
- Prespecify synthesis before results are known; later changes require a dated,
  reasoned amendment that discloses whether results were visible.
- Treat eligibility changes after screening begins as consequential amendments.

## Completion

When serializing shared artifacts, read [the contracts](../systematic-review/references/contracts.md); do not invent field names.

Finish `APPROVED` only after M1 binds the protocol subject. Otherwise finish
`NEEDS_HUMAN`. The next phase is search design.
