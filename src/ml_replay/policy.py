from __future__ import annotations

import math
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd
from river.drift import ADWIN
from sklearn.linear_model import SGDRegressor
from sklearn.preprocessing import RobustScaler

from src.features.pipeline import CORE_FEATURE_COLUMNS, SUPPORTED_TICKERS
from src.ml_dataset.dataset import DatasetConfig
from src.ml_replay.config import (
    ChampionChallengerPolicyConfig,
    ReplayConfig,
    ReplayError,
)
from src.ml_replay.storage import canonical_json, read_json, sha256_bytes, sha256_file
from src.ml_training.config import TRAINING_CONFIG_VERSION
from src.ml_training.pipeline import model_state_sha256, scaler_state_sha256


BASELINE_CHECKPOINT_VERSION = "1.1.0"
POLICY_CHECKPOINT_VERSION = "2.2.0"
POLICY_MODEL_NAMES = {
    "B0": "CONSTANT_BASELINE",
    "B1": "ROLLING_20D_BASELINE",
    "B2": "STATIC_SGD",
    "B3": "ONLINE_SGD",
}
POLICY_FORECAST_COLUMNS = [
    "experiment_id",
    "policy_version",
    "policy_prediction_id",
    "prediction_date",
    "split",
    "ticker",
    "role",
    "champion_version_id",
    "model_id",
    "model_name",
    "is_frozen_snapshot",
    "model_version",
    "state_sha256",
    "prediction_mode",
    "forecast_horizon_trading_days",
    "target_start_date",
    "target_end_date",
    "predicted_vol_annualized",
    "feature_set_version",
    "feature_run_id",
    "input_snapshot_id",
    "last_training_target_end_date",
    "champion_effective_from_date",
    "run_id",
    "prediction_created_at_utc",
]
POLICY_EVALUATION_COLUMNS = [
    "experiment_id",
    "policy_version",
    "policy_prediction_id",
    "prediction_date",
    "split",
    "ticker",
    "role",
    "champion_version_id",
    "active_champion_version_id_at_eval",
    "model_id",
    "model_name",
    "is_frozen_snapshot",
    "model_version",
    "state_sha256",
    "target_start_date",
    "target_end_date",
    "predicted_vol_annualized",
    "target_realized_vol_5d",
    "target_version",
    "absolute_error",
    "squared_error",
    "evaluation_date",
    "label_available_replay_date",
    "stale_champion_skipped_from_policy",
    "policy_skip_reason",
    "prediction_run_id",
    "evaluation_run_id",
]
POLICY_DETECTOR_COLUMNS = [
    "experiment_id",
    "policy_version",
    "policy_prediction_id",
    "prediction_date",
    "evaluation_date",
    "ticker",
    "champion_version_id",
    "champion_model_id",
    "champion_state_sha256",
    "feed_order_in_session",
    "absolute_error",
    "adwin_delta",
    "adwin_width",
    "adwin_estimation_before",
    "adwin_estimation",
    "drift_detected",
    "drift_direction",
    "triggered_decision",
    "cooldown_active",
    "cooldown_remaining_before",
    "prediction_run_id",
    "evaluation_run_id",
]
POLICY_DECISION_COLUMNS = [
    "experiment_id",
    "policy_version",
    "event_id",
    "decision_date",
    "ticker",
    "trigger_prediction_id",
    "trigger_prediction_date",
    "drift_direction",
    "adwin_estimation_before",
    "adwin_estimation_after",
    "adwin_width",
    "champion_version_id_before",
    "champion_model_id_before",
    "champion_state_sha256_before",
    "shadow_model_id",
    "shadow_state_sha256_pre_update",
    "comparison_window_pairs",
    "minimum_pairs",
    "min_relative_improvement",
    "valid_pair_count",
    "champion_window_mae",
    "shadow_b3_window_mae",
    "relative_improvement",
    "decision_outcome",
    "decision_reason",
    "switched",
    "champion_version_id_after",
    "champion_model_id_after",
    "champion_state_sha256_after",
    "effective_from_date",
    "rollback_target_version_id",
    "rollback_target_model_id",
    "rollback_target_state_sha256",
    "cooldown_active",
    "cooldown_remaining_before",
    "cooldown_remaining_after",
    "detector_reset_after_decision",
    "run_id",
]
POLICY_TIMELINE_COLUMNS = [
    "experiment_id",
    "policy_version",
    "timeline_event_id",
    "event_type",
    "recorded_date",
    "decision_date",
    "effective_from_date",
    "ticker",
    "version_seq",
    "from_champion_version_id",
    "from_model_id",
    "from_state_sha256",
    "to_champion_version_id",
    "to_model_id",
    "to_state_sha256",
    "rollback_target_version_id",
    "rollback_target_model_id",
    "rollback_target_state_sha256",
    "decision_event_id",
    "reason",
    "run_id",
]
POLICY_FAILURE_COLUMNS = [
    "experiment_id",
    "policy_version",
    "prediction_date",
    "split",
    "ticker",
    "role",
    "champion_version_id",
    "model_id",
    "model_name",
    "failure_type",
    "reason",
    "raw_value",
    "run_id",
]
POLICY_TABLE_SPECS: dict[str, tuple[str, list[str]]] = {
    "policy_forecasts.csv": ("policy_forecasts.csv", POLICY_FORECAST_COLUMNS),
    "policy_evaluations.csv": ("policy_evaluations.csv", POLICY_EVALUATION_COLUMNS),
    "policy_detector_stream.csv": ("policy_detector_stream.csv", POLICY_DETECTOR_COLUMNS),
    "policy_decision_events.csv": ("policy_decision_events.csv", POLICY_DECISION_COLUMNS),
    "policy_champion_timeline.csv": ("policy_champion_timeline.csv", POLICY_TIMELINE_COLUMNS),
    "policy_failures.csv": ("policy_failures.csv", POLICY_FAILURE_COLUMNS),
}


@dataclass
class PolicyRuntimeState:
    shadow_b3_models: dict[str, SGDRegressor]
    shadow_scalers: dict[str, RobustScaler]
    shadow_last_target_end_by_ticker: dict[str, date]
    active_champion: dict[str, dict[str, Any]]
    policy_adwin: dict[str, ADWIN]
    pending_forecasts: list[dict[str, Any]]
    evaluated_prediction_ids: set[str]
    processed_error_ids: set[str]
    emitted_event_ids: set[str]
    paired_history: dict[str, list[dict[str, Any]]]
    comparison_failures: list[dict[str, Any]]
    cooldown_remaining: dict[str, int]
    version_seq_by_ticker: dict[str, int]
    initial_timeline_recorded: bool = False


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


def _stable_id(value: Any) -> str:
    return sha256_bytes(canonical_json(value).encode("utf-8"))


def _valid_forecast(value: Any) -> bool:
    try:
        return bool(math.isfinite(float(value)) and float(value) >= 0)
    except (TypeError, ValueError, OverflowError):
        return False


def _feature_frame(values: np.ndarray) -> pd.DataFrame:
    return pd.DataFrame([np.asarray(values, dtype=float)], columns=list(CORE_FEATURE_COLUMNS))


def _is_true(value: Any) -> bool:
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    return bool(value)


def _baseline_candidate_hash(
    ticker: str,
    model_id: str,
    baseline_entry: Mapping[str, Any],
) -> str:
    if model_id == "B0":
        payload = {
            "model_id": "B0",
            "model_name": POLICY_MODEL_NAMES["B0"],
            "ticker": ticker,
            "b0_train_mean": float(baseline_entry["b0_train_mean"]),
            "b0_train_end_date": str(baseline_entry["b0_train_end_date"]),
        }
        return _stable_id(payload)
    if model_id == "B1":
        payload = {
            "model_id": "B1",
            "model_name": POLICY_MODEL_NAMES["B1"],
            "ticker": ticker,
            "b1_feature": str(baseline_entry["b1_feature"]),
            "b1_strategy": str(baseline_entry["b1_strategy"]),
        }
        return _stable_id(payload)
    raise ReplayError(f"unsupported baseline model id: {model_id}")


