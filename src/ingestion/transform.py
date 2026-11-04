from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd


def _to_market_date(index: pd.Index, market_timezone: str) -> list:
    """แปลง index เป็นวันที่ซื้อขาย โดยคำนึงถึง timezone ถ้ามี"""
    dates = []

    for value in index:
        timestamp = pd.Timestamp(value)

        if timestamp.tzinfo is not None:
            timestamp = timestamp.tz_convert(ZoneInfo(market_timezone))

        # ถ้า index ไม่มี timezone ให้ถือเป็น daily session date
        dates.append(timestamp.date())

    return dates


def transform_ticker(
    ticker: str,
    raw_data: pd.DataFrame,
    config: dict[str, Any],
    run_metadata: dict[str, Any],
    ingestion_window: dict[str, Any],
) -> pd.DataFrame:
    """แปลง raw DataFrame ของ ticker เดียวเป็น schema มาตรฐาน"""

    if config["price"]["auto_adjust"] is not True:
        raise ValueError("TRANSFORM_ERROR: auto_adjust must be true")

    if raw_data is None or raw_data.empty:
        raise ValueError(f"TRANSFORM_ERROR: no raw data for {ticker}")

    # รองรับ MultiIndex columns ที่อาจได้จาก yfinance บางเวอร์ชัน
    data = raw_data.copy()
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = [
            next(
                (str(level) for level in column if str(level) == "Close"),
                str(column[-1]),
            )
            for column in data.columns
        ]

    if "Close" not in data.columns:
        raise ValueError(
            f"TRANSFORM_ERROR: missing Close column for {ticker}"
        )

    market_timezone = config["calendar"]["market_timezone"]
    data["date"] = _to_market_date(data.index, market_timezone)

    data["adjusted_close"] = pd.to_numeric(
        data["Close"], errors="coerce"
    )

    result = data[["date", "adjusted_close"]].copy()
    result["ticker"] = ticker
    result = result.sort_values(["ticker", "date"]).reset_index(drop=True)

    # คำนวณ return แยก ticker; แถวแรกจึงไม่มีราคาก่อนหน้าและเป็น null
    previous_price = result.groupby("ticker")["adjusted_close"].shift(1)
    result["simple_return"] = result["adjusted_close"].div(previous_price) - 1

    valid_prices = (result["adjusted_close"] > 0) & (previous_price > 0)
    result.loc[~valid_prices, "simple_return"] = np.nan

    result["log_return"] = np.log(
        result["adjusted_close"].div(previous_price)
    )
    result.loc[~valid_prices, "log_return"] = np.nan

    threshold = config["validation"]["simple_return_anomaly_threshold"]
    result["is_anomaly_flagged"] = (
        result["simple_return"].abs() > threshold
    ).fillna(False)

    analysis_start = pd.Timestamp(
        ingestion_window["config_start_date"]
    ).date()
    result["is_warmup_buffer"] = result["date"] < analysis_start

    result["run_id"] = run_metadata["run_id"]
    result["source_batch_id"] = run_metadata["source_batch_id"]
    result["ingested_at_utc"] = datetime.now(timezone.utc)

    # ตรวจ key ซ้ำเบื้องต้นก่อนส่งต่อ validation
    duplicate_mask = result.duplicated(
        subset=["date", "ticker"],
        keep=False,
    )
    if duplicate_mask.any():
        raise ValueError(
            f"TRANSFORM_ERROR: duplicate (date, ticker) rows for {ticker}"
        )

    columns = [
        "date",
        "ticker",
        "adjusted_close",
        "simple_return",
        "log_return",
        "is_anomaly_flagged",
        "is_warmup_buffer",
        "run_id",
        "source_batch_id",
        "ingested_at_utc",
    ]
    return result[columns]


def transform_all(
    fetch_results: dict[str, dict[str, Any]],
    config: dict[str, Any],
    run_metadata: dict[str, Any],
    ingestion_window: dict[str, Any],
) -> pd.DataFrame:
    """รวมข้อมูล ticker ที่ fetch สำเร็จเป็นตาราง long format"""
    frames = []

    for ticker, fetch_result in fetch_results.items():
        if fetch_result.get("status") != "SUCCESS":
            continue

        frames.append(
            transform_ticker(
                ticker=ticker,
                raw_data=fetch_result["data"],
                config=config,
                run_metadata=run_metadata,
                ingestion_window=ingestion_window,
            )
        )

    if not frames:
        return pd.DataFrame(
            columns=[
                "date", "ticker", "adjusted_close", "simple_return",
                "log_return", "is_anomaly_flagged", "is_warmup_buffer",
                "run_id", "source_batch_id", "ingested_at_utc",
            ]
        )

    return (
        pd.concat(frames, ignore_index=True)
        .sort_values(["ticker", "date"])
        .reset_index(drop=True)
    )