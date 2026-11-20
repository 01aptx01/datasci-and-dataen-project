from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd
import pandas_market_calendars as market_calendars
import yaml

from src.features.pipeline import CORE_FEATURE_COLUMNS, SUPPORTED_TICKERS
from src.features.pipeline import FeaturePipelineError
from src.features.storage import validate_feature_table
from src.targets.pipeline import LABEL_COLUMNS, TargetPipelineError
from src.targets.storage import validate_target_table


class DatasetPreparationError(ValueError):
    """Raised when dataset inputs violate the Stage 03 preparation contract."""


@dataclass(frozen=True)
class DatasetConfig:
    config_version: str = "1.0.0"
    market: str = "XNYS"
    data_cutoff: date = date(2026, 9, 25)
    train_start_date: date = date(2021, 9, 27)
    train_end_date: date = date(2024, 9, 30)
    validation_start_date: date = date(2024, 10, 1)
    validation_end_date: date = date(2025, 9, 30)
    test_start_date: date = date(2025, 10, 1)
    test_end_date: date = date(2026, 9, 25)
    core_features: tuple[str, ...] = CORE_FEATURE_COLUMNS
    strict_point_in_time_source_verification: bool = False

    def __post_init__(self) -> None:
        date_fields = (
            "data_cutoff",
            "train_start_date",
            "train_end_date",
            "validation_start_date",
            "validation_end_date",
            "test_start_date",
            "test_end_date",
        )
        for name in date_fields:
            object.__setattr__(self, name, _as_date(getattr(self, name), name))
        if self.market != "XNYS":
            raise DatasetPreparationError("market must be XNYS for the locked split contract")
        if tuple(self.core_features) != tuple(CORE_FEATURE_COLUMNS):
            raise DatasetPreparationError("core_features must match the locked eight-feature order")
        locked_dates = (
            self.train_start_date,
            self.train_end_date,
            self.validation_start_date,
            self.validation_end_date,
            self.test_start_date,
            self.test_end_date,
            self.data_cutoff,
        )
        expected_dates = (
            date(2021, 9, 27),
            date(2024, 9, 30),
            date(2024, 10, 1),
            date(2025, 9, 30),
            date(2025, 10, 1),
            date(2026, 9, 25),
            date(2026, 9, 25),
        )
        if locked_dates != expected_dates:
            raise DatasetPreparationError("split dates and data cutoff are locked by the approved contract")
        if not isinstance(self.strict_point_in_time_source_verification, bool):
            raise DatasetPreparationError("strict_point_in_time_source_verification must be boolean")
        if self.strict_point_in_time_source_verification:
            raise DatasetPreparationError(
                "Strict point-in-time source verification is outside the approved project scope"
            )

    @classmethod
    def from_yaml(cls, path: str | Path = "config/ml_dataset.yaml") -> "DatasetConfig":
        config_path = Path(path)
        if not config_path.is_file():
            raise FileNotFoundError(f"ML Dataset config not found: {config_path}")
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise DatasetPreparationError("ML Dataset config must be a YAML mapping")
        splits = raw.get("splits", {})
        replay = raw.get("replay", {})
        if not isinstance(replay, dict) or not isinstance(
            replay.get("strict_point_in_time_source_verification", False), bool
        ):
            raise DatasetPreparationError("replay strict point-in-time option must be boolean")
        if replay.get("availability_rule") != (
            "is_label_mature and target_obs_count == 5 and target_end_date <= replay_date"
        ):
            raise DatasetPreparationError("replay availability_rule does not match the approved contract")
        if replay.get("fixed_split_purge_rule") != "target_end_date >= next_split_start_date":
            raise DatasetPreparationError("fixed_split_purge_rule does not match the approved contract")
        try:
            config = cls(
                config_version=raw["config_version"],
                market=raw["market"],
                data_cutoff=raw["data_cutoff"],
                train_start_date=splits["train"]["start_date"],
                train_end_date=splits["train"]["end_date"],
                validation_start_date=splits["validation"]["start_date"],
                validation_end_date=splits["validation"]["end_date"],
                test_start_date=splits["test"]["start_date"],
                test_end_date=splits["test"]["end_date"],
                core_features=tuple(raw["core_features"]),
                strict_point_in_time_source_verification=replay.get(
                    "strict_point_in_time_source_verification", False
                ),
            )
        except (KeyError, TypeError) as error:
            raise DatasetPreparationError(f"ML Dataset config is missing a required value: {error}") from error
        if config.config_version != "1.0.0":
            raise DatasetPreparationError("unsupported ML Dataset config_version")
        return config

    def split_for_date(self, value: date) -> str:
        if self.train_start_date <= value <= self.train_end_date:
            return "train"
        if self.validation_start_date <= value <= self.validation_end_date:
            return "validation"
        if self.test_start_date <= value <= self.test_end_date:
            return "test"
        return "outside_study"

    def as_dict(self) -> dict[str, Any]:
        return {
            "config_version": self.config_version,
            "market": self.market,
            "data_cutoff": self.data_cutoff.isoformat(),
            "core_features": list(self.core_features),
            "splits": {
                "train": [self.train_start_date.isoformat(), self.train_end_date.isoformat()],
                "validation": [self.validation_start_date.isoformat(), self.validation_end_date.isoformat()],
                "test": [self.test_start_date.isoformat(), self.test_end_date.isoformat()],
            },
            "purge_rule": "target_end_date >= next_split_start_date",
            "strict_point_in_time_source_verification": False,
        }


