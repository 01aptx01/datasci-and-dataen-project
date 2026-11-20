from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.targets.calendar import resolve_target_sessions
from src.targets.config import TargetConfig, TargetConfigError, load_target_config
from src.targets.pipeline import TargetPipelineError, build_target_labels
from src.targets.storage import publish_target_labels, recover_target_transactions


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _date_text(value: Any) -> str:
    return pd.Timestamp(value).date().isoformat()


def _source_summary(data: pd.DataFrame) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    dates = pd.to_datetime(data["date"], errors="coerce")
    for ticker, group in data.assign(_date=dates).groupby("ticker", sort=True):
        source_dates = group["_date"].dropna()
        summary[str(ticker)] = {
            "start_date": _date_text(source_dates.min()),
            "end_date": _date_text(source_dates.max()),
            "rows": int(len(group)),
            "source_batch_ids": sorted(
                str(value) for value in group["source_batch_id"].dropna().unique()
            ),
        }
    return summary


def _source_snapshot_manifest(data: pd.DataFrame) -> list[dict[str, Any]]:
    snapshots: list[dict[str, Any]] = []
    for batch_id, group in data.groupby("source_batch_id", sort=True):
        batch_id = str(batch_id)
        manifest_path = Path("data/raw") / batch_id / "manifest.json"
        if not manifest_path.is_file():
            raise TargetPipelineError(
                f"Raw Snapshot manifest is missing for source_batch_id {batch_id}: {manifest_path}"
            )
        try:
            snapshot = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise TargetPipelineError(
                f"Raw Snapshot manifest is unreadable for source_batch_id {batch_id}"
            ) from error
        if not isinstance(snapshot, dict) or snapshot.get("source_batch_id") != batch_id:
            raise TargetPipelineError(
                f"Raw Snapshot manifest source_batch_id does not match curated input: {batch_id}"
            )
        raw_file_value = snapshot.get("raw_file_path")
        if not isinstance(raw_file_value, str) or not raw_file_value.strip():
            raise TargetPipelineError(f"Raw Snapshot manifest has no raw_file_path: {manifest_path}")
        raw_file_path = Path(raw_file_value)
        if not raw_file_path.is_absolute():
            raw_file_path = Path.cwd() / raw_file_path
        if not raw_file_path.is_file():
            raise TargetPipelineError(
                f"Raw Snapshot file is missing for source_batch_id {batch_id}: {raw_file_path}"
            )
        raw_sha = snapshot.get("sha256")
        if not isinstance(raw_sha, str) or re.fullmatch(r"[0-9a-fA-F]{64}", raw_sha) is None:
            raise TargetPipelineError(
                f"Raw Snapshot manifest has an invalid sha256 for source_batch_id {batch_id}"
            )
        dates = pd.to_datetime(group["date"], errors="coerce")
        snapshots.append(
            {
                "source_batch_id": batch_id,
                "snapshot_manifest_path": str(manifest_path).replace("\\", "/"),
                "snapshot_manifest_sha256": _sha256_file(manifest_path),
                "raw_file_path": str(raw_file_value).replace("\\", "/"),
                "raw_file_sha256": raw_sha.lower(),
                "source": snapshot.get("source"),
                "client": snapshot.get("client"),
                "source_version": snapshot.get("yfinance_version"),
                "start_date": _date_text(dates.min()),
                "end_date": _date_text(dates.max()),
                "rows": int(len(group)),
                "manifest_status": "AVAILABLE",
            }
        )
    return snapshots


