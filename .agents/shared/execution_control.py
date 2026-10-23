"""Deterministic cost forecasting, rate control, fan-out, and resume.

Efficiency is the third priority here, behind accuracy and cost, so every
control in this module is built so that speed cannot buy itself with weaker
guarantees:

* Concurrency is bounded and never touches the immutable run configuration,
  the input hashes, or the serialized ingestion order. Workers may run in
  parallel; results are applied in a deterministic order.
* Every record is idempotent by identifier, so an interrupted run resumes by
  skipping completed work rather than redoing or duplicating it.
* Summaries are computed from the completed set, not from wall-clock arrival,
  so two runs over the same inputs produce the same summary.
* Clocks, jitter, and transports are injected. Nothing here sleeps, and nothing
  here makes a network call.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple


CONTROL_SCHEMA_VERSION = "1.0"

TERMINAL_EVENTS = {
    "PACKAGE_LOCKED",
    "PACKAGE_APPROVED",
    "CORRECTION_APPLIED",
    "AUDIT_LOCKED",
}


class ExecutionControlError(ValueError):
    """Raised when a forecast, governor, fan-out, or resume input is invalid."""


def _positive(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ExecutionControlError(f"{field} must be a positive integer")
    return value


def _non_negative_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ExecutionControlError(f"{field} must be a non-negative number")
    return float(value)


# --------------------------------------------------------------------------
# Cost forecasting
# --------------------------------------------------------------------------


def forecast_cost(
    samples: Sequence[Dict[str, Any]],
    *,
    population_size: int,
    price_per_million: Dict[str, float],
    second_reviewer_fraction: float = 0.0,
) -> Dict[str, Any]:
    """Project a full run from a fixture challenge run.

    ``samples`` are completed records carrying real token counts. The forecast
    scales their mean to the population and adds the second-reviewer share,
    which in this pipeline fires only on proposed exclusions.
    """
    population = _positive(population_size, "population_size")
    if not samples:
        raise ExecutionControlError("a forecast needs at least one sampled record")
    fraction = _non_negative_number(second_reviewer_fraction, "second_reviewer_fraction")
    if fraction > 1:
        raise ExecutionControlError("second_reviewer_fraction must be within [0, 1]")
    for key in ("input", "output"):
        _non_negative_number(price_per_million.get(key), f"price_per_million.{key}")

    totals = {"input": 0, "output": 0}
    truncated = 0
    for index, sample in enumerate(samples):
        where = f"samples[{index}]"
        if not isinstance(sample, dict):
            raise ExecutionControlError(f"{where} must be an object")
        usage = sample.get("usage")
        if not isinstance(usage, dict):
            raise ExecutionControlError(f"{where}.usage must be an object")
        totals["input"] += int(_non_negative_number(usage.get("input_tokens"), f"{where}.usage.input_tokens"))
        totals["output"] += int(_non_negative_number(usage.get("output_tokens"), f"{where}.usage.output_tokens"))
        if sample.get("truncated") is True:
            truncated += 1

    count = len(samples)
    mean_input = totals["input"] / count
    mean_output = totals["output"] / count
    reviewer_units = population * (1.0 + fraction)
    projected_input = mean_input * reviewer_units
    projected_output = mean_output * reviewer_units
    cost = (
        projected_input / 1_000_000 * price_per_million["input"]
        + projected_output / 1_000_000 * price_per_million["output"]
    )
    return {
        "schema_version": CONTROL_SCHEMA_VERSION,
        "sampled_records": count,
        "population_size": population,
        "second_reviewer_fraction": fraction,
        "reviewer_units": reviewer_units,
        "mean_input_tokens": mean_input,
        "mean_output_tokens": mean_output,
        "projected_input_tokens": projected_input,
        "projected_output_tokens": projected_output,
        "projected_cost": round(cost, 6),
        "truncated_samples": truncated,
        "truncation_rate": truncated / count,
        # A forecast from an enriched challenge set is a budgeting estimate,
        # never a performance measurement.
        "estimand_scope": "COST_FORECAST_ONLY",
        "requires_human_authorization": True,
    }


# --------------------------------------------------------------------------
# Rate control
# --------------------------------------------------------------------------


def retry_delay(
    attempt: int,
    *,
    retry_after: Optional[float] = None,
    base_delay: float = 0.75,
    jitter: float = 0.0,
    maximum: float = 60.0,
) -> float:
    """Delay before the next attempt.

    A server-supplied ``Retry-After`` always wins: guessing shorter than the
    server asked is how a fleet of workers turns one 429 into a stampede.
    Otherwise back off exponentially and add jitter so concurrent workers do
    not retry in lockstep.
    """
    number = _positive(attempt, "attempt")
    spread = _non_negative_number(jitter, "jitter")
    if spread > 1:
        raise ExecutionControlError("jitter must be within [0, 1]")
    if retry_after is not None:
        delay = _non_negative_number(retry_after, "retry_after")
    else:
        delay = _non_negative_number(base_delay, "base_delay") * (2 ** (number - 1))
    delay = min(delay, _non_negative_number(maximum, "maximum"))
    return delay * (1.0 + spread)


def deterministic_jitter(seed: str, key: str) -> float:
    """Reproducible jitter in [0, 1). Tests need repeatable timing."""
    digest = hashlib.sha256(f"{seed}\0{key}".encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") / 2**32


class RateGovernor:
    """Shared concurrency cap, request pacing, and a global retry budget.

    One governor serves every worker, so the limits are fleet-wide rather than
    per-worker. The clock is injected; this class never sleeps.
    """

    def __init__(
        self,
        *,
        max_concurrency: int,
        min_interval: float = 0.0,
        retry_budget: int,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self.max_concurrency = _positive(max_concurrency, "max_concurrency")
        self.min_interval = _non_negative_number(min_interval, "min_interval")
        self.retry_budget = _positive(retry_budget, "retry_budget")
        self._clock = clock or (lambda: 0.0)
        self._in_flight = 0
        self._last_start: Optional[float] = None
        self.retries_used = 0

    def acquire(self) -> Dict[str, Any]:
        if self._in_flight >= self.max_concurrency:
            raise ExecutionControlError(
                "concurrency cap reached; a worker must finish before another starts"
            )
        now = self._clock()
        wait = 0.0
        if self._last_start is not None:
            elapsed = now - self._last_start
            if elapsed < self.min_interval:
                wait = self.min_interval - elapsed
        self._in_flight += 1
        self._last_start = now + wait
        return {"wait": wait, "in_flight": self._in_flight}

    def release(self) -> None:
        if self._in_flight == 0:
            raise ExecutionControlError("release called with no request in flight")
        self._in_flight -= 1

    def spend_retry(self) -> int:
        """Consume one unit of the fleet-wide retry budget."""
        if self.retries_used >= self.retry_budget:
            raise ExecutionControlError(
                "global retry budget exhausted; stopping instead of hammering "
                "the endpoint"
            )
        self.retries_used += 1
        return self.retry_budget - self.retries_used

    @property
    def in_flight(self) -> int:
        return self._in_flight


# --------------------------------------------------------------------------
# Bounded fan-out and resume
# --------------------------------------------------------------------------


def plan_fanout(
    items: Sequence[str],
    *,
    completed: Iterable[str] = (),
    max_concurrency: int,
) -> Dict[str, Any]:
    """Plan bounded parallel work over the items that are not already done.

    Waves preserve the caller's ordering, so ingestion stays deterministic even
    though execution is parallel.
    """
    limit = _positive(max_concurrency, "max_concurrency")
    ordered = list(items)
    for item in ordered:
        if not isinstance(item, str) or not item.strip():
            raise ExecutionControlError("fan-out items must be non-empty strings")
    if len(set(ordered)) != len(ordered):
        raise ExecutionControlError("fan-out items contain duplicates")
    done = set(completed)
    unknown = sorted(done - set(ordered))
    if unknown:
        raise ExecutionControlError(
            "completed items are absent from the population: " + ", ".join(unknown[:5])
        )
    pending = [item for item in ordered if item not in done]
    waves = [pending[index : index + limit] for index in range(0, len(pending), limit)]
    return {
        "schema_version": CONTROL_SCHEMA_VERSION,
        "total": len(ordered),
        "already_completed": len(done),
        "pending": pending,
        "waves": waves,
        "max_concurrency": limit,
        "ingestion_order": pending,
        "serialized_ingestion": True,
    }


def apply_results(
    plan: Dict[str, Any], results: Sequence[Dict[str, Any]]
) -> Dict[str, Any]:
    """Apply worker results in the plan's deterministic ingestion order.

    Out-of-order completion is expected under concurrency and must not change
    the outcome; duplicate results for one item are idempotent.
    """
    by_item: Dict[str, Dict[str, Any]] = {}
    duplicates: List[str] = []
    for index, result in enumerate(results):
        if not isinstance(result, dict):
            raise ExecutionControlError(f"results[{index}] must be an object")
        item = result.get("item_id")
        if not isinstance(item, str) or not item.strip():
            raise ExecutionControlError(f"results[{index}].item_id must be a string")
        if item in by_item:
            if by_item[item] != result:
                raise ExecutionControlError(
                    f"conflicting duplicate result for {item}; ingestion is "
                    "idempotent only for identical records"
                )
            duplicates.append(item)
            continue
        by_item[item] = result

    unexpected = sorted(set(by_item) - set(plan["pending"]))
    if unexpected:
        raise ExecutionControlError(
            "results outside the planned work: " + ", ".join(unexpected[:5])
        )
    applied = [by_item[item] for item in plan["ingestion_order"] if item in by_item]
    missing = [item for item in plan["pending"] if item not in by_item]
    return {
        "schema_version": CONTROL_SCHEMA_VERSION,
        "applied": applied,
        "applied_count": len(applied),
        "duplicate_results_ignored": sorted(set(duplicates)),
        "outstanding": missing,
        "complete": not missing,
    }


def resume_summary(
    plan: Dict[str, Any], applied: Sequence[Dict[str, Any]]
) -> Dict[str, Any]:
    """Deterministic summary computed from the completed set.

    Depends only on which items completed, never on the order they arrived, so
    an interrupted-and-resumed run summarises identically to an uninterrupted
    one.
    """
    identifiers = sorted(
        result["item_id"] for result in applied if isinstance(result, dict)
    )
    digest = hashlib.sha256("\0".join(identifiers).encode("utf-8")).hexdigest()
    return {
        "schema_version": CONTROL_SCHEMA_VERSION,
        "total": plan["total"],
        "completed": plan["already_completed"] + len(identifiers),
        "outstanding": plan["total"] - plan["already_completed"] - len(identifiers),
        "completed_set_sha256": digest,
    }


# --------------------------------------------------------------------------
# Current state from the ledger
# --------------------------------------------------------------------------


def current_state(events: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Derive the review's current state from append-only ledger entries.

    The state is generated, never hand-maintained, so it cannot disagree with
    the record it summarises.
    """
    ordered: List[Tuple[int, Dict[str, Any]]] = []
    for index, entry in enumerate(events):
        if not isinstance(entry, dict):
            raise ExecutionControlError(f"events[{index}] must be an object")
        sequence = entry.get("sequence")
        if not isinstance(sequence, int) or isinstance(sequence, bool):
            raise ExecutionControlError(f"events[{index}].sequence must be an integer")
        event = entry.get("event")
        if not isinstance(event, dict):
            raise ExecutionControlError(f"events[{index}].event must be an object")
        ordered.append((sequence, entry))
    ordered.sort(key=lambda pair: pair[0])

    phases: Dict[str, str] = {}
    last_event: Optional[Dict[str, Any]] = None
    for _, entry in ordered:
        event = entry["event"]
        phase = event.get("phase")
        if isinstance(phase, str) and phase.strip():
            phases[phase] = event["event_type"]
        last_event = event
    completed = sorted(
        phase for phase, status in phases.items() if status in TERMINAL_EVENTS
    )
    return {
        "schema_version": CONTROL_SCHEMA_VERSION,
        "entries": len(ordered),
        "phase_status": dict(sorted(phases.items())),
        "completed_phases": completed,
        "last_event_type": last_event["event_type"] if last_event else None,
        "last_actor": last_event.get("actor_id") if last_event else None,
        "generated_from_ledger": True,
    }


