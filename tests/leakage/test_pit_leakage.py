"""PIT leakage tests: future injection must not change earlier as-of views."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from dsde.data.asof_query import AsOfQuery
from dsde.data.pit_store import PitStore
from dsde.data.providers import FileJsonProvider
from dsde.data.synthetic import write_synthetic_bundle
from dsde.domain.schemas import FundamentalSnapshot, ObservationRecord, PriceBar


def _snap_fund(f: FundamentalSnapshot) -> tuple:
    return (
        f.instrument_id,
        f.period_end,
        f.revision_id,
        f.financial_features.get("net_income"),
        f.available_at,
    )


def test_future_injection_does_not_change_earlier_asof(tmp_path: Path) -> None:
    root = write_synthetic_bundle(tmp_path / "synth")
    store = PitStore()
    store.ingest_provider(FileJsonProvider(root))
    q = AsOfQuery(store)

    as_of = datetime(2020, 1, 21, 12, 0, 0)
    before_funds = [_snap_fund(f) for f in q.fundamentals(as_of, instrument_id="SYN001.SH")]
    before_prices = [
        (p.trade_date, p.close, p.revision_id)
        for p in sorted(
            q.prices(as_of, instrument_id="SYN001.SH"), key=lambda x: x.trade_date
        )
    ]
    before_obs = [
        (o.value, o.revision_id)
        for o in q.observations(as_of, entity_id="SYN001.SH", feature_name="analyst_note")
    ]

    # Inject "future" fundamentals revision and price bar with available_at >> as_of
    store.ingest_fundamentals(
        [
            FundamentalSnapshot(
                instrument_id="SYN001.SH",
                period_start=date(2019, 10, 1),
                period_end=date(2019, 12, 31),
                announcement_time=datetime(2020, 6, 1, 18, 0),
                available_at=datetime(2020, 6, 1, 18, 0),
                financial_features={"revenue": 100.0, "net_income": 1.0},
                revision_id="r_future_leak",
                is_synthetic=True,
            )
        ],
        source="leak_inject",
    )
    store.ingest_prices(
        [
            PriceBar(
                instrument_id="SYN001.SH",
                trade_date=date(2020, 1, 2),
                available_at=datetime(2020, 6, 1, 15, 0),
                close=999.0,
                revision_id="r_future_price",
                is_synthetic=True,
            )
        ],
        source="leak_inject",
    )
    store.ingest_observations(
        [
            ObservationRecord(
                entity_id="SYN001.SH",
                feature_name="analyst_note",
                value="should_not_see",
                event_time=datetime(2020, 1, 10),
                available_at=datetime(2020, 6, 1, 12, 0),
                revision_id="r_future_obs",
                is_synthetic=True,
            )
        ],
        source="leak_inject",
    )

    after_funds = [_snap_fund(f) for f in q.fundamentals(as_of, instrument_id="SYN001.SH")]
    after_prices = [
        (p.trade_date, p.close, p.revision_id)
        for p in sorted(
            q.prices(as_of, instrument_id="SYN001.SH"), key=lambda x: x.trade_date
        )
    ]
    after_obs = [
        (o.value, o.revision_id)
        for o in q.observations(as_of, entity_id="SYN001.SH", feature_name="analyst_note")
    ]

    assert after_funds == before_funds
    assert after_prices == before_prices
    assert after_obs == before_obs

    # Sanity: later as_of can see the injected revision
    late = q.latest_fundamental(datetime(2020, 6, 2), "SYN001.SH")
    assert late is not None
    assert late.revision_id == "r_future_leak"


def test_asof_api_asserts_no_leakage_invariant(tmp_path: Path) -> None:
    root = write_synthetic_bundle(tmp_path / "synth")
    store = PitStore()
    store.ingest_provider(FileJsonProvider(root))
    q = AsOfQuery(store)
    as_of = datetime(2020, 2, 1)
    for row in q.prices(as_of):
        assert row.available_at <= as_of
    for row in q.fundamentals(as_of):
        assert (row.available_at or row.announcement_time) <= as_of
    for row in q.observations(as_of):
        assert row.available_at <= as_of
    for row in q.corporate_actions(as_of):
        assert row.available_at <= as_of
