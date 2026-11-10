"""ทดสอบตัวตรวจ EDA ด้วยข้อมูลจำลอง โดยไม่แตะข้อมูลตลาดจริงของโปรเจกต์"""

import numpy as np
import pandas as pd
import pandas_market_calendars as mcal
import pytest

from src.eda.quality import add_historical_rv, inspect_historical_rv, inspect_market_prices


@pytest.fixture
def sample():
    """สร้างข้อมูล 3 สินทรัพย์ โดยให้ 61 วันแรกเป็นช่วง warm-up"""
    days = mcal.get_calendar("XNYS").schedule("2024-01-02", "2024-06-01").index[:90]
    config = {
        "source": {"tickers": ["SPY", "IEF", "GLD"]},
        "date_range": {"start_date": days[61].strftime("%Y-%m-%d")},
        "validation": {"simple_return_anomaly_threshold": 0.20},
    }
    frames = []
    for index, ticker in enumerate(config["source"]["tickers"]):
        prices = (100 + index * 40) * np.exp(np.cumsum(np.sin(np.arange(len(days))) * 0.01 + 0.001))
        simple = np.r_[np.nan, prices[1:] / prices[:-1] - 1]
        logs = np.r_[np.nan, np.log(prices[1:] / prices[:-1])]
        frames.append(pd.DataFrame({
            "date": days, "ticker": ticker, "adjusted_close": prices,
            "high": prices + 1, "low": prices - 1,
            "simple_return": simple, "log_return": logs,
            "is_warmup_buffer": np.arange(len(days)) < 61,
            "is_anomaly_flagged": False, "run_id": "run_test",
            "source_batch_id": "batch_test", "ingested_at_utc": pd.Timestamp("2024-06-02", tz="UTC"),
        }))
    return pd.concat(frames, ignore_index=True), config, days


def report(data, config, days):
    return inspect_market_prices(data, config, days)[1]


def test_valid_data_passes_without_mutating_input(sample):
    data, config, days = sample
    original = data.copy(deep=True)
    sorted_data, checks = inspect_market_prices(data.sample(frac=1, random_state=4), config, days)
    assert checks.status.eq("PASS").all()
    pd.testing.assert_frame_equal(data, original)
    assert inspect_historical_rv(add_historical_rv(sorted_data)).status.eq("PASS").all()


@pytest.mark.parametrize("missing", ["first", "last", "middle", "ticker"])
def test_detects_missing_boundaries_internal_days_and_entire_ticker(sample, missing):
    data, config, days = sample
    if missing == "ticker":
        broken = data.loc[data.ticker.ne("IEF")]
    else:
        day = days[{"first": 0, "last": -1, "middle": 70}[missing]]
        broken = data.loc[data.date.ne(day)]
    checks = report(broken, config, days)
    failures = checks.loc[checks.check.eq("missing_trading_sessions") & checks.status.eq("FAIL")]
    assert len(failures) == (1 if missing == "ticker" else 3)
    assert failures.issues.eq(len(days) if missing == "ticker" else 1).all()


