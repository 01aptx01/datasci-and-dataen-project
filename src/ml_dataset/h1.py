from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd
import pandas_market_calendars as market_calendars
from scipy.stats import norm
import statsmodels.api as sm

from src.features.pipeline import SUPPORTED_TICKERS
from src.ml_dataset.dataset import DatasetConfig, PreparedDataset


H1_HAC_LAGS = (5, 10, 20)
H1_ALPHA = 0.05
H1_MIN_SAMPLE_SIZE = max(H1_HAC_LAGS) + 3


@dataclass
class H1AnalysisResult:
    results: pd.DataFrame
    sensitivity: pd.DataFrame
    artifact_dir: Path


def holm_adjust(p_values: Sequence[float]) -> list[float]:
    """Return Holm step-down adjusted p-values in their original order."""
    values = np.asarray(p_values, dtype=float)
    if values.ndim != 1 or not np.isfinite(values).all() or ((values < 0) | (values > 1)).any():
        raise ValueError("p_values must be a one-dimensional sequence in [0, 1]")
    count = len(values)
    if not count:
        return []
    order = np.argsort(values, kind="stable")
    sorted_values = values[order]
    multipliers = count - np.arange(count)
    adjusted_sorted = np.maximum.accumulate(sorted_values * multipliers)
    adjusted_sorted = np.minimum(adjusted_sorted, 1.0)
    adjusted = np.empty(count, dtype=float)
    adjusted[order] = adjusted_sorted
    return adjusted.tolist()


def _fit_hac(x: np.ndarray, y: np.ndarray, maxlags: int) -> dict[str, float]:
    design = sm.add_constant(x, has_constant="add")
    fitted = sm.OLS(y, design).fit(
        cov_type="HAC",
        cov_kwds={"maxlags": maxlags, "use_correction": True},
    )
    beta = float(fitted.params[1])
    intercept = float(fitted.params[0])
    covariance = np.asarray(fitted.cov_params(), dtype=float)
    standard_error = float(np.sqrt(covariance[1, 1]))
    if not np.isfinite([beta, intercept, standard_error]).all() or standard_error <= 0:
        raise ValueError("HAC covariance is not finite and positive")
    statistic = beta / standard_error
    p_value = float(norm.sf(statistic))
    z_975 = float(norm.ppf(0.975))
    lower = beta - z_975 * standard_error
    upper = beta + z_975 * standard_error
    return {
        "beta": beta,
        "intercept": intercept,
        "hac_se": standard_error,
        "test_statistic": statistic,
        "p_raw_one_sided": p_value,
        "ci95_lower": float(lower),
        "ci95_upper": float(upper),
    }


def _interpret_effect(beta: float | None) -> str:
    if beta is None or not np.isfinite(beta):
        return "Insufficient evidence to estimate the association."
    change = beta * 0.01
    direction = "higher" if beta > 0 else "lower" if beta < 0 else "unchanged"
    return (
        f"A 0.01 increase in annualized rv_5d is associated with an estimated "
        f"{abs(change):.6f} {direction} Forward RV5 (annualized decimal); this is an "
        "association, not causation or proof of out-of-sample forecast value."
    )


