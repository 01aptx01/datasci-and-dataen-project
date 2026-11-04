from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any
import json
import subprocess
import uuid


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git_commit() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _dependency_versions() -> dict[str, str | None]:
    packages = ["yfinance", "pandas", "pandas-market-calendars", "PyYAML"]

    result = {}
    for package in packages:
        try:
            result[package] = version(package)
        except PackageNotFoundError:
            result[package] = None

    return result


def _save_metadata(metadata: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "run_metadata.json"
    temp_file = output_dir / "run_metadata.tmp"

    temp_file.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    temp_file.replace(output_file)


def start_run(
    config: dict[str, Any],
    ingestion_window: dict[str, Any],
    audit_root: str = "data/audit",
) -> tuple[dict[str, Any], Path]:
    """สร้าง metadata สถานะเริ่มต้น RUNNING และบันทึกลง audit"""
    run_id = (
        datetime.now(timezone.utc).strftime("run_%Y%m%d_%H%M%S")
        + f"_{uuid.uuid4().hex[:4]}"
    )
    source_batch_id = run_id.replace("run_", "yf_", 1)

    tickers = config["source"]["tickers"]
    output_dir = Path(audit_root) / run_id

    metadata = {
        "run_id": run_id,
        "source_batch_id": source_batch_id,
        "started_at_utc": _utc_now(),
        "finished_at_utc": None,
        "source": {
            "provider": config["source"]["provider"],
            "client": config["source"]["client"],
        },
        "tickers": {
            ticker: {"status": "RUNNING"}
            for ticker in tickers
        },
        "config_start_date": ingestion_window["config_start_date"],
        "config_end_date": ingestion_window["config_end_date"],
        "actual_fetch_start_date": ingestion_window["actual_fetch_start_date"],
        "api_end_date": ingestion_window["api_end_date"],
        "auto_adjust": config["price"]["auto_adjust"],
        "code_version": _git_commit(),
        "dependency_versions": _dependency_versions(),
        "overall_status": "RUNNING",
        "portfolio_ready": False,
    }

    _save_metadata(metadata, output_dir)
    return metadata, output_dir


def finish_run(
    metadata: dict[str, Any],
    ticker_statuses: dict[str, str],
    output_dir: Path,
) -> dict[str, Any]:
    """อัปเดตผลราย ticker และสถานะรวมหลังจบการดึงข้อมูล"""
    allowed_statuses = {"SUCCESS", "FAILED"}

    for ticker in metadata["tickers"]:
        status = ticker_statuses.get(ticker, "FAILED")
        if status not in allowed_statuses:
            raise ValueError(
                f"Invalid status for {ticker}: use SUCCESS or FAILED"
            )
        metadata["tickers"][ticker]["status"] = status

    statuses = [item["status"] for item in metadata["tickers"].values()]
    success_count = statuses.count("SUCCESS")

    if success_count == len(statuses):
        metadata["overall_status"] = "SUCCESS"
    elif success_count > 0:
        metadata["overall_status"] = "PARTIAL"
    else:
        metadata["overall_status"] = "FAILED"

    metadata["portfolio_ready"] = all(
        status == "SUCCESS" for status in statuses
    )
    metadata["finished_at_utc"] = _utc_now()

    _save_metadata(metadata, output_dir)
    return metadata