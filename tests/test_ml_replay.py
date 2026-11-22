from __future__ import annotations

import hashlib
from copy import deepcopy
from datetime import date, timedelta
import json
import math
from pathlib import Path
import shutil

import joblib
import numpy as np
import pandas as pd
import pandas_market_calendars as market_calendars
import pytest
from pandas.testing import assert_frame_equal
from sklearn.linear_model import LinearRegression

from src.features.pipeline import CORE_FEATURE_COLUMNS, FEATURE_COLUMNS, SUPPORTED_TICKERS
from src.ml_dataset.dataset import prepare_ml_dataset
from src.ml_training import run_training_selection
from src.ml_training.pipeline import B4_MODEL_VERSION
from src.targets.pipeline import LABEL_COLUMNS


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


def _next_sessions(anchor: date, count: int) -> list[date]:
    schedule = market_calendars.get_calendar("XNYS").schedule(
        start_date=anchor + timedelta(days=1), end_date=anchor + timedelta(days=20)
    )
    return [stamp.date() for stamp in schedule.index[:count]]


def _synthetic_tables() -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(2024)
    training_dates = [
        stamp.date()
        for stamp in market_calendars.get_calendar("XNYS")
        .schedule(start_date="2024-09-03", end_date="2024-09-24")
        .index
    ]
    replay_dates = [
        stamp.date()
        for stamp in market_calendars.get_calendar("XNYS")
        .schedule(start_date="2024-10-01", end_date="2024-10-18")
        .index
    ]
    dates = training_dates + replay_dates
    feature_rows: list[dict[str, object]] = []
    label_rows: list[dict[str, object]] = []
    for ticker_index, ticker in enumerate(SUPPORTED_TICKERS):
        for index, anchor in enumerate(dates):
            vec = rng.normal(0.0, 0.02, size=len(CORE_FEATURE_COLUMNS))
            values = dict(zip(CORE_FEATURE_COLUMNS, vec))
            values["rv_5d"] = abs(values["rv_5d"]) + 0.10 + ticker_index * 0.005
            values["rv_20d"] = abs(values["rv_20d"]) + 0.12 + ticker_index * 0.01
            values["rv_60d"] = abs(values["rv_60d"]) + 0.13 + ticker_index * 0.01
            feature_rows.append(
                {
                    "date": anchor,
                    "ticker": ticker,
                    **values,
                    "rsi_14d": 50.0,
                    "bb_width_20d": 0.1,
                    "is_model_ready": True,
                    "is_warmup_buffer": False,
                    "feature_set_version": "2.0.0",
                    "run_id": "synthetic-feature-run",
                    "source_batch_id": "synthetic-source-batch",
                    "feature_as_of_utc": pd.Timestamp("2026-11-20T00:00:00Z"),
                }
            )
            target_start, target_end = _next_sessions(anchor, 5)[0], _next_sessions(anchor, 5)[-1]
            label_rows.append(
                {
                    "date": anchor,
                    "ticker": ticker,
                    "target_start_date": target_start,
                    "target_end_date": target_end,
                    "target_obs_count": 5,
                    "target_realized_vol_5d": 0.13 + ticker_index * 0.01 + index * 0.0005,
                    "is_label_mature": True,
                    "target_version": "2.0.0",
                    "run_id": "synthetic-target-run",
                    "source_batch_id": "synthetic-source-batch",
                    "record_created_at_utc": pd.Timestamp("2026-11-20T00:00:00Z"),
                    "label_matured_at_utc": pd.Timestamp("2026-11-20T00:00:00Z"),
                }
            )
    return pd.DataFrame(feature_rows, columns=FEATURE_COLUMNS), pd.DataFrame(
        label_rows, columns=LABEL_COLUMNS
    )


@pytest.fixture(scope="module")
def synthetic_stage04(tmp_path_factory: pytest.TempPathFactory) -> tuple[object, pd.DataFrame, Path]:
    features, labels = _synthetic_tables()
    prepared = prepare_ml_dataset(
        features,
        labels,
        replay_date=date(2026, 9, 25),
    )
    artifact_dir = tmp_path_factory.mktemp("stage04") / "initial-models"
    run_training_selection(prepared, labels, artifact_dir=artifact_dir)
    return prepared, labels, artifact_dir


def test_final_replay_saves_contract_forecasts_and_evaluates_only_mature_labels(
    synthetic_stage04: tuple[object, pd.DataFrame, Path], tmp_path: Path
) -> None:
    from src.ml_replay import run_final_replay

    prepared, labels, artifact_dir = synthetic_stage04
    result = run_final_replay(
        prepared,
        labels,
        initial_model_artifact_dir=artifact_dir,
        output_root=tmp_path / "replay",
        replay_end_date=date(2024, 10, 18),
    )

    predictions = result.predictions
    assert predictions.columns.tolist() == PREDICTION_COLUMNS
    assert len(predictions) == 14 * 3 * 5
    assert not predictions["prediction_id"].duplicated().any()
    assert set(predictions["model_name"]) == {
        "CONSTANT_BASELINE",
        "ROLLING_20D_BASELINE",
        "STATIC_SGD",
        "ONLINE_SGD",
        "HAR_X_OLS",
    }
    assert predictions["prediction_mode"].eq("HISTORICAL_REPLAY").all()
    assert predictions["prediction_date"].min() == date(2024, 10, 1)
    assert predictions["prediction_date"].max() == date(2024, 10, 18)
    assert not (predictions["prediction_date"] < date(2024, 10, 1)).any()
    first_spy_b0 = predictions.loc[
        (predictions["prediction_date"] == date(2024, 10, 1))
        & (predictions["ticker"] == "SPY")
        & (predictions["model_name"] == "CONSTANT_BASELINE")
    ].iloc[0]
    assert first_spy_b0["target_start_date"] == date(2024, 10, 2)
    assert first_spy_b0["target_end_date"] == date(2024, 10, 8)
    b1_mask = predictions["model_name"] == "ROLLING_20D_BASELINE"
    assert predictions.loc[b1_mask, "last_training_target_end_date"].isna().all()
    learned_model_rows = predictions.loc[~b1_mask]
    assert (
        learned_model_rows["last_training_target_end_date"]
        <= learned_model_rows["prediction_date"]
    ).all()

    evaluations = result.evaluations
    first_anchor_evaluations = evaluations.loc[
        evaluations["prediction_date"] == date(2024, 10, 1)
    ]
    assert len(first_anchor_evaluations) == 3 * 5
    assert first_anchor_evaluations["evaluation_date"].eq(date(2024, 10, 8)).all()
    assert first_anchor_evaluations["split"].eq("validation").all()
    assert first_anchor_evaluations["target_version"].eq("2.0.0").all()
    assert (evaluations["label_available_replay_date"] >= evaluations["target_end_date"]).all()
    assert not result.updated_labels.duplicated(["ticker", "anchor_date"]).any()
    assert (result.updated_labels["target_end_date"] <= result.updated_labels["update_date"]).all()
    assert (result.drift_errors["prediction_id"].value_counts() <= 1).all()
    assert result.coverage["mature_evaluable_count"].sum() == len(evaluations)
    assert result.coverage["pending_label_count"].sum() == len(predictions) - len(evaluations)
    assert result.coverage["evaluation_failure_count"].sum() == 0
    assert len(result.committed_sessions) == 14
    assert result.experiment_manifest["point_in_time_source_availability_verified"] is False
    assert result.experiment_manifest["b2_frozen_state_verified"] is True
    assert result.experiment_manifest["b4_frozen_state_verified"] is True
    assert result.final_b2_state_sha256_by_ticker == {
        ticker: manifest_hash
        for ticker, manifest_hash in result.experiment_manifest[
            "initial_state_sha256_by_ticker"
        ].items()
    }

    replay_again = run_final_replay(
        prepared,
        labels,
        initial_model_artifact_dir=artifact_dir,
        output_root=tmp_path / "replay",
        replay_end_date=date(2024, 10, 18),
        resume=True,
    )
    assert replay_again.run_id != result.run_id
    assert replay_again.predictions["prediction_id"].tolist() == predictions["prediction_id"].tolist()
    assert replay_again.predictions["run_id"].tolist() == predictions["run_id"].tolist()
    assert len(replay_again.committed_sessions) == 14