def _champion_version_id(
    ticker: str,
    version_seq: int,
    model_id: str,
    state_sha256: str,
) -> str:
    return f"{ticker}_v{version_seq:03d}_{model_id}_{state_sha256[:12]}"


def champion_entry_state_sha256(entry: Mapping[str, Any]) -> str:
    model_id = str(entry["model_id"])
    if model_id in {"B2", "B3"}:
        return model_state_sha256(entry["estimator"], entry["scaler"])
    if model_id == "B0":
        return _baseline_candidate_hash(
            str(entry["ticker"]),
            "B0",
            {
                "b0_train_mean": entry["b0_train_mean"],
                "b0_train_end_date": entry["b0_train_end_date"],
            },
        )
    if model_id == "B1":
        return _baseline_candidate_hash(
            str(entry["ticker"]),
            "B1",
            {
                "b1_feature": entry["b1_feature"],
                "b1_strategy": entry["b1_strategy"],
            },
        )
    raise ReplayError(f"unsupported champion model_id: {model_id}")


def load_initial_champion_artifact(
    artifact_dir: str | Path,
    training_manifest: Mapping[str, Any],
    initial_tickers: Mapping[str, Mapping[str, Any]],
    baselines: Mapping[str, Mapping[str, Any]],
    policy_cfg: ChampionChallengerPolicyConfig,
) -> tuple[dict[str, Any], dict[str, str]]:
    """Load and checksum-verify Stage 04 initial champion selection before policy replay."""
    directory = Path(artifact_dir).expanduser().resolve()
    if training_manifest.get("training_config_version") != TRAINING_CONFIG_VERSION:
        raise ReplayError(
            "Champion-Challenger replay requires Stage 04 artifact with "
            f"training_config_version {TRAINING_CONFIG_VERSION}"
        )
    artifact_hashes = training_manifest.get("artifact_sha256", {})
    required_files = (
        "initial_champion_selection.json",
        "initial_champion_validation_scores.csv",
    )
    file_hashes: dict[str, str] = {}
    for filename in required_files:
        path = directory / filename
        actual_hash = sha256_file(path) if path.is_file() else None
        expected_hash = artifact_hashes.get(filename)
        if not actual_hash or actual_hash != expected_hash:
            raise ReplayError(f"Stage 04 initial champion checksum is invalid: {filename}")
        file_hashes[filename] = actual_hash

    selection = read_json(
        directory / "initial_champion_selection.json",
        "Stage 04 initial champion selection",
    )
    if selection.get("policy_version") != policy_cfg.policy_version:
        raise ReplayError("Stage 04 initial champion policy_version does not match Stage 05 policy")
    if selection.get("test_used_for_initial_champion") is not False:
        raise ReplayError("Stage 04 initial champion selection must not use Test data")
    if selection.get("scoring_split") != "validation":
        raise ReplayError("Stage 04 initial champion selection must use Validation split only")
    if selection.get("cutover_date") != policy_cfg.activation_start_date.isoformat():
        raise ReplayError("Stage 04 cutover_date does not match Stage 05 activation_start_date")
    if list(selection.get("candidate_models", [])) != list(policy_cfg.candidate_order):
        raise ReplayError("Stage 04 candidate_models do not match Stage 05 candidate_order")

    tickers_info = selection.get("tickers", {})
    if set(tickers_info) != set(SUPPORTED_TICKERS):
        raise ReplayError("Stage 04 initial champion selection must include all supported ETFs")
    for ticker in SUPPORTED_TICKERS:
        t_info = tickers_info[ticker]
        selected_id = str(t_info.get("selected_model_id", ""))
        if selected_id not in policy_cfg.candidate_order:
            raise ReplayError(f"{ticker} selected initial champion {selected_id} is excluded")
        if int(t_info.get("paired_anchor_count", 0)) < 1 or float(t_info.get("paired_coverage", 0.0)) < 1.0:
            raise ReplayError(f"{ticker} Stage 04 initial champion has incomplete Validation coverage")
        expected_b2_hash = str(initial_tickers[ticker]["state_sha256"])
        if t_info.get("b2_equals_b3_initial_state_sha256") != expected_b2_hash:
            raise ReplayError(f"{ticker} B2=B3 initial state lineage does not match Stage 04 artifact")
        cand_hashes = t_info.get("state_sha256_by_candidate", {})
        expected_hash = (
            expected_b2_hash
            if selected_id == "B2"
            else _baseline_candidate_hash(ticker, selected_id, baselines[ticker])
        )
        if t_info.get("selected_model_state_sha256") != expected_hash or cand_hashes.get(selected_id) != expected_hash:
            raise ReplayError(f"{ticker} Stage 04 initial champion state hash mismatch for {selected_id}")

    return selection, {
        "initial_champion_selection_sha256": file_hashes["initial_champion_selection.json"],
        "initial_champion_scores_sha256": file_hashes["initial_champion_validation_scores.csv"],
    }


def _build_initial_active_champion_entry(
    ticker: str,
    selected_id: str,
    *,
    initial_tickers: Mapping[str, Mapping[str, Any]],
    baselines: Mapping[str, Mapping[str, Any]],
    initial_train_ends: Mapping[str, date],
    activation_start_date: date,
) -> dict[str, Any]:
    if selected_id == "B2":
        est = deepcopy(initial_tickers[ticker]["b2"])
        scaler = deepcopy(initial_tickers[ticker]["scaler"])
        state_hash = model_state_sha256(est, scaler)
        last_train_end: date | None = initial_train_ends[ticker]
    elif selected_id == "B0":
        est = None
        scaler = None
        state_hash = _baseline_candidate_hash(ticker, "B0", baselines[ticker])
        last_train_end = initial_train_ends[ticker]
    elif selected_id == "B1":
        est = None
        scaler = None
        state_hash = _baseline_candidate_hash(ticker, "B1", baselines[ticker])
        last_train_end = None
    else:
        raise ReplayError(f"unsupported initial champion id for {ticker}: {selected_id}")

    version_id = _champion_version_id(ticker, 1, selected_id, state_hash)
    entry: dict[str, Any] = {
        "ticker": ticker,
        "champion_version_id": version_id,
        "version_seq": 1,
        "model_id": selected_id,
        "model_name": POLICY_MODEL_NAMES[selected_id],
        "is_frozen_snapshot": True,
        "state_sha256": state_hash,
        "estimator": est,
        "scaler": scaler,
        "b0_train_mean": float(baselines[ticker]["b0_train_mean"]),
        "b0_train_end_date": str(baselines[ticker]["b0_train_end_date"]),
        "b1_feature": str(baselines[ticker]["b1_feature"]),
        "b1_strategy": str(baselines[ticker]["b1_strategy"]),
        "last_training_target_end_date": last_train_end,
        "effective_from_date": activation_start_date,
        "rollback_target_version_id": None,
        "rollback_target_model_id": None,
        "rollback_target_state_sha256": None,
    }
    if champion_entry_state_sha256(entry) != state_hash:
        raise ReplayError(f"{ticker} constructed active champion state hash mismatch")
    return entry


