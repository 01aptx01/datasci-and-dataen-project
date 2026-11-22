from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
import pandas_market_calendars as market_calendars

from src.features.pipeline import SUPPORTED_TICKERS
from src.ml_dataset.dataset import DatasetConfig, PreparedDataset
from src.ml_dataset.h1 import holm_adjust
from src.ml_evaluation.config import EvaluationConfig, EvaluationError, MODEL_NAMES
from src.ml_evaluation.hypotheses import synchronized_moving_block_bootstrap
from src.ml_evaluation.metrics import (
    aggregate_period_metrics,
    build_forecast_audit,
    calculate_error_metrics,
    rolling_session_metrics,
)
from src.ml_evaluation.portfolio import calculate_portfolio_risk
from src.ml_replay.storage import canonical_json, sha256_file, write_json_atomic


PREDICTION_COLUMNS = (
    "prediction_id",
    "prediction_date",
    "ticker",
    "model_name",
    "model_version",
    "prediction_mode",
    "forecast_horizon_trading_days",
    "target_start_date",
    "target_end_date",
    "predicted_vol_annualized",
    "feature_set_version",
    "feature_run_id",
    "input_snapshot_id",
    "last_training_target_end_date",
    "run_id",
    "prediction_created_at_utc",
)

REPLAY_OUTPUTS = (
    "asset_volatility_predictions.csv",
    "coverage.csv",
    "drift_alerts.csv",
    "drift_errors.csv",
    "evaluation.csv",
    "forecast_failures.csv",
    "updates.csv",
)

FINAL_EVALUATION_OUTPUTS = frozenset(
    {
        "evaluation.csv",
        "forecast_audit.csv",
        "forecast_exceptions.csv",
        "coverage.csv",
        "model_metrics.csv",
        "reference_b0_b3_metrics.csv",
        "pair_comparisons.csv",
        "b4_comparisons.csv",
        "high_volatility_metrics.csv",
        "monthly_metrics.csv",
        "yearly_metrics.csv",
        "rolling_mae20.csv",
        "drift_error_timeline.csv",
        "portfolio_risk.csv",
        "hypotheses_plan.json",
        "hypothesis_results.csv",
        "bootstrap_diagnostics.csv",
        "H1_manifest.json",
        "H1_results.csv",
        "H1_sensitivity.csv",
        "H1_dataset_audit.csv",
        "H1_scatter_data.csv",
        "H1_scatter_plot_spec.json",
        "H1_scatter_plot.png",
        "H1_hypothesis_spec.json",
        "ML_dataset_preparation_report.json",
        "evaluation_summary.md",
    }
)


@dataclass(frozen=True)
class FinalEvaluationResult:
    evaluation_id: str
    artifact_dir: Path
    evaluation: pd.DataFrame
    coverage: pd.DataFrame
    model_metrics: pd.DataFrame
    pair_comparisons: pd.DataFrame
    hypothesis_results: pd.DataFrame
    portfolio_risk: pd.DataFrame
    manifest: Mapping[str, Any]
    b4_comparisons: pd.DataFrame | None = None
    reference_b0_b3_metrics: pd.DataFrame | None = None


