from __future__ import annotations

import hashlib
import json
from datetime import date
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from src.ml_evaluation.hypotheses import (
    equal_weight_macro_mean,
    synchronized_moving_block_bootstrap,
)
from src.ml_evaluation.metrics import (
    aggregate_period_metrics,
    build_forecast_audit,
    calculate_error_metrics,
    rolling_session_metrics,
)
from src.ml_evaluation.portfolio import calculate_portfolio_risk
from src.ml_evaluation.config import EvaluationConfig, EvaluationError
from src.ml_evaluation.pipeline import (
    _build_b4_comparisons,
    _build_coverage_summary,
    _build_drift_error_timeline,
    _build_model_metrics,
    _build_pair_comparisons,
    _build_portfolio_risk_table,
    _build_reference_b0_b3_metrics,
    _mark_common_panel,
    _train_high_vol_thresholds,
    _verify_training_artifacts,
)


TICKERS = ("SPY", "IEF", "GLD")


def _training_artifact_lineage(tmp_path, *, include_b4_hash: bool, b4_suite: bool = True):
    artifact_names = [
        "initial_models.joblib",
        "selected_configs.json",
        "training_config.json",
        "validation_candidate_evaluations.csv",
        "b4_validation_evaluations.csv",
    ]
    artifact_hashes = {}
    for name in artifact_names:
        path = tmp_path / name
        path.write_text(f"artifact:{name}", encoding="utf-8")
        artifact_hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    training_manifest = {
        "selection_split": "validation",
        "test_used_for_training_or_selection": False,
        "selection_status": "selected",
        "selected_configs": [],
    }
    manifest_path = tmp_path / "training_manifest.json"
    manifest_path.write_text(json.dumps(training_manifest), encoding="utf-8")
    if not include_b4_hash:
        artifact_hashes.pop("b4_validation_evaluations.csv")
    replay_manifest = {
        "stage04_artifact_sha256": artifact_hashes,
        "stage04_training_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "selected_configs": [],
    }
    if b4_suite:
        replay_manifest["model_suite_version"] = "1.1.0"
        replay_manifest["b4_initial_state_sha256_by_ticker"] = {}
    return replay_manifest, artifact_hashes


def test_training_artifact_verification_requires_b4_validation_hash_for_b4_suite(tmp_path) -> None:
    replay_manifest, _ = _training_artifact_lineage(tmp_path, include_b4_hash=False)

    with pytest.raises(EvaluationError, match="b4_validation_evaluations.csv"):
        _verify_training_artifacts(tmp_path, replay_manifest)


def test_training_artifact_verification_includes_b4_validation_hash_for_b4_suite(tmp_path) -> None:
    replay_manifest, artifact_hashes = _training_artifact_lineage(tmp_path, include_b4_hash=True)

    verified = _verify_training_artifacts(tmp_path, replay_manifest)

    assert verified["b4_validation_evaluations.csv"] == artifact_hashes["b4_validation_evaluations.csv"]


def test_training_artifact_verification_preserves_legacy_b0_b3_lineage(tmp_path) -> None:
    replay_manifest, _ = _training_artifact_lineage(
        tmp_path,
        include_b4_hash=False,
        b4_suite=False,
    )

    verified = _verify_training_artifacts(tmp_path, replay_manifest)

    assert "b4_validation_evaluations.csv" not in verified


def test_forecast_audit_separates_pending_targets_from_invalid_forecasts() -> None:
    expected = pd.DataFrame(
        [
            {"prediction_date": date(2025, 10, 1), "ticker": "SPY", "split": "test"},
            {"prediction_date": date(2025, 10, 2), "ticker": "SPY", "split": "test"},
            {"prediction_date": date(2025, 10, 3), "ticker": "SPY", "split": "test"},
            {"prediction_date": date(2026, 9, 26), "ticker": "SPY", "split": "outside_study"},
        ]
    )
    labels = pd.DataFrame(
        [
            {
                "date": date(2025, 10, 1),
                "ticker": "SPY",
                "target_start_date": date(2025, 10, 2),
                "target_end_date": date(2025, 10, 8),
                "target_obs_count": 5,
                "target_realized_vol_5d": 0.20,
                "is_label_mature": True,
                "target_version": "2.0.0",
            },
            {
                "date": date(2025, 10, 2),
                "ticker": "SPY",
                "target_start_date": date(2025, 10, 3),
                "target_end_date": date(2026, 9, 30),
                "target_obs_count": 5,
                "target_realized_vol_5d": 0.25,
                "is_label_mature": True,
                "target_version": "2.0.0",
            },
            {
                "date": date(2025, 10, 3),
                "ticker": "SPY",
                "target_start_date": date(2025, 10, 6),
                "target_end_date": date(2025, 10, 10),
                "target_obs_count": 4,
                "target_realized_vol_5d": np.nan,
                "is_label_mature": False,
                "target_version": "2.0.0",
            },
        ]
    )
    predictions = pd.DataFrame(
        [
            {
                "prediction_id": "p1",
                "prediction_date": date(2025, 10, 1),
                "ticker": "SPY",
                "model_name": "STATIC_SGD",
                "predicted_vol_annualized": 0.10,
                "target_start_date": date(2025, 10, 2),
                "target_end_date": date(2025, 10, 8),
            },
            {
                "prediction_id": "p2",
                "prediction_date": date(2025, 10, 2),
                "ticker": "SPY",
                "model_name": "STATIC_SGD",
                "predicted_vol_annualized": 0.15,
                "target_start_date": date(2025, 10, 3),
                "target_end_date": date(2026, 9, 30),
            },
        ]
    )
    failures = pd.DataFrame(
        [
            {
                "prediction_date": date(2025, 10, 3),
                "ticker": "SPY",
                "model_name": "STATIC_SGD",
                "failure_type": "INVALID_PREDICTION_VALUE",
                "reason": "non_finite_prediction",
            }
        ]
    )

    audit = build_forecast_audit(
        expected,
        labels,
        predictions,
        failures,
        cutoff=date(2026, 9, 25),
        model_names=("STATIC_SGD",),
    ).set_index("prediction_date")

    assert set(audit.index) == {date(2025, 10, 1), date(2025, 10, 2), date(2025, 10, 3)}
    assert audit.loc[date(2025, 10, 1), "evaluation_status"] == "EVALUABLE"
    assert audit.loc[date(2025, 10, 1), "absolute_error"] == pytest.approx(0.10)
    assert audit.loc[date(2025, 10, 2), "label_status"] == "PENDING"
    assert audit.loc[date(2025, 10, 2), "evaluation_status"] == "PENDING_LABEL"
    assert audit.loc[date(2025, 10, 3), "forecast_status"] == "INVALID"
    assert audit.loc[date(2025, 10, 3), "evaluation_status"] == "INVALID_FORECAST"


def test_error_metrics_use_annualized_decimal_errors() -> None:
    metrics = calculate_error_metrics([0.10, 0.20], [0.20, 0.10])

    assert metrics["n"] == 2
    assert metrics["mae"] == pytest.approx(0.10)
    assert metrics["rmse"] == pytest.approx(0.10)


