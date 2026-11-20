from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable

import pandas as pd

from src.targets.config import TargetConfig
from src.targets.pipeline import TargetPipelineError


def _market_date(value: date | str) -> date:
    try:
        stamp = pd.Timestamp(value)
    except (TypeError, ValueError) as error:
        raise TargetPipelineError("market_prices_daily contains an invalid date") from error
    if pd.isna(stamp):
        raise TargetPipelineError("market_prices_daily contains an invalid date")
    return stamp.date()


def resolve_target_sessions(
    config: TargetConfig,
    source_dates: Iterable[date | str],
) -> tuple[tuple[date, ...], tuple[date, ...]]:
    """Resolve validated XNYS sessions for the source and configured anchor range."""
    dates = tuple(sorted({_market_date(value) for value in source_dates}))
    if not dates:
        raise TargetPipelineError("market_prices_daily has no valid market dates")
    if config.start_date < dates[0]:
        raise TargetPipelineError("input does not reach target.start_date")
    if config.end_date > dates[-1]:
        raise TargetPipelineError("input does not reach target.end_date")

    try:
        import pandas_market_calendars as market_calendars
    except ImportError as error:
        raise TargetPipelineError(
            "pandas-market-calendars is required to resolve XNYS target windows"
        ) from error

    schedule_end = max(config.end_date, dates[-1]) + timedelta(days=21)
    schedule = market_calendars.get_calendar(config.market).schedule(
        start_date=dates[0],
        end_date=schedule_end,
    )
    sessions = tuple(pd.Timestamp(value).date() for value in schedule.index)
    session_set = set(sessions)
    unexpected = sorted(set(dates) - session_set)
    if unexpected:
        raise TargetPipelineError(
            f"market_prices_daily contains non-XNYS sessions: {unexpected[0].isoformat()}"
        )
    if config.start_date not in session_set or config.end_date not in session_set:
        raise TargetPipelineError("target.start_date and target.end_date must be XNYS sessions")

    anchors = tuple(
        day for day in sessions if config.start_date <= day <= config.end_date
    )
    if not anchors:
        raise TargetPipelineError("configured Target date range contains no XNYS sessions")
    return sessions, anchors