def _json_default(value: Any) -> Any:
    if isinstance(value, (date, datetime, Path)):
        return value.isoformat() if isinstance(value, (date, datetime)) else str(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, np.bool_):
        return bool(value)
    if pd.isna(value):
        return None
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def _read_json(path: Path, description: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvaluationError(f"could not read {description}: {path}") from error
    if not isinstance(value, dict):
        raise EvaluationError(f"{description} must be a JSON object: {path}")
    return value


def _file_sha256(path: Path) -> str:
    if not path.is_file():
        raise EvaluationError(f"required file is missing: {path}")
    return sha256_file(path)


def _package_versions() -> dict[str, str | None]:
    names = (
        "joblib",
        "numpy",
        "pandas",
        "pandas-market-calendars",
        "river",
        "scikit-learn",
        "scipy",
        "statsmodels",
    )
    installed: dict[str, str | None] = {"python": ".".join(map(str, os.sys.version_info[:3]))}
    for name in names:
        try:
            installed[name] = version(name)
        except PackageNotFoundError:
            installed[name] = None
    return installed


def _load_hypothesis_config(path: str | Path) -> tuple[dict[str, Any], str]:
    config_path = Path(path)
    if not config_path.is_file():
        raise FileNotFoundError(f"Hypothesis test config not found: {config_path}")
    try:
        import yaml

        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise EvaluationError("hypothesis test config could not be read") from error
    if not isinstance(raw, dict):
        raise EvaluationError("hypothesis test config must be a YAML mapping")
    try:
        h1 = raw["hypotheses"]["H1"]
        h2 = raw["hypotheses"]["H2"]
        h3 = raw["hypotheses"]["H3"]
        locked = (
            raw["alpha"] == 0.05
            and raw["alternative"] == "greater"
            and raw["data_cutoff"] == "2026-09-25"
            and raw["test_tuning_allowed"] is False
            and raw["confidence_interval"]["level"] == 0.95
            and raw["confidence_interval"]["sided"] == "two-sided"
            and h1["split"] == "train"
            and h1["predictor"] == "rv_5d"
            and h1["target"] == "target_realized_vol_5d"
            and h1["method"] == "ols_hac"
            and h1["hac_maxlags"] == 5
            and h1["hac_sensitivity_maxlags"] == [10, 20]
            and h1["holm_family"] == "H1"
            and h1["ticker_scope"] == "separate_etf"
            and h1["one_sided_alternative"] == "greater"
            and h2["split"] == "test"
            and h2["model"] == "B3"
            and h2["baseline"] == "B2"
            and h2["method"] == "synchronized_moving_block_bootstrap"
            and h2["paired_by"] == ["prediction_date", "ticker"]
            and h2["paired_sample_definition"] == "same_final_replay_experiment_valid_predictions_with_mature_targets_by_cutoff"
            and h2["effect_definition"] == "baseline_absolute_error_minus_B3_absolute_error"
            and h2["positive_effect_means"] == "B3_lower_error"
            and h2["holm_family"] == "H2_H3"
            and h3["split"] == "test"
            and h3["model"] == "B3"
            and h3["baseline"] == "B1"
            and h3["method"] == "synchronized_moving_block_bootstrap"
            and h3["paired_by"] == ["prediction_date", "ticker"]
            and h3["paired_sample_definition"] == "same_final_replay_experiment_valid_predictions_with_mature_targets_by_cutoff"
            and h3["effect_definition"] == "baseline_absolute_error_minus_B3_absolute_error"
            and h3["positive_effect_means"] == "B3_lower_error"
            and h3["holm_family"] == "H2_H3"
        )
        bootstrap = h2["bootstrap"]
        h3_bootstrap = h3["bootstrap"]
        locked = locked and (
            bootstrap["block_length_xnys_sessions"] == 10
            and bootstrap["replicates"] == 2000
            and bootstrap["seed"] == 42
            and bootstrap["sensitivity_block_lengths"] == [5, 20]
            and h3_bootstrap == bootstrap
            and raw["holm_families"]["H1"] == list(SUPPORTED_TICKERS)
            and raw["holm_families"]["H2_H3"] == ["H2", "H3"]
        )
    except (KeyError, TypeError) as error:
        raise EvaluationError("hypothesis test config is missing locked H1-H3 fields") from error
    if not locked:
        raise EvaluationError("hypothesis test config differs from the approved H1-H3 preregistration")
    return raw, _file_sha256(config_path)


def _verify_replay_artifacts(replay_dir: Path, config: EvaluationConfig) -> tuple[dict[str, Any], dict[str, pd.DataFrame], dict[str, str]]:
    manifest_path = replay_dir / "experiment_manifest.json"
    manifest = _read_json(manifest_path, "Final Replay experiment manifest")
    if manifest.get("phase") != "FINAL_REPLAY" or manifest.get("status") != "COMPLETED":
        raise EvaluationError("Final Evaluation requires a completed Final Replay experiment")
    if manifest.get("experiment_id") != replay_dir.name:
        raise EvaluationError("Final Replay experiment directory does not match its experiment_id")
    if manifest.get("last_fully_committed_session") != config.data_cutoff.isoformat():
        raise EvaluationError("Final Replay does not reach the locked strict cutoff")
    replay_window = manifest.get("replay_window", {})
    if replay_window.get("test") != [config.test_start_date.isoformat(), config.test_end_date.isoformat()]:
        raise EvaluationError("Final Replay Test window differs from the locked Test dates")
    if replay_window.get("strict_data_cutoff") != config.data_cutoff.isoformat():
        raise EvaluationError("Final Replay strict data cutoff differs from Stage 06")
    replay_config = manifest.get("replay_config", {})
    if replay_config.get("prediction_mode") != "HISTORICAL_REPLAY" or replay_config.get(
        "data_cutoff"
    ) != config.data_cutoff.isoformat():
        raise EvaluationError("Final Replay prediction mode or data cutoff is invalid")
    if manifest.get("source_quality_passed") is not True:
        raise EvaluationError("Final Replay source quality gate did not pass")
    if manifest.get("b2_frozen_state_verified") is not True:
        raise EvaluationError("Final Replay does not prove that B2 remained frozen")
    if (
        replay_config.get("update_model") != "B3"
        or replay_config.get("update_policy") != "mature_labels_only"
        or replay_config.get("duplicate_updates_allowed") is not False
        or replay_config.get("adwin", {}).get("policy") != "monitor_only"
        or replay_config.get("processing_order")
        != ["predict", "save_forecast", "evaluate", "adwin_monitor", "update_b3", "checkpoint_commit"]
    ):
        raise EvaluationError("Final Replay update, ADWIN, duplicate-update, or processing-order contract is invalid")
    expected_hashes = manifest.get("final_outputs_sha256")
    if not isinstance(expected_hashes, dict) or set(REPLAY_OUTPUTS) - set(expected_hashes):
        raise EvaluationError("Final Replay manifest does not hash every required output")
    output_dir = replay_dir / "outputs"
    hashes: dict[str, str] = {}
    outputs: dict[str, pd.DataFrame] = {}
    for filename in REPLAY_OUTPUTS:
        path = output_dir / filename
        digest = _file_sha256(path)
        if digest != expected_hashes[filename]:
            raise EvaluationError(f"Final Replay output checksum mismatch: {filename}")
        hashes[filename] = digest
        outputs[filename] = pd.read_csv(path, low_memory=False)
    predictions = outputs["asset_volatility_predictions.csv"]
    if tuple(predictions.columns) != PREDICTION_COLUMNS:
        raise EvaluationError("Final Replay Predictions do not preserve the 16-column Prediction Contract")
    if predictions.empty:
        raise EvaluationError("Final Replay contains no predictions")
    if set(predictions["model_name"].astype(str)) != set(config.model_names):
        raise EvaluationError("Final Replay must contain the complete locked B0-B4 model suite")
    if set(predictions["ticker"].astype(str)) != set(config.tickers):
        raise EvaluationError("Final Replay must contain all three approved ETFs")
    if not predictions["prediction_mode"].eq("HISTORICAL_REPLAY").all():
        raise EvaluationError("Final Replay Predictions must use HISTORICAL_REPLAY mode")
    if predictions["input_snapshot_id"].astype(str).nunique() != 1 or predictions[
        "input_snapshot_id"
    ].astype(str).iloc[0] != str(manifest.get("input_snapshot_id")):
        raise EvaluationError("Final Replay Predictions do not share the manifest's single input snapshot")
    feature_run_id = manifest.get("source_lineage", {}).get("feature_run_id")
    if not feature_run_id or not predictions["feature_run_id"].astype(str).eq(str(feature_run_id)).all():
        raise EvaluationError("Final Replay Prediction feature lineage differs from its manifest")
    horizon = pd.to_numeric(predictions["forecast_horizon_trading_days"], errors="coerce")
    if not horizon.eq(5).all():
        raise EvaluationError("Final Replay Predictions must use the locked five-session horizon")
    pred_dates = pd.to_datetime(predictions["prediction_date"], errors="coerce")
    if pred_dates.isna().any() or (pred_dates.dt.date > config.test_end_date).any():
        raise EvaluationError("Final Replay contains invalid or post-cutoff prediction anchors")
    if predictions["prediction_id"].duplicated().any():
        raise EvaluationError("Final Replay contains duplicate stable prediction IDs")
    logical_key = [
        "prediction_date",
        "ticker",
        "model_name",
        "prediction_mode",
        "model_version",
        "feature_set_version",
        "input_snapshot_id",
    ]
    if predictions.duplicated(logical_key).any():
        raise EvaluationError("Final Replay contains duplicate logical Prediction keys")
    return manifest, outputs, hashes


def _verify_training_artifacts(training_dir: Path, replay_manifest: Mapping[str, Any]) -> dict[str, str]:
    expected = replay_manifest.get("stage04_artifact_sha256", {})
    manifest_expected = replay_manifest.get("stage04_training_manifest_sha256")
    names = [
        "initial_models.joblib",
        "selected_configs.json",
        "training_config.json",
        "validation_candidate_evaluations.csv",
    ]
    # Stage 04 always writes this audit for the B0-B4 suite. Require its
    # checksum from the Final Replay lineage instead of silently treating a
    # missing entry as evidence that this is a legacy B0-B3 artifact.
    has_b4_suite = (
        replay_manifest.get("model_suite_version") == "1.1.0"
        or "b4_initial_state_sha256_by_ticker" in replay_manifest
    )
    if has_b4_suite:
        names.append("b4_validation_evaluations.csv")
    hashes: dict[str, str] = {}
    for name in names:
        digest = _file_sha256(training_dir / name)
        if digest != expected.get(name):
            raise EvaluationError(f"Stage 04 artifact checksum mismatch: {name}")
        hashes[name] = digest
    training_manifest_path = training_dir / "training_manifest.json"
    digest = _file_sha256(training_manifest_path)
    if digest != manifest_expected:
        raise EvaluationError("Stage 04 training manifest checksum does not match Final Replay lineage")
    hashes["training_manifest.json"] = digest
    training_manifest = _read_json(training_manifest_path, "Stage 04 training manifest")
    if training_manifest.get("selection_split") != "validation":
        raise EvaluationError("Stage 04 selection was not restricted to Validation")
    if training_manifest.get("test_used_for_training_or_selection") is not False:
        raise EvaluationError("Stage 04 manifest does not prove Test was excluded from training/selection")
    if training_manifest.get("selection_status") != "selected":
        raise EvaluationError("Stage 04 did not record selected per-ETF configurations")
    replay_selected = replay_manifest.get("selected_configs", [])
    training_selected = training_manifest.get("selected_configs", [])
    if canonical_json(replay_selected) != canonical_json(training_selected):
        raise EvaluationError("Final Replay selected configurations differ from Stage 04 Validation results")
    return hashes


def _verify_source_lineage(prepared: PreparedDataset, replay_manifest: Mapping[str, Any]) -> dict[str, Any]:
    summary = prepared.report.summary
    if summary.get("manifest_verification") != "verified" or summary.get("source_quality_passed") is not True:
        raise EvaluationError("Stage 06 requires Stage 03 inputs with verified manifests and passing source quality")
    replay_lineage = replay_manifest.get("source_lineage", {})
    prepared_lineage = prepared.report.lineage
    keys = (
        "feature_run_id",
        "target_run_id",
        "feature_parquet_sha256",
        "target_parquet_sha256",
        "source_input_sha256",
    )
    for key in keys:
        if prepared_lineage.get(key) != replay_lineage.get(key):
            raise EvaluationError(f"Stage 03 input lineage differs from Final Replay: {key}")
    if replay_manifest.get("point_in_time_source_availability_verified") is not False:
        raise EvaluationError("Stage 06 must preserve the Simulated Historical Replay availability limitation")
    return dict(prepared_lineage)


def _verify_correlation_artifact(
    correlations: pd.DataFrame,
    correlation_path: Path,
    source_artifact_paths: Mapping[str, Path],
    feature_run_id: str,
) -> dict[str, str]:
    required_source_names = {
        "feature_manifest",
        "feature_transaction",
        "target_manifest",
        "target_transaction",
    }
    if set(source_artifact_paths) != required_source_names:
        raise EvaluationError("Stage 06 requires the verified Feature/Target manifests and publish transactions")
    source_hashes = {name: _file_sha256(path) for name, path in source_artifact_paths.items()}
    feature_manifest = _read_json(source_artifact_paths["feature_manifest"], "Stage 03 Feature manifest")
    feature_transaction = _read_json(source_artifact_paths["feature_transaction"], "Stage 03 Feature publish transaction")
    if feature_manifest.get("run_id") != feature_run_id or feature_transaction.get("status") != "COMMITTED":
        raise EvaluationError("correlation source must be bound to the committed Stage 03 Feature run")
    output = feature_manifest.get("outputs", {}).get("asset_rolling_correlations", {})
    expected_path = Path(str(output.get("path", ""))).resolve()
    if expected_path != correlation_path:
        raise EvaluationError("correlation Parquet path differs from the Stage 03 Feature manifest")
    if list(output.get("columns", [])) != list(correlations.columns):
        raise EvaluationError("correlation Parquet schema differs from the Stage 03 Feature manifest")
    rows_in_run = int(output.get("rows_in_run", -1))
    if rows_in_run != int(correlations["run_id"].astype(str).eq(feature_run_id).sum()):
        raise EvaluationError("correlation Parquet row count differs from the Stage 03 Feature manifest")
    matching_entries = [
        entry
        for entry in feature_transaction.get("entries", [])
        if Path(str(entry.get("target_path", ""))).resolve() == correlation_path
    ]
    if len(matching_entries) != 1:
        raise EvaluationError("Feature publish transaction does not identify the correlation Parquet exactly once")
    correlation_sha = _file_sha256(correlation_path)
    if matching_entries[0].get("sha256") != correlation_sha:
        raise EvaluationError("correlation Parquet checksum differs from the committed Feature transaction")
    return {**source_hashes, "correlations_parquet": correlation_sha}


def _verify_h1_artifacts(
    h1_dir: Path,
    expected_lineage: Mapping[str, Any],
    config: EvaluationConfig,
) -> tuple[pd.DataFrame, dict[str, Any], dict[str, str]]:
    manifest = _read_json(h1_dir / "H1_manifest.json", "Stage 03 H1 manifest")
    spec = _read_json(h1_dir / "H1_hypothesis_spec.json", "Stage 03 H1 hypothesis specification")
    required_files = (
        "H1_manifest.json",
        "H1_hypothesis_spec.json",
        "H1_results.csv",
        "H1_sensitivity.csv",
        "H1_dataset_audit.csv",
        "H1_scatter_data.csv",
        "H1_scatter_plot_spec.json",
        "H1_scatter_plot.png",
        "ML_dataset_preparation_report.json",
    )
    hashes = {filename: _file_sha256(h1_dir / filename) for filename in required_files}
    if manifest.get("analysis") != "H1_train_only_ols_hac_holm":
        raise EvaluationError("Stage 03 H1 artifact is not the approved Train-only analysis")
    if manifest.get("point_in_time_source_availability_verified") is not False:
        raise EvaluationError("H1 artifacts must retain the historical source availability limitation")
    expected_h1 = {
        "hypothesis_id": "H1",
        "null": "beta <= 0",
        "alternative": "beta > 0",
        "model": "OLS: target_realized_vol_5d ~ const + rv_5d, fit separately by ETF",
        "split": "train only",
        "train_anchor_range_inclusive": [config.train_start_date.isoformat(), config.train_end_date.isoformat()],
        "fixed_train_purge": f"target_end_date < {config.validation_start_date.isoformat()}",
        "alpha": 0.05,
        "primary_hac_maxlags": 5,
        "sensitivity_hac_maxlags": [10, 20],
        "model_selection": False,
        "causal_claim": False,
        "data_cutoff": config.data_cutoff.isoformat(),
        "source_availability_limitation": "Historical source availability at each past replay date is not verified.",
    }
    for key, value in expected_h1.items():
        if spec.get(key) != value:
            raise EvaluationError(f"Stage 03 H1 hypothesis specification differs from contract: {key}")
    spec_lineage = spec.get("lineage", {})
    for key in (
        "feature_run_id",
        "target_run_id",
        "feature_parquet_sha256",
        "target_parquet_sha256",
        "source_input_sha256",
    ):
        if spec_lineage.get(key) != expected_lineage.get(key):
            raise EvaluationError(f"Stage 03 H1 source lineage differs from Final Replay: {key}")
    if spec.get("source_quality_passed") is not True:
        raise EvaluationError("Stage 03 H1 does not record passing source quality")

    results = pd.read_csv(h1_dir / "H1_results.csv", low_memory=False)
    if set(results["ticker"].astype(str)) != set(SUPPORTED_TICKERS) or results["ticker"].duplicated().any():
        raise EvaluationError("Stage 03 H1 results must contain exactly one row per ETF")
    if not pd.to_numeric(results["hac_lag"], errors="coerce").eq(5).all():
        raise EvaluationError("Stage 03 H1 primary results must use HAC maxlags=5")
    audit = pd.read_csv(h1_dir / "H1_dataset_audit.csv", low_memory=False)
    sample_audit = audit.loc[audit["reason"] == "H1_analysis_sample"]
    if set(sample_audit["ticker"].astype(str)) != set(SUPPORTED_TICKERS) or not sample_audit[
        "split"
    ].eq("train").all():
        raise EvaluationError("Stage 03 H1 dataset audit does not prove a Train-only sample")
    if pd.to_numeric(sample_audit["missing_xnys_anchors"], errors="coerce").fillna(1).ne(0).any():
        raise EvaluationError("Stage 03 H1 dataset audit contains missing XNYS Train anchors")

    raw_values: list[float] = []
    available: list[bool] = []
    for value in results["p_raw_one_sided"]:
        if pd.isna(value):
            raw_values.append(1.0)
            available.append(False)
        else:
            number = float(value)
            if not 0.0 <= number <= 1.0:
                raise EvaluationError("Stage 03 H1 raw p-values must be in [0,1]")
            raw_values.append(number)
            available.append(True)
    adjusted = holm_adjust(raw_values)
    sensitivity = pd.read_csv(h1_dir / "H1_sensitivity.csv", low_memory=False)
    required_sensitivity_columns = {"ticker", "hac_maxlags", "n", "status"}
    if not required_sensitivity_columns.issubset(sensitivity.columns):
        raise EvaluationError("Stage 03 H1 sensitivity output is missing required fields")
    expected_sensitivity_pairs = {(ticker, lag) for ticker in SUPPORTED_TICKERS for lag in (5, 10, 20)}
    actual_sensitivity_pairs = set(
        zip(sensitivity["ticker"].astype(str), pd.to_numeric(sensitivity["hac_maxlags"], errors="coerce"))
    )
    if actual_sensitivity_pairs != expected_sensitivity_pairs or sensitivity.duplicated(["ticker", "hac_maxlags"]).any():
        raise EvaluationError("Stage 03 H1 sensitivity output must include each ETF at HAC lags 5, 10, and 20 once")
    for index, row in results.iterrows():
        if available[index]:
            required_statistics = [row["beta"], row["test_statistic"], row["p_holm"], row["ci95_lower"], row["ci95_upper"]]
            if not np.isfinite(np.asarray(required_statistics, dtype=float)).all():
                raise EvaluationError("Stage 03 H1 computable result is missing a finite statistic, p-value, or CI")
            if not 0.0 <= float(row["p_holm"]) <= 1.0 or abs(float(row["p_holm"]) - adjusted[index]) > 1e-12:
                raise EvaluationError("Stage 03 H1 Holm-adjusted p-values do not match the declared family")
            decision = "reject_h0" if adjusted[index] <= 0.05 else "not_rejected"
            if str(row["decision"]) != decision:
                raise EvaluationError("Stage 03 H1 decision does not match its Holm-adjusted p-value")
        elif str(row["decision"]) != "insufficient_evidence":
            raise EvaluationError("Stage 03 H1 unavailable tests must be marked insufficient_evidence")
    for row in results.itertuples(index=False):
        expected_n = manifest.get("n_by_ticker", {}).get(str(row.ticker))
        if expected_n != int(row.n):
            raise EvaluationError("Stage 03 H1 manifest and result sample counts differ")
        sample_row = sample_audit.loc[sample_audit["ticker"].astype(str) == str(row.ticker)].iloc[0]
        if int(sample_row["count"]) != int(row.n) or int(sample_row["expected_count"]) != int(row.expected_n):
            raise EvaluationError("Stage 03 H1 sample audit, result, and manifest counts differ")
    return results, spec, hashes


def _normalised_expected_anchors(prepared: PreparedDataset, config: EvaluationConfig) -> pd.DataFrame:
    metadata = prepared.prediction.metadata.copy()
    if "prediction_date" not in metadata.columns and "date" in metadata.columns:
        metadata = metadata.rename(columns={"date": "prediction_date"})
    required = {"prediction_date", "ticker", "split"}
    if not required.issubset(metadata.columns):
        raise EvaluationError("Stage 03 Prediction View metadata does not contain date/ticker/split")
    expected = metadata.loc[:, ["prediction_date", "ticker", "split"]].copy()
    expected["prediction_date"] = pd.to_datetime(expected["prediction_date"], errors="coerce").dt.date
    if expected["prediction_date"].isna().any():
        raise EvaluationError("Stage 03 Prediction View contains invalid anchor dates")
    expected = expected.loc[
        expected["split"].isin(("validation", "test"))
        & expected["prediction_date"].between(config.validation_start_date, config.test_end_date)
    ].copy()
    return expected.sort_values(["prediction_date", "ticker"], kind="stable").reset_index(drop=True)


def _validate_joined_windows(audit: pd.DataFrame) -> None:
    has_both = audit["prediction_id"].notna() & audit["target_version"].notna()
    mismatch = has_both & (
        audit["target_start_date"].ne(audit["target_start_date_prediction"])
        | audit["target_end_date"].ne(audit["target_end_date_prediction"])
    )
    if mismatch.any():
        raise EvaluationError("Final Replay Prediction target windows differ from the joined Label rows")


def _mark_common_panel(audit: pd.DataFrame, model_names: Sequence[str]) -> pd.DataFrame:
    result = audit.copy()
    group_keys = ["prediction_date", "ticker", "split"]
    valid_count = (
        result.loc[result["evaluation_status"] == "EVALUABLE"]
        .groupby(group_keys, sort=False)["model_name"]
        .nunique()
    )
    common_keys = set(valid_count.loc[valid_count == len(model_names)].index.tolist())
    result["is_common_panel"] = [
        (row.prediction_date, row.ticker, row.split) in common_keys
        for row in result.itertuples(index=False)
    ]
    return result


def _build_coverage_summary(audit: pd.DataFrame) -> pd.DataFrame:
    if audit.empty:
        return pd.DataFrame(
            columns=[
                "split",
                "ticker",
                "model_name",
                "expected_eligible_prediction_anchors",
                "forecast_success_count",
                "invalid_forecast_count",
                "missing_forecast_count",
                "mature_target_count",
                "pending_label_count",
                "invalid_or_missing_target_count",
                "mature_evaluable_count",
                "common_panel_count",
                "forecast_coverage",
                "evaluation_coverage",
            ]
        )
    grouping = ["split", "ticker", "model_name"]
    grouped = audit.groupby(grouping, as_index=False, sort=True)
    summary = grouped.agg(
        expected_eligible_prediction_anchors=("prediction_date", "nunique"),
        forecast_success_count=("forecast_status", lambda values: int(values.eq("VALID").sum())),
        invalid_forecast_count=("forecast_status", lambda values: int(values.eq("INVALID").sum())),
        missing_forecast_count=("forecast_status", lambda values: int(values.eq("MISSING").sum())),
        mature_target_count=("label_status", lambda values: int(values.eq("MATURE").sum())),
        pending_label_count=("label_status", lambda values: int(values.eq("PENDING").sum())),
        invalid_or_missing_target_count=("label_status", lambda values: int(values.isin(("INVALID", "MISSING")).sum())),
        mature_evaluable_count=("evaluation_status", lambda values: int(values.eq("EVALUABLE").sum())),
        common_panel_count=("is_common_panel", lambda values: int(values.sum())),
    )
    denominator = summary["expected_eligible_prediction_anchors"].replace(0, np.nan)
    summary["forecast_coverage"] = summary["forecast_success_count"] / denominator
    summary["evaluation_coverage"] = summary["mature_evaluable_count"] / denominator
    return summary


def _error_frame(audit: pd.DataFrame, *, split: str | None = None, common_only: bool = False) -> pd.DataFrame:
    selected = audit.loc[audit["evaluation_status"] == "EVALUABLE"].copy()
    if split is not None:
        selected = selected.loc[selected["split"] == split]
    if common_only:
        selected = selected.loc[selected["is_common_panel"]]
    selected["target_realized_vol_5d"] = selected["target_realized_vol_5d"].astype(float)
    selected["predicted_vol_annualized"] = selected["predicted_vol_annualized"].astype(float)
    return selected


REFERENCE_B0_B3_MODELS = (
    "CONSTANT_BASELINE",
    "ROLLING_20D_BASELINE",
    "STATIC_SGD",
    "ONLINE_SGD",
)


def _common_b0_b3_keys(audit: pd.DataFrame) -> set[tuple[Any, Any, Any]]:
    evaluable = audit.loc[
        (audit["evaluation_status"] == "EVALUABLE")
        & audit["model_name"].isin(REFERENCE_B0_B3_MODELS)
    ]
    counts = evaluable.groupby(["prediction_date", "ticker", "split"], sort=False)[
        "model_name"
    ].nunique()
    return set(counts.loc[counts == len(REFERENCE_B0_B3_MODELS)].index.tolist())


def _build_model_metrics(audit: pd.DataFrame, config: EvaluationConfig) -> pd.DataFrame:
    common = _error_frame(audit, split="test", common_only=True)
    rows: list[dict[str, Any]] = []
    test_coverage = audit.loc[audit["split"] == "test"].groupby("ticker")["prediction_date"].nunique()
    for model in config.model_names:
        ticker_rows: list[dict[str, Any]] = []
        for ticker in config.tickers:
            sample = common.loc[
                (common["ticker"] == ticker) & (common["model_name"] == model)
            ]
            values = calculate_error_metrics(
                sample["target_realized_vol_5d"].to_numpy(dtype=float),
                sample["predicted_vol_annualized"].to_numpy(dtype=float),
            )
            row = {
                "split": "test",
                "ticker": ticker,
                "model_name": model,
                "paired_n": values["n"],
                "expected_eligible_anchor_count": int(test_coverage.get(ticker, 0)),
                "mae": values["mae"],
                "rmse": values["rmse"],
                "comparison_panel": "common B0-B4 matured valid anchors",
            }
            rows.append(row)
            ticker_rows.append(row)
        if all(int(row["paired_n"]) > 0 for row in ticker_rows):
            macro_mae = float(np.mean([float(row["mae"]) for row in ticker_rows]))
            macro_rmse = float(np.sqrt(np.mean([float(row["rmse"]) ** 2 for row in ticker_rows])))
        else:
            macro_mae = np.nan
            macro_rmse = np.nan
        rows.append(
            {
                "split": "test",
                "ticker": "MACRO",
                "model_name": model,
                "paired_n": int(sum(int(row["paired_n"]) for row in ticker_rows)),
                "expected_eligible_anchor_count": int(sum(int(test_coverage.get(ticker, 0)) for ticker in config.tickers)),
                "mae": macro_mae,
                "rmse": macro_rmse,
                "comparison_panel": "equal ETF weight; common B0-B4 matured valid anchors",
            }
        )
    return pd.DataFrame(rows)


def _build_reference_b0_b3_metrics(audit: pd.DataFrame, config: EvaluationConfig) -> pd.DataFrame:
    b0_b3_keys = _common_b0_b3_keys(audit)
    evaluable = _error_frame(audit, split="test", common_only=False)
    evaluable = evaluable.loc[
        [
            (row.prediction_date, row.ticker, row.split) in b0_b3_keys
            for row in evaluable.itertuples(index=False)
        ]
    ]
    rows: list[dict[str, Any]] = []
    test_coverage = audit.loc[audit["split"] == "test"].groupby("ticker")["prediction_date"].nunique()
    for model in REFERENCE_B0_B3_MODELS:
        ticker_rows: list[dict[str, Any]] = []
        for ticker in config.tickers:
            sample = evaluable.loc[
                (evaluable["ticker"] == ticker) & (evaluable["model_name"] == model)
            ]
            values = calculate_error_metrics(
                sample["target_realized_vol_5d"].to_numpy(dtype=float),
                sample["predicted_vol_annualized"].to_numpy(dtype=float),
            )
            row = {
                "split": "test",
                "ticker": ticker,
                "model_name": model,
                "paired_n": values["n"],
                "expected_eligible_anchor_count": int(test_coverage.get(ticker, 0)),
                "mae": values["mae"],
                "rmse": values["rmse"],
                "comparison_panel": "reference B0-B3 common matured valid anchors",
            }
            rows.append(row)
            ticker_rows.append(row)
        if all(int(row["paired_n"]) > 0 for row in ticker_rows):
            macro_mae = float(np.mean([float(row["mae"]) for row in ticker_rows]))
            macro_rmse = float(np.sqrt(np.mean([float(row["rmse"]) ** 2 for row in ticker_rows])))
        else:
            macro_mae = np.nan
            macro_rmse = np.nan
        rows.append(
            {
                "split": "test",
                "ticker": "MACRO",
                "model_name": model,
                "paired_n": int(sum(int(row["paired_n"]) for row in ticker_rows)),
                "expected_eligible_anchor_count": int(sum(int(test_coverage.get(ticker, 0)) for ticker in config.tickers)),
                "mae": macro_mae,
                "rmse": macro_rmse,
                "comparison_panel": "equal ETF weight; reference B0-B3 common matured valid anchors",
            }
        )
    return pd.DataFrame(rows)


def _paired_error_differences(
    evaluations: pd.DataFrame,
    comparator_name: str,
    comparison_name: str = "ONLINE_SGD",
) -> pd.DataFrame:
    comparator = evaluations.loc[evaluations["model_name"] == comparator_name, [
        "prediction_date", "ticker", "target_realized_vol_5d", "absolute_error"
    ]].rename(columns={"absolute_error": "comparator_absolute_error", "target_realized_vol_5d": "comparator_target"})
    comparison = evaluations.loc[evaluations["model_name"] == comparison_name, [
        "prediction_date", "ticker", "target_realized_vol_5d", "absolute_error"
    ]].rename(columns={"absolute_error": "comparison_absolute_error", "target_realized_vol_5d": "comparison_target"})
    paired = comparator.merge(
        comparison,
        on=["prediction_date", "ticker"],
        how="inner",
        validate="one_to_one",
    )
    if not np.allclose(
        paired["comparator_target"].to_numpy(dtype=float),
        paired["comparison_target"].to_numpy(dtype=float),
        atol=1e-12,
        rtol=0.0,
    ):
        raise EvaluationError("paired model rows do not share the same realized target")
    paired["difference"] = paired["comparator_absolute_error"] - paired["comparison_absolute_error"]
    return paired.loc[:, ["prediction_date", "ticker", "difference"]].sort_values(
        ["prediction_date", "ticker"], kind="stable"
    ).reset_index(drop=True)


def _build_pair_comparisons(evaluations: pd.DataFrame, config: EvaluationConfig) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    pairs = (("B0", "CONSTANT_BASELINE"), ("H3", "ROLLING_20D_BASELINE"), ("H2", "STATIC_SGD"))
    for comparison_id, baseline in pairs:
        differences = _paired_error_differences(evaluations, baseline)
        pair_source = evaluations.loc[evaluations["model_name"].isin((baseline, "ONLINE_SGD"))]
        pair = pair_source.pivot(
            index=["prediction_date", "ticker"],
            columns="model_name",
            values=["target_realized_vol_5d", "absolute_error", "predicted_vol_annualized"],
        )
        for ticker in config.tickers:
            if (
                not pair.empty
                and baseline in pair.columns.get_level_values(1)
                and "ONLINE_SGD" in pair.columns.get_level_values(1)
                and ticker in pair.index.get_level_values("ticker")
            ):
                sample = pair.xs(ticker, level="ticker").dropna(
                    subset=[("absolute_error", baseline), ("absolute_error", "ONLINE_SGD")]
                )
            else:
                sample = pd.DataFrame()
            baseline_errors = sample[("absolute_error", baseline)].to_numpy(dtype=float) if not sample.empty else np.asarray([])
            online_errors = sample[("absolute_error", "ONLINE_SGD")].to_numpy(dtype=float) if not sample.empty else np.asarray([])
            baseline_mae = float(np.mean(baseline_errors)) if len(baseline_errors) else np.nan
            online_mae = float(np.mean(online_errors)) if len(online_errors) else np.nan
            baseline_rmse = float(np.sqrt(np.mean(np.square(baseline_errors)))) if len(baseline_errors) else np.nan
            online_rmse = float(np.sqrt(np.mean(np.square(online_errors)))) if len(online_errors) else np.nan
            delta = baseline_mae - online_mae if len(baseline_errors) else np.nan
            rows.append(
                {
                    "comparison_id": comparison_id,
                    "baseline_model": baseline,
                    "online_model": "ONLINE_SGD",
                    "ticker": ticker,
                    "paired_n": int(len(baseline_errors)),
                    "baseline_mae": baseline_mae,
                    "online_mae": online_mae,
                    "delta_mae_baseline_minus_online": delta,
                    "relative_improvement_pct": (delta / baseline_mae * 100.0) if len(baseline_errors) and baseline_mae != 0 else np.nan,
                    "baseline_rmse": baseline_rmse,
                    "online_rmse": online_rmse,
                    "common_all_four_n": int(
                        evaluations.loc[
                            (evaluations["ticker"] == ticker) & evaluations["is_common_panel"],
                            "prediction_date",
                        ].nunique()
                    ),
                    "pairing_policy": "same prediction_date/ticker with mature target and both forecasts valid",
                }
            )
        per_ticker = differences.groupby("ticker")["difference"].agg(["mean", "count"])
        if set(per_ticker.index) == set(config.tickers) and per_ticker["count"].gt(0).all():
            macro_delta = float(per_ticker["mean"].mean())
            pair = pair_source.pivot(index=["prediction_date", "ticker"], columns="model_name", values=["absolute_error"])
            baseline_mae_by_ticker: dict[str, float] = {}
            online_mae_by_ticker: dict[str, float] = {}
            for ticker in config.tickers:
                ticker_pair = pair.xs(ticker, level="ticker")
                matched = ticker_pair.dropna(subset=[("absolute_error", baseline), ("absolute_error", "ONLINE_SGD")])
                baseline_mae_by_ticker[ticker] = float(matched[("absolute_error", baseline)].mean())
                online_mae_by_ticker[ticker] = float(matched[("absolute_error", "ONLINE_SGD")].mean())
            macro_baseline = float(np.mean(list(baseline_mae_by_ticker.values())))
            macro_online = float(np.mean(list(online_mae_by_ticker.values())))
            relative = (macro_delta / macro_baseline * 100.0) if macro_baseline != 0 else np.nan
        else:
            macro_delta = macro_baseline = macro_online = relative = np.nan
        rows.append(
            {
                "comparison_id": comparison_id,
                "baseline_model": baseline,
                "online_model": "ONLINE_SGD",
                "ticker": "MACRO",
                "paired_n": int(differences.shape[0]),
                "baseline_mae": macro_baseline,
                "online_mae": macro_online,
                "delta_mae_baseline_minus_online": macro_delta,
                "relative_improvement_pct": relative,
                "baseline_rmse": np.nan,
                "online_rmse": np.nan,
                "common_all_four_n": int(
                    evaluations.loc[evaluations["is_common_panel"], ["prediction_date", "ticker"]]
                    .drop_duplicates()
                    .shape[0]
                ),
                "pairing_policy": "equal ETF weight over per-ETF paired anchors",
            }
        )
    return pd.DataFrame(rows)


def _build_b4_comparisons(audit: pd.DataFrame, config: EvaluationConfig) -> pd.DataFrame:
    """Build retrospective Test paired comparisons for B4 (HAR_X_OLS) vs B2/B3/B1."""
    b4_name = "HAR_X_OLS"
    test_evaluable = _error_frame(audit, split="test", common_only=False)
    test_expected = audit.loc[audit["split"] == "test"].groupby("ticker")["prediction_date"].nunique()
    b0_b3_keys = _common_b0_b3_keys(audit.loc[audit["split"] == "test"])
    common_five_keys = set(
        test_evaluable.loc[test_evaluable["is_common_panel"], ["prediction_date", "ticker"]]
        .itertuples(index=False, name=None)
    )
    b0_b3_test_keys = {(pred_date, ticker) for pred_date, ticker, _ in b0_b3_keys}

    specs = (
        ("B4_VS_B2", "STATIC_SGD"),
        ("B4_VS_B3", "ONLINE_SGD"),
        ("B4_VS_B1", "ROLLING_20D_BASELINE"),
    )
    rows: list[dict[str, Any]] = []
    for comparison_id, comparator in specs:
        differences = _paired_error_differences(test_evaluable, comparator, comparison_name=b4_name)
        pair_source = test_evaluable.loc[test_evaluable["model_name"].isin((comparator, b4_name))]
        pair = pair_source.pivot(
            index=["prediction_date", "ticker"],
            columns="model_name",
            values=["target_realized_vol_5d", "absolute_error", "predicted_vol_annualized"],
        )
        b4_mae_by_ticker: dict[str, float] = {}
        comp_mae_by_ticker: dict[str, float] = {}
        for ticker in config.tickers:
            if (
                not pair.empty
                and comparator in pair.columns.get_level_values(1)
                and b4_name in pair.columns.get_level_values(1)
                and ticker in pair.index.get_level_values("ticker")
            ):
                sample = pair.xs(ticker, level="ticker").dropna(
                    subset=[("absolute_error", comparator), ("absolute_error", b4_name)]
                )
            else:
                sample = pd.DataFrame()
            comp_errors = sample[("absolute_error", comparator)].to_numpy(dtype=float) if not sample.empty else np.asarray([])
            b4_errors = sample[("absolute_error", b4_name)].to_numpy(dtype=float) if not sample.empty else np.asarray([])
            comp_mae = float(np.mean(comp_errors)) if len(comp_errors) else np.nan
            b4_mae = float(np.mean(b4_errors)) if len(b4_errors) else np.nan
            comp_rmse = float(np.sqrt(np.mean(np.square(comp_errors)))) if len(comp_errors) else np.nan
            b4_rmse = float(np.sqrt(np.mean(np.square(b4_errors)))) if len(b4_errors) else np.nan
            delta = comp_mae - b4_mae if len(comp_errors) else np.nan
            expected_n = int(test_expected.get(ticker, 0))
            if len(comp_errors):
                b4_mae_by_ticker[ticker] = b4_mae
                comp_mae_by_ticker[ticker] = comp_mae
            rows.append(
                {
                    "comparison_id": comparison_id,
                    "b4_model": b4_name,
                    "comparator_model": comparator,
                    "split": "test",
                    "ticker": ticker,
                    "paired_n": int(len(comp_errors)),
                    "expected_eligible_anchor_count": expected_n,
                    "paired_coverage": (len(comp_errors) / expected_n) if expected_n else np.nan,
                    "b4_mae": b4_mae,
                    "comparator_mae": comp_mae,
                    "delta_mae_comparator_minus_b4": delta,
                    "relative_improvement_pct": (delta / comp_mae * 100.0) if len(comp_errors) and comp_mae != 0 else np.nan,
                    "b4_rmse": b4_rmse,
                    "comparator_rmse": comp_rmse,
                    "common_all_five_n": sum(1 for _, t in common_five_keys if t == ticker),
                    "common_b0_b3_n": sum(1 for _, t in b0_b3_test_keys if t == ticker),
                    "direction_definition": "comparator_mae_minus_b4_mae (positive means HAR_X_OLS lower error)",
                    "evaluation_scope": "retrospective_test_non_hypothesis",
                    "pairing_policy": "same prediction_date/ticker/split with mature target and both forecasts valid",
                }
            )
        per_ticker = differences.groupby("ticker")["difference"].agg(["mean", "count"])
        total_expected = int(sum(int(test_expected.get(ticker, 0)) for ticker in config.tickers))
        if set(per_ticker.index) == set(config.tickers) and per_ticker["count"].gt(0).all():
            macro_delta = float(per_ticker["mean"].mean())
            macro_b4 = float(np.mean([b4_mae_by_ticker[t] for t in config.tickers]))
            macro_comp = float(np.mean([comp_mae_by_ticker[t] for t in config.tickers]))
            macro_rel = (macro_delta / macro_comp * 100.0) if macro_comp != 0 else np.nan
        else:
            macro_delta = macro_b4 = macro_comp = macro_rel = np.nan
        rows.append(
            {
                "comparison_id": comparison_id,
                "b4_model": b4_name,
                "comparator_model": comparator,
                "split": "test",
                "ticker": "MACRO",
                "paired_n": int(differences.shape[0]),
                "expected_eligible_anchor_count": total_expected,
                "paired_coverage": (int(differences.shape[0]) / total_expected) if total_expected else np.nan,
                "b4_mae": macro_b4,
                "comparator_mae": macro_comp,
                "delta_mae_comparator_minus_b4": macro_delta,
                "relative_improvement_pct": macro_rel,
                "b4_rmse": np.nan,
                "comparator_rmse": np.nan,
                "common_all_five_n": len(common_five_keys),
                "common_b0_b3_n": len(b0_b3_test_keys),
                "direction_definition": "comparator_mae_minus_b4_mae (positive means HAR_X_OLS lower error)",
                "evaluation_scope": "retrospective_test_non_hypothesis",
                "pairing_policy": "equal ETF weight over per-ETF paired anchors",
            }
        )
    return pd.DataFrame(rows)


def _train_high_vol_thresholds(prepared: PreparedDataset, config: EvaluationConfig) -> tuple[dict[str, float], dict[str, int]]:
    metadata = prepared.supervised.metadata.reset_index(drop=True).copy()
    features = prepared.supervised.X.reset_index(drop=True)
    if prepared.supervised.y is None:
        raise EvaluationError("Train 80th percentile requires aligned supervised X/y/metadata")
    target = prepared.supervised.y.reset_index(drop=True)
    if not (len(metadata) == len(features) == len(target)):
        raise EvaluationError("Train 80th percentile requires aligned supervised X/y/metadata")
    if "target_end_date" not in metadata or "split" not in metadata:
        raise EvaluationError("Supervised metadata lacks split or target-end fields for the High-Vol threshold")
    metadata["date"] = pd.to_datetime(metadata["date"], errors="coerce").dt.date
    metadata["target_end_date"] = pd.to_datetime(metadata["target_end_date"], errors="coerce").dt.date
    values = pd.DataFrame(
        {
            "ticker": metadata["ticker"].astype(str),
            "split": metadata["split"].astype(str),
            "date": metadata["date"],
            "target_end_date": metadata["target_end_date"],
            "y": target.astype(float).to_numpy(),
        }
    )
    train = values.loc[
        (values["split"] == "train")
        & values["date"].between(config.train_start_date, config.train_end_date)
        & (values["target_end_date"] < config.validation_start_date)
    ]
    thresholds: dict[str, float] = {}
    counts: dict[str, int] = {}
    for ticker in config.tickers:
        sample = train.loc[train["ticker"] == ticker, "y"].to_numpy(dtype=float)
        if not len(sample) or not np.isfinite(sample).all() or (sample < 0).any():
            raise EvaluationError(f"Train-only High-Vol threshold is unavailable for {ticker}")
        thresholds[ticker] = float(np.quantile(sample, config.high_volatility_quantile))
        counts[ticker] = int(len(sample))
    return thresholds, counts


def _build_high_volatility_metrics(
    audit: pd.DataFrame,
    thresholds: Mapping[str, float],
    train_counts: Mapping[str, int],
    config: EvaluationConfig,
) -> pd.DataFrame:
    test = audit.loc[
        (audit["split"] == "test")
        & audit["label_status"].eq("MATURE")
        & pd.to_numeric(audit["target_realized_vol_5d"], errors="coerce").gt(
            audit["ticker"].map(thresholds)
        )
    ].copy()
    common = test.loc[test["is_common_panel"]]
    rows: list[dict[str, Any]] = []
    for ticker in config.tickers:
        for model in config.model_names:
            sample = common.loc[(common["ticker"] == ticker) & (common["model_name"] == model)]
            metrics = calculate_error_metrics(
                sample["target_realized_vol_5d"].to_numpy(dtype=float),
                sample["predicted_vol_annualized"].to_numpy(dtype=float),
            )
            rows.append(
                {
                    "split": "test",
                    "ticker": ticker,
                    "model_name": model,
                    "train_target_p80_threshold": thresholds[ticker],
                    "threshold_train_n": train_counts[ticker],
                    "high_vol_target_anchor_count": int(test.loc[test["ticker"] == ticker, "prediction_date"].nunique()),
                    "high_vol_common_evaluable_n": metrics["n"],
                    "mae": metrics["mae"],
                    "rmse": metrics["rmse"],
                    "evaluation_coverage": (
                        metrics["n"] / test.loc[test["ticker"] == ticker, "prediction_date"].nunique()
                        if test.loc[test["ticker"] == ticker, "prediction_date"].nunique()
                        else np.nan
                    ),
                    "subset_policy": "Forward RV5 > Train eligible/purge-clean ETF-specific 80th percentile",
                }
            )
    return pd.DataFrame(rows)


def _xnys_sessions(config: EvaluationConfig, start: date, end: date) -> list[date]:
    schedule = market_calendars.get_calendar(config.market).schedule(
        start_date=start.isoformat(), end_date=end.isoformat()
    )
    sessions = [pd.Timestamp(value).date() for value in schedule.index]
    if not sessions or sessions[0] != start or sessions[-1] != end:
        raise EvaluationError(f"requested range {start}..{end} is not bounded by XNYS sessions")
    return sessions


def _build_hypothesis_rows(
    h1_results: pd.DataFrame,
    test_evaluations: pd.DataFrame,
    test_sessions: Sequence[date],
    hypotheses: Mapping[str, Any],
    analysis_config_id: str,
    config: EvaluationConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    for result in h1_results.itertuples(index=False):
        raw_p = None if pd.isna(result.p_raw_one_sided) else float(result.p_raw_one_sided)
        adjusted_p = None if pd.isna(result.p_holm) else float(result.p_holm)
        decision = {
            "reject_h0": "Reject H₀",
            "not_rejected": "Fail to Reject H₀",
            "insufficient_evidence": "Insufficient Evidence",
        }.get(str(result.decision), "Insufficient Evidence")
        rows.append(
            {
                "hypothesis_id": "H1",
                "ticker_or_macro": result.ticker,
                "null": "beta <= 0",
                "alternative": "beta > 0",
                "dataset_split": "train",
                "n_expected": int(result.expected_n),
                "n_paired": int(result.n),
                "paired_n_by_ticker": json.dumps({str(result.ticker): int(result.n)}, sort_keys=True),
                "alpha": 0.05,
                "method": "OLS + Newey-West HAC maxlags=5; one-sided normal tail; Holm across SPY/IEF/GLD",
                "test_statistic": None if pd.isna(result.test_statistic) else float(result.test_statistic),
                "effect_size": None if pd.isna(result.beta) else float(result.beta),
                "raw_p_value": raw_p,
                "adjusted_p_value": adjusted_p,
                "confidence_interval_95": json.dumps(
                    [None if pd.isna(result.ci95_lower) else float(result.ci95_lower),
                     None if pd.isna(result.ci95_upper) else float(result.ci95_upper)]
                ),
                "decision": decision,
                "effect_size_interpretation": result.effect_size_interpretation,
                "analysis_config_id": analysis_config_id,
            }
        )

    comparison_specs = (("H2", "STATIC_SGD"), ("H3", "ROLLING_20D_BASELINE"))
    primary: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    for hypothesis_id, baseline in comparison_specs:
        spec = hypotheses[hypothesis_id]
        paired = _paired_error_differences(test_evaluations, baseline)
        bootstrap_config = spec["bootstrap"]
        primary_result = synchronized_moving_block_bootstrap(
            paired,
            test_sessions,
            block_length=int(bootstrap_config["block_length_xnys_sessions"]),
            replicates=int(bootstrap_config["replicates"]),
            seed=int(bootstrap_config["seed"]),
            alpha=float(spec.get("alpha", 0.05)),
            minimum_pairs_per_ticker=config.bootstrap_minimum_pairs_per_ticker,
        )
        primary.append(
            {
                "hypothesis_id": hypothesis_id,
                "ticker_or_macro": "MACRO",
                "null": "mu_macro(baseline_error - B3_error) <= 0",
                "alternative": "mu_macro(baseline_error - B3_error) > 0",
                "dataset_split": "test",
                "n_expected": len(test_sessions) * len(config.tickers),
                "n_paired": int(sum(primary_result.n_by_ticker.values())),
                "paired_n_by_ticker": json.dumps(dict(primary_result.n_by_ticker), sort_keys=True),
                "alpha": 0.05,
                "method": "Synchronized moving-block bootstrap; 10 XNYS sessions; 2000 replicates; seed=42; Holm across H2/H3",
                "test_statistic": primary_result.observed_delta,
                "effect_size": primary_result.observed_delta,
                "raw_p_value": primary_result.raw_p_value,
                "adjusted_p_value": None,
                "confidence_interval_95": json.dumps([primary_result.ci_lower, primary_result.ci_upper]),
                "decision": "Insufficient Evidence" if primary_result.status != "COMPUTED" else "",
                "effect_size_interpretation": (
                    "Positive annualized-decimal DeltaMAE means B3 has lower paired absolute error; "
                    "multiply by 100 to express percentage points."
                ),
                "analysis_config_id": analysis_config_id,
                "statistical_status": primary_result.status,
                "bootstrap_standard_error": primary_result.bootstrap_standard_error,
                "block_length_xnys_sessions": int(bootstrap_config["block_length_xnys_sessions"]),
                "bootstrap_replicates": int(bootstrap_config["replicates"]),
                "bootstrap_seed": int(bootstrap_config["seed"]),
                "invalid_bootstrap_replicates": primary_result.invalid_replicate_count,
            }
        )
        for block_length in [int(value) for value in bootstrap_config["sensitivity_block_lengths"]]:
            diagnostic = synchronized_moving_block_bootstrap(
                paired,
                test_sessions,
                block_length=block_length,
                replicates=int(bootstrap_config["replicates"]),
                seed=int(bootstrap_config["seed"]),
                alpha=0.05,
                minimum_pairs_per_ticker=config.bootstrap_minimum_pairs_per_ticker,
            )
            diagnostics.append(
                {
                    "hypothesis_id": hypothesis_id,
                    "role": "sensitivity_diagnostic",
                    "block_length_xnys_sessions": block_length,
                    "replicates": int(bootstrap_config["replicates"]),
                    "seed": int(bootstrap_config["seed"]),
                    "status": diagnostic.status,
                    "observed_delta": diagnostic.observed_delta,
                    "bootstrap_standard_error": diagnostic.bootstrap_standard_error,
                    "ci95_lower": diagnostic.ci_lower,
                    "ci95_upper": diagnostic.ci_upper,
                    "p_raw_one_sided": diagnostic.raw_p_value,
                    "n_by_ticker": json.dumps(dict(diagnostic.n_by_ticker), sort_keys=True),
                    "invalid_replicates": diagnostic.invalid_replicate_count,
                }
            )

    available = [row["raw_p_value"] for row in primary]
    family_inputs = [1.0 if value is None or pd.isna(value) else float(value) for value in available]
    adjusted = holm_adjust(family_inputs)
    for index, row in enumerate(primary):
        if row["raw_p_value"] is not None and row["statistical_status"] == "COMPUTED":
            row["adjusted_p_value"] = float(adjusted[index])
            row["decision"] = "Reject H₀" if adjusted[index] <= 0.05 else "Fail to Reject H₀"
        else:
            row["decision"] = "Insufficient Evidence"
    rows.extend(primary)
    return pd.DataFrame(rows), pd.DataFrame(diagnostics)


def _canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=_json_default)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _evaluation_code_hashes() -> dict[str, str]:
    module_dir = Path(__file__).resolve().parent
    paths = {
        name: module_dir / name
        for name in ("__init__.py", "config.py", "hypotheses.py", "metrics.py", "pipeline.py", "portfolio.py")
    }
    return {name: _file_sha256(path) for name, path in paths.items()}


def _write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, float_format="%.17g", lineterminator="\n", na_rep="")


