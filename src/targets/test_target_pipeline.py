from __future__ import annotations

from datetime import date, datetime, timezone

import numpy as np
import pandas as pd
import pandas_market_calendars as market_calendars
import pytest

from src.targets.pipeline import LABEL_COLUMNS, TargetPipelineError, build_target_labels


def _sessions(start: str, end: str) -> tuple[date, ...]:
    schedule = market_calendars.get_calendar("XNYS").schedule(
        start_date=start,
        end_date=end,
    )
    return tuple(pd.Timestamp(value).date() for value in schedule.index)


def _prices_for_returns(
    sessions: tuple[date, ...],
    returns: tuple[float, ...],
    tickers: tuple[str, ...] = ("SPY", "IEF", "GLD"),
) -> pd.DataFrame:
    rows = []
    for ticker in tickers:
        close = 100.0
        previous = None
        for day, log_return in zip(sessions, returns, strict=True):
            if previous is not None:
                close *= float(np.exp(log_return))
            rows.append(
                {
                    "date": day,
                    "ticker": ticker,
                    "adjusted_close": close,
                    "log_return": np.nan if previous is None else log_return,
                    "run_id": "price_run",
                    "source_batch_id": f"batch_{ticker.lower()}",
                }
            )
            previous = day
    return pd.DataFrame(rows)


def test_target_uses_only_the_next_five_xnys_returns() -> None:
    sessions = _sessions("2026-01-12", "2026-01-23")
    anchor = sessions[0]
    returns = (0.7, 0.01, -0.02, 0.03, -0.04, 0.05, 0.6, -0.8)
    prices = _prices_for_returns(sessions[: len(returns)], returns)

    labels, findings = build_target_labels(
        prices,
        expected_trading_days=sessions,
        anchor_dates=(anchor,),
        run_id="target_run_1",
        processed_at_utc=datetime(2026, 1, 26, tzinfo=timezone.utc),
    )

    expected = float(np.sqrt((252.0 / 5.0) * np.square(returns[1:6]).sum()))
    spy = labels.loc[labels["ticker"].eq("SPY")].iloc[0]
    assert list(labels.columns) == LABEL_COLUMNS
    assert spy["date"] == anchor
    assert spy["target_start_date"] == sessions[1]
    assert spy["target_end_date"] == sessions[5]
    assert spy["target_obs_count"] == 5
    assert spy["target_realized_vol_5d"] == pytest.approx(expected)
    assert bool(spy["is_label_mature"])
    assert findings == []


@pytest.mark.parametrize("observed_future_returns", range(5))
def test_incomplete_future_window_stays_pending(
    observed_future_returns: int,
) -> None:
    sessions = _sessions("2026-01-12", "2026-01-23")
    anchor = sessions[0]
    returns = (0.7, 0.01, -0.02, 0.03, -0.04, 0.05)
    prices = _prices_for_returns(
        sessions[: observed_future_returns + 1],
        returns[: observed_future_returns + 1],
    )

    labels, _ = build_target_labels(
        prices,
        expected_trading_days=sessions,
        anchor_dates=(anchor,),
        run_id="target_run_pending",
        processed_at_utc="2026-01-26T15:00:00Z",
    )

    spy = labels.loc[labels["ticker"].eq("SPY")].iloc[0]
    assert spy["target_obs_count"] == observed_future_returns
    assert pd.isna(spy["target_realized_vol_5d"])
    assert not bool(spy["is_label_mature"])
    assert pd.isna(spy["label_matured_at_utc"])
    assert spy["record_created_at_utc"].tzinfo is not None


def test_missing_session_does_not_shift_the_forward_window() -> None:
    sessions = _sessions("2026-01-12", "2026-01-23")
    anchor = sessions[0]
    returns = (0.7, 0.01, -0.02, 0.03, -0.04, 0.05, 0.06)
    prices = _prices_for_returns(sessions[: len(returns)], returns)
    prices = prices.loc[~prices["date"].eq(sessions[1])].reset_index(drop=True)

    labels, findings = build_target_labels(
        prices,
        expected_trading_days=sessions,
        anchor_dates=(anchor,),
        run_id="target_run_gap",
        processed_at_utc="2026-01-26T15:00:00Z",
    )

    spy = labels.loc[labels["ticker"].eq("SPY")].iloc[0]
    assert spy["target_end_date"] == sessions[5]
    assert spy["target_obs_count"] == 3
    assert pd.isna(spy["target_realized_vol_5d"])
    assert not bool(spy["is_label_mature"])
    assert any(
        finding["finding_type"] == "MISSING_SESSION"
        and finding["date"] == sessions[1].isoformat()
        and finding["ticker"] == "SPY"
        for finding in findings
    )


def test_missing_ticker_anchor_is_recorded_without_dropping_other_tickers() -> None:
    sessions = _sessions("2026-01-12", "2026-01-23")
    anchor = sessions[0]
    returns = (0.7, 0.01, -0.02, 0.03, -0.04, 0.05)
    prices = _prices_for_returns(sessions[: len(returns)], returns)
    prices = prices.loc[prices["ticker"].ne("GLD")].reset_index(drop=True)

    labels, findings = build_target_labels(
        prices,
        expected_trading_days=sessions,
        anchor_dates=(anchor,),
        run_id="target_run_missing_ticker",
        processed_at_utc="2026-01-26T15:00:00Z",
    )

    assert set(labels["ticker"]) == {"SPY", "IEF"}
    assert any(
        finding["finding_type"] == "MISSING_ANCHOR_ROW"
        and finding["date"] == anchor.isoformat()
        and finding["ticker"] == "GLD"
        for finding in findings
    )