def test_invalid_forecast_is_rejected_and_retained_in_coverage(
    synthetic_stage04: tuple[object, pd.DataFrame, Path], tmp_path: Path
) -> None:
    from src.ml_replay import run_final_replay

    prepared, labels, artifact_dir = synthetic_stage04
    altered = deepcopy(prepared)
    mask = (altered.prediction.metadata["date"] == date(2024, 10, 1)) & (
        altered.prediction.metadata["ticker"] == "SPY"
    )
    altered.prediction.X.loc[mask, "rv_20d"] = -0.2
    result = run_final_replay(
        altered,
        labels,
        initial_model_artifact_dir=artifact_dir,
        output_root=tmp_path / "invalid-forecast",
        replay_end_date=date(2024, 10, 1),
    )

    invalid = result.forecast_failures.loc[
        (result.forecast_failures["prediction_date"] == date(2024, 10, 1))
        & (result.forecast_failures["ticker"] == "SPY")
        & (result.forecast_failures["model_name"] == "ROLLING_20D_BASELINE")
    ]
    assert len(invalid) == 1
    assert invalid.iloc[0]["failure_type"] == "invalid_forecast"
    assert not (
        (result.predictions["prediction_date"] == date(2024, 10, 1))
        & (result.predictions["ticker"] == "SPY")
        & (result.predictions["model_name"] == "ROLLING_20D_BASELINE")
    ).any()
    coverage = result.coverage.loc[
        (result.coverage["prediction_date"] == date(2024, 10, 1))
        & (result.coverage["ticker"] == "SPY")
        & (result.coverage["model_name"] == "ROLLING_20D_BASELINE")
    ].iloc[0]
    assert coverage["expected_count"] == 1
    assert coverage["published_count"] == 0
    assert coverage["invalid_count"] == 1


def test_replay_refuses_a_modified_stage04_model_artifact(
    synthetic_stage04: tuple[object, pd.DataFrame, Path], tmp_path: Path
) -> None:
    from src.ml_replay import ReplayError, run_final_replay

    prepared, labels, artifact_dir = synthetic_stage04
    altered_artifact = tmp_path / "altered-stage04"
    shutil.copytree(artifact_dir, altered_artifact)
    with (altered_artifact / "initial_models.joblib").open("ab") as stream:
        stream.write(b"tampered")

    with pytest.raises(ReplayError, match="artifact checksum is invalid: initial_models.joblib"):
        run_final_replay(
            prepared,
            labels,
            initial_model_artifact_dir=altered_artifact,
            output_root=tmp_path / "integrity-check",
            replay_end_date=date(2024, 10, 1),
        )


def test_replay_rejects_unsupported_b4_model_version_in_bundle(
    synthetic_stage04: tuple[object, pd.DataFrame, Path], tmp_path: Path
) -> None:
    from src.ml_replay import ReplayError, run_final_replay

    prepared, labels, artifact_dir = synthetic_stage04
    altered_artifact = tmp_path / "unsupported-b4-version"
    shutil.copytree(artifact_dir, altered_artifact)
    bundle_path = altered_artifact / "initial_models.joblib"
    bundle = joblib.load(bundle_path)
    bundle["b4_models"]["SPY"]["model_version"] = f"{B4_MODEL_VERSION}-unsupported"
    joblib.dump(bundle, bundle_path, compress=3)

    manifest_path = altered_artifact / "training_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifact_sha256"]["initial_models.joblib"] = hashlib.sha256(
        bundle_path.read_bytes()
    ).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ReplayError, match="B4 Stage 04 identity is invalid"):
        run_final_replay(
            prepared,
            labels,
            initial_model_artifact_dir=altered_artifact,
            output_root=tmp_path / "version-check",
            replay_end_date=date(2024, 10, 1),
        )


def test_replay_rejects_b4_model_version_mismatch_in_training_manifest(
    synthetic_stage04: tuple[object, pd.DataFrame, Path], tmp_path: Path
) -> None:
    from src.ml_replay import ReplayError, run_final_replay

    prepared, labels, artifact_dir = synthetic_stage04
    altered_artifact = tmp_path / "unsupported-b4-manifest-version"
    shutil.copytree(artifact_dir, altered_artifact)
    manifest_path = altered_artifact / "training_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["b4_models"]["SPY"]["model_version"] = f"{B4_MODEL_VERSION}-unsupported"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ReplayError, match="B4 training manifest identity is invalid"):
        run_final_replay(
            prepared,
            labels,
            initial_model_artifact_dir=altered_artifact,
            output_root=tmp_path / "manifest-version-check",
            replay_end_date=date(2024, 10, 1),
        )


def test_replay_accepts_legacy_b4_training_config_artifact(
    synthetic_stage04: tuple[object, pd.DataFrame, Path], tmp_path: Path
) -> None:
    from src.ml_replay.pipeline import _load_initial_artifact, sha256_file

    prepared, _, artifact_dir = synthetic_stage04
    legacy_artifact = tmp_path / "legacy-b4-training-config"
    shutil.copytree(artifact_dir, legacy_artifact)

    training_config_path = legacy_artifact / "training_config.json"
    training_config = json.loads(training_config_path.read_text(encoding="utf-8"))
    training_config["training_config_version"] = "1.0.0"
    training_config_path.write_text(json.dumps(training_config), encoding="utf-8")

    manifest_path = legacy_artifact / "training_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["training_config_version"] = "1.0.0"
    manifest["artifact_sha256"]["training_config.json"] = sha256_file(training_config_path)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    bundle, loaded_manifest, tickers, _, _ = _load_initial_artifact(legacy_artifact, prepared)

    assert loaded_manifest["training_config_version"] == "1.0.0"
    assert bundle["b4_models"]["SPY"]["model_version"] == B4_MODEL_VERSION
    assert set(tickers) == set(SUPPORTED_TICKERS)


def test_resume_refuses_an_experiment_with_different_replay_identity(
    synthetic_stage04: tuple[object, pd.DataFrame, Path], tmp_path: Path
) -> None:
    from src.ml_replay import ReplayError, run_final_replay

    prepared, labels, artifact_dir = synthetic_stage04
    output_root = tmp_path / "identity-check"
    run_final_replay(
        prepared,
        labels,
        initial_model_artifact_dir=artifact_dir,
        output_root=output_root,
        replay_end_date=date(2024, 10, 1),
    )

    with pytest.raises(ReplayError, match="no experiment with the same data/config/code identity"):
        run_final_replay(
            prepared,
            labels,
            initial_model_artifact_dir=artifact_dir,
            output_root=output_root,
            replay_end_date=date(2024, 10, 2),
            resume=True,
        )


