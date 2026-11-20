from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pandas_market_calendars as market_calendars
import pytest

from src.features.pipeline import CORE_FEATURE_COLUMNS, FEATURE_COLUMNS
from src.ml_dataset.dataset import (
    DatasetConfig,
    DatasetPreparationError,
    load_validated_inputs,
    prepare_ml_dataset,
)
from src.targets.pipeline import LABEL_COLUMNS


SESSIONS = tuple(
    stamp.date()
    for stamp in market_calendars.get_calendar("XNYS")
    .schedule(start_date="2021-06-01", end_date="2026-12-31")
    .index
)
SESSION_INDEX = {day: index for index, day in enumerate(SESSIONS)}


def _target_dates(anchor: date) -> tuple[date, date]:
    position = SESSION_INDEX[anchor]
    return SESSIONS[position + 1], SESSIONS[position + 5]


def _feature_rows(
    anchors: list[date],
    *,
    tickers: tuple[str, ...] = ("SPY",),
    rv_values: dict[str, list[float]] | None = None,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for ticker in tickers:
        for index, anchor in enumerate(anchors):
            values = {column: 0.05 + index / 100_000 for column in CORE_FEATURE_COLUMNS}
            values["rv_5d"] = (
                rv_values[ticker][index]
                if rv_values and ticker in rv_values
                else 0.10 + index / 100_000
            )
            rows.append(
                {
                    "date": anchor,
                    "ticker": ticker,
                    **values,
                    "rsi_14d": 50.0,
                    "bb_width_20d": 0.1,
                    "is_model_ready": True,
                    "is_warmup_buffer": False,
                    "feature_set_version": "2.0.0",
                    "run_id": "feature_test_run",
                    "source_batch_id": "source_test_batch",
                    "feature_as_of_utc": pd.Timestamp("2026-11-20T00:00:00Z"),
                }
            )
    return pd.DataFrame(rows, columns=FEATURE_COLUMNS)


def _label_rows(
    anchors: list[date],
    *,
    ticker: str = "SPY",
    y_values: list[float] | None = None,
    mature: list[bool] | None = None,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for index, anchor in enumerate(anchors):
        start, end = _target_dates(anchor)
        is_mature = mature[index] if mature else True
        rows.append(
            {
                "date": anchor,
                "ticker": ticker,
                "target_start_date": start,
                "target_end_date": end,
                "target_obs_count": 5 if is_mature else 2,
                "target_realized_vol_5d": (
                    float(y_values[index]) if y_values is not None and is_mature else (0.2 if is_mature else np.nan)
                ),
                "is_label_mature": is_mature,
                "target_version": "2.0.0",
                "run_id": "target_test_run",
                "source_batch_id": "source_test_batch",
                "record_created_at_utc": pd.Timestamp("2026-11-20T00:00:00Z"),
                "label_matured_at_utc": (
                    pd.Timestamp("2026-11-20T00:00:00Z") if is_mature else pd.NaT
                ),
            }
        )
    return pd.DataFrame(rows, columns=LABEL_COLUMNS)


def _session_range(start: str, end: str) -> list[date]:
    return [stamp.date() for stamp in market_calendars.get_calendar("XNYS").schedule(
        start_date=start, end_date=end
    ).index]


def test_core_features_are_fixed_order_and_config_has_locked_splits() -> None:
    config = DatasetConfig()

    assert tuple(config.core_features) == CORE_FEATURE_COLUMNS
    assert config.train_start_date == date(2021, 9, 27)
    assert config.train_end_date == date(2024, 9, 30)
    assert config.validation_start_date == date(2024, 10, 1)
    assert config.test_end_date == date(2026, 9, 25)
    assert config.data_cutoff == date(2026, 9, 25)
    assert DatasetConfig.from_yaml().as_dict() == config.as_dict()


def test_pending_or_missing_label_does_not_remove_prediction_row() -> None:
    anchors = _session_range("2024-09-20", "2024-09-24")[:3]
    features = _feature_rows(anchors)
    labels = _label_rows(anchors[:2], mature=[False, True])

    prepared = prepare_ml_dataset(features, labels)

    assert prepared.prediction.X.columns.tolist() == list(CORE_FEATURE_COLUMNS)
    assert prepared.prediction.metadata["date"].tolist() == anchors
    assert prepared.supervised.metadata["date"].tolist() == [anchors[1]]
    assert "target_realized_vol_5d" not in prepared.prediction.X.columns
    assert prepared.report.summary["source_quality_passed"] is None


def test_not_ready_and_warmup_features_are_excluded_with_reasons() -> None:
    anchors = _session_range("2024-09-20", "2024-09-24")[:3]
    features = _feature_rows(anchors)
    features.loc[0, "rv_60d"] = np.nan
    features.loc[0, "is_model_ready"] = False
    features.loc[1, "is_warmup_buffer"] = True

    prepared = prepare_ml_dataset(features, _label_rows(anchors))

    assert prepared.prediction.metadata["date"].tolist() == [anchors[2]]
    assert "feature_not_ready" in prepared.audit.loc[0, "exclusion_reasons"]
    assert "warmup_buffer" in prepared.audit.loc[1, "exclusion_reasons"]


def test_fixed_purge_does_not_block_later_online_update() -> None:
    # Sep 24's five-session target ends on the Validation boundary, so Train purges it.
    boundary_anchor = date(2024, 9, 24)
    features = _feature_rows([boundary_anchor])
    labels = _label_rows([boundary_anchor])

    prepared = prepare_ml_dataset(features, labels, replay_date=date(2024, 10, 1))

    row = prepared.audit.iloc[0]
    assert row["target_end_date"] == date(2024, 10, 1)
    assert bool(row["fixed_purged"])
    assert bool(row["online_update_eligible"])
    assert prepared.supervised.X.empty


def test_purge_uses_greater_than_or_equal_boundary() -> None:
    boundary_anchor = date(2024, 9, 24)
    before_boundary_anchor = date(2024, 9, 23)
    anchors = [before_boundary_anchor, boundary_anchor]
    prepared = prepare_ml_dataset(_feature_rows(anchors), _label_rows(anchors))

    assert prepared.audit["fixed_purged"].tolist() == [False, True]
    assert prepared.supervised.metadata["date"].tolist() == [before_boundary_anchor]


def test_replay_cutoff_blocks_backfilled_future_label_and_future_anchor() -> None:
    anchors = [date(2024, 9, 24), date(2024, 10, 2)]
    prepared = prepare_ml_dataset(
        _feature_rows(anchors), _label_rows(anchors), replay_date=date(2024, 9, 30)
    )

    by_date = prepared.audit.set_index("date")
    assert not bool(by_date.loc[anchors[0], "online_update_eligible"])
    assert not bool(by_date.loc[anchors[1], "prediction_eligible"])
    assert prepared.prediction.metadata["date"].tolist() == [anchors[0]]


def test_updated_label_ledger_prevents_duplicate_online_update_candidate() -> None:
    anchor = date(2024, 9, 23)
    prepared = prepare_ml_dataset(
        _feature_rows([anchor]),
        _label_rows([anchor]),
        replay_date=date(2024, 9, 30),
        updated_label_ledger={(anchor, "SPY")},
    )

    row = prepared.audit.iloc[0]
    assert not bool(row["online_update_eligible"])
    assert "already_updated" in row["exclusion_reasons"]


def test_duplicate_feature_or_label_primary_key_hard_fails() -> None:
    anchor = date(2024, 9, 23)
    feature = _feature_rows([anchor])
    labels = _label_rows([anchor])
    with pytest.raises(DatasetPreparationError, match="duplicate.*features"):
        prepare_ml_dataset(pd.concat([feature, feature]), labels)
    with pytest.raises(DatasetPreparationError, match="duplicate.*labels"):
        prepare_ml_dataset(feature, pd.concat([labels, labels]))


def test_bad_feature_schema_fails_with_dataset_error() -> None:
    anchor = date(2024, 9, 23)
    with pytest.raises(DatasetPreparationError, match="schema mismatch"):
        prepare_ml_dataset(_feature_rows([anchor]).drop(columns=["rv_60d"]), _label_rows([anchor]))


def test_xnys_target_window_mismatch_hard_fails() -> None:
    anchor = date(2024, 9, 23)
    labels = _label_rows([anchor])
    labels.loc[0, "target_end_date"] = date(2024, 10, 1)

    with pytest.raises(DatasetPreparationError, match="XNYS target window"):
        prepare_ml_dataset(_feature_rows([anchor]), labels)


def test_label_lineage_mismatch_hard_fails() -> None:
    anchor = date(2024, 9, 23)
    labels = _label_rows([anchor])
    labels.loc[0, "source_batch_id"] = "different_snapshot"

    with pytest.raises(DatasetPreparationError, match="source_batch_id"):
        prepare_ml_dataset(_feature_rows([anchor]), labels)


def test_report_counts_exclusions_by_ticker_split_and_reason() -> None:
    anchors = [date(2024, 9, 23), date(2024, 9, 24)]
    prepared = prepare_ml_dataset(_feature_rows(anchors), _label_rows(anchors))

    counts = prepared.report.counts_by_ticker_split_reason
    assert {"ticker", "split", "reason", "count"}.issubset(counts.columns)
    purge = counts.loc[counts["reason"] == "fixed_split_purge"]
    assert purge["count"].sum() == 1


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_loader_inputs(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    anchor = date(2024, 9, 23)
    feature_path = tmp_path / "features.parquet"
    label_path = tmp_path / "labels.parquet"
    _feature_rows([anchor]).to_parquet(feature_path, index=False)
    _label_rows([anchor]).to_parquet(label_path, index=False)
    common_source_hash = "same-source-snapshot-hash"
    source_snapshots = [{"source_batch_id": "source_test_batch"}]
    feature_manifest = {
        "run_id": "feature_test_run",
        "pipeline": "feature_engineering",
        "feature_set_version": "2.0.0",
        "input": {"table": "market_prices_daily", "sha256": common_source_hash, "source_snapshots": source_snapshots},
        "quality": {"failed_tickers": [], "finding_count": 0, "warnings": []},
        "outputs": {"asset_volatility_features": {"path": str(feature_path)}},
    }
    target_manifest = {
        "run_id": "target_test_run",
        "pipeline": "target_label_pipeline",
        "target_version": "2.0.0",
        "input": {"table": "market_prices_daily", "sha256": common_source_hash, "source_snapshots": source_snapshots},
        "quality": {"finding_count": 0, "findings": []},
        "output": {"table": "asset_volatility_labels", "path": str(label_path)},
    }
    feature_manifest_path = tmp_path / "feature_manifest.json"
    target_manifest_path = tmp_path / "target_manifest.json"
    feature_manifest_path.write_text(json.dumps(feature_manifest), encoding="utf-8")
    target_manifest_path.write_text(json.dumps(target_manifest), encoding="utf-8")
    feature_transaction_path = tmp_path / "feature_transaction.json"
    target_transaction_path = tmp_path / "target_transaction.json"
    feature_transaction_path.write_text(
        json.dumps(
            {
                "status": "COMMITTED",
                "entries": [
                    {"target_path": str(feature_path), "sha256": _sha256(feature_path)}
                ],
            }
        ),
        encoding="utf-8",
    )
    target_transaction_path.write_text(
        json.dumps(
            {
                "status": "COMMITTED",
                "entries": [{"target_path": str(label_path), "sha256": _sha256(label_path)}],
            }
        ),
        encoding="utf-8",
    )
    return feature_manifest_path, target_manifest_path, feature_transaction_path, target_transaction_path


def test_loader_checks_committed_transaction_hashes_and_common_source(tmp_path: Path) -> None:
    feature_manifest, target_manifest, feature_tx, target_tx = _write_loader_inputs(tmp_path)
    loaded = load_validated_inputs(
        tmp_path / "features.parquet",
        tmp_path / "labels.parquet",
        feature_manifest,
        target_manifest,
        feature_tx,
        target_tx,
    )
    assert loaded.source_quality_passed
    assert loaded.lineage["source_input_sha256"] == "same-source-snapshot-hash"

    tx = json.loads(target_tx.read_text(encoding="utf-8"))
    tx["entries"][0]["sha256"] = "bad-checksum"
    target_tx.write_text(json.dumps(tx), encoding="utf-8")
    with pytest.raises(DatasetPreparationError, match="transaction checksum"):
        load_validated_inputs(
            tmp_path / "features.parquet",
            tmp_path / "labels.parquet",
            feature_manifest,
            target_manifest,
            feature_tx,
            target_tx,
        )
