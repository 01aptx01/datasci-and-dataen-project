from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pandas_market_calendars as market_calendars
import pytest
from sklearn.linear_model import LinearRegression, SGDRegressor

from src.features.pipeline import CORE_FEATURE_COLUMNS, SUPPORTED_TICKERS
from src.ml_dataset.dataset import DatasetView, PreparationReport, PreparedDataset
from src.ml_training import (
    B4_MODEL_ID,
    B4_MODEL_NAME,
    B4_MODEL_VERSION,
    CandidateConfig,
    TrainingConfig,
    TrainingError,
    b4_state_sha256,
    evaluate_b4_validation,
    evaluate_candidate,
    fit_b4_ols,
    model_state_sha256,
    predict_baselines,
    run_training_selection,
    scaler_state_sha256,
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

    assert config.training_config_version == "1.2.0"
    assert len(config.grid) == 27
    assert {item.eta0 for item in config.grid} == {0.0001, 0.001, 0.01}
    assert {item.alpha for item in config.grid} == {1e-5, 1e-4, 1e-3}
    assert {item.max_iter for item in config.grid} == {20, 50, 100}
    assert config.coverage_policy == "all_expected_paired_anchors_required"
    assert config.b4_estimator == "LinearRegression"
    assert config.b4_fit_intercept is True
    assert config.b4_ill_conditioned_threshold == 1e8
    assert config.tie_break_policy == "grid_order_with_absolute_tolerance"
    assert config.tie_tolerance == 1e-12
    assert config.initial_champion is not None
    assert config.initial_champion.policy_version == "1.0.0"
    assert config.initial_champion.candidate_models == ("B0", "B1", "B2")
    assert config.initial_champion.tie_break_order == ("B0", "B1", "B2")
    assert config.initial_champion.scoring_split == "validation"
    assert config.initial_champion.cutover_date == date(2025, 10, 1)
    assert config.initial_champion.minimum_paired_coverage == 1.0
    assert config.initial_champion.minimum_cutover_anchors == 1
    assert config.initial_champion.tie_tolerance == 1e-12
    assert len(config.fingerprint()) == 64
    assert len(config.initial_champion.fingerprint()) == 64


def test_initial_champion_config_rejects_excluded_models_and_contract_overrides(
    tmp_path: Path,
) -> None:
    config_text = Path("config/ml_training.yaml").read_text(encoding="utf-8")

    bad_candidates = tmp_path / "bad_candidates.yaml"
    bad_candidates.write_text(
        config_text.replace("candidate_models: [B0, B1, B2]", "candidate_models: [B0, B1, B2, B3]", 1),
        encoding="utf-8",
    )
    with pytest.raises(TrainingError, match="B3 and B4 are excluded"):
        TrainingConfig.from_yaml(bad_candidates)

    bad_split = tmp_path / "bad_split.yaml"
    bad_split.write_text(
        config_text.replace("  scoring_split: validation", "  scoring_split: test", 1),
        encoding="utf-8",
    )
    with pytest.raises(TrainingError, match="Validation only"):
        TrainingConfig.from_yaml(bad_split)

    missing_section = tmp_path / "missing_section.yaml"
    missing_section.write_text(
        config_text.split("initial_champion:", maxsplit=1)[0],
        encoding="utf-8",
    )
    with pytest.raises(TrainingError, match="requires an initial_champion section"):
        TrainingConfig.from_yaml(missing_section)


def test_b4_fit_intercept_config_requires_a_boolean(tmp_path: Path) -> None:
    config_text = Path("config/ml_training.yaml").read_text(encoding="utf-8")
    invalid_path = tmp_path / "invalid_b4_config.yaml"
    invalid_path.write_text(
        config_text.replace("fit_intercept: true", 'fit_intercept: "false"', 1),
        encoding="utf-8",
    )

    with pytest.raises(TrainingError, match="b4_fit_intercept must be a boolean"):
        TrainingConfig.from_yaml(invalid_path)


def test_training_config_accepts_legacy_version_but_requires_current_version_for_b4(
    tmp_path: Path,
) -> None:
    config_text = Path("config/ml_training.yaml").read_text(encoding="utf-8")
    legacy_path = tmp_path / "legacy_ml_training.yaml"
    legacy_path.write_text(
        config_text.replace('training_config_version: "1.2.0"', 'training_config_version: "1.0.0"', 1),
        encoding="utf-8",
    )
    legacy_config = TrainingConfig.from_yaml(legacy_path)

    assert legacy_config.training_config_version == "1.0.0"

    b4_path = tmp_path / "b4_ml_training.yaml"
    b4_path.write_text(
        config_text.replace('training_config_version: "1.2.0"', 'training_config_version: "1.1.0"', 1),
        encoding="utf-8",
    )
    b4_config = TrainingConfig.from_yaml(b4_path)
    assert b4_config.training_config_version == "1.1.0"

    prepared, labels = _synthetic_prepared_b4()
    with pytest.raises(TrainingError, match="1.0.0 predates B4"):
        fit_b4_ols(prepared, "SPY", legacy_config)
    with pytest.raises(TrainingError, match="1.0.0 predates B4"):
        run_training_selection(prepared, labels, config=legacy_config, include_b4=True)

    current_config = TrainingConfig.from_yaml()
    artifact = fit_b4_ols(prepared, "SPY", current_config)
    legacy_evaluation_config = replace(current_config, training_config_version="1.0.0")
    summary, _ = evaluate_b4_validation(
        prepared,
        "SPY",
        artifact,
        legacy_evaluation_config,
    )
    assert summary["valid_count"] == summary["expected_anchor_count"]


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
        include_b4=False,
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


def _synthetic_prepared_b4(
    *,
    n_train: int = 16,
    collinear: bool = False,
    ill_conditioned: bool = False,
) -> tuple[PreparedDataset, pd.DataFrame]:
    rng = np.random.default_rng(12345)
    train_sessions = [
        stamp.date()
        for stamp in market_calendars.get_calendar("XNYS")
        .schedule(start_date="2024-08-01", end_date="2024-09-24")
        .index
    ]
    # Keep last session (2024-09-24) as fixed_purged; pick n_train - 1 earlier sessions + 2024-09-24.
    assert len(train_sessions) >= n_train
    train_dates = train_sessions[-(n_train):]
    validation_dates = [
        date(2024, 10, 1),
        date(2024, 10, 2),
        date(2024, 10, 3),
        date(2024, 10, 4),
    ]
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
                if collinear:
                    base_val = 0.01 + 0.001 * index + 0.0005 * ticker_index
                    feature_values = {name: base_val for name in CORE_FEATURE_COLUMNS}
                elif ill_conditioned and split == "train":
                    vec = rng.normal(0.0, 0.02, size=len(CORE_FEATURE_COLUMNS))
                    vec[1] = vec[0] + rng.normal(0.0, 1e-11)
                    feature_values = dict(zip(CORE_FEATURE_COLUMNS, vec))
                    feature_values["rv_20d"] = abs(feature_values["rv_20d"]) + 0.10
                else:
                    vec = rng.normal(0.0, 0.02, size=len(CORE_FEATURE_COLUMNS))
                    feature_values = dict(zip(CORE_FEATURE_COLUMNS, vec))
                    feature_values["rv_5d"] = abs(feature_values["rv_5d"]) + 0.10
                    feature_values["rv_20d"] = abs(feature_values["rv_20d"]) + 0.12
                    feature_values["rv_60d"] = abs(feature_values["rv_60d"]) + 0.13
                if split == "test":
                    feature_values = {name: 9999.0 for name in CORE_FEATURE_COLUMNS}
                target = (
                    float(0.14 + 0.3 * abs(feature_values["rv_20d"]) + 0.005 * ticker_index)
                    if split != "test"
                    else 25.0
                )
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
    supervised_mask = [(row["date"], row["ticker"]) in supervised_keys for row in ordered]
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
            lineage={"source_snapshot_id": "synthetic-b4-snapshot"},
            versions={"feature": ["2.0.0"], "target": ["2.0.0"]},
            limitations=("synthetic b4 fixture",),
        ),
    )
    return prepared, pd.DataFrame(label_rows)


