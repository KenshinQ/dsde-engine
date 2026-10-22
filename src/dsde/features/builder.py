"""Feature builder: PIT-safe fundamental vs market feature snapshots."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime

from dsde.data.asof_query import AsOfQuery
from dsde.data.pit_store import PitStore
from dsde.features.registry import FeatureFamily, FeatureRegistry, default_registry
from dsde.features.transforms import (
    max_drawdown_from_peak,
    rolling_mean,
    rolling_std,
    simple_returns,
)


@dataclass
class FeatureSnapshot:
    """Features available at as_of; fundamental vs market separated."""

    as_of: datetime
    instrument_id: str
    fundamental: dict[str, float | None] = field(default_factory=dict)
    market: dict[str, float | None] = field(default_factory=dict)
    fundamental_announcement_time: datetime | None = None
    fundamental_period_end: date | None = None
    fundamental_revision_id: str | None = None
    market_gated_feature_names: list[str] = field(default_factory=list)
    is_synthetic: bool = False
    snapshot_hash: str = ""

    def all_features(self) -> dict[str, float | None]:
        return {**self.fundamental, **self.market}


class FeatureBuilder:
    """Build features from PitStore via AsOfQuery — no future bars/fundamentals."""

    def __init__(
        self,
        store: PitStore,
        registry: FeatureRegistry | None = None,
    ) -> None:
        self.store = store
        self.query = AsOfQuery(store)
        self.registry = registry or default_registry()

    def build(self, *, as_of: datetime, instrument_id: str) -> FeatureSnapshot:
        fund = self._fundamental_features(as_of, instrument_id)
        mkt, gated = self._market_features(as_of, instrument_id)
        latest = self.query.latest_fundamental(as_of, instrument_id)
        snap = FeatureSnapshot(
            as_of=as_of,
            instrument_id=instrument_id,
            fundamental=fund,
            market=mkt,
            fundamental_announcement_time=(
                latest.announcement_time if latest else None
            ),
            fundamental_period_end=latest.period_end if latest else None,
            fundamental_revision_id=latest.revision_id if latest else None,
            market_gated_feature_names=gated,
            is_synthetic=True,  # Phase 2 demos use synthetic PIT; callers may override
            snapshot_hash="",
        )
        # Detect synthetic from store rows
        prices = self.query.prices(as_of, instrument_id=instrument_id)
        if prices and all(p.is_synthetic for p in prices):
            snap.is_synthetic = True
        elif latest is not None:
            snap.is_synthetic = latest.is_synthetic
        snap.snapshot_hash = self._hash_snapshot(snap)
        return snap

    def _hash_snapshot(self, snap: FeatureSnapshot) -> str:
        payload = {
            "as_of": snap.as_of.isoformat(),
            "instrument_id": snap.instrument_id,
            "fundamental": snap.fundamental,
            "market": snap.market,
            "fund_rev": snap.fundamental_revision_id,
        }
        blob = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]

    def _fundamental_features(
        self, as_of: datetime, instrument_id: str
    ) -> dict[str, float | None]:
        """Only use fundamentals with announcement/available_at <= as_of."""
        rows = self.query.fundamentals(as_of, instrument_id=instrument_id)
        out: dict[str, float | None] = {
            s.name: None
            for s in self.registry.by_family(FeatureFamily.FUNDAMENTAL)
        }
        if not rows:
            return out
        # Latest by period_end
        rows_sorted = sorted(rows, key=lambda f: f.period_end)
        latest = rows_sorted[-1]
        prev = rows_sorted[-2] if len(rows_sorted) >= 2 else None
        rev = latest.financial_features.get("revenue")
        ni = latest.financial_features.get("net_income")
        cfo = latest.cash_flow_features.get("cfo")
        assets = latest.balance_sheet_features.get("total_assets")

        if rev and prev is not None:
            prev_rev = prev.financial_features.get("revenue")
            if prev_rev and prev_rev != 0:
                out["revenue_yoy"] = float(rev) / float(prev_rev) - 1.0
        if rev and ni is not None and rev != 0:
            out["net_income_margin"] = float(ni) / float(rev)
        if ni is not None and cfo is not None and ni != 0:
            out["cfo_to_ni"] = float(cfo) / float(ni)
        if assets is not None and prev is not None:
            prev_a = prev.balance_sheet_features.get("total_assets")
            if prev_a and prev_a != 0:
                out["leverage_proxy"] = float(assets) / float(prev_a) - 1.0
        return out

    def _market_features(
        self, as_of: datetime, instrument_id: str
    ) -> tuple[dict[str, float | None], list[str]]:
        bars = [
            p
            for p in self.query.prices(as_of, instrument_id=instrument_id)
            if not p.is_suspended and p.close is not None
        ]
        bars = sorted(bars, key=lambda b: b.trade_date)
        closes = [float(b.close) for b in bars if b.close is not None]
        gated = self.registry.market_gated_names()
        out: dict[str, float | None] = {name: None for name in gated}

        if len(closes) >= 2:
            rets = simple_returns(closes)
            if len(rets) >= 20:
                out["mkt_ret_20d"] = sum(rets[-20:])
                vol = rolling_std(rets, 20)
                out["mkt_vol_20d"] = vol
                up = sum(1 for r in rets[-20:] if r > 0) / 20.0
                out["mkt_breadth_proxy"] = up
            if len(closes) >= 20:
                ma = rolling_mean(closes, 20)
                if ma and ma != 0:
                    out["mkt_trend_ma_gap"] = closes[-1] / ma - 1.0
            if len(closes) >= 60:
                out["mkt_drawdown_60d"] = max_drawdown_from_peak(closes[-60:])
            elif len(closes) >= 2:
                out["mkt_drawdown_60d"] = max_drawdown_from_peak(closes)

        # Assert all market features are gate-tagged in registry
        for name in out:
            spec = self.registry.get(name)
            assert spec.requires_market_regime_gate is True
            assert spec.family == FeatureFamily.MARKET
        return out, gated

    def assert_no_future_prices(self, as_of: datetime, instrument_id: str) -> None:
        for p in self.query.prices(as_of, instrument_id=instrument_id):
            if p.available_at > as_of:
                raise AssertionError("future price leaked into features")
