"""ตรวจข้อมูลสำหรับ EDA โดยไม่แก้ค่าหรือเขียนทับข้อมูลต้นทาง"""

import numpy as np
import pandas as pd
from pandas.api.types import is_bool_dtype, is_numeric_dtype


PRICE_COLUMNS = ["adjusted_close", "high", "low"]
RETURN_COLUMNS = ["simple_return", "log_return"]
FLAG_COLUMNS = ["is_anomaly_flagged", "is_warmup_buffer"]
REQUIRED_COLUMNS = [
    "date", "ticker", *PRICE_COLUMNS, *RETURN_COLUMNS, *FLAG_COLUMNS,
    "run_id", "source_batch_id", "ingested_at_utc",
]
PRICE_TOLERANCE = 1e-4  # ใช้ค่าคลาดเคลื่อนที่ยอมรับได้เท่ากับขั้น ingestion


def inspect_market_prices(data, config, expected_trading_days):
    """คืนสำเนาข้อมูลที่เรียงแล้วและผลตรวจ โดยเทียบกับวันซื้อขายที่ควรมี

    นับปัญหาเป็นแถว ยกเว้นวันขาดนับเป็นวัน และชนิดข้อมูลผิดนับเป็นคอลัมน์
    แสดงตัวอย่างไม่เกิน 5 รายการต่อการตรวจ
    """
    missing = sorted(set(REQUIRED_COLUMNS) - set(data.columns))
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df = data.copy(deep=True)
    rows = []

    def record(check, ticker, count, examples=""):
        rows.append({
            "check": check, "ticker": ticker, "issues": int(count),
            "status": "PASS" if count == 0 else "FAIL", "examples": examples,
        })

    def check_rows(check, mask, ticker="ALL"):
        bad = df.loc[pd.Series(mask, index=df.index).fillna(True)]
        sample = bad[["date", "ticker"]].head(5).astype(str).to_dict("records")
        record(check, ticker, len(bad), repr(sample) if len(bad) else "")

    wrong_numeric = [
        c for c in PRICE_COLUMNS + RETURN_COLUMNS
        if not is_numeric_dtype(df[c]) or is_bool_dtype(df[c])
    ]
    wrong_flags = [c for c in FLAG_COLUMNS if not is_bool_dtype(df[c])]
    record("numeric_dtypes", "ALL", len(wrong_numeric), repr(wrong_numeric))
    record("boolean_dtypes", "ALL", len(wrong_flags), repr(wrong_flags))
    for column in PRICE_COLUMNS + RETURN_COLUMNS:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    if isinstance(df["date"].dtype, pd.DatetimeTZDtype):
        raise ValueError("date must be a timezone-naive trading session date")
    check_rows("valid_session_date", df.date.isna() | df.date.ne(df.date.dt.normalize()))
    check_rows("duplicate_primary_key", df.duplicated(["date", "ticker"], keep=False))
    tickers = config["source"]["tickers"]
    check_rows("ticker_domain", ~df.ticker.isin(tickers))
    for column in ["ticker", *FLAG_COLUMNS, "run_id", "source_batch_id", "ingested_at_utc"]:
        check_rows(f"required_non_null:{column}", df[column].isna())
    for column in ["ticker", "run_id", "source_batch_id"]:
        check_rows(f"nonempty_string:{column}", ~df[column].map(
            lambda value: isinstance(value, str) and bool(value.strip())
        ))
    timestamp_dtype = df.ingested_at_utc.dtype
    utc_dtype = isinstance(timestamp_dtype, pd.DatetimeTZDtype) and str(timestamp_dtype.tz) == "UTC"
    record("ingestion_timestamp_utc_dtype", "ALL", int(not utc_dtype))

    for column in PRICE_COLUMNS:
        check_rows(f"positive_finite:{column}", ~np.isfinite(df[column]) | df[column].le(0))
    tol = PRICE_TOLERANCE
    check_rows("high_low_consistency", ~(
        df.low.le(df.high + tol)
        & df.adjusted_close.ge(df.low - tol)
        & df.adjusted_close.le(df.high + tol)
    ))
    start = pd.Timestamp(config["date_range"]["start_date"])
    check_rows("warmup_flag_matches_config", df.is_warmup_buffer.ne(df.date.lt(start)))
    threshold = config["validation"]["simple_return_anomaly_threshold"]
    check_rows("anomaly_flag_matches_threshold", df.is_anomaly_flagged.ne(df.simple_return.abs().gt(threshold)))

    expected = pd.DatetimeIndex(pd.to_datetime(expected_trading_days)).normalize()
    if expected.empty or expected.has_duplicates:
        raise ValueError("Expected trading sessions must be nonempty and unique")
    for ticker in tickers:
        observed = pd.DatetimeIndex(df.loc[df.ticker.eq(ticker), "date"].dropna())
        missing_days = expected.difference(observed)
        extra_days = observed.difference(expected)
        record("missing_trading_sessions", ticker, len(missing_days), repr(missing_days.strftime("%Y-%m-%d").tolist()[:5]))
        record("unexpected_sessions", ticker, len(extra_days), repr(extra_days.strftime("%Y-%m-%d").tolist()[:5]))

    df = df.sort_values(["ticker", "date"]).reset_index(drop=True)
    for ticker, group in df.groupby("ticker"):
        prices = group.adjusted_close.to_numpy(dtype=float)
        reference_simple = np.full(len(group), np.nan)
        reference_log = np.full(len(group), np.nan)
        with np.errstate(divide="ignore", invalid="ignore"):
            reference_simple[1:] = prices[1:] / prices[:-1] - 1
            reference_log[1:] = np.log(prices[1:] / prices[:-1])
        for column, reference in zip(RETURN_COLUMNS, [reference_simple, reference_log]):
            actual = group[column].to_numpy(dtype=float)
            # แถวแรกไม่มีราคาก่อนหน้า จึงต้องว่าง; แถวถัดไปต้องไม่เป็น NaN หรือ Inf
            valid = np.isfinite(actual)
            valid[0] = np.isnan(actual[0])
            mismatch = ~np.isclose(actual, reference, rtol=1e-9, atol=1e-12, equal_nan=True)
            for name, mask in [("validity", ~valid), ("formula", mismatch)]:
                examples = group.loc[mask, ["date", "ticker", column]].head(5).astype(str).to_dict("records")
                record(f"{column}:{name}", ticker, mask.sum(), repr(examples) if mask.any() else "")

    return df, pd.DataFrame(rows)


