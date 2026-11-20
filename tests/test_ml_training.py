from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pandas_market_calendars as market_calendars
import pytest
from sklearn.linear_model import SGDRegressor

from src.features.pipeline import CORE_FEATURE_COLUMNS, SUPPORTED_TICKERS
from src.ml_dataset.dataset import DatasetView, PreparationReport, PreparedDataset
from src.ml_training import (
    CandidateConfig,
    TrainingConfig,
    TrainingError,
    evaluate_candidate,
    model_state_sha256,
    predict_baselines,
    run_training_selection,
)
from src.ml_training import pipeline as training_pipeline


def _next_xnys_session(anchor: date, offset: int) -> date:
    end = anchor + timedelta(days=20)
    sessions = market_calendars.get_calendar("XNYS").schedule(
        start_date=anchor + timedelta(days=1), end_date=end
    ).index
    return sessions[offset - 1].date()


def _synthetic_prepared() -> tuple[PreparedDataset, pd.DataFrame]:
    train_dates = [
        date(2024, 9, 17),
        date(2024, 9, 18),
        date(2024, 9, 19),
        date(2024, 9, 20),
        date(2024, 9, 23),
        date(2024, 9, 24),  # Purged at the Train/Validation boundary; matures on Oct 1.
    ]
    validation_dates = [date(2024, 10, 1), date(2024, 10, 2), date(2024, 10, 3)]
    test_dates = [date(2025, 10, 1)]
    rows: list[dict[str, object]] = []
    label_rows: list[dict[str, object]] = []
    supervised_keys: set[tuple[date, str]] = set()

    for ticker_index, ticker in enumerate(SUPPORTED_TICKERS):
        for split, anchors in (
            ("train", train_dates),
            ("validation", validation_dates),
            ("test", test_dates),
        ):
            for index, anchor in enumerate(anchors):
                fixed_purged = split == "train" and anchor == date(2024, 9, 24)
                target_end = _next_xnys_session(anchor, 5)
                target = (
                    0.12 + ticker_index * 0.01 + index * 0.001
                    if split == "train"
                    else 0.14 + ticker_index * 0.01 + index * 0.001
                    if split == "validation"
                    else 25.0
                )
                feature_values = {
                    name: 0.01 + ticker_index * 0.0001 + index * 0.00001
                    for name in CORE_FEATURE_COLUMNS
                }
                feature_values["rv_20d"] = 0.2 + index * 0.01
                if split == "test":
                    feature_values = {name: 9999.0 for name in CORE_FEATURE_COLUMNS}
                rows.append(
                    {
                        "date": anchor,
                        "ticker": ticker,
                        **feature_values,
                        "split": split,
                        "target_end_date": target_end,
                        "is_label_mature": True,
                        "target_obs_count": 5,
                        "feature_quality_passed": True,
                        "label_quality_passed": True,
                        "prediction_eligible": True,
                        "supervised_eligible": split != "train" or not fixed_purged,
                        "fixed_purged": fixed_purged,
                        "online_update_eligible": True,
                        "already_updated": False,
                        "exclusion_reasons": ("fixed_split_purge",) if fixed_purged else (),
                    }
                )
                label_rows.append(
                    {
                        "date": anchor,
                        "ticker": ticker,
                        "target_end_date": target_end,
                        "target_obs_count": 5,
                        "target_realized_vol_5d": target,
                        "is_label_mature": True,
                    }
                )
                if split != "train" or not fixed_purged:
                    supervised_keys.add((anchor, ticker))

    ordered = sorted(rows, key=lambda row: (row["ticker"], row["date"]))
    metadata_columns = [
        "date",
        "ticker",
        "split",
        "target_end_date",
        "is_label_mature",
        "target_obs_count",
        "feature_quality_passed",
        "label_quality_passed",
        "prediction_eligible",
        "supervised_eligible",
        "fixed_purged",
        "online_update_eligible",
        "already_updated",
        "exclusion_reasons",
    ]
    metadata = pd.DataFrame(ordered).loc[:, metadata_columns].reset_index(drop=True)
    X = pd.DataFrame(ordered).loc[:, list(CORE_FEATURE_COLUMNS)].reset_index(drop=True)
    audit = metadata.copy()
    supervised_mask = [
        (row["date"], row["ticker"]) in supervised_keys for row in ordered
    ]
    supervised_metadata = metadata.loc[supervised_mask].reset_index(drop=True)
    supervised_X = X.loc[supervised_mask].reset_index(drop=True)
    target_lookup = {
        (row["date"], row["ticker"]): row["target_realized_vol_5d"] for row in label_rows
    }
    supervised_y = pd.Series(
        [target_lookup[(row.date, row.ticker)] for row in supervised_metadata.itertuples()],
        name="target_realized_vol_5d",
        dtype="float64",
    )
    prepared = PreparedDataset(
        prediction=DatasetView(X=X, metadata=metadata),
        supervised=DatasetView(X=supervised_X, metadata=supervised_metadata, y=supervised_y),
        audit=audit,
        report=PreparationReport(
            summary={"as_of_date": "2026-09-25", "data_cutoff": "2026-09-25"},
            counts_by_ticker_split_reason=pd.DataFrame(),
            lineage={"source_snapshot_id": "synthetic-source-snapshot"},
            versions={"feature": ["2.0.0"], "target": ["2.0.0"]},
            limitations=("synthetic test fixture",),
        ),
    )
    return prepared, pd.DataFrame(label_rows)