def test_yearly_aggregation_keeps_validation_and_test_separate() -> None:
    expected = pd.DataFrame(
        [
            {"prediction_date": date(2025, 8, 1), "ticker": "SPY", "split": "validation"},
            {"prediction_date": date(2025, 10, 1), "ticker": "SPY", "split": "test"},
        ]
    )
    evaluations = pd.DataFrame(
        [
            {
                "prediction_date": date(2025, 8, 1),
                "ticker": "SPY",
                "model_name": "ONLINE_SGD",
                "split": "validation",
                "target_realized_vol_5d": 0.20,
                "predicted_vol_annualized": 0.10,
            },
            {
                "prediction_date": date(2025, 10, 1),
                "ticker": "SPY",
                "model_name": "ONLINE_SGD",
                "split": "test",
                "target_realized_vol_5d": 0.20,
                "predicted_vol_annualized": 0.30,
            },
        ]
    )

    yearly = aggregate_period_metrics(expected, evaluations, period="year")

    assert len(yearly) == 2
    assert set(yearly["split"]) == {"validation", "test"}
    assert set(yearly["calendar_year"]) == {2025}
    assert yearly.set_index("split").loc["validation", "mae"] == pytest.approx(0.10)
    assert yearly.set_index("split").loc["test", "mae"] == pytest.approx(0.10)


def test_rolling_metrics_count_pending_sessions_without_scoring_them() -> None:
    sessions = [date(2025, 1, 1) + pd.Timedelta(days=index) for index in range(20)]
    expected = pd.DataFrame(
        [{"prediction_date": session, "ticker": "SPY", "split": "test"} for session in sessions]
    )
    evaluations = pd.DataFrame(
        [
            {
                "prediction_date": session,
                "ticker": "SPY",
                "model_name": "STATIC_SGD",
                "split": "test",
                "target_realized_vol_5d": 0.20,
                "predicted_vol_annualized": 0.15,
            }
            for session in sessions[:15]
        ]
    )

    rolling = rolling_session_metrics(
        expected,
        evaluations,
        {"test": sessions},
        window_size=20,
        minimum_evaluable=10,
    )

    assert len(rolling) == 1
    assert rolling.iloc[0]["window_session_count"] == 20
    assert rolling.iloc[0]["evaluable_count"] == 15
    assert rolling.iloc[0]["coverage"] == pytest.approx(0.75)
    assert rolling.iloc[0]["mae"] == pytest.approx(0.05)


def test_hypothesis_macro_effect_weights_each_etf_equally() -> None:
    macro = equal_weight_macro_mean({"SPY": 0.0, "IEF": 2.0, "GLD": 10.0})

    assert macro == pytest.approx(4.0)


def test_block_bootstrap_is_synchronized_and_seeded() -> None:
    sessions = [date(2025, 1, 1) + pd.Timedelta(days=index) for index in range(60)]
    base = np.arange(60, dtype=float) / 100.0
    rows = [
        {"prediction_date": session, "ticker": ticker, "difference": multiplier * value}
        for session, value in zip(sessions, base)
        for ticker, multiplier in zip(TICKERS, (1.0, 2.0, 3.0))
    ]
    differences = pd.DataFrame(rows)

    first = synchronized_moving_block_bootstrap(
        differences,
        sessions,
        block_length=10,
        replicates=100,
        seed=42,
        minimum_pairs_per_ticker=30,
    )
    second = synchronized_moving_block_bootstrap(
        differences,
        sessions,
        block_length=10,
        replicates=100,
        seed=42,
        minimum_pairs_per_ticker=30,
    )

    assert first.status == "COMPUTED"
    assert first.observed_delta == pytest.approx(float(np.mean(base) * 2.0))
    assert first.raw_p_value == second.raw_p_value
    assert np.array_equal(first.replicate_deltas, second.replicate_deltas)
    assert np.allclose(
        first.per_ticker_replicates["IEF"],
        first.per_ticker_replicates["SPY"] * 2.0,
    )
    assert np.allclose(
        first.per_ticker_replicates["GLD"],
        first.per_ticker_replicates["SPY"] * 3.0,
    )


def test_centered_bootstrap_p_value_uses_the_prespecified_one_sided_tail() -> None:
    sessions = [date(2025, 1, 1) + pd.Timedelta(days=index) for index in range(40)]
    differences = pd.DataFrame(
        [
            {"prediction_date": session, "ticker": ticker, "difference": 0.1}
            for session in sessions
            for ticker in TICKERS
        ]
    )

    result = synchronized_moving_block_bootstrap(
        differences,
        sessions,
        block_length=10,
        replicates=200,
        seed=42,
        minimum_pairs_per_ticker=30,
    )

    assert result.observed_delta == pytest.approx(0.1)
    assert result.raw_p_value == pytest.approx(1 / 201)
    assert result.ci_lower == pytest.approx(0.1)
    assert result.ci_upper == pytest.approx(0.1)


def test_bootstrap_reports_insufficient_evidence_when_an_etf_is_undercovered() -> None:
    sessions = [date(2025, 1, 1) + pd.Timedelta(days=index) for index in range(40)]
    differences = pd.DataFrame(
        [
            {"prediction_date": session, "ticker": ticker, "difference": 0.1}
            for session in sessions
            for ticker in TICKERS
            if ticker != "GLD"
        ]
    )

    result = synchronized_moving_block_bootstrap(
        differences,
        sessions,
        block_length=10,
        replicates=50,
        seed=42,
        minimum_pairs_per_ticker=30,
    )

    assert result.status == "INSUFFICIENT_EVIDENCE"
    assert result.raw_p_value is None
    assert result.ci_lower is None
    assert result.ci_upper is None
    assert result.n_by_ticker["GLD"] == 0


def test_portfolio_risk_uses_correlation_covariance_and_default_weights() -> None:
    result = calculate_portfolio_risk(
        {"SPY": 0.20, "IEF": 0.10, "GLD": 0.15},
        {
            "corr_spy_ief_20d": 0.5,
            "corr_spy_gld_20d": 0.5,
            "corr_ief_gld_20d": 0.5,
        },
    )

    assert result.status == "OK"
    assert result.weights == {"SPY": 0.5, "IEF": 0.3, "GLD": 0.2}
    assert result.portfolio_vol_annualized == pytest.approx(np.sqrt(0.0187))


def test_portfolio_risk_recomputes_for_user_weights_without_model_state() -> None:
    forecasts = {"SPY": 0.20, "IEF": 0.10, "GLD": 0.15}
    correlations = {
        "corr_spy_ief_20d": 0.0,
        "corr_spy_gld_20d": 0.0,
        "corr_ief_gld_20d": 0.0,
    }

    first = calculate_portfolio_risk(forecasts, correlations)
    second = calculate_portfolio_risk(
        forecasts,
        correlations,
        weights={"SPY": 0.0, "IEF": 1.0, "GLD": 0.0},
    )

    assert first.portfolio_vol_annualized == pytest.approx(np.sqrt(0.0118))
    assert second.portfolio_vol_annualized == pytest.approx(0.10)
    assert second.weights == {"SPY": 0.0, "IEF": 1.0, "GLD": 0.0}


def test_portfolio_risk_returns_incomplete_for_missing_forecast_or_unready_correlation() -> None:
    result = calculate_portfolio_risk(
        {"SPY": 0.20, "IEF": 0.10},
        {
            "corr_spy_ief_20d": 0.5,
            "corr_spy_gld_20d": 0.2,
            "corr_ief_gld_20d": 0.1,
        },
        correlation_ready=False,
    )

    assert result.status == "INCOMPLETE_INPUTS"
    assert result.portfolio_vol_annualized is None
    assert "GLD forecast" in result.missing_inputs
    assert "20-session correlation is not ready" in result.missing_inputs


def test_portfolio_risk_does_not_silently_project_non_psd_correlation() -> None:
    result = calculate_portfolio_risk(
        {"SPY": 0.20, "IEF": 0.10, "GLD": 0.15},
        {
            "corr_spy_ief_20d": -1.0,
            "corr_spy_gld_20d": -1.0,
            "corr_ief_gld_20d": -1.0,
        },
    )

    assert result.status == "INCOMPLETE_INPUTS"
    assert result.portfolio_vol_annualized is None
    assert "correlation matrix is not positive semidefinite" in result.missing_inputs


