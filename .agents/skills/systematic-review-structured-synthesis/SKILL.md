---
name: systematic-review-structured-synthesis
description: Execute an M4-approved meta-analysis, other quantitative synthesis, structured synthesis without meta-analysis, or evidence map. Use the prespecified method, deterministic calculation checks, complete study accounting, and human resolution of consequential exceptions. Do not change methods in response to results.
---

# Structured Synthesis

## Workflow

1. Verify the M4-approved synthesis classification, estimand, inputs, and method.
2. Before calculating counts, test mapped classifications against the M4
   codebook, incompatible-state rules, and negative examples. Route ambiguous or
   contradictory states to humans instead of resolving them from keywords.
3. Preserve all mapped eligible results and explain any non-use.
4. Calculate quantitative results with reproducible code and independently
   verify inputs, transformations, weights, uncertainty, and direction.
5. For synthesis without meta-analysis, use a justified structured method and
   avoid significance-based vote counting or hidden pooling.
6. For evidence maps, summarize distributions and gaps without implying effects
   the included evidence cannot establish.
7. Use Tier 2 provenance for synthesis inputs and consequential findings.
8. Route calculation discrepancies, dependence problems, protocol departures,
   or interpretation uncertainty to humans.

When serializing shared artifacts, read [the contracts](../systematic-review/references/contracts.md); do not invent field names.

Finish `READY`; continue to certainty assessment only when the active module and
protocol require it, otherwise continue to reporting.
