import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


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
    root_dir: str = "data/raw/yfinance",
) -> dict[str, Any]:
    """บันทึกข้อมูลดิบจาก yfinance และ metadata โดยไม่เขียนทับ run เดิม"""

    run_id = run_metadata["run_id"]
    run_dir = Path(root_dir) / f"run_id={run_id}"

    if run_dir.exists():
        raise FileExistsError(
            f"Snapshot already exists for {run_id}; refusing to overwrite"
        )

    run_dir.mkdir(parents=True)
    ticker_metadata = {}

    for ticker, result in results.items():
        status = result.get("status", "FAILED")
        data = result.get("data")

        if status != "SUCCESS" or not isinstance(data, pd.DataFrame):
            ticker_metadata[ticker] = {
                "status": status,
                "rows": 0,
                "path": None,
                "sha256": None,
                "errors": result.get("errors", []),
            }
            continue

        ticker_dir = run_dir / f"ticker={ticker}"
        ticker_dir.mkdir()
        data_path = ticker_dir / "data.parquet"

        try:
            # บันทึก DataFrame ตามที่ yfinance ส่งกลับมา ก่อน transform
            data.to_parquet(data_path, index=True)

            ticker_metadata[ticker] = {
                "status": "SAVED",
                "rows": len(data),
                "path": str(data_path),
                "sha256": _sha256(data_path),
                "errors": [],
            }
        except Exception as error:
            ticker_metadata[ticker] = {
                "status": "STORE_FAILED",
                "rows": 0,
                "path": None,
                "sha256": None,
                "errors": [f"{type(error).__name__}: {error}"],
            }

    snapshot_metadata = {
        "run_id": run_id,
        "source_batch_id": run_metadata.get("source_batch_id"),
        "source": config["source"]["provider"],
        "client": config["source"]["client"],
        "interval": config["source"]["interval"],
        "auto_adjust": config["price"]["auto_adjust"],
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "config_start_date": ingestion_window["config_start_date"],
        "config_end_date": ingestion_window["config_end_date"],
        "actual_fetch_start_date": ingestion_window["actual_fetch_start_date"],
        "api_end_date": ingestion_window["api_end_date"],
        "tickers": ticker_metadata,
    }

    metadata_path = run_dir / "metadata.json"
    metadata_path.write_text(
        json.dumps(snapshot_metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return snapshot_metadata