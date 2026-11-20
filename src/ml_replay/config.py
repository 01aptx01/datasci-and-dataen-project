from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

from src.ml_dataset.dataset import DatasetConfig


class ReplayError(ValueError):
    """Raised when replay configuration or artifacts violate the Stage 05 contract."""


def _as_date(value: Any, field: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        parsed = date.fromisoformat(str(value))
    except (TypeError, ValueError) as error:
        raise ReplayError(f"{field} must be a valid ISO market date") from error
    return parsed


@dataclass(frozen=True)
class ReplayConfig:
    replay_config_version: str = "1.0.0"
    market: str = "XNYS"
    prediction_mode: str = "HISTORICAL_REPLAY"
    forecast_horizon_trading_days: int = 5
    replay_start_date: date = date(2024, 10, 1)
    data_cutoff: date = date(2026, 9, 25)
    label_availability_rule: str = (
        "is_label_mature and target_obs_count == 5 and target_end_date <= replay_date"
    )
    update_policy: str = "mature_labels_only"
    update_model: str = "B3"
    duplicate_updates_allowed: bool = False
    processing_order: tuple[str, ...] = (
        "predict",
        "save_forecast",
        "evaluate",
        "adwin_monitor",
        "update_b3",
        "checkpoint_commit",
    )
    adwin_detector: str = "ADWIN"
    adwin_delta: float = 0.002
    adwin_policy: str = "monitor_only"
    checkpoint_cadence: str = "every_xnys_session"
    atomic_commit: bool = True
    resume_policy: str = "latest_valid_committed_checkpoint_only"

    def __post_init__(self) -> None:
        object.__setattr__(self, "replay_start_date", _as_date(self.replay_start_date, "replay_start_date"))
        object.__setattr__(self, "data_cutoff", _as_date(self.data_cutoff, "data_cutoff"))
        locked = {
            "replay_config_version": "1.0.0",
            "market": "XNYS",
            "prediction_mode": "HISTORICAL_REPLAY",
            "forecast_horizon_trading_days": 5,
            "replay_start_date": DatasetConfig().validation_start_date,
            "data_cutoff": DatasetConfig().data_cutoff,
            "label_availability_rule": (
                "is_label_mature and target_obs_count == 5 and target_end_date <= replay_date"
            ),
            "update_policy": "mature_labels_only",
            "update_model": "B3",
            "duplicate_updates_allowed": False,
            "processing_order": (
                "predict",
                "save_forecast",
                "evaluate",
                "adwin_monitor",
                "update_b3",
                "checkpoint_commit",
            ),
            "adwin_detector": "ADWIN",
            "adwin_delta": 0.002,
            "adwin_policy": "monitor_only",
            "checkpoint_cadence": "every_xnys_session",
            "atomic_commit": True,
            "resume_policy": "latest_valid_committed_checkpoint_only",
        }
        for name, expected in locked.items():
            actual = getattr(self, name)
            if name == "processing_order":
                actual = tuple(actual)
            if actual != expected:
                raise ReplayError(f"{name} is locked by the approved Stage 05 contract")

    @classmethod
    def from_yaml(cls, path: str | Path = "config/ml_replay.yaml") -> "ReplayConfig":
        config_path = Path(path)
        if not config_path.is_file():
            raise FileNotFoundError(f"ML Replay config not found: {config_path}")
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or not isinstance(raw.get("adwin"), dict):
            raise ReplayError("ML Replay config must be a YAML mapping with an ADWIN section")
        if not isinstance(raw.get("checkpoint"), dict):
            raise ReplayError("ML Replay config must include a checkpoint section")
        try:
            return cls(
                replay_config_version=str(raw["replay_config_version"]),
                market=str(raw["market"]),
                prediction_mode=str(raw["prediction_mode"]),
                forecast_horizon_trading_days=int(raw["forecast_horizon_trading_days"]),
                replay_start_date=raw["replay_start_date"],
                data_cutoff=raw["data_cutoff"],
                label_availability_rule=str(raw["label_availability_rule"]),
                update_policy=str(raw["update_policy"]),
                update_model=str(raw["update_model"]),
                duplicate_updates_allowed=raw["duplicate_updates_allowed"],
                processing_order=tuple(raw["processing_order"]),
                adwin_detector=str(raw["adwin"]["detector"]),
                adwin_delta=float(raw["adwin"]["delta"]),
                adwin_policy=str(raw["adwin"]["policy"]),
                checkpoint_cadence=str(raw["checkpoint"]["cadence"]),
                atomic_commit=raw["checkpoint"]["atomic_commit"],
                resume_policy=str(raw["checkpoint"]["resume_policy"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            if isinstance(error, ReplayError):
                raise
            raise ReplayError(f"ML Replay config is missing or invalid: {error}") from error

    def as_dict(self) -> dict[str, Any]:
        return {
            "replay_config_version": self.replay_config_version,
            "market": self.market,
            "prediction_mode": self.prediction_mode,
            "forecast_horizon_trading_days": self.forecast_horizon_trading_days,
            "replay_start_date": self.replay_start_date.isoformat(),
            "data_cutoff": self.data_cutoff.isoformat(),
            "label_availability_rule": self.label_availability_rule,
            "update_policy": self.update_policy,
            "update_model": self.update_model,
            "duplicate_updates_allowed": self.duplicate_updates_allowed,
            "processing_order": list(self.processing_order),
            "adwin": {
                "detector": self.adwin_detector,
                "delta": self.adwin_delta,
                "policy": self.adwin_policy,
            },
            "checkpoint": {
                "cadence": self.checkpoint_cadence,
                "atomic_commit": self.atomic_commit,
                "resume_policy": self.resume_policy,
            },
        }
