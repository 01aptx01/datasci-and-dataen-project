"""Verify and export an immutable, reviewable Stage 06 results snapshot."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


REQUIRED_OUTPUT_FILES = (
    "H1_dataset_audit.csv",
    "H1_hypothesis_spec.json",
    "H1_manifest.json",
    "H1_results.csv",
    "H1_scatter_data.csv",
    "H1_scatter_plot.png",
    "H1_scatter_plot_spec.json",
    "H1_sensitivity.csv",
    "ML_dataset_preparation_report.json",
    "b4_comparisons.csv",
    "bootstrap_diagnostics.csv",
    "coverage.csv",
    "drift_error_timeline.csv",
    "evaluation.csv",
    "evaluation_summary.md",
    "forecast_audit.csv",
    "forecast_exceptions.csv",
    "high_volatility_metrics.csv",
    "hypotheses_plan.json",
    "hypothesis_results.csv",
    "model_metrics.csv",
    "monthly_metrics.csv",
    "pair_comparisons.csv",
    "portfolio_risk.csv",
    "reference_b0_b3_metrics.csv",
    "rolling_mae20.csv",
    "yearly_metrics.csv",
)

_EVALUATION_CODE_FILES = (
    "__init__.py",
    "config.py",
    "hypotheses.py",
    "metrics.py",
    "pipeline.py",
    "portfolio.py",
)
_EXPECTED_TICKERS = ["SPY", "IEF", "GLD"]
_EXPECTED_MODELS = [
    "CONSTANT_BASELINE",
    "ROLLING_20D_BASELINE",
    "STATIC_SGD",
    "ONLINE_SGD",
    "HAR_X_OLS",
]
_ABSOLUTE_PATH = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\[^\\/]+[\\/][^\\/]+|/(?!/)[^/])")


class ArtifactVerificationError(ValueError):
    """Raised when the Stage 06 source or its upstream lineage is inconsistent."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _read_json(path: Path, description: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ArtifactVerificationError(f"cannot read {description}: {path.name}") from error
    if not isinstance(value, dict):
        raise ArtifactVerificationError(f"{description} must contain a JSON object")
    return value


def _safe_artifact_name(name: str) -> bool:
    return bool(name) and Path(name).name == name and name not in {".", ".."}


def _verify_hashes(directory: Path, expected: dict[str, str], description: str) -> None:
    for name, expected_hash in expected.items():
        if not _safe_artifact_name(name):
            raise ArtifactVerificationError(f"unsafe {description} filename: {name}")
        artifact = directory / name
        if not artifact.is_file():
            raise ArtifactVerificationError(f"missing {description} artifact: {name}")
        actual_hash = _sha256(artifact)
        if actual_hash != expected_hash:
            raise ArtifactVerificationError(f"checksum mismatch for {description} {name}")


def _redact_paths(value: Any, repo_root: Path | None) -> Any:
    if isinstance(value, dict):
        return {key: _redact_paths(item, repo_root) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_paths(item, repo_root) for item in value]
    if isinstance(value, str) and _ABSOLUTE_PATH.match(value):
        if repo_root is not None:
            try:
                relative = Path(value).resolve().relative_to(repo_root.resolve())
                return relative.as_posix()
            except (OSError, ValueError):
                pass
        return "[REDACTED_LOCAL_PATH]"
    return value


def _text_hash_candidates(path: Path, repo_root: Path) -> set[str]:
    candidates = {_sha256(path)}
    try:
        normalized_text = path.read_text(encoding="utf-8").encode("utf-8")
        candidates.add(hashlib.sha256(normalized_text).hexdigest())
    except UnicodeDecodeError:
        pass
    relative = path.resolve().relative_to(repo_root.resolve()).as_posix()
    result = subprocess.run(
        ["git", "show", f"HEAD:{relative}"],
        cwd=repo_root,
        check=False,
        capture_output=True,
    )
    if result.returncode == 0:
        candidates.add(hashlib.sha256(result.stdout).hexdigest())
    return candidates


