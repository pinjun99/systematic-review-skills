# Workspace lifecycle commands

Owner: `.agents/shared/workspace_lifecycle.py`. Schema:
`systematic-review-workspace-1.0`.

This is the outer wrapper around a material run. It does not change any phase's
scientific logic, outputs, or locks — it records who produced what, from which
verified inputs, and whether the run actually finished.

Only a **material** run uses it: a run that produces or changes an artifact.
Advisory, read-only, or explanatory use of a skill creates no run directory and
writes nothing.

## Directory contract

```text
<review-root>/
├── review_manifest.json
├── ledger/
│   └── execution.jsonl
├── runs/
│   └── <phase-id>/
│       └── <run-id>/
│           ├── inputs_manifest.json
│           ├── outputs/
│           ├── run_manifest.json       # success only; immutable
│           └── failure_manifest.json   # failure only; immutable
├── handoffs/
│   └── <producer-run-id>/
│       └── <consumer-skill>/
│           └── <handoff-id>/
│               └── handoff_manifest.json
└── state/
    └── review_state.json               # generated view
```

`runs/<phase-id>/` and `handoffs/…` appear only when that phase actually starts
a run or publishes a handoff. Nothing pre-creates a downstream directory.

## Commands

Every command prints a JSON summary on success and exits `0`. Every refusal
writes one line to stderr and exits `2`. A refusal writes nothing except, when
failure is explicitly being recorded for an already-started run, that run's
failure manifest.

### `init-review`

```bash
python3 .agents/shared/workspace_lifecycle.py init-review \
  --root /path/to/review --review-id review-001
```

Creates `review_manifest.json`, `ledger/`, and `state/`. It creates no phase
directory. Refuses a root that already holds a review manifest.

### `start-run`

```bash
python3 .agents/shared/workspace_lifecycle.py start-run \
  --root /path/to/review \
  --phase-id phase-06 \
  --skill-id systematic-review-protocol \
  --run-id run-001 \
  --input approved-requirements=/abs/path/requirements.json \
  --parent-run-id run-000
```

`--input ROLE=PATH` hashes the file now. `--inputs-file FILE` takes a JSON array
of existing ArtifactRefs — use it to consume an upstream handoff's artifact list
unchanged. Both may be combined.

Every input is verified **before** the destination is created, so a run that
cannot trust its evidence leaves behind no directory and no ledger event. On
success it creates exactly `runs/<phase-id>/<run-id>/` and that run's
`outputs/`, writes `inputs_manifest.json`, and records `RUN_STARTED`. That start
event binds a canonical digest of the review, phase, skill, run, exact input
ArtifactRefs, parents, and consumed handoff IDs. Completion and every status
reader recompute the same digest, so editing `inputs_manifest.json` while a run
is in flight is refused before a terminal event is appended.

Any input whose validated `record_type` is a handoff manifest is verified for
**this** `--skill-id` and
**this** review before the run directory exists. A handoff addressed to another
consumer is refused here, not merely when someone chooses to run
`verify-handoff`, and `consumed_handoff_ids` is recorded from the verified
manifest rather than inferred from a filename.

A handoff belonging to another review is refused too, even if its manifest file
was renamed. A review is a closed evidence boundary: any direct input contained
inside another initialized review is refused. Raw initial evidence outside an
initialized review and direct inputs inside this same review remain valid.
Evidence produced by another review enters through `register-legacy-run`, which
records the import here.

Write the run's outputs into the `outputs_dir` reported in the summary.

### `complete-run`

```bash
python3 .agents/shared/workspace_lifecycle.py complete-run \
  --run-dir /path/to/review/runs/phase-06/run-001 \
  --output protocol-package=/abs/path/.../outputs/protocol.json \
  --status COMPLETED \
  --consumer systematic-review-search-design
```

`--status` is `COMPLETED` or `LOCKED`. `--consumer` may repeat; it records the
consumers this producer knows about, and creates nothing for them.

Refuses unless every output re-hashes correctly and lives inside this run's own
`outputs/`, and every recorded input still verifies. An upstream artifact that
changed while the run was in flight is a refusal, not a warning. Writes
`run_manifest.json` once and records `RUN_COMPLETED` or `RUN_LOCKED`.

### `fail-run`

```bash
python3 .agents/shared/workspace_lifecycle.py fail-run \
  --run-dir /path/to/review/runs/phase-06/run-001 \
  --reason-code INPUT_VERIFICATION_FAILED \
  --message "the approved export was withdrawn upstream"
```

Writes `failure_manifest.json` once and records `RUN_FAILED`. The directory and
its inputs manifest are kept: what was attempted is itself evidence.

### `inspect-run`

```bash
python3 .agents/shared/workspace_lifecycle.py inspect-run \
  --run-dir /path/to/review/runs/phase-06/run-001
```

