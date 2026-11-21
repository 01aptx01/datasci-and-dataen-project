#!/usr/bin/env python3
"""Verify the pinned Stage 06 handoff and emit only the Forecast UI CSV subset."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import re
import shutil
import stat
import subprocess
import sys
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any


class SnapshotError(RuntimeError):
    """Raised when the frozen source cannot be proven to be the pinned snapshot."""


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def parse_checksums(raw: bytes, source: str) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for line_number, line in enumerate(raw.decode("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        match = re.fullmatch(r"([a-fA-F0-9]{64})  (.+)", line)
        if not match:
            raise SnapshotError(f"{source}:{line_number} is not a SHA-256 checksum line")
        digest, name = match.groups()
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or "\\" in name:
            raise SnapshotError(f"{source}:{line_number} contains an unsafe path")
        if name in checksums:
            raise SnapshotError(f"{source} contains duplicate path {name}")
        checksums[name] = digest.lower()
    if not checksums:
        raise SnapshotError(f"{source} is empty")
    return checksums


def validate_archive_paths(archive: zipfile.ZipFile) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for info in archive.infolist():
        path = PurePosixPath(info.filename)
        if path.is_absolute() or ".." in path.parts or "\\" in info.filename:
            raise SnapshotError(f"Unsafe ZIP member path: {info.filename}")
        if info.filename in seen:
            raise SnapshotError(f"Duplicate ZIP member path: {info.filename}")
        seen.add(info.filename)
        file_type = stat.S_IFMT(info.external_attr >> 16)
        if file_type == stat.S_IFLNK:
            raise SnapshotError(f"ZIP symbolic links are not accepted: {info.filename}")
        if not info.is_dir():
            names.append(info.filename)
    return names


def parse_csv_bytes(payload: bytes, filename: str, expected_headers: list[str]) -> tuple[list[dict[str, str]], list[str]]:
    try:
        decoded = payload.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise SnapshotError(f"{filename} is not UTF-8") from error
    reader = csv.DictReader(io.StringIO(decoded, newline=""))
    headers = reader.fieldnames or []
    if headers != expected_headers:
        raise SnapshotError(f"{filename} header does not match the pinned schema")
    rows = list(reader)
    if any(None in row for row in rows):
        raise SnapshotError(f"{filename} contains a row with the wrong number of fields")
    return rows, headers


def number_or_none(value: str | None, field: str, row_number: int) -> float | None:
    if value is None or value == "":
        return None
    try:
        result = float(value)
    except ValueError as error:
        raise SnapshotError(f"Invalid {field} on CSV row {row_number}") from error
    if not math.isfinite(result) or result < 0:
        raise SnapshotError(f"Invalid nonnegative finite {field} on CSV row {row_number}")
    return result


def validate_status_row(row: dict[str, str], row_number: int) -> None:
    split = row["split"]
    if split not in {"validation", "test"}:
        raise SnapshotError(f"Unexpected split on forecast audit row {row_number}: {split}")
    if row["ticker"] not in {"SPY", "IEF", "GLD"}:
        raise SnapshotError(f"Unexpected ticker on forecast audit row {row_number}")
    if row["model_name"] not in {"CONSTANT_BASELINE", "ROLLING_20D_BASELINE", "STATIC_SGD", "ONLINE_SGD"}:
        raise SnapshotError(f"Unexpected model on forecast audit row {row_number}")
    actual = number_or_none(row["target_realized_vol_5d"], "target_realized_vol_5d", row_number)
    error = number_or_none(row["absolute_error"], "absolute_error", row_number)
    number_or_none(row["predicted_vol_annualized"], "predicted_vol_annualized", row_number)
    label = row["label_status"]
    forecast = row["forecast_status"]
    evaluation = row["evaluation_status"]
    mature = row["is_label_mature"].lower() == "true"
    if row["is_label_mature"].lower() not in {"true", "false"}:
        raise SnapshotError(f"Invalid is_label_mature on forecast audit row {row_number}")
    if label == "PENDING" or evaluation == "PENDING_LABEL":
        if label != "PENDING" or evaluation != "PENDING_LABEL" or mature or actual is not None or error is not None:
            raise SnapshotError(f"Pending forecast audit row {row_number} contains mature-label values or conflicting status")
    elif evaluation == "EVALUABLE":
        if label != "MATURE" or not mature or actual is None or error is None:
            raise SnapshotError(f"Evaluable forecast audit row {row_number} is missing mature source values")
    elif evaluation not in {"INVALID_FORECAST", "MISSING_FORECAST"}:
        raise SnapshotError(f"Unknown evaluation_status on forecast audit row {row_number}: {evaluation}")
    if forecast not in {"VALID", "INVALID", "MISSING"}:
        raise SnapshotError(f"Unknown forecast_status on forecast audit row {row_number}: {forecast}")


def validate_json_identity(
    identity: dict[str, Any], stage06: dict[str, Any], stage05: dict[str, Any], policy: dict[str, Any]
) -> None:
    expected = policy["identity"]
    evaluation_id = expected["evaluationId"]
    replay_id = expected["replayId"]
    if identity.get("source_verification_status") != "SOURCE VERIFIED":
        raise SnapshotError("source_identity.json is not marked SOURCE VERIFIED")
    if identity.get("evaluation_id") != evaluation_id or stage06.get("evaluation_id") != evaluation_id:
        raise SnapshotError("Evaluation ID does not match the pinned review snapshot")
    if stage06.get("input_identity_sha256") != evaluation_id:
        raise SnapshotError("Evaluation ID does not match the Stage 06 input identity")
    replay_ids = {
        identity.get("final_replay_experiment_id"),
        stage06.get("final_replay_experiment_id"),
        stage05.get("experiment_id"),
        stage05.get("compatibility_fingerprint"),
    }
    if replay_ids != {replay_id}:
        raise SnapshotError("Replay ID does not match across the frozen manifests")
    if identity.get("stage05_status") != "COMPLETED" or identity.get("stage06_status") != "COMPLETED":
        raise SnapshotError("Source identity does not show completed Stage 05 and Stage 06 runs")
    if stage06.get("status") != "COMPLETED" or stage05.get("status") != "COMPLETED":
        raise SnapshotError("Stage 05 or Stage 06 manifest is not COMPLETED")
    if stage06.get("stage") != "06_final_evaluation_testing_portfolio":
        raise SnapshotError("Pinned source is not a Stage 06 Final Evaluation")
    if identity.get("baseline_git_commit") != expected["baselineGitCommit"]:
        raise SnapshotError("Baseline Git commit does not match the pinned snapshot")
    if identity.get("source_point_in_time_availability_verified") is not False:
        raise SnapshotError("Source point-in-time availability status is inconsistent")
    config = stage06.get("evaluation_config", {})
    if config.get("data_cutoff") != expected["strictCutoff"] or config.get("test_end_date") != expected["strictCutoff"]:
        raise SnapshotError("Strict cutoff does not match the pinned review snapshot")
    if stage05.get("phase") != "FINAL_REPLAY":
        raise SnapshotError("Stage 05 manifest is not the final replay")


def verify_archive(repo_root: Path, policy: dict[str, Any]) -> tuple[dict[str, bytes], dict[str, Any], dict[str, Any], dict[str, Any]]:
    source = policy["source"]
    downloads = repo_root / "docs" / "ml-results" / "downloads"
    zip_path = downloads / source["zipName"]
    if not zip_path.is_file():
        raise SnapshotError(f"Handoff ZIP is missing: {zip_path}")
    outer_checksums = parse_checksums((downloads / "SHA256SUMS.txt").read_bytes(), "SHA256SUMS.txt")
    if outer_checksums.get(source["zipName"]) != source["zipSha256"]:
        raise SnapshotError("SHA256SUMS.txt does not match the pinned ZIP identity")
    zip_bytes = zip_path.read_bytes()
    if sha256(zip_bytes) != source["zipSha256"]:
        raise SnapshotError("Handoff ZIP SHA-256 mismatch")

    external_member_checksums = parse_checksums((downloads / "bundle-CHECKSUMS.sha256").read_bytes(), "bundle-CHECKSUMS.sha256")
    try:
        archive = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile as error:
        raise SnapshotError("Handoff ZIP is corrupt") from error
    with archive:
        archive_names = validate_archive_paths(archive)
        if "CHECKSUMS.sha256" not in archive_names:
            raise SnapshotError("Handoff ZIP does not include CHECKSUMS.sha256")
        internal_member_checksums = parse_checksums(archive.read("CHECKSUMS.sha256"), "ZIP CHECKSUMS.sha256")
        if internal_member_checksums != external_member_checksums:
            raise SnapshotError("Internal and published member checksum manifests disagree")
        if set(archive_names) != set(internal_member_checksums) | {"CHECKSUMS.sha256"}:
            raise SnapshotError("ZIP members do not match the published checksum list")
        for name, expected_digest in internal_member_checksums.items():
            if sha256(archive.read(name)) != expected_digest:
                raise SnapshotError(f"Handoff member SHA-256 mismatch: {name}")
        if any(internal_member_checksums.get(name) != digest for name, digest in policy["memberSha256"].items()):
            raise SnapshotError("Handoff member hashes differ from the pinned adapter policy")

        member_names = policy["members"]
        required = [member_names[key] for key in ("sourceIdentity", "executionManifest", "stage05Manifest", "forecastAudit", "evaluation")]
        for name in required:
            if name not in internal_member_checksums:
                raise SnapshotError(f"Required handoff member is missing: {name}")
        payloads = {name: archive.read(name) for name in required}

    identity = json.loads(payloads[member_names["sourceIdentity"]])
    stage06 = json.loads(payloads[member_names["executionManifest"]])
    stage05 = json.loads(payloads[member_names["stage05Manifest"]])
    if not all(isinstance(value, dict) for value in (identity, stage06, stage05)):
        raise SnapshotError("Handoff identity documents must be JSON objects")
    validate_json_identity(identity, stage06, stage05, policy)
    return payloads, identity, stage06, stage05


def validate_handoff_csvs(payloads: dict[str, bytes], policy: dict[str, Any]) -> tuple[list[str], list[dict[str, str]], list[dict[str, str]], dict[str, Any]]:
    members = policy["members"]
    headers = policy["expectedHeaders"]
    audit_rows, audit_headers = parse_csv_bytes(payloads[members["forecastAudit"]], members["forecastAudit"], headers["forecastAudit"])
    evaluation_rows, evaluation_headers = parse_csv_bytes(payloads[members["evaluation"]], members["evaluation"], headers["evaluation"])
    counts = policy["expectedCounts"]
    if len(audit_rows) != counts["forecastAuditRows"] or len(evaluation_rows) != counts["evaluationRows"]:
        raise SnapshotError("CSV row counts do not match the pinned review snapshot")

    prediction_ids: set[str] = set()
    for row_number, row in enumerate(audit_rows, start=2):
        if row["prediction_id"] in prediction_ids:
            raise SnapshotError(f"Duplicate prediction_id in forecast_audit.csv at row {row_number}")
        prediction_ids.add(row["prediction_id"])
        validate_status_row(row, row_number)

    test_rows = [row for row in audit_rows if row["split"] == "test"]
    evaluable_rows = [row for row in test_rows if row["evaluation_status"] == "EVALUABLE"]
    pending_rows = [row for row in test_rows if row["evaluation_status"] == "PENDING_LABEL"]
    if (len(test_rows), len(evaluable_rows), len(pending_rows)) != (
        counts["testForecastRows"], counts["testEvaluableRows"], counts["testPendingRows"]
    ):
        raise SnapshotError("Test, mature, or Pending row counts do not match the pinned experiment")

    evaluation_by_id: dict[str, dict[str, str]] = {}
    for row_number, row in enumerate(evaluation_rows, start=2):
        if row["split"] != "test":
            raise SnapshotError(f"evaluation.csv contains a non-Test row at {row_number}")
        prediction_id = row["prediction_id"]
        if prediction_id in evaluation_by_id:
            raise SnapshotError(f"Duplicate prediction_id in evaluation.csv at row {row_number}")
        evaluation_by_id[prediction_id] = row
        audit = next((item for item in evaluable_rows if item["prediction_id"] == prediction_id), None)
        if audit is None:
            raise SnapshotError(f"evaluation.csv has no matching evaluable audit row: {prediction_id}")
        for field in ("prediction_date", "ticker", "model_name", "target_start_date", "target_end_date"):
            if audit[field] != row[field]:
                raise SnapshotError(f"evaluation.csv field {field} disagrees with forecast_audit.csv for {prediction_id}")
        for field in ("predicted_vol_annualized", "target_realized_vol_5d", "absolute_error"):
            left = number_or_none(audit[field], field, 0)
            right = number_or_none(row[field], field, 0)
            if left is None or right is None or not math.isclose(left, right, rel_tol=0.0, abs_tol=1e-12):
                raise SnapshotError(f"evaluation.csv field {field} disagrees with forecast_audit.csv for {prediction_id}")
    if len(evaluation_by_id) != len(evaluable_rows):
        raise SnapshotError("evaluation.csv does not cover every evaluable Test audit row")

    summary = {
        "forecastAuditRows": len(audit_rows),
        "evaluationRows": len(evaluation_rows),
        "testForecastRows": len(test_rows),
        "testEvaluableRows": len(evaluable_rows),
        "testPendingRows": len(pending_rows),
        "recordedTestDates": len({row["prediction_date"] for row in test_rows}),
    }
    return audit_headers, audit_rows, evaluation_rows, {
        "headers": {"forecastAudit": audit_headers, "evaluation": evaluation_headers},
        "counts": summary,
    }


def current_commit(repo_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unavailable"


def safe_replace_generated_directory(target: Path, expected_evaluation_id: str, expected_zip_sha: str) -> None:
    if not target.exists():
        return
    if target.is_symlink() or not target.is_dir():
        raise SnapshotError(f"Refusing to replace unexpected snapshot output: {target}")
    marker = target / "dashboard_snapshot_manifest.json"
    if not marker.is_file():
        raise SnapshotError(f"Refusing to replace an unmarked existing directory: {target}")
    try:
        existing = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SnapshotError(f"Refusing to replace an invalid snapshot marker: {target}") from error
    if existing.get("evaluationId") != expected_evaluation_id or existing.get("sourceZipSha256") != expected_zip_sha:
        raise SnapshotError(f"Refusing to replace a different snapshot in {target}")
    expected_names = {"forecast_audit.csv", "evaluation.csv", "dashboard_snapshot_manifest.json"}
    if {path.name for path in target.iterdir()} != expected_names:
        raise SnapshotError(f"Refusing to replace unexpected files in {target}")
    for filename, member_key in (("forecast_audit.csv", "forecastAudit"), ("evaluation.csv", "evaluation")):
        artifact = existing.get("files", {}).get(member_key, {})
        digest = hashlib.sha256((target / filename).read_bytes()).hexdigest()
        if digest != artifact.get("sha256"):
            raise SnapshotError(f"Refusing to replace a modified generated artifact: {filename}")


def prepare_snapshot(repo_root: Path, output_root: Path, policy_path: Path) -> Path:
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    payloads, identity, stage06, stage05 = verify_archive(repo_root, policy)
    _audit_headers, _audit_rows, _evaluation_rows, table_summary = validate_handoff_csvs(payloads, policy)
    output_root.mkdir(parents=True, exist_ok=True)
    output_root = output_root.resolve()
    evaluation_id = policy["identity"]["evaluationId"]
    target = (output_root / evaluation_id).resolve()
    if target.parent != output_root or target.name != evaluation_id:
        raise SnapshotError("Snapshot output path escaped the requested public directory")
    safe_replace_generated_directory(target, evaluation_id, policy["source"]["zipSha256"])
    temporary = output_root / f".{evaluation_id}.tmp-{uuid.uuid4().hex}"
    temporary.mkdir()
    try:
        public_files: dict[str, dict[str, Any]] = {}
        for key, filename, member_key in (
            ("forecastAudit", policy["publicOutputs"]["forecastAudit"], "forecastAudit"),
            ("evaluation", policy["publicOutputs"]["evaluation"], "evaluation"),
        ):
            payload = payloads[policy["members"][member_key]]
            (temporary / filename).write_bytes(payload)
            public_files[key] = {
                "path": filename,
                "sha256": sha256(payload),
                "bytes": len(payload),
                "rowCount": table_summary["counts"]["forecastAuditRows" if key == "forecastAudit" else "evaluationRows"],
                "headers": table_summary["headers"][key],
            }

        manifest = {
            "schemaVersion": "1.0.0",
            "sourceRepository": policy["source"]["repository"],
            "sourceHandoffCommit": policy["source"]["handoffCommit"],
            "sourceMainCommitAtStart": policy["source"]["mainCommitAtStart"],
            "sourceZipName": policy["source"]["zipName"],
            "sourceZipSha256": policy["source"]["zipSha256"],
            "evaluationId": policy["identity"]["evaluationId"],
            "replayId": policy["identity"]["replayId"],
            "baselineGitCommit": identity["baseline_git_commit"],
            "sourceVerificationStatus": identity["source_verification_status"],
            "stage05Status": stage05["status"],
            "stage06Status": stage06["status"],
            "reportApproval": policy["identity"]["reportApproval"],
            "mode": "SIMULATED HISTORICAL REPLAY",
            "pointInTimeSourceAvailabilityVerified": identity["source_point_in_time_availability_verified"],
            "strictCutoff": policy["identity"]["strictCutoff"],
            "createdAtUtc": identity.get("created_at_utc", "unknown"),
            "builtFromCommit": current_commit(repo_root),
            "expectedCounts": table_summary["counts"],
            "files": public_files,
        }
        (temporary / "dashboard_snapshot_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        if target.exists():
            shutil.rmtree(target)
        os.replace(temporary, target)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path, default=Path("public/snapshots"))
    parser.add_argument("--policy", type=Path, default=Path(__file__).resolve().parents[1] / "snapshot.policy.json")
    arguments = parser.parse_args()
    repo_root = arguments.repo_root.resolve()
    output = arguments.output if arguments.output.is_absolute() else Path.cwd() / arguments.output
    try:
        target = prepare_snapshot(repo_root, output, arguments.policy.resolve())
    except (SnapshotError, OSError, json.JSONDecodeError, UnicodeDecodeError, zipfile.BadZipFile) as error:
        print(f"SNAPSHOT REJECTED: {error}", file=sys.stderr)
        return 1
    manifest = json.loads((target / "dashboard_snapshot_manifest.json").read_text(encoding="utf-8"))
    print(
        "SNAPSHOT VERIFIED: "
        f"evaluation_id={manifest['evaluationId']} "
        f"replay_id={manifest['replayId']} "
        f"zip_sha256={manifest['sourceZipSha256']} "
        f"test_pending_rows={manifest['expectedCounts']['testPendingRows']} "
        f"output={target}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
