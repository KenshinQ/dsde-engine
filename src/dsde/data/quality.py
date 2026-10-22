"""Import quality reporting."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import Any

from dsde.domain.enums import QualityFlag
from dsde.domain.schemas import QualityReport


def build_quality_report(
    *,
    source: str,
    records: Iterable[Any],
    duplicate_keys: list[tuple[Any, ...]] | None = None,
    missing_field_count: int = 0,
    rejected_count: int = 0,
    is_synthetic: bool = False,
    notes: list[str] | None = None,
) -> QualityReport:
    rows = list(records)
    n = len(rows)
    flag_counts: Counter[str] = Counter()
    for r in rows:
        flags = getattr(r, "quality_flags", None) or []
        for f in flags:
            flag_counts[str(getattr(f, "value", f))] += 1
        if getattr(r, "is_suspended", False):
            flag_counts[QualityFlag.SUSPENDED.value] += 1

    dup = len(duplicate_keys or [])
    accepted = max(0, n - rejected_count)
    missing_rate = (missing_field_count / n) if n else 0.0
    duplicate_rate = (dup / n) if n else 0.0
    return QualityReport(
        source=source,
        record_count=n,
        accepted_count=accepted,
        rejected_count=rejected_count,
        duplicate_count=dup,
        missing_field_count=missing_field_count,
        missing_rate=missing_rate,
        duplicate_rate=duplicate_rate,
        quality_flags=dict(flag_counts),
        notes=list(notes or []),
        is_synthetic=is_synthetic,
    )
