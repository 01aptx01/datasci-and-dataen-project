from importlib import import_module
from importlib.util import find_spec
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd
import pytest
import yaml


def feature_api():
    assert find_spec("src.features.pipeline") is not None, (
        "Expected src.features.pipeline to implement the feature contract"
    )
    return import_module("src.features.pipeline")


def make_prices(periods=65, start_date_index=60, mode="varied"):
    dates = pd.bdate_range("2024-01-02", periods=periods).date
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
        start_date=dates[60],
        expected_trading_days=dates,
    )


def build(api, prices, config, run_id="feat_run_test"):
    return api.build_feature_tables(
        prices,
        config,
        run_id=run_id,
        feature_as_of_utc="2026-11-13T00:00:00Z",
    )


def test_feature_pipeline_module_is_available():
    assert find_spec("src.features.pipeline") is not None


def test_example_config_loads():
    settings = import_module("src.features.run").load_config("config/features.yaml")
    assert settings["feature_config"].start_date.isoformat() == "2021-09-27"
    assert settings["feature_config"].end_date.isoformat() == "2026-09-25"
    assert settings["feature_config"].warmup_trading_days == 61
    assert settings["input_path"].as_posix() == "data/curated/market_prices_daily.parquet"


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
    row = features.query("ticker == 'SPY'").sort_values("date").iloc[60]
    spy_features = features.query("ticker == 'SPY'").sort_values("date").reset_index(drop=True)
    expected_rv60 = np.sqrt(252 / 60 * np.square(source["log_return"].iloc[1:61]).sum())
    assert row["ret_1d_t"] == pytest.approx(source["log_return"].iloc[60])
    assert row["ret_lag_1d"] == pytest.approx(source["log_return"].iloc[59])
    assert row["ret_lag_2d"] == pytest.approx(source["log_return"].iloc[58])
    assert row["ret_trailing_5d"] == pytest.approx(
        source["adjusted_close"].iloc[60] / source["adjusted_close"].iloc[55] - 1
    )
    assert row["ret_trailing_20d"] == pytest.approx(
        source["adjusted_close"].iloc[60] / source["adjusted_close"].iloc[40] - 1
    )
    expected_rv5 = np.sqrt(252 / 5 * np.square(source["log_return"].iloc[56:61]).sum())
    expected_rv20 = np.sqrt(252 / 20 * np.square(source["log_return"].iloc[41:61]).sum())
    expected_bb_width = (
        4
        * source["adjusted_close"].iloc[41:61].std(ddof=0)
        / source["adjusted_close"].iloc[41:61].mean()
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


def test_features_do_not_change_when_future_rows_are_added(sample_prices, feature_config):
    api = feature_api()
    ticker = "IEF"
    t = sorted(sample_prices["date"].unique())[53]
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
    sample_prices, feature_config
):
    api = feature_api()
    storage = import_module("src.features.storage")
    features, correlations = build(api, sample_prices, feature_config, "feat_first")
    tmp_path = Path.cwd() / f"storage-test-{uuid4().hex}"
    tmp_path.mkdir()
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


def test_configured_pipeline_reads_parquet_and_writes_lineage_manifest(sample_prices):
    api = feature_api()
    runner = import_module("src.features.run")
    root = Path.cwd() / f"cli-test-{uuid4().hex}"
    root.mkdir()
    input_path = root / "market_prices_daily.parquet"
    sample_prices.to_parquet(input_path, index=False)
    dates = sorted(sample_prices["date"].unique())
    config_path = root / "features.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "feature": {
                    "start_date": dates[60].isoformat(),
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

    report = runner.run_feature_pipeline(config_path, run_id="feat_cli_test")
    manifest_path = root / "audit" / "run_id=feat_cli_test" / "manifest.json"
    assert report["feature_rows"] == len(sample_prices)
    assert report["correlation_rows"] == len(dates)
    assert Path(report["features_path"]).is_file()
    assert Path(report["correlations_path"]).is_file()
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    assert manifest["input"]["sha256"]
    assert manifest["input"]["sources_by_ticker"]["SPY"]["source_batch_ids"]
    snapshot = manifest["input"]["source_snapshots"][0]
    assert snapshot["source_batch_id"].startswith("batch_")
    assert snapshot["raw_file_path"].startswith("data/raw/")
    assert snapshot["snapshot_manifest_path"].endswith("/manifest.json")
    assert manifest["outputs"]["asset_volatility_features"]["columns"] == api.FEATURE_COLUMNS

