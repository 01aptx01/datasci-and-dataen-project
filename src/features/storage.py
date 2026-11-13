from __future__ import annotations

import json
import os
import tempfile
import uuid
from numbers import Real
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd

from src.features.pipeline import (
    CORE_FEATURE_COLUMNS,
    CORRELATION_COLUMNS,
    CORRELATION_VALUE_COLUMNS,
    FEATURE_COLUMNS,
    FEATURE_VALUE_COLUMNS,
    FeaturePipelineError,
    is_valid_correlation_matrix,
)


FEATURE_KEYS = ("date", "ticker")
CORRELATION_KEYS = ("date",)
FEATURE_LINEAGE = {"run_id", "source_batch_id", "feature_as_of_utc"}
CORRELATION_LINEAGE = {"run_id", "source_batch_id", "computed_at_utc"}


def _is_missing(value: Any) -> bool:
    missing = pd.isna(value)
    return bool(missing) if isinstance(missing, (bool, np.bool_)) else False


def _validate_table(
    data: pd.DataFrame,
    columns: Sequence[str],
    keys: Sequence[str],
    table_name: str,
) -> None:
    if not isinstance(data, pd.DataFrame):
        raise FeaturePipelineError(f"{table_name} output must be a DataFrame")
    if list(data.columns) != list(columns):
        raise FeaturePipelineError(
            f"{table_name} schema mismatch; expected columns in dictionary order"
        )
    if data.empty:
        raise FeaturePipelineError(f"{table_name} output cannot be empty")
    if data.duplicated(list(keys)).any():
        raise FeaturePipelineError(f"{table_name} has duplicate primary keys")
    if data.loc[:, list(keys)].isna().any().any():
        raise FeaturePipelineError(f"{table_name} primary keys cannot be NULL")

    if table_name == "asset_volatility_features":
        for column in ("is_model_ready", "is_warmup_buffer"):
            if not data[column].map(
                lambda value: isinstance(value, (bool, np.bool_))
            ).all():
                raise FeaturePipelineError(f"{table_name} {column} must be boolean")
        try:
            numeric = data.loc[:, list(FEATURE_VALUE_COLUMNS)].to_numpy(dtype=float)
        except (TypeError, ValueError) as error:
            raise FeaturePipelineError(
                f"{table_name} feature values must be numeric"
            ) from error
        non_null = ~pd.isna(numeric)
        if not np.isfinite(numeric[non_null]).all():
            raise FeaturePipelineError(
                f"{table_name} feature values must be finite when present"
            )
        core = data.loc[:, list(CORE_FEATURE_COLUMNS)].to_numpy(dtype=float)
        ready_expected = np.isfinite(core).all(axis=1)
        if not np.array_equal(data["is_model_ready"].to_numpy(dtype=bool), ready_expected):
            raise FeaturePipelineError("asset_volatility_features is_model_ready is inconsistent")
        for column in ("rv_5d", "rv_20d", "rv_60d"):
            values = data[column].dropna().to_numpy(dtype=float)
            if not np.isfinite(values).all() or (values < 0).any():
                raise FeaturePipelineError(f"{table_name} {column} must be finite and non-negative")
        rsi = data["rsi_14d"].dropna().to_numpy(dtype=float)
        if (rsi < 0).any() or (rsi > 100).any():
            raise FeaturePipelineError(f"{table_name} rsi_14d must be in [0, 100]")
        widths = data["bb_width_20d"].dropna().to_numpy(dtype=float)
        if (widths < 0).any():
            raise FeaturePipelineError(f"{table_name} bb_width_20d must be non-negative")
        for column in ("feature_set_version", "run_id", "source_batch_id", "feature_as_of_utc"):
            values = data[column]
            limit = 16 if column == "feature_set_version" else 64
            if (
                values.isna().any()
                or not values.map(lambda value: isinstance(value, str)).all()
                or values.str.strip().eq("").any()
                or values.str.len().gt(limit).any()
            ):
                raise FeaturePipelineError(
                    f"{table_name} {column} must be a non-empty string up to {limit} characters"
                )
    else:
        if not data["is_corr_ready"].map(
            lambda value: isinstance(value, (bool, np.bool_))
        ).all():
            raise FeaturePipelineError(
                "asset_rolling_correlations is_corr_ready must be boolean"
            )
        flags = data["is_corr_ready"].to_numpy(dtype=bool)
        pair_values = data.loc[:, list(CORRELATION_VALUE_COLUMNS)]
        if pair_values.loc[flags].isna().any().any():
            raise FeaturePipelineError("ready correlation rows must have all three pair values")
        if not pair_values.loc[~flags].isna().all().all():
            raise FeaturePipelineError("unready correlation rows must have NULL pair values")
        try:
            ready_values = pair_values.loc[flags].to_numpy(dtype=float)
        except (TypeError, ValueError) as error:
            raise FeaturePipelineError(
                "ready correlation values must be numeric"
            ) from error
        if ready_values.size and (
            not np.isfinite(ready_values).all()
            or (ready_values < -1.0 - 1e-12).any()
            or (ready_values > 1.0 + 1e-12).any()
        ):
            raise FeaturePipelineError("ready correlations must be finite values in [-1, 1]")
        if ready_values.size:
            for row in ready_values:
                matrix = np.array(
                    [
                        [1.0, row[0], row[1]],
                        [row[0], 1.0, row[2]],
                        [row[1], row[2], 1.0],
                    ]
                )
                if not is_valid_correlation_matrix(matrix):
                    raise FeaturePipelineError(
                        "ready correlation rows must form a symmetric positive semidefinite matrix"
                    )
        for column in ("run_id", "source_batch_id", "computed_at_utc"):
            values = data[column]
            if (
                values.isna().any()
                or not values.map(lambda value: isinstance(value, str)).all()
                or values.str.strip().eq("").any()
                or values.str.len().gt(64).any()
            ):
                raise FeaturePipelineError(
                    f"asset_rolling_correlations {column} must be a non-empty string up to 64 characters"
                )


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


