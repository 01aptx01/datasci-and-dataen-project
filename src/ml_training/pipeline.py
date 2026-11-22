from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import tempfile
import uuid
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Iterable, Mapping

import joblib
import numpy as np
import pandas as pd
import pandas_market_calendars as market_calendars
from sklearn.linear_model import LinearRegression, SGDRegressor
from sklearn.preprocessing import RobustScaler

from src.features.pipeline import CORE_FEATURE_COLUMNS, SUPPORTED_TICKERS

B4_MODEL_ID = "B4"
B4_MODEL_NAME = "HAR_X_OLS"
B4_MODEL_VERSION = "b4_ols_v1.0.0"
BASELINE_MODEL_NAMES = {
    "B0": "CONSTANT_BASELINE",
    "B1": "ROLLING_20D_BASELINE",
    "B2": "STATIC_SGD",
}
from src.ml_dataset.dataset import PreparedDataset
from src.ml_training.config import (
    LEGACY_TRAINING_CONFIG_VERSION,
    TRAINING_CONFIG_VERSION,
    CandidateConfig,
    InitialChampionConfig,
    TrainingConfig,
    TrainingError,
)


@dataclass
class CandidateRun:
    ticker: str
    candidate: CandidateConfig
    b2_mae: float
    b3_mae: float
    joint_mae: float
    expected_anchor_count: int
    b2_valid_count: int
    b3_valid_count: int
    paired_anchor_count: int
    paired_coverage: float
    b2_invalid_count: int
    b3_invalid_count: int
    admissible: bool
    failure_reason: str | None
    initial_state_sha256: str
    final_b2_state_sha256: str
    duplicate_update_count: int
    predictions: pd.DataFrame
    update_events: pd.DataFrame
    updated_label_keys: tuple[tuple[date, str], ...]
    grid_order: int


@dataclass
class TrainingSelectionResult:
    candidate_evaluations: pd.DataFrame
    selected_configs: pd.DataFrame
    initial_models: dict[str, dict[str, Any]]
    baselines: dict[str, dict[str, Any]]
    manifest: dict[str, Any]
    artifact_dir: Path | None = None
    b4_models: dict[str, dict[str, Any]] | None = None
    b4_validation: pd.DataFrame | None = None
    initial_champions: pd.DataFrame | None = None
    initial_champion_scores: pd.DataFrame | None = None


