import csv
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import pandas as pd


QUARANTINE_COLUMNS = [
    "run_id",
    "source_batch_id",
    "date",
    "ticker",
    "raw_value",
    "reason",
    "detected_at_utc",
]


def append_to_quarantine_csv(
    records: list[dict[str, Any]],
    csv_path: str | Path = "logs/quarantine.csv",
) -> None:
    """บันทึกรายการที่ตก validation ลง logs/quarantine.csv แบบ append-only ตาม Data Contract"""
    if not records:
        return

    path = Path(csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = path.is_file() and path.stat().st_size > 0

    with path.open("a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=QUARANTINE_COLUMNS)
        if not file_exists:
            writer.writeheader()
        for record in records:
            row = {
                col: (
                    record.get(col)
                    if record.get(col) is not None
                    else ""
                )
                for col in QUARANTINE_COLUMNS
            }
            writer.writerow(row)


def handle_quarantine_and_publish(
    data: pd.DataFrame,
    validation_report: dict[str, Any],
    tickers: list[str],
    run_id: str,
    source_batch_id: str | None = None,
    quarantine_root: str = "data/quarantine",
    publish_root: str = "data/validated",
    quarantine_csv_path: str = "logs/quarantine.csv",
) -> dict[str, Any]:
    run_quarantine_dir = Path(quarantine_root) / f"run_id={run_id}"
    run_publish_dir = Path(publish_root) / f"run_id={run_id}"

    # ป้องกันการเขียนทับหลักฐานจาก run เดิม
    if run_quarantine_dir.exists() or run_publish_dir.exists():
        raise FileExistsError(f"Output already exists for run_id={run_id}")

    run_quarantine_dir.mkdir(parents=True)
    run_publish_dir.mkdir(parents=True)

    ticker_results = validation_report["ticker_results"]
    quarantine_records = []
    anomaly_records = []
    summary = {}
    detected_at_utc = datetime.now(timezone.utc).isoformat()

    for ticker in tickers:
        result = ticker_results.get(ticker, {})
        status = result.get("status", "FAILED")
        errors = result.get("error_codes", [])

        # เก็บ quarantine findings พร้อมอ้างอิง run
        for item in result.get("quarantine", []):
            quarantine_records.append({
                "run_id": run_id,
                "source_batch_id": source_batch_id or "",
                "ticker": ticker,
                "date": item.get("date", ""),
                "raw_value": (
                    item.get("raw_value")
                    if item.get("raw_value") is not None
                    else ""
                ),
                "reason": item.get("reason", ""),
                "detected_at_utc": detected_at_utc,
            })

        for item in result.get("warnings", []):
            anomaly_records.append({
                "run_id": run_id,
                "ticker": ticker,
                **item,
            })

        ticker_data = data.loc[data["ticker"] == ticker].copy()
        blocked = status == "FAILED"

        if blocked:
            publish_status = "BLOCKED"
            rows_published = 0
        else:
            publish_status = "PUBLISHED"
            rows_published = len(ticker_data)

            ticker_dir = run_publish_dir / f"ticker={ticker}"
            ticker_dir.mkdir()
            ticker_data.to_parquet(ticker_dir / "data.parquet", index=False)

        summary[ticker] = {
            "validation_status": status,
            "publish_status": publish_status,
            "rows_checked": result.get("rows_checked", len(ticker_data)),
            "rows_passed": result.get("rows_passed", 0),
            "rows_published": rows_published,
            "quarantined_records": sum(
                1 for item in result.get("quarantine", [])
                if item.get("reason") != "MISSING_EXPECTED_TRADING_DAY"
            ),
            "missing_day_events": sum(
                1 for item in result.get("quarantine", [])
                if item.get("reason") == "MISSING_EXPECTED_TRADING_DAY"
            ),
            "blocked_reasons": errors if blocked else [],
        }

    # บันทึกลง canonical logs/quarantine.csv แบบ append-only
    append_to_quarantine_csv(quarantine_records, quarantine_csv_path)

    # แยก hard-error quarantine ออกจาก anomaly review queue
    (run_quarantine_dir / "records.json").write_text(
        json.dumps(quarantine_records, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    (run_quarantine_dir / "anomaly_review.json").write_text(
        json.dumps(anomaly_records, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    portfolio_ready = all(
        item["publish_status"] == "PUBLISHED"
        for item in summary.values()
    )

    output = {
        "run_id": run_id,
        "source_batch_id": source_batch_id,
        "ticker_summary": summary,
        "portfolio_ready": portfolio_ready,
        "portfolio_status": "READY" if portfolio_ready else "BLOCKED",
        "quarantine_path": str(run_quarantine_dir),
        "quarantine_csv": str(quarantine_csv_path),
        "quarantined_records_count": len(quarantine_records),
        "publish_path": str(run_publish_dir),
    }

    (run_quarantine_dir / "summary.json").write_text(
        json.dumps(output, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    return output