@dataclass
class LoadedInputs:
    features: pd.DataFrame
    labels: pd.DataFrame
    lineage: dict[str, Any]
    source_quality_passed: bool
    feature_failed_tickers: frozenset[str] = frozenset()
    label_failed_tickers: frozenset[str] = frozenset()
    label_quality_globally_failed: bool = False


@dataclass
class DatasetView:
    X: pd.DataFrame
    metadata: pd.DataFrame
    y: pd.Series | None = None


@dataclass
class PreparationReport:
    summary: dict[str, Any]
    counts_by_ticker_split_reason: pd.DataFrame
    lineage: dict[str, Any]
    versions: dict[str, list[str]]
    limitations: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "counts_by_ticker_split_reason": self.counts_by_ticker_split_reason.to_dict("records"),
            "lineage": self.lineage,
            "versions": self.versions,
            "limitations": list(self.limitations),
        }


@dataclass
class PreparedDataset:
    prediction: DatasetView
    supervised: DatasetView
    audit: pd.DataFrame
    report: PreparationReport


def _as_date(value: Any, field_name: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        stamp = pd.Timestamp(value)
    except (TypeError, ValueError) as error:
        raise DatasetPreparationError(f"{field_name} must be a valid market date") from error
    if pd.isna(stamp):
        raise DatasetPreparationError(f"{field_name} must be a valid market date")
    return stamp.date()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: str | Path, description: str) -> dict[str, Any]:
    manifest_path = Path(path)
    if not manifest_path.is_file():
        raise FileNotFoundError(f"{description} not found: {manifest_path}")
    try:
        value = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as error:
        raise DatasetPreparationError(f"Could not read {description}: {manifest_path}") from error
    if not isinstance(value, dict):
        raise DatasetPreparationError(f"{description} must contain a JSON object")
    return value


def _resolved_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def _verify_published_file(
    parquet_path: Path,
    manifest: Mapping[str, Any],
    transaction: Mapping[str, Any],
    *,
    output_key: str,
    table_name: str,
) -> str:
    output_path_value = (
        manifest.get("outputs", {}).get(output_key, {}).get("path")
        if output_key != "output"
        else manifest.get("output", {}).get("path")
    )
    if not output_path_value or _resolved_path(output_path_value) != _resolved_path(parquet_path):
        raise DatasetPreparationError(f"{table_name} manifest path does not match the requested Parquet")
    if transaction.get("status") != "COMMITTED" or not isinstance(transaction.get("entries"), list):
        raise DatasetPreparationError(f"{table_name} publish transaction is not COMMITTED")

    actual_sha = _sha256(parquet_path)
    matching = []
    for entry in transaction["entries"]:
        target_path = entry.get("target_path")
        if target_path and _resolved_path(target_path) == _resolved_path(parquet_path):
            matching.append(entry)
    if len(matching) != 1 or matching[0].get("sha256") != actual_sha:
        raise DatasetPreparationError(
            f"{table_name} transaction checksum does not match the published Parquet"
        )
    return actual_sha