def test_portfolio_risk_rejects_non_long_only_or_not_fully_invested_weights() -> None:
    with pytest.raises(ValueError, match="nonnegative"):
        calculate_portfolio_risk(
            {"SPY": 0.20, "IEF": 0.10, "GLD": 0.15},
            {"corr_spy_ief_20d": 0.0, "corr_spy_gld_20d": 0.0, "corr_ief_gld_20d": 0.0},
            weights={"SPY": -0.1, "IEF": 0.6, "GLD": 0.5},
        )

    with pytest.raises(ValueError, match="sum to 1"):
        calculate_portfolio_risk(
            {"SPY": 0.20, "IEF": 0.10, "GLD": 0.15},
            {"corr_spy_ief_20d": 0.0, "corr_spy_gld_20d": 0.0, "corr_ief_gld_20d": 0.0},
            weights={"SPY": 0.4, "IEF": 0.3, "GLD": 0.2},
        )


def test_pair_comparisons_weight_etfs_equally_when_sample_sizes_differ() -> None:
    rows = []
    anchors = {
        "SPY": [(date(2025, 10, 1), 0.00), (date(2025, 10, 2), 0.00), (date(2025, 10, 3), 0.00)],
        "IEF": [(date(2025, 10, 1), 0.10)],
        "GLD": [(date(2025, 10, 1), 0.40)],
    }
    for ticker, ticker_anchors in anchors.items():
        for session, h2_delta in ticker_anchors:
            target = 1.0
            online_error = 0.10
            model_errors = {
                "CONSTANT_BASELINE": online_error + h2_delta,
                "ROLLING_20D_BASELINE": online_error + h2_delta,
                "STATIC_SGD": online_error + h2_delta,
                "ONLINE_SGD": online_error,
            }
            for model, error in model_errors.items():
                rows.append(
                    {
                        "prediction_date": session,
                        "ticker": ticker,
                        "model_name": model,
                        "split": "test",
                        "target_realized_vol_5d": target,
                        "predicted_vol_annualized": target + error,
                        "absolute_error": error,
                        "is_common_panel": True,
                    }
                )

    comparisons = _build_pair_comparisons(pd.DataFrame(rows), EvaluationConfig())
    h2_macro = comparisons.loc[(comparisons["comparison_id"] == "H2") & (comparisons["ticker"] == "MACRO")].iloc[0]

    assert h2_macro["paired_n"] == 5
    assert h2_macro["delta_mae_baseline_minus_online"] == pytest.approx((0.0 + 0.1 + 0.4) / 3)
    assert h2_macro["relative_improvement_pct"] == pytest.approx(((0.0 + 0.1 + 0.4) / 3) / ((0.1 + 0.2 + 0.5) / 3) * 100)


def test_high_volatility_threshold_uses_only_train_purge_clean_targets() -> None:
    dates = [date(2022, 1, 3), date(2022, 1, 4), date(2022, 1, 5), date(2022, 1, 6), date(2022, 1, 7)]
    rows = []
    target_values = []
    for ticker in TICKERS:
        for value, session in enumerate(dates, start=1):
            rows.append(
                {
                    "ticker": ticker,
                    "date": session,
                    "split": "train",
                    "target_end_date": date(2022, 1, 14),
                }
            )
            target_values.append(float(value))
    # Large Validation/Test outcomes must not move the Train-derived threshold.
    for ticker in TICKERS:
        rows.append(
            {
                "ticker": ticker,
                "date": date(2025, 10, 1),
                "split": "test",
                "target_end_date": date(2025, 10, 8),
            }
        )
        target_values.append(1000.0)
    supervised = SimpleNamespace(
        metadata=pd.DataFrame(rows),
        X=pd.DataFrame({"feature": np.zeros(len(rows))}),
        y=pd.Series(target_values, dtype=float),
    )

    thresholds, counts = _train_high_vol_thresholds(SimpleNamespace(supervised=supervised), EvaluationConfig())

    assert counts == {ticker: 5 for ticker in TICKERS}
    assert thresholds == {ticker: pytest.approx(4.2) for ticker in TICKERS}


def test_portfolio_table_keeps_incomplete_asset_sets_visible() -> None:
    session = date(2025, 10, 1)
    audit = pd.DataFrame(
        [
            {
                "prediction_date": session,
                "ticker": ticker,
                "split": "test",
                "model_name": model,
                "forecast_status": "VALID",
                "predicted_vol_annualized": 0.1,
                "run_id": "replay-run",
                "input_snapshot_id": "snapshot",
                "prediction_mode": "HISTORICAL_REPLAY",
            }
            for ticker in ("SPY", "IEF")
            for model in EvaluationConfig().model_names
        ]
    )
    correlations = pd.DataFrame(
        [
            {
                "date": session,
                "corr_spy_ief_20d": 0.0,
                "corr_spy_gld_20d": 0.0,
                "corr_ief_gld_20d": 0.0,
                "is_corr_ready": True,
                "run_id": "feature-run",
            }
        ]
    )

    result = _build_portfolio_risk_table(
        audit,
        correlations,
        feature_run_id="feature-run",
        config=EvaluationConfig(),
    )

    assert len(result) == len(EvaluationConfig().model_names)
    assert result["portfolio_status"].eq("INCOMPLETE_INPUTS").all()
    assert result["portfolio_vol_annualized"].isna().all()
    assert result["missing_inputs"].str.contains("GLD forecast").all()


def test_adwin_timeline_matches_test_errors_and_overlays_alerts() -> None:
    dates = [date(2025, 10, 1), date(2025, 10, 2)]
    audit = pd.DataFrame(
        [
            {
                "prediction_id": f"p{index}",
                "prediction_date": session,
                "ticker": "SPY",
                "split": "test",
                "model_name": "ONLINE_SGD",
                "evaluation_status": "EVALUABLE",
                "absolute_error": 0.01 * index,
            }
            for index, session in enumerate(dates, start=1)
        ]
    )
    errors = pd.DataFrame(
        [
            {
                "prediction_id": f"p{index}",
                "prediction_date": session,
                "ticker": "SPY",
                "absolute_error": 0.01 * index,
                "drift_detected": index == 2,
                "adwin_delta": 0.002,
                "adwin_width": 10,
                "adwin_estimation": 0.01 * index,
            }
            for index, session in enumerate(dates, start=1)
        ]
    )
    alerts = pd.DataFrame([{"prediction_id": "p2"}])

    timeline = _build_drift_error_timeline(audit, errors, alerts, EvaluationConfig())

    assert len(timeline) == 2
    assert timeline["drift_detected"].tolist() == [False, True]
    assert timeline["alert_record_present"].tolist() == [False, True]