@pytest.mark.parametrize("kind,check", [
    ("duplicate", "duplicate_primary_key"),
    ("weekend", "unexpected_sessions"),
    ("zero", "positive_finite:adjusted_close"),
    ("infinite", "positive_finite:high"),
    ("outside_range", "high_low_consistency"),
    ("warmup", "warmup_flag_matches_config"),
    ("flag", "anomaly_flag_matches_threshold"),
    ("null_return", "log_return:validity"),
    ("wrong_return", "simple_return:formula"),
    ("first_return", "log_return:validity"),
    ("numeric_dtype", "numeric_dtypes"),
    ("flag_dtype", "boolean_dtypes"),
    ("bad_date", "valid_session_date"),
])
def test_detects_corruption(sample, kind, check):
    data, config, days = sample
    broken = data.copy(deep=True)
    if kind == "duplicate":
        broken = pd.concat([broken, broken.iloc[[2]]], ignore_index=True)
    elif kind == "weekend":
        broken.loc[2, "date"] = pd.Timestamp("2024-01-06")
    elif kind == "zero":
        broken.loc[2, "adjusted_close"] = 0
    elif kind == "infinite":
        broken.loc[2, "high"] = np.inf
    elif kind == "outside_range":
        broken.loc[2, "adjusted_close"] = broken.loc[2, "high"] + 2
    elif kind == "warmup":
        broken.loc[2, "is_warmup_buffer"] = False
    elif kind == "flag":
        broken.loc[2, "is_anomaly_flagged"] = True
    elif kind == "null_return":
        broken.loc[2, "log_return"] = np.nan
    elif kind == "wrong_return":
        broken.loc[2, "simple_return"] += 0.01
    elif kind == "first_return":
        broken.loc[0, "log_return"] = 0
    elif kind == "numeric_dtype":
        broken["adjusted_close"] = broken.adjusted_close.astype(str)
    elif kind == "flag_dtype":
        broken["is_warmup_buffer"] = broken.is_warmup_buffer.astype(int)
    elif kind == "bad_date":
        broken.loc[2, "date"] = pd.NaT
    checks = report(broken, config, days)
    assert checks.loc[checks.check.eq(check), "status"].eq("FAIL").any()


def test_missing_column_has_clear_error(sample):
    data, config, days = sample
    with pytest.raises(ValueError, match="Missing required columns.*log_return"):
        report(data.drop(columns="log_return"), config, days)


def test_real_extreme_return_is_a_warning_not_a_failure(sample):
    data, config, days = sample
    data.loc[2, "adjusted_close"] *= 1.5
    data["high"] = data.adjusted_close + 1
    data["low"] = data.adjusted_close - 1
    previous = data.groupby("ticker").adjusted_close.shift()
    data["simple_return"] = data.adjusted_close / previous - 1
    data["log_return"] = np.log(data.adjusted_close / previous)
    data["is_anomaly_flagged"] = data.simple_return.abs().gt(0.20)
    assert data.is_anomaly_flagged.any()
    assert report(data, config, days).status.eq("PASS").all()


def test_rv_reference_detects_std_formula_and_missing_analysis_value(sample):
    data, _, _ = sample
    data = add_historical_rv(data)
    data["rv_20d"] = data.groupby("ticker").log_return.transform(
        lambda values: values.rolling(20).std() * np.sqrt(252)
    )
    data.loc[data.index[-1], "rv_60d"] = np.nan
    checks = inspect_historical_rv(data)
    assert checks.loc[checks.window.eq(20), "formula_mismatches"].gt(0).all()
    assert checks.loc[checks.window.eq(60), "invalid_analysis_rows"].sum() == 1


def test_rv_uses_only_past_values_and_stays_within_ticker(sample):
    data, _, days = sample
    original = add_historical_rv(data)
    data.loc[data.ticker.eq("IEF") & data.date.ge(days[75]), "log_return"] = 10
    changed = add_historical_rv(data)
    unaffected = changed.ticker.ne("IEF") | changed.date.lt(days[75])
    pd.testing.assert_frame_equal(
        original.loc[unaffected, ["rv_5d", "rv_20d", "rv_60d"]],
        changed.loc[unaffected, ["rv_5d", "rv_20d", "rv_60d"]],
    )


def test_insufficient_warmup_is_not_filled_with_zero(sample):
    data, _, days = sample
    short = data.loc[data.date.ge(days[50])].copy()
    # จำลองแถวแรกของข้อมูลช่วงสั้น ซึ่งไม่มีราคาก่อนหน้าให้คำนวณ return
    short.loc[short.groupby("ticker").head(1).index, "log_return"] = np.nan
    calculated = add_historical_rv(short)
    checks = inspect_historical_rv(calculated)
    assert checks.loc[checks.window.eq(60), "invalid_analysis_rows"].gt(0).all()
    assert calculated.rv_60d.isna().all()

@pytest.mark.parametrize("price", [0.0, -1.0, np.nan, np.inf, -np.inf])
@pytest.mark.parametrize("position", [0, 1])
def test_raw_return_rejects_invalid_prices(price, position):
    from src.eda.quality import raw_price_returns
    prices = [100.0, 105.0]
    prices[position] = price
    assert raw_price_returns(*prices) is None


