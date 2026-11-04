import argparse
import json
import logging
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas_market_calendars as mcal
import yaml


NY = ZoneInfo("America/New_York")


def run_after_market_close(
    config_path: str,
    buffer_minutes: int = 30,
) -> int:
    with open(config_path, encoding="utf-8") as file:
        config = yaml.safe_load(file)

    calendar = mcal.get_calendar(config["calendar"]["market"])
    now_ny = datetime.now(NY)
    today = now_ny.date()

    schedule = calendar.schedule(
        start_date=today.isoformat(),
        end_date=today.isoformat(),
    )

    log_dir = Path("data/audit/scheduler")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{today.isoformat()}.json"

    if schedule.empty:
        result = {
            "date": today.isoformat(),
            "status": "SKIPPED_NON_TRADING_DAY",
            "message": "ตลาดปิดวันนี้ ไม่มี trading session",
        }
        log_path.write_text(
            json.dumps(result, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logging.info(result["status"])
        return 0

    # ปฏิทินส่งเวลาปิดเป็น UTC; แปลงเป็นเวลา New York
    market_close_utc = schedule.iloc[0]["market_close"].to_pydatetime()
    market_close_ny = market_close_utc.astimezone(NY)
    ready_time = market_close_ny + timedelta(minutes=buffer_minutes)

    if now_ny < ready_time:
        logging.info(
            "ยังไม่ถึงเวลารัน: รอถึง %s",
            ready_time.isoformat(),
        )
        return 0

    command = [
        sys.executable,
        "-m",
        "src.ingestion.run",
        "--config",
        config_path,
    ]

    completed = subprocess.run(command, check=False)

    result = {
        "date": today.isoformat(),
        "market_close_ny": market_close_ny.isoformat(),
        "buffer_minutes": buffer_minutes,
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "SUCCESS" if completed.returncode == 0 else "FAILED",
        "return_code": completed.returncode,
    }
    log_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return completed.returncode


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/ingestion.yaml")
    parser.add_argument("--buffer-minutes", type=int, default=30)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    raise SystemExit(
        run_after_market_close(args.config, args.buffer_minutes)
    )