def _source_batch_ids(manifest: Mapping[str, Any]) -> set[str]:
    snapshots = manifest.get("input", {}).get("source_snapshots", [])
    if not isinstance(snapshots, list):
        return set()
    return {
        str(snapshot["source_batch_id"])
        for snapshot in snapshots
        if isinstance(snapshot, dict) and snapshot.get("source_batch_id")
    }


def _manifest_ticker_failures(quality: Mapping[str, Any]) -> tuple[set[str], bool]:
    findings = quality.get("findings")
    if not isinstance(findings, list):
        return set(), bool(quality.get("finding_count", 0))
    failed_tickers = {
        str(item["ticker"])
        for item in findings
        if isinstance(item, dict) and item.get("ticker") in SUPPORTED_TICKERS
    }
    has_global_finding = any(
        not isinstance(item, dict) or item.get("ticker") not in SUPPORTED_TICKERS
        for item in findings
    )
    # A count without corresponding finding details cannot be safely localized.
    if int(quality.get("finding_count", len(findings))) > len(findings):
        has_global_finding = True
    return failed_tickers, has_global_finding


def load_validated_inputs(
    feature_path: str | Path,
    label_path: str | Path,
    feature_manifest_path: str | Path,
    target_manifest_path: str | Path,
    feature_transaction_path: str | Path,
    target_transaction_path: str | Path,
) -> LoadedInputs:
    """Read published Parquet tables and bind them to their manifests and transactions."""
    feature_file = Path(feature_path)
    label_file = Path(label_path)
    if not feature_file.is_file() or not label_file.is_file():
        raise FileNotFoundError("Both curated Features and Labels Parquet files must exist")
    feature_manifest = _read_json(feature_manifest_path, "Feature manifest")
    target_manifest = _read_json(target_manifest_path, "Target manifest")
    feature_transaction = _read_json(feature_transaction_path, "Feature publish transaction")
    target_transaction = _read_json(target_transaction_path, "Target publish transaction")
    if feature_manifest.get("pipeline") != "feature_engineering":
        raise DatasetPreparationError("Feature manifest pipeline must be feature_engineering")
    if target_manifest.get("pipeline") != "target_label_pipeline":
        raise DatasetPreparationError("Target manifest pipeline must be target_label_pipeline")

    feature_sha = _verify_published_file(
        feature_file,
        feature_manifest,
        feature_transaction,
        output_key="asset_volatility_features",
        table_name="asset_volatility_features",
    )
    label_sha = _verify_published_file(
        label_file,
        target_manifest,
        target_transaction,
        output_key="output",
        table_name="asset_volatility_labels",
    )
    feature_source_hash = feature_manifest.get("input", {}).get("sha256")
    target_source_hash = target_manifest.get("input", {}).get("sha256")
    if not feature_source_hash or feature_source_hash != target_source_hash:
        raise DatasetPreparationError("Feature and Target manifests do not share one source snapshot")
    if feature_manifest.get("input", {}).get("table") != "market_prices_daily":
        raise DatasetPreparationError("Feature manifest input must be market_prices_daily")
    if target_manifest.get("input", {}).get("table") != "market_prices_daily":
        raise DatasetPreparationError("Target manifest input must be market_prices_daily")

    try:
        features = validate_feature_table(pd.read_parquet(feature_file))
        labels = validate_target_table(pd.read_parquet(label_file))
    except (FeaturePipelineError, TargetPipelineError) as error:
        raise DatasetPreparationError(f"Published source table failed schema validation: {error}") from error

    for table_name, table, manifest, version_column, version_value in (
        ("Features", features, feature_manifest, "feature_set_version", feature_manifest.get("feature_set_version")),
        ("Labels", labels, target_manifest, "target_version", target_manifest.get("target_version")),
    ):
        if set(table["run_id"].astype(str)) != {str(manifest.get("run_id"))}:
            raise DatasetPreparationError(f"{table_name} rows do not match the manifest run_id")
        if set(table[version_column].astype(str)) != {str(version_value)}:
            raise DatasetPreparationError(f"{table_name} rows do not match the manifest version")

    known_batches = _source_batch_ids(feature_manifest) & _source_batch_ids(target_manifest)
    if not known_batches:
        raise DatasetPreparationError("Both manifests must identify a common source_batch_id")
    feature_batches = set(features["source_batch_id"].astype(str))
    target_batches = set(labels["source_batch_id"].astype(str))
    if not feature_batches.issubset(known_batches) or not target_batches.issubset(known_batches):
        raise DatasetPreparationError("Parquet source_batch_id values are not declared in both manifests")

    feature_quality = feature_manifest.get("quality", {})
    target_quality = target_manifest.get("quality", {})
    feature_failed_tickers = frozenset(str(value) for value in feature_quality.get("failed_tickers", []))
    label_failed, label_global_failure = _manifest_ticker_failures(target_quality)
    if not isinstance(target_quality.get("findings"), list) and int(target_quality.get("finding_count", 0)):
        label_global_failure = True
    source_snapshots = target_manifest.get("input", {}).get("source_snapshots", [])
    source_versions = sorted(
        {
            f"{snapshot.get('source', snapshot.get('client', 'unknown'))}:"
            f"{snapshot.get('source_version', 'unknown')}"
            for snapshot in source_snapshots
            if isinstance(snapshot, dict)
        }
    )
    lineage = {
        "feature_run_id": feature_manifest.get("run_id"),
        "target_run_id": target_manifest.get("run_id"),
        "feature_manifest_path": str(Path(feature_manifest_path).resolve()),
        "target_manifest_path": str(Path(target_manifest_path).resolve()),
        "feature_parquet_sha256": feature_sha,
        "target_parquet_sha256": label_sha,
        "source_input_sha256": feature_source_hash,
        "source_batch_ids": sorted(known_batches),
        "source_versions": source_versions,
        "feature_quality_finding_count": int(feature_quality.get("finding_count", 0)),
        "target_quality_finding_count": int(target_quality.get("finding_count", 0)),
    }
    source_quality_passed = not feature_failed_tickers and not label_failed and not label_global_failure
    return LoadedInputs(
        features=features,
        labels=labels,
        lineage=lineage,
        source_quality_passed=source_quality_passed,
        feature_failed_tickers=feature_failed_tickers,
        label_failed_tickers=frozenset(label_failed),
        label_quality_globally_failed=label_global_failure,
    )


