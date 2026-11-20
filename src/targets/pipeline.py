from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd


SUPPORTED_TICKERS = ("SPY", "IEF", "GLD")
LABEL_COLUMNS = [
    "date",
    "ticker",
    "target_start_date",
    "target_end_date",
    "target_obs_count",
    "target_realized_vol_5d",
    "is_label_mature",
    "target_version",
    "run_id",
    "source_batch_id",
    "record_created_at_utc",
    "label_matured_at_utc",
]
INPUT_COLUMNS = (
    "date",
    "ticker",
    "adjusted_close",
    "log_return",
    "run_id",
    "source_batch_id",
)
RETURN_ATOL = 1e-12
RETURN_RTOL = 1e-8


class TargetPipelineError(ValueError):
    """Raised when target input or output violates the Target Contract."""


def _market_date(value: Any) -> date | None:
    if isinstance(value, (bool, int, float, np.number)):
        return None
    try:
        stamp = pd.Timestamp(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(stamp):
        return None
    return stamp.date()


def _utc_timestamp(value: str | datetime | pd.Timestamp | None) -> pd.Timestamp:
    if value is None:
        return pd.Timestamp(datetime.now(timezone.utc))
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError) as error:
        raise TargetPipelineError("processed_at_utc must be a valid timezone-aware timestamp") from error
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise TargetPipelineError("processed_at_utc must be timezone-aware")
    return timestamp.tz_convert("UTC")


