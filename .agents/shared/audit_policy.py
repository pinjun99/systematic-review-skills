"""Prespecified finite-population audit policy for screening exclusions.

Design commitments, all of which follow from one fact: false exclusions live
only among the exclusions, and there are usually very few of them.

* Exact hypergeometric arithmetic throughout. The rule of three is an
  infinite-population approximation and is wrong when the sample approaches the
  population, which is exactly where an affordable audit sits.
* Tolerance is stated as ``first_unacceptable_missed_records``. Ruling out "K
  or more" supports a claim of at most ``K - 1``; the two are recorded
  separately so the off-by-one cannot be lost in prose.
* High-risk strata are audited exhaustively as a census; the remainder gets a
  seeded probability sample. Only the remainder carries an inference, and the
  two are never merged into one unweighted rate.
* Two stages with prespecified alpha allocation. Expansion draws the next
  entries from one frozen permutation, so nothing can be added selectively
  after an error is seen.
* Sizing is a function of the realized population. The protocol locks the
  function; the later phase evaluates it. No new scientific decision downstream.
* A detection sample is not an error-rate estimate, and an enriched challenge
  set is not a production performance measure. Both say so in their output.
"""

from __future__ import annotations

from fractions import Fraction
import hashlib
from typing import Any, Dict, Iterable, List, Optional, Sequence


POLICY_SCHEMA_VERSION = "1.0"

ENRICHED_SCOPE = "ENRICHED_CHALLENGE_SET_ONLY"
DETECTION_SCOPE = "DETECTION_ONLY"
PROBABILITY_SCOPE = "PROBABILITY_SAMPLE_REMAINDER_ONLY"

VERDICT_CORRECT = "CORRECT"
VERDICT_FALSE_EXCLUSION = "FALSE_EXCLUSION"
VERDICT_UNCERTAIN = "UNCERTAIN"
VERDICTS = (VERDICT_CORRECT, VERDICT_FALSE_EXCLUSION, VERDICT_UNCERTAIN)

ROLE_CENSUS = "CENSUS"
ROLE_SAMPLE = "SAMPLE"
ROLES = (ROLE_CENSUS, ROLE_SAMPLE)

OUTCOME_ACCEPT = "ACCEPT_AUTOMATION"
OUTCOME_EXPAND = "EXPAND_TO_STAGE_2"
OUTCOME_DISABLE = "DISABLE_AUTOMATION_FULL_HUMAN_REASSESSMENT"


class AuditPolicyError(ValueError):
    """Raised when a policy, sample, or observation set is invalid."""


