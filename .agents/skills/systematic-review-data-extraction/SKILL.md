---
name: systematic-review-data-extraction
description: Extract study, method, intervention or exposure, outcome, and result data from the M3 included corpus. Use primary AI extraction, deterministic validation, isolated second-AI checking of critical or suspicious fields, fresh strongest-model lead-agent adjudication of evidence-resolvable exceptions, and human escalation only for consequential unresolved judgment. Do not require page quotations for every descriptive field.
---

# Data Extraction

## Workflow

1. Build the form from the M1 protocol and active method modules; pilot it on a
   varied sample before production extraction.
2. Link every value to stable study, report, outcome, time point, and analysis
   identifiers. Preserve raw wording and normalized value separately.
3. Have one AI extract all fields. Run deterministic checks for type, range,
   units, denominators, totals, internal arithmetic, and duplicate outcomes.
4. Use Tier 2 source locations for numerical results, outcome definitions,
   critical design details, and fields that drive appraisal or synthesis.
5. Send critical fields and suspicious records to an isolated second AI.
6. Send disagreements and exceptions to a fresh lead-agent adjudication context
   using the strongest approved reasoning model available, preferring Sol when it
   is the current top-tier option. Give it the source packet, both frozen AI
   records, validation findings, and approved charting rules. Record the exact
   lead model and version plus immutable references to every adjudication input.
7. Allow the lead agent to resolve an evidence-resolvable exception only when an
   approved rule supports retaining reported contradictions or values verbatim,
   keeping alternatives visible, using `null`, or marking a result indeterminate.
   Record its rationale, source locations, and disposition. Never silently
   correct, normalize, infer, or choose between incompatible statements. Never
   represent the lead agent as a human reviewer or human approval.
8. Escalate only genuinely consequential unresolved judgment to humans: a new
   scientific or charting policy, a choice between plausible incompatible
   interpretations, an override of approved criteria, insufficient source
   evidence, or a choice that materially affects appraisal or synthesis. Require
   human approval for new reusable charting rules and the final audit or dataset
   lock.
9. Sample routine descriptive fields for human audit and reconcile all included
   studies and prespecified outcomes.

## Batching

Extract one study per call, with all of that study's linked reports together.
A form carries many fields per study; batching studies is how a value from one
study is written into another's row. Fix this before production extraction and
record it. Reject and re-run a whole call rather than repairing single fields.

Require every extracted record to carry the identifier of the study it belongs
to, and reject any output whose identifier does not match the study that was
sent.

`not_reported` requires a documented targeted search of the available report,
not an exhaustive quotation trail. Derived values must retain formula and
inputs.

When serializing shared artifacts, read [the contracts](../systematic-review/references/contracts.md); do not invent field names.

Finish `READY`; the next applicable phase is risk of bias or synthesis planning.