def test_resume_rejects_a_corrupted_committed_checkpoint(
    synthetic_stage04: tuple[object, pd.DataFrame, Path], tmp_path: Path
) -> None:
    from src.ml_replay import ReplayError, run_final_replay

    prepared, labels, artifact_dir = synthetic_stage04
    output_root = tmp_path / "checkpoint-integrity"
    result = run_final_replay(
        prepared,
        labels,
        initial_model_artifact_dir=artifact_dir,
        output_root=output_root,
        replay_end_date=date(2024, 10, 1),
    )
    checkpoint = result.artifact_dir / "checkpoints" / "committed" / "2024-10-01" / "checkpoint.joblib"
    with checkpoint.open("ab") as stream:
        stream.write(b"corrupted")

    with pytest.raises(ReplayError, match="session artifact checksum is invalid: 2024-10-01/checkpoint.joblib"):
        run_final_replay(
            prepared,
            labels,
            initial_model_artifact_dir=artifact_dir,
            output_root=output_root,
            replay_end_date=date(2024, 10, 1),
            resume=True,
        )


def _without_execution_metadata(frame: pd.DataFrame, excluded: tuple[str, ...]) -> pd.DataFrame:
    return frame.drop(columns=list(excluded), errors="ignore").reset_index(drop=True)


@pytest.mark.parametrize(
    "failure_point",
    (
        "after_predict",
        "after_forecast_staged",
        "after_adwin",
        "after_b3_update",
        "before_checkpoint_serialization",
        "after_checkpoint_serialization",
        "before_commit_marker",
        "after_commit_marker_before_publish",
    ),
)
def test_replay_recovers_from_uncommitted_daily_failure_without_duplicate_learning(
    synthetic_stage04: tuple[object, pd.DataFrame, Path],
    tmp_path: Path,
    failure_point: str,
) -> None:
    from src.ml_replay import run_final_replay

    prepared, labels, artifact_dir = synthetic_stage04
    replay_end = date(2024, 10, 18)
    uninterrupted = run_final_replay(
        prepared,
        labels,
        initial_model_artifact_dir=artifact_dir,
        output_root=tmp_path / "uninterrupted",
        replay_end_date=replay_end,
    )

    def fail_once(point: str, session_date: date) -> None:
        if point == failure_point and session_date == date(2024, 10, 8):
            raise RuntimeError(f"simulated interruption at {point}")

    with pytest.raises(RuntimeError, match=f"simulated interruption at {failure_point}"):
        run_final_replay(
            prepared,
            labels,
            initial_model_artifact_dir=artifact_dir,
            output_root=tmp_path / "recovered",
            replay_end_date=replay_end,
            failure_injector=fail_once,
        )
    resumed = run_final_replay(
        prepared,
        labels,
        initial_model_artifact_dir=artifact_dir,
        output_root=tmp_path / "recovered",
        replay_end_date=replay_end,
        resume=True,
    )

    assert resumed.completed
    assert resumed.predictions["prediction_id"].tolist() == uninterrupted.predictions[
        "prediction_id"
    ].tolist()
    assert not resumed.predictions["prediction_id"].duplicated().any()
    assert_frame_equal(
        _without_execution_metadata(
            resumed.predictions,
            ("run_id", "prediction_created_at_utc"),
        ),
        _without_execution_metadata(
            uninterrupted.predictions,
            ("run_id", "prediction_created_at_utc"),
        ),
        check_dtype=False,
        check_exact=True,
    )
    assert_frame_equal(
        _without_execution_metadata(
            resumed.evaluations,
            ("prediction_run_id", "evaluation_run_id"),
        ),
        _without_execution_metadata(
            uninterrupted.evaluations,
            ("prediction_run_id", "evaluation_run_id"),
        ),
        check_dtype=False,
        check_exact=True,
    )
    assert_frame_equal(
        _without_execution_metadata(resumed.drift_errors, ("prediction_run_id", "evaluation_run_id")),
        _without_execution_metadata(
            uninterrupted.drift_errors,
            ("prediction_run_id", "evaluation_run_id"),
        ),
        check_dtype=False,
        check_exact=True,
    )
    assert_frame_equal(
        _without_execution_metadata(resumed.updated_labels, ("run_id",)),
        _without_execution_metadata(uninterrupted.updated_labels, ("run_id",)),
        check_dtype=False,
        check_exact=True,
    )
    assert resumed.final_b3_state_sha256_by_ticker == uninterrupted.final_b3_state_sha256_by_ticker
    assert resumed.final_adwin_state_sha256_by_ticker == uninterrupted.final_adwin_state_sha256_by_ticker
    assert len(resumed.committed_sessions) == 14
    assert not resumed.updated_labels.duplicated(["ticker", "anchor_date"]).any()
    assert not resumed.drift_errors["prediction_id"].duplicated().any()


def test_b4_replay_predictions_match_direct_artifact_and_stay_frozen(
    synthetic_stage04: tuple[object, pd.DataFrame, Path], tmp_path: Path
) -> None:
    from src.ml_replay import run_final_replay

    prepared, labels, artifact_dir = synthetic_stage04
    result = run_final_replay(
        prepared,
        labels,
        initial_model_artifact_dir=artifact_dir,
        output_root=tmp_path / "b4-direct",
        replay_end_date=date(2024, 10, 18),
    )
    bundle = joblib.load(artifact_dir / "initial_models.joblib")
    b4_preds = result.predictions.loc[result.predictions["model_name"] == "HAR_X_OLS"].copy()
    assert len(b4_preds) == 14 * 3
    assert b4_preds["model_version"].eq("b4_ols_v1.0.0").all()
    assert (b4_preds["last_training_target_end_date"] <= date(2024, 9, 30)).all()
    assert not result.updated_labels.empty
    assert result.experiment_manifest["b4_frozen_state_verified"] is True

    # Direct calculation from Stage 04 artifact must match Replay B4 predictions within 1e-15.
    for row in b4_preds.itertuples(index=False):
        b4_entry = bundle["b4_models"][row.ticker]
        mask = (prepared.prediction.metadata["date"] == row.prediction_date) & (
            prepared.prediction.metadata["ticker"] == row.ticker
        )
        feat_row = prepared.prediction.X.loc[mask, list(CORE_FEATURE_COLUMNS)]
        expected_pred = float(b4_entry["model"].predict(b4_entry["scaler"].transform(feat_row))[0])
        assert abs(float(row.predicted_vol_annualized) - expected_pred) <= 1e-15