def _serialise_optional(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=_json_default, allow_nan=False)


def _assert_replay_evaluation_matches_audit(
    replay_evaluations: pd.DataFrame,
    audit: pd.DataFrame,
    config: EvaluationConfig,
) -> None:
    required = {
        "prediction_id",
        "prediction_date",
        "split",
        "ticker",
        "model_name",
        "target_start_date",
        "target_end_date",
        "predicted_vol_annualized",
        "target_realized_vol_5d",
        "absolute_error",
        "squared_error",
    }
    if not required.issubset(replay_evaluations.columns):
        raise EvaluationError("Final Replay evaluation output does not satisfy its published schema")
    source = replay_evaluations.copy()
    source["prediction_date"] = pd.to_datetime(source["prediction_date"], errors="coerce").dt.date
    source["target_start_date"] = pd.to_datetime(source["target_start_date"], errors="coerce").dt.date
    source["target_end_date"] = pd.to_datetime(source["target_end_date"], errors="coerce").dt.date
    if source[["prediction_date", "target_start_date", "target_end_date"]].isna().any().any():
        raise EvaluationError("Final Replay evaluations contain invalid dates")
    if source["prediction_id"].duplicated().any():
        raise EvaluationError("Final Replay evaluation output contains duplicate Prediction IDs")
    if not source["split"].isin(("validation", "test")).all():
        raise EvaluationError("Final Replay evaluations contain rows outside Validation/Test")
    if (source["prediction_date"] > config.test_end_date).any() or (source["target_end_date"] > config.data_cutoff).any():
        raise EvaluationError("Final Replay evaluation used an anchor/label beyond the strict cutoff")

    expected = audit.loc[audit["evaluation_status"].eq("EVALUABLE"), list(required)].copy()
    expected["prediction_date"] = pd.to_datetime(expected["prediction_date"], errors="coerce").dt.date
    expected["target_start_date"] = pd.to_datetime(expected["target_start_date"], errors="coerce").dt.date
    expected["target_end_date"] = pd.to_datetime(expected["target_end_date"], errors="coerce").dt.date
    source = source.loc[:, list(required)]
    if len(source) != len(expected) or set(source["prediction_id"]) != set(expected["prediction_id"]):
        raise EvaluationError("Final Replay evaluation membership differs from Mature/valid expected Forecast rows")
    source = source.sort_values("prediction_id", kind="stable").reset_index(drop=True)
    expected = expected.sort_values("prediction_id", kind="stable").reset_index(drop=True)
    for column in ("prediction_id", "prediction_date", "split", "ticker", "model_name", "target_start_date", "target_end_date"):
        if not source[column].equals(expected[column]):
            raise EvaluationError(f"Final Replay evaluation differs from source audit: {column}")
    for column in ("predicted_vol_annualized", "target_realized_vol_5d", "absolute_error", "squared_error"):
        actual = pd.to_numeric(source[column], errors="coerce").to_numpy(dtype=float)
        derived = pd.to_numeric(expected[column], errors="coerce").to_numpy(dtype=float)
        if not np.isfinite(actual).all() or not np.allclose(actual, derived, atol=1e-12, rtol=0.0):
            raise EvaluationError(f"Final Replay evaluation differs from source audit: {column}")


