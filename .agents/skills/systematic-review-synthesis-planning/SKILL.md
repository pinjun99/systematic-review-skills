---
name: systematic-review-synthesis-planning
description: Confirm the prespecified synthesis plan against the included evidence, classify each synthesis group, document justified amendments, and prepare the M4 evidence-and-synthesis approval subject. Use after extraction and any applicable appraisal. Do not select methods because of observed significance or effect direction.
---

# Synthesis Planning

## Workflow

1. Map every included result to the protocol's outcome or evidence-map IDs.
2. Validate completeness, compatible estimands, units, time points, designs,
   multiplicity, and independence.
3. Apply prespecified rules to classify each group for meta-analysis, other
   quantitative synthesis, structured synthesis, evidence mapping, or no
   synthesis.
4. For each nontrivial classification, define a concise codebook with the
   inclusion rule, exclusion rule, a negative example, and incompatible states.
   Resolve ambiguous mappings from source evidence rather than keyword matches,
   and validate invariants such as `not reported != no harm observed` before M4.
5. Amend the plan only for an evidence property that could not reasonably have
   been specified earlier. Record rationale, date, decision maker, and whether
   results were visible.
6. Combine the final extraction dataset, appraisal results when applicable,
   synthesis classifications, unresolved limitations, and amendments into the
   M4 subject.
7. Obtain human approval of M4 before calculating final synthesis results.

Do not recreate the protocol synthesis plan or relock unaffected upstream data.

When serializing shared artifacts, read [the contracts](../systematic-review/references/contracts.md); do not invent field names.

Finish `APPROVED` after M4; the next phase is structured synthesis or the
prespecified quantitative branch.
