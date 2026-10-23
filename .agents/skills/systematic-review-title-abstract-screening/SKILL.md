---
name: systematic-review-title-abstract-screening
description: Screen titles and abstracts conservatively against the M1 eligibility contract. Use one primary AI reviewer for all records, a second isolated AI for proposed exclusions and uncertain cases, and humans for disagreements or ambiguity. Do not retrieve full texts or require quotations for inclusions.
---

# Title and Abstract Screening

## Workflow

1. Validate the deduplicated corpus and project the approved criterion codes
   without rewriting them.
2. Have Reviewer A classify each record as include, exclude, or uncertain.
3. Have isolated Reviewer B check every proposed exclusion and uncertain record.
4. Accept exclusion automatically only when both reviewers agree on exclusion
   and the same primary reason, the cited title/abstract span is found in that
   record's own title or abstract by exact string match, and neither reports
   ambiguity. A reviewer's own `verified` flag is self-reported and is not
   evidence that the span exists; check the span against the source text.
5. Retain routine inclusions with a Tier 0 checklist and no quotation.
6. Route disagreement, missing abstract, multiple plausible interpretations,
   or low confidence to humans. When uncertain, retain. Retention defers the
   decision to full text. Cochrane's usual route for a disagreement is
   discussion or a third reviewer. Published reviews advance a median near 8%
   of screened records to full text. If retention pushes the figure well above
   that, report the number as a stated method choice.
7. Serialize each reviewer with the shared `decision_record` schema, validate
   it with `.agents/shared/v2_runtime.py`, create the final
   `screening_resolution` with `.agents/shared/v2_screening.py`, and reconcile
   counts.

Use Tier 1 for exclusions: one primary reason plus one decisive title/abstract
span. Use Tier 2 for unresolved cases. Do not assess remaining criteria after a
decisive exclusion unless adjudication requires it.

## Evidence identity

`.agents/shared/v2_screening.py` accepts `TWO_AI_EXCLUSION_AGREEMENT` only when
`a["evidence"] == b["evidence"]` byte for byte. Step 4 asks that both reviewers
reach the same decision and the same primary reason, and that each cited span
occur in that record. The tool is stricter. Two reviewers who exclude a record
for the same reason while naming different sentences are treated as disagreeing.
In one review that mismatch was 2,619 of 8,617 records.

Before the run:

- Cite spans by identifier, never by retyped text. Require the first qualifying
  span in the record's own order: the earliest span that on its own establishes
  the failure. Do not let a reviewer pick the most detailed span.
- Where both reviewers excluded for the same primary reason but cited different
  spans, adopt the earlier span for both before calling the resolver, and
  record what was discarded. Do this outside the tool. Leave `v2_screening.py`
  unmodified and log the normalisation as a stated deviation.

## Batching and codes

Screen in batches. Do not send the whole corpus in one call, and do not spend a
call per record. Default to 20 records per batch unless the protocol sets
another size. Fix the size before the run and record it. A size chosen during
the run is not reproducible. Reject and re-run a whole batch rather than
repairing single rows, because a batch that failed once may have drifted
elsewhere.

Each decision must carry the identifier of the record it answers. Reject a
batch when an identifier does not match the record that was sent. A repair is
allowed only when the returned identifier matches no record in the corpus, has
the same length as the identifier sent, and differs in exactly one character,
so the decision cannot move to a real study. Log every repair. Never repair an
identifier of a different length.

Project the protocol's exclusion codes as a closed list, with a map from each
eligibility criterion to the code used when that criterion fails. Reject a code
outside the list. A reviewer that cannot fit a listed code returns `uncertain`
and must not invent one. If the protocol defines no code set, record the
primary reason verbatim and raise the missing code set as a protocol gap.

Before the run, withdraw codes the corpus makes impossible, such as a year,
language, or design limit already applied at search. A reviewer that sees a
plausible cue will otherwise reach for a code that cannot apply. Say in the
protocol why the corresponding PRISMA exclusion cell is empty.

Never treat a publisher boilerplate string as study metadata. A copyright line
such as `© 2013 IEEE` is not the publication year. Year, language, and document
type come from the record's indexed fields. In one review this confusion
produced 24 wrong exclusions, including a record that was a strong inclusion
candidate.

When serializing shared artifacts, read [the contracts](../systematic-review/references/contracts.md); do not invent field names.

Finish `READY`; the next phase is full-text retrieval.
