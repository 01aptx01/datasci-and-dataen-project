from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sys
import tempfile
import zipfile
from typing import Any

import numpy as np
import pandas as pd
import pandas_market_calendars as market_calendars
import yaml

from src.features.pipeline import CORE_FEATURE_COLUMNS, SUPPORTED_TICKERS
from src.ml_dataset.dataset import DatasetConfig, load_validated_inputs, prepare_ml_dataset
from src.ml_diagnostics.feature_drift import (
    FeatureDriftSettings,
    FeatureDriftTables,
    build_feature_drift_tables,
)
from src.ml_diagnostics.sources import SourceVerificationError, verify_source_identity


class FeatureDriftRunError(RuntimeError):
    """Raised when the source audit or deterministic diagnostic cannot complete."""


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _read_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise FeatureDriftRunError(f"NOT_AVAILABLE: required {label} is missing")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FeatureDriftRunError(f"SOURCE_MISMATCH: could not read {label}") from error
    if not isinstance(value, dict):
        raise FeatureDriftRunError(f"SOURCE_MISMATCH: {label} must be a JSON object")
    return value


def _relative_path(root: Path, value: str, label: str) -> Path:
    raw = Path(value)
    if raw.is_absolute() or ".." in raw.parts:
        raise FeatureDriftRunError(f"SOURCE_MISMATCH: {label} must be a safe repository-relative path")
    result = (root / raw).resolve()
    if not result.is_relative_to(root.resolve()):
        raise FeatureDriftRunError(f"SOURCE_MISMATCH: {label} escapes the repository")
    return result


def _require_hash(path: Path, expected: str | None, label: str) -> str:
    if not path.is_file():
        raise FeatureDriftRunError(f"NOT_AVAILABLE: required {label} is missing")
    actual = sha256_file(path)
    if not expected or actual != expected:
        raise FeatureDriftRunError(f"SOURCE_MISMATCH: {label} SHA-256 does not match its pinned identity")
    return actual


def _verify_artifact_group(directory: Path, expected_hashes: dict[str, str], label: str) -> None:
    for name, expected in sorted(expected_hashes.items()):
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise FeatureDriftRunError(f"SOURCE_MISMATCH: unsafe {label} artifact path")
        artifact = (directory / relative).resolve()
        if not artifact.is_relative_to(directory.resolve()):
            raise FeatureDriftRunError(f"SOURCE_MISMATCH: {label} artifact escapes its source directory")
        _require_hash(artifact, expected, f"{label} artifact {name}")


def _semantic_lineage(manifest: dict[str, Any]) -> dict[str, Any]:
    lineage = manifest.get("source_lineage", {})
    keys = (
        "feature_run_id",
        "target_run_id",
        "feature_parquet_sha256",
        "target_parquet_sha256",
        "source_input_sha256",
        "source_batch_ids",
        "source_versions",
        "feature_quality_finding_count",
        "target_quality_finding_count",
    )
    return {key: lineage.get(key) for key in keys}


