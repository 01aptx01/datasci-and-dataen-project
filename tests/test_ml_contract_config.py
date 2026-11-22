from __future__ import annotations

import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]

EXPECTED_MODELS = {
    "B0": "CONSTANT_BASELINE",
    "B1": "ROLLING_20D_BASELINE",
    "B2": "STATIC_SGD",
    "B3": "ONLINE_SGD",
    "B4": "HAR_X_OLS",
}

CORE_FEATURES = [
    "ret_1d_t",
    "ret_lag_1d",
    "ret_lag_2d",
    "ret_trailing_5d",
    "ret_trailing_20d",
    "rv_5d",
    "rv_20d",
    "rv_60d",
]


def _load_yaml(path: Path) -> dict:
    assert path.is_file(), f"Required Stage 01 config is missing: {path}"
    with path.open(encoding="utf-8") as file:
        return yaml.safe_load(file)


def test_model_config_defines_locked_b0_through_b3_policies() -> None:
    config = _load_yaml(ROOT / "config" / "models.yaml")

    assert config["models"] == [
        {
            "model_id": "B0",
            "model_name": "CONSTANT_BASELINE",
            "strategy": "train_mean_per_etf",
        },
        {
            "model_id": "B1",
            "model_name": "ROLLING_20D_BASELINE",
            "strategy": "feature_value",
            "feature": "rv_20d",
        },
        {
            "model_id": "B2",
            "model_name": "STATIC_SGD",
            "strategy": "sgd",
            "update_policy": "frozen_after_initial_fit",
        },
        {
            "model_id": "B3",
            "model_name": "ONLINE_SGD",
            "strategy": "sgd",
            "update_policy": "partial_fit_mature_labels_only",
        },
        {
            "model_id": "B4",
            "model_name": "HAR_X_OLS",
            "strategy": "ols",
            "update_policy": "frozen_after_initial_fit",
        },
    ]
    assert config["sgd"]["estimator"] == "SGDRegressor"
    assert config["sgd"]["features"] == CORE_FEATURES
    assert config["sgd"]["scaler"] == "RobustScaler"
    assert config["sgd"]["scaler_fit_scope"] == "train_only_per_etf"
    assert config["sgd"]["shared_initial_state_models"] == ["B2", "B3"]
    assert config["online_replay"]["order"] == [
        "predict",
        "save_forecast",
        "evaluate",
        "update_b3",
        "checkpoint",
    ]
    assert config["online_replay"]["update_model"] == "B3"
    assert config["online_replay"]["update_policy"] == "mature_labels_only"
    assert config["online_replay"]["duplicate_updates_allowed"] is False
    assert "adwin" not in config["online_replay"]


def test_hypothesis_config_freezes_h1_h2_h3_methods_before_test() -> None:
    config = _load_yaml(ROOT / "config" / "hypothesis_tests.yaml")

    assert config["alpha"] == 0.05
    assert config["alternative"] == "greater"
    assert config["data_cutoff"] == "2026-09-25"
    assert config["confidence_interval"]["level"] == 0.95
    assert config["confidence_interval"]["sided"] == "two-sided"
    assert config["holm_families"] == {
        "H1": ["SPY", "IEF", "GLD"],
        "H2_H3": ["H2", "H3"],
    }

    h1 = config["hypotheses"]["H1"]
    assert h1["split"] == "train"
    assert h1["method"] == "ols_hac"
    assert h1["hac_maxlags"] == 5
    assert h1["hac_sensitivity_maxlags"] == [10, 20]

    for hypothesis_id in ("H2", "H3"):
        hypothesis = config["hypotheses"][hypothesis_id]
        assert hypothesis["split"] == "test"
        assert hypothesis["model"] == "B3"
        assert hypothesis["method"] == "synchronized_moving_block_bootstrap"
        assert hypothesis["paired_by"] == ["prediction_date", "ticker"]
        assert hypothesis["bootstrap"]["block_length_xnys_sessions"] == 10
        assert hypothesis["bootstrap"]["replicates"] == 2000
        assert hypothesis["bootstrap"]["seed"] == 42
        assert hypothesis["bootstrap"]["sensitivity_block_lengths"] == [5, 20]

    assert config["hypotheses"]["H2"]["baseline"] == "B2"
    assert config["hypotheses"]["H3"]["baseline"] == "B1"
    assert config["test_tuning_allowed"] is False


