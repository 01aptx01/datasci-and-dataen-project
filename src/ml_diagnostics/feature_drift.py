from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import json

import numpy as np
import pandas as pd
from scipy.stats import wasserstein_distance


def _sample(values: Sequence[float], name: str) -> np.ndarray:
    try:
        sample = np.asarray(values, dtype=float)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must contain numeric values") from error
    if sample.ndim != 1 or sample.size == 0:
        raise ValueError(f"{name} must be a non-empty one-dimensional sample")
    if not np.isfinite(sample).all():
        raise ValueError(f"{name} must contain only finite values")
    return sample


def calculate_distribution_metrics(
    reference_values: Sequence[float],
    window_values: Sequence[float],
    *,
    train_iqr: float,
    bin_edges: Sequence[float],
    train_q01: float,
    train_q99: float,
    smoothing: float = 0.5,
) -> dict[str, float | int | None]:
    """Compare two samples using raw/Train-IQR-normalized W1 and fixed-bin PSI."""
    reference = _sample(reference_values, "reference_values")
    window = _sample(window_values, "window_values")
    edges = np.asarray(bin_edges, dtype=float)
    if edges.ndim != 1 or edges.size < 2 or np.isnan(edges).any() or not np.all(np.diff(edges) > 0):
        raise ValueError("bin_edges must be strictly increasing and contain no NaN")
    if not math.isfinite(train_iqr) or train_iqr < 0:
        raise ValueError("train_iqr must be finite and non-negative")
    if not math.isfinite(train_q01) or not math.isfinite(train_q99) or train_q01 > train_q99:
        raise ValueError("Train Q01/Q99 bounds must be finite and ordered")
    if not math.isfinite(smoothing) or smoothing <= 0:
        raise ValueError("smoothing must be finite and positive")

    distance = float(wasserstein_distance(reference, window))
    normalized = distance / train_iqr if train_iqr > 0 else None
    reference_counts = np.histogram(reference, bins=edges)[0].astype(float)
    window_counts = np.histogram(window, bins=edges)[0].astype(float)
    bin_count = len(reference_counts)
    reference_proportions = (reference_counts + smoothing) / (len(reference) + smoothing * bin_count)
    window_proportions = (window_counts + smoothing) / (len(window) + smoothing * bin_count)
    psi = float(np.sum((window_proportions - reference_proportions) * np.log(window_proportions / reference_proportions)))

    return {
        "reference_n": int(reference.size),
        "window_n": int(window.size),
        "wasserstein_raw": distance,
        "wasserstein_normalized": normalized,
        "psi": psi,
        "median_ref": float(np.median(reference)),
        "median_current": float(np.median(window)),
        "p95_ref": float(np.quantile(reference, 0.95, method="linear")),
        "p95_current": float(np.quantile(window, 0.95, method="linear")),
        "out_of_train_range_rate": float(np.mean((window < train_q01) | (window > train_q99))),
    }


def derive_train_bin_edges(train_values: Sequence[float], *, bin_count: int = 10) -> tuple[float, ...] | None:
    """Fit deterministic quantile bins, dropping duplicate cuts and keeping open tails."""
    sample = _sample(train_values, "train_values")
    if bin_count < 2:
        raise ValueError("bin_count must be at least two")
    if np.unique(sample).size < 2:
        return None
    quantiles = np.quantile(sample, np.arange(1, bin_count, dtype=float) / bin_count, method="linear")
    internal = np.unique(quantiles)
    if internal.size == 0:
        return None
    return (float("-inf"), *(float(edge) for edge in internal), float("inf"))


