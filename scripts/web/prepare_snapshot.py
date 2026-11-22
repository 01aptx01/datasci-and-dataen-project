#!/usr/bin/env python3
"""Verify the pinned Stage 06 handoff and emit only approved dashboard CSVs."""

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
    if any(None in row or any(value is None for value in row.values()) for row in rows):
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
    if row["model_name"] not in {"CONSTANT_BASELINE", "ROLLING_20D_BASELINE", "STATIC_SGD", "ONLINE_SGD", "HAR_X_OLS"}:
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


def signed_finite(value: str, field: str, row_number: int) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise SnapshotError(f"Invalid {field} on CSV row {row_number}") from error
    if not math.isfinite(result):
        raise SnapshotError(f"Invalid finite {field} on CSV row {row_number}")
    return result


def source_json(value: str, field: str, row_number: int) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError) as error:
        raise SnapshotError(f"Invalid JSON in {field} on CSV row {row_number}") from error


def source_bool(value: str, field: str, row_number: int) -> bool:
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    raise SnapshotError(f"Invalid boolean {field} on CSV row {row_number}")


def source_date(value: str, field: str, row_number: int) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise SnapshotError(f"Invalid {field} date on CSV row {row_number}")
    return value


def portfolio_volatility(matrix: list[list[float]], weights: list[float], row_number: int) -> float:
    if len(matrix) != 3 or any(len(row) != 3 for row in matrix) or len(weights) != 3:
        raise SnapshotError(f"portfolio covariance/weight dimensions are invalid on CSV row {row_number}")
    if any(not math.isfinite(value) for row in matrix for value in row) or any(not math.isfinite(value) or value < 0 for value in weights):
        raise SnapshotError(f"portfolio covariance/weights contain invalid values on CSV row {row_number}")
    if abs(sum(weights) - 1) > 1e-10:
        raise SnapshotError(f"Stored portfolio weights do not sum to one on CSV row {row_number}")
    if any(abs(matrix[row][column] - matrix[column][row]) > 1e-10 for row in range(3) for column in range(row + 1, 3)):
        raise SnapshotError(f"portfolio covariance is not symmetric on CSV row {row_number}")
    a, b, c = matrix[0][0], matrix[1][1], matrix[2][2]
    d, e, f = matrix[0][1], matrix[0][2], matrix[1][2]
    minors = (a * b - d * d, a * c - e * e, b * c - f * f)
    determinant = a * (b * c - f * f) - d * (d * c - e * f) + e * (d * f - b * e)
    if min(a, b, c, *minors, determinant) < -1e-10:
        raise SnapshotError(f"portfolio covariance is not positive semidefinite on CSV row {row_number}")
    variance = sum(weights[row] * weights[column] * matrix[row][column] for row in range(3) for column in range(3))
    if not math.isfinite(variance) or variance < -1e-10:
        raise SnapshotError(f"portfolio variance is invalid on CSV row {row_number}")
    return math.sqrt(max(0.0, variance))