def test_b4_fit_and_validation_matches_b2_sample_and_scaler(tmp_path: Path) -> None:
    prepared, labels = _synthetic_prepared_b4()
    run_with_b4 = run_training_selection(
        prepared,
        labels,
        artifact_dir=tmp_path / "run-b4-a",
        include_b4=True,
    )
    run_without_b4 = run_training_selection(
        prepared,
        labels,
        artifact_dir=tmp_path / "run-no-b4",
        include_b4=False,
    )
    run_rerun = run_training_selection(
        prepared,
        labels,
        artifact_dir=tmp_path / "run-b4-b",
        include_b4=True,
    )

    # B2/B3 selection must remain identical whether B4 runs or not.
    pd.testing.assert_frame_equal(run_with_b4.selected_configs, run_without_b4.selected_configs)
    pd.testing.assert_frame_equal(
        run_with_b4.candidate_evaluations, run_without_b4.candidate_evaluations
    )

    assert run_with_b4.b4_models is not None
    assert run_with_b4.b4_validation is not None
    bundle = joblib.load((tmp_path / "run-b4-a") / "initial_models.joblib")
    manifest = json.loads(((tmp_path / "run-b4-a") / "training_manifest.json").read_text("utf-8"))
    assert set(bundle["b4_models"]) == set(SUPPORTED_TICKERS)
    assert "b4_validation_evaluations.csv" in manifest["artifact_sha256"]

    for ticker in SUPPORTED_TICKERS:
        b2_entry = run_with_b4.initial_models[ticker]
        b4_entry = run_with_b4.b4_models[ticker]
        loaded_b4 = bundle["b4_models"][ticker]
        assert b4_entry["model_id"] == B4_MODEL_ID
        assert b4_entry["model_name"] == B4_MODEL_NAME
        assert b4_entry["model_version"] == B4_MODEL_VERSION
        assert tuple(b4_entry["feature_order"]) == tuple(CORE_FEATURE_COLUMNS)
        assert b4_entry["design_rank"] == 9
        assert b4_entry["last_training_target_end_date"] < date(2024, 10, 1)
        assert b4_entry["scaler_state_sha256"] == scaler_state_sha256(b2_entry["scaler"])
        assert b4_state_sha256(loaded_b4["model"], loaded_b4["scaler"]) == b4_entry["state_sha256"]
        assert loaded_b4["state_sha256"] == manifest["b4_models"][ticker]["state_sha256"]

        # Reloaded artifact predictions match in-memory fitted model & rerun within 1e-15.
        val_mask = (prepared.supervised.metadata["split"] == "validation") & (
            prepared.supervised.metadata["ticker"] == ticker
        )
        val_X = prepared.supervised.X.loc[val_mask]
        pred_mem = b4_entry["model"].predict(b4_entry["scaler"].transform(val_X))
        pred_disk = loaded_b4["model"].predict(loaded_b4["scaler"].transform(val_X))
        assert np.allclose(pred_mem, pred_disk, atol=1e-15, rtol=0.0)
        assert b4_entry["state_sha256"] == run_rerun.b4_models[ticker]["state_sha256"]


