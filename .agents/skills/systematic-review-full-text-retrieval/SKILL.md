---
name: systematic-review-full-text-retrieval
description: Retrieve exact full-text reports for screening using lawful open access or the user's existing access, verify file identity, and record retrieval exceptions. Use after title/abstract screening. Do not make eligibility decisions or treat inaccessible reports as exclusions.
---

# Full-Text Retrieval

## Workflow

1. Create a retrieval record for every sought report with stable report and
   study-linkage candidates.
2. Search DOI and official publisher or repository sources; use the user's
   existing institutional access only through authorised actions.
3. Verify title, authors, year, DOI, document type, completeness, and file
   readability. Preserve the exact acquired file and source URL.
4. Record each outcome as retrieved, wrong document, duplicate report, or not
   retrieved with attempts and access reason.
5. OCR only defective pages and retain original PDFs.
6. Extract machine-readable text for every retrieved report and store it beside
   the preserved file under the same report identifier. Downstream phases cite
   passages against this extracted text, so a report held only as an unextracted
   PDF cannot have its citations checked. Record extraction failure as a
   retrieval exception.
7. Reconcile reports sought, retrieved, and not retrieved.

Retrieval exceptions are reportable access outcomes. They do not block the
remaining corpus from progressing and never become scientific exclusions.

When serializing shared artifacts, read [the contracts](../systematic-review/references/contracts.md); do not invent field names.

Finish `READY` with explicit retrieval exceptions; the next phase is full-text
screening.
