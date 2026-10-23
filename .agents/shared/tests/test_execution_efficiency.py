#!/usr/bin/env python3
"""Cost forecasting, rate control, bounded fan-out, and resume.

Fake clocks and fixture records throughout. No test here makes a network call.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


SHARED = Path(__file__).resolve().parents[1]
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))

from approval_ledger import append_event, verify_ledger  # noqa: E402
from execution_control import (  # noqa: E402
    ExecutionControlError,
    RateGovernor,
    apply_results,
    current_state,
    deterministic_jitter,
    forecast_cost,
    plan_fanout,
    resume_summary,
    retry_delay,
)

PRICES = {"input": 1.0, "output": 4.0}


def sample(input_tokens=1000, output_tokens=200, truncated=False):
    return {
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
        "truncated": truncated,
    }


class ForecastTests(unittest.TestCase):
    def test_forecast_scales_the_sample_to_the_population(self):
        result = forecast_cost(
            [sample(), sample()], population_size=1000, price_per_million=PRICES
        )
        self.assertEqual(1000.0, result["mean_input_tokens"])
        self.assertEqual(200.0, result["mean_output_tokens"])
        self.assertEqual(1_000_000.0, result["projected_input_tokens"])
        # 1.0 (input) + 0.8 (output) = 1.8
        self.assertAlmostEqual(1.8, result["projected_cost"], places=6)

    def test_second_reviewer_share_is_added(self):
        base = forecast_cost(
            [sample()], population_size=1000, price_per_million=PRICES
        )
        with_b = forecast_cost(
            [sample()],
            population_size=1000,
            price_per_million=PRICES,
            second_reviewer_fraction=0.5,
        )
        self.assertEqual(1500.0, with_b["reviewer_units"])
        self.assertAlmostEqual(
            base["projected_cost"] * 1.5, with_b["projected_cost"], places=6
        )

    def test_truncation_rate_is_reported(self):
        result = forecast_cost(
            [sample(), sample(truncated=True)],
            population_size=10,
            price_per_million=PRICES,
        )
        self.assertEqual(1, result["truncated_samples"])
        self.assertEqual(0.5, result["truncation_rate"])

    def test_forecast_is_a_budget_estimate_not_a_measurement(self):
        result = forecast_cost(
            [sample()], population_size=10, price_per_million=PRICES
        )
        self.assertEqual("COST_FORECAST_ONLY", result["estimand_scope"])
        self.assertTrue(result["requires_human_authorization"])

    def test_an_empty_sample_cannot_forecast(self):
        with self.assertRaisesRegex(ExecutionControlError, "at least one"):
            forecast_cost([], population_size=10, price_per_million=PRICES)

    def test_forecast_is_deterministic(self):
        first = forecast_cost(
            [sample(), sample(1200, 300)],
            population_size=500,
            price_per_million=PRICES,
        )
        second = forecast_cost(
            [sample(), sample(1200, 300)],
            population_size=500,
            price_per_million=PRICES,
        )
        self.assertEqual(first, second)


class RetryTests(unittest.TestCase):
    def test_server_retry_after_wins_over_our_backoff(self):
        self.assertEqual(30.0, retry_delay(1, retry_after=30.0))
        self.assertEqual(30.0, retry_delay(5, retry_after=30.0))

    def test_backoff_is_exponential_without_a_header(self):
        self.assertEqual(0.75, retry_delay(1, base_delay=0.75))
        self.assertEqual(1.5, retry_delay(2, base_delay=0.75))
        self.assertEqual(3.0, retry_delay(3, base_delay=0.75))

    def test_delay_is_capped(self):
        self.assertEqual(60.0, retry_delay(20, base_delay=0.75))
        self.assertEqual(60.0, retry_delay(1, retry_after=900.0))

    def test_jitter_spreads_concurrent_workers(self):
        plain = retry_delay(2, base_delay=1.0)
        jittered = retry_delay(2, base_delay=1.0, jitter=0.25)
        self.assertEqual(2.0, plain)
        self.assertEqual(2.5, jittered)

    def test_deterministic_jitter_is_reproducible_and_bounded(self):
        first = deterministic_jitter("seed", "REC001")
        self.assertEqual(first, deterministic_jitter("seed", "REC001"))
        self.assertNotEqual(first, deterministic_jitter("seed", "REC002"))
        for key in ("a", "b", "c"):
            value = deterministic_jitter("seed", key)
            self.assertGreaterEqual(value, 0.0)
            self.assertLess(value, 1.0)


class GovernorTests(unittest.TestCase):
    def setUp(self):
        self.now = [0.0]
        self.governor = RateGovernor(
            max_concurrency=2,
            min_interval=0.5,
            retry_budget=3,
            clock=lambda: self.now[0],
        )

    def test_concurrency_is_capped_fleet_wide(self):
        self.governor.acquire()
        self.governor.acquire()
        self.assertEqual(2, self.governor.in_flight)
        with self.assertRaisesRegex(ExecutionControlError, "concurrency cap"):
            self.governor.acquire()
        self.governor.release()
        self.governor.acquire()

    def test_pacing_returns_a_wait_rather_than_sleeping(self):
        first = self.governor.acquire()
        self.assertEqual(0.0, first["wait"])
        second = self.governor.acquire()
        self.assertEqual(0.5, second["wait"])

    def test_pacing_clears_once_the_interval_has_passed(self):
        self.governor.acquire()
        self.governor.release()
        self.now[0] = 10.0
        self.assertEqual(0.0, self.governor.acquire()["wait"])

    def test_retry_budget_is_global_and_finite(self):
        self.assertEqual(2, self.governor.spend_retry())
        self.assertEqual(1, self.governor.spend_retry())
        self.assertEqual(0, self.governor.spend_retry())
        with self.assertRaisesRegex(ExecutionControlError, "retry budget exhausted"):
            self.governor.spend_retry()

    def test_release_without_a_request_is_refused(self):
        with self.assertRaisesRegex(ExecutionControlError, "no request in flight"):
            self.governor.release()


class FanoutAndResumeTests(unittest.TestCase):
    def setUp(self):
        self.items = [f"REC{index:03d}" for index in range(7)]

    def test_waves_respect_the_concurrency_cap_and_input_order(self):
        plan = plan_fanout(self.items, max_concurrency=3)
        self.assertEqual([3, 3, 1], [len(wave) for wave in plan["waves"]])
        self.assertEqual(self.items, plan["ingestion_order"])
        self.assertTrue(plan["serialized_ingestion"])

    def test_resume_skips_completed_work(self):
        plan = plan_fanout(
            self.items, completed=self.items[:4], max_concurrency=3
        )
        self.assertEqual(4, plan["already_completed"])
        self.assertEqual(self.items[4:], plan["pending"])

    def test_out_of_order_completion_does_not_change_ingestion(self):
        plan = plan_fanout(self.items, max_concurrency=3)
        results = [{"item_id": item, "decision": "retain"} for item in self.items]
        forward = apply_results(plan, results)
        backward = apply_results(plan, list(reversed(results)))
        self.assertEqual(forward["applied"], backward["applied"])
        self.assertTrue(forward["complete"])

    def test_identical_duplicate_results_are_idempotent(self):
        plan = plan_fanout(self.items, max_concurrency=3)
        results = [{"item_id": item, "decision": "retain"} for item in self.items]
        outcome = apply_results(plan, results + [results[0]])
        self.assertEqual(["REC000"], outcome["duplicate_results_ignored"])
        self.assertEqual(len(self.items), outcome["applied_count"])

    def test_conflicting_duplicate_results_are_refused(self):
        plan = plan_fanout(self.items, max_concurrency=3)
        results = [{"item_id": "REC000", "decision": "retain"}]
        with self.assertRaisesRegex(ExecutionControlError, "conflicting duplicate"):
            apply_results(plan, results + [{"item_id": "REC000", "decision": "exclude"}])

    def test_results_outside_the_plan_are_refused(self):
        plan = plan_fanout(self.items, max_concurrency=3)
        with self.assertRaisesRegex(ExecutionControlError, "outside the planned work"):
            apply_results(plan, [{"item_id": "UNPLANNED", "decision": "retain"}])

    def test_an_interrupted_run_summarises_like_an_uninterrupted_one(self):
        whole = plan_fanout(self.items, max_concurrency=3)
        all_results = [{"item_id": item, "decision": "retain"} for item in self.items]
        complete = resume_summary(whole, apply_results(whole, all_results)["applied"])

        first_half = plan_fanout(self.items, max_concurrency=3)
        partial = apply_results(first_half, all_results[:4])
        self.assertFalse(partial["complete"])
        resumed_plan = plan_fanout(
            self.items, completed=self.items[:4], max_concurrency=3
        )
        resumed = apply_results(resumed_plan, all_results[4:])
        summary = resume_summary(resumed_plan, resumed["applied"])

        self.assertEqual(complete["completed"], summary["completed"])
        self.assertEqual(0, summary["outstanding"])

    def test_completed_items_must_belong_to_the_population(self):
        with self.assertRaisesRegex(ExecutionControlError, "absent from the population"):
            plan_fanout(self.items, completed=["GHOST"], max_concurrency=3)

    def test_duplicate_items_are_refused(self):
        with self.assertRaisesRegex(ExecutionControlError, "duplicates"):
            plan_fanout(["A", "A"], max_concurrency=2)


class CurrentStateTests(unittest.TestCase):
    def setUp(self):
        import tempfile

        self._temp = tempfile.TemporaryDirectory()
        self.ledger = Path(self._temp.name) / "execution.jsonl"

    def tearDown(self):
        self._temp.cleanup()

    def record(self, phase, event_type):
        append_event(
            str(self.ledger),
            {
                "event_type": event_type,
                "actor_id": "Human approver",
                "session_id": "APPROVER-1",
                "recorded_at": "2026-07-30T12:00:00+08:00",
                "phase": phase,
            },
        )

    def entries(self):
        import json

        return [
            json.loads(line)
            for line in self.ledger.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def test_state_is_generated_from_ledger_events(self):
        self.record("PHASE_9", "PACKAGE_LOCKED")
        self.record("PHASE_10", "AUDIT_STARTED")
        state = current_state(self.entries())
        self.assertTrue(state["generated_from_ledger"])
        self.assertEqual(["PHASE_9"], state["completed_phases"])
        self.assertEqual("AUDIT_STARTED", state["last_event_type"])
        self.assertTrue(verify_ledger(str(self.ledger))["chain_intact"])

    def test_a_later_event_supersedes_an_earlier_one_for_the_same_phase(self):
        self.record("PHASE_10", "AUDIT_STARTED")
        self.record("PHASE_10", "PACKAGE_LOCKED")
        state = current_state(self.entries())
        self.assertEqual(["PHASE_10"], state["completed_phases"])

    def test_state_is_order_independent(self):
        self.record("PHASE_9", "PACKAGE_LOCKED")
        self.record("PHASE_10", "PACKAGE_LOCKED")
        entries = self.entries()
        self.assertEqual(current_state(entries), current_state(list(reversed(entries))))


class CommandLineTests(unittest.TestCase):
    """The CLI is the only path that reaches real runs, so it is exercised."""

    def setUp(self):
        import tempfile

        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)

    def tearDown(self):
        self._temp.cleanup()

    def run_cli(self, *arguments):
        import subprocess

        return subprocess.run(
            [sys.executable, str(SHARED / "execution_control.py"), *arguments],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_forecast_reads_a_real_reviewer_log(self):
        import json

        run = self.root / "run-v1"
        run.mkdir()
        (run / "reviewer_a.jsonl").write_text(
            "\n".join(
                json.dumps(
                    {
                        "record_id": f"REC{index}",
                        "usage": {"input_tokens": 1000, "output_tokens": 200},
                    }
                )
                for index in range(4)
            )
            + "\n",
            encoding="utf-8",
        )
        result = self.run_cli(
            "forecast",
            "--run", str(run),
            "--population", "1000",
            "--input-price", "1.0",
            "--output-price", "4.0",
        )
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout.split("AUTHORIZATION")[0])
        self.assertEqual(4, payload["sampled_records"])
        self.assertAlmostEqual(1.8, payload["projected_cost"], places=6)
        self.assertIn("AUTHORIZATION REQUIRED", result.stdout)

    def test_forecast_refuses_a_log_without_usage(self):
        run = self.root / "run-v2"
        run.mkdir()
        (run / "reviewer_a.jsonl").write_text('{"record_id": "REC0"}\n', encoding="utf-8")
        result = self.run_cli(
            "forecast",
            "--run", str(run),
            "--population", "10",
            "--input-price", "1.0",
            "--output-price", "4.0",
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("no usage records", result.stderr)

    def test_packet_fanout_plans_and_ingests_deterministically(self):
        import json

        packets = self.root / "packets.jsonl"
        packets.write_text(
            "\n".join(
                json.dumps({"packet": {"study_id": f"S{index:03d}"}})
                for index in range(5)
            )
            + "\n",
            encoding="utf-8",
        )
        plan_path = self.root / "plan.json"
        planned = self.run_cli(
            "plan-fanout",
            "--packets", str(packets),
            "--concurrency", "2",
            "--output", str(plan_path),
        )
        self.assertEqual(0, planned.returncode, planned.stderr)
        self.assertIn("3 waves", planned.stdout)

        results = self.root / "results.jsonl"
        results.write_text(
            "\n".join(
                json.dumps({"item_id": f"S{index:03d}", "decision": "include"})
                for index in reversed(range(5))
            )
            + "\n",
            encoding="utf-8",
        )
        applied_path = self.root / "applied.json"
        ingested = self.run_cli(
            "ingest",
            "--plan", str(plan_path),
            "--results", str(results),
            "--output", str(applied_path),
        )
        self.assertEqual(0, ingested.returncode, ingested.stderr)
        applied = json.loads(applied_path.read_text(encoding="utf-8"))
        # Results arrived reversed; ingestion order follows the plan.
        self.assertEqual(
            [f"S{index:03d}" for index in range(5)],
            [row["item_id"] for row in applied["applied"]],
        )
        self.assertTrue(applied["complete"])

    def test_plan_refuses_to_overwrite_an_existing_output(self):
        packets = self.root / "packets.jsonl"
        packets.write_text("S001\n", encoding="utf-8")
        target = self.root / "plan.json"
        target.write_text("{}", encoding="utf-8")
        result = self.run_cli(
            "plan-fanout",
            "--packets", str(packets),
            "--output", str(target),
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("refusing to overwrite", result.stderr)


if __name__ == "__main__":
    unittest.main()