Read-only. Re-hashes the run's artifacts and reconciles the run's directory
against the ledger, refusing if either disagrees. `--no-verify` skips both, for
diagnosing a run already known to be broken — treat its output as a description
of the directory, not a status.

### `generate-state`

```bash
python3 .agents/shared/workspace_lifecycle.py generate-state \
  --root /path/to/review
```

Rebuilds `state/review_state.json` from the verified ledger and the terminal
manifests it names, then replaces the file atomically. It is the only workspace
file that is ever rewritten, because every byte of it is derived.

There is no command that edits state by hand, and hand-editing the file has no
effect: the next generation overwrites it.

### `create-handoff`

```bash
python3 .agents/shared/workspace_lifecycle.py create-handoff \
  --root /path/to/review \
  --producer-run-id run-001 \
  --consumer-skill systematic-review-full-text-retrieval \
  --handoff-id handoff-to-phase-10 \
  --artifact approved-eligibility-contract=/abs/path/.../outputs/eligibility.json
```

Publishes a consumer-specific handoff at
`handoffs/<producer-run-id>/<consumer-skill>/<handoff-id>/`, outside the
immutable producer run. `--artifact` may repeat; `--artifacts-file` takes a JSON
array of existing ArtifactRefs.

One producer may publish to as many consumers as it likes, including distant
ones — a Phase 1 output that Phase 10 will eventually need gets its handoff now.
**It creates nothing else.** No consumer run, no consumer output directory, and
the manifest has no field in which a consumer's status could be written.

Refuses a producer that is nonterminal or failed — judged by the directory *and*
the ledger together, so a hand-written manifest cannot stand in for a run that
never happened — a producer run ID that exists in more than one phase (ambiguous, since the signature identifies a producer by
run ID alone), a handoff ID already used anywhere in the review, and any
artifact that is not an output the producer actually locked. A handoff can never
introduce evidence the producer never declared.

The producer is located by run ID, so keep run IDs unique across phases.

**Frozen export corpora.** When an existing phase contract genuinely requires a
frozen export rather than a reference, the producer records that corpus as one
already-verified output under the reserved role `frozen-export-corpus`. The
handoff then names it in `frozen_export`. Nothing is copied; there is no second
copy mechanism.

### `verify-handoff`

```bash
python3 .agents/shared/workspace_lifecycle.py verify-handoff \
  --path /path/to/review/handoffs/run-001/systematic-review-protocol/handoff-002 \
  --consumer-skill systematic-review-protocol
```

Read-only. Accepts the handoff directory or the manifest file. Confirms the
consumer identity is exact, that the manifest still sits where it says it does
(a moved or renamed handoff is refused), that the **ledger records this exact
handoff's creation** — id, producer, consumer, and `created_ledger_sequence` —
that the producer is still terminal and successful **by the reconciled
definition below**, and that every referenced artifact still hashes to what the
producer committed to.

A handoff manifest is a file a producer wrote. Copying one to a new identifier
satisfies every other check, so the ledger event is what makes it a handoff.

**Which review judges it comes from where it sits.** The review root is derived
from the handoff's own path — `<root>/handoffs/<producer-run-id>/<consumer-skill>/<handoff-id>/`
— exactly as a run's root is derived from its directory, and the producer run
manifest it names must live under that same root. A manifest outside such a tree
is not a handoff. A record never nominates the authority that checks it.

Run this before consuming a handoff. Reading one without it is trusting a
filename.

### `register-legacy-run`

```bash
python3 .agents/shared/workspace_lifecycle.py register-legacy-run \
  --root /path/to/review \
  --phase-id phase-09 \
  --skill-id systematic-review-title-abstract-screening \
  --run-id legacy-run-001 \
  --legacy-status LOCKED \
  --artifact screening-lock=/abs/path/existing/full_text_screening_lock.json
```

Registers artifacts that already exist, by reference. **The sources are never
moved, copied, or rewritten** — not one byte, not one path. The wrapper run has
no `outputs/` directory because it owns no bytes.

`--legacy-status` is `LOCKED` or `COMPLETED`: the state those artifacts were
already in. `FAILED` is refused; you do not register failed work into the chain.

A registered legacy run is a first-class producer — it can publish handoffs like
any other run.

## Migrating existing work

**Legacy registration is optional.** An existing locked artifact needs it only
when that artifact must enter the workspace-managed chain as a verifiable
producer — for example when a new run wants to consume it through a handoff.

It is also the *only* route for evidence produced outside this review, including
evidence from another review. A run may not consume another review's handoff.

Until then, do nothing. Existing phase manifests, SQLite stores, locks, and
exports keep working exactly as they are; this layer wraps and references them,
it does not replace them. There is no migration deadline, no bulk import step,
and no state in which unregistered legacy artifacts are "wrong".

Registering changes nothing about the source. It adds a wrapper run that points
at it.

