from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Iterable, Sequence

import numpy as np
import pandas as pd


SUPPORTED_TICKERS = ("SPY", "IEF", "GLD")
INPUT_COLUMNS = (
    "date",
    "ticker",
    "open",
    "adjusted_close",
    "high",
    "low",
    "simple_return",
    "log_return",
    "is_anomaly_flagged",
    "is_warmup_buffer",
    "run_id",
    "source_batch_id",
    "ingested_at_utc",
)
CORE_FEATURE_COLUMNS = (
    "ret_1d_t",
    "ret_lag_1d",
    "ret_lag_2d",
    "ret_trailing_5d",
    "ret_trailing_20d",
    "rv_5d",
    "rv_20d",
    "rv_60d",
)
FEATURE_VALUE_COLUMNS = CORE_FEATURE_COLUMNS + ("rsi_14d", "bb_width_20d")
FEATURE_COLUMNS = [
    "date",
    "ticker",
    *FEATURE_VALUE_COLUMNS,
    "is_model_ready",
    "is_warmup_buffer",
    "feature_set_version",
    "run_id",
    "source_batch_id",
    "feature_as_of_utc",
]
CORRELATION_VALUE_COLUMNS = (
    "corr_spy_ief_20d",
    "corr_spy_gld_20d",
    "corr_ief_gld_20d",
)
CORRELATION_COLUMNS = [
    "date",
    *CORRELATION_VALUE_COLUMNS,
    "is_corr_ready",
    "run_id",
    "source_batch_id",
    "computed_at_utc",
]


class FeaturePipelineError(ValueError):
    """Raised when price inputs or feature outputs fail the Feature Contract."""


def _as_date(value: object) -> date | None:
    if value is None or pd.isna(value):
        return None
    stamp = pd.Timestamp(value)
    if pd.isna(stamp):
        return None
    if stamp.tzinfo is not None:
        stamp = stamp.tz_convert("America/New_York")
    return stamp.date()


def _as_utc_timestamp(value: str | datetime | pd.Timestamp | None) -> str:
    stamp = pd.Timestamp.now(tz="UTC") if value is None else pd.Timestamp(value)
    if stamp.tzinfo is None:
        raise FeaturePipelineError("feature_as_of_utc must include a UTC offset")
    return stamp.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class FeatureConfig:
    start_date: str | date
    end_date: str | date | None = None
    warmup_trading_days: int = 61
    tickers: tuple[str, ...] = SUPPORTED_TICKERS
    feature_set_version: str = "2.0.0"
    market: str = "XNYS"
    expected_trading_days: tuple[str | date, ...] | None = None

    def __post_init__(self) -> None:
        start = _as_date(self.start_date)
        if start is None:
            raise FeaturePipelineError("start_date must be a valid market date")
        object.__setattr__(self, "start_date", start)

        if self.end_date is not None:
            end = _as_date(self.end_date)
            if end is None or end < start:
                raise FeaturePipelineError("end_date must be a valid date on or after start_date")
            object.__setattr__(self, "end_date", end)
        if not isinstance(self.warmup_trading_days, int) or self.warmup_trading_days < 1:
            raise FeaturePipelineError("warmup_trading_days must be a positive integer")

        tickers = tuple(self.tickers)
        if len(tickers) != len(set(tickers)) or set(tickers) != set(SUPPORTED_TICKERS):
            raise FeaturePipelineError("tickers must contain SPY, IEF, and GLD exactly once")
        object.__setattr__(self, "tickers", tickers)

        parts = self.feature_set_version.split(".")
        if (
            len(self.feature_set_version) > 16
            or len(parts) != 3
            or any(not part.isdigit() for part in parts)
        ):
            raise FeaturePipelineError("feature_set_version must be a semver string up to 16 characters")

        if self.expected_trading_days is not None:
            expected = tuple(_as_date(value) for value in self.expected_trading_days)
            if any(value is None for value in expected):
                raise FeaturePipelineError("expected_trading_days contains an invalid date")
            if tuple(sorted(set(expected))) != expected:
                raise FeaturePipelineError("expected_trading_days must be sorted and unique")
            object.__setattr__(self, "expected_trading_days", expected)


