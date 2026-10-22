"""Baseline A: rule / rolling-stat state classifier → soft beliefs."""

from __future__ import annotations

import math
import random
from datetime import datetime
from typing import Any

from dsde.domain.enums import FundamentalState, MarketState
from dsde.domain.schemas import ObservationRecord, StateBelief
from dsde.features.builder import FeatureSnapshot
from dsde.features.transforms import RollingScaler
from dsde.states.diagnostics import belief_path_diagnostics
from dsde.states.filtering import fingerprint_from_features, fundamental_observation_changed


def _softmax(logits: dict[str, float], temperature: float = 1.0) -> dict[str, float]:
    t = max(temperature, 1e-6)
    m = max(logits.values())
    exps = {k: math.exp((v - m) / t) for k, v in logits.items()}
    z = sum(exps.values())
    return {k: v / z for k, v in exps.items()}


class RuleStatStateEstimator:
    """Low-complexity baseline: threshold rules on features → softmax probs.

    Fundamental beliefs update only when a new announcement fingerprint appears.
    Market beliefs may update daily from gated market features (gate flag recorded).
    """

    model_version = "rule_stat_v1"

    def __init__(self, *, temperature: float = 0.75, min_history: int = 5) -> None:
        self.temperature = temperature
        self.min_history = min_history
        self.scaler = RollingScaler()
        self._seed = 0
        self._rng = random.Random(0)
        self._history_beliefs: list[StateBelief] = []
        self._last_fund_fp: dict[str, str | None] = {}
        self._fitted = False
        self._degrade_count = 0

    def fit(self, history: list[FeatureSnapshot], *, seed: int = 0) -> RuleStatStateEstimator:
        self._seed = seed
        self._rng = random.Random(seed)
        rows = [h.all_features() for h in history]
        if len(rows) >= self.min_history:
            self.scaler.fit(rows)
            self._fitted = True
        else:
            self._fitted = False
            self._degrade_count += 1
        return self

    def initialize(self, *, as_of: datetime, instrument_id: str | None = None) -> StateBelief:
        b = StateBelief.uniform_placeholder(
            as_of=as_of, instrument_id=instrument_id, is_synthetic=True
        )
        b.model_version = self.model_version
        if not self._fitted:
            b.degraded = True
            b.warnings = ["estimator_not_fitted_or_underidentified"]
        return b

    def update(
        self,
        *,
        as_of: datetime,
        features: FeatureSnapshot,
        prior: StateBelief | None = None,
        observations: list[ObservationRecord] | None = None,
    ) -> StateBelief:
        _ = observations  # unused in baseline; interface parity
        prior = prior or self.initialize(as_of=as_of, instrument_id=features.instrument_id)
        iid = features.instrument_id
        warnings: list[str] = []
        degraded = False

        raw = features.all_features()
        scaled = self.scaler.transform(raw) if self._fitted else raw

        # --- fundamental: only on new announcement ---
        fp = fingerprint_from_features(features)
        prev_fp = self._last_fund_fp.get(iid)
        if fundamental_observation_changed(prev_fp, features):
            fund = self._fundamental_logits(scaled)
            self._last_fund_fp[iid] = fp
        else:
            fund = dict(prior.fundamental)
            # Do not forge new fundamental observation
            if fp is None and all(v is None for v in features.fundamental.values()):
                warnings.append("no_fundamental_announcement_hold_prior")

        # --- market: daily from features; always mark gate ---
        market = self._market_logits(scaled)
        gate_passed = False  # Phase 2 default: not passed (TRE closed)

        # Under-identification: mostly missing features
        n_present = sum(1 for v in scaled.values() if v is not None)
        if n_present < 2:
            degraded = True
            warnings.append("underidentified_sparse_features")
            self._degrade_count += 1
            fund = {s.value: 1.0 / len(FundamentalState) for s in FundamentalState}
            market = {
                s.value: 1.0 / 3
                for s in (MarketState.RISK_ON, MarketState.NEUTRAL, MarketState.RISK_OFF)
            }

        # Tiny seed jitter for tie-breaking only (reproducible)
        jitter = self._rng.random() * 1e-9

        belief = StateBelief(
            as_of=as_of,
            instrument_id=iid,
            fundamental=fund,
            market=market,
            market_regime_gate_passed=gate_passed,
            is_synthetic=features.is_synthetic,
            model_version=self.model_version,
            degraded=degraded or not self._fitted,
            warnings=warnings
            + (["scaler_not_fitted"] if not self._fitted else []),
            diagnostics={"n_features_present": n_present, "jitter": jitter},
            feature_contributions={
                k: float(v) for k, v in scaled.items() if v is not None
            },
            input_snapshot_hash=features.snapshot_hash,
        )
        self._history_beliefs.append(belief)
        return belief

    def _fundamental_logits(self, scaled: dict[str, float | None]) -> dict[str, float]:
        margin = scaled.get("net_income_margin") or 0.0
        yoy = scaled.get("revenue_yoy") or 0.0
        cfo = scaled.get("cfo_to_ni") or 0.0
        logits = {
            FundamentalState.GROWTH.value: 0.5 * yoy + 0.3 * margin + 0.2 * cfo,
            FundamentalState.STABLE.value: 0.4 - abs(yoy) - 0.2 * abs(margin),
            FundamentalState.DETERIORATING.value: -0.6 * yoy - 0.4 * margin - 0.3 * cfo,
            FundamentalState.RECOVERING.value: 0.3 * yoy - 0.5 * abs(min(margin, 0.0)),
        }
        return _softmax(logits, self.temperature)

    def _market_logits(self, scaled: dict[str, float | None]) -> dict[str, float]:
        ret = scaled.get("mkt_ret_20d") or 0.0
        vol = scaled.get("mkt_vol_20d") or 0.0
        dd = scaled.get("mkt_drawdown_60d") or 0.0
        trend = scaled.get("mkt_trend_ma_gap") or 0.0
        logits = {
            MarketState.RISK_ON.value: 0.8 * ret + 0.5 * trend - 0.3 * vol,
            MarketState.NEUTRAL.value: 0.2 - abs(ret) - abs(trend),
            MarketState.RISK_OFF.value: -0.8 * ret - 0.6 * dd - 0.4 * vol,
        }
        return _softmax(logits, self.temperature)

    def diagnostics(self) -> dict[str, Any]:
        path = belief_path_diagnostics(self._history_beliefs)
        path.update(
            {
                "model_version": self.model_version,
                "fitted": self._fitted,
                "degrade_count": self._degrade_count,
                "seed": self._seed,
            }
        )
        return path
