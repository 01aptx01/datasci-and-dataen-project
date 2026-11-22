from __future__ import annotations

import hashlib
import importlib
import importlib.util
import io
import json
import zipfile

import pytest


DATA_FILES = (
    "feature_drift_metrics.csv",
    "feature_drift_histograms.csv",
    "feature_drift_reference_summary.csv",
    "feature_drift_calibration.csv",
    "feature_drift_summary.md",
)
HEADERS = {
    "feature_drift_metrics.csv": "diagnostic_id,evaluation_id,replay_id,source_feature_run_id,feature_set_version,split,as_of_date,ticker,feature_name,reference_start,reference_end,reference_n,current_start,current_end,current_n,window_size,wasserstein_raw,train_iqr,wasserstein_normalized,psi,median_ref,median_current,p95_ref,p95_current,out_of_train_range_rate,wasserstein_threshold,psi_threshold,status,status_reason\n",
    "feature_drift_histograms.csv": "diagnostic_id,as_of_date,ticker,feature_name,window_size,bin_index,lower_edge,upper_edge,reference_count,current_count,reference_pct,current_pct,bin_definition_id,effective_bin_count\n",
    "feature_drift_reference_summary.csv": "diagnostic_id,ticker,feature_name,reference_start,reference_end,reference_n,q01,q05,q25,median,q75,q95,q99,train_iqr,effective_bin_count,bin_definition_id,reference_hash,bin_status\n",
    "feature_drift_calibration.csv": "diagnostic_id,ticker,feature_name,window_size,calibration_start,calibration_end,valid_window_count,threshold_percentile,threshold_method,wasserstein_threshold,psi_threshold,calibration_status\n",
    "feature_drift_summary.md": "# Feature Drift diagnostic\n\nLocal verification fixture.\n",
}


def _api(name: str):
    try:
        spec = importlib.util.find_spec("src.ml_diagnostics.export")
    except ModuleNotFoundError:
        spec = None
    assert spec is not None, "Feature Drift package verifier is not implemented"
    module = importlib.import_module("src.ml_diagnostics.export")
    function = getattr(module, name, None)
    assert callable(function), f"{name} is not implemented"
    return function


def _write_fixture(directory):
    payloads = {name: value.encode("utf-8") for name, value in HEADERS.items()}
    digest = lambda payload: hashlib.sha256(payload).hexdigest()
    identity = '{"evaluationId":"evaluation-1","replayId":"replay-1"}'
    diagnostic_id = digest(identity.encode("utf-8"))
    manifest = {
        "schemaVersion": "1.0.0",
        "status": "COMPLETED",
        "diagnosticId": diagnostic_id,
        "diagnosticIdentityCanonical": identity,
        "evaluationId": "evaluation-1",
        "replayId": "replay-1",
        "strictCutoff": "2026-09-25",
        "featureSetVersion": "2.0.0",
        "source": {
            "featureRunId": "features-run-1",
            "targetRunId": "targets-run-1",
            "featureParquetSha256": "a" * 64,
            "targetParquetSha256": "b" * 64,
        },
        "configuration": {
            "tickers": ["SPY"],
            "core_features": ["rv_5d"],
            "windows": {"sizes": [3]},
        },
        "files": {
            name: {
                "path": name,
                "sha256": digest(payload),
                "bytes": len(payload),
                "rows": 0 if name != "feature_drift_summary.md" else None,
            }
            for name, payload in payloads.items()
        },
    }
    manifest_payload = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    payloads["feature_drift_manifest.json"] = manifest_payload
    checksum_names = sorted(payloads)
    payloads["CHECKSUMS.sha256"] = "".join(
        f"{digest(payloads[name])}  {name}\n" for name in checksum_names
    ).encode("utf-8")
    for name, payload in payloads.items():
        (directory / name).write_bytes(payload)
    return manifest


def test_diagnostic_zip_is_reproducible_and_pins_identity(tmp_path) -> None:
    create = _api("create_diagnostic_archive")
    verify = _api("verify_diagnostic_archive")
    manifest = _write_fixture(tmp_path)

    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"
    first_sha = create(tmp_path, first)
    second_sha = create(tmp_path, second)

    assert first_sha == second_sha
    assert first.read_bytes() == second.read_bytes()
    result = verify(
        first.read_bytes(),
        expected_identity={
            "evaluationId": "evaluation-1",
            "replayId": "replay-1",
            "strictCutoff": "2026-09-25",
            "featureSetVersion": "2.0.0",
            "featureRunId": "features-run-1",
            "targetRunId": "targets-run-1",
            "featureParquetSha256": "a" * 64,
            "targetParquetSha256": "b" * 64,
        },
    )
    assert result["manifest"]["diagnosticId"] == manifest["diagnosticId"]


def test_tampered_metric_member_is_rejected_before_csv_use(tmp_path) -> None:
    create = _api("create_diagnostic_archive")
    verify = _api("verify_diagnostic_archive")
    _write_fixture(tmp_path)
    package_path = tmp_path / "diagnostic.zip"
    create(tmp_path, package_path)

    tampered = io.BytesIO()
    with zipfile.ZipFile(package_path) as source, zipfile.ZipFile(tampered, "w") as destination:
        for name in source.namelist():
            payload = source.read(name)
            if name == "feature_drift_metrics.csv":
                payload += b"tampered\n"
            destination.writestr(name, payload)

    with pytest.raises(ValueError, match="SHA-256 mismatch for feature_drift_metrics.csv"):
        verify(tampered.getvalue())


def test_static_adapter_copies_only_verified_allowlisted_data(tmp_path) -> None:
    create = _api("create_diagnostic_archive")
    publish = _api("publish_verified_archive")
    manifest = _write_fixture(tmp_path)
    package_path = tmp_path / "diagnostic.zip"
    create(tmp_path, package_path)
    dist = tmp_path / "dist"

    diagnostic_id = publish(
        package_path.read_bytes(),
        dist,
        expected_identity={
            "evaluationId": "evaluation-1",
            "replayId": "replay-1",
            "strictCutoff": "2026-09-25",
            "featureSetVersion": "2.0.0",
            "featureRunId": "features-run-1",
            "targetRunId": "targets-run-1",
            "featureParquetSha256": "a" * 64,
            "targetParquetSha256": "b" * 64,
        },
    )

    copied = dist / "feature-drift" / "current"
    assert diagnostic_id == manifest["diagnosticId"]
    assert {path.name for path in copied.iterdir()} == {
        "feature_drift_manifest.json",
        "feature_drift_metrics.csv",
        "feature_drift_histograms.csv",
        "feature_drift_reference_summary.csv",
        "feature_drift_calibration.csv",
        "CHECKSUMS.sha256",
    }
    assert not (copied / "feature_drift_summary.md").exists()