def _build_forecast_exceptions(audit: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "split",
        "prediction_date",
        "ticker",
        "model_name",
        "forecast_status",
        "failure_type",
        "reason",
        "label_status",
        "evaluation_status",
    ]
    exceptions = audit.loc[audit["forecast_status"].ne("VALID"), columns].copy()
    return exceptions.sort_values(["split", "prediction_date", "ticker", "model_name"], kind="stable").reset_index(drop=True)


def _build_drift_error_timeline(
    audit: pd.DataFrame,
    drift_errors: pd.DataFrame,
    drift_alerts: pd.DataFrame,
    config: EvaluationConfig,
) -> pd.DataFrame:
    required = {"prediction_id", "prediction_date", "ticker", "absolute_error", "drift_detected"}
    if not required.issubset(drift_errors.columns):
        raise EvaluationError("Final Replay drift error output is missing required fields")
    test_b3 = audit.loc[
        (audit["split"] == "test")
        & (audit["model_name"] == "ONLINE_SGD")
        & audit["evaluation_status"].eq("EVALUABLE"),
        ["prediction_id", "prediction_date", "ticker", "absolute_error"],
    ].copy()
    source = drift_errors.copy()
    source["prediction_date"] = pd.to_datetime(source["prediction_date"], errors="coerce").dt.date
    test_errors = source.loc[source["prediction_date"].between(config.test_start_date, config.test_end_date)].copy()
    if test_errors["prediction_id"].duplicated().any():
        raise EvaluationError("ADWIN error output contains duplicate Test Prediction IDs")
    if set(test_errors["prediction_id"]) != set(test_b3["prediction_id"]):
        raise EvaluationError("Test ADWIN errors do not match mature valid B3 Test evaluations one-to-one")
    joined = test_b3.merge(
        test_errors.loc[:, ["prediction_id", "absolute_error", "drift_detected", "adwin_delta", "adwin_width", "adwin_estimation"]],
        on="prediction_id",
        how="left",
        suffixes=("_evaluation", "_adwin"),
        validate="one_to_one",
    )
    if not np.allclose(
        joined["absolute_error_evaluation"].to_numpy(dtype=float),
        pd.to_numeric(joined["absolute_error_adwin"], errors="coerce").to_numpy(dtype=float),
        atol=1e-12,
        rtol=0.0,
    ):
        raise EvaluationError("ADWIN error values differ from the immutable B3 Test evaluation")
    alerts = drift_alerts.copy()
    if not alerts.empty:
        if "prediction_id" not in alerts.columns or alerts["prediction_id"].duplicated().any():
            raise EvaluationError("ADWIN alert output must have unique Prediction IDs")
        alert_ids = set(alerts["prediction_id"].astype(str))
        source_ids = set(test_errors["prediction_id"].astype(str))
        if not alert_ids.issubset(source_ids):
            raise EvaluationError("ADWIN alert refers to a Prediction without a Test error")
    joined["drift_detected"] = joined["drift_detected"].fillna(False).astype(bool)
    if not alerts.empty:
        test_alert_ids = set(alerts["prediction_id"].astype(str))
        joined["alert_record_present"] = joined["prediction_id"].astype(str).isin(test_alert_ids)
        if not joined.loc[joined["alert_record_present"], "drift_detected"].all():
            raise EvaluationError("ADWIN alert table and drift error flags disagree")
    else:
        joined["alert_record_present"] = False
    return joined.sort_values(["prediction_date", "ticker"], kind="stable").reset_index(drop=True)