def test_training_config_locks_grid_and_deterministic_selection_rules() -> None:
    config = TrainingConfig.from_yaml()

    assert len(config.grid) == 27
    assert {item.eta0 for item in config.grid} == {0.0001, 0.001, 0.01}
    assert {item.alpha for item in config.grid} == {1e-5, 1e-4, 1e-3}
    assert {item.max_iter for item in config.grid} == {20, 50, 100}
    assert config.coverage_policy == "all_expected_paired_anchors_required"
    assert config.tie_break_policy == "grid_order_with_absolute_tolerance"
    assert config.tie_tolerance == 1e-12


def test_b0_uses_frozen_train_mean_and_b1_reads_same_day_rv20() -> None:
    features = pd.DataFrame(
        [
            {"date": date(2025, 1, 2), "ticker": "SPY", "rv_20d": 0.21},
            {"date": date(2025, 1, 2), "ticker": "IEF", "rv_20d": 0.08},
        ]
    )
    baselines = {
        "SPY": {"b0_train_mean": 0.12},
        "IEF": {"b0_train_mean": 0.05},
    }

    result = predict_baselines(features, baselines)

    assert result.set_index(["ticker", "model_id"])["predicted_vol_annualized"].to_dict() == {
        ("SPY", "B0"): 0.12,
        ("SPY", "B1"): 0.21,
        ("IEF", "B0"): 0.05,
        ("IEF", "B1"): 0.08,
    }


def test_validation_candidate_predicts_before_mature_updates_and_never_updates_test() -> None:
    prepared, labels = _synthetic_prepared()
    evaluation = evaluate_candidate(
        prepared,
        labels,
        ticker="SPY",
        candidate=CandidateConfig(eta0=0.001, alpha=1e-4, max_iter=20),
    )

    first_day = evaluation.predictions.loc[
        evaluation.predictions["prediction_date"] == date(2024, 10, 1)
    ].iloc[0]
    first_update = evaluation.update_events.iloc[0]
    assert first_day["model_state_sha256_before_prediction"] == evaluation.initial_state_sha256
    assert first_update["replay_date"] == date(2024, 10, 1)
    assert first_update["anchor_date"] == date(2024, 9, 24)
    assert first_update["target_end_date"] <= first_update["replay_date"]
    assert evaluation.predictions["prediction_date"].max() < date(2025, 10, 1)
    assert (evaluation.update_events["target_end_date"] <= evaluation.update_events["replay_date"]).all()
    assert evaluation.updated_label_keys == tuple(dict.fromkeys(evaluation.updated_label_keys))
    assert set(evaluation.updated_label_keys).isdisjoint(
        {(date(2025, 10, 1), ticker) for ticker in SUPPORTED_TICKERS}
    )
    assert evaluation.duplicate_update_count == 0
    assert len(evaluation.updated_label_keys) > 0


def test_negative_predictions_remain_invalid_and_block_candidate_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared, labels = _synthetic_prepared()
    monkeypatch.setattr(
        SGDRegressor,
        "predict",
        lambda self, features: np.full(len(features), -0.25),
    )

    evaluation = evaluate_candidate(
        prepared,
        labels,
        ticker="SPY",
        candidate=CandidateConfig(eta0=0.001, alpha=1e-4, max_iter=20),
    )

    assert not evaluation.admissible
    assert evaluation.failure_reason == "INCOMPLETE_PAIRED_VALIDATION_COVERAGE"
    assert evaluation.b2_invalid_count == evaluation.expected_anchor_count
    assert evaluation.b3_invalid_count == evaluation.expected_anchor_count
    assert evaluation.paired_anchor_count == 0
    assert evaluation.predictions["b2_prediction_raw"].eq(-0.25).all()
    assert evaluation.predictions["b3_prediction_raw"].eq(-0.25).all()


