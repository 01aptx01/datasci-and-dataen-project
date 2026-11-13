from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from src.features.pipeline import (
    FeatureConfig,
    FeaturePipelineError,
    build_feature_tables,
    validate_price_data,
)
from src.features.storage import publish_feature_outputs


def load_config(config_path: str | Path) -> dict[str, Any]:
    path = Path(config_path)
    if not path.is_file():
        raise FileNotFoundError(f"Feature config file not found: {path}")
    try:
        config = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise FeaturePipelineError(f"invalid YAML in {path}: {error}") from error
    if not isinstance(config, dict):
        raise FeaturePipelineError("feature config must be a YAML mapping")

    try:
        feature_section = config["feature"]
        calendar_section = config["calendar"]
        paths = config["paths"]
        publish_section = config["publish"]
        feature_config = FeatureConfig(
            start_date=feature_section["start_date"],
            end_date=feature_section.get("end_date"),
            warmup_trading_days=feature_section.get("warmup_trading_days", 61),
            tickers=tuple(feature_section.get("tickers", ("SPY", "IEF", "GLD"))),
            feature_set_version=feature_section.get("feature_set_version", "2.0.0"),
            market=calendar_section["market"],
            expected_trading_days=(
                None
                if feature_section.get("expected_trading_days") is None
                else tuple(feature_section["expected_trading_days"])
            ),
        )
        input_path = Path(paths["input"])
        features_path = Path(paths["features"])
        correlations_path = Path(paths["correlations"])
        manifest_dir = Path(paths["manifest_dir"])
        overwrite_conflicts = publish_section.get("overwrite_conflicts", False)
    except (KeyError, TypeError) as error:
        raise FeaturePipelineError(f"feature config is missing a required value: {error}") from error

    for key, value in (
        ("paths.input", input_path),
        ("paths.features", features_path),
        ("paths.correlations", correlations_path),
        ("paths.manifest_dir", manifest_dir),
    ):
        if not str(value).strip():
            raise FeaturePipelineError(f"{key} cannot be empty")
    if not isinstance(overwrite_conflicts, bool):
        raise FeaturePipelineError("publish.overwrite_conflicts must be boolean")
    if not isinstance(calendar_section["market"], str) or not calendar_section["market"].strip():
        raise FeaturePipelineError("calendar.market must be a non-empty string")

    return {
        "feature_config": feature_config,
        "input_path": input_path,
        "features_path": features_path,
        "correlations_path": correlations_path,
        "manifest_dir": manifest_dir,
        "overwrite_conflicts": overwrite_conflicts,
        "config_path": path,
        "raw": config,
    }


def _expected_market_sessions(
    data: pd.DataFrame,
    config: FeatureConfig,
) -> tuple[Any, ...]:
    try:
        import pandas_market_calendars as market_calendars
    except ImportError as error:
        raise FeaturePipelineError(
            "pandas-market-calendars is required to validate the complete XNYS session sequence"
        ) from error

    dates = pd.to_datetime(data["date"], errors="coerce")
    if dates.isna().any() or dates.empty:
        raise FeaturePipelineError("market_prices_daily contains invalid dates")
    calendar = market_calendars.get_calendar(config.market)
    search_start = config.start_date - timedelta(
        days=max(30, config.warmup_trading_days * 3)
    )
    effective_end = config.end_date or dates.max().date()
    schedule = calendar.schedule(
        start_date=min(search_start, dates.min().date()),
        end_date=effective_end,
    )
    all_sessions = tuple(pd.Timestamp(value).date() for value in schedule.index)
    if not all_sessions:
        raise FeaturePipelineError("no exchange sessions overlap the input price range")
    warmup_sessions = tuple(day for day in all_sessions if day < config.start_date)
    if len(warmup_sessions) < config.warmup_trading_days:
        raise FeaturePipelineError(
            f"calendar returned fewer than {config.warmup_trading_days} warm-up sessions"
        )
    required_start = warmup_sessions[-config.warmup_trading_days]
    actual_start = dates.min().date()
    expected_start = min(actual_start, required_start)
    sessions = tuple(
        day
        for day in all_sessions
        if expected_start <= day <= effective_end
    )
    return sessions


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _source_summary(data: pd.DataFrame) -> dict[str, Any]:
    summary = {}
    for ticker, group in data.groupby("ticker", sort=True):
        batches = sorted(str(value) for value in group["source_batch_id"].dropna().unique())
        summary[ticker] = {
            "start_date": min(group["date"]).isoformat(),
            "end_date": max(group["date"]).isoformat(),
            "rows": int(len(group)),
            "source_batch_ids": batches,
        }
    return summary