def _build_portfolio_risk_table(
    audit: pd.DataFrame,
    correlations: pd.DataFrame,
    *,
    feature_run_id: str,
    config: EvaluationConfig,
) -> pd.DataFrame:
    required_corr = {
        "date",
        "corr_spy_ief_20d",
        "corr_spy_gld_20d",
        "corr_ief_gld_20d",
        "is_corr_ready",
        "run_id",
    }
    if not required_corr.issubset(correlations.columns):
        raise EvaluationError(f"20-session correlations are missing: {sorted(required_corr - set(correlations.columns))}")
    corr = correlations.loc[:, sorted(required_corr)].copy()
    corr["date"] = pd.to_datetime(corr["date"], errors="coerce").dt.date
    if corr["date"].isna().any() or corr["date"].duplicated().any():
        raise EvaluationError("20-session correlation dates must be valid and unique")
    if not corr["run_id"].astype(str).eq(str(feature_run_id)).all():
        raise EvaluationError("20-session correlation run_id does not match the Stage 03 Feature run")
    corr_lookup = corr.set_index("date").to_dict(orient="index")
    expected_dates = audit.loc[:, ["prediction_date", "split"]].drop_duplicates()
    if expected_dates["prediction_date"].duplicated().any():
        raise EvaluationError("a portfolio date cannot belong to more than one evaluation split")
    rows: list[dict[str, Any]] = []
    weights = dict(zip(config.tickers, config.portfolio_default_weights))
    for expected_row in expected_dates.sort_values("prediction_date", kind="stable").itertuples(index=False):
        session = expected_row.prediction_date
        daily = audit.loc[(audit["prediction_date"] == session) & (audit["split"] == expected_row.split)]
        corr_row = corr_lookup.get(session)
        for model in config.model_names:
            model_rows = daily.loc[daily["model_name"] == model].set_index("ticker", drop=False)
            forecast_values: dict[str, float | None] = {}
            status_by_ticker: dict[str, str] = {}
            for ticker in config.tickers:
                if ticker not in model_rows.index:
                    forecast_values[ticker] = None
                    status_by_ticker[ticker] = "MISSING"
                    continue
                forecast_row = model_rows.loc[ticker]
                status_by_ticker[ticker] = str(forecast_row["forecast_status"])
                value = forecast_row["predicted_vol_annualized"]
                if pd.isna(value):
                    forecast_values[ticker] = None
                else:
                    forecast_values[ticker] = float(value)
            correlation_values = None if corr_row is None else corr_row
            corr_ready = bool(corr_row is not None and corr_row["is_corr_ready"])
            result = calculate_portfolio_risk(
                forecast_values,
                correlation_values,
                weights=weights,
                correlation_ready=corr_ready,
                weight_sum_tolerance=config.weight_sum_tolerance,
                symmetry_tolerance=config.correlation_symmetry_tolerance,
                minimum_eigenvalue=config.correlation_minimum_eigenvalue,
            )
            present = model_rows.reset_index(drop=True)
            for field in ("run_id", "input_snapshot_id", "prediction_mode"):
                if field in present and present[field].dropna().astype(str).nunique() > 1:
                    raise EvaluationError(f"portfolio assets do not share the same {field} on {session} for {model}")
            lookup = lambda column: None if corr_row is None or pd.isna(corr_row.get(column)) else float(corr_row[column])
            rows.append(
                {
                    "split": expected_row.split,
                    "prediction_date": session,
                    "model_name": model,
                    "prediction_mode": "HISTORICAL_REPLAY",
                    "feature_run_id": feature_run_id,
                    "replay_run_id": present["run_id"].iloc[0] if len(present) and "run_id" in present else None,
                    "input_snapshot_id": present["input_snapshot_id"].iloc[0] if len(present) and "input_snapshot_id" in present else None,
                    "spy_forecast_vol_annualized": forecast_values["SPY"],
                    "ief_forecast_vol_annualized": forecast_values["IEF"],
                    "gld_forecast_vol_annualized": forecast_values["GLD"],
                    "spy_forecast_status": status_by_ticker["SPY"],
                    "ief_forecast_status": status_by_ticker["IEF"],
                    "gld_forecast_status": status_by_ticker["GLD"],
                    "corr_spy_ief_20d": lookup("corr_spy_ief_20d"),
                    "corr_spy_gld_20d": lookup("corr_spy_gld_20d"),
                    "corr_ief_gld_20d": lookup("corr_ief_gld_20d"),
                    "is_corr_ready": corr_ready,
                    "correlation_run_id": None if corr_row is None else str(corr_row["run_id"]),
                    "weight_spy": result.weights["SPY"],
                    "weight_ief": result.weights["IEF"],
                    "weight_gld": result.weights["GLD"],
                    "portfolio_vol_annualized": result.portfolio_vol_annualized,
                    "portfolio_status": result.status,
                    "missing_inputs": _serialise_optional(list(result.missing_inputs)),
                    "covariance_matrix": _serialise_optional(result.covariance_matrix),
                }
            )
    return pd.DataFrame(rows)


