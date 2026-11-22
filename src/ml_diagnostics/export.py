from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
import uuid
from collections.abc import Mapping
from datetime import date
from typing import Any
import zipfile

import yaml


DATA_FILES = (
    "feature_drift_metrics.csv",
    "feature_drift_histograms.csv",
    "feature_drift_reference_summary.csv",
    "feature_drift_calibration.csv",
    "feature_drift_summary.md",
)
MANIFEST_NAME = "feature_drift_manifest.json"
CHECKSUMS_NAME = "CHECKSUMS.sha256"
ARCHIVE_FILES = (*DATA_FILES, MANIFEST_NAME, CHECKSUMS_NAME)
FRONTEND_FILES = (
    MANIFEST_NAME,
    "feature_drift_metrics.csv",
    "feature_drift_histograms.csv",
    "feature_drift_reference_summary.csv",
    "feature_drift_calibration.csv",
    CHECKSUMS_NAME,
)
METRICS_HEADERS = (
    "diagnostic_id", "evaluation_id", "replay_id", "source_feature_run_id", "feature_set_version", "split", "as_of_date", "ticker", "feature_name",
    "reference_start", "reference_end", "reference_n", "current_start", "current_end", "current_n", "window_size", "wasserstein_raw", "train_iqr",
    "wasserstein_normalized", "psi", "median_ref", "median_current", "p95_ref", "p95_current", "out_of_train_range_rate", "wasserstein_threshold",
    "psi_threshold", "status", "status_reason",
)
HISTOGRAM_HEADERS = (
    "diagnostic_id", "as_of_date", "ticker", "feature_name", "window_size", "bin_index", "lower_edge", "upper_edge", "reference_count", "current_count",
    "reference_pct", "current_pct", "bin_definition_id", "effective_bin_count",
)
REFERENCE_HEADERS = (
    "diagnostic_id", "ticker", "feature_name", "reference_start", "reference_end", "reference_n", "q01", "q05", "q25", "median", "q75", "q95", "q99",
    "train_iqr", "effective_bin_count", "bin_definition_id", "reference_hash", "bin_status",
)
CALIBRATION_HEADERS = (
    "diagnostic_id", "ticker", "feature_name", "window_size", "calibration_start", "calibration_end", "valid_window_count", "threshold_percentile",
    "threshold_method", "wasserstein_threshold", "psi_threshold", "calibration_status",
)
EXPECTED_HEADERS = {
    "feature_drift_metrics.csv": METRICS_HEADERS,
    "feature_drift_histograms.csv": HISTOGRAM_HEADERS,
    "feature_drift_reference_summary.csv": REFERENCE_HEADERS,
    "feature_drift_calibration.csv": CALIBRATION_HEADERS,
}
ALLOWED_STATUSES = {
    "DRIFT_SIGNAL", "NO_SIGNAL", "INSUFFICIENT_DATA", "UNCOMPUTABLE_SCALE", "CALIBRATION_LIMITATION",
}