def _fit_result_row(
    ticker: str,
    data: pd.DataFrame,
    expected_anchor_count: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    n = len(data)
    missing_count = max(0, expected_anchor_count - n)
    dates = data["date"]
    row: dict[str, Any] = {
        "ticker": ticker,
        "n": int(n),
        "expected_n": int(expected_anchor_count),
        "missing_xnys_anchors": int(missing_count),
        "train_start_date": min(dates) if n else None,
        "train_end_date": max(dates) if n else None,
        "beta": np.nan,
        "intercept": np.nan,
        "hac_se": np.nan,
        "test_statistic": np.nan,
        "p_raw_one_sided": np.nan,
        "p_holm": np.nan,
        "ci95_lower": np.nan,
        "ci95_upper": np.nan,
        "hac_lag": H1_HAC_LAGS[0],
        "decision": "insufficient_evidence",
        "effect_size_interpretation": _interpret_effect(None),
    }
    sensitivity_rows: list[dict[str, Any]] = []
    if missing_count:
        for lag in H1_HAC_LAGS:
            sensitivity_rows.append(
                {"ticker": ticker, "hac_maxlags": lag, "n": n, "status": "insufficient_evidence"}
            )
        row["decision_reason"] = (
            f"{missing_count} expected Train XNYS anchor(s) are missing; "
            "session-lag HAC cannot treat the remaining rows as consecutive sessions"
        )
        return row, sensitivity_rows
    if n < H1_MIN_SAMPLE_SIZE:
        for lag in H1_HAC_LAGS:
            sensitivity_rows.append(
                {"ticker": ticker, "hac_maxlags": lag, "n": n, "status": "insufficient_evidence"}
            )
        row["decision_reason"] = f"requires at least {H1_MIN_SAMPLE_SIZE} Train rows"
        return row, sensitivity_rows

    x = data["rv_5d"].to_numpy(dtype=float)
    y = data["target_realized_vol_5d"].to_numpy(dtype=float)
    if not np.isfinite(x).all() or not np.isfinite(y).all() or np.ptp(x) <= np.finfo(float).eps:
        for lag in H1_HAC_LAGS:
            sensitivity_rows.append(
                {"ticker": ticker, "hac_maxlags": lag, "n": n, "status": "insufficient_evidence"}
            )
        row["decision_reason"] = "rv_5d has no usable variation or X/y is non-finite"
        return row, sensitivity_rows

    fits: dict[int, dict[str, float]] = {}
    for lag in H1_HAC_LAGS:
        try:
            fit = _fit_hac(x, y, lag)
        except (ValueError, np.linalg.LinAlgError, ZeroDivisionError) as error:
            sensitivity_rows.append(
                {
                    "ticker": ticker,
                    "hac_maxlags": lag,
                    "n": n,
                    "status": "hac_unavailable",
                    "reason": str(error),
                }
            )
            continue
        fits[lag] = fit
        sensitivity_rows.append(
            {
                "ticker": ticker,
                "hac_maxlags": lag,
                "n": n,
                **fit,
                "status": "computed",
            }
        )
    main = fits.get(H1_HAC_LAGS[0])
    if main is None:
        row["decision_reason"] = "primary HAC maxlags=5 covariance was unavailable"
        return row, sensitivity_rows
    row.update(main)
    row["decision_reason"] = ""
    row["effect_size_interpretation"] = _interpret_effect(main["beta"])
    return row, sensitivity_rows


def _git_metadata() -> dict[str, Any]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "diff", "--quiet"],
            check=False,
        ).returncode != 0
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "working_tree_dirty": None}
    return {"commit": commit, "working_tree_dirty": dirty}


