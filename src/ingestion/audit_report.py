import json
from pathlib import Path
from typing import Any

import pandas as pd


def append_to_ingestion_runs_jsonl(
    audit_entry: dict[str, Any],
    jsonl_path: str | Path = "logs/ingestion_runs.jsonl",
) -> None:
    """บันทึกสรุปผลการรันลง logs/ingestion_runs.jsonl แบบ append-only (1 JSON Object ต่อ 1 บรรทัด)"""
    path = Path(jsonl_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(
            json.dumps(audit_entry, ensure_ascii=False, default=str) + "\n"
        )


def _date_bounds(data: Any) -> tuple[str | None, str | None]:
    """คืนวันที่แรกและสุดท้ายที่พบในข้อมูล"""
    if not isinstance(data, pd.DataFrame) or data.empty:
        return None, None

    dates = pd.to_datetime(data.index, errors="coerce")
    dates = dates[~dates.isna()]

    if len(dates) == 0:
        return None, None

    return dates.min().date().isoformat(), dates.max().date().isoformat()


def create_run_report(
    run_metadata: dict[str, Any],
    fetch_results: dict[str, dict[str, Any]],
    validation_report: dict[str, Any],
    quarantine_result: dict[str, Any],
    publish_report: dict[str, Any],
    audit_root: str = "data/audit",
    jsonl_path: str | Path = "logs/ingestion_runs.jsonl",
) -> dict[str, Any]:
    """สร้าง Audit report รวมของ run และบันทึกเป็น JSON กับ Markdown พร้อมลง logs/ingestion_runs.jsonl"""

    run_id = run_metadata["run_id"]
    ticker_report = {}

    validation_by_ticker = validation_report.get("ticker_results", {})
    quarantine_by_ticker = quarantine_result.get("ticker_summary", {})

    for ticker in run_metadata.get("tickers", {}):
        fetched = fetch_results.get(ticker, {})
        validation = validation_by_ticker.get(ticker, {})
        quarantine = quarantine_by_ticker.get(ticker, {})

        raw_data = fetched.get("data")
        actual_min, actual_max = _date_bounds(raw_data)

        ticker_report[ticker] = {
            "fetched_rows": fetched.get("rows_fetched", 0),
            "fetch_attempts": fetched.get("attempts", 0),
            "actual_min_date": actual_min,
            "actual_max_date": actual_max,
            "rows_validated": validation.get("rows_checked", 0),
            "rows_validated_passed": validation.get("rows_passed", 0),
            "rows_quarantined": quarantine.get("quarantined_records", 0),
            "missing_day_events": quarantine.get("missing_day_events", 0),
            "anomalies": len(validation.get("warnings", [])),
            "rows_published": quarantine.get("rows_published", 0),
            "validation_status": validation.get("status", "FAILED"),
            "publish_status": quarantine.get("publish_status", "BLOCKED"),
            "error_codes": validation.get("error_codes", []),
            "warnings": validation.get("warnings", []),
        }

    ticker_statuses = [
        item["publish_status"] for item in ticker_report.values()
    ]
    if all(status == "PUBLISHED" for status in ticker_statuses):
        overall_status = "SUCCESS"
    elif any(status == "PUBLISHED" for status in ticker_statuses):
        overall_status = "PARTIAL_SUCCESS"
    else:
        overall_status = "FAILED"

    report = {
        "run_id": run_id,
        "source_batch_id": run_metadata.get("source_batch_id"),
        "mode": run_metadata.get("mode"),
        "started_at_utc": run_metadata.get("started_at_utc"),
        "finished_at_utc": run_metadata.get("finished_at_utc"),
        "source": run_metadata.get("source"),
        "config_start_date": run_metadata.get("config_start_date"),
        "config_end_date": run_metadata.get("config_end_date"),
        "actual_fetch_start_date": run_metadata.get(
            "actual_fetch_start_date"
        ),
        "api_end_date": run_metadata.get("api_end_date"),
        "auto_adjust": run_metadata.get("auto_adjust"),
        "code_version": run_metadata.get("code_version"),
        "dependency_versions": run_metadata.get("dependency_versions"),
        "raw_snapshot_path": f"data/raw/yfinance/run_id={run_id}",
        "validated_data_path": publish_report.get("table"),
        "ticker_results": ticker_report,
        "overall_status": overall_status,
        "portfolio_ready": publish_report.get("portfolio_ready", False),
        "publish_counts": {
            "rows_inserted": publish_report.get("rows_inserted", 0),
            "rows_updated": publish_report.get("rows_updated", 0),
            "rows_unchanged": publish_report.get("rows_unchanged", 0),
        },
    }

    # บันทึก logs/ingestion_runs.jsonl 1 บรรทัดตาม Data Contract ข้อ 7
    contract_tickers = {}
    error_messages = []
    total_fetched = 0
    total_passed = 0
    total_published = 0
    total_quarantined = 0
    total_anomalies = 0

    for ticker, item in ticker_report.items():
        t_status = "SUCCESS" if item["publish_status"] == "PUBLISHED" else "FAILED"
        contract_tickers[ticker] = {
            "status": t_status,
            "rows_fetched_raw": item["fetched_rows"],
            "rows_validated_passed": item["rows_validated_passed"],
            "rows_published": item["rows_published"],
        }
        total_fetched += item["fetched_rows"]
        total_passed += item["rows_validated_passed"]
        total_published += item["rows_published"]
        total_quarantined += item["rows_quarantined"] + item["missing_day_events"]
        total_anomalies += item["anomalies"]
        if item["error_codes"]:
            error_messages.append(f"{ticker}: {', '.join(item['error_codes'])}")

    jsonl_entry = {
        "run_id": run_id,
        "source_batch_id": run_metadata.get("source_batch_id"),
        "started_at_utc": run_metadata.get("started_at_utc"),
        "finished_at_utc": run_metadata.get("finished_at_utc"),
        "status": overall_status,
        "config_start_date": run_metadata.get("config_start_date"),
        "config_end_date": run_metadata.get("config_end_date"),
        "actual_fetch_start_date": run_metadata.get("actual_fetch_start_date"),
        "effective_end_date": (
            run_metadata.get("effective_end_date")
            or run_metadata.get("config_end_date")
        ),
        "raw_snapshot_path": (
            run_metadata.get("raw_snapshot_path")
            or report.get("raw_snapshot_path")
        ),
        "rows_fetched_raw": total_fetched,
        "rows_validated_passed": total_passed,
        "rows_published": total_published,
        "rows_quarantined": total_quarantined,
        "rows_anomaly_flagged": total_anomalies,
        "tickers": contract_tickers,
        "error_message": "; ".join(error_messages) if error_messages else None,
    }
    append_to_ingestion_runs_jsonl(jsonl_entry, jsonl_path=jsonl_path)

    output_dir = Path(audit_root) / f"run_id={run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)

    (output_dir / "run_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    lines = [
        f"# Ingestion Report — {run_id}",
        "",
        f"- Overall status: **{overall_status}**",
        f"- Portfolio ready: **{report['portfolio_ready']}**",
        f"- Analysis range: {report['config_start_date']} to "
        f"{report['config_end_date']}",
        f"- Fetch starts: {report['actual_fetch_start_date']}",
        "",
        "| Ticker | Fetched | Validated | Quarantined rows | Missing days "
        "| Anomalies | Published | Status |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]

    for ticker, item in ticker_report.items():
        lines.append(
            f"| {ticker} | {item['fetched_rows']} "
            f"| {item['rows_validated_passed']} "
            f"| {item['rows_quarantined']} "
            f"| {item['missing_day_events']} "
            f"| {item['anomalies']} "
            f"| {item['rows_published']} "
            f"| {item['publish_status']} |"
        )

    (output_dir / "run_report.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    return report