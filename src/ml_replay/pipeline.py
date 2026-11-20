from __future__ import annotations

import hashlib
import json
import math
import pickle
import platform
import subprocess
import uuid
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

import joblib
import numpy as np
import pandas as pd
import pandas_market_calendars as market_calendars
import yaml
from river.drift import ADWIN

from src.features.pipeline import CORE_FEATURE_COLUMNS, SUPPORTED_TICKERS
from src.ml_dataset.dataset import DatasetConfig, PreparedDataset
from src.ml_replay.config import ReplayConfig, ReplayError
from src.ml_replay.storage import (
    begin_session,
    canonical_json,
    commit_session,
    json_default,
    load_checkpoint,
    read_json,
    sha256_bytes,
    sha256_file,
    stage_table,
    write_json_atomic,
)
from src.ml_training.config import CandidateConfig, TrainingConfig
from src.ml_training.pipeline import model_state_sha256


PREDICTION_COLUMNS = [
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
]
EVALUATION_COLUMNS = [
    "experiment_id",
    "prediction_id",
    "prediction_date",
    "split",
    "ticker",
    "model_name",
    "model_version",
    "prediction_mode",
    "forecast_horizon_trading_days",
    "target_start_date",
    "target_end_date",
    "predicted_vol_annualized",
    "target_realized_vol_5d",
    "target_version",
    "feature_set_version",
    "input_snapshot_id",
    "absolute_error",
    "squared_error",
    "evaluation_date",
    "label_available_replay_date",
    "prediction_run_id",
    "evaluation_run_id",
]
DRIFT_ERROR_COLUMNS = [
    "experiment_id",
    "prediction_id",
    "prediction_date",
    "evaluation_date",
    "ticker",
    "absolute_error",
    "adwin_delta",
    "adwin_width",
    "adwin_estimation",
    "drift_detected",
    "prediction_run_id",
    "evaluation_run_id",
]
DRIFT_ALERT_COLUMNS = DRIFT_ERROR_COLUMNS.copy()
UPDATE_COLUMNS = [
    "experiment_id",
    "update_date",
    "ticker",
    "anchor_date",
    "target_end_date",
    "target_realized_vol_5d",
    "batch_id",
    "batch_size",
    "b3_state_version_before",
    "b3_state_version_after",
    "run_id",
]
FAILURE_COLUMNS = [
    "experiment_id",
    "prediction_date",
    "ticker",
    "model_name",
    "failure_type",
    "reason",
    "run_id",
]
DAILY_COVERAGE_COLUMNS = [
    "experiment_id",
    "prediction_date",
    "split",
    "ticker",
    "model_name",
    "expected_count",
    "published_count",
    "invalid_count",
    "missing_feature_count",
    "run_id",
]
COVERAGE_COLUMNS = DAILY_COVERAGE_COLUMNS + [
    "mature_evaluable_count",
    "pending_label_count",
    "evaluation_failure_count",
]
MODEL_NAMES = {
    "B0": "CONSTANT_BASELINE",
    "B1": "ROLLING_20D_BASELINE",
    "B2": "STATIC_SGD",
    "B3": "ONLINE_SGD",
}
MODEL_ORDER = ("B0", "B1", "B2", "B3")
REQUIRED_LABEL_COLUMNS = {
    "date",
    "ticker",
    "target_start_date",
    "target_end_date",
    "target_obs_count",
    "target_realized_vol_5d",
    "is_label_mature",
    "target_version",
}


@dataclass
class ReplayResult:
    experiment_id: str
    run_id: str
    artifact_dir: Path
    predictions: pd.DataFrame
    evaluations: pd.DataFrame
    drift_errors: pd.DataFrame
    drift_alerts: pd.DataFrame
    updated_labels: pd.DataFrame
    forecast_failures: pd.DataFrame
    coverage: pd.DataFrame
    committed_sessions: tuple[date, ...]
    experiment_manifest: dict[str, Any]
    final_b3_state_sha256_by_ticker: dict[str, str]
    final_b2_state_sha256_by_ticker: dict[str, str]
    final_adwin_state_sha256_by_ticker: dict[str, str]
    completed: bool


@dataclass
class _RuntimeState:
    b3_models: dict[str, Any]
    scalers: dict[str, Any]
    adwin_detectors: dict[str, ADWIN]
    updated_label_keys: set[tuple[date, str]]
    processed_error_ids: set[str]
    evaluated_prediction_ids: set[str]
    pending_predictions: list[dict[str, Any]]
    last_b3_target_end_by_ticker: dict[str, date]
    last_committed_session: date | None = None


