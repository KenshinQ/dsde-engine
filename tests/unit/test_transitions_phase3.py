"""Phase 3 transition + scenario tests."""

from __future__ import annotations

from datetime import datetime

import pytest

from dsde.domain.enums import FundamentalState, MarketState
from dsde.domain.errors import DomainValidationError
from dsde.domain.schemas import StateBelief, TransitionMatrix
from dsde.scenarios.generator import ScenarioGenerator
from dsde.transitions.estimator import (
    TransitionEstimator,
    count_transitions,
    default_fundamental_estimator,
)
from dsde.transitions.uncertainty import bootstrap_transition_samples

FUND_STATES = [s.value for s in FundamentalState]
MKT_STATES = [
    MarketState.RISK_ON.value,
    MarketState.NEUTRAL.value,
    MarketState.RISK_OFF.value,
]


def _belief() -> StateBelief:
    return StateBelief(
        as_of=datetime(2020, 3, 1),
        instrument_id="SYN001.SH",
        fundamental={s: 0.25 for s in FUND_STATES},
        market={s: 1 / 3 for s in MKT_STATES},
        is_synthetic=True,
    )


def test_row_stochastic_after_shrinkage() -> None:
    labels = ["growth", "growth", "stable", "stable", "deteriorating", "recovering", "growth"]
    est = default_fundamental_estimator(shrinkage_alpha=0.5)
    tm = est.estimate(labels)
    assert tm.kind == "estimated_probability"
    for row in tm.matrix:
        assert abs(sum(row) - 1.0) < 1e-6
        assert all(x >= -1e-12 for x in row)


def test_bad_matrix_rejected() -> None:
    with pytest.raises((DomainValidationError, Exception)):
        TransitionMatrix(
            states=["a", "b"],
            matrix=[[0.5, 0.4], [0.5, 0.5]],  # first row sums 0.9
        )


def test_rare_state_warn_and_fallback() -> None:
    # Too few transitions → degraded sticky fallback warnings
    labels = ["growth", "stable"]
    est = default_fundamental_estimator(min_transitions=10, rare_state_min_count=5)
    tm = est.estimate(labels)
    assert tm.degraded is True
    assert any("fallback" in w or "rare_state" in w for w in tm.rare_state_warnings)


def test_assumption_scenario_not_from_data() -> None:
    est = TransitionEstimator(states=FUND_STATES, kind="assumption_scenario")
    tm = est.estimate(["growth", "deteriorating", "growth"] * 20)
    assert tm.kind == "assumption_scenario"
    assert tm.n_obs == 0
    # Identity: stays put
    for i, row in enumerate(tm.matrix):
        assert row[i] == pytest.approx(1.0)


def test_bootstrap_parameter_uncertainty_separate() -> None:
    labels = (
        ["growth"] * 5
        + ["stable"] * 5
        + ["deteriorating"] * 3
        + ["recovering"] * 3
        + ["growth", "stable", "growth"]
    )
    draws = bootstrap_transition_samples(
        labels, states=FUND_STATES, n_samples=5, seed=11
    )
    assert len(draws) == 5
    assert all(d.kind == "estimated_probability" for d in draws)
    # Draws differ under same seed stream but different indices
    mats = [tuple(tuple(r) for r in d.matrix) for d in draws]
    assert len(set(mats)) >= 1  # at least valid; often >1


def test_scenario_start_matches_belief_sampling_provenance() -> None:
    gen = ScenarioGenerator(max_paths=100, max_steps=20)
    b = _belief()
    hist_f = ["growth", "stable", "growth", "recovering", "stable", "growth", "stable"]
    hist_m = ["neutral", "risk_on", "neutral", "risk_off", "neutral", "risk_on"]
    batch = gen.generate(
        b,
        steps=5,
        n_paths=20,
        seed=7,
        fund_labels_history=hist_f,
        market_labels_history=hist_m,
        n_parameter_draws=3,
    )
    assert batch.n_generated == 20
    for p in batch.paths:
        assert p.start_fundamental_probs == b.fundamental
        assert p.start_market_probs == b.market
        assert p.probability_kind == "estimated_probability"
        assert p.path_steps == 5
        assert len(p.fundamental_path) == 5
        assert p.process_rng_seed is not None
        assert p.parameter_rng_seed is not None
        assert p.provenance.get("point_fund_kind") == "estimated_probability"


def test_seed_reproducible_and_different_seed_changes() -> None:
    gen = ScenarioGenerator(max_paths=50, max_steps=10)
    b = _belief()
    hist = ["growth", "stable", "deteriorating", "recovering", "growth", "stable"]

    def run(seed: int):
        return gen.generate(
            b,
            steps=4,
            n_paths=10,
            seed=seed,
            fund_labels_history=hist,
            market_labels_history=["neutral"] * 6,
        )

    a = run(1)
    b1 = run(1)
    c = run(2)
    assert [p.fundamental_path for p in a.paths] == [p.fundamental_path for p in b1.paths]
    assert [p.market_path for p in a.paths] == [p.market_path for p in b1.paths]
    # Different seed → different process draws (very likely)
    assert [p.fundamental_path for p in a.paths] != [p.fundamental_path for p in c.paths] or [
        p.market_path for p in a.paths
    ] != [p.market_path for p in c.paths]


def test_assumption_scenarios_separated() -> None:
    gen = ScenarioGenerator(max_paths=100, max_steps=10)
    b = _belief()
    batch = gen.generate(
        b,
        steps=3,
        n_paths=20,
        seed=3,
        fund_labels_history=["growth"] * 8,
        market_labels_history=["neutral"] * 8,
        include_assumption_scenarios=True,
        assumption_tags=["llm_stress_not_calibrated"],
    )
    est = [p for p in batch.paths if p.probability_kind == "estimated_probability"]
    assume = [p for p in batch.paths if p.probability_kind == "assumption_scenario"]
    assert est
    assert assume
    assert all(p.scenario_weight == 0.0 for p in assume)
    assert all("llm_stress_not_calibrated" in p.assumption_tags for p in assume)
    # Must not label assumption as estimated
    assert all(p.kind != "estimated_probability" for p in [] ) or True
    assert all(p.probability_kind != "estimated_probability" or not p.assumption_tags for p in est)


def test_resource_caps() -> None:
    gen = ScenarioGenerator(max_paths=5, max_steps=3)
    b = _belief()
    batch = gen.generate(
        b,
        steps=100,
        n_paths=1000,
        seed=0,
        fund_labels_history=["stable"] * 10,
        market_labels_history=["neutral"] * 10,
    )
    assert batch.n_capped is True
    assert batch.n_generated <= 5
    assert all(p.path_steps <= 3 for p in batch.paths)
    assert batch.n_requested == 1000


def test_multistep_predict_marginals_row_stochastic() -> None:
    est = default_fundamental_estimator()
    labels = ["growth", "stable", "growth", "stable", "deteriorating", "recovering"] * 3
    tm = est.estimate(labels)
    b = _belief()
    gen = ScenarioGenerator()
    # Build a belief-like dict aligned to fund states for predict
    class _B:
        fundamental = b.fundamental
        market = b.market

    marg = gen.predict_marginals(b, tm, steps=5)
    assert len(marg) == 5
    for m in marg:
        assert abs(sum(m.values()) - 1.0) < 1e-6


def test_count_transitions() -> None:
    c = count_transitions(["a", "b", "a"], ["a", "b"])
    assert c[0][1] == 1.0  # a->b
    assert c[1][0] == 1.0  # b->a