def test_contracts_and_data_dictionary_use_the_same_four_model_ids() -> None:
    prediction_contract = (ROOT / "docs" / "contract" / "prediction_contract.md").read_text(
        encoding="utf-8"
    )
    feature_contract = (ROOT / "docs" / "contract" / "feature_contract.md").read_text(
        encoding="utf-8"
    )
    data_dictionary = (ROOT / "docs" / "contract" / "datadict.md").read_text(
        encoding="utf-8"
    )

    prediction_model_section = prediction_contract.split("### 1.1", maxsplit=1)[1].split(
        "## 2.", maxsplit=1
    )[0]
    for model_id, model_name in EXPECTED_MODELS.items():
        assert model_name in prediction_model_section
        assert f"**{model_id}**" in prediction_model_section
        assert model_name in data_dictionary

    assert re.search(r"\*\*B2[^*\r\n]*Static SGDRegressor:", feature_contract)
    assert re.search(r"\*\*B3[^*\r\n]*Online SGDRegressor:", feature_contract)

    replay_order = (
        "Predict → Save Forecast → Evaluate Mature Labels → "
        "Update B3 → Checkpoint"
    )
    assert replay_order in prediction_contract
    assert replay_order in (ROOT / "docs" / "contract" / "target_contract.md").read_text(
        encoding="utf-8"
    )

    expected_logical_tables = {
        "market_prices_daily",
        "asset_volatility_features",
        "asset_volatility_labels",
        "asset_rolling_correlations",
        "asset_volatility_predictions",
    }
    table_summary = data_dictionary.split("## สรุป 5 ตารางหลัก", maxsplit=1)[1].split(
        "### มาตรฐานร่วม", maxsplit=1
    )[0]
    assert {table for table in expected_logical_tables if f"`{table}`" in table_summary} == (
        expected_logical_tables
    )
    for table, expected_count in {
        "asset_volatility_predictions": 16,
        "asset_volatility_labels": 12,
    }.items():
        columns = re.findall(
            rf"^\| `{table}` \| `([^`]+)` \|", data_dictionary, flags=re.MULTILINE
        )
        assert len(columns) == expected_count