def validate_d4_d5_sources(
    audit_rows: list[dict[str, str]], evaluation_rows: list[dict[str, str]],
    sources: dict[str, list[dict[str, str]]], policy: dict[str, Any],
) -> None:
    models = {"CONSTANT_BASELINE", "ROLLING_20D_BASELINE", "STATIC_SGD", "ONLINE_SGD", "HAR_X_OLS"}
    tickers = {"SPY", "IEF", "GLD"}
    audit_by_scope = {(row["split"], row["prediction_date"], row["ticker"], row["model_name"]): row for row in audit_rows}
    portfolio_keys: set[tuple[str, str, str]] = set()
    for row_number, row in enumerate(sources["portfolioRisk"], start=2):
        key = (row["split"], row["prediction_date"], row["model_name"])
        if key in portfolio_keys or row["split"] not in {"test", "validation"} or row["model_name"] not in models:
            raise SnapshotError(f"Unsupported or duplicate portfolio_risk.csv scope on row {row_number}")
        portfolio_keys.add(key)
        source_date(row["prediction_date"], "prediction_date", row_number)
        if row["split"] == "test" and row["prediction_date"] > policy["identity"]["strictCutoff"]:
            raise SnapshotError(f"portfolio_risk.csv exceeds the strict cutoff on row {row_number}")
        if row["prediction_mode"] != "HISTORICAL_REPLAY":
            raise SnapshotError(f"portfolio_risk.csv contains an unsupported prediction mode on row {row_number}")
        if not row["replay_run_id"] or not row["correlation_run_id"] or not re.fullmatch(r"[a-fA-F0-9]{64}", row["input_snapshot_id"]):
            raise SnapshotError(f"portfolio_risk.csv is missing source lineage on row {row_number}")
        missing = source_json(row["missing_inputs"], "missing_inputs", row_number)
        matrix = source_json(row["covariance_matrix"], "covariance_matrix", row_number)
        if not isinstance(missing, list) or any(not isinstance(item, str) for item in missing) or not isinstance(matrix, list) or any(not isinstance(item, list) for item in matrix):
            raise SnapshotError(f"portfolio_risk.csv JSON fields are malformed on row {row_number}")
        weights = [number_or_none(row[f"weight_{ticker.lower()}"], f"weight_{ticker.lower()}", row_number) for ticker in ("SPY", "IEF", "GLD")]
        forecast_values = [number_or_none(row[f"{ticker.lower()}_forecast_vol_annualized"], f"{ticker.lower()}_forecast_vol_annualized", row_number) for ticker in ("SPY", "IEF", "GLD")]
        forecast_statuses = [row[f"{ticker.lower()}_forecast_status"] for ticker in ("SPY", "IEF", "GLD")]
        if any(status not in {"VALID", "INVALID", "MISSING"} for status in forecast_statuses) or any((status == "VALID") != (value is not None) for status, value in zip(forecast_statuses, forecast_values)):
            raise SnapshotError(f"portfolio_risk.csv forecast statuses disagree with values on row {row_number}")
        if row["portfolio_status"] == "OK":
            if missing or not source_bool(row["is_corr_ready"], "is_corr_ready", row_number) or any(status != "VALID" for status in forecast_statuses):
                raise SnapshotError(f"An OK portfolio row has incomplete inputs on row {row_number}")
            parsed_matrix = [[signed_finite(str(value), "covariance_matrix", row_number) for value in matrix_row] for matrix_row in matrix]
            if any(len(matrix_row) != 3 for matrix_row in parsed_matrix):
                raise SnapshotError(f"portfolio covariance dimensions are invalid on row {row_number}")
            calculated = portfolio_volatility(parsed_matrix, [value or 0.0 for value in weights], row_number)
            stored = number_or_none(row["portfolio_vol_annualized"], "portfolio_vol_annualized", row_number)
            if stored is None or not math.isclose(calculated, stored, rel_tol=0.0, abs_tol=1e-10):
                raise SnapshotError(f"Stored portfolio value does not match covariance and source weights on row {row_number}")
            for ticker, value, status in zip(("SPY", "IEF", "GLD"), forecast_values, forecast_statuses):
                audit = audit_by_scope.get((row["split"], row["prediction_date"], ticker, row["model_name"]))
                if audit is None or audit["forecast_status"] != status or not math.isclose(number_or_none(audit["predicted_vol_annualized"], "predicted_vol_annualized", 0) or -1, value or -2, rel_tol=0.0, abs_tol=1e-12):
                    raise SnapshotError(f"portfolio forecast inputs do not match forecast_audit.csv on row {row_number}")
        else:
            raise SnapshotError(f"Unexpected portfolio_status on source row {row_number}: {row['portfolio_status']}")

    rolling_keys: set[tuple[str, str, str, str]] = set()
    for row_number, row in enumerate(sources["rollingMae20"], start=2):
        key = (row["split"], row["ticker"], row["model_name"], row["window_end"])
        if key in rolling_keys or row["split"] not in {"test", "validation"} or row["ticker"] not in tickers or row["model_name"] not in models:
            raise SnapshotError(f"Unsupported or duplicate rolling_mae20.csv row {row_number}")
        rolling_keys.add(key)
        start = source_date(row["window_start"], "window_start", row_number)
        end = source_date(row["window_end"], "window_end", row_number)
        window_sessions, expected_n, evaluable_n = (int(row[field]) for field in ("window_session_count", "expected_anchor_count", "evaluable_count"))
        coverage = signed_finite(row["coverage"], "coverage", row_number)
        if start > end or window_sessions != 20 or expected_n <= 0 or not 0 < evaluable_n <= expected_n or not math.isclose(coverage, evaluable_n / expected_n, rel_tol=0.0, abs_tol=1e-10):
            raise SnapshotError(f"rolling_mae20.csv source window/count/coverage is inconsistent on row {row_number}")
        number_or_none(row["mae"], "mae", row_number)
        number_or_none(row["rmse"], "rmse", row_number)

    evaluations_by_id = {row["prediction_id"]: row for row in evaluation_rows if row["model_name"] == "ONLINE_SGD"}
    drift_ids: set[str] = set()
    for row_number, row in enumerate(sources["driftErrorTimeline"], start=2):
        prediction_id = row["prediction_id"]
        if prediction_id in drift_ids:
            raise SnapshotError(f"Duplicate prediction ID in drift_error_timeline.csv row {row_number}")
        drift_ids.add(prediction_id)
        evaluation = evaluations_by_id.get(prediction_id)
        if evaluation is None or evaluation["ticker"] != row["ticker"] or evaluation["prediction_date"] != row["prediction_date"]:
            raise SnapshotError(f"Drift row does not match a B3 Test evaluation at row {row_number}")
        if not math.isclose(signed_finite(row["absolute_error_evaluation"], "absolute_error_evaluation", row_number), float(evaluation["absolute_error"]), rel_tol=0.0, abs_tol=1e-12):
            raise SnapshotError(f"Drift error disagrees with evaluation.csv on row {row_number}")
        signed_finite(row["absolute_error_adwin"], "absolute_error_adwin", row_number)
        if source_bool(row["drift_detected"], "drift_detected", row_number) or source_bool(row["alert_record_present"], "alert_record_present", row_number):
            raise SnapshotError("Pinned B3 Test drift source contains an unapproved alert event")
        if signed_finite(row["adwin_delta"], "adwin_delta", row_number) <= 0 or int(row["adwin_width"]) <= 0:
            raise SnapshotError(f"Invalid ADWIN diagnostics on row {row_number}")
        signed_finite(row["adwin_estimation"], "adwin_estimation", row_number)
    if drift_ids != set(evaluations_by_id):
        raise SnapshotError("Drift timeline does not cover the verified B3 Test evaluation set")

    h1_results = sources["h1Results"]
    h1_by_ticker: dict[str, dict[str, str]] = {}
    for row_number, row in enumerate(h1_results, start=2):
        if row["ticker"] not in tickers or row["ticker"] in h1_by_ticker:
            raise SnapshotError(f"Unsupported or duplicate H1 result at row {row_number}")
        h1_by_ticker[row["ticker"]] = row
        if int(row["n"]) <= 0 or int(row["n"]) != int(row["expected_n"]) or int(row["hac_lag"]) != 5:
            raise SnapshotError(f"H1 primary results must use the complete Train sample and HAC lag 5 on row {row_number}")
        for field in ("beta", "intercept", "hac_se", "test_statistic", "p_raw_one_sided", "p_holm", "ci95_lower", "ci95_upper"):
            signed_finite(row[field], field, row_number)

    scatter_counts: dict[str, int] = {ticker: 0 for ticker in tickers}
    scatter_keys: set[tuple[str, str]] = set()
    for row_number, row in enumerate(sources["h1ScatterData"], start=2):
        if row["split"] != "train" or row["ticker"] not in tickers:
            raise SnapshotError(f"H1 scatter data must be Train-only on row {row_number}")
        key = (row["date"], row["ticker"])
        if key in scatter_keys:
            raise SnapshotError(f"Duplicate H1 scatter observation on row {row_number}")
        scatter_keys.add(key)
        source_date(row["date"], "date", row_number)
        source_date(row["target_end_date"], "target_end_date", row_number)
        signed_finite(row["rv_5d"], "rv_5d", row_number)
        signed_finite(row["target_realized_vol_5d"], "target_realized_vol_5d", row_number)
        scatter_counts[row["ticker"]] += 1
    if set(h1_by_ticker) != tickers or any(scatter_counts[ticker] != int(h1_by_ticker[ticker]["n"]) for ticker in tickers):
        raise SnapshotError("H1 scatter sample counts do not match H1_results.csv")

    sensitivity_keys: set[tuple[str, int]] = set()
    for row_number, row in enumerate(sources["h1Sensitivity"], start=2):
        lag, n = int(row["hac_maxlags"]), int(row["n"])
        key = (row["ticker"], lag)
        if row["ticker"] not in tickers or lag not in {5, 10, 20} or key in sensitivity_keys or row["status"] != "computed":
            raise SnapshotError(f"Unsupported or duplicate H1 sensitivity row {row_number}")
        sensitivity_keys.add(key)
        for field in ("beta", "intercept", "hac_se", "test_statistic", "p_raw_one_sided", "ci95_lower", "ci95_upper"):
            signed_finite(row[field], field, row_number)
        if n != int(h1_by_ticker[row["ticker"]]["n"]):
            raise SnapshotError(f"H1 sensitivity sample size differs from the primary row on {row_number}")
        if lag == 5 and not math.isclose(float(row["beta"]), float(h1_by_ticker[row["ticker"]]["beta"]), rel_tol=0.0, abs_tol=1e-12):
            raise SnapshotError(f"H1 sensitivity lag 5 does not match the primary estimate on row {row_number}")

    hypothesis_keys: set[tuple[str, str]] = set()
    for row_number, row in enumerate(sources["hypothesisResults"], start=2):
        key = (row["hypothesis_id"], row["ticker_or_macro"])
        expected_split = "train" if row["hypothesis_id"] == "H1" else "test"
        if key in hypothesis_keys or row["dataset_split"] != expected_split or (row["hypothesis_id"] == "H1" and row["ticker_or_macro"] not in tickers) or (row["hypothesis_id"] in {"H2", "H3"} and row["ticker_or_macro"] != "MACRO"):
            raise SnapshotError(f"Hypothesis split/ticker identity is inconsistent on row {row_number}")
        hypothesis_keys.add(key)
        ticker_counts = source_json(row["paired_n_by_ticker"], "paired_n_by_ticker", row_number)
        interval = source_json(row["confidence_interval_95"], "confidence_interval_95", row_number)
        if not isinstance(ticker_counts, dict) or any(ticker not in tickers or not isinstance(n, int) or n < 0 for ticker, n in ticker_counts.items()) or not ticker_counts or not isinstance(interval, list) or len(interval) != 2:
            raise SnapshotError(f"Hypothesis nested JSON values are malformed on row {row_number}")
        for field in ("alpha", "test_statistic", "effect_size", "raw_p_value", "adjusted_p_value", "confidence_interval_95"):
            if field == "confidence_interval_95":
                for item in interval:
                    signed_finite(str(item), field, row_number)
            else:
                value = signed_finite(row[field], field, row_number)
                if field in {"alpha", "raw_p_value", "adjusted_p_value"} and not 0 <= value <= 1:
                    raise SnapshotError(f"Invalid hypothesis probability value on row {row_number}")
        if int(row["n_paired"]) > int(row["n_expected"]):
            raise SnapshotError(f"Hypothesis paired sample exceeds expected sample on row {row_number}")
    expected_hypothesis_keys = {("H1", ticker) for ticker in tickers} | {("H2", "MACRO"), ("H3", "MACRO")}
    if hypothesis_keys != expected_hypothesis_keys:
        raise SnapshotError("Hypothesis source does not contain the required H1–H3 rows")

    bootstrap_keys: set[tuple[str, int]] = set()
    for row_number, row in enumerate(sources["bootstrapDiagnostics"], start=2):
        key = (row["hypothesis_id"], int(row["block_length_xnys_sessions"]))
        if key[0] not in {"H2", "H3"} or key[1] not in {5, 20} or key in bootstrap_keys or row["status"] != "COMPUTED":
            raise SnapshotError(f"Unsupported or duplicate bootstrap diagnostic row {row_number}")
        bootstrap_keys.add(key)
        nested = source_json(row["n_by_ticker"], "n_by_ticker", row_number)
        if not isinstance(nested, dict) or set(nested) != tickers or any(not isinstance(n, int) or n <= 0 for n in nested.values()):
            raise SnapshotError(f"Bootstrap ticker counts are malformed on row {row_number}")
        for field in ("observed_delta", "bootstrap_standard_error", "ci95_lower", "ci95_upper", "p_raw_one_sided"):
            signed_finite(row[field], field, row_number)
    if bootstrap_keys != {(hypothesis, lag) for hypothesis in ("H2", "H3") for lag in (5, 20)}:
        raise SnapshotError("Bootstrap diagnostic source does not contain H2/H3 sensitivity lags 5 and 20")

    high_vol_keys: set[tuple[str, str, str]] = set()
    for row_number, row in enumerate(sources["highVolatilityMetrics"], start=2):
        key = (row["split"], row["ticker"], row["model_name"])
        if row["split"] not in {"test", "validation"} or row["ticker"] not in tickers or row["model_name"] not in models or key in high_vol_keys:
            raise SnapshotError(f"Unsupported or duplicate high-volatility row {row_number}")
        high_vol_keys.add(key)
        if int(row["threshold_train_n"]) <= 0:
            raise SnapshotError(f"High-volatility threshold sample is missing on row {row_number}")
        count = int(row["high_vol_target_anchor_count"])
        evaluable = int(row["high_vol_common_evaluable_n"])
        if evaluable > count:
            raise SnapshotError(f"High-volatility evaluable count exceeds the subset on row {row_number}")
        if evaluable == 0:
            if any(row[field].strip() for field in ("mae", "rmse", "evaluation_coverage")):
                raise SnapshotError(f"Zero-sample high-volatility row must keep metrics blank on row {row_number}")
        else:
            for field in ("mae", "rmse", "evaluation_coverage"):
                number_or_none(row[field], field, row_number)
        if row["split"] == "test" and row["ticker"] == "IEF" and (count != 0 or evaluable != 0 or any(row[field].strip() for field in ("mae", "rmse", "evaluation_coverage"))):
            raise SnapshotError("IEF Test high-volatility metrics must remain blank at n=0")


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
    downloads = repo_root / source.get("zipDir", "docs/ml-results/downloads")
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
        required = [member_names[key] for key in (
            "sourceIdentity", "executionManifest", "stage05Manifest", "forecastAudit", "evaluation",
            "modelMetrics", "pairComparisons", "coverage", "portfolioRisk", "rollingMae20", "driftErrorTimeline",
            "h1ScatterData", "h1Results", "h1Sensitivity", "hypothesisResults", "bootstrapDiagnostics", "highVolatilityMetrics",
        )] + [member_names[k] for k in ("b4Comparisons", "referenceB0B3Metrics") if k in member_names]
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