# --------------------------------------------------------------------------
# Command line: forecasting and packet fan-out
# --------------------------------------------------------------------------


def load_usage_samples(run_directory: str, reviewer: str = "a") -> List[Dict[str, Any]]:
    """Read completed reviewer checkpoints from a preflight run.

    Forecasting from real checkpoints keeps one implementation of the token
    arithmetic and avoids inventing a second estimate of what a call costs.
    """
    import json

    path = Path(run_directory) / f"reviewer_{reviewer}.jsonl"
    if not path.is_file():
        raise ExecutionControlError(f"no reviewer log at {path}")
    samples: List[Dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except ValueError as exc:
            raise ExecutionControlError(f"{path} line {number} is not JSON") from exc
        usage = entry.get("usage")
        if not isinstance(usage, dict) or not usage:
            continue
        samples.append(
            {
                "usage": usage,
                "truncated": entry.get("status") == "invalid_or_failed",
            }
        )
    if not samples:
        raise ExecutionControlError(f"{path} contains no usage records")
    return samples


def _main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    forecast = commands.add_parser(
        "forecast", help="Project a full run from a completed preflight run"
    )
    forecast.add_argument("--run", required=True)
    forecast.add_argument("--population", type=int, required=True)
    forecast.add_argument("--input-price", type=float, required=True)
    forecast.add_argument("--output-price", type=float, required=True)
    forecast.add_argument("--second-reviewer-fraction", type=float, default=0.0)

    plan = commands.add_parser("plan-fanout", help="Plan bounded packet waves")
    plan.add_argument("--packets", required=True)
    plan.add_argument("--concurrency", type=int, default=4)
    plan.add_argument("--completed")
    plan.add_argument("--output", required=True)

    ingest = commands.add_parser(
        "ingest", help="Apply results in the plan's deterministic order"
    )
    ingest.add_argument("--plan", required=True)
    ingest.add_argument("--results", required=True)
    ingest.add_argument("--output", required=True)

    args = parser.parse_args(argv)
    try:
        if args.command == "forecast":
            result = forecast_cost(
                load_usage_samples(args.run),
                population_size=args.population,
                price_per_million={
                    "input": args.input_price,
                    "output": args.output_price,
                },
                second_reviewer_fraction=args.second_reviewer_fraction,
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            print(
                "AUTHORIZATION REQUIRED — this is a budget forecast, not an "
                "approval to spend.",
            )
        elif args.command == "plan-fanout":
            items = _read_ids(args.packets)
            completed = _read_ids(args.completed) if args.completed else []
            result = plan_fanout(
                items, completed=completed, max_concurrency=args.concurrency
            )
            _write_new(args.output, result)
            print(
                f"PLANNED {len(result['pending'])} packets in "
                f"{len(result['waves'])} waves of at most {args.concurrency}"
            )
        else:
            plan_value = _read_json(args.plan)
            results = _read_jsonl(args.results)
            applied = apply_results(plan_value, results)
            _write_new(args.output, applied)
            summary = resume_summary(plan_value, applied["applied"])
            print(
                f"INGESTED {applied['applied_count']}; "
                f"outstanding {summary['outstanding']}"
            )
        return 0
    except (ExecutionControlError, OSError, ValueError) as exc:
        import sys as _sys

        print(f"ERROR: {exc}", file=_sys.stderr)
        return 2


def _read_json(path: str) -> Dict[str, Any]:
    import json

    return json.loads(Path(path).read_text(encoding="utf-8"))


def _read_jsonl(path: str) -> List[Dict[str, Any]]:
    import json

    return [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _read_ids(path: str) -> List[str]:
    """Read packet identifiers from JSONL packets or a plain id list."""
    import json

    text = Path(path).read_text(encoding="utf-8")
    identifiers: List[str] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        if line.lstrip().startswith("{"):
            entry = json.loads(line)
            packet = entry.get("packet") if isinstance(entry, dict) else None
            candidate = None
            for source in (entry, packet):
                if not isinstance(source, dict):
                    continue
                for key in ("item_id", "study_id", "target_id", "record_id"):
                    if isinstance(source.get(key), str):
                        candidate = source[key]
                        break
                if candidate:
                    break
            if not candidate:
                raise ExecutionControlError(
                    f"packet line has no recognizable identifier: {line[:60]}"
                )
            identifiers.append(candidate)
        else:
            identifiers.append(line.strip())
    return identifiers


def _write_new(path: str, value: Dict[str, Any]) -> None:
    import json

    target = Path(path)
    if target.exists():
        raise ExecutionControlError(f"refusing to overwrite existing output: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    raise SystemExit(_main())
