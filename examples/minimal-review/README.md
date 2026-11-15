# Minimal fictional review

This is a draft scoping review for learning the file contracts, with one invented
study and report. It contains no real evidence or approval. Paths in the phase
result are relative to this example directory. `NEEDS_HUMAN` means M1 approval
is still needed; `next_phase` names the planned step, not permission to start it.

Run these commands from the repository root with Python 3.12:

```bash
python3 .agents/shared/v2_runtime.py validate-config examples/minimal-review/review_config.json
```

Expected stdout (exit status 0):

```json
{
  "schema_version": "2.0",
  "review_id": "fictional-token-map",
  "title": "Fictional classroom token-sorting studies: an evidence map",
  "protocol_version": "1.0",
  "active_modules": [
    "scoping_evidence_mapping"
  ],
  "team_roles": {
    "owner": "Fictional Reviewer"
  },
  "ai_policy": {
    "posture": "AI_FIRST_RISK_BASED",
    "paid_api_authorized": false
  }
}
```

```bash
python3 .agents/shared/v2_runtime.py validate-phase examples/minimal-review/phase_result.json
```

Expected stdout (exit status 0):

```json
{
  "schema_version": "2.0",
  "phase": "protocol",
  "state": "NEEDS_HUMAN",
  "input_refs": [
    "review_config.json"
  ],
  "output_refs": [
    "protocol.json"
  ],
  "unresolved_issue_ids": [],
  "next_phase": "search_design"
}
```

```bash
python3 -m json.tool examples/minimal-review/protocol.json > /dev/null
```

Expected: no output, exit status 0. This checks JSON syntax only. The runtime
has **no protocol-schema validator** or `validate-protocol` subcommand.
`protocol.json` illustrates scientific content for human review; the runtime
can accept it as the JSON subject of `approve`, which checks the approval's
canonical subject hash, not the protocol's methods. The regression test checks
that path with a temporary, explicitly fictional approval. It does not approve
this example or write an approval into the repository.

For a real review, replace the invented content, complete the protocol with the
protocol skill, and obtain M1 approval before search design. See the
[user manual](../../docs/user-manual.md) and [CLI reference](../../docs/validators.md).

## Fictional PRISMA figure

`prisma_flow_counts.json` illustrates a possible flow ending in the single
invented study and report. It is a renderer fixture, not progress or approval
for this draft protocol. Its derived envelope and derivation rows are a
synthetic snapshot with an empty `sources` list so the example is portable;
it does not verify upstream review files. Real reviews must retain the
source-backed output of `derive_prisma_counts` unchanged.

From the repository root (Python 3.10+):

```bash
python3 .agents/shared/prisma_flow.py examples/minimal-review/prisma_flow_counts.json --format svg --output /tmp/fictional-prisma.svg
python3 .agents/shared/prisma_flow.py examples/minimal-review/prisma_flow_counts.json --format mermaid
python3 .agents/shared/prisma_flow.py examples/minimal-review/prisma_flow_counts.json --format text
```

Expected: exit 0; the first command writes the standalone SVG without stdout,
and the others print a flowchart or summary with 12 records identified,
10 screened, 4 reports sought, 3 assessed, and 1 included study/report.
Place the Mermaid output inside a `mermaid` fenced code block for GitHub.
