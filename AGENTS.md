# Systematic Review Skills

This repository contains the canonical lean systematic-review skill suite.

## Working rules

- Use `systematic-review` as the coordinator and load only the active phase skill.
- Preserve stable study and report identifiers across phases.
- Keep routine evidence compact; require precise source evidence for exclusions,
  uncertainty, numerical results, and consequential claims.
- Ask for human decisions only at M1-M5 or for genuine scientific exceptions.
- Never change eligibility, synthesis methods, or interpretation in response to
  observed significance or effect direction.
- Keep internal audit language, workflow IDs, and control terminology out of
  manuscript prose unless a truthful disclosure requires them.
- Approve the manuscript structure and authorial style before major drafting.
- Treat semantic classification checks and publication-quality review as
  separate from mechanical traceability checks.
- Do not load every skill or reference file at once.
- Do not modify files for advice-only requests.

Run `python3 .agents/run_tests.py` after changing the suite and validate each
changed skill with the Codex skill validator.
