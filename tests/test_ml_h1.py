from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pandas_market_calendars as market_calendars
import pytest
import statsmodels.api as sm
from scipy.stats import norm

from src.ml_dataset.dataset import prepare_ml_dataset
from src.ml_dataset.h1 import analyze_h1, holm_adjust
from tests.test_ml_dataset_preparation import _feature_rows, _label_rows


def _build_h1_fixture() -> tuple[object, dict[str, float]]:
    sessions = [
        stamp.date()
        for stamp in market_calendars.get_calendar("XNYS")
        .schedule(start_date="2021-09-27", end_date="2024-09-30")
        .index
    ]
    train_anchors = sessions
    rng = np.random.default_rng(187)
    betas = {"SPY": 1.4, "IEF": 0.0, "GLD": -0.35}
    x_by_ticker: dict[str, list[float]] = {}
    y_by_ticker: dict[str, list[float]] = {}
    train_features = []
    train_labels = []
    for ticker, beta in betas.items():
        x = np.linspace(0.08, 0.34, len(train_anchors))
        shocks = rng.normal(0.0, 0.012, len(train_anchors))
        residuals = np.zeros(len(train_anchors))
        for index in range(1, len(train_anchors)):
            residuals[index] = 0.75 * residuals[index - 1] + shocks[index]
        if beta == 0.0:
            centered_x = x - x.mean()
            residuals = residuals - residuals.mean() - (
                np.dot(centered_x, residuals) / np.dot(centered_x, centered_x)
            ) * centered_x
        y = 0.18 + beta * x + residuals
        x_by_ticker[ticker] = x.tolist()
        y_by_ticker[ticker] = y.tolist()
        train_features.append(
            _feature_rows(train_anchors, tickers=(ticker,), rv_values={ticker: x.tolist()})
        )
        train_labels.append(
            _label_rows(train_anchors, ticker=ticker, y_values=y.tolist())
        )

    # Add one eligible-looking Validation and Test observation; H1 must ignore both.
    later_anchors = [date(2025, 9, 30), date(2025, 10, 1)]
    later_features = []
    later_labels = []
    for ticker in betas:
        later_features.append(
            _feature_rows(later_anchors, tickers=(ticker,), rv_values={ticker: [0.9, 0.9]})
        )
        later_labels.append(
            _label_rows(later_anchors, ticker=ticker, y_values=[9.0, 9.0])
        )
    features = pd.concat([*train_features, *later_features], ignore_index=True)
    labels = pd.concat([*train_labels, *later_labels], ignore_index=True)
    return prepare_ml_dataset(features, labels), betas


def test_h1_is_train_only_uses_hac_holm_and_writes_required_artifacts(tmp_path) -> None:
    prepared, expected_betas = _build_h1_fixture()

    result = analyze_h1(prepared, tmp_path / "h1-run")

    rows = result.results.set_index("ticker")
    assert set(rows.index) == {"SPY", "IEF", "GLD"}
    assert rows["n"].eq(rows["expected_n"]).all()
    assert rows["expected_n"].gt(700).all()
    expected_train_end = max(
        prepared.supervised.metadata.loc[
            prepared.supervised.metadata["split"] == "train", "date"
        ]
    )
    assert rows["train_end_date"].eq(expected_train_end).all()
    assert rows.loc["SPY", "beta"] == pytest.approx(expected_betas["SPY"], abs=0.15)
    assert rows.loc["SPY", "p_holm"] < 0.05
    assert rows.loc["IEF", "p_raw_one_sided"] > 0.05
    assert rows.loc["IEF", "beta"] == pytest.approx(0.0, abs=0.15)
    assert rows.loc["GLD", "beta"] < 0
    assert rows.loc["SPY", "hac_se"] > 0
    assert set(result.sensitivity["hac_maxlags"]) == {5, 10, 20}
    assert rows["decision"].str.len().gt(0).all()
    for name in (
        "H1_hypothesis_spec.json",
        "H1_dataset_audit.csv",
        "H1_results.csv",
        "H1_sensitivity.csv",
        "H1_scatter_data.csv",
        "H1_scatter_plot_spec.json",
        "H1_manifest.json",
    ):
        assert (tmp_path / "h1-run" / name).is_file()
    scatter = pd.read_csv(result.artifact_dir / "H1_scatter_data.csv")
    assert set(scatter["split"]) == {"train"}
    spy = scatter.loc[scatter["ticker"] == "SPY"]
    fitted = sm.OLS(
        spy["target_realized_vol_5d"], sm.add_constant(spy["rv_5d"])
    ).fit(cov_type="HAC", cov_kwds={"maxlags": 5, "use_correction": True})
    assert rows.loc["SPY", "hac_se"] == pytest.approx(
        np.sqrt(fitted.cov_params().iloc[1, 1])
    )
    assert rows.loc["SPY", "p_raw_one_sided"] == pytest.approx(
        norm.sf(rows.loc["SPY", "test_statistic"])
    )


def test_holm_adjustment_matches_three_test_family() -> None:
    adjusted = holm_adjust([0.01, 0.04, 0.03])

    assert adjusted == pytest.approx([0.03, 0.06, 0.06])


def test_h1_marks_small_samples_as_insufficient_evidence(tmp_path) -> None:
    sessions = [
        stamp.date()
        for stamp in market_calendars.get_calendar("XNYS")
        .schedule(start_date="2021-09-27", end_date="2022-01-31")
        .index
    ][:12]
    prepared = prepare_ml_dataset(_feature_rows(sessions), _label_rows(sessions))

    result = analyze_h1(prepared, tmp_path / "small-run")

    spy = result.results.loc[result.results["ticker"] == "SPY"].iloc[0]
    assert spy["decision"] == "insufficient_evidence"
    assert pd.isna(spy["beta"])