def _integer(value: Any, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise AuditPolicyError(f"{field} must be an integer >= {minimum}")
    return value


def _alpha(value: Any, field: str) -> Fraction:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AuditPolicyError(f"{field} must be a number")
    fraction = Fraction(str(value))
    if not 0 < fraction < 1:
        raise AuditPolicyError(f"{field} must lie strictly between 0 and 1")
    return fraction


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AuditPolicyError(f"{field} must be a non-empty string")
    return value


# --------------------------------------------------------------------------
# Exact hypergeometric arithmetic
# --------------------------------------------------------------------------


def _binomial(n: int, k: int) -> int:
    if k < 0 or k > n or n < 0:
        return 0
    result = 1
    for index in range(k):
        result = result * (n - index) // (index + 1)
    return result


def probability_zero_found(N: int, K: int, n: int) -> Fraction:
    """P(no bad item in the sample | exactly K bad items in the population).

    ``C(N - K, n) / C(N, n)``, expanded as a product so it stays exact.
    """
    _integer(N, "N")
    _integer(K, "K")
    _integer(n, "n")
    if n > N:
        raise AuditPolicyError("sample size cannot exceed the population")
    if K > N:
        raise AuditPolicyError("bad-item count cannot exceed the population")
    if K == 0:
        return Fraction(1)
    if n > N - K:
        return Fraction(0)
    probability = Fraction(1)
    for index in range(K):
        probability *= Fraction(N - n - index, N - index)
    return probability


def probability_at_most(N: int, K: int, n: int, k: int) -> Fraction:
    """P(X <= k | N, K, n) for the hypergeometric distribution, exactly."""
    _integer(k, "k")
    if k >= min(K, n):
        return Fraction(1)
    denominator = _binomial(N, n)
    if denominator == 0:
        raise AuditPolicyError("invalid hypergeometric parameters")
    total = Fraction(0)
    for observed in range(k + 1):
        total += Fraction(
            _binomial(K, observed) * _binomial(N - K, n - observed), denominator
        )
    return total


def sample_size_exact(N: int, first_unacceptable: int, alpha: float) -> int:
    """Smallest zero-error sample that rules out ``first_unacceptable`` bad items.

    Observing no error in the returned ``n`` rejects "at least
    ``first_unacceptable`` bad items exist" at level ``alpha``, which supports a
    claim of at most ``first_unacceptable - 1``.
    """
    population = _integer(N, "N")
    unacceptable = _integer(first_unacceptable, "first_unacceptable", minimum=1)
    level = _alpha(alpha, "alpha")
    if population == 0:
        return 0
    if unacceptable > population:
        # The hypothesis is already impossible: the population is too small to
        # hold that many bad items.
        return 0
    low, high = 0, population
    while low < high:
        middle = (low + high) // 2
        if probability_zero_found(population, unacceptable, middle) <= level:
            high = middle
        else:
            low = middle + 1
    return low


def upper_bound_undetected(N: int, n: int, k: int, alpha: float) -> int:
    """Exact upper confidence bound on bad items the audit did not see.

    Returns the largest number of bad items that could remain among the
    ``N - n`` unaudited records while staying consistent with having observed
    ``k`` in ``n``, at confidence ``1 - alpha``.
    """
    population = _integer(N, "N")
    sample = _integer(n, "n")
    found = _integer(k, "k")
    level = _alpha(alpha, "alpha")
    if sample > population:
        raise AuditPolicyError("sample size cannot exceed the population")
    if found > sample:
        raise AuditPolicyError("cannot observe more errors than records audited")
    if population == 0:
        return 0
    # P(X <= k | K) decreases as K grows; the first refuted K bounds the total.
    total_bound = population
    for candidate in range(found, population + 1):
        if probability_at_most(population, candidate, sample, found) <= level:
            total_bound = candidate - 1
            break
    total_bound = max(total_bound, found)
    return max(0, total_bound - found)


# --------------------------------------------------------------------------
# Frozen selection
# --------------------------------------------------------------------------


def frozen_permutation(population: Sequence[str], seed: str) -> List[str]:
    """One reproducible ordering of the population.

    Every stage draws a prefix of this ordering, so an expansion after an error
    cannot be steered toward or away from anything.
    """
    _text(seed, "seed")
    items = list(population)
    for item in items:
        _text(item, "population item")
    if len(set(items)) != len(items):
        raise AuditPolicyError("population contains duplicate identifiers")
    return sorted(
        items,
        key=lambda item: hashlib.sha256(f"{seed}\0{item}".encode("utf-8")).hexdigest(),
    )


def select_seeded_sample(population: List[str], n: int, seed: str) -> List[str]:
    """Take the first ``n`` entries of the frozen permutation."""
    size = _integer(n, "n")
    ordering = frozen_permutation(population, seed)
    if size > len(ordering):
        raise AuditPolicyError("requested sample is larger than the population")
    return ordering[:size]


# --------------------------------------------------------------------------
# Policy
# --------------------------------------------------------------------------


def validate_policy(policy: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a policy that a protocol locked before any results existed."""
    if not isinstance(policy, dict):
        raise AuditPolicyError("policy must be an object")
    if policy.get("schema_version") != POLICY_SCHEMA_VERSION:
        raise AuditPolicyError(f"policy schema must be {POLICY_SCHEMA_VERSION}")
    _text(policy.get("policy_version"), "policy.policy_version")
    _text(policy.get("seed"), "policy.seed")
    _text(policy.get("unit"), "policy.unit")

    first_unacceptable = _integer(
        policy.get("first_unacceptable_missed_records"),
        "policy.first_unacceptable_missed_records",
        minimum=1,
    )
    tolerated = _integer(
        policy.get("maximum_tolerated_missed_records"),
        "policy.maximum_tolerated_missed_records",
    )
    if tolerated != first_unacceptable - 1:
        raise AuditPolicyError(
            "maximum_tolerated_missed_records must equal "
            "first_unacceptable_missed_records - 1; ruling out K supports K-1"
        )

    alpha = _alpha(policy.get("alpha"), "policy.alpha")
    stages = policy.get("stage_alpha")
    if not isinstance(stages, dict):
        raise AuditPolicyError("policy.stage_alpha must be an object")
    stage_1 = _alpha(stages.get("stage_1"), "policy.stage_alpha.stage_1")
    stage_2 = _alpha(stages.get("stage_2"), "policy.stage_alpha.stage_2")
    if stage_1 + stage_2 > alpha:
        raise AuditPolicyError(
            "stage alphas must not exceed the total alpha; repeated looks at "
            "the data spend it"
        )
    if stage_2 >= stage_1:
        raise AuditPolicyError(
            "stage_2 alpha must be smaller than stage_1 so expansion enlarges "
            "the sample"
        )

    high_risk = policy.get("high_risk_items", [])
    if not isinstance(high_risk, list):
        raise AuditPolicyError("policy.high_risk_items must be an array")
    for item in high_risk:
        _text(item, "policy.high_risk_items[]")
    if len(set(high_risk)) != len(high_risk):
        raise AuditPolicyError("policy.high_risk_items contains duplicates")

    if not isinstance(policy.get("high_risk_strata", []), list):
        raise AuditPolicyError("policy.high_risk_strata must be an array")

    confirmation = policy.get("confirmation_fraction", 0)
    if isinstance(confirmation, bool) or not isinstance(confirmation, (int, float)):
        raise AuditPolicyError("policy.confirmation_fraction must be a number")
    if not 0 <= Fraction(str(confirmation)) <= 1:
        raise AuditPolicyError("policy.confirmation_fraction must be within [0, 1]")
    return policy


def plan_audit(policy: Dict[str, Any], population: Sequence[str]) -> Dict[str, Any]:
    """Compute the realized plan from the realized population.

    The protocol locked the function; this evaluates it. Nothing here is a new
    scientific decision.
    """
    validate_policy(policy)
    items = list(population)
    for item in items:
        _text(item, "population item")
    if len(set(items)) != len(items):
        raise AuditPolicyError("population contains duplicate identifiers")
    known = set(items)
    declared = list(policy.get("high_risk_items", []))
    missing = sorted(set(declared) - known)
    if missing:
        raise AuditPolicyError(
            "high-risk items are absent from the population: " + ", ".join(missing[:5])
        )
    census = set(declared)
    remainder = [item for item in items if item not in census]
    remainder_size = len(remainder)
    first_unacceptable = policy["first_unacceptable_missed_records"]
    stage_1 = policy["stage_alpha"]["stage_1"]
    stage_2 = policy["stage_alpha"]["stage_2"]
    n1 = sample_size_exact(remainder_size, first_unacceptable, stage_1)
    n2 = sample_size_exact(remainder_size, first_unacceptable, stage_2)
    ordering = frozen_permutation(remainder, policy["seed"])
    confirmation = _confirmation_count(policy, n1)
    return {
        "schema_version": POLICY_SCHEMA_VERSION,
        "confirmation_size": confirmation,
        "confirmation_items": ordering[:confirmation],
        "population_size": len(items),
        "census_size": len(census),
        "remainder_size": remainder_size,
        "census_items": sorted(census),
        "stage_1_size": n1,
        "stage_2_size": n2,
        "stage_1_items": ordering[:n1],
        "stage_2_items": ordering[:n2],
        "frozen_permutation": ordering,
        "first_unacceptable_missed_records": first_unacceptable,
        "maximum_tolerated_missed_records": policy["maximum_tolerated_missed_records"],
        "inference_scope": PROBABILITY_SCOPE,
        "census_is_not_an_estimate": True,
    }


def _confirmation_count(policy: Dict[str, Any], stage_1_size: int) -> int:
    """How many stage-1 confirmations a second human must repeat.

    Prespecified as a fraction of the stage-1 sample and drawn from the front
    of the frozen permutation, so the confirmation subset cannot be chosen
    after the first reviewer's verdicts are known.
    """
    fraction = Fraction(str(policy.get("confirmation_fraction", 0)))
    if fraction == 0 or stage_1_size == 0:
        return 0
    exact = fraction * stage_1_size
    return min(stage_1_size, -((-exact.numerator) // exact.denominator))


def _index_observations(observed: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    by_item: Dict[str, Dict[str, Any]] = {}
    for index, record in enumerate(observed):
        where = f"observed[{index}]"
        if not isinstance(record, dict):
            raise AuditPolicyError(f"{where} must be an object")
        item = _text(record.get("item_id"), f"{where}.item_id")
        if item in by_item:
            raise AuditPolicyError(f"duplicate observation for {item}")
        verdict = _text(record.get("verdict"), f"{where}.verdict")
        if verdict not in VERDICTS:
            raise AuditPolicyError(f"{where}.verdict is unsupported: {verdict}")
        role = _text(record.get("role"), f"{where}.role")
        if role not in ROLES:
            raise AuditPolicyError(f"{where}.role is unsupported: {role}")
        reviewer = _text(record.get("reviewer_id"), f"{where}.reviewer_id")
        second = record.get("second_reviewer_id")
        if verdict in (VERDICT_FALSE_EXCLUSION, VERDICT_UNCERTAIN):
            second_id = _text(second, f"{where}.second_reviewer_id")
            if second_id == reviewer:
                raise AuditPolicyError(
                    f"{where} needs a second, distinct human adjudicator; one "
                    "reviewer is not a gold standard"
                )
        elif second is not None:
            second_id = _text(second, f"{where}.second_reviewer_id")
            if second_id == reviewer:
                raise AuditPolicyError(
                    f"{where} confirmation must use a distinct second reviewer"
                )
        by_item[item] = record
    return by_item


def evaluate_two_stage(
    policy: Dict[str, Any],
    population: List[str],
    observed: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Evaluate the audit and return the automation decision.

    Stage 1 may pass only under its own alpha. Any error expands to stage 2
    using the next frozen entries. Acceptance requires the exact upper bound on
    undetected errors in the probability-sampled remainder to sit within the
    prespecified tolerance; otherwise automation is disabled and the affected
    population goes to full human reassessment.
    """
    plan = plan_audit(policy, population)
    by_item = _index_observations(observed)

    census_required = set(plan["census_items"])
    census_reviewed = {
        item for item, record in by_item.items() if record["role"] == ROLE_CENSUS
    }
    census_missing = sorted(census_required - census_reviewed)
    if census_missing:
        raise AuditPolicyError(
            "high-risk census is incomplete: " + ", ".join(census_missing[:5])
        )
    unexpected = sorted(census_reviewed - census_required)
    if unexpected:
        raise AuditPolicyError(
            "census observations outside the high-risk stratum: "
            + ", ".join(unexpected[:5])
        )

    stage_1_items = plan["stage_1_items"]
    missing_stage_1 = sorted(set(stage_1_items) - set(by_item))
    if missing_stage_1:
        raise AuditPolicyError(
            "stage 1 sample is incomplete: " + ", ".join(missing_stage_1[:5])
        )

    unconfirmed = sorted(
        item
        for item in plan["confirmation_items"]
        if by_item[item]["verdict"] == VERDICT_CORRECT
        and not by_item[item].get("second_reviewer_id")
    )
    if unconfirmed:
        raise AuditPolicyError(
            "prespecified confirmation sample lacks a second reviewer for: "
            + ", ".join(unconfirmed[:5])
            + " — an unchecked first reviewer is the audit's blind spot"
        )

    def errors_in(items: Sequence[str]) -> List[str]:
        return sorted(
            item
            for item in items
            if by_item[item]["verdict"]
            in (VERDICT_FALSE_EXCLUSION, VERDICT_UNCERTAIN)
        )

    census_errors = errors_in(sorted(census_required))
    stage_1_errors = errors_in(stage_1_items)
    remainder_size = plan["remainder_size"]
    tolerance = plan["maximum_tolerated_missed_records"]
    stage_1_alpha = policy["stage_alpha"]["stage_1"]
    stage_2_alpha = policy["stage_alpha"]["stage_2"]

    if not stage_1_errors:
        bound = upper_bound_undetected(
            remainder_size, len(stage_1_items), 0, stage_1_alpha
        )
        return _result(
            plan,
            stage=1,
            audited=len(stage_1_items),
            errors=[],
            census_errors=census_errors,
            bound=bound,
            alpha=stage_1_alpha,
            outcome=OUTCOME_ACCEPT if bound <= tolerance else OUTCOME_DISABLE,
        )

    stage_2_items = plan["stage_2_items"]
    pending = sorted(set(stage_2_items) - set(by_item))
    if pending:
        return _result(
            plan,
            stage=1,
            audited=len(stage_1_items),
            errors=stage_1_errors,
            census_errors=census_errors,
            bound=None,
            alpha=stage_1_alpha,
            outcome=OUTCOME_EXPAND,
            pending=pending,
        )

    stage_2_errors = errors_in(stage_2_items)
    bound = upper_bound_undetected(
        remainder_size, len(stage_2_items), len(stage_2_errors), stage_2_alpha
    )
    return _result(
        plan,
        stage=2,
        audited=len(stage_2_items),
        errors=stage_2_errors,
        census_errors=census_errors,
        bound=bound,
        alpha=stage_2_alpha,
        outcome=OUTCOME_ACCEPT if bound <= tolerance else OUTCOME_DISABLE,
    )


def _result(
    plan: Dict[str, Any],
    *,
    stage: int,
    audited: int,
    errors: Sequence[str],
    census_errors: Sequence[str],
    bound: Optional[int],
    alpha: Fraction,
    outcome: str,
    pending: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    return {
        "schema_version": POLICY_SCHEMA_VERSION,
        "stage": stage,
        "outcome": outcome,
        "alpha_spent": float(alpha),
        "remainder_size": plan["remainder_size"],
        "remainder_audited": audited,
        "remainder_errors": list(errors),
        "upper_bound_undetected": bound,
        "maximum_tolerated_missed_records": plan["maximum_tolerated_missed_records"],
        "first_unacceptable_missed_records": plan["first_unacceptable_missed_records"],
        "pending_stage_2_items": list(pending or []),
        # Reported separately and never merged into the sampled estimate.
        "census_size": plan["census_size"],
        "census_errors": list(census_errors),
        "confirmation_size": plan["confirmation_size"],
        "census_scope": DETECTION_SCOPE,
        "census_is_not_an_estimate": True,
        "inference_scope": PROBABILITY_SCOPE,
        "combined_unweighted_rate_reported": False,
    }


# --------------------------------------------------------------------------
# Truthful scope labels for non-inferential outputs
# --------------------------------------------------------------------------


def challenge_set_result(summary: Dict[str, Any]) -> Dict[str, Any]:
    """Label a challenge-set measurement as unusable for production claims."""
    if not isinstance(summary, dict):
        raise AuditPolicyError("challenge summary must be an object")
    return {
        **summary,
        "estimand_scope": ENRICHED_SCOPE,
        "production_error_rate_estimate": False,
        "manuscript_performance_claim_authorized": False,
        "valid_use": "reviewer-pair ranking and configuration selection only",
    }


def detection_only_result(
    summary: Dict[str, Any], *, schema_version: str = "2.0"
) -> Dict[str, Any]:
    """Label a Phase 12-style detection sample as not an error-rate estimate."""
    if not isinstance(summary, dict):
        raise AuditPolicyError("detection summary must be an object")
    return {
        **summary,
        "audit_output_schema_version": schema_version,
        "estimand_scope": DETECTION_SCOPE,
        "error_rate_estimate": False,
        "manuscript_performance_claim_authorized": False,
        "valid_use": "reporting how many assessments were checked and what was found",
    }


def classify_legacy_audit(summary: Dict[str, Any]) -> Dict[str, Any]:
    """Legacy audit outputs are detection-only unless they carry valid inference.

    A prior locked package is never rewritten, so its claims are constrained on
    read instead.
    """
    if not isinstance(summary, dict):
        raise AuditPolicyError("legacy summary must be an object")
    policy = summary.get("audit_policy")
    has_inference = (
        isinstance(policy, dict)
        and "alpha" in policy
        and "first_unacceptable_missed_records" in policy
    )
    if has_inference:
        return {**summary, "estimand_scope": PROBABILITY_SCOPE}
    return detection_only_result(summary, schema_version="1.0-legacy")


def assert_not_a_production_claim(result: Dict[str, Any]) -> None:
    """Refuse to let a challenge or detection result become a reported rate."""
    if not isinstance(result, dict):
        raise AuditPolicyError("result must be an object")
    scope = result.get("estimand_scope")
    if scope in (ENRICHED_SCOPE, DETECTION_SCOPE):
        raise AuditPolicyError(
            f"{scope} results cannot be reported as a production error rate"
        )
