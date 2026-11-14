# Validator and utility commands

Run from the repository root with Python 3.12; no third-party packages are
needed. Start with the [minimal fictional review](../examples/minimal-review/README.md)
for runnable config/phase checks. Other filenames below are placeholders for
artifacts from your review, not bundled fixtures. Commands that write files
need writable output paths. Validation does not constitute scientific approval.

Each CLI supports `--help`; for subcommand details append `--help` after the
subcommand. `audit_policy.py` is the exception: it is an importable library.

## `v2_runtime.py`

Successful commands print indented JSON and exit 0. Invalid inputs exit nonzero
with an error. `approve` and `import-v1` also write their output path, replacing
an existing file. There is no protocol-schema validation command.

### `validate-config`

Check review identity, module allowlist, team owner, and AI policy:

```bash
python3 .agents/shared/v2_runtime.py validate-config examples/minimal-review/review_config.json
```

### `validate-decision`

Check one screening decision's IDs, checklist, reviewer, and evidence tier:

```bash
python3 .agents/shared/v2_runtime.py validate-decision decision.json
```

### `validate-phase`

Check phase/state, references, unresolved issues, and next phase:

```bash
python3 .agents/shared/v2_runtime.py validate-phase examples/minimal-review/phase_result.json
```

### `approve`

Verify an existing human approval against its exact JSON subject and write the
normalized approval. `approval.json` needs `milestone_id` (one of `M1_PROTOCOL`,
`M2_SEARCH`, `M3_SELECTION`, `M4_EVIDENCE`, `M5_PUBLICATION`), `approved_by`,
ISO-8601 `approved_at`, `assertion`, and `subject_sha256`. Compute that hash with
`v2_runtime.object_sha256` over the parsed subject, not the file's raw bytes.
The command checks the record and hash; it cannot verify human identity or
scientific adequacy.

```bash
python3 .agents/shared/v2_runtime.py approve subject.json approval.json approved.json
```

### `import-v1`

Import scientific data, discarding legacy approval state. The first argument is
one of `bibliographic_records`, `pdf_sources`, `study_report_links`,
`screening_decisions`, `exclusion_reasons`, or `extraction_dataset`. Supply the
source file's lowercase SHA-256 (64 hex characters); the CLI records the supplied
hash without comparing it to the source bytes.

```bash
python3 .agents/shared/v2_runtime.py import-v1 screening_decisions v1.json "$SOURCE_SHA256" imported.json
```

### `affected`

Print the owner and its transitive dependents, sorted. The graph maps each
artifact reference to a list of references that depend on it.

```bash
python3 .agents/shared/v2_runtime.py affected extraction.json dependency_graph.json
```

## `v2_screening.py`

No subcommands. Supply a primary AI decision record, optionally a distinct second
AI record and a human adjudication record, and a required output path. All
records must concern the same study and stage. The command prints and writes a
resolution, replacing an existing output; exit 0 can still mean `NEEDS_HUMAN`.
Inspect the returned state and route before proceeding.

```bash
python3 .agents/shared/v2_screening.py reviewer_a.json --reviewer-b reviewer_b.json --human human.json --output resolution.json
```

## `v2_corrections.py`

Both commands print JSON and write the output path, replacing an existing file.

### `register`

The input issue needs `issue_id`, `owner_ref`, `finding`, and `severity`
(`routine`, `important`, or `critical`). Register it as `OPEN`:

```bash
python3 .agents/shared/v2_corrections.py register issue.json open_issue.json
```

### `resolve`

Resolve an `OPEN` issue with a corrected artifact reference and a dependency
graph in the same format as `v2_runtime.py affected`. The output lists affected
and stale references; the command does not edit or recompute those artifacts.

```bash
python3 .agents/shared/v2_corrections.py resolve open_issue.json extraction_corrected.json dependency_graph.json resolved_issue.json
```

## `workspace_lifecycle.py`

This separate run-management interface uses workspace manifests, ledgers, and
ArtifactRefs, not the V2 `phase_result.json` state contract. Do not initialize an
existing review merely to try these commands. Success prints JSON; lifecycle
errors print to stderr and exit 2. Use a disposable `demo-workspace` below.
Artifact arguments use `ROLE=PATH`; the corresponding `--inputs-file`,
`--outputs-file`, or `--artifacts-file` takes a JSON array of ArtifactRefs.

### `init-review`

Create a new workspace manifest and ledger:

```bash
python3 .agents/shared/workspace_lifecycle.py init-review --root demo-workspace --review-id fictional-demo
```

### `start-run`

Bind existing inputs and create `runs/protocol/protocol-001/`. Repeat `--input`
for multiple inputs; repeat `--parent-run-id` for terminal parent runs.