def _validate_run_id(run_id: str) -> str:
    if not isinstance(run_id, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", run_id) is None:
        raise TargetPipelineError("run_id must be path-safe and at most 64 characters")
    return run_id


def _raw_config_values(config: TargetConfig) -> dict[str, Any]:
    return {
        "target": {
            "start_date": config.start_date.isoformat(),
            "end_date": config.end_date.isoformat(),
            "target_version": config.target_version,
        },
        "calendar": {"market": config.market},
        "paths": {
            "input": str(config.input_path),
            "output": str(config.output_path),
            "manifest_dir": str(config.manifest_dir),
        },
        "publish": {"overwrite_conflicts": config.overwrite_conflicts},
    }


def run_target_pipeline(
    config_path: str | Path = "config/target.yaml",
    run_id: str | None = None,
    overwrite_conflicts: bool | None = None,
    overwrite_reason: str | None = None,
) -> dict[str, Any]:
    config_file = Path(config_path)
    config: TargetConfig = load_target_config(config_file)
    effective_run_id = run_id or (
        "target_"
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        + "_"
        + uuid.uuid4().hex[:8]
    )
    _validate_run_id(effective_run_id)

    recovered_runs = recover_target_transactions(config.manifest_dir)
    run_dir = config.manifest_dir / f"run_id={effective_run_id}"
    manifest_path = run_dir / "manifest.json"
    if run_dir.exists():
        raise TargetPipelineError(f"run_id already has a Target manifest directory: {run_dir}")
    if not config.input_path.is_file():
        raise FileNotFoundError(f"market_prices_daily Parquet not found: {config.input_path}")
    source = pd.read_parquet(config.input_path)
    if not isinstance(source, pd.DataFrame) or source.empty or "date" not in source:
        raise TargetPipelineError("market_prices_daily must contain rows and a date column")
    parsed_dates = pd.to_datetime(source["date"], errors="coerce")
    if parsed_dates.isna().any():
        raise TargetPipelineError("market_prices_daily contains an invalid date")
    source_dates = tuple(parsed_dates.dt.date)
    source_min = min(source_dates)
    source_max = max(source_dates)
    if not (source_min <= config.start_date <= config.end_date <= source_max):
        raise TargetPipelineError(
            "target.start_date..end_date must be covered by market_prices_daily input dates"
        )

    expected_sessions, anchor_dates = resolve_target_sessions(config, source_dates)
    created_at = datetime.now(timezone.utc)
    labels, findings = build_target_labels(
        source,
        expected_trading_days=expected_sessions,
        anchor_dates=anchor_dates,
        run_id=effective_run_id,
        target_version=config.target_version,
        processed_at_utc=created_at,
    )
    source_snapshots = _source_snapshot_manifest(source)
    findings_by_type = dict(sorted(Counter(item["finding_type"] for item in findings).items()))
    mature_count = int(labels["is_label_mature"].sum())
    pending_count = int((~labels["is_label_mature"]).sum())
    resolved_overwrite_conflicts = (
        config.overwrite_conflicts
        if overwrite_conflicts is None
        else overwrite_conflicts
    )

    manifest = {
        "run_id": effective_run_id,
        "pipeline": "target_label_pipeline",
        "target_version": config.target_version,
        "created_at_utc": created_at.isoformat().replace("+00:00", "Z"),
        "input": {
            "table": "market_prices_daily",
            "path": str(config.input_path),
            "sha256": _sha256_file(config.input_path),
            "rows": int(len(source)),
            "start_date": _date_text(parsed_dates.min()),
            "end_date": _date_text(parsed_dates.max()),
            "sources_by_ticker": _source_summary(source),
            "source_snapshots": source_snapshots,
        },
        "calendar": {
            "market": config.market,
            "expected_trading_days": len(expected_sessions),
            "calendar_start_date": expected_sessions[0].isoformat(),
            "calendar_end_date": expected_sessions[-1].isoformat(),
        },
        "scope": {
            "anchor_start_date": config.start_date.isoformat(),
            "anchor_end_date": config.end_date.isoformat(),
            "anchor_session_count": len(anchor_dates),
        },
        "config": {
            "path": str(config_file),
            "sha256": _sha256_file(config_file),
            "values": _raw_config_values(config),
            "overwrite_conflicts": resolved_overwrite_conflicts,
            "overwrite_reason": overwrite_reason if resolved_overwrite_conflicts else None,
        },
        "quality": {
            "finding_count": len(findings),
            "finding_counts_by_type": findings_by_type,
            "findings": findings,
            "mature_rows_in_run": mature_count,
            "pending_rows_in_run": pending_count,
            "rows_by_ticker": {
                str(ticker): int(count)
                for ticker, count in labels.groupby("ticker").size().items()
            },
        },
        "notes": [
            "record_created_at_utc and label_matured_at_utc are actual processing times, not simulated historical availability times.",
            "Historical input rows before target.start_date are used only to validate returns and are not emitted as labels.",
        ],
    }
    allow_overwrite = resolved_overwrite_conflicts
    publish_counts, final_manifest = publish_target_labels(
        labels,
        config.output_path,
        manifest_path,
        manifest,
        run_dir=run_dir,
        overwrite_conflicts=allow_overwrite,
        overwrite_reason=overwrite_reason,
    )

    return {
        "run_id": effective_run_id,
        "rows_in_run": int(len(labels)),
        "rows_after_publish": final_manifest["output"]["rows_after_publish"],
        "mature_rows_in_run": mature_count,
        "pending_rows_in_run": pending_count,
        "finding_count": len(findings),
        "finding_counts_by_type": findings_by_type,
        "publish_counts": publish_counts,
        "date_range": {
            "start_date": labels["date"].min().isoformat(),
            "end_date": labels["date"].max().isoformat(),
        },
        "output_path": str(config.output_path),
        "manifest_path": str(manifest_path),
        "transaction_status": "COMMITTED",
        "recovered_run_ids": recovered_runs,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build validated five-session forward-volatility labels for SPY, IEF, and GLD"
    )
    parser.add_argument("--config", default="config/target.yaml", help="Path to Target YAML config")
    parser.add_argument("--run-id", help="Optional path-safe run identifier")
    parser.add_argument(
        "--overwrite-conflicts",
        action="store_true",
        default=None,
        help="Allow audited changes to existing mature labels",
    )
    parser.add_argument(
        "--overwrite-reason",
        help="Required explanation when --overwrite-conflicts is used",
    )
    args = parser.parse_args(argv)
    try:
        report = run_target_pipeline(
            args.config,
            run_id=args.run_id,
            overwrite_conflicts=args.overwrite_conflicts,
            overwrite_reason=args.overwrite_reason,
        )
    except (FileNotFoundError, TargetConfigError, TargetPipelineError) as error:
        logging.error("Target Pipeline failed: %s", error)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
