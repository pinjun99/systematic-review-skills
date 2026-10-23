---
name: systematic-review-deduplication
description: Deduplicate search records while preserving every source record, provenance, and stable report identifier. Use after search execution and before screening. Do not delete evidence or merge records when identity remains ambiguous.
---

# Deduplication

## Workflow

1. Validate raw-source counts and assign immutable source-record IDs.
2. Normalize identifiers and citation fields without overwriting raw values.
3. Match exact DOI, database IDs, and other strong identifiers first; then use
   conservative bibliographic similarity for candidates.
4. Preserve duplicate groups and choose one screening representative. Keep all
   source provenance and alternate metadata.
5. Route conflicting identifiers and uncertain matches to humans.
6. Export unique screening records, duplicate groups, and count reconciliation.

Use Tier 0 records for routine duplicate decisions. Record a short rationale for
ambiguous human resolutions; page-cited evidence is irrelevant here.

When serializing shared artifacts, read [the contracts](../systematic-review/references/contracts.md); do not invent field names.

Finish `READY`; the next phase is title/abstract screening.