def _as_date(value: Any, name: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        stamp = pd.Timestamp(value)
    except (TypeError, ValueError) as error:
        raise ReplayError(f"{name} must be a valid market date") from error
    if pd.isna(stamp):
        raise ReplayError(f"{name} must be a valid market date")
    return stamp.date()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _package_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {"python": platform.python_version()}
    for package in (
        "scikit-learn",
        "numpy",
        "pandas",
        "pandas-market-calendars",
        "joblib",
        "river",
    ):
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            versions[package] = None
    return versions


def _frame_sha256(frame: pd.DataFrame) -> str:
    canonical = frame.copy()
    if {"date", "ticker"}.issubset(canonical.columns):
        canonical = canonical.sort_values(["date", "ticker"], kind="stable")
    canonical = canonical.reset_index(drop=True)
    digest = hashlib.sha256()
    digest.update(canonical_json({"columns": list(canonical.columns), "dtypes": [str(v) for v in canonical.dtypes]}).encode())
    try:
        hashes = pd.util.hash_pandas_object(canonical, index=False, categorize=True)
    except TypeError as error:
        raise ReplayError(f"could not fingerprint input table: {error}") from error
    digest.update(hashes.to_numpy(dtype=np.uint64).tobytes())
    return digest.hexdigest()


def _input_snapshot_id(prepared: PreparedDataset, labels: pd.DataFrame) -> str:
    tables = {
        "prediction_X": _frame_sha256(prepared.prediction.X),
        "prediction_metadata": _frame_sha256(prepared.prediction.metadata),
        "supervised_X": _frame_sha256(prepared.supervised.X),
        "supervised_metadata": _frame_sha256(prepared.supervised.metadata),
        "supervised_y": _frame_sha256(prepared.supervised.y.to_frame() if prepared.supervised.y is not None else pd.DataFrame()),
        "audit": _frame_sha256(prepared.audit),
        "labels": _frame_sha256(labels),
    }
    return sha256_bytes(canonical_json({"lineage": prepared.report.lineage, "tables": tables}).encode("utf-8"))


def _code_sha256() -> str:
    repository_root = Path(__file__).resolve().parents[2]
    digest = hashlib.sha256()
    paths: list[Path] = []
    for package in ("features", "targets", "ml_dataset", "ml_training", "ml_replay"):
        paths.extend((repository_root / "src" / package).glob("*.py"))
    paths.extend(
        repository_root / "config" / filename
        for filename in ("ml_dataset.yaml", "ml_training.yaml", "ml_replay.yaml", "models.yaml")
    )
    paths.extend(
        repository_root / "docs" / "contract" / filename
        for filename in (
            "data_contract.md",
            "datadict.md",
            "feature_contract.md",
            "target_contract.md",
            "prediction_contract.md",
        )
    )
    paths.append(repository_root / "pyproject.toml")
    paths = sorted(set(paths))
    for path in paths:
        resolved = path.resolve()
        if not resolved.is_file():
            continue
        digest.update(resolved.relative_to(repository_root).as_posix().encode("utf-8"))
        digest.update(resolved.read_bytes())
    return digest.hexdigest()


def _git_commit_sha() -> str | None:
    repository_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository_root,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _contract_identity(prepared: PreparedDataset, labels: pd.DataFrame) -> dict[str, Any]:
    repository_root = Path(__file__).resolve().parents[2]
    contract_paths = {
        name: repository_root / "docs" / "contract" / filename
        for name, filename in (
            ("data", "data_contract.md"),
            ("data_dictionary", "datadict.md"),
            ("features", "feature_contract.md"),
            ("targets", "target_contract.md"),
            ("predictions", "prediction_contract.md"),
        )
    }
    return {
        "feature_versions": sorted(
            str(value) for value in prepared.prediction.metadata.get("feature_set_version", pd.Series(dtype=str)).dropna().unique()
        ),
        "target_versions": sorted(str(value) for value in labels["target_version"].dropna().unique()),
        "dataset_config_versions": list(prepared.report.versions.get("dataset_config", [])),
        "contract_file_sha256": {
            name: sha256_file(path) for name, path in contract_paths.items() if path.is_file()
        },
        "prediction_schema_sha256": sha256_bytes(canonical_json(PREDICTION_COLUMNS).encode("utf-8")),
    }


def _validate_model_names() -> None:
    path = Path("config/models.yaml")
    if not path.is_file():
        raise ReplayError("config/models.yaml is required for Stage 05 model identity")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    configured = {
        str(item.get("model_id")): str(item.get("model_name"))
        for item in raw.get("models", [])
        if isinstance(item, dict)
    }
    if configured != MODEL_NAMES:
        raise ReplayError("config/models.yaml model IDs/names do not match the locked B0-B3 contract")


def _input_maps(
    prepared: PreparedDataset,
    labels: pd.DataFrame,
) -> tuple[dict[tuple[date, str], np.ndarray], dict[tuple[date, str], dict[str, Any]], dict[tuple[date, str], dict[str, Any]], dict[tuple[date, str], dict[str, Any]]]:
    if tuple(prepared.prediction.X.columns) != tuple(CORE_FEATURE_COLUMNS):
        raise ReplayError("prediction feature order does not match the locked eight core features")
    if len(prepared.prediction.X) != len(prepared.prediction.metadata):
        raise ReplayError("prediction features and metadata must be aligned")
    missing_labels = REQUIRED_LABEL_COLUMNS.difference(labels.columns)
    if missing_labels:
        raise ReplayError(f"labels are missing required columns: {sorted(missing_labels)}")
    if labels.duplicated(["date", "ticker"]).any():
        raise ReplayError("label primary key (date, ticker) must be unique")
    if prepared.audit.duplicated(["date", "ticker"]).any():
        raise ReplayError("dataset audit primary key (date, ticker) must be unique")

    feature_map: dict[tuple[date, str], np.ndarray] = {}
    feature_metadata: dict[tuple[date, str], dict[str, Any]] = {}
    for metadata_row, values in zip(
        prepared.prediction.metadata.to_dict("records"),
        prepared.prediction.X.to_numpy(dtype=float),
    ):
        anchor = _as_date(metadata_row["date"], "feature date")
        ticker = str(metadata_row["ticker"])
        if ticker not in SUPPORTED_TICKERS:
            raise ReplayError(f"unsupported ticker in prediction view: {ticker}")
        key = (anchor, ticker)
        if key in feature_map:
            raise ReplayError(f"prediction feature primary key is duplicated: {key}")
        if not np.isfinite(values).all():
            raise ReplayError(f"prediction view contains non-finite core features for {key}")
        feature_map[key] = values.copy()
        feature_metadata[key] = metadata_row

    audit_map = {
        (_as_date(row["date"], "audit date"), str(row["ticker"])): row
        for row in prepared.audit.to_dict("records")
    }
    label_map: dict[tuple[date, str], dict[str, Any]] = {}
    for row in labels.to_dict("records"):
        key = (_as_date(row["date"], "label date"), str(row["ticker"]))
        if key[1] not in SUPPORTED_TICKERS:
            raise ReplayError(f"unsupported ticker in labels: {key[1]}")
        label_map[key] = row
    return feature_map, feature_metadata, audit_map, label_map


def _load_initial_artifact(
    artifact_dir: str | Path,
    prepared: PreparedDataset,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, date], set[tuple[date, str]]]:
    directory = Path(artifact_dir).expanduser().resolve()
    manifest_path = directory / "training_manifest.json"
    manifest = read_json(manifest_path, "Stage 04 training manifest")
    if manifest.get("stage") != "04_models_training_and_validation" or manifest.get("selection_status") != "selected":
        raise ReplayError("Stage 04 artifact is not a completed selected training run")
    if manifest.get("test_used_for_training_or_selection") is not False:
        raise ReplayError("Stage 04 artifact does not prove that Test was excluded from selection")
    if canonical_json(manifest.get("source_lineage", {})) != canonical_json(prepared.report.lineage):
        raise ReplayError("Stage 04 training source lineage does not match the prepared dataset")
    artifact_hashes = manifest.get("artifact_sha256")
    if not isinstance(artifact_hashes, dict):
        raise ReplayError("Stage 04 manifest has no artifact checksums")
    required_artifacts = (
        "validation_candidate_evaluations.csv",
        "selected_configs.json",
        "initial_models.joblib",
        "training_config.json",
    )
    for filename in required_artifacts:
        path = directory / filename
        if not path.is_file() or sha256_file(path) != artifact_hashes.get(filename):
            raise ReplayError(f"Stage 04 artifact checksum is invalid: {filename}")

    trained_versions = manifest.get("versions", {})
    current_versions = _package_versions()
    for package in ("scikit-learn", "numpy", "pandas", "pandas-market-calendars", "joblib"):
        if trained_versions.get(package) != current_versions.get(package):
            raise ReplayError(f"Stage 04 artifact {package} version does not match the current environment")
    try:
        bundle = joblib.load(directory / "initial_models.joblib")
    except Exception as error:
        raise ReplayError("could not load the trusted Stage 04 model bundle") from error
    if not isinstance(bundle, dict) or bundle.get("bundle_version") != "1.0.0":
        raise ReplayError("unsupported Stage 04 initial model bundle version")
    tickers = bundle.get("tickers", {})
    baselines = bundle.get("baselines", {})
    if set(tickers) != set(SUPPORTED_TICKERS) or set(baselines) != set(SUPPORTED_TICKERS):
        raise ReplayError("Stage 04 artifacts must contain B0-B3 states for SPY, IEF, and GLD")

    supervised = prepared.supervised
    if supervised.y is None or len(supervised.X) != len(supervised.metadata) or len(supervised.y) != len(supervised.metadata):
        raise ReplayError("prepared supervised features, metadata, and target must be aligned")
    train_metadata = supervised.metadata.reset_index(drop=True)
    train_y = supervised.y.reset_index(drop=True)
    seed_keys: set[tuple[date, str]] = set()
    last_train_target_end: dict[str, date] = {}
    for ticker in SUPPORTED_TICKERS:
        pair = tickers[ticker]
        expected_order = tuple(CORE_FEATURE_COLUMNS)
        if tuple(pair.get("feature_order", ())) != expected_order:
            raise ReplayError(f"{ticker} Stage 04 feature order is incompatible")
        initial_hash = str(pair.get("state_sha256", ""))
        actual_b2 = model_state_sha256(pair["b2"], pair["scaler"])
        actual_b3 = model_state_sha256(pair["b3"], pair["scaler"])
        manifest_hash = manifest.get("initial_state_sha256_by_ticker", {}).get(ticker)
        if not initial_hash or actual_b2 != initial_hash or actual_b3 != initial_hash or manifest_hash != initial_hash:
            raise ReplayError(f"{ticker} B2/B3 initial model and scaler hashes do not match")
        selected = pair.get("selected_candidate", {})
        candidate = CandidateConfig(
            eta0=float(selected["eta0"]),
            alpha=float(selected["alpha"]),
            max_iter=int(selected["max_iter"]),
        )
        if candidate not in TrainingConfig.from_yaml().grid:
            raise ReplayError(f"{ticker} selected candidate is outside the locked Stage 04 grid")
        ticker_train = train_metadata.loc[
            (train_metadata["split"] == "train") & (train_metadata["ticker"].astype(str) == ticker)
        ]
        if ticker_train.empty:
            raise ReplayError(f"{ticker} has no fixed-purge-clean Train rows in the prepared dataset")
        row_indices = ticker_train.index.to_list()
        expected_mean = float(train_y.loc[row_indices].astype(float).mean())
        if not math.isclose(float(baselines[ticker]["b0_train_mean"]), expected_mean, rel_tol=0, abs_tol=1e-14):
            raise ReplayError(f"{ticker} B0 Train mean does not match the prepared Train labels")
        train_ends = [_as_date(value, "Train target end") for value in ticker_train["target_end_date"]]
        last_train_target_end[ticker] = max(train_ends)
        seed_keys.update(
            (_as_date(row.date, "Train anchor"), str(row.ticker))
            for row in ticker_train.itertuples(index=False)
        )
    return bundle, manifest, tickers, last_train_target_end, seed_keys