def _json_default(value: Any) -> Any:
    if isinstance(value, (date, datetime, Path)):
        return value.isoformat() if isinstance(value, (date, datetime)) else str(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if pd.isna(value):
        return None
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def _write_scatter_plot(data: pd.DataFrame, artifact_dir: Path) -> str | None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None
    fig, axes = plt.subplots(1, len(SUPPORTED_TICKERS), figsize=(15, 4), squeeze=False)
    for axis, ticker in zip(axes[0], SUPPORTED_TICKERS):
        sample = data.loc[data["ticker"] == ticker]
        axis.scatter(sample["rv_5d"], sample["target_realized_vol_5d"], alpha=0.55, s=14)
        axis.set_title(ticker)
        axis.set_xlabel("rv_5d at anchor t")
        axis.set_ylabel("Forward RV5 annualized")
        axis.grid(alpha=0.2)
    fig.suptitle("H1 Volatility Persistence — Train only")
    fig.tight_layout()
    output_path = artifact_dir / "H1_scatter_plot.png"
    fig.savefig(output_path, dpi=160)
    plt.close(fig)
    return output_path.name


def analyze_h1(
    prepared: PreparedDataset,
    artifact_dir: str | Path,
    *,
    config: DatasetConfig | None = None,
) -> H1AnalysisResult:
    """Run the pre-registered Train-only OLS/HAC/Holm H1 analysis and save artifacts."""
    effective_config = config or DatasetConfig()
    output_dir = Path(artifact_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if prepared.supervised.y is None:
        raise ValueError("H1 requires the supervised view with its target y")
    metadata = prepared.supervised.metadata.reset_index(drop=True)
    features = prepared.supervised.X.reset_index(drop=True)
    target = prepared.supervised.y.reset_index(drop=True)
    if not (len(metadata) == len(features) == len(target)):
        raise ValueError("Supervised X, y, and metadata must align row-for-row")
    analysis = metadata.loc[:, ["date", "ticker", "split", "target_end_date"]].copy()
    analysis["rv_5d"] = features["rv_5d"].astype(float).to_numpy()
    analysis["target_realized_vol_5d"] = target.astype(float).to_numpy()
    analysis = analysis.loc[
        (analysis["split"] == "train")
        & (analysis["date"] >= effective_config.train_start_date)
        & (analysis["date"] <= effective_config.train_end_date)
        & (analysis["target_end_date"] < effective_config.validation_start_date)
    ].sort_values(["ticker", "date"], kind="stable").reset_index(drop=True)

    calendar_end = effective_config.validation_start_date + timedelta(days=30)
    schedule = market_calendars.get_calendar(effective_config.market).schedule(
        start_date=effective_config.train_start_date.isoformat(),
        end_date=calendar_end.isoformat(),
    )
    expected_sessions = [pd.Timestamp(value).date() for value in schedule.index]
    session_positions = {day: index for index, day in enumerate(expected_sessions)}
    expected_anchors = [
        day
        for day in expected_sessions
        if effective_config.train_start_date <= day <= effective_config.train_end_date
        and session_positions[day] + 5 < len(expected_sessions)
        and expected_sessions[session_positions[day] + 5] < effective_config.validation_start_date
    ]

    rows: list[dict[str, Any]] = []
    sensitivity_rows: list[dict[str, Any]] = []
    for ticker in SUPPORTED_TICKERS:
        ticker_data = analysis.loc[analysis["ticker"] == ticker].copy()
        result_row, ticker_sensitivity = _fit_result_row(
            ticker, ticker_data, len(expected_anchors)
        )
        rows.append(result_row)
        sensitivity_rows.extend(ticker_sensitivity)
    results = pd.DataFrame(rows)
    sensitivity = pd.DataFrame(sensitivity_rows)

    available = results["p_raw_one_sided"].notna()
    # Treat a test without an estimable p-value as p=1 for conservative family adjustment.
    family_values = [float(value) if pd.notna(value) else 1.0 for value in results["p_raw_one_sided"]]
    adjusted = holm_adjust(family_values)
    results["p_holm"] = [adjusted[index] if available.iloc[index] else np.nan for index in range(len(results))]
    results["decision"] = np.where(
        available & results["p_holm"].le(H1_ALPHA), "reject_h0", results["decision"]
    )
    results.loc[available & results["p_holm"].gt(H1_ALPHA), "decision"] = "not_rejected"

    audit = prepared.report.counts_by_ticker_split_reason.copy()
    audit = audit.loc[audit["split"] == "train"].copy()
    sample_rows = []
    for ticker in SUPPORTED_TICKERS:
        sample = analysis.loc[analysis["ticker"] == ticker]
        missing = len(set(expected_anchors) - set(sample["date"]))
        sample_rows.append(
            {
                "ticker": ticker,
                "split": "train",
                "reason": "H1_analysis_sample",
                "count": int(len(sample)),
                "expected_count": len(expected_anchors),
                "missing_xnys_anchors": missing,
                "anchor_start_date": min(sample["date"]) if not sample.empty else None,
                "anchor_end_date": max(sample["date"]) if not sample.empty else None,
            }
        )
        if missing:
            sample_rows.append(
                {
                    "ticker": ticker,
                    "split": "train",
                    "reason": "H1_xnys_anchor_gap",
                    "count": missing,
                    "expected_count": len(expected_anchors),
                    "missing_xnys_anchors": missing,
                    "anchor_start_date": min(expected_anchors) if expected_anchors else None,
                    "anchor_end_date": max(expected_anchors) if expected_anchors else None,
                }
            )
    audit["anchor_start_date"] = None
    audit["anchor_end_date"] = None
    audit["expected_count"] = pd.NA
    audit["missing_xnys_anchors"] = pd.NA
    audit = pd.concat([audit, pd.DataFrame(sample_rows)], ignore_index=True)
    scatter_spec = {
        "title": "H1 Volatility Persistence — Train only",
        "data_file": "H1_scatter_data.csv",
        "facets": "one panel per ETF: SPY, IEF, GLD",
        "x": {
            "column": "rv_5d",
            "description": "Backward-looking 5-session annualized realized volatility at anchor t",
        },
        "y": {
            "column": "target_realized_vol_5d",
            "description": "Forward 5-session annualized realized volatility from t+1 through t+5",
        },
        "filters": {
            "split": "train",
            "anchor_start_inclusive": effective_config.train_start_date.isoformat(),
            "anchor_end_inclusive": effective_config.train_end_date.isoformat(),
            "target_end_exclusive": effective_config.validation_start_date.isoformat(),
        },
        "mark": "scatter points; no fitted line is used for the inferential test",
    }
    plot_file = _write_scatter_plot(analysis, output_dir)
    if plot_file:
        scatter_spec["rendered_plot"] = plot_file
    spec = {
        "hypothesis_id": "H1",
        "objective": (
            "Test positive association between rv_5d at anchor t and forward annualized "
            "realized volatility over t+1..t+5."
        ),
        "null": "beta <= 0",
        "alternative": "beta > 0",
        "model": "OLS: target_realized_vol_5d ~ const + rv_5d, fit separately by ETF",
        "split": "train only",
        "train_anchor_range_inclusive": [
            effective_config.train_start_date.isoformat(),
            effective_config.train_end_date.isoformat(),
        ],
        "fixed_train_purge": "target_end_date < 2024-10-01",
        "alpha": H1_ALPHA,
        "primary_hac_maxlags": 5,
        "sensitivity_hac_maxlags": [10, 20],
        "hac_covariance": (
            "Newey-West HAC with small-sample correction; one-sided p computed as "
            "normal.sf(beta / HAC_SE)"
        ),
        "confidence_interval": "95% two-sided normal interval from the primary HAC standard error",
        "multiple_testing": (
            "Holm family of SPY, IEF, and GLD; unavailable tests enter adjustment as p=1 "
            "and remain marked insufficient_evidence."
        ),
        "min_sample_size": H1_MIN_SAMPLE_SIZE,
        "contiguous_xnys_coverage_required": True,
        "missing_xnys_session_policy": (
            "Report the gap and mark that ETF insufficient_evidence; do not let "
            "session-lag HAC bridge missing sessions."
        ),
        "model_selection": False,
        "causal_claim": False,
        "data_cutoff": effective_config.data_cutoff.isoformat(),
        "source_availability_limitation": "Historical source availability at each past replay date is not verified.",
        "versions": prepared.report.versions,
        "lineage": prepared.report.lineage,
        "source_quality_passed": prepared.report.summary.get("source_quality_passed"),
    }
    manifest = {
        "artifact_version": "1.0.0",
        "created_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "analysis": "H1_train_only_ols_hac_holm",
        "code_version": _git_metadata(),
        "random_seed": None,
        "randomness": "none; OLS/HAC/Holm analysis is deterministic",
        "hypothesis_spec": "H1_hypothesis_spec.json",
        "results": "H1_results.csv",
        "sensitivity": "H1_sensitivity.csv",
        "dataset_audit": "H1_dataset_audit.csv",
        "preparation_report": "ML_dataset_preparation_report.json",
        "scatter_data": "H1_scatter_data.csv",
        "scatter_plot_spec": "H1_scatter_plot_spec.json",
        "rendered_plot": plot_file,
        "n_by_ticker": {row["ticker"]: int(row["n"]) for row in rows},
        "train_anchor_ranges": {
            row["ticker"]: [
                row["train_start_date"].isoformat() if row["train_start_date"] else None,
                row["train_end_date"].isoformat() if row["train_end_date"] else None,
            ]
            for row in rows
        },
        "point_in_time_source_availability_verified": False,
    }

    (output_dir / "H1_hypothesis_spec.json").write_text(
        json.dumps(spec, indent=2, default=_json_default), encoding="utf-8"
    )
    (output_dir / "ML_dataset_preparation_report.json").write_text(
        json.dumps(prepared.report.to_dict(), indent=2, default=_json_default), encoding="utf-8"
    )
    audit.to_csv(output_dir / "H1_dataset_audit.csv", index=False)
    results.to_csv(output_dir / "H1_results.csv", index=False)
    sensitivity.to_csv(output_dir / "H1_sensitivity.csv", index=False)
    analysis.to_csv(output_dir / "H1_scatter_data.csv", index=False)
    (output_dir / "H1_scatter_plot_spec.json").write_text(
        json.dumps(scatter_spec, indent=2, default=_json_default), encoding="utf-8"
    )
    (output_dir / "H1_manifest.json").write_text(
        json.dumps(manifest, indent=2, default=_json_default), encoding="utf-8"
    )
    return H1AnalysisResult(results=results, sensitivity=sensitivity, artifact_dir=output_dir)
