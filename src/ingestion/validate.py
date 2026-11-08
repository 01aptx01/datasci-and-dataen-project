from typing import Any

import numpy as np
import pandas as pd


REQUIRED_COLUMNS = {
    "date",
    "ticker",
    "adjusted_close",
    "high",
    "low",
    "simple_return",
    "log_return",
    "is_anomaly_flagged",
    "is_warmup_buffer",
}


def validate_ticker(
    ticker: str,
    data: pd.DataFrame,
    expected_trading_days: list[str],
    anomaly_threshold: float = 0.20,
    config_start_date: str | None = None,
) -> dict[str, Any]:
    errors = []
    warnings = []
    quarantine = []

    if not isinstance(data, pd.DataFrame) or data.empty:
        return {
            "ticker": ticker,
            "status": "FAILED",
            "rows_checked": 0,
            "error_codes": ["EMPTY_DATA"],
            "warnings": [],
            "missing_days": expected_trading_days,
            "duplicates": [],
            "quarantine": [],
        }

    missing_columns = sorted(REQUIRED_COLUMNS - set(data.columns))
    if missing_columns:
        return {
            "ticker": ticker,
            "status": "FAILED",
            "rows_checked": len(data),
            "error_codes": ["INVALID_SCHEMA"],
            "warnings": [],
            "missing_columns": missing_columns,
            "missing_days": [],
            "duplicates": [],
            "quarantine": [],
        }

    df = data.copy()

    # ตรวจ ticker โดเมนที่รองรับ SPY, IEF, GLD
    supported_tickers = {"SPY", "IEF", "GLD"}
    observed_tickers = set(df["ticker"].dropna().unique())
    if observed_tickers != {ticker} or ticker not in supported_tickers:
        errors.append("UNSUPPORTED_OR_MIXED_TICKER")

    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    if df["date"].isna().any():
        errors.append("INVALID_DATE")

    # 1. Price Validity: adjusted_close, high, low เป็น Finite และ > 0
    tol = 1e-4
    for col in ["adjusted_close", "high", "low"]:
        price = pd.to_numeric(df[col], errors="coerce")
        valid = price.notna() & np.isfinite(price) & (price > 0)
        if not valid.all():
            errors.append("NON_POSITIVE_PRICE")
            for index in df.index[~valid]:
                quarantine.append({
                    "ticker": ticker,
                    "date": str(df.at[index, "date"]),
                    "reason": "NON_POSITIVE_PRICE",
                    "raw_value": f"{col}={df.at[index, col]}",
                })

    # 2. High/Low Consistency: low <= adjusted_close <= high และ low <= high
    ac = pd.to_numeric(df["adjusted_close"], errors="coerce")
    hi = pd.to_numeric(df["high"], errors="coerce")
    lo = pd.to_numeric(df["low"], errors="coerce")
    valid_hl = (
        (lo <= hi + tol)
        & (lo - tol <= ac)
        & (ac <= hi + tol)
    )
    if not valid_hl.all():
        errors.append("INVALID_HIGH_LOW")
        for index in df.index[~valid_hl]:
            quarantine.append({
                "ticker": ticker,
                "date": str(df.at[index, "date"]),
                "reason": "INVALID_HIGH_LOW",
                "raw_value": f"low={lo.at[index]}, adjusted_close={ac.at[index]}, high={hi.at[index]}",
            })

    # 3. Warm-up Flag: is_warmup_buffer == (date < config.start_date)
    if config_start_date is not None:
        try:
            start_d = pd.to_datetime(config_start_date).date()
            expected_warmup = df["date"] < start_d
            actual_warmup = df["is_warmup_buffer"].astype(bool)
            warmup_match = actual_warmup == expected_warmup
            if not warmup_match.all():
                errors.append("INVALID_WARMUP_FLAG")
                for index in df.index[~warmup_match]:
                    quarantine.append({
                        "ticker": ticker,
                        "date": str(df.at[index, "date"]),
                        "reason": "INVALID_WARMUP_FLAG",
                        "raw_value": f"is_warmup_buffer={df.at[index, 'is_warmup_buffer']}, expected={expected_warmup.at[index]}",
                    })
        except Exception:
            pass

    # 4. Primary key ซ้ำ: (date, ticker)
    duplicate_mask = df.duplicated(["date", "ticker"], keep=False)
    duplicates = (
        df.loc[duplicate_mask, ["date", "ticker"]]
        .astype(str)
        .to_dict("records")
    )
    if duplicates:
        errors.append("DUPLICATE_PRIMARY_KEY")
        for row in duplicates:
            quarantine.append({**row, "reason": "DUPLICATE_PRIMARY_KEY"})

    # 5. ตรวจวันที่ซื้อขายที่คาดหวัง
    observed_days = set(df["date"].dropna().astype(str))
    missing_days = sorted(set(expected_trading_days) - observed_days)
    if missing_days:
        errors.append("MISSING_EXPECTED_TRADING_DAY")
        for missing_day in missing_days:
            quarantine.append({
                "ticker": ticker,
                "date": missing_day,
                "reason": "MISSING_EXPECTED_TRADING_DAY",
                "raw_value": None,
            })

    # 6. ตรวจผลตอบแทน: null ได้เฉพาะแถวแรกของ ticker
    df = df.sort_values("date").reset_index(drop=True)
    for column in ("simple_return", "log_return"):
        values = pd.to_numeric(df[column], errors="coerce")
        null_rows = values.isna()

        if null_rows.any():
            allowed_null = null_rows.iloc[0] and null_rows.sum() == 1
            if not allowed_null:
                errors.append("INVALID_RETURN")

        non_null = values.dropna()
        if not np.isfinite(non_null).all():
            errors.append("INVALID_RETURN")

    # 7. Anomaly เป็น warning ไม่ทำให้ ticker fail
    simple_return = pd.to_numeric(df["simple_return"], errors="coerce")
    anomaly_mask = simple_return.abs() > anomaly_threshold
    anomalies = df.loc[anomaly_mask, ["date", "ticker", "simple_return"]]

    for _, row in anomalies.iterrows():
        warnings.append({
            "ticker": ticker,
            "date": str(row["date"]),
            "reason": "RETURN_ANOMALY",
            "simple_return": float(row["simple_return"]),
        })

    return {
        "ticker": ticker,
        "status": "FAILED" if errors else (
            "SUCCESS_WITH_WARNING" if warnings else "SUCCESS"
        ),
        "rows_checked": len(df),
        "rows_passed": len(df) - int(duplicate_mask.sum()),
        "error_codes": sorted(set(errors)),
        "warnings": warnings,
        "missing_days": missing_days,
        "duplicates": duplicates,
        "quarantine": quarantine,
    }


def validate_all(
    data: pd.DataFrame,
    expected_trading_days: list[str],
    tickers: list[str],
    anomaly_threshold: float = 0.20,
    config_start_date: str | None = None,
) -> dict[str, Any]:
    """ตรวจข้อมูลรวม โดยแยกผลลัพธ์ตาม ticker"""
    results = {}

    for ticker in tickers:
        ticker_data = data.loc[data["ticker"] == ticker].copy()
        results[ticker] = validate_ticker(
            ticker=ticker,
            data=ticker_data,
            expected_trading_days=expected_trading_days,
            anomaly_threshold=anomaly_threshold,
            config_start_date=config_start_date,
        )

    statuses = [result["status"] for result in results.values()]
    failed_count = sum(status == "FAILED" for status in statuses)

    if failed_count == 0:
        overall_status = "SUCCESS"
    elif failed_count == len(statuses):
        overall_status = "FAILED"
    else:
        overall_status = "PARTIAL_SUCCESS"

    return {
        "overall_status": overall_status,
        "portfolio_ready": all(status != "FAILED" for status in statuses),
        "ticker_results": results,
    }