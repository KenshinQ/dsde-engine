"""As-of / replay query API over PitStore."""

from __future__ import annotations

from datetime import date, datetime

from dsde.data.calendar import next_session_open, resolve_signal_execution
from dsde.data.pit_store import PitStore
from dsde.domain.errors import PitQueryError
from dsde.domain.schemas import (
    CorporateAction,
    FundamentalSnapshot,
    ObservationRecord,
    PriceBar,
    SignalExecutionTiming,
)


class AsOfQuery:
    """Read-only PIT views. Never returns rows with available_at > as_of."""

    def __init__(self, store: PitStore) -> None:
        self.store = store

    def assert_no_leakage(self, as_of: datetime, rows: list) -> None:
        for row in rows:
            avail = getattr(row, "available_at", None)
            if avail is None and hasattr(row, "announcement_time"):
                avail = row.announcement_time
            if avail is not None and avail > as_of:
                raise PitQueryError(
                    f"leakage: available_at {avail} > as_of {as_of} for {row!r}"
                )

    def prices(
        self,
        as_of: datetime,
        *,
        instrument_id: str | None = None,
        trade_date: date | None = None,
    ) -> list[PriceBar]:
        rows = self.store.prices_asof(
            as_of, instrument_id=instrument_id, trade_date=trade_date
        )
        self.assert_no_leakage(as_of, rows)
        return rows

    def fundamentals(
        self,
        as_of: datetime,
        *,
        instrument_id: str | None = None,
        period_end: date | None = None,
    ) -> list[FundamentalSnapshot]:
        rows = self.store.fundamentals_asof(
            as_of, instrument_id=instrument_id, period_end=period_end
        )
        self.assert_no_leakage(as_of, rows)
        return rows

    def observations(
        self,
        as_of: datetime,
        *,
        entity_id: str | None = None,
        feature_name: str | None = None,
    ) -> list[ObservationRecord]:
        rows = self.store.observations_asof(
            as_of, entity_id=entity_id, feature_name=feature_name
        )
        self.assert_no_leakage(as_of, rows)
        return rows

    def corporate_actions(
        self,
        as_of: datetime,
        *,
        instrument_id: str | None = None,
    ) -> list[CorporateAction]:
        rows = self.store.corporate_actions_asof(as_of, instrument_id=instrument_id)
        self.assert_no_leakage(as_of, rows)
        return rows

    def latest_fundamental(
        self, as_of: datetime, instrument_id: str
    ) -> FundamentalSnapshot | None:
        rows = self.fundamentals(as_of, instrument_id=instrument_id)
        if not rows:
            return None
        return max(rows, key=lambda f: (f.period_end, f.available_at or f.announcement_time))

    def price_on(
        self, as_of: datetime, instrument_id: str, trade_date: date
    ) -> PriceBar | None:
        rows = self.prices(as_of, instrument_id=instrument_id, trade_date=trade_date)
        return rows[0] if rows else None

    def signal_execution_timing(
        self,
        signal_time: datetime,
        *,
        signal_rule: str = "close",
        execution_rule: str = "next_open",
    ) -> SignalExecutionTiming:
        """Build timing contract; execution strictly after signal via calendar."""
        return resolve_signal_execution(
            self.store.calendar,
            signal_time=signal_time,
            signal_rule=signal_rule,
            execution_rule=execution_rule,
        )

    def next_execution_open(self, signal_time: datetime) -> datetime | None:
        return next_session_open(self.store.calendar, signal_time)