def test_invalid_future_return_holds_only_the_affected_ticker_label() -> None:
    sessions = _sessions("2026-01-12", "2026-01-23")
    anchor = sessions[0]
    returns = (0.7, 0.01, -0.02, 0.03, -0.04, 0.05)
    prices = _prices_for_returns(sessions[: len(returns)], returns)
    prices.loc[
        prices["date"].eq(sessions[1]) & prices["ticker"].eq("SPY"),
        "log_return",
    ] = np.inf

    labels, findings = build_target_labels(
        prices,
        expected_trading_days=sessions,
        anchor_dates=(anchor,),
        run_id="target_run_invalid_return",
        processed_at_utc="2026-01-26T15:00:00Z",
    )

    spy = labels.loc[labels["ticker"].eq("SPY")].iloc[0]
    ief = labels.loc[labels["ticker"].eq("IEF")].iloc[0]
    assert spy["target_obs_count"] == 4
    assert not bool(spy["is_label_mature"])
    assert bool(ief["is_label_mature"])
    assert any(
        finding["finding_type"] == "INVALID_LOG_RETURN"
        and finding["date"] == sessions[1].isoformat()
        and finding["ticker"] == "SPY"
        for finding in findings
    )


@pytest.mark.parametrize("invalid_price", [np.nan, np.inf, 0.0, -1.0])
def test_invalid_future_price_holds_only_the_affected_ticker_label(
    invalid_price: float,
) -> None:
    sessions = _sessions("2026-01-12", "2026-01-23")
    anchor = sessions[0]
    returns = (0.7, 0.01, -0.02, 0.03, -0.04, 0.05)
    prices = _prices_for_returns(sessions[: len(returns)], returns)
    prices.loc[
        prices["date"].eq(sessions[1]) & prices["ticker"].eq("SPY"),
        "adjusted_close",
    ] = invalid_price

    labels, findings = build_target_labels(
        prices,
        expected_trading_days=sessions,
        anchor_dates=(anchor,),
        run_id="target_run_invalid_price",
        processed_at_utc="2026-01-26T15:00:00Z",
    )

    spy = labels.loc[labels["ticker"].eq("SPY")].iloc[0]
    ief = labels.loc[labels["ticker"].eq("IEF")].iloc[0]
    assert spy["target_obs_count"] == 3
    assert not bool(spy["is_label_mature"])
    assert bool(ief["is_label_mature"])
    assert any(
        finding["finding_type"] == "INVALID_ADJUSTED_CLOSE"
        and finding["date"] == sessions[1].isoformat()
        and finding["ticker"] == "SPY"
        for finding in findings
    )


def test_invalid_anchor_price_does_not_block_other_tickers() -> None:
    sessions = _sessions("2026-01-12", "2026-01-23")
    anchor = sessions[0]
    returns = (0.7, 0.01, -0.02, 0.03, -0.04, 0.05)
    prices = _prices_for_returns(sessions[: len(returns)], returns)
    prices.loc[
        prices["date"].eq(anchor) & prices["ticker"].eq("SPY"),
        "adjusted_close",
    ] = 0.0

    labels, findings = build_target_labels(
        prices,
        expected_trading_days=sessions,
        anchor_dates=(anchor,),
        run_id="target_run_invalid_anchor_price",
        processed_at_utc="2026-01-26T15:00:00Z",
    )

    assert set(labels["ticker"]) == {"IEF", "GLD"}
    assert any(
        finding["finding_type"] == "INVALID_ADJUSTED_CLOSE"
        and finding["date"] == anchor.isoformat()
        and finding["ticker"] == "SPY"
        for finding in findings
    )


def test_label_is_not_mature_in_a_replay_snapshot_before_window_end() -> None:
    sessions = _sessions("2026-01-12", "2026-01-23")
    anchor = sessions[0]
    replay_date = sessions[3]
    returns = (0.7, 0.01, -0.02, 0.03)
    prices = _prices_for_returns(sessions[: len(returns)], returns)

    labels, _ = build_target_labels(
        prices,
        expected_trading_days=sessions,
        anchor_dates=(anchor,),
        run_id="target_run_replay_cutoff",
        processed_at_utc="2026-01-15T21:00:00Z",
    )

    spy = labels.loc[labels["ticker"].eq("SPY")].iloc[0]
    assert spy["target_end_date"] > replay_date
    assert spy["target_obs_count"] == 3
    assert pd.isna(spy["target_realized_vol_5d"])
    assert not bool(spy["is_label_mature"])


def test_duplicate_primary_key_is_rejected() -> None:
    sessions = _sessions("2026-01-12", "2026-01-23")
    returns = (0.7, 0.01, -0.02, 0.03, -0.04, 0.05)
    prices = _prices_for_returns(sessions[: len(returns)], returns)
    prices = pd.concat([prices, prices.iloc[[0]]], ignore_index=True)

    with pytest.raises(TargetPipelineError, match="duplicate.*primary keys"):
        build_target_labels(
            prices,
            expected_trading_days=sessions,
            anchor_dates=(sessions[0],),
            run_id="target_run_duplicate",
        )