def add_historical_rv(data, windows=(5, 20, 60)):
    """คำนวณ RV รายปีจาก RMS โดยไม่หักค่าเฉลี่ย ใช้ข้อมูลย้อนหลังถึงวัน t เท่านั้น"""
    df = data.sort_values(["ticker", "date"]).reset_index(drop=True).copy()
    for window in windows:
        df[f"rv_{window}d"] = df.groupby("ticker")["log_return"].transform(
            lambda values: np.sqrt(252 * values.pow(2).rolling(window, min_periods=window).mean())
        )
    return df


def inspect_historical_rv(data, windows=(5, 20, 60)):
    """ทวน RV ด้วย NumPy ทีละหน้าต่างย้อนหลัง โดยไม่ใช้ pandas rolling ซ้ำ

    ตรวจตำแหน่งค่าว่างช่วง warm-up ด้วย ส่วนช่วงวิเคราะห์ต้องมี RV ไม่ติดลบ
    และไม่เป็น NaN หรือ Inf
    """
    results = []
    for ticker, group in data.groupby("ticker"):
        if not group.date.is_monotonic_increasing or group.date.duplicated().any():
            raise ValueError("RV verification requires unique sorted sessions per ticker")
        returns = group.log_return.to_numpy(dtype=float)
        analysis_mask = ~group.is_warmup_buffer.to_numpy(dtype=bool)
        for window in windows:
            reference = np.full(len(group), np.nan)
            for end in range(window - 1, len(group)):
                values = returns[end - window + 1:end + 1]
                if np.isfinite(values).all():
                    reference[end] = np.sqrt(252 / window * np.dot(values, values))
            actual = group[f"rv_{window}d"].to_numpy(dtype=float)
            mismatch = ~np.isclose(actual, reference, rtol=1e-9, atol=1e-12, equal_nan=True)
            unavailable = analysis_mask & (~np.isfinite(actual) | (actual < 0))
            comparable = np.isfinite(actual) & np.isfinite(reference)
            error = float(np.max(np.abs(actual[comparable] - reference[comparable]))) if comparable.any() else np.nan
            issues = mismatch | unavailable
            results.append({
                "ticker": ticker, "window": window, "formula_mismatches": int(mismatch.sum()),
                "invalid_analysis_rows": int(unavailable.sum()), "max_abs_error": error,
                "status": "PASS" if not issues.any() else "FAIL",
                "example_dates": group.loc[issues, "date"].dt.strftime("%Y-%m-%d").head(5).tolist(),
            })
    return pd.DataFrame(results)