def _market_date(value: Any, name: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        stamp = pd.Timestamp(value)
    except (TypeError, ValueError) as error:
        raise TrainingError(f"{name} must be a valid market date") from error
    if pd.isna(stamp):
        raise TrainingError(f"{name} must be a valid market date")
    return stamp.date()


def _require_b4_training_config(config: TrainingConfig) -> None:
    if config.training_config_version == LEGACY_TRAINING_CONFIG_VERSION:
        raise TrainingError(
            f"training_config_version {LEGACY_TRAINING_CONFIG_VERSION} predates B4; "
            "use version 1.1.0 to train B4"
        )


def _boolean_values(values: pd.Series) -> pd.Series:
    """Normalize nullable source flags without relying on object downcasting."""
    return values.astype("boolean").fillna(False).astype(bool)


def _json_default(value: Any) -> Any:
    if isinstance(value, (date, datetime, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, tuple):
        return list(value)
    raise TypeError(f"cannot serialize {type(value).__name__}")


def model_state_sha256(model: SGDRegressor, scaler: RobustScaler) -> str:
    """Hash prediction and incremental optimizer state plus the frozen scaler."""
    digest = hashlib.sha256()
    for label, value in (
        ("model_params", model.get_params(deep=False)),
        ("scaler_params", scaler.get_params(deep=False)),
    ):
        payload = json.dumps(value, sort_keys=True, default=_json_default, separators=(",", ":"))
        digest.update(label.encode("utf-8"))
        digest.update(payload.encode("utf-8"))
    for owner, attributes in (
        ("model", ("coef_", "intercept_", "n_iter_", "t_", "n_features_in_")),
        ("scaler", ("center_", "scale_", "n_features_in_", "feature_names_in_")),
    ):
        for attribute in attributes:
            if not hasattr(model if owner == "model" else scaler, attribute):
                continue
            value = getattr(model if owner == "model" else scaler, attribute)
            array = np.asarray(value)
            digest.update(f"{owner}.{attribute}:{array.dtype}:{array.shape}".encode("utf-8"))
            if array.dtype.hasobject:
                payload = json.dumps(
                    array.tolist(), sort_keys=True, default=_json_default, separators=(",", ":")
                )
                digest.update(payload.encode("utf-8"))
            else:
                digest.update(array.tobytes())
    return digest.hexdigest()


def scaler_state_sha256(scaler: RobustScaler) -> str:
    """Hash a fitted RobustScaler's parameters and learned statistics."""
    digest = hashlib.sha256()
    payload = json.dumps(
        scaler.get_params(deep=False),
        sort_keys=True,
        default=_json_default,
        separators=(",", ":"),
    )
    digest.update(b"scaler_params")
    digest.update(payload.encode("utf-8"))
    for attribute in ("center_", "scale_", "n_features_in_", "feature_names_in_"):
        if not hasattr(scaler, attribute):
            continue
        array = np.asarray(getattr(scaler, attribute))
        digest.update(f"scaler.{attribute}:{array.dtype}:{array.shape}".encode("utf-8"))
        if array.dtype.hasobject:
            encoded = json.dumps(
                array.tolist(), sort_keys=True, default=_json_default, separators=(",", ":")
            )
            digest.update(encoded.encode("utf-8"))
        else:
            digest.update(array.tobytes())
    return digest.hexdigest()


def b4_state_sha256(model: LinearRegression, scaler: RobustScaler) -> str:
    """Hash frozen B4 HAR-X OLS state together with its frozen RobustScaler."""
    digest = hashlib.sha256()
    identity = {
        "model_id": B4_MODEL_ID,
        "model_name": B4_MODEL_NAME,
        "model_version": B4_MODEL_VERSION,
        "feature_order": list(CORE_FEATURE_COLUMNS),
        "model_params": model.get_params(deep=False),
    }
    digest.update(
        json.dumps(identity, sort_keys=True, default=_json_default, separators=(",", ":")).encode(
            "utf-8"
        )
    )
    for attribute in ("coef_", "intercept_", "n_features_in_"):
        if not hasattr(model, attribute):
            continue
        array = np.asarray(getattr(model, attribute), dtype=float)
        digest.update(f"b4.{attribute}:{array.dtype}:{array.shape}".encode("utf-8"))
        digest.update(array.tobytes())
    digest.update(scaler_state_sha256(scaler).encode("utf-8"))
    return digest.hexdigest()


def _train_keys_fingerprint(
    train_metadata: pd.DataFrame,
    train_X: pd.DataFrame,
    train_y: pd.Series,
) -> str:
    """Fingerprint exact Train (date, ticker) keys, features, and targets."""
    digest = hashlib.sha256()
    keys = [
        [_market_date(row.date, "train date").isoformat(), str(row.ticker)]
        for row in train_metadata.itertuples(index=False)
    ]
    digest.update(json.dumps(keys, separators=(",", ":")).encode("utf-8"))
    digest.update(np.ascontiguousarray(train_X.to_numpy(dtype=np.float64)).tobytes())
    digest.update(np.ascontiguousarray(train_y.to_numpy(dtype=np.float64)).tobytes())
    return digest.hexdigest()


def _validate_candidate(candidate: CandidateConfig, config: TrainingConfig) -> int:
    try:
        return config.grid.index(candidate)
    except ValueError as error:
        raise TrainingError("candidate is not in the locked Stage 04 search grid") from error


def _training_rows(
    prepared: PreparedDataset,
    ticker: str,
    config: TrainingConfig,
) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series]:
    view = prepared.supervised
    if view.y is None or len(view.X) != len(view.metadata) or len(view.X) != len(view.y):
        raise TrainingError("supervised X, metadata, and y must be aligned")
    if tuple(view.X.columns) != tuple(config.core_features):
        raise TrainingError("supervised features do not match the locked feature order")
    metadata = view.metadata.copy()
    if metadata.duplicated(["date", "ticker"]).any():
        raise TrainingError("supervised primary key (date, ticker) must be unique")
    train_mask = (metadata["split"] == "train") & (metadata["ticker"].astype(str) == ticker)
    validation_mask = (metadata["split"] == "validation") & (
        metadata["ticker"].astype(str) == ticker
    )
    train_X = view.X.loc[train_mask].reset_index(drop=True)
    train_y = view.y.loc[train_mask].reset_index(drop=True).astype(float)
    validation_X = view.X.loc[validation_mask].reset_index(drop=True)
    validation_y = view.y.loc[validation_mask].reset_index(drop=True).astype(float)
    train_metadata = metadata.loc[train_mask].reset_index(drop=True)
    validation_metadata = metadata.loc[validation_mask].reset_index(drop=True)
    if train_X.empty or validation_X.empty:
        raise TrainingError(f"{ticker} requires eligible Train and Validation rows")
    required_metadata = {
        "target_end_date",
        "is_label_mature",
        "target_obs_count",
        "feature_quality_passed",
        "label_quality_passed",
    }
    missing_metadata = required_metadata.difference(metadata.columns)
    if missing_metadata:
        raise TrainingError(
            f"supervised metadata is missing Stage 04 fields: {sorted(missing_metadata)}"
        )
    for split_name, split_metadata, next_start in (
        ("Train", train_metadata, config.dataset.validation_start_date),
        ("Validation", validation_metadata, config.dataset.test_start_date),
    ):
        if not _boolean_values(split_metadata["is_label_mature"]).all():
            raise TrainingError(f"{ticker} {split_name} supervised labels must be mature")
        if not (pd.to_numeric(split_metadata["target_obs_count"], errors="coerce") == 5).all():
            raise TrainingError(f"{ticker} {split_name} labels must have exactly five observations")
        if not _boolean_values(split_metadata["feature_quality_passed"]).all():
            raise TrainingError(f"{ticker} {split_name} feature quality must pass")
        if not _boolean_values(split_metadata["label_quality_passed"]).all():
            raise TrainingError(f"{ticker} {split_name} label quality must pass")
        target_ends = split_metadata["target_end_date"].map(
            lambda value: None if pd.isna(value) else _market_date(value, "target_end_date")
        )
        if target_ends.isna().any() or any(value >= next_start for value in target_ends):
            raise TrainingError(
                f"{ticker} {split_name} supervised labels must pass the fixed split purge"
            )
        if any(value > config.dataset.data_cutoff for value in target_ends):
            raise TrainingError(f"{ticker} {split_name} labels exceed the strict data cutoff")
    if not np.isfinite(train_X.to_numpy(dtype=float)).all():
        raise TrainingError(f"{ticker} Train features must be finite")
    if not np.isfinite(train_y.to_numpy(dtype=float)).all() or (train_y < 0).any():
        raise TrainingError(f"{ticker} Train labels must be finite and nonnegative")
    if not np.isfinite(validation_X.to_numpy(dtype=float)).all():
        raise TrainingError(f"{ticker} Validation features must be finite")
    if not np.isfinite(validation_y.to_numpy(dtype=float)).all() or (validation_y < 0).any():
        raise TrainingError(f"{ticker} Validation labels must be finite and nonnegative")
    train_start = min(_market_date(value, "train date") for value in train_metadata["date"])
    train_end = max(_market_date(value, "train date") for value in train_metadata["date"])
    validation_start = min(
        _market_date(value, "validation date") for value in validation_metadata["date"]
    )
    validation_end = max(
        _market_date(value, "validation date") for value in validation_metadata["date"]
    )
    if train_start < config.dataset.train_start_date or train_end > config.dataset.train_end_date:
        raise TrainingError(f"{ticker} Train anchors fall outside the locked Train window")
    if (
        validation_start < config.dataset.validation_start_date
        or validation_end > config.dataset.validation_end_date
    ):
        raise TrainingError(f"{ticker} Validation anchors fall outside the locked Validation window")
    return train_X, train_y, validation_X, validation_y


def _fit_initial_pair(
    train_X: pd.DataFrame,
    train_y: pd.Series,
    candidate: CandidateConfig,
    config: TrainingConfig,
) -> dict[str, Any]:
    scaler = RobustScaler()
    scaler.fit(train_X)
    scaled_train = scaler.transform(train_X)
    trained = SGDRegressor(
        loss=config.loss,
        penalty=config.penalty,
        learning_rate=config.learning_rate,
        eta0=candidate.eta0,
        alpha=candidate.alpha,
        max_iter=candidate.max_iter,
        tol=config.tol,
        shuffle=config.shuffle,
        random_state=config.random_state,
        early_stopping=config.early_stopping,
    )
    trained.fit(scaled_train, train_y.to_numpy(dtype=float))
    b2 = deepcopy(trained)
    b3 = deepcopy(trained)
    state_hash = model_state_sha256(trained, scaler)
    if model_state_sha256(b2, scaler) != state_hash or model_state_sha256(b3, scaler) != state_hash:
        raise TrainingError("B2 and B3 initial estimator states do not match")
    if b2 is b3 or np.shares_memory(b2.coef_, b3.coef_):
        raise TrainingError("B2 and B3 must not share mutable estimator state")
    return {"scaler": scaler, "b2": b2, "b3": b3, "state_sha256": state_hash}


def _prediction_feature_map(
    prepared: PreparedDataset,
    ticker: str,
    config: TrainingConfig,
) -> dict[tuple[date, str], np.ndarray]:
    view = prepared.prediction
    if len(view.X) != len(view.metadata) or tuple(view.X.columns) != tuple(config.core_features):
        raise TrainingError("prediction features and metadata must align in locked feature order")
    metadata = view.metadata
    mask = metadata["split"].isin(["train", "validation"]) & (
        metadata["ticker"].astype(str) == ticker
    )
    selected_metadata = metadata.loc[mask]
    selected_X = view.X.loc[mask]
    if selected_metadata.duplicated(["date", "ticker"]).any():
        raise TrainingError("prediction primary key (date, ticker) must be unique")
    feature_map: dict[tuple[date, str], np.ndarray] = {}
    for (_, row), values in zip(selected_metadata.iterrows(), selected_X.to_numpy(dtype=float)):
        key = (_market_date(row["date"], "prediction date"), str(row["ticker"]))
        if not np.isfinite(values).all():
            raise TrainingError(f"non-finite eligible prediction features for {key}")
        feature_map[key] = values.copy()
    return feature_map


def _audit_for_replay(prepared: PreparedDataset, ticker: str) -> pd.DataFrame:
    audit = prepared.audit.copy()
    required = {
        "date",
        "ticker",
        "split",
        "target_end_date",
        "is_label_mature",
        "target_obs_count",
        "feature_quality_passed",
        "label_quality_passed",
        "prediction_eligible",
        "online_update_eligible",
        "already_updated",
    }
    missing = required.difference(audit.columns)
    if missing:
        raise TrainingError(f"dataset audit is missing Stage 04 fields: {sorted(missing)}")
    audit = audit.loc[
        audit["split"].isin(["train", "validation"])
        & (audit["ticker"].astype(str) == ticker)
    ].copy()
    if audit.duplicated(["date", "ticker"]).any():
        raise TrainingError("dataset audit primary key (date, ticker) must be unique")
    if _boolean_values(audit["already_updated"]).any():
        raise TrainingError("Stage 04 Validation trials must start with an empty update ledger")
    audit["date"] = audit["date"].map(lambda value: _market_date(value, "audit date"))
    audit["target_end_date"] = audit["target_end_date"].map(
        lambda value: None if pd.isna(value) else _market_date(value, "target_end_date")
    )
    return audit.sort_values("date", kind="stable").reset_index(drop=True)


def _mature_update_labels(
    labels: pd.DataFrame,
    required_keys: set[tuple[date, str]],
) -> dict[tuple[date, str], dict[str, Any]]:
    required_columns = {
        "date",
        "ticker",
        "target_end_date",
        "target_obs_count",
        "target_realized_vol_5d",
        "is_label_mature",
    }
    missing = required_columns.difference(labels.columns)
    if missing:
        raise TrainingError(f"labels are missing Stage 04 fields: {sorted(missing)}")
    found: dict[tuple[date, str], dict[str, Any]] = {}
    for row in labels.itertuples(index=False):
        key = (_market_date(getattr(row, "date"), "label date"), str(getattr(row, "ticker")))
        if key not in required_keys:
            continue
        if key in found:
            raise TrainingError(f"label primary key (date, ticker) is duplicated for {key}")
        found[key] = {
            "target_end_date": _market_date(getattr(row, "target_end_date"), "target_end_date"),
            "target_obs_count": int(getattr(row, "target_obs_count")),
            "target_realized_vol_5d": getattr(row, "target_realized_vol_5d"),
            "is_label_mature": bool(getattr(row, "is_label_mature")),
        }
    absent = required_keys.difference(found)
    if absent:
        example = sorted(absent)[:3]
        raise TrainingError(f"eligible replay labels are missing from input: {example}")
    return found


def _is_valid_forecast(value: Any) -> bool:
    return isinstance(value, (int, float, np.integer, np.floating)) and np.isfinite(float(value)) and float(value) >= 0


def evaluate_candidate(
    prepared: PreparedDataset,
    labels: pd.DataFrame,
    *,
    ticker: str,
    candidate: CandidateConfig,
    config: TrainingConfig | None = None,
) -> CandidateRun:
    """Fit one candidate and run its paired B2/B3 Validation replay."""
    effective_config = config or TrainingConfig.from_yaml()
    if ticker not in SUPPORTED_TICKERS:
        raise TrainingError(f"unsupported ETF: {ticker}")
    grid_order = _validate_candidate(candidate, effective_config)
    train_X, train_y, _, _ = _training_rows(prepared, ticker, effective_config)
    validation_view = prepared.supervised
    validation_mask = (validation_view.metadata["split"] == "validation") & (
        validation_view.metadata["ticker"].astype(str) == ticker
    )
    validation_metadata = validation_view.metadata.loc[validation_mask].reset_index(drop=True)
    validation_y = validation_view.y.loc[validation_mask].reset_index(drop=True).astype(float)
    expected_keys = [
        (_market_date(row.date, "validation date"), str(row.ticker))
        for row in validation_metadata.itertuples(index=False)
    ]
    if not expected_keys or len(set(expected_keys)) != len(expected_keys):
        raise TrainingError(f"{ticker} requires unique eligible Validation anchors")

    pair = _fit_initial_pair(train_X, train_y, candidate, effective_config)
    scaler: RobustScaler = pair["scaler"]
    b2: SGDRegressor = pair["b2"]
    b3: SGDRegressor = pair["b3"]
    initial_hash = pair["state_sha256"]
    if model_state_sha256(b2, scaler) != model_state_sha256(b3, scaler):
        raise TrainingError("B2 and B3 did not start from the same state")

    feature_map = _prediction_feature_map(prepared, ticker, effective_config)
    audit = _audit_for_replay(prepared, ticker)
    update_rows = audit.loc[
        _boolean_values(audit["online_update_eligible"])
        & _boolean_values(audit["prediction_eligible"])
        & _boolean_values(audit["feature_quality_passed"])
        & _boolean_values(audit["label_quality_passed"])
        & _boolean_values(audit["is_label_mature"])
        & (pd.to_numeric(audit["target_obs_count"], errors="coerce") == 5)
        & audit["target_end_date"].notna()
    ].copy()
    update_rows = update_rows.loc[
        update_rows.apply(
            lambda row: (row["date"], str(row["ticker"])) in feature_map,
            axis=1,
        )
    ]
    update_keys = {
        (row.date, str(row.ticker)) for row in update_rows.itertuples(index=False)
    }
    label_map = _mature_update_labels(labels, update_keys)
    update_rows_by_maturity = {
        maturity_date: group
        for maturity_date, group in update_rows.groupby("target_end_date", sort=True)
    }

    # Initial Train keys are already represented in the fitted model and may never be updated again.
    train_metadata = prepared.supervised.metadata
    train_mask = (train_metadata["split"] == "train") & (
        train_metadata["ticker"].astype(str) == ticker
    )
    ledger = {
        (_market_date(row.date, "training date"), str(row.ticker))
        for row in train_metadata.loc[train_mask].itertuples(index=False)
    }
    updated_keys: list[tuple[date, str]] = []
    update_events: list[dict[str, Any]] = []
    forecast_by_key: dict[tuple[date, str], dict[str, Any]] = {}

    validation_sessions = market_calendars.get_calendar(effective_config.dataset.market).schedule(
        start_date=effective_config.dataset.validation_start_date,
        end_date=effective_config.dataset.validation_end_date,
    ).index
    session_dates = {session.date() for session in validation_sessions}
    replay_days = {key[0] for key in expected_keys}
    replay_days.update(
        row.target_end_date
        for row in update_rows.itertuples(index=False)
        if effective_config.dataset.validation_start_date
        <= row.target_end_date
        <= effective_config.dataset.validation_end_date
        and row.date <= row.target_end_date
    )
    if not replay_days.issubset(session_dates):
        raise TrainingError("Validation anchors and mature-label dates must be XNYS sessions")
    for replay_day in sorted(replay_days):
        todays = [key for key in expected_keys if key[0] == replay_day]
        for key in todays:
            features = feature_map.get(key)
            if features is None:
                continue
            scaled = scaler.transform(pd.DataFrame([features], columns=effective_config.core_features))
            b2_raw = float(b2.predict(scaled)[0])
            b3_raw = float(b3.predict(scaled)[0])
            forecast_by_key[key] = {
                "prediction_date": key[0],
                "ticker": ticker,
                "b2_prediction_raw": b2_raw,
                "b3_prediction_raw": b3_raw,
                "b2_prediction_valid": _is_valid_forecast(b2_raw),
                "b3_prediction_valid": _is_valid_forecast(b3_raw),
                "model_state_sha256_before_prediction": model_state_sha256(b3, scaler),
            }

        # Update after recording every forecast for this market session.
        due: list[tuple[tuple[date, str], dict[str, Any]]] = []
        rows_maturing_today = update_rows_by_maturity.get(replay_day)
        if rows_maturing_today is None:
            rows_maturing_today = update_rows.iloc[0:0]
        for row in rows_maturing_today.itertuples(index=False):
            key = (row.date, str(row.ticker))
            if key in ledger or key[0] > replay_day or row.target_end_date > replay_day:
                continue
            label = label_map[key]
            if label["target_end_date"] != row.target_end_date:
                raise TrainingError(f"audit/label target_end_date mismatch for {key}")
            if not label["is_label_mature"] or label["target_obs_count"] != 5:
                raise TrainingError(f"eligible replay label is not mature for {key}")
            target = label["target_realized_vol_5d"]
            if not _is_valid_forecast(target):
                raise TrainingError(f"eligible replay label is invalid for {key}")
            due.append((key, label))
        due.sort(key=lambda item: item[0])
        if due:
            before_update_hash = model_state_sha256(b3, scaler)
            batch_X = np.vstack([feature_map[key] for key, _ in due])
            batch_y = np.asarray([float(label["target_realized_vol_5d"]) for _, label in due])
            scaled_batch = scaler.transform(
                pd.DataFrame(batch_X, columns=effective_config.core_features)
            )
            b3.partial_fit(scaled_batch, batch_y)
            after_update_hash = model_state_sha256(b3, scaler)
            for key, label in due:
                if key in ledger:
                    raise TrainingError(f"duplicate B3 update attempted for {key}")
                ledger.add(key)
                updated_keys.append(key)
                update_events.append(
                    {
                        "replay_date": replay_day,
                        "anchor_date": key[0],
                        "ticker": ticker,
                        "target_end_date": label["target_end_date"],
                        "target_obs_count": label["target_obs_count"],
                        "model_state_sha256_before_update": before_update_hash,
                        "model_state_sha256_after_update": after_update_hash,
                    }
                )

    actual_by_key = dict(zip(expected_keys, validation_y.to_numpy(dtype=float)))
    paired_predictions: list[dict[str, Any]] = []
    b2_invalid_count = 0
    b3_invalid_count = 0
    for key in expected_keys:
        forecast = forecast_by_key.get(key)
        if forecast is None:
            b2_invalid_count += 1
            b3_invalid_count += 1
            continue
        b2_valid = bool(forecast["b2_prediction_valid"])
        b3_valid = bool(forecast["b3_prediction_valid"])
        b2_invalid_count += int(not b2_valid)
        b3_invalid_count += int(not b3_valid)
        if b2_valid and b3_valid:
            paired_predictions.append(
                {
                    "actual": actual_by_key[key],
                    "b2": forecast["b2_prediction_raw"],
                    "b3": forecast["b3_prediction_raw"],
                }
            )

    expected_count = len(expected_keys)
    paired_count = len(paired_predictions)
    coverage = paired_count / expected_count
    if paired_count:
        b2_mae = float(np.mean([abs(row["actual"] - row["b2"]) for row in paired_predictions]))
        b3_mae = float(np.mean([abs(row["actual"] - row["b3"]) for row in paired_predictions]))
        joint_mae = (b2_mae + b3_mae) / 2
    else:
        b2_mae = float("nan")
        b3_mae = float("nan")
        joint_mae = float("nan")
    admissible = paired_count == expected_count
    failure_reason = None if admissible else "INCOMPLETE_PAIRED_VALIDATION_COVERAGE"
    final_b2_hash = model_state_sha256(b2, scaler)
    if final_b2_hash != initial_hash:
        raise TrainingError("B2 state changed during Validation; static model must remain frozen")
    predictions = pd.DataFrame(
        [forecast_by_key[key] for key in expected_keys if key in forecast_by_key]
    )
    events = pd.DataFrame(update_events)
    return CandidateRun(
        ticker=ticker,
        candidate=candidate,
        b2_mae=b2_mae,
        b3_mae=b3_mae,
        joint_mae=joint_mae,
        expected_anchor_count=expected_count,
        b2_valid_count=expected_count - b2_invalid_count,
        b3_valid_count=expected_count - b3_invalid_count,
        paired_anchor_count=paired_count,
        paired_coverage=coverage,
        b2_invalid_count=b2_invalid_count,
        b3_invalid_count=b3_invalid_count,
        admissible=admissible,
        failure_reason=failure_reason,
        initial_state_sha256=initial_hash,
        final_b2_state_sha256=final_b2_hash,
        duplicate_update_count=len(updated_keys) - len(set(updated_keys)),
        predictions=predictions,
        update_events=events,
        updated_label_keys=tuple(updated_keys),
        grid_order=grid_order,
    )


def fit_b4_ols(
    prepared: PreparedDataset,
    ticker: str,
    config: TrainingConfig | None = None,
    *,
    b2_scaler: RobustScaler | None = None,
) -> dict[str, Any]:
    """Fit frozen B4 HAR-X OLS with intercept on the exact B2 Train sample and RobustScaler."""
    effective_config = config or TrainingConfig.from_yaml()
    _require_b4_training_config(effective_config)
    if ticker not in SUPPORTED_TICKERS:
        raise TrainingError(f"unsupported ETF: {ticker}")
    train_X, train_y, _, _ = _training_rows(prepared, ticker, effective_config)
    metadata = prepared.supervised.metadata
    train_mask = (metadata["split"] == "train") & (metadata["ticker"].astype(str) == ticker)
    train_metadata = metadata.loc[train_mask].reset_index(drop=True)
    n_features = len(effective_config.core_features)
    min_rows = n_features + 1
    if len(train_X) < min_rows:
        raise TrainingError(
            f"{ticker} B4 requires at least {min_rows} eligible Train rows for OLS with intercept (got {len(train_X)})"
        )
    X_arr = train_X.to_numpy(dtype=float)
    y_arr = train_y.to_numpy(dtype=float)
    if not np.isfinite(X_arr).all() or not np.isfinite(y_arr).all() or (y_arr < 0).any():
        raise TrainingError(f"{ticker} B4 Train features and labels must be finite and nonnegative")

    scaler = RobustScaler()
    scaler.fit(train_X)
    scaler_hash = scaler_state_sha256(scaler)
    if b2_scaler is not None:
        b2_scaler_hash = scaler_state_sha256(b2_scaler)
        if scaler_hash != b2_scaler_hash:
            raise TrainingError(f"{ticker} B4 RobustScaler identity does not match B2")
        scaler = deepcopy(b2_scaler)

    scaled_train = scaler.transform(train_X)
    if not np.isfinite(scaled_train).all():
        raise TrainingError(f"{ticker} B4 scaled Train features contain non-finite values")
    design = np.column_stack([np.ones(len(scaled_train), dtype=float), scaled_train])
    rank = int(np.linalg.matrix_rank(design))
    if rank < min_rows:
        raise TrainingError(
            f"{ticker} B4 OLS design matrix is rank-deficient (rank={rank} < {min_rows})"
        )
    singular_values = np.linalg.svd(design, compute_uv=False)
    cond = float(singular_values[0] / singular_values[-1]) if singular_values[-1] > 0 else float("inf")
    warnings: list[str] = []
    threshold = effective_config.b4_ill_conditioned_threshold
    if not math.isfinite(cond) or cond > threshold:
        warnings.append(
            f"design_matrix_ill_conditioned:cond={cond:.6e}>threshold={threshold:.1e}"
        )

    model = LinearRegression(fit_intercept=effective_config.b4_fit_intercept)
    model.fit(scaled_train, y_arr)
    if (
        not np.isfinite(model.intercept_)
        or not np.isfinite(model.coef_).all()
        or len(model.coef_) != n_features
    ):
        raise TrainingError(f"{ticker} B4 OLS produced non-finite or malformed parameters")

    train_ends = [
        _market_date(value, "target_end_date")
        for value in train_metadata["target_end_date"]
    ]
    last_target_end = max(train_ends)
    if last_target_end >= effective_config.dataset.validation_start_date:
        raise TrainingError(f"{ticker} B4 Train labels violate fixed split purge")
    keys_fingerprint = _train_keys_fingerprint(train_metadata, train_X, train_y)
    state_hash = b4_state_sha256(model, scaler)
    return {
        "model_id": B4_MODEL_ID,
        "model_name": B4_MODEL_NAME,
        "model_version": B4_MODEL_VERSION,
        "model": model,
        "scaler": scaler,
        "intercept": float(model.intercept_),
        "coefficients": {
            name: float(coef)
            for name, coef in zip(effective_config.core_features, model.coef_)
        },
        "feature_order": tuple(effective_config.core_features),
        "scaler_state_sha256": scaler_hash,
        "state_sha256": state_hash,
        "train_keys_count": int(len(train_metadata)),
        "train_keys_fingerprint": keys_fingerprint,
        "train_cutoff": effective_config.dataset.train_end_date,
        "last_training_target_end_date": last_target_end,
        "design_rank": rank,
        "condition_number": cond,
        "ill_conditioned": bool(warnings),
        "warnings": tuple(warnings),
    }


def evaluate_b4_validation(
    prepared: PreparedDataset,
    ticker: str,
    b4_artifact: Mapping[str, Any],
    config: TrainingConfig | None = None,
) -> tuple[dict[str, Any], pd.DataFrame]:
    """Evaluate frozen B4 HAR-X OLS on Validation anchors without affecting B2/B3 selection."""
    effective_config = config or TrainingConfig.from_yaml()
    if ticker not in SUPPORTED_TICKERS:
        raise TrainingError(f"unsupported ETF: {ticker}")
    _, _, validation_X, validation_y = _training_rows(prepared, ticker, effective_config)
    metadata = prepared.supervised.metadata
    validation_mask = (metadata["split"] == "validation") & (metadata["ticker"].astype(str) == ticker)
    validation_metadata = metadata.loc[validation_mask].reset_index(drop=True)
    if tuple(b4_artifact["feature_order"]) != tuple(effective_config.core_features):
        raise TrainingError(f"{ticker} B4 feature_order does not match locked Core Features")

    scaler: RobustScaler = b4_artifact["scaler"]
    model: LinearRegression = b4_artifact["model"]
    scaled_val = scaler.transform(validation_X)
    raw_preds = model.predict(scaled_val)

    rows: list[dict[str, Any]] = []
    valid_errors: list[float] = []
    invalid_reasons: list[str] = []
    for meta_row, actual, pred_raw in zip(
        validation_metadata.itertuples(index=False),
        validation_y.to_numpy(dtype=float),
        raw_preds,
    ):
        pred_val = float(pred_raw)
        is_valid = _is_valid_forecast(pred_val)
        reason = (
            None
            if is_valid
            else "forecast must be finite and nonnegative; value was rejected without clipping"
        )
        if not is_valid:
            invalid_reasons.append(
                f"{_market_date(meta_row.date, 'validation date').isoformat()}:{reason}"
            )
        else:
            valid_errors.append(abs(float(actual) - pred_val))
        rows.append(
            {
                "prediction_date": _market_date(meta_row.date, "validation date"),
                "ticker": ticker,
                "model_id": B4_MODEL_ID,
                "model_name": B4_MODEL_NAME,
                "model_version": B4_MODEL_VERSION,
                "target_realized_vol_5d": float(actual),
                "predicted_vol_annualized": pred_val if is_valid else np.nan,
                "raw_prediction": pred_val,
                "forecast_valid": bool(is_valid),
                "invalid_reason": reason,
                "absolute_error": abs(float(actual) - pred_val) if is_valid else np.nan,
                "squared_error": (float(actual) - pred_val) ** 2 if is_valid else np.nan,
            }
        )
    expected_count = len(validation_X)
    valid_count = len(valid_errors)
    invalid_count = expected_count - valid_count
    if valid_count == 0:
        raise TrainingError(f"{ticker} B4 produced zero valid Validation forecasts")
    coverage = valid_count / expected_count
    mae = float(np.mean(valid_errors))
    rmse = float(np.sqrt(np.mean(np.square(valid_errors))))
    summary = {
        "ticker": ticker,
        "model_id": B4_MODEL_ID,
        "model_name": B4_MODEL_NAME,
        "model_version": B4_MODEL_VERSION,
        "expected_anchor_count": int(expected_count),
        "valid_count": int(valid_count),
        "invalid_count": int(invalid_count),
        "coverage": float(coverage),
        "mae_validation": mae,
        "rmse_validation": rmse,
        "invalid_reasons": invalid_reasons,
        "train_keys_count": int(b4_artifact["train_keys_count"]),
        "train_keys_fingerprint": str(b4_artifact["train_keys_fingerprint"]),
        "last_training_target_end_date": b4_artifact["last_training_target_end_date"].isoformat(),
        "design_rank": int(b4_artifact["design_rank"]),
        "condition_number": float(b4_artifact["condition_number"]),
        "ill_conditioned": bool(b4_artifact["ill_conditioned"]),
        "warnings": list(b4_artifact["warnings"]),
    }
    return summary, pd.DataFrame(rows)


def predict_baselines(
    features: pd.DataFrame,
    baselines: Mapping[str, Mapping[str, Any]],
) -> pd.DataFrame:
    """Return B0 Train-mean and B1 same-day RV20 forecasts in long form."""
    required = {"date", "ticker", "rv_20d"}
    missing = required.difference(features.columns)
    if missing:
        raise TrainingError(f"baseline features are missing columns: {sorted(missing)}")
    if features.duplicated(["date", "ticker"]).any():
        raise TrainingError("baseline input primary key (date, ticker) must be unique")
    predictions: list[dict[str, Any]] = []
    for row in features.itertuples(index=False):
        ticker = str(row.ticker)
        if ticker not in baselines:
            raise TrainingError(f"B0 Train mean is missing for {ticker}")
        b0 = baselines[ticker].get("b0_train_mean")
        b1 = getattr(row, "rv_20d")
        if not _is_valid_forecast(b0):
            raise TrainingError(f"B0 Train mean is invalid for {ticker}")
        if not _is_valid_forecast(b1):
            raise TrainingError(f"B1 rv_20d input is invalid for {ticker}")
        prediction_date = _market_date(row.date, "baseline prediction date")
        predictions.extend(
            (
                {
                    "prediction_date": prediction_date,
                    "ticker": ticker,
                    "model_id": "B0",
                    "predicted_vol_annualized": float(b0),
                },
                {
                    "prediction_date": prediction_date,
                    "ticker": ticker,
                    "model_id": "B1",
                    "predicted_vol_annualized": float(b1),
                },
            )
        )
    return pd.DataFrame(predictions)


def _canonical_json_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=_json_default)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _initial_candidate_state_hashes(
    ticker: str,
    initial_model_entry: Mapping[str, Any],
    baseline_entry: Mapping[str, Any],
) -> dict[str, str]:
    b2_hash = model_state_sha256(initial_model_entry["b2"], initial_model_entry["scaler"])
    if b2_hash != str(initial_model_entry["state_sha256"]):
        raise TrainingError(f"{ticker} B2 state hash does not match initial_models entry")
    b0_hash = _canonical_json_sha256(
        {
            "model_id": "B0",
            "model_name": BASELINE_MODEL_NAMES["B0"],
            "ticker": ticker,
            "b0_train_mean": float(baseline_entry["b0_train_mean"]),
            "b0_train_end_date": str(baseline_entry["b0_train_end_date"]),
        }
    )
    b1_hash = _canonical_json_sha256(
        {
            "model_id": "B1",
            "model_name": BASELINE_MODEL_NAMES["B1"],
            "ticker": ticker,
            "b1_feature": str(baseline_entry["b1_feature"]),
            "b1_strategy": str(baseline_entry["b1_strategy"]),
        }
    )
    return {"B0": b0_hash, "B1": b1_hash, "B2": b2_hash}