def _verify_current_code_and_config(
    repo_root: Path, manifest: dict[str, Any]
) -> dict[str, Any]:
    expected_code_hashes = manifest.get("code_sha256_by_file")
    if not isinstance(expected_code_hashes, dict) or set(expected_code_hashes) != set(
        _EVALUATION_CODE_FILES
    ):
        raise ArtifactVerificationError("Stage 06 code identity is incomplete")

    actual_code_hashes: dict[str, str] = {}
    for name in _EVALUATION_CODE_FILES:
        relative = f"src/ml_evaluation/{name}"
        result = subprocess.run(
            ["git", "show", f"HEAD:{relative}"],
            cwd=repo_root,
            check=False,
            capture_output=True,
        )
        if result.returncode != 0:
            raise ArtifactVerificationError(f"cannot verify tracked evaluation code: {relative}")
        actual_code_hashes[name] = hashlib.sha256(result.stdout).hexdigest()
    if actual_code_hashes != expected_code_hashes:
        raise ArtifactVerificationError("Stage 06 code hashes do not match the current Git source")

    config_path = repo_root / "config" / "ml_evaluation.yaml"
    hypothesis_path = repo_root / "config" / "hypothesis_tests.yaml"
    if not config_path.is_file() or not hypothesis_path.is_file():
        raise ArtifactVerificationError("current Stage 06 config files are missing")
    hypothesis_hash = manifest.get("hypothesis_config_sha256")
    if hypothesis_hash not in _text_hash_candidates(hypothesis_path, repo_root):
        raise ArtifactVerificationError("hypothesis config hash does not match the Stage 06 run")

    evaluation_hash = None
    for candidate in _text_hash_candidates(config_path, repo_root):
        analysis_id = _canonical_sha256(
            {
                "evaluation_config_sha256": candidate,
                "hypothesis_config_sha256": hypothesis_hash,
                "code_sha256_by_file": actual_code_hashes,
            }
        )
        if analysis_id == manifest.get("analysis_config_id"):
            evaluation_hash = candidate
            break
    if evaluation_hash is None:
        raise ArtifactVerificationError("evaluation config identity does not match Stage 06")

    identity_payload = {
        "stage03_lineage": manifest.get("source_lineage"),
        "final_replay_experiment_id": manifest.get("final_replay_experiment_id"),
        "final_replay_outputs_sha256": manifest.get("final_replay_outputs_sha256"),
        "stage04_artifacts_sha256": manifest.get("stage04_artifacts_sha256"),
        "stage03_h1_artifacts_sha256": manifest.get("stage03_h1_artifacts_sha256"),
        "stage03_source_artifacts_sha256": manifest.get("stage03_source_artifacts_sha256"),
        "evaluation_config_sha256": evaluation_hash,
        "hypothesis_config_sha256": hypothesis_hash,
        "code_sha256_by_file": actual_code_hashes,
    }
    identity_hash = _canonical_sha256(identity_payload)
    if identity_hash != manifest.get("input_identity_sha256"):
        raise ArtifactVerificationError("Stage 06 input identity hash could not be reproduced")
    if identity_hash != manifest.get("evaluation_id"):
        raise ArtifactVerificationError("evaluation_id does not match the frozen input identity")

    git_result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_root, check=True, capture_output=True, text=True
    )
    return {
        "baseline_git_commit": git_result.stdout.strip(),
        "evaluation_config_sha256": evaluation_hash,
        "hypothesis_config_sha256": hypothesis_hash,
        "code_sha256_by_file": actual_code_hashes,
        "analysis_config_id": manifest["analysis_config_id"],
        "input_identity_sha256": identity_hash,
    }