def test_b4_rejects_insufficient_train_rows() -> None:
    prepared, labels = _synthetic_prepared_b4(n_train=8)  # 7 eligible + 1 fixed_purged < 9
    with pytest.raises(TrainingError, match="at least 9 eligible Train rows"):
        fit_b4_ols(prepared, "SPY")


def test_b4_rejects_rank_deficient_design_matrix() -> None:
    prepared, labels = _synthetic_prepared_b4(n_train=14, collinear=True)
    with pytest.raises(TrainingError, match="rank-deficient"):
        fit_b4_ols(prepared, "SPY")


def test_b4_warns_on_ill_conditioned_design_matrix_without_failing() -> None:
    prepared, _ = _synthetic_prepared_b4(n_train=16, ill_conditioned=True)
    artifact = fit_b4_ols(prepared, "SPY")
    assert artifact["design_rank"] == 9
    assert artifact["ill_conditioned"] is True
    assert any("ill_conditioned" in msg for msg in artifact["warnings"])


def test_b4_rejects_non_finite_train_inputs() -> None:
    prepared, _ = _synthetic_prepared_b4(n_train=16)
    spy_train_idx = prepared.supervised.metadata.index[
        (prepared.supervised.metadata["split"] == "train")
        & (prepared.supervised.metadata["ticker"] == "SPY")
    ][0]
    prepared.supervised.X.loc[spy_train_idx, "rv_5d"] = np.nan
    with pytest.raises(TrainingError, match="must be finite"):
        fit_b4_ols(prepared, "SPY")


def test_b4_validation_rejects_negative_forecasts_without_clipping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared, _ = _synthetic_prepared_b4(n_train=16)
    artifact = fit_b4_ols(prepared, "SPY")
    original_predict = LinearRegression.predict

    def predict_one_negative(self: LinearRegression, X: np.ndarray) -> np.ndarray:
        preds = original_predict(self, X).copy()
        preds[0] = -0.05
        return preds

    monkeypatch.setattr(LinearRegression, "predict", predict_one_negative)
    summary, rows = evaluate_b4_validation(prepared, "SPY", artifact)
    assert summary["expected_anchor_count"] == 4
    assert summary["valid_count"] == 3
    assert summary["invalid_count"] == 1
    assert summary["coverage"] == pytest.approx(0.75)
    assert len(summary["invalid_reasons"]) == 1
    assert rows.iloc[0]["raw_prediction"] == pytest.approx(-0.05)
    assert pd.isna(rows.iloc[0]["predicted_vol_annualized"])
    assert bool(rows.iloc[0]["forecast_valid"]) is False

    monkeypatch.setattr(
        LinearRegression,
        "predict",
        lambda self, X: np.full(len(X), -0.1),
    )
    with pytest.raises(TrainingError, match="zero valid Validation forecasts"):
        evaluate_b4_validation(prepared, "SPY", artifact)
