from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from datetime import date, datetime, timezone
from numbers import Integral, Real
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.targets.pipeline import LABEL_COLUMNS, SUPPORTED_TICKERS, TargetPipelineError


LABEL_KEYS = ("date", "ticker")
LINEAGE_COLUMNS = {
    "run_id",
    "source_batch_id",
    "record_created_at_utc",
    "label_matured_at_utc",
}
def _is_missing(value: Any) -> bool:
    result = pd.isna(value)
    return bool(result) if isinstance(result, (bool, np.bool_)) else False


def _as_market_date(value: Any, column: str) -> date | None:
    if _is_missing(value):
        return None
    if isinstance(value, (bool, int, float, np.number)):
        raise TargetPipelineError(f"asset_volatility_labels {column} contains an invalid date")
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError) as error:
        raise TargetPipelineError(f"asset_volatility_labels {column} contains an invalid date") from error
    if pd.isna(timestamp):
        return None
    return timestamp.date()


def _normalize_utc_column(data: pd.DataFrame, column: str, nullable: bool) -> None:
    converted = []
    for value in data[column]:
        if _is_missing(value):
            if not nullable:
                raise TargetPipelineError(f"asset_volatility_labels {column} cannot be NULL")
            converted.append(pd.NaT)
            continue
        try:
            timestamp = pd.Timestamp(value)
        except (TypeError, ValueError) as error:
            raise TargetPipelineError(
                f"asset_volatility_labels {column} contains an invalid timestamp"
            ) from error
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise TargetPipelineError(
                f"asset_volatility_labels {column} must be timezone-aware UTC"
            )
        converted.append(timestamp.tz_convert("UTC"))
    data[column] = pd.to_datetime(converted, utc=True)


