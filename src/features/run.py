from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from src.features.pipeline import (
    FeatureConfig,
    FeaturePipelineError,
    build_feature_tables,
    collect_feature_warnings,
    filter_corrupted_feature_tickers,
)
from src.features.storage import publish_feature_outputs
from src.features.transactions import (
    prepare_feature_transaction,
    reconcile_feature_quarantine,
    recover_pending_feature_runs,
    update_transaction_status,
    verify_published_feature_run,
)


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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _iso_market_date(value: Any) -> str:
    return pd.Timestamp(value).date().isoformat()


def _source_summary(data: pd.DataFrame) -> dict[str, Any]:
    summary = {}
    for ticker, group in data.groupby("ticker", sort=True):
        batches = sorted(str(value) for value in group["source_batch_id"].dropna().unique())
        dates = pd.to_datetime(group["date"], errors="coerce")
        summary[ticker] = {
            "start_date": _iso_market_date(dates.min()),
            "end_date": _iso_market_date(dates.max()),
            "rows": int(len(group)),
            "source_batch_ids": batches,
        }
    return summary


def _source_snapshot_manifest(data: pd.DataFrame) -> list[dict[str, Any]]:
    snapshots = []
    for batch_id, group in data.groupby("source_batch_id", sort=True):
        batch_id = str(batch_id)
        safe_batch_id = re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", batch_id)
        if safe_batch_id is None:
            raise FeaturePipelineError(
                f"source snapshot batch id is not path-safe: {batch_id}"
            )

        manifest_path = Path("data/raw") / batch_id / "manifest.json"
        if not manifest_path.is_file():
            raise FeaturePipelineError(
                f"Raw Snapshot manifest is missing for source_batch_id {batch_id}: "
                f"{manifest_path}"
            )
        try:
            snapshot_manifest = json.loads(
                manifest_path.read_text(encoding="utf-8")
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise FeaturePipelineError(
                f"Raw Snapshot manifest is unreadable for source_batch_id {batch_id}: "
                f"{manifest_path}"
            ) from error
        if not isinstance(snapshot_manifest, dict):
            raise FeaturePipelineError(
                f"Raw Snapshot manifest must be a JSON object for source_batch_id {batch_id}"
            )
        if snapshot_manifest.get("source_batch_id") != batch_id:
            raise FeaturePipelineError(
                f"Raw Snapshot manifest source_batch_id does not match curated input batch {batch_id}"
            )

        raw_file_path = snapshot_manifest.get("raw_file_path")
        if not isinstance(raw_file_path, str) or not raw_file_path.strip():
            raise FeaturePipelineError(
                f"Raw Snapshot raw_file_path is missing for source_batch_id {batch_id}"
            )
        if not Path(raw_file_path).is_file():
            raise FeaturePipelineError(
                f"Raw Snapshot raw_file_path does not exist for source_batch_id {batch_id}: "
                f"{raw_file_path}"
            )

        raw_file_sha256 = snapshot_manifest.get("sha256")
        if not isinstance(raw_file_sha256, str) or re.fullmatch(
            r"[0-9a-fA-F]{64}", raw_file_sha256
        ) is None:
            raise FeaturePipelineError(
                f"Raw Snapshot sha256 must be 64 hexadecimal characters for source_batch_id {batch_id}"
            )

        snapshots.append(
            {
                "source_batch_id": batch_id,
                "ingestion_run_ids": sorted(
                    str(value) for value in group["run_id"].dropna().unique()
                ),
                "tickers": sorted(str(value) for value in group["ticker"].unique()),
                "start_date": _iso_market_date(
                    pd.to_datetime(group["date"], errors="coerce").min()
                ),
                "end_date": _iso_market_date(
                    pd.to_datetime(group["date"], errors="coerce").max()
                ),
                "rows": int(len(group)),
                "raw_file_path": raw_file_path.replace("\\", "/"),
                "snapshot_manifest_path": str(manifest_path).replace("\\", "/"),
                "raw_file_sha256": raw_file_sha256,
                "manifest_status": "AVAILABLE",
            }
        )
    return snapshots


def run_feature_pipeline(
    config_path: str | Path = "config/features.yaml",
    run_id: str | None = None,
    overwrite_conflicts: bool | None = None,
) -> dict[str, Any]:
    settings = load_config(config_path)
    effective_run_id = run_id if run_id is not None else (
        "feat_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:8]
    )
    if not isinstance(effective_run_id, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", effective_run_id
    ):
        raise FeaturePipelineError("run_id must be path-safe and at most 64 characters")
    recovered_runs = recover_pending_feature_runs(settings["manifest_dir"])
    manifest_path = (
        settings["manifest_dir"] / f"run_id={effective_run_id}" / "manifest.json"
    )
    if manifest_path.parent.exists():
        raise FeaturePipelineError(
            f"run_id already has a manifest directory: {manifest_path.parent}"
        )

    input_path: Path = settings["input_path"]
    if not input_path.is_file():
        raise FileNotFoundError(f"market_prices_daily Parquet not found: {input_path}")

    source = pd.read_parquet(input_path)
    feature_config: FeatureConfig = settings["feature_config"]

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    features, correlations = build_feature_tables(
        source,
        feature_config,
        run_id=effective_run_id,
        feature_as_of_utc=timestamp,
    )
    source_snapshots = _source_snapshot_manifest(source)
    resolved_expected_days = tuple(correlations["date"])
    feature_warnings = collect_feature_warnings(features)
    features, failed_tickers, quarantine_records = filter_corrupted_feature_tickers(
        features
    )
    for record in quarantine_records:
        record["run_id"] = effective_run_id
        record["detected_at_utc"] = timestamp
    if features.empty:
        raise FeaturePipelineError(
            "all ticker features failed quality checks; no feature output was published"
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
            "rows": int(len(source)),
            "start_date": _iso_market_date(
                pd.to_datetime(source["date"], errors="coerce").min()
            ),
            "end_date": _iso_market_date(
                pd.to_datetime(source["date"], errors="coerce").max()
            ),
            "sources_by_ticker": _source_summary(source),
            "source_snapshots": source_snapshots,
        },
        "config": {
            "path": str(config_file),
            "sha256": _sha256_file(config_file),
            "values": settings["raw"],
            "expected_trading_days": [
                day.isoformat() for day in resolved_expected_days
            ],
        },
        "quality": {
            "failed_tickers": failed_tickers,
            "quarantine_records": len(quarantine_records),
            "warnings": feature_warnings,
            "results_path": str(manifest_path.parent / "quality_results.parquet"),
            "finding_count": len(quarantine_records) + len(feature_warnings),
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
    allow_overwrite = (
        settings["overwrite_conflicts"]
        if overwrite_conflicts is None
        else overwrite_conflicts
    )
    quarantine_path = Path("logs/quarantine.csv")
    quality_path = manifest_path.parent / "quality_results.parquet"
    transaction_path = manifest_path.parent / "transaction.json"

    def prepare_transaction() -> None:
        prepare_feature_transaction(
            manifest_path.parent,
            effective_run_id,
            timestamp,
            quarantine_records,
            feature_warnings,
            quarantine_path,
            settings["features_path"],
            settings["correlations_path"],
            manifest_path,
            len(features),
            len(correlations),
        )

    report = publish_feature_outputs(
        features,
        correlations,
        settings["features_path"],
        settings["correlations_path"],
        manifest_path,
        manifest,
        overwrite_conflicts=allow_overwrite,
        before_replace=prepare_transaction,
    )
    verify_published_feature_run(json.loads(transaction_path.read_text(encoding="utf-8")))
    update_transaction_status(transaction_path, "OUTPUTS_PUBLISHED")
    reconcile_feature_quarantine(quality_path, quarantine_path)
    update_transaction_status(transaction_path, "COMMITTED")
    return {
        "run_id": effective_run_id,
        **report,
        "failed_tickers": failed_tickers,
        "quarantine_records": len(quarantine_records),
        "feature_warning_count": len(feature_warnings),
        "features_path": str(settings["features_path"]),
        "correlations_path": str(settings["correlations_path"]),
        "manifest_path": str(manifest_path),
        "quality_results_path": str(quality_path),
        "transaction_status": "COMMITTED",
        "recovered_run_ids": recovered_runs,
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