def _hypotheses_plan(
    *,
    config: EvaluationConfig,
    hypothesis_config: Mapping[str, Any],
    analysis_config_id: str,
    evaluation_config_sha256: str,
    hypothesis_config_sha256: str,
    code_hashes: Mapping[str, str],
    replay_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "plan_version": "1.0.0",
        "status": "FROZEN_BEFORE_TEST_ANALYSIS",
        "planned_at_utc": datetime.now(timezone.utc).isoformat(),
        "analysis_config_id": analysis_config_id,
        "evaluation_config_sha256": evaluation_config_sha256,
        "hypothesis_tests_config_sha256": hypothesis_config_sha256,
        "code_sha256_by_file": dict(code_hashes),
        "models": list(config.model_names),
        "features": list(config.core_features),
        "splits": {
            "train": [config.train_start_date.isoformat(), config.train_end_date.isoformat()],
            "validation": [config.validation_start_date.isoformat(), config.validation_end_date.isoformat()],
            "test": [config.test_start_date.isoformat(), config.test_end_date.isoformat()],
            "strict_data_cutoff": config.data_cutoff.isoformat(),
        },
        "test_tuning_allowed": False,
        "prediction_source": "immutable Predictions from the one completed Final Replay experiment",
        "final_replay_experiment_id": replay_manifest["experiment_id"],
        "pairing_key": ["prediction_date", "ticker"],
        "paired_metric": "baseline_absolute_error_minus_B3_absolute_error",
        "macro_weighting": "equal weight across SPY, IEF, and GLD per-ETF means",
        "holm_families": hypothesis_config["holm_families"],
        "hypotheses": hypothesis_config["hypotheses"],
        "h1_source": "Stage 03 Train-only OLS/HAC/Holm artifact; not refit on Test",
        "h2_h3_inference": {
            "method": "synchronized_moving_block_bootstrap",
            "primary_block_length_xnys_sessions": 10,
            "replicates": 2000,
            "seed": 42,
            "sensitivity_block_lengths": [5, 20],
            "ci_level": 0.95,
            "p_value": "one-sided centered-null; Holm-adjusted across H2/H3",
            "minimum_pairs_per_ticker": config.bootstrap_minimum_pairs_per_ticker,
        },
        "point_in_time_source_availability_verified": replay_manifest.get("point_in_time_source_availability_verified"),
        "limitation": "Historical snapshot availability on each simulated replay date is not verified.",
    }


