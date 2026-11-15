import argparse
import logging
import sys
from pathlib import Path

from src.ingestion.config import load_config
from src.ingestion.calendar import build_ingestion_window
from src.ingestion.run_metadata import start_run, finish_run
from src.ingestion.fetch import fetch_all
from src.ingestion.raw_storage import save_raw_snapshot
from src.ingestion.transform import transform_all
from src.ingestion.validate import validate_all
from src.ingestion.quarantine import handle_quarantine_and_publish
from src.ingestion.publish import publish_market_prices
from src.ingestion.audit_report import (
    create_run_report,
    append_to_ingestion_runs_jsonl,
)


def run_pipeline(config_path: str) -> int:
    metadata = None
    audit_dir = None

    try:
        # Session 2–4: อ่าน Config, คำนวณช่วงวัน และเริ่ม run
        config = load_config(config_path)
        window = build_ingestion_window(config)
        metadata, audit_dir = start_run(config, window)

        logging.info("เริ่ม pipeline: %s", metadata["run_id"])

        # Session 5: ดึงข้อมูลแยก ticker
        fetch_results = fetch_all(config, window)

        # Session 6: บันทึก raw snapshot ก่อน transform
        snapshot = save_raw_snapshot(
            results=fetch_results,
            run_metadata=metadata,
            config=config,
            ingestion_window=window,
        )
        metadata["raw_snapshot_path"] = snapshot.get("raw_file_path")

        # ถ้าบันทึก raw ของ ticker ไม่สำเร็จ ให้บล็อก ticker นั้น
        for ticker, snapshot_info in snapshot["tickers"].items():
            if snapshot_info["status"] != "SAVED":
                fetch_results[ticker]["status"] = "FAILED"
                fetch_results[ticker]["failure_type"] = "RAW_STORAGE_ERROR"
                fetch_results[ticker]["errors"].extend(
                    snapshot_info.get("errors", [])
                )
                fetch_results[ticker]["data"] = None

        # Session 7–8: transform และตรวจข้อมูล
        staging_data = transform_all(
            fetch_results=fetch_results,
            config=config,
            run_metadata=metadata,
            ingestion_window=window,
        )

        validation_report = validate_all(
            data=staging_data,
            expected_trading_days=window["expected_trading_days"],
            tickers=config["source"]["tickers"],
            anomaly_threshold=config["validation"][
                "simple_return_anomaly_threshold"
            ],
            config_start_date=window.get("config_start_date"),
        )

        # Session 9: กักข้อมูลผิดและกำหนด ticker ที่ publish ได้
        quarantine_result = handle_quarantine_and_publish(
            data=staging_data,
            validation_report=validation_report,
            tickers=config["source"]["tickers"],
            run_id=metadata["run_id"],
            source_batch_id=metadata.get("source_batch_id"),
        )

        # Session 10: upsert เฉพาะ ticker ที่ผ่าน
        publishable_tickers = [
            ticker
            for ticker, result in quarantine_result["ticker_summary"].items()
            if result["publish_status"] == "PUBLISHED"
        ]
        publishable_data = staging_data[
            staging_data["ticker"].isin(publishable_tickers)
        ].copy()

        publish_report = publish_market_prices(
            validated_data=publishable_data,
            ticker_summary=quarantine_result["ticker_summary"],
            run_id=metadata["run_id"],
        )

        # ปิด run และบันทึกสถานะราย ticker
        final_ticker_statuses = {
            ticker: (
                "SUCCESS"
                if result["publish_status"] == "PUBLISHED"
                else "FAILED"
            )
            for ticker, result in quarantine_result["ticker_summary"].items()
        }
        metadata = finish_run(
            metadata=metadata,
            ticker_statuses=final_ticker_statuses,
            output_dir=audit_dir,
        )

        # Session 11: สร้างรายงานรวม
        create_run_report(
            run_metadata=metadata,
            fetch_results=fetch_results,
            validation_report=validation_report,
            quarantine_result=quarantine_result,
            publish_report=publish_report,
        )

        logging.info(
            "จบ run %s: status=%s, portfolio_ready=%s",
            metadata["run_id"],
            metadata["overall_status"],
            metadata["portfolio_ready"],
        )

        if metadata["overall_status"] == "SUCCESS":
            return 0
        if metadata["overall_status"] in ("PARTIAL", "PARTIAL_SUCCESS"):
            return 2
        return 1

    except Exception as error:
        logging.exception("Pipeline ล้มเหลว")

        # บันทึกสถานะ FAILED หากสร้าง run metadata ไปแล้ว
        if metadata is not None and audit_dir is not None:
            try:
                failed_statuses = {
                    ticker: "FAILED"
                    for ticker in metadata.get("tickers", {})
                }
                metadata = finish_run(metadata, failed_statuses, audit_dir)
                append_to_ingestion_runs_jsonl({
                    "run_id": metadata["run_id"],
                    "source_batch_id": metadata.get("source_batch_id"),
                    "started_at_utc": metadata.get("started_at_utc"),
                    "finished_at_utc": metadata.get("finished_at_utc"),
                    "status": "FAILED",
                    "config_start_date": metadata.get("config_start_date"),
                    "config_end_date": metadata.get("config_end_date"),
                    "actual_fetch_start_date": metadata.get("actual_fetch_start_date"),
                    "effective_end_date": metadata.get("effective_end_date") or metadata.get("config_end_date"),
                    "raw_snapshot_path": metadata.get("raw_snapshot_path"),
                    "rows_fetched_raw": 0,
                    "rows_validated_passed": 0,
                    "rows_published": 0,
                    "rows_quarantined": 0,
                    "rows_anomaly_flagged": 0,
                    "tickers": {
                        t: {
                            "status": "FAILED",
                            "rows_fetched_raw": 0,
                            "rows_validated_passed": 0,
                            "rows_published": 0,
                        }
                        for t in metadata.get("tickers", {})
                    },
                    "error_message": f"PIPELINE_ERROR: {error}",
                })
            except Exception:
                logging.exception("บันทึกสถานะ FAILED ไม่สำเร็จ")

        return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the DSDN ingestion pipeline"
    )
    parser.add_argument(
        "--config",
        default="config/ingestion.yaml",
        help="Path to ingestion YAML config",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if not Path(args.config).is_file():
        logging.error("ไม่พบไฟล์ Config: %s", args.config)
        return 1

    return run_pipeline(args.config)


if __name__ == "__main__":
    sys.exit(main())