from __future__ import annotations

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
from src.ml_evaluation.config import EvaluationConfig
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
)


TICKERS = ("SPY", "IEF", "GLD")


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
