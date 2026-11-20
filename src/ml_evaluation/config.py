from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from src.features.pipeline import CORE_FEATURE_COLUMNS, SUPPORTED_TICKERS
from src.ml_dataset.dataset import DatasetConfig


MODEL_NAMES = (
    "CONSTANT_BASELINE",
    "ROLLING_20D_BASELINE",
    "STATIC_SGD",
    "ONLINE_SGD",
)


class EvaluationError(ValueError):
    """Raised when Stage 06 inputs, artifacts, or configuration are invalid."""


@dataclass(frozen=True)
class EvaluationConfig:
    evaluation_config_version: str = "1.0.0"
    market: str = "XNYS"
    data_cutoff: date = date(2026, 9, 25)
    test_start_date: date = date(2025, 10, 1)
    test_end_date: date = date(2026, 9, 25)
    train_start_date: date = date(2021, 9, 27)
    train_end_date: date = date(2024, 9, 30)
    validation_start_date: date = date(2024, 10, 1)
    validation_end_date: date = date(2025, 9, 30)
    tickers: tuple[str, ...] = SUPPORTED_TICKERS
    model_names: tuple[str, ...] = MODEL_NAMES
    core_features: tuple[str, ...] = CORE_FEATURE_COLUMNS
    high_volatility_quantile: float = 0.80
    rolling_window_sessions: int = 20
    rolling_minimum_evaluable: int = 10
    bootstrap_minimum_pairs_per_ticker: int = 30
    portfolio_default_weights: tuple[float, float, float] = (0.50, 0.30, 0.20)
    weight_sum_tolerance: float = 1e-8
    correlation_symmetry_tolerance: float = 1e-12
    correlation_minimum_eigenvalue: float = -1e-10

    def __post_init__(self) -> None:
        for name in (
            "data_cutoff",
            "test_start_date",
            "test_end_date",
            "train_start_date",
            "train_end_date",
            "validation_start_date",
            "validation_end_date",
        ):
            value = getattr(self, name)
            if not isinstance(value, date):
                object.__setattr__(self, name, date.fromisoformat(str(value)))
        expected = DatasetConfig()
        locked_dates = (
            self.data_cutoff,
            self.train_start_date,
            self.train_end_date,
            self.validation_start_date,
            self.validation_end_date,
            self.test_start_date,
            self.test_end_date,
        )
        expected_dates = (
            expected.data_cutoff,
            expected.train_start_date,
            expected.train_end_date,
            expected.validation_start_date,
            expected.validation_end_date,
            expected.test_start_date,
            expected.test_end_date,
        )
        if self.evaluation_config_version != "1.0.0":
            raise EvaluationError("unsupported evaluation_config_version")
        if self.market != "XNYS" or locked_dates != expected_dates:
            raise EvaluationError("market, split dates, and data cutoff are locked by the approved contract")
        if tuple(self.tickers) != tuple(SUPPORTED_TICKERS):
            raise EvaluationError("tickers must be SPY, IEF, GLD in the approved order")
        if tuple(self.model_names) != MODEL_NAMES:
            raise EvaluationError("model_names must match the locked B0-B3 identities and order")
        if tuple(self.core_features) != tuple(CORE_FEATURE_COLUMNS):
            raise EvaluationError("core_features must match the locked eight-feature order")
        if self.high_volatility_quantile != 0.80:
            raise EvaluationError("high_volatility_quantile must remain at the Train 80th percentile")
        if self.rolling_window_sessions != 20:
            raise EvaluationError("rolling_window_sessions must be 20 XNYS sessions")
        if not 1 <= self.rolling_minimum_evaluable <= self.rolling_window_sessions:
            raise EvaluationError("rolling_minimum_evaluable must be between 1 and 20")
        if self.bootstrap_minimum_pairs_per_ticker < 1:
            raise EvaluationError("bootstrap_minimum_pairs_per_ticker must be positive")
        weights = self.portfolio_default_weights
        if len(weights) != 3 or any(value < 0 for value in weights):
            raise EvaluationError("portfolio_default_weights must contain three nonnegative weights")
        if abs(sum(weights) - 1.0) > self.weight_sum_tolerance:
            raise EvaluationError("portfolio_default_weights must sum to 1")
        if self.weight_sum_tolerance != 1e-8:
            raise EvaluationError("weight_sum_tolerance is locked by the portfolio contract")
        if self.correlation_symmetry_tolerance != 1e-12:
            raise EvaluationError("correlation_symmetry_tolerance is locked by the feature contract")
        if self.correlation_minimum_eigenvalue != -1e-10:
            raise EvaluationError("correlation_minimum_eigenvalue is locked by the portfolio contract")

    @classmethod
    def from_yaml(cls, path: str | Path = "config/ml_evaluation.yaml") -> "EvaluationConfig":
        config_path = Path(path)
        if not config_path.is_file():
            raise FileNotFoundError(f"ML Evaluation config not found: {config_path}")
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise EvaluationError("ML Evaluation config must be a YAML mapping")
        try:
            portfolio = raw["portfolio"]
            temporal = raw["temporal_diagnostics"]
            high_vol = raw["high_volatility"]
            return cls(
                evaluation_config_version=str(raw["evaluation_config_version"]),
                market=str(raw["market"]),
                data_cutoff=date.fromisoformat(str(raw["data_cutoff"])),
                test_start_date=date.fromisoformat(str(raw["splits"]["test"]["start_date"])),
                test_end_date=date.fromisoformat(str(raw["splits"]["test"]["end_date"])),
                train_start_date=date.fromisoformat(str(raw["splits"]["train"]["start_date"])),
                train_end_date=date.fromisoformat(str(raw["splits"]["train"]["end_date"])),
                validation_start_date=date.fromisoformat(str(raw["splits"]["validation"]["start_date"])),
                validation_end_date=date.fromisoformat(str(raw["splits"]["validation"]["end_date"])),
                tickers=tuple(raw["tickers"]),
                model_names=tuple(raw["model_names"]),
                core_features=tuple(raw["core_features"]),
                high_volatility_quantile=float(high_vol["train_target_quantile"]),
                rolling_window_sessions=int(temporal["rolling_window_sessions"]),
                rolling_minimum_evaluable=int(temporal["rolling_minimum_evaluable"]),
                bootstrap_minimum_pairs_per_ticker=int(
                    raw["hypothesis_inference"]["minimum_pairs_per_ticker"]
                ),
                portfolio_default_weights=tuple(
                    float(portfolio["default_weights"][ticker]) for ticker in SUPPORTED_TICKERS
                ),
                weight_sum_tolerance=float(portfolio["weight_sum_tolerance"]),
                correlation_symmetry_tolerance=float(portfolio["correlation_symmetry_tolerance"]),
                correlation_minimum_eigenvalue=float(portfolio["correlation_minimum_eigenvalue"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            if isinstance(error, EvaluationError):
                raise
            raise EvaluationError(f"ML Evaluation config is missing or invalid: {error}") from error

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key, value in tuple(payload.items()):
            if isinstance(value, date):
                payload[key] = value.isoformat()
            elif isinstance(value, tuple):
                payload[key] = list(value)
        return payload
