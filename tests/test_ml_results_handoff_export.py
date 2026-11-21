import hashlib
import json
from pathlib import Path

import pytest

from scripts.export_ml_results_handoff import (
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
