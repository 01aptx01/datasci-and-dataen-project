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


def raw_price_returns(previous, current):
    """คืน return จากราคา raw ที่เป็นจำนวนบวกและ finite เท่านั้น"""
    if not np.isfinite([previous, current]).all() or previous <= 0 or current <= 0:
        return None
    ratio = current / previous
    if not np.isfinite(ratio) or ratio <= 0:
        return None
    return ratio - 1, np.log(ratio)


def distribution_sensitivity(analysis, events):
    """เปรียบเทียบสถิติด้วยวัน extreme ชุดเดียวกันโดยไม่แก้ข้อมูลต้นทาง"""
    rows = []
    for ticker, group in analysis.groupby('ticker'):
        top = events.loc[events.ticker.eq(ticker)].sort_values('rank')
        base = group.log_return.dropna().std(ddof=1)
        base_skew = group.log_return.skew()
        base_kurt = group.log_return.kurt()
        for k in (0, 1, 5):
            dates = set(top.head(k).date)
            values = group.loc[~group.date.isin(dates), 'log_return'].dropna()
            std = values.std(ddof=1)
            rows.append(dict(ticker=ticker, case=f'top-{k}', excluded=len(dates),
                excluded_dates=', '.join(sorted(pd.Timestamp(d).strftime('%Y-%m-%d') for d in dates)),
                n=len(values), mean_log_pct=100*values.mean(), median_log_pct=100*values.median(),
                std_log_pct=100*std, skew=values.skew(), kurtosis=values.kurt(),
                delta_std_pct_points=100*(std-base), std_change_pct=100*(std/base-1) if base and np.isfinite(base) else np.nan,
                delta_skew=values.skew()-base_skew, delta_kurtosis=values.kurt()-base_kurt))
    return pd.DataFrame(rows)


def peak_rv_contributions(data, events, windows=(5, 20, 60)):
    """อธิบายส่วนร่วมของ return² ในหน้าต่าง RV เดิมที่สูงสุด"""
    rows = []
    for ticker, group in data.groupby('ticker'):
        group = group.sort_values('date').reset_index(drop=True)
        top_dates = set(events.loc[events.ticker.eq(ticker), 'date'])
        for n in windows:
            eligible = group.loc[~group.is_warmup_buffer & group[f'rv_{n}d'].notna()]
            if eligible.empty:
                continue
            peak = eligible[f'rv_{n}d'].max()
            end = eligible.index[eligible[f'rv_{n}d'].eq(peak)][0]
            window = group.iloc[max(0, end-n+1):end+1]
            if len(window) != n or not np.isfinite(window.log_return).all():
                raise ValueError('Incomplete RV window')
            squares = window.log_return.pow(2)
            total = squares.sum()
            largest = window.loc[squares.idxmax()]
            rows.append(dict(ticker=ticker, window=n, start=window.date.iloc[0], end=window.date.iloc[-1],
                count=len(window), rv_annual_pct=peak*100, sum_r2=total, largest_date=largest.date,
                largest_log_return=largest.log_return, largest_simple_pct=largest.simple_return*100,
                largest_share_pct=100*squares.max()/total if total else np.nan,
                top5_share_pct=100*squares[window.date.isin(top_dates)].sum()/total if total else np.nan))
    return pd.DataFrame(rows)


def correlation_sensitivity(analysis, events, pairs):
    """เปรียบเทียบ correlation รายคู่โดยเว้น union ของวันที่ตรงกัน"""
    wide = analysis.pivot(index='date', columns='ticker', values='log_return')
    rows = []
    for a, b in pairs:
        aligned = wide[[a, b]].dropna()
        base = np.nan
        for k in (0, 1, 5):
            excluded = set(events.loc[events.ticker.isin([a,b]) & events['rank'].le(k), 'date'])
            actual = aligned.index.intersection(pd.Index(list(excluded)))
            remaining = aligned.drop(index=actual)
            corr = remaining[a].corr(remaining[b]) if len(remaining) >= 2 and remaining[a].nunique() > 1 and remaining[b].nunique() > 1 else np.nan
            if k == 0:
                base = corr
            rows.append(dict(pair=f'{a}-{b}', case=f'top-{k}', n=len(remaining), excluded=len(actual), correlation=corr, delta=corr-base))
    return pd.DataFrame(rows)


def annual_coverage(analysis, market_sessions, start, end, tickers):
    """แยกปีไม่เต็มตามขอบเขตจากวันซื้อขายที่ขาดจริง"""
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    sessions = pd.DatetimeIndex(pd.to_datetime(market_sessions)).tz_localize(None).normalize()
    rows = []
    for year in range(start.year, end.year + 1):
        full = sessions[sessions.year == year]
        expected = full[(full >= start) & (full <= end)]
        partial = len(expected) != len(full)
        for ticker in tickers:
            observed = pd.DatetimeIndex(analysis.loc[(analysis.ticker == ticker) & (analysis.date.dt.year == year), 'date'])
            rows.append(dict(year=year, ticker=ticker, days=len(observed), first=observed.min(), last=observed.max(),
                             expected_days=len(expected), missing_days=len(expected.difference(observed)), partial=partial))
    return pd.DataFrame(rows)


def annual_correlations(analysis, tickers, pairs):
    """คำนวณ Pearson จากวันร่วมที่ครบทุกสินทรัพย์ภายในแต่ละปี"""
    wide = analysis.pivot(index='date', columns='ticker', values='log_return').reindex(columns=tickers).sort_index()
    rows = []
    for year, group in wide.groupby(wide.index.year):
        complete = group.dropna()
        row = {'year': year, 'common_days': len(complete)}
        for a, b in pairs:
            row[f'{a}-{b}'] = complete[a].corr(complete[b]) if len(complete) >= 2 and complete[a].nunique() > 1 and complete[b].nunique() > 1 else np.nan
        rows.append(row)
    return pd.DataFrame(rows)
