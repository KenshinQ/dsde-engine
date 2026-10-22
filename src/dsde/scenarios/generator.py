"""ScenarioGenerator: belief × transitions → future paths with provenance."""

from __future__ import annotations

import random

from dsde.domain.schemas import (
    ScenarioBatch,
    ScenarioPath,
    StateBelief,
    TransitionMatrix,
)
from dsde.scenarios.sampling import sample_categorical, sample_from_row
from dsde.transitions.estimator import (
    TransitionEstimator,
    default_fundamental_estimator,
    default_market_estimator,
)


class ScenarioGenerator:
    """Generate factorized fundamental/market paths.

    Parameter uncertainty (bootstrap draws) uses `parameter_seed`;
    process noise uses `process_seed` — recorded separately on each path.
    """

    def __init__(
        self,
        *,
        max_paths: int = 500,
        max_steps: int = 60,
        fund_estimator: TransitionEstimator | None = None,
        market_estimator: TransitionEstimator | None = None,
    ) -> None:
        self.max_paths = max_paths
        self.max_steps = max_steps
        self.fund_estimator = fund_estimator or default_fundamental_estimator()
        self.market_estimator = market_estimator or default_market_estimator()

    def generate(
        self,
        belief: StateBelief,
        *,
        steps: int,
        n_paths: int,
        seed: int = 0,
        fund_labels_history: list[str] | None = None,
        market_labels_history: list[str] | None = None,
        n_parameter_draws: int = 1,
        include_assumption_scenarios: bool = False,
        assumption_tags: list[str] | None = None,
    ) -> ScenarioBatch:
        if steps < 1:
            raise ValueError("steps must be >= 1")
        if n_paths < 1:
            raise ValueError("n_paths must be >= 1")

        notes: list[str] = []
        capped = False
        n_req = n_paths
        if n_paths > self.max_paths:
            notes.append(f"capped_paths:{n_paths}->{self.max_paths}")
            n_paths = self.max_paths
            capped = True
        if steps > self.max_steps:
            notes.append(f"capped_steps:{steps}->{self.max_steps}")
            steps = self.max_steps
            capped = True

        # Point estimates from history (estimated_probability only)
        fund_hist = fund_labels_history or []
        mkt_hist = market_labels_history or []
        fund_point = self.fund_estimator.estimate(fund_hist, seed=seed)
        mkt_point = self.market_estimator.estimate(mkt_hist, seed=seed)

        # Parameter draws (uncertainty) — separate RNG stream
        param_seed = seed + 10_000
        process_seed = seed + 20_000
        fund_draws = self.fund_estimator.sample_parameters(
            n=max(1, n_parameter_draws), seed=param_seed, labels=fund_hist
        )
        mkt_draws = self.market_estimator.sample_parameters(
            n=max(1, n_parameter_draws), seed=param_seed + 1, labels=mkt_hist
        )

        paths: list[ScenarioPath] = []
        proc_rng = random.Random(process_seed)

        for i in range(n_paths):
            draw_i = i % len(fund_draws)
            fund_tm = fund_draws[draw_i]
            mkt_tm = mkt_draws[draw_i % len(mkt_draws)]
            # Per-path process RNG derived from process_seed + i
            path_proc_seed = process_seed + i * 997
            path_rng = random.Random(path_proc_seed)

            f0 = sample_categorical(belief.fundamental, path_rng)
            m0 = sample_categorical(belief.market, path_rng)
            # Ensure start distribution sampling is from belief (provenance)
            f_path = [f0]
            m_path = [m0]
            for _ in range(steps - 1):
                f_path.append(self._step(fund_tm, f_path[-1], path_rng))
                m_path.append(self._step(mkt_tm, m_path[-1], path_rng))

            paths.append(
                ScenarioPath(
                    scenario_id=f"est-{seed}-{i}",
                    seed=seed,
                    path_steps=steps,
                    fundamental_path=f_path,
                    market_path=m_path,
                    start_fundamental_probs=dict(belief.fundamental),
                    start_market_probs=dict(belief.market),
                    parameter_draw_id=f"param-{draw_i}",
                    scenario_weight=1.0 / n_paths,
                    assumption_tags=[],
                    probability_kind="estimated_probability",
                    process_rng_seed=path_proc_seed,
                    parameter_rng_seed=param_seed,
                    transition_model_version=fund_point.model_version,
                    provenance={
                        "fund_n_obs": fund_tm.n_obs,
                        "market_n_obs": mkt_tm.n_obs,
                        "fund_degraded": fund_tm.degraded,
                        "market_degraded": mkt_tm.degraded,
                        "fund_warnings": list(fund_tm.rare_state_warnings),
                        "market_warnings": list(mkt_tm.rare_state_warnings),
                        "point_fund_kind": fund_point.kind,
                        "belief_as_of": belief.as_of.isoformat(),
                        "instrument_id": belief.instrument_id,
                    },
                    is_synthetic=belief.is_synthetic,
                )
            )

        if include_assumption_scenarios:
            # Explicit non-statistical sticky stress — NEVER mixed into estimated probs
            tags = assumption_tags or ["expert_sticky_stress"]
            assum_fund = TransitionEstimator(
                states=list(fund_point.states),
                kind="assumption_scenario",
            ).estimate([])
            assum_mkt = TransitionEstimator(
                states=list(mkt_point.states),
                kind="assumption_scenario",
            ).estimate([])
            # Add a small number (capped) of assumption paths
            n_assume = min(max(1, n_paths // 10), 10)
            for j in range(n_assume):
                if len(paths) >= self.max_paths:
                    notes.append("assumption_paths_skipped_at_cap")
                    break
                a_seed = process_seed + 50_000 + j
                rng = random.Random(a_seed)
                f0 = sample_categorical(belief.fundamental, rng)
                m0 = sample_categorical(belief.market, rng)
                f_path = [f0]
                m_path = [m0]
                for _ in range(steps - 1):
                    f_path.append(self._step(assum_fund, f_path[-1], rng))
                    m_path.append(self._step(assum_mkt, m_path[-1], rng))
                paths.append(
                    ScenarioPath(
                        scenario_id=f"assume-{seed}-{j}",
                        seed=seed,
                        path_steps=steps,
                        fundamental_path=f_path,
                        market_path=m_path,
                        start_fundamental_probs=dict(belief.fundamental),
                        start_market_probs=dict(belief.market),
                        parameter_draw_id=None,
                        scenario_weight=0.0,  # not part of statistical measure
                        assumption_tags=list(tags),
                        probability_kind="assumption_scenario",
                        process_rng_seed=a_seed,
                        parameter_rng_seed=None,
                        transition_model_version=assum_fund.model_version,
                        provenance={
                            "note": "assumption_scenario_excluded_from_estimated_probability",
                            "tags": list(tags),
                        },
                        is_synthetic=belief.is_synthetic,
                    )
                )
            notes.append(f"assumption_scenarios_added:{n_assume}")

        # Consume proc_rng once so interface stays available for extensions
        _ = proc_rng.random()

        return ScenarioBatch(
            paths=paths,
            n_requested=n_req,
            n_generated=len(paths),
            n_capped=capped,
            max_paths_cap=self.max_paths,
            max_steps_cap=self.max_steps,
            seed=seed,
            notes=notes,
        )

    @staticmethod
    def _step(tm: TransitionMatrix, state: str, rng: random.Random) -> str:
        try:
            i = tm.states.index(state)
        except ValueError:
            i = 0
        return sample_from_row(tm.states, tm.matrix[i], rng)

    def predict_marginals(
        self,
        belief: StateBelief,
        transition: TransitionMatrix,
        *,
        steps: int,
    ) -> list[dict[str, float]]:
        """Multi-step predictive distribution from belief × P (for frequency checks)."""
        states = transition.states
        p = [
            belief.fundamental.get(s, 0.0)
            if s in belief.fundamental
            else belief.market.get(s, 0.0)
            for s in states
        ]
        # Normalize in case belief keys differ
        ssum = sum(p)
        if ssum <= 0:
            p = [1.0 / len(states)] * len(states)
        else:
            p = [x / ssum for x in p]
        out = [dict(zip(states, p, strict=True))]
        for _ in range(steps - 1):
            nxt = [0.0] * len(states)
            for i, pi in enumerate(p):
                for j, pij in enumerate(transition.matrix[i]):
                    nxt[j] += pi * pij
            p = nxt
            out.append(dict(zip(states, p, strict=True)))
        return out
