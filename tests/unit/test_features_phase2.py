"""Phase 2 feature builder tests."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from dsde.data.asof_query import AsOfQuery
from dsde.data.pit_store import PitStore
from dsde.data.providers import FileJsonProvider
from dsde.data.synthetic import write_synthetic_bundle
from dsde.features.builder import FeatureBuilder
from dsde.features.registry import FeatureFamily, default_registry
from dsde.features.transforms import RollingScaler


@pytest.fixture()
def store(tmp_path: Path) -> PitStore:
    root = write_synthetic_bundle(tmp_path / "synth")
    s = PitStore()
    s.ingest_provider(FileJsonProvider(root))
    return s


def test_market_features_require_regime_gate() -> None:
    reg = default_registry()
    market = reg.by_family(FeatureFamily.MARKET)
    assert market
    assert all(s.requires_market_regime_gate for s in market)
    fund = reg.by_family(FeatureFamily.FUNDAMENTAL)
    assert fund
    assert all(not s.requires_market_regime_gate for s in fund)


def test_features_no_future_leakage(store: PitStore) -> None:
    fb = FeatureBuilder(store)
    as_of = datetime(2020, 1, 10, 15, 0)
    snap = fb.build(as_of=as_of, instrument_id="SYN001.SH")
    # No fundamental yet (announce 2020-01-20)
    assert snap.fundamental_announcement_time is None or (
        snap.fundamental_announcement_time <= as_of
    )
    q = AsOfQuery(store)
    for p in q.prices(as_of, instrument_id="SYN001.SH"):
        assert p.available_at <= as_of
    fb.assert_no_future_prices(as_of, "SYN001.SH")
    # After announcement
    later = fb.build(as_of=datetime(2020, 1, 21, 18, 0), instrument_id="SYN001.SH")
    assert later.fundamental_period_end == date(2019, 12, 31)
    assert later.fundamental.get("net_income_margin") is not None


def test_scaler_fit_train_only_no_test_leak(store: PitStore) -> None:
    fb = FeatureBuilder(store)
    train_asofs = [
        datetime(2020, 1, 31, 15, 0),
        datetime(2020, 2, 14, 15, 0),
        datetime(2020, 2, 28, 15, 0),
        datetime(2020, 3, 6, 15, 0),
        datetime(2020, 3, 13, 15, 0),
        datetime(2020, 3, 20, 15, 0),
    ]
    train_snaps = [
        fb.build(as_of=t, instrument_id="SYN001.SH") for t in train_asofs
    ]
    scaler = RollingScaler().fit([s.all_features() for s in train_snaps])
    assert scaler.fitted
    # Freeze means — building a later snap and fitting again would change means;
    # transform must use frozen train params.
    frozen_means = dict(scaler.means)
    test_snap = fb.build(as_of=datetime(2020, 3, 27, 15, 0), instrument_id="SYN001.SH")
    _ = scaler.transform(test_snap.all_features())
    assert scaler.means == frozen_means


def test_fundamental_not_forged_without_announcement(store: PitStore) -> None:
    fb = FeatureBuilder(store)
    before = fb.build(as_of=datetime(2020, 1, 15, 12, 0), instrument_id="SYN001.SH")
    # Prior year period announced 2019-01-20 is visible, but Q4 2019 not yet
    # Feature values may exist from 2018 period only — period_end should not be Q4 2019
    if before.fundamental_period_end is not None:
        assert before.fundamental_period_end <= date(2018, 12, 31)
    after = fb.build(as_of=datetime(2020, 1, 21, 12, 0), instrument_id="SYN001.SH")
    assert after.fundamental_period_end == date(2019, 12, 31)