def _synthetic_audit_five_models() -> pd.DataFrame:
    rows = []
    # SPY has 2 evaluable dates, IEF has 1, GLD has 1, plus 1 pending date across all ETFs.
    evaluable_dates = {
        "SPY": [date(2025, 10, 1), date(2025, 10, 2)],
        "IEF": [date(2025, 10, 1)],
        "GLD": [date(2025, 10, 1)],
    }
    errors_by_model = {
        "CONSTANT_BASELINE": {"SPY": [0.10, 0.30], "IEF": [0.20], "GLD": [0.40]},
        "ROLLING_20D_BASELINE": {"SPY": [0.08, 0.12], "IEF": [0.15], "GLD": [0.25]},
        "STATIC_SGD": {"SPY": [0.06, 0.14], "IEF": [0.12], "GLD": [0.22]},
        "ONLINE_SGD": {"SPY": [0.05, 0.11], "IEF": [0.10], "GLD": [0.20]},
        "HAR_X_OLS": {"SPY": [0.04, 0.08], "IEF": [0.11], "GLD": [0.18]},
    }
    for ticker, sessions in evaluable_dates.items():
        for idx, session in enumerate(sessions):
            for model, per_etf in errors_by_model.items():
                err = per_etf[ticker][idx]
                actual = 0.20
                rows.append(
                    {
                        "prediction_date": session,
                        "ticker": ticker,
                        "split": "test",
                        "model_name": model,
                        "target_realized_vol_5d": actual,
                        "predicted_vol_annualized": actual + err,
                        "absolute_error": err,
                        "squared_error": err ** 2,
                        "forecast_status": "VALID",
                        "label_status": "MATURE",
                        "evaluation_status": "EVALUABLE",
                    }
                )
        # Pending label row on 2025-10-10 must remain unscored.
        for model in errors_by_model:
            rows.append(
                {
                    "prediction_date": date(2025, 10, 10),
                    "ticker": ticker,
                    "split": "test",
                    "model_name": model,
                    "target_realized_vol_5d": np.nan,
                    "predicted_vol_annualized": 0.25,
                    "absolute_error": np.nan,
                    "squared_error": np.nan,
                    "forecast_status": "VALID",
                    "label_status": "PENDING",
                    "evaluation_status": "PENDING_LABEL",
                }
            )
    return pd.DataFrame(rows)


def test_b4_evaluation_manual_mae_rmse_macro_and_deltamae_direction() -> None:
    config = EvaluationConfig()
    audit = _mark_common_panel(_synthetic_audit_five_models(), config.model_names)
    metrics = _build_model_metrics(audit, config)
    b4_comp = _build_b4_comparisons(audit, config)

    # Hand calculation for HAR_X_OLS:
    # SPY errors: [0.04, 0.08] -> MAE=0.06, RMSE=sqrt((0.0016+0.0064)/2)=sqrt(0.004)
    # IEF error: [0.11] -> MAE=0.11, RMSE=0.11
    # GLD error: [0.18] -> MAE=0.18, RMSE=0.18
    # Equal-ETF Macro MAE = (0.06 + 0.11 + 0.18)/3 = 0.35/3
    # Equal-ETF Macro RMSE = sqrt((0.004 + 0.11**2 + 0.18**2)/3)
    b4_spy = metrics.loc[(metrics["model_name"] == "HAR_X_OLS") & (metrics["ticker"] == "SPY")].iloc[0]
    b4_macro = metrics.loc[(metrics["model_name"] == "HAR_X_OLS") & (metrics["ticker"] == "MACRO")].iloc[0]
    assert b4_spy["mae"] == pytest.approx(0.06)
    assert b4_spy["rmse"] == pytest.approx(np.sqrt(0.004))
    assert b4_macro["mae"] == pytest.approx((0.06 + 0.11 + 0.18) / 3.0)
    assert b4_macro["rmse"] == pytest.approx(np.sqrt((0.004 + 0.11 ** 2 + 0.18 ** 2) / 3.0))

    # B4 vs B2 (STATIC_SGD):
    # SPY: B2 MAE=(0.06+0.14)/2=0.10, B4 MAE=0.06 -> DeltaMAE = 0.10 - 0.06 = +0.04
    # IEF: B2 MAE=0.12, B4 MAE=0.11 -> DeltaMAE = +0.01
    # GLD: B2 MAE=0.22, B4 MAE=0.18 -> DeltaMAE = +0.04
    # Macro DeltaMAE = (0.04 + 0.01 + 0.04) / 3 = 0.03
    b4_vs_b2_macro = b4_comp.loc[
        (b4_comp["comparison_id"] == "B4_VS_B2") & (b4_comp["ticker"] == "MACRO")
    ].iloc[0]
    assert b4_vs_b2_macro["paired_n"] == 4
    assert b4_vs_b2_macro["delta_mae_comparator_minus_b4"] == pytest.approx(0.03)
    assert b4_vs_b2_macro["evaluation_scope"] == "retrospective_test_non_hypothesis"


def test_b4_invalid_shrinks_common_five_without_shrinking_b0_b3_reference_and_pending_unscored() -> None:
    config = EvaluationConfig()
    audit = _synthetic_audit_five_models()
    # Mark HAR_X_OLS on SPY 2025-10-02 as INVALID_FORECAST.
    mask = (
        (audit["ticker"] == "SPY")
        & (audit["prediction_date"] == date(2025, 10, 2))
        & (audit["model_name"] == "HAR_X_OLS")
    )
    audit.loc[mask, ["forecast_status", "evaluation_status"]] = ["INVALID", "INVALID_FORECAST"]
    audit.loc[mask, ["predicted_vol_annualized", "absolute_error", "squared_error"]] = np.nan

    marked = _mark_common_panel(audit, config.model_names)
    metrics_5 = _build_model_metrics(marked, config)
    ref_4 = _build_reference_b0_b3_metrics(marked, config)
    cov = _build_coverage_summary(marked)

    # Common 5-model SPY count drops from 2 to 1, while B0-B3 reference SPY count stays 2!
    b2_in_5 = metrics_5.loc[(metrics_5["model_name"] == "STATIC_SGD") & (metrics_5["ticker"] == "SPY")].iloc[0]
    b2_in_4 = ref_4.loc[(ref_4["model_name"] == "STATIC_SGD") & (ref_4["ticker"] == "SPY")].iloc[0]
    assert b2_in_5["paired_n"] == 1
    assert b2_in_4["paired_n"] == 2

    # Pending 2025-10-10 rows are never scored, and remain visible in coverage.
    b4_spy_cov = cov.loc[(cov["model_name"] == "HAR_X_OLS") & (cov["ticker"] == "SPY")].iloc[0]
    assert b4_spy_cov["expected_eligible_prediction_anchors"] == 3
    assert b4_spy_cov["invalid_forecast_count"] == 1
    assert b4_spy_cov["pending_label_count"] == 1
    assert b4_spy_cov["mature_evaluable_count"] == 1