@dataclass(frozen=True)
class FeatureDriftSettings:
    core_features: tuple[str, ...]
    tickers: tuple[str, ...]
    train_start: date
    train_end: date
    validation_start: date
    validation_end: date
    test_start: date
    test_end: date
    window_sizes: tuple[int, ...] = (60, 120)
    bin_count: int = 10
    smoothing: float = 0.5
    threshold_percentile: float = 95.0
    minimum_calibration_windows: int = 100

    def __post_init__(self) -> None:
        if not self.core_features or not self.tickers:
            raise ValueError("core_features and tickers must not be empty")
        if any(not isinstance(value, date) for value in (
            self.train_start, self.train_end, self.validation_start,
            self.validation_end, self.test_start, self.test_end,
        )):
            raise ValueError("split boundaries must be datetime.date values")
        if not (self.train_start <= self.train_end < self.validation_start <= self.validation_end < self.test_start <= self.test_end):
            raise ValueError("Train, Validation, and Test date ranges must be ordered and non-overlapping")
        if not self.window_sizes or any(size < 2 for size in self.window_sizes):
            raise ValueError("window_sizes must contain values of at least two sessions")
        if self.bin_count < 2 or not math.isfinite(self.smoothing) or self.smoothing <= 0:
            raise ValueError("bin_count and smoothing must define valid histogram bins")
        if not 0 < self.threshold_percentile < 100 or self.minimum_calibration_windows < 1:
            raise ValueError("calibration percentile and minimum window count are invalid")


@dataclass(frozen=True)
class FeatureDriftTables:
    metrics: pd.DataFrame
    histograms: pd.DataFrame
    reference_summary: pd.DataFrame
    calibration: pd.DataFrame


