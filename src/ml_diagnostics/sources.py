from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


class SourceVerificationError(ValueError):
    """Raised when diagnostic inputs do not reconcile with frozen lineage."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SourceVerificationError(message)


def verify_source_identity(
    feature_manifest: Mapping[str, Any],
    target_manifest: Mapping[str, Any],
    training_manifest: Mapping[str, Any],
    evaluation_manifest: Mapping[str, Any],
    preparation_report: Mapping[str, Any],
    *,
    actual_feature_sha256: str,
    actual_target_sha256: str,
    expected_evaluation_id: str,
    expected_replay_id: str,
    expected_cutoff: str,
    expected_feature_set_version: str,
    expected_core_features: Sequence[str],
) -> dict[str, Any]:
    """Reconcile Stage 03/04/06 identities before any drift calculation."""
    _require(evaluation_manifest.get("status") == "COMPLETED", "Stage 06 evaluation is not COMPLETED")
    _require(evaluation_manifest.get("evaluation_id") == expected_evaluation_id, "Evaluation ID does not match the frozen dashboard snapshot")
    _require(evaluation_manifest.get("final_replay_experiment_id") == expected_replay_id, "Replay ID does not match the frozen dashboard snapshot")

    evaluation_config = evaluation_manifest.get("evaluation_config", {})
    training_config = training_manifest.get("dataset_config", {})
    for label, config in (("Stage 06", evaluation_config), ("Stage 04", training_config)):
        _require(config.get("market") == "XNYS", f"{label} market must be XNYS")
        _require(config.get("data_cutoff") == expected_cutoff, f"{label} cutoff does not match the pinned cutoff")
        _require(tuple(config.get("core_features", ())) == tuple(expected_core_features), f"{label} Core Feature contract does not match")

    _require(training_manifest.get("test_used_for_training_or_selection") is False, "Stage 04 does not prove that Test was excluded from training and selection")
    _require(feature_manifest.get("pipeline") == "feature_engineering", "Feature manifest has an unexpected pipeline identity")
    _require(target_manifest.get("pipeline") == "target_label_pipeline", "Target manifest has an unexpected pipeline identity")
    _require(feature_manifest.get("feature_set_version") == expected_feature_set_version, "Feature version does not match the diagnostic contract")

    feature_lineage = evaluation_manifest.get("source_lineage", {})
    training_lineage = training_manifest.get("source_lineage", {})
    _require(bool(feature_lineage), "Stage 06 is missing source lineage")
    semantic_lineage_keys = (
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
    _require(
        all(feature_lineage.get(key) == training_lineage.get(key) for key in semantic_lineage_keys),
        "Stage 04 and Stage 06 source lineage does not match",
    )
    _require(feature_manifest.get("run_id") == feature_lineage.get("feature_run_id"), "Feature run ID does not match frozen lineage")
    _require(target_manifest.get("run_id") == feature_lineage.get("target_run_id"), "Target run ID does not match frozen lineage")

    _require(actual_feature_sha256 == feature_lineage.get("feature_parquet_sha256"), "feature Parquet SHA-256 does not match frozen lineage")
    _require(actual_feature_sha256 == training_lineage.get("feature_parquet_sha256"), "feature Parquet SHA-256 does not match Stage 04 lineage")
    _require(actual_target_sha256 == feature_lineage.get("target_parquet_sha256"), "target Parquet SHA-256 does not match frozen lineage")
    _require(actual_target_sha256 == training_lineage.get("target_parquet_sha256"), "target Parquet SHA-256 does not match Stage 04 lineage")
    source_input_sha256 = feature_lineage.get("source_input_sha256")
    _require(bool(source_input_sha256), "Frozen lineage is missing the source snapshot SHA-256")
    _require(feature_manifest.get("input", {}).get("sha256") == source_input_sha256, "Feature manifest source snapshot SHA-256 does not match frozen lineage")
    _require(target_manifest.get("input", {}).get("sha256") == source_input_sha256, "Target manifest source snapshot SHA-256 does not match frozen lineage")

    preparation_summary = preparation_report.get("summary", {})
    preparation_lineage = preparation_report.get("lineage", {})
    _require(preparation_summary.get("manifest_verification") == "verified", "Stage 03 preparation manifest was not verified")
    _require(preparation_summary.get("source_quality_passed") is True, "Stage 03 source quality did not pass")
    _require(preparation_summary.get("data_cutoff") == expected_cutoff, "Stage 03 preparation cutoff does not match")
    for key in ("feature_run_id", "target_run_id", "feature_parquet_sha256", "target_parquet_sha256", "source_input_sha256"):
        _require(preparation_lineage.get(key) == feature_lineage.get(key), f"Stage 03 preparation {key} does not match Stage 06 lineage")

    return {
        "evaluation_id": expected_evaluation_id,
        "replay_id": expected_replay_id,
        "strict_cutoff": expected_cutoff,
        "feature_run_id": str(feature_lineage["feature_run_id"]),
        "target_run_id": str(feature_lineage["target_run_id"]),
        "training_run_id": str(training_manifest.get("training_run_id", "")),
        "feature_set_version": expected_feature_set_version,
        "feature_parquet_sha256": actual_feature_sha256,
        "target_parquet_sha256": actual_target_sha256,
        "source_input_sha256": str(source_input_sha256),
        "feature_quality_finding_count": int(feature_lineage.get("feature_quality_finding_count", 0)),
        "target_quality_finding_count": int(feature_lineage.get("target_quality_finding_count", 0)),
        "point_in_time_source_availability_verified": bool(
            preparation_summary.get("point_in_time_source_availability_verified", False)
        ),
    }
