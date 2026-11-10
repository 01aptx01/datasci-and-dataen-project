import pandas as pd
import pytest

from src.ingestion.calendar import build_ingestion_window
from src.ingestion.fetch import fetch_ticker
from src.ingestion.transform import transform_ticker
from src.ingestion.validate import validate_all
from src.ingestion.quarantine import handle_quarantine_and_publish
from src.ingestion.audit_report import create_run_report
from src.ingestion.raw_storage import save_raw_snapshot


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


def test_calendar_caps_future_end_date_to_effective_end_date(config):
    config["date_range"]["end_date"] = "2035-01-01"
    window = build_ingestion_window(config)

    assert window["effective_end_date"] < "2035-01-01"
    assert window["expected_trading_days"][-1] == window["effective_end_date"]
    assert window["api_end_date"] > window["effective_end_date"]


def test_transform_filters_dates_after_effective_end(config, run_metadata):
    raw = pd.DataFrame(
        {
            "Open": [100.0, 102.0, 105.0], "Close": [100.0, 102.0, 105.0],
            "High": [101.0, 103.0, 106.0],
            "Low": [99.0, 101.0, 104.0],
        },
        index=pd.to_datetime(["2021-09-27", "2021-09-28", "2021-09-30"]),
    )
    window = {
        "config_start_date": "2021-09-27",
        "config_end_date": "2021-09-30",
        "effective_end_date": "2021-09-28",
    }

    result = transform_ticker(
        "SPY", raw, config, run_metadata, window
    )

    # 2021-09-30 should be filtered out
    assert len(result) == 2
    assert str(result.loc[1, "date"]) == "2021-09-28"


