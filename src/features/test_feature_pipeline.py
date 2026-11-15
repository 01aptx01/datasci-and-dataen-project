from importlib import import_module
from importlib.util import find_spec
from dataclasses import replace
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml


def feature_api():
    assert find_spec("src.features.pipeline") is not None, (
        "Expected src.features.pipeline to implement the feature contract"
    )
    return import_module("src.features.pipeline")


def make_prices(periods=65, start_date_index=61, mode="varied"):
    import pandas_market_calendars as market_calendars

    sessions = market_calendars.get_calendar("XNYS").schedule(
        start_date="2024-01-02",
        end_date="2025-01-01",
    ).index
    dates = sessions.date[:periods]
    frames = []
    for asset_index, ticker in enumerate(("SPY", "IEF", "GLD")):
        index = np.arange(periods, dtype=float)
        if mode == "varied":
            returns = (
                0.004 * np.sin((index + asset_index * 1.7) / 3.1)
                + 0.002 * np.cos((index * (asset_index + 1)) / 5.3)
                + (asset_index - 1) * 0.0007
            )
        elif mode == "up":
            returns = np.full(periods, 0.01)
        elif mode == "flat":
            returns = np.zeros(periods)
        else:
            raise ValueError(mode)

        closes = np.empty(periods, dtype=float)
        closes[0] = 100 + asset_index * 10
        for row in range(1, periods):
            closes[row] = closes[row - 1] * np.exp(returns[row])

        log_returns = np.full(periods, np.nan)
        log_returns[1:] = np.log(closes[1:] / closes[:-1])
        simple_returns = np.full(periods, np.nan)
        simple_returns[1:] = closes[1:] / closes[:-1] - 1
        frames.append(
            pd.DataFrame(
                {
                    "date": dates,
                    "ticker": ticker,
                    "open": closes * 1.001,
                    "adjusted_close": closes,
                    "high": closes * 1.01,
                    "low": closes * 0.99,
                    "simple_return": simple_returns,
                    "log_return": log_returns,
                    "is_anomaly_flagged": False,
                    "is_warmup_buffer": [day < dates[start_date_index] for day in dates],
                    "run_id": "ing_run_test",
                    "source_batch_id": [f"batch_{day:%Y%m%d}" for day in dates],
                    "ingested_at_utc": pd.Timestamp("2024-04-01T21:00:00Z"),
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


@pytest.fixture
def sample_prices():
    return make_prices()


@pytest.fixture
def feature_config(sample_prices):
    api = feature_api()
    dates = tuple(sorted(sample_prices["date"].unique()))
    return api.FeatureConfig(
        start_date=dates[61],
        expected_trading_days=dates,
    )


def build(api, prices, config, run_id="feat_run_test"):
    return api.build_feature_tables(
        prices,
        config,
        run_id=run_id,
        feature_as_of_utc="2026-11-13T00:00:00Z",
    )


def write_feature_config(root, input_path, dates):
    config_path = root / "features.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "feature": {
                    "start_date": dates[61].isoformat(),
                    "tickers": ["SPY", "IEF", "GLD"],
                    "feature_set_version": "2.0.0",
                    "expected_trading_days": [day.isoformat() for day in dates],
                },
                "calendar": {"market": "XNYS"},
                "paths": {
                    "input": str(input_path),
                    "features": str(root / "asset_volatility_features.parquet"),
                    "correlations": str(root / "asset_rolling_correlations.parquet"),
                    "manifest_dir": str(root / "audit"),
                },
                "publish": {"overwrite_conflicts": False},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    for day in dates:
        batch_id = f"batch_{day:%Y%m%d}"
        batch_dir = root / "data" / "raw" / batch_id
        batch_dir.mkdir(parents=True, exist_ok=True)
        raw_path = batch_dir / "raw_prices.csv"
        raw_path.write_text("date,ticker\n", encoding="utf-8")
        manifest = {
            "source_batch_id": batch_id,
            "raw_file_path": raw_path.relative_to(root).as_posix(),
            "sha256": "a" * 64,
        }
        (batch_dir / "manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
    return config_path


def test_feature_pipeline_module_is_available():
    assert find_spec("src.features.pipeline") is not None


def test_example_config_loads():
    settings = import_module("src.features.run").load_config("config/features.yaml")
    assert settings["feature_config"].start_date.isoformat() == "2021-09-27"
    assert settings["feature_config"].end_date.isoformat() == "2026-09-25"
    assert settings["feature_config"].warmup_trading_days == 61
    assert settings["input_path"].as_posix() == "data/curated/market_prices_daily.parquet"


def test_feature_config_rejects_less_than_contract_warmup_days(sample_prices):
    api = feature_api()
    dates = tuple(sorted(sample_prices["date"].unique()))

    with pytest.raises(api.FeaturePipelineError, match="at least 61"):
        api.FeatureConfig(
            start_date=dates[61],
            warmup_trading_days=60,
            expected_trading_days=dates,
        )


def test_explicit_sessions_must_include_contract_warmup_days(sample_prices):
    api = feature_api()
    dates = tuple(sorted(sample_prices["date"].unique()))
    config = api.FeatureConfig(
        start_date=dates[60],
        expected_trading_days=dates,
    )

    with pytest.raises(api.FeaturePipelineError, match="at least 61 warm-up sessions"):
        api.build_feature_tables(sample_prices, config, run_id="short_warmup_test")


def test_explicit_sessions_must_match_configured_market_calendar(sample_prices):
    api = feature_api()
    dates = tuple(sorted(sample_prices["date"].unique()))
    saturday = pd.Timestamp("2024-01-06").date()
    config = api.FeatureConfig(
        start_date=dates[61],
        expected_trading_days=tuple(sorted((*dates, saturday))),
    )

    with pytest.raises(api.FeaturePipelineError, match="must match.*market calendar"):
        api.build_feature_tables(sample_prices, config, run_id="non_session_override")


def test_rejects_naive_ingested_at_timestamp(sample_prices, feature_config):
    api = feature_api()
    invalid = sample_prices.copy()
    invalid["ingested_at_utc"] = invalid["ingested_at_utc"].dt.tz_localize(None)

    with pytest.raises(api.FeaturePipelineError, match="timezone-aware"):
        api.build_feature_tables(invalid, feature_config, run_id="naive_ingestion_time")


def test_ohlc_tolerance_accepts_small_rounding_difference(sample_prices, feature_config):
    api = feature_api()
    invalid = sample_prices.copy()
    row = invalid.index[0]
    invalid.loc[row, "low"] = invalid.loc[row, "adjusted_close"] + 5e-5

    api.build_feature_tables(invalid, feature_config, run_id="ohlc_within_tolerance")


def test_ohlc_tolerance_rejects_difference_above_contract_limit(
    sample_prices, feature_config
):
    api = feature_api()
    invalid = sample_prices.copy()
    row = invalid.index[0]
    invalid.loc[row, "low"] = invalid.loc[row, "adjusted_close"] + 1.1e-4

    with pytest.raises(api.FeaturePipelineError, match="input OHLC values"):
        api.build_feature_tables(invalid, feature_config, run_id="ohlc_outside_tolerance")


def test_output_schemas_formulas_and_readiness(sample_prices, feature_config):
    api = feature_api()
    features, correlations = build(api, sample_prices, feature_config)

    assert list(features.columns) == api.FEATURE_COLUMNS
    assert len(api.CORE_FEATURE_COLUMNS) == 8
    assert len(features.columns) == 18
    assert list(correlations.columns) == api.CORRELATION_COLUMNS
    assert len(correlations.columns) == 8
    assert len(features) == len(sample_prices)
    assert len(correlations) == sample_prices["date"].nunique()

    source = sample_prices.query("ticker == 'SPY'").sort_values("date").reset_index(drop=True)
    row = features.query("ticker == 'SPY'").sort_values("date").iloc[61]
    spy_features = features.query("ticker == 'SPY'").sort_values("date").reset_index(drop=True)
    expected_rv60 = np.sqrt(252 / 60 * np.square(source["log_return"].iloc[2:62]).sum())
    assert row["ret_1d_t"] == pytest.approx(source["log_return"].iloc[61])
    assert row["ret_lag_1d"] == pytest.approx(source["log_return"].iloc[60])
    assert row["ret_lag_2d"] == pytest.approx(source["log_return"].iloc[59])
    assert row["ret_trailing_5d"] == pytest.approx(
        source["adjusted_close"].iloc[61] / source["adjusted_close"].iloc[56] - 1
    )
    assert row["ret_trailing_20d"] == pytest.approx(
        source["adjusted_close"].iloc[61] / source["adjusted_close"].iloc[41] - 1
    )
    expected_rv5 = np.sqrt(252 / 5 * np.square(source["log_return"].iloc[57:62]).sum())
    expected_rv20 = np.sqrt(252 / 20 * np.square(source["log_return"].iloc[42:62]).sum())
    expected_bb_width = (
        4
        * source["adjusted_close"].iloc[42:62].std(ddof=0)
        / source["adjusted_close"].iloc[42:62].mean()
    )
    assert row["rv_5d"] == pytest.approx(expected_rv5)
    assert row["rv_20d"] == pytest.approx(expected_rv20)
    assert row["rv_60d"] == pytest.approx(expected_rv60)
    assert row["bb_width_20d"] == pytest.approx(expected_bb_width)
    assert bool(row["is_model_ready"]) is True
    assert bool(row["is_warmup_buffer"]) is False
    assert pd.isna(spy_features.loc[0, "ret_1d_t"])
    assert pd.isna(spy_features.loc[0, "ret_lag_1d"])
    assert pd.isna(spy_features.loc[1, "ret_lag_1d"])
    assert pd.isna(spy_features.loc[2, "ret_lag_2d"])
    assert bool(spy_features.loc[59, "is_model_ready"]) is False
    assert pd.isna(spy_features.loc[59, "rv_60d"])


def test_feature_warnings_flag_contract_limits_without_dropping_rows(
    sample_prices, feature_config
):
    api = feature_api()
    features, _ = build(api, sample_prices, feature_config)
    row_index = features.index[
        features["ticker"].eq("SPY") & features["ret_1d_t"].notna()
    ][0]
    features.loc[row_index, "ret_1d_t"] = 0.16

    warnings = api.collect_feature_warnings(features)

    assert warnings == [
        {
            "date": features.loc[row_index, "date"].isoformat(),
            "ticker": "SPY",
            "feature": "ret_1d_t",
            "value": 0.16,
            "lower_bound": -0.15,
            "upper_bound": 0.15,
        }
    ]
    assert len(features) == len(sample_prices)
    assert features.loc[row_index, "ret_1d_t"] == 0.16


def test_build_feature_tables_checks_xnys_sessions_without_explicit_days(sample_prices):
    api = feature_api()
    dates = tuple(sorted(sample_prices["date"].unique()))
    missing_day = dates[20]
    prices = sample_prices.loc[sample_prices["date"] != missing_day].copy()
    prices["is_warmup_buffer"] = prices["date"].map(lambda day: day < dates[-1])
    config = api.FeatureConfig(
        start_date=dates[-1],
        end_date=dates[-1],
        warmup_trading_days=61,
    )

    with pytest.raises(api.FeaturePipelineError, match="missing expected trading days"):
        api.build_feature_tables(prices, config, run_id="feature_calendar_test")


def test_features_do_not_change_when_future_rows_are_added(sample_prices, feature_config):
    api = feature_api()
    ticker = "IEF"
    t = sorted(sample_prices["date"].unique())[62]
    before = sample_prices.loc[(sample_prices["ticker"] == ticker) & (sample_prices["date"] <= t)]
    before_dates = tuple(sorted(before["date"].unique()))
    before_config = replace(feature_config, expected_trading_days=before_dates)
    partial_features, _ = build(api, before, before_config)
    full_features, _ = build(api, sample_prices, feature_config)
    business = [
        "ret_1d_t", "ret_lag_1d", "ret_lag_2d", "ret_trailing_5d",
        "ret_trailing_20d", "rv_5d", "rv_20d", "rv_60d", "rsi_14d",
        "bb_width_20d", "is_model_ready", "is_warmup_buffer",
    ]
    old_row = partial_features.query("ticker == @ticker and date == @t").iloc[0]
    full_row = full_features.query("ticker == @ticker and date == @t").iloc[0]
    pd.testing.assert_series_equal(old_row[business], full_row[business], check_names=False)


def test_features_are_calculated_within_each_ticker(sample_prices, feature_config):
    api = feature_api()
    features, _ = build(api, sample_prices, feature_config)
    source = sample_prices.query("ticker == 'GLD'").sort_values("date").reset_index(drop=True)
    row = features.query("ticker == 'GLD'").sort_values("date").iloc[25]
    assert row["ret_1d_t"] == pytest.approx(source["log_return"].iloc[25])
    assert row["ret_1d_t"] != pytest.approx(
        sample_prices.query("ticker == 'SPY'").sort_values("date").iloc[25]["log_return"]
    )


def test_model_readiness_is_independent_of_warmup_buffer(sample_prices, feature_config):
    api = feature_api()
    dates = tuple(sorted(sample_prices["date"].unique()))
    config = replace(feature_config, start_date=dates[63])
    prices = sample_prices.copy()
    prices["is_warmup_buffer"] = prices["date"].map(lambda day: day < dates[63])
    features, _ = build(api, prices, config)
    warmup_ready = features.query("ticker == 'SPY' and date == @dates[60]").iloc[0]
    assert bool(warmup_ready["is_model_ready"]) is True
    assert bool(warmup_ready["is_warmup_buffer"]) is True


def test_experimental_features_follow_warmup_and_wilder_rsi(sample_prices, feature_config):
    api = feature_api()
    rising = make_prices(mode="up")
    features, _ = build(api, rising, feature_config)
    spy = features.query("ticker == 'SPY'").sort_values("date").reset_index(drop=True)
    assert pd.isna(spy.loc[13, "rsi_14d"])
    assert spy.loc[14, "rsi_14d"] == pytest.approx(100.0)
    assert pd.isna(spy.loc[18, "bb_width_20d"])
    assert spy.loc[19, "bb_width_20d"] >= 0

    flat = make_prices(mode="flat")
    flat_features, _ = build(api, flat, feature_config)
    flat_spy = flat_features.query("ticker == 'SPY'").sort_values("date").reset_index(drop=True)
    assert flat_spy.loc[14, "rsi_14d"] == pytest.approx(50.0)


def test_rejects_duplicate_primary_keys(sample_prices, feature_config):
    api = feature_api()
    invalid = pd.concat([sample_prices, sample_prices.iloc[[0]]], ignore_index=True)
    with pytest.raises(api.FeaturePipelineError, match="duplicate"):
        api.build_feature_tables(invalid, feature_config, run_id="test")


def test_rejects_inconsistent_return_source(sample_prices, feature_config):
    api = feature_api()
    invalid = sample_prices.copy()
    invalid.loc[invalid.index[8], "log_return"] += 0.1
    with pytest.raises(api.FeaturePipelineError, match="log_return"):
        api.build_feature_tables(invalid, feature_config, run_id="test")


def test_rejects_warmup_mismatch_and_missing_expected_session(sample_prices, feature_config):
    api = feature_api()
    invalid_flag = sample_prices.copy()
    invalid_flag.loc[0, "is_warmup_buffer"] = False
    with pytest.raises(api.FeaturePipelineError, match="warmup"):
        api.build_feature_tables(invalid_flag, feature_config, run_id="test")

    missing_session = sample_prices.loc[
        ~((sample_prices["ticker"] == "IEF") & (sample_prices["date"] == feature_config.expected_trading_days[10]))
    ].copy()
    with pytest.raises(api.FeaturePipelineError, match="missing expected"):
        api.build_feature_tables(missing_session, feature_config, run_id="test")


def test_run_aborts_without_publish_when_market_session_is_missing(
    sample_prices, tmp_path, monkeypatch, caplog
):
    runner = import_module("src.features.run")
    missing_date = sorted(sample_prices["date"].unique())[10]
    incomplete_prices = sample_prices.loc[
        ~(
            sample_prices["ticker"].eq("IEF")
            & sample_prices["date"].eq(missing_date)
        )
    ]
    input_path = tmp_path / "market_prices_daily.parquet"
    incomplete_prices.to_parquet(input_path, index=False)
    dates = sorted(sample_prices["date"].unique())
    config_path = write_feature_config(tmp_path, input_path, dates)

    features_path = tmp_path / "asset_volatility_features.parquet"
    correlations_path = tmp_path / "asset_rolling_correlations.parquet"
    features_path.write_bytes(b"previous-features")
    correlations_path.write_bytes(b"previous-correlations")
    quarantine_path = tmp_path / "logs" / "quarantine.csv"
    quarantine_path.parent.mkdir(parents=True)
    quarantine_path.write_bytes(b"existing-quarantine-records")
    original_files = {
        path: path.read_bytes()
        for path in (features_path, correlations_path, quarantine_path)
    }
    run_id = "missing_session_abort_test"
    monkeypatch.chdir(tmp_path)

    assert runner.main(["--config", str(config_path), "--run-id", run_id]) == 1

    assert f"missing expected trading days for ticker IEF: {missing_date.isoformat()}" in caplog.text
    assert all(path.read_bytes() == contents for path, contents in original_files.items())
    assert not (tmp_path / "audit" / f"run_id={run_id}").exists()


def test_rejects_missing_schema_and_invalid_prices(sample_prices, feature_config):
    api = feature_api()
    missing_column = sample_prices.drop(columns=["source_batch_id"])
    with pytest.raises(api.FeaturePipelineError, match="source_batch_id"):
        api.build_feature_tables(missing_column, feature_config, run_id="test")

    invalid_price = sample_prices.copy()
    invalid_price.loc[0, "adjusted_close"] = 0
    with pytest.raises(api.FeaturePipelineError, match="positive"):
        api.build_feature_tables(invalid_price, feature_config, run_id="test")


def test_correlations_use_one_synchronized_20_return_window(sample_prices, feature_config):
    api = feature_api()
    _, correlations = build(api, sample_prices, feature_config)
    row = correlations.sort_values("date").iloc[20]
    aligned = (
        sample_prices.pivot(index="date", columns="ticker", values="log_return")
        .loc[:, ["SPY", "IEF", "GLD"]]
        .iloc[1:21]
    )
    expected = np.corrcoef(aligned.to_numpy(), rowvar=False)
    assert bool(row["is_corr_ready"]) is True
    assert row["corr_spy_ief_20d"] == pytest.approx(expected[0, 1])
    assert row["corr_spy_gld_20d"] == pytest.approx(expected[0, 2])
    assert row["corr_ief_gld_20d"] == pytest.approx(expected[1, 2])


def test_incomplete_or_zero_variance_correlation_window_is_not_ready(sample_prices, feature_config):
    api = feature_api()
    missing = sample_prices.loc[
        ~((sample_prices["ticker"] == "GLD") & (sample_prices["date"] == feature_config.expected_trading_days[12]))
    ].copy()
    incomplete = api.build_rolling_correlations(
        missing, feature_config.tickers, "corr_test", "2026-11-13T00:00:00Z",
        expected_trading_days=feature_config.expected_trading_days,
    )
    row = incomplete.sort_values("date").iloc[20]
    assert bool(row["is_corr_ready"]) is False
    assert pd.isna(row["corr_spy_ief_20d"])

    flat = make_prices(mode="flat")
    no_variance = api.build_rolling_correlations(
        flat, feature_config.tickers, "corr_test", "2026-11-13T00:00:00Z",
        expected_trading_days=feature_config.expected_trading_days,
    )
    assert not no_variance["is_corr_ready"].any()


def test_rejects_non_psd_correlation_matrix():
    api = feature_api()
    invalid = np.array([[1.0, 0.9, 0.9], [0.9, 1.0, -0.9], [0.9, -0.9, 1.0]])
    assert api.is_valid_correlation_matrix(invalid) is False
    assert api.is_valid_correlation_matrix(np.eye(3)) is True


def test_parquet_publish_is_idempotent_and_blocks_silent_conflicts(
    sample_prices, feature_config, tmp_path
):
    api = feature_api()
    storage = import_module("src.features.storage")
    features, correlations = build(api, sample_prices, feature_config, "feat_first")
    feature_path = tmp_path / "asset_volatility_features.parquet"
    correlation_path = tmp_path / "asset_rolling_correlations.parquet"
    manifest_path = tmp_path / "run_id=feat_first" / "manifest.json"
    manifest = {"run_id": "feat_first", "input_sha256": "abc123"}

    first = storage.publish_feature_outputs(
        features, correlations, feature_path, correlation_path, manifest_path, manifest
    )
    second = storage.publish_feature_outputs(
        features.assign(run_id="feat_second"),
        correlations.assign(run_id="feat_second"),
        feature_path,
        correlation_path,
        tmp_path / "run_id=feat_second" / "manifest.json",
        {"run_id": "feat_second", "input_sha256": "abc123"},
    )
    assert first["feature_rows"] == len(features)
    assert second["feature_rows"] == len(features)
    assert pd.read_parquet(feature_path).duplicated(["date", "ticker"]).sum() == 0
    assert pd.read_parquet(correlation_path).duplicated(["date"]).sum() == 0

    conflict = features.copy()
    ready_index = conflict.index[conflict["rv_20d"].notna()][0]
    conflict.loc[ready_index, "rv_20d"] += 0.1
    with pytest.raises(api.FeaturePipelineError, match="conflicting"):
        storage.publish_feature_outputs(
            conflict,
            correlations,
            feature_path,
            correlation_path,
            tmp_path / "run_id=conflict" / "manifest.json",
            {"run_id": "conflict"},
        )


def test_publish_migrates_legacy_iso_timestamps_to_utc_parquet_types(
    sample_prices, feature_config, tmp_path
):
    api = feature_api()
    storage = import_module("src.features.storage")
    features, correlations = build(api, sample_prices, feature_config, "feat_legacy")
    feature_path = tmp_path / "asset_volatility_features.parquet"
    correlation_path = tmp_path / "asset_rolling_correlations.parquet"
    manifest_path = tmp_path / "run_id=feat_migrated" / "manifest.json"

    legacy_features = features.assign(
        feature_as_of_utc=features["feature_as_of_utc"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    legacy_correlations = correlations.assign(
        computed_at_utc=correlations["computed_at_utc"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    legacy_features.to_parquet(feature_path, index=False)
    legacy_correlations.to_parquet(correlation_path, index=False)

    storage.publish_feature_outputs(
        features.assign(run_id="feat_migrated"),
        correlations.assign(run_id="feat_migrated"),
        feature_path,
        correlation_path,
        manifest_path,
        {"run_id": "feat_migrated"},
    )

    migrated_features = pd.read_parquet(feature_path)
    migrated_correlations = pd.read_parquet(correlation_path)
    assert isinstance(migrated_features["feature_as_of_utc"].dtype, pd.DatetimeTZDtype)
    assert str(migrated_features["feature_as_of_utc"].dtype.tz) == "UTC"
    assert isinstance(migrated_correlations["computed_at_utc"].dtype, pd.DatetimeTZDtype)
    assert str(migrated_correlations["computed_at_utc"].dtype.tz) == "UTC"


def test_interrupted_output_replacement_restores_previous_files(tmp_path, monkeypatch):
    storage = import_module("src.features.storage")
    feature_path = tmp_path / "features.parquet"
    correlation_path = tmp_path / "correlations.parquet"
    feature_path.write_bytes(b"previous-features")
    correlation_path.write_bytes(b"previous-correlations")
    previous = {
        feature_path: feature_path.read_bytes(),
        correlation_path: correlation_path.read_bytes(),
    }
    staged_features = tmp_path / "features.tmp.parquet"
    staged_correlations = tmp_path / "correlations.tmp.parquet"
    staged_features.write_bytes(b"new-features")
    staged_correlations.write_bytes(b"new-correlations")
    journal_path = tmp_path / "publish-transaction.json"
    real_replace = storage.os.replace

    def interrupt_after_first_publish(source, target):
        result = real_replace(source, target)
        if Path(target) == feature_path and Path(source) == staged_features:
            raise KeyboardInterrupt("simulated process interruption")
        return result

    monkeypatch.setattr(storage.os, "replace", interrupt_after_first_publish)
    with pytest.raises(KeyboardInterrupt, match="simulated process interruption"):
        storage._replace_files_atomically(
            {feature_path: staged_features, correlation_path: staged_correlations},
            journal_path,
        )

    monkeypatch.setattr(storage.os, "replace", real_replace)
    journal = storage.recover_publish_journal(journal_path)

    assert journal["status"] == "ROLLED_BACK"
    assert {path: path.read_bytes() for path in previous} == previous


def test_publish_rejects_timezone_naive_legacy_timestamp(
    sample_prices, feature_config, tmp_path
):
    api = feature_api()
    storage = import_module("src.features.storage")
    features, correlations = build(api, sample_prices, feature_config, "feat_legacy_naive")
    feature_path = tmp_path / "asset_volatility_features.parquet"
    correlation_path = tmp_path / "asset_rolling_correlations.parquet"
    manifest_path = tmp_path / "run_id=feat_rejected_naive" / "manifest.json"

    legacy_features = features.assign(
        feature_as_of_utc=features["feature_as_of_utc"].dt.strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
    )
    legacy_features.to_parquet(feature_path, index=False)
    correlations.to_parquet(correlation_path, index=False)
    existing_bytes = {
        path: path.read_bytes() for path in (feature_path, correlation_path)
    }

    with pytest.raises(api.FeaturePipelineError, match="explicit timezone"):
        storage.publish_feature_outputs(
            features.assign(run_id="feat_rejected_naive"),
            correlations.assign(run_id="feat_rejected_naive"),
            feature_path,
            correlation_path,
            manifest_path,
            {"run_id": "feat_rejected_naive"},
        )

    assert all(path.read_bytes() == contents for path, contents in existing_bytes.items())
    assert not manifest_path.exists()


def test_publish_rejects_dictionary_type_mismatches(
    sample_prices, feature_config, tmp_path
):
    api = feature_api()
    storage = import_module("src.features.storage")
    features, correlations = build(api, sample_prices, feature_config, "feat_types")

    string_dates = features.assign(date=features["date"].astype(str))
    with pytest.raises(api.FeaturePipelineError, match="date must contain DATE values"):
        storage.publish_feature_outputs(
            string_dates,
            correlations,
            tmp_path / "date_features.parquet",
            tmp_path / "date_correlations.parquet",
            tmp_path / "date_manifest.json",
            {"run_id": "date_types"},
        )

    string_features = features.copy()
    string_features["rv_20d"] = string_features["rv_20d"].map(
        lambda value: None if pd.isna(value) else str(value)
    )
    with pytest.raises(api.FeaturePipelineError, match="rv_20d must be numeric"):
        storage.publish_feature_outputs(
            string_features,
            correlations,
            tmp_path / "numeric_features.parquet",
            tmp_path / "numeric_correlations.parquet",
            tmp_path / "numeric_manifest.json",
            {"run_id": "numeric_types"},
        )


def test_pipeline_manifest_includes_snapshot_path_and_checksum(
    sample_prices, tmp_path, monkeypatch
):
    api = feature_api()
    runner = import_module("src.features.run")
    root = tmp_path
    input_path = root / "market_prices_daily.parquet"
    sample_prices.to_parquet(input_path, index=False)
    dates = sorted(sample_prices["date"].unique())
    config_path = write_feature_config(root, input_path, dates)
    monkeypatch.chdir(root)

    report = runner.run_feature_pipeline(config_path, run_id="feat_cli_test")
    manifest_path = root / "audit" / "run_id=feat_cli_test" / "manifest.json"
    assert report["feature_rows"] == len(sample_prices)
    assert report["correlation_rows"] == len(dates)
    assert Path(report["features_path"]).is_file()
    assert Path(report["correlations_path"]).is_file()
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    assert manifest["input"]["sha256"]
    assert manifest["input"]["start_date"] == dates[0].isoformat()
    assert manifest["input"]["end_date"] == dates[-1].isoformat()
    assert manifest["input"]["sources_by_ticker"]["SPY"]["source_batch_ids"]
    assert manifest["input"]["sources_by_ticker"]["SPY"]["start_date"] == dates[0].isoformat()
    snapshot = manifest["input"]["source_snapshots"][0]
    assert snapshot["source_batch_id"].startswith("batch_")
    assert snapshot["raw_file_path"].startswith("data/raw/")
    assert snapshot["snapshot_manifest_path"].endswith("/manifest.json")
    assert snapshot["manifest_status"] == "AVAILABLE"
    assert len(snapshot["raw_file_sha256"]) == 64
    assert all(
        item["manifest_status"] == "AVAILABLE"
        and len(item["raw_file_sha256"]) == 64
        for item in manifest["input"]["source_snapshots"]
    )
    assert manifest["outputs"]["asset_volatility_features"]["columns"] == api.FEATURE_COLUMNS
    transaction = json.loads(
        (manifest_path.parent / "transaction.json").read_text(encoding="utf-8")
    )
    quality_results = pd.read_parquet(
        manifest_path.parent / "quality_results.parquet"
    )
    assert transaction["status"] == "COMMITTED"
    assert transaction["expected_quarantine_records"] == 0
    assert quality_results.empty

    features_written = pd.read_parquet(report["features_path"])
    correlations_written = pd.read_parquet(report["correlations_path"])
    assert isinstance(features_written["feature_as_of_utc"].dtype, pd.DatetimeTZDtype)
    assert str(features_written["feature_as_of_utc"].dtype.tz) == "UTC"
    assert isinstance(correlations_written["computed_at_utc"].dtype, pd.DatetimeTZDtype)
    assert str(correlations_written["computed_at_utc"].dtype.tz) == "UTC"
    manifest_before = manifest_path.read_text(encoding="utf-8")
    with pytest.raises(api.FeaturePipelineError, match="run_id already has a manifest"):
        runner.run_feature_pipeline(config_path, run_id="feat_cli_test")
    assert manifest_path.read_text(encoding="utf-8") == manifest_before


def test_run_id_cannot_escape_the_manifest_directory(sample_prices, tmp_path):
    runner = import_module("src.features.run")
    input_path = tmp_path / "market_prices_daily.parquet"
    sample_prices.to_parquet(input_path, index=False)
    dates = sorted(sample_prices["date"].unique())
    config_path = write_feature_config(tmp_path, input_path, dates)

    with pytest.raises(runner.FeaturePipelineError, match="run_id must be path-safe"):
        runner.run_feature_pipeline(config_path, run_id="../outside")


@pytest.mark.parametrize(
    "lineage_problem",
    [
        "missing_manifest",
        "unreadable_manifest",
        "mismatched_source_batch_id",
        "missing_raw_file_path",
        "missing_raw_file",
        "invalid_sha256",
    ],
)
def test_lineage_failure_prevents_publish_and_orphan_quarantine(
    sample_prices, feature_config, tmp_path, monkeypatch, lineage_problem
):
    api = feature_api()
    runner = import_module("src.features.run")
    input_path = tmp_path / "market_prices_daily.parquet"
    sample_prices.to_parquet(input_path, index=False)
    dates = sorted(sample_prices["date"].unique())
    config_path = write_feature_config(tmp_path, input_path, dates)

    batch_id = sorted(sample_prices["source_batch_id"].unique())[0]
    batch_dir = tmp_path / "data" / "raw" / batch_id
    snapshot_manifest_path = batch_dir / "manifest.json"
    if lineage_problem == "missing_manifest":
        snapshot_manifest_path.unlink()
    elif lineage_problem == "unreadable_manifest":
        snapshot_manifest_path.write_text("{", encoding="utf-8")
    else:
        snapshot_manifest = json.loads(
            snapshot_manifest_path.read_text(encoding="utf-8")
        )
        if lineage_problem == "mismatched_source_batch_id":
            snapshot_manifest["source_batch_id"] = "different_batch"
        elif lineage_problem == "missing_raw_file_path":
            snapshot_manifest.pop("raw_file_path")
        elif lineage_problem == "missing_raw_file":
            snapshot_manifest["raw_file_path"] = (
                f"data/raw/{batch_id}/missing_raw_prices.csv"
            )
        elif lineage_problem == "invalid_sha256":
            snapshot_manifest["sha256"] = "not-a-sha256"
        snapshot_manifest_path.write_text(
            json.dumps(snapshot_manifest), encoding="utf-8"
        )

    previous_features, previous_correlations = build(
        api, sample_prices, feature_config, "feat_previous"
    )
    features_path = tmp_path / "asset_volatility_features.parquet"
    correlations_path = tmp_path / "asset_rolling_correlations.parquet"
    previous_features.to_parquet(features_path, index=False)
    previous_correlations.to_parquet(correlations_path, index=False)
    quarantine_path = tmp_path / "logs" / "quarantine.csv"
    quarantine_path.parent.mkdir(parents=True)
    quarantine_path.write_text(
        "run_id,source_batch_id,date,ticker,raw_value,reason,detected_at_utc\n"
        "previous_run,previous_batch,2024-01-02,SPY,,EXISTING,2026-11-14T00:00:00Z\n",
        encoding="utf-8",
    )
    previous_files = {
        path: path.read_bytes()
        for path in (features_path, correlations_path, quarantine_path)
    }

    build_tables = runner.build_feature_tables
    corrupted_date = dates[62]

    def build_with_corrupted_core(*args, **kwargs):
        features, correlations = build_tables(*args, **kwargs)
        row = features.index[
            features["ticker"].eq("SPY") & features["date"].eq(corrupted_date)
        ][0]
        features.loc[row, "rv_20d"] = np.nan
        features.loc[row, "is_model_ready"] = False
        return features, correlations

    monkeypatch.setattr(runner, "build_feature_tables", build_with_corrupted_core)
    monkeypatch.chdir(tmp_path)
    run_id = "lineage_failure_test"

    with pytest.raises(api.FeaturePipelineError, match=batch_id):
        runner.run_feature_pipeline(config_path, run_id=run_id)

    assert all(path.read_bytes() == contents for path, contents in previous_files.items())
    assert not (tmp_path / "audit" / f"run_id={run_id}").exists()


def test_publish_conflict_does_not_append_orphan_quarantine(
    sample_prices, feature_config, tmp_path, monkeypatch
):
    api = feature_api()
    runner = import_module("src.features.run")
    input_path = tmp_path / "market_prices_daily.parquet"
    sample_prices.to_parquet(input_path, index=False)
    dates = sorted(sample_prices["date"].unique())
    config_path = write_feature_config(tmp_path, input_path, dates)
    previous_features, previous_correlations = build(
        api, sample_prices, feature_config, "feat_previous"
    )
    features_path = tmp_path / "asset_volatility_features.parquet"
    correlations_path = tmp_path / "asset_rolling_correlations.parquet"
    previous_features.to_parquet(features_path, index=False)
    previous_correlations.to_parquet(correlations_path, index=False)
    quarantine_path = tmp_path / "logs" / "quarantine.csv"
    quarantine_path.parent.mkdir(parents=True)
    quarantine_path.write_text(
        "run_id,source_batch_id,date,ticker,raw_value,reason,detected_at_utc\n"
        "previous_run,previous_batch,2024-01-02,SPY,,EXISTING,2026-11-14T00:00:00Z\n",
        encoding="utf-8",
    )
    previous_files = {
        path: path.read_bytes()
        for path in (features_path, correlations_path, quarantine_path)
    }
    build_tables = runner.build_feature_tables
    conflict_date = dates[62]

    def build_with_quarantine_and_conflict(*args, **kwargs):
        features, correlations = build_tables(*args, **kwargs)
        spy_index = features.index[
            features["ticker"].eq("SPY") & features["date"].eq(conflict_date)
        ][0]
        features.loc[spy_index, "rv_20d"] = np.nan
        features.loc[spy_index, "is_model_ready"] = False
        ief_index = features.index[
            features["ticker"].eq("IEF") & features["date"].eq(conflict_date)
        ][0]
        features.loc[ief_index, "rv_20d"] += 0.1
        return features, correlations

    monkeypatch.setattr(runner, "build_feature_tables", build_with_quarantine_and_conflict)
    monkeypatch.chdir(tmp_path)
    run_id = "publish_conflict_test"

    with pytest.raises(api.FeaturePipelineError, match="conflicting"):
        runner.run_feature_pipeline(config_path, run_id=run_id)

    assert all(path.read_bytes() == contents for path, contents in previous_files.items())
    assert not (tmp_path / "audit" / f"run_id={run_id}").exists()


def test_corrupted_core_feature_is_quarantined_and_ticker_is_not_published(
    sample_prices, tmp_path, monkeypatch
):
    api = feature_api()
    runner = import_module("src.features.run")
    input_path = tmp_path / "market_prices_daily.parquet"
    sample_prices.to_parquet(input_path, index=False)
    dates = sorted(sample_prices["date"].unique())
    config_path = write_feature_config(tmp_path, input_path, dates)
    build_tables = runner.build_feature_tables
    corrupted_date = dates[62]
    quarantine_path = tmp_path / "logs" / "quarantine.csv"
    quarantine_path.parent.mkdir(parents=True)
    quarantine_path.write_text(
        "run_id,source_batch_id,date,ticker,raw_value,reason,detected_at_utc\n"
        "ingestion_previous,batch_previous,2024-01-02,IEF,,EXISTING,2026-11-14T00:00:00Z\n",
        encoding="utf-8",
    )

    def build_with_corrupted_core(*args, **kwargs):
        features, correlations = build_tables(*args, **kwargs)
        spy_row = features.index[
            features["ticker"].eq("SPY") & features["date"].eq(corrupted_date)
        ][0]
        features.loc[spy_row, "rv_20d"] = np.nan
        features.loc[spy_row, "is_model_ready"] = False
        warning_row = features.index[
            features["ticker"].eq("SPY") & features["date"].eq(dates[63])
        ][0]
        features.loc[warning_row, "ret_1d_t"] = 0.16
        return features, correlations

    monkeypatch.setattr(runner, "build_feature_tables", build_with_corrupted_core)
    monkeypatch.chdir(tmp_path)

    report = runner.run_feature_pipeline(config_path, run_id="feat_quality_gate_test")

    written_features = pd.read_parquet(report["features_path"])
    quarantine = pd.read_csv(quarantine_path)
    manifest = yaml.safe_load(
        (tmp_path / "audit" / "run_id=feat_quality_gate_test" / "manifest.json")
        .read_text(encoding="utf-8")
    )
    transaction = json.loads(
        (tmp_path / "audit" / "run_id=feat_quality_gate_test" / "transaction.json")
        .read_text(encoding="utf-8")
    )
    quality_results = pd.read_parquet(
        tmp_path / "audit" / "run_id=feat_quality_gate_test" / "quality_results.parquet"
    )
    assert set(written_features["ticker"]) == {"IEF", "GLD"}
    assert "SPY" in report["failed_tickers"]
    assert quarantine.columns.tolist() == [
        "run_id",
        "source_batch_id",
        "date",
        "ticker",
        "raw_value",
        "reason",
        "detected_at_utc",
    ]
    assert len(quarantine) == 2
    previous = quarantine.loc[quarantine["run_id"] == "ingestion_previous"].iloc[0]
    feature_finding = quarantine.loc[
        quarantine["run_id"] == "feat_quality_gate_test"
    ].iloc[0]
    assert previous["reason"] == "EXISTING"
    assert feature_finding["ticker"] == "SPY"
    assert feature_finding["date"] == corrupted_date.isoformat()
    assert feature_finding["reason"] == "CORRUPTED_FEATURE_NULL"
    assert manifest["quality"]["failed_tickers"] == ["SPY"]
    assert manifest["quality"]["quarantine_records"] == 1
    assert transaction["status"] == "COMMITTED"
    assert set(quality_results["finding_type"]) == {"QUARANTINE", "WARNING"}
    runner.reconcile_feature_quarantine(report["quality_results_path"], quarantine_path)
    assert len(pd.read_csv(quarantine_path)) == 2
    assert manifest["quality"]["warnings"] == [
        {
            "date": dates[63].isoformat(),
            "ticker": "SPY",
            "feature": "ret_1d_t",
            "value": 0.16,
            "lower_bound": -0.15,
            "upper_bound": 0.15,
        }
    ]


def test_pending_quarantine_is_recovered_on_next_run_without_duplicates(
    sample_prices, tmp_path, monkeypatch
):
    api = feature_api()
    runner = import_module("src.features.run")
    input_path = tmp_path / "market_prices_daily.parquet"
    sample_prices.to_parquet(input_path, index=False)
    dates = sorted(sample_prices["date"].unique())
    config_path = write_feature_config(tmp_path, input_path, dates)
    build_tables = runner.build_feature_tables
    corrupted_date = dates[62]

    def build_with_corrupted_core(*args, **kwargs):
        features, correlations = build_tables(*args, **kwargs)
        spy_row = features.index[
            features["ticker"].eq("SPY") & features["date"].eq(corrupted_date)
        ][0]
        features.loc[spy_row, "rv_20d"] = np.nan
        features.loc[spy_row, "is_model_ready"] = False
        return features, correlations

    monkeypatch.setattr(runner, "build_feature_tables", build_with_corrupted_core)
    monkeypatch.chdir(tmp_path)
    reconcile = runner.reconcile_feature_quarantine

    def interrupt_after_quarantine_write(*args, **kwargs):
        reconcile(*args, **kwargs)
        raise OSError("simulated interruption after quarantine write")

    monkeypatch.setattr(
        runner, "reconcile_feature_quarantine", interrupt_after_quarantine_write
    )
    with pytest.raises(OSError, match="simulated interruption after quarantine write"):
        runner.run_feature_pipeline(config_path, run_id="pending_quarantine")

    run_dir = tmp_path / "audit" / "run_id=pending_quarantine"
    state_path = run_dir / "transaction.json"
    quality_path = run_dir / "quality_results.parquet"
    assert quality_path.is_file()
    assert json.loads(state_path.read_text(encoding="utf-8"))["status"] == (
        "OUTPUTS_PUBLISHED"
    )
    quarantine_before_recovery = pd.read_csv(tmp_path / "logs" / "quarantine.csv")
    assert len(quarantine_before_recovery) == 1

    monkeypatch.setattr(runner, "reconcile_feature_quarantine", reconcile)
    runner.run_feature_pipeline(config_path, run_id="recovery_followup")

    state = json.loads(state_path.read_text(encoding="utf-8"))
    quality = pd.read_parquet(quality_path)
    quarantine = pd.read_csv(tmp_path / "logs" / "quarantine.csv")
    assert state["status"] == "COMMITTED"
    assert set(quality["finding_type"]) == {"QUARANTINE"}
    assert len(quarantine.loc[quarantine["run_id"] == "pending_quarantine"]) == 1
    assert len(quarantine.loc[quarantine["run_id"] == "recovery_followup"]) == 1


def test_pending_transaction_rejects_corrupted_quality_evidence(
    sample_prices, tmp_path, monkeypatch
):
    runner = import_module("src.features.run")
    input_path = tmp_path / "market_prices_daily.parquet"
    sample_prices.to_parquet(input_path, index=False)
    dates = sorted(sample_prices["date"].unique())
    config_path = write_feature_config(tmp_path, input_path, dates)
    monkeypatch.chdir(tmp_path)
    runner.run_feature_pipeline(config_path, run_id="pending_bad_evidence")

    run_dir = tmp_path / "audit" / "run_id=pending_bad_evidence"
    state_path = run_dir / "transaction.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["status"] = "OUTPUTS_PUBLISHED"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    (run_dir / "quality_results.parquet").write_bytes(b"corrupted evidence")

    with pytest.raises(runner.FeaturePipelineError, match="quality result checksum mismatch"):
        runner.run_feature_pipeline(config_path, run_id="must_not_publish")

    assert not (tmp_path / "audit" / "run_id=must_not_publish").exists()
    assert json.loads(state_path.read_text(encoding="utf-8"))["status"] == (
        "OUTPUTS_PUBLISHED"
    )