def _validation_cutover_labels(
    labels: pd.DataFrame,
    cutover_date: date,
) -> dict[tuple[date, str], dict[str, Any]]:
    required_columns = {
        "date",
        "ticker",
        "target_end_date",
        "target_obs_count",
        "target_realized_vol_5d",
        "is_label_mature",
    }
    missing = required_columns.difference(labels.columns)
    if missing:
        raise TrainingError(f"labels are missing Stage 04 fields: {sorted(missing)}")
    found: dict[tuple[date, str], dict[str, Any]] = {}
    for row in labels.itertuples(index=False):
        anchor_date = _market_date(getattr(row, "date"), "label date")
        ticker = str(getattr(row, "ticker"))
        if ticker not in SUPPORTED_TICKERS or anchor_date >= cutover_date:
            # Never inspect Test labels or labels on/after cutover during initial champion selection.
            continue
        key = (anchor_date, ticker)
        if key in found:
            raise TrainingError(f"label primary key (date, ticker) is duplicated for {key}")
        raw_end = getattr(row, "target_end_date")
        raw_obs = getattr(row, "target_obs_count")
        raw_mature = getattr(row, "is_label_mature")
        found[key] = {
            "target_end_date": None if pd.isna(raw_end) else _market_date(raw_end, "target_end_date"),
            "target_obs_count": None if pd.isna(raw_obs) else int(raw_obs),
            "target_realized_vol_5d": getattr(row, "target_realized_vol_5d"),
            "is_label_mature": False if pd.isna(raw_mature) else bool(raw_mature),
        }
    return found


