from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Any

import yaml

from src.features.pipeline import CORE_FEATURE_COLUMNS
from src.ml_dataset.dataset import DatasetConfig


class TrainingError(ValueError):
    """Raised when Stage 04 inputs or configuration violate the training contract."""


TRAINING_CONFIG_VERSION = "1.1.0"
LEGACY_TRAINING_CONFIG_VERSION = "1.0.0"
SUPPORTED_TRAINING_CONFIG_VERSIONS = {
    LEGACY_TRAINING_CONFIG_VERSION,
    TRAINING_CONFIG_VERSION,
}


@dataclass(frozen=True)
class CandidateConfig:
    eta0: float
    alpha: float
    max_iter: int

    @property
    def candidate_id(self) -> str:
        return f"eta0={self.eta0:g};alpha={self.alpha:g};max_iter={self.max_iter}"

    def as_dict(self) -> dict[str, float | int | str]:
        return {
            "candidate_id": self.candidate_id,
            "eta0": self.eta0,
            "alpha": self.alpha,
            "max_iter": self.max_iter,
        }


@dataclass(frozen=True)
class TrainingConfig:
    training_config_version: str = TRAINING_CONFIG_VERSION
    core_features: tuple[str, ...] = CORE_FEATURE_COLUMNS
    eta0_values: tuple[float, ...] = (0.0001, 0.001, 0.01)
    alpha_values: tuple[float, ...] = (1e-5, 1e-4, 1e-3)
    initial_max_iter_values: tuple[int, ...] = (20, 50, 100)
    b4_estimator: str = "LinearRegression"
    b4_fit_intercept: bool = True
    b4_ill_conditioned_threshold: float = 1e8
    loss: str = "squared_error"
    penalty: str = "l2"
    learning_rate: str = "constant"
    shuffle: bool = True
    random_state: int = 42
    tol: None = None
    early_stopping: bool = False
    scaler: str = "RobustScaler"
    scaler_fit_scope: str = "train_only_per_etf"
    coverage_policy: str = "all_expected_paired_anchors_required"
    minimum_paired_coverage: float = 1.0
    tie_break_policy: str = "grid_order_with_absolute_tolerance"
    tie_tolerance: float = 1e-12
    invalid_prediction_policy: str = "reject_and_count_without_clipping"
    label_maturity_rule: str = (
        "is_label_mature and target_obs_count == 5 and target_end_date <= replay_date"
    )
    dataset: DatasetConfig = DatasetConfig()

    def __post_init__(self) -> None:
        if self.training_config_version not in SUPPORTED_TRAINING_CONFIG_VERSIONS:
            raise TrainingError("unsupported training_config_version")
        if not isinstance(self.b4_fit_intercept, bool):
            raise TrainingError("b4_fit_intercept must be a boolean")
        if tuple(self.core_features) != tuple(CORE_FEATURE_COLUMNS):
            raise TrainingError("core_features must match the locked eight-feature order")
        if tuple(self.eta0_values) != (0.0001, 0.001, 0.01):
            raise TrainingError("eta0 search values are locked by the approved contract")
        if tuple(self.alpha_values) != (1e-5, 1e-4, 1e-3):
            raise TrainingError("alpha search values are locked by the approved contract")
        if tuple(self.initial_max_iter_values) != (20, 50, 100):
            raise TrainingError("initial max_iter values are locked by the approved contract")
        locked = {
            "loss": "squared_error",
            "penalty": "l2",
            "learning_rate": "constant",
            "shuffle": True,
            "random_state": 42,
            "tol": None,
            "early_stopping": False,
            "scaler": "RobustScaler",
            "scaler_fit_scope": "train_only_per_etf",
            "coverage_policy": "all_expected_paired_anchors_required",
            "minimum_paired_coverage": 1.0,
            "tie_break_policy": "grid_order_with_absolute_tolerance",
            "invalid_prediction_policy": "reject_and_count_without_clipping",
            "label_maturity_rule": (
                "is_label_mature and target_obs_count == 5 and target_end_date <= replay_date"
            ),
            "b4_ill_conditioned_threshold": 1e8,
            "b4_estimator": "LinearRegression",
            "b4_fit_intercept": True,
        }
        for name, expected in locked.items():
            if getattr(self, name) != expected:
                raise TrainingError(f"{name} is locked by the approved Stage 04 contract")
        if self.tie_tolerance != 1e-12:
            raise TrainingError("tie_tolerance must remain 1e-12 for deterministic tie handling")

    @property
    def grid(self) -> tuple[CandidateConfig, ...]:
        return tuple(
            CandidateConfig(eta0=eta0, alpha=alpha, max_iter=max_iter)
            for eta0, alpha, max_iter in product(
                self.eta0_values,
                self.alpha_values,
                self.initial_max_iter_values,
            )
        )

    @classmethod
    def from_yaml(
        cls,
        path: str | Path = "config/ml_training.yaml",
        *,
        dataset: DatasetConfig | None = None,
    ) -> "TrainingConfig":
        config_path = Path(path)
        if not config_path.is_file():
            raise FileNotFoundError(f"ML Training config not found: {config_path}")
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise TrainingError("ML Training config must be a YAML mapping")
        try:
            sgd = raw["sgd"]
            b4 = raw.get("b4", {})
            search = raw["search_grid"]
            selection = raw["selection"]
            replay = raw["replay"]
            if sgd["estimator"] != "SGDRegressor" or sgd["scaler"] != "RobustScaler":
                raise TrainingError("Stage 04 requires SGDRegressor and RobustScaler")
            if selection["objective"] != "(mae_b2_validation + mae_b3_validation) / 2":
                raise TrainingError("selection objective does not match the approved contract")
            if selection["scope"] != "per_etf" or selection["scoring_split"] != "validation":
                raise TrainingError("model selection must be per ETF using Validation only")
            if selection["paired_anchor_policy"] != "complete_coverage_required":
                raise TrainingError("selection must require complete paired coverage")
            if replay["update_order"] != "predict_then_update":
                raise TrainingError("Validation replay must predict before updating B3")
            if replay["online_update"] != "mature_labels_only" or replay["duplicate_updates_allowed"]:
                raise TrainingError("online updates must use mature labels exactly once")
            if replay["train_fit_ledger_seeded"] is not True:
                raise TrainingError("initial Train fit keys must seed the B3 update ledger")
            return cls(
                training_config_version=raw["training_config_version"],
                core_features=tuple(raw["core_features"]),
                eta0_values=tuple(float(value) for value in search["eta0"]),
                alpha_values=tuple(float(value) for value in search["alpha"]),
                initial_max_iter_values=tuple(int(value) for value in search["initial_max_iter"]),
                b4_estimator=str(b4.get("estimator", "LinearRegression")),
                b4_fit_intercept=b4.get("fit_intercept", True),
                b4_ill_conditioned_threshold=float(
                    b4.get("ill_conditioned_threshold", 1e8)
                ),
                loss=sgd["loss"],
                penalty=sgd["penalty"],
                learning_rate=sgd["learning_rate"],
                shuffle=sgd["shuffle"],
                random_state=sgd["random_state"],
                tol=sgd["tol"],
                early_stopping=sgd["early_stopping"],
                scaler=sgd["scaler"],
                scaler_fit_scope=sgd["scaler_fit_scope"],
                coverage_policy="all_expected_paired_anchors_required",
                minimum_paired_coverage=float(selection["minimum_paired_coverage"]),
                tie_break_policy=selection["tie_break_policy"],
                tie_tolerance=float(selection["tie_tolerance"]),
                invalid_prediction_policy=selection["invalid_prediction_policy"],
                label_maturity_rule=replay["label_maturity_rule"],
                dataset=dataset or DatasetConfig.from_yaml(),
            )
        except (KeyError, TypeError, ValueError) as error:
            if isinstance(error, TrainingError):
                raise
            raise TrainingError(f"ML Training config is missing or invalid: {error}") from error

    def as_dict(self) -> dict[str, Any]:
        return {
            "training_config_version": self.training_config_version,
            "core_features": list(self.core_features),
            "sgd": {
                "estimator": "SGDRegressor",
                "loss": self.loss,
                "penalty": self.penalty,
                "learning_rate": self.learning_rate,
                "shuffle": self.shuffle,
                "random_state": self.random_state,
                "tol": self.tol,
                "early_stopping": self.early_stopping,
                "scaler": self.scaler,
                "scaler_fit_scope": self.scaler_fit_scope,
            },
            "b4": {
                "estimator": self.b4_estimator,
                "fit_intercept": self.b4_fit_intercept,
                "ill_conditioned_threshold": self.b4_ill_conditioned_threshold,
            },
            "search_grid": {
                "eta0": list(self.eta0_values),
                "alpha": list(self.alpha_values),
                "initial_max_iter": list(self.initial_max_iter_values),
                "candidate_count": len(self.grid),
            },
            "selection": {
                "objective": "(mae_b2_validation + mae_b3_validation) / 2",
                "scope": "per_etf",
                "scoring_split": "validation",
                "coverage_policy": self.coverage_policy,
                "minimum_paired_coverage": self.minimum_paired_coverage,
                "tie_break_policy": self.tie_break_policy,
                "tie_tolerance": self.tie_tolerance,
                "invalid_prediction_policy": self.invalid_prediction_policy,
            },
            "replay": {
                "update_order": "predict_then_update",
                "online_update": "mature_labels_only",
                "label_maturity_rule": self.label_maturity_rule,
                "duplicate_updates_allowed": False,
                "train_fit_ledger_seeded": True,
            },
            "dataset": self.dataset.as_dict(),
        }
