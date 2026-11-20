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
from sklearn.linear_model import SGDRegressor
from sklearn.preprocessing import RobustScaler

from src.features.pipeline import CORE_FEATURE_COLUMNS, SUPPORTED_TICKERS
from src.ml_dataset.dataset import PreparedDataset
from src.ml_training.config import CandidateConfig, TrainingConfig, TrainingError


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
        joblib.dump(
            {
                "bundle_version": "1.0.0",
                "tickers": initial_models,
                "baselines": baselines,
            },
            models_path,
            compress=3,
        )
        artifact_hashes = {
            path.name: _sha256(path)
            for path in (candidate_path, selected_path, models_path, config_path)
        }
        manifest = {
            "stage": "04_models_training_and_validation",
            "training_run_id": str(uuid.uuid4()),
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "training_config_version": config.training_config_version,
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
            "source_lineage": dict(source_lineage),
            "versions": _package_versions(),
            "artifact_sha256": artifact_hashes,
            "artifacts_are_validation_trials_not_final_replay": True,
        }
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
) -> TrainingSelectionResult:
    """Run the locked 81-candidate Validation search and save clean initial model pairs."""
    effective_config = config or TrainingConfig.from_yaml()
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

    manifest: dict[str, Any] = {
        "stage": "04_models_training_and_validation",
        "training_config_version": effective_config.training_config_version,
        "selection_split": "validation",
        "selection_objective": "(mae_b2_validation + mae_b3_validation) / 2",
        "test_used_for_training_or_selection": False,
        "point_in_time_source_availability_verified": False,
        "limitations": list(prepared.report.limitations),
        "candidate_count_total": int(len(candidate_rows)),
        "candidate_count_per_ticker": int(len(effective_config.grid)),
        "source_lineage": lineage,
        "versions": _package_versions(),
    }
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
    )
