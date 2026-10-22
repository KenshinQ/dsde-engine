"""Trading calendar helpers and signal/execution timing."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from dsde.domain.errors import DomainValidationError
from dsde.domain.schemas import CalendarDay, SignalExecutionTiming, TradingCalendar


def build_weekday_calendar(
    start: date,
    end: date,
    *,
    calendar_id: str = "XSHG",
    holidays: set[date] | None = None,
) -> TradingCalendar:
    holidays = holidays or set()
    days: list[CalendarDay] = []
    d = start
    while d <= end:
        is_td = d.weekday() < 5 and d not in holidays
        days.append(CalendarDay(calendar_id=calendar_id, day=d, is_trading_day=is_td))
        d += timedelta(days=1)
    return TradingCalendar(calendar_id=calendar_id, days=days)


def next_session_open(calendar: TradingCalendar, after: datetime) -> datetime | None:
    """Next trading day's open (09:30 local naive) strictly after `after`."""
    d = after.date()
    # If after is before open on a trading day, could use same day — Phase 1
    # default: always next trading day after signal date (close → next open).
    nxt = calendar.next_trading_day(d)
    if nxt is None:
        return None
    return datetime.combine(nxt, time(9, 30))


def resolve_signal_execution(
    calendar: TradingCalendar,
    *,
    signal_time: datetime,
    signal_rule: str = "close",
    execution_rule: str = "next_open",
) -> SignalExecutionTiming:
    if execution_rule != "next_open":
        raise DomainValidationError(f"unsupported execution_rule: {execution_rule}")
    exec_t = next_session_open(calendar, signal_time)
    if exec_t is None:
        raise DomainValidationError("no next trading day for execution_time")
    return SignalExecutionTiming(
        signal_time=signal_time,
        execution_time=exec_t,
        signal_rule=signal_rule,
        execution_rule=execution_rule,
    )
