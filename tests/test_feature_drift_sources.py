from __future__ import annotations

from copy import deepcopy
import importlib
import importlib.util

import pytest


def _verifier():
    try:
        spec = importlib.util.find_spec("src.ml_diagnostics.sources")
    except ModuleNotFoundError:
        spec = None
    assert spec is not None, "Feature Drift source verifier is not implemented"
    module = importlib.import_module("src.ml_diagnostics.sources")
    verify_source_identity = getattr(module, "verify_source_identity", None)
    assert callable(verify_source_identity), "verify_source_identity is not implemented"

    return verify_source_identity


def _source_documents():
    feature_sha = "a" * 64
    target_sha = "b" * 64
    source_sha = "c" * 64
    lineage = {
        "feature_run_id": "features-run-1",
        "target_run_id": "targets-run-1",
        "feature_parquet_sha256": feature_sha,
        "target_parquet_sha256": target_sha,
        "source_input_sha256": source_sha,
        "feature_quality_finding_count": 0,
        "target_quality_finding_count": 0,
    }
    features = {
        "pipeline": "feature_engineering",
        "run_id": "features-run-1",
        "feature_set_version": "2.0.0",
        "input": {"sha256": source_sha},
    }
    targets = {
        "pipeline": "target_label_pipeline",
        "run_id": "targets-run-1",
        "target_version": "2.0.0",
        "input": {"sha256": source_sha},
    }
    evaluation_config = {
        "market": "XNYS",
        "data_cutoff": "2026-09-25",
        "core_features": ["rv_5d"],
    }
    training = {
        "training_run_id": "training-run-1",
        "source_lineage": deepcopy(lineage),
        "dataset_config": {
            "market": "XNYS",
            "data_cutoff": "2026-09-25",
            "core_features": ["rv_5d"],
        },
        "test_used_for_training_or_selection": False,
    }
    evaluation = {
        "evaluation_id": "evaluation-1",
        "final_replay_experiment_id": "replay-1",
        "status": "COMPLETED",
        "evaluation_config": deepcopy(evaluation_config),
        "source_lineage": deepcopy(lineage),
    }
    preparation_report = {
        "summary": {
            "data_cutoff": "2026-09-25",
            "manifest_verification": "verified",
            "source_quality_passed": True,
            "point_in_time_source_availability_verified": False,
        },
        "lineage": {
            "feature_run_id": lineage["feature_run_id"],
            "target_run_id": lineage["target_run_id"],
            "feature_parquet_sha256": feature_sha,
            "target_parquet_sha256": target_sha,
            "source_input_sha256": source_sha,
        },
    }
    return features, targets, training, evaluation, preparation_report, feature_sha, target_sha


def test_source_identity_rejects_a_parquet_hash_that_differs_from_frozen_lineage() -> None:
    verify = _verifier()
    features, targets, training, evaluation, report, feature_sha, target_sha = _source_documents()

    with pytest.raises(ValueError, match="feature Parquet SHA-256"):
        verify(
            features,
            targets,
            training,
            evaluation,
            report,
            actual_feature_sha256="d" * 64,
            actual_target_sha256=target_sha,
            expected_evaluation_id="evaluation-1",
            expected_replay_id="replay-1",
            expected_cutoff="2026-09-25",
            expected_feature_set_version="2.0.0",
            expected_core_features=("rv_5d",),
        )


def test_source_identity_accepts_reconciled_stage03_stage04_and_stage06_lineage() -> None:
    verify = _verifier()
    features, targets, training, evaluation, report, feature_sha, target_sha = _source_documents()

    identity = verify(
        features,
        targets,
        training,
        evaluation,
        report,
        actual_feature_sha256=feature_sha,
        actual_target_sha256=target_sha,
        expected_evaluation_id="evaluation-1",
        expected_replay_id="replay-1",
        expected_cutoff="2026-09-25",
        expected_feature_set_version="2.0.0",
        expected_core_features=("rv_5d",),
    )

    assert identity["evaluation_id"] == "evaluation-1"
    assert identity["replay_id"] == "replay-1"
    assert identity["feature_parquet_sha256"] == feature_sha
    assert identity["point_in_time_source_availability_verified"] is False


def test_source_identity_ignores_non_semantic_path_metadata() -> None:
    verify = _verifier()
    features, targets, training, evaluation, report, feature_sha, target_sha = _source_documents()
    training["source_lineage"]["manifest_path"] = "data/relative/training.json"
    evaluation["source_lineage"]["manifest_path"] = "C:/different/machine/evaluation.json"

    identity = verify(
        features,
        targets,
        training,
        evaluation,
        report,
        actual_feature_sha256=feature_sha,
        actual_target_sha256=target_sha,
        expected_evaluation_id="evaluation-1",
        expected_replay_id="replay-1",
        expected_cutoff="2026-09-25",
        expected_feature_set_version="2.0.0",
        expected_core_features=("rv_5d",),
    )

    assert identity["feature_run_id"] == "features-run-1"
