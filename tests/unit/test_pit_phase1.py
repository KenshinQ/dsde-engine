"""Phase 1 PIT unit tests: as-of, revisions, calendar, quality, edge cases."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from dsde.data.asof_query import AsOfQuery
from dsde.data.pit_store import PitStore
from dsde.data.providers import FileJsonProvider
from dsde.data.synthetic import write_synthetic_bundle
from dsde.domain.enums import CorporateActionType, QualityFlag
from dsde.domain.errors import DomainValidationError
from dsde.domain.schemas import (
    PriceBar,
    SignalExecutionTiming,
)


@pytest.fixture()
def synth_dir(tmp_path: Path) -> Path:
    return write_synthetic_bundle(tmp_path / "synth")


@pytest.fixture()
def store(synth_dir: Path) -> PitStore:
    provider = FileJsonProvider(synth_dir, name="synthetic_fixture")
    s = PitStore()
    s.ingest_provider(provider)
    return s


def test_asof_never_returns_future_available_at(store: PitStore) -> None:
    q = AsOfQuery(store)
    as_of = datetime(2020, 1, 15, 15, 0, 0)
    prices = q.prices(as_of, instrument_id="SYN001.SH")
    assert prices
    assert all(p.available_at <= as_of for p in prices)
    funds = q.fundamentals(as_of, instrument_id="SYN001.SH")
    # Q4 2019 announced 2020-01-20 — not yet visible on Jan 15;
    # prior FY2018 period (announced 2019-01-20) may be visible.
    assert all(f.available_at <= as_of for f in funds)
    assert all(f.period_end.year <= 2018 for f in funds)


def test_period_end_vs_announcement_time_separated(store: PitStore) -> None:
    q = AsOfQuery(store)
    after_announce = datetime(2020, 1, 21, 0, 0, 0)
    funds = q.fundamentals(after_announce, instrument_id="SYN001.SH")
    assert len(funds) >= 1
    f = max(funds, key=lambda x: x.period_end)
    assert f.period_end == date(2019, 12, 31)
    assert f.announcement_time.date() == date(2020, 1, 20)
    assert f.period_end != f.announcement_time.date()


def test_revision_earlier_asof_sees_old_version(store: PitStore) -> None:
    q = AsOfQuery(store)
    early = q.latest_fundamental(datetime(2020, 1, 25), "SYN001.SH")
    late = q.latest_fundamental(datetime(2020, 2, 20), "SYN001.SH")
    assert early is not None and late is not None
    assert early.revision_id == "r0"
    assert early.financial_features["net_income"] == 10.0
    assert late.revision_id == "r1"
    assert late.financial_features["net_income"] == 9.5

    obs_early = q.observations(
        datetime(2020, 1, 12), entity_id="SYN001.SH", feature_name="analyst_note"
    )
    obs_late = q.observations(
        datetime(2020, 1, 30), entity_id="SYN001.SH", feature_name="analyst_note"
    )
    assert obs_early[0].value == "initial"
    assert obs_late[0].value == "updated"


def test_quality_report_on_import(synth_dir: Path) -> None:
    provider = FileJsonProvider(synth_dir)
    store = PitStore()
    reports = store.ingest_provider(provider)
    assert reports
    price_report = next(r for r in reports if "prices" in (r.notes or []))
    assert price_report.record_count > 0
    assert price_report.source
    assert price_report.accepted_count == price_report.record_count
    # suspension flag counted
    assert price_report.quality_flags.get("suspended", 0) >= 1


def test_suspension_flag(store: PitStore) -> None:
    q = AsOfQuery(store)
    bar = q.price_on(datetime(2020, 2, 3, 16, 0), "SYN001.SH", date(2020, 2, 3))
    assert bar is not None
    assert bar.is_suspended is True
    assert QualityFlag.SUSPENDED in bar.quality_flags or bar.close is None


def test_delist_meta(store: PitStore) -> None:
    meta = store.instruments["SYN002.SH"]
    assert meta.delist_date == date(2020, 6, 1)
    assert meta.is_listed_on(date(2020, 5, 31)) is True
    assert meta.is_listed_on(date(2020, 6, 1)) is False
    assert store.instrument_listed("SYN002.SH", date(2020, 6, 2)) is False


def test_corporate_action_asof(store: PitStore) -> None:
    q = AsOfQuery(store)
    before = q.corporate_actions(datetime(2020, 2, 10), instrument_id="SYN001.SH")
    after = q.corporate_actions(datetime(2020, 2, 21), instrument_id="SYN001.SH")
    assert before == []
    assert len(after) == 1
    assert after[0].action_type == CorporateActionType.DIVIDEND
    assert after[0].cash_amount == 0.1


def test_missing_and_duplicate_quality(tmp_path: Path) -> None:
    store = PitStore()
    avail = datetime(2020, 1, 2, 15, 0)
    rows = [
        PriceBar(
            instrument_id="X",
            trade_date=date(2020, 1, 2),
            available_at=avail,
            close=None,
            is_suspended=False,
            revision_id="r0",
        ),
        PriceBar(
            instrument_id="X",
            trade_date=date(2020, 1, 2),
            available_at=avail,
            close=1.0,
            revision_id="r0",
        ),
    ]
    report = store.ingest_prices(rows, source="dup_test")
    assert report.duplicate_count >= 1
    assert report.missing_field_count >= 1
    assert report.duplicate_rate > 0


def test_signal_vs_execution_time_separated(store: PitStore) -> None:
    signal = datetime(2020, 1, 3, 15, 0)  # Friday close-ish
    timing = AsOfQuery(store).signal_execution_timing(signal)
    assert timing.execution_time > timing.signal_time
    assert timing.signal_rule == "close"
    assert timing.execution_rule == "next_open"
    # Monday 2020-01-06 is next trading day after Fri Jan 3
    assert timing.execution_time.date() == date(2020, 1, 6)

    with pytest.raises(DomainValidationError):
        SignalExecutionTiming(
            signal_time=signal,
            execution_time=signal,
        )


def test_file_adapter_roundtrip(synth_dir: Path) -> None:
    p = FileJsonProvider(synth_dir)
    assert p.load_instruments()
    assert p.load_prices()
    assert p.load_fundamentals()
    assert p.load_corporate_actions()
    assert p.load_calendar().days
    assert p.load_observations()
