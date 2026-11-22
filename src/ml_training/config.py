from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime
from itertools import product
from pathlib import Path
from typing import Any

import yaml

from src.features.pipeline import CORE_FEATURE_COLUMNS
from src.ml_dataset.dataset import DatasetConfig


class TrainingError(ValueError):
    """Raised when Stage 04 inputs or configuration violate the training contract."""


TRAINING_CONFIG_VERSION = "1.2.0"
B4_TRAINING_CONFIG_VERSION = "1.1.0"
LEGACY_TRAINING_CONFIG_VERSION = "1.0.0"
SUPPORTED_TRAINING_CONFIG_VERSIONS = {
    LEGACY_TRAINING_CONFIG_VERSION,
    B4_TRAINING_CONFIG_VERSION,
    TRAINING_CONFIG_VERSION,
}
INITIAL_CHAMPION_POLICY_VERSION = "1.0.0"
ALLOWED_INITIAL_CHAMPION_CANDIDATES = ("B0", "B1", "B2")


def _as_date(value: Any, field_name: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as error:
        raise TrainingError(f"{field_name} must be a valid ISO market date") from error


@dataclass(frozen=True)
class InitialChampionConfig:
    policy_version: str = INITIAL_CHAMPION_POLICY_VERSION
    candidate_models: tuple[str, ...] = ALLOWED_INITIAL_CHAMPION_CANDIDATES
    tie_break_order: tuple[str, ...] = ALLOWED_INITIAL_CHAMPION_CANDIDATES
    scoring_split: str = "validation"
    cutover_date: date = date(2025, 10, 1)
    cutover_maturity_rule: str = (
        "is_label_mature and target_obs_count == 5 and target_end_date < cutover_date"
    )
    paired_anchor_policy: str = "complete_coverage_required"
    minimum_paired_coverage: float = 1.0
    minimum_cutover_anchors: int = 1
    tie_tolerance: float = 1e-12
    invalid_prediction_policy: str = "reject_and_count_without_clipping"

    def __post_init__(self) -> None:
        object.__setattr__(self, "cutover_date", _as_date(self.cutover_date, "cutover_date"))
        object.__setattr__(self, "candidate_models", tuple(self.candidate_models))
        object.__setattr__(self, "tie_break_order", tuple(self.tie_break_order))
        if self.policy_version != INITIAL_CHAMPION_POLICY_VERSION:
            raise TrainingError("unsupported initial_champion policy_version")
        if self.candidate_models != ALLOWED_INITIAL_CHAMPION_CANDIDATES:
            raise TrainingError(
                "initial_champion candidate_models must be ('B0', 'B1', 'B2'); B3 and B4 are excluded"
            )
        if set(self.tie_break_order) != set(self.candidate_models) or len(
            self.tie_break_order
        ) != len(self.candidate_models):
            raise TrainingError("initial_champion tie_break_order must list each candidate once")
        if self.scoring_split != "validation":
            raise TrainingError("initial_champion selection must use Validation only")
        if self.cutover_date != DatasetConfig().test_start_date:
            raise TrainingError("initial_champion cutover_date must match DatasetConfig().test_start_date")
        if (
            self.cutover_maturity_rule
            != "is_label_mature and target_obs_count == 5 and target_end_date < cutover_date"
        ):
            raise TrainingError("initial_champion cutover_maturity_rule violates policy contract")
        if self.paired_anchor_policy != "complete_coverage_required":
            raise TrainingError("initial_champion requires complete paired coverage")
        if self.minimum_paired_coverage != 1.0:
            raise TrainingError("initial_champion minimum_paired_coverage must remain 1.0")
        if not isinstance(self.minimum_cutover_anchors, int) or isinstance(
            self.minimum_cutover_anchors, bool
        ) or self.minimum_cutover_anchors < 1:
            raise TrainingError("initial_champion minimum_cutover_anchors must be a positive integer")
        if self.tie_tolerance != 1e-12:
            raise TrainingError("initial_champion tie_tolerance must remain 1e-12")
        if self.invalid_prediction_policy != "reject_and_count_without_clipping":
            raise TrainingError("initial_champion must reject invalid predictions without clipping")

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> "InitialChampionConfig":
        if not isinstance(raw, dict):
            raise TrainingError("initial_champion config section must be a YAML mapping")
        try:
            return cls(
                policy_version=str(raw["policy_version"]),
                candidate_models=tuple(str(item) for item in raw["candidate_models"]),
                tie_break_order=tuple(str(item) for item in raw["tie_break_order"]),
                scoring_split=str(raw["scoring_split"]),
                cutover_date=raw["cutover_date"],
                cutover_maturity_rule=str(raw["cutover_maturity_rule"]),
                paired_anchor_policy=str(raw["paired_anchor_policy"]),
                minimum_paired_coverage=float(raw["minimum_paired_coverage"]),
                minimum_cutover_anchors=int(raw["minimum_cutover_anchors"]),
                tie_tolerance=float(raw["tie_tolerance"]),
                invalid_prediction_policy=str(raw["invalid_prediction_policy"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            if isinstance(error, TrainingError):
                raise
            raise TrainingError(f"initial_champion config is missing or invalid: {error}") from error

    def as_dict(self) -> dict[str, Any]:
        return {
            "policy_version": self.policy_version,
            "candidate_models": list(self.candidate_models),
            "tie_break_order": list(self.tie_break_order),
            "scoring_split": self.scoring_split,
            "cutover_date": self.cutover_date.isoformat(),
            "cutover_maturity_rule": self.cutover_maturity_rule,
            "paired_anchor_policy": self.paired_anchor_policy,
            "minimum_paired_coverage": self.minimum_paired_coverage,
            "minimum_cutover_anchors": self.minimum_cutover_anchors,
            "tie_tolerance": self.tie_tolerance,
            "invalid_prediction_policy": self.invalid_prediction_policy,
        }

    def fingerprint(self) -> str:
        payload = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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
    initial_champion: InitialChampionConfig | None = field(default_factory=InitialChampionConfig)

    def __post_init__(self) -> None:
        if self.training_config_version not in SUPPORTED_TRAINING_CONFIG_VERSIONS:
            raise TrainingError("unsupported training_config_version")
        if self.training_config_version == TRAINING_CONFIG_VERSION and self.initial_champion is None:
            raise TrainingError(
                f"training_config_version {TRAINING_CONFIG_VERSION} requires initial_champion config"
            )
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
            version_str = str(raw["training_config_version"])
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
            initial_champion_raw = raw.get("initial_champion")
            if version_str == TRAINING_CONFIG_VERSION:
                if initial_champion_raw is None:
                    raise TrainingError(
                        f"training_config_version {TRAINING_CONFIG_VERSION} requires an initial_champion section"
                    )
                initial_champion = InitialChampionConfig.from_mapping(initial_champion_raw)
            else:
                initial_champion = (
                    InitialChampionConfig.from_mapping(initial_champion_raw)
                    if initial_champion_raw is not None
                    else None
                )
            return cls(
                training_config_version=version_str,
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
                initial_champion=initial_champion,
            )
        except (KeyError, TypeError, ValueError) as error:
            if isinstance(error, TrainingError):
                raise
            raise TrainingError(f"ML Training config is missing or invalid: {error}") from error

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
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
        if self.initial_champion is not None:
            payload["initial_champion"] = self.initial_champion.as_dict()
        return payload

    def fingerprint(self) -> str:
        payload = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