def _same_business_row(
    old: pd.Series,
    new: pd.Series,
    lineage_columns: set[str],
) -> bool:
    return all(
        _same_value(old[column], new[column])
        for column in new.index
        if column not in lineage_columns
    )


def _upsert(
    old: pd.DataFrame,
    incoming: pd.DataFrame,
    columns: Sequence[str],
    keys: Sequence[str],
    lineage_columns: set[str],
    table_name: str,
    overwrite_conflicts: bool,
) -> tuple[pd.DataFrame, dict[str, int]]:
    _validate_table(incoming, columns, keys, table_name)
    if old.empty:
        combined = incoming.copy()
        return combined, {
            "inserted": len(incoming),
            "unchanged": 0,
            "updated": 0,
        }

    _validate_table(old, columns, keys, table_name)
    rows = {
        tuple(row[column] for column in keys): row.copy()
        for _, row in old.iterrows()
    }
    counts = {"inserted": 0, "unchanged": 0, "updated": 0}
    for _, new_row in incoming.iterrows():
        key = tuple(new_row[column] for column in keys)
        old_row = rows.get(key)
        if old_row is None:
            counts["inserted"] += 1
        elif _same_business_row(old_row, new_row, lineage_columns):
            counts["unchanged"] += 1
        elif not overwrite_conflicts:
            raise FeaturePipelineError(
                f"{table_name} has conflicting business values for key {key}; "
                "review the input and explicitly enable overwrite_conflicts to replace them"
            )
        else:
            counts["updated"] += 1
        rows[key] = new_row.copy()

    combined = pd.DataFrame(rows.values(), columns=columns)
    combined = combined.sort_values(list(keys)).reset_index(drop=True)
    _validate_table(combined, columns, keys, table_name)
    return combined, counts