def _verify_upstream_artifacts(
    repo_root: Path, manifest: dict[str, Any], replay_manifest: dict[str, Any]
) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as error:  # pragma: no cover - dependency is declared by the project
        raise ArtifactVerificationError("PyYAML is required to verify upstream artifact paths") from error

    config_path = repo_root / "config" / "ml_evaluation.yaml"
    raw_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    paths = raw_config.get("paths", {})

    expected_groups = (
        ("stage04_artifacts_sha256", Path(paths["training_artifact_dir"])),
        ("stage03_h1_artifacts_sha256", Path(paths["h1_artifact_dir"])),
    )
    verified_groups: dict[str, dict[str, str]] = {}
    for field, relative_dir in expected_groups:
        hashes = manifest.get(field)
        if not isinstance(hashes, dict):
            raise ArtifactVerificationError(f"{field} is missing from the Stage 06 manifest")
        directory = (repo_root / relative_dir).resolve()
        _verify_hashes(directory, hashes, field)
        verified_groups[field] = hashes

    source_paths = {
        "correlations_parquet": Path(paths["correlations_parquet"]),
        "feature_manifest": Path(paths["feature_manifest"]),
        "feature_transaction": Path(paths["feature_transaction"]),
        "target_manifest": Path(paths["target_manifest"]),
        "target_transaction": Path(paths["target_transaction"]),
    }
    source_hashes = manifest.get("stage03_source_artifacts_sha256")
    if not isinstance(source_hashes, dict) or set(source_hashes) != set(source_paths):
        raise ArtifactVerificationError("Stage 03 source lineage hashes are incomplete")
    for name, relative_path in source_paths.items():
        path = (repo_root / relative_path).resolve()
        if not path.is_file() or _sha256(path) != source_hashes[name]:
            raise ArtifactVerificationError(f"Stage 03 source lineage checksum mismatch: {name}")

    replay_training = replay_manifest.get("stage04_artifact_sha256")
    training_hashes = verified_groups["stage04_artifacts_sha256"]
    if not isinstance(replay_training, dict) or any(
        training_hashes.get(name) != digest for name, digest in replay_training.items()
    ):
        raise ArtifactVerificationError("Stage 04 training lineage differs between Stage 05 and 06")
    if replay_manifest.get("stage04_training_manifest_sha256") != training_hashes.get(
        "training_manifest.json"
    ):
        raise ArtifactVerificationError("Stage 04 training manifest hash differs between stages")

    return {
        "stage04_artifacts_sha256": verified_groups["stage04_artifacts_sha256"],
        "stage03_h1_artifacts_sha256": verified_groups["stage03_h1_artifacts_sha256"],
        "stage03_source_artifacts_sha256": source_hashes,
        "source_lineage": manifest.get("source_lineage", {}),
    }