def _source_snapshot_manifest(data: pd.DataFrame) -> list[dict[str, Any]]:
    snapshots = []
    for batch_id, group in data.groupby("source_batch_id", sort=True):
        batch_id = str(batch_id)
        safe_batch_id = re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", batch_id)
        if safe_batch_id:
            batch_dir = Path("data/raw") / batch_id
            manifest_path = batch_dir / "manifest.json"
            raw_file_path = batch_dir / "raw_prices.csv"
        else:
            manifest_path = None
            raw_file_path = None

        snapshot_manifest = {}
        status = "NOT_FOUND"
        if manifest_path is not None and manifest_path.is_file():
            try:
                snapshot_manifest = json.loads(
                    manifest_path.read_text(encoding="utf-8")
                )
                status = "AVAILABLE"
            except (OSError, json.JSONDecodeError):
                status = "UNREADABLE"

        snapshots.append(
            {
                "source_batch_id": batch_id,
                "ingestion_run_ids": sorted(
                    str(value) for value in group["run_id"].dropna().unique()
                ),
                "tickers": sorted(str(value) for value in group["ticker"].unique()),
                "start_date": min(group["date"]).isoformat(),
                "end_date": max(group["date"]).isoformat(),
                "rows": int(len(group)),
                "raw_file_path": (
                    snapshot_manifest.get("raw_file_path")
                    if snapshot_manifest
                    else None if raw_file_path is None else str(raw_file_path).replace("\\", "/")
                ),
                "snapshot_manifest_path": (
                    None
                    if manifest_path is None
                    else str(manifest_path).replace("\\", "/")
                ),
                "raw_file_sha256": snapshot_manifest.get("sha256"),
                "manifest_status": status,
            }
        )
    return snapshots


def run_feature_pipeline(
    config_path: str | Path = "config/features.yaml",
    run_id: str | None = None,
    overwrite_conflicts: bool | None = None,
) -> dict[str, Any]:
    settings = load_config(config_path)
    input_path: Path = settings["input_path"]
    if not input_path.is_file():
        raise FileNotFoundError(f"market_prices_daily Parquet not found: {input_path}")

    source = pd.read_parquet(input_path)
    feature_config: FeatureConfig = settings["feature_config"]
    if feature_config.expected_trading_days is None:
        sessions = _expected_market_sessions(source, feature_config)
        feature_config = replace(feature_config, expected_trading_days=sessions)
    validated = validate_price_data(source, feature_config)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    effective_run_id = run_id or (
        "feat_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:8]
    )
    features, correlations = build_feature_tables(
        validated,
        feature_config,
        run_id=effective_run_id,
        feature_as_of_utc=timestamp,
    )

    config_file: Path = settings["config_path"]
    manifest = {
        "run_id": effective_run_id,
        "pipeline": "feature_engineering",
        "feature_set_version": feature_config.feature_set_version,
        "created_at_utc": timestamp,
        "input": {
            "table": "market_prices_daily",
            "path": str(input_path),
            "sha256": _sha256_file(input_path),
            "rows": int(len(validated)),
            "start_date": min(validated["date"]).isoformat(),
            "end_date": max(validated["date"]).isoformat(),
            "sources_by_ticker": _source_summary(validated),
            "source_snapshots": _source_snapshot_manifest(validated),
        },
        "config": {
            "path": str(config_file),
            "sha256": _sha256_file(config_file),
            "values": settings["raw"],
            "expected_trading_days": [
                day.isoformat() for day in feature_config.expected_trading_days or ()
            ],
        },
        "outputs": {
            "asset_volatility_features": {
                "path": str(settings["features_path"]),
                "rows_in_run": int(len(features)),
                "columns": list(features.columns),
            },
            "asset_rolling_correlations": {
                "path": str(settings["correlations_path"]),
                "rows_in_run": int(len(correlations)),
                "columns": list(correlations.columns),
            },
        },
        "notes": [
            "Historical adjusted prices may be revised after their original publication date.",
            "Rolling correlations are a historical proxy, not a forecast of future correlation.",
        ],
    }
    manifest_path = settings["manifest_dir"] / f"run_id={effective_run_id}" / "manifest.json"
    allow_overwrite = (
        settings["overwrite_conflicts"]
        if overwrite_conflicts is None
        else overwrite_conflicts
    )
    report = publish_feature_outputs(
        features,
        correlations,
        settings["features_path"],
        settings["correlations_path"],
        manifest_path,
        manifest,
        overwrite_conflicts=allow_overwrite,
    )
    return {
        "run_id": effective_run_id,
        **report,
        "features_path": str(settings["features_path"]),
        "correlations_path": str(settings["correlations_path"]),
        "manifest_path": str(manifest_path),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build point-in-time asset volatility features and rolling correlations"
    )
    parser.add_argument(
        "--config",
        default="config/features.yaml",
        help="Path to feature pipeline YAML config",
    )
    parser.add_argument("--run-id", help="Optional run identifier (generated when omitted)")
    parser.add_argument(
        "--overwrite-conflicts",
        action="store_true",
        help="Explicitly replace existing rows whose business values changed",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    try:
        report = run_feature_pipeline(
            args.config,
            run_id=args.run_id,
            overwrite_conflicts=True if args.overwrite_conflicts else None,
        )
    except Exception:
        logging.exception("Feature pipeline failed")
        return 1
    logging.info(
        "Feature pipeline %s published %s feature rows and %s correlation rows",
        report["run_id"],
        report["feature_rows"],
        report["correlation_rows"],
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