def _validation_cutover_features(
    prepared: PreparedDataset,
    ticker: str,
    config: TrainingConfig,
    cutover_date: date,
) -> dict[date, np.ndarray]:
    view = prepared.prediction
    if len(view.X) != len(view.metadata) or tuple(view.X.columns) != tuple(config.core_features):
        raise TrainingError("prediction features and metadata must align in locked feature order")
    metadata = view.metadata
    mask = (metadata["split"] == "validation") & (metadata["ticker"].astype(str) == ticker)
    selected_metadata = metadata.loc[mask]
    selected_X = view.X.loc[mask]
    if selected_metadata.duplicated(["date", "ticker"]).any():
        raise TrainingError("prediction primary key (date, ticker) must be unique")
    feature_map: dict[date, np.ndarray] = {}
    for (_, row), values in zip(selected_metadata.iterrows(), selected_X.to_numpy(dtype=float)):
        anchor_date = _market_date(row["date"], "prediction date")
        if anchor_date >= cutover_date:
            raise TrainingError(f"{ticker} Validation anchor {anchor_date} reaches or exceeds cutover {cutover_date}")
        if not np.isfinite(values).all():
            raise TrainingError(f"non-finite eligible prediction features for {(anchor_date, ticker)}")
        feature_map[anchor_date] = values.copy()
    return feature_map


