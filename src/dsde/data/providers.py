"""Provider-agnostic data adapter interface + file-based example."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from dsde.domain.enums import CorporateActionType, QualityFlag
from dsde.domain.errors import DataImportError
from dsde.domain.schemas import (
    CalendarDay,
    CorporateAction,
    FundamentalSnapshot,
    InstrumentMeta,
    ObservationRecord,
    PriceBar,
    TradingCalendar,
)


def _parse_dt(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    # Accept ISO with or without Z
    text = value.replace("Z", "+00:00") if value.endswith("Z") else value
    return datetime.fromisoformat(text)


def _parse_date(value: str | date) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return date.fromisoformat(str(value)[:10])


@runtime_checkable
class DataProvider(Protocol):
    """Source-agnostic adapter: load typed records into memory structures."""

    name: str

    def load_instruments(self) -> list[InstrumentMeta]: ...

    def load_prices(self) -> list[PriceBar]: ...

    def load_fundamentals(self) -> list[FundamentalSnapshot]: ...

    def load_corporate_actions(self) -> list[CorporateAction]: ...

    def load_calendar(self) -> TradingCalendar: ...

    def load_observations(self) -> list[ObservationRecord]: ...


class FileJsonProvider:
    """File-based adapter example: reads a directory of JSON / JSONL files.

    Expected layout (missing files → empty lists):
      instruments.json
      prices.jsonl
      fundamentals.jsonl
      corporate_actions.jsonl
      calendar.json
      observations.jsonl
    """

    def __init__(self, root: Path | str, *, name: str | None = None) -> None:
        self.root = Path(root)
        self.name = name or f"file_json:{self.root.name}"
        if not self.root.is_dir():
            raise DataImportError(f"provider root not found: {self.root}")

    def _read_json(self, name: str) -> Any:
        path = self.root / name
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def _read_jsonl(self, name: str) -> list[dict[str, Any]]:
        path = self.root / name
        if not path.is_file():
            return []
        rows: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
        return rows

    def load_instruments(self) -> list[InstrumentMeta]:
        raw = self._read_json("instruments.json") or []
        out: list[InstrumentMeta] = []
        for row in raw:
            out.append(
                InstrumentMeta(
                    instrument_id=row["instrument_id"],
                    exchange=row.get("exchange", "XSHG"),
                    list_date=_parse_date(row["list_date"])
                    if row.get("list_date")
                    else None,
                    delist_date=_parse_date(row["delist_date"])
                    if row.get("delist_date")
                    else None,
                    is_synthetic=bool(row.get("is_synthetic", False)),
                )
            )
        return out

    def load_prices(self) -> list[PriceBar]:
        out: list[PriceBar] = []
        for row in self._read_jsonl("prices.jsonl"):
            flags = [QualityFlag(x) for x in row.get("quality_flags", ["ok"])]
            out.append(
                PriceBar(
                    instrument_id=row["instrument_id"],
                    trade_date=_parse_date(row["trade_date"]),
                    available_at=_parse_dt(row["available_at"]),
                    open=row.get("open"),
                    high=row.get("high"),
                    low=row.get("low"),
                    close=row.get("close"),
                    volume=row.get("volume"),
                    amount=row.get("amount"),
                    adj_factor=row.get("adj_factor", 1.0),
                    is_suspended=bool(row.get("is_suspended", False)),
                    limit_up=row.get("limit_up"),
                    limit_down=row.get("limit_down"),
                    quality_flags=flags,
                    source=row.get("source", self.name),
                    revision_id=row.get("revision_id"),
                    is_synthetic=bool(row.get("is_synthetic", False)),
                )
            )
        return out

    def load_fundamentals(self) -> list[FundamentalSnapshot]:
        out: list[FundamentalSnapshot] = []
        for row in self._read_jsonl("fundamentals.jsonl"):
            flags = [QualityFlag(x) for x in row.get("quality_flags", ["ok"])]
            announce = _parse_dt(row["announcement_time"])
            out.append(
                FundamentalSnapshot(
                    instrument_id=row["instrument_id"],
                    period_start=_parse_date(row["period_start"]),
                    period_end=_parse_date(row["period_end"]),
                    announcement_time=announce,
                    available_at=_parse_dt(row["available_at"])
                    if row.get("available_at")
                    else announce,
                    financial_features=row.get("financial_features") or {},
                    cash_flow_features=row.get("cash_flow_features") or {},
                    balance_sheet_features=row.get("balance_sheet_features") or {},
                    quality_flags=flags,
                    source_version=row.get("source_version", "v1"),
                    revision_id=row.get("revision_id"),
                    is_synthetic=bool(row.get("is_synthetic", False)),
                )
            )
        return out

    def load_corporate_actions(self) -> list[CorporateAction]:
        out: list[CorporateAction] = []
        for row in self._read_jsonl("corporate_actions.jsonl"):
            out.append(
                CorporateAction(
                    instrument_id=row["instrument_id"],
                    action_type=CorporateActionType(row["action_type"]),
                    ex_date=_parse_date(row["ex_date"]),
                    available_at=_parse_dt(row["available_at"]),
                    record_date=_parse_date(row["record_date"])
                    if row.get("record_date")
                    else None,
                    pay_date=_parse_date(row["pay_date"]) if row.get("pay_date") else None,
                    cash_amount=row.get("cash_amount"),
                    ratio=row.get("ratio"),
                    source=row.get("source", self.name),
                    revision_id=row.get("revision_id"),
                    is_synthetic=bool(row.get("is_synthetic", False)),
                )
            )
        return out

    def load_calendar(self) -> TradingCalendar:
        raw = self._read_json("calendar.json") or {"calendar_id": "XSHG", "days": []}
        days = [
            CalendarDay(
                calendar_id=raw.get("calendar_id", "XSHG"),
                day=_parse_date(d["day"]),
                is_trading_day=bool(d.get("is_trading_day", True)),
            )
            for d in raw.get("days", [])
        ]
        return TradingCalendar(calendar_id=raw.get("calendar_id", "XSHG"), days=days)

    def load_observations(self) -> list[ObservationRecord]:
        out: list[ObservationRecord] = []
        for row in self._read_jsonl("observations.jsonl"):
            flags = [QualityFlag(x) for x in row.get("quality_flags", ["ok"])]
            out.append(
                ObservationRecord(
                    entity_id=row.get("entity_id") or row["instrument_id"],
                    feature_name=row["feature_name"],
                    value=row.get("value"),
                    event_time=_parse_dt(row["event_time"]),
                    available_at=_parse_dt(row["available_at"]),
                    ingested_at=_parse_dt(row["ingested_at"])
                    if row.get("ingested_at")
                    else None,
                    source=row.get("source", self.name),
                    revision_id=row.get("revision_id"),
                    quality_flags=flags,
                    units=row.get("units"),
                    is_synthetic=bool(row.get("is_synthetic", False)),
                )
            )
        return out