def validate_target_table(table: pd.DataFrame, table_name: str = "asset_volatility_labels") -> pd.DataFrame:
    if not isinstance(table, pd.DataFrame):
        raise TargetPipelineError(f"{table_name} must be a DataFrame")
    if list(table.columns) != LABEL_COLUMNS:
        raise TargetPipelineError(
            f"{table_name} schema mismatch; expected the 12 Data Dictionary columns in order"
        )
    if table.empty:
        raise TargetPipelineError(f"{table_name} cannot be empty")

    data = table.copy()
    for column in ("date", "target_start_date", "target_end_date"):
        data[column] = data[column].map(lambda value: _as_market_date(value, column))
    if data["date"].isna().any():
        raise TargetPipelineError(f"{table_name} date cannot be NULL")
    if data.duplicated(list(LABEL_KEYS)).any():
        raise TargetPipelineError(f"{table_name} has duplicate (date, ticker) keys")
    if data.loc[:, list(LABEL_KEYS)].isna().any().any():
        raise TargetPipelineError(f"{table_name} primary keys cannot be NULL")
    if not data["ticker"].map(
        lambda value: isinstance(value, str) and value in SUPPORTED_TICKERS
    ).all():
        raise TargetPipelineError(f"{table_name} ticker must be SPY, IEF, or GLD")
    has_start = data["target_start_date"].notna()
    has_end = data["target_end_date"].notna()
    if not has_start.eq(has_end).all():
        raise TargetPipelineError(
            f"{table_name} target_start_date and target_end_date must both be NULL or present"
        )
    if (
        data.loc[has_start, "target_start_date"]
        >= data.loc[has_end, "target_end_date"]
    ).any():
        raise TargetPipelineError(f"{table_name} target window start must precede its end")

    raw_counts = data["target_obs_count"]
    if not raw_counts.map(
        lambda value: isinstance(value, (Integral, np.integer))
        and not isinstance(value, (bool, np.bool_))
    ).all():
        raise TargetPipelineError(f"{table_name} target_obs_count must be an integer from 0 to 5")
    counts = pd.to_numeric(raw_counts, errors="coerce")
    if counts.isna().any() or not np.equal(counts, np.floor(counts)).all():
        raise TargetPipelineError(f"{table_name} target_obs_count must be an integer from 0 to 5")
    if ((counts < 0) | (counts > 5)).any():
        raise TargetPipelineError(f"{table_name} target_obs_count must be an integer from 0 to 5")
    data["target_obs_count"] = counts.astype("int64")

    raw_values = data["target_realized_vol_5d"]
    if not raw_values.dropna().map(
        lambda value: isinstance(value, Real)
        and not isinstance(value, (bool, np.bool_))
    ).all():
        raise TargetPipelineError(f"{table_name} target_realized_vol_5d must be numeric or NULL")
    values = pd.to_numeric(raw_values, errors="coerce")
    data["target_realized_vol_5d"] = values.astype("float64")
    maturity_flags = data["is_label_mature"]
    if not maturity_flags.map(lambda value: isinstance(value, (bool, np.bool_))).all():
        raise TargetPipelineError(f"{table_name} is_label_mature must be boolean")
    data["is_label_mature"] = maturity_flags.astype(bool)
    mature = data["is_label_mature"]
    mature_values = data.loc[mature, "target_realized_vol_5d"].to_numpy(dtype=float)
    if (
        (data.loc[mature, "target_obs_count"] != 5).any()
        or not np.isfinite(mature_values).all()
        or (mature_values < 0).any()
    ):
        raise TargetPipelineError(
            f"{table_name} mature labels require five finite non-negative returns"
        )
    if (
        (data.loc[~mature, "target_obs_count"] > 4).any()
        or data.loc[~mature, "target_realized_vol_5d"].notna().any()
    ):
        raise TargetPipelineError(f"{table_name} pending labels require NULL target and 0..4 observations")

    for column in ("target_version", "run_id", "source_batch_id"):
        limit = 16 if column == "target_version" else 64
        values = data[column]
        if (
            values.isna().any()
            or not values.map(lambda value: isinstance(value, str)).all()
            or values.str.strip().eq("").any()
            or values.str.len().gt(limit).any()
        ):
            raise TargetPipelineError(
                f"{table_name} {column} must be a non-empty string up to {limit} characters"
            )
    versions = data["target_version"].str.split(".")
    if not versions.map(
        lambda parts: len(parts) == 3 and all(part.isdigit() for part in parts)
    ).all():
        raise TargetPipelineError(f"{table_name} target_version must be semantic version")

    _normalize_utc_column(data, "record_created_at_utc", nullable=False)
    _normalize_utc_column(data, "label_matured_at_utc", nullable=True)
    if data.loc[mature, "label_matured_at_utc"].isna().any():
        raise TargetPipelineError(f"{table_name} mature labels require label_matured_at_utc")
    if data.loc[~mature, "label_matured_at_utc"].notna().any():
        raise TargetPipelineError(f"{table_name} pending labels require NULL label_matured_at_utc")
    if (data.loc[mature, "label_matured_at_utc"] < data.loc[mature, "record_created_at_utc"]).any():
        raise TargetPipelineError(
            f"{table_name} label_matured_at_utc cannot predate record_created_at_utc"
        )
    if data.loc[mature, ["target_start_date", "target_end_date"]].isna().any().any():
        raise TargetPipelineError(f"{table_name} mature labels require a known target window")
    return data.loc[:, LABEL_COLUMNS].sort_values(list(LABEL_KEYS)).reset_index(drop=True)


def _same_value(left: Any, right: Any) -> bool:
    if _is_missing(left) or _is_missing(right):
        return _is_missing(left) and _is_missing(right)
    if (
        isinstance(left, Real)
        and isinstance(right, Real)
        and not isinstance(left, (bool, np.bool_))
        and not isinstance(right, (bool, np.bool_))
    ):
        return bool(np.isclose(float(left), float(right), rtol=1e-12, atol=1e-12))
    return left == right


def _same_business_row(old: pd.Series, new: pd.Series) -> bool:
    return all(
        _same_value(old[column], new[column])
        for column in new.index
        if column not in LINEAGE_COLUMNS
    )


def _is_expected_progress(old: pd.Series, new: pd.Series) -> bool:
    stable_columns = ("date", "ticker", "target_start_date", "target_end_date", "target_version")
    if not all(_same_value(old[column], new[column]) for column in stable_columns):
        return False
    if old["is_label_mature"]:
        return bool(new["is_label_mature"]) and _same_value(
            old["target_realized_vol_5d"], new["target_realized_vol_5d"]
        )
    if new["target_obs_count"] < old["target_obs_count"]:
        return False
    return bool(new["is_label_mature"]) or not bool(old["is_label_mature"])