def test_fetch_success(monkeypatch, config):
    raw = pd.DataFrame(
        {
            "Open": [99.5, 101.5], "Close": [100.0, 102.0],
            "High": [101.0, 103.0],
            "Low": [99.0, 101.0],
        },
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
            {"Open": [100.0], "Close": [100.0], "High": [101.0], "Low": [99.0]},
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


def test_fetch_fails_when_required_column_missing(monkeypatch, config):
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


def test_transform_maps_prices_and_calculates_returns(config, run_metadata):
    raw = pd.DataFrame(
        {
            "Open": [99.5, 101.5], "Close": [100.0, 102.0],
            "High": [101.0, 103.0],
            "Low": [99.0, 101.0],
        },
        index=pd.to_datetime(["2021-09-27", "2021-09-28"]),
    )
    window = {"config_start_date": "2021-09-27"}

    result = transform_ticker(
        "SPY", raw, config, run_metadata, window
    )

    assert result.loc[0, "open"] == 99.5
    assert result.loc[1, "open"] == 101.5
    assert result.loc[0, "adjusted_close"] == 100.0
    assert result.loc[0, "high"] == 101.0
    assert result.loc[0, "low"] == 99.0
    assert pd.isna(result.loc[0, "simple_return"])
    assert result.loc[1, "simple_return"] == pytest.approx(0.02)
    assert result.loc[1, "log_return"] == pytest.approx(0.0198026, rel=1e-4)

    expected_columns = [
        "date",
        "ticker",
        "open",
        "adjusted_close",
        "high",
        "low",
        "simple_return",
        "log_return",
        "is_anomaly_flagged",
        "is_warmup_buffer",
        "run_id",
        "source_batch_id",
        "ingested_at_utc",
    ]
    assert list(result.columns) == expected_columns


def test_fetch_requires_open(monkeypatch, config):
    raw = pd.DataFrame(
        {"Close": [100.0], "High": [101.0], "Low": [99.0]},
        index=pd.to_datetime(["2021-09-27"]),
    )
    monkeypatch.setattr("src.ingestion.fetch.yf.download", lambda **kwargs: raw)
    result = fetch_ticker("SPY", config, {
        "actual_fetch_start_date": "2021-09-27", "api_end_date": "2021-09-29",
    })
    assert result["failure_type"] == "SCHEMA_ERROR"
    assert "Open" in result["errors"][-1]


def test_transform_requires_open(config, run_metadata):
    raw = pd.DataFrame(
        {"Close": [100.0], "High": [101.0], "Low": [99.0]},
        index=pd.to_datetime(["2021-09-27"]),
    )
    with pytest.raises(ValueError, match="missing Open"):
        transform_ticker("SPY", raw, config, run_metadata, {"config_start_date": "2021-09-27"})


@pytest.mark.parametrize("opening,code", [
    (0, "NON_POSITIVE_PRICE"), (-1, "NON_POSITIVE_PRICE"),
    (float('nan'), "NON_POSITIVE_PRICE"), (float('inf'), "NON_POSITIVE_PRICE"),
    (98, "INVALID_HIGH_LOW"), (102, "INVALID_HIGH_LOW"),
])
def test_validation_rejects_invalid_open(config, run_metadata, opening, code):
    raw = pd.DataFrame(
        {"Open": [opening], "Close": [100.0], "High": [101.0], "Low": [99.0]},
        index=pd.to_datetime(["2021-09-27"]),
    )
    data = transform_ticker("SPY", raw, config, run_metadata, {"config_start_date": "2021-09-27"})
    result = validate_all(data=data, expected_trading_days=["2021-09-27"], tickers=["SPY"])
    assert code in result["ticker_results"]["SPY"]["error_codes"]


def test_validation_flags_anomaly_as_warning(config):
    data = pd.DataFrame({
        "date": pd.to_datetime(["2021-09-27", "2021-09-28"]).date,
        "ticker": ["SPY", "SPY"],
        "open": [100.0, 125.0], "adjusted_close": [100.0, 125.0],
        "high": [105.0, 126.0],
        "low": [99.0, 120.0],
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
        "open": [100.0, 101.0], "adjusted_close": [100.0, 101.0],
        "high": [102.0, 103.0],
        "low": [99.0, 100.0],
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
    assert "DUPLICATE_PRIMARY_KEY" in ief["error_codes"]
    assert "MISSING_EXPECTED_TRADING_DAY" in ief["error_codes"]
    assert ief["missing_days"] == ["2021-09-28"]


def test_validation_detects_invalid_high_low(config):
    # low > high
    data = pd.DataFrame({
        "date": pd.to_datetime(["2021-09-27"]).date,
        "ticker": ["SPY"],
        "open": [100.0], "adjusted_close": [100.0],
        "high": [95.0],
        "low": [105.0],
        "simple_return": [None],
        "log_return": [None],
        "is_anomaly_flagged": [False],
        "is_warmup_buffer": [False],
    })

    report = validate_all(
        data=data,
        expected_trading_days=["2021-09-27"],
        tickers=["SPY"],
    )

    spy = report["ticker_results"]["SPY"]
    assert spy["status"] == "FAILED"
    assert "INVALID_HIGH_LOW" in spy["error_codes"]


def test_validation_detects_non_positive_price(config):
    data = pd.DataFrame({
        "date": pd.to_datetime(["2021-09-27"]).date,
        "ticker": ["GLD"],
        "open": [-50.0], "adjusted_close": [-50.0],
        "high": [100.0],
        "low": [-60.0],
        "simple_return": [None],
        "log_return": [None],
        "is_anomaly_flagged": [False],
        "is_warmup_buffer": [False],
    })

    report = validate_all(
        data=data,
        expected_trading_days=["2021-09-27"],
        tickers=["GLD"],
    )

    gld = report["ticker_results"]["GLD"]
    assert gld["status"] == "FAILED"
    assert "NON_POSITIVE_PRICE" in gld["error_codes"]


def test_validation_detects_invalid_warmup_flag(config):
    data = pd.DataFrame({
        "date": pd.to_datetime(["2021-09-26", "2021-09-28"]).date,
        "ticker": ["SPY", "SPY"],
        "open": [100.0, 102.0], "adjusted_close": [100.0, 102.0],
        "high": [105.0, 106.0],
        "low": [98.0, 101.0],
        "simple_return": [None, 0.02],
        "log_return": [None, 0.0198],
        "is_anomaly_flagged": [False, False],
        # 2021-09-26 is before 2021-09-27, so should be True, but we set False
        "is_warmup_buffer": [False, False],
    })

    report = validate_all(
        data=data,
        expected_trading_days=["2021-09-26", "2021-09-28"],
        tickers=["SPY"],
        config_start_date="2021-09-27",
    )

    spy = report["ticker_results"]["SPY"]
    assert spy["status"] == "FAILED"
    assert "INVALID_WARMUP_FLAG" in spy["error_codes"]


def test_quarantine_appends_to_csv(tmp_path):
    data = pd.DataFrame({
        "date": pd.to_datetime(["2021-09-27"]).date,
        "ticker": ["SPY"],
        "open": [-10.0], "adjusted_close": [-10.0],
        "high": [100.0],
        "low": [90.0],
        "simple_return": [None],
        "log_return": [None],
        "is_anomaly_flagged": [False],
        "is_warmup_buffer": [False],
    })

    validation_report = validate_all(
        data=data,
        expected_trading_days=["2021-09-27"],
        tickers=["SPY"],
    )

    csv_file = tmp_path / "quarantine.csv"
    handle_quarantine_and_publish(
        data=data,
        validation_report=validation_report,
        tickers=["SPY"],
        run_id="run_test_quarantine",
        source_batch_id="yf_test_batch",
        quarantine_root=str(tmp_path / "quarantine"),
        publish_root=str(tmp_path / "publish"),
        quarantine_csv_path=str(csv_file),
    )

    assert csv_file.is_file()
    df_quarantine = pd.read_csv(csv_file)
    assert len(df_quarantine) >= 1
    assert "run_id" in df_quarantine.columns
    assert "source_batch_id" in df_quarantine.columns
    assert "reason" in df_quarantine.columns
    assert "detected_at_utc" in df_quarantine.columns
    assert df_quarantine.iloc[0]["reason"] == "NON_POSITIVE_PRICE"
    assert df_quarantine.iloc[0]["source_batch_id"] == "yf_test_batch"


def test_audit_report_appends_to_jsonl(tmp_path):
    import json

    metadata = {
        "run_id": "run_test_audit",
        "source_batch_id": "yf_test_batch",
        "started_at_utc": "2026-09-24T01:00:00Z",
        "finished_at_utc": "2026-09-24T01:00:05Z",
        "config_start_date": "2021-09-27",
        "config_end_date": "2021-10-01",
        "actual_fetch_start_date": "2021-06-28",
        "api_end_date": "2021-10-02",
        "tickers": {"SPY": {"status": "SUCCESS"}},
    }
    fetch_results = {
        "SPY": {
            "rows_fetched": 5,
            "attempts": 1,
            "data": pd.DataFrame(index=pd.to_datetime(["2021-09-27"])),
        }
    }
    validation_report = {
        "ticker_results": {
            "SPY": {
                "rows_checked": 5,
                "rows_passed": 5,
                "status": "SUCCESS",
                "warnings": [],
                "error_codes": [],
            }
        }
    }
    quarantine_result = {
        "ticker_summary": {
            "SPY": {
                "publish_status": "PUBLISHED",
                "rows_published": 5,
                "quarantined_records": 0,
                "missing_day_events": 0,
            }
        }
    }
    publish_report = {
        "table": "data/curated/market_prices_daily.parquet",
        "portfolio_ready": True,
        "rows_inserted": 5,
        "rows_updated": 0,
        "rows_unchanged": 0,
    }

    jsonl_file = tmp_path / "ingestion_runs.jsonl"
    report = create_run_report(
        run_metadata=metadata,
        fetch_results=fetch_results,
        validation_report=validation_report,
        quarantine_result=quarantine_result,
        publish_report=publish_report,
        audit_root=str(tmp_path / "audit"),
        jsonl_path=str(jsonl_file),
    )

    assert report["overall_status"] == "SUCCESS"
    assert jsonl_file.is_file()

    with jsonl_file.open("r", encoding="utf-8") as f:
        lines = f.readlines()
    assert len(lines) == 1

    entry = json.loads(lines[0])
    assert entry["run_id"] == "run_test_audit"
    assert entry["status"] == "SUCCESS"
    assert entry["rows_fetched_raw"] == 5
    assert entry["rows_published"] == 5
    assert "SPY" in entry["tickers"]
    assert entry["tickers"]["SPY"]["status"] == "SUCCESS"


def test_save_raw_snapshot_creates_csv_and_manifest(tmp_path, config):
    import json

    results = {
        "SPY": {
            "status": "SUCCESS",
            "data": pd.DataFrame(
                {"Open": [100.0], "Close": [100.0], "High": [102.0], "Low": [98.0]},
                index=pd.to_datetime(["2021-09-27"]),
            ),
        }
    }
    run_meta = {
        "run_id": "run_001",
        "source_batch_id": "batch_001",
    }
    window = {
        "config_start_date": "2021-09-27",
        "config_end_date": "2021-10-01",
        "actual_fetch_start_date": "2021-06-28",
        "api_end_date": "2021-10-02",
    }

    snapshot = save_raw_snapshot(
        results=results,
        run_metadata=run_meta,
        config=config,
        ingestion_window=window,
        root_dir=str(tmp_path / "raw"),
    )

    batch_dir = tmp_path / "raw" / "batch_001"
    raw_csv = batch_dir / "raw_prices.csv"
    manifest_file = batch_dir / "manifest.json"

    assert raw_csv.is_file()
    assert manifest_file.is_file()

    df_raw = pd.read_csv(raw_csv)
    assert len(df_raw) == 1
    assert "ticker" in df_raw.columns
    assert "Close" in df_raw.columns

    manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert manifest_data["source_batch_id"] == "batch_001"
    assert manifest_data["sha256"] == snapshot["sha256"]
    assert manifest_data["rows_fetched_raw"] == 1

    # Overwrite refusal test
    with pytest.raises(FileExistsError):
        save_raw_snapshot(
            results=results,
            run_metadata=run_meta,
            config=config,
            ingestion_window=window,
            root_dir=str(tmp_path / "raw"),
        )