def _target_window(anchor: date, calendar_index: Mapping[date, int], sessions: list[date]) -> tuple[date, date]:
    position = calendar_index.get(anchor)
    if position is None or position + 5 >= len(sessions):
        raise ReplayError(f"could not resolve XNYS target window for {anchor}")
    return sessions[position + 1], sessions[position + 5]


def _stable_id(value: Any) -> str:
    return sha256_bytes(canonical_json(value).encode("utf-8"))


def _valid_forecast(value: Any) -> bool:
    try:
        return bool(math.isfinite(float(value)) and float(value) >= 0)
    except (TypeError, ValueError, OverflowError):
        return False


def _feature_frame(values: np.ndarray) -> pd.DataFrame:
    return pd.DataFrame([np.asarray(values, dtype=float)], columns=list(CORE_FEATURE_COLUMNS))


def _new_runtime_state(
    initial_tickers: Mapping[str, Any],
    initial_last_train_end: Mapping[str, date],
    seed_keys: set[tuple[date, str]],
    adwin_delta: float,
) -> _RuntimeState:
    return _RuntimeState(
        b3_models={ticker: deepcopy(initial_tickers[ticker]["b3"]) for ticker in SUPPORTED_TICKERS},
        scalers={ticker: deepcopy(initial_tickers[ticker]["scaler"]) for ticker in SUPPORTED_TICKERS},
        adwin_detectors={ticker: ADWIN(delta=adwin_delta) for ticker in SUPPORTED_TICKERS},
        updated_label_keys=set(seed_keys),
        processed_error_ids=set(),
        evaluated_prediction_ids=set(),
        pending_predictions=[],
        last_b3_target_end_by_ticker=dict(initial_last_train_end),
    )


def _serialize_runtime_state(
    runtime: _RuntimeState,
    *,
    experiment_id: str,
    compatibility_fingerprint: str,
    run_id: str,
    last_committed_session: date,
    initial_hash_by_ticker: Mapping[str, str],
) -> dict[str, Any]:
    b3_hashes = {
        ticker: model_state_sha256(runtime.b3_models[ticker], runtime.scalers[ticker])
        for ticker in SUPPORTED_TICKERS
    }
    adwin_hashes = {
        ticker: _adwin_state_sha256(runtime.adwin_detectors[ticker])
        for ticker in SUPPORTED_TICKERS
    }
    state = {
        "checkpoint_version": "1.0.0",
        "experiment_id": experiment_id,
        "compatibility_fingerprint": compatibility_fingerprint,
        "run_id": run_id,
        "last_committed_session": last_committed_session.isoformat(),
        "b3_models": runtime.b3_models,
        "scalers": runtime.scalers,
        "adwin_detectors": runtime.adwin_detectors,
        "updated_label_keys": sorted(
            [(anchor.isoformat(), ticker) for anchor, ticker in runtime.updated_label_keys]
        ),
        "processed_error_ids": sorted(runtime.processed_error_ids),
        "evaluated_prediction_ids": sorted(runtime.evaluated_prediction_ids),
        "pending_predictions": runtime.pending_predictions,
        "last_b3_target_end_by_ticker": {
            ticker: value.isoformat() for ticker, value in runtime.last_b3_target_end_by_ticker.items()
        },
        "initial_b2_state_sha256_by_ticker": dict(initial_hash_by_ticker),
        "b3_state_sha256_by_ticker": b3_hashes,
        "adwin_state_sha256_by_ticker": adwin_hashes,
    }
    return state


def _restore_runtime_state(
    saved: Mapping[str, Any],
    *,
    experiment_id: str,
    compatibility_fingerprint: str,
) -> _RuntimeState:
    if saved.get("checkpoint_version") != "1.0.0":
        raise ReplayError("unsupported Stage 05 checkpoint version")
    if saved.get("compatibility_fingerprint") != compatibility_fingerprint:
        raise ReplayError("checkpoint config, data, code, model, or environment is incompatible")
    runtime = _RuntimeState(
        b3_models=dict(saved["b3_models"]),
        scalers=dict(saved["scalers"]),
        adwin_detectors=dict(saved["adwin_detectors"]),
        updated_label_keys={(_as_date(anchor, "updated label anchor"), str(ticker)) for anchor, ticker in saved["updated_label_keys"]},
        processed_error_ids=set(saved["processed_error_ids"]),
        evaluated_prediction_ids=set(saved["evaluated_prediction_ids"]),
        pending_predictions=list(saved["pending_predictions"]),
        last_b3_target_end_by_ticker={
            ticker: _as_date(value, "last B3 target end")
            for ticker, value in saved["last_b3_target_end_by_ticker"].items()
        },
        last_committed_session=_as_date(saved["last_committed_session"], "last committed session"),
    )
    for ticker in SUPPORTED_TICKERS:
        actual_model_hash = model_state_sha256(runtime.b3_models[ticker], runtime.scalers[ticker])
        if actual_model_hash != saved["b3_state_sha256_by_ticker"].get(ticker):
            raise ReplayError(f"{ticker} B3 checkpoint model/scaler hash is invalid")
        actual_adwin_hash = _adwin_state_sha256(runtime.adwin_detectors[ticker])
        if actual_adwin_hash != saved["adwin_state_sha256_by_ticker"].get(ticker):
            raise ReplayError(f"{ticker} ADWIN checkpoint hash is invalid")
    return runtime


def _adwin_state_sha256(detector: ADWIN) -> str:
    """Hash the detector parameters and River 0.22 bucket state deterministically."""
    helper = detector._helper
    bucket_deque = helper.bucket_deque
    bucket_hashes = [
        sha256_bytes(pickle.dumps(bucket, protocol=5))
        for bucket in bucket_deque
    ]
    state = {
        "delta": detector.delta,
        "clock": detector.clock,
        "max_buckets": detector.max_buckets,
        "min_window_length": detector.min_window_length,
        "grace_period": detector.grace_period,
        "drift_detected": detector.drift_detected,
        "width": detector.width,
        "estimation": detector.estimation,
        "variance": detector.variance,
        "total": detector.total,
        "n_detections": detector.n_detections,
        "bucket_deque_maxlen": bucket_deque.maxlen,
        "bucket_hashes_in_order": bucket_hashes,
    }
    return sha256_bytes(canonical_json(state).encode("utf-8"))


def _state_summary(state: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "last_committed_session": state["last_committed_session"],
        "b3_state_sha256_by_ticker": state["b3_state_sha256_by_ticker"],
        "adwin_state_sha256_by_ticker": state["adwin_state_sha256_by_ticker"],
        "updated_label_count": len(state["updated_label_keys"]),
        "processed_error_count": len(state["processed_error_ids"]),
        "evaluated_prediction_count": len(state["evaluated_prediction_ids"]),
        "pending_prediction_count": len(state["pending_predictions"]),
    }


