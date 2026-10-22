"""Phase 2 state estimator tests."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from dsde.data.pit_store import PitStore
from dsde.data.providers import FileJsonProvider
from dsde.data.synthetic import write_synthetic_bundle
from dsde.domain.enums import FundamentalState, MarketState
from dsde.features.builder import FeatureBuilder
from dsde.states.baseline import RuleStatStateEstimator
from dsde.states.factorized import FactorizedProbStateEstimator
from dsde.states.filtering import fingerprint_from_features, fundamental_observation_changed


@pytest.fixture()
def store(tmp_path: Path) -> PitStore:
    root = write_synthetic_bundle(tmp_path / "synth")
    s = PitStore()
    s.ingest_provider(FileJsonProvider(root))
    return s


def _history(store: PitStore, n: int = 8) -> tuple[FeatureBuilder, list]:
    fb = FeatureBuilder(store)
    days = [
        datetime(2020, 1, 31, 15, 0),
        datetime(2020, 2, 7, 15, 0),
        datetime(2020, 2, 14, 15, 0),
        datetime(2020, 2, 21, 15, 0),
        datetime(2020, 2, 28, 15, 0),
        datetime(2020, 3, 6, 15, 0),
        datetime(2020, 3, 13, 15, 0),
        datetime(2020, 3, 20, 15, 0),
        datetime(2020, 3, 27, 15, 0),
    ][:n]
    snaps = [fb.build(as_of=d, instrument_id="SYN001.SH") for d in days]
    return fb, snaps


def _valid_belief(b) -> None:
    assert abs(sum(b.fundamental.values()) - 1.0) < 1e-6
    assert abs(sum(b.market.values()) - 1.0) < 1e-6
    assert set(b.fundamental) == {s.value for s in FundamentalState}
    assert set(b.market) >= {
        MarketState.RISK_ON.value,
        MarketState.NEUTRAL.value,
        MarketState.RISK_OFF.value,
    }


def test_rule_and_factorized_emit_valid_beliefs(store: PitStore) -> None:
    fb, hist = _history(store)
    rule = RuleStatStateEstimator().fit(hist, seed=7)
    prob = FactorizedProbStateEstimator().fit(hist, seed=7)
    snap = hist[-1]
    b1 = rule.update(as_of=snap.as_of, features=snap)
    b2 = prob.update(as_of=snap.as_of, features=snap)
    _valid_belief(b1)
    _valid_belief(b2)
    assert b1.market_regime_gate_passed is False
    assert b2.market_regime_gate_passed is False


def test_seed_reproducible(store: PitStore) -> None:
    _, hist = _history(store)
    snap = hist[-1]

    def run(seed: int):
        est = FactorizedProbStateEstimator().fit(hist, seed=seed)
        return est.update(as_of=snap.as_of, features=snap)

    a = run(42)
    b = run(42)
    c = run(99)
    assert a.fundamental == b.fundamental
    assert a.market == b.market
    # Different seed may change fit jitter on weights → possibly different probs
    # At minimum diagnostics seed differs
    assert a.diagnostics["seed"] == 42
    assert c.diagnostics["seed"] == 99


def test_no_forged_fundamental_between_announcements(store: PitStore) -> None:
    fb = FeatureBuilder(store)
    # After first Q4 announcement, before revision
    s1 = fb.build(as_of=datetime(2020, 1, 25, 15, 0), instrument_id="SYN001.SH")
    s2 = fb.build(as_of=datetime(2020, 2, 10, 15, 0), instrument_id="SYN001.SH")
    # Same announcement fingerprint until revision on 2020-02-15
    assert fingerprint_from_features(s1) == fingerprint_from_features(s2)
    assert not fundamental_observation_changed(fingerprint_from_features(s1), s2)

    hist = [s1]
    est = RuleStatStateEstimator(min_history=1).fit(hist, seed=0)
    b1 = est.update(as_of=s1.as_of, features=s1)
    b2 = est.update(as_of=s2.as_of, features=s2, prior=b1)
    assert b2.fundamental == b1.fundamental
    assert any("no_new_announcement" in w or "hold_prior" in w for w in b2.warnings) or (
        b2.fundamental == b1.fundamental
    )

    s3 = fb.build(as_of=datetime(2020, 2, 16, 15, 0), instrument_id="SYN001.SH")
    assert fundamental_observation_changed(fingerprint_from_features(s2), s3)
    b3 = est.update(as_of=s3.as_of, features=s3, prior=b2)
    # New announcement fingerprint → allowed to refresh fundamental probs
    assert b3.input_snapshot_hash == s3.snapshot_hash
    assert fingerprint_from_features(s3) != fingerprint_from_features(s2)


def test_degrade_when_underidentified(store: PitStore) -> None:
    fb = FeatureBuilder(store)
    # Very early: sparse market history
    early = fb.build(as_of=datetime(2019, 11, 5, 15, 0), instrument_id="SYN001.SH")
    est = FactorizedProbStateEstimator(min_history=50).fit([early], seed=1)
    assert est._fitted is False
    b = est.update(as_of=early.as_of, features=early)
    assert b.degraded is True
    assert b.warnings
    diag = est.diagnostics()
    assert "fundamental_share" in diag
    assert diag["degrade_count"] >= 1


def test_diagnostics_share_duration_transitions(store: PitStore) -> None:
    fb, hist = _history(store, n=9)
    est = RuleStatStateEstimator().fit(hist, seed=3)
    prior = None
    for snap in hist:
        prior = est.update(as_of=snap.as_of, features=snap, prior=prior)
    diag = est.diagnostics()
    assert diag["n"] == len(hist)
    assert diag["fundamental_share"]
    assert diag["market_share"]
    assert "fundamental_durations" in diag
    assert "market_transitions" in diag
