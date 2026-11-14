# Adding a method module

The current five module IDs are `clinical_intervention`,
`observational_association`, `ai_diagnostic_prediction`,
`preclinical_organ_bath`, and `scoping_evidence_mapping`. A module defines
eligibility fields, critical extraction fields, appraisal/certainty policy, and
permitted synthesis routes. It does not add another workflow phase or milestone.

Choose a stable module ID and update these files together:

| File | Required change |
|---|---|
| [v2-method-modules.json](../.agents/shared/references/v2-method-modules.json) | Add the module under `modules`, retaining schema `2.0`. Supply nonempty `eligibility_fields`, `critical_extraction_fields`, and `synthesis_options`, plus explicit `risk_of_bias` and `certainty` policies. |
| [v2_runtime.py](../.agents/shared/v2_runtime.py) | Add the ID to `MODULES`; otherwise `validate-config` rejects it in `active_modules`. |
| [Coordinator method guidance](../.agents/skills/systematic-review/references/method-modules.md) | Add a section explaining the module's scientific scope, required details, and limits. Keep progressive loading: read only active modules. |
| [Protocol module checklist](../.agents/skills/systematic-review-protocol/references/protocol-modules.md) | Add a row with the eligibility core and decisions to prespecify. |
| [test_v2_modules.py](../.agents/shared/tests/test_v2_modules.py) | Extend the exact portfolio assertion and add meaningful checks for the new module's critical fields and policy. Keep existing module assertions. |
| [test_v2_runtime.py](../.agents/shared/tests/test_v2_runtime.py) | Add an accepted configuration for the new ID; preserve unknown-module rejection. |
| [test_v2_skills.py](../.agents/shared/tests/test_v2_skills.py) | Extend the expected method-guidance headings to cover the new section. |
| [v2_benchmark.py](../.agents/shared/v2_benchmark.py) | Add the ID to `REQUIRED_MODULES` so benchmark validation requires its coverage. |
| [gold.json](../.agents/shared/tests/fixtures/v2/gold.json) | Add fictional cases with unique, stable IDs, expected decisions, critical fields, and applicable expert judgments. Preserve existing cases and required scenarios. |
| [test_v2_benchmark.py](../.agents/shared/tests/test_v2_benchmark.py) | Update the exact case count (currently 15) to match the expanded fixture and add checks for module-specific failure modes. Do not relax coverage or scientific error checks. |
| [README.md](../README.md), [user-manual.md](user-manual.md), and this page | Update the supported-module lists and explain when to select the new module. |

`test_v2_modules.py` currently permits these `risk_of_bias` policy strings:
`REQUIRED_WHEN_RESULTS_ARE_SYNTHESIZED`, `PROTOCOL_DECISION`, and
`NOT_REQUIRED_BY_DEFAULT`. Existing certainty policies are
`REQUIRED_FOR_IMPORTANT_EFFECT_OUTCOMES`, `PROTOCOL_DECISION`, and
`NOT_REQUIRED_BY_DEFAULT`; certainty strings are not currently enumerated by
that test. Document any new policy meaning and test it explicitly.

Appraisal and certainty stay optional unless the protocol requires them.
For scoping and preclinical reviews, do not automatically impose clinical
appraisal or GRADE. The protocol must reconcile the selected module's defaults
with the review objective: clinical intervention modules already prescribe
appraisal when results are synthesized and certainty for important effect
outcomes. A new module must not weaken those existing expectations. State any
applicable framework and justify the protocol decision before results exist.

For mixed reviews, assign fields and synthesis groups to an owning module.
Activate the new ID in the review's `review_config.json` and specify its methods
in `protocol.json`, subject to M1 approval or an approved protocol amendment.
Never select a module or synthesis method in response to significance or effect
direction. Adding fixture coverage does not establish release readiness or
replace the pending paired-model benchmark.

Keep long guidance in reference files; no `SKILL.md` edit is normally needed.
If a skill's routing or scope must change, update only that skill, preserve its
100-line limit, and run the Codex skill validator on it. Follow the Python
license-header convention and use only the standard library. Finish with:

```bash
python3 .agents/run_tests.py
```

See [CONTRIBUTING.md](../CONTRIBUTING.md) for the contribution rules and the
[CLI reference](validators.md) for configuration validation.