def _records_frame(rows: Iterable[Mapping[str, Any]], columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(list(rows), columns=columns)


def _split_for_date(value: date) -> str:
    return DatasetConfig().split_for_date(value)


def _read_daily_tables(committed_dirs: Iterable[Path], filename: str, columns: list[str]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for directory in committed_dirs:
        path = directory / filename
        frame = pd.read_csv(path)
        if not frame.empty:
            frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=columns)
    result = pd.concat(frames, ignore_index=True).reindex(columns=columns)
    return result


def _date_columns(frame: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    result = frame.copy()
    for column in columns:
        if column not in result or result[column].isna().all():
            continue
        result[column] = pd.to_datetime(result[column], errors="coerce").dt.date
    return result


def _utc_columns(frame: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    result = frame.copy()
    for column in columns:
        if column in result:
            result[column] = pd.to_datetime(result[column], utc=True, errors="coerce")
    return result


def _manifest_output_path(experiment_dir: Path) -> Path:
    return experiment_dir / "experiment_manifest.json"


def _load_existing_commits(
    checkpoint_root: Path,
    *,
    experiment_id: str,
    sessions: list[date],
) -> tuple[list[Path], dict[str, Any] | None]:
    committed_root = checkpoint_root / "committed"
    if not committed_root.exists():
        return [], None
    directories: list[Path] = []
    for child in committed_root.iterdir():
        if not child.is_dir():
            continue
        try:
            _as_date(child.name, "checkpoint folder date")
        except ReplayError:
            continue
        directories.append(child)
    directories.sort(key=lambda item: item.name)
    commit_dates = [_as_date(directory.name, "checkpoint folder date") for directory in directories]
    if commit_dates != sessions[: len(commit_dates)]:
        raise ReplayError("committed session sequence has a gap or an out-of-range checkpoint")
    latest_manifest: dict[str, Any] | None = None
    for directory in directories:
        latest_manifest, _ = _verify_commit(directory, experiment_id)
    return directories, latest_manifest


def _verify_commit(path: Path, experiment_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    from src.ml_replay.storage import verify_committed_session

    return verify_committed_session(path, expected_experiment_id=experiment_id)


def _is_true(value: Any) -> bool:
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    return bool(value)


def _eligible_label(
    key: tuple[date, str],
    *,
    replay_date: date,
    label_map: Mapping[tuple[date, str], Mapping[str, Any]],
    audit_map: Mapping[tuple[date, str], Mapping[str, Any]],
) -> tuple[Mapping[str, Any], float] | None:
    label = label_map.get(key)
    audit = audit_map.get(key)
    if label is None or audit is None:
        return None
    target_end = _as_date(label.get("target_end_date"), "label target_end_date")
    # Do not inspect the realized target until its market-time availability date.
    if target_end > replay_date:
        return None
    try:
        observation_count = int(label.get("target_obs_count"))
        target_value = float(label.get("target_realized_vol_5d"))
    except (TypeError, ValueError, OverflowError):
        return None
    if (
        not _is_true(label.get("is_label_mature"))
        or observation_count != 5
        or not math.isfinite(target_value)
        or target_value < 0
        or not _is_true(audit.get("feature_quality_passed"))
        or not _is_true(audit.get("label_quality_passed"))
        or not _is_true(audit.get("prediction_eligible"))
    ):
        return None
    return label, target_value


def _invoke_failure_hook(
    failure_injector: Callable[[str, date], None] | None,
    point: str,
    session_date: date,
) -> None:
    if failure_injector is not None:
        failure_injector(point, session_date)


def _atomic_csv(path: Path, frame: pd.DataFrame, columns: list[str]) -> None:
    import os

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        content = frame.reindex(columns=columns).to_csv(
            index=False, float_format="%.17g", lineterminator="\n"
        )
        with temporary.open("w", encoding="utf-8", newline="") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _enrich_coverage(
    coverage: pd.DataFrame,
    predictions: pd.DataFrame,
    evaluations: pd.DataFrame,
    *,
    availability_cutoff: date,
) -> pd.DataFrame:
    result = coverage.reindex(columns=DAILY_COVERAGE_COLUMNS).copy()
    result["mature_evaluable_count"] = 0
    result["pending_label_count"] = 0
    result["evaluation_failure_count"] = 0
    prediction_lookup: dict[tuple[date, str, str], dict[str, Any]] = {}
    for row in predictions.to_dict("records"):
        key = (
            _as_date(row["prediction_date"], "coverage prediction date"),
            str(row["ticker"]),
            str(row["model_name"]),
        )
        prediction_lookup[key] = row
    evaluated_ids = set(evaluations.get("prediction_id", pd.Series(dtype=str)).astype(str))
    for index, row in result.iterrows():
        if int(row["published_count"]) == 0:
            continue
        key = (
            _as_date(row["prediction_date"], "coverage prediction date"),
            str(row["ticker"]),
            str(row["model_name"]),
        )
        forecast = prediction_lookup.get(key)
        if forecast is None:
            result.at[index, "evaluation_failure_count"] = 1
        elif str(forecast["prediction_id"]) in evaluated_ids:
            result.at[index, "mature_evaluable_count"] = 1
        elif _as_date(forecast["target_end_date"], "coverage target end") > availability_cutoff:
            result.at[index, "pending_label_count"] = 1
        else:
            result.at[index, "evaluation_failure_count"] = 1
    if not result.empty:
        for column in (
            "mature_evaluable_count",
            "pending_label_count",
            "evaluation_failure_count",
        ):
            result[column] = result[column].astype("int64")
    return result.reindex(columns=COVERAGE_COLUMNS)


def _build_outputs(
    experiment_dir: Path,
    committed_dirs: list[Path],
    *,
    availability_cutoff: date,
) -> dict[str, pd.DataFrame]:
    outputs = {
        "asset_volatility_predictions.csv": _read_daily_tables(
            committed_dirs, "predictions.csv", PREDICTION_COLUMNS
        ),
        "evaluation.csv": _read_daily_tables(committed_dirs, "evaluations.csv", EVALUATION_COLUMNS),
        "drift_errors.csv": _read_daily_tables(committed_dirs, "drift_errors.csv", DRIFT_ERROR_COLUMNS),
        "drift_alerts.csv": _read_daily_tables(committed_dirs, "drift_alerts.csv", DRIFT_ALERT_COLUMNS),
        "updates.csv": _read_daily_tables(committed_dirs, "updates.csv", UPDATE_COLUMNS),
        "forecast_failures.csv": _read_daily_tables(committed_dirs, "forecast_failures.csv", FAILURE_COLUMNS),
        "coverage.csv": _read_daily_tables(committed_dirs, "coverage.csv", DAILY_COVERAGE_COLUMNS),
    }
    for name, frame in outputs.items():
        if name == "asset_volatility_predictions.csv":
            outputs[name] = _date_columns(
                frame,
                ("prediction_date", "target_start_date", "target_end_date", "last_training_target_end_date"),
            )
            outputs[name] = _utc_columns(outputs[name], ("prediction_created_at_utc",))
        elif name == "evaluation.csv":
            outputs[name] = _date_columns(
                frame,
                ("prediction_date", "target_start_date", "target_end_date", "evaluation_date", "label_available_replay_date"),
            )
        elif name in ("drift_errors.csv", "drift_alerts.csv"):
            outputs[name] = _date_columns(frame, ("prediction_date", "evaluation_date"))
        elif name == "updates.csv":
            outputs[name] = _date_columns(frame, ("update_date", "anchor_date", "target_end_date"))
        elif name in ("forecast_failures.csv", "coverage.csv"):
            outputs[name] = _date_columns(frame, ("prediction_date",))

    outputs["coverage.csv"] = _enrich_coverage(
        outputs["coverage.csv"],
        outputs["asset_volatility_predictions.csv"],
        outputs["evaluation.csv"],
        availability_cutoff=availability_cutoff,
    )
    predictions = outputs["asset_volatility_predictions.csv"]
    if not predictions.empty:
        predictions = predictions.sort_values(
            ["prediction_date", "ticker", "model_name"], kind="stable"
        ).reset_index(drop=True)
        outputs["asset_volatility_predictions.csv"] = predictions
    for filename, frame in outputs.items():
        _atomic_csv(experiment_dir / "outputs" / filename, frame, list(frame.columns))
    return outputs


def _result_from_outputs(
    *,
    experiment_id: str,
    run_id: str,
    experiment_dir: Path,
    outputs: Mapping[str, pd.DataFrame],
    committed_dates: tuple[date, ...],
    manifest: dict[str, Any],
    final_state: Mapping[str, Any] | None,
    final_b2_hashes: Mapping[str, str],
    completed: bool,
) -> ReplayResult:
    predictions = outputs["asset_volatility_predictions.csv"]
    if not predictions.empty:
        predictions = predictions.reindex(columns=PREDICTION_COLUMNS)
    b3_hashes = dict(final_state.get("b3_state_sha256_by_ticker", {})) if final_state else {}
    adwin_hashes = dict(final_state.get("adwin_state_sha256_by_ticker", {})) if final_state else {}
    return ReplayResult(
        experiment_id=experiment_id,
        run_id=run_id,
        artifact_dir=experiment_dir,
        predictions=predictions,
        evaluations=outputs["evaluation.csv"],
        drift_errors=outputs["drift_errors.csv"],
        drift_alerts=outputs["drift_alerts.csv"],
        updated_labels=outputs["updates.csv"],
        forecast_failures=outputs["forecast_failures.csv"],
        coverage=outputs["coverage.csv"],
        committed_sessions=committed_dates,
        experiment_manifest=manifest,
        final_b3_state_sha256_by_ticker=b3_hashes,
        final_b2_state_sha256_by_ticker=dict(final_b2_hashes),
        final_adwin_state_sha256_by_ticker=adwin_hashes,
        completed=completed,
    )


def run_final_replay(
    prepared: PreparedDataset,
    labels: pd.DataFrame,
    *,
    initial_model_artifact_dir: str | Path,
    output_root: str | Path,
    config: ReplayConfig | None = None,
    replay_end_date: date | str | None = None,
    resume: bool = False,
    stop_after_session: date | str | None = None,
    failure_injector: Callable[[str, date], None] | None = None,
) -> ReplayResult:
    """Replay every XNYS session from Validation start through the requested end date.

    ``stop_after_session`` and ``failure_injector`` support bounded acceptance and
    recovery tests. Use the strict data cutoff as the end date for Final Replay.
    """
    _validate_model_names()
    replay_config = config or ReplayConfig.from_yaml()
    effective_end = replay_config.data_cutoff if replay_end_date is None else _as_date(
        replay_end_date, "replay_end_date"
    )
    if not replay_config.replay_start_date <= effective_end <= replay_config.data_cutoff:
        raise ReplayError("replay_end_date must fall between Validation start and the strict cutoff")
    if labels.empty:
        raise ReplayError("Final Replay requires the Stage 03 label table, including pending labels")
    feature_map, feature_metadata, audit_map, label_map = _input_maps(prepared, labels)
    bundle, training_manifest, initial_tickers, initial_train_ends, seed_keys = _load_initial_artifact(
        initial_model_artifact_dir, prepared
    )
    initial_hash_by_ticker = {
        ticker: str(initial_tickers[ticker]["state_sha256"]) for ticker in SUPPORTED_TICKERS
    }
    input_snapshot_id = _input_snapshot_id(prepared, labels)
    versions = _package_versions()
    code_sha = _code_sha256()
    git_sha = _git_commit_sha()
    contract_identity = _contract_identity(prepared, labels)
    training_manifest_path = Path(initial_model_artifact_dir).expanduser().resolve() / "training_manifest.json"
    stage4_artifact_identity = {
        "training_manifest_sha256": sha256_file(training_manifest_path),
        "initial_models_sha256": training_manifest["artifact_sha256"]["initial_models.joblib"],
        "selected_configs": training_manifest.get("selected_configs", []),
        "initial_state_sha256_by_ticker": initial_hash_by_ticker,
    }
    semantic_identity = {
        "phase": "FINAL_REPLAY",
        "replay_config": replay_config.as_dict(),
        "effective_replay_end_date": effective_end.isoformat(),
        "input_snapshot_id": input_snapshot_id,
        "source_lineage": prepared.report.lineage,
        "source_point_in_time_availability_verified": False,
        "stage04_artifact": stage4_artifact_identity,
        "code_sha256": code_sha,
        "git_commit_sha": git_sha,
        "contract_identity": contract_identity,
        "versions": versions,
    }
    compatibility_fingerprint = sha256_bytes(canonical_json(semantic_identity).encode("utf-8"))
    experiment_id = compatibility_fingerprint
    run_id = str(uuid.uuid4())
    base = Path(output_root).expanduser().resolve()
    experiment_dir = base / "experiments" / experiment_id
    checkpoint_root = experiment_dir / "checkpoints"
    manifest_path = _manifest_output_path(experiment_dir)

    calendar_end = effective_end + pd.Timedelta(days=20)
    calendar_start = min(
        replay_config.replay_start_date,
        min(feature_map) [0] if feature_map else replay_config.replay_start_date,
    )
    schedule = market_calendars.get_calendar(replay_config.market).schedule(
        start_date=calendar_start.isoformat(), end_date=calendar_end.isoformat()
    )
    calendar_sessions = [stamp.date() for stamp in schedule.index]
    calendar_index = {session: index for index, session in enumerate(calendar_sessions)}
    sessions = [
        session
        for session in calendar_sessions
        if replay_config.replay_start_date <= session <= effective_end
    ]
    if not sessions or sessions[0] != replay_config.replay_start_date or sessions[-1] != effective_end:
        raise ReplayError("replay start and end must be XNYS trading sessions")
    stop_date = None if stop_after_session is None else _as_date(stop_after_session, "stop_after_session")
    if stop_date is not None and stop_date not in sessions:
        raise ReplayError("stop_after_session must be one of the replay XNYS sessions")

    if resume and not experiment_dir.exists():
        raise ReplayError(
            "resume requested, but no experiment with the same data/config/code identity exists"
        )
    if experiment_dir.exists():
        if not resume:
            raise FileExistsError(
                f"experiment already exists; use resume=True to continue: {experiment_dir}"
            )
        experiment_manifest = read_json(manifest_path, "experiment manifest")
        if experiment_manifest.get("experiment_id") != experiment_id or experiment_manifest.get(
            "compatibility_fingerprint"
        ) != compatibility_fingerprint:
            raise ReplayError("existing experiment is incompatible with this replay request")
    else:
        experiment_dir.mkdir(parents=True, exist_ok=False)
        (checkpoint_root / "committed").mkdir(parents=True, exist_ok=True)
        (checkpoint_root / "staging").mkdir(parents=True, exist_ok=True)
        experiment_manifest = {
            "schema_version": "1.0.0",
            "stage": "05_daily_replay_adwin_checkpoints",
            "phase": "FINAL_REPLAY",
            "experiment_id": experiment_id,
            "compatibility_fingerprint": compatibility_fingerprint,
            "replay_config": replay_config.as_dict(),
            "replay_window": {
                "start_date": replay_config.replay_start_date.isoformat(),
                "requested_end_date": effective_end.isoformat(),
                "strict_data_cutoff": replay_config.data_cutoff.isoformat(),
                "covers_strict_cutoff": effective_end == replay_config.data_cutoff,
                "validation": ["2024-10-01", "2025-09-30"],
                "test": ["2025-10-01", "2026-09-25"],
            },
            "input_snapshot_id": input_snapshot_id,
            "source_lineage": prepared.report.lineage,
            "source_quality_passed": prepared.report.summary.get("source_quality_passed"),
            "point_in_time_source_availability_verified": False,
            "limitations": list(prepared.report.limitations),
            "stage04_training_manifest_sha256": stage4_artifact_identity[
                "training_manifest_sha256"
            ],
            "stage04_artifact_sha256": training_manifest.get("artifact_sha256", {}),
            "selected_configs": training_manifest.get("selected_configs", []),
            "initial_state_sha256_by_ticker": initial_hash_by_ticker,
            "code_sha256": code_sha,
            "git_commit_sha": git_sha,
            "contract_identity": contract_identity,
            "versions": versions,
            "experiment_identity": semantic_identity,
            "created_at_utc": _utc_now(),
            "updated_at_utc": _utc_now(),
            "status": "CREATED",
            "last_fully_committed_session": None,
            "executions": [],
            "final_outputs_sha256": {},
        }

    committed_dirs, _ = _load_existing_commits(
        checkpoint_root,
        experiment_id=experiment_id,
        sessions=sessions,
    )
    if not resume and committed_dirs:
        raise FileExistsError("refusing to start over an experiment with existing committed sessions")
    initial_runtime = _new_runtime_state(
        initial_tickers,
        initial_train_ends,
        seed_keys,
        replay_config.adwin_delta,
    )
    if committed_dirs:
        saved_state, _ = load_checkpoint(
            committed_dirs[-1], expected_experiment_id=experiment_id
        )
        runtime = _restore_runtime_state(
            saved_state,
            experiment_id=experiment_id,
            compatibility_fingerprint=compatibility_fingerprint,
        )
    else:
        runtime = initial_runtime

    execution = {"run_id": run_id, "started_at_utc": _utc_now(), "status": "RUNNING"}
    experiment_manifest.setdefault("executions", []).append(execution)
    experiment_manifest["current_run_id"] = run_id
    experiment_manifest["status"] = "RUNNING"
    experiment_manifest["updated_at_utc"] = _utc_now()
    write_json_atomic(manifest_path, experiment_manifest)

    baseline_versions = {
        ticker: {
            model_id: _stable_id(
                {
                    "model_id": model_id,
                    "model_name": MODEL_NAMES[model_id],
                    "ticker": ticker,
                    "baseline": bundle["baselines"][ticker].get(
                        "b0_train_mean" if model_id == "B0" else "b1_feature"
                    ),
                    "version": replay_config.replay_config_version,
                }
            )
            for model_id in ("B0", "B1")
        }
        for ticker in SUPPORTED_TICKERS
    }
    b2_version = dict(initial_hash_by_ticker)
    already_committed = len(committed_dirs)
    all_committed_dates = [
        _as_date(directory.name, "committed session") for directory in committed_dirs
    ]
    latest_state: dict[str, Any] | None = None
    if committed_dirs:
        latest_state, _ = load_checkpoint(committed_dirs[-1], expected_experiment_id=experiment_id)

    try:
        for session_date in sessions[already_committed:]:
            stage_dir = begin_session(checkpoint_root, session_date)
            session_predictions: list[dict[str, Any]] = []
            session_failures: list[dict[str, Any]] = []
            session_coverage: list[dict[str, Any]] = []
            session_evaluations: list[dict[str, Any]] = []
            session_drift_errors: list[dict[str, Any]] = []
            session_drift_alerts: list[dict[str, Any]] = []
            session_updates: list[dict[str, Any]] = []

            # 1. Predict all eligible models from pre-update state.
            for ticker in SUPPORTED_TICKERS:
                key = (session_date, ticker)
                values = feature_map.get(key)
                metadata = feature_metadata.get(key)
                audit = audit_map.get(key, {})
                if values is None or metadata is None:
                    raw_reasons = audit.get("exclusion_reasons", ())
                    reason = ",".join(str(item) for item in raw_reasons) or "feature_row_missing_or_ineligible"
                    for model_id in MODEL_ORDER:
                        session_failures.append(
                            {
                                "experiment_id": experiment_id,
                                "prediction_date": session_date,
                                "split": _split_for_date(session_date),
                                "ticker": ticker,
                                "model_name": MODEL_NAMES[model_id],
                                "failure_type": "feature_unavailable",
                                "reason": reason,
                                "run_id": run_id,
                            }
                        )
                        session_coverage.append(
                            {
                                "experiment_id": experiment_id,
                                "prediction_date": session_date,
                                "split": _split_for_date(session_date),
                                "ticker": ticker,
                                "model_name": MODEL_NAMES[model_id],
                                "expected_count": 1,
                                "published_count": 0,
                                "invalid_count": 0,
                                "missing_feature_count": 1,
                                "run_id": run_id,
                            }
                        )
                    continue

                target_start, target_end = _target_window(session_date, calendar_index, calendar_sessions)
                b3_state_version = model_state_sha256(runtime.b3_models[ticker], runtime.scalers[ticker])
                scaled = runtime.scalers[ticker].transform(_feature_frame(values))
                for model_id in MODEL_ORDER:
                    published = 0
                    invalid = 0
                    try:
                        if model_id == "B0":
                            value = bundle["baselines"][ticker]["b0_train_mean"]
                            model_version = baseline_versions[ticker][model_id]
                            training_end = initial_train_ends[ticker]
                        elif model_id == "B1":
                            value = values[tuple(CORE_FEATURE_COLUMNS).index("rv_20d")]
                            model_version = baseline_versions[ticker][model_id]
                            training_end = None
                        elif model_id == "B2":
                            value = initial_tickers[ticker]["b2"].predict(
                                initial_tickers[ticker]["scaler"].transform(_feature_frame(values))
                            )[0]
                            model_version = b2_version[ticker]
                            training_end = initial_train_ends[ticker]
                        else:
                            value = runtime.b3_models[ticker].predict(scaled)[0]
                            model_version = b3_state_version
                            training_end = runtime.last_b3_target_end_by_ticker[ticker]
                    except Exception as error:
                        invalid = 1
                        session_failures.append(
                            {
                                "experiment_id": experiment_id,
                                "prediction_date": session_date,
                                "ticker": ticker,
                                "model_name": MODEL_NAMES[model_id],
                                "failure_type": "prediction_error",
                                "reason": f"{type(error).__name__}: {error}",
                                "run_id": run_id,
                            }
                        )
                    else:
                        if not _valid_forecast(value):
                            invalid = 1
                            session_failures.append(
                                {
                                    "experiment_id": experiment_id,
                                    "prediction_date": session_date,
                                    "ticker": ticker,
                                    "model_name": MODEL_NAMES[model_id],
                                    "failure_type": "invalid_forecast",
                                    "reason": "forecast must be finite and nonnegative; value was rejected without clipping",
                                    "run_id": run_id,
                                }
                            )
                        else:
                            feature_version = str(metadata["feature_set_version"])
                            logical_key = {
                                "prediction_date": session_date.isoformat(),
                                "ticker": ticker,
                                "model_name": MODEL_NAMES[model_id],
                                "prediction_mode": replay_config.prediction_mode,
                                "model_version": str(model_version),
                                "feature_set_version": feature_version,
                                "input_snapshot_id": input_snapshot_id,
                            }
                            row = {
                                "prediction_id": _stable_id(logical_key),
                                "prediction_date": session_date,
                                "ticker": ticker,
                                "model_name": MODEL_NAMES[model_id],
                                "model_version": str(model_version),
                                "prediction_mode": replay_config.prediction_mode,
                                "forecast_horizon_trading_days": replay_config.forecast_horizon_trading_days,
                                "target_start_date": target_start,
                                "target_end_date": target_end,
                                "predicted_vol_annualized": float(value),
                                "feature_set_version": feature_version,
                                "feature_run_id": str(metadata["feature_run_id"]),
                                "input_snapshot_id": input_snapshot_id,
                                "last_training_target_end_date": training_end,
                                "run_id": run_id,
                                "prediction_created_at_utc": _utc_now(),
                            }
                            session_predictions.append(row)
                            published = 1
                    session_coverage.append(
                        {
                            "experiment_id": experiment_id,
                            "prediction_date": session_date,
                            "ticker": ticker,
                            "model_name": MODEL_NAMES[model_id],
                            "expected_count": 1,
                            "published_count": published,
                            "invalid_count": invalid,
                            "missing_feature_count": 0,
                            "run_id": run_id,
                        }
                    )

            _invoke_failure_hook(failure_injector, "after_predict", session_date)
            prediction_frame = _records_frame(session_predictions, PREDICTION_COLUMNS)
            stage_table(stage_dir, "predictions.csv", prediction_frame, PREDICTION_COLUMNS)
            _invoke_failure_hook(failure_injector, "after_forecast_staged", session_date)
            pending_ids = {row["prediction_id"] for row in runtime.pending_predictions}
            if any(row["prediction_id"] in pending_ids for row in session_predictions):
                raise ReplayError(f"duplicate logical predictions reached session {session_date}")
            runtime.pending_predictions.extend(session_predictions)

            # 2. Evaluate only forecasts whose label is available by this simulated date.
            remaining_pending: list[dict[str, Any]] = []
            for forecast in sorted(
                runtime.pending_predictions,
                key=lambda item: (item["prediction_date"], item["ticker"], item["model_name"]),
            ):
                prediction_id = str(forecast["prediction_id"])
                anchor = _as_date(forecast["prediction_date"], "forecast prediction_date")
                target_end = _as_date(forecast["target_end_date"], "forecast target_end_date")
                key = (anchor, str(forecast["ticker"]))
                if prediction_id in runtime.evaluated_prediction_ids:
                    continue
                if target_end > session_date:
                    remaining_pending.append(forecast)
                    continue
                label = label_map.get(key)
                audit = audit_map.get(key, {})
                reason: str | None = None
                target_value: float | None = None
                if label is None:
                    reason = "label_missing_when_target_window_matured"
                else:
                    label_target_end = _as_date(label.get("target_end_date"), "label target_end_date")
                    if label_target_end > session_date:
                        remaining_pending.append(forecast)
                        continue
                    label_start = _as_date(label.get("target_start_date"), "label target_start_date")
                    if label_start != _as_date(forecast["target_start_date"], "forecast target_start_date") or label_target_end != target_end:
                        reason = "label_target_window_mismatch"
                    else:
                        try:
                            observation_count = int(label.get("target_obs_count", 0))
                        except (TypeError, ValueError, OverflowError):
                            observation_count = 0
                        if not _is_true(label.get("is_label_mature")) or observation_count != 5:
                            reason = "label_not_mature_or_observation_count_not_five"
                    if reason is None and not _is_true(audit.get("label_quality_passed")):
                        reason = "label_quality_failed"
                    if reason is None:
                        try:
                            candidate_value = float(label.get("target_realized_vol_5d"))
                        except (TypeError, ValueError, OverflowError):
                            candidate_value = math.nan
                        if not math.isfinite(candidate_value) or candidate_value < 0:
                            reason = "label_value_invalid"
                        else:
                            target_value = candidate_value
                if reason is not None:
                    session_failures.append(
                        {
                            "experiment_id": experiment_id,
                            "prediction_date": anchor,
                            "ticker": forecast["ticker"],
                            "model_name": forecast["model_name"],
                            "failure_type": "evaluation_label_unavailable",
                            "reason": reason,
                            "run_id": run_id,
                        }
                    )
                    runtime.evaluated_prediction_ids.add(prediction_id)
                    continue

                assert target_value is not None
                prediction_value = float(forecast["predicted_vol_annualized"])
                absolute_error = abs(prediction_value - target_value)
                evaluation = {
                    "experiment_id": experiment_id,
                    "prediction_id": prediction_id,
                    "prediction_date": anchor,
                    "split": _split_for_date(anchor),
                    "ticker": forecast["ticker"],
                    "model_name": forecast["model_name"],
                    "model_version": forecast["model_version"],
                    "prediction_mode": forecast["prediction_mode"],
                    "forecast_horizon_trading_days": forecast["forecast_horizon_trading_days"],
                    "target_start_date": forecast["target_start_date"],
                    "target_end_date": target_end,
                    "predicted_vol_annualized": prediction_value,
                    "target_realized_vol_5d": target_value,
                    "target_version": str(label.get("target_version", "")),
                    "feature_set_version": forecast["feature_set_version"],
                    "input_snapshot_id": forecast["input_snapshot_id"],
                    "absolute_error": absolute_error,
                    "squared_error": absolute_error**2,
                    "evaluation_date": session_date,
                    "label_available_replay_date": session_date,
                    "prediction_run_id": forecast["run_id"],
                    "evaluation_run_id": run_id,
                }
                session_evaluations.append(evaluation)
                runtime.evaluated_prediction_ids.add(prediction_id)

                if forecast["model_name"] == MODEL_NAMES["B3"]:
                    if prediction_id in runtime.processed_error_ids:
                        raise ReplayError(f"ADWIN error was already processed: {prediction_id}")
                    detector = runtime.adwin_detectors[str(forecast["ticker"])]
                    detector.update(absolute_error)
                    drift_row = {
                        "experiment_id": experiment_id,
                        "prediction_id": prediction_id,
                        "prediction_date": anchor,
                        "evaluation_date": session_date,
                        "ticker": forecast["ticker"],
                        "absolute_error": absolute_error,
                        "adwin_delta": replay_config.adwin_delta,
                        "adwin_width": int(detector.width),
                        "adwin_estimation": float(detector.estimation),
                        "drift_detected": bool(detector.drift_detected),
                        "prediction_run_id": forecast["run_id"],
                        "evaluation_run_id": run_id,
                    }
                    session_drift_errors.append(drift_row)
                    if drift_row["drift_detected"]:
                        session_drift_alerts.append(dict(drift_row))
                    runtime.processed_error_ids.add(prediction_id)
            runtime.pending_predictions = remaining_pending
            _invoke_failure_hook(failure_injector, "after_adwin", session_date)

            # 3. Update B3 once per ETF with the complete deterministic mature batch.
            for ticker in SUPPORTED_TICKERS:
                eligible_rows: list[tuple[date, np.ndarray, float, date]] = []
                for key, values in feature_map.items():
                    anchor, row_ticker = key
                    if row_ticker != ticker or anchor > session_date or key in runtime.updated_label_keys:
                        continue
                    eligible = _eligible_label(
                        key,
                        replay_date=session_date,
                        label_map=label_map,
                        audit_map=audit_map,
                    )
                    if eligible is None:
                        continue
                    label, target_value = eligible
                    target_end = _as_date(label["target_end_date"], "label target_end_date")
                    eligible_rows.append((anchor, values, target_value, target_end))
                eligible_rows.sort(key=lambda item: item[0])
                if not eligible_rows:
                    continue
                model = runtime.b3_models[ticker]
                scaler = runtime.scalers[ticker]
                state_before = model_state_sha256(model, scaler)
                scaled_batch = scaler.transform(
                    pd.DataFrame(
                        np.vstack([item[1] for item in eligible_rows]),
                        columns=list(CORE_FEATURE_COLUMNS),
                    )
                )
                target_batch = np.asarray([item[2] for item in eligible_rows], dtype=float)
                model.partial_fit(scaled_batch, target_batch)
                state_after = model_state_sha256(model, scaler)
                batch_id = _stable_id(
                    {
                        "experiment_id": experiment_id,
                        "update_date": session_date.isoformat(),
                        "ticker": ticker,
                        "anchor_dates": [item[0].isoformat() for item in eligible_rows],
                        "state_before": state_before,
                    }
                )
                for anchor, _, target_value, target_end in eligible_rows:
                    key = (anchor, ticker)
                    runtime.updated_label_keys.add(key)
                    session_updates.append(
                        {
                            "experiment_id": experiment_id,
                            "update_date": session_date,
                            "ticker": ticker,
                            "anchor_date": anchor,
                            "target_end_date": target_end,
                            "target_realized_vol_5d": target_value,
                            "batch_id": batch_id,
                            "batch_size": len(eligible_rows),
                            "b3_state_version_before": state_before,
                            "b3_state_version_after": state_after,
                            "run_id": run_id,
                        }
                    )
                runtime.last_b3_target_end_by_ticker[ticker] = max(
                    runtime.last_b3_target_end_by_ticker[ticker],
                    max(item[3] for item in eligible_rows),
                )
            _invoke_failure_hook(failure_injector, "after_b3_update", session_date)

            # 4. Serialize post-update state and atomically publish this complete session.
            runtime.last_committed_session = session_date
            state = _serialize_runtime_state(
                runtime,
                experiment_id=experiment_id,
                compatibility_fingerprint=compatibility_fingerprint,
                run_id=run_id,
                last_committed_session=session_date,
                initial_hash_by_ticker=initial_hash_by_ticker,
            )
            state_summary = _state_summary(state)
            table_frames = {
                "predictions.csv": (prediction_frame, PREDICTION_COLUMNS),
                "evaluations.csv": (_records_frame(session_evaluations, EVALUATION_COLUMNS), EVALUATION_COLUMNS),
                "drift_errors.csv": (_records_frame(session_drift_errors, DRIFT_ERROR_COLUMNS), DRIFT_ERROR_COLUMNS),
                "drift_alerts.csv": (_records_frame(session_drift_alerts, DRIFT_ALERT_COLUMNS), DRIFT_ALERT_COLUMNS),
                "updates.csv": (_records_frame(session_updates, UPDATE_COLUMNS), UPDATE_COLUMNS),
                "forecast_failures.csv": (_records_frame(session_failures, FAILURE_COLUMNS), FAILURE_COLUMNS),
                "coverage.csv": (_records_frame(session_coverage, DAILY_COVERAGE_COLUMNS), DAILY_COVERAGE_COLUMNS),
            }
            commit_dir = commit_session(
                checkpoint_root,
                session_date=session_date,
                experiment_id=experiment_id,
                run_id=run_id,
                tables=table_frames,
                state=state,
                state_summary=state_summary,
                manifest_fields={
                    "compatibility_fingerprint": compatibility_fingerprint,
                    "input_snapshot_id": input_snapshot_id,
                    "code_sha256": code_sha,
                    "git_commit_sha": git_sha,
                    "contract_identity": contract_identity,
                    "versions": versions,
                    "prediction_count": len(session_predictions),
                    "evaluation_count": len(session_evaluations),
                    "drift_error_count": len(session_drift_errors),
                    "update_count": len(session_updates),
                    "forecast_failure_count": len(session_failures),
                    "coverage_row_count": len(session_coverage),
                },
                stage_dir=stage_dir,
                before_checkpoint=failure_injector,
            )
            all_committed_dates.append(session_date)
            committed_dirs.append(commit_dir)
            latest_state = state
            experiment_manifest["last_fully_committed_session"] = session_date.isoformat()
            experiment_manifest["updated_at_utc"] = _utc_now()
            experiment_manifest["status"] = "RUNNING"
            write_json_atomic(manifest_path, experiment_manifest)
            if stop_date == session_date and session_date != effective_end:
                break

        completed = bool(all_committed_dates and all_committed_dates[-1] == effective_end)
        final_b2_hashes = {
            ticker: model_state_sha256(
                initial_tickers[ticker]["b2"], initial_tickers[ticker]["scaler"]
            )
            for ticker in SUPPORTED_TICKERS
        }
        if final_b2_hashes != initial_hash_by_ticker:
            raise ReplayError("B2 Static SGD or its frozen scaler changed during Final Replay")
        experiment_manifest["b2_frozen_state_verified"] = True
        if completed:
            outputs = _build_outputs(
                experiment_dir,
                committed_dirs,
                availability_cutoff=effective_end,
            )
            experiment_manifest["final_outputs_sha256"] = {
                filename: sha256_file(experiment_dir / "outputs" / filename)
                for filename in outputs
            }
        else:
            outputs = {
                "asset_volatility_predictions.csv": _read_daily_tables(
                    committed_dirs, "predictions.csv", PREDICTION_COLUMNS
                ),
                "evaluation.csv": _read_daily_tables(committed_dirs, "evaluations.csv", EVALUATION_COLUMNS),
                "drift_errors.csv": _read_daily_tables(committed_dirs, "drift_errors.csv", DRIFT_ERROR_COLUMNS),
                "drift_alerts.csv": _read_daily_tables(committed_dirs, "drift_alerts.csv", DRIFT_ALERT_COLUMNS),
                "updates.csv": _read_daily_tables(committed_dirs, "updates.csv", UPDATE_COLUMNS),
                "forecast_failures.csv": _read_daily_tables(committed_dirs, "forecast_failures.csv", FAILURE_COLUMNS),
                "coverage.csv": _read_daily_tables(committed_dirs, "coverage.csv", DAILY_COVERAGE_COLUMNS),
            }
            outputs["asset_volatility_predictions.csv"] = _date_columns(
                outputs["asset_volatility_predictions.csv"],
                ("prediction_date", "target_start_date", "target_end_date", "last_training_target_end_date"),
            )
            outputs["asset_volatility_predictions.csv"] = _utc_columns(
                outputs["asset_volatility_predictions.csv"], ("prediction_created_at_utc",)
            )
            outputs["evaluation.csv"] = _date_columns(
                outputs["evaluation.csv"],
                ("prediction_date", "target_start_date", "target_end_date", "evaluation_date", "label_available_replay_date"),
            )
            outputs["drift_errors.csv"] = _date_columns(
                outputs["drift_errors.csv"], ("prediction_date", "evaluation_date")
            )
            outputs["drift_alerts.csv"] = _date_columns(
                outputs["drift_alerts.csv"], ("prediction_date", "evaluation_date")
            )
            outputs["updates.csv"] = _date_columns(
                outputs["updates.csv"], ("update_date", "anchor_date", "target_end_date")
            )
            outputs["forecast_failures.csv"] = _date_columns(
                outputs["forecast_failures.csv"], ("prediction_date",)
            )
            outputs["coverage.csv"] = _date_columns(outputs["coverage.csv"], ("prediction_date",))
            coverage_as_of = all_committed_dates[-1] if all_committed_dates else replay_config.replay_start_date
            outputs["coverage.csv"] = _enrich_coverage(
                outputs["coverage.csv"],
                outputs["asset_volatility_predictions.csv"],
                outputs["evaluation.csv"],
                availability_cutoff=coverage_as_of,
            )
        execution_status = "COMPLETED" if completed else "INTERRUPTED_AT_REQUESTED_SESSION"
        execution.update(
            {
                "status": execution_status,
                "finished_at_utc": _utc_now(),
                "last_fully_committed_session": experiment_manifest.get("last_fully_committed_session"),
            }
        )
        experiment_manifest["status"] = "COMPLETED" if completed else "INTERRUPTED"
        experiment_manifest["updated_at_utc"] = _utc_now()
        write_json_atomic(manifest_path, experiment_manifest)
        committed_dates = tuple(all_committed_dates)
        return _result_from_outputs(
            experiment_id=experiment_id,
            run_id=run_id,
            experiment_dir=experiment_dir,
            outputs=outputs,
            committed_dates=committed_dates,
            manifest=experiment_manifest,
            final_state=latest_state,
            final_b2_hashes=final_b2_hashes,
            completed=completed,
        )
    except Exception as error:
        execution.update(
            {
                "status": "FAILED",
                "finished_at_utc": _utc_now(),
                "failure_type": type(error).__name__,
                "failure_message": str(error),
            }
        )
        experiment_manifest["status"] = "FAILED"
        experiment_manifest["updated_at_utc"] = _utc_now()
        write_json_atomic(manifest_path, experiment_manifest)
        raise