def _load_xnys_sessions(
    config: DatasetConfig,
    feature_dates: Iterable[date],
    label_dates: Iterable[date],
    target_end_dates: Iterable[date],
) -> tuple[date, ...]:
    candidates = list(feature_dates) + list(label_dates) + list(target_end_dates)
    if not candidates:
        raise DatasetPreparationError("No dates are available to validate against XNYS")
    start = min(candidates) - timedelta(days=10)
    end = max(max(candidates), config.data_cutoff) + timedelta(days=30)
    schedule = market_calendars.get_calendar(config.market).schedule(
        start_date=start.isoformat(), end_date=end.isoformat()
    )
    return tuple(pd.Timestamp(value).date() for value in schedule.index)


def _validate_calendar(features: pd.DataFrame, labels: pd.DataFrame, config: DatasetConfig) -> tuple[date, ...]:
    target_ends = [value for value in labels["target_end_date"].dropna().tolist()]
    sessions = _load_xnys_sessions(config, features["date"].tolist(), labels["date"].tolist(), target_ends)
    session_set = set(sessions)
    invalid_feature_days = sorted(set(features["date"]) - session_set)
    invalid_label_days = sorted(set(labels["date"]) - session_set)
    if invalid_feature_days or invalid_label_days:
        bad_date = (invalid_feature_days or invalid_label_days)[0]
        raise DatasetPreparationError(f"input contains a non-XNYS market date: {bad_date}")
    position = {day: index for index, day in enumerate(sessions)}
    for row in labels.itertuples(index=False):
        if pd.isna(row.target_start_date) or pd.isna(row.target_end_date):
            continue
        anchor_position = position[row.date]
        if anchor_position + 5 >= len(sessions):
            raise DatasetPreparationError(f"XNYS calendar does not cover label window for {row.date}")
        expected_start = sessions[anchor_position + 1]
        expected_end = sessions[anchor_position + 5]
        if row.target_start_date != expected_start or row.target_end_date != expected_end:
            raise DatasetPreparationError(
                f"XNYS target window mismatch for ({row.date}, {row.ticker}); expected "
                f"{expected_start}..{expected_end}"
            )
    return sessions