def test_raw_return_computes_simple_and_log():
    from src.eda.quality import raw_price_returns
    assert raw_price_returns(100.0, 105.0) == pytest.approx((0.05, np.log(1.05)))


def test_sensitivity_uses_union_and_preserves_input():
    from src.eda.quality import distribution_sensitivity, correlation_sensitivity
    dates = pd.date_range('2024-01-01', periods=6)
    data = pd.concat([pd.DataFrame({'date': dates, 'ticker': t, 'log_return': v}) for t, v in [
        ('A', [1, 2, 3, 4, 5, 6]), ('B', [2, 4, 1, 5, 3, 6])]], ignore_index=True)
    events = pd.DataFrame({'ticker': ['A', 'A', 'B', 'B'], 'date': [dates[0], dates[1], dates[0], dates[2]], 'rank': [1, 2, 1, 2]})
    original = data.copy(deep=True)
    dist = distribution_sensitivity(data, events)
    assert dist.loc[(dist.ticker == 'A') & (dist.case == 'top-5'), 'n'].iloc[0] == 4
    corr = correlation_sensitivity(data, events, [('A', 'B')]).set_index('case')
    assert corr.loc['top-1', 'excluded'] == 1
    assert corr.loc['top-5', 'excluded'] == 3
    assert corr.loc['top-5', 'correlation'] == pytest.approx(data.pivot(index='date', columns='ticker', values='log_return').iloc[3:].corr().loc['A','B'])
    pd.testing.assert_frame_equal(data, original)


def test_correlation_unavailable_for_constant_or_insufficient_data():
    from src.eda.quality import correlation_sensitivity
    data = pd.DataFrame({'date': [1, 2, 1, 2], 'ticker': ['A','A','B','B'], 'log_return': [1.,1.,2.,3.]})
    events = pd.DataFrame({'date': [1,2], 'ticker': ['A','B'], 'rank': [1,1]})
    assert correlation_sensitivity(data, events, [('A','B')]).correlation.isna().all()


def test_peak_rv_window_contribution_and_zero():
    from src.eda.quality import peak_rv_contributions
    data = pd.DataFrame({'date': pd.date_range('2024-01-01', periods=4), 'ticker': ['A']*4,
        'log_return': [0.,1.,2.,0.], 'simple_return': [0.,1.,2.,0.],
        'is_warmup_buffer': [True,True,False,False], 'rv_2d': [np.nan,1.,3.,2.]})
    events = pd.DataFrame({'ticker':['A'], 'date':[data.date.iloc[2]], 'rank':[1]})
    result = peak_rv_contributions(data, events, (2,)).iloc[0]
    assert result['count'] == 2 and result['start'] == data.date.iloc[1]
    assert result['sum_r2'] == 5 and result['largest_share_pct'] == 80 and result['top5_share_pct'] == 80
    data['log_return'] = 0.; data['rv_2d'] = [np.nan,0.,0.,0.]
    result = peak_rv_contributions(data, events, (2,)).iloc[0]
    assert result['end'] == data.date.iloc[2] and np.isnan(result['largest_share_pct'])


def test_annual_coverage_distinguishes_partial_from_missing():
    from src.eda.quality import annual_coverage
    dates = pd.to_datetime(['2023-12-28','2023-12-29','2024-01-02','2024-01-03','2024-01-04'])
    data = pd.DataFrame({'date': dates[[1,2,4]], 'ticker': ['A']*3})
    original = data.copy(deep=True)
    result = annual_coverage(data, dates, dates[1], dates[-1], ['A']).set_index('year')
    assert result.loc[2023, 'partial'] and result.loc[2023, 'missing_days'] == 0
    assert not result.loc[2024, 'partial'] and result.loc[2024, 'missing_days'] == 1
    pd.testing.assert_frame_equal(data, original)