def _synthetic_policy_eval_tables(
    *,
    with_events: bool = True,
    zero_spy_matches: bool = False,
) -> dict[str, pd.DataFrame]:
    """Build hand-verifiable benchmark & policy Test tables for Stage 06 policy evaluation."""
    from src.ml_replay.policy import (
        POLICY_DECISION_COLUMNS,
        POLICY_DETECTOR_COLUMNS,
        POLICY_EVALUATION_COLUMNS,
        POLICY_FAILURE_COLUMNS,
        POLICY_FORECAST_COLUMNS,
        POLICY_TIMELINE_COLUMNS,
    )

    init_champ = {"SPY": "B2", "IEF": "B1", "GLD": "B0"}
    dates = [date(2025, 10, 1), date(2025, 10, 2)]
    eval_dates = [date(2025, 10, 8), date(2025, 10, 9)]  # +7 calendar days each
    bench_eval_rows: list[dict[str, object]] = []
    pol_fc_rows: list[dict[str, object]] = []
    pol_ev_rows: list[dict[str, object]] = []
    pol_stream_rows: list[dict[str, object]] = []
    pol_fail_rows: list[dict[str, object]] = []

    # Exact targets = 0.20 everywhere so errors are trivially readable by hand.
    model_errors = {
        "SPY": {
            "CONSTANT_BASELINE": [0.10, 0.10],
            "ROLLING_20D_BASELINE": [0.08, 0.08],
            "STATIC_SGD": [0.06, 0.10],          # FIXED_INITIAL_CHAMPION (B2) MAE = 0.08
            "ONLINE_SGD": [0.04, 0.04],
            "HAR_X_OLS": [0.05, 0.05],
            "SERVED_CHAMPION": [0.06, 0.10],     # No alert on SPY -> identical to B2 (MAE = 0.08)
            "SHADOW_B3": [0.04, 0.04],
        },
        "IEF": {
            "CONSTANT_BASELINE": [0.12, 0.12],
            "ROLLING_20D_BASELINE": [0.05, 0.07],  # FIXED_INITIAL_CHAMPION (B1) MAE = 0.06
            "STATIC_SGD": [0.08, 0.08],
            "ONLINE_SGD": [0.06, 0.06],
            "HAR_X_OLS": [0.07, 0.07],
            "SERVED_CHAMPION": [0.05, 0.07],     # Alert retained on IEF -> MAE = 0.06
            "SHADOW_B3": [0.06, 0.06],
        },
        "GLD": {
            "CONSTANT_BASELINE": [0.10, 0.14],   # FIXED_INITIAL_CHAMPION (B0) MAE = 0.12
            "ROLLING_20D_BASELINE": [0.09, 0.09],
            "STATIC_SGD": [0.08, 0.08],
            "ONLINE_SGD": [0.04, 0.04],
            "HAR_X_OLS": [0.07, 0.07],
            "SERVED_CHAMPION": [0.10, 0.04] if with_events else [0.10, 0.14],  # Promoted -> MAE = 0.07 vs 0.12
            "SHADOW_B3": [0.04, 0.04],
        },
    }

    for ticker in ("SPY", "IEF", "GLD"):
        init_id = init_champ[ticker]
        for idx, (anchor, ev_d) in enumerate(zip(dates, eval_dates)):
            for m_name in ("CONSTANT_BASELINE", "ROLLING_20D_BASELINE", "STATIC_SGD", "ONLINE_SGD", "HAR_X_OLS"):
                err = model_errors[ticker][m_name][idx]
                bench_eval_rows.append(
                    {
                        "experiment_id": "exp-policy-test",
                        "prediction_id": f"b-{ticker}-{m_name}-{idx}",
                        "prediction_date": anchor,
                        "split": "test",
                        "ticker": ticker,
                        "model_name": m_name,
                        "model_version": "v1",
                        "prediction_mode": "HISTORICAL_REPLAY",
                        "forecast_horizon_trading_days": 5,
                        "target_start_date": anchor,
                        "target_end_date": ev_d,
                        "predicted_vol_annualized": 0.20 + err,
                        "target_realized_vol_5d": 0.20,
                        "target_version": "2.0.0",
                        "feature_set_version": "2.0.0",
                        "input_snapshot_id": "snap-1",
                        "absolute_error": err,
                        "squared_error": err**2,
                        "evaluation_date": ev_d,
                        "label_available_replay_date": ev_d,
                        "prediction_run_id": "r1",
                        "evaluation_run_id": "r1",
                    }
                )
            if zero_spy_matches and ticker == "SPY":
                pol_fail_rows.append(
                    {
                        "experiment_id": "exp-policy-test",
                        "policy_version": "1.0.0",
                        "prediction_date": anchor,
                        "split": "test",
                        "ticker": ticker,
                        "role": "SERVED_CHAMPION",
                        "champion_version_id": f"{ticker}_v001_{init_id}_aaaaaaaaaaaa",
                        "model_id": init_id,
                        "model_name": "STATIC_SGD",
                        "failure_type": "invalid_forecast",
                        "reason": "negative forecast rejected",
                        "raw_value": -0.05,
                        "run_id": "r1",
                    }
                )
                continue
            for role in ("SERVED_CHAMPION", "SHADOW_B3"):
                err = model_errors[ticker][role][idx]
                pid = f"p-{ticker}-{role}-{idx}"
                ver_id = (
                    f"{ticker}_v002_B3_bbbbbbbbbbbb"
                    if (with_events and ticker == "GLD" and idx == 1 and role == "SERVED_CHAMPION")
                    else f"{ticker}_v001_{init_id}_aaaaaaaaaaaa"
                )
                pol_fc_rows.append(
                    {
                        "experiment_id": "exp-policy-test",
                        "policy_version": "1.0.0",
                        "policy_prediction_id": pid,
                        "prediction_date": anchor,
                        "split": "test",
                        "ticker": ticker,
                        "role": role,
                        "champion_version_id": ver_id,
                        "model_id": init_id if role == "SERVED_CHAMPION" else "B3",
                        "model_name": "ONLINE_SGD" if role == "SHADOW_B3" else "STATIC_SGD",
                        "is_frozen_snapshot": role == "SERVED_CHAMPION",
                        "model_version": ver_id,
                        "state_sha256": "a" * 64,
                        "prediction_mode": "HISTORICAL_REPLAY",
                        "forecast_horizon_trading_days": 5,
                        "target_start_date": anchor,
                        "target_end_date": ev_d,
                        "predicted_vol_annualized": 0.20 + err,
                        "feature_set_version": "2.0.0",
                        "feature_run_id": "feat-1",
                        "input_snapshot_id": "snap-1",
                        "last_training_target_end_date": date(2024, 9, 30),
                        "champion_effective_from_date": date(2025, 10, 1),
                        "run_id": "r1",
                        "prediction_created_at_utc": "2026-11-22T00:00:00+00:00",
                    }
                )
                pol_ev_rows.append(
                    {
                        "experiment_id": "exp-policy-test",
                        "policy_version": "1.0.0",
                        "policy_prediction_id": pid,
                        "prediction_date": anchor,
                        "split": "test",
                        "ticker": ticker,
                        "role": role,
                        "champion_version_id": ver_id,
                        "active_champion_version_id_at_eval": ver_id,
                        "model_id": init_id if role == "SERVED_CHAMPION" else "B3",
                        "model_name": "ONLINE_SGD" if role == "SHADOW_B3" else "STATIC_SGD",
                        "is_frozen_snapshot": role == "SERVED_CHAMPION",
                        "model_version": ver_id,
                        "state_sha256": "a" * 64,
                        "target_start_date": anchor,
                        "target_end_date": ev_d,
                        "predicted_vol_annualized": 0.20 + err,
                        "target_realized_vol_5d": 0.20,
                        "target_version": "2.0.0",
                        "absolute_error": err,
                        "squared_error": err**2,
                        "evaluation_date": ev_d,
                        "label_available_replay_date": ev_d,
                        "stale_champion_skipped_from_policy": False,
                        "policy_skip_reason": None,
                        "prediction_run_id": "r1",
                        "evaluation_run_id": "r1",
                    }
                )
                if role == "SERVED_CHAMPION":
                    is_alert = with_events and (
                        (ticker == "IEF" and idx == 1) or (ticker == "GLD" and idx == 0)
                    )
                    pol_stream_rows.append(
                        {
                            "experiment_id": "exp-policy-test",
                            "policy_version": "1.0.0",
                            "policy_prediction_id": pid,
                            "prediction_date": anchor,
                            "evaluation_date": ev_d,
                            "ticker": ticker,
                            "champion_version_id": ver_id,
                            "champion_model_id": init_id,
                            "champion_state_sha256": "a" * 64,
                            "feed_order_in_session": 1,
                            "absolute_error": err,
                            "adwin_delta": 0.002,
                            "adwin_width": 2,
                            "adwin_estimation_before": 0.05,
                            "adwin_estimation": err,
                            "drift_detected": is_alert,
                            "drift_direction": "error_increase" if is_alert else "no_signal",
                            "triggered_decision": is_alert,
                            "cooldown_active": False,
                            "cooldown_remaining_before": 0,
                            "prediction_run_id": "r1",
                            "evaluation_run_id": "r1",
                        }
                    )
        # Add 1 pending forecast per ticker (no evaluation row) + 1 invalid forecast on SPY (when not zero_spy_matches).
        pol_fc_rows.append(
            {
                "experiment_id": "exp-policy-test",
                "policy_version": "1.0.0",
                "policy_prediction_id": f"p-{ticker}-SERVED_CHAMPION-pending",
                "prediction_date": date(2025, 10, 10),
                "split": "test",
                "ticker": ticker,
                "role": "SERVED_CHAMPION",
                "champion_version_id": f"{ticker}_v001_{init_id}_aaaaaaaaaaaa",
                "model_id": init_id,
                "model_name": "STATIC_SGD",
                "is_frozen_snapshot": True,
                "model_version": f"{ticker}_v001_{init_id}_aaaaaaaaaaaa",
                "state_sha256": "a" * 64,
                "prediction_mode": "HISTORICAL_REPLAY",
                "forecast_horizon_trading_days": 5,
                "target_start_date": date(2025, 10, 13),
                "target_end_date": date(2025, 10, 17),
                "predicted_vol_annualized": 0.21,
                "feature_set_version": "2.0.0",
                "feature_run_id": "feat-1",
                "input_snapshot_id": "snap-1",
                "last_training_target_end_date": date(2024, 9, 30),
                "champion_effective_from_date": date(2025, 10, 1),
                "run_id": "r1",
                "prediction_created_at_utc": "2026-11-22T00:00:00+00:00",
            }
        )
    if not zero_spy_matches:
        pol_fail_rows.append(
            {
                "experiment_id": "exp-policy-test",
                "policy_version": "1.0.0",
                "prediction_date": date(2025, 10, 3),
                "split": "test",
                "ticker": "SPY",
                "role": "SERVED_CHAMPION",
                "champion_version_id": "SPY_v001_B2_aaaaaaaaaaaa",
                "model_id": "B2",
                "model_name": "STATIC_SGD",
                "failure_type": "invalid_forecast",
                "reason": "negative forecast rejected",
                "raw_value": -0.02,
                "run_id": "r1",
            }
        )

    timeline_rows = [
        {
            "experiment_id": "exp-policy-test",
            "policy_version": "1.0.0",
            "timeline_event_id": f"tl-init-{t}",
            "event_type": "INITIAL_CHAMPION_CUTOVER",
            "recorded_date": date(2025, 10, 1),
            "decision_date": None,
            "effective_from_date": date(2025, 10, 1),
            "ticker": t,
            "version_seq": 1,
            "from_champion_version_id": None,
            "from_model_id": None,
            "from_state_sha256": None,
            "to_champion_version_id": f"{t}_v001_{init_champ[t]}_aaaaaaaaaaaa",
            "to_model_id": init_champ[t],
            "to_state_sha256": "a" * 64,
            "rollback_target_version_id": None,
            "rollback_target_model_id": None,
            "rollback_target_state_sha256": None,
            "decision_event_id": None,
            "reason": "stage04_initial_champion",
            "run_id": "r1",
        }
        for t in ("SPY", "IEF", "GLD")
    ]
    decision_rows: list[dict[str, object]] = []
    if with_events:
        decision_rows.extend(
            [
                {
                    "experiment_id": "exp-policy-test",
                    "policy_version": "1.0.0",
                    "event_id": "ev-gld-promo",
                    "decision_date": date(2025, 10, 8),
                    "ticker": "GLD",
                    "trigger_prediction_id": "p-GLD-SERVED_CHAMPION-0",
                    "trigger_prediction_date": date(2025, 10, 1),
                    "drift_direction": "error_increase",
                    "adwin_estimation_before": 0.05,
                    "adwin_estimation_after": 0.10,
                    "adwin_width": 2,
                    "champion_version_id_before": "GLD_v001_B0_aaaaaaaaaaaa",
                    "champion_model_id_before": "B0",
                    "champion_state_sha256_before": "a" * 64,
                    "shadow_model_id": "B3",
                    "shadow_state_sha256_pre_update": "b" * 64,
                    "comparison_window_pairs": 60,
                    "minimum_pairs": 30,
                    "min_relative_improvement": 0.05,
                    "valid_pair_count": 35,
                    "champion_window_mae": 0.12,
                    "shadow_b3_window_mae": 0.04,
                    "relative_improvement": 2.0 / 3.0,
                    "decision_outcome": "promoted",
                    "decision_reason": "relative_improvement_0.666667_meets_or_exceeds_0.05",
                    "switched": True,
                    "champion_version_id_after": "GLD_v002_B3_bbbbbbbbbbbb",
                    "champion_model_id_after": "B3",
                    "champion_state_sha256_after": "b" * 64,
                    "effective_from_date": date(2025, 10, 9),
                    "rollback_target_version_id": "GLD_v001_B0_aaaaaaaaaaaa",
                    "rollback_target_model_id": "B0",
                    "rollback_target_state_sha256": "a" * 64,
                    "cooldown_active": False,
                    "cooldown_remaining_before": 0,
                    "cooldown_remaining_after": 20,
                    "detector_reset_after_decision": True,
                    "run_id": "r1",
                },
                {
                    "experiment_id": "exp-policy-test",
                    "policy_version": "1.0.0",
                    "event_id": "ev-ief-ret",
                    "decision_date": date(2025, 10, 9),
                    "ticker": "IEF",
                    "trigger_prediction_id": "p-IEF-SERVED_CHAMPION-1",
                    "trigger_prediction_date": date(2025, 10, 2),
                    "drift_direction": "error_increase",
                    "adwin_estimation_before": 0.05,
                    "adwin_estimation_after": 0.07,
                    "adwin_width": 2,
                    "champion_version_id_before": "IEF_v001_B1_aaaaaaaaaaaa",
                    "champion_model_id_before": "B1",
                    "champion_state_sha256_before": "a" * 64,
                    "shadow_model_id": "B3",
                    "shadow_state_sha256_pre_update": "c" * 64,
                    "comparison_window_pairs": 60,
                    "minimum_pairs": 30,
                    "min_relative_improvement": 0.05,
                    "valid_pair_count": 35,
                    "champion_window_mae": 0.06,
                    "shadow_b3_window_mae": 0.06,
                    "relative_improvement": 0.0,
                    "decision_outcome": "retained",
                    "decision_reason": "relative_improvement_0.000000_below_threshold_0.05",
                    "switched": False,
                    "champion_version_id_after": "IEF_v001_B1_aaaaaaaaaaaa",
                    "champion_model_id_after": "B1",
                    "champion_state_sha256_after": "a" * 64,
                    "effective_from_date": None,
                    "rollback_target_version_id": None,
                    "rollback_target_model_id": None,
                    "rollback_target_state_sha256": None,
                    "cooldown_active": False,
                    "cooldown_remaining_before": 0,
                    "cooldown_remaining_after": 20,
                    "detector_reset_after_decision": False,
                    "run_id": "r1",
                },
            ]
        )
        timeline_rows.append(
            {
                "experiment_id": "exp-policy-test",
                "policy_version": "1.0.0",
                "timeline_event_id": "tl-gld-promo",
                "event_type": "PROMOTED_SNAPSHOT_ACTIVE_NEXT_SESSION",
                "recorded_date": date(2025, 10, 8),
                "decision_date": date(2025, 10, 8),
                "effective_from_date": date(2025, 10, 9),
                "ticker": "GLD",
                "version_seq": 2,
                "from_champion_version_id": "GLD_v001_B0_aaaaaaaaaaaa",
                "from_model_id": "B0",
                "from_state_sha256": "a" * 64,
                "to_champion_version_id": "GLD_v002_B3_bbbbbbbbbbbb",
                "to_model_id": "B3",
                "to_state_sha256": "b" * 64,
                "rollback_target_version_id": "GLD_v001_B0_aaaaaaaaaaaa",
                "rollback_target_model_id": "B0",
                "rollback_target_state_sha256": "a" * 64,
                "decision_event_id": "ev-gld-promo",
                "reason": "relative_improvement_0.666667_meets_or_exceeds_0.05",
                "run_id": "r1",
            }
        )

    return {
        "evaluation.csv": pd.DataFrame(bench_eval_rows),
        "asset_volatility_predictions.csv": pd.DataFrame(),
        "policy_forecasts.csv": pd.DataFrame(pol_fc_rows, columns=POLICY_FORECAST_COLUMNS),
        "policy_evaluations.csv": pd.DataFrame(pol_ev_rows, columns=POLICY_EVALUATION_COLUMNS),
        "policy_detector_stream.csv": pd.DataFrame(pol_stream_rows, columns=POLICY_DETECTOR_COLUMNS),
        "policy_decision_events.csv": pd.DataFrame(decision_rows, columns=POLICY_DECISION_COLUMNS),
        "policy_champion_timeline.csv": pd.DataFrame(timeline_rows, columns=POLICY_TIMELINE_COLUMNS),
        "policy_failures.csv": pd.DataFrame(pol_fail_rows, columns=POLICY_FAILURE_COLUMNS),
    }


