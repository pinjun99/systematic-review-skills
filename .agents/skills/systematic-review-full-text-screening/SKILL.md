---
name: systematic-review-full-text-screening
description: Decide full-text eligibility at study level with one primary AI reviewer, targeted second-AI checking, and human exception resolution. Use after retrieval to create the M3 study-selection subject. Require one decisive page-cited reason for exclusions, not quotations for every inclusion criterion.
---

# Full-Text Screening

## Workflow

1. Freeze the retrieved corpus inventory and link multiple reports to studies.
   Keep uncertain linkage as an exception.
2. Give Reviewer A the approved criteria and the minimum complete study packet.
3. Record routine inclusions as Tier 0: a structured all-criteria checklist with
   no manufactured quotations.
4. Have isolated Reviewer B check every proposed exclusion and uncertain case.
5. Accept exclusion automatically only when both reviewers agree on the same
   primary reason and one verified supporting passage with a page or equivalent locator,
   checked against the extracted report text rather than against the reviewer's
   own `verified` flag, which is self-reported. Assess no further criteria once
   decisive exclusion is established.
6. Route disagreement, poor text extraction, contradictory reports, ambiguous
   design, eligibility uncertainty, or human override for adjudication.

   The same trap as at title/abstract: `.agents/shared/v2_screening.py` accepts
   `TWO_AI_EXCLUSION_AGREEMENT` only when `a["evidence"] == b["evidence"]` **byte
   for byte**, while step 5 asks only for the same primary reason and one located
   supporting passage each. Two reviewers who exclude a report for the same reason
   while citing different pages are read as disagreeing. Fix a deterministic
   locator rule in the reviewer packet — cite the **earliest** passage in the
   report that on its own establishes the failure, by identifier rather than
   retyped text — and normalise differing locators for an identical decision and
   reason **before** the resolver, deterministically and with the discarded
   locator recorded. Leave `v2_screening.py` unmodified and log the normalisation
   as a stated deviation.
7. Serialize each reviewer with the shared `decision_record` schema, validate it with `.agents/shared/v2_runtime.py`, and create the final `screening_resolution` with `.agents/shared/v2_screening.py`.
8. Preserve reports not retrieved separately and reconcile PRISMA counts.
9. Prepare included studies, one primary reason per excluded report, retrieval
   exceptions, and resolution history as the M3 subject.

## Batching

Screen one study per call, with all of that study's linked reports together. Full
reports are long and the decision is consequential; batching studies invites a
passage from one report being cited against another. Fix this before the run and
record it. Reject and re-run a whole call rather than repairing single fields.

Project the protocol's own exclusion code set into the reviewer packet as a closed
list, with an explicit map from each eligibility criterion to the code that applies
when it fails. Reject any decision carrying a code outside the list; a reviewer that
cannot fit a listed code returns an exception rather than inventing one.

Do not reopen scientific criteria here. A criterion change requires a protocol
amendment and targeted rescreening of genuinely affected records.

When serializing shared artifacts, read [the contracts](../systematic-review/references/contracts.md); do not invent field names.

Finish `APPROVED` after M3; the next phase is data extraction.