def test_champion_challenger_policy_config_and_contract_preserve_baseline(
    tmp_path: Path,
) -> None:
    import pytest

    from src.ml_replay.config import ReplayConfig, ReplayError

    baseline_cfg = ReplayConfig.from_yaml(ROOT / "config" / "ml_replay.yaml")
    assert baseline_cfg.replay_config_version == "1.1.0"
    assert not hasattr(baseline_cfg, "adwin_policy")
    assert "adwin" not in baseline_cfg.as_dict()
    assert baseline_cfg.processing_order == (
        "predict", "save_forecast", "evaluate", "update_b3", "checkpoint_commit"
    )
    assert baseline_cfg.is_champion_challenger is False
    assert baseline_cfg.champion_challenger is None
    assert len(baseline_cfg.fingerprint()) == 64

    policy_cfg = ReplayConfig.from_yaml(
        ROOT / "config" / "ml_replay.yaml",
        policy_mode="champion_challenger",
    )
    assert policy_cfg.replay_config_version == "2.1.0"
    assert not hasattr(policy_cfg, "adwin_policy")
    assert "adwin_monitor" not in policy_cfg.processing_order
    assert policy_cfg.champion_challenger.as_dict()["adwin"]["detector"] == "ADWIN"
    assert policy_cfg.is_champion_challenger is True
    assert policy_cfg.champion_challenger is not None
    assert policy_cfg.champion_challenger.policy_version == "1.0.0"
    assert policy_cfg.champion_challenger.candidate_order == ("B0", "B1", "B2")
    assert policy_cfg.champion_challenger.challenger_model == "B3"
    assert policy_cfg.champion_challenger.comparison_window_pairs == 60
    assert policy_cfg.champion_challenger.minimum_pairs == 30
    assert policy_cfg.champion_challenger.min_relative_improvement == 0.05
    assert policy_cfg.champion_challenger.cooldown_sessions == 20
    assert policy_cfg.champion_challenger.snapshot_timing == "pre_update_decision_time"
    assert policy_cfg.champion_challenger.effective_timing == "next_session"
    assert policy_cfg.fingerprint() != baseline_cfg.fingerprint()
    assert len(policy_cfg.champion_challenger.fingerprint()) == 64

    policy_contract = (
        ROOT / "docs" / "contract" / "champion_challenger_policy_contract.md"
    ).read_text(encoding="utf-8")
    assert "Exploratory / Retrospective Policy Specification" in policy_contract
    assert "No alteration of B0–B4 or H1–H3" in policy_contract
    assert "point_in_time_source_availability_verified" in policy_contract

    raw_replay = (ROOT / "config" / "ml_replay.yaml").read_text(encoding="utf-8")
    bad_window = tmp_path / "bad_window.yaml"
    bad_window.write_text(
        raw_replay.replace("window_pairs: 60", "window_pairs: 20", 1),
        encoding="utf-8",
    )
    with pytest.raises(ReplayError, match="1 <= min <= window"):
        ReplayConfig.from_yaml(bad_window, policy_mode="champion_challenger")

    bad_improvement = tmp_path / "bad_improvement.yaml"
    bad_improvement.write_text(
        raw_replay.replace("min_relative_improvement: 0.05", "min_relative_improvement: 0.0", 1),
        encoding="utf-8",
    )
    with pytest.raises(ReplayError, match="finite and positive"):
        ReplayConfig.from_yaml(bad_improvement, policy_mode="champion_challenger")


def test_b2_equals_b3_before_update_diverges_after_validation_update_and_ignores_test_labels() -> None:
    from datetime import date

    import numpy as np

    from src.ml_training import CandidateConfig, TrainingConfig, evaluate_candidate
    from tests.test_ml_training import _synthetic_prepared

    prepared, labels = _synthetic_prepared()
    candidate = CandidateConfig(eta0=0.001, alpha=1e-4, max_iter=20)
    eval_clean = evaluate_candidate(prepared, labels, ticker="SPY", candidate=candidate)

    labels_tampered_test = labels.copy()
    labels_tampered_test.loc[
        labels_tampered_test["date"] >= date(2025, 10, 1),
        "target_realized_vol_5d",
    ] = 9999.0
    eval_tampered = evaluate_candidate(
        prepared,
        labels_tampered_test,
        ticker="SPY",
        candidate=candidate,
    )

    assert eval_clean.final_b2_state_sha256 == eval_clean.initial_state_sha256
    assert len(eval_clean.update_events) > 0
    assert all(key[0] < date(2025, 10, 1) for key in eval_clean.updated_label_keys)

    first_row = eval_clean.predictions.iloc[0]
    later_row = eval_clean.predictions.iloc[-1]
    assert first_row["model_state_sha256_before_prediction"] == eval_clean.initial_state_sha256
    assert np.isclose(
        first_row["b2_prediction_raw"],
        first_row["b3_prediction_raw"],
        atol=1e-15,
        rtol=0.0,
    )
    assert later_row["model_state_sha256_before_prediction"] != eval_clean.initial_state_sha256
    assert not np.isclose(
        later_row["b2_prediction_raw"],
        later_row["b3_prediction_raw"],
        atol=1e-12,
        rtol=0.0,
    )
    assert eval_clean.updated_label_keys == eval_tampered.updated_label_keys
    assert eval_clean.b2_mae == eval_tampered.b2_mae
    assert eval_clean.b3_mae == eval_tampered.b3_mae
    assert eval_clean.predictions.equals(eval_tampered.predictions)
    assert TrainingConfig.from_yaml().initial_champion is not None