def test_policy_evaluation_hand_computed_metrics_comparisons_latency_and_edge_cases() -> None:
    from src.ml_evaluation import evaluate_policy_tables

    init_champ = {"SPY": "B2", "IEF": "B1", "GLD": "B0"}

    # 1. With promotion on GLD, retained on IEF, no alert on SPY, invalid & pending forecasts.
    tables = _synthetic_policy_eval_tables(with_events=True)
    metrics, comparisons, ops, cov = evaluate_policy_tables(
        benchmark_evaluations=tables["evaluation.csv"],
        benchmark_predictions=tables["asset_volatility_predictions.csv"],
        policy_forecasts=tables["policy_forecasts.csv"],
        policy_evaluations=tables["policy_evaluations.csv"],
        policy_detector_stream=tables["policy_detector_stream.csv"],
        policy_decision_events=tables["policy_decision_events.csv"],
        policy_champion_timeline=tables["policy_champion_timeline.csv"],
        policy_failures=tables["policy_failures.csv"],
        initial_champion_by_ticker=init_champ,
    )

    # Hand calculations for CHAMPION_CHALLENGER_POLICY:
    # SPY: [0.06, 0.10] -> MAE=0.08, MSE=(0.0036+0.0100)/2=0.0068
    # IEF: [0.05, 0.07] -> MAE=0.06, MSE=(0.0025+0.0049)/2=0.0037
    # GLD: [0.10, 0.04] -> MAE=0.07, MSE=(0.0100+0.0016)/2=0.0058
    # Macro MAE = (0.08 + 0.06 + 0.07)/3 = 0.07
    # Macro RMSE = sqrt((0.0068 + 0.0037 + 0.0058)/3)
    pol_gld = metrics.loc[(metrics["strategy"] == "CHAMPION_CHALLENGER_POLICY") & (metrics["ticker"] == "GLD")].iloc[0]
    pol_macro = metrics.loc[(metrics["strategy"] == "CHAMPION_CHALLENGER_POLICY") & (metrics["ticker"] == "MACRO")].iloc[0]
    assert pol_gld["paired_n"] == 2
    assert pol_gld["mae"] == pytest.approx(0.07)
    assert pol_gld["rmse"] == pytest.approx(np.sqrt(0.0058))
    assert pol_macro["mae"] == pytest.approx(0.07)
    assert pol_macro["rmse"] == pytest.approx(np.sqrt((0.0068 + 0.0037 + 0.0058) / 3.0))

    # Policy vs Fixed Initial Champion:
    # SPY delta=0.00, IEF delta=0.00, GLD delta=0.12-0.07=+0.05 -> Macro delta = +0.05/3
    comp_macro = comparisons.loc[
        (comparisons["comparison_id"] == "POLICY_VS_FIXED_INITIAL_CHAMPION") & (comparisons["ticker"] == "MACRO")
    ].iloc[0]
    assert comp_macro["delta_mae_comparator_minus_policy"] == pytest.approx(0.05 / 3.0)
    assert bool(comp_macro["confirmatory_hypothesis"]) is False
    assert comp_macro["evaluation_scope"] == "retrospective_exploratory_non_confirmatory"
    assert "H1-H3" in comp_macro["test_reuse_limitation"]

    # Operations & latency: GLD decision->effective = 1 day (Oct 8 -> Oct 9), trigger->decision = 7 days.
    ops_gld = ops.loc[ops["ticker"] == "GLD"].iloc[0]
    ops_spy = ops.loc[ops["ticker"] == "SPY"].iloc[0]
    ops_macro = ops.loc[ops["ticker"] == "MACRO"].iloc[0]
    assert int(ops_gld["promotion_count"]) == 1
    assert ops_gld["mean_decision_to_effective_calendar_days"] == pytest.approx(1.0)
    assert ops_gld["mean_trigger_anchor_to_decision_calendar_days"] == pytest.approx(7.0)
    assert ops_gld["mean_label_maturity_lag_calendar_days"] == pytest.approx(7.0)
    assert bool(ops_spy["zero_alerts_observed"]) is True
    assert int(ops_spy["served_invalid_forecast_count"]) == 1
    assert int(ops_spy["pending_served_forecast_count"]) == 1
    assert int(ops_macro["alert_count"]) == 2
    assert int(ops_macro["promotion_count"]) == 1
    assert int(ops_macro["retained_count"]) == 1

    # Coverage captures invalid & pending forecasts cleanly.
    spy_cov = cov.loc[(cov["ticker"] == "SPY") & (cov["role"] == "SERVED_CHAMPION")].iloc[0]
    assert int(spy_cov["invalid_forecasts"]) == 1
    assert int(spy_cov["pending_labels"]) == 1
    assert int(spy_cov["matched_common_panel_n"]) == 2

    # 2. Zero alerts & zero promotions case: policy equals fixed initial champion exactly.
    no_ev_tables = _synthetic_policy_eval_tables(with_events=False)
    _, comp_no_ev, ops_no_ev, _ = evaluate_policy_tables(
        benchmark_evaluations=no_ev_tables["evaluation.csv"],
        benchmark_predictions=no_ev_tables["asset_volatility_predictions.csv"],
        policy_forecasts=no_ev_tables["policy_forecasts.csv"],
        policy_evaluations=no_ev_tables["policy_evaluations.csv"],
        policy_detector_stream=no_ev_tables["policy_detector_stream.csv"],
        policy_decision_events=no_ev_tables["policy_decision_events.csv"],
        policy_champion_timeline=no_ev_tables["policy_champion_timeline.csv"],
        policy_failures=no_ev_tables["policy_failures.csv"],
        initial_champion_by_ticker=init_champ,
    )
    macro_no_ev = ops_no_ev.loc[ops_no_ev["ticker"] == "MACRO"].iloc[0]
    assert bool(macro_no_ev["zero_alerts_observed"]) is True
    assert bool(macro_no_ev["zero_promotions_observed"]) is True
    assert pd.isna(macro_no_ev["mean_decision_to_effective_calendar_days"])
    assert comp_no_ev.loc[
        (comp_no_ev["comparison_id"] == "POLICY_VS_FIXED_INITIAL_CHAMPION") & (comp_no_ev["ticker"] == "MACRO"),
        "delta_mae_comparator_minus_policy",
    ].iloc[0] == pytest.approx(0.0)

    # 3. Insufficient matched sample on SPY -> SPY and MACRO marked INSUFFICIENT_SAMPLE without crashing.
    insuff_tables = _synthetic_policy_eval_tables(with_events=False, zero_spy_matches=True)
    m_insuff, comp_insuff, _, _ = evaluate_policy_tables(
        benchmark_evaluations=insuff_tables["evaluation.csv"],
        benchmark_predictions=insuff_tables["asset_volatility_predictions.csv"],
        policy_forecasts=insuff_tables["policy_forecasts.csv"],
        policy_evaluations=insuff_tables["policy_evaluations.csv"],
        policy_detector_stream=insuff_tables["policy_detector_stream.csv"],
        policy_decision_events=insuff_tables["policy_decision_events.csv"],
        policy_champion_timeline=insuff_tables["policy_champion_timeline.csv"],
        policy_failures=insuff_tables["policy_failures.csv"],
        initial_champion_by_ticker=init_champ,
    )
    assert m_insuff.loc[
        (m_insuff["strategy"] == "CHAMPION_CHALLENGER_POLICY") & (m_insuff["ticker"] == "SPY"), "status"
    ].iloc[0] == "INSUFFICIENT_SAMPLE"
    assert m_insuff.loc[
        (m_insuff["strategy"] == "CHAMPION_CHALLENGER_POLICY") & (m_insuff["ticker"] == "MACRO"), "status"
    ].iloc[0] == "INSUFFICIENT_SAMPLE"
    assert comp_insuff.loc[
        (comp_insuff["comparison_id"] == "POLICY_VS_FIXED_INITIAL_CHAMPION") & (comp_insuff["ticker"] == "MACRO"),
        "status",
    ].iloc[0] == "INSUFFICIENT_SAMPLE"

    # 4. Target mismatch across matched join fails explicitly.
    bad_target_pol = tables["policy_evaluations.csv"].copy()
    bad_target_pol.loc[0, "target_realized_vol_5d"] = 0.99
    with pytest.raises(EvaluationError, match="target_realized_vol_5d mismatch"):
        evaluate_policy_tables(
            benchmark_evaluations=tables["evaluation.csv"],
            benchmark_predictions=tables["asset_volatility_predictions.csv"],
            policy_forecasts=tables["policy_forecasts.csv"],
            policy_evaluations=bad_target_pol,
            policy_detector_stream=tables["policy_detector_stream.csv"],
            policy_decision_events=tables["policy_decision_events.csv"],
            policy_champion_timeline=tables["policy_champion_timeline.csv"],
            policy_failures=tables["policy_failures.csv"],
            initial_champion_by_ticker=init_champ,
        )


