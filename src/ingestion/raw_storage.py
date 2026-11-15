import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


def _get_pkg_version(package_name: str) -> str | None:
    try:
        return version(package_name)
    except PackageNotFoundError:
        return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def save_raw_snapshot(
    results: dict[str, dict[str, Any]],
    run_metadata: dict[str, Any],
    config: dict[str, Any],
    ingestion_window: dict[str, Any],
    root_dir: str = "data/raw",
) -> dict[str, Any]:
    """
    บันทึกข้อมูลดิบเป็น data/raw/<source_batch_id>/raw_prices.csv
    พร้อม manifest.json ตาม Data Contract ข้อ 3 โดยไม่เขียนทับ snapshot เดิม
    """

    run_id = run_metadata["run_id"]
    source_batch_id = run_metadata.get("source_batch_id") or run_id
    batch_dir = Path(root_dir) / source_batch_id

    if batch_dir.exists():
        raise FileExistsError(
            f"Snapshot already exists for {source_batch_id}; refusing to overwrite"
        )

    batch_dir.mkdir(parents=True)
    ticker_metadata = {}
    raw_frames = []

    for ticker, result in results.items():
        status = result.get("status", "FAILED")
        data = result.get("data")

        if status != "SUCCESS" or not isinstance(data, pd.DataFrame):
            ticker_metadata[ticker] = {
                "status": status,
                "rows": 0,
                "errors": result.get("errors", []),
            }
            continue

        try:
            df_ticker = data.copy()
            df_ticker["ticker"] = ticker
            if "date" not in df_ticker.columns:
                df_ticker.index.name = "date"
                df_ticker = df_ticker.reset_index()

            raw_frames.append(df_ticker)
            ticker_metadata[ticker] = {
                "status": "SAVED",
                "rows": len(df_ticker),
                "errors": [],
            }
        except Exception as error:
            ticker_metadata[ticker] = {
                "status": "STORE_FAILED",
                "rows": 0,
                "errors": [f"{type(error).__name__}: {error}"],
            }

    raw_csv_path = batch_dir / "raw_prices.csv"

    if raw_frames:
        combined_raw = pd.concat(raw_frames, ignore_index=True)
        # นำ date และ ticker ขึ้นก่อนหากมี
        front_cols = [c for c in ["date", "ticker"] if c in combined_raw.columns]
        other_cols = [c for c in combined_raw.columns if c not in front_cols]
        combined_raw = combined_raw[front_cols + other_cols]
        combined_raw.to_csv(raw_csv_path, index=False)
        raw_sha256 = _sha256(raw_csv_path)
        rows_fetched_raw = len(combined_raw)
    else:
        raw_csv_path.write_text("date,ticker\n", encoding="utf-8")
        raw_sha256 = _sha256(raw_csv_path)
        rows_fetched_raw = 0

    manifest = {
        "source_batch_id": source_batch_id,
        "run_id": run_id,
        "source": config["source"]["provider"],
        "client": config["source"]["client"],
        "tickers": config["source"]["tickers"],
        "auto_adjust": config["price"]["auto_adjust"],
        "interval": config["source"]["interval"],
        "requested_start_date": ingestion_window["config_start_date"],
        "requested_end_date": ingestion_window["config_end_date"],
        "effective_end_date": (
            ingestion_window.get("effective_end_date")
            or ingestion_window["config_end_date"]
        ),
        "actual_fetch_start_date": ingestion_window["actual_fetch_start_date"],
        "api_end_date": ingestion_window["api_end_date"],
        "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
        "raw_file_path": str(raw_csv_path).replace("\\", "/"),
        "rows_fetched_raw": rows_fetched_raw,
        "yfinance_version": _get_pkg_version("yfinance"),
        "sha256": raw_sha256,
        "tickers_detail": ticker_metadata,
    }

    manifest_path = batch_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return {
        "source_batch_id": source_batch_id,
        "run_id": run_id,
        "raw_file_path": str(raw_csv_path).replace("\\", "/"),
        "manifest_path": str(manifest_path).replace("\\", "/"),
        "sha256": raw_sha256,
        "tickers": ticker_metadata,
        "manifest": manifest,
    }