class DiagnosticPackageError(ValueError):
    """Raised when a diagnostic package is incomplete, changed or mismatched."""


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _finite_number(value: str, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise DiagnosticPackageError(f"Invalid {label} in Feature Drift CSV") from error
    if number != number or number in (float("inf"), float("-inf")):
        raise DiagnosticPackageError(f"Non-finite {label} in Feature Drift CSV")
    return number


def _parse_checksums(payload: bytes) -> dict[str, str]:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise DiagnosticPackageError("Feature Drift checksums are not UTF-8") from error
    checksums: dict[str, str] = {}
    for line_number, line in enumerate(text.splitlines(), start=1):
        match = re.fullmatch(r"([a-fA-F0-9]{64})  ([A-Za-z0-9_.-]+)", line)
        if not match:
            raise DiagnosticPackageError(f"Invalid Feature Drift checksum line {line_number}")
        digest, name = match.groups()
        if name in checksums:
            raise DiagnosticPackageError(f"Duplicate Feature Drift checksum for {name}")
        checksums[name] = digest.lower()
    if not checksums:
        raise DiagnosticPackageError("Feature Drift checksums are empty")
    return checksums


def _parse_csv(payload: bytes, name: str, headers: tuple[str, ...]) -> list[dict[str, str]]:
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise DiagnosticPackageError(f"{name} is not UTF-8") from error
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if tuple(reader.fieldnames or ()) != headers:
        raise DiagnosticPackageError(f"{name} header does not match the Feature Drift schema")
    rows = list(reader)
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise DiagnosticPackageError(f"{name} contains a row with the wrong number of fields")
    return rows


def _validate_csv_members(manifest: dict[str, Any], members: dict[str, bytes]) -> None:
    files = manifest.get("files", {})
    if set(files) != set(DATA_FILES):
        raise DiagnosticPackageError("Feature Drift manifest file list differs from the package allowlist")
    for name in DATA_FILES:
        record = files[name]
        payload = members[name]
        if record.get("path") != name or record.get("sha256") != _sha256(payload) or record.get("bytes") != len(payload):
            raise DiagnosticPackageError(f"Feature Drift manifest checksum does not match {name}")

    parsed: dict[str, list[dict[str, str]]] = {}
    for name, headers in EXPECTED_HEADERS.items():
        rows = _parse_csv(members[name], name, headers)
        if files[name].get("rows") != len(rows):
            raise DiagnosticPackageError(f"Feature Drift row count does not match {name}")
        parsed[name] = rows

    configuration = manifest.get("configuration", {})
    tickers = set(configuration.get("tickers", []))
    features = set(configuration.get("core_features", []))
    windows = {str(value) for value in configuration.get("windows", {}).get("sizes", [])}
    cutoff = manifest.get("strictCutoff")
    evaluation_id = manifest.get("evaluationId")
    replay_id = manifest.get("replayId")
    diagnostic_id = manifest.get("diagnosticId")
    try:
        date.fromisoformat(str(cutoff))
    except ValueError as error:
        raise DiagnosticPackageError("Feature Drift cutoff must be an ISO market date") from error

    metric_index: dict[tuple[str, str, str, str], dict[str, str]] = {}
    for row in parsed["feature_drift_metrics.csv"]:
        if row["diagnostic_id"] != diagnostic_id or row["evaluation_id"] != evaluation_id or row["replay_id"] != replay_id:
            raise DiagnosticPackageError("Feature Drift metrics contain mismatched diagnostic identities")
        if row["split"] != "test" or row["ticker"] not in tickers or row["feature_name"] not in features:
            raise DiagnosticPackageError("Feature Drift metrics contain an unsupported scope")
        try:
            date.fromisoformat(row["as_of_date"])
            date.fromisoformat(row["current_start"])
            date.fromisoformat(row["current_end"])
        except ValueError as error:
            raise DiagnosticPackageError("Feature Drift metrics contain an invalid date") from error
        if row["as_of_date"] > cutoff or row["current_end"] != row["as_of_date"]:
            raise DiagnosticPackageError("Feature Drift metrics contain a date beyond the as-of boundary")
        if row["window_size"] not in windows or row["status"] not in ALLOWED_STATUSES:
            raise DiagnosticPackageError("Feature Drift metrics contain an unsupported window or status")
        key = (row["as_of_date"], row["ticker"], row["feature_name"], row["window_size"])
        if key in metric_index:
            raise DiagnosticPackageError("Feature Drift metrics contain duplicate daily scope")
        metric_index[key] = row
        try:
            reference_n = int(row["reference_n"])
            current_n = int(row["current_n"])
            window_size = int(row["window_size"])
        except ValueError as error:
            raise DiagnosticPackageError("Feature Drift sample counts must be integers") from error
        if reference_n < 1 or not 0 <= current_n <= window_size:
            raise DiagnosticPackageError("Feature Drift sample counts are outside their valid range")
        if row["status"] in {"DRIFT_SIGNAL", "NO_SIGNAL"} and current_n != window_size:
            raise DiagnosticPackageError("A Feature Drift signal requires a complete current window")
        for field in ("wasserstein_raw", "train_iqr", "wasserstein_normalized", "psi", "wasserstein_threshold", "psi_threshold"):
            if row[field] != "":
                _finite_number(row[field], field)

    grouped_histograms: dict[tuple[str, str, str, str], list[dict[str, str]]] = {}
    for row in parsed["feature_drift_histograms.csv"]:
        key = (row["as_of_date"], row["ticker"], row["feature_name"], row["window_size"])
        metric = metric_index.get(key)
        if metric is None or metric["status"] == "INSUFFICIENT_DATA":
            raise DiagnosticPackageError("Feature Drift histogram has no matching complete metric row")
        grouped_histograms.setdefault(key, []).append(row)
    for key, rows in grouped_histograms.items():
        metric = metric_index[key]
        rows.sort(key=lambda row: int(row["bin_index"]))
        if [int(row["bin_index"]) for row in rows] != list(range(len(rows))):
            raise DiagnosticPackageError("Feature Drift histogram bins are missing or duplicated")
        if sum(int(row["reference_count"]) for row in rows) != int(metric["reference_n"]):
            raise DiagnosticPackageError("Feature Drift reference histogram counts do not reconcile")
        if sum(int(row["current_count"]) for row in rows) != int(metric["current_n"]):
            raise DiagnosticPackageError("Feature Drift current histogram counts do not reconcile")
        current_pct = sum(_finite_number(row["current_pct"], "current_pct") for row in rows)
        reference_pct = sum(_finite_number(row["reference_pct"], "reference_pct") for row in rows)
        if abs(current_pct - 1.0) > 1e-10 or abs(reference_pct - 1.0) > 1e-10:
            raise DiagnosticPackageError("Feature Drift histogram proportions do not sum to one")

    for name in ("feature_drift_reference_summary.csv", "feature_drift_calibration.csv"):
        for row in parsed[name]:
            if row["diagnostic_id"] != diagnostic_id:
                raise DiagnosticPackageError(f"{name} contains a mismatched diagnostic ID")


def verify_diagnostic_archive(
    archive_payload: bytes,
    *,
    expected_identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if len(archive_payload) > 50 * 1024 * 1024:
        raise DiagnosticPackageError("Feature Drift package exceeds the allowed size")
    try:
        with zipfile.ZipFile(io.BytesIO(archive_payload)) as archive:
            members: dict[str, bytes] = {}
            total_size = 0
            names: set[str] = set()
            for info in archive.infolist():
                path = PurePosixPath(info.filename)
                if path.is_absolute() or ".." in path.parts or "\\" in info.filename or info.is_dir():
                    raise DiagnosticPackageError(f"Unsafe Feature Drift package member path: {info.filename}")
                if info.filename in names:
                    raise DiagnosticPackageError(f"Duplicate Feature Drift package member: {info.filename}")
                names.add(info.filename)
                if stat.S_ISLNK(info.external_attr >> 16):
                    raise DiagnosticPackageError(f"Feature Drift package symlink is not accepted: {info.filename}")
                total_size += info.file_size
                if total_size > 50 * 1024 * 1024:
                    raise DiagnosticPackageError("Feature Drift package expands beyond the allowed size")
                members[info.filename] = archive.read(info)
            if archive.testzip() is not None:
                raise DiagnosticPackageError("Feature Drift package failed CRC verification")
    except (OSError, zipfile.BadZipFile, RuntimeError) as error:
        raise DiagnosticPackageError("Feature Drift package could not be read") from error
    if set(members) != set(ARCHIVE_FILES):
        raise DiagnosticPackageError("Feature Drift package members differ from the allowlist")

    checksums = _parse_checksums(members[CHECKSUMS_NAME])
    if set(checksums) != set(ARCHIVE_FILES) - {CHECKSUMS_NAME}:
        raise DiagnosticPackageError("Feature Drift checksum list differs from the package allowlist")
    for name, expected_hash in checksums.items():
        if _sha256(members[name]) != expected_hash:
            raise DiagnosticPackageError(f"Feature Drift SHA-256 mismatch for {name}")
    try:
        manifest = json.loads(members[MANIFEST_NAME].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DiagnosticPackageError("Feature Drift manifest is invalid JSON") from error
    if not isinstance(manifest, dict) or manifest.get("schemaVersion") != "1.0.0" or manifest.get("status") != "COMPLETED":
        raise DiagnosticPackageError("Feature Drift manifest schema or status is not complete")
    identity_canonical = manifest.get("diagnosticIdentityCanonical")
    if not isinstance(identity_canonical, str) or _sha256(identity_canonical.encode("utf-8")) != manifest.get("diagnosticId"):
        raise DiagnosticPackageError("Feature Drift diagnostic ID does not match its canonical source identity")
    source = manifest.get("source", {})
    for name in ("featureParquetSha256", "targetParquetSha256"):
        if not re.fullmatch(r"[a-f0-9]{64}", str(source.get(name, ""))):
            raise DiagnosticPackageError("Feature Drift source Parquet identity is invalid")
    _validate_csv_members(manifest, members)

    if expected_identity:
        paths = {
            "evaluationId": ("evaluationId",),
            "replayId": ("replayId",),
            "strictCutoff": ("strictCutoff",),
            "featureSetVersion": ("featureSetVersion",),
            "featureRunId": ("source", "featureRunId"),
            "targetRunId": ("source", "targetRunId"),
            "featureParquetSha256": ("source", "featureParquetSha256"),
            "targetParquetSha256": ("source", "targetParquetSha256"),
        }
        for expected_key, path in paths.items():
            if expected_key not in expected_identity:
                continue
            actual: Any = manifest
            for key in path:
                actual = actual.get(key) if isinstance(actual, dict) else None
            if actual != expected_identity[expected_key]:
                raise DiagnosticPackageError(f"Feature Drift package {expected_key} does not match its frozen source")
    return {"manifest": manifest, "members": members}


def _verify_source_payloads(payloads: dict[str, bytes]) -> None:
    checksums = _parse_checksums(payloads[CHECKSUMS_NAME])
    if set(checksums) != set(ARCHIVE_FILES) - {CHECKSUMS_NAME}:
        raise DiagnosticPackageError("Feature Drift checksum list differs from the package allowlist")
    for name, digest in checksums.items():
        if _sha256(payloads[name]) != digest:
            raise DiagnosticPackageError(f"Feature Drift SHA-256 mismatch for {name}")


def create_diagnostic_archive(source_directory: Path, output_path: Path) -> str:
    """Write a deterministic diagnostics-only ZIP and verify it before publication."""
    source_directory = source_directory.resolve()
    output_path = output_path.resolve()
    payloads: dict[str, bytes] = {}
    for name in ARCHIVE_FILES:
        source = source_directory / name
        if not source.is_file() or not source.resolve().is_relative_to(source_directory):
            raise DiagnosticPackageError(f"Required Feature Drift package member is missing: {name}")
        payloads[name] = source.read_bytes()
    _verify_source_payloads(payloads)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=".feature-drift-", suffix=".zip", dir=output_path.parent, delete=False) as stream:
        temp_path = Path(stream.name)
    try:
        with zipfile.ZipFile(temp_path, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name in ARCHIVE_FILES:
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                archive.writestr(info, payloads[name], compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        built = temp_path.read_bytes()
        verify_diagnostic_archive(built)
        temp_path.replace(output_path)
        return _sha256(built)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def publish_verified_archive(
    archive_payload: bytes,
    dist_directory: Path,
    *,
    expected_identity: Mapping[str, Any] | None = None,
) -> str:
    """Verify a sidecar and atomically copy only browser-approved members."""
    verified = verify_diagnostic_archive(archive_payload, expected_identity=expected_identity)
    dist = dist_directory.resolve()
    parent = dist / "feature-drift"
    parent.mkdir(parents=True, exist_ok=True)
    destination = parent / "current"
    temp = parent / f".current-{uuid.uuid4().hex}"
    temp.mkdir()
    try:
        for name in FRONTEND_FILES:
            (temp / name).write_bytes(verified["members"][name])
        if destination.exists():
            names = {path.name for path in destination.iterdir()}
            if names != set(FRONTEND_FILES) or any(
                (destination / name).read_bytes() != verified["members"][name]
                for name in FRONTEND_FILES
            ):
                raise DiagnosticPackageError("Existing Feature Drift static data differs from the verified package")
            for path in temp.iterdir():
                path.unlink()
            temp.rmdir()
        else:
            os.replace(temp, destination)
    except Exception:
        if temp.exists():
            for path in temp.iterdir():
                path.unlink(missing_ok=True)
            temp.rmdir()
        raise
    return str(verified["manifest"]["diagnosticId"])


def _repo_file(root: Path, value: str, label: str) -> Path:
    raw = Path(value)
    if raw.is_absolute() or ".." in raw.parts:
        raise DiagnosticPackageError(f"{label} must use a safe repository-relative path")
    result = (root / raw).resolve()
    if not result.is_relative_to(root):
        raise DiagnosticPackageError(f"{label} escapes the repository")
    return result


def _read_json_file(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DiagnosticPackageError(f"{label} is unavailable or invalid") from error
    if not isinstance(value, dict):
        raise DiagnosticPackageError(f"{label} must be a JSON object")
    return value


def _semantic_source_lineage(manifest: Mapping[str, Any]) -> dict[str, Any]:
    lineage = manifest.get("source_lineage", {})
    keys = (
        "feature_run_id",
        "target_run_id",
        "feature_parquet_sha256",
        "target_parquet_sha256",
        "source_input_sha256",
        "source_batch_ids",
        "source_versions",
        "feature_quality_finding_count",
        "target_quality_finding_count",
    )
    return {key: lineage.get(key) for key in keys} if isinstance(lineage, Mapping) else {}


def _load_pinned_execution(root: Path, config: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    sources = config.get("sources", {})
    if not isinstance(sources, Mapping):
        raise DiagnosticPackageError("Feature Drift source paths are invalid")
    policy_path = _repo_file(root, str(sources.get("snapshot_policy", "")), "Snapshot policy")
    handoff_path = _repo_file(root, str(sources.get("snapshot_handoff_zip", "")), "Snapshot handoff ZIP")
    policy = _read_json_file(policy_path, "Snapshot policy")
    identity = policy.get("identity", {})
    for policy_key, config_key in (
        ("evaluationId", "evaluation_id"),
        ("replayId", "replay_id"),
        ("strictCutoff", "strict_cutoff"),
    ):
        if identity.get(policy_key) != config.get(config_key):
            raise DiagnosticPackageError(f"Feature Drift {config_key} does not match the frozen snapshot policy")
    if not handoff_path.is_file() or _sha256_file(handoff_path) != policy.get("source", {}).get("zipSha256"):
        raise DiagnosticPackageError("Frozen Stage 06 handoff ZIP does not match the snapshot policy")
    try:
        with zipfile.ZipFile(handoff_path) as archive:
            if archive.testzip() is not None:
                raise DiagnosticPackageError("Frozen Stage 06 handoff ZIP failed CRC verification")
            member = policy["members"]["executionManifest"]
            member_path = PurePosixPath(member)
            if member_path.is_absolute() or ".." in member_path.parts or "\\" in member:
                raise DiagnosticPackageError("Frozen execution manifest path is unsafe")
            payload = archive.read(member)
    except (KeyError, OSError, zipfile.BadZipFile) as error:
        raise DiagnosticPackageError("Frozen Stage 06 execution manifest is unavailable") from error
    expected_hash = policy.get("memberSha256", {}).get(member)
    if not expected_hash or _sha256(payload) != expected_hash:
        raise DiagnosticPackageError("Frozen execution manifest does not match its pinned checksum")
    try:
        execution = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DiagnosticPackageError("Frozen Stage 06 execution manifest is invalid") from error
    if not isinstance(execution, dict):
        raise DiagnosticPackageError("Frozen Stage 06 execution manifest must be a JSON object")
    if execution.get("evaluation_id") != config.get("evaluation_id") or execution.get("final_replay_experiment_id") != config.get("replay_id"):
        raise DiagnosticPackageError("Frozen Stage 06 Evaluation/Replay IDs do not match the Feature Drift config")
    return policy, execution


def publish_active_sidecar(repo_root: Path, dist_directory: Path) -> str | None:
    """Copy the active local ZIP only after matching Stage 04/06 and snapshot identity."""
    root = repo_root.resolve()
    dist = dist_directory.resolve()
    if dist != (root / "web" / "dist").resolve():
        raise DiagnosticPackageError("Feature Drift static output must stay inside web/dist")
    try:
        config = yaml.safe_load((root / "config/feature_drift.yaml").read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise DiagnosticPackageError("Feature Drift config is unavailable during the web build") from error
    if not isinstance(config, dict):
        raise DiagnosticPackageError("Feature Drift config is invalid during the web build")
    outputs = config.get("outputs", {})
    active_path = (root / outputs.get("active_pointer", "")).resolve()
    output_root = (root / outputs.get("root", "")).resolve()
    if not active_path.is_relative_to(output_root):
        raise DiagnosticPackageError("Feature Drift active pointer is outside generated data")
    if not active_path.is_file():
        return None
    try:
        active = json.loads(active_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DiagnosticPackageError("Feature Drift active pointer is invalid") from error
    package_relative = Path(str(active.get("packagePath", "")))
    if package_relative.is_absolute() or ".." in package_relative.parts:
        raise DiagnosticPackageError("Feature Drift active package path is unsafe")
    package = (root / package_relative).resolve()
    if not package.is_relative_to(output_root) or package.name != "feature_drift_package.zip" or not package.is_file():
        raise DiagnosticPackageError("Feature Drift active package is missing or outside generated data")
    archive_payload = package.read_bytes()
    if _sha256(archive_payload) != active.get("packageSha256"):
        raise DiagnosticPackageError("Feature Drift active package SHA-256 does not match its pointer")

    try:
        _, frozen_execution = _load_pinned_execution(root, config)
        training_path = _repo_file(root, config["sources"]["stage04_manifest"], "Stage 04 manifest")
        evaluation_path = _repo_file(root, config["sources"]["stage06_manifest"], "Stage 06 manifest")
        feature_path = _repo_file(root, config["sources"]["features"], "Feature Parquet")
        target_path = _repo_file(root, config["sources"]["labels"], "Target Parquet")
        training = _read_json_file(training_path, "Stage 04 training manifest")
        evaluation = _read_json_file(evaluation_path, "Stage 06 execution manifest")
    except Exception as error:
        raise DiagnosticPackageError(f"Feature Drift source identity cannot be checked: {error}") from error
    if _semantic_source_lineage(evaluation) != _semantic_source_lineage(frozen_execution):
        raise DiagnosticPackageError("Local Stage 06 source lineage differs from the frozen handoff")
    if training.get("source_lineage", {}).get("feature_parquet_sha256") != _sha256_file(feature_path):
        raise DiagnosticPackageError("Feature Parquet no longer matches Stage 04 lineage")
    if training.get("source_lineage", {}).get("target_parquet_sha256") != _sha256_file(target_path):
        raise DiagnosticPackageError("Target Parquet no longer matches Stage 04 lineage")
    lineage = evaluation.get("source_lineage", {})
    expected = {
        "evaluationId": config["evaluation_id"],
        "replayId": config["replay_id"],
        "strictCutoff": config["strict_cutoff"],
        "featureSetVersion": config["feature_set_version"],
        "featureRunId": lineage.get("feature_run_id"),
        "targetRunId": lineage.get("target_run_id"),
        "featureParquetSha256": _sha256_file(feature_path),
        "targetParquetSha256": _sha256_file(target_path),
    }
    verified = verify_diagnostic_archive(archive_payload, expected_identity=expected)
    if active.get("diagnosticId") != verified["manifest"].get("diagnosticId"):
        raise DiagnosticPackageError("Feature Drift active ID does not match the verified package")
    return publish_verified_archive(archive_payload, dist, expected_identity=expected)
