from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml


class TargetConfigError(ValueError):
    """Raised when Target Pipeline configuration is invalid."""


@dataclass(frozen=True)
class TargetConfig:
    start_date: date
    end_date: date
    target_version: str
    market: str
    input_path: Path
    output_path: Path
    manifest_dir: Path
    overwrite_conflicts: bool = False


def _date_value(value: Any, name: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as error:
            raise TargetConfigError(f"{name} must be an ISO market date") from error
    raise TargetConfigError(f"{name} must be an ISO market date")


def _required_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TargetConfigError(f"{name} must be a YAML mapping")
    return value


def _config_path(value: Any, name: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise TargetConfigError(f"{name} must be a non-empty path")
    return Path(value)


def load_target_config(config_path: str | Path = "config/target.yaml") -> TargetConfig:
    path = Path(config_path)
    if not path.is_file():
        raise FileNotFoundError(f"Target config file not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise TargetConfigError(f"invalid YAML in {path}: {error}") from error
    root = _required_mapping(raw, "target config")
    target = _required_mapping(root.get("target"), "target")
    calendar = _required_mapping(root.get("calendar"), "calendar")
    paths = _required_mapping(root.get("paths"), "paths")
    publish = _required_mapping(root.get("publish", {}), "publish")

    try:
        start_date = _date_value(target["start_date"], "target.start_date")
        end_date = _date_value(target["end_date"], "target.end_date")
        target_version = target["target_version"]
        market = calendar["market"]
        input_path = _config_path(paths["input"], "paths.input")
        output_path = _config_path(paths["output"], "paths.output")
        manifest_dir = _config_path(paths["manifest_dir"], "paths.manifest_dir")
    except KeyError as error:
        raise TargetConfigError(f"Target config is missing a required value: {error}") from error

    if end_date < start_date:
        raise TargetConfigError("target.end_date must be on or after target.start_date")
    if (
        not isinstance(target_version, str)
        or len(target_version) > 16
        or re.fullmatch(r"\d+\.\d+\.\d+", target_version) is None
    ):
        raise TargetConfigError("target.target_version must be a semantic version up to 16 characters")
    if market != "XNYS":
        raise TargetConfigError("calendar.market must be XNYS for this Target Contract")
    if input_path.resolve() == output_path.resolve():
        raise TargetConfigError("paths.input and paths.output must be different files")

    overwrite_conflicts = publish.get("overwrite_conflicts", False)
    if not isinstance(overwrite_conflicts, bool):
        raise TargetConfigError("publish.overwrite_conflicts must be boolean")

    return TargetConfig(
        start_date=start_date,
        end_date=end_date,
        target_version=target_version,
        market=market,
        input_path=input_path,
        output_path=output_path,
        manifest_dir=manifest_dir,
        overwrite_conflicts=overwrite_conflicts,
    )