def _load_existing_result(artifact_dir: Path, evaluation_id: str, identity_sha256: str) -> FinalEvaluationResult:
    manifest = _read_json(artifact_dir / "execution_manifest.json", "existing Final Evaluation manifest")
    if manifest.get("evaluation_id") != evaluation_id or manifest.get("input_identity_sha256") != identity_sha256:
        raise EvaluationError("Final Evaluation output directory exists with a different input identity")
    output_hashes = manifest.get("outputs_sha256")
    if not isinstance(output_hashes, dict) or set(output_hashes) != FINAL_EVALUATION_OUTPUTS:
        raise EvaluationError("existing Final Evaluation manifest does not list every required output")
    for filename, expected_digest in output_hashes.items():
        if _file_sha256(artifact_dir / filename) != expected_digest:
            raise EvaluationError(f"existing Final Evaluation artifact checksum mismatch: {filename}")
    return FinalEvaluationResult(
        evaluation_id=evaluation_id,
        artifact_dir=artifact_dir,
        evaluation=pd.read_csv(artifact_dir / "evaluation.csv", low_memory=False),
        coverage=pd.read_csv(artifact_dir / "coverage.csv", low_memory=False),
        model_metrics=pd.read_csv(artifact_dir / "model_metrics.csv", low_memory=False),
        pair_comparisons=pd.read_csv(artifact_dir / "pair_comparisons.csv", low_memory=False),
        hypothesis_results=pd.read_csv(artifact_dir / "hypothesis_results.csv", low_memory=False),
        portfolio_risk=pd.read_csv(artifact_dir / "portfolio_risk.csv", low_memory=False),
        manifest=manifest,
        b4_comparisons=pd.read_csv(artifact_dir / "b4_comparisons.csv", low_memory=False),
        reference_b0_b3_metrics=pd.read_csv(artifact_dir / "reference_b0_b3_metrics.csv", low_memory=False),
    )