def test_b4_invalid_forecast_and_pending_semantics(
    synthetic_stage04: tuple[object, pd.DataFrame, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.ml_replay import run_final_replay

    prepared, labels, artifact_dir = synthetic_stage04
    original_predict = LinearRegression.predict

    def predict_negative_once(self: LinearRegression, X: np.ndarray) -> np.ndarray:
        preds = original_predict(self, X).copy()
        preds[0] = -0.15
        return preds

    monkeypatch.setattr(LinearRegression, "predict", predict_negative_once)
    result = run_final_replay(
        prepared,
        labels,
        initial_model_artifact_dir=artifact_dir,
        output_root=tmp_path / "b4-invalid",
        replay_end_date=date(2024, 10, 8),
    )

    b4_failures = result.forecast_failures.loc[
        result.forecast_failures["model_name"] == "HAR_X_OLS"
    ]
    assert len(b4_failures) == 6 * 3
    assert (b4_failures["failure_type"] == "invalid_forecast").all()
    b4_cov = result.coverage.loc[result.coverage["model_name"] == "HAR_X_OLS"]
    assert b4_cov["invalid_count"].sum() == 6 * 3
    assert b4_cov["published_count"].sum() == 0
    assert result.predictions.loc[result.predictions["model_name"] == "HAR_X_OLS"].empty


def test_replay_stop_resume_and_incompatible_b4_checkpoint_rejected(
    synthetic_stage04: tuple[object, pd.DataFrame, Path], tmp_path: Path
) -> None:
    from src.ml_replay import ReplayError, run_final_replay

    prepared, labels, artifact_dir = synthetic_stage04
    continuous = run_final_replay(
        prepared,
        labels,
        initial_model_artifact_dir=artifact_dir,
        output_root=tmp_path / "continuous",
        replay_end_date=date(2024, 10, 18),
    )

    resumed_root = tmp_path / "stop-resume"
    partial = run_final_replay(
        prepared,
        labels,
        initial_model_artifact_dir=artifact_dir,
        output_root=resumed_root,
        replay_end_date=date(2024, 10, 18),
        stop_after_session=date(2024, 10, 8),
    )
    assert not partial.completed
    resumed = run_final_replay(
        prepared,
        labels,
        initial_model_artifact_dir=artifact_dir,
        output_root=resumed_root,
        replay_end_date=date(2024, 10, 18),
        resume=True,
    )
    assert resumed.completed
    assert_frame_equal(
        resumed.predictions.drop(columns=["run_id", "prediction_created_at_utc"]),
        continuous.predictions.drop(columns=["run_id", "prediction_created_at_utc"]),
        check_dtype=False,
        check_exact=True,
    )
    assert_frame_equal(
        resumed.evaluations.drop(columns=["prediction_run_id", "evaluation_run_id"]),
        continuous.evaluations.drop(columns=["prediction_run_id", "evaluation_run_id"]),
        check_dtype=False,
        check_exact=True,
    )

    # Corrupting compatibility_fingerprint in a committed checkpoint must be rejected on resume.
    ck_path = (
        resumed.artifact_dir / "checkpoints" / "committed" / "2024-10-08" / "checkpoint.joblib"
    )
    ck = joblib.load(ck_path)
    ck["compatibility_fingerprint"] = "incompatible-suite-or-b4-artifact"
    joblib.dump(ck, ck_path)
    with pytest.raises(ReplayError, match="checkpoint"):
        run_final_replay(
            prepared,
            labels,
            initial_model_artifact_dir=artifact_dir,
            output_root=resumed_root,
            replay_end_date=date(2024, 10, 18),
            resume=True,
        )


def _build_policy_test_dataset(
    scenario: str,
    *,
    test_end_date: date,
) -> tuple[object, pd.DataFrame, dict[str, list[date]]]:
    """Build deterministic Stage 03 inputs spanning Train, Validation cutover, and Test."""
    schedule = market_calendars.get_calendar("XNYS").schedule(
        start_date="2024-09-03",
        end_date=(pd.Timestamp(test_end_date) + pd.Timedelta(days=20)).strftime("%Y-%m-%d"),
    )
    sessions = [stamp.date() for stamp in schedule.index]
    session_idx = {d: i for i, d in enumerate(sessions)}

    train_dates = [d for d in sessions if date(2024, 9, 3) <= d <= date(2024, 9, 25)][:15]
    val_early = [d for d in sessions if date(2024, 10, 1) <= d <= date(2024, 10, 10)]
    val_cutover = [d for d in sessions if date(2025, 9, 17) <= d <= date(2025, 9, 30)]
    val_dates = val_early + val_cutover
    test_dates = [d for d in sessions if date(2025, 10, 1) <= d <= test_end_date]

    feature_rows: list[dict[str, object]] = []
    label_rows: list[dict[str, object]] = []

    for ticker_idx, ticker in enumerate(SUPPORTED_TICKERS):
        rng = np.random.default_rng(1000 + ticker_idx)
        base_target = 0.14 + ticker_idx * 0.02
        # Set constant Train targets around base_target so B0 ~= base_target.
        all_dates = train_dates + val_dates + test_dates
        for pos, anchor in enumerate(all_dates):
            split = (
                "train"
                if anchor < date(2024, 10, 1)
                else "validation"
                if anchor < date(2025, 10, 1)
                else "test"
            )
            vec = rng.normal(0.0, 0.015, size=len(CORE_FEATURE_COLUMNS))
            values = dict(zip(CORE_FEATURE_COLUMNS, vec))
            values["rv_5d"] = abs(values["rv_5d"]) + 0.06
            values["rv_20d"] = abs(values["rv_20d"]) + 0.40 + ticker_idx * 0.05  # non-constant in Train for B4 rank=9, poor unless overridden
            values["rv_60d"] = abs(values["rv_60d"]) + 0.07

            target_start = sessions[session_idx[anchor] + 1]
            target_end = sessions[session_idx[anchor] + 5]
            target_val = base_target

            if split == "train":
                target_val = base_target + 0.002 * math.sin(pos)
            elif split == "validation":
                # Keep B0 strong & clear winner at Validation->Test cutover by making rv_20d far
                # and target tightly centered near B0 (~base_target).
                if scenario == "no_drift":
                    target_val = base_target + 0.001 * math.cos(pos)
                elif ticker == "SPY" and scenario == "main_outcomes":
                    # Make Validation target close to train mean so B0 wins SPY.
                    target_val = base_target
                elif ticker == "IEF" and scenario == "main_outcomes":
                    # Make Validation target equal rv_20d so B1 wins IEF (or B0 wins).
                    values["rv_20d"] = base_target
                    target_val = base_target
                elif ticker == "GLD" and scenario == "main_outcomes":
                    target_val = base_target
                elif scenario == "zero_mae":
                    target_val = base_target
            else:
                test_idx = pos - len(train_dates) - len(val_dates)
                if scenario == "no_drift":
                    target_val = base_target + 0.001 * math.sin(test_idx)
                elif scenario == "main_outcomes":
                    if ticker == "SPY":
                        # Mark Test anchors 0..38 with a finite sentinel on ret_1d_t so test can invalidate
                        # SHADOW_B3 (while B0 initial champion succeeds), giving 64 served ADWIN errors
                        # [0.0]*32 + [1.5]*32 with only 25 valid pairs (< 30) -> insufficient_pairs!
                        if test_idx < 39:
                            values["ret_1d_t"] = 0.987654
                        target_val = base_target if test_idx < 32 else base_target + 1.50
                    elif ticker == "IEF":
                        # 1) anchors 0..31: target == rv_20d == base_target (B1 wins cutover cleanly, 0 error).
                        # 2) anchors 32..end: target alternates {base, base + 1.50} uncorrelated with features
                        #    while rv_20d stays at base + 0.75 -> B1 error = 0.75, ADWIN fires at step 64,
                        #    and shadow_b3 achieves MAE ~= 0.75 (< 5% gain) -> retained!
                        if test_idx < 32:
                            target_val = base_target
                            values["rv_20d"] = base_target
                        else:
                            target_val = base_target + (1.50 if test_idx % 2 == 1 else 0.0)
                            values["rv_20d"] = base_target + 0.75
                    elif ticker == "GLD":
                        # 1) anchors 0..31: calm Regime 1 around base_target (builds 32 low-error pairs).
                        # 2) anchors 32..101: Regime 2 (target=1.20, stable ~2x-IQR shift on ret_1d_t/ret_lag_1d)
                        #    -> ADWIN fires at step 64 (session ~68) -> promotes v002 (B3 snapshot) effective session ~69;
                        #    anchors 69..101 give v002 33 calm Regime 2 pairs & clear 20-session cooldown.
                        # 3) anchors 102..end: Regime 3 (target=2.60, positive shift on ret_lag_2d/ret_trailing_5d so
                        #    frozen v002 stays positive ~0.5 while shadow_b3 adapts to ~2.4) -> B3-to-B3 promotes v003!
                        if test_idx < 32:
                            target_val = base_target
                            for col in CORE_FEATURE_COLUMNS:
                                values[col] = 0.005 * math.sin(test_idx)
                            values["rv_5d"] = 0.07
                            values["rv_20d"] = 0.51
                            values["rv_60d"] = 0.08
                        elif test_idx < 102:
                            target_val = 1.20
                            values["ret_1d_t"] = 0.025
                            values["ret_lag_1d"] = 0.025
                            values["ret_lag_2d"] = 0.0
                            values["ret_trailing_5d"] = 0.0
                            values["ret_trailing_20d"] = 0.0
                            values["rv_5d"] = 0.07
                            values["rv_20d"] = 0.51
                            values["rv_60d"] = 0.08
                        else:
                            target_val = 2.60
                            values["ret_1d_t"] = 0.005
                            values["ret_lag_1d"] = 0.005
                            values["ret_lag_2d"] = 0.025
                            values["ret_trailing_5d"] = 0.025
                            values["ret_trailing_20d"] = 0.015
                            values["rv_5d"] = 0.07
                            values["rv_20d"] = 0.51
                            values["rv_60d"] = 0.08
                elif scenario == "zero_mae":
                    # 15 initial high-error obs (error=1.2), then 70 zero-error obs -> ADWIN error_decrease around obs 75
                    # where the latest 60 pairs ALL have champion_mae == 0.0 -> invalid!
                    if test_idx < 15:
                        target_val = base_target + 1.20
                    else:
                        target_val = base_target
                        values["rv_20d"] = base_target

            feature_rows.append(
                {
                    "date": anchor,
                    "ticker": ticker,
                    **values,
                    "rsi_14d": 50.0,
                    "bb_width_20d": 0.1,
                    "is_model_ready": True,
                    "is_warmup_buffer": False,
                    "feature_set_version": "2.0.0",
                    "run_id": f"synthetic-policy-{scenario}",
                    "source_batch_id": "synthetic-source-batch",
                    "feature_as_of_utc": pd.Timestamp("2026-11-20T00:00:00Z"),
                }
            )
            label_rows.append(
                {
                    "date": anchor,
                    "ticker": ticker,
                    "target_start_date": target_start,
                    "target_end_date": target_end,
                    "target_obs_count": 5,
                    "target_realized_vol_5d": float(target_val),
                    "is_label_mature": True,
                    "target_version": "2.0.0",
                    "run_id": f"synthetic-target-{scenario}",
                    "source_batch_id": "synthetic-source-batch",
                    "record_created_at_utc": pd.Timestamp("2026-11-20T00:00:00Z"),
                    "label_matured_at_utc": pd.Timestamp("2026-11-20T00:00:00Z"),
                }
            )

    features_df = pd.DataFrame(feature_rows, columns=FEATURE_COLUMNS)
    labels_df = pd.DataFrame(label_rows, columns=LABEL_COLUMNS)
    prepared = prepare_ml_dataset(features_df, labels_df, replay_date=date(2026, 9, 25))
    return prepared, labels_df, {"train": train_dates, "validation": val_dates, "test": test_dates}


def _quick_stage04_policy_artifact(
    prepared: object,
    labels: pd.DataFrame,
    artifact_dir: Path,
) -> Path:
    from src.ml_training import CandidateConfig, TrainingConfig, fit_b4_ols, select_initial_champion
    from src.ml_training import pipeline as tp

    config = TrainingConfig.from_yaml()
    candidate = CandidateConfig(eta0=0.01, alpha=1e-5, max_iter=50)
    runs = [
        tp.evaluate_candidate(prepared, labels, ticker=t, candidate=candidate, config=config)
        for t in SUPPORTED_TICKERS
    ]
    candidate_rows = pd.DataFrame([tp._result_row(run) for run in runs])
    selected_rows = candidate_rows.copy()
    initial_models: dict[str, dict[str, object]] = {}
    baselines: dict[str, dict[str, object]] = {}
    b4_models: dict[str, dict[str, object]] = {}
    b4_summaries: list[dict[str, object]] = []
    b4_frames: list[pd.DataFrame] = []
    for ticker in SUPPORTED_TICKERS:
        train_X, train_y, _, _ = tp._training_rows(prepared, ticker, config)
        pair = tp._fit_initial_pair(train_X, train_y, candidate, config)
        initial_models[ticker] = {
            **pair,
            "selected_candidate": candidate.as_dict(),
            "train_cutoff": config.dataset.train_end_date,
            "feature_order": tuple(config.core_features),
        }
        b4_art = fit_b4_ols(prepared, ticker, config, b2_scaler=pair["scaler"])
        b4_sum, b4_df = tp.evaluate_b4_validation(prepared, ticker, b4_art, config)
        b4_models[ticker] = b4_art
        b4_summaries.append(b4_sum)
        b4_frames.append(b4_df)
        baselines[ticker] = {
            "b0_model_id": "B0",
            "b0_model_name": "CONSTANT_BASELINE",
            "b0_train_mean": float(train_y.mean()),
            "b0_train_row_count": int(len(train_y)),
            "b0_train_end_date": config.dataset.train_end_date.isoformat(),
            "b1_model_id": "B1",
            "b1_model_name": "ROLLING_20D_BASELINE",
            "b1_feature": "rv_20d",
            "b1_strategy": "feature_value",
        }
    _, ic_scores, ic_summary = select_initial_champion(
        prepared, labels, initial_models, baselines, config=config
    )
    tp._persist_artifacts(
        artifact_dir,
        candidate_rows,
        selected_rows,
        initial_models,
        baselines,
        config,
        dict(prepared.report.lineage),
        prepared.report.limitations,
        selection_status="selected",
        b4_models=b4_models,
        b4_validation_rows=pd.concat(b4_frames, ignore_index=True),
        b4_validation_summary=b4_summaries,
        initial_champion_scores=ic_scores,
        initial_champion_summary=ic_summary,
    )
    return artifact_dir


def test_policy_replay_no_drift_and_preserves_b0_through_b4_outputs(tmp_path: Path) -> None:
    from src.ml_replay import ReplayConfig, run_final_replay

    replay_end = date(2025, 11, 20)
    prepared, labels, _ = _build_policy_test_dataset("no_drift", test_end_date=replay_end)
    stage04_dir = _quick_stage04_policy_artifact(prepared, labels, tmp_path / "stage04-no-drift")

    baseline_cfg = ReplayConfig.from_yaml(policy_mode="baseline")
    policy_cfg = ReplayConfig.from_yaml(policy_mode="champion_challenger")
    res_base = run_final_replay(
        prepared,
        labels,
        initial_model_artifact_dir=stage04_dir,
        output_root=tmp_path / "base-out",
        config=baseline_cfg,
        replay_end_date=replay_end,
    )
    res_policy = run_final_replay(
        prepared,
        labels,
        initial_model_artifact_dir=stage04_dir,
        output_root=tmp_path / "policy-out",
        config=policy_cfg,
        replay_end_date=replay_end,
    )

    assert res_base.experiment_id != res_policy.experiment_id
    assert res_base.policy_forecasts is None
    assert res_policy.policy_forecasts is not None
    assert res_policy.policy_evaluations is not None
    assert res_policy.policy_detector_stream is not None
    assert res_policy.policy_decision_events is not None
    assert res_policy.policy_champion_timeline is not None

    # B0-B4 benchmark predictions, evaluations, ADWIN drift, and updates remain invariant.
    assert_frame_equal(
        _without_execution_metadata(res_base.predictions, ("run_id", "prediction_created_at_utc")),
        _without_execution_metadata(res_policy.predictions, ("run_id", "prediction_created_at_utc")),
        check_dtype=False,
        check_exact=True,
    )
    assert_frame_equal(
        _without_execution_metadata(
            res_base.evaluations,
            ("experiment_id", "prediction_run_id", "evaluation_run_id"),
        ),
        _without_execution_metadata(
            res_policy.evaluations,
            ("experiment_id", "prediction_run_id", "evaluation_run_id"),
        ),
        check_dtype=False,
        check_exact=True,
    )
    assert_frame_equal(
        _without_execution_metadata(
            res_base.drift_errors,
            ("experiment_id", "prediction_run_id", "evaluation_run_id"),
        ),
        _without_execution_metadata(
            res_policy.drift_errors,
            ("experiment_id", "prediction_run_id", "evaluation_run_id"),
        ),
        check_dtype=False,
        check_exact=True,
    )
    assert res_base.final_b3_state_sha256_by_ticker == res_policy.final_b3_state_sha256_by_ticker

    # No-drift guarantees: zero alerts, zero decisions, only initial cutover timeline entries,
    # Validation purge rows never enter policy forecasts or detector stream, and horizon tail stays pending.
    assert res_policy.policy_decision_events.empty
    assert not res_policy.policy_detector_stream["drift_detected"].any()
    assert (res_policy.policy_forecasts["prediction_date"] >= date(2025, 10, 1)).all()
    assert (res_policy.policy_detector_stream["prediction_date"] >= date(2025, 10, 1)).all()
    assert len(res_policy.policy_champion_timeline) == 3
    assert set(res_policy.policy_champion_timeline["event_type"]) == {"INITIAL_CHAMPION_CUTOVER"}
    assert len(res_policy.policy_forecasts) > len(res_policy.policy_evaluations)


def test_policy_replay_covers_insufficient_cooldown_retained_promotion_and_b3_to_b3(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from river.drift import ADWIN
    from sklearn.linear_model import SGDRegressor
    from src.ml_replay import ReplayConfig, pipeline as replay_pipeline, policy as policy_mod, run_final_replay

    replay_end = date(2026, 5, 1)
    prepared, labels, _ = _build_policy_test_dataset("main_outcomes", test_end_date=replay_end)
    stage04_dir = _quick_stage04_policy_artifact(prepared, labels, tmp_path / "stage04-main")
    policy_cfg = ReplayConfig.from_yaml(policy_mode="champion_challenger")
    assert policy_cfg.champion_challenger is not None

    # Cause SPY Test anchors 0..38 (where scaled ret_1d_t > 30 and ret_lag_1d < 5) to fail SHADOW_B3
    # without clipping while served B0 succeeds -> 64 served errors with < 30 pairs -> insufficient_pairs.
    orig_predict = SGDRegressor.predict

    def invalid_on_sentinel_scaled(self: SGDRegressor, X: np.ndarray) -> np.ndarray:
        preds = orig_predict(self, X).copy()
        if isinstance(X, np.ndarray) and X.shape[1] >= 1 and X[0, 0] > 30.0 and X[0, 1] < 5.0:
            preds[0] = -0.25
        return preds

    monkeypatch.setattr(SGDRegressor, "predict", invalid_on_sentinel_scaled)

    result = run_final_replay(
        prepared,
        labels,
        initial_model_artifact_dir=stage04_dir,
        output_root=tmp_path / "policy-main",
        config=policy_cfg,
        replay_end_date=replay_end,
    )
    monkeypatch.undo()

    decisions = result.policy_decision_events
    timeline = result.policy_champion_timeline
    evals = result.policy_evaluations
    forecasts = result.policy_forecasts
    stream = result.policy_detector_stream
    assert decisions is not None and not decisions.empty
    assert timeline is not None and evals is not None and forecasts is not None and stream is not None

    # SPY: early invalid shadow forecasts -> valid_pair_count < 30 when ADWIN fires at step 64 -> insufficient_pairs!
    spy_decisions = decisions.loc[decisions["ticker"] == "SPY"]
    assert "insufficient_pairs" in set(spy_decisions["decision_outcome"])
    assert not spy_decisions["switched"].any()
    assert int(spy_decisions.loc[spy_decisions["decision_outcome"] == "insufficient_pairs", "valid_pair_count"].iloc[0]) < 30

    # Verify cooldown_suppressed explicitly using restored state + real ADWIN trigger during active cooldown.
    ckpt_last = joblib.load(
        result.artifact_dir / "checkpoints" / "committed" / replay_end.isoformat() / "checkpoint.joblib"
    )
    p_cd = policy_mod.restore_policy_state(
        ckpt_last["policy_state"],
        policy_cfg=policy_cfg.champion_challenger,
        adwin_hash_fn=replay_pipeline._adwin_state_sha256,
    )
    p_cd.cooldown_remaining["SPY"] = 10
    p_cd.policy_adwin["SPY"] = ADWIN(delta=policy_cfg.champion_challenger.adwin_delta)
    for _ in range(30):
        p_cd.policy_adwin["SPY"].update(0.01)
    probe = deepcopy(p_cd.policy_adwin["SPY"])
    pre_steps = 0
    while True:
        probe.update(1.50)
        if probe.drift_detected:
            break
        pre_steps += 1
        assert pre_steps < 50
    for _ in range(pre_steps):
        p_cd.policy_adwin["SPY"].update(1.50)
    cd_champ = p_cd.active_champion["SPY"]
    p_cd.pending_forecasts = [
        {
            "policy_prediction_id": "cd-served-1",
            "prediction_date": date(2026, 4, 25),
            "split": "test",
            "ticker": "SPY",
            "role": "SERVED_CHAMPION",
            "champion_version_id": cd_champ["champion_version_id"],
            "model_id": cd_champ["model_id"],
            "model_name": cd_champ["model_name"],
            "is_frozen_snapshot": True,
            "model_version": cd_champ["champion_version_id"],
            "state_sha256": cd_champ["state_sha256"],
            "target_start_date": date(2026, 4, 27),
            "target_end_date": date(2026, 5, 1),
            "predicted_vol_annualized": 0.14,
            "run_id": "cd-run",
        }
    ]
    _, cd_stream, cd_decisions, _, _ = policy_mod.run_policy_evaluate_and_decide(
        p_cd,
        session_date=date(2026, 5, 4),
        policy_cfg=policy_cfg.champion_challenger,
        experiment_id="exp-cd",
        run_id="run-cd",
        label_map={
            (date(2026, 4, 25), "SPY"): {
                "target_start_date": date(2026, 4, 27),
                "target_end_date": date(2026, 5, 1),
                "target_obs_count": 5,
                "target_realized_vol_5d": 1.64,
                "is_label_mature": True,
                "target_version": "2.0.0",
            }
        },
        audit_map={(date(2026, 4, 25), "SPY"): {"label_quality_passed": True}},
        calendar_index={date(2026, 5, 4): 0, date(2026, 5, 5): 1},
        calendar_sessions=[date(2026, 5, 4), date(2026, 5, 5)],
    )
    assert len(cd_decisions) == 1
    assert cd_decisions[0]["decision_outcome"] == "cooldown_suppressed"
    assert cd_decisions[0]["cooldown_active"] is True
    assert cd_decisions[0]["cooldown_remaining_before"] == 10
    assert cd_decisions[0]["cooldown_remaining_after"] == 9
    assert cd_decisions[0]["switched"] is False
    assert cd_stream[0]["drift_detected"] is True
    assert cd_stream[0]["cooldown_active"] is True

    # IEF: >= 30 pairs but shadow B3 cannot beat B1 by >=5% -> retained.
    ief_decisions = decisions.loc[decisions["ticker"] == "IEF"]
    assert "retained" in set(ief_decisions["decision_outcome"])
    assert not ief_decisions["switched"].any()

    # GLD: first promotion (initial champion -> B3 snapshot v002) and later second promotion (B3 v002 -> B3 v003).
    gld_decisions = decisions.loc[decisions["ticker"] == "GLD"]
    gld_promos = gld_decisions.loc[gld_decisions["decision_outcome"] == "promoted"]
    assert len(gld_promos) >= 2
    first_promo = gld_promos.iloc[0]
    second_promo = gld_promos.iloc[1]
    assert first_promo["champion_model_id_before"] in {"B0", "B1", "B2"}
    assert first_promo["champion_model_id_after"] == "B3"
    assert first_promo["detector_reset_after_decision"] == True  # noqa: E712
    assert first_promo["effective_from_date"] > first_promo["decision_date"]
    assert first_promo["rollback_target_version_id"] == first_promo["champion_version_id_before"]
    assert second_promo["champion_model_id_before"] == "B3"
    assert second_promo["champion_model_id_after"] == "B3"
    assert second_promo["rollback_target_version_id"] == first_promo["champion_version_id_after"]
    assert second_promo["rollback_target_version_id"] == second_promo["champion_version_id_before"]

    # On promotion day itself, served GLD forecast used the OLD champion; next session uses NEW snapshot!
    promo_day = first_promo["decision_date"]
    eff_day = first_promo["effective_from_date"]
    gld_served = forecasts.loc[
        (forecasts["ticker"] == "GLD") & (forecasts["role"] == "SERVED_CHAMPION")
    ].set_index("prediction_date")
    assert gld_served.loc[promo_day, "champion_version_id"] == first_promo["champion_version_id_before"]
    assert gld_served.loc[eff_day, "champion_version_id"] == first_promo["champion_version_id_after"]
    assert bool(gld_served.loc[eff_day, "is_frozen_snapshot"]) is True

    # Old-champion forecasts that mature after promotion appear in policy_evaluations for audit
    # but are explicitly skipped from new champion's ADWIN stream.
    stale_evals = evals.loc[
        (evals["ticker"] == "GLD") & (evals["stale_champion_skipped_from_policy"])
    ]
    assert not stale_evals.empty
    assert (stale_evals["policy_skip_reason"] == "matured_under_newer_champion_version").all()
    assert set(stale_evals["policy_prediction_id"]).isdisjoint(set(stream["policy_prediction_id"]))

    # Timeline starts with initial cutover and records every promotion with rollback lineage.
    assert len(timeline.loc[(timeline["ticker"] == "GLD") & (timeline["event_type"] == "PROMOTED_SNAPSHOT_ACTIVE_NEXT_SESSION")]) == len(gld_promos)


def test_policy_replay_handles_zero_mae_invalid_and_negative_forecasts_without_clipping(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sklearn.linear_model import SGDRegressor
    from src.ml_replay import ReplayConfig, pipeline as replay_pipeline, policy as policy_mod, run_final_replay

    replay_end = date(2025, 10, 10)
    prepared, labels, _ = _build_policy_test_dataset("no_drift", test_end_date=replay_end)
    stage04_dir = _quick_stage04_policy_artifact(prepared, labels, tmp_path / "stage04-zero-mae")
    policy_cfg = ReplayConfig.from_yaml(policy_mode="champion_challenger")
    assert policy_cfg.champion_challenger is not None

    # 1. Negative (<0) shadow B3 forecast logs unclipped raw_value to policy_failures.csv.
    orig_predict = SGDRegressor.predict

    def neg_predict(self: SGDRegressor, X: pd.DataFrame) -> np.ndarray:
        preds = orig_predict(self, X)
        return np.full(len(preds), -0.25)

    monkeypatch.setattr(SGDRegressor, "predict", neg_predict)
    result_neg = run_final_replay(
        prepared,
        labels,
        initial_model_artifact_dir=stage04_dir,
        output_root=tmp_path / "policy-neg",
        config=policy_cfg,
        replay_end_date=replay_end,
    )
    assert result_neg.policy_failures is not None
    neg_shadow = result_neg.policy_failures.loc[
        (result_neg.policy_failures["role"] == "SHADOW_B3")
        & (result_neg.policy_failures["failure_type"] == "invalid_forecast")
    ]
    assert not neg_shadow.empty
    assert (neg_shadow["raw_value"] == -0.25).all()
    assert result_neg.policy_forecasts.loc[result_neg.policy_forecasts["role"] == "SHADOW_B3"].empty
    monkeypatch.undo()

    # 2. Clean run up to 2025-10-10, then test zero_champion_mae_denominator_undefined guard directly
    # with real ADWIN trigger + 35 exact 0.0-error valid pairs.
    clean_res = run_final_replay(
        prepared,
        labels,
        initial_model_artifact_dir=stage04_dir,
        output_root=tmp_path / "policy-clean-zero",
        config=policy_cfg,
        replay_end_date=replay_end,
    )
    ckpt = joblib.load(clean_res.artifact_dir / "checkpoints" / "committed" / "2025-10-10" / "checkpoint.joblib")
    p_state = policy_mod.restore_policy_state(
        ckpt["policy_state"],
        policy_cfg=policy_cfg.champion_challenger,
        adwin_hash_fn=replay_pipeline._adwin_state_sha256,
    )
    for _ in range(30):
        p_state.policy_adwin["SPY"].update(0.01)
    probe = deepcopy(p_state.policy_adwin["SPY"])
    high_err = 1.50
    pre_steps = 0
    while True:
        probe.update(high_err)
        if probe.drift_detected:
            break
        pre_steps += 1
        assert pre_steps < 50
    for _ in range(pre_steps):
        p_state.policy_adwin["SPY"].update(high_err)

    champ = p_state.active_champion["SPY"]
    p_state.paired_history["SPY"] = [
        {
            "prediction_date": date(2025, 9, 1) + timedelta(days=j),
            "target_end_date": date(2025, 9, 6) + timedelta(days=j),
            "evaluation_date": date(2025, 9, 6) + timedelta(days=j),
            "champion_version_id": champ["champion_version_id"],
            "champion_model_id": champ["model_id"],
            "champion_abs_error": 0.0,
            "shadow_b3_abs_error": 0.05,
        }
        for j in range(35)
    ]
    p_state.pending_forecasts = [
        {
            "policy_prediction_id": "zero-mae-trigger-served",
            "prediction_date": date(2025, 10, 12),
            "split": "test",
            "ticker": "SPY",
            "role": "SERVED_CHAMPION",
            "champion_version_id": champ["champion_version_id"],
            "model_id": champ["model_id"],
            "model_name": champ["model_name"],
            "is_frozen_snapshot": True,
            "model_version": champ["champion_version_id"],
            "state_sha256": champ["state_sha256"],
            "target_start_date": date(2025, 10, 13),
            "target_end_date": date(2025, 10, 17),
            "predicted_vol_annualized": 0.14,
            "run_id": "test-run",
        },
        {
            "policy_prediction_id": "zero-mae-trigger-shadow",
            "prediction_date": date(2025, 10, 12),
            "split": "test",
            "ticker": "SPY",
            "role": "SHADOW_B3",
            "champion_version_id": champ["champion_version_id"],
            "model_id": "B3",
            "model_name": "ONLINE_SGD",
            "is_frozen_snapshot": False,
            "model_version": "shadow",
            "state_sha256": "shadow",
            "target_start_date": date(2025, 10, 13),
            "target_end_date": date(2025, 10, 17),
            "predicted_vol_annualized": 0.19,
            "run_id": "test-run",
        },
    ]
    label_map = {
        (date(2025, 10, 12), "SPY"): {
            "target_start_date": date(2025, 10, 13),
            "target_end_date": date(2025, 10, 17),
            "target_obs_count": 5,
            "target_realized_vol_5d": 1.64,
            "is_label_mature": True,
            "target_version": "2.0.0",
        }
    }
    audit_map = {(date(2025, 10, 12), "SPY"): {"label_quality_passed": True}}
    # Make paired champion error on the trigger anchor also 0.0? Wait: trigger anchor has error 1.50,
    # so make p_state.paired_history contain only 0.0 and omit SHADOW_B3 on the trigger anchor so
    # all 35 valid paired comparisons have champion_abs_error == 0.0!
    p_state.pending_forecasts = [p_state.pending_forecasts[0]]
    _, _, decisions, _, _ = policy_mod.run_policy_evaluate_and_decide(
        p_state,
        session_date=date(2025, 10, 20),
        policy_cfg=policy_cfg.champion_challenger,
        experiment_id="exp-zero",
        run_id="run-zero",
        label_map=label_map,
        audit_map=audit_map,
        calendar_index={date(2025, 10, 20): 0, date(2025, 10, 21): 1},
        calendar_sessions=[date(2025, 10, 20), date(2025, 10, 21)],
    )
    assert len(decisions) == 1
    assert decisions[0]["decision_outcome"] == "invalid"
    assert decisions[0]["decision_reason"] == "zero_champion_mae_denominator_undefined"
    assert decisions[0]["relative_improvement"] is None
    assert decisions[0]["switched"] is False


def test_policy_multiple_labels_same_day_feed_order_and_single_decision(tmp_path: Path) -> None:
    from src.ml_replay import ReplayConfig, pipeline as replay_pipeline, policy as policy_mod, run_final_replay

    # Run a short policy replay up to 2025-10-08 so policy state is initialized, then feed 2 maturing
    # served/shadow pairs on the SAME evaluation_date cleanly in deterministic chronological order.
    replay_end = date(2025, 10, 8)
    prepared, labels, _ = _build_policy_test_dataset("no_drift", test_end_date=replay_end)
    stage04_dir = _quick_stage04_policy_artifact(prepared, labels, tmp_path / "stage04-multi")
    policy_cfg = ReplayConfig.from_yaml(policy_mode="champion_challenger")
    assert policy_cfg.champion_challenger is not None

    res = run_final_replay(
        prepared,
        labels,
        initial_model_artifact_dir=stage04_dir,
        output_root=tmp_path / "policy-multi",
        config=policy_cfg,
        replay_end_date=replay_end,
    )
    ckpt = joblib.load(res.artifact_dir / "checkpoints" / "committed" / "2025-10-08" / "checkpoint.joblib")
    p_state = policy_mod.restore_policy_state(
        ckpt["policy_state"],
        policy_cfg=policy_cfg.champion_challenger,
        adwin_hash_fn=replay_pipeline._adwin_state_sha256,
    )
    # Find exact step right before real ADWIN(delta=0.002) fires after 30 calm errors + regime shift.
    for _ in range(30):
        p_state.policy_adwin["SPY"].update(0.01)
    probe = deepcopy(p_state.policy_adwin["SPY"])
    high_err = 1.66
    pre_steps = 0
    while True:
        probe.update(high_err)
        if probe.drift_detected:
            break
        pre_steps += 1
        assert pre_steps < 50
    for _ in range(pre_steps):
        p_state.policy_adwin["SPY"].update(high_err)

    p_state.pending_forecasts = []
    label_map = {}
    audit_map = {}
    champ = p_state.active_champion["SPY"]
    for j in range(30):
        p_state.paired_history["SPY"].append(
            {
                "prediction_date": date(2025, 9, 1) + timedelta(days=j),
                "target_end_date": date(2025, 9, 6) + timedelta(days=j),
                "evaluation_date": date(2025, 9, 6) + timedelta(days=j),
                "champion_version_id": champ["champion_version_id"],
                "champion_model_id": champ["model_id"],
                "champion_abs_error": 1.0,
                "shadow_b3_abs_error": 0.1,
            }
        )
    for idx, d in enumerate((date(2025, 10, 9), date(2025, 10, 10))):
        t_start = date(2025, 10, 10) if idx == 0 else date(2025, 10, 13)
        t_end = date(2025, 10, 17)
        for role in ("SERVED_CHAMPION", "SHADOW_B3"):
            p_state.pending_forecasts.append(
                {
                    "policy_prediction_id": f"p-{idx}-{role}",
                    "prediction_date": d,
                    "split": "test",
                    "ticker": "SPY",
                    "role": role,
                    "champion_version_id": champ["champion_version_id"],
                    "model_id": champ["model_id"] if role == "SERVED_CHAMPION" else "B3",
                    "model_name": champ["model_name"] if role == "SERVED_CHAMPION" else "ONLINE_SGD",
                    "is_frozen_snapshot": role == "SERVED_CHAMPION",
                    "model_version": champ["champion_version_id"],
                    "state_sha256": champ["state_sha256"],
                    "target_start_date": t_start,
                    "target_end_date": t_end,
                    "predicted_vol_annualized": 0.14 if role == "SERVED_CHAMPION" else 1.80,
                    "run_id": "test-run",
                }
            )
        label_map[(d, "SPY")] = {
            "target_start_date": t_start,
            "target_end_date": t_end,
            "target_obs_count": 5,
            "target_realized_vol_5d": 1.80,
            "is_label_mature": True,
            "target_version": "2.0.0",
        }
        audit_map[(d, "SPY")] = {"label_quality_passed": True}

    evals, stream, decisions, _, _ = policy_mod.run_policy_evaluate_and_decide(
        p_state,
        session_date=date(2025, 10, 20),
        policy_cfg=policy_cfg.champion_challenger,
        experiment_id="exp-multi",
        run_id="run-multi",
        label_map=label_map,
        audit_map=audit_map,
        calendar_index={date(2025, 10, 20): 0, date(2025, 10, 21): 1},
        calendar_sessions=[date(2025, 10, 20), date(2025, 10, 21)],
    )
    assert len(evals) == 4
    spy_stream = [row for row in stream if row["ticker"] == "SPY"]
    assert [row["feed_order_in_session"] for row in spy_stream] == [1, 2]
    assert [row["prediction_date"] for row in spy_stream] == [date(2025, 10, 9), date(2025, 10, 10)]
    assert spy_stream[0]["drift_detected"] is True
    assert spy_stream[0]["triggered_decision"] is True
    assert spy_stream[1]["triggered_decision"] is False
    assert len(decisions) == 1
    assert decisions[0]["decision_outcome"] == "promoted"
