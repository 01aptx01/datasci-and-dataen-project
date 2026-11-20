from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from src.features.pipeline import SUPPORTED_TICKERS
from src.ml_dataset.dataset import DatasetPreparationError
from src.ml_dataset.h1 import holm_adjust


@dataclass(frozen=True)
class BootstrapResult:
    status: str
    observed_delta: float | None
    bootstrap_standard_error: float | None
    ci_lower: float | None
    ci_upper: float | None
    raw_p_value: float | None
    n_by_ticker: Mapping[str, int]
    replicate_deltas: np.ndarray
    per_ticker_replicates: Mapping[str, np.ndarray]
    invalid_replicate_count: int


def equal_weight_macro_mean(per_ticker_values: Mapping[str, float]) -> float:
    """Average per-ETF statistics with equal ETF weights, never row weights."""
    missing = set(SUPPORTED_TICKERS) - set(per_ticker_values)
    if missing:
        raise ValueError(f"macro result is missing ETF values: {sorted(missing)}")
    values = np.asarray([per_ticker_values[ticker] for ticker in SUPPORTED_TICKERS], dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("macro ETF values must all be finite")
    return float(values.mean())


def _as_date(value: object, field: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    parsed = pd.Timestamp(value)
    if pd.isna(parsed):
        raise ValueError(f"{field} must be a valid market date")
    return parsed.date()


def _insufficient_result(counts: dict[str, int]) -> BootstrapResult:
    empty = np.asarray([], dtype=float)
    return BootstrapResult(
        status="INSUFFICIENT_EVIDENCE",
        observed_delta=None,
        bootstrap_standard_error=None,
        ci_lower=None,
        ci_upper=None,
        raw_p_value=None,
        n_by_ticker=counts,
        replicate_deltas=empty,
        per_ticker_replicates={ticker: empty.copy() for ticker in SUPPORTED_TICKERS},
        invalid_replicate_count=0,
    )


def synchronized_moving_block_bootstrap(
    differences: pd.DataFrame,
    session_dates: Sequence[date],
    *,
    block_length: int,
    replicates: int,
    seed: int,
    alpha: float = 0.05,
    minimum_pairs_per_ticker: int = 30,
) -> BootstrapResult:
    """Bootstrap macro paired-loss differences on synchronized XNYS date blocks.

    Positive values in ``difference`` mean the online model has lower absolute
    error than the comparison model. Bootstrap blocks select the same calendar
    sessions for every ETF, retaining both temporal and cross-ETF dependence.
    """
    required = {"prediction_date", "ticker", "difference"}
    if not required.issubset(differences.columns):
        raise ValueError(f"differences missing columns: {sorted(required - set(differences.columns))}")
    if block_length < 1 or replicates < 1 or minimum_pairs_per_ticker < 1:
        raise ValueError("block length, replicate count, and minimum paired sample must be positive")
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between zero and one")
    sessions = tuple(_as_date(value, "XNYS session") for value in session_dates)
    if not sessions or tuple(sorted(set(sessions))) != sessions:
        raise ValueError("session_dates must be nonempty, sorted, and unique")
    if block_length > len(sessions):
        return _insufficient_result({ticker: 0 for ticker in SUPPORTED_TICKERS})

    frame = differences.loc[:, ["prediction_date", "ticker", "difference"]].copy()
    frame["prediction_date"] = frame["prediction_date"].map(lambda value: _as_date(value, "prediction_date"))
    frame["ticker"] = frame["ticker"].astype(str)
    frame["difference"] = pd.to_numeric(frame["difference"], errors="coerce")
    if frame.duplicated(["prediction_date", "ticker"]).any():
        raise ValueError("paired differences must be unique by prediction_date and ticker")
    unknown_tickers = set(frame["ticker"]) - set(SUPPORTED_TICKERS)
    if unknown_tickers:
        raise ValueError(f"unknown tickers in paired differences: {sorted(unknown_tickers)}")
    session_position = {value: index for index, value in enumerate(sessions)}
    if any(value not in session_position for value in frame["prediction_date"]):
        raise ValueError("paired differences contain dates outside the XNYS session calendar")
    if not np.isfinite(frame["difference"].dropna().to_numpy(dtype=float)).all():
        raise ValueError("paired differences must be finite when present")
    matrix = np.full((len(sessions), len(SUPPORTED_TICKERS)), np.nan, dtype=float)
    ticker_position = {ticker: index for index, ticker in enumerate(SUPPORTED_TICKERS)}
    for row in frame.itertuples(index=False):
        if pd.notna(row.difference):
            matrix[session_position[row.prediction_date], ticker_position[row.ticker]] = float(row.difference)
    counts = {
        ticker: int(np.isfinite(matrix[:, index]).sum())
        for index, ticker in enumerate(SUPPORTED_TICKERS)
    }
    if any(counts[ticker] < minimum_pairs_per_ticker for ticker in SUPPORTED_TICKERS):
        return _insufficient_result(counts)
    per_ticker_observed = {
        ticker: float(np.nanmean(matrix[:, index]))
        for index, ticker in enumerate(SUPPORTED_TICKERS)
    }
    observed = equal_weight_macro_mean(per_ticker_observed)
    rng = np.random.default_rng(seed)
    block_count = int(np.ceil(len(sessions) / block_length))
    starts = rng.integers(0, len(sessions) - block_length + 1, size=(replicates, block_count))
    replicate_by_ticker = {ticker: np.empty(replicates, dtype=float) for ticker in SUPPORTED_TICKERS}
    replicate_macro = np.empty(replicates, dtype=float)
    invalid_replicates = 0
    for replicate_index in range(replicates):
        sampled = np.concatenate(
            [np.arange(start, start + block_length, dtype=int) for start in starts[replicate_index]]
        )[: len(sessions)]
        sampled_panel = matrix[sampled, :]
        ticker_means: dict[str, float] = {}
        for column, ticker in enumerate(SUPPORTED_TICKERS):
            values = sampled_panel[:, column]
            available = np.isfinite(values)
            if not available.any():
                invalid_replicates += 1
                ticker_means = {}
                break
            ticker_means[ticker] = float(values[available].mean())
        if not ticker_means:
            continue
        for ticker, value in ticker_means.items():
            replicate_by_ticker[ticker][replicate_index] = value
        replicate_macro[replicate_index] = equal_weight_macro_mean(ticker_means)

    if invalid_replicates:
        return BootstrapResult(
            status="INSUFFICIENT_EVIDENCE",
            observed_delta=observed,
            bootstrap_standard_error=None,
            ci_lower=None,
            ci_upper=None,
            raw_p_value=None,
            n_by_ticker=counts,
            replicate_deltas=np.asarray([], dtype=float),
            per_ticker_replicates={ticker: np.asarray([], dtype=float) for ticker in SUPPORTED_TICKERS},
            invalid_replicate_count=invalid_replicates,
        )

    centered = replicate_macro - observed
    p_value = (1 + int(np.count_nonzero(centered >= observed))) / (replicates + 1)
    lower, upper = np.quantile(replicate_macro, [alpha / 2.0, 1.0 - alpha / 2.0])
    per_ticker_replicates = {
        ticker: values.copy() for ticker, values in replicate_by_ticker.items()
    }
    return BootstrapResult(
        status="COMPUTED",
        observed_delta=observed,
        bootstrap_standard_error=float(np.std(replicate_macro, ddof=1)) if replicates > 1 else 0.0,
        ci_lower=float(lower),
        ci_upper=float(upper),
        raw_p_value=float(p_value),
        n_by_ticker=counts,
        replicate_deltas=replicate_macro,
        per_ticker_replicates=per_ticker_replicates,
        invalid_replicate_count=0,
    )


__all__ = ["BootstrapResult", "equal_weight_macro_mean", "holm_adjust", "synchronized_moving_block_bootstrap"]