def _normalize_prices(prices: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(prices, pd.DataFrame) or prices.empty:
        raise TargetPipelineError("market_prices_daily must be a non-empty DataFrame")
    missing = [column for column in INPUT_COLUMNS if column not in prices.columns]
    if missing:
        raise TargetPipelineError(
            f"market_prices_daily is missing required columns: {', '.join(missing)}"
        )

    data = prices.loc[:, list(INPUT_COLUMNS)].copy()
    data["date"] = data["date"].map(_market_date)
    if data["date"].isna().any():
        raise TargetPipelineError("date contains an invalid market date")
    if data["ticker"].isna().any():
        raise TargetPipelineError("ticker cannot be NULL")
    data["ticker"] = data["ticker"].astype(str)
    unsupported = sorted(set(data["ticker"]) - set(SUPPORTED_TICKERS))
    if unsupported:
        raise TargetPipelineError(f"unsupported ticker values: {', '.join(unsupported)}")
    if data.duplicated(["date", "ticker"]).any():
        raise TargetPipelineError("duplicate (date, ticker) primary keys in market_prices_daily")

    data["adjusted_close"] = pd.to_numeric(data["adjusted_close"], errors="coerce")
    close_values = data["adjusted_close"].to_numpy(dtype=float)
    data["valid_adjusted_close"] = np.isfinite(close_values) & (close_values > 0)
    data["log_return"] = pd.to_numeric(data["log_return"], errors="coerce")

    for column in ("run_id", "source_batch_id"):
        values = data[column]
        if (
            values.isna().any()
            or not values.map(lambda value: isinstance(value, str)).all()
            or values.str.strip().eq("").any()
            or values.str.len().gt(64).any()
        ):
            raise TargetPipelineError(
                f"{column} must be a non-empty string up to 64 characters"
            )
    return data.sort_values(["ticker", "date"]).reset_index(drop=True)


def _validate_sessions(
    expected_trading_days: Iterable[str | date],
) -> tuple[date, ...]:
    sessions = tuple(_market_date(value) for value in expected_trading_days)
    if not sessions or any(day is None for day in sessions):
        raise TargetPipelineError("expected_trading_days must contain valid market dates")
    normalized = tuple(day for day in sessions if day is not None)
    if tuple(sorted(set(normalized))) != normalized:
        raise TargetPipelineError("expected_trading_days must be sorted and unique")
    return normalized


def _target_version(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 16:
        raise TargetPipelineError("target_version must be a non-empty string up to 16 characters")
    parts = value.split(".")
    if len(parts) != 3 or any(not part.isdigit() for part in parts):
        raise TargetPipelineError("target_version must be a semantic version such as 2.0.0")
    return value


def build_target_labels(
    prices: pd.DataFrame,
    *,
    expected_trading_days: Iterable[str | date],
    anchor_dates: Iterable[str | date] | None = None,
    run_id: str,
    target_version: str = "2.0.0",
    processed_at_utc: str | datetime | pd.Timestamp | None = None,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Build five-session forward volatility labels and quality findings."""
    if not isinstance(run_id, str) or not run_id.strip() or len(run_id) > 64:
        raise TargetPipelineError("run_id must be a non-empty string up to 64 characters")
    version = _target_version(target_version)
    processed_at = _utc_timestamp(processed_at_utc)
    data = _normalize_prices(prices)
    sessions = _validate_sessions(expected_trading_days)
    session_positions = {day: index for index, day in enumerate(sessions)}
    if not set(data["date"]).issubset(session_positions):
        raise TargetPipelineError("market_prices_daily contains dates outside expected_trading_days")

    if anchor_dates is None:
        anchors = tuple(sorted(data["date"].unique()))
    else:
        anchors = tuple(_market_date(value) for value in anchor_dates)
        if any(day is None for day in anchors):
            raise TargetPipelineError("anchor_dates must contain valid market dates")
        anchors = tuple(day for day in anchors if day is not None)
        if tuple(sorted(set(anchors))) != anchors:
            raise TargetPipelineError("anchor_dates must be sorted and unique")
        if not set(anchors).issubset(session_positions):
            raise TargetPipelineError("anchor_dates must be XNYS sessions in expected_trading_days")
    for anchor in anchors:
        position = session_positions[anchor]
        if position + 5 >= len(sessions):
            raise TargetPipelineError(
                f"expected_trading_days must include five future sessions after {anchor.isoformat()}"
            )

    findings: list[dict[str, Any]] = []
    valid_returns: dict[tuple[str, date], float] = {}
    latest_source_date = max(data["date"])

    for ticker, group in data.groupby("ticker", sort=True):
        prices_by_date = {
            row.date: float(row.adjusted_close)
            for row in group.itertuples(index=False)
        }
        valid_prices_by_date = {
            row.date: bool(row.valid_adjusted_close)
            for row in group.itertuples(index=False)
        }
        returns_by_date = {
            row.date: row.log_return
            for row in group.itertuples(index=False)
        }
        ticker_dates = set(prices_by_date)
        min_ticker_date = min(ticker_dates)

        for day in sorted(ticker_dates):
            if not valid_prices_by_date[day]:
                findings.append(
                    {
                        "finding_type": "INVALID_ADJUSTED_CLOSE",
                        "date": day.isoformat(),
                        "ticker": ticker,
                        "raw_value": str(prices_by_date[day]),
                        "reason": "adjusted_close must be finite and positive",
                    }
                )

        for missing_day in sessions:
            if min_ticker_date <= missing_day <= latest_source_date and missing_day not in ticker_dates:
                findings.append(
                    {
                        "finding_type": "MISSING_SESSION",
                        "date": missing_day.isoformat(),
                        "ticker": ticker,
                        "reason": "expected XNYS price row is missing inside the observed input range",
                    }
                )

        for day in sorted(ticker_dates):
            if not valid_prices_by_date[day]:
                continue
            position = session_positions[day]
            if position == 0:
                continue
            previous_day = sessions[position - 1]
            if previous_day not in prices_by_date or not valid_prices_by_date[previous_day]:
                reason = (
                    f"previous XNYS session {previous_day.isoformat()} has invalid adjusted_close"
                    if previous_day in prices_by_date
                    else f"previous XNYS session {previous_day.isoformat()} is unavailable"
                )
                findings.append(
                    {
                        "finding_type": "INVALID_LOG_RETURN",
                        "date": day.isoformat(),
                        "ticker": ticker,
                        "reason": reason,
                    }
                )
                continue
            observed = returns_by_date[day]
            expected = float(np.log(prices_by_date[day] / prices_by_date[previous_day]))
            if not isinstance(observed, (int, float, np.integer, np.floating)) or not np.isfinite(observed):
                findings.append(
                    {
                        "finding_type": "INVALID_LOG_RETURN",
                        "date": day.isoformat(),
                        "ticker": ticker,
                        "reason": "log_return is missing or non-finite",
                    }
                )
                continue
            observed_value = float(observed)
            if not np.isclose(observed_value, expected, rtol=RETURN_RTOL, atol=RETURN_ATOL):
                findings.append(
                    {
                        "finding_type": "INVALID_LOG_RETURN",
                        "date": day.isoformat(),
                        "ticker": ticker,
                        "reason": "log_return does not match adjusted_close for adjacent XNYS sessions",
                    }
                )
                continue
            valid_returns[(ticker, day)] = observed_value

    rows: list[dict[str, Any]] = []
    rows_by_key = {
        (row.date, row.ticker): row
        for row in data.itertuples(index=False)
    }
    for anchor in anchors:
        position = session_positions[anchor]
        window = sessions[position + 1 : position + 6]
        for ticker in SUPPORTED_TICKERS:
            anchor_row = rows_by_key.get((anchor, ticker))
            if anchor_row is None:
                if anchor <= latest_source_date:
                    findings.append(
                        {
                            "finding_type": "MISSING_ANCHOR_ROW",
                            "date": anchor.isoformat(),
                            "ticker": ticker,
                            "reason": "configured anchor session has no validated price row",
                        }
                    )
                continue
            if not bool(anchor_row.valid_adjusted_close):
                continue

            observed_returns = [
                valid_returns[(ticker, day)]
                for day in window
                if (ticker, day) in valid_returns
            ]
            count = len(observed_returns)
            mature = count == 5
            target_value = (
                float(np.sqrt((252.0 / 5.0) * np.square(observed_returns).sum()))
                if mature
                else np.nan
            )
            rows.append(
                {
                    "date": anchor,
                    "ticker": ticker,
                    "target_start_date": window[0],
                    "target_end_date": window[-1],
                    "target_obs_count": count,
                    "target_realized_vol_5d": target_value,
                    "is_label_mature": mature,
                    "target_version": version,
                    "run_id": run_id,
                    "source_batch_id": str(anchor_row.source_batch_id),
                    "record_created_at_utc": processed_at,
                    "label_matured_at_utc": processed_at if mature else pd.NaT,
                }
            )

    labels = pd.DataFrame(rows, columns=LABEL_COLUMNS)
    if labels.empty:
        raise TargetPipelineError("no labels were produced for the configured anchor dates")
    labels["target_obs_count"] = labels["target_obs_count"].astype("int64")
    labels["target_realized_vol_5d"] = pd.to_numeric(
        labels["target_realized_vol_5d"], errors="coerce"
    ).astype("float64")
    labels["is_label_mature"] = labels["is_label_mature"].astype(bool)
    labels["record_created_at_utc"] = pd.to_datetime(
        labels["record_created_at_utc"], utc=True
    )
    labels["label_matured_at_utc"] = pd.to_datetime(
        labels["label_matured_at_utc"], utc=True
    )
    labels = labels.sort_values(["date", "ticker"]).reset_index(drop=True)
    return labels.loc[:, LABEL_COLUMNS], findings
