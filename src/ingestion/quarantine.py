import json
from pathlib import Path
from typing import Any

import pandas as pd


def handle_quarantine_and_publish(
    data: pd.DataFrame,
    validation_report: dict[str, Any],
    tickers: list[str],
    run_id: str,
    quarantine_root: str = "data/quarantine",
    publish_root: str = "data/validated",
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

    for ticker in tickers:
        result = ticker_results.get(ticker, {})
        status = result.get("status", "FAILED")
        errors = result.get("error_codes", [])

        # เก็บ quarantine findings พร้อมอ้างอิง run
        for item in result.get("quarantine", []):
            quarantine_records.append({
                "run_id": run_id,
                "ticker": ticker,
                **item,
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
        "ticker_summary": summary,
        "portfolio_ready": portfolio_ready,
        "portfolio_status": "READY" if portfolio_ready else "BLOCKED",
        "quarantine_path": str(run_quarantine_dir),
        "publish_path": str(run_publish_dir),
    }

    (run_quarantine_dir / "summary.json").write_text(
        json.dumps(output, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    return output