import pandas as pd
import pytest

from src.ingestion.calendar import build_ingestion_window
from src.ingestion.fetch import fetch_ticker
from src.ingestion.transform import transform_ticker
from src.ingestion.validate import validate_all


@pytest.fixture
def config():
    return {
        "source": {
            "provider": "Yahoo Finance",
            "client": "yfinance",
            "interval": "1d",
            "tickers": ["SPY", "IEF", "GLD"],
        },
        "date_range": {
            "start_date": "2021-09-27",
            "end_date": "2021-10-01",
            "warmup_trading_days": 61,
        },
        "price": {
            "auto_adjust": True,
            "canonical_price": "adjusted_close",
        },
        "calendar": {
            "market": "XNYS",
            "market_timezone": "America/New_York",
        },
        "validation": {
            "simple_return_anomaly_threshold": 0.20,
        },
        "execution": {
            "mode": "historical",
            "max_attempts": 3,
            "timeout_seconds": 15,
        },
    }


@pytest.fixture
def run_metadata():
    return {
        "run_id": "run_test_001",
        "source_batch_id": "yf_test_001",
    }


def test_calendar_uses_inclusive_end_and_trading_day_warmup(config):
    window = build_ingestion_window(config)

    assert window["api_end_date"] == "2021-10-02"
    assert window["actual_fetch_start_date"] < "2021-09-27"
    assert window["expected_trading_day_count"] == len(
        window["expected_trading_days"]
    )
    assert "2021-09-27" in window["expected_trading_days"]


def test_calendar_rejects_start_after_end(config):
    config["date_range"]["start_date"] = "2021-10-05"
    config["date_range"]["end_date"] = "2021-10-01"

    with pytest.raises(ValueError, match="start_date"):
        build_ingestion_window(config)


def test_fetch_success(monkeypatch, config):
    raw = pd.DataFrame(
        {"Close": [100.0, 102.0]},
        index=pd.to_datetime(["2021-09-27", "2021-09-28"]),
    )
    monkeypatch.setattr(
        "src.ingestion.fetch.yf.download",
        lambda **kwargs: raw,
    )

    window = {
        "actual_fetch_start_date": "2021-09-27",
        "api_end_date": "2021-09-29",
    }
    result = fetch_ticker("SPY", config, window)

    assert result["status"] == "SUCCESS"
    assert result["rows_fetched"] == 2


def test_fetch_retries_timeout(monkeypatch, config):
    calls = {"count": 0}

    def timeout_then_success(**kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise TimeoutError("temporary timeout")
        return pd.DataFrame(
            {"Close": [100.0]},
            index=pd.to_datetime(["2021-09-27"]),
        )

    monkeypatch.setattr(
        "src.ingestion.fetch.yf.download",
        timeout_then_success,
    )
    monkeypatch.setattr("src.ingestion.fetch.time.sleep", lambda _: None)

    window = {
        "actual_fetch_start_date": "2021-09-27",
        "api_end_date": "2021-09-29",
    }
    result = fetch_ticker("SPY", config, window)

    assert result["status"] == "SUCCESS"
    assert result["attempts"] == 2
    assert len(result["errors"]) == 1


def test_fetch_fails_when_close_column_missing(monkeypatch, config):
    raw = pd.DataFrame(
        {"Open": [100.0]},
        index=pd.to_datetime(["2021-09-27"]),
    )
    monkeypatch.setattr(
        "src.ingestion.fetch.yf.download",
        lambda **kwargs: raw,
    )

    window = {
        "actual_fetch_start_date": "2021-09-27",
        "api_end_date": "2021-09-29",
    }
    result = fetch_ticker("SPY", config, window)

    assert result["status"] == "FAILED"
    assert result["failure_type"] == "SCHEMA_ERROR"


def test_transform_maps_close_and_calculates_returns(config, run_metadata):
    raw = pd.DataFrame(
        {"Close": [100.0, 102.0]},
        index=pd.to_datetime(["2021-09-27", "2021-09-28"]),
    )
    window = {"config_start_date": "2021-09-27"}

    result = transform_ticker(
        "SPY", raw, config, run_metadata, window
    )

    assert result.loc[0, "adjusted_close"] == 100.0
    assert pd.isna(result.loc[0, "simple_return"])
    assert result.loc[1, "simple_return"] == pytest.approx(0.02)
    assert result.loc[1, "log_return"] == pytest.approx(0.0198026)


def test_validation_flags_anomaly_as_warning(config):
    data = pd.DataFrame({
        "date": pd.to_datetime(["2021-09-27", "2021-09-28"]).date,
        "ticker": ["SPY", "SPY"],
        "adjusted_close": [100.0, 125.0],
        "simple_return": [None, 0.25],
        "log_return": [None, 0.22314355],
        "is_anomaly_flagged": [False, True],
        "is_warmup_buffer": [False, False],
    })

    report = validate_all(
        data=data,
        expected_trading_days=["2021-09-27", "2021-09-28"],
        tickers=["SPY"],
        anomaly_threshold=0.20,
    )

    spy = report["ticker_results"]["SPY"]
    assert spy["status"] == "SUCCESS_WITH_WARNING"
    assert len(spy["warnings"]) == 1


def test_validation_detects_missing_day_and_duplicate(config):
    data = pd.DataFrame({
        "date": pd.to_datetime([
            "2021-09-27", "2021-09-27",
        ]).date,
        "ticker": ["IEF", "IEF"],
        "adjusted_close": [100.0, 101.0],
        "simple_return": [None, 0.01],
        "log_return": [None, 0.00995],
        "is_anomaly_flagged": [False, False],
        "is_warmup_buffer": [False, False],
    })

    report = validate_all(
        data=data,
        expected_trading_days=["2021-09-27", "2021-09-28"],
        tickers=["IEF"],
    )

    ief = report["ticker_results"]["IEF"]
    assert ief["status"] == "FAILED"
    assert "DUPLICATE_DATE_TICKER_KEY" in ief["error_codes"]
    assert "MISSING_EXPECTED_TRADING_DAY" in ief["error_codes"]
    assert ief["missing_days"] == ["2021-09-28"]