def test_annual_correlation_uses_common_dates_and_handles_constants():
    from src.eda.quality import annual_correlations
    dates = pd.date_range('2024-01-01', periods=4)
    data = pd.concat([pd.DataFrame({'date': dates, 'ticker': t, 'log_return': v}) for t,v in [
        ('A',[1.,2.,3.,4.]), ('B',[1.,4.,2.,3.]), ('C',[1.,np.nan,1.,1.])]])
    result = annual_correlations(data, ['A','B','C'], [('A','B'),('A','C')]).iloc[0]
    assert result.common_days == 3
    assert result['A-B'] == pytest.approx(np.corrcoef([1,3,4], [1,2,3])[0,1])
    assert np.isnan(result['A-C'])


def test_rv_remains_continuous_across_year():
    dates = pd.to_datetime(['2023-12-28','2023-12-29','2024-01-02'])
    data = pd.DataFrame({'date':dates, 'ticker':['A']*3, 'log_return':[0.01,0.02,0.03]})
    result = add_historical_rv(data, windows=(2,))
    assert result.rv_2d.iloc[-1] == pytest.approx(np.sqrt(252*(.02**2+.03**2)/2))


def test_sample_acf_known_values_and_no_input_mutation():
    from src.eda.quality import sample_acf
    values = np.array([1., 2., 3., 4.])
    original = values.copy()
    assert sample_acf(values, 3) == pytest.approx([1., .25, -.30, -.45])
    np.testing.assert_array_equal(values, original)


def test_sample_acf_constant_short_and_long_lags():
    from src.eda.quality import sample_acf
    assert np.isnan(sample_acf([3., 3., 3.], 4)).all()
    assert np.isnan(sample_acf([], 4)).all()
    assert np.isnan(sample_acf([2.], 4)).all()
    result = sample_acf([1., 2.], 4)
    assert result[0] == 1 and np.isnan(result[2:]).all()


@pytest.mark.parametrize('invalid', [np.nan, np.inf, -np.inf])
def test_sample_acf_rejects_nonfinite(invalid):
    from src.eda.quality import sample_acf
    with pytest.raises(ValueError, match='finite'):
        sample_acf([1., invalid, 3.])


def test_sample_acf_translation_scale_and_small_values():
    from src.eda.quality import sample_acf
    values = np.array([1., 2., 3., 4.])
    expected = sample_acf(values, 3)
    for transformed in (values + 35, values * -3, values * 1e-6, values * 1e-12):
        np.testing.assert_allclose(sample_acf(transformed, 3), expected, atol=1e-12)


def test_notebook_acf_preparation_sorts_and_separates_tickers():
    import json
    from pathlib import Path
    from src.eda.quality import sample_acf
    notebook = json.loads((Path(__file__).resolve().parents[2] / 'notebooks' / '01_eda_market_prices.ipynb').read_text(encoding='utf-8'))
    source = next(''.join(c['source']) for c in notebook['cells'] if ''.join(c['source']).startswith('# เตรียม ACF'))
    dates = pd.date_range('2024-01-02', periods=4)
    frame = pd.concat([pd.DataFrame({'date':dates, 'ticker':t, 'log_return':v}) for t,v in [('SPY',[1.,2.,3.,4.]), ('IEF',[4.,1.,2.,3.]), ('GLD',[1.,4.,2.,3.])]]).sample(frac=1, random_state=1)
    ns = {'pd':pd, 'np':np, 'analysis':frame, 'expected_sessions':dates, 'start_date':dates[0], 'end_date':dates[-1], 'config':{'source':{'tickers':['SPY','IEF','GLD']}}}
    exec(compile(source, '<notebook ACF>', 'exec'), ns)
    np.testing.assert_allclose(ns['acf_values'][('SPY','Return')][:4], sample_acf([1.,2.,3.,4.], 3))
    np.testing.assert_allclose(ns['acf_values'][('IEF','Return')][:4], sample_acf([4.,1.,2.,3.], 3))
    ns['analysis'] = frame.drop(frame.index[0])
    with pytest.raises(ValueError, match='วันซื้อขาย'):
        exec(compile(source, '<notebook ACF>', 'exec'), ns)