def validate_b4_comparisons(
    audit_rows: list[dict[str, str]],
    evaluation_rows: list[dict[str, str]],
    comparison_rows: list[dict[str, str]],
) -> None:
    tickers = ("SPY", "IEF", "GLD")
    models = ("CONSTANT_BASELINE", "ROLLING_20D_BASELINE", "STATIC_SGD", "ONLINE_SGD", "HAR_X_OLS")
    comparator_by_id = {
        "B4_VS_B2": "STATIC_SGD",
        "B4_VS_B3": "ONLINE_SGD",
        "B4_VS_B1": "ROLLING_20D_BASELINE",
    }
    expected_scopes = {(comparison_id, ticker) for comparison_id in comparator_by_id for ticker in (*tickers, "MACRO")}
    row_by_scope: dict[tuple[str, str], tuple[int, dict[str, str]]] = {}
    for row_number, row in enumerate(comparison_rows, start=2):
        scope = (row["comparison_id"], row["ticker"])
        if scope not in expected_scopes or scope in row_by_scope:
            raise SnapshotError(f"Unsupported or duplicate B4 comparison scope on row {row_number}")
        comparator = comparator_by_id[scope[0]]
        expected_pairing = "equal ETF weight over per-ETF paired anchors" if scope[1] == "MACRO" else "same prediction_date/ticker/split with mature target and both forecasts valid"
        if (
            row["split"] != "test"
            or row["b4_model"] != "HAR_X_OLS"
            or row["comparator_model"] != comparator
            or row["direction_definition"] != "comparator_mae_minus_b4_mae (positive means HAR_X_OLS lower error)"
            or row["evaluation_scope"] != "retrospective_test_non_hypothesis"
            or row["pairing_policy"] != expected_pairing
        ):
            raise SnapshotError(f"B4 comparison identity or semantics are inconsistent on row {row_number}")
        row_by_scope[scope] = (row_number, row)
    if set(row_by_scope) != expected_scopes:
        raise SnapshotError("b4_comparisons.csv does not contain the complete comparison scope")

    evaluation_by_scope: dict[tuple[str, str, str], dict[str, str]] = {}
    for row_number, row in enumerate(evaluation_rows, start=2):
        key = (row["prediction_date"], row["ticker"], row["model_name"])
        if key in evaluation_by_scope:
            raise SnapshotError(f"Duplicate evaluation model/date/ticker scope on row {row_number}")
        evaluation_by_scope[key] = row
    expected_dates = {
        ticker: {row["prediction_date"] for row in audit_rows if row["split"] == "test" and row["ticker"] == ticker}
        for ticker in tickers
    }
    all_five_n = {
        ticker: sum(all((date, ticker, model) in evaluation_by_scope for model in models) for date in expected_dates[ticker])
        for ticker in tickers
    }
    base_four_n = {
        ticker: sum(all((date, ticker, model) in evaluation_by_scope for model in models[:4]) for date in expected_dates[ticker])
        for ticker in tickers
    }

    def close(actual: float, expected: float, field: str, row_number: int) -> None:
        if not math.isclose(actual, expected, rel_tol=0.0, abs_tol=1e-9):
            raise SnapshotError(f"B4 comparison {field} does not reconcile with evaluation.csv on row {row_number}")

    for comparison_id, comparator in comparator_by_id.items():
        summaries: dict[str, dict[str, float | int]] = {}
        for ticker in tickers:
            pairs = [
                (evaluation_by_scope[(date, ticker, "HAR_X_OLS")], evaluation_by_scope[(date, ticker, comparator)])
                for date in expected_dates[ticker]
                if (date, ticker, "HAR_X_OLS") in evaluation_by_scope and (date, ticker, comparator) in evaluation_by_scope
            ]
            if not pairs:
                raise SnapshotError(f"B4 comparison {comparison_id}/{ticker} has no paired evaluations")
            for b4, baseline in pairs:
                if b4["target_realized_vol_5d"] != baseline["target_realized_vol_5d"] or b4["target_end_date"] != baseline["target_end_date"]:
                    raise SnapshotError(f"B4 comparison {comparison_id}/{ticker} has mismatched paired target windows")
            b4_errors = [float(b4["absolute_error"]) for b4, _ in pairs]
            baseline_errors = [float(baseline["absolute_error"]) for _, baseline in pairs]
            summaries[ticker] = {
                "paired_n": len(pairs),
                "expected_n": len(expected_dates[ticker]),
                "b4_mae": sum(b4_errors) / len(pairs),
                "comparator_mae": sum(baseline_errors) / len(pairs),
                "b4_rmse": math.sqrt(sum(error * error for error in b4_errors) / len(pairs)),
                "comparator_rmse": math.sqrt(sum(error * error for error in baseline_errors) / len(pairs)),
            }
        macro = {
            "paired_n": sum(int(summaries[ticker]["paired_n"]) for ticker in tickers),
            "expected_n": sum(int(summaries[ticker]["expected_n"]) for ticker in tickers),
            "b4_mae": sum(float(summaries[ticker]["b4_mae"]) for ticker in tickers) / len(tickers),
            "comparator_mae": sum(float(summaries[ticker]["comparator_mae"]) for ticker in tickers) / len(tickers),
        }
        summaries["MACRO"] = macro
        for ticker, summary in summaries.items():
            row_number, row = row_by_scope[(comparison_id, ticker)]
            paired_n = int(row["paired_n"])
            expected_n = int(row["expected_eligible_anchor_count"])
            if paired_n != int(summary["paired_n"]) or expected_n != int(summary["expected_n"]):
                raise SnapshotError(f"B4 comparison counts do not match paired evaluations on row {row_number}")
            b4_mae = number_or_none(row["b4_mae"], "b4_mae", row_number)
            comparator_mae = number_or_none(row["comparator_mae"], "comparator_mae", row_number)
            delta = signed_finite(row["delta_mae_comparator_minus_b4"], "delta_mae_comparator_minus_b4", row_number)
            relative = signed_finite(row["relative_improvement_pct"], "relative_improvement_pct", row_number)
            coverage = number_or_none(row["paired_coverage"], "paired_coverage", row_number)
            if None in (b4_mae, comparator_mae, coverage):
                raise SnapshotError(f"B4 comparison summary is incomplete on row {row_number}")
            close(float(b4_mae), float(summary["b4_mae"]), "b4_mae", row_number)
            close(float(comparator_mae), float(summary["comparator_mae"]), "comparator_mae", row_number)
            expected_delta = float(summary["comparator_mae"]) - float(summary["b4_mae"])
            close(delta, expected_delta, "delta_mae_comparator_minus_b4", row_number)
            close(float(coverage), paired_n / expected_n, "paired_coverage", row_number)
            if float(comparator_mae) == 0:
                raise SnapshotError(f"B4 comparison relative improvement is undefined on row {row_number}")
            close(relative, expected_delta / float(summary["comparator_mae"]) * 100.0, "relative_improvement_pct", row_number)
            common_all = sum(all_five_n.values()) if ticker == "MACRO" else all_five_n[ticker]
            common_base = sum(base_four_n.values()) if ticker == "MACRO" else base_four_n[ticker]
            if int(row["common_all_five_n"]) != common_all or int(row["common_b0_b3_n"]) != common_base:
                raise SnapshotError(f"B4 comparison reference panel counts do not match evaluation.csv on row {row_number}")
            if ticker == "MACRO":
                if row["b4_rmse"] or row["comparator_rmse"]:
                    raise SnapshotError(f"Macro B4 comparison RMSE fields must be blank on row {row_number}")
            else:
                b4_rmse = number_or_none(row["b4_rmse"], "b4_rmse", row_number)
                comparator_rmse = number_or_none(row["comparator_rmse"], "comparator_rmse", row_number)
                close(float(b4_rmse or 0.0), float(summary["b4_rmse"]), "b4_rmse", row_number)
                close(float(comparator_rmse or 0.0), float(summary["comparator_rmse"]), "comparator_rmse", row_number)


