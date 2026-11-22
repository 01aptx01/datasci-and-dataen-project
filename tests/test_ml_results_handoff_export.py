import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from scripts.export_ml_results_handoff import (
    CURRENT_OUTPUT_FILES,
    REQUIRED_OUTPUT_FILES,
    ArtifactVerificationError,
    export_results_bundle,
    verify_source_artifacts,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def completed_source(tmp_path: Path) -> tuple[Path, Path]:
    evaluation_id = "eval-001"
    replay_id = "replay-001"
    source_dir = tmp_path / "experiments" / evaluation_id
    replay_dir = tmp_path / "replay" / replay_id
    replay_outputs = replay_dir / "outputs"
    source_dir.mkdir(parents=True)
    replay_outputs.mkdir(parents=True)

    output_hashes = {}
    for name in REQUIRED_OUTPUT_FILES:
        artifact = source_dir / name
        if name.endswith(".csv"):
            artifact.write_text("column\nvalue\n", encoding="utf-8")
        elif name.endswith(".json"):
            artifact.write_text("{}\n", encoding="utf-8")
        elif name.endswith(".png"):
            artifact.write_bytes(b"synthetic-image")
        else:
            artifact.write_text("Synthetic source result.\n", encoding="utf-8")
        output_hashes[name] = _sha256(artifact)

    replay_output = replay_outputs / "evaluation.csv"
    replay_output.write_text("ticker,forecast\nSPY,0.1\n", encoding="utf-8")
    replay_hashes = {"evaluation.csv": _sha256(replay_output)}
    replay_manifest = {
        "status": "COMPLETED",
        "experiment_id": replay_id,
        "final_outputs_sha256": replay_hashes,
        "source_lineage": {"feature_manifest_path": str(tmp_path / "private" / "feature.json")},
    }
    (replay_dir / "experiment_manifest.json").write_text(
        json.dumps(replay_manifest), encoding="utf-8"
    )

    source_manifest = {
        "status": "COMPLETED",
        "stage": "06_final_evaluation_testing_portfolio",
        "evaluation_id": evaluation_id,
        "input_identity_sha256": evaluation_id,
        "created_at_utc": "2026-11-21T00:00:00Z",
        "analysis_config_id": "config-001",
        "final_replay_experiment_id": replay_id,
        "final_replay_outputs_sha256": replay_hashes,
        "outputs_sha256": output_hashes,
        "evaluation_config": {
            "data_cutoff": "2026-09-25",
            "test_start_date": "2025-10-01",
            "test_end_date": "2026-09-25",
            "tickers": ["SPY", "IEF", "GLD"],
            "model_names": [
                "CONSTANT_BASELINE",
                "ROLLING_20D_BASELINE",
                "STATIC_SGD",
                "ONLINE_SGD",
                "HAR_X_OLS",
            ],
        },
        "source_lineage": {
            "feature_run_id": "feature-001",
            "target_run_id": "target-001",
            "feature_manifest_path": str(tmp_path / "private" / "feature.json"),
        },
        "limitations": ["Synthetic test fixture."],
    }
    (source_dir / "execution_manifest.json").write_text(
        json.dumps(source_manifest), encoding="utf-8"
    )
    return source_dir, replay_dir


@pytest.fixture
def current_completed_source(completed_source: tuple[Path, Path]) -> tuple[Path, Path]:
    source_dir, replay_dir = completed_source
    manifest_path = source_dir / "execution_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["schema_version"] = "1.1.0"
    manifest["outputs_sha256"].pop("drift_error_timeline.csv")
    (source_dir / "drift_error_timeline.csv").unlink()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    replay_manifest_path = replay_dir / "experiment_manifest.json"
    replay_manifest = json.loads(replay_manifest_path.read_text(encoding="utf-8"))
    replay_manifest["replay_config"] = {
        "replay_config_version": "1.1.0",
        "processing_order": ["predict", "save_forecast", "evaluate", "update_b3", "checkpoint_commit"],
    }
    replay_manifest_path.write_text(json.dumps(replay_manifest), encoding="utf-8")
    return source_dir, replay_dir


def test_export_copies_one_verified_run_and_redacts_local_paths(
    completed_source: tuple[Path, Path], tmp_path: Path
) -> None:
    source_dir, replay_dir = completed_source
    original_hashes = {
        path.name: _sha256(path) for path in source_dir.iterdir() if path.is_file()
    }
    output_dir = tmp_path / "handoff"

    identity = export_results_bundle(source_dir, replay_dir, output_dir)

    exported_results = output_dir / "approved_results"
    assert identity["evaluation_id"] == source_dir.name
    assert identity["source_verification_status"] == "SOURCE VERIFIED"
    assert set(path.name for path in exported_results.iterdir()) == set(
        REQUIRED_OUTPUT_FILES
    ) | {"execution_manifest.json", "stage05_experiment_manifest.json"}
    assert identity["source_manifest_sha256"] == _sha256(
        source_dir / "execution_manifest.json"
    )
    redacted_manifest = (exported_results / "execution_manifest.json").read_text(
        encoding="utf-8"
    )
    assert str(tmp_path) not in redacted_manifest
    assert "[REDACTED_LOCAL_PATH]" in redacted_manifest
    assert {
        path.name: _sha256(path) for path in source_dir.iterdir() if path.is_file()
    } == original_hashes

    checksum_lines = (output_dir / "CHECKSUMS.sha256").read_text(
        encoding="utf-8"
    ).splitlines()
    assert any(line.endswith("approved_results/model_metrics.csv") for line in checksum_lines)
    assert all(len(line.split("  ", 1)[0]) == 64 for line in checksum_lines)


def test_export_current_schema_omits_legacy_b3_timeline(
    current_completed_source: tuple[Path, Path], tmp_path: Path
) -> None:
    source_dir, replay_dir = current_completed_source
    output_dir = tmp_path / "current-handoff"

    identity = export_results_bundle(source_dir, replay_dir, output_dir)

    exported_results = output_dir / "approved_results"
    assert identity["handoff_schema_version"] == "1.2.0"
    assert set(path.name for path in exported_results.iterdir()) == set(CURRENT_OUTPUT_FILES) | {
        "execution_manifest.json",
        "stage05_experiment_manifest.json",
    }
    assert "drift_error_timeline.csv" not in identity["csv_data_rows"]
    exported_manifest = json.loads(
        (exported_results / "execution_manifest.json").read_text(encoding="utf-8")
    )
    assert exported_manifest["schema_version"] == "1.1.0"
    assert "drift_error_timeline.csv" not in exported_manifest["outputs_sha256"]


def test_export_rejects_legacy_timeline_listed_in_current_manifest(
    current_completed_source: tuple[Path, Path]
) -> None:
    source_dir, replay_dir = current_completed_source
    timeline_path = source_dir / "drift_error_timeline.csv"
    timeline_path.write_text("column\nvalue\n", encoding="utf-8")
    manifest_path = source_dir / "execution_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["outputs_sha256"][timeline_path.name] = _sha256(timeline_path)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ArtifactVerificationError, match="must not publish the legacy B3 ADWIN timeline"):
        verify_source_artifacts(source_dir, replay_dir)


def test_export_verification_rejects_unlisted_physical_stage06_b3_timeline(
    current_completed_source: tuple[Path, Path]
) -> None:
    source_dir, replay_dir = current_completed_source
    (source_dir / "drift_error_timeline.csv").write_text("legacy\n", encoding="utf-8")

    with pytest.raises(ArtifactVerificationError, match="must not contain a legacy B3 ADWIN timeline file"):
        verify_source_artifacts(source_dir, replay_dir)


def test_export_verification_rejects_unlisted_physical_stage05_b3_drift_output(
    current_completed_source: tuple[Path, Path]
) -> None:
    source_dir, replay_dir = current_completed_source
    replay_outputs = replay_dir / "outputs"
    (replay_outputs / "drift_alerts.csv").write_text("legacy\n", encoding="utf-8")

    with pytest.raises(ArtifactVerificationError, match="current Stage 05 must not contain legacy B3 ADWIN output files"):
        verify_source_artifacts(source_dir, replay_dir)


@pytest.mark.parametrize(
    "fixture_name",
    ["completed_source", "current_completed_source"],
    ids=["archived-schema", "current-schema"],
)
def test_export_rejects_unexpected_hashed_stage06_outputs(
    request: pytest.FixtureRequest, fixture_name: str, tmp_path: Path
) -> None:
    source_dir, replay_dir = request.getfixturevalue(fixture_name)
    extra_output = source_dir / "unexpected.csv"
    extra_output.write_text("column\nvalue\n", encoding="utf-8")
    manifest_path = source_dir / "execution_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["outputs_sha256"][extra_output.name] = _sha256(extra_output)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    destination = tmp_path / "must-not-export"
    with pytest.raises(ArtifactVerificationError, match="unexpected: unexpected.csv"):
        export_results_bundle(source_dir, replay_dir, destination)
    assert not destination.exists()


def test_export_rejects_unknown_stage06_schema_version(completed_source: tuple[Path, Path]) -> None:
    source_dir, replay_dir = completed_source
    manifest_path = source_dir / "execution_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["schema_version"] = "9.9.9"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ArtifactVerificationError, match="unsupported Stage 06 schema version"):
        verify_source_artifacts(source_dir, replay_dir)


def test_export_rejects_a_changed_source_artifact(
    completed_source: tuple[Path, Path], tmp_path: Path
) -> None:
    source_dir, replay_dir = completed_source
    with (source_dir / "model_metrics.csv").open("a", encoding="utf-8") as stream:
        stream.write("changed\n")

    with pytest.raises(ArtifactVerificationError, match="model_metrics.csv"):
        export_results_bundle(source_dir, replay_dir, tmp_path / "handoff")


def test_export_rejects_replay_lineage_mismatch(
    completed_source: tuple[Path, Path], tmp_path: Path
) -> None:
    source_dir, replay_dir = completed_source
    replay_manifest_path = replay_dir / "experiment_manifest.json"
    replay_manifest = json.loads(replay_manifest_path.read_text(encoding="utf-8"))
    replay_manifest["experiment_id"] = "another-replay"
    replay_manifest_path.write_text(json.dumps(replay_manifest), encoding="utf-8")

    with pytest.raises(ArtifactVerificationError, match="replay"):
        export_results_bundle(source_dir, replay_dir, tmp_path / "handoff")


def test_export_refuses_to_overwrite_an_existing_directory(
    completed_source: tuple[Path, Path], tmp_path: Path
) -> None:
    source_dir, replay_dir = completed_source
    output_dir = tmp_path / "handoff"
    output_dir.mkdir()
    (output_dir / "keep.txt").write_text("do not overwrite", encoding="utf-8")

    with pytest.raises(FileExistsError):
        export_results_bundle(source_dir, replay_dir, output_dir)

    assert (output_dir / "keep.txt").read_text(encoding="utf-8") == "do not overwrite"


def test_export_redacts_nested_upstream_paths(
    completed_source: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_dir, replay_dir = completed_source
    verified = verify_source_artifacts(source_dir, replay_dir)
    local_path = tmp_path / "private" / "feature_manifest.json"
    verified["upstream_identity"] = {
        "source_lineage": {
            "feature_manifest_path": str(local_path),
            "target_manifest_path": r"\\research-share\private\target_manifest.json",
        },
        "stage04_artifacts_sha256": {"training_manifest.json": "abc123"},
    }
    monkeypatch.setattr(
        "scripts.export_ml_results_handoff.verify_source_artifacts",
        lambda *_args, **_kwargs: verified,
    )

    output_dir = tmp_path / "handoff"
    export_results_bundle(source_dir, replay_dir, output_dir)

    exported_identity = (output_dir / "source_identity.json").read_text(encoding="utf-8")
    exported_payload = json.loads(exported_identity)
    assert str(local_path) not in exported_identity
    assert (
        exported_payload["upstream_artifact_hashes"]["source_lineage"]["target_manifest_path"]
        == "[REDACTED_LOCAL_PATH]"
    )
    assert "[REDACTED_LOCAL_PATH]" in exported_identity


def _build_policy_source_pair(
    tmp_path: Path,
    *,
    with_events: bool,
    tag: str,
) -> tuple[Path, Path]:
    from src.ml_evaluation import run_policy_evaluation
    from src.ml_replay.config import POLICY_PROCESSING_ORDER, POLICY_REPLAY_CONFIG_VERSION
    from src.ml_replay.policy import POLICY_CHECKPOINT_VERSION
    from tests.test_ml_evaluation import _synthetic_policy_eval_tables

    tables = _synthetic_policy_eval_tables(with_events=with_events)
    replay_dir = tmp_path / f"replay-{tag}" / "exp-policy-test"
    out_dir = replay_dir / "outputs"
    out_dir.mkdir(parents=True)

    all_files = {
        "asset_volatility_predictions.csv": pd.DataFrame(columns=["prediction_id"]),
        "evaluation.csv": tables["evaluation.csv"],
        "updates.csv": pd.DataFrame(columns=["batch_id"]),
        "forecast_failures.csv": pd.DataFrame(columns=["reason"]),
        "coverage.csv": pd.DataFrame(columns=["ticker"]),
        "policy_forecasts.csv": tables["policy_forecasts.csv"],
        "policy_evaluations.csv": tables["policy_evaluations.csv"],
        "policy_detector_stream.csv": tables["policy_detector_stream.csv"],
        "policy_decision_events.csv": tables["policy_decision_events.csv"],
        "policy_champion_timeline.csv": tables["policy_champion_timeline.csv"],
        "policy_failures.csv": tables["policy_failures.csv"],
    }
    hashes = {}
    for name, df in all_files.items():
        path = out_dir / name
        df.to_csv(path, index=False, float_format="%.17g", lineterminator="\n")
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()

    n_dec = len(tables["policy_decision_events.csv"])
    n_promo = int((tables["policy_decision_events.csv"]["decision_outcome"] == "promoted").sum()) if n_dec else 0
    manifest = {
        "phase": "FINAL_REPLAY",
        "status": "COMPLETED",
        "experiment_id": "exp-policy-test",
        "last_fully_committed_session": "2026-09-25",
        "b2_frozen_state_verified": True,
        "b4_frozen_state_verified": True,
        "checkpoint_version": POLICY_CHECKPOINT_VERSION,
        "replay_config": {
            "replay_config_version": POLICY_REPLAY_CONFIG_VERSION,
            "processing_order": list(POLICY_PROCESSING_ORDER),
        },
        "champion_challenger_policy": {"policy_version": "1.0.0"},
        "policy_config_fingerprint": "f" * 64,
        "initial_champion": {"SPY": "B2", "IEF": "B1", "GLD": "B0"},
        "final_outputs_sha256": hashes,
        "final_policy_summary": {"total_policy_decisions": n_dec, "total_policy_promotions": n_promo},
    }
    (replay_dir / "experiment_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    eval_res = run_policy_evaluation(replay_dir, output_root=tmp_path / f"eval-{tag}")
    assert eval_res.artifact_dir is not None
    return eval_res.artifact_dir, replay_dir


def _rehash_policy_payloads(payloads: dict[str, bytes]) -> dict[str, bytes]:
    """Recompute exported_file_sha256 & CHECKSUMS.sha256 to test semantic checks beyond raw hashing."""
    updated = dict(payloads)
    identity = json.loads(updated["policy_source_identity.json"].decode("utf-8"))
    for rel_path in list(identity.get("exported_file_sha256", {})):
        if rel_path in updated:
            identity["exported_file_sha256"][rel_path] = hashlib.sha256(updated[rel_path]).hexdigest()
    updated["policy_source_identity.json"] = (
        json.dumps(identity, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    lines = [
        f"{hashlib.sha256(updated[name]).hexdigest()}  {name}"
        for name in sorted(k for k in updated if k != "CHECKSUMS.sha256")
    ]
    updated["CHECKSUMS.sha256"] = ("\n".join(lines) + "\n").encode("utf-8")
    return updated


def _reversion_policy_bundle(
    payloads: dict[str, bytes], *, replay_version: str, checkpoint_version: str, processing_order: list[str] | None = None,
    include_legacy_adwin: bool | None = None,
) -> dict[str, bytes]:
    updated = dict(payloads)
    identity = json.loads(updated["policy_source_identity.json"].decode("utf-8"))
    stage05_path = "policy_results/stage05_policy_manifest.json"
    stage05 = json.loads(updated[stage05_path].decode("utf-8"))
    identity["replay_config_version"] = replay_version
    identity["checkpoint_version"] = checkpoint_version
    stage05["checkpoint_version"] = checkpoint_version
    replay_config = stage05["replay_config"]
    replay_config["replay_config_version"] = replay_version
    if processing_order is None:
        processing_order = [
            "predict", "save_forecast", "evaluate", "adwin_monitor", "policy_adwin_and_decision", "update_b3", "checkpoint_commit",
        ] if replay_version == "2.0.0" else [
            "predict", "save_forecast", "evaluate", "policy_adwin_and_decision", "update_b3", "checkpoint_commit",
        ]
    replay_config["processing_order"] = processing_order
    has_legacy_adwin = replay_version == "2.0.0" if include_legacy_adwin is None else include_legacy_adwin
    final_outputs = stage05["final_outputs_sha256"]
    if has_legacy_adwin:
        replay_config["adwin"] = {"policy": "monitor_only"}
        final_outputs["drift_errors.csv"] = "a" * 64
        final_outputs["drift_alerts.csv"] = "b" * 64
    else:
        replay_config.pop("adwin", None)
        final_outputs.pop("drift_errors.csv", None)
        final_outputs.pop("drift_alerts.csv", None)
    updated["policy_source_identity.json"] = json.dumps(identity).encode("utf-8")
    updated[stage05_path] = json.dumps(stage05).encode("utf-8")
    return _rehash_policy_payloads(updated)


def test_policy_handoff_export_and_prepare_snapshot_supports_nonzero_and_zero_alerts_preserving_baseline(
    tmp_path: Path,
) -> None:
    from scripts.export_ml_results_handoff import export_policy_results_bundle
    from scripts.web.prepare_snapshot import prepare_policy_snapshot

    eval_alert, replay_alert = _build_policy_source_pair(tmp_path, with_events=True, tag="alerts")
    eval_zero, replay_zero = _build_policy_source_pair(tmp_path, with_events=False, tag="zero")

    bundle_alert = tmp_path / "handoff-policy-alerts"
    zip_alert = tmp_path / "ml-results-policy-alerts.zip"
    id_alert = export_policy_results_bundle(
        eval_alert,
        replay_alert,
        bundle_alert,
        zip_output_path=zip_alert,
    )
    assert id_alert["handoff_schema_version"] == "1.2.0"
    assert id_alert["alert_count_total"] == 2
    assert id_alert["decision_count_total"] == 2
    assert id_alert["promotion_count_total"] == 1
    assert zip_alert.is_file() and len(id_alert["zip_sha256"]) == 64

    # Existing baseline snapshot directory must stay completely untouched when preparing policy snapshot.
    public_snapshots = tmp_path / "public" / "snapshots"
    baseline_sentinel = public_snapshots / "ae5cc8cc-baseline" / "keep.txt"
    baseline_sentinel.parent.mkdir(parents=True)
    baseline_sentinel.write_text("existing-baseline-intact", encoding="utf-8")

    published_alert = prepare_policy_snapshot(
        tmp_path,
        public_snapshots,
        zip_alert,
        expected_zip_sha256=id_alert["zip_sha256"],
    )
    assert baseline_sentinel.read_text(encoding="utf-8") == "existing-baseline-intact"
    manifest_alert = json.loads((published_alert / "policy_snapshot_manifest.json").read_text("utf-8"))
    assert manifest_alert["schemaVersion"] == "1.2.0"
    assert manifest_alert["expectedCounts"]["policyAlertCount"] == 2
    assert manifest_alert["expectedCounts"]["policyPromotionCount"] == 1
    assert manifest_alert["mode"] == "SIMULATED HISTORICAL REPLAY"
    assert manifest_alert["exploratoryOnly"] is True
    assert manifest_alert["pointInTimeSourceAvailabilityVerified"] is False
    active = json.loads((public_snapshots / "policy" / "ACTIVE.json").read_text("utf-8"))
    assert active["activePolicyEvaluationId"] == id_alert["policy_evaluation_id"]

    # Zero-alert bundle also exports & validates cleanly.
    bundle_zero = tmp_path / "handoff-policy-zero"
    id_zero = export_policy_results_bundle(eval_zero, replay_zero, bundle_zero)
    assert id_zero["alert_count_total"] == 0
    assert id_zero["promotion_count_total"] == 0
    published_zero = prepare_policy_snapshot(tmp_path, public_snapshots, bundle_zero)
    manifest_zero = json.loads((published_zero / "policy_snapshot_manifest.json").read_text("utf-8"))
    assert manifest_zero["expectedCounts"]["policyAlertCount"] == 0
    assert manifest_zero["expectedCounts"]["policyPromotionCount"] == 0


def test_policy_snapshot_validation_rejects_forged_events_mismatches_duplicates_and_bad_relations(
    tmp_path: Path,
) -> None:
    from scripts.export_ml_results_handoff import export_policy_results_bundle
    from scripts.web.prepare_snapshot import (
        SnapshotError,
        _load_policy_bundle_payloads,
        prepare_policy_snapshot,
        validate_policy_bundle_payloads,
    )

    eval_dir, replay_dir = _build_policy_source_pair(tmp_path, with_events=True, tag="tamper")
    bundle_dir = tmp_path / "handoff-tamper"
    zip_path = tmp_path / "tamper.zip"
    id_info = export_policy_results_bundle(eval_dir, replay_dir, bundle_dir, zip_output_path=zip_path)
    base_payloads, _ = _load_policy_bundle_payloads(bundle_dir)

    # 1. Wrong ZIP SHA-256 rejected.
    with pytest.raises(SnapshotError, match="ZIP SHA-256 mismatch"):
        prepare_policy_snapshot(tmp_path, tmp_path / "out-zip", zip_path, expected_zip_sha256="0" * 64)

    # 2. Tampered file checksum without rehash rejected.
    bad_hash = dict(base_payloads)
    bad_hash["policy_results/policy_decision_events.csv"] += b"\n"
    with pytest.raises(SnapshotError, match="SHA-256 mismatch"):
        validate_policy_bundle_payloads(bad_hash)

    # 3. Forged decision event (trigger_prediction_id not triggered in ADWIN stream) rejected even after rehash.
    forged = dict(base_payloads)
    forged["policy_results/policy_decision_events.csv"] = (
        forged["policy_results/policy_decision_events.csv"]
        .decode("utf-8")
        .replace("p-GLD-SERVED_CHAMPION-0", "p-GLD-SERVED_CHAMPION-1", 1)
        .encode("utf-8")
    )
    with pytest.raises(SnapshotError, match="Forged or ungrounded decision event"):
        validate_policy_bundle_payloads(_rehash_policy_payloads(forged))

    # 4. Version mismatch rejected.
    bad_ver = dict(base_payloads)
    id_mod = json.loads(bad_ver["policy_source_identity.json"].decode("utf-8"))
    id_mod["handoff_schema_version"] = "9.9.9"
    bad_ver["policy_source_identity.json"] = json.dumps(id_mod).encode("utf-8")
    with pytest.raises(SnapshotError, match="Unsupported policy handoff_schema_version"):
        validate_policy_bundle_payloads(_rehash_policy_payloads(bad_ver))

    # 5. Policy config fingerprint mismatch rejected.
    bad_fp = dict(base_payloads)
    ev_mod = json.loads(bad_fp["policy_results/policy_evaluation_manifest.json"].decode("utf-8"))
    ev_mod["policy_config_fingerprint"] = "a" * 64
    bad_fp["policy_results/policy_evaluation_manifest.json"] = json.dumps(ev_mod).encode("utf-8")
    with pytest.raises(SnapshotError, match="fingerprint mismatch"):
        validate_policy_bundle_payloads(_rehash_policy_payloads(bad_fp))

    # 6. Duplicate event_id rejected.
    dup_ev = dict(base_payloads)
    lines = dup_ev["policy_results/policy_decision_events.csv"].decode("utf-8").splitlines()
    lines.append(lines[1])
    dup_ev["policy_results/policy_decision_events.csv"] = ("\n".join(lines) + "\n").encode("utf-8")
    id_dup = json.loads(dup_ev["policy_source_identity.json"].decode("utf-8"))
    id_dup["csv_data_rows"]["policy_decision_events.csv"] += 1
    dup_ev["policy_source_identity.json"] = json.dumps(id_dup).encode("utf-8")
    with pytest.raises(SnapshotError, match="duplicate event_id"):
        validate_policy_bundle_payloads(_rehash_policy_payloads(dup_ev))

    # 7. Invalid date relationship (effective_from_date == decision_date on promotion) rejected.
    bad_date = dict(base_payloads)
    dec_df = pd.read_csv(bundle_dir / "policy_results" / "policy_decision_events.csv")
    dec_df.loc[dec_df["decision_outcome"] == "promoted", "effective_from_date"] = "2025-10-08"
    bad_date["policy_results/policy_decision_events.csv"] = dec_df.to_csv(
        index=False, lineterminator="\n"
    ).encode("utf-8")
    with pytest.raises(SnapshotError, match="effective_from_date > decision_date"):
        validate_policy_bundle_payloads(_rehash_policy_payloads(bad_date))

    # 8. Invalid model relationship (promoted switching to B2 instead of B3) rejected.
    bad_model = dict(base_payloads)
    dec_df2 = pd.read_csv(bundle_dir / "policy_results" / "policy_decision_events.csv")
    dec_df2.loc[dec_df2["decision_outcome"] == "promoted", "champion_model_id_after"] = "B2"
    bad_model["policy_results/policy_decision_events.csv"] = dec_df2.to_csv(
        index=False, lineterminator="\n"
    ).encode("utf-8")
    with pytest.raises(SnapshotError, match="must switch to B3 snapshot"):
        validate_policy_bundle_payloads(_rehash_policy_payloads(bad_model))
    assert id_info["policy_evaluation_id"] == eval_dir.name


def test_policy_bundle_accepts_only_exact_archived_and_current_replay_contracts(tmp_path: Path) -> None:
    from scripts.export_ml_results_handoff import export_policy_results_bundle
    from scripts.web.prepare_snapshot import SnapshotError, _load_policy_bundle_payloads, validate_policy_bundle_payloads

    eval_dir, replay_dir = _build_policy_source_pair(tmp_path, with_events=True, tag="versions")
    bundle_dir = tmp_path / "handoff-versions"
    export_policy_results_bundle(eval_dir, replay_dir, bundle_dir)
    payloads, _ = _load_policy_bundle_payloads(bundle_dir)

    for checkpoint_version in ("2.0.0", "2.1.0"):
        archived = _reversion_policy_bundle(
            payloads, replay_version="2.0.0", checkpoint_version=checkpoint_version,
        )
        validate_policy_bundle_payloads(archived)

    current = _reversion_policy_bundle(
        payloads, replay_version="2.1.0", checkpoint_version="2.2.0",
    )
    validate_policy_bundle_payloads(current)

    wrong_current_checkpoint = _reversion_policy_bundle(
        payloads, replay_version="2.1.0", checkpoint_version="2.1.0",
    )
    with pytest.raises(SnapshotError, match="requires replay_config_version 2.1.0 and checkpoint_version 2.2.0"):
        validate_policy_bundle_payloads(wrong_current_checkpoint)

    wrong_archived_checkpoint = _reversion_policy_bundle(
        payloads, replay_version="2.0.0", checkpoint_version="2.2.0",
    )
    with pytest.raises(SnapshotError, match="requires checkpoint 2.0.0 or 2.1.0"):
        validate_policy_bundle_payloads(wrong_archived_checkpoint)

    wrong_order = _reversion_policy_bundle(
        payloads, replay_version="2.1.0", checkpoint_version="2.2.0",
        processing_order=["predict", "evaluate", "save_forecast", "policy_adwin_and_decision", "update_b3", "checkpoint_commit"],
    )
    with pytest.raises(SnapshotError, match="processing_order does not match its exact 2.1.0 contract"):
        validate_policy_bundle_payloads(wrong_order)

    forged_legacy_output = _reversion_policy_bundle(
        payloads, replay_version="2.1.0", checkpoint_version="2.2.0", include_legacy_adwin=True,
    )
    with pytest.raises(SnapshotError, match="must not contain retired B3 ADWIN configuration or outputs"):
        validate_policy_bundle_payloads(forged_legacy_output)


def test_baseline_snapshot_policy_schema_versions_gate_the_legacy_drift_timeline() -> None:
    from scripts.web.prepare_snapshot import SnapshotError, validate_snapshot_policy_schema

    policy_path = Path(__file__).resolve().parents[1] / "web" / "snapshot.policy.json"
    archived = json.loads(policy_path.read_text(encoding="utf-8"))
    validate_snapshot_policy_schema(archived)

    missing_archived_timeline = json.loads(json.dumps(archived))
    del missing_archived_timeline["members"]["driftErrorTimeline"]
    with pytest.raises(SnapshotError, match="requires the archived B3 drift timeline"):
        validate_snapshot_policy_schema(missing_archived_timeline)

    current = json.loads(json.dumps(archived))
    current["schemaVersion"] = "1.2.0"
    del current["members"]["driftErrorTimeline"]
    del current["expectedHeaders"]["driftErrorTimeline"]
    del current["expectedCounts"]["driftErrorTimelineRows"]
    del current["publicOutputs"]["driftErrorTimeline"]
    for member in list(current["memberSha256"]):
        if "drift_error_timeline.csv" in member.lower():
            del current["memberSha256"][member]
    validate_snapshot_policy_schema(current)

    forged_current_timeline = json.loads(json.dumps(current))
    forged_current_timeline["expectedCounts"]["driftAlertRows"] = 1
    with pytest.raises(SnapshotError, match="schema 1.2.0 must not define"):
        validate_snapshot_policy_schema(forged_current_timeline)
