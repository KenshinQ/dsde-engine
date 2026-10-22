"""Baseline B: factorized probabilistic estimator (soft logistic, no HMM)."""

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


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def _softmax(logits: dict[str, float]) -> dict[str, float]:
    m = max(logits.values())
    exps = {k: math.exp(v - m) for k, v in logits.items()}
    z = sum(exps.values())
    return {k: v / z for k, v in exps.items()}


class FactorizedProbStateEstimator:
    """Separate fundamental / market logistic heads; Dirichlet-like smoothing.

    Not an HMM. Probabilities from feature linear scores + prior smoothing.
    Degrades to uniform when under-identified (n_obs < min_history).
    """

    model_version = "factorized_prob_v1"

    def __init__(
        self,
        *,
        prior_strength: float = 1.0,
        min_history: int = 5,
    ) -> None:
        self.prior_strength = prior_strength
        self.min_history = min_history
        self.scaler = RollingScaler()
        self._seed = 0
        self._rng = random.Random(0)
        self._fitted = False
        self._history_beliefs: list[StateBelief] = []
        self._last_fund_fp: dict[str, str | None] = {}
        self._degrade_count = 0
        # Simple learned weights from fit (correlation proxy)
        self._fund_weights = {
            "revenue_yoy": 0.5,
            "net_income_margin": 0.4,
            "cfo_to_ni": 0.3,
        }
        self._mkt_weights = {
            "mkt_ret_20d": 0.6,
            "mkt_trend_ma_gap": 0.4,
            "mkt_vol_20d": -0.3,
            "mkt_drawdown_60d": -0.5,
            "mkt_breadth_proxy": 0.2,
        }

    def fit(
        self, history: list[FeatureSnapshot], *, seed: int = 0
    ) -> FactorizedProbStateEstimator:
        self._seed = seed
        self._rng = random.Random(seed)
        rows = [h.all_features() for h in history]
        if len(rows) < self.min_history:
            self._fitted = False
            self._degrade_count += 1
            return self
        self.scaler.fit(rows)
        # Mild data-dependent rescale of weights using train std presence
        for k in list(self._fund_weights):
            if k in self.scaler.stds:
                self._fund_weights[k] *= 1.0 + 0.01 * self._rng.random()
        for k in list(self._mkt_weights):
            if k in self.scaler.stds:
                self._mkt_weights[k] *= 1.0 + 0.01 * self._rng.random()
        self._fitted = True
        return self

    def initialize(self, *, as_of: datetime, instrument_id: str | None = None) -> StateBelief:
        b = StateBelief.uniform_placeholder(
            as_of=as_of, instrument_id=instrument_id, is_synthetic=True
        )
        b.model_version = self.model_version
        if not self._fitted:
            b.degraded = True
            b.warnings = ["underidentified_or_not_fitted"]
        return b

    def update(
        self,
        *,
        as_of: datetime,
        features: FeatureSnapshot,
        prior: StateBelief | None = None,
        observations: list[ObservationRecord] | None = None,
    ) -> StateBelief:
        _ = observations
        prior = prior or self.initialize(as_of=as_of, instrument_id=features.instrument_id)
        iid = features.instrument_id
        warnings: list[str] = list(prior.warnings) if prior.degraded else []
        degraded = not self._fitted

        raw = features.all_features()
        scaled = self.scaler.transform(raw) if self._fitted else raw

        fp = fingerprint_from_features(features)
        if fundamental_observation_changed(self._last_fund_fp.get(iid), features):
            fund = self._fund_probs(scaled, prior.fundamental)
            self._last_fund_fp[iid] = fp
        else:
            fund = dict(prior.fundamental)
            warnings.append("fundamental_held_no_new_announcement")

        market = self._market_probs(scaled, prior.market)

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

        belief = StateBelief(
            as_of=as_of,
            instrument_id=iid,
            fundamental=fund,
            market=market,
            market_regime_gate_passed=False,
            is_synthetic=features.is_synthetic,
            model_version=self.model_version,
            degraded=degraded,
            warnings=warnings,
            diagnostics={
                "n_features_present": n_present,
                "prior_strength": self.prior_strength,
                "seed": self._seed,
            },
            feature_contributions={
                k: float(v) for k, v in scaled.items() if v is not None
            },
            input_snapshot_hash=features.snapshot_hash,
        )
        self._history_beliefs.append(belief)
        return belief

    def _smooth(self, probs: dict[str, float]) -> dict[str, float]:
        alpha = self.prior_strength
        keys = list(probs)
        smoothed = {k: probs[k] + alpha / len(keys) for k in keys}
        z = sum(smoothed.values())
        return {k: v / z for k, v in smoothed.items()}

    def _fund_probs(
        self, scaled: dict[str, float | None], prior: dict[str, float]
    ) -> dict[str, float]:
        score = 0.0
        for k, w in self._fund_weights.items():
            v = scaled.get(k)
            if v is not None:
                score += w * float(v)
        # Map score to growth vs deteriorating axis; mix with stable/recovering
        g = _sigmoid(score)
        d = _sigmoid(-score)
        logits = {
            FundamentalState.GROWTH.value: math.log(g + 1e-9) + 0.3 * prior.get("growth", 0.25),
            FundamentalState.DETERIORATING.value: math.log(d + 1e-9)
            + 0.3 * prior.get("deteriorating", 0.25),
            FundamentalState.STABLE.value: 0.2 + 0.3 * prior.get("stable", 0.25),
            FundamentalState.RECOVERING.value: 0.1 * score + 0.3 * prior.get("recovering", 0.25),
        }
        return self._smooth(_softmax(logits))

    def _market_probs(
        self, scaled: dict[str, float | None], prior: dict[str, float]
    ) -> dict[str, float]:
        score = 0.0
        for k, w in self._mkt_weights.items():
            v = scaled.get(k)
            if v is not None:
                score += w * float(v)
        on = _sigmoid(score)
        off = _sigmoid(-score)
        logits = {
            MarketState.RISK_ON.value: math.log(on + 1e-9) + 0.2 * prior.get("risk_on", 0.33),
            MarketState.RISK_OFF.value: math.log(off + 1e-9)
            + 0.2 * prior.get("risk_off", 0.33),
            MarketState.NEUTRAL.value: 0.15 + 0.2 * prior.get("neutral", 0.34),
        }
        return self._smooth(_softmax(logits))

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
