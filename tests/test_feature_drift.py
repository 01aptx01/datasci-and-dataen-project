from __future__ import annotations

import importlib
import importlib.util
import math
from datetime import date, timedelta

import pandas as pd


def _api(name: str):
    module_name = "src.ml_diagnostics.feature_drift"
    try:
        spec = importlib.util.find_spec(module_name)
    except ModuleNotFoundError:
        spec = None
    assert spec is not None, "Feature Drift calculation module is not implemented"
    module = importlib.import_module(module_name)
    function = getattr(module, name, None)
    assert callable(function), f"{name} is not implemented"
    return function


def test_identical_train_and_window_distributions_have_zero_wasserstein_and_psi() -> None:
    calculate = _api("calculate_distribution_metrics")

    result = calculate(
        reference_values=[-2.0, -1.0, 0.0, 1.0, 2.0],
        window_values=[-2.0, -1.0, 0.0, 1.0, 2.0],
        train_iqr=2.0,
        bin_edges=[-math.inf, -1.5, -0.5, 0.5, 1.5, math.inf],
        train_q01=-2.0,
        train_q99=2.0,
    )

    assert result["wasserstein_raw"] == 0.0
    assert result["wasserstein_normalized"] == 0.0
    assert result["psi"] == 0.0
    assert result["reference_n"] == 5
    assert result["window_n"] == 5


def test_train_quantile_bins_drop_duplicate_edges_and_keep_open_tails() -> None:
    derive_edges = _api("derive_train_bin_edges")

    edges = derive_edges([0.0, 0.0, 0.0, 1.0, 1.0, 1.0], bin_count=5)

    assert edges is not None
    assert edges[0] == -math.inf
    assert edges[-1] == math.inf
    assert all(left < right for left, right in zip(edges, edges[1:]))
    assert len(edges) < 7


def test_daily_metrics_use_only_the_selected_session_and_break_incomplete_windows() -> None:
    settings_type = _api("FeatureDriftSettings")
    build_tables = _api("build_feature_drift_tables")
    sessions = tuple(date(2025, 1, 1) + timedelta(days=index) for index in range(16))
    features = pd.DataFrame(
        [
            {"date": session, "ticker": "SPY", "rv_5d": float(index)}
            for index, session in enumerate(sessions)
        ]
    )
    settings = settings_type(
        core_features=("rv_5d",),
        tickers=("SPY",),
        train_start=sessions[0],
        train_end=sessions[5],
        validation_start=sessions[6],
        validation_end=sessions[10],
        test_start=sessions[11],
        test_end=sessions[15],
        window_sizes=(3,),
        bin_count=5,
        minimum_calibration_windows=2,
    )
    reference = features.loc[features.date.between(sessions[0], sessions[5])].copy()

    baseline = build_tables(features, reference, sessions, settings)
    selected = baseline.metrics.loc[baseline.metrics.as_of_date.eq(sessions[11].isoformat())].iloc[0]

    changed_future = features.copy()
    changed_future.loc[changed_future.date.gt(sessions[11]), "rv_5d"] = 10_000.0
    later = build_tables(changed_future, reference, sessions, settings)
    same_selected = later.metrics.loc[later.metrics.as_of_date.eq(sessions[11].isoformat())].iloc[0]
    assert selected["wasserstein_raw"] == same_selected["wasserstein_raw"]
    assert selected["psi"] == same_selected["psi"]

    incomplete_features = features.loc[features.date.ne(sessions[10])].copy()
    incomplete = build_tables(incomplete_features, reference, sessions, settings)
    incomplete_selected = incomplete.metrics.loc[
        incomplete.metrics.as_of_date.eq(sessions[11].isoformat())
    ].iloc[0]
    assert incomplete_selected["status"] == "INSUFFICIENT_DATA"
    assert pd.isna(incomplete_selected["wasserstein_raw"])