def verify_source_artifacts(
    source_dir: str | Path,
    replay_dir: str | Path,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    """Verify Stage 06 output hashes and the linked Final Replay before export."""
    source_path = Path(source_dir).resolve()
    replay_path = Path(replay_dir).resolve()
    manifest_path = source_path / "execution_manifest.json"
    replay_manifest_path = replay_path / "experiment_manifest.json"
    if not manifest_path.is_file():
        raise ArtifactVerificationError("execution_manifest.json is missing")
    if not replay_manifest_path.is_file():
        raise ArtifactVerificationError("Stage 05 experiment_manifest.json is missing")

    manifest = _read_json(manifest_path, "Stage 06 execution manifest")
    replay_manifest = _read_json(replay_manifest_path, "Stage 05 experiment manifest")
    evaluation_id = manifest.get("evaluation_id")
    if manifest.get("status") != "COMPLETED":
        raise ArtifactVerificationError("Stage 06 status is not COMPLETED")
    if not evaluation_id or source_path.name != evaluation_id:
        raise ArtifactVerificationError("evaluation directory does not match evaluation_id")
    if manifest.get("input_identity_sha256") != evaluation_id:
        raise ArtifactVerificationError("evaluation_id does not match input_identity_sha256")
    if manifest.get("stage") != "06_final_evaluation_testing_portfolio":
        raise ArtifactVerificationError("source artifact is not a Stage 06 Final Evaluation")

    config = manifest.get("evaluation_config", {})
    expected_values = {
        "data_cutoff": "2026-09-25",
        "test_start_date": "2025-10-01",
        "test_end_date": "2026-09-25",
        "tickers": _EXPECTED_TICKERS,
        "model_names": _EXPECTED_MODELS,
    }
    for name, expected in expected_values.items():
        if config.get(name) != expected:
            raise ArtifactVerificationError(f"approved evaluation config differs at {name}")

    output_hashes = manifest.get("outputs_sha256")
    if not isinstance(output_hashes, dict):
        raise ArtifactVerificationError("Stage 06 output hashes are missing")
    missing = set(REQUIRED_OUTPUT_FILES) - set(output_hashes)
    if missing:
        raise ArtifactVerificationError(
            "Stage 06 required outputs are missing from manifest: " + ", ".join(sorted(missing))
        )
    _verify_hashes(source_path, output_hashes, "Stage 06")

    replay_id = manifest.get("final_replay_experiment_id")
    if replay_manifest.get("status") != "COMPLETED":
        raise ArtifactVerificationError("linked Stage 05 replay status is not COMPLETED")
    if replay_manifest.get("experiment_id") != replay_id or replay_path.name != replay_id:
        raise ArtifactVerificationError("linked Stage 05 replay identity does not match")
    replay_hashes = manifest.get("final_replay_outputs_sha256")
    if not isinstance(replay_hashes, dict) or replay_hashes != replay_manifest.get(
        "final_outputs_sha256"
    ):
        raise ArtifactVerificationError("Stage 05 output hashes differ between the linked manifests")
    _verify_hashes(replay_path / "outputs", replay_hashes, "Stage 05 replay")

    root = Path(repo_root).resolve() if repo_root is not None else None
    repository_identity = _verify_current_code_and_config(root, manifest) if root else {}
    upstream_identity = (
        _verify_upstream_artifacts(root, manifest, replay_manifest) if root else {}
    )
    return {
        "source_dir": source_path,
        "replay_dir": replay_path,
        "manifest": manifest,
        "replay_manifest": replay_manifest,
        "repository_identity": repository_identity,
        "upstream_identity": upstream_identity,
    }


def _row_counts(source_dir: Path, files: tuple[str, ...]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for name in files:
        if not name.endswith(".csv"):
            continue
        with (source_dir / name).open("r", encoding="utf-8-sig", newline="") as stream:
            counts[name] = sum(1 for _ in csv.reader(stream)) - 1
    return counts


def export_results_bundle(
    source_dir: str | Path,
    replay_dir: str | Path,
    output_dir: str | Path,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    """Copy one verified evaluation and write redacted provenance/checksums."""
    destination = Path(output_dir).resolve()
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite existing handoff directory: {destination}")

    verified = verify_source_artifacts(source_dir, replay_dir, repo_root)
    source_path: Path = verified["source_dir"]
    replay_path: Path = verified["replay_dir"]
    manifest: dict[str, Any] = verified["manifest"]
    replay_manifest: dict[str, Any] = verified["replay_manifest"]
    destination.mkdir(parents=True)
    approved_dir = destination / "approved_results"
    approved_dir.mkdir()
    source_hashes: dict[str, str] = {}
    export_hashes: dict[str, str] = {}
    redacted_files: list[str] = []
    repo_path = Path(repo_root).resolve() if repo_root is not None else None

    names = (*REQUIRED_OUTPUT_FILES, "execution_manifest.json")
    for name in names:
        origin = source_path / name
        source_hashes[name] = _sha256(origin)
        target = approved_dir / name
        if name.endswith(".json"):
            payload = _read_json(origin, name)
            redacted = _redact_paths(payload, repo_path)
            if redacted != payload:
                target.write_text(
                    json.dumps(redacted, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                    newline="\n",
                )
                redacted_files.append(name)
            else:
                shutil.copy2(origin, target)
        else:
            shutil.copy2(origin, target)
        export_hashes[name] = _sha256(target)

    replay_manifest_target = approved_dir / "stage05_experiment_manifest.json"
    replay_manifest_source_hash = _sha256(replay_path / "experiment_manifest.json")
    redacted_replay = _redact_paths(replay_manifest, repo_path)
    replay_manifest_target.write_text(
        json.dumps(redacted_replay, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    export_hashes[replay_manifest_target.name] = _sha256(replay_manifest_target)

    row_counts = _row_counts(approved_dir, REQUIRED_OUTPUT_FILES)
    identity = {
        "handoff_schema_version": "1.1.0",
        "source_verification_status": "SOURCE VERIFIED",
        "evaluation_id": manifest["evaluation_id"],
        "final_replay_experiment_id": manifest["final_replay_experiment_id"],
        "stage06_status": manifest["status"],
        "stage05_status": replay_manifest["status"],
        "created_at_utc": manifest.get("created_at_utc"),
        "baseline_git_commit": verified["repository_identity"].get("baseline_git_commit"),
        "analysis_config_id": manifest.get("analysis_config_id"),
        "input_identity_sha256": manifest.get("input_identity_sha256"),
        "evaluation_config": manifest.get("evaluation_config"),
        "code_sha256_by_file": manifest.get("code_sha256_by_file"),
        "verified_config_hashes": {
            key: verified["repository_identity"].get(key)
            for key in ("evaluation_config_sha256", "hypothesis_config_sha256")
        },
        "source_artifact_reference": "data/processed/ml_evaluation/experiments/<evaluation_id>/",
        "stage05_artifact_reference": "data/processed/ml_replay/experiments/<final_replay_experiment_id>/",
        "source_manifest_sha256": source_hashes["execution_manifest.json"],
        "stage05_manifest_source_sha256": replay_manifest_source_hash,
        "source_output_sha256": manifest.get("outputs_sha256"),
        "stage05_output_sha256": replay_manifest.get("final_outputs_sha256"),
        "exported_file_sha256": export_hashes,
        "exported_files_with_redacted_paths": sorted(redacted_files),
        "exported_stage05_manifest_has_redacted_paths": redacted_replay != replay_manifest,
        "csv_data_rows": row_counts,
        "source_lineage": _redact_paths(manifest.get("source_lineage", {}), repo_path),
        "upstream_artifact_hashes": _redact_paths(
            verified["upstream_identity"], repo_path
        ),
        "h1_source_manifest": _read_json(approved_dir / "H1_manifest.json", "H1 manifest"),
        "limitations": manifest.get("limitations", []),
        "source_point_in_time_availability_verified": manifest.get(
            "point_in_time_source_availability_verified", False
        ),
    }
    identity_path = destination / "source_identity.json"
    identity_path.write_text(
        json.dumps(identity, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    export_hashes["source_identity.json"] = _sha256(identity_path)

    checksum_path = destination / "CHECKSUMS.sha256"
    checksum_targets = [
        path for path in destination.rglob("*") if path.is_file() and path != checksum_path
    ]
    checksum_lines = [
        f"{_sha256(path)}  {path.relative_to(destination).as_posix()}"
        for path in sorted(checksum_targets, key=lambda value: value.relative_to(destination).as_posix())
    ]
    checksum_path.write_text("\n".join(checksum_lines) + "\n", encoding="utf-8", newline="\n")
    return identity


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--replay-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    arguments = parser.parse_args()
    identity = export_results_bundle(
        arguments.source_dir,
        arguments.replay_dir,
        arguments.output_dir,
        arguments.repo_root,
    )
    print(
        "SOURCE VERIFIED: "
        f"evaluation_id={identity['evaluation_id']} "
        f"files={len(identity['exported_file_sha256'])}"
    )


if __name__ == "__main__":
    main()
