from __future__ import annotations

import importlib.metadata
import sys

import joblib
import numpy as np
import pandas as pd
import scipy.stats
import sklearn
import statsmodels.api as sm
from river import drift
from sklearn.linear_model import SGDRegressor
from sklearn.preprocessing import RobustScaler
from statsmodels.stats.multitest import multipletests


def test_pinned_ml_and_drift_packages_import_under_project_python() -> None:
    assert sys.version_info[:2] == (3, 10)
    assert sklearn.__version__ == "1.7.2"
    assert importlib.metadata.version("river") == "0.22.0"
    assert importlib.metadata.version("joblib")
    assert importlib.metadata.version("statsmodels")
    assert importlib.metadata.version("scipy")
    assert (2, 0) <= tuple(map(int, np.__version__.split(".")[:2])) < (2, 3)
    assert (2, 2) <= tuple(map(int, pd.__version__.split(".")[:2])) < (2, 3)


def test_sgd_scaler_and_trusted_joblib_checkpoint_round_trip(tmp_path) -> None:
    features = np.array(
        [[-2.0, 0.1], [-1.0, 0.3], [0.0, 0.4], [1.0, 0.8], [2.0, 1.2]],
        dtype=float,
    )
    target = np.array([0.1, 0.2, 0.3, 0.5, 0.8], dtype=float)

    scaler = RobustScaler().fit(features)
    scaled_features = scaler.transform(features)
    model = SGDRegressor(
        loss="squared_error",
        penalty="l2",
        learning_rate="constant",
        eta0=0.001,
        alpha=0.0001,
        max_iter=20,
        tol=None,
        early_stopping=False,
        shuffle=True,
        random_state=42,
    ).fit(scaled_features, target)
    model.partial_fit(scaled_features[:1], target[:1])

    detector = drift.ADWIN(delta=0.002)
    for error in [0.01] * 20:
        detector.update(error)

    checkpoint_path = tmp_path / "trusted_state.joblib"
    joblib.dump({"model": model, "scaler": scaler, "detector": detector}, checkpoint_path)
    restored = joblib.load(checkpoint_path)

    np.testing.assert_allclose(
        restored["model"].predict(scaled_features), model.predict(scaled_features)
    )
    np.testing.assert_allclose(restored["scaler"].center_, scaler.center_)
    assert restored["detector"].width == detector.width
    assert restored["detector"].delta == detector.delta
    assert restored["detector"].drift_detected == detector.drift_detected
    detector.update(0.02)
    restored["detector"].update(0.02)
    assert restored["detector"].width == detector.width
    assert restored["detector"].drift_detected == detector.drift_detected


def test_adwin_updates_and_detects_a_synthetic_distribution_change() -> None:
    detector = drift.ADWIN(delta=0.002)
    detection_index = None

    for index, value in enumerate([0.0] * 1000 + [5.0] * 1000):
        detector.update(value)
        if detector.drift_detected:
            detection_index = index
            break

    assert detection_index is not None


def test_statsmodels_hac_scipy_one_sided_p_and_holm_smoke() -> None:
    rng = np.random.default_rng(42)
    x = np.linspace(-1.0, 1.0, 300)
    innovations = rng.normal(0.0, 0.1, size=x.size)
    residuals = np.zeros_like(x)
    for index in range(1, x.size):
        residuals[index] = 0.6 * residuals[index - 1] + innovations[index]
    y = 0.25 + 0.8 * x + residuals

    result = sm.OLS(y, sm.add_constant(x)).fit(
        cov_type="HAC",
        cov_kwds={"maxlags": 5},
        use_t=False,
    )
    slope = float(result.params[1])
    one_sided_p = float(scipy.stats.norm.sf(result.tvalues[1]))
    confidence_interval = result.conf_int(alpha=0.05)[1]
    expected_one_sided_p = scipy.stats.norm.sf(slope / result.bse[1])
    expected_half_width = scipy.stats.norm.ppf(0.975) * result.bse[1]
    expected_confidence_interval = [
        slope - expected_half_width,
        slope + expected_half_width,
    ]
    _, holm_adjusted, _, _ = multipletests(
        [0.01, 0.04, 0.20], alpha=0.05, method="holm"
    )

    assert slope > 0
    np.testing.assert_allclose(one_sided_p, expected_one_sided_p)
    np.testing.assert_allclose(confidence_interval, expected_confidence_interval)
    np.testing.assert_allclose(holm_adjusted, [0.03, 0.08, 0.20])