def _stage_parquet(data: pd.DataFrame, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        prefix=f".{target.stem}.",
        suffix=".tmp.parquet",
        dir=target.parent,
        delete=False,
    )
    temp_path = Path(handle.name)
    handle.close()
    try:
        data.to_parquet(temp_path, index=False)
        return temp_path
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise


def _stage_text(content: str, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        prefix=f".{target.stem}.",
        suffix=".tmp",
        dir=target.parent,
        delete=False,
    )
    temp_path = Path(handle.name)
    handle.close()
    temp_path.write_text(content, encoding="utf-8")
    return temp_path


def _replace_files_atomically(staged: dict[Path, Path]) -> None:
    backups: dict[Path, Path] = {}
    replaced: list[Path] = []
    transaction_id = uuid.uuid4().hex
    try:
        for target in staged:
            if target.exists():
                backup = target.with_name(f".{target.name}.{transaction_id}.rollback")
                os.replace(target, backup)
                backups[target] = backup
        for target, temp_path in staged.items():
            os.replace(temp_path, target)
            replaced.append(target)
    except Exception:
        for target in reversed(replaced):
            if target.exists():
                target.unlink()
        for target, backup in backups.items():
            if backup.exists():
                os.replace(backup, target)
        raise
    finally:
        for temp_path in staged.values():
            if temp_path.exists():
                temp_path.unlink()
    for backup in backups.values():
        if backup.exists():
            backup.unlink()


def publish_feature_outputs(
    features: pd.DataFrame,
    correlations: pd.DataFrame,
    features_path: str | Path,
    correlations_path: str | Path,
    manifest_path: str | Path,
    manifest: dict[str, Any],
    overwrite_conflicts: bool = False,
) -> dict[str, int]:
    """Validate, idempotently upsert, and atomically replace both Parquet outputs."""
    feature_table = Path(features_path)
    correlation_table = Path(correlations_path)
    manifest_file = Path(manifest_path)
    if len({feature_table.resolve(), correlation_table.resolve(), manifest_file.resolve()}) != 3:
        raise FeaturePipelineError("feature, correlation, and manifest paths must be distinct")

    old_features = pd.read_parquet(feature_table) if feature_table.exists() else pd.DataFrame()
    old_correlations = (
        pd.read_parquet(correlation_table)
        if correlation_table.exists()
        else pd.DataFrame()
    )
    combined_features, feature_counts = _upsert(
        old_features,
        features,
        FEATURE_COLUMNS,
        FEATURE_KEYS,
        FEATURE_LINEAGE,
        "asset_volatility_features",
        overwrite_conflicts,
    )
    combined_correlations, correlation_counts = _upsert(
        old_correlations,
        correlations,
        CORRELATION_COLUMNS,
        CORRELATION_KEYS,
        CORRELATION_LINEAGE,
        "asset_rolling_correlations",
        overwrite_conflicts,
    )

    encoded_manifest = json.dumps(
        manifest,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        default=str,
    )
    staged: dict[Path, Path] = {}
    try:
        staged[feature_table] = _stage_parquet(combined_features, feature_table)
        staged[correlation_table] = _stage_parquet(combined_correlations, correlation_table)
        staged[manifest_file] = _stage_text(encoded_manifest + "\n", manifest_file)
        _replace_files_atomically(staged)
    except Exception as error:
        for temp_path in staged.values():
            if temp_path.exists():
                temp_path.unlink()
        if isinstance(error, FeaturePipelineError):
            raise
        raise FeaturePipelineError(f"failed to publish feature outputs: {error}") from error

    return {
        "feature_rows": len(combined_features),
        "correlation_rows": len(combined_correlations),
        "feature_rows_inserted": feature_counts["inserted"],
        "feature_rows_unchanged": feature_counts["unchanged"],
        "feature_rows_updated": feature_counts["updated"],
        "correlation_rows_inserted": correlation_counts["inserted"],
        "correlation_rows_unchanged": correlation_counts["unchanged"],
        "correlation_rows_updated": correlation_counts["updated"],
    }

