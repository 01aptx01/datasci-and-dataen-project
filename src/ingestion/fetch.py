import time
from typing import Any

import pandas as pd
import yfinance as yf


def fetch_ticker(
    ticker: str,
    config: dict[str, Any],
    ingestion_window: dict[str, Any],
) -> dict[str, Any]:
    """ดึงข้อมูล ticker เดียว พร้อม retry และสรุปสถานะการดึง"""

    source = config["source"]
    execution = config["execution"]
    price = config["price"]

    max_attempts = execution["max_attempts"]
    timeout = execution["timeout_seconds"]
    errors = []

    for attempt in range(1, max_attempts + 1):
        try:
            data = yf.download(
                tickers=ticker,
                start=ingestion_window["actual_fetch_start_date"],
                end=ingestion_window["api_end_date"],
                interval=source["interval"],
                auto_adjust=price["auto_adjust"],
                actions=False,
                repair=False,
                keepna=True,
                progress=False,
                timeout=timeout,
                multi_level_index=False,
            )

            if data is None or data.empty:
                raise RuntimeError("Empty response from Yahoo Finance")

            # ตรวจ schema ก่อน retry: schema ผิดแก้ด้วยการลองดึงซ้ำไม่ได้
            col_names = (
                set(data.columns)
                if not isinstance(data.columns, pd.MultiIndex)
                else {str(c) for col in data.columns for c in col}
            )
            missing = {"Close", "High", "Low"} - col_names
            if missing:
                return {
                    "ticker": ticker,
                    "status": "FAILED",
                    "failure_type": "SCHEMA_ERROR",
                    "rows_fetched": 0,
                    "attempts": attempt,
                    "errors": errors + [
                        f"Missing required column(s): {', '.join(sorted(missing))}"
                    ],
                    "data": None,
                }

            data = data.copy()
            data.index.name = "date"

            return {
                "ticker": ticker,
                "status": "SUCCESS",
                "failure_type": None,
                "rows_fetched": len(data),
                "attempts": attempt,
                "errors": errors,
                "data": data,
            }

        except Exception as error:
            errors.append(f"Attempt {attempt}: {type(error).__name__}: {error}")

            if attempt < max_attempts:
                # เพิ่มเวลารอทีละขั้น เช่น 1 วินาที, 2 วินาที
                time.sleep(2 ** (attempt - 1))

    return {
        "ticker": ticker,
        "status": "FAILED",
        "failure_type": "FETCH_ERROR",
        "rows_fetched": 0,
        "attempts": max_attempts,
        "errors": errors,
        "data": None,
    }


def fetch_all(
    config: dict[str, Any],
    ingestion_window: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """ดึงทีละ ticker เพื่อแยกสถานะและ retry รายตัว"""
    results = {}

    for ticker in config["source"]["tickers"]:
        results[ticker] = fetch_ticker(
            ticker=ticker,
            config=config,
            ingestion_window=ingestion_window,
        )

    return results