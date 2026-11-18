from __future__ import annotations

from datetime import date

import pytest

from src.targets.calendar import resolve_target_sessions
from src.targets.config import TargetConfig
from src.targets.pipeline import TargetPipelineError


def _config(start: date, end: date) -> TargetConfig:
    return TargetConfig(
        start_date=start,
        end_date=end,
        target_version="2.0.0",
        market="XNYS",
        input_path="data/curated/market_prices_daily.parquet",
        output_path="data/curated/asset_volatility_labels.parquet",
        manifest_dir="data/audit/targets",
    )


def test_calendar_window_uses_xnys_sessions_and_excludes_warmup_anchors() -> None:
    config = _config(date(2026, 1, 16), date(2026, 1, 21))

    expected, anchors = resolve_target_sessions(
        config,
        source_dates=(
            date(2026, 1, 12),
            date(2026, 1, 13),
            date(2026, 1, 14),
            date(2026, 1, 15),
            date(2026, 1, 16),
            date(2026, 1, 20),
            date(2026, 1, 21),
        ),
    )

    assert anchors == (date(2026, 1, 16), date(2026, 1, 20), date(2026, 1, 21))
    assert date(2026, 1, 19) not in expected
    assert expected[expected.index(date(2026, 1, 16)) + 1] == date(2026, 1, 20)
    assert len(expected) >= expected.index(date(2026, 1, 21)) + 6


def test_calendar_window_rejects_non_session_scope_boundary() -> None:
    config = _config(date(2026, 1, 16), date(2026, 1, 19))

    with pytest.raises(TargetPipelineError, match="XNYS session"):
        resolve_target_sessions(
            config,
            source_dates=(date(2026, 1, 12), date(2026, 1, 20)),
        )