def _summary_markdown(
    model_metrics: pd.DataFrame,
    pair_comparisons: pd.DataFrame,
    hypotheses: pd.DataFrame,
    coverage: pd.DataFrame,
    evaluation_id: str,
    b4_comparisons: pd.DataFrame | None = None,
) -> str:
    lines = [
        "# Stage 06 Final Evaluation",
        "",
        f"- Evaluation ID: `{evaluation_id}`",
        "- Test: 2025-10-01 through 2026-09-25; predictions come from the completed Final Replay.",
        "- Test data were not used to select models, hyperparameters, features, thresholds, or methods.",
        "",
        "## Test error on the common B0-B4 panel",
        "",
        "| Model | SPY MAE | IEF MAE | GLD MAE | Macro MAE | Macro RMSE |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for model in MODEL_NAMES:
        subset = model_metrics.loc[model_metrics["model_name"] == model].set_index("ticker")
        row = [model, *(subset.loc[ticker, "mae"] for ticker in SUPPORTED_TICKERS), subset.loc["MACRO", "mae"], subset.loc["MACRO", "rmse"]]
        formatted = ["NA" if pd.isna(value) else f"{float(value):.6f}" for value in row[1:]]
        lines.append(f"| {row[0]} | " + " | ".join(formatted) + " |")
    lines.extend(
        [
            "",
            "## Primary paired comparisons",
            "",
            "Positive DeltaMAE means B3 has lower paired absolute error than the baseline. Deltas are annualized-decimal values.",
            "",
            "| Comparison | Macro DeltaMAE | Relative improvement (%) | Paired N |",
            "|---|---:|---:|---:|",
        ]
    )
    for row in pair_comparisons.loc[pair_comparisons["ticker"] == "MACRO"].itertuples(index=False):
        delta = "NA" if pd.isna(row.delta_mae_baseline_minus_online) else f"{row.delta_mae_baseline_minus_online:.6f}"
        relative = "NA" if pd.isna(row.relative_improvement_pct) else f"{row.relative_improvement_pct:.2f}"
        lines.append(f"| {row.comparison_id} (B3 vs {row.baseline_model}) | {delta} | {relative} | {row.paired_n} |")
    if b4_comparisons is not None and not b4_comparisons.empty:
        lines.extend(
            [
                "",
                "## B4 (HAR-X OLS) retrospective paired comparisons",
                "",
                "Positive DeltaMAE means B4 (HAR_X_OLS) has lower paired absolute error than the comparator. These are retrospective non-hypothesis comparisons.",
                "",
                "| Comparison | Macro DeltaMAE | Relative improvement (%) | Paired N |",
                "|---|---:|---:|---:|",
            ]
        )
        for row in b4_comparisons.loc[b4_comparisons["ticker"] == "MACRO"].itertuples(index=False):
            delta = "NA" if pd.isna(row.delta_mae_comparator_minus_b4) else f"{row.delta_mae_comparator_minus_b4:.6f}"
            relative = "NA" if pd.isna(row.relative_improvement_pct) else f"{row.relative_improvement_pct:.2f}"
            lines.append(f"| {row.comparison_id} (B4 vs {row.comparator_model}) | {delta} | {relative} | {row.paired_n} |")
    lines.extend(
        [
            "",
            "## Hypothesis decisions",
            "",
            "| Hypothesis | Scope | Effect | Raw p | Holm-adjusted p | Decision |",
            "|---|---|---:|---:|---:|---|",
        ]
    )
    for row in hypotheses.itertuples(index=False):
        effect = "NA" if pd.isna(row.effect_size) else f"{float(row.effect_size):.6f}"
        raw_p = "NA" if pd.isna(row.raw_p_value) else f"{float(row.raw_p_value):.6f}"
        adjusted_p = "NA" if pd.isna(row.adjusted_p_value) else f"{float(row.adjusted_p_value):.6f}"
        lines.append(f"| {row.hypothesis_id} | {row.ticker_or_macro} | {effect} | {raw_p} | {adjusted_p} | {row.decision} |")
    test_coverage = coverage.loc[coverage["split"] == "test"]
    lines.extend(
        [
            "",
            "## Coverage",
            "",
            f"- Test expected anchors across ETF/model rows: {int(test_coverage['expected_eligible_prediction_anchors'].sum())}.",
            f"- Valid forecasts: {int(test_coverage['forecast_success_count'].sum())}; invalid/missing forecasts: {int(test_coverage['invalid_forecast_count'].sum() + test_coverage['missing_forecast_count'].sum())}.",
            f"- Pending labels: {int(test_coverage['pending_label_count'].sum())}; these are not forecast failures.",
            "",
            "## Limits and interpretation",
            "",
            "- The historical source snapshot was downloaded after the replay period. Point-in-time source availability is not verified; this is a Simulated Historical Replay.",
            "- Test estimates describe this frozen historical snapshot and replay protocol. They do not establish prospective live performance or causality.",
            "- H1 is a Train-only association test and does not establish forecast superiority. Non-significance is a valid result.",
            "- Portfolio risk is a forecast-based historical diagnostic; the default 50/30/20 weights can be changed in the consumer without retraining.",
            "",
        ]
    )
    return "\n".join(lines)


def run_final_evaluation(
    prepared: PreparedDataset,
    labels: pd.DataFrame,
    correlations: pd.DataFrame,
    *,
    replay_artifact_dir: str | Path,
    training_artifact_dir: str | Path,
    h1_artifact_dir: str | Path,
    correlation_source_path: str | Path,
    source_artifact_paths: Mapping[str, str | Path],
    output_root: str | Path,
    hypothesis_config_path: str | Path = "config/hypothesis_tests.yaml",
    evaluation_config_path: str | Path = "config/ml_evaluation.yaml",
    config: EvaluationConfig | None = None,
) -> FinalEvaluationResult:
    """Create immutable Final Test evidence from the selected Stage 03-05 artifacts."""
    effective_config = config or EvaluationConfig.from_yaml(evaluation_config_path)
    hypothesis_config, hypothesis_config_sha = _load_hypothesis_config(hypothesis_config_path)
    evaluation_config_path = Path(evaluation_config_path)
    evaluation_config_sha = _file_sha256(evaluation_config_path) if evaluation_config_path.is_file() else _canonical_sha256(effective_config.as_dict())
    replay_dir = Path(replay_artifact_dir).resolve()
    training_dir = Path(training_artifact_dir).resolve()
    h1_dir = Path(h1_artifact_dir).resolve()
    corr_path = Path(correlation_source_path).resolve()
    source_paths = {name: Path(path).resolve() for name, path in source_artifact_paths.items()}
    output_base = Path(output_root).resolve()

    replay_manifest, replay_outputs, replay_hashes = _verify_replay_artifacts(replay_dir, effective_config)
    training_hashes = _verify_training_artifacts(training_dir, replay_manifest)
    source_lineage = _verify_source_lineage(prepared, replay_manifest)
    h1_results, h1_spec, h1_hashes = _verify_h1_artifacts(h1_dir, source_lineage, effective_config)
    source_hashes = _verify_correlation_artifact(
        correlations,
        corr_path,
        source_paths,
        str(source_lineage["feature_run_id"]),
    )
    if "run_id" not in correlations or set(correlations["run_id"].astype(str)) != {str(source_lineage["feature_run_id"])}:
        raise EvaluationError("correlation parquet must contain only the Feature run referenced by Stage 03/05")
    if len(correlations) != len(pd.read_parquet(corr_path)):
        raise EvaluationError("loaded correlation frame does not match its source Parquet row count")

    code_hashes = _evaluation_code_hashes()
    analysis_config_id = _canonical_sha256(
        {
            "evaluation_config_sha256": evaluation_config_sha,
            "hypothesis_config_sha256": hypothesis_config_sha,
            "code_sha256_by_file": code_hashes,
        }
    )
    input_identity = {
        "stage03_lineage": source_lineage,
        "final_replay_experiment_id": replay_manifest["experiment_id"],
        "final_replay_outputs_sha256": replay_hashes,
        "stage04_artifacts_sha256": training_hashes,
        "stage03_h1_artifacts_sha256": h1_hashes,
        "stage03_source_artifacts_sha256": source_hashes,
        "evaluation_config_sha256": evaluation_config_sha,
        "hypothesis_config_sha256": hypothesis_config_sha,
        "code_sha256_by_file": code_hashes,
    }
    identity_sha = _canonical_sha256(input_identity)
    evaluation_id = identity_sha
    artifact_dir = output_base / evaluation_id
    if artifact_dir.exists():
        return _load_existing_result(artifact_dir, evaluation_id, identity_sha)

    output_base.mkdir(parents=True, exist_ok=True)
    temporary_dir = Path(tempfile.mkdtemp(prefix=f".stage06-{evaluation_id[:12]}-", dir=output_base))
    try:
        plan = _hypotheses_plan(
            config=effective_config,
            hypothesis_config=hypothesis_config,
            analysis_config_id=analysis_config_id,
            evaluation_config_sha256=evaluation_config_sha,
            hypothesis_config_sha256=hypothesis_config_sha,
            code_hashes=code_hashes,
            replay_manifest=replay_manifest,
        )
        write_json_atomic(temporary_dir / "hypotheses_plan.json", plan)

        expected_anchors = _normalised_expected_anchors(prepared, effective_config)
        failures = replay_outputs["forecast_failures.csv"]
        predictions = replay_outputs["asset_volatility_predictions.csv"]
        audit = build_forecast_audit(
            expected_anchors,
            labels,
            predictions,
            failures,
            cutoff=effective_config.data_cutoff,
            model_names=effective_config.model_names,
            validation_start_date=effective_config.validation_start_date,
            test_end_date=effective_config.test_end_date,
            tickers=effective_config.tickers,
        )
        _validate_joined_windows(audit)
        if audit.empty or not audit["split"].isin(("validation", "test")).all():
            raise EvaluationError("Final Evaluation has no eligible Validation/Test anchors or found out-of-scope rows")
        if (audit.loc[audit["label_status"].eq("MATURE"), "target_end_date"] > effective_config.data_cutoff).any():
            raise EvaluationError("a label beyond the strict cutoff was classified as mature")
        audit = _mark_common_panel(audit, effective_config.model_names)
        _assert_replay_evaluation_matches_audit(replay_outputs["evaluation.csv"], audit, effective_config)

        evaluations = _error_frame(audit)
        test_evaluations = evaluations.loc[evaluations["split"] == "test"].copy()
        if test_evaluations["prediction_date"].map(lambda value: value < effective_config.test_start_date or value > effective_config.test_end_date).any():
            raise EvaluationError("Final Test evaluation includes an anchor outside the locked study period")
        coverage = _build_coverage_summary(audit)
        model_metrics = _build_model_metrics(audit, effective_config)
        reference_b0_b3_metrics = _build_reference_b0_b3_metrics(audit, effective_config)
        pair_comparisons = _build_pair_comparisons(test_evaluations, effective_config)
        b4_comparisons = _build_b4_comparisons(audit, effective_config)
        thresholds, threshold_counts = _train_high_vol_thresholds(prepared, effective_config)
        high_volatility = _build_high_volatility_metrics(audit, thresholds, threshold_counts, effective_config)
        monthly = aggregate_period_metrics(expected_anchors, evaluations, period="month", model_names=effective_config.model_names)
        yearly = aggregate_period_metrics(expected_anchors, evaluations, period="year", model_names=effective_config.model_names)
        session_dates = {
            "validation": _xnys_sessions(effective_config, effective_config.validation_start_date, effective_config.validation_end_date),
            "test": _xnys_sessions(effective_config, effective_config.test_start_date, effective_config.test_end_date),
        }
        rolling = rolling_session_metrics(
            expected_anchors,
            evaluations,
            session_dates,
            window_size=effective_config.rolling_window_sessions,
            minimum_evaluable=effective_config.rolling_minimum_evaluable,
            model_names=effective_config.model_names,
        )
        drift_timeline = _build_drift_error_timeline(
            audit,
            replay_outputs["drift_errors.csv"],
            replay_outputs["drift_alerts.csv"],
            effective_config,
        )
        portfolio = _build_portfolio_risk_table(
            audit,
            correlations,
            feature_run_id=str(source_lineage["feature_run_id"]),
            config=effective_config,
        )
        hypothesis_results, bootstrap_diagnostics = _build_hypothesis_rows(
            h1_results,
            test_evaluations,
            session_dates["test"],
            hypothesis_config["hypotheses"],
            analysis_config_id,
            effective_config,
        )

        replay_test_evaluation = replay_outputs["evaluation.csv"].copy()
        replay_test_evaluation["prediction_date"] = pd.to_datetime(
            replay_test_evaluation["prediction_date"], errors="coerce"
        ).dt.date
        test_evaluation_output = replay_test_evaluation.loc[
            (replay_test_evaluation["split"] == "test")
            & replay_test_evaluation["prediction_date"].between(effective_config.test_start_date, effective_config.test_end_date)
        ].copy()
        if test_evaluation_output["prediction_id"].duplicated().any():
            raise EvaluationError("Final Test output contains duplicate immutable Predictions")
        outputs: dict[str, pd.DataFrame] = {
            "evaluation.csv": test_evaluation_output,
            "forecast_audit.csv": audit,
            "forecast_exceptions.csv": _build_forecast_exceptions(audit),
            "coverage.csv": coverage,
            "model_metrics.csv": model_metrics,
            "reference_b0_b3_metrics.csv": reference_b0_b3_metrics,
            "pair_comparisons.csv": pair_comparisons,
            "b4_comparisons.csv": b4_comparisons,
            "high_volatility_metrics.csv": high_volatility,
            "monthly_metrics.csv": monthly,
            "yearly_metrics.csv": yearly,
            "rolling_mae20.csv": rolling,
            "drift_error_timeline.csv": drift_timeline,
            "portfolio_risk.csv": portfolio,
            "hypothesis_results.csv": hypothesis_results,
            "bootstrap_diagnostics.csv": bootstrap_diagnostics,
        }
        for filename, frame in outputs.items():
            _write_csv(temporary_dir / filename, frame)

        for filename in (
            "H1_manifest.json",
            "H1_results.csv",
            "H1_sensitivity.csv",
            "H1_dataset_audit.csv",
            "H1_scatter_data.csv",
            "H1_scatter_plot_spec.json",
            "H1_scatter_plot.png",
            "H1_hypothesis_spec.json",
            "ML_dataset_preparation_report.json",
        ):
            shutil.copyfile(h1_dir / filename, temporary_dir / filename)
        summary = _summary_markdown(
            model_metrics,
            pair_comparisons,
            hypothesis_results,
            coverage,
            evaluation_id,
            b4_comparisons=b4_comparisons,
        )
        (temporary_dir / "evaluation_summary.md").write_text(summary, encoding="utf-8", newline="\n")

        # Recheck all read-only upstream evidence before committing the output directory.
        for filename, digest in replay_hashes.items():
            if _file_sha256(replay_dir / "outputs" / filename) != digest:
                raise EvaluationError(f"Final Replay artifact changed while Stage 06 was running: {filename}")
        for filename, digest in training_hashes.items():
            if _file_sha256(training_dir / filename) != digest:
                raise EvaluationError(f"Stage 04 artifact changed while Stage 06 was running: {filename}")
        for filename, digest in h1_hashes.items():
            if _file_sha256(h1_dir / filename) != digest:
                raise EvaluationError(f"Stage 03 H1 artifact changed while Stage 06 was running: {filename}")
        for name, path in source_paths.items():
            if _file_sha256(path) != source_hashes[name]:
                raise EvaluationError(f"Stage 03 source manifest/transaction changed while Stage 06 was running: {name}")
        if _file_sha256(corr_path) != source_hashes["correlations_parquet"]:
            raise EvaluationError("correlation Parquet changed while Stage 06 was running")

        output_hashes = {
            path.name: _file_sha256(path)
            for path in sorted(temporary_dir.iterdir(), key=lambda item: item.name)
            if path.is_file()
        }
        if set(output_hashes) != FINAL_EVALUATION_OUTPUTS:
            raise EvaluationError("Final Evaluation did not create the complete required evidence set")
        manifest = {
            "schema_version": "1.0.0",
            "stage": "06_final_evaluation_testing_portfolio",
            "status": "COMPLETED",
            "evaluation_id": evaluation_id,
            "input_identity_sha256": identity_sha,
            "analysis_config_id": analysis_config_id,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "evaluation_config": effective_config.as_dict(),
            "hypothesis_config_sha256": hypothesis_config_sha,
            "source_lineage": source_lineage,
            "final_replay_experiment_id": replay_manifest["experiment_id"],
            "final_replay_outputs_sha256": replay_hashes,
            "stage04_artifacts_sha256": training_hashes,
            "stage03_h1_artifacts_sha256": h1_hashes,
            "stage03_source_artifacts_sha256": source_hashes,
            "point_in_time_source_availability_verified": False,
            "counts": {
                "expected_validation_test_anchors": int(expected_anchors[["prediction_date", "ticker"]].drop_duplicates().shape[0]),
                "forecast_audit_rows": int(len(audit)),
                "test_expected_anchors": int(expected_anchors.loc[expected_anchors["split"] == "test", ["prediction_date", "ticker"]].drop_duplicates().shape[0]),
                "test_predictions": int((audit["split"].eq("test") & audit["forecast_status"].eq("VALID")).sum()),
                "test_evaluable_predictions": int(len(test_evaluation_output)),
                "test_pending_label_rows": int((audit["split"].eq("test") & audit["label_status"].eq("PENDING")).sum()),
                "test_forecast_exceptions": int((audit["split"].eq("test") & audit["forecast_status"].ne("VALID")).sum()),
                "test_common_panel_anchor_pairs": int(audit.loc[audit["split"].eq("test") & audit["is_common_panel"], ["prediction_date", "ticker"]].drop_duplicates().shape[0]),
            },
            "limitations": [
                "Historical snapshot availability on each simulated replay date is not verified; results are conditional on Simulated Historical Replay.",
                "Test outcomes describe this frozen snapshot and do not establish prospective live performance or causality.",
                "Portfolio risk is a forecast-based diagnostic using the approved 20-session rolling correlations and default long-only weights.",
            ],
            "versions": _package_versions(),
            "code_sha256_by_file": code_hashes,
            "outputs_sha256": output_hashes,
        }
        write_json_atomic(temporary_dir / "execution_manifest.json", manifest)
        if artifact_dir.exists():
            raise EvaluationError("Final Evaluation output appeared during execution; refusing to overwrite it")
        os.replace(temporary_dir, artifact_dir)
        return FinalEvaluationResult(
            evaluation_id=evaluation_id,
            artifact_dir=artifact_dir,
            evaluation=test_evaluation_output,
            coverage=coverage,
            model_metrics=model_metrics,
            pair_comparisons=pair_comparisons,
            hypothesis_results=hypothesis_results,
            portfolio_risk=portfolio,
            manifest=manifest,
            b4_comparisons=b4_comparisons,
            reference_b0_b3_metrics=reference_b0_b3_metrics,
        )
    except Exception:
        if temporary_dir.exists():
            shutil.rmtree(temporary_dir)
        raise


def run_from_config(config_path: str | Path = "config/ml_evaluation.yaml") -> FinalEvaluationResult:
    """Load and verify the approved Stage 03 inputs before running Stage 06."""
    import yaml

    from src.ml_dataset.dataset import DatasetConfig, load_validated_inputs, prepare_ml_dataset

    path = Path(config_path)
    if not path.is_file():
        raise FileNotFoundError(f"ML Evaluation config not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        paths = raw["paths"]
    except (OSError, TypeError, KeyError) as error:
        raise EvaluationError("ML Evaluation config must define its input/output paths") from error
    if not isinstance(paths, dict):
        raise EvaluationError("ML Evaluation paths must be a YAML mapping")
    required_paths = (
        "dataset_config",
        "features_parquet",
        "labels_parquet",
        "correlations_parquet",
        "feature_manifest",
        "target_manifest",
        "feature_transaction",
        "target_transaction",
        "replay_experiment_dir",
        "training_artifact_dir",
        "h1_artifact_dir",
        "hypothesis_tests_config",
        "output_root",
    )
    missing = [name for name in required_paths if name not in paths]
    if missing:
        raise EvaluationError(f"ML Evaluation config is missing paths: {missing}")
    dataset_config = DatasetConfig.from_yaml(paths["dataset_config"])
    loaded = load_validated_inputs(
        paths["features_parquet"],
        paths["labels_parquet"],
        paths["feature_manifest"],
        paths["target_manifest"],
        paths["feature_transaction"],
        paths["target_transaction"],
    )
    prepared = prepare_ml_dataset(loaded, config=dataset_config)
    correlations = pd.read_parquet(paths["correlations_parquet"])
    return run_final_evaluation(
        prepared,
        loaded.labels,
        correlations,
        replay_artifact_dir=paths["replay_experiment_dir"],
        training_artifact_dir=paths["training_artifact_dir"],
        h1_artifact_dir=paths["h1_artifact_dir"],
        correlation_source_path=paths["correlations_parquet"],
        source_artifact_paths={
            "feature_manifest": paths["feature_manifest"],
            "feature_transaction": paths["feature_transaction"],
            "target_manifest": paths["target_manifest"],
            "target_transaction": paths["target_transaction"],
        },
        output_root=paths["output_root"],
        hypothesis_config_path=paths["hypothesis_tests_config"],
        evaluation_config_path=path,
    )