def new_policy_runtime_state(
    initial_tickers: Mapping[str, Mapping[str, Any]],
    baselines: Mapping[str, Mapping[str, Any]],
    initial_train_ends: Mapping[str, date],
    initial_champion_selection: Mapping[str, Any],
    policy_cfg: ChampionChallengerPolicyConfig,
) -> PolicyRuntimeState:
    selected_by_ticker = initial_champion_selection["selected_by_ticker"]
    active = {
        ticker: _build_initial_active_champion_entry(
            ticker,
            str(selected_by_ticker[ticker]),
            initial_tickers=initial_tickers,
            baselines=baselines,
            initial_train_ends=initial_train_ends,
            activation_start_date=policy_cfg.activation_start_date,
        )
        for ticker in SUPPORTED_TICKERS
    }
    return PolicyRuntimeState(
        shadow_b3_models={ticker: deepcopy(initial_tickers[ticker]["b3"]) for ticker in SUPPORTED_TICKERS},
        shadow_scalers={ticker: deepcopy(initial_tickers[ticker]["scaler"]) for ticker in SUPPORTED_TICKERS},
        shadow_last_target_end_by_ticker=dict(initial_train_ends),
        active_champion=active,
        policy_adwin={ticker: ADWIN(delta=policy_cfg.adwin_delta) for ticker in SUPPORTED_TICKERS},
        pending_forecasts=[],
        evaluated_prediction_ids=set(),
        processed_error_ids=set(),
        emitted_event_ids=set(),
        paired_history={ticker: [] for ticker in SUPPORTED_TICKERS},
        comparison_failures=[],
        cooldown_remaining={ticker: 0 for ticker in SUPPORTED_TICKERS},
        version_seq_by_ticker={ticker: 1 for ticker in SUPPORTED_TICKERS},
        initial_timeline_recorded=False,
    )


def assert_policy_isolation(
    policy_state: PolicyRuntimeState,
    benchmark_b3_models: Mapping[str, Any],
    benchmark_scalers: Mapping[str, Any],
    initial_scalers: Mapping[str, Any],
) -> None:
    """Enforce memory isolation between benchmark B3, shadow B3, and frozen champion snapshots."""
    for ticker in SUPPORTED_TICKERS:
        bench_b3 = benchmark_b3_models[ticker]
        shadow_b3 = policy_state.shadow_b3_models[ticker]
        bench_scaler = benchmark_scalers[ticker]
        shadow_scaler = policy_state.shadow_scalers[ticker]
        if shadow_b3 is bench_b3 or np.shares_memory(shadow_b3.coef_, bench_b3.coef_):
            raise ReplayError(f"{ticker} shadow B3 aliases benchmark B3 mutable state")
        if scaler_state_sha256(shadow_scaler) != scaler_state_sha256(initial_scalers[ticker]):
            raise ReplayError(f"{ticker} shadow B3 RobustScaler mutated after Train")
        if model_state_sha256(shadow_b3, shadow_scaler) != model_state_sha256(bench_b3, bench_scaler):
            raise ReplayError(f"{ticker} shadow B3 drifted out of lockstep with benchmark B3")

        champ = policy_state.active_champion[ticker]
        champ_est = champ.get("estimator")
        if champ_est is not None:
            if (
                champ_est is shadow_b3
                or champ_est is bench_b3
                or np.shares_memory(champ_est.coef_, shadow_b3.coef_)
                or np.shares_memory(champ_est.coef_, bench_b3.coef_)
            ):
                raise ReplayError(f"{ticker} frozen champion snapshot aliases mutable B3 state")
            if scaler_state_sha256(champ["scaler"]) != scaler_state_sha256(initial_scalers[ticker]):
                raise ReplayError(f"{ticker} champion RobustScaler mutated after Train")


def _predict_from_champion(entry: Mapping[str, Any], values: np.ndarray) -> float:
    model_id = str(entry["model_id"])
    if model_id == "B0":
        return float(entry["b0_train_mean"])
    if model_id == "B1":
        return float(values[tuple(CORE_FEATURE_COLUMNS).index(str(entry["b1_feature"]))])
    if model_id in {"B2", "B3"}:
        scaled = entry["scaler"].transform(_feature_frame(values))
        return float(entry["estimator"].predict(scaled)[0])
    raise ReplayError(f"unsupported champion model_id: {model_id}")


