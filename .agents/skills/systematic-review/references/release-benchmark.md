# Release benchmark

Use `.agents/shared/v2_benchmark.py` with identical gold fixtures, model,
settings, and execution environment for the legacy and current workflows.

Do not promote the workflow when model-run measurements are missing. The static legacy
baseline is recorded in `.agents/shared/references/v2-baseline.json`; its
pending status is intentionally release-blocking.

The scientific gate requires no false exclusion, no critical error, at least
95% primary-reason agreement, 100% critical-field and evidence fidelity, and
expert-judgment agreement no lower than the legacy workflow. The efficiency gate applies the
thresholds encoded in `v2_benchmark.py`.

Any disagreement affecting inclusion, a primary outcome, or a conclusion must
receive blinded expert adjudication before promotion.