def _load_frozen_identity(
    root: Path,
    config: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    sources = config["sources"]
    policy_path = _relative_path(root, sources["snapshot_policy"], "snapshot policy")
    zip_path = _relative_path(root, sources["snapshot_handoff_zip"], "snapshot handoff ZIP")
    policy = _read_json(policy_path, "snapshot policy")
    identity = policy.get("identity", {})
    for policy_key, config_key in (("evaluationId", "evaluation_id"), ("replayId", "replay_id"), ("strictCutoff", "strict_cutoff")):
        if identity.get(policy_key) != config.get(config_key):
            raise FeatureDriftRunError(f"SOURCE_MISMATCH: {config_key} does not match snapshot.policy.json")
    zip_sha = _require_hash(zip_path, policy.get("source", {}).get("zipSha256"), "frozen Stage 06 handoff ZIP")
    try:
        with zipfile.ZipFile(zip_path) as archive:
            if archive.testzip() is not None:
                raise FeatureDriftRunError("SOURCE_MISMATCH: frozen Stage 06 handoff ZIP failed CRC verification")
            member_name = policy["members"]["executionManifest"]
            member_path = Path(member_name)
            if member_path.is_absolute() or ".." in member_path.parts or "\\" in member_name:
                raise FeatureDriftRunError("SOURCE_MISMATCH: unsafe pinned execution manifest path")
            payload = archive.read(member_name)
    except (KeyError, OSError, zipfile.BadZipFile) as error:
        raise FeatureDriftRunError("SOURCE_MISMATCH: frozen Stage 06 execution manifest is unavailable") from error
    pinned_hash = policy.get("memberSha256", {}).get(member_name)
    if not pinned_hash or sha256_bytes(payload) != pinned_hash:
        raise FeatureDriftRunError("SOURCE_MISMATCH: execution manifest in the frozen handoff ZIP is not pinned")
    try:
        frozen_execution = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FeatureDriftRunError("SOURCE_MISMATCH: frozen execution manifest is invalid") from error
    if not isinstance(frozen_execution, dict):
        raise FeatureDriftRunError("SOURCE_MISMATCH: frozen execution manifest must be a JSON object")
    if frozen_execution.get("evaluation_id") != config["evaluation_id"] or frozen_execution.get("final_replay_experiment_id") != config["replay_id"]:
        raise FeatureDriftRunError("SOURCE_MISMATCH: frozen handoff Evaluation/Replay IDs do not match the diagnostic config")
    return policy, frozen_execution, {
        "snapshot_policy_sha256": sha256_file(policy_path),
        "snapshot_handoff_zip_sha256": zip_sha,
        "frozen_execution_manifest_sha256": pinned_hash,
    }


def _validate_splits(config: dict[str, Any], training_manifest: dict[str, Any], evaluation_manifest: dict[str, Any]) -> None:
    splits = config["splits"]
    training_splits = training_manifest.get("dataset_config", {}).get("splits", {})
    for name in ("train", "validation", "test"):
        if training_splits.get(name) != list(splits[name]):
            raise FeatureDriftRunError(f"SOURCE_MISMATCH: Stage 04 {name} dates do not match feature-drift.yaml")
    eval_config = evaluation_manifest.get("evaluation_config", {})
    expected_eval_dates = {
        "train_start_date": splits["train"][0],
        "train_end_date": splits["train"][1],
        "validation_start_date": splits["validation"][0],
        "validation_end_date": splits["validation"][1],
        "test_start_date": splits["test"][0],
        "test_end_date": splits["test"][1],
        "data_cutoff": config["strict_cutoff"],
    }
    for key, value in expected_eval_dates.items():
        if eval_config.get(key) != value:
            raise FeatureDriftRunError(f"SOURCE_MISMATCH: Stage 06 {key} does not match feature-drift.yaml")


def _settings(config: dict[str, Any]) -> FeatureDriftSettings:
    splits = config["splits"]
    metrics = config["metrics"]
    if config.get("market") != "XNYS" or metrics.get("threshold_quantile_method") != "linear":
        raise FeatureDriftRunError("SOURCE_MISMATCH: only the locked XNYS/linear-quantile diagnostic contract is supported")
    return FeatureDriftSettings(
        core_features=tuple(config["core_features"]),
        tickers=tuple(config["tickers"]),
        train_start=date.fromisoformat(splits["train"][0]),
        train_end=date.fromisoformat(splits["train"][1]),
        validation_start=date.fromisoformat(splits["validation"][0]),
        validation_end=date.fromisoformat(splits["validation"][1]),
        test_start=date.fromisoformat(splits["test"][0]),
        test_end=date.fromisoformat(splits["test"][1]),
        window_sizes=tuple(int(value) for value in config["windows"]["sizes"]),
        bin_count=int(metrics["quantile_bins"]),
        smoothing=float(metrics["psi_smoothing"]),
        threshold_percentile=float(metrics["threshold_percentile"]),
        minimum_calibration_windows=int(metrics["minimum_calibration_windows"]),
    )


def _prepare_sources(root: Path, config_path: Path) -> dict[str, Any]:
    try:
        raw_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise FeatureDriftRunError("SOURCE_MISMATCH: feature drift config could not be read") from error
    if not isinstance(raw_config, dict) or raw_config.get("schema_version") != "1.0.0":
        raise FeatureDriftRunError("SOURCE_MISMATCH: unsupported feature drift config")
    config = raw_config
    if tuple(config.get("core_features", ())) != tuple(CORE_FEATURE_COLUMNS):
        raise FeatureDriftRunError("SOURCE_MISMATCH: config Core 8 does not match the frozen Stage 04 contract")
    if tuple(config.get("tickers", ())) != tuple(SUPPORTED_TICKERS):
        raise FeatureDriftRunError("SOURCE_MISMATCH: config tickers do not match the frozen experiment")
    settings = _settings(config)

    policy, frozen_execution, pinned_file_hashes = _load_frozen_identity(root, config)
    sources = config["sources"]
    paths = {key: _relative_path(root, value, key) for key, value in sources.items()}
    feature_manifest = _read_json(paths["feature_manifest"], "Stage 02 Feature manifest")
    target_manifest = _read_json(paths["target_manifest"], "Stage 02 Target manifest")
    training_manifest = _read_json(paths["stage04_manifest"], "Stage 04 training manifest")
    evaluation_manifest = _read_json(paths["stage06_manifest"], "local Stage 06 execution manifest")
    preparation_report = _read_json(paths["stage03_report"], "Stage 03 preparation report")

    actual_feature_sha = sha256_file(paths["features"])
    actual_target_sha = sha256_file(paths["labels"])
    identity = verify_source_identity(
        feature_manifest,
        target_manifest,
        training_manifest,
        evaluation_manifest,
        preparation_report,
        actual_feature_sha256=actual_feature_sha,
        actual_target_sha256=actual_target_sha,
        expected_evaluation_id=config["evaluation_id"],
        expected_replay_id=config["replay_id"],
        expected_cutoff=config["strict_cutoff"],
        expected_feature_set_version=config["feature_set_version"],
        expected_core_features=settings.core_features,
    )
    if _semantic_lineage(evaluation_manifest) != _semantic_lineage(frozen_execution):
        raise FeatureDriftRunError("SOURCE_MISMATCH: local Stage 06 source lineage differs from the frozen dashboard handoff")
    for key in (
        "evaluation_config",
        "stage03_source_artifacts_sha256",
        "stage03_h1_artifacts_sha256",
        "stage04_artifacts_sha256",
        "outputs_sha256",
        "final_replay_outputs_sha256",
    ):
        if evaluation_manifest.get(key) != frozen_execution.get(key):
            raise FeatureDriftRunError(f"SOURCE_MISMATCH: local Stage 06 {key} differs from the frozen handoff")

    stage03_source_paths = {
        "correlations_parquet": paths["correlation_parquet"],
        "feature_manifest": paths["feature_manifest"],
        "feature_transaction": paths["feature_transaction"],
        "target_manifest": paths["target_manifest"],
        "target_transaction": paths["target_transaction"],
    }
    expected_stage03_sources = evaluation_manifest.get("stage03_source_artifacts_sha256", {})
    if set(stage03_source_paths) != set(expected_stage03_sources):
        raise FeatureDriftRunError("SOURCE_MISMATCH: Stage 03 source artifact list differs from the frozen lineage")
    for key, path in stage03_source_paths.items():
        _require_hash(path, expected_stage03_sources.get(key), f"Stage 03 source {key}")

    stage03_artifacts = evaluation_manifest.get("stage03_h1_artifacts_sha256", {})
    _verify_artifact_group(paths["stage03_directory"], stage03_artifacts, "Stage 03")
    stage04_artifacts = evaluation_manifest.get("stage04_artifacts_sha256", {})
    _verify_artifact_group(paths["stage04_directory"], stage04_artifacts, "Stage 04")
    _verify_artifact_group(paths["stage06_directory"], evaluation_manifest.get("outputs_sha256", {}), "Stage 06")
    report_sha = evaluation_manifest.get("outputs_sha256", {}).get("ML_dataset_preparation_report.json")
    _require_hash(paths["stage03_report"], report_sha, "Stage 03 preparation report")

    _validate_splits(config, training_manifest, evaluation_manifest)
    features_input = feature_manifest.get("input", {})
    if features_input.get("sha256") != identity["source_input_sha256"]:
        raise FeatureDriftRunError("SOURCE_MISMATCH: feature source input hash is not bound to the frozen run")
    if feature_manifest.get("outputs", {}).get("asset_volatility_features", {}).get("path", "").replace("\\", "/") != sources["features"]:
        raise FeatureDriftRunError("SOURCE_MISMATCH: feature manifest output path differs from the selected Parquet")
    if target_manifest.get("output", {}).get("path", "").replace("\\", "/") != sources["labels"]:
        raise FeatureDriftRunError("SOURCE_MISMATCH: target manifest output path differs from the selected Parquet")
    if target_manifest.get("target_version") != config["feature_set_version"]:
        raise FeatureDriftRunError("SOURCE_MISMATCH: target version does not match the frozen dataset version")
    if tuple(training_manifest.get("feature_order", ())) != settings.core_features:
        raise FeatureDriftRunError("SOURCE_MISMATCH: Stage 04 feature order does not match the frozen Core 8")

    try:
        loaded = load_validated_inputs(
            feature_path=paths["features"],
            label_path=paths["labels"],
            feature_manifest_path=paths["feature_manifest"],
            target_manifest_path=paths["target_manifest"],
            feature_transaction_path=paths["feature_transaction"],
            target_transaction_path=paths["target_transaction"],
        )
        dataset_config = DatasetConfig.from_yaml(_relative_path(root, "config/ml_dataset.yaml", "Stage 03 dataset config"))
        prepared = prepare_ml_dataset(loaded, config=dataset_config)
    except (FileNotFoundError, ValueError, OSError) as error:
        raise FeatureDriftRunError(f"SOURCE_MISMATCH: Stage 03 validated input loader rejected a source: {error}") from error

    prepared_summary = prepared.report.summary
    saved_summary = preparation_report.get("summary", {})
    for key in ("features_input_rows", "labels_input_rows", "join_matched_rows", "supervised_eligible_rows", "data_cutoff"):
        if prepared_summary.get(key) != saved_summary.get(key):
            raise FeatureDriftRunError(f"SOURCE_MISMATCH: reconstructed Stage 03 {key} differs from its saved audit")
    supervised = prepared.supervised.metadata
    train_counts = supervised.loc[supervised["split"].eq("train")].groupby("ticker").size().to_dict()
    expected_train_counts = {
        ticker: int(training_manifest["baselines"][ticker]["b0_train_row_count"])
        for ticker in settings.tickers
    }
    if train_counts != expected_train_counts:
        raise FeatureDriftRunError("SOURCE_MISMATCH: reconstructed model-eligible Train reference differs from Stage 04")
    validation_counts = supervised.loc[supervised["split"].eq("validation")].groupby("ticker").size().to_dict()
    expected_validation_counts = {
        row["ticker"]: int(row["b2_valid_count"])
        for row in training_manifest.get("selected_configs", [])
    }
    if validation_counts != expected_validation_counts:
        raise FeatureDriftRunError("SOURCE_MISMATCH: reconstructed Validation cohort differs from Stage 04 selection evidence")

    feature_frame = loaded.features.copy()
    dates = pd.to_datetime(feature_frame["date"], errors="coerce").dt.date
    if dates.isna().any() or dates.max() > settings.test_end:
        raise FeatureDriftRunError("SOURCE_MISMATCH: feature table contains an invalid date or a row after the strict cutoff")
    feature_frame["date"] = dates
    versions = set(feature_frame["feature_set_version"].astype(str))
    run_ids = set(feature_frame["run_id"].astype(str))
    if versions != {config["feature_set_version"]} or run_ids != {identity["feature_run_id"]}:
        raise FeatureDriftRunError("SOURCE_MISMATCH: feature rows do not match the verified Feature run/version")
    source_tickers = set(feature_frame["ticker"].astype(str))
    if source_tickers != set(settings.tickers):
        raise FeatureDriftRunError("SOURCE_MISMATCH: feature table does not contain exactly the three frozen tickers")

    source_start = min(feature_frame["date"])
    strict_cutoff = settings.test_end
    schedule = market_calendars.get_calendar("XNYS").schedule(
        start_date=source_start.isoformat(),
        end_date=strict_cutoff.isoformat(),
    )
    sessions = tuple(stamp.date() for stamp in schedule.index)
    expected_sessions = set(sessions)
    for ticker in settings.tickers:
        ticker_dates = set(feature_frame.loc[feature_frame["ticker"].eq(ticker), "date"])
        if ticker_dates != expected_sessions:
            raise FeatureDriftRunError(f"SOURCE_MISMATCH: {ticker} feature rows do not match every XNYS session through the cutoff")

    ready_mask = feature_frame["is_model_ready"].astype(bool) & ~feature_frame["is_warmup_buffer"].astype(bool)
    ready_features = feature_frame.loc[ready_mask].copy()
    finite = np.isfinite(ready_features.loc[:, list(settings.core_features)].to_numpy(dtype=float))
    if not finite.all():
        raise FeatureDriftRunError("SOURCE_MISMATCH: model-ready Core 8 includes a non-finite value")

    train_keys = supervised.loc[supervised["split"].eq("train"), ["date", "ticker"]]
    train_reference = feature_frame.merge(train_keys, on=["date", "ticker"], how="inner", validate="one_to_one")
    code_hashes = {
        path.name: sha256_file(path)
        for path in sorted(Path(__file__).parent.glob("*.py"))
    }
    config_sha = sha256_file(config_path)
    source_files = {
        "feature_parquet": {"path": sources["features"], "sha256": actual_feature_sha},
        "target_parquet": {"path": sources["labels"], "sha256": actual_target_sha},
        "feature_manifest": {"path": sources["feature_manifest"], "sha256": sha256_file(paths["feature_manifest"])},
        "feature_publish_transaction": {"path": sources["feature_transaction"], "sha256": sha256_file(paths["feature_transaction"])},
        "target_manifest": {"path": sources["target_manifest"], "sha256": sha256_file(paths["target_manifest"])},
        "target_publish_transaction": {"path": sources["target_transaction"], "sha256": sha256_file(paths["target_transaction"])},
        "stage03_preparation_report": {"path": sources["stage03_report"], "sha256": sha256_file(paths["stage03_report"])},
        "stage04_training_manifest": {"path": sources["stage04_manifest"], "sha256": sha256_file(paths["stage04_manifest"])},
        "stage06_execution_manifest": {"path": sources["stage06_manifest"], "sha256": sha256_file(paths["stage06_manifest"])},
        "correlation_parquet": {"path": sources["correlation_parquet"], "sha256": sha256_file(paths["correlation_parquet"])},
        "snapshot_policy": {"path": sources["snapshot_policy"], "sha256": pinned_file_hashes["snapshot_policy_sha256"]},
        "snapshot_handoff_zip": {"path": sources["snapshot_handoff_zip"], "sha256": pinned_file_hashes["snapshot_handoff_zip_sha256"]},
        "frozen_execution_manifest": {"path": policy["members"]["executionManifest"], "sha256": pinned_file_hashes["frozen_execution_manifest_sha256"]},
    }
    return {
        "config": config,
        "settings": settings,
        "identity": identity,
        "feature_frame": ready_features,
        "train_reference": train_reference,
        "market_sessions": sessions,
        "prepared_summary": prepared_summary,
        "train_counts": train_counts,
        "validation_counts": validation_counts,
        "feature_rows_by_ticker": {
            ticker: int(ready_features["ticker"].eq(ticker).sum()) for ticker in settings.tickers
        },
        "source_files": source_files,
        "config_sha256": config_sha,
        "code_sha256_by_file": code_hashes,
    }


def _csv_bytes(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False, lineterminator="\n", na_rep="", float_format="%.17g").encode("utf-8")


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _summary_markdown(
    diagnostic_id: str,
    identity: dict[str, Any],
    tables: FeatureDriftTables,
    train_counts: dict[str, int],
) -> bytes:
    signals = int(tables.metrics["status"].eq("DRIFT_SIGNAL").sum())
    no_signal = int(tables.metrics["status"].eq("NO_SIGNAL").sum())
    insufficient = int(tables.metrics["status"].eq("INSUFFICIENT_DATA").sum())
    calibration_counts = ", ".join(
        f"{row.ticker}/{row.feature_name}/{int(row.window_size)}: {int(row.valid_window_count)}"
        for row in tables.calibration.itertuples(index=False)
    )
    train = ", ".join(f"{ticker} {count}" for ticker, count in train_counts.items())
    text = f"""# Feature Drift diagnostic

| Identity | Value |
|---|---|
| Diagnostic ID | `{diagnostic_id}` |
| Evaluation | `{identity['evaluation_id']}` |
| Replay | `{identity['replay_id']}` |
| Strict cutoff | `{identity['strict_cutoff']}` |
| Feature run | `{identity['feature_run_id']}` · version `{identity['feature_set_version']}` |

## Interpretation

This read-only diagnostic compares each Core 8 feature separately for SPY, IEF and GLD. The fixed reference uses the model-eligible Train rows (`{train}`). The current distribution uses trailing XNYS feature sessions ending on the recorded Test date. Validation windows calibrate the per-ticker/per-feature 95th-percentile heuristic thresholds. PSI uses fixed Train quantile bins and Jeffreys smoothing of 0.5 per bin on both distributions.

The recorded source snapshot is a simulated historical analysis. Its availability at the original observation dates was not independently verified (`point_in_time_source_availability_verified: {str(identity['point_in_time_source_availability_verified']).lower()}`). A distribution signal does not establish concept drift, forecast degradation, causality or future risk. Feature Drift does not change forecasts, ADWIN, portfolio calculations or H1–H3.

## Coverage

- Test rows: {len(tables.metrics):,} (`DRIFT_SIGNAL` {signals:,}; `NO_SIGNAL` {no_signal:,}; `INSUFFICIENT_DATA` {insufficient:,}).
- Calibration windows by ticker, feature and length: {calibration_counts}.
- Methods and source checks: see `feature_drift_manifest.json`.
"""
    return text.encode("utf-8")


def _write_diagnostic(
    repo_root: Path,
    prepared: dict[str, Any],
    tables: FeatureDriftTables,
) -> tuple[Path, dict[str, Any]]:
    config = prepared["config"]
    identity = prepared["identity"]
    configuration = {
        "schema_version": config["schema_version"],
        "market": config["market"],
        "evaluation_id": config["evaluation_id"],
        "replay_id": config["replay_id"],
        "strict_cutoff": config["strict_cutoff"],
        "feature_set_version": config["feature_set_version"],
        "tickers": config["tickers"],
        "core_features": config["core_features"],
        "splits": config["splits"],
        "windows": config["windows"],
        "metrics": config["metrics"],
    }
    id_material = canonical_json({
        "configuration": configuration,
        "configuration_sha256": prepared["config_sha256"],
        "sources": prepared["source_files"],
        "source_identity": identity,
        "code_sha256_by_file": prepared["code_sha256_by_file"],
    })
    diagnostic_id = sha256_bytes(id_material.encode("utf-8"))
    for frame in (tables.metrics, tables.histograms, tables.reference_summary, tables.calibration):
        frame["diagnostic_id"] = diagnostic_id
    if not tables.metrics.empty:
        tables.metrics["evaluation_id"] = identity["evaluation_id"]
        tables.metrics["replay_id"] = identity["replay_id"]
        tables.metrics["source_feature_run_id"] = identity["feature_run_id"]
        tables.metrics["feature_set_version"] = identity["feature_set_version"]

    output_root = _relative_path(repo_root, config["outputs"]["root"], "diagnostic output root")
    active_pointer = _relative_path(repo_root, config["outputs"]["active_pointer"], "diagnostic active pointer")
    output_root.mkdir(parents=True, exist_ok=True)
    if not active_pointer.is_relative_to(output_root):
        raise FeatureDriftRunError("SOURCE_MISMATCH: active pointer must stay inside the generated diagnostic directory")

    table_payloads = {
        "feature_drift_metrics.csv": _csv_bytes(tables.metrics),
        "feature_drift_histograms.csv": _csv_bytes(tables.histograms),
        "feature_drift_reference_summary.csv": _csv_bytes(tables.reference_summary),
        "feature_drift_calibration.csv": _csv_bytes(tables.calibration),
        "feature_drift_summary.md": _summary_markdown(diagnostic_id, identity, tables, prepared["train_counts"]),
    }
    file_records: dict[str, dict[str, Any]] = {}
    for name, payload in table_payloads.items():
        frame = {
            "feature_drift_metrics.csv": tables.metrics,
            "feature_drift_histograms.csv": tables.histograms,
            "feature_drift_reference_summary.csv": tables.reference_summary,
            "feature_drift_calibration.csv": tables.calibration,
        }.get(name)
        file_records[name] = {
            "path": name,
            "sha256": sha256_bytes(payload),
            "bytes": len(payload),
            "rows": int(len(frame)) if frame is not None else None,
        }

    manifest: dict[str, Any] = {
        "schemaVersion": "1.0.0",
        "status": "COMPLETED",
        "diagnosticId": diagnostic_id,
        "diagnosticIdentityCanonical": id_material,
        "evaluationId": identity["evaluation_id"],
        "replayId": identity["replay_id"],
        "strictCutoff": identity["strict_cutoff"],
        "featureSetVersion": identity["feature_set_version"],
        "source": {
            "featureRunId": identity["feature_run_id"],
            "targetRunId": identity["target_run_id"],
            "trainingRunId": identity["training_run_id"],
            "featureParquetSha256": identity["feature_parquet_sha256"],
            "targetParquetSha256": identity["target_parquet_sha256"],
            "sourceInputSha256": identity["source_input_sha256"],
            "featureQualityFindingCount": identity["feature_quality_finding_count"],
            "targetQualityFindingCount": identity["target_quality_finding_count"],
            "pointInTimeSourceAvailabilityVerified": identity["point_in_time_source_availability_verified"],
            "sourceFiles": prepared["source_files"],
        },
        "configuration": configuration,
        "configurationSha256": prepared["config_sha256"],
        "codeSha256ByFile": prepared["code_sha256_by_file"],
        "method": {
            "reference": "per-ticker model-eligible supervised Train rows",
            "currentWindow": "consecutive XNYS sessions ending at as_of_date, feature values only",
            "wasserstein": "1D Wasserstein distance divided by fixed Train IQR when IQR is positive",
            "psi": "fixed Train quantile bins; Jeffreys smoothing 0.5 per bin on both distributions",
            "threshold": "per-ticker/per-feature empirical linear 95th percentile of complete Validation windows",
            "signalType": "heuristic diagnostic signal; not a significance test",
            "missingSessions": "INSUFFICIENT_DATA; no fill, interpolation or shorter replacement window",
        },
        "coverage": {
            "featureRowsByTicker": prepared["feature_rows_by_ticker"],
            "modelEligibleTrainRowsByTicker": prepared["train_counts"],
            "modelEligibleValidationRowsByTicker": prepared["validation_counts"],
            "validationCalibrationRows": int(len(tables.calibration)),
            "testMetricRows": int(len(tables.metrics)),
            "testHistogramRows": int(len(tables.histograms)),
            "pointInTimeSourceAvailabilityVerified": identity["point_in_time_source_availability_verified"],
        },
        "limitations": [
            "Historical source availability at each simulated observation date is not verified; this is simulated historical analysis, not prospective monitoring.",
            "Feature distribution changes alone do not establish concept drift, causality or future model performance.",
            "Overlapping daily windows and 24 Core Feature streams are correlated; heuristic thresholds are not independent hypothesis tests.",
            "This package does not change Stage 01-06 outputs, B0-B3 forecasts, ADWIN, portfolio calculations or official H1-H3 decisions.",
        ],
        "files": file_records,
    }
    manifest_payload = _json_bytes(manifest)
    table_payloads["feature_drift_manifest.json"] = manifest_payload
    checksum_names = sorted(table_payloads)
    checksum_payload = "".join(
        f"{sha256_bytes(table_payloads[name])}  {name}\n" for name in checksum_names
    ).encode("utf-8")
    table_payloads["CHECKSUMS.sha256"] = checksum_payload

    final_dir = output_root / diagnostic_id
    temp_dir = Path(tempfile.mkdtemp(prefix=".tmp-feature-drift-", dir=output_root))
    try:
        for name, payload in table_payloads.items():
            (temp_dir / name).write_bytes(payload)
        from src.ml_diagnostics.export import create_diagnostic_archive

        temp_package = temp_dir / "feature_drift_package.zip"
        create_diagnostic_archive(temp_dir, temp_package)
        package_payload = temp_package.read_bytes()
        if final_dir.exists():
            if not final_dir.is_dir():
                raise FeatureDriftRunError("SOURCE_MISMATCH: content-addressed diagnostic path is not a directory")
            expected_names = {*table_payloads, "feature_drift_package.zip"}
            current_names = {path.name for path in final_dir.iterdir()}
            if current_names != expected_names or any((final_dir / name).read_bytes() != payload for name, payload in table_payloads.items()) or (final_dir / "feature_drift_package.zip").read_bytes() != package_payload:
                raise FeatureDriftRunError("SOURCE_MISMATCH: existing content-addressed diagnostic output differs")
            shutil.rmtree(temp_dir)
        else:
            os.replace(temp_dir, final_dir)
    except Exception:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        raise

    package_path = final_dir / "feature_drift_package.zip"
    active = {
        "diagnosticId": diagnostic_id,
        "packagePath": package_path.relative_to(repo_root).as_posix(),
        "packageSha256": sha256_file(package_path),
    }
    active_temp = active_pointer.with_suffix(".tmp")
    active_temp.write_bytes(_json_bytes(active))
    os.replace(active_temp, active_pointer)
    return final_dir, {**manifest, "packageSha256": active["packageSha256"]}


def run_feature_drift(repo_root: Path, config_path: Path | None = None) -> tuple[Path, dict[str, Any]]:
    root = repo_root.resolve()
    effective_config = config_path or root / "config" / "feature_drift.yaml"
    if not effective_config.is_absolute():
        effective_config = (root / effective_config).resolve()
    if not effective_config.is_relative_to(root):
        raise FeatureDriftRunError("SOURCE_MISMATCH: feature drift config must stay inside the repository")
    prepared = _prepare_sources(root, effective_config)
    tables = build_feature_drift_tables(
        prepared["feature_frame"],
        prepared["train_reference"],
        prepared["market_sessions"],
        prepared["settings"],
    )
    return _write_diagnostic(root, prepared, tables)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a source-verified, read-only Feature Drift diagnostic")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--config", type=Path, default=Path("config/feature_drift.yaml"))
    args = parser.parse_args()
    try:
        output, manifest = run_feature_drift(args.repo_root, args.config)
    except (FeatureDriftRunError, SourceVerificationError, ValueError, KeyError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(f"Feature Drift diagnostic completed: {manifest['diagnosticId']}")
    print(f"Output: {output.relative_to(args.repo_root.resolve()).as_posix()}")
    print(f"Package SHA-256: {manifest['packageSha256']}")
    print(f"Test metric rows: {manifest['coverage']['testMetricRows']:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