```bash
python3 .agents/shared/workspace_lifecycle.py start-run --root demo-workspace --phase-id protocol --skill-id systematic-review-protocol --run-id protocol-001 --input config=examples/minimal-review/review_config.json
```

### `complete-run`

After the producer writes `protocol.json` inside its run’s `outputs/` directory, verify and
register it as an output. `--status` accepts `COMPLETED` (default) or `LOCKED`;
repeat `--consumer` to declare downstream skills.

```bash
python3 .agents/shared/workspace_lifecycle.py complete-run --run-dir demo-workspace/runs/protocol/protocol-001 --output protocol=demo-workspace/runs/protocol/protocol-001/outputs/protocol.json --status COMPLETED --consumer systematic-review-search-design
```

### `fail-run`

An alternative to completion for an active run, not a step after completion:

```bash
python3 .agents/shared/workspace_lifecycle.py fail-run --run-dir demo-workspace/runs/protocol/protocol-001 --reason-code MISSING_INPUT --message "Fictional demonstration input is missing"
```

### `inspect-run`

Inspect and verify a run. `--no-verify` skips verification when only inspection
is intended.

```bash
python3 .agents/shared/workspace_lifecycle.py inspect-run --run-dir demo-workspace/runs/protocol/protocol-001
```

### `generate-state`

Derive and write the current review state from registered runs and the ledger:

```bash
python3 .agents/shared/workspace_lifecycle.py generate-state --root demo-workspace
```

### `create-handoff`

Publish registered outputs of a successful producer to a named consumer:

```bash
python3 .agents/shared/workspace_lifecycle.py create-handoff --root demo-workspace --producer-run-id protocol-001 --consumer-skill systematic-review-search-design --handoff-id search-inputs --artifact protocol=demo-workspace/runs/protocol/protocol-001/outputs/protocol.json
```

### `verify-handoff`

Use the handoff manifest path returned by `create-handoff` as `HANDOFF_PATH`;
verify its consumer, ledger record, and artifacts:

```bash
python3 .agents/shared/workspace_lifecycle.py verify-handoff --path "$HANDOFF_PATH" --consumer-skill systematic-review-search-design
```

### `register-legacy-run`

Register existing legacy artifacts without rewriting them. The required
`--legacy-status` is `COMPLETED` or `LOCKED`. This records provenance; it does
not grant V2 milestone approval.

```bash
python3 .agents/shared/workspace_lifecycle.py register-legacy-run --root demo-workspace --phase-id protocol --skill-id systematic-review-protocol --run-id legacy-protocol-001 --artifact protocol=legacy/protocol.json --legacy-status COMPLETED
```

## `audit_policy.py`

No CLI or subcommands: executing this file with `--help` currently exits 0 with
no output. Import it to use `validate_policy`, `plan_audit`, and
`evaluate_two_stage`. Policy choices must already be prespecified in the
protocol. A small arithmetic example, not a review policy recommendation:

```bash
PYTHONPATH=.agents/shared python3 -c 'from audit_policy import sample_size_exact; print(sample_size_exact(100, 1, 0.05))'
```

Expected stdout: `95`. See [test_audit_policy.py](../.agents/shared/tests/test_audit_policy.py)
for complete policy and observation fixtures.

## `execution_control.py`

These utilities forecast costs and organize local results; they do not call a
model or authorize spending. Errors print to stderr and exit 2. `plan-fanout`
and `ingest` create output files and refuse to overwrite existing ones.

### `forecast`

Read actual usage from `reviewer_a.jsonl` inside the directory passed to
`--run`. Prices are per million
input/output tokens; the numbers below are illustrative, not current prices.
The optional second-reviewer fraction defaults to 0. Prints a JSON forecast and
an authorization-required notice.

```bash
python3 .agents/shared/execution_control.py forecast --run preflight-run --population 100 --input-price 1 --output-price 2 --second-reviewer-fraction 0.2
```

### `plan-fanout`

Read packet IDs (one per line or JSONL records with recognized identifiers).
Optionally supply completed IDs to skip. Concurrency defaults to 4. Writes the
plan and prints `PLANNED N packets in W waves of at most C`.

```bash
python3 .agents/shared/execution_control.py plan-fanout --packets packets.jsonl --concurrency 4 --completed completed.txt --output fanout.json
```

### `ingest`

Apply JSONL results in the plan's deterministic order. Writes the applied
results and prints `INGESTED N; outstanding M`.

```bash
python3 .agents/shared/execution_control.py ingest --plan fanout.json --results results.jsonl --output applied.json
```
