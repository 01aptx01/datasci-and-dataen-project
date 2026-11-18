from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.targets.pipeline import LABEL_COLUMNS, TargetPipelineError
from src.targets.storage import (
    merge_target_labels,
    publish_target_labels,
    recover_target_transactions,
)


def _row(
    *,
    mature: bool,
    run_id: str,
    created_at: str,
    matured_at: str | None,
    target_value: float = 0.2,
    target_version: str = "2.0.0",
) -> dict:
    return {
        "date": date(2026, 1, 12),
        "ticker": "SPY",
        "target_start_date": date(2026, 1, 13),
        "target_end_date": date(2026, 1, 20),
        "target_obs_count": 5 if mature else 2,
        "target_realized_vol_5d": target_value if mature else np.nan,
        "is_label_mature": mature,
        "target_version": target_version,
        "run_id": run_id,
        "source_batch_id": "batch_spy",
        "record_created_at_utc": pd.Timestamp(created_at),
        "label_matured_at_utc": pd.Timestamp(matured_at) if matured_at else pd.NaT,
    }


def _table(row: dict) -> pd.DataFrame:
    return pd.DataFrame([row], columns=LABEL_COLUMNS)


def test_pending_to_mature_preserves_original_created_timestamp() -> None:
    created_at = "2026-01-26T15:00:00Z"
    pending = _table(
        _row(
            mature=False,
            run_id="target_run_1",
            created_at=created_at,
            matured_at=None,
        )
    )
    mature = _table(
        _row(
            mature=True,
            run_id="target_run_2",
            created_at="2026-01-27T15:00:00Z",
            matured_at="2026-01-27T15:00:00Z",
        )
    )

    combined, counts = merge_target_labels(pending, mature)

    row = combined.iloc[0]
    assert counts == {"inserted": 0, "unchanged": 0, "updated": 1}
    assert row["is_label_mature"]
    assert row["record_created_at_utc"] == pd.Timestamp(created_at)
    assert row["label_matured_at_utc"] == pd.Timestamp("2026-01-27T15:00:00Z")


def test_idempotent_mature_upsert_preserves_first_maturity_timestamp() -> None:
    first = _table(
        _row(
            mature=True,
            run_id="target_run_1",
            created_at="2026-01-26T15:00:00Z",
            matured_at="2026-01-26T15:00:00Z",
        )
    )
    rerun = _table(
        _row(
            mature=True,
            run_id="target_run_2",
            created_at="2026-01-27T15:00:00Z",
            matured_at="2026-01-27T15:00:00Z",
        )
    )

    combined, counts = merge_target_labels(first, rerun)

    assert counts == {"inserted": 0, "unchanged": 1, "updated": 0}
    assert combined.loc[0, "record_created_at_utc"] == pd.Timestamp("2026-01-26T15:00:00Z")
    assert combined.loc[0, "label_matured_at_utc"] == pd.Timestamp("2026-01-26T15:00:00Z")


def test_mature_business_change_requires_explicit_overwrite() -> None:
    old = _table(
        _row(
            mature=True,
            run_id="target_run_1",
            created_at="2026-01-26T15:00:00Z",
            matured_at="2026-01-26T15:00:00Z",
        )
    )
    changed = _table(
        _row(
            mature=True,
            run_id="target_run_2",
            created_at="2026-01-27T15:00:00Z",
            matured_at="2026-01-27T15:00:00Z",
            target_value=0.3,
        )
    )

    with pytest.raises(TargetPipelineError, match="conflicting business values"):
        merge_target_labels(old, changed)


def test_matured_timestamp_cannot_predate_record_creation() -> None:
    invalid = _table(
        _row(
            mature=True,
            run_id="target_run_invalid_time",
            created_at="2026-01-27T15:00:00Z",
            matured_at="2026-01-26T15:00:00Z",
        )
    )

    with pytest.raises(TargetPipelineError, match="cannot predate"):
        merge_target_labels(pd.DataFrame(columns=LABEL_COLUMNS), invalid)


def test_failed_manifest_replace_restores_previous_parquet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_path = tmp_path / "asset_volatility_labels.parquet"
    manifest_path = tmp_path / "manifest.json"
    run_dir = tmp_path / "run_id=target_run_2"
    original = _table(
        _row(
            mature=False,
            run_id="target_run_1",
            created_at="2026-01-26T15:00:00Z",
            matured_at=None,
        )
    )
    original.to_parquet(output_path, index=False)
    original_bytes = output_path.read_bytes()
    incoming = _table(
        _row(
            mature=True,
            run_id="target_run_2",
            created_at="2026-01-27T15:00:00Z",
            matured_at="2026-01-27T15:00:00Z",
        )
    )
    real_replace = __import__("os").replace

    def fail_manifest_replace(source, destination):
        if Path(destination) == manifest_path and str(source).endswith(".tmp"):
            raise OSError("simulated manifest publish failure")
        return real_replace(source, destination)

    monkeypatch.setattr("src.targets.storage.os.replace", fail_manifest_replace)

    with pytest.raises(OSError, match="simulated manifest publish failure"):
        publish_target_labels(
            incoming,
            output_path,
            manifest_path,
            {"run_id": "target_run_2"},
            run_dir=run_dir,
        )

    assert output_path.read_bytes() == original_bytes
    assert not manifest_path.exists()


def test_recovery_ignores_superseded_committed_output_checksums(tmp_path: Path) -> None:
    output_path = tmp_path / "asset_volatility_labels.parquet"
    manifest_dir = tmp_path / "audit"
    first = _table(
        _row(
            mature=False,
            run_id="target_run_1",
            created_at="2026-01-26T15:00:00Z",
            matured_at=None,
        )
    )
    second = _table(
        _row(
            mature=False,
            run_id="target_run_2",
            created_at="2026-01-27T15:00:00Z",
            matured_at=None,
        )
    )
    first_dir = manifest_dir / "run_id=target_run_1"
    second_dir = manifest_dir / "run_id=target_run_2"
    publish_target_labels(
        first,
        output_path,
        first_dir / "manifest.json",
        {"run_id": "target_run_1"},
        run_dir=first_dir,
    )
    publish_target_labels(
        second,
        output_path,
        second_dir / "manifest.json",
        {"run_id": "target_run_2"},
        run_dir=second_dir,
    )

    assert recover_target_transactions(manifest_dir) == []