def merge_target_labels(
    old: pd.DataFrame,
    incoming: pd.DataFrame,
    *,
    overwrite_conflicts: bool = False,
    overwrite_reason: str | None = None,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Idempotently upsert labels while preserving original creation/maturity times."""
    new_data = validate_target_table(incoming)
    if old.empty:
        return new_data.copy(), {"inserted": len(new_data), "unchanged": 0, "updated": 0}
    old_data = validate_target_table(old)
    if overwrite_conflicts and (not isinstance(overwrite_reason, str) or not overwrite_reason.strip()):
        raise TargetPipelineError("overwrite_reason is required when replacing historical labels")

    rows = {
        (row["date"], row["ticker"]): row.copy()
        for _, row in old_data.iterrows()
    }
    counts = {"inserted": 0, "unchanged": 0, "updated": 0}
    for _, incoming_row in new_data.iterrows():
        key = (incoming_row["date"], incoming_row["ticker"])
        old_row = rows.get(key)
        if old_row is None:
            counts["inserted"] += 1
            rows[key] = incoming_row.copy()
            continue

        same_business = _same_business_row(old_row, incoming_row)
        expected_progress = _is_expected_progress(old_row, incoming_row)
        if not same_business and not expected_progress and not overwrite_conflicts:
            raise TargetPipelineError(
                f"asset_volatility_labels has conflicting business values for key {key}; "
                "review the source and provide an explicit overwrite reason to replace them"
            )
        merged = incoming_row.copy()
        merged["record_created_at_utc"] = old_row["record_created_at_utc"]
        if same_business and bool(old_row["is_label_mature"]):
            merged["label_matured_at_utc"] = old_row["label_matured_at_utc"]
        if same_business:
            counts["unchanged"] += 1
        else:
            counts["updated"] += 1
        rows[key] = merged

    combined = pd.DataFrame(rows.values(), columns=LABEL_COLUMNS)
    combined = validate_target_table(combined)
    return combined, counts


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_default(value: Any) -> Any:
    if isinstance(value, (date, datetime, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(f"cannot serialize {type(value).__name__} to JSON")


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        delete=False,
    )
    temporary = Path(handle.name)
    try:
        with handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True, default=_json_default)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _cleanup_entries(entries: list[dict[str, Any]]) -> None:
    for entry in entries:
        for name in ("staged_path", "backup_path"):
            path = Path(entry[name])
            if path.exists():
                path.unlink()


def _rollback_journal(path: Path, journal: dict[str, Any]) -> None:
    entries = journal.get("entries")
    if not isinstance(entries, list) or not entries:
        raise TargetPipelineError(f"Target publish journal has no file entries: {path}")
    for entry in reversed(entries):
        target = Path(entry["target_path"])
        staged = Path(entry["staged_path"])
        backup = Path(entry["backup_path"])
        if backup.exists():
            if target.exists():
                target.unlink()
            os.replace(backup, target)
        elif entry["originally_existed"] and not target.exists():
            raise TargetPipelineError(f"cannot restore previous Target output: {target}")
        elif not entry["originally_existed"] and not staged.exists() and target.exists():
            target.unlink()
        if staged.exists():
            staged.unlink()
    journal["status"] = "ROLLED_BACK"
    _write_json_atomic(path, journal)


def recover_target_transactions(manifest_dir: str | Path) -> list[str]:
    """Roll back interrupted publishes and clean backups from completed publishes."""
    root = Path(manifest_dir)
    recovered: list[str] = []
    if not root.exists():
        return recovered
    for journal_path in sorted(root.glob("run_id=*/publish-transaction.json")):
        try:
            journal = json.loads(journal_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise TargetPipelineError(f"cannot read Target publish journal: {journal_path}") from error
        if not isinstance(journal, dict):
            raise TargetPipelineError(f"Target publish journal must be a JSON object: {journal_path}")
        status = journal.get("status")
        if status == "PREPARED":
            _rollback_journal(journal_path, journal)
            recovered.append(str(journal.get("run_id", journal_path.parent.name)))
        elif status == "COMMITTED":
            # The shared Parquet path can be replaced by a later committed run.
            # Each run's immutable manifest retains the checksum from its own publish.
            _cleanup_entries(journal.get("entries", []))
        elif status != "ROLLED_BACK":
            raise TargetPipelineError(f"unknown Target publish status in {journal_path}: {status!r}")
    return recovered


def _stage_file(path: Path, suffix: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        prefix=f".{path.stem}.", suffix=suffix, dir=path.parent, delete=False
    )
    temporary = Path(handle.name)
    handle.close()
    return temporary


def _replace_files_atomically(
    staged_files: dict[Path, Path],
    journal_path: Path,
    run_id: str,
) -> None:
    transaction_id = uuid.uuid4().hex
    entries = [
        {
            "target_path": str(target),
            "staged_path": str(staged),
            "backup_path": str(target.with_name(f".{target.name}.{transaction_id}.bak")),
            "originally_existed": target.exists(),
            "sha256": _sha256_file(staged),
        }
        for target, staged in staged_files.items()
    ]
    journal = {"version": 1, "run_id": run_id, "status": "PREPARED", "entries": entries}
    _write_json_atomic(journal_path, journal)
    try:
        for entry in entries:
            target = Path(entry["target_path"])
            backup = Path(entry["backup_path"])
            if entry["originally_existed"]:
                os.replace(target, backup)
        for entry in entries:
            os.replace(Path(entry["staged_path"]), Path(entry["target_path"]))
        for entry in entries:
            target = Path(entry["target_path"])
            if _sha256_file(target) != entry["sha256"]:
                raise TargetPipelineError(f"published Target file checksum mismatch: {target}")
        journal["status"] = "COMMITTED"
        _write_json_atomic(journal_path, journal)
    except Exception:
        _rollback_journal(journal_path, journal)
        raise
    _cleanup_entries(entries)


def publish_target_labels(
    incoming: pd.DataFrame,
    output_path: str | Path,
    manifest_path: str | Path,
    manifest: dict[str, Any],
    *,
    run_dir: str | Path,
    overwrite_conflicts: bool = False,
    overwrite_reason: str | None = None,
) -> tuple[dict[str, int], dict[str, Any]]:
    output_file = Path(output_path)
    manifest_file = Path(manifest_path)
    journal_file = Path(run_dir) / "publish-transaction.json"
    if len({output_file.resolve(), manifest_file.resolve(), journal_file.resolve()}) != 3:
        raise TargetPipelineError("Target output, manifest, and publish journal paths must be distinct")
    if manifest_file.exists() or Path(run_dir).exists():
        raise TargetPipelineError(f"Target run directory already exists: {run_dir}")

    old = pd.DataFrame(columns=LABEL_COLUMNS)
    if output_file.is_file():
        try:
            old = pd.read_parquet(output_file)
        except Exception as error:
            raise TargetPipelineError(f"cannot read existing Target output: {output_file}") from error
    combined, counts = merge_target_labels(
        old,
        incoming,
        overwrite_conflicts=overwrite_conflicts,
        overwrite_reason=overwrite_reason,
    )

    output_stage = _stage_file(output_file, ".tmp.parquet")
    manifest_stage: Path | None = None
    try:
        combined.to_parquet(output_stage, index=False)
        output_sha = _sha256_file(output_stage)
        final_manifest = dict(manifest)
        final_manifest["publish_counts"] = counts
        final_manifest["output"] = {
            "table": "asset_volatility_labels",
            "path": str(output_file),
            "sha256": output_sha,
            "rows_in_run": int(len(incoming)),
            "rows_after_publish": int(len(combined)),
            "columns": list(LABEL_COLUMNS),
        }
        manifest_stage = _stage_file(manifest_file, ".tmp")
        with manifest_stage.open("w", encoding="utf-8") as target:
            json.dump(
                final_manifest,
                target,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                default=_json_default,
            )
            target.write("\n")
            target.flush()
            os.fsync(target.fileno())
        _replace_files_atomically(
            {output_file: output_stage, manifest_file: manifest_stage},
            journal_file,
            str(final_manifest.get("run_id", "")),
        )
        return counts, final_manifest
    except Exception:
        for staged in (output_stage, manifest_stage):
            if staged is not None and staged.exists():
                staged.unlink()
        raise
