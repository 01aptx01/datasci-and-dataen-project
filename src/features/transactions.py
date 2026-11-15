from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.features.pipeline import FeaturePipelineError
from src.ingestion.quarantine import QUARANTINE_COLUMNS


QUALITY_COLUMNS = [
    "finding_id",
    "run_id",
    "finding_type",
    "source_batch_id",
    "date",
    "ticker",
    "raw_value",
    "reason",
    "feature",
    "value",
    "lower_bound",
    "upper_bound",
    "detected_at_utc",
]

TRANSACTION_FILENAME = "transaction.json"
QUALITY_FILENAME = "quality_results.parquet"
PUBLISH_JOURNAL_FILENAME = "publish-transaction.json"
QUARANTINE_IDENTITY = tuple(QUARANTINE_COLUMNS)


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", newline="", prefix=f".{path.name}.",
        suffix=".tmp", dir=path.parent, delete=False,
    )
    temp_path = Path(handle.name)
    try:
        with handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _finding_id(row: dict[str, Any]) -> str:
    identity = [
        row.get("run_id", ""), row.get("finding_type", ""),
        row.get("source_batch_id", ""), row.get("date", ""),
        row.get("ticker", ""), row.get("raw_value", ""),
        row.get("reason", ""), row.get("feature", ""),
    ]
    encoded = json.dumps(identity, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _quality_rows(
    run_id: str,
    detected_at_utc: str,
    quarantine_records: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for item in quarantine_records:
        row = {
            "run_id": run_id,
            "finding_type": "QUARANTINE",
            "source_batch_id": item.get("source_batch_id") or "",
            "date": item.get("date") or "",
            "ticker": item.get("ticker") or "",
            "raw_value": item.get("raw_value") or "",
            "reason": item.get("reason") or "",
            "feature": "",
            "value": None,
            "lower_bound": None,
            "upper_bound": None,
            "detected_at_utc": item.get("detected_at_utc") or detected_at_utc,
        }
        row["finding_id"] = _finding_id(row)
        rows.append(row)

    for item in warnings:
        row = {
            "run_id": run_id,
            "finding_type": "WARNING",
            "source_batch_id": "",
            "date": item.get("date") or "",
            "ticker": item.get("ticker") or "",
            "raw_value": "",
            "reason": "HEURISTIC_WARNING",
            "feature": item.get("feature") or "",
            "value": item.get("value"),
            "lower_bound": item.get("lower_bound"),
            "upper_bound": item.get("upper_bound"),
            "detected_at_utc": detected_at_utc,
        }
        row["finding_id"] = _finding_id(row)
        rows.append(row)

    return pd.DataFrame(rows, columns=QUALITY_COLUMNS)


def _write_quality_results(path: Path, findings: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        prefix=f".{path.stem}.", suffix=".tmp.parquet", dir=path.parent,
        delete=False,
    )
    temp_path = Path(handle.name)
    handle.close()
    try:
        findings.to_parquet(temp_path, index=False)
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def prepare_feature_transaction(
    run_dir: str | Path,
    run_id: str,
    timestamp: str,
    quarantine_records: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    quarantine_path: str | Path,
    features_path: str | Path,
    correlations_path: str | Path,
    manifest_path: str | Path,
    feature_rows: int,
    correlation_rows: int,
) -> tuple[Path, Path]:
    directory = Path(run_dir)
    directory.mkdir(parents=True, exist_ok=True)
    quality_path = directory / QUALITY_FILENAME
    state_path = directory / TRANSACTION_FILENAME
    if quality_path.exists() or state_path.exists():
        raise FeaturePipelineError(f"Feature transaction already exists for run_id={run_id}")
    findings = _quality_rows(run_id, timestamp, quarantine_records, warnings)
    _write_quality_results(quality_path, findings)
    state = {
        "run_id": run_id,
        "status": "PREPARED",
        "created_at_utc": timestamp,
        "updated_at_utc": timestamp,
        "quality_results_path": str(quality_path),
        "quality_results_sha256": _sha256_file(quality_path),
        "publish_journal_path": str(directory / PUBLISH_JOURNAL_FILENAME),
        "manifest_path": str(manifest_path),
        "features_path": str(features_path),
        "correlations_path": str(correlations_path),
        "quarantine_path": str(quarantine_path),
        "expected_feature_rows": int(feature_rows),
        "expected_correlation_rows": int(correlation_rows),
        "expected_quarantine_records": int(len(quarantine_records)),
        "expected_finding_count": int(len(findings)),
    }
    _write_transaction(state_path, state)
    return quality_path, state_path


def _write_transaction(path: Path, state: dict[str, Any]) -> None:
    updated = dict(state)
    updated["updated_at_utc"] = _now_utc()
    _atomic_write_text(
        path,
        json.dumps(updated, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    state.update(updated)


def update_transaction_status(
    state_path: str | Path,
    status: str,
    **details: Any,
) -> dict[str, Any]:
    path = Path(state_path)
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FeaturePipelineError(f"cannot read Feature transaction state: {path}") from error
    if not isinstance(state, dict):
        raise FeaturePipelineError(f"Feature transaction state must be a JSON object: {path}")
    state.update(details)
    state["status"] = status
    _write_transaction(path, state)
    return state


def load_quarantine_records(quality_results_path: str | Path) -> list[dict[str, str]]:
    path = Path(quality_results_path)
    try:
        findings = pd.read_parquet(path)
    except Exception as error:
        raise FeaturePipelineError(f"cannot read Feature quality results: {path}") from error
    if list(findings.columns) != QUALITY_COLUMNS:
        raise FeaturePipelineError(f"Feature quality results schema mismatch: {path}")

    records = []
    for item in findings.loc[findings["finding_type"] == "QUARANTINE"].to_dict("records"):
        records.append({
            column: _text_value(item.get(column))
            for column in QUARANTINE_COLUMNS
        })
    return records


def _text_value(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value)


def _quarantine_signature(row: dict[str, Any]) -> tuple[str, ...]:
    return tuple(_text_value(row.get(column)) for column in QUARANTINE_IDENTITY)


def reconcile_feature_quarantine(
    quality_results_path: str | Path,
    csv_path: str | Path = "logs/quarantine.csv",
) -> int:
    expected = load_quarantine_records(quality_results_path)
    if not expected:
        return 0

    path = Path(csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: list[dict[str, str]] = []
    if path.is_file() and path.stat().st_size:
        try:
            with path.open("r", newline="", encoding="utf-8-sig") as source:
                reader = csv.DictReader(source, strict=True)
                if reader.fieldnames != QUARANTINE_COLUMNS:
                    raise FeaturePipelineError(
                        f"quarantine CSV schema mismatch; expected {QUARANTINE_COLUMNS}: {path}"
                    )
                for row in reader:
                    if None in row or any(value is None for value in row.values()):
                        raise FeaturePipelineError(f"malformed quarantine CSV row: {path}")
                    existing.append({
                        column: _text_value(row.get(column))
                        for column in QUARANTINE_COLUMNS
                    })
        except (OSError, UnicodeDecodeError, csv.Error) as error:
            raise FeaturePipelineError(f"cannot read quarantine CSV: {path}") from error

    expected_signatures = {_quarantine_signature(row) for row in expected}
    expected_run_ids = {row["run_id"] for row in expected}
    retained: list[dict[str, str]] = []
    seen: set[tuple[str, ...]] = set()
    for row in existing:
        signature = _quarantine_signature(row)
        if row["run_id"] in expected_run_ids and signature not in expected_signatures:
            raise FeaturePipelineError(
                f"quarantine CSV has an unexpected or partial record for run_id={row['run_id']}"
            )
        if row["run_id"] in expected_run_ids and signature in seen:
            continue
        retained.append(row)
        seen.add(signature)

    additions = []
    for row in expected:
        signature = _quarantine_signature(row)
        if signature not in seen:
            additions.append(row)
            seen.add(signature)
    if additions or len(retained) != len(existing):
        all_rows = retained + additions
        handle = tempfile.NamedTemporaryFile(
            mode="w", newline="", encoding="utf-8", prefix=f".{path.name}.",
            suffix=".tmp", dir=path.parent, delete=False,
        )
        temp_path = Path(handle.name)
        try:
            with handle:
                writer = csv.DictWriter(handle, fieldnames=QUARANTINE_COLUMNS)
                writer.writeheader()
                writer.writerows(all_rows)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, path)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    verified = _read_quarantine_csv(path)
    verified_signatures = {_quarantine_signature(row) for row in verified}
    missing = [
        row for row in expected
        if _quarantine_signature(row) not in verified_signatures
    ]
    if missing:
        raise FeaturePipelineError(
            f"quarantine reconciliation incomplete: {len(missing)} finding(s) missing"
        )
    actual_run_rows = sum(
        row["run_id"] in expected_run_ids for row in verified
    )
    if actual_run_rows != len(expected_signatures):
        raise FeaturePipelineError(
            f"quarantine reconciliation count mismatch for run_id={expected[0]['run_id']}"
        )
    return len(additions)


def _read_quarantine_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", newline="", encoding="utf-8-sig") as source:
            reader = csv.DictReader(source, strict=True)
            if reader.fieldnames != QUARANTINE_COLUMNS:
                raise FeaturePipelineError(f"quarantine CSV schema mismatch: {path}")
            rows = []
            for row in reader:
                if None in row or any(value is None for value in row.values()):
                    raise FeaturePipelineError(f"malformed quarantine CSV row: {path}")
                rows.append({
                    column: _text_value(row.get(column)) for column in QUARANTINE_COLUMNS
                })
            return rows
    except (OSError, UnicodeDecodeError, csv.Error) as error:
        raise FeaturePipelineError(f"cannot verify quarantine CSV: {path}") from error


def recover_pending_feature_runs(manifest_dir: str | Path) -> list[str]:
    """Recover complete publishes left before quarantine reconciliation or roll back incomplete ones."""
    from src.features.storage import recover_publish_journal

    root = Path(manifest_dir)
    if not root.exists():
        return []
    recovered = []
    for run_dir in sorted(root.glob("run_id=*")):
        state_path = run_dir / TRANSACTION_FILENAME
        if not state_path.is_file():
            continue
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise FeaturePipelineError(
                f"cannot read pending Feature transaction: {state_path}"
            ) from error
        if not isinstance(state, dict):
            raise FeaturePipelineError(
                f"pending Feature transaction must be a JSON object: {state_path}"
            )
        if state.get("status") not in {"PREPARED", "OUTPUTS_PUBLISHED"}:
            continue

        journal_path = Path(state["publish_journal_path"])
        if not journal_path.is_file():
            if state.get("status") == "PREPARED":
                update_transaction_status(
                    state_path,
                    "FAILED",
                    failure_reason="publish journal is missing before output commit",
                )
                continue
            raise FeaturePipelineError(
                f"published Feature transaction has no publish journal: {journal_path}"
            )

        journal = recover_publish_journal(journal_path)
        if journal["status"] == "ROLLED_BACK":
            update_transaction_status(
                state_path,
                "FAILED",
                failure_reason="interrupted output replacement was rolled back",
            )
            continue

        verify_published_feature_run(state)
        update_transaction_status(state_path, "OUTPUTS_PUBLISHED")
        reconcile_feature_quarantine(
            state["quality_results_path"],
            state["quarantine_path"],
        )
        update_transaction_status(state_path, "COMMITTED")
        recovered.append(str(state["run_id"]))
    return recovered


def verify_published_feature_run(state: dict[str, Any]) -> None:
    manifest_path = Path(state["manifest_path"])
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FeaturePipelineError(
            f"cannot verify published Feature manifest: {manifest_path}"
        ) from error
    if not isinstance(manifest, dict) or manifest.get("run_id") != state.get("run_id"):
        raise FeaturePipelineError(
            f"published Feature manifest run_id does not match transaction: {manifest_path}"
        )

    for table_name, path_key, expected_key in (
        ("asset_volatility_features", "features_path", "expected_feature_rows"),
        ("asset_rolling_correlations", "correlations_path", "expected_correlation_rows"),
    ):
        output_metadata = manifest.get("outputs", {}).get(table_name)
        if not isinstance(output_metadata, dict):
            raise FeaturePipelineError(
                f"published Feature manifest is missing {table_name} metadata"
            )
        table_path = Path(state[path_key])
        try:
            table = pd.read_parquet(table_path)
        except Exception as error:
            raise FeaturePipelineError(
                f"cannot verify published {table_name}: {table_path}"
            ) from error
        if "run_id" not in table.columns:
            raise FeaturePipelineError(f"published {table_name} has no run_id column")
        if list(table.columns) != output_metadata.get("columns"):
            raise FeaturePipelineError(
                f"published {table_name} schema does not match the run manifest"
            )
        if int(output_metadata.get("rows_in_run", -1)) != int(state[expected_key]):
            raise FeaturePipelineError(
                f"published {table_name} manifest row count does not match transaction"
            )
        actual_rows = int(table["run_id"].eq(state["run_id"]).sum())
        if actual_rows != int(state[expected_key]):
            raise FeaturePipelineError(
                f"published {table_name} row count mismatch for run_id={state['run_id']}: "
                f"expected {state[expected_key]}, found {actual_rows}"
            )

    quality_path = Path(state["quality_results_path"])
    if _sha256_file(quality_path) != state.get("quality_results_sha256"):
        raise FeaturePipelineError(
            f"quality result checksum mismatch for run_id={state['run_id']}"
        )
    findings = pd.read_parquet(quality_path)
    if list(findings.columns) != QUALITY_COLUMNS:
        raise FeaturePipelineError(
            f"quality result schema mismatch for run_id={state['run_id']}"
        )
    if int(len(findings)) != int(state["expected_finding_count"]):
        raise FeaturePipelineError(
            f"quality result count mismatch for run_id={state['run_id']}"
        )
    if findings["finding_id"].duplicated().any() or not findings["run_id"].eq(
        state["run_id"]
    ).all():
        raise FeaturePipelineError(
            f"quality result identity mismatch for run_id={state['run_id']}"
        )
    actual_quarantine = int(findings["finding_type"].eq("QUARANTINE").sum())
    if actual_quarantine != int(state["expected_quarantine_records"]):
        raise FeaturePipelineError(
            f"quality result count mismatch for run_id={state['run_id']}: "
            f"expected {state['expected_quarantine_records']}, found {actual_quarantine}"
        )
