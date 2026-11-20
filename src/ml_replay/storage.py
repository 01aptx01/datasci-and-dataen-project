from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping

import joblib
import numpy as np
import pandas as pd

from src.ml_replay.config import ReplayError


def json_default(value: Any) -> Any:
    if isinstance(value, (date, datetime, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (tuple, set, frozenset)):
        return list(value)
    raise TypeError(f"cannot serialize {type(value).__name__}")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=json_default)


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_json_atomic(path: str | Path, value: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    payload = json.dumps(value, indent=2, sort_keys=True, default=json_default) + "\n"
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()


def read_json(path: str | Path, description: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReplayError(f"Could not read {description}: {path}") from error
    if not isinstance(value, dict):
        raise ReplayError(f"{description} must contain a JSON object")
    return value


def _write_csv(path: Path, frame: pd.DataFrame, columns: list[str]) -> None:
    ordered = frame.reindex(columns=columns)
    content = ordered.to_csv(index=False, float_format="%.17g", lineterminator="\n")
    with path.open("w", encoding="utf-8", newline="") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def begin_session(checkpoint_root: str | Path, session_date: date) -> Path:
    root = Path(checkpoint_root).resolve()
    staging_root = root / "staging"
    (root / "committed").mkdir(parents=True, exist_ok=True)
    staging_root.mkdir(parents=True, exist_ok=True)
    stage_dir = staging_root / f".{session_date.isoformat()}.stage-{uuid.uuid4().hex}"
    stage_dir.mkdir()
    return stage_dir


def stage_table(stage_dir: str | Path, filename: str, frame: pd.DataFrame, columns: list[str]) -> None:
    path = Path(stage_dir) / filename
    if path.parent != Path(stage_dir):
        raise ReplayError("staged table path must stay inside its daily transaction")
    _write_csv(path, frame, columns)


def commit_session(
    checkpoint_root: str | Path,
    *,
    session_date: date,
    experiment_id: str,
    run_id: str,
    tables: Mapping[str, tuple[pd.DataFrame, list[str]]],
    state: Mapping[str, Any],
    state_summary: Mapping[str, Any],
    manifest_fields: Mapping[str, Any],
    stage_dir: str | Path | None = None,
    before_checkpoint: Any = None,
) -> Path:
    root = Path(checkpoint_root).resolve()
    committed_root = root / "committed"
    root.mkdir(parents=True, exist_ok=True)
    committed_root.mkdir(parents=True, exist_ok=True)
    final_dir = committed_root / session_date.isoformat()
    if final_dir.exists():
        raise ReplayError(f"refusing to overwrite an existing committed session: {session_date}")
    stage_path = Path(stage_dir).resolve() if stage_dir is not None else begin_session(root, session_date)
    if stage_path.parent != (root / "staging").resolve():
        raise ReplayError("daily transaction staging directory is outside the checkpoint staging root")
    try:
        file_hashes: dict[str, str] = {}
        for filename, (frame, columns) in tables.items():
            file_path = stage_path / filename
            if file_path.exists():
                expected = frame.reindex(columns=columns).to_csv(
                    index=False, float_format="%.17g", lineterminator="\n"
                )
                if file_path.read_text(encoding="utf-8") != expected:
                    raise ReplayError(f"staged forecast file changed before commit: {filename}")
            else:
                _write_csv(file_path, frame, columns)
            file_hashes[filename] = sha256_file(file_path)

        checkpoint_path = stage_path / "checkpoint.joblib"
        if before_checkpoint is not None:
            before_checkpoint("before_checkpoint_serialization", session_date)
        joblib.dump(dict(state), checkpoint_path, compress=3)
        file_hashes[checkpoint_path.name] = sha256_file(checkpoint_path)
        if before_checkpoint is not None:
            before_checkpoint("after_checkpoint_serialization", session_date)

        manifest = {
            "status": "COMMITTED",
            "session_date": session_date.isoformat(),
            "experiment_id": experiment_id,
            "run_id": run_id,
            "files_sha256": file_hashes,
            "state": dict(state_summary),
            **dict(manifest_fields),
        }
        manifest_path = stage_path / "manifest.json"
        write_json_atomic(manifest_path, manifest)
        manifest_hash = sha256_file(manifest_path)
        if before_checkpoint is not None:
            before_checkpoint("before_commit_marker", session_date)
        marker_path = stage_path / "COMMITTED"
        write_json_atomic(
            marker_path,
            {"session_date": session_date.isoformat(), "manifest_sha256": manifest_hash},
        )
        if before_checkpoint is not None:
            before_checkpoint("after_commit_marker_before_publish", session_date)
        stage_path.replace(final_dir)
    except Exception:
        # An incomplete staging directory is deliberately left untrusted and is ignored on resume.
        raise
    return final_dir


def verify_committed_session(
    path: str | Path,
    *,
    expected_experiment_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    directory = Path(path)
    marker_path = directory / "COMMITTED"
    manifest_path = directory / "manifest.json"
    marker = read_json(marker_path, "session commit marker")
    manifest = read_json(manifest_path, "session commit manifest")
    if marker.get("session_date") != manifest.get("session_date"):
        raise ReplayError(f"commit marker date does not match manifest: {directory.name}")
    if sha256_file(manifest_path) != marker.get("manifest_sha256"):
        raise ReplayError(f"session manifest checksum is invalid: {directory.name}")
    if manifest.get("status") != "COMMITTED":
        raise ReplayError(f"session is not marked COMMITTED: {directory.name}")
    if manifest.get("experiment_id") != expected_experiment_id:
        raise ReplayError(f"checkpoint belongs to a different experiment: {directory.name}")
    files = manifest.get("files_sha256")
    if not isinstance(files, dict) or not files:
        raise ReplayError(f"session manifest has no file checksums: {directory.name}")
    for filename, expected_hash in files.items():
        file_path = directory / filename
        if not file_path.is_file() or sha256_file(file_path) != expected_hash:
            raise ReplayError(f"session artifact checksum is invalid: {directory.name}/{filename}")
    return manifest, marker


def load_checkpoint(path: str | Path, *, expected_experiment_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    directory = Path(path)
    manifest, _ = verify_committed_session(directory, expected_experiment_id=expected_experiment_id)
    try:
        state = joblib.load(directory / "checkpoint.joblib")
    except Exception as error:
        raise ReplayError(f"Could not restore committed checkpoint: {directory.name}") from error
    if not isinstance(state, dict) or state.get("experiment_id") != expected_experiment_id:
        raise ReplayError(f"checkpoint state identity is invalid: {directory.name}")
    if state.get("last_committed_session") != manifest.get("session_date"):
        raise ReplayError(f"checkpoint session date does not match manifest: {directory.name}")
    return state, manifest
