from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pandas_market_calendars as market_calendars
import pytest
import yaml

from src.targets.pipeline import LABEL_COLUMNS
from src.targets.run import run_target_pipeline


TICKERS = ("SPY", "IEF", "GLD")
START_DATE = date(2026, 1, 12)
END_DATE = date(2026, 1, 22)


def _sessions(start: str, end: str) -> tuple[date, ...]:
    schedule = market_calendars.get_calendar("XNYS").schedule(
        start_date=start,
        end_date=end,
    )
    return tuple(pd.Timestamp(value).date() for value in schedule.index)


def _synthetic_prices(sessions: tuple[date, ...]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    first_future_session = date(2026, 1, 23)
    for ticker_index, ticker in enumerate(TICKERS):
        close = 100.0 + ticker_index
        previous_day: date | None = None
        for session_index, day in enumerate(sessions):
            log_return = (
                np.nan
                if previous_day is None
                else (0.002 + ticker_index * 0.0003)
                * (-1.0 if session_index % 2 else 1.0)
                * (1.0 + session_index / 10.0)
            )
            if previous_day is not None:
                close *= float(np.exp(log_return))
            is_future = day >= first_future_session
            rows.append(
                {
                    "date": day,
                    "ticker": ticker,
                    "adjusted_close": close,
                    "log_return": log_return,
                    "run_id": "synthetic_future" if is_future else "synthetic_backfill",
                    "source_batch_id": (
                        "synthetic_future" if is_future else "synthetic_backfill"
                    ),
                }
            )
            previous_day = day
    return pd.DataFrame(rows)


def _write_raw_snapshot(cwd: Path, batch_id: str) -> None:
    raw_dir = cwd / "data" / "raw" / batch_id
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / "synthetic_prices.csv"
    raw_path.write_text(f"synthetic snapshot for {batch_id}\n", encoding="utf-8")
    raw_relative_path = raw_path.relative_to(cwd).as_posix()
    manifest = {
        "source_batch_id": batch_id,
        "raw_file_path": raw_relative_path,
        "sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
        "source": "synthetic",
        "client": "integration-test",
        "yfinance_version": "synthetic",
    }
    (raw_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_config(
    path: Path,
    *,
    input_path: Path,
    output_path: Path,
    manifest_dir: Path,
) -> None:
    config = {
        "target": {
            "start_date": START_DATE.isoformat(),
            "end_date": END_DATE.isoformat(),
            "target_version": "2.0.0",
        },
        "calendar": {"market": "XNYS"},
        "paths": {
            "input": str(input_path),
            "output": str(output_path),
            "manifest_dir": str(manifest_dir),
        },
        "publish": {"overwrite_conflicts": False},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")


def _read_output(path: Path) -> pd.DataFrame:
    output = pd.read_parquet(path).sort_values(["date", "ticker"]).reset_index(drop=True)
    assert list(output.columns) == LABEL_COLUMNS
    assert not output.duplicated(["date", "ticker"]).any()
    return output


def _timestamp_map(data: pd.DataFrame, column: str) -> dict[tuple[date, str], pd.Timestamp]:
    return {
        (row.date, row.ticker): getattr(row, column)
        for row in data.itertuples(index=False)
    }


def test_run_target_pipeline_backfill_pending_mature_and_idempotency(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    all_sessions = _sessions("2026-01-09", "2026-01-29")
    study_sessions = tuple(day for day in all_sessions if START_DATE <= day <= END_DATE)
    expected_anchors = set(study_sessions)
    future_sessions = tuple(day for day in all_sessions if day > END_DATE)
    assert len(future_sessions) == 5

    prices = _synthetic_prices(all_sessions)
    initial_prices = prices.loc[prices["date"] <= END_DATE].copy()
    input_path = tmp_path / "market_prices_daily.parquet"
    output_path = tmp_path / "asset_volatility_labels.parquet"
    manifest_dir = tmp_path / "audit" / "targets"
    config_path = tmp_path / "config" / "target.yaml"
    initial_prices.to_parquet(input_path, index=False)
    _write_config(
        config_path,
        input_path=input_path,
        output_path=output_path,
        manifest_dir=manifest_dir,
    )
    _write_raw_snapshot(tmp_path, "synthetic_backfill")
    _write_raw_snapshot(tmp_path, "synthetic_future")

    backfill_report = run_target_pipeline(config_path, run_id="integration_backfill")
    backfill = _read_output(output_path)
    assert backfill_report["rows_in_run"] == 24
    assert backfill_report["rows_after_publish"] == 24
    assert backfill_report["mature_rows_in_run"] == 9
    assert backfill_report["pending_rows_in_run"] == 15
    assert backfill_report["finding_count"] == 0
    assert set(backfill["date"]) == expected_anchors
    assert backfill["date"].min() == START_DATE
    assert backfill["date"].max() == END_DATE
    assert set(backfill["ticker"]) == set(TICKERS)
    assert backfill.groupby("target_obs_count").size().to_dict() == {
        0: 3,
        1: 3,
        2: 3,
        3: 3,
        4: 3,
        5: 9,
    }
    assert backfill.loc[~backfill["is_label_mature"], "target_realized_vol_5d"].isna().all()
    created_at_before_maturity = _timestamp_map(backfill, "record_created_at_utc")
    matured_at_before_future = {
        key: value
        for key, value in _timestamp_map(backfill, "label_matured_at_utc").items()
        if not pd.isna(value)
    }

    complete_prices = prices.copy()
    complete_prices.to_parquet(input_path, index=False)
    mature_report = run_target_pipeline(config_path, run_id="integration_future")
    mature = _read_output(output_path)
    assert mature_report["rows_in_run"] == 24
    assert mature_report["rows_after_publish"] == 24
    assert mature_report["mature_rows_in_run"] == 24
    assert mature_report["pending_rows_in_run"] == 0
    assert mature_report["finding_count"] == 0
    assert set(mature["date"]) == expected_anchors
    assert mature["date"].min() == START_DATE
    assert mature["date"].max() == END_DATE
    assert mature["is_label_mature"].all()
    assert mature["target_obs_count"].eq(5).all()
    assert mature["target_realized_vol_5d"].notna().all()

    source_returns = {
        (row.date, row.ticker): row.log_return
        for row in complete_prices.itertuples(index=False)
    }
    session_positions = {day: position for position, day in enumerate(all_sessions)}
    for row in mature.itertuples(index=False):
        anchor_position = session_positions[row.date]
        forward_sessions = all_sessions[anchor_position + 1 : anchor_position + 6]
        assert len(forward_sessions) == 5
        expected_target = float(
            np.sqrt(
                (252.0 / 5.0)
                * sum(source_returns[(day, row.ticker)] ** 2 for day in forward_sessions)
            )
        )
        assert row.target_start_date == forward_sessions[0]
        assert row.target_end_date == forward_sessions[-1]
        assert row.target_realized_vol_5d == pytest.approx(expected_target)

    created_at_after_maturity = _timestamp_map(mature, "record_created_at_utc")
    assert created_at_after_maturity == created_at_before_maturity
    matured_at_after_maturity = _timestamp_map(mature, "label_matured_at_utc")
    for key, original_timestamp in matured_at_before_future.items():
        assert matured_at_after_maturity[key] == original_timestamp

    backfill_pending_keys = set(created_at_before_maturity) - set(matured_at_before_future)
    assert backfill_pending_keys
    mature_manifest = json.loads(Path(mature_report["manifest_path"]).read_text(encoding="utf-8"))
    future_maturity_timestamp = pd.Timestamp(mature_manifest["created_at_utc"])
    for key in backfill_pending_keys:
        assert matured_at_after_maturity[key] == future_maturity_timestamp

    idempotent_report = run_target_pipeline(config_path, run_id="integration_idempotent")
    idempotent = _read_output(output_path)
    assert idempotent_report["rows_after_publish"] == 24
    assert idempotent_report["publish_counts"] == {
        "inserted": 0,
        "unchanged": 24,
        "updated": 0,
    }
    assert _timestamp_map(idempotent, "record_created_at_utc") == created_at_after_maturity
    assert _timestamp_map(idempotent, "label_matured_at_utc") == matured_at_after_maturity
    assert set(idempotent["date"]) == expected_anchors