def _as_date(value: object, field: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError as error:
        raise ValueError(f"{field} contains an invalid date: {value}") from error


def _canonical_float(value: float) -> str:
    if value == float("-inf"):
        return "-inf"
    if value == float("inf"):
        return "+inf"
    return format(float(value), ".17g")


def _reference_hash(dates: Sequence[date], values: Sequence[float]) -> str:
    pairs = sorted((day.isoformat(), float(value)) for day, value in zip(dates, values, strict=True))
    payload = "".join(f"{day},{_canonical_float(value)}\n" for day, value in pairs).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _bin_definition_id(edges: Sequence[float]) -> str:
    payload = json.dumps([_canonical_float(edge) for edge in edges], separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _quantiles(values: np.ndarray) -> dict[str, float]:
    return {
        name: float(np.quantile(values, quantile, method="linear"))
        for name, quantile in (("q01", 0.01), ("q05", 0.05), ("q25", 0.25), ("q50", 0.50), ("q75", 0.75), ("q95", 0.95), ("q99", 0.99))
    }


def build_feature_drift_tables(
    features: pd.DataFrame,
    train_reference: pd.DataFrame,
    market_sessions: Sequence[date],
    settings: FeatureDriftSettings,
) -> FeatureDriftTables:
    """Build daily Validation calibration and Test diagnostics without future rows."""
    required_columns = {"date", "ticker", *settings.core_features}
    for name, frame in (("features", features), ("train_reference", train_reference)):
        missing = required_columns - set(frame.columns)
        if missing:
            raise ValueError(f"{name} is missing required columns: {', '.join(sorted(missing))}")
    if features.duplicated(["date", "ticker"]).any():
        raise ValueError("features contains duplicate (date, ticker) rows")
    if train_reference.duplicated(["date", "ticker"]).any():
        raise ValueError("train_reference contains duplicate (date, ticker) rows")

    sessions = tuple(_as_date(value, "market_sessions") for value in market_sessions)
    if tuple(sorted(set(sessions))) != sessions:
        raise ValueError("market_sessions must be unique and sorted")
    session_index = {day: index for index, day in enumerate(sessions)}
    feature_days = [_as_date(value, "features.date") for value in features["date"].tolist()]
    reference_days = [_as_date(value, "train_reference.date") for value in train_reference["date"].tolist()]
    feature_rows: dict[tuple[str, date], dict[str, float]] = {}
    for (_, row), day in zip(features.iterrows(), feature_days, strict=True):
        ticker = str(row["ticker"])
        values = {feature: float(row[feature]) for feature in settings.core_features}
        if not all(math.isfinite(value) for value in values.values()):
            raise ValueError(f"features contains a non-finite ready value on {day} for {ticker}")
        feature_rows[(ticker, day)] = values

    references: dict[tuple[str, str], dict[str, object]] = {}
    summary_rows: list[dict[str, object]] = []
    for ticker in settings.tickers:
        ticker_positions = [index for index, value in enumerate(train_reference["ticker"].tolist()) if str(value) == ticker]
        if not ticker_positions:
            raise ValueError(f"train_reference has no eligible rows for {ticker}")
        ticker_days = [reference_days[index] for index in ticker_positions]
        if any(day < settings.train_start or day > settings.train_end for day in ticker_days):
            raise ValueError(f"train_reference for {ticker} extends outside the locked Train range")
        for feature in settings.core_features:
            values = np.asarray([float(train_reference.iloc[index][feature]) for index in ticker_positions], dtype=float)
            if not np.isfinite(values).all():
                raise ValueError(f"train_reference contains non-finite {feature} values for {ticker}")
            quantiles = _quantiles(values)
            iqr = quantiles["q75"] - quantiles["q25"]
            edges = derive_train_bin_edges(values, bin_count=settings.bin_count)
            definition_id = _bin_definition_id(edges) if edges is not None else ""
            reference_hash = _reference_hash(ticker_days, values)
            reference = {
                "values": values,
                "dates": ticker_days,
                "start": min(ticker_days).isoformat(),
                "end": max(ticker_days).isoformat(),
                "quantiles": quantiles,
                "iqr": iqr,
                "edges": edges,
                "bin_definition_id": definition_id,
                "reference_hash": reference_hash,
            }
            references[(ticker, feature)] = reference
            summary_rows.append({
                "ticker": ticker,
                "feature_name": feature,
                "reference_start": reference["start"],
                "reference_end": reference["end"],
                "reference_n": int(values.size),
                "q01": quantiles["q01"],
                "q05": quantiles["q05"],
                "q25": quantiles["q25"],
                "median": quantiles["q50"],
                "q75": quantiles["q75"],
                "q95": quantiles["q95"],
                "q99": quantiles["q99"],
                "train_iqr": iqr,
                "effective_bin_count": len(edges) - 1 if edges is not None else 0,
                "bin_definition_id": definition_id,
                "reference_hash": reference_hash,
                "bin_status": "COMPUTABLE" if edges is not None else "UNCOMPUTABLE_BINS",
            })

    validation_scores: dict[tuple[str, str, int], list[dict[str, float]]] = {}
    test_window_results: list[dict[str, object]] = []
    for split, start, end in (
        ("validation", settings.validation_start, settings.validation_end),
        ("test", settings.test_start, settings.test_end),
    ):
        for as_of in (day for day in sessions if start <= day <= end):
            if as_of not in session_index:
                continue
            position = session_index[as_of]
            for ticker in settings.tickers:
                for feature in settings.core_features:
                    reference = references[(ticker, feature)]
                    for window_size in settings.window_sizes:
                        first = max(0, position - window_size + 1)
                        expected_days = sessions[first : position + 1]
                        current = [feature_rows[(ticker, day)][feature] for day in expected_days if (ticker, day) in feature_rows]
                        complete = len(expected_days) == window_size and len(current) == window_size
                        metrics = None
                        if complete and reference["edges"] is not None:
                            metrics = calculate_distribution_metrics(
                                reference["values"], current,
                                train_iqr=float(reference["iqr"]),
                                bin_edges=reference["edges"],
                                train_q01=float(reference["quantiles"]["q01"]),
                                train_q99=float(reference["quantiles"]["q99"]),
                                smoothing=settings.smoothing,
                            )
                        elif complete:
                            metrics = calculate_distribution_metrics(
                                reference["values"], current,
                                train_iqr=float(reference["iqr"]),
                                bin_edges=(-math.inf, math.inf),
                                train_q01=float(reference["quantiles"]["q01"]),
                                train_q99=float(reference["quantiles"]["q99"]),
                                smoothing=settings.smoothing,
                            )
                            metrics["psi"] = None
                        key = (ticker, feature, window_size)
                        if split == "validation":
                            if metrics is not None:
                                validation_scores.setdefault(key, []).append({
                                    "wasserstein_normalized": metrics["wasserstein_normalized"],
                                    "psi": metrics["psi"],
                                })
                            continue
                        test_window_results.append({
                            "ticker": ticker,
                            "feature_name": feature,
                            "as_of_date": as_of,
                            "window_size": window_size,
                            "current_start": expected_days[0] if expected_days else as_of,
                            "current_end": as_of,
                            "current_n": len(current),
                            "complete": complete,
                            "metrics": metrics,
                            "reference": reference,
                        })

    calibration_by_key: dict[tuple[str, str, int], dict[str, object]] = {}
    calibration_rows: list[dict[str, object]] = []
    for ticker in settings.tickers:
        for feature in settings.core_features:
            for window_size in settings.window_sizes:
                key = (ticker, feature, window_size)
                scores = validation_scores.get(key, [])
                normalized = [float(row["wasserstein_normalized"]) for row in scores if row["wasserstein_normalized"] is not None]
                psi_values = [float(row["psi"]) for row in scores if row["psi"] is not None]
                enough = len(normalized) >= settings.minimum_calibration_windows
                w1_threshold = float(np.quantile(normalized, settings.threshold_percentile / 100, method="linear")) if enough else None
                psi_threshold = float(np.quantile(psi_values, settings.threshold_percentile / 100, method="linear")) if enough and len(psi_values) >= settings.minimum_calibration_windows else None
                reference = references[(ticker, feature)]
                if float(reference["iqr"]) <= 0:
                    status = "UNCOMPUTABLE_SCALE"
                elif not enough:
                    status = "CALIBRATION_LIMITATION"
                elif reference["edges"] is None:
                    status = "W1_CALIBRATED_PSI_UNAVAILABLE"
                else:
                    status = "CALIBRATED"
                calibration = {
                    "wasserstein_threshold": w1_threshold,
                    "psi_threshold": psi_threshold,
                    "valid_window_count": len(normalized),
                    "status": status,
                }
                calibration_by_key[key] = calibration
                calibration_rows.append({
                    "ticker": ticker,
                    "feature_name": feature,
                    "window_size": window_size,
                    "calibration_start": settings.validation_start.isoformat(),
                    "calibration_end": settings.validation_end.isoformat(),
                    "valid_window_count": len(normalized),
                    "threshold_percentile": settings.threshold_percentile,
                    "threshold_method": "empirical_linear_quantile_validation_only",
                    "wasserstein_threshold": w1_threshold,
                    "psi_threshold": psi_threshold,
                    "calibration_status": status,
                })

    metric_rows: list[dict[str, object]] = []
    histogram_rows: list[dict[str, object]] = []
    for item in test_window_results:
        ticker = str(item["ticker"])
        feature = str(item["feature_name"])
        window_size = int(item["window_size"])
        key = (ticker, feature, window_size)
        reference = item["reference"]
        calibration = calibration_by_key[key]
        metrics = item["metrics"]
        complete = bool(item["complete"])
        if not complete:
            status = "INSUFFICIENT_DATA"
            reason = f"Expected {window_size} consecutive XNYS sessions; found {item['current_n']} ready feature values"
        elif float(reference["iqr"]) <= 0:
            status = "UNCOMPUTABLE_SCALE"
            reason = "Train IQR is zero; raw W1 is retained but normalized W1 and its signal are unavailable"
        elif calibration["wasserstein_threshold"] is None:
            status = "CALIBRATION_LIMITATION"
            reason = "Validation has too few complete windows to lock a W1 threshold"
        elif float(metrics["wasserstein_normalized"]) > float(calibration["wasserstein_threshold"]):
            status = "DRIFT_SIGNAL"
            reason = f"Normalized W1 exceeds the Validation {settings.threshold_percentile:g}th-percentile heuristic threshold"
        else:
            status = "NO_SIGNAL"
            reason = f"Normalized W1 is at or below the Validation {settings.threshold_percentile:g}th-percentile heuristic threshold"
        row: dict[str, object] = {
            "evaluation_id": "",
            "replay_id": "",
            "source_feature_run_id": "",
            "feature_set_version": "",
            "split": "test",
            "as_of_date": item["as_of_date"].isoformat(),
            "ticker": ticker,
            "feature_name": feature,
            "reference_start": reference["start"],
            "reference_end": reference["end"],
            "reference_n": int(len(reference["values"])),
            "current_start": item["current_start"].isoformat(),
            "current_end": item["current_end"].isoformat(),
            "current_n": item["current_n"],
            "window_size": window_size,
            "wasserstein_raw": metrics["wasserstein_raw"] if metrics else None,
            "train_iqr": reference["iqr"],
            "wasserstein_normalized": metrics["wasserstein_normalized"] if metrics else None,
            "psi": metrics["psi"] if metrics else None,
            "median_ref": metrics["median_ref"] if metrics else reference["quantiles"]["q50"],
            "median_current": metrics["median_current"] if metrics else None,
            "p95_ref": metrics["p95_ref"] if metrics else reference["quantiles"]["q95"],
            "p95_current": metrics["p95_current"] if metrics else None,
            "out_of_train_range_rate": metrics["out_of_train_range_rate"] if metrics else None,
            "wasserstein_threshold": calibration["wasserstein_threshold"],
            "psi_threshold": calibration["psi_threshold"],
            "status": status,
            "status_reason": reason,
        }
        metric_rows.append(row)

        edges = reference["edges"]
        if complete and metrics is not None and edges is not None:
            current_values = [feature_rows[(ticker, day)][feature] for day in sessions[session_index[item["as_of_date"]] - window_size + 1 : session_index[item["as_of_date"]] + 1]]
            ref_counts = np.histogram(reference["values"], bins=edges)[0]
            current_counts = np.histogram(current_values, bins=edges)[0]
            bin_count = len(ref_counts)
            for bin_index, (lower, upper, ref_count, current_count) in enumerate(zip(edges[:-1], edges[1:], ref_counts, current_counts, strict=True)):
                histogram_rows.append({
                    "as_of_date": item["as_of_date"].isoformat(),
                    "ticker": ticker,
                    "feature_name": feature,
                    "window_size": window_size,
                    "bin_index": bin_index,
                    "lower_edge": _canonical_float(lower),
                    "upper_edge": _canonical_float(upper),
                    "reference_count": int(ref_count),
                    "current_count": int(current_count),
                    "reference_pct": float(ref_count / len(reference["values"])),
                    "current_pct": float(current_count / len(current_values)),
                    "bin_definition_id": reference["bin_definition_id"],
                    "effective_bin_count": bin_count,
                })

    metrics_columns = [
        "diagnostic_id", "evaluation_id", "replay_id", "source_feature_run_id", "feature_set_version", "split", "as_of_date", "ticker", "feature_name",
        "reference_start", "reference_end", "reference_n", "current_start", "current_end", "current_n", "window_size", "wasserstein_raw", "train_iqr",
        "wasserstein_normalized", "psi", "median_ref", "median_current", "p95_ref", "p95_current", "out_of_train_range_rate", "wasserstein_threshold",
        "psi_threshold", "status", "status_reason",
    ]
    histogram_columns = [
        "diagnostic_id", "as_of_date", "ticker", "feature_name", "window_size", "bin_index", "lower_edge", "upper_edge", "reference_count", "current_count",
        "reference_pct", "current_pct", "bin_definition_id", "effective_bin_count",
    ]
    reference_columns = [
        "diagnostic_id", "ticker", "feature_name", "reference_start", "reference_end", "reference_n", "q01", "q05", "q25", "median", "q75", "q95", "q99",
        "train_iqr", "effective_bin_count", "bin_definition_id", "reference_hash", "bin_status",
    ]
    calibration_columns = [
        "diagnostic_id", "ticker", "feature_name", "window_size", "calibration_start", "calibration_end", "valid_window_count", "threshold_percentile",
        "threshold_method", "wasserstein_threshold", "psi_threshold", "calibration_status",
    ]
    return FeatureDriftTables(
        metrics=pd.DataFrame(metric_rows).reindex(columns=metrics_columns),
        histograms=pd.DataFrame(histogram_rows).reindex(columns=histogram_columns),
        reference_summary=pd.DataFrame(summary_rows).reindex(columns=reference_columns),
        calibration=pd.DataFrame(calibration_rows).reindex(columns=calibration_columns),
    )
