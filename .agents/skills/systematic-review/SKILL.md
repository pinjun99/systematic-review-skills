---
name: systematic-review
description: Coordinate a complete AI-first systematic review through protocol, discovery, study selection, extraction, appraisal, synthesis, reporting, and independent QC. Use for new health, AI, observational, preclinical or organ-bath, and scoping/evidence-mapping reviews, or to resume a workspace. Use the phase skills for the active chapter; do not migrate legacy projects automatically.
---

# Systematic Review

Run one coherent review storyline. Automate routine work, preserve scientific
decisions, and ask humans only at five milestones or genuine exceptions.

## Start or resume

1. Locate `review_config.json` and the latest `phase_result.json`.
2. If neither exists, invoke `systematic-review-protocol`.
3. Validate JSON with `.agents/shared/v2_runtime.py`.
4. Read only the active method module in
   [method-modules.md](references/method-modules.md).
5. Apply module fields from `.agents/shared/references/v2-method-modules.json`.
6. Invoke only the skill for the current phase.
7. Return a short progress summary: completed phase, unresolved exceptions,
   next phase, and whether human action is required.

Do not load all phase skills or method modules at once.

## Storyline

| Chapter | Phase skill | Human milestone |
|---|---|---|
| Define | protocol | M1 protocol and eligibility |
| Discover | search design, search execution, deduplication | M2 final search |
| Select | title/abstract screening, retrieval, full-text screening | M3 study selection |
| Understand | extraction, risk of bias, synthesis planning | M4 evidence and synthesis decisions |
| Synthesize | structured synthesis, certainty when applicable | exception resolution only |
| Communicate | reporting package, independent QC | M5 publication package |

## Common rules

- Use stable study and report identifiers across every phase.
- Treat retrieval failure as an access outcome, never a scientific exclusion.
- Use Tier 0 for routine structured records, Tier 1 for decisive exclusions,
  and Tier 2 for uncertain or consequential evidence.
- Never request quotations for every criterion of a routine included study.
- Use one primary exclusion reason. Assess no further criteria once exclusion
  is established unless needed for adjudication.
- Route ambiguity, disagreement, source conflict, poor text extraction,
  protocol deviation, and consequential uncertainty to humans.
- Register local issues with `.agents/shared/v2_corrections.py` and invalidate only their actual dependents.
- Hash milestone subjects and final datasets; do not hash-bind ordinary drafts.
- Never exclude or alter methods because of effect direction or significance.
- Never claim the workflow is release-ready until the scientific and efficiency benchmark
  gates pass.

Read [contracts.md](references/contracts.md) only when creating or validating
shared JSON. Read [release-benchmark.md](references/release-benchmark.md) only when evaluating a release.

## Legacy compatibility

Keep legacy files unchanged. Import only validated scientific data through
`v2_runtime.py import-v1`; discard legacy locks, approvals, and terminal states.
Label imported provenance and route conflicts to human resolution.

Never rerun an existing review merely to adopt this workflow.

## Stop conditions

Stop with `NEEDS_HUMAN` when a scientific exception remains, a required
milestone lacks approval, an active method module is unsupported, or a source
cannot support a consequential claim. Otherwise write `READY` and name the next
phase.
