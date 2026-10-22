"""In-memory PIT store with revision-aware ingest."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any

from dsde.data.providers import DataProvider
from dsde.data.quality import build_quality_report
from dsde.domain.enums import QualityFlag
from dsde.domain.schemas import (
    CorporateAction,
    FundamentalSnapshot,
    InstrumentMeta,
    ObservationRecord,
    PriceBar,
    QualityReport,
    TradingCalendar,
)


def _aware_key_dt(dt: datetime) -> datetime:
    """Normalize for comparison; naive treated as comparable among themselves."""
    return dt


class PitStore:
    """Point-in-time store. As-of queries never see available_at > as_of."""

    def __init__(self) -> None:
        self.instruments: dict[str, InstrumentMeta] = {}
        self.prices: list[PriceBar] = []
        self.fundamentals: list[FundamentalSnapshot] = []
        self.corporate_actions: list[CorporateAction] = []
        self.observations: list[ObservationRecord] = []
        self.calendar: TradingCalendar = TradingCalendar()
        self.last_quality_reports: list[QualityReport] = []

    def ingest_provider(self, provider: DataProvider) -> list[QualityReport]:
        """Load all tables from a provider and append quality reports."""
        reports: list[QualityReport] = []
        reports.append(self.ingest_instruments(provider.load_instruments(), source=provider.name))
        reports.append(self.ingest_prices(provider.load_prices(), source=provider.name))
        reports.append(
            self.ingest_fundamentals(provider.load_fundamentals(), source=provider.name)
        )
        reports.append(
            self.ingest_corporate_actions(
                provider.load_corporate_actions(), source=provider.name
            )
        )
        reports.append(
            self.ingest_observations(provider.load_observations(), source=provider.name)
        )
        cal = provider.load_calendar()
        if cal.days:
            self.calendar = cal
            reports.append(
                QualityReport(
                    source=provider.name,
                    record_count=len(cal.days),
                    accepted_count=len(cal.days),
                    notes=["calendar replaced"],
                    is_synthetic=any(
                        getattr(d, "is_synthetic", False) for d in []  # calendar days have no flag
                    ),
                )
            )
        self.last_quality_reports.extend(reports)
        return reports

    def ingest_instruments(
        self, rows: list[InstrumentMeta], *, source: str
    ) -> QualityReport:
        for row in rows:
            self.instruments[row.instrument_id] = row
        return build_quality_report(
            source=source,
            records=rows,
            is_synthetic=any(r.is_synthetic for r in rows),
            notes=["instruments"],
        )

    def ingest_prices(self, rows: list[PriceBar], *, source: str) -> QualityReport:
        key_counts: dict[tuple[Any, ...], int] = defaultdict(int)
        missing = 0
        for r in rows:
            key = (r.instrument_id, r.trade_date, r.revision_id)
            key_counts[key] += 1
            if r.close is None and not r.is_suspended:
                missing += 1
                if QualityFlag.MISSING not in r.quality_flags:
                    r.quality_flags = list(r.quality_flags) + [QualityFlag.MISSING]
        dups = [k for k, c in key_counts.items() if c > 1]
        self.prices.extend(rows)
        return build_quality_report(
            source=source,
            records=rows,
            duplicate_keys=dups,
            missing_field_count=missing,
            is_synthetic=any(r.is_synthetic for r in rows),
            notes=["prices"],
        )

    def ingest_fundamentals(
        self, rows: list[FundamentalSnapshot], *, source: str
    ) -> QualityReport:
        key_counts: dict[tuple[Any, ...], int] = defaultdict(int)
        for r in rows:
            key = (r.instrument_id, r.period_end, r.revision_id)
            key_counts[key] += 1
        dups = [k for k, c in key_counts.items() if c > 1]
        self.fundamentals.extend(rows)
        return build_quality_report(
            source=source,
            records=rows,
            duplicate_keys=dups,
            is_synthetic=any(r.is_synthetic for r in rows),
            notes=["fundamentals"],
        )

    def ingest_corporate_actions(
        self, rows: list[CorporateAction], *, source: str
    ) -> QualityReport:
        self.corporate_actions.extend(rows)
        return build_quality_report(
            source=source,
            records=rows,
            is_synthetic=any(r.is_synthetic for r in rows),
            notes=["corporate_actions"],
        )

    def ingest_observations(
        self, rows: list[ObservationRecord], *, source: str
    ) -> QualityReport:
        key_counts: dict[tuple[Any, ...], int] = defaultdict(int)
        for r in rows:
            key = (r.entity_id, r.feature_name, r.event_time, r.revision_id)
            key_counts[key] += 1
        dups = [k for k, c in key_counts.items() if c > 1]
        self.observations.extend(rows)
        return build_quality_report(
            source=source,
            records=rows,
            duplicate_keys=dups,
            is_synthetic=any(r.is_synthetic for r in rows),
            notes=["observations"],
        )

    # --- as-of helpers used by AsOfQuery ---

    def prices_asof(
        self,
        as_of: datetime,
        *,
        instrument_id: str | None = None,
        trade_date: date | None = None,
    ) -> list[PriceBar]:
        visible = [
            p
            for p in self.prices
            if _aware_key_dt(p.available_at) <= _aware_key_dt(as_of)
            and (instrument_id is None or p.instrument_id == instrument_id)
            and (trade_date is None or p.trade_date == trade_date)
        ]
        # Latest revision per (instrument, trade_date)
        best: dict[tuple[str, date], PriceBar] = {}
        for p in sorted(visible, key=lambda x: x.available_at):
            best[(p.instrument_id, p.trade_date)] = p
        return list(best.values())

    def fundamentals_asof(
        self,
        as_of: datetime,
        *,
        instrument_id: str | None = None,
        period_end: date | None = None,
    ) -> list[FundamentalSnapshot]:
        visible = [
            f
            for f in self.fundamentals
            if _aware_key_dt(f.available_at or f.announcement_time)
            <= _aware_key_dt(as_of)
            and (instrument_id is None or f.instrument_id == instrument_id)
            and (period_end is None or f.period_end == period_end)
        ]
        best: dict[tuple[str, date], FundamentalSnapshot] = {}
        for f in sorted(
            visible, key=lambda x: x.available_at or x.announcement_time
        ):
            best[(f.instrument_id, f.period_end)] = f
        return list(best.values())

    def observations_asof(
        self,
        as_of: datetime,
        *,
        entity_id: str | None = None,
        feature_name: str | None = None,
    ) -> list[ObservationRecord]:
        visible = [
            o
            for o in self.observations
            if _aware_key_dt(o.available_at) <= _aware_key_dt(as_of)
            and (entity_id is None or o.entity_id == entity_id)
            and (feature_name is None or o.feature_name == feature_name)
        ]
        best: dict[tuple[str, str, datetime], ObservationRecord] = {}
        for o in sorted(visible, key=lambda x: x.available_at):
            best[(o.entity_id, o.feature_name, o.event_time)] = o
        return list(best.values())

    def corporate_actions_asof(
        self,
        as_of: datetime,
        *,
        instrument_id: str | None = None,
    ) -> list[CorporateAction]:
        return [
            c
            for c in self.corporate_actions
            if _aware_key_dt(c.available_at) <= _aware_key_dt(as_of)
            and (instrument_id is None or c.instrument_id == instrument_id)
        ]

    def instrument_listed(self, instrument_id: str, on: date) -> bool | None:
        meta = self.instruments.get(instrument_id)
        if meta is None:
            return None
        return meta.is_listed_on(on)