One consequence worth knowing: a legacy run is the **only** kind of run allowed
to name artifacts it did not write. Shared reconciliation verifies every
declared output and enforces output ownership for every non-legacy run, so a
normal run manifest can never claim a file elsewhere in the review as its own
output.

## What is refused, and why

| Refusal | Reason |
|---|---|
| Directory exists but no terminal manifest | A folder is not a status. The run is `STARTED`. |
| Terminal manifest the ledger does not corroborate | A run is terminal only when directory and ledger agree, in identity and sequences as well as status. |
| Handoff the ledger did not record | A copied manifest is not a handoff. |
| Handoff consumed by a skill it was not addressed to | Consumer identity is bound when the run starts. |
| Run directory with no ledger entry | Orphaned. Someone made a folder by hand. |
| Ledger entry with no run directory | Orphaned. The run vanished. |
| Ledger and manifests disagree on status | Conflicting. Never silently resolved. |
| Terminal manifest already present | A terminal state is written once; a correction is a **new run**. |
| Output outside this run's `outputs/` | A run may only own what it produced. |
| Output or input hash changed | Stale evidence. |
| Reused run, handoff, phase, or artifact-role identifier | Ambiguous provenance. Case-insensitive across directories and ledger history. |
| Symlink below the review root, or a path escaping it | Path safety. |
| Tampered ledger chain | The ledger is the event authority. |

## Terminality

A run is terminal only when **both** agree: its directory carries exactly one
terminal manifest, *and* the append-only ledger records the matching terminal
event. Disagreement is refused, never resolved.

`inspect-run`, `create-handoff`, `verify-handoff`, and `generate-state` all
apply this through one shared implementation, including output hash and
ownership checks, so they cannot disagree about a verified run. Two
implementations drifted apart once: manifest-only checking let a hand-written
`run_manifest.json` publish a handoff that verified cleanly while
`generate-state` refused it.

Agreement is full identity, not status: the terminal manifest's review, phase,
run, and skill must match the inputs manifest and the ledger entry, and both
ledger sequences must match too. For revision-11 runs, the terminal ledger
event also binds a canonical digest of the complete terminal manifest assertion
(with only `terminal_ledger_sequence` bound by the event position). The shared
reconciliation recomputes that digest and verifies every success output; only a
legacy wrapper may retain an external output. New start events carry an
explicit binding-required marker. For newly started runs, the ledger's
`inputs_binding_sha256` fixes the inputs manifest's security-relevant fields at
`RUN_STARTED`, and the shared reconciliation recomputes it for nonterminal and
terminal runs. The terminal manifest's committed inputs-manifest hash is also
**recomputed**, and its `parent_run_ids` and `consumed_handoff_ids` must equal
the inputs manifest's. Historical terminal runs without the newer start binding
remain readable and report an unbound terminal assertion; an unbound historical
in-flight run may fail but may not complete. What a run read, descended from,
and consumed is fixed when the run starts; a terminal manifest restates it and
never revises it.

## Statuses

`STARTED` (nonterminal) → `COMPLETED` | `LOCKED` | `FAILED`.

Phase status is derived from its runs, with a run still in flight winning:
`STARTED` > `LOCKED` > `COMPLETED` > `FAILED`.

## Honest limits

- **Recorded identity is an assertion.** `actor_id` and `session_id` come from
  `SR_WORKSPACE_ACTOR_ID` and `SR_WORKSPACE_SESSION_ID`, or fall back to
  `SELF_ASSERTED_UNSPECIFIED` and a generated per-process session. The existing
  ledger already reports `SELF_ASSERTED_UNAUTHENTICATED` without a runtime
  anchor outside agent write scope. Nothing here authenticates anyone.
- **Recorded timestamps are assertions.** Every record carries
  `timestamp_assurance: RECORDED_ASSERTION_UNVERIFIED`.
- **A tamper-evident chain is not tamper-proof.** An agent that can write the
  ledger can rebuild it. The chain proves internal consistency only.
- **Ledger reconciliation is not authentication.** Requiring the directory and
  the ledger to agree removes accidental and one-sided forgery — a copied run
  directory, a restored backup, a session that wrote a manifest instead of
  calling `complete-run`. New runs bind both their input provenance at start
  and their complete terminal assertion at termination, so a one-sided edit
  inside a legitimately owned run directory is refused by verified readers.
  An agent that can write the workspace can still rewrite the ledger and every
  agreeing side at once, and `verify_ledger` will still say
  `SELF_ASSERTED_UNAUTHENTICATED`.
- **`required_inputs_available` is not readiness.** It reports whether every
  input ArtifactRef already recorded by that phase's runs still verifies. It
  says nothing about whether a phase's prerequisites are met — that judgment
  belongs to the phase contracts, not to this wrapper.
- **A phase absent from `review_state.json` has no runs.** It does not mean the
  phase is ready to start.