def test_run_policy_evaluation_verifies_checksums_reconciliation_and_rejects_forged_events(
    tmp_path: Path,
) -> None:
    from src.ml_evaluation import POLICY_EVALUATION_VERSION, reconcile_policy_replay_tables, run_policy_evaluation
    from src.ml_replay.config import POLICY_PROCESSING_ORDER, POLICY_REPLAY_CONFIG_VERSION
    from src.ml_replay.policy import POLICY_CHECKPOINT_VERSION

    tables = _synthetic_policy_eval_tables(with_events=True)
    replay_dir = tmp_path / "exp-policy-test"
    out_dir = replay_dir / "outputs"
    out_dir.mkdir(parents=True)

    # Write all 7 benchmark + 6 policy CSVs and hash them cleanly.
    all_files = {
        "asset_volatility_predictions.csv": pd.DataFrame(columns=["prediction_id"]),
        "evaluation.csv": tables["evaluation.csv"],
        "drift_errors.csv": pd.DataFrame(columns=["prediction_id"]),
        "drift_alerts.csv": pd.DataFrame(columns=["prediction_id"]),
        "updates.csv": pd.DataFrame(columns=["batch_id"]),
        "forecast_failures.csv": pd.DataFrame(columns=["reason"]),
        "coverage.csv": pd.DataFrame(columns=["ticker"]),
        "policy_forecasts.csv": tables["policy_forecasts.csv"],
        "policy_evaluations.csv": tables["policy_evaluations.csv"],
        "policy_detector_stream.csv": tables["policy_detector_stream.csv"],
        "policy_decision_events.csv": tables["policy_decision_events.csv"],
        "policy_champion_timeline.csv": tables["policy_champion_timeline.csv"],
        "policy_failures.csv": tables["policy_failures.csv"],
    }
    hashes = {}
    for name, df in all_files.items():
        path = out_dir / name
        df.to_csv(path, index=False, float_format="%.17g", lineterminator="\n")
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()

    manifest = {
        "phase": "FINAL_REPLAY",
        "status": "COMPLETED",
        "experiment_id": "exp-policy-test",
        "last_fully_committed_session": "2026-09-25",
        "b2_frozen_state_verified": True,
        "b4_frozen_state_verified": True,
        "checkpoint_version": POLICY_CHECKPOINT_VERSION,
        "replay_config": {
            "replay_config_version": POLICY_REPLAY_CONFIG_VERSION,
            "processing_order": list(POLICY_PROCESSING_ORDER),
            "adwin": {"policy": "monitor_only"},
        },
        "champion_challenger_policy": {"policy_version": "1.0.0"},
        "policy_config_fingerprint": "f" * 64,
        "initial_champion": {"SPY": "B2", "IEF": "B1", "GLD": "B0"},
        "final_outputs_sha256": hashes,
        "final_policy_summary": {"total_policy_decisions": 2, "total_policy_promotions": 1},
    }
    (replay_dir / "experiment_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    eval_out = tmp_path / "stage06-policy-eval"
    result = run_policy_evaluation(replay_dir, output_root=eval_out)
    assert result.policy_evaluation_version == POLICY_EVALUATION_VERSION
    assert result.artifact_dir is not None and result.artifact_dir.is_dir()
    assert result.manifest["test_reuse_exploratory_only"] is True
    assert result.manifest["h1_h3_confirmatory_unchanged"] is True
    assert result.manifest["point_in_time_source_availability_verified"] is False
    assert result.reconciliation["reconciliation_passed"] is True
    assert set(result.manifest["artifact_sha256"]) == {
        "policy_model_metrics.csv",
        "policy_comparisons.csv",
        "policy_operations_summary.csv",
        "policy_coverage_summary.csv",
        "policy_reconciliation.json",
        "policy_evaluation_summary.md",
    }

    # Forged decision event without matching triggered stream row must fail reconciliation.
    forged_decisions = tables["policy_decision_events.csv"].copy()
    forged_decisions.loc[0, "trigger_prediction_id"] = "forged-id"
    with pytest.raises(EvaluationError, match="no matching triggered ADWIN stream row"):
        reconcile_policy_replay_tables(
            manifest=manifest,
            policy_forecasts=tables["policy_forecasts.csv"],
            policy_evaluations=tables["policy_evaluations.csv"],
            policy_detector_stream=tables["policy_detector_stream.csv"],
            policy_decision_events=forged_decisions,
            policy_champion_timeline=tables["policy_champion_timeline.csv"],
            policy_failures=tables["policy_failures.csv"],
        )

    # Promotion violating effective_from_date > decision_date must fail reconciliation.
    bad_eff = tables["policy_decision_events.csv"].copy()
    bad_eff.loc[0, "effective_from_date"] = date(2025, 10, 8)
    with pytest.raises(EvaluationError, match="effective_from_date > decision_date"):
        reconcile_policy_replay_tables(
            manifest=manifest,
            policy_forecasts=tables["policy_forecasts.csv"],
            policy_evaluations=tables["policy_evaluations.csv"],
            policy_detector_stream=tables["policy_detector_stream.csv"],
            policy_decision_events=bad_eff,
            policy_champion_timeline=tables["policy_champion_timeline.csv"],
            policy_failures=tables["policy_failures.csv"],
        )

    # Tampering with a Stage 05 output CSV on disk must fail checksum verification.
    (out_dir / "policy_decision_events.csv").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(EvaluationError, match="checksum mismatch: policy_decision_events.csv"):
        run_policy_evaluation(replay_dir)
