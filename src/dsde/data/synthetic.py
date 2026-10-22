"""Synthetic PIT dataset writer for Phase 1 tests and demos."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, time
from pathlib import Path

from dsde.data.calendar import build_weekday_calendar


def write_synthetic_bundle(root: Path | str) -> Path:
    """Write a small synthetic A-share-like bundle under `root`. Returns root."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)

    instruments = [
        {
            "instrument_id": "SYN001.SH",
            "exchange": "XSHG",
            "list_date": "2019-01-02",
            "delist_date": None,
            "is_synthetic": True,
        },
        {
            "instrument_id": "SYN002.SH",
            "exchange": "XSHG",
            "list_date": "2019-01-02",
            "delist_date": "2020-06-01",
            "is_synthetic": True,
        },
    ]
    (root / "instruments.json").write_text(
        json.dumps(instruments, indent=2), encoding="utf-8"
    )

    cal = build_weekday_calendar(date(2019, 11, 1), date(2020, 3, 31))
    cal_doc = {
        "calendar_id": cal.calendar_id,
        "days": [
            {"day": d.day.isoformat(), "is_trading_day": d.is_trading_day}
            for d in cal.days
        ],
    }
    (root / "calendar.json").write_text(json.dumps(cal_doc, indent=2), encoding="utf-8")

    # Prices: SYN001 normal + one suspension; SYN002 until delist
    price_lines: list[str] = []
    for d in cal.days:
        if not d.is_trading_day:
            continue
        avail = datetime.combine(d.day, time(15, 0))
        suspended = d.day == date(2020, 2, 3)
        row = {
            "instrument_id": "SYN001.SH",
            "trade_date": d.day.isoformat(),
            "available_at": avail.isoformat(),
            "open": 10.0,
            "high": 10.5,
            "low": 9.8,
            "close": None if suspended else 10.2,
            "volume": 0.0 if suspended else 1_000_000.0,
            "is_suspended": suspended,
            "quality_flags": ["suspended"] if suspended else ["ok"],
            "source": "synthetic",
            "revision_id": "r0",
            "is_synthetic": True,
        }
        price_lines.append(json.dumps(row))
        if d.day < date(2020, 6, 1) and d.day <= date(2020, 3, 31):
            row2 = {
                **row,
                "instrument_id": "SYN002.SH",
                "close": 5.0,
                "is_suspended": False,
                "quality_flags": ["ok"],
                "volume": 500_000.0,
            }
            price_lines.append(json.dumps(row2))
    (root / "prices.jsonl").write_text("\n".join(price_lines) + "\n", encoding="utf-8")

    # Fundamentals: period_end Q4 2019, announced later; then a revision
    fund_rows = [
        {
            "instrument_id": "SYN001.SH",
            "period_start": "2018-10-01",
            "period_end": "2018-12-31",
            "announcement_time": "2019-01-20T18:00:00",
            "available_at": "2019-01-20T18:00:00",
            "financial_features": {"revenue": 90.0, "net_income": 8.0},
            "cash_flow_features": {"cfo": 7.0},
            "balance_sheet_features": {"total_assets": 450.0},
            "source_version": "v1",
            "revision_id": "r0",
            "quality_flags": ["ok"],
            "is_synthetic": True,
        },
        {
            "instrument_id": "SYN001.SH",
            "period_start": "2019-10-01",
            "period_end": "2019-12-31",
            "announcement_time": "2020-01-20T18:00:00",
            "available_at": "2020-01-20T18:00:00",
            "financial_features": {"revenue": 100.0, "net_income": 10.0},
            "cash_flow_features": {"cfo": 8.0},
            "balance_sheet_features": {"total_assets": 500.0},
            "source_version": "v1",
            "revision_id": "r0",
            "quality_flags": ["ok"],
            "is_synthetic": True,
        },
        {
            "instrument_id": "SYN001.SH",
            "period_start": "2019-10-01",
            "period_end": "2019-12-31",
            "announcement_time": "2020-02-15T18:00:00",
            "available_at": "2020-02-15T18:00:00",
            "financial_features": {"revenue": 100.0, "net_income": 9.5},
            "cash_flow_features": {"cfo": 7.5},
            "balance_sheet_features": {"total_assets": 500.0},
            "source_version": "v2",
            "revision_id": "r1",
            "quality_flags": ["revised"],
            "is_synthetic": True,
        },
    ]
    (root / "fundamentals.jsonl").write_text(
        "\n".join(json.dumps(r) for r in fund_rows) + "\n", encoding="utf-8"
    )

    actions = [
        {
            "instrument_id": "SYN001.SH",
            "action_type": "dividend",
            "ex_date": "2020-03-10",
            "available_at": "2020-02-20T09:00:00",
            "cash_amount": 0.1,
            "source": "synthetic",
            "revision_id": "r0",
            "is_synthetic": True,
        }
    ]
    (root / "corporate_actions.jsonl").write_text(
        "\n".join(json.dumps(r) for r in actions) + "\n", encoding="utf-8"
    )

    # Generic observations with revisions
    obs = [
        {
            "entity_id": "SYN001.SH",
            "feature_name": "analyst_note",
            "value": "initial",
            "event_time": "2020-01-10T00:00:00",
            "available_at": "2020-01-10T12:00:00",
            "revision_id": "r0",
            "is_synthetic": True,
            "quality_flags": ["ok"],
        },
        {
            "entity_id": "SYN001.SH",
            "feature_name": "analyst_note",
            "value": "updated",
            "event_time": "2020-01-10T00:00:00",
            "available_at": "2020-01-25T12:00:00",
            "revision_id": "r1",
            "is_synthetic": True,
            "quality_flags": ["revised"],
        },
    ]
    (root / "observations.jsonl").write_text(
        "\n".join(json.dumps(r) for r in obs) + "\n", encoding="utf-8"
    )

    meta = {
        "generated_at": datetime.now(UTC).isoformat(),
        "is_synthetic": True,
        "note": "DSDE Phase 1 synthetic bundle — not for investment conclusions",
    }
    (root / "MANIFEST.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return root