def validate_handoff_csvs(payloads: dict[str, bytes], policy: dict[str, Any]) -> tuple[list[str], list[dict[str, str]], list[dict[str, str]], dict[str, Any]]:
    members = policy["members"]
    headers = policy["expectedHeaders"]
    audit_rows, audit_headers = parse_csv_bytes(payloads[members["forecastAudit"]], members["forecastAudit"], headers["forecastAudit"])
    evaluation_rows, evaluation_headers = parse_csv_bytes(payloads[members["evaluation"]], members["evaluation"], headers["evaluation"])
    model_metric_rows, model_metric_headers = parse_csv_bytes(payloads[members["modelMetrics"]], members["modelMetrics"], headers["modelMetrics"])
    pair_rows, pair_headers = parse_csv_bytes(payloads[members["pairComparisons"]], members["pairComparisons"], headers["pairComparisons"])
    coverage_rows, coverage_headers = parse_csv_bytes(payloads[members["coverage"]], members["coverage"], headers["coverage"])
    counts = policy["expectedCounts"]
    if len(audit_rows) != counts["forecastAuditRows"] or len(evaluation_rows) != counts["evaluationRows"]:
        raise SnapshotError("CSV row counts do not match the pinned review snapshot")
    if len(model_metric_rows) != counts["modelMetricsRows"] or len(pair_rows) != counts["pairComparisonsRows"] or len(coverage_rows) != counts["coverageRows"]:
        raise SnapshotError("D3 model or coverage CSV row counts do not match the pinned review snapshot")

    additional_keys = [
        "portfolioRisk", "rollingMae20", "driftErrorTimeline", "h1ScatterData", "h1Results", "h1Sensitivity",
        "hypothesisResults", "bootstrapDiagnostics", "highVolatilityMetrics",
    ]
    for optional_key in ("b4Comparisons", "referenceB0B3Metrics"):
        if optional_key in members:
            additional_keys.append(optional_key)
    additional_rows: dict[str, list[dict[str, str]]] = {}
    additional_headers: dict[str, list[str]] = {}
    for key in additional_keys:
        rows, actual_headers = parse_csv_bytes(payloads[members[key]], members[key], headers[key])
        additional_rows[key] = rows
        additional_headers[key] = actual_headers
        if len(rows) != counts[f"{key}Rows"]:
            raise SnapshotError(f"{members[key]} row count does not match the pinned review snapshot")

    validate_d4_d5_sources(audit_rows, evaluation_rows, additional_rows, policy)
    if "b4Comparisons" in additional_rows:
        validate_b4_comparisons(audit_rows, evaluation_rows, additional_rows["b4Comparisons"])

    models = {"CONSTANT_BASELINE", "ROLLING_20D_BASELINE", "STATIC_SGD", "ONLINE_SGD", "HAR_X_OLS"}
    tickers = {"SPY", "IEF", "GLD"}
    macro_tickers = tickers | {"MACRO"}
    metric_keys: set[tuple[str, str, str]] = set()
    for row_number, row in enumerate(model_metric_rows, start=2):
        if row["split"] != "test":
            raise SnapshotError(f"model_metrics.csv is Test-only (row {row_number})")
        if row["ticker"] not in macro_tickers or row["model_name"] not in models:
            raise SnapshotError(f"Unsupported model/ticker in model_metrics.csv row {row_number}")
        key = (row["split"], row["ticker"], row["model_name"])
        if key in metric_keys:
            raise SnapshotError(f"Duplicate model_metrics.csv row {row_number}")
        metric_keys.add(key)
        try:
            paired_n = int(row["paired_n"])
            expected_n = int(row["expected_eligible_anchor_count"])
        except ValueError as error:
            raise SnapshotError(f"Invalid model metric count on row {row_number}") from error
        if paired_n <= 0 or expected_n <= 0 or paired_n > expected_n:
            raise SnapshotError(f"Inconsistent model metric count on row {row_number}")
        number_or_none(row["mae"], "mae", row_number)
        number_or_none(row["rmse"], "rmse", row_number)
        if not row["comparison_panel"].strip():
            raise SnapshotError(f"Missing comparison_panel on model_metrics.csv row {row_number}")

    baseline_by_comparison = {
        "B0": "CONSTANT_BASELINE", "B1": "ROLLING_20D_BASELINE", "B2": "STATIC_SGD",
        "H2": "STATIC_SGD", "H3": "ROLLING_20D_BASELINE",
    }
    pair_keys: set[tuple[str, str]] = set()
    for row_number, row in enumerate(pair_rows, start=2):
        comparison = row["comparison_id"]
        if comparison not in baseline_by_comparison or row["baseline_model"] != baseline_by_comparison[comparison] or row["online_model"] != "ONLINE_SGD":
            raise SnapshotError(f"Pair comparison identity is inconsistent on row {row_number}")
        if row["ticker"] not in macro_tickers:
            raise SnapshotError(f"Unsupported ticker in pair_comparisons.csv row {row_number}")
        key = (comparison, row["ticker"])
        if key in pair_keys:
            raise SnapshotError(f"Duplicate pair_comparisons.csv row {row_number}")
        pair_keys.add(key)
        try:
            paired_n = int(row["paired_n"])
            common_n = int(row["common_all_four_n"])
            signed_values = [float(row[field]) for field in ("delta_mae_baseline_minus_online", "relative_improvement_pct")]
        except ValueError as error:
            raise SnapshotError(f"Invalid paired comparison value on row {row_number}") from error
        if paired_n <= 0 or common_n > paired_n or not all(math.isfinite(value) for value in signed_values):
            raise SnapshotError(f"Inconsistent paired comparison value on row {row_number}")
        for field in ("baseline_mae", "online_mae"):
            number_or_none(row[field], field, row_number)
        baseline_rmse = number_or_none(row["baseline_rmse"], "baseline_rmse", row_number)
        online_rmse = number_or_none(row["online_rmse"], "online_rmse", row_number)
        if (row["ticker"] == "MACRO") != (baseline_rmse is None and online_rmse is None):
            raise SnapshotError(f"Macro RMSE must remain blank while ETF RMSE is present on pair row {row_number}")

    coverage_keys: set[tuple[str, str, str]] = set()
    for row_number, row in enumerate(coverage_rows, start=2):
        if row["split"] not in {"test", "validation"} or row["ticker"] not in tickers or row["model_name"] not in models:
            raise SnapshotError(f"Unsupported split/model/ticker in coverage.csv row {row_number}")
        key = (row["split"], row["ticker"], row["model_name"])
        if key in coverage_keys:
            raise SnapshotError(f"Duplicate coverage.csv row {row_number}")
        coverage_keys.add(key)
        count_fields = (
            "expected_eligible_prediction_anchors", "forecast_success_count", "invalid_forecast_count",
            "missing_forecast_count", "mature_target_count", "pending_label_count",
            "invalid_or_missing_target_count", "mature_evaluable_count", "common_panel_count",
        )
        try:
            row_counts = {field: int(row[field]) for field in count_fields}
            coverage_rates = [float(row[field]) for field in ("forecast_coverage", "evaluation_coverage")]
        except ValueError as error:
            raise SnapshotError(f"Invalid coverage value on row {row_number}") from error
        if any(value < 0 for value in row_counts.values()) or any(not math.isfinite(value) or value < 0 or value > 1 for value in coverage_rates):
            raise SnapshotError(f"Invalid nonnegative coverage value on row {row_number}")
        forecast_count = row_counts["forecast_success_count"] + row_counts["invalid_forecast_count"] + row_counts["missing_forecast_count"]
        target_count = row_counts["mature_target_count"] + row_counts["pending_label_count"] + row_counts["invalid_or_missing_target_count"]
        if forecast_count != row_counts["expected_eligible_prediction_anchors"] or target_count != row_counts["expected_eligible_prediction_anchors"]:
            raise SnapshotError(f"Coverage counts do not reconcile on row {row_number}")
        if row_counts["mature_evaluable_count"] > row_counts["mature_target_count"] or row_counts["common_panel_count"] > row_counts["mature_evaluable_count"]:
            raise SnapshotError(f"Coverage maturity counts are inconsistent on row {row_number}")

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
        "modelMetricsRows": len(model_metric_rows),
        "pairComparisonsRows": len(pair_rows),
        "coverageRows": len(coverage_rows),
        **{f"{key}Rows": len(additional_rows[key]) for key in additional_keys},
        "recordedTestDates": len({row["prediction_date"] for row in test_rows}),
    }
    return audit_headers, audit_rows, evaluation_rows, {
        "headers": {
            "forecastAudit": audit_headers, "evaluation": evaluation_headers,
            "modelMetrics": model_metric_headers, "pairComparisons": pair_headers, "coverage": coverage_headers,
            **additional_headers,
        },
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
    public_outputs = existing.get("files", {})
    approved_names = {
        "forecast_audit.csv", "evaluation.csv", "model_metrics.csv", "pair_comparisons.csv", "coverage.csv",
        "portfolio_risk.csv", "rolling_mae20.csv", "drift_error_timeline.csv", "H1_scatter_data.csv", "H1_results.csv",
        "H1_sensitivity.csv", "hypothesis_results.csv", "bootstrap_diagnostics.csv", "high_volatility_metrics.csv",
        "b4_comparisons.csv", "reference_b0_b3_metrics.csv",
    }
    artifact_names = {artifact.get("path") for artifact in public_outputs.values()}
    expected_names = artifact_names | {"dashboard_snapshot_manifest.json"}
    if not artifact_names or not artifact_names.issubset(approved_names) or {path.name for path in target.iterdir()} != expected_names:
        raise SnapshotError(f"Refusing to replace unexpected files in {target}")
    for artifact in public_outputs.values():
        filename = artifact.get("path")
        if filename not in approved_names:
            raise SnapshotError(f"Refusing to replace unexpected generated artifact: {filename}")
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
        count_keys = {
            "forecastAudit": "forecastAuditRows", "evaluation": "evaluationRows", "modelMetrics": "modelMetricsRows",
            "pairComparisons": "pairComparisonsRows", "coverage": "coverageRows",
            "portfolioRisk": "portfolioRiskRows", "rollingMae20": "rollingMae20Rows", "driftErrorTimeline": "driftErrorTimelineRows",
            "h1ScatterData": "h1ScatterDataRows", "h1Results": "h1ResultsRows", "h1Sensitivity": "h1SensitivityRows",
            "hypothesisResults": "hypothesisResultsRows", "bootstrapDiagnostics": "bootstrapDiagnosticsRows", "highVolatilityMetrics": "highVolatilityMetricsRows",
            "b4Comparisons": "b4ComparisonsRows", "referenceB0B3Metrics": "referenceB0B3MetricsRows",
        }
        for key, filename in policy["publicOutputs"].items():
            member_key = key
            payload = payloads[policy["members"][member_key]]
            (temporary / filename).write_bytes(payload)
            public_files[key] = {
                "path": filename,
                "sha256": sha256(payload),
                "bytes": len(payload),
                "rowCount": table_summary["counts"][count_keys[key]],
                "headers": table_summary["headers"][key],
            }

        manifest = {
            "schemaVersion": policy.get("schemaVersion", "1.1.0" if "b4Comparisons" in policy["publicOutputs"] else "1.0.0"),
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
    parser.add_argument("--policy", type=Path, default=Path(__file__).resolve().parents[2] / "web" / "snapshot.policy.json")
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
