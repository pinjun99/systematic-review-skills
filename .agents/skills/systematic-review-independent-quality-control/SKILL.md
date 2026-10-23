---
name: systematic-review-independent-quality-control
description: Independently audit a reporting candidate using a fresh context, exhaustive high-consequence checks, reproducible sampling of routine content, and local correction routing. Use before M5 publication approval or to recheck affected outputs after corrections. Do not edit scientific source artifacts directly.
---

# Independent Quality Control

## Workflow

1. Use a fresh auditor context and verify the candidate package identity.
2. Check every published number, primary outcome, conclusion, certainty
   statement, protocol deviation, PRISMA count, and consequential interpretation.
3. Verify their source or claim-ledger links and inspect a reproducible,
   result-blind sample of routine claims and citations.
4. Check consistency across manuscript, tables, figures, supplements, abstract,
   and declarations.
5. Run a publication-quality pass for internal audit-language leakage,
   contradictory eligibility or Methods statements, finding-led section logic,
   unnecessarily negative framing, and consistency with the selected authorial
   style. Treat this as separate from scientific traceability.
6. Register each finding against its owning record with severity and affected
   claim IDs using `.agents/shared/v2_corrections.py`. Do not prescribe a phase-wide rerun.
7. After correction, use the dependency graph to re-audit the corrected owner
   and actual downstream dependents only.
8. Report unresolved findings as `NEEDS_HUMAN`; otherwise clear the package for
   M5 approval.

A corrected reporting sentence does not invalidate extraction data. A corrected
study value invalidates only analyses and claims that consume that value.
Technical reconciliation alone does not clear a candidate; both scientific and
publication-quality checks must pass.

When serializing shared artifacts, read [the contracts](../systematic-review/references/contracts.md); do not invent field names.

Finish `READY` for M5 approval when no critical or important finding remains.
