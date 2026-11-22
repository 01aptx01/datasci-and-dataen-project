from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
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