def _select_ticker_initial_champion(
    prepared: PreparedDataset,
    label_lookup: Mapping[tuple[date, str], Mapping[str, Any]],
    ticker: str,
    initial_model_entry: Mapping[str, Any],
    baseline_entry: Mapping[str, Any],
    config: TrainingConfig,
    ic_cfg: InitialChampionConfig,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    audit = prepared.audit
    required = {"date", "ticker", "split", "target_end_date", "prediction_eligible"}
    missing = required.difference(audit.columns)
    if missing:
        raise TrainingError(f"dataset audit is missing Stage 04 fields: {sorted(missing)}")
    val_audit = audit.loc[
        (audit["split"] == "validation") & (audit["ticker"].astype(str) == ticker)
    ].copy()
    if val_audit.duplicated(["date", "ticker"]).any():
        raise TrainingError("dataset audit primary key (date, ticker) must be unique")
    val_audit["date"] = val_audit["date"].map(lambda value: _market_date(value, "audit date"))
    if (val_audit["date"] >= ic_cfg.cutover_date).any():
        raise TrainingError(f"{ticker} Validation rows must precede cutover_date {ic_cfg.cutover_date}")
    val_audit["target_end_date"] = val_audit["target_end_date"].map(
        lambda value: None if pd.isna(value) else _market_date(value, "target_end_date")
    )
    eligible = val_audit.loc[_boolean_values(val_audit["prediction_eligible"])].sort_values(
        "date", kind="stable"
    )
    validation_total_anchors = int(len(eligible))
    immature_mask = eligible["target_end_date"].isna() | (eligible["target_end_date"] >= ic_cfg.cutover_date)
    immature_rows = eligible.loc[immature_mask]
    expected_rows = eligible.loc[~immature_mask].reset_index(drop=True)
    immature_at_cutover_count = int(len(immature_rows))
    expected_cutover_count = int(len(expected_rows))
    if expected_cutover_count < ic_cfg.minimum_cutover_anchors:
        raise TrainingError(
            f"{ticker} initial champion selection found {expected_cutover_count} mature Validation anchors "
            f"before cutover {ic_cfg.cutover_date.isoformat()} (< minimum_cutover_anchors="
            f"{ic_cfg.minimum_cutover_anchors}); immature_at_cutover_count={immature_at_cutover_count}"
        )

    feature_map = _validation_cutover_features(prepared, ticker, config, ic_cfg.cutover_date)
    expected_dates = [row.date for row in expected_rows.itertuples(index=False)]
    missing_features = [anchor for anchor in expected_dates if anchor not in feature_map]
    if missing_features:
        raise TrainingError(
            f"{ticker} is missing Validation prediction features before cutover: {missing_features[:3]}"
        )
    x_df = pd.DataFrame(
        [feature_map[anchor] for anchor in expected_dates],
        columns=list(config.core_features),
    )
    scaler: RobustScaler = initial_model_entry["scaler"]
    b2_model: SGDRegressor = initial_model_entry["b2"]
    b2_raw_preds = b2_model.predict(scaler.transform(x_df))
    b1_raw_preds = x_df["rv_20d"].to_numpy(dtype=float)
    b0_raw_val = baseline_entry.get("b0_train_mean")
    state_hashes = _initial_candidate_state_hashes(ticker, initial_model_entry, baseline_entry)

    valid_counts = {m: 0 for m in ic_cfg.candidate_models}
    invalid_counts = {m: 0 for m in ic_cfg.candidate_models}
    abs_errors: dict[str, list[float]] = {m: [] for m in ic_cfg.candidate_models}
    sq_errors: dict[str, list[float]] = {m: [] for m in ic_cfg.candidate_models}
    label_invalid_count = 0
    failure_reasons: list[str] = []
    paired_anchor_count = 0
    candidate_score_rows: list[dict[str, Any]] = []

    for idx, meta_row in enumerate(expected_rows.itertuples(index=False)):
        anchor_date: date = meta_row.date
        audit_target_end: date = meta_row.target_end_date
        label_entry = label_lookup.get((anchor_date, ticker))
        label_valid = True
        label_reason: str | None = None
        actual_val = float("nan")
        if label_entry is None:
            label_valid = False
            label_reason = "missing_validation_label_at_cutover"
        elif not bool(label_entry["is_label_mature"]) or label_entry["target_obs_count"] != 5:
            label_valid = False
            label_reason = "label_immature_before_cutover"
        elif label_entry["target_end_date"] is None or label_entry["target_end_date"] >= ic_cfg.cutover_date:
            label_valid = False
            label_reason = "label_target_end_not_strictly_before_cutover"
        elif label_entry["target_end_date"] != audit_target_end:
            label_valid = False
            label_reason = "label_target_end_mismatch_with_audit"
        elif not _is_valid_forecast(label_entry["target_realized_vol_5d"]):
            label_valid = False
            label_reason = "label_target_value_nonfinite_or_negative"
        else:
            actual_val = float(label_entry["target_realized_vol_5d"])

        if not label_valid:
            label_invalid_count += 1
            failure_reasons.append(f"{anchor_date.isoformat()}:{label_reason}")

        raw_by_model = {
            "B0": b0_raw_val,
            "B1": float(b1_raw_preds[idx]),
            "B2": float(b2_raw_preds[idx]),
        }
        anchor_model_valid: dict[str, bool] = {}
        anchor_errors: dict[str, float] = {}
        per_anchor_rows: list[dict[str, Any]] = []
        for model_id in ic_cfg.candidate_models:
            raw_pred = raw_by_model[model_id]
            pred_valid = _is_valid_forecast(raw_pred)
            anchor_model_valid[model_id] = pred_valid
            pred_float = float(raw_pred) if isinstance(raw_pred, (int, float, np.integer, np.floating)) else np.nan
            invalid_reason: str | None = None
            if pred_valid:
                valid_counts[model_id] += 1
            else:
                invalid_counts[model_id] += 1
                invalid_reason = "forecast must be finite and nonnegative; value rejected without clipping"
                failure_reasons.append(f"{anchor_date.isoformat()}:{model_id}:{invalid_reason}")
            if pred_valid and label_valid:
                abs_err = abs(actual_val - pred_float)
                sq_err = (actual_val - pred_float) ** 2
                anchor_errors[model_id] = abs_err
            else:
                abs_err = np.nan
                sq_err = np.nan
                if invalid_reason is None and label_reason is not None:
                    invalid_reason = label_reason
            per_anchor_rows.append(
                {
                    "ticker": ticker,
                    "prediction_date": anchor_date,
                    "target_end_date": audit_target_end,
                    "cutover_date": ic_cfg.cutover_date,
                    "model_id": model_id,
                    "model_name": BASELINE_MODEL_NAMES[model_id],
                    "target_realized_vol_5d": actual_val if label_valid else np.nan,
                    "raw_prediction": pred_float,
                    "predicted_vol_annualized": pred_float if pred_valid else np.nan,
                    "forecast_valid": bool(pred_valid),
                    "label_valid": bool(label_valid),
                    "invalid_reason": invalid_reason,
                    "absolute_error": abs_err,
                    "squared_error": sq_err,
                }
            )

        paired_valid = label_valid and all(anchor_model_valid.values())
        if paired_valid:
            paired_anchor_count += 1
            for model_id in ic_cfg.candidate_models:
                abs_errors[model_id].append(anchor_errors[model_id])
                sq_errors[model_id].append(anchor_errors[model_id] ** 2)
        for row_dict in per_anchor_rows:
            row_dict["paired_valid"] = bool(paired_valid)
            candidate_score_rows.append(row_dict)

    paired_coverage = paired_anchor_count / expected_cutover_count if expected_cutover_count > 0 else 0.0
    if (
        paired_anchor_count < ic_cfg.minimum_cutover_anchors
        or paired_coverage < ic_cfg.minimum_paired_coverage
    ):
        raise TrainingError(
            f"{ticker} initial champion selection failed completeness gate "
            f"({paired_anchor_count}/{expected_cutover_count} = {paired_coverage:.4f} < "
            f"{ic_cfg.minimum_paired_coverage}); invalid_counts={invalid_counts}, "
            f"label_invalid_count={label_invalid_count}, examples={failure_reasons[:3]}"
        )

    mae_by_model = {m: float(np.mean(abs_errors[m])) for m in ic_cfg.candidate_models}
    rmse_by_model = {m: float(np.sqrt(np.mean(sq_errors[m]))) for m in ic_cfg.candidate_models}
    best_mae = min(mae_by_model.values())
    tied_models = [
        m for m in ic_cfg.tie_break_order if abs(mae_by_model[m] - best_mae) <= ic_cfg.tie_tolerance
    ]
    winner = tied_models[0]
    runner_up = sorted(
        [m for m in ic_cfg.tie_break_order if m != winner],
        key=lambda m: (mae_by_model[m], ic_cfg.tie_break_order.index(m)),
    )[0]
    margin = float(mae_by_model[runner_up] - mae_by_model[winner])

    for row_dict in candidate_score_rows:
        row_dict["selected_initial_champion"] = row_dict["model_id"] == winner

    selection_row = {
        "ticker": ticker,
        "policy_version": ic_cfg.policy_version,
        "scoring_split": ic_cfg.scoring_split,
        "cutover_date": ic_cfg.cutover_date,
        "validation_total_anchor_count": validation_total_anchors,
        "immature_at_cutover_count": immature_at_cutover_count,
        "expected_cutover_anchor_count": expected_cutover_count,
        "paired_anchor_count": paired_anchor_count,
        "paired_coverage": float(paired_coverage),
        "b0_valid_count": valid_counts["B0"],
        "b0_invalid_count": invalid_counts["B0"],
        "mae_b0_validation": mae_by_model["B0"],
        "rmse_b0_validation": rmse_by_model["B0"],
        "b1_valid_count": valid_counts["B1"],
        "b1_invalid_count": invalid_counts["B1"],
        "mae_b1_validation": mae_by_model["B1"],
        "rmse_b1_validation": rmse_by_model["B1"],
        "b2_valid_count": valid_counts["B2"],
        "b2_invalid_count": invalid_counts["B2"],
        "mae_b2_validation": mae_by_model["B2"],
        "rmse_b2_validation": rmse_by_model["B2"],
        "selected_model_id": winner,
        "selected_model_name": BASELINE_MODEL_NAMES[winner],
        "selected_validation_mae": mae_by_model[winner],
        "runner_up_model_id": runner_up,
        "runner_up_validation_mae": mae_by_model[runner_up],
        "mae_margin_vs_runner_up": margin,
        "tie_detected": len(tied_models) > 1,
        "tied_models": ",".join(tied_models),
        "tie_tolerance": ic_cfg.tie_tolerance,
        "selected_model_state_sha256": state_hashes[winner],
        "b2_equals_b3_initial_state_sha256": state_hashes["B2"],
        "last_training_target_end_date": str(baseline_entry["b0_train_end_date"]),
        "candidate_models_considered": ",".join(ic_cfg.candidate_models),
        "excluded_models": "B3,B4",
        "config_fingerprint": ic_cfg.fingerprint(),
    }
    ticker_json = {
        **selection_row,
        "cutover_date": ic_cfg.cutover_date.isoformat(),
        "immature_at_cutover_dates": [d.isoformat() for d in immature_rows["date"].tolist()],
        "tied_models": list(tied_models),
        "candidate_models_considered": list(ic_cfg.candidate_models),
        "excluded_models": ["B3", "B4"],
        "mae_by_model": mae_by_model,
        "rmse_by_model": rmse_by_model,
        "state_sha256_by_candidate": state_hashes,
    }
    return selection_row, candidate_score_rows, ticker_json


def select_initial_champion(
    prepared: PreparedDataset,
    labels: pd.DataFrame,
    initial_models: Mapping[str, Mapping[str, Any]],
    baselines: Mapping[str, Mapping[str, Any]],
    *,
    config: TrainingConfig | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Select the per-ETF Initial Champion (B0/B1/B2 only) at Validation->Test cutover."""
    effective_config = config or TrainingConfig.from_yaml()
    if effective_config.initial_champion is None:
        raise TrainingError(
            "initial_champion config is required; use training_config_version 1.2.0 or provide initial_champion"
        )
    ic_cfg = effective_config.initial_champion
    label_lookup = _validation_cutover_labels(labels, ic_cfg.cutover_date)
    selection_rows: list[dict[str, Any]] = []
    score_rows: list[dict[str, Any]] = []
    tickers_summary: dict[str, Any] = {}
    for ticker in SUPPORTED_TICKERS:
        if ticker not in initial_models or ticker not in baselines:
            raise TrainingError(f"missing Stage 04 initial model or baseline entry for {ticker}")
        sel_row, ticker_scores, ticker_json = _select_ticker_initial_champion(
            prepared,
            label_lookup,
            ticker,
            initial_models[ticker],
            baselines[ticker],
            effective_config,
            ic_cfg,
        )
        selection_rows.append(sel_row)
        score_rows.extend(ticker_scores)
        tickers_summary[ticker] = ticker_json
    selection_df = pd.DataFrame(selection_rows).reset_index(drop=True)
    scores_df = pd.DataFrame(score_rows).reset_index(drop=True)
    summary = {
        "policy_version": ic_cfg.policy_version,
        "training_config_version": effective_config.training_config_version,
        "training_config_fingerprint": effective_config.fingerprint(),
        "initial_champion_config_fingerprint": ic_cfg.fingerprint(),
        "scoring_split": ic_cfg.scoring_split,
        "cutover_date": ic_cfg.cutover_date.isoformat(),
        "cutover_maturity_rule": ic_cfg.cutover_maturity_rule,
        "candidate_models": list(ic_cfg.candidate_models),
        "excluded_models": ["B3", "B4"],
        "tie_break_order": list(ic_cfg.tie_break_order),
        "tie_tolerance": ic_cfg.tie_tolerance,
        "test_used_for_initial_champion": False,
        "selected_by_ticker": {
            ticker: tickers_summary[ticker]["selected_model_id"] for ticker in SUPPORTED_TICKERS
        },
        "tickers": tickers_summary,
    }
    return selection_df, scores_df, summary


def _result_row(run: CandidateRun) -> dict[str, Any]:
    return {
        "ticker": run.ticker,
        **run.candidate.as_dict(),
        "grid_order": run.grid_order,
        "mae_b2_validation": run.b2_mae,
        "mae_b3_validation": run.b3_mae,
        "joint_mae_validation": run.joint_mae,
        "expected_anchor_count": run.expected_anchor_count,
        "b2_valid_count": run.b2_valid_count,
        "b3_valid_count": run.b3_valid_count,
        "paired_anchor_count": run.paired_anchor_count,
        "paired_coverage": run.paired_coverage,
        "b2_invalid_count": run.b2_invalid_count,
        "b3_invalid_count": run.b3_invalid_count,
        "admissible": run.admissible,
        "failure_reason": run.failure_reason,
        "initial_state_sha256": run.initial_state_sha256,
        "b2_state_unchanged": run.final_b2_state_sha256 == run.initial_state_sha256,
        "duplicate_update_count": run.duplicate_update_count,
        "b3_update_count": len(run.updated_label_keys),
    }


def _select_configs(candidate_rows: pd.DataFrame, config: TrainingConfig) -> pd.DataFrame:
    selected: list[dict[str, Any]] = []
    for ticker in SUPPORTED_TICKERS:
        ticker_rows = candidate_rows.loc[candidate_rows["ticker"] == ticker]
        admissible = ticker_rows.loc[ticker_rows["admissible"]].copy()
        if admissible.empty:
            raise TrainingError(
                f"{ticker} has no candidate with complete paired Validation coverage"
            )
        minimum = float(admissible["joint_mae_validation"].min())
        tied = admissible.loc[
            (admissible["joint_mae_validation"] - minimum).abs() <= config.tie_tolerance
        ].sort_values("grid_order", kind="stable")
        selected.append(tied.iloc[0].to_dict())
    return pd.DataFrame(selected).reset_index(drop=True)


def _package_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for package in ("scikit-learn", "numpy", "pandas", "pandas-market-calendars", "joblib"):
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            versions[package] = None
    return versions


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )


def _persist_artifacts(
    artifact_dir: Path,
    candidate_rows: pd.DataFrame,
    selected_rows: pd.DataFrame,
    initial_models: dict[str, dict[str, Any]],
    baselines: dict[str, dict[str, Any]],
    config: TrainingConfig,
    source_lineage: Mapping[str, Any],
    source_limitations: Iterable[str],
    *,
    selection_status: str = "selected",
    selection_failures: Iterable[str] = (),
    b4_models: dict[str, dict[str, Any]] | None = None,
    b4_validation_rows: pd.DataFrame | None = None,
    b4_validation_summary: list[dict[str, Any]] | None = None,
    initial_champion_scores: pd.DataFrame | None = None,
    initial_champion_summary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    target = artifact_dir.expanduser().resolve()
    if target.exists():
        raise FileExistsError(f"training artifact directory already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{target.name}.stage04-", dir=target.parent)).resolve()
    if stage.parent != target.parent:
        raise TrainingError("temporary artifact directory escaped the requested output parent")
    try:
        candidate_path = stage / "validation_candidate_evaluations.csv"
        selected_path = stage / "selected_configs.json"
        models_path = stage / "initial_models.joblib"
        config_path = stage / "training_config.json"
        manifest_path = stage / "training_manifest.json"
        candidate_rows.to_csv(candidate_path, index=False, float_format="%.17g")
        _write_json(
            selected_path,
            selected_rows.drop(columns=["grid_order"], errors="ignore").to_dict("records"),
        )
        _write_json(config_path, config.as_dict())
        bundle_payload: dict[str, Any] = {
            "bundle_version": "1.0.0",
            "tickers": initial_models,
            "baselines": baselines,
        }
        if b4_models is not None:
            bundle_payload["b4_models"] = b4_models
        joblib.dump(
            bundle_payload,
            models_path,
            compress=3,
        )
        hashed_paths = [candidate_path, selected_path, models_path, config_path]
        if b4_validation_rows is not None and not b4_validation_rows.empty:
            b4_val_path = stage / "b4_validation_evaluations.csv"
            b4_validation_rows.to_csv(b4_val_path, index=False, float_format="%.17g")
            hashed_paths.append(b4_val_path)
        if initial_champion_summary is not None and initial_champion_scores is not None:
            ic_sel_path = stage / "initial_champion_selection.json"
            ic_scores_path = stage / "initial_champion_validation_scores.csv"
            _write_json(ic_sel_path, dict(initial_champion_summary))
            initial_champion_scores.to_csv(ic_scores_path, index=False, float_format="%.17g")
            hashed_paths.extend([ic_sel_path, ic_scores_path])
        artifact_hashes = {
            path.name: _sha256(path)
            for path in hashed_paths
        }
        b4_manifest_metadata: dict[str, Any] = {}
        if b4_models:
            for ticker, entry in b4_models.items():
                b4_manifest_metadata[ticker] = {
                    "model_id": entry["model_id"],
                    "model_name": entry["model_name"],
                    "model_version": entry["model_version"],
                    "intercept": entry["intercept"],
                    "coefficients": entry["coefficients"],
                    "feature_order": list(entry["feature_order"]),
                    "scaler_state_sha256": entry["scaler_state_sha256"],
                    "state_sha256": entry["state_sha256"],
                    "train_keys_count": entry["train_keys_count"],
                    "train_keys_fingerprint": entry["train_keys_fingerprint"],
                    "train_cutoff": entry["train_cutoff"].isoformat(),
                    "last_training_target_end_date": entry["last_training_target_end_date"].isoformat(),
                    "design_rank": entry["design_rank"],
                    "condition_number": entry["condition_number"],
                    "ill_conditioned": entry["ill_conditioned"],
                    "warnings": list(entry["warnings"]),
                }
        manifest = {
            "stage": "04_models_training_and_validation",
            "training_run_id": str(uuid.uuid4()),
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "training_config_version": config.training_config_version,
            "training_config_fingerprint": config.fingerprint(),
            "dataset_config": config.dataset.as_dict(),
            "feature_order": list(config.core_features),
            "selection_split": "validation",
            "selection_objective": "(mae_b2_validation + mae_b3_validation) / 2",
            "selection_status": selection_status,
            "selection_failures": list(selection_failures),
            "test_used_for_training_or_selection": False,
            "point_in_time_source_availability_verified": False,
            "limitations": list(source_limitations),
            "selected_configs": selected_rows.drop(columns=["grid_order"], errors="ignore").to_dict(
                "records"
            ),
            "initial_state_sha256_by_ticker": {
                ticker: pair["state_sha256"] for ticker, pair in initial_models.items()
            },
            "baselines": baselines,
            "b4_models": b4_manifest_metadata,
            "b4_validation": list(b4_validation_summary or []),
            "source_lineage": dict(source_lineage),
            "versions": _package_versions(),
            "artifact_sha256": artifact_hashes,
            "artifacts_are_validation_trials_not_final_replay": True,
        }
        if initial_champion_summary is not None:
            manifest["initial_champion"] = dict(initial_champion_summary)
        _write_json(manifest_path, manifest)
        stage.replace(target)
        return manifest
    except Exception:
        if stage.exists() and stage.parent == target.parent:
            shutil.rmtree(stage)
        raise


def run_training_selection(
    prepared: PreparedDataset,
    labels: pd.DataFrame,
    *,
    config: TrainingConfig | None = None,
    artifact_dir: str | Path | None = None,
    include_b4: bool = True,
) -> TrainingSelectionResult:
    """Run the locked 81-candidate Validation search and save clean initial model pairs."""
    effective_config = config or TrainingConfig.from_yaml()
    if include_b4:
        _require_b4_training_config(effective_config)
    if len(effective_config.grid) != 27:
        raise TrainingError("Stage 04 must evaluate exactly 27 candidates per ETF")
    runs: list[CandidateRun] = []
    for ticker in SUPPORTED_TICKERS:
        for candidate in effective_config.grid:
            runs.append(
                evaluate_candidate(
                    prepared,
                    labels,
                    ticker=ticker,
                    candidate=candidate,
                    config=effective_config,
                )
            )
    candidate_rows = pd.DataFrame([_result_row(run) for run in runs])
    lineage = dict(prepared.report.lineage)
    try:
        selected_rows = _select_configs(candidate_rows, effective_config)
    except TrainingError as error:
        if artifact_dir is not None:
            _persist_artifacts(
                Path(artifact_dir),
                candidate_rows,
                pd.DataFrame(),
                {},
                {},
                effective_config,
                lineage,
                prepared.report.limitations,
                selection_status="failed_no_admissible_candidate",
                selection_failures=[str(error)],
            )
            raise TrainingError(
                f"{error}; 81-candidate Validation audit saved to {Path(artifact_dir).resolve()}"
            ) from error
        raise

    initial_models: dict[str, dict[str, Any]] = {}
    baselines: dict[str, dict[str, Any]] = {}
    b4_models: dict[str, dict[str, Any]] = {}
    b4_validation_summaries: list[dict[str, Any]] = []
    b4_validation_frames: list[pd.DataFrame] = []
    for ticker in SUPPORTED_TICKERS:
        train_X, train_y, _, _ = _training_rows(prepared, ticker, effective_config)
        selected = selected_rows.loc[selected_rows["ticker"] == ticker].iloc[0]
        selected_candidate = CandidateConfig(
            eta0=float(selected["eta0"]),
            alpha=float(selected["alpha"]),
            max_iter=int(selected["max_iter"]),
        )
        clean_pair = _fit_initial_pair(train_X, train_y, selected_candidate, effective_config)
        if clean_pair["state_sha256"] != selected["initial_state_sha256"]:
            raise TrainingError(
                f"{ticker} clean selected re-fit does not match its Validation trial initial state"
            )
        initial_models[ticker] = {
            **clean_pair,
            "selected_candidate": selected_candidate.as_dict(),
            "train_cutoff": effective_config.dataset.train_end_date,
            "feature_order": tuple(effective_config.core_features),
        }
        if include_b4:
            b4_artifact = fit_b4_ols(
                prepared,
                ticker,
                effective_config,
                b2_scaler=clean_pair["scaler"],
            )
            b4_summary, b4_val_df = evaluate_b4_validation(
                prepared,
                ticker,
                b4_artifact,
                effective_config,
            )
            b4_models[ticker] = b4_artifact
            b4_validation_summaries.append(b4_summary)
            b4_validation_frames.append(b4_val_df)
        train_metadata = prepared.supervised.metadata
        train_mask = (train_metadata["split"] == "train") & (
            train_metadata["ticker"].astype(str) == ticker
        )
        # B0 is a frozen Train-only statistic. B1 reads the same-day rv_20d input directly.
        baselines[ticker] = {
            "b0_model_id": "B0",
            "b0_model_name": "CONSTANT_BASELINE",
            "b0_train_mean": float(train_y.mean()),
            "b0_train_row_count": int(train_mask.sum()),
            "b0_train_end_date": effective_config.dataset.train_end_date.isoformat(),
            "b1_model_id": "B1",
            "b1_model_name": "ROLLING_20D_BASELINE",
            "b1_feature": "rv_20d",
            "b1_strategy": "feature_value",
        }

    b4_validation_all = (
        pd.concat(b4_validation_frames, ignore_index=True)
        if b4_validation_frames
        else pd.DataFrame()
    )
    initial_champions_df: pd.DataFrame | None = None
    initial_champion_scores_df: pd.DataFrame | None = None
    initial_champion_summary: dict[str, Any] | None = None
    if effective_config.initial_champion is not None:
        (
            initial_champions_df,
            initial_champion_scores_df,
            initial_champion_summary,
        ) = select_initial_champion(
            prepared,
            labels,
            initial_models,
            baselines,
            config=effective_config,
        )

    manifest: dict[str, Any] = {
        "stage": "04_models_training_and_validation",
        "training_config_version": effective_config.training_config_version,
        "training_config_fingerprint": effective_config.fingerprint(),
        "selection_split": "validation",
        "selection_objective": "(mae_b2_validation + mae_b3_validation) / 2",
        "test_used_for_training_or_selection": False,
        "point_in_time_source_availability_verified": False,
        "limitations": list(prepared.report.limitations),
        "candidate_count_total": int(len(candidate_rows)),
        "candidate_count_per_ticker": int(len(effective_config.grid)),
        "b4_validation": b4_validation_summaries,
        "source_lineage": lineage,
        "versions": _package_versions(),
    }
    if initial_champion_summary is not None:
        manifest["initial_champion"] = dict(initial_champion_summary)
    persisted_dir: Path | None = None
    if artifact_dir is not None:
        persisted_dir = Path(artifact_dir).expanduser().resolve()
        manifest = _persist_artifacts(
            persisted_dir,
            candidate_rows,
            selected_rows,
            initial_models,
            baselines,
            effective_config,
            lineage,
            prepared.report.limitations,
            selection_status="selected",
            b4_models=b4_models if include_b4 else None,
            b4_validation_rows=b4_validation_all if include_b4 else None,
            b4_validation_summary=b4_validation_summaries if include_b4 else None,
            initial_champion_scores=initial_champion_scores_df,
            initial_champion_summary=initial_champion_summary,
        )
    return TrainingSelectionResult(
        candidate_evaluations=candidate_rows,
        selected_configs=selected_rows.drop(columns=["grid_order"], errors="ignore").reset_index(
            drop=True
        ),
        initial_models=initial_models,
        baselines=baselines,
        manifest=manifest,
        artifact_dir=persisted_dir,
        b4_models=b4_models if include_b4 else None,
        b4_validation=b4_validation_all if include_b4 else None,
        initial_champions=initial_champions_df,
        initial_champion_scores=initial_champion_scores_df,
    )
