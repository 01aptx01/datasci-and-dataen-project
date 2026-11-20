from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np

from src.features.pipeline import SUPPORTED_TICKERS


@dataclass(frozen=True)
class PortfolioRiskResult:
    portfolio_vol_annualized: float | None
    status: str
    weights: Mapping[str, float]
    missing_inputs: tuple[str, ...]
    covariance_matrix: tuple[tuple[float, ...], ...] | None


def calculate_portfolio_risk(
    forecasts: Mapping[str, float | None],
    correlations: Mapping[str, float | None] | None,
    *,
    weights: Mapping[str, float] | None = None,
    correlation_ready: bool = True,
    weight_sum_tolerance: float = 1e-8,
    symmetry_tolerance: float = 1e-12,
    minimum_eigenvalue: float = -1e-10,
) -> PortfolioRiskResult:
    """Calculate annualized five-session portfolio volatility from three forecasts."""
    effective_weights = (
        {"SPY": 0.50, "IEF": 0.30, "GLD": 0.20}
        if weights is None
        else {ticker: float(weights[ticker]) for ticker in SUPPORTED_TICKERS if ticker in weights}
    )
    if set(effective_weights) != set(SUPPORTED_TICKERS):
        raise ValueError("weights must specify exactly SPY, IEF, and GLD")
    weight_vector = np.asarray([effective_weights[ticker] for ticker in SUPPORTED_TICKERS], dtype=float)
    if not np.isfinite(weight_vector).all() or (weight_vector < 0).any():
        raise ValueError("portfolio weights must be finite and nonnegative")
    if abs(float(weight_vector.sum()) - 1.0) > weight_sum_tolerance:
        raise ValueError("long-only portfolio weights must sum to 1")

    missing: list[str] = []
    forecast_values: list[float] = []
    for ticker in SUPPORTED_TICKERS:
        value = forecasts.get(ticker)
        if value is None:
            missing.append(f"{ticker} forecast")
            forecast_values.append(np.nan)
            continue
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            numeric = np.nan
        if not np.isfinite(numeric) or numeric < 0:
            missing.append(f"{ticker} forecast is invalid")
        forecast_values.append(numeric)
    if not correlation_ready:
        missing.append("20-session correlation is not ready")
    required_correlations = ("corr_spy_ief_20d", "corr_spy_gld_20d", "corr_ief_gld_20d")
    if correlations is None:
        missing.append("20-session correlation values are missing")
        corr_values = [np.nan] * 3
    else:
        corr_values = []
        for column in required_correlations:
            value = correlations.get(column)
            try:
                numeric = float(value) if value is not None else np.nan
            except (TypeError, ValueError):
                numeric = np.nan
            if not np.isfinite(numeric):
                missing.append(f"{column} is missing or non-finite")
            elif not -1.0 <= numeric <= 1.0:
                missing.append(f"{column} is outside [-1, 1]")
            corr_values.append(numeric)

    if missing:
        return PortfolioRiskResult(None, "INCOMPLETE_INPUTS", effective_weights, tuple(missing), None)

    rho_spy_ief, rho_spy_gld, rho_ief_gld = corr_values
    correlation_matrix = np.asarray(
        [
            [1.0, rho_spy_ief, rho_spy_gld],
            [rho_spy_ief, 1.0, rho_ief_gld],
            [rho_spy_gld, rho_ief_gld, 1.0],
        ],
        dtype=float,
    )
    if not np.allclose(correlation_matrix, correlation_matrix.T, atol=symmetry_tolerance, rtol=0.0):
        return PortfolioRiskResult(
            None,
            "INCOMPLETE_INPUTS",
            effective_weights,
            ("correlation matrix is not symmetric",),
            None,
        )
    if float(np.linalg.eigvalsh(correlation_matrix).min()) < minimum_eigenvalue:
        return PortfolioRiskResult(
            None,
            "INCOMPLETE_INPUTS",
            effective_weights,
            ("correlation matrix is not positive semidefinite",),
            None,
        )

    sigma = np.diag(np.asarray(forecast_values, dtype=float))
    covariance = sigma @ correlation_matrix @ sigma
    portfolio_variance = float(weight_vector @ covariance @ weight_vector)
    if not np.allclose(covariance, covariance.T, atol=symmetry_tolerance, rtol=0.0):
        return PortfolioRiskResult(None, "INCOMPLETE_INPUTS", effective_weights, ("covariance matrix is not symmetric",), None)
    if not np.isfinite(portfolio_variance) or portfolio_variance < -1e-12:
        return PortfolioRiskResult(
            None,
            "INCOMPLETE_INPUTS",
            effective_weights,
            ("portfolio variance is negative or non-finite",),
            None,
        )
    portfolio_volatility = float(np.sqrt(max(0.0, portfolio_variance)))
    return PortfolioRiskResult(
        portfolio_volatility,
        "OK",
        effective_weights,
        (),
        tuple(tuple(float(value) for value in row) for row in covariance),
    )


__all__ = ["PortfolioRiskResult", "calculate_portfolio_risk"]