def run_policy_predict_session(
    policy_state: PolicyRuntimeState,
    *,
    session_date: date,
    policy_cfg: ChampionChallengerPolicyConfig,
    replay_config: ReplayConfig,
    experiment_id: str,
    run_id: str,
    input_snapshot_id: str,
    utc_now_fn: Any,
    feature_map: Mapping[tuple[date, str], np.ndarray],
    feature_metadata: Mapping[tuple[date, str], Mapping[str, Any]],
    calendar_index: Mapping[date, int],
    calendar_sessions: list[date],
    split_name: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    if session_date < policy_cfg.activation_start_date:
        return [], [], []

    session_forecasts: list[dict[str, Any]] = []
    session_failures: list[dict[str, Any]] = []
    session_timeline: list[dict[str, Any]] = []

    if not policy_state.initial_timeline_recorded:
        for ticker in SUPPORTED_TICKERS:
            champ = policy_state.active_champion[ticker]
            timeline_id = _stable_id(
                {
                    "experiment_id": experiment_id,
                    "event_type": "INITIAL_CHAMPION_CUTOVER",
                    "ticker": ticker,
                    "to_champion_version_id": champ["champion_version_id"],
                }
            )
            session_timeline.append(
                {
                    "experiment_id": experiment_id,
                    "policy_version": policy_cfg.policy_version,
                    "timeline_event_id": timeline_id,
                    "event_type": "INITIAL_CHAMPION_CUTOVER",
                    "recorded_date": session_date,
                    "decision_date": None,
                    "effective_from_date": champ["effective_from_date"],
                    "ticker": ticker,
                    "version_seq": int(champ["version_seq"]),
                    "from_champion_version_id": None,
                    "from_model_id": None,
                    "from_state_sha256": None,
                    "to_champion_version_id": champ["champion_version_id"],
                    "to_model_id": champ["model_id"],
                    "to_state_sha256": champ["state_sha256"],
                    "rollback_target_version_id": None,
                    "rollback_target_model_id": None,
                    "rollback_target_state_sha256": None,
                    "decision_event_id": None,
                    "reason": policy_cfg.initial_selection_source,
                    "run_id": run_id,
                }
            )
        policy_state.initial_timeline_recorded = True

    pos = calendar_index.get(session_date)
    if pos is None or pos + 5 >= len(calendar_sessions):
        raise ReplayError(f"could not resolve XNYS target window for policy session {session_date}")
    target_start, target_end = calendar_sessions[pos + 1], calendar_sessions[pos + 5]

    for ticker in SUPPORTED_TICKERS:
        champ = policy_state.active_champion[ticker]
        if champ["effective_from_date"] > session_date:
            raise ReplayError(
                f"{ticker} active champion {champ['champion_version_id']} effective_from_date "
                f"{champ['effective_from_date']} exceeds session {session_date}"
            )
        champ_version_id = str(champ["champion_version_id"])
        key = (session_date, ticker)
        values = feature_map.get(key)
        metadata = feature_metadata.get(key)
        if values is None or metadata is None:
            for role, m_id, m_name in (
                ("SERVED_CHAMPION", champ["model_id"], champ["model_name"]),
                ("SHADOW_B3", "B3", POLICY_MODEL_NAMES["B3"]),
            ):
                session_failures.append(
                    {
                        "experiment_id": experiment_id,
                        "policy_version": policy_cfg.policy_version,
                        "prediction_date": session_date,
                        "split": split_name,
                        "ticker": ticker,
                        "role": role,
                        "champion_version_id": champ_version_id,
                        "model_id": m_id,
                        "model_name": m_name,
                        "failure_type": "feature_unavailable",
                        "reason": "feature_row_missing_or_ineligible",
                        "raw_value": None,
                        "run_id": run_id,
                    }
                )
            continue

        shadow_model = policy_state.shadow_b3_models[ticker]
        shadow_scaler = policy_state.shadow_scalers[ticker]
        shadow_hash = model_state_sha256(shadow_model, shadow_scaler)
        feature_version = str(metadata["feature_set_version"])
        feature_run_id = str(metadata["feature_run_id"])

        roles = (
            (
                "SERVED_CHAMPION",
                str(champ["model_id"]),
                str(champ["model_name"]),
                True,
                champ_version_id,
                str(champ["state_sha256"]),
                champ["last_training_target_end_date"],
                lambda: _predict_from_champion(champ, values),
            ),
            (
                "SHADOW_B3",
                "B3",
                POLICY_MODEL_NAMES["B3"],
                False,
                shadow_hash,
                shadow_hash,
                policy_state.shadow_last_target_end_by_ticker[ticker],
                lambda: float(shadow_model.predict(shadow_scaler.transform(_feature_frame(values)))[0]),
            ),
        )
        for role, model_id, model_name, is_frozen, model_ver, state_hash, train_end, predictor in roles:
            raw_val: float | None = None
            try:
                raw_val = float(predictor())
            except Exception as error:
                session_failures.append(
                    {
                        "experiment_id": experiment_id,
                        "policy_version": policy_cfg.policy_version,
                        "prediction_date": session_date,
                        "split": split_name,
                        "ticker": ticker,
                        "role": role,
                        "champion_version_id": champ_version_id,
                        "model_id": model_id,
                        "model_name": model_name,
                        "failure_type": "prediction_error",
                        "reason": f"{type(error).__name__}: {error}",
                        "raw_value": raw_val,
                        "run_id": run_id,
                    }
                )
                continue

            if not _valid_forecast(raw_val):
                session_failures.append(
                    {
                        "experiment_id": experiment_id,
                        "policy_version": policy_cfg.policy_version,
                        "prediction_date": session_date,
                        "split": split_name,
                        "ticker": ticker,
                        "role": role,
                        "champion_version_id": champ_version_id,
                        "model_id": model_id,
                        "model_name": model_name,
                        "failure_type": "invalid_forecast",
                        "reason": "forecast must be finite and nonnegative; value was rejected without clipping",
                        "raw_value": raw_val if math.isfinite(raw_val) else None,
                        "run_id": run_id,
                    }
                )
                continue

            pred_id = _stable_id(
                {
                    "experiment_id": experiment_id,
                    "policy_version": policy_cfg.policy_version,
                    "prediction_date": session_date.isoformat(),
                    "ticker": ticker,
                    "role": role,
                    "champion_version_id": champ_version_id,
                    "model_version": model_ver,
                    "input_snapshot_id": input_snapshot_id,
                }
            )
            forecast_row = {
                "experiment_id": experiment_id,
                "policy_version": policy_cfg.policy_version,
                "policy_prediction_id": pred_id,
                "prediction_date": session_date,
                "split": split_name,
                "ticker": ticker,
                "role": role,
                "champion_version_id": champ_version_id,
                "model_id": model_id,
                "model_name": model_name,
                "is_frozen_snapshot": bool(is_frozen),
                "model_version": model_ver,
                "state_sha256": state_hash,
                "prediction_mode": replay_config.prediction_mode,
                "forecast_horizon_trading_days": replay_config.forecast_horizon_trading_days,
                "target_start_date": target_start,
                "target_end_date": target_end,
                "predicted_vol_annualized": float(raw_val),
                "feature_set_version": feature_version,
                "feature_run_id": feature_run_id,
                "input_snapshot_id": input_snapshot_id,
                "last_training_target_end_date": train_end,
                "champion_effective_from_date": champ["effective_from_date"],
                "run_id": run_id,
                "prediction_created_at_utc": utc_now_fn(),
            }
            session_forecasts.append(forecast_row)

    for failure in session_failures:
        policy_state.comparison_failures.append({
            "prediction_date": session_date,
            "target_end_date": target_end,
            "ticker": failure["ticker"],
            "champion_version_id": failure["champion_version_id"],
            "reason": failure["failure_type"],
        })
    existing_pending_ids = {row["policy_prediction_id"] for row in policy_state.pending_forecasts}
    if any(row["policy_prediction_id"] in existing_pending_ids for row in session_forecasts):
        raise ReplayError(f"duplicate policy predictions reached session {session_date}")
    policy_state.pending_forecasts.extend(session_forecasts)
    return session_forecasts, session_failures, session_timeline


def _validate_policy_label(
    forecast: Mapping[str, Any],
    *,
    session_date: date,
    label_map: Mapping[tuple[date, str], Mapping[str, Any]],
    audit_map: Mapping[tuple[date, str], Mapping[str, Any]],
) -> tuple[bool, float | None, str | None, str]:
    anchor = _as_date(forecast["prediction_date"], "policy prediction_date")
    target_end = _as_date(forecast["target_end_date"], "policy target_end_date")
    if target_end > session_date:
        return True, None, None, ""
    key = (anchor, str(forecast["ticker"]))
    label = label_map.get(key)
    audit = audit_map.get(key, {})
    if label is None:
        return False, None, "label_missing_when_target_window_matured", ""
    label_target_end = _as_date(label.get("target_end_date"), "label target_end_date")
    if label_target_end > session_date:
        return True, None, None, ""
    label_start = _as_date(label.get("target_start_date"), "label target_start_date")
    if label_start != _as_date(forecast["target_start_date"], "policy target_start_date") or label_target_end != target_end:
        return False, None, "label_target_window_mismatch", ""
    try:
        observation_count = int(label.get("target_obs_count", 0))
    except (TypeError, ValueError, OverflowError):
        observation_count = 0
    if not _is_true(label.get("is_label_mature")) or observation_count != 5:
        return False, None, "label_not_mature_or_observation_count_not_five", ""
    if not _is_true(audit.get("label_quality_passed")):
        return False, None, "label_quality_failed", ""
    try:
        target_value = float(label.get("target_realized_vol_5d"))
    except (TypeError, ValueError, OverflowError):
        return False, None, "label_value_invalid", ""
    if not math.isfinite(target_value) or target_value < 0:
        return False, None, "label_value_invalid", ""
    return False, target_value, None, str(label.get("target_version", ""))


def run_policy_evaluate_and_decide(
    policy_state: PolicyRuntimeState,
    *,
    session_date: date,
    policy_cfg: ChampionChallengerPolicyConfig,
    experiment_id: str,
    run_id: str,
    label_map: Mapping[tuple[date, str], Mapping[str, Any]],
    audit_map: Mapping[tuple[date, str], Mapping[str, Any]],
    calendar_index: Mapping[date, int],
    calendar_sessions: list[date],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    if session_date < policy_cfg.activation_start_date:
        return [], [], [], [], []

    session_evaluations: list[dict[str, Any]] = []
    session_detector_stream: list[dict[str, Any]] = []
    session_decisions: list[dict[str, Any]] = []
    session_timeline: list[dict[str, Any]] = []
    session_failures: list[dict[str, Any]] = []

    active_ver_at_eval = {
        ticker: str(policy_state.active_champion[ticker]["champion_version_id"])
        for ticker in SUPPORTED_TICKERS
    }
    remaining_pending: list[dict[str, Any]] = []
    matured_by_anchor_ticker: dict[tuple[date, str], dict[str, dict[str, Any]]] = {}
    active_served_by_ticker: dict[str, list[dict[str, Any]]] = {t: [] for t in SUPPORTED_TICKERS}

    for forecast in sorted(
        policy_state.pending_forecasts,
        key=lambda item: (item["prediction_date"], str(item["ticker"]), str(item["role"]), str(item["policy_prediction_id"])),
    ):
        pred_id = str(forecast["policy_prediction_id"])
        if pred_id in policy_state.evaluated_prediction_ids:
            continue
        anchor = _as_date(forecast["prediction_date"], "policy prediction_date")
        ticker = str(forecast["ticker"])
        still_pending, target_value, reason, target_version = _validate_policy_label(
            forecast,
            session_date=session_date,
            label_map=label_map,
            audit_map=audit_map,
        )
        if still_pending:
            remaining_pending.append(forecast)
            continue
        if reason is not None or target_value is None:
            session_failures.append(
                {
                    "experiment_id": experiment_id,
                    "policy_version": policy_cfg.policy_version,
                    "prediction_date": anchor,
                    "split": str(forecast["split"]),
                    "ticker": ticker,
                    "role": str(forecast["role"]),
                    "champion_version_id": str(forecast["champion_version_id"]),
                    "model_id": str(forecast["model_id"]),
                    "model_name": str(forecast["model_name"]),
                    "failure_type": "evaluation_label_unavailable",
                    "reason": reason or "label_unavailable",
                    "raw_value": None,
                    "run_id": run_id,
                }
            )
            policy_state.comparison_failures.append({
                "prediction_date": anchor,
                "target_end_date": _as_date(forecast["target_end_date"], "policy target_end_date"),
                "ticker": ticker,
                "champion_version_id": str(forecast["champion_version_id"]),
                "reason": "evaluation_label_unavailable",
            })
            policy_state.evaluated_prediction_ids.add(pred_id)
            continue

        pred_val = float(forecast["predicted_vol_annualized"])
        abs_err = abs(pred_val - target_value)
        forecast_ver = str(forecast["champion_version_id"])
        current_ver = active_ver_at_eval[ticker]
        is_stale_champion = forecast_ver != current_ver
        skip_reason = "matured_under_newer_champion_version" if is_stale_champion else None

        eval_row = {
            "experiment_id": experiment_id,
            "policy_version": policy_cfg.policy_version,
            "policy_prediction_id": pred_id,
            "prediction_date": anchor,
            "split": str(forecast["split"]),
            "ticker": ticker,
            "role": str(forecast["role"]),
            "champion_version_id": forecast_ver,
            "active_champion_version_id_at_eval": current_ver,
            "model_id": str(forecast["model_id"]),
            "model_name": str(forecast["model_name"]),
            "is_frozen_snapshot": bool(forecast["is_frozen_snapshot"]),
            "model_version": str(forecast["model_version"]),
            "state_sha256": str(forecast["state_sha256"]),
            "target_start_date": _as_date(forecast["target_start_date"], "target_start_date"),
            "target_end_date": _as_date(forecast["target_end_date"], "target_end_date"),
            "predicted_vol_annualized": pred_val,
            "target_realized_vol_5d": target_value,
            "target_version": target_version,
            "absolute_error": abs_err,
            "squared_error": abs_err**2,
            "evaluation_date": session_date,
            "label_available_replay_date": session_date,
            "stale_champion_skipped_from_policy": bool(is_stale_champion),
            "policy_skip_reason": skip_reason,
            "prediction_run_id": str(forecast["run_id"]),
            "evaluation_run_id": run_id,
        }
        session_evaluations.append(eval_row)
        policy_state.evaluated_prediction_ids.add(pred_id)

        if not is_stale_champion:
            matured_by_anchor_ticker.setdefault((anchor, ticker), {})[str(forecast["role"])] = eval_row
            if str(forecast["role"]) == "SERVED_CHAMPION":
                active_served_by_ticker[ticker].append(eval_row)

    policy_state.pending_forecasts = remaining_pending

    # Update active paired comparison history deterministically before running decision checks.
    for (anchor, ticker), pair_roles in sorted(matured_by_anchor_ticker.items()):
        served_eval = pair_roles.get("SERVED_CHAMPION")
        shadow_eval = pair_roles.get("SHADOW_B3")
        if served_eval is None or shadow_eval is None:
            continue
        ver_id = str(served_eval["champion_version_id"])
        if ver_id != str(shadow_eval["champion_version_id"]) or ver_id != active_ver_at_eval[ticker]:
            continue
        history = policy_state.paired_history[ticker]
        existing_keys = {(item["prediction_date"], item["champion_version_id"]) for item in history}
        if (anchor, ver_id) in existing_keys:
            raise ReplayError(f"duplicate paired observation in policy history: {(anchor, ticker, ver_id)}")
        history.append(
            {
                "prediction_date": anchor,
                "target_end_date": _as_date(served_eval["target_end_date"], "pair target_end_date"),
                "evaluation_date": session_date,
                "champion_version_id": ver_id,
                "champion_model_id": str(served_eval["model_id"]),
                "champion_abs_error": float(served_eval["absolute_error"]),
                "shadow_b3_abs_error": float(shadow_eval["absolute_error"]),
            }
        )
        history.sort(key=lambda item: (item["prediction_date"], item["champion_version_id"]))
        if len(history) > policy_cfg.comparison_window_pairs:
            policy_state.paired_history[ticker] = history[-policy_cfg.comparison_window_pairs :]

    for ticker in SUPPORTED_TICKERS:
        cooldown_before = int(policy_state.cooldown_remaining[ticker])
        errors = sorted(
            active_served_by_ticker[ticker],
            key=lambda item: (item["prediction_date"], str(item["policy_prediction_id"])),
        )
        detector = policy_state.policy_adwin[ticker]
        first_trigger_stream: dict[str, Any] | None = None

        for idx, err_row in enumerate(errors, start=1):
            pred_id = str(err_row["policy_prediction_id"])
            if pred_id in policy_state.processed_error_ids:
                raise ReplayError(f"policy ADWIN error was already processed: {pred_id}")
            est_before = float(detector.estimation)
            detector.update(float(err_row["absolute_error"]))
            est_after = float(detector.estimation)
            detected = bool(detector.drift_detected)
            if not detected:
                direction = "no_signal"
            elif est_after > est_before:
                direction = "error_increase"
            elif est_after < est_before:
                direction = "error_decrease"
            else:
                direction = "shift_neutral"
            is_trigger = (
                detected
                and direction in policy_cfg.trigger_directions
                and first_trigger_stream is None
            )
            stream_row = {
                "experiment_id": experiment_id,
                "policy_version": policy_cfg.policy_version,
                "policy_prediction_id": pred_id,
                "prediction_date": err_row["prediction_date"],
                "evaluation_date": session_date,
                "ticker": ticker,
                "champion_version_id": str(err_row["champion_version_id"]),
                "champion_model_id": str(err_row["model_id"]),
                "champion_state_sha256": str(err_row["state_sha256"]),
                "feed_order_in_session": idx,
                "absolute_error": float(err_row["absolute_error"]),
                "adwin_delta": policy_cfg.adwin_delta,
                "adwin_width": int(detector.width),
                "adwin_estimation_before": est_before,
                "adwin_estimation": est_after,
                "drift_detected": detected,
                "drift_direction": direction,
                "triggered_decision": bool(is_trigger),
                "cooldown_active": cooldown_before > 0,
                "cooldown_remaining_before": cooldown_before,
                "prediction_run_id": str(err_row["prediction_run_id"]),
                "evaluation_run_id": run_id,
            }
            session_detector_stream.append(stream_row)
            policy_state.processed_error_ids.add(pred_id)
            if is_trigger:
                first_trigger_stream = stream_row

        if first_trigger_stream is None:
            if cooldown_before > 0:
                policy_state.cooldown_remaining[ticker] = cooldown_before - 1
            continue

        decision_row, timeline_row = _resolve_trigger_decision(
            policy_state,
            ticker=ticker,
            session_date=session_date,
            trigger_row=first_trigger_stream,
            cooldown_before=cooldown_before,
            policy_cfg=policy_cfg,
            experiment_id=experiment_id,
            run_id=run_id,
            calendar_index=calendar_index,
            calendar_sessions=calendar_sessions,
        )
        session_decisions.append(decision_row)
        if timeline_row is not None:
            session_timeline.append(timeline_row)

    return (
        session_evaluations,
        session_detector_stream,
        session_decisions,
        session_timeline,
        session_failures,
    )


def _resolve_trigger_decision(
    policy_state: PolicyRuntimeState,
    *,
    ticker: str,
    session_date: date,
    trigger_row: Mapping[str, Any],
    cooldown_before: int,
    policy_cfg: ChampionChallengerPolicyConfig,
    experiment_id: str,
    run_id: str,
    calendar_index: Mapping[date, int],
    calendar_sessions: list[date],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    active = policy_state.active_champion[ticker]
    ver_before = str(active["champion_version_id"])
    model_id_before = str(active["model_id"])
    state_before = str(active["state_sha256"])

    event_id = _stable_id(
        {
            "experiment_id": experiment_id,
            "policy_version": policy_cfg.policy_version,
            "decision_date": session_date.isoformat(),
            "ticker": ticker,
            "trigger_prediction_id": str(trigger_row["policy_prediction_id"]),
            "champion_version_id_before": ver_before,
        }
    )
    if event_id in policy_state.emitted_event_ids:
        raise ReplayError(f"duplicate policy decision event detected: {event_id}")

    shadow_model = policy_state.shadow_b3_models[ticker]
    shadow_scaler = policy_state.shadow_scalers[ticker]
    shadow_hash_pre_update = model_state_sha256(shadow_model, shadow_scaler)

    window_records = [
        item
        for item in policy_state.paired_history[ticker]
        if item["champion_version_id"] == ver_before
    ][-policy_cfg.comparison_window_pairs :]
    pair_count = len(window_records)
    window_start = (
        window_records[0]["prediction_date"]
        if pair_count >= policy_cfg.comparison_window_pairs
        else policy_state.active_champion[ticker]["effective_from_date"]
    )
    missing_anchors = {
        _as_date(item["prediction_date"], "comparison failure prediction_date")
        for item in policy_state.comparison_failures
        if item["ticker"] == ticker
        and item["champion_version_id"] == ver_before
        and _as_date(item["target_end_date"], "comparison failure target_end_date") <= session_date
        and _as_date(item["prediction_date"], "comparison failure prediction_date") >= _as_date(window_start, "comparison window start")
    }
    champion_mae: float | None = None
    shadow_mae: float | None = None
    rel_improvement: float | None = None
    if pair_count > 0:
        champion_mae = float(np.mean([item["champion_abs_error"] for item in window_records]))
        shadow_mae = float(np.mean([item["shadow_b3_abs_error"] for item in window_records]))

    switched = False
    ver_after = ver_before
    model_id_after = model_id_before
    state_after = state_before
    effective_from_date: date | None = None
    rollback_ver = active.get("rollback_target_version_id")
    rollback_model = active.get("rollback_target_model_id")
    rollback_hash = active.get("rollback_target_state_sha256")
    cooldown_after = cooldown_before
    detector_reset = False
    timeline_row: dict[str, Any] | None = None

    if cooldown_before > 0:
        outcome = "cooldown_suppressed"
        reason = f"cooldown_active_{cooldown_before}_sessions_remaining"
        cooldown_after = cooldown_before - 1
    elif pair_count < policy_cfg.minimum_pairs:
        outcome = "insufficient_pairs"
        reason = f"valid_pairs_{pair_count}_below_minimum_{policy_cfg.minimum_pairs}_missing_{len(missing_anchors)}"
        cooldown_after = policy_cfg.cooldown_sessions
    elif missing_anchors:
        outcome = "invalid"
        reason = f"incomplete_comparison_window_missing_{len(missing_anchors)}_anchors_valid_{pair_count}"
        cooldown_after = policy_cfg.cooldown_sessions
    elif (
        champion_mae is None
        or shadow_mae is None
        or not math.isfinite(champion_mae)
        or not math.isfinite(shadow_mae)
        or champion_mae <= 0.0
    ):
        outcome = "invalid"
        reason = (
            "zero_champion_mae_denominator_undefined"
            if champion_mae == 0.0
            else "invalid_or_nonfinite_paired_mae"
        )
        cooldown_after = policy_cfg.cooldown_sessions
    else:
        rel_improvement = float((champion_mae - shadow_mae) / champion_mae)
        if rel_improvement >= policy_cfg.min_relative_improvement:
            outcome = "promoted"
            switched = True
            reason = (
                f"relative_improvement_{rel_improvement:.6f}_meets_or_exceeds_"
                f"{policy_cfg.min_relative_improvement:.2f}"
            )
            pos = calendar_index.get(session_date)
            if pos is None or pos + 1 >= len(calendar_sessions):
                raise ReplayError(f"cannot determine next XNYS session after {session_date}")
            effective_from_date = calendar_sessions[pos + 1]
            snap_est = deepcopy(shadow_model)
            snap_scaler = deepcopy(shadow_scaler)
            new_state_hash = model_state_sha256(snap_est, snap_scaler)
            next_seq = int(policy_state.version_seq_by_ticker[ticker]) + 1
            policy_state.version_seq_by_ticker[ticker] = next_seq
            ver_after = _champion_version_id(ticker, next_seq, "B3", new_state_hash)
            model_id_after = "B3"
            state_after = new_state_hash
            rollback_ver = ver_before
            rollback_model = model_id_before
            rollback_hash = state_before

            policy_state.active_champion[ticker] = {
                "ticker": ticker,
                "champion_version_id": ver_after,
                "version_seq": next_seq,
                "model_id": "B3",
                "model_name": POLICY_MODEL_NAMES["B3"],
                "is_frozen_snapshot": True,
                "state_sha256": new_state_hash,
                "estimator": snap_est,
                "scaler": snap_scaler,
                "b0_train_mean": active["b0_train_mean"],
                "b0_train_end_date": active["b0_train_end_date"],
                "b1_feature": active["b1_feature"],
                "b1_strategy": active["b1_strategy"],
                "last_training_target_end_date": policy_state.shadow_last_target_end_by_ticker[ticker],
                "effective_from_date": effective_from_date,
                "rollback_target_version_id": rollback_ver,
                "rollback_target_model_id": rollback_model,
                "rollback_target_state_sha256": rollback_hash,
            }
            if policy_cfg.reset_on_promotion:
                policy_state.policy_adwin[ticker] = ADWIN(delta=policy_cfg.adwin_delta)
                detector_reset = True
            policy_state.paired_history[ticker] = []
            policy_state.comparison_failures = [item for item in policy_state.comparison_failures if item["ticker"] != ticker]
            cooldown_after = policy_cfg.cooldown_sessions

            timeline_id = _stable_id(
                {
                    "experiment_id": experiment_id,
                    "event_type": "PROMOTED_SNAPSHOT_ACTIVE_NEXT_SESSION",
                    "ticker": ticker,
                    "to_champion_version_id": ver_after,
                    "decision_event_id": event_id,
                }
            )
            timeline_row = {
                "experiment_id": experiment_id,
                "policy_version": policy_cfg.policy_version,
                "timeline_event_id": timeline_id,
                "event_type": "PROMOTED_SNAPSHOT_ACTIVE_NEXT_SESSION",
                "recorded_date": session_date,
                "decision_date": session_date,
                "effective_from_date": effective_from_date,
                "ticker": ticker,
                "version_seq": next_seq,
                "from_champion_version_id": ver_before,
                "from_model_id": model_id_before,
                "from_state_sha256": state_before,
                "to_champion_version_id": ver_after,
                "to_model_id": model_id_after,
                "to_state_sha256": state_after,
                "rollback_target_version_id": rollback_ver,
                "rollback_target_model_id": rollback_model,
                "rollback_target_state_sha256": rollback_hash,
                "decision_event_id": event_id,
                "reason": reason,
                "run_id": run_id,
            }
        else:
            outcome = "retained"
            reason = (
                f"relative_improvement_{rel_improvement:.6f}_below_threshold_"
                f"{policy_cfg.min_relative_improvement:.2f}"
            )
            cooldown_after = policy_cfg.cooldown_sessions

    policy_state.cooldown_remaining[ticker] = cooldown_after
    policy_state.emitted_event_ids.add(event_id)

    decision_row = {
        "experiment_id": experiment_id,
        "policy_version": policy_cfg.policy_version,
        "event_id": event_id,
        "decision_date": session_date,
        "ticker": ticker,
        "trigger_prediction_id": str(trigger_row["policy_prediction_id"]),
        "trigger_prediction_date": trigger_row["prediction_date"],
        "drift_direction": str(trigger_row["drift_direction"]),
        "adwin_estimation_before": float(trigger_row["adwin_estimation_before"]),
        "adwin_estimation_after": float(trigger_row["adwin_estimation"]),
        "adwin_width": int(trigger_row["adwin_width"]),
        "champion_version_id_before": ver_before,
        "champion_model_id_before": model_id_before,
        "champion_state_sha256_before": state_before,
        "shadow_model_id": policy_cfg.challenger_model,
        "shadow_state_sha256_pre_update": shadow_hash_pre_update,
        "comparison_window_pairs": policy_cfg.comparison_window_pairs,
        "minimum_pairs": policy_cfg.minimum_pairs,
        "min_relative_improvement": policy_cfg.min_relative_improvement,
        "valid_pair_count": pair_count,
        "champion_window_mae": champion_mae,
        "shadow_b3_window_mae": shadow_mae,
        "relative_improvement": rel_improvement,
        "decision_outcome": outcome,
        "decision_reason": reason,
        "switched": switched,
        "champion_version_id_after": ver_after,
        "champion_model_id_after": model_id_after,
        "champion_state_sha256_after": state_after,
        "effective_from_date": effective_from_date,
        "rollback_target_version_id": rollback_ver,
        "rollback_target_model_id": rollback_model,
        "rollback_target_state_sha256": rollback_hash,
        "cooldown_active": cooldown_before > 0,
        "cooldown_remaining_before": cooldown_before,
        "cooldown_remaining_after": cooldown_after,
        "detector_reset_after_decision": detector_reset,
        "run_id": run_id,
    }
    return decision_row, timeline_row


def update_shadow_b3_batch(
    policy_state: PolicyRuntimeState,
    *,
    ticker: str,
    eligible_rows: list[tuple[date, np.ndarray, float, date]],
) -> None:
    if not eligible_rows:
        return
    model = policy_state.shadow_b3_models[ticker]
    scaler = policy_state.shadow_scalers[ticker]
    scaled_batch = scaler.transform(
        pd.DataFrame(
            np.vstack([item[1] for item in eligible_rows]),
            columns=list(CORE_FEATURE_COLUMNS),
        )
    )
    target_batch = np.asarray([item[2] for item in eligible_rows], dtype=float)
    model.partial_fit(scaled_batch, target_batch)
    policy_state.shadow_last_target_end_by_ticker[ticker] = max(
        policy_state.shadow_last_target_end_by_ticker[ticker],
        max(item[3] for item in eligible_rows),
    )


def _policy_ledger_sha256(policy_state: PolicyRuntimeState) -> str:
    champion_meta = {
        ticker: {
            "champion_version_id": str(policy_state.active_champion[ticker]["champion_version_id"]),
            "version_seq": int(policy_state.active_champion[ticker]["version_seq"]),
            "model_id": str(policy_state.active_champion[ticker]["model_id"]),
            "state_sha256": str(policy_state.active_champion[ticker]["state_sha256"]),
            "effective_from_date": _as_date(
                policy_state.active_champion[ticker]["effective_from_date"],
                "champion effective_from_date",
            ).isoformat(),
            "rollback_target_version_id": policy_state.active_champion[ticker].get(
                "rollback_target_version_id"
            ),
            "rollback_target_model_id": policy_state.active_champion[ticker].get(
                "rollback_target_model_id"
            ),
            "rollback_target_state_sha256": policy_state.active_champion[ticker].get(
                "rollback_target_state_sha256"
            ),
        }
        for ticker in SUPPORTED_TICKERS
    }
    payload = {
        "champion_meta": champion_meta,
        "pending_forecasts": sorted(
            policy_state.pending_forecasts,
            key=lambda item: str(item.get("policy_prediction_id", "")),
        ),
        "evaluated_prediction_ids": sorted(policy_state.evaluated_prediction_ids),
        "processed_error_ids": sorted(policy_state.processed_error_ids),
        "emitted_event_ids": sorted(policy_state.emitted_event_ids),
        "paired_history": {
            ticker: list(policy_state.paired_history[ticker]) for ticker in SUPPORTED_TICKERS
        },
        "comparison_failures": list(policy_state.comparison_failures),
        "cooldown_remaining": {
            ticker: int(policy_state.cooldown_remaining[ticker]) for ticker in SUPPORTED_TICKERS
        },
        "version_seq_by_ticker": {
            ticker: int(policy_state.version_seq_by_ticker[ticker]) for ticker in SUPPORTED_TICKERS
        },
        "initial_timeline_recorded": bool(policy_state.initial_timeline_recorded),
    }
    return sha256_bytes(canonical_json(payload).encode("utf-8"))


def build_final_policy_summary(
    final_state: Mapping[str, Any] | None,
    outputs: Mapping[str, pd.DataFrame],
) -> dict[str, Any]:
    """Validate deduplication invariants and summarize per-ETF final policy & rollback state."""
    forecasts = outputs.get("policy_forecasts.csv", pd.DataFrame(columns=POLICY_FORECAST_COLUMNS))
    stream = outputs.get("policy_detector_stream.csv", pd.DataFrame(columns=POLICY_DETECTOR_COLUMNS))
    decisions = outputs.get("policy_decision_events.csv", pd.DataFrame(columns=POLICY_DECISION_COLUMNS))
    timeline = outputs.get("policy_champion_timeline.csv", pd.DataFrame(columns=POLICY_TIMELINE_COLUMNS))

    if not forecasts.empty and forecasts["policy_prediction_id"].duplicated().any():
        raise ReplayError("duplicate policy_prediction_id detected in policy_forecasts.csv")
    if not decisions.empty and decisions["event_id"].duplicated().any():
        raise ReplayError("duplicate event_id detected in policy_decision_events.csv")
    if not timeline.empty and timeline["timeline_event_id"].duplicated().any():
        raise ReplayError("duplicate timeline_event_id detected in policy_champion_timeline.csv")

    ps = final_state.get("policy_state", {}) if final_state else {}
    active_by_ticker = ps.get("active_champion", {})
    tickers_summary: dict[str, Any] = {}
    for ticker in SUPPORTED_TICKERS:
        t_stream = stream.loc[stream["ticker"] == ticker] if not stream.empty else stream
        t_dec = decisions.loc[decisions["ticker"] == ticker] if not decisions.empty else decisions
        t_active = active_by_ticker.get(ticker, {})
        outcome_counts = (
            t_dec["decision_outcome"].value_counts().to_dict() if not t_dec.empty else {}
        )
        tickers_summary[ticker] = {
            "active_champion_version_id": t_active.get("champion_version_id"),
            "active_model_id": t_active.get("model_id"),
            "active_state_sha256": t_active.get("state_sha256"),
            "effective_from_date": (
                t_active["effective_from_date"].isoformat()
                if isinstance(t_active.get("effective_from_date"), date)
                else t_active.get("effective_from_date")
            ),
            "rollback_target_version_id": t_active.get("rollback_target_version_id"),
            "rollback_target_model_id": t_active.get("rollback_target_model_id"),
            "rollback_target_state_sha256": t_active.get("rollback_target_state_sha256"),
            "shadow_b3_state_sha256": ps.get("shadow_b3_state_sha256_by_ticker", {}).get(ticker),
            "policy_adwin_state_sha256": ps.get("policy_adwin_state_sha256_by_ticker", {}).get(ticker),
            "detector_observation_count": int(len(t_stream)),
            "alert_count": int(t_stream["drift_detected"].astype(bool).sum()) if not t_stream.empty else 0,
            "decision_count": int(len(t_dec)),
            "promotion_count": int((t_dec["decision_outcome"] == "promoted").sum()) if not t_dec.empty else 0,
            "outcome_counts": {str(k): int(v) for k, v in outcome_counts.items()},
        }
    return {
        "policy_version": ps.get("policy_version"),
        "policy_config_fingerprint": ps.get("policy_config_fingerprint"),
        "policy_ledger_sha256": ps.get("policy_ledger_sha256"),
        "total_policy_forecasts": int(len(forecasts)),
        "total_policy_decisions": int(len(decisions)),
        "total_policy_promotions": (
            int((decisions["decision_outcome"] == "promoted").sum()) if not decisions.empty else 0
        ),
        "tickers": tickers_summary,
    }


def serialize_policy_state(
    policy_state: PolicyRuntimeState,
    *,
    policy_cfg: ChampionChallengerPolicyConfig,
    adwin_hash_fn: Any,
) -> dict[str, Any]:
    shadow_hashes = {
        ticker: model_state_sha256(
            policy_state.shadow_b3_models[ticker],
            policy_state.shadow_scalers[ticker],
        )
        for ticker in SUPPORTED_TICKERS
    }
    policy_adwin_hashes = {
        ticker: adwin_hash_fn(policy_state.policy_adwin[ticker])
        for ticker in SUPPORTED_TICKERS
    }
    champion_hashes = {
        ticker: champion_entry_state_sha256(policy_state.active_champion[ticker])
        for ticker in SUPPORTED_TICKERS
    }
    return {
        "policy_version": policy_cfg.policy_version,
        "policy_config_fingerprint": policy_cfg.fingerprint(),
        "policy_ledger_sha256": _policy_ledger_sha256(policy_state),
        "shadow_b3_models": policy_state.shadow_b3_models,
        "shadow_scalers": policy_state.shadow_scalers,
        "shadow_last_target_end_by_ticker": {
            ticker: value.isoformat()
            for ticker, value in policy_state.shadow_last_target_end_by_ticker.items()
        },
        "shadow_b3_state_sha256_by_ticker": shadow_hashes,
        "active_champion": policy_state.active_champion,
        "active_champion_state_sha256_by_ticker": champion_hashes,
        "policy_adwin": policy_state.policy_adwin,
        "policy_adwin_state_sha256_by_ticker": policy_adwin_hashes,
        "pending_forecasts": policy_state.pending_forecasts,
        "evaluated_prediction_ids": sorted(policy_state.evaluated_prediction_ids),
        "processed_error_ids": sorted(policy_state.processed_error_ids),
        "emitted_event_ids": sorted(policy_state.emitted_event_ids),
        "paired_history": policy_state.paired_history,
        "comparison_failures": policy_state.comparison_failures,
        "cooldown_remaining": dict(policy_state.cooldown_remaining),
        "version_seq_by_ticker": dict(policy_state.version_seq_by_ticker),
        "initial_timeline_recorded": bool(policy_state.initial_timeline_recorded),
    }


def restore_policy_state(
    saved_policy: Mapping[str, Any] | None,
    *,
    policy_cfg: ChampionChallengerPolicyConfig,
    adwin_hash_fn: Any,
) -> PolicyRuntimeState:
    if not isinstance(saved_policy, Mapping):
        raise ReplayError("policy checkpoint payload is missing or invalid")
    if saved_policy.get("policy_version") != policy_cfg.policy_version:
        raise ReplayError("checkpoint policy_version is incompatible with current policy")
    if saved_policy.get("policy_config_fingerprint") != policy_cfg.fingerprint():
        raise ReplayError("checkpoint policy_config_fingerprint does not match current policy config")
    if "comparison_failures" not in saved_policy:
        raise ReplayError("policy checkpoint lacks the comparison completeness ledger")

    state = PolicyRuntimeState(
        shadow_b3_models=dict(saved_policy["shadow_b3_models"]),
        shadow_scalers=dict(saved_policy["shadow_scalers"]),
        shadow_last_target_end_by_ticker={
            ticker: _as_date(value, "shadow last target end")
            for ticker, value in saved_policy["shadow_last_target_end_by_ticker"].items()
        },
        active_champion={
            ticker: dict(entry)
            for ticker, entry in saved_policy["active_champion"].items()
        },
        policy_adwin=dict(saved_policy["policy_adwin"]),
        pending_forecasts=list(saved_policy["pending_forecasts"]),
        evaluated_prediction_ids=set(saved_policy["evaluated_prediction_ids"]),
        processed_error_ids=set(saved_policy["processed_error_ids"]),
        emitted_event_ids=set(saved_policy["emitted_event_ids"]),
        paired_history={
            ticker: list(rows)
            for ticker, rows in saved_policy["paired_history"].items()
        },
        comparison_failures=list(saved_policy["comparison_failures"]),
        cooldown_remaining={
            ticker: int(val)
            for ticker, val in saved_policy["cooldown_remaining"].items()
        },
        version_seq_by_ticker={
            ticker: int(val)
            for ticker, val in saved_policy["version_seq_by_ticker"].items()
        },
        initial_timeline_recorded=bool(saved_policy["initial_timeline_recorded"]),
    )
    if saved_policy.get("policy_ledger_sha256") != _policy_ledger_sha256(state):
        raise ReplayError("policy checkpoint ledger checksum is invalid")
    for ticker in SUPPORTED_TICKERS:
        actual_shadow = model_state_sha256(
            state.shadow_b3_models[ticker],
            state.shadow_scalers[ticker],
        )
        if actual_shadow != saved_policy["shadow_b3_state_sha256_by_ticker"].get(ticker):
            raise ReplayError(f"{ticker} shadow B3 checkpoint hash is invalid")
        actual_adwin = adwin_hash_fn(state.policy_adwin[ticker])
        if actual_adwin != saved_policy["policy_adwin_state_sha256_by_ticker"].get(ticker):
            raise ReplayError(f"{ticker} policy ADWIN checkpoint hash is invalid")
        champ = state.active_champion[ticker]
        actual_champ = champion_entry_state_sha256(champ)
        if (
            actual_champ != champ.get("state_sha256")
            or actual_champ != saved_policy["active_champion_state_sha256_by_ticker"].get(ticker)
        ):
            raise ReplayError(f"{ticker} active champion checkpoint hash is invalid")
    return state
