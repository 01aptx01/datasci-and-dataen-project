from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

from src.ml_dataset.dataset import DatasetConfig


class ReplayError(ValueError):
    """Raised when replay configuration or artifacts violate the Stage 05 contract."""


BASELINE_REPLAY_CONFIG_VERSION = "1.0.0"
POLICY_REPLAY_CONFIG_VERSION = "2.0.0"
SUPPORTED_REPLAY_CONFIG_VERSIONS = {
    BASELINE_REPLAY_CONFIG_VERSION,
    POLICY_REPLAY_CONFIG_VERSION,
}
POLICY_PROCESSING_ORDER = (
    "predict",
    "save_forecast",
    "evaluate",
    "adwin_monitor",
    "policy_adwin_and_decision",
    "update_b3",
    "checkpoint_commit",
)
BASELINE_PROCESSING_ORDER = (
    "predict",
    "save_forecast",
    "evaluate",
    "adwin_monitor",
    "update_b3",
    "checkpoint_commit",
)
ALLOWED_DRIFT_TRIGGER_DIRECTIONS = (
    "error_increase",
    "error_decrease",
    "shift_neutral",
)
ALLOWED_DECISION_OUTCOMES = (
    "promoted",
    "retained",
    "insufficient_pairs",
    "invalid",
)


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
class ChampionChallengerPolicyConfig:
    policy_version: str = "1.0.0"
    policy_name: str = "drift_triggered_champion_challenger"
    activation_split: str = "test"
    activation_start_date: date = date(2025, 10, 1)
    candidate_order: tuple[str, ...] = ("B0", "B1", "B2")
    challenger_model: str = "B3"
    initial_selection_source: str = "stage04_initial_champion"
    adwin_detector: str = "ADWIN"
    adwin_delta: float = 0.002
    adwin_policy: str = "drift_triggered_champion_challenger"
    reset_on_promotion: bool = True
    trigger_directions: tuple[str, ...] = ALLOWED_DRIFT_TRIGGER_DIRECTIONS
    same_session_multiple_alert_policy: str = (
        "first_alert_triggers_decision_remaining_errors_fed_in_order"
    )
    stale_champion_error_policy: str = "skip_detector_and_pair_audit_only"
    comparison_window_pairs: int = 60
    minimum_pairs: int = 30
    min_relative_improvement: float = 0.05
    zero_champion_mae_policy: str = "invalid_undefined_denominator"
    snapshot_timing: str = "pre_update_decision_time"
    effective_timing: str = "next_session"
    cooldown_sessions: int = 20
    cooldown_applies_to_outcomes: tuple[str, ...] = ALLOWED_DECISION_OUTCOMES
    cooldown_alert_policy: str = "record_alert_without_decision"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "activation_start_date",
            _as_date(self.activation_start_date, "activation_start_date"),
        )
        object.__setattr__(self, "candidate_order", tuple(self.candidate_order))
        object.__setattr__(self, "trigger_directions", tuple(self.trigger_directions))
        object.__setattr__(
            self,
            "cooldown_applies_to_outcomes",
            tuple(self.cooldown_applies_to_outcomes),
        )
        if self.policy_version != "1.0.0":
            raise ReplayError("unsupported champion_challenger policy_version")
        if self.policy_name != "drift_triggered_champion_challenger":
            raise ReplayError("unsupported champion_challenger policy_name")
        if self.activation_split != "test":
            raise ReplayError("champion_challenger activation_split must be test")
        if self.activation_start_date != DatasetConfig().test_start_date:
            raise ReplayError(
                "champion_challenger activation_start_date must match DatasetConfig().test_start_date"
            )
        if self.candidate_order != ("B0", "B1", "B2"):
            raise ReplayError(
                "champion_challenger candidate_order must be ('B0', 'B1', 'B2'); B3/B4 excluded"
            )
        if self.challenger_model != "B3":
            raise ReplayError("champion_challenger challenger_model must be B3")
        if self.initial_selection_source != "stage04_initial_champion":
            raise ReplayError("initial_selection_source must come from Stage 04 initial champion")
        if self.adwin_detector != "ADWIN" or self.adwin_policy != "drift_triggered_champion_challenger":
            raise ReplayError("policy detector must be ADWIN with drift_triggered_champion_challenger")
        if not math.isfinite(self.adwin_delta) or not 0.0 < self.adwin_delta < 1.0:
            raise ReplayError("policy adwin_delta must lie strictly between 0 and 1")
        if self.reset_on_promotion is not True:
            raise ReplayError("policy ADWIN must reset on champion promotion")
        if not self.trigger_directions or any(
            direction not in ALLOWED_DRIFT_TRIGGER_DIRECTIONS
            for direction in self.trigger_directions
        ):
            raise ReplayError("policy trigger_directions contains an unsupported direction")
        if (
            self.same_session_multiple_alert_policy
            != "first_alert_triggers_decision_remaining_errors_fed_in_order"
        ):
            raise ReplayError("unsupported same_session_multiple_alert_policy")
        if self.stale_champion_error_policy != "skip_detector_and_pair_audit_only":
            raise ReplayError("unsupported stale_champion_error_policy")
        for name, value in (
            ("comparison_window_pairs", self.comparison_window_pairs),
            ("minimum_pairs", self.minimum_pairs),
            ("cooldown_sessions", self.cooldown_sessions),
        ):
            if not isinstance(value, int) or isinstance(value, bool):
                raise ReplayError(f"{name} must be an integer")
        if self.comparison_window_pairs < 1 or not 1 <= self.minimum_pairs <= self.comparison_window_pairs:
            raise ReplayError("policy comparison window and minimum_pairs must satisfy 1 <= min <= window")
        if not math.isfinite(self.min_relative_improvement) or self.min_relative_improvement <= 0.0:
            raise ReplayError("policy min_relative_improvement must be finite and positive")
        if self.zero_champion_mae_policy != "invalid_undefined_denominator":
            raise ReplayError("zero_champion_mae_policy must be invalid_undefined_denominator")
        if self.snapshot_timing != "pre_update_decision_time" or self.effective_timing != "next_session":
            raise ReplayError("promotion snapshot must be pre-update and effective from next session")
        if self.cooldown_sessions < 0:
            raise ReplayError("cooldown_sessions must be nonnegative")
        if not set(self.cooldown_applies_to_outcomes).issubset(ALLOWED_DECISION_OUTCOMES):
            raise ReplayError("cooldown_applies_to_outcomes contains an unsupported outcome")
        if self.cooldown_alert_policy != "record_alert_without_decision":
            raise ReplayError("alerts during cooldown must be recorded without hiding")

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> "ChampionChallengerPolicyConfig":
        if not isinstance(raw, dict) or not isinstance(raw.get("adwin"), dict):
            raise ReplayError("champion_challenger_policy must be a mapping with an adwin section")
        if not isinstance(raw.get("comparison"), dict) or not isinstance(raw.get("promotion"), dict):
            raise ReplayError("champion_challenger_policy must include comparison and promotion sections")
        try:
            adwin = raw["adwin"]
            comparison = raw["comparison"]
            promotion = raw["promotion"]
            return cls(
                policy_version=str(raw["policy_version"]),
                policy_name=str(raw["policy_name"]),
                activation_split=str(raw["activation_split"]),
                activation_start_date=raw["activation_start_date"],
                candidate_order=tuple(str(item) for item in raw["candidate_order"]),
                challenger_model=str(raw["challenger_model"]),
                initial_selection_source=str(raw["initial_selection_source"]),
                adwin_detector=str(adwin["detector"]),
                adwin_delta=float(adwin["delta"]),
                adwin_policy=str(adwin["policy"]),
                reset_on_promotion=adwin["reset_on_promotion"],
                trigger_directions=tuple(str(item) for item in adwin["trigger_directions"]),
                same_session_multiple_alert_policy=str(adwin["same_session_multiple_alert_policy"]),
                stale_champion_error_policy=str(adwin["stale_champion_error_policy"]),
                comparison_window_pairs=int(comparison["window_pairs"]),
                minimum_pairs=int(comparison["minimum_pairs"]),
                min_relative_improvement=float(comparison["min_relative_improvement"]),
                zero_champion_mae_policy=str(comparison["zero_champion_mae_policy"]),
                snapshot_timing=str(promotion["snapshot_timing"]),
                effective_timing=str(promotion["effective_timing"]),
                cooldown_sessions=int(promotion["cooldown_sessions"]),
                cooldown_applies_to_outcomes=tuple(
                    str(item) for item in promotion["cooldown_applies_to_outcomes"]
                ),
                cooldown_alert_policy=str(promotion["cooldown_alert_policy"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            if isinstance(error, ReplayError):
                raise
            raise ReplayError(f"champion_challenger_policy is missing or invalid: {error}") from error

    def as_dict(self) -> dict[str, Any]:
        return {
            "policy_version": self.policy_version,
            "policy_name": self.policy_name,
            "activation_split": self.activation_split,
            "activation_start_date": self.activation_start_date.isoformat(),
            "candidate_order": list(self.candidate_order),
            "challenger_model": self.challenger_model,
            "initial_selection_source": self.initial_selection_source,
            "adwin": {
                "detector": self.adwin_detector,
                "delta": self.adwin_delta,
                "policy": self.adwin_policy,
                "reset_on_promotion": self.reset_on_promotion,
                "trigger_directions": list(self.trigger_directions),
                "same_session_multiple_alert_policy": self.same_session_multiple_alert_policy,
                "stale_champion_error_policy": self.stale_champion_error_policy,
            },
            "comparison": {
                "window_pairs": self.comparison_window_pairs,
                "minimum_pairs": self.minimum_pairs,
                "min_relative_improvement": self.min_relative_improvement,
                "zero_champion_mae_policy": self.zero_champion_mae_policy,
            },
            "promotion": {
                "snapshot_timing": self.snapshot_timing,
                "effective_timing": self.effective_timing,
                "cooldown_sessions": self.cooldown_sessions,
                "cooldown_applies_to_outcomes": list(self.cooldown_applies_to_outcomes),
                "cooldown_alert_policy": self.cooldown_alert_policy,
            },
        }

    def fingerprint(self) -> str:
        payload = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ReplayConfig:
    replay_config_version: str = BASELINE_REPLAY_CONFIG_VERSION
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
    processing_order: tuple[str, ...] = BASELINE_PROCESSING_ORDER
    adwin_detector: str = "ADWIN"
    adwin_delta: float = 0.002
    adwin_policy: str = "monitor_only"
    checkpoint_cadence: str = "every_xnys_session"
    atomic_commit: bool = True
    resume_policy: str = "latest_valid_committed_checkpoint_only"
    champion_challenger: ChampionChallengerPolicyConfig | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "replay_start_date", _as_date(self.replay_start_date, "replay_start_date"))
        object.__setattr__(self, "data_cutoff", _as_date(self.data_cutoff, "data_cutoff"))
        object.__setattr__(self, "processing_order", tuple(self.processing_order))
        if self.replay_config_version not in SUPPORTED_REPLAY_CONFIG_VERSIONS:
            raise ReplayError(f"unsupported replay_config_version: {self.replay_config_version}")
        locked_common = {
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
            "adwin_detector": "ADWIN",
            "adwin_delta": 0.002,
            "checkpoint_cadence": "every_xnys_session",
            "atomic_commit": True,
            "resume_policy": "latest_valid_committed_checkpoint_only",
        }
        for name, expected in locked_common.items():
            if getattr(self, name) != expected:
                raise ReplayError(f"{name} is locked by the approved Stage 05 contract")
        if self.replay_config_version == BASELINE_REPLAY_CONFIG_VERSION:
            if self.processing_order != BASELINE_PROCESSING_ORDER:
                raise ReplayError("processing_order is locked by the approved Stage 05 contract")
            if self.adwin_policy != "monitor_only":
                raise ReplayError("adwin_policy is locked by the approved Stage 05 contract")
            if self.champion_challenger is not None:
                raise ReplayError("baseline replay_config_version 1.0.0 cannot attach champion_challenger policy")
        else:
            if self.processing_order != POLICY_PROCESSING_ORDER:
                raise ReplayError("policy processing_order must match the Champion-Challenger contract")
            if self.adwin_policy != "monitor_only":
                raise ReplayError("baseline B3 ADWIN monitor must remain monitor_only even in policy mode")
            if self.champion_challenger is None:
                raise ReplayError("replay_config_version 2.0.0 requires champion_challenger configuration")

    @property
    def is_champion_challenger(self) -> bool:
        return self.replay_config_version == POLICY_REPLAY_CONFIG_VERSION and self.champion_challenger is not None

    @classmethod
    def from_yaml(
        cls,
        path: str | Path = "config/ml_replay.yaml",
        *,
        policy_mode: str = "baseline",
    ) -> "ReplayConfig":
        config_path = Path(path)
        if not config_path.is_file():
            raise FileNotFoundError(f"ML Replay config not found: {config_path}")
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or not isinstance(raw.get("adwin"), dict):
            raise ReplayError("ML Replay config must be a YAML mapping with an ADWIN section")
        if not isinstance(raw.get("checkpoint"), dict):
            raise ReplayError("ML Replay config must include a checkpoint section")
        if policy_mode not in {"baseline", "champion_challenger"}:
            raise ReplayError(f"unsupported policy_mode: {policy_mode}")
        try:
            top_version = str(raw["replay_config_version"])
            if policy_mode == "baseline" and top_version != POLICY_REPLAY_CONFIG_VERSION:
                return cls(
                    replay_config_version=top_version,
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
                    champion_challenger=None,
                )
            policy_raw = raw.get("champion_challenger_policy")
            if not isinstance(policy_raw, dict):
                raise ReplayError("ML Replay config is missing champion_challenger_policy section")
            policy_cfg = ChampionChallengerPolicyConfig.from_mapping(policy_raw)
            return cls(
                replay_config_version=str(policy_raw["replay_config_version"]),
                market=str(raw["market"]),
                prediction_mode=str(raw["prediction_mode"]),
                forecast_horizon_trading_days=int(raw["forecast_horizon_trading_days"]),
                replay_start_date=raw["replay_start_date"],
                data_cutoff=raw["data_cutoff"],
                label_availability_rule=str(raw["label_availability_rule"]),
                update_policy=str(raw["update_policy"]),
                update_model=str(raw["update_model"]),
                duplicate_updates_allowed=raw["duplicate_updates_allowed"],
                processing_order=tuple(policy_raw["processing_order"]),
                adwin_detector=str(raw["adwin"]["detector"]),
                adwin_delta=float(raw["adwin"]["delta"]),
                adwin_policy=str(raw["adwin"]["policy"]),
                checkpoint_cadence=str(raw["checkpoint"]["cadence"]),
                atomic_commit=raw["checkpoint"]["atomic_commit"],
                resume_policy=str(raw["checkpoint"]["resume_policy"]),
                champion_challenger=policy_cfg,
            )
        except (KeyError, TypeError, ValueError) as error:
            if isinstance(error, ReplayError):
                raise
            raise ReplayError(f"ML Replay config is missing or invalid: {error}") from error

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
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
        if self.champion_challenger is not None:
            payload["champion_challenger_policy"] = self.champion_challenger.as_dict()
        return payload

    def fingerprint(self) -> str:
        payload = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