def _validate_tables(features: pd.DataFrame, labels: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not isinstance(features, pd.DataFrame) or features.empty:
        raise DatasetPreparationError("asset_volatility_features must be a non-empty DataFrame")
    if not isinstance(labels, pd.DataFrame):
        raise DatasetPreparationError("asset_volatility_labels must be a DataFrame")
    if {"date", "ticker"}.issubset(features.columns) and features.duplicated(["date", "ticker"]).any():
        raise DatasetPreparationError("duplicate (date, ticker) primary keys in features")
    if {"date", "ticker"}.issubset(labels.columns) and labels.duplicated(["date", "ticker"]).any():
        raise DatasetPreparationError("duplicate (date, ticker) primary keys in labels")
    try:
        checked_features = validate_feature_table(features)
        if labels.empty and list(labels.columns) == list(LABEL_COLUMNS):
            checked_labels = labels.copy()
            for column in ("date", "target_start_date", "target_end_date"):
                checked_labels[column] = pd.Series(dtype=object)
        else:
            checked_labels = validate_target_table(labels)
    except (FeaturePipelineError, TargetPipelineError) as error:
        raise DatasetPreparationError(f"source table failed schema validation: {error}") from error
    return checked_features, checked_labels


def _key_set(values: Iterable[tuple[Any, Any]]) -> set[tuple[date, str]]:
    keys: set[tuple[date, str]] = set()
    for key_date, ticker in values:
        keys.add((_as_date(key_date, "ledger date"), str(ticker)))
    return keys


def _split_bounds(config: DatasetConfig) -> tuple[tuple[str, date, date], ...]:
    return (
        ("train", config.train_start_date, config.train_end_date),
        ("validation", config.validation_start_date, config.validation_end_date),
        ("test", config.test_start_date, config.test_end_date),
    )


def _make_report_counts(events: list[dict[str, Any]]) -> pd.DataFrame:
    columns = ["ticker", "split", "reason", "count"]
    if not events:
        return pd.DataFrame(columns=columns)
    return (
        pd.DataFrame(events)
        .groupby(["ticker", "split", "reason"], dropna=False)
        .size()
        .rename("count")
        .reset_index()
        .sort_values(["ticker", "split", "reason"], kind="stable")
        .reset_index(drop=True)
    )


def prepare_ml_dataset(
    inputs: LoadedInputs | pd.DataFrame,
    labels: pd.DataFrame | None = None,
    *,
    config: DatasetConfig | None = None,
    replay_date: date | str | None = None,
    updated_label_ledger: Iterable[tuple[Any, Any]] = (),
) -> PreparedDataset:
    """Build independent in-memory Prediction and fixed-split Supervised views."""
    effective_config = config or DatasetConfig()
    if isinstance(inputs, LoadedInputs):
        features_frame = inputs.features
        labels_frame = inputs.labels
        lineage = dict(inputs.lineage)
        feature_failed = set(inputs.feature_failed_tickers)
        label_failed = set(inputs.label_failed_tickers)
        label_quality_global_failure = inputs.label_quality_globally_failed
        source_quality_passed = inputs.source_quality_passed
        manifest_verification = "verified"
    else:
        features_frame = inputs
        if labels is None:
            raise DatasetPreparationError("labels must be provided with a raw feature DataFrame")
        labels_frame = labels
        lineage = {"manifest_verification": "not_provided"}
        feature_failed = set()
        label_failed = set()
        label_quality_global_failure = False
        source_quality_passed = None
        manifest_verification = "not_provided"

    as_of = effective_config.data_cutoff if replay_date is None else _as_date(replay_date, "replay_date")
    if as_of > effective_config.data_cutoff:
        raise DatasetPreparationError("replay_date cannot exceed the strict data cutoff")
    checked_features, checked_labels = _validate_tables(features_frame, labels_frame)
    _validate_calendar(checked_features, checked_labels, effective_config)
    if not checked_labels.empty:
        shared = checked_features[["date", "ticker", "source_batch_id"]].merge(
            checked_labels[["date", "ticker", "source_batch_id"]],
            on=["date", "ticker"],
            how="inner",
            suffixes=("_feature", "_label"),
            validate="one_to_one",
        )
        mismatch = shared[shared["source_batch_id_feature"] != shared["source_batch_id_label"]]
        if not mismatch.empty:
            first = mismatch.iloc[0]
            raise DatasetPreparationError(
                f"source_batch_id mismatch for ({first['date']}, {first['ticker']})"
            )

    ledger = _key_set(updated_label_ledger)
    feature_keys = set(zip(checked_features["date"], checked_features["ticker"]))
    label_lookup = {
        (row.date, row.ticker): row._asdict()
        for row in checked_labels.itertuples(index=False)
    }
    label_keys = set(label_lookup)
    matched_keys = feature_keys & label_keys
    events: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []
    all_core = checked_features.loc[:, list(effective_config.core_features)].to_numpy(dtype=float)
    core_finite = np.isfinite(all_core).all(axis=1)

    def add_event(ticker: str, split: str, reason: str) -> None:
        events.append({"ticker": ticker, "split": split, "reason": reason})

    for index, feature in checked_features.iterrows():
        anchor = feature["date"]
        ticker = str(feature["ticker"])
        split = effective_config.split_for_date(anchor)
        key = (anchor, ticker)
        label = label_lookup.get(key)
        reasons: list[str] = []
        if key in matched_keys:
            add_event(ticker, split, "join_matched")
        if split == "outside_study":
            reasons.append("outside_study")
        if anchor > effective_config.data_cutoff:
            reasons.append("after_data_cutoff")
        if anchor > as_of:
            reasons.append("after_replay_date")
        if not bool(feature["is_model_ready"]):
            reasons.append("feature_not_ready")
        if bool(feature["is_warmup_buffer"]):
            reasons.append("warmup_buffer")
        if not core_finite[index]:
            reasons.append("core_feature_nonfinite")
        if ticker in feature_failed:
            reasons.append("feature_source_quality_failed")
        feature_eligible = (
            split != "outside_study"
            and anchor <= effective_config.data_cutoff
            and anchor <= as_of
            and bool(feature["is_model_ready"])
            and not bool(feature["is_warmup_buffer"])
            and bool(core_finite[index])
            and ticker not in feature_failed
        )
        if feature_eligible:
            add_event(ticker, split, "prediction_eligible")

        label_available = False
        target_end: date | None = None
        target_start: date | None = None
        target_y = np.nan
        label_mature = False
        target_obs_count: int | None = None
        target_version: str | None = None
        target_run_id: str | None = None
        label_quality_ok = not label_quality_global_failure and ticker not in label_failed
        if label is None:
            reasons.append("label_missing")
        else:
            target_start = label.get("target_start_date")
            target_end = label.get("target_end_date")
            label_mature = bool(label["is_label_mature"])
            target_obs_count = int(label["target_obs_count"])
            target_y = label["target_realized_vol_5d"]
            target_version = str(label["target_version"])
            target_run_id = str(label["run_id"])
            if not label_quality_ok:
                reasons.append("label_source_quality_failed")
            if not label_mature:
                reasons.append("label_pending")
            if target_obs_count != 5:
                reasons.append("target_obs_count_not_five")
            target_valid = (
                isinstance(target_y, (int, float, np.integer, np.floating))
                and np.isfinite(float(target_y))
                and float(target_y) >= 0
            )
            if not target_valid:
                reasons.append("target_invalid")
            if target_end is None or pd.isna(target_end):
                reasons.append("target_end_date_missing")
            elif target_end > as_of:
                reasons.append("target_after_as_of")
            label_available = (
                label_quality_ok
                and label_mature
                and target_obs_count == 5
                and target_valid
                and target_end is not None
                and not pd.isna(target_end)
                and target_end <= as_of
            )

        fixed_purged = False
        purge_boundary: date | None = None
        if label_available and target_end is not None:
            if split == "train":
                purge_boundary = effective_config.validation_start_date
            elif split == "validation":
                purge_boundary = effective_config.test_start_date
            fixed_purged = purge_boundary is not None and target_end >= purge_boundary
            if fixed_purged:
                reasons.append("fixed_split_purge")

        supervised_eligible = feature_eligible and label_available and not fixed_purged
        online_update_eligible = feature_eligible and label_available and (anchor, ticker) not in ledger
        if label_available and not feature_eligible:
            reasons.append("feature_ineligible_for_label_use")
        if feature_eligible and label_available and not fixed_purged:
            add_event(ticker, split, "supervised_eligible")
        if online_update_eligible:
            add_event(ticker, split, "online_update_eligible")
        elif label_available and (anchor, ticker) in ledger:
            reasons.append("already_updated")

        for reason in dict.fromkeys(reasons):
            add_event(ticker, split, reason)
        audit_rows.append(
            {
                "date": anchor,
                "ticker": ticker,
                "split": split,
                "target_start_date": target_start,
                "target_end_date": target_end,
                "is_label_mature": label_mature if label is not None else pd.NA,
                "target_obs_count": target_obs_count if label is not None else pd.NA,
                "feature_set_version": str(feature["feature_set_version"]),
                "target_version": target_version,
                "feature_run_id": str(feature["run_id"]),
                "target_run_id": target_run_id,
                "source_batch_id": str(feature["source_batch_id"]),
                "feature_quality_passed": ticker not in feature_failed,
                "label_quality_passed": label_quality_ok if label is not None else False,
                "prediction_eligible": feature_eligible,
                "supervised_eligible": supervised_eligible,
                "fixed_purged": fixed_purged,
                "purge_boundary": purge_boundary,
                "online_update_eligible": online_update_eligible,
                "already_updated": (anchor, ticker) in ledger,
                "exclusion_reasons": tuple(dict.fromkeys(reasons)),
            }
        )

    for label_key in sorted(label_keys - feature_keys):
        label_date, ticker = label_key
        split = effective_config.split_for_date(label_date)
        add_event(ticker, split, "label_unmatched")

    feature_dates = set(checked_features["date"])
    study_sessions = [
        day
        for day in _load_xnys_sessions(
            effective_config,
            checked_features["date"].tolist(),
            checked_labels["date"].tolist() if not checked_labels.empty else [],
            checked_labels["target_end_date"].dropna().tolist() if not checked_labels.empty else [],
        )
        if any(start <= day <= end for _, start, end in _split_bounds(effective_config))
    ]
    for day in study_sessions:
        split = effective_config.split_for_date(day)
        for ticker in SUPPORTED_TICKERS:
            if (day, ticker) not in feature_keys:
                add_event(ticker, split, "feature_row_missing")

    audit = pd.DataFrame(audit_rows).sort_values(["ticker", "date"], kind="stable").reset_index(drop=True)
    prediction = audit.loc[audit["prediction_eligible"]].copy().reset_index(drop=True)
    supervised = audit.loc[audit["supervised_eligible"]].copy().reset_index(drop=True)
    # Align X, y, and metadata in deterministic (ticker, date) order.
    audit_index_to_original = {
        (row["date"], row["ticker"]): i for i, row in enumerate(audit_rows)
    }
    sorted_supervised_positions = [
        audit_index_to_original[(row.date, row.ticker)] for row in supervised.itertuples(index=False)
    ]
    feature_pos_by_key = {
        (row["date"], row["ticker"]): i for i, row in checked_features[["date", "ticker"]].iterrows()
    }
    pred_feature_rows = [
        feature_pos_by_key[(row.date, row.ticker)] for row in prediction.itertuples(index=False)
    ]
    supervised_feature_rows = [
        feature_pos_by_key[(row.date, row.ticker)] for row in supervised.itertuples(index=False)
    ]
    prediction_X = (
        checked_features.iloc[pred_feature_rows]
        .loc[:, list(effective_config.core_features)]
        .reset_index(drop=True)
    )
    supervised_X = (
        checked_features.iloc[supervised_feature_rows]
        .loc[:, list(effective_config.core_features)]
        .reset_index(drop=True)
    )
    supervised_y_values = [
        float(label_lookup[(audit_rows[position]["date"], audit_rows[position]["ticker"])]["target_realized_vol_5d"])
        for position in sorted_supervised_positions
    ]
    supervised_y_series = pd.Series(supervised_y_values, name="target_realized_vol_5d", dtype="float64")
    prediction_metadata = prediction.reset_index(drop=True)
    supervised_metadata = supervised.reset_index(drop=True)

    report_counts = _make_report_counts(events)
    feature_version_values = sorted(checked_features["feature_set_version"].astype(str).unique().tolist())
    target_version_values = (
        sorted(checked_labels["target_version"].astype(str).unique().tolist())
        if not checked_labels.empty
        else []
    )
    summary = {
        "features_input_rows": int(len(checked_features)),
        "labels_input_rows": int(len(checked_labels)),
        "join_matched_rows": int(len(matched_keys)),
        "features_without_label_rows": int(len(feature_keys - label_keys)),
        "labels_without_feature_rows": int(len(label_keys - feature_keys)),
        "prediction_eligible_rows": int(len(prediction)),
        "supervised_eligible_rows": int(len(supervised)),
        "online_update_eligible_rows": int(audit["online_update_eligible"].sum()),
        "fixed_purged_rows": int(audit["fixed_purged"].sum()),
        "as_of_date": as_of.isoformat(),
        "data_cutoff": effective_config.data_cutoff.isoformat(),
        "manifest_verification": manifest_verification,
        "source_quality_passed": (
            None if source_quality_passed is None else bool(source_quality_passed)
        ),
        "point_in_time_source_availability_verified": False,
    }
    versions = {
        "dataset_config": [effective_config.config_version],
        "source": list(lineage.get("source_versions", [])),
        "feature": feature_version_values,
        "target": target_version_values,
    }
    limitations = (
        (
            "Historical snapshot availability on each simulated replay date is not verified; "
            "replay uses target_end_date <= replay_date and pipeline validation evidence."
        ),
        (
            "The source snapshot was downloaded after the historical observation period; "
            "point-in-time source availability is not claimed."
        ),
    ) + (
        ("Input manifest and publish-transaction checks were not provided; source quality remains unverified.",)
        if manifest_verification != "verified"
        else ()
    )
    report = PreparationReport(
        summary=summary,
        counts_by_ticker_split_reason=report_counts,
        lineage=lineage,
        versions=versions,
        limitations=limitations,
    )
    return PreparedDataset(
        prediction=DatasetView(prediction_X, prediction_metadata),
        supervised=DatasetView(supervised_X, supervised_metadata, supervised_y_series),
        audit=audit,
        report=report,
    )
