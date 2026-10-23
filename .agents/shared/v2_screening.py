#!/usr/bin/env python3
"""Resolve V2 screening reviewer records conservatively and reproducibly."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from v2_runtime import SCHEMA_VERSION, V2ContractError, validate_decision_record


def resolve_screening(
    reviewer_a: Any, reviewer_b: Any | None = None, human: Any | None = None
) -> dict[str, Any]:
    a = validate_decision_record(reviewer_a)
    b = validate_decision_record(reviewer_b) if reviewer_b is not None else None
    h = validate_decision_record(human) if human is not None else None
    records = [record for record in (a, b, h) if record is not None]
    if any(record["study_id"] != a["study_id"] for record in records):
        raise V2ContractError("screening reviewers refer to different studies")
    if any(record["stage"] != a["stage"] for record in records):
        raise V2ContractError("screening reviewers refer to different stages")
    reviewer_ids = [record["reviewer"]["id"] for record in records]
    if len(reviewer_ids) != len(set(reviewer_ids)):
        raise V2ContractError("screening reviewer IDs must be distinct")

    if a["reviewer"]["type"] != "ai" or (b is not None and b["reviewer"]["type"] != "ai"):
        raise V2ContractError("Reviewer A and Reviewer B must be AI records")

    base = {
        "schema_version": SCHEMA_VERSION,
        "study_id": a["study_id"],
        "stage": a["stage"],
        "reviewer_record_ids": [record["record_id"] for record in records],
    }
    if h is not None:
        if h["reviewer"]["type"] != "human":
            raise V2ContractError("the adjudication record must be human")
        if h["decision"] == "uncertain":
            return {
                **base, "state": "NEEDS_HUMAN", "route": "HUMAN_UNRESOLVED",
                "final_decision": None, "primary_reason_code": None, "evidence": h["evidence"],
            }
        return {
            **base, "state": "READY", "route": "HUMAN_ADJUDICATION",
            "final_decision": h["decision"],
            "primary_reason_code": h.get("primary_reason_code"),
            "evidence": h["evidence"],
        }

    if a["decision"] == "include" and b is None:
        return {
            **base, "state": "READY", "route": "ROUTINE_AI_INCLUSION",
            "final_decision": "include", "primary_reason_code": None,
            "evidence": [],
        }
    if b is None:
        return {
            **base, "state": "NEEDS_HUMAN", "route": "SECOND_AI_REQUIRED",
            "final_decision": None, "primary_reason_code": None,
            "evidence": [],
        }
    if (
        a["decision"] == b["decision"] == "exclude"
        and a["primary_reason_code"] == b["primary_reason_code"]
        and a["evidence"] == b["evidence"]
    ):
        return {
            **base, "state": "READY", "route": "TWO_AI_EXCLUSION_AGREEMENT",
            "final_decision": "exclude",
            "primary_reason_code": a["primary_reason_code"],
            "evidence": a["evidence"],
        }
    return {
        **base, "state": "NEEDS_HUMAN", "route": "REVIEWER_DISAGREEMENT",
        "final_decision": None, "primary_reason_code": None, "evidence": [],
    }


def load(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reviewer_a")
    parser.add_argument("--reviewer-b")
    parser.add_argument("--human")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = resolve_screening(
        load(args.reviewer_a),
        load(args.reviewer_b) if args.reviewer_b else None,
        load(args.human) if args.human else None,
    )
    rendered = json.dumps(result, indent=2) + "\n"
    Path(args.output).write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