def _normalise_input(prices: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(prices, pd.DataFrame) or prices.empty:
        raise FeaturePipelineError("market_prices_daily must be a non-empty DataFrame")
    missing = [column for column in INPUT_COLUMNS if column not in prices.columns]
    if missing:
        raise FeaturePipelineError(f"market_prices_daily is missing required columns: {', '.join(missing)}")

    data = prices.loc[:, INPUT_COLUMNS].copy()
    data["date"] = data["date"].map(_as_date)
    if data["date"].isna().any():
        raise FeaturePipelineError("date contains an invalid market date")
    if data["ticker"].isna().any():
        raise FeaturePipelineError("ticker cannot be NULL")
    data["ticker"] = data["ticker"].astype(str)
    if data["ticker"].str.len().gt(16).any():
        raise FeaturePipelineError("ticker values must be at most 16 characters")

    for column in ("open", "adjusted_close", "high", "low", "simple_return", "log_return"):
        data[column] = pd.to_numeric(data[column], errors="coerce")
    return data.sort_values(["ticker", "date"]).reset_index(drop=True)


def validate_price_data(
    prices: pd.DataFrame,
    config: FeatureConfig,
) -> pd.DataFrame:
    """Validate curated prices and return a sorted, normalized copy."""
    data = _normalise_input(prices)
    unsupported = sorted(set(data["ticker"]) - set(config.tickers))
    if unsupported:
        raise FeaturePipelineError(f"unsupported ticker values: {', '.join(unsupported)}")

    if data.duplicated(["date", "ticker"]).any():
        raise FeaturePipelineError("duplicate (date, ticker) primary keys")

    for column in ("open", "adjusted_close", "high", "low"):
        values = data[column].to_numpy(dtype=float)
        if not np.isfinite(values).all() or (values <= 0).any():
            raise FeaturePipelineError(f"{column} must contain only finite positive prices")

    tolerance = 1e-4
    valid_ohlc = (
        (data["low"] <= data["high"] + tolerance)
        & (data["low"] - tolerance <= data["open"])
        & (data["open"] <= data["high"] + tolerance)
        & (data["low"] - tolerance <= data["adjusted_close"])
        & (data["adjusted_close"] <= data["high"] + tolerance)
    )
    if not valid_ohlc.all():
        raise FeaturePipelineError("input OHLC values do not satisfy low <= open/adjusted_close <= high")

    for column in ("is_anomaly_flagged", "is_warmup_buffer"):
        valid_flags = data[column].map(lambda value: isinstance(value, (bool, np.bool_)))
        if not valid_flags.all():
            raise FeaturePipelineError(f"{column} must contain boolean values")
        data[column] = data[column].astype(bool)

    for column in ("run_id", "source_batch_id"):
        values = data[column]
        if (
            values.isna().any()
            or not values.map(lambda value: isinstance(value, str)).all()
            or values.str.strip().eq("").any()
            or values.str.len().gt(64).any()
        ):
            raise FeaturePipelineError(
                f"{column} must be a non-empty string up to 64 characters"
            )
    data["ingested_at_utc"] = pd.to_datetime(
        data["ingested_at_utc"], utc=True, errors="coerce"
    )
    if data["ingested_at_utc"].isna().any():
        raise FeaturePipelineError("ingested_at_utc must contain valid UTC timestamps")

    expected_warmup = data["date"].map(lambda value: value < config.start_date)
    if not data["is_warmup_buffer"].eq(expected_warmup).all():
        raise FeaturePipelineError("is_warmup_buffer does not match date < start_date")

    for ticker, group in data.groupby("ticker", sort=False):
        group = group.sort_values("date").reset_index(drop=True)
        if config.expected_trading_days is not None:
            expected_days = set(config.expected_trading_days)
            actual_days = set(group["date"])
            missing_days = sorted(expected_days - actual_days)
            extra_days = sorted(actual_days - expected_days)
            if missing_days:
                sample = ", ".join(day.isoformat() for day in missing_days[:3])
                raise FeaturePipelineError(
                    f"missing expected trading days for ticker {ticker}: {sample}"
                )
            if extra_days:
                sample = ", ".join(day.isoformat() for day in extra_days[:3])
                raise FeaturePipelineError(
                    f"unexpected trading days for ticker {ticker}: {sample}"
                )

        previous = group["adjusted_close"].shift(1)
        expected_simple = group["adjusted_close"].div(previous) - 1
        expected_log = np.log(group["adjusted_close"].div(previous))
        for column, expected in (
            ("simple_return", expected_simple),
            ("log_return", expected_log),
        ):
            actual = group[column]
            first_is_null = pd.isna(actual.iloc[0])
            if not first_is_null or actual.iloc[1:].isna().any():
                raise FeaturePipelineError(
                    f"{column} may be NULL only on the first row for ticker {ticker}"
                )
            actual_values = actual.iloc[1:].to_numpy(dtype=float)
            expected_values = expected.iloc[1:].to_numpy(dtype=float)
            if (
                not np.isfinite(actual_values).all()
                or not np.allclose(actual_values, expected_values, rtol=1e-8, atol=1e-12)
            ):
                raise FeaturePipelineError(
                    f"{column} is inconsistent with adjusted_close for ticker {ticker}"
                )

    return data


def _wilder_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    values = prices.to_numpy(dtype=float)
    result = np.full(len(values), np.nan, dtype=float)
    changes = np.diff(values)
    if len(changes) < period or not np.isfinite(changes).all():
        return pd.Series(result, index=prices.index, dtype=float)

    gains = np.maximum(changes, 0.0)
    losses = np.maximum(-changes, 0.0)
    average_gain = float(gains[:period].mean())
    average_loss = float(losses[:period].mean())

    def rsi_value(gain: float, loss: float) -> float:
        if gain == 0 and loss == 0:
            return 50.0
        if loss == 0:
            return 100.0
        if gain == 0:
            return 0.0
        relative_strength = gain / loss
        return 100.0 - 100.0 / (1.0 + relative_strength)

    result[period] = rsi_value(average_gain, average_loss)
    for change_index in range(period, len(changes)):
        average_gain = ((period - 1) * average_gain + gains[change_index]) / period
        average_loss = ((period - 1) * average_loss + losses[change_index]) / period
        result[change_index + 1] = rsi_value(average_gain, average_loss)
    return pd.Series(result, index=prices.index, dtype=float)


def is_valid_correlation_matrix(matrix: np.ndarray) -> bool:
    values = np.asarray(matrix, dtype=float)
    if values.shape != (3, 3) or not np.isfinite(values).all():
        return False
    if (values < -1.0 - 1e-12).any() or (values > 1.0 + 1e-12).any():
        return False
    if not np.allclose(values, values.T, rtol=0.0, atol=1e-12):
        return False
    if not np.allclose(np.diag(values), np.ones(3), rtol=0.0, atol=1e-12):
        return False
    try:
        return float(np.linalg.eigvalsh(values).min()) >= -1e-10
    except np.linalg.LinAlgError:
        return False


def build_rolling_correlations(
    prices: pd.DataFrame,
    tickers: Sequence[str] = SUPPORTED_TICKERS,
    run_id: str = "feature_run",
    computed_at_utc: str | datetime | pd.Timestamp | None = None,
    expected_trading_days: Iterable[str | date] | None = None,
) -> pd.DataFrame:
    """Build Pearson correlations from the same trailing 20 market sessions."""
    if not isinstance(prices, pd.DataFrame) or prices.empty:
        raise FeaturePipelineError("cannot calculate correlations from empty price data")
    required = {"date", "ticker", "log_return", "source_batch_id"}
    missing = sorted(required - set(prices.columns))
    if missing:
        raise FeaturePipelineError(f"correlation input is missing columns: {', '.join(missing)}")

    data = prices.loc[:, ["date", "ticker", "log_return", "source_batch_id"]].copy()
    data["date"] = data["date"].map(_as_date)
    if data["date"].isna().any():
        raise FeaturePipelineError("correlation input contains an invalid date")
    data["log_return"] = pd.to_numeric(data["log_return"], errors="coerce")
    if data.duplicated(["date", "ticker"]).any():
        raise FeaturePipelineError("duplicate (date, ticker) keys in correlation input")

    ticker_order = tuple(tickers)
    if tuple(ticker_order) != SUPPORTED_TICKERS:
        raise FeaturePipelineError("correlation ticker order must be SPY, IEF, GLD")
    if expected_trading_days is None:
        days = tuple(sorted(set(data["date"])))
    else:
        days = tuple(_as_date(day) for day in expected_trading_days)
        if any(day is None for day in days) or tuple(sorted(set(days))) != days:
            raise FeaturePipelineError("expected_trading_days must be valid, sorted, and unique")

    aligned = data.pivot(index="date", columns="ticker", values="log_return")
    aligned = aligned.reindex(index=days, columns=ticker_order)
    computed_at = _as_utc_timestamp(computed_at_utc)
    output = []
    for position, day in enumerate(days):
        window_days = days[max(0, position - 19) : position + 1]
        window = aligned.reindex(window_days)
        matrix = None
        if len(window_days) == 20:
            values = window.to_numpy(dtype=float)
            if values.shape == (20, 3) and np.isfinite(values).all():
                if np.all(np.var(values, axis=0) > 0):
                    candidate = np.corrcoef(values, rowvar=False)
                    if is_valid_correlation_matrix(candidate):
                        matrix = candidate

        day_rows = data.loc[data["date"] == day]
        if day_rows.empty:
            raise FeaturePipelineError(
                f"no source row exists for correlation date {day.isoformat()}"
            )
        batch_by_ticker = day_rows.set_index("ticker")["source_batch_id"].to_dict()
        source_batch_id = next(
            (
                batch_by_ticker[ticker]
                for ticker in ticker_order
                if ticker in batch_by_ticker
                and pd.notna(batch_by_ticker[ticker])
                and str(batch_by_ticker[ticker]).strip()
            ),
            None,
        )
        if source_batch_id is None:
            raise FeaturePipelineError(f"no source_batch_id exists for correlation date {day}")

        output.append(
            {
                "date": day,
                "corr_spy_ief_20d": None if matrix is None else float(matrix[0, 1]),
                "corr_spy_gld_20d": None if matrix is None else float(matrix[0, 2]),
                "corr_ief_gld_20d": None if matrix is None else float(matrix[1, 2]),
                "is_corr_ready": matrix is not None,
                "run_id": run_id,
                "source_batch_id": str(source_batch_id),
                "computed_at_utc": computed_at,
            }
        )

    return pd.DataFrame(output, columns=CORRELATION_COLUMNS)


def build_feature_tables(
    prices: pd.DataFrame,
    config: FeatureConfig,
    run_id: str,
    feature_as_of_utc: str | datetime | pd.Timestamp | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Create the 18-column asset feature table and 8-column correlation table."""
    if not isinstance(config, FeatureConfig):
        raise FeaturePipelineError("config must be a FeatureConfig")
    if not isinstance(run_id, str) or not run_id.strip() or len(run_id) > 64:
        raise FeaturePipelineError("run_id must be a non-empty string up to 64 characters")

    data = validate_price_data(prices, config)
    feature_as_of = _as_utc_timestamp(feature_as_of_utc)
    frames = []
    for ticker, group in data.groupby("ticker", sort=False):
        group = group.sort_values("date").reset_index(drop=True)
        log_returns = group["log_return"].astype(float)
        close = group["adjusted_close"].astype(float)
        features = pd.DataFrame(
            {
                "date": group["date"],
                "ticker": ticker,
                "ret_1d_t": log_returns,
                "ret_lag_1d": log_returns.shift(1),
                "ret_lag_2d": log_returns.shift(2),
                "ret_trailing_5d": close.div(close.shift(5)) - 1.0,
                "ret_trailing_20d": close.div(close.shift(20)) - 1.0,
            }
        )
        for window in (5, 20, 60):
            squared_returns = log_returns.pow(2).rolling(
                window=window, min_periods=window
            ).sum()
            features[f"rv_{window}d"] = np.sqrt(252.0 / window * squared_returns)

        features["rsi_14d"] = _wilder_rsi(close, period=14)
        rolling_mean = close.rolling(window=20, min_periods=20).mean()
        rolling_std = close.rolling(window=20, min_periods=20).std(ddof=0)
        features["bb_width_20d"] = 4.0 * rolling_std.div(rolling_mean)
        features["is_model_ready"] = np.isfinite(
            features.loc[:, CORE_FEATURE_COLUMNS].to_numpy(dtype=float)
        ).all(axis=1)
        features["is_warmup_buffer"] = group["is_warmup_buffer"].astype(bool)
        features["feature_set_version"] = config.feature_set_version
        features["run_id"] = run_id
        features["source_batch_id"] = group["source_batch_id"].astype(str)
        features["feature_as_of_utc"] = feature_as_of
        frames.append(features.loc[:, FEATURE_COLUMNS])

    if not frames:
        raise FeaturePipelineError("no supported ticker rows are available")
    asset_features = (
        pd.concat(frames, ignore_index=True)
        .sort_values(["date", "ticker"])
        .reset_index(drop=True)
    )
    correlations = build_rolling_correlations(
        data,
        tickers=SUPPORTED_TICKERS,
        run_id=run_id,
        computed_at_utc=feature_as_of,
        expected_trading_days=config.expected_trading_days,
    )
    return asset_features.loc[:, FEATURE_COLUMNS], correlations.loc[:, CORRELATION_COLUMNS]