def test_run_selection_saves_all_trials_and_clean_same_state_pairs(tmp_path: Path) -> None:
    prepared, labels = _synthetic_prepared()

    result = run_training_selection(
        prepared,
        labels,
        artifact_dir=tmp_path / "training-run",
    )

    assert len(result.candidate_evaluations) == 81
    assert result.candidate_evaluations.groupby("ticker").size().to_dict() == {
        ticker: 27 for ticker in SUPPORTED_TICKERS
    }
    assert len(result.selected_configs) == 3
    assert result.selected_configs["ticker"].tolist() == list(SUPPORTED_TICKERS)
    assert result.candidate_evaluations["admissible"].all()
    assert result.candidate_evaluations["paired_coverage"].eq(1.0).all()
    assert result.candidate_evaluations["b2_state_unchanged"].all()
    assert result.candidate_evaluations["b3_update_count"].gt(0).all()
    assert np.allclose(
        result.candidate_evaluations["joint_mae_validation"],
        (
            result.candidate_evaluations["mae_b2_validation"]
            + result.candidate_evaluations["mae_b3_validation"]
        )
        / 2,
    )

    for ticker, pair in result.initial_models.items():
        assert pair["b2"] is not pair["b3"]
        assert model_state_sha256(pair["b2"], pair["scaler"]) == pair["state_sha256"]
        assert model_state_sha256(pair["b3"], pair["scaler"]) == pair["state_sha256"]
        selected = result.selected_configs.loc[result.selected_configs["ticker"] == ticker].iloc[0]
        assert pair["state_sha256"] == selected["initial_state_sha256"]
        ticker_train = (prepared.supervised.metadata["split"] == "train") & (
            prepared.supervised.metadata["ticker"] == ticker
        )
        expected_center = np.median(
            prepared.supervised.X.loc[ticker_train].to_numpy(dtype=float), axis=0
        )
        assert np.allclose(pair["scaler"].center_, expected_center)
        assert result.baselines[ticker]["b0_train_mean"] > 0
        assert result.baselines[ticker]["b0_train_row_count"] == 5
        assert result.baselines[ticker]["b1_feature"] == "rv_20d"

    output = tmp_path / "training-run"
    assert (output / "validation_candidate_evaluations.csv").is_file()
    assert (output / "selected_configs.json").is_file()
    assert (output / "initial_models.joblib").is_file()
    assert (output / "training_manifest.json").is_file()
    manifest = json.loads((output / "training_manifest.json").read_text(encoding="utf-8"))
    assert manifest["point_in_time_source_availability_verified"] is False
    assert manifest["limitations"] == ["synthetic test fixture"]
    for file_name, expected_hash in manifest["artifact_sha256"].items():
        actual_hash = hashlib.sha256((output / file_name).read_bytes()).hexdigest()
        assert actual_hash == expected_hash
    saved_models = joblib.load(output / "initial_models.joblib")
    assert set(saved_models["tickers"]) == set(SUPPORTED_TICKERS)


def test_failed_selection_still_saves_candidate_audit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared, labels = _synthetic_prepared()
    output = tmp_path / "failed-training-run"

    def reject_selection(candidate_rows: pd.DataFrame, config: TrainingConfig) -> pd.DataFrame:
        raise TrainingError("SPY has no candidate with complete paired Validation coverage")

    monkeypatch.setattr(training_pipeline, "_select_configs", reject_selection)

    with pytest.raises(TrainingError, match="Validation audit saved"):
        run_training_selection(prepared, labels, artifact_dir=output)

    trials = pd.read_csv(output / "validation_candidate_evaluations.csv")
    manifest = json.loads((output / "training_manifest.json").read_text(encoding="utf-8"))
    assert len(trials) == 81
    assert manifest["selection_status"] == "failed_no_admissible_candidate"
    assert "SPY has no candidate" in manifest["selection_failures"][0]
    assert manifest["initial_state_sha256_by_ticker"] == {}
