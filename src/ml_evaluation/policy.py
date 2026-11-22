from __future__ import annotations

import hashlib
import json
import math
import shutil
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from src.features.pipeline import SUPPORTED_TICKERS
from src.ml_evaluation.config import EvaluationConfig, EvaluationError, MODEL_NAMES
from src.ml_evaluation.metrics import calculate_error_metrics
from src.ml_replay.config import POLICY_PROCESSING_ORDER, POLICY_REPLAY_CONFIG_VERSION
from src.ml_replay.policy import POLICY_CHECKPOINT_VERSION


POLICY_EVALUATION_VERSION = "1.2.0"
POLICY_MODEL_ID_TO_NAME = {
    "B0": "CONSTANT_BASELINE",
    "B1": "ROLLING_20D_BASELINE",
    "B2": "STATIC_SGD",
    "B3": "ONLINE_SGD",
    "B4": "HAR_X_OLS",
}
EVALUATED_POLICY_STRATEGIES = (
    "CHAMPION_CHALLENGER_POLICY",
    "FIXED_INITIAL_CHAMPION",
    "SHADOW_B3",
    "CONSTANT_BASELINE",
    "ROLLING_20D_BASELINE",
    "STATIC_SGD",
    "ONLINE_SGD",
    "HAR_X_OLS",
)
BENCHMARK_REPLAY_FILES = (
    "asset_volatility_predictions.csv",
    "evaluation.csv",
    "drift_errors.csv",
    "drift_alerts.csv",
    "updates.csv",
    "forecast_failures.csv",
    "coverage.csv",
)
POLICY_REPLAY_FILES = (
    "policy_forecasts.csv",
    "policy_evaluations.csv",
    "policy_detector_stream.csv",
    "policy_decision_events.csv",
    "policy_champion_timeline.csv",
    "policy_failures.csv",
)
TEST_REUSE_LIMITATION = (
    "Exploratory retrospective policy specified after observing Stage 06 Test outcomes; "
    "reported strictly separately from confirmatory hypotheses H1-H3."
)
PIT_LIMITATION = (
    "Simulated historical replay (point_in_time_source_availability_verified=false); "
    "does not represent live inference or live operational retraining."
)
SHADOW_PROCESS_LIMITATION = (
    "Paired challenger MAE evaluates the continuously updating shadow B3 process prior to decision time, "
    "whereas promotion serves a frozen pre-update B3 snapshot from the next session."
)


@dataclass
class PolicyEvaluationResult:
    evaluation_id: str
    policy_evaluation_version: str
    replay_experiment_id: str
    artifact_dir: Path | None
    model_metrics: pd.DataFrame
    comparisons: pd.DataFrame
    operations_summary: pd.DataFrame
    coverage_summary: pd.DataFrame
    reconciliation: dict[str, Any]
    manifest: dict[str, Any]


def _json_default(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    raise TypeError(f"cannot JSON-serialize object of type {type(value).__name__}")


def _canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=_json_default)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path, description: str) -> dict[str, Any]:
    if not path.is_file():
        raise EvaluationError(f"required {description} is missing: {path}")
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise EvaluationError(f"could not parse {description}: {path}") from error
    if not isinstance(loaded, dict):
        raise EvaluationError(f"{description} must be a JSON object: {path}")
    return loaded


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "nat"}:
        return None
    try:
        return pd.Timestamp(text).date()
    except (TypeError, ValueError):
        return None


def _bool_series(series: pd.Series) -> pd.Series:
    return series.map(
        lambda v: False
        if (v is None or (isinstance(v, float) and math.isnan(v)))
        else str(v).strip().lower() in {"true", "1", "yes"}
        if isinstance(v, str)
        else bool(v)
    )


def verify_policy_replay_artifacts(
    replay_dir: str | Path,
    *,
    config: EvaluationConfig | None = None,
    require_strict_cutoff: bool = True,
) -> tuple[dict[str, Any], dict[str, pd.DataFrame], dict[str, str], dict[str, Any]]:
    """Verify Stage 05 policy replay manifest, file checksums, and event/timeline reconciliation."""
    effective_config = config or EvaluationConfig()
    directory = Path(replay_dir).expanduser().resolve()
    manifest = _read_json(directory / "experiment_manifest.json", "Stage 05 policy replay manifest")

    if manifest.get("phase") != "FINAL_REPLAY" or manifest.get("status") != "COMPLETED":
        raise EvaluationError("policy evaluation requires a completed Stage 05 policy replay")
    if manifest.get("experiment_id") != directory.name:
        raise EvaluationError("policy replay directory name does not match experiment_id")
    if require_strict_cutoff and manifest.get("last_fully_committed_session") != effective_config.data_cutoff.isoformat():
        raise EvaluationError("policy replay does not reach the locked strict data cutoff")
    if manifest.get("b2_frozen_state_verified") is not True or manifest.get("b4_frozen_state_verified") is not True:
        raise EvaluationError("policy replay does not prove frozen B2/B4 states")

    replay_cfg = manifest.get("replay_config", {})
    if replay_cfg.get("replay_config_version") != POLICY_REPLAY_CONFIG_VERSION:
        raise EvaluationError(
            f"policy evaluation requires replay_config_version {POLICY_REPLAY_CONFIG_VERSION}"
        )
    if list(replay_cfg.get("processing_order", [])) != list(POLICY_PROCESSING_ORDER):
        raise EvaluationError("policy replay processing_order does not match the approved contract")
    if manifest.get("checkpoint_version") != POLICY_CHECKPOINT_VERSION:
        raise EvaluationError(f"policy replay checkpoint_version must be {POLICY_CHECKPOINT_VERSION}")
    if replay_cfg.get("adwin", {}).get("policy") != "monitor_only":
        raise EvaluationError("benchmark B3 ADWIN must remain monitor_only in policy replay")

    expected_hashes = manifest.get("final_outputs_sha256")
    all_files = BENCHMARK_REPLAY_FILES + POLICY_REPLAY_FILES
    if not isinstance(expected_hashes, dict) or set(all_files) - set(expected_hashes):
        raise EvaluationError("policy replay manifest does not hash every benchmark and policy output")

    outputs: dict[str, pd.DataFrame] = {}
    verified_hashes: dict[str, str] = {}
    output_dir = directory / "outputs"
    for filename in all_files:
        path = output_dir / filename
        if not path.is_file():
            raise EvaluationError(f"missing Stage 05 output file: {filename}")
        digest = _file_sha256(path)
        if digest != expected_hashes[filename]:
            raise EvaluationError(f"Stage 05 output checksum mismatch: {filename}")
        verified_hashes[filename] = digest
        outputs[filename] = pd.read_csv(path, low_memory=False)

    reconciliation = reconcile_policy_replay_tables(
        manifest=manifest,
        policy_forecasts=outputs["policy_forecasts.csv"],
        policy_evaluations=outputs["policy_evaluations.csv"],
        policy_detector_stream=outputs["policy_detector_stream.csv"],
        policy_decision_events=outputs["policy_decision_events.csv"],
        policy_champion_timeline=outputs["policy_champion_timeline.csv"],
        policy_failures=outputs["policy_failures.csv"],
    )
    return manifest, outputs, verified_hashes, reconciliation


def reconcile_policy_replay_tables(
    *,
    manifest: Mapping[str, Any],
    policy_forecasts: pd.DataFrame,
    policy_evaluations: pd.DataFrame,
    policy_detector_stream: pd.DataFrame,
    policy_decision_events: pd.DataFrame,
    policy_champion_timeline: pd.DataFrame,
    policy_failures: pd.DataFrame,
) -> dict[str, Any]:
    """Verify strict 1:1 consistency across policy forecasts, detector stream, decisions, and timeline."""
    if not policy_forecasts.empty and policy_forecasts["policy_prediction_id"].duplicated().any():
        raise EvaluationError("policy_forecasts.csv contains duplicate policy_prediction_id")
    if not policy_evaluations.empty and policy_evaluations["policy_prediction_id"].duplicated().any():
        raise EvaluationError("policy_evaluations.csv contains duplicate policy_prediction_id")
    if not policy_decision_events.empty and policy_decision_events["event_id"].duplicated().any():
        raise EvaluationError("policy_decision_events.csv contains duplicate event_id")
    if not policy_champion_timeline.empty and policy_champion_timeline["timeline_event_id"].duplicated().any():
        raise EvaluationError("policy_champion_timeline.csv contains duplicate timeline_event_id")

    initial_by_ticker = manifest.get("initial_champion", {})
    if set(initial_by_ticker) != set(SUPPORTED_TICKERS):
        raise EvaluationError("policy replay manifest is missing initial_champion for all supported ETFs")

    # Verify initial cutover rows in timeline match manifest initial_champion.
    if not policy_champion_timeline.empty:
        init_rows = policy_champion_timeline.loc[
            policy_champion_timeline["event_type"] == "INITIAL_CHAMPION_CUTOVER"
        ]
        for ticker in SUPPORTED_TICKERS:
            t_init = init_rows.loc[init_rows["ticker"] == ticker]
            if len(t_init) != 1 or str(t_init.iloc[0]["to_model_id"]) != str(initial_by_ticker[ticker]):
                raise EvaluationError(
                    f"{ticker} INITIAL_CHAMPION_CUTOVER timeline entry does not reconcile with manifest"
                )

    # Verify every decision event reconciles to a triggered drift row in policy_detector_stream.
    stream_triggers = (
        policy_detector_stream.loc[
            _bool_series(policy_detector_stream["drift_detected"])
            & _bool_series(policy_detector_stream["triggered_decision"])
        ]
        if not policy_detector_stream.empty
        else policy_detector_stream
    )
    if len(stream_triggers) != len(policy_decision_events):
        raise EvaluationError(
            f"triggered detector alerts ({len(stream_triggers)}) do not match decision events "
            f"({len(policy_decision_events)})"
        )
    if not policy_decision_events.empty:
        trigger_index = {
            (str(row.policy_prediction_id), str(row.ticker), _as_date(row.evaluation_date))
            for row in stream_triggers.itertuples(index=False)
        }
        for row in policy_decision_events.itertuples(index=False):
            key = (str(row.trigger_prediction_id), str(row.ticker), _as_date(row.decision_date))
            if key not in trigger_index:
                raise EvaluationError(
                    f"decision event {row.event_id} has no matching triggered ADWIN stream row {key}"
                )

    # Verify promotions reconcile 1:1 with PROMOTED_SNAPSHOT_ACTIVE_NEXT_SESSION timeline rows.
    promoted_decisions = (
        policy_decision_events.loc[policy_decision_events["decision_outcome"] == "promoted"]
        if not policy_decision_events.empty
        else policy_decision_events
    )
    promoted_timeline = (
        policy_champion_timeline.loc[
            policy_champion_timeline["event_type"] == "PROMOTED_SNAPSHOT_ACTIVE_NEXT_SESSION"
        ]
        if not policy_champion_timeline.empty
        else policy_champion_timeline
    )
    if len(promoted_decisions) != len(promoted_timeline):
        raise EvaluationError(
            f"promoted decision count ({len(promoted_decisions)}) does not match timeline promotions "
            f"({len(promoted_timeline)})"
        )
    if not promoted_decisions.empty:
        tl_by_event = {
            str(row.decision_event_id): row for row in promoted_timeline.itertuples(index=False)
        }
        for row in promoted_decisions.itertuples(index=False):
            tl_row = tl_by_event.get(str(row.event_id))
            if tl_row is None:
                raise EvaluationError(f"promoted decision {row.event_id} missing from champion timeline")
            dec_date = _as_date(row.decision_date)
            eff_date = _as_date(row.effective_from_date)
            tl_eff = _as_date(tl_row.effective_from_date)
            if dec_date is None or eff_date is None or eff_date <= dec_date or tl_eff != eff_date:
                raise EvaluationError(
                    f"promoted decision {row.event_id} violates effective_from_date > decision_date"
                )
            if str(tl_row.to_champion_version_id) != str(row.champion_version_id_after):
                raise EvaluationError(f"promoted decision {row.event_id} version mismatch in timeline")

    # Reconcile against manifest final_policy_summary if present.
    final_summary = manifest.get("final_policy_summary")
    if isinstance(final_summary, Mapping):
        if int(final_summary.get("total_policy_decisions", -1)) != len(policy_decision_events):
            raise EvaluationError("manifest final_policy_summary decision count mismatch")
        if int(final_summary.get("total_policy_promotions", -1)) != len(promoted_decisions):
            raise EvaluationError("manifest final_policy_summary promotion count mismatch")

    per_ticker_counts: dict[str, dict[str, int]] = {}
    for ticker in SUPPORTED_TICKERS:
        t_stream = policy_detector_stream.loc[policy_detector_stream["ticker"] == ticker] if not policy_detector_stream.empty else policy_detector_stream
        t_dec = policy_decision_events.loc[policy_decision_events["ticker"] == ticker] if not policy_decision_events.empty else policy_decision_events
        t_promo = promoted_decisions.loc[promoted_decisions["ticker"] == ticker] if not promoted_decisions.empty else promoted_decisions
        t_fail = policy_failures.loc[policy_failures["ticker"] == ticker] if not policy_failures.empty else policy_failures
        per_ticker_counts[ticker] = {
            "detector_observations": int(len(t_stream)),
            "alerts": int(_bool_series(t_stream["drift_detected"]).sum()) if not t_stream.empty else 0,
            "decisions": int(len(t_dec)),
            "promotions": int(len(t_promo)),
            "policy_failures": int(len(t_fail)),
        }

    return {
        "reconciliation_passed": True,
        "total_policy_forecasts": int(len(policy_forecasts)),
        "total_policy_evaluations": int(len(policy_evaluations)),
        "total_detector_observations": int(len(policy_detector_stream)),
        "total_alerts": int(
            _bool_series(policy_detector_stream["drift_detected"]).sum()
            if not policy_detector_stream.empty
            else 0
        ),
        "total_decisions": int(len(policy_decision_events)),
        "total_promotions": int(len(promoted_decisions)),
        "per_ticker": per_ticker_counts,
    }


def _clean_eval_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    cleaned = frame.copy()
    cleaned["prediction_date"] = cleaned["prediction_date"].map(_as_date)
    if "evaluation_date" in cleaned.columns:
        cleaned["evaluation_date"] = cleaned["evaluation_date"].map(_as_date)
    if "target_end_date" in cleaned.columns:
        cleaned["target_end_date"] = cleaned["target_end_date"].map(_as_date)
    for col in ("predicted_vol_annualized", "target_realized_vol_5d", "absolute_error", "squared_error"):
        if col in cleaned.columns:
            cleaned[col] = pd.to_numeric(cleaned[col], errors="coerce")
    return cleaned


def _valid_eval_mask(frame: pd.DataFrame) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype=bool)
    return (
        frame["prediction_date"].notna()
        & frame["predicted_vol_annualized"].map(lambda v: isinstance(v, (int, float, np.floating)) and math.isfinite(float(v)) and float(v) >= 0)
        & frame["target_realized_vol_5d"].map(lambda v: isinstance(v, (int, float, np.floating)) and math.isfinite(float(v)) and float(v) >= 0)
    )


def evaluate_policy_tables(
    *,
    benchmark_evaluations: pd.DataFrame,
    benchmark_predictions: pd.DataFrame,
    policy_forecasts: pd.DataFrame,
    policy_evaluations: pd.DataFrame,
    policy_detector_stream: pd.DataFrame,
    policy_decision_events: pd.DataFrame,
    policy_champion_timeline: pd.DataFrame,
    policy_failures: pd.DataFrame,
    initial_champion_by_ticker: Mapping[str, str],
    tickers: Sequence[str] = SUPPORTED_TICKERS,
    config: EvaluationConfig | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Compute matched-key Test metrics, paired comparisons, operational stats, and coverage."""
    effective_config = config or EvaluationConfig()
    bench_eval = _clean_eval_frame(benchmark_evaluations)
    if not bench_eval.empty:
        bench_eval = bench_eval.loc[bench_eval["split"].astype(str) == "test"].copy()
    pol_eval = _clean_eval_frame(policy_evaluations)
    if not pol_eval.empty:
        pol_eval = pol_eval.loc[pol_eval["split"].astype(str) == "test"].copy()

    pol_fc = policy_forecasts.copy()
    if not pol_fc.empty:
        pol_fc["prediction_date"] = pol_fc["prediction_date"].map(_as_date)
        pol_fc = pol_fc.loc[pol_fc["split"].astype(str) == "test"].copy()
    pol_fail = policy_failures.copy()
    if not pol_fail.empty:
        pol_fail["prediction_date"] = pol_fail["prediction_date"].map(_as_date)
        pol_fail = pol_fail.loc[pol_fail["split"].astype(str) == "test"].copy()

    # Build per-ticker strategy DataFrames on Test mature valid rows.
    strategy_frames_by_ticker: dict[str, dict[str, pd.DataFrame]] = {}
    matched_keys_by_ticker: dict[str, list[date]] = {}
    for ticker in tickers:
        init_model_id = str(initial_champion_by_ticker[ticker])
        if init_model_id not in POLICY_MODEL_ID_TO_NAME:
            raise EvaluationError(f"unsupported initial champion model_id for {ticker}: {init_model_id}")
        init_model_name = POLICY_MODEL_ID_TO_NAME[init_model_id]

        t_bench = bench_eval.loc[bench_eval["ticker"].astype(str) == ticker] if not bench_eval.empty else bench_eval
        t_pol = pol_eval.loc[pol_eval["ticker"].astype(str) == ticker] if not pol_eval.empty else pol_eval

        served_df = (
            t_pol.loc[(t_pol["role"] == "SERVED_CHAMPION") & _valid_eval_mask(t_pol)].copy()
            if not t_pol.empty
            else pd.DataFrame(columns=pol_eval.columns)
        )
        shadow_df = (
            t_pol.loc[(t_pol["role"] == "SHADOW_B3") & _valid_eval_mask(t_pol)].copy()
            if not t_pol.empty
            else pd.DataFrame(columns=pol_eval.columns)
        )

        frames: dict[str, pd.DataFrame] = {
            "CHAMPION_CHALLENGER_POLICY": served_df,
            "SHADOW_B3": shadow_df,
        }
        for m_name in MODEL_NAMES:
            m_df = (
                t_bench.loc[(t_bench["model_name"] == m_name) & _valid_eval_mask(t_bench)].copy()
                if not t_bench.empty
                else pd.DataFrame(columns=bench_eval.columns)
            )
            frames[m_name] = m_df
        frames["FIXED_INITIAL_CHAMPION"] = frames[init_model_name].copy()

        # Check duplicate (prediction_date) keys within any strategy for this ticker.
        for strat_name, df in frames.items():
            if not df.empty and df["prediction_date"].duplicated().any():
                raise EvaluationError(f"duplicate Test evaluation anchor for {(ticker, strat_name)}")

        # Compute strict intersection of mature valid keys across all 8 strategies.
        key_sets = [set(df["prediction_date"].tolist()) for df in frames.values()]
        common_dates = sorted(set.intersection(*key_sets)) if key_sets else []

        # Verify target_realized_vol_5d alignment across matched keys.
        if common_dates:
            ref_targets = (
                frames["CHAMPION_CHALLENGER_POLICY"]
                .set_index("prediction_date")
                .loc[common_dates, "target_realized_vol_5d"]
                .to_numpy(dtype=float)
            )
            for strat_name, df in frames.items():
                strat_targets = (
                    df.set_index("prediction_date")
                    .loc[common_dates, "target_realized_vol_5d"]
                    .to_numpy(dtype=float)
                )
                if not np.allclose(ref_targets, strat_targets, atol=1e-12, rtol=0.0):
                    raise EvaluationError(
                        f"target_realized_vol_5d mismatch on matched Test keys for {(ticker, strat_name)}"
                    )

        strategy_frames_by_ticker[ticker] = frames
        matched_keys_by_ticker[ticker] = common_dates

    # 1. Per-ETF and Equal-Weight MACRO model metrics on matched mature Test keys.
    metric_rows: list[dict[str, Any]] = []
    per_ticker_metrics: dict[str, dict[str, dict[str, Any]]] = {
        strat: {} for strat in EVALUATED_POLICY_STRATEGIES
    }
    for strat in EVALUATED_POLICY_STRATEGIES:
        for ticker in tickers:
            common_dates = matched_keys_by_ticker[ticker]
            df = strategy_frames_by_ticker[ticker][strat]
            evaluable_n = int(len(df))
            if not common_dates:
                row = {
                    "split": "test",
                    "ticker": ticker,
                    "strategy": strat,
                    "initial_champion_model_id": str(initial_champion_by_ticker[ticker]),
                    "paired_n": 0,
                    "evaluable_n": evaluable_n,
                    "mae": np.nan,
                    "rmse": np.nan,
                    "mse": np.nan,
                    "status": "INSUFFICIENT_SAMPLE",
                    "evaluation_scope": "retrospective_exploratory_non_confirmatory",
                }
            else:
                sub = df.set_index("prediction_date").loc[common_dates]
                stats = calculate_error_metrics(
                    sub["target_realized_vol_5d"].to_numpy(dtype=float),
                    sub["predicted_vol_annualized"].to_numpy(dtype=float),
                )
                mse = float(stats["rmse"]) ** 2
                row = {
                    "split": "test",
                    "ticker": ticker,
                    "strategy": strat,
                    "initial_champion_model_id": str(initial_champion_by_ticker[ticker]),
                    "paired_n": int(stats["n"]),
                    "evaluable_n": evaluable_n,
                    "mae": float(stats["mae"]),
                    "rmse": float(stats["rmse"]),
                    "mse": mse,
                    "status": "COMPUTED",
                    "evaluation_scope": "retrospective_exploratory_non_confirmatory",
                }
            metric_rows.append(row)
            per_ticker_metrics[strat][ticker] = row

        # Equal-weight MACRO across tickers (requires all tickers COMPUTED).
        ticker_rows = [per_ticker_metrics[strat][t] for t in tickers]
        if all(r["status"] == "COMPUTED" for r in ticker_rows):
            macro_mae = float(np.mean([r["mae"] for r in ticker_rows]))
            macro_mse = float(np.mean([r["mse"] for r in ticker_rows]))
            macro_rmse = float(math.sqrt(macro_mse))
            macro_status = "COMPUTED"
        else:
            macro_mae = np.nan
            macro_mse = np.nan
            macro_rmse = np.nan
            macro_status = "INSUFFICIENT_SAMPLE"
        metric_rows.append(
            {
                "split": "test",
                "ticker": "MACRO",
                "strategy": strat,
                "initial_champion_model_id": "PER_ETF",
                "paired_n": int(sum(r["paired_n"] for r in ticker_rows)),
                "evaluable_n": int(sum(r["evaluable_n"] for r in ticker_rows)),
                "mae": macro_mae,
                "rmse": macro_rmse,
                "mse": macro_mse,
                "status": macro_status,
                "evaluation_scope": "retrospective_exploratory_non_confirmatory",
            }
        )
    metrics_df = pd.DataFrame(metric_rows)

    # 2. Paired comparisons: CHAMPION_CHALLENGER_POLICY vs every comparator on matched keys.
    comparators = (
        ("POLICY_VS_FIXED_INITIAL_CHAMPION", "FIXED_INITIAL_CHAMPION"),
        ("POLICY_VS_SHADOW_B3", "SHADOW_B3"),
        ("POLICY_VS_B0", "CONSTANT_BASELINE"),
        ("POLICY_VS_B1", "ROLLING_20D_BASELINE"),
        ("POLICY_VS_B2", "STATIC_SGD"),
        ("POLICY_VS_B3", "ONLINE_SGD"),
        ("POLICY_VS_B4", "HAR_X_OLS"),
    )
    comp_rows: list[dict[str, Any]] = []
    for comp_id, comp_strat in comparators:
        per_ticker_deltas: list[dict[str, Any]] = []
        for ticker in tickers:
            pol_m = per_ticker_metrics["CHAMPION_CHALLENGER_POLICY"][ticker]
            cmp_m = per_ticker_metrics[comp_strat][ticker]
            if pol_m["status"] == "COMPUTED" and cmp_m["status"] == "COMPUTED":
                delta_mae = float(cmp_m["mae"] - pol_m["mae"])
                delta_rmse = float(cmp_m["rmse"] - pol_m["rmse"])
                rel_mae = float(delta_mae / cmp_m["mae"]) if cmp_m["mae"] > 0.0 else np.nan
                status = "COMPUTED"
            else:
                delta_mae = np.nan
                delta_rmse = np.nan
                rel_mae = np.nan
                status = "INSUFFICIENT_SAMPLE"
            c_row = {
                "comparison_id": comp_id,
                "split": "test",
                "ticker": ticker,
                "policy_strategy": "CHAMPION_CHALLENGER_POLICY",
                "comparator_strategy": comp_strat,
                "paired_n": int(pol_m["paired_n"]),
                "policy_mae": pol_m["mae"],
                "comparator_mae": cmp_m["mae"],
                "delta_mae_comparator_minus_policy": delta_mae,
                "relative_mae_improvement": rel_mae,
                "policy_rmse": pol_m["rmse"],
                "comparator_rmse": cmp_m["rmse"],
                "delta_rmse_comparator_minus_policy": delta_rmse,
                "status": status,
                "evaluation_scope": "retrospective_exploratory_non_confirmatory",
                "confirmatory_hypothesis": False,
                "test_reuse_limitation": TEST_REUSE_LIMITATION,
            }
            comp_rows.append(c_row)
            per_ticker_deltas.append(c_row)

        pol_macro = metrics_df.loc[
            (metrics_df["strategy"] == "CHAMPION_CHALLENGER_POLICY") & (metrics_df["ticker"] == "MACRO")
        ].iloc[0]
        cmp_macro = metrics_df.loc[
            (metrics_df["strategy"] == comp_strat) & (metrics_df["ticker"] == "MACRO")
        ].iloc[0]
        if all(r["status"] == "COMPUTED" for r in per_ticker_deltas):
            m_delta_mae = float(np.mean([r["delta_mae_comparator_minus_policy"] for r in per_ticker_deltas]))
            m_delta_rmse = float(cmp_macro["rmse"] - pol_macro["rmse"])
            m_rel_mae = float(m_delta_mae / cmp_macro["mae"]) if cmp_macro["mae"] > 0.0 else np.nan
            m_status = "COMPUTED"
        else:
            m_delta_mae = np.nan
            m_delta_rmse = np.nan
            m_rel_mae = np.nan
            m_status = "INSUFFICIENT_SAMPLE"
        comp_rows.append(
            {
                "comparison_id": comp_id,
                "split": "test",
                "ticker": "MACRO",
                "policy_strategy": "CHAMPION_CHALLENGER_POLICY",
                "comparator_strategy": comp_strat,
                "paired_n": int(sum(r["paired_n"] for r in per_ticker_deltas)),
                "policy_mae": float(pol_macro["mae"]) if pd.notna(pol_macro["mae"]) else np.nan,
                "comparator_mae": float(cmp_macro["mae"]) if pd.notna(cmp_macro["mae"]) else np.nan,
                "delta_mae_comparator_minus_policy": m_delta_mae,
                "relative_mae_improvement": m_rel_mae,
                "policy_rmse": float(pol_macro["rmse"]) if pd.notna(pol_macro["rmse"]) else np.nan,
                "comparator_rmse": float(cmp_macro["rmse"]) if pd.notna(cmp_macro["rmse"]) else np.nan,
                "delta_rmse_comparator_minus_policy": m_delta_rmse,
                "status": m_status,
                "evaluation_scope": "retrospective_exploratory_non_confirmatory",
                "confirmatory_hypothesis": False,
                "test_reuse_limitation": TEST_REUSE_LIMITATION,
            }
        )
    comparisons_df = pd.DataFrame(comp_rows)

    # 3. Operations, Drift, Switch, Latency, and Coverage summaries per ETF + MACRO.
    ops_rows: list[dict[str, Any]] = []
    cov_rows: list[dict[str, Any]] = []
    for ticker in tickers:
        t_fc = pol_fc.loc[pol_fc["ticker"].astype(str) == ticker] if not pol_fc.empty else pol_fc
        t_ev = pol_eval.loc[pol_eval["ticker"].astype(str) == ticker] if not pol_eval.empty else pol_eval
        t_fail = pol_fail.loc[pol_fail["ticker"].astype(str) == ticker] if not pol_fail.empty else pol_fail
        t_stream = (
            policy_detector_stream.loc[policy_detector_stream["ticker"].astype(str) == ticker]
            if not policy_detector_stream.empty
            else policy_detector_stream
        )
        t_dec = (
            policy_decision_events.loc[policy_decision_events["ticker"].astype(str) == ticker]
            if not policy_decision_events.empty
            else policy_decision_events
        )
        t_tl = (
            policy_champion_timeline.loc[policy_champion_timeline["ticker"].astype(str) == ticker]
            if not policy_champion_timeline.empty
            else policy_champion_timeline
        )

        served_fc = t_fc.loc[t_fc["role"] == "SERVED_CHAMPION"] if not t_fc.empty else t_fc
        shadow_fc = t_fc.loc[t_fc["role"] == "SHADOW_B3"] if not t_fc.empty else t_fc
        served_ev = t_ev.loc[t_ev["role"] == "SERVED_CHAMPION"] if not t_ev.empty else t_ev
        shadow_ev = t_ev.loc[t_ev["role"] == "SHADOW_B3"] if not t_ev.empty else t_ev

        served_invalid = (
            int(((t_fail["role"] == "SERVED_CHAMPION") & (t_fail["failure_type"] == "invalid_forecast")).sum())
            if not t_fail.empty
            else 0
        )
        shadow_invalid = (
            int(((t_fail["role"] == "SHADOW_B3") & (t_fail["failure_type"] == "invalid_forecast")).sum())
            if not t_fail.empty
            else 0
        )
        served_eval_fail = (
            int(((t_fail["role"] == "SERVED_CHAMPION") & (t_fail["failure_type"] == "evaluation_label_unavailable")).sum())
            if not t_fail.empty
            else 0
        )
        shadow_eval_fail = (
            int(((t_fail["role"] == "SHADOW_B3") & (t_fail["failure_type"] == "evaluation_label_unavailable")).sum())
            if not t_fail.empty
            else 0
        )
        served_pending = max(0, int(len(served_fc)) - int(len(served_ev)) - served_eval_fail)
        shadow_pending = max(0, int(len(shadow_fc)) - int(len(shadow_ev)) - shadow_eval_fail)

        for role_name, fc_n, ev_n, inv_n, pend_n, eval_fail_n in (
            ("SERVED_CHAMPION", len(served_fc), len(served_ev), served_invalid, served_pending, served_eval_fail),
            ("SHADOW_B3", len(shadow_fc), len(shadow_ev), shadow_invalid, shadow_pending, shadow_eval_fail),
        ):
            expected_n = int(fc_n + inv_n)
            cov_rows.append(
                {
                    "split": "test",
                    "ticker": ticker,
                    "role": role_name,
                    "expected_anchors_observed": expected_n,
                    "published_forecasts": int(fc_n),
                    "invalid_forecasts": int(inv_n),
                    "mature_evaluated": int(ev_n),
                    "pending_labels": int(pend_n),
                    "evaluation_failures": int(eval_fail_n),
                    "matched_common_panel_n": int(len(matched_keys_by_ticker[ticker])),
                    "publish_rate": float(fc_n / expected_n) if expected_n > 0 else np.nan,
                    "mature_evaluation_rate": float(ev_n / fc_n) if fc_n > 0 else np.nan,
                }
            )

        alerts_df = t_stream.loc[_bool_series(t_stream["drift_detected"])] if not t_stream.empty else t_stream
        promos_df = t_dec.loc[t_dec["decision_outcome"] == "promoted"] if not t_dec.empty else t_dec

        lag_days_list = [
            (ev_d - pr_d).days
            for pr_d, ev_d in zip(served_ev["prediction_date"].tolist(), served_ev["evaluation_date"].tolist())
            if pr_d is not None and ev_d is not None
        ] if not served_ev.empty else []

        alert_lag_days = [
            (_as_date(r.decision_date) - _as_date(r.trigger_prediction_date)).days
            for r in t_dec.itertuples(index=False)
            if _as_date(r.decision_date) is not None and _as_date(r.trigger_prediction_date) is not None
        ] if not t_dec.empty else []

        promo_eff_lag_days = [
            (_as_date(r.effective_from_date) - _as_date(r.decision_date)).days
            for r in promos_df.itertuples(index=False)
            if _as_date(r.effective_from_date) is not None and _as_date(r.decision_date) is not None
        ] if not promos_df.empty else []

        final_model_id = str(initial_champion_by_ticker[ticker])
        final_version_id: str | None = None
        if not t_tl.empty:
            last_tl = t_tl.iloc[-1]
            final_model_id = str(last_tl["to_model_id"])
            final_version_id = str(last_tl["to_champion_version_id"])

        stale_skipped = (
            int(_bool_series(served_ev["stale_champion_skipped_from_policy"]).sum())
            if not served_ev.empty and "stale_champion_skipped_from_policy" in served_ev.columns
            else 0
        )

        outcome_counts = (
            t_dec["decision_outcome"].value_counts().to_dict() if not t_dec.empty else {}
        )
        ops_rows.append(
            {
                "split": "test",
                "ticker": ticker,
                "initial_champion_model_id": str(initial_champion_by_ticker[ticker]),
                "final_champion_model_id": final_model_id,
                "final_champion_version_id": final_version_id,
                "matched_common_panel_n": int(len(matched_keys_by_ticker[ticker])),
                "detector_observation_count": int(len(t_stream)),
                "alert_count": int(len(alerts_df)),
                "decision_event_count": int(len(t_dec)),
                "promotion_count": int(outcome_counts.get("promoted", 0)),
                "retained_count": int(outcome_counts.get("retained", 0)),
                "insufficient_pairs_count": int(outcome_counts.get("insufficient_pairs", 0)),
                "invalid_decision_count": int(outcome_counts.get("invalid", 0)),
                "cooldown_suppressed_count": int(outcome_counts.get("cooldown_suppressed", 0)),
                "stale_champion_skipped_eval_count": stale_skipped,
                "served_invalid_forecast_count": served_invalid,
                "shadow_invalid_forecast_count": shadow_invalid,
                "pending_served_forecast_count": served_pending,
                "mean_label_maturity_lag_calendar_days": (
                    float(np.mean(lag_days_list)) if lag_days_list else np.nan
                ),
                "mean_trigger_anchor_to_decision_calendar_days": (
                    float(np.mean(alert_lag_days)) if alert_lag_days else np.nan
                ),
                "mean_decision_to_effective_calendar_days": (
                    float(np.mean(promo_eff_lag_days)) if promo_eff_lag_days else np.nan
                ),
                "first_alert_date": (
                    min(_as_date(v) for v in alerts_df["evaluation_date"] if _as_date(v) is not None).isoformat()
                    if not alerts_df.empty
                    else None
                ),
                "first_promotion_date": (
                    min(_as_date(v) for v in promos_df["decision_date"] if _as_date(v) is not None).isoformat()
                    if not promos_df.empty
                    else None
                ),
                "zero_alerts_observed": len(alerts_df) == 0,
                "zero_promotions_observed": len(promos_df) == 0,
            }
        )

    # Aggregate ALL/MACRO row for operations summary.
    ops_df_tickers = pd.DataFrame(ops_rows)
    ops_rows.append(
        {
            "split": "test",
            "ticker": "MACRO",
            "initial_champion_model_id": "PER_ETF",
            "final_champion_model_id": "PER_ETF",
            "final_champion_version_id": None,
            "matched_common_panel_n": int(ops_df_tickers["matched_common_panel_n"].sum()),
            "detector_observation_count": int(ops_df_tickers["detector_observation_count"].sum()),
            "alert_count": int(ops_df_tickers["alert_count"].sum()),
            "decision_event_count": int(ops_df_tickers["decision_event_count"].sum()),
            "promotion_count": int(ops_df_tickers["promotion_count"].sum()),
            "retained_count": int(ops_df_tickers["retained_count"].sum()),
            "insufficient_pairs_count": int(ops_df_tickers["insufficient_pairs_count"].sum()),
            "invalid_decision_count": int(ops_df_tickers["invalid_decision_count"].sum()),
            "cooldown_suppressed_count": int(ops_df_tickers["cooldown_suppressed_count"].sum()),
            "stale_champion_skipped_eval_count": int(ops_df_tickers["stale_champion_skipped_eval_count"].sum()),
            "served_invalid_forecast_count": int(ops_df_tickers["served_invalid_forecast_count"].sum()),
            "shadow_invalid_forecast_count": int(ops_df_tickers["shadow_invalid_forecast_count"].sum()),
            "pending_served_forecast_count": int(ops_df_tickers["pending_served_forecast_count"].sum()),
            "mean_label_maturity_lag_calendar_days": (
                float(ops_df_tickers["mean_label_maturity_lag_calendar_days"].mean(skipna=True))
                if ops_df_tickers["mean_label_maturity_lag_calendar_days"].notna().any()
                else np.nan
            ),
            "mean_trigger_anchor_to_decision_calendar_days": (
                float(ops_df_tickers["mean_trigger_anchor_to_decision_calendar_days"].mean(skipna=True))
                if ops_df_tickers["mean_trigger_anchor_to_decision_calendar_days"].notna().any()
                else np.nan
            ),
            "mean_decision_to_effective_calendar_days": (
                float(ops_df_tickers["mean_decision_to_effective_calendar_days"].mean(skipna=True))
                if ops_df_tickers["mean_decision_to_effective_calendar_days"].notna().any()
                else np.nan
            ),
            "first_alert_date": (
                min(v for v in ops_df_tickers["first_alert_date"].dropna().tolist())
                if ops_df_tickers["first_alert_date"].notna().any()
                else None
            ),
            "first_promotion_date": (
                min(v for v in ops_df_tickers["first_promotion_date"].dropna().tolist())
                if ops_df_tickers["first_promotion_date"].notna().any()
                else None
            ),
            "zero_alerts_observed": int(ops_df_tickers["alert_count"].sum()) == 0,
            "zero_promotions_observed": int(ops_df_tickers["promotion_count"].sum()) == 0,
        }
    )
    return metrics_df, comparisons_df, pd.DataFrame(ops_rows), pd.DataFrame(cov_rows)


def _render_summary_markdown(
    *,
    evaluation_id: str,
    replay_manifest: Mapping[str, Any],
    metrics_df: pd.DataFrame,
    comparisons_df: pd.DataFrame,
    ops_df: pd.DataFrame,
) -> str:
    macro_ops = ops_df.loc[ops_df["ticker"] == "MACRO"].iloc[0]
    macro_vs_fixed = comparisons_df.loc[
        (comparisons_df["comparison_id"] == "POLICY_VS_FIXED_INITIAL_CHAMPION")
        & (comparisons_df["ticker"] == "MACRO")
    ].iloc[0]
    lines = [
        "# Stage 06 Exploratory Policy Evaluation: Drift-Triggered Champion–Challenger",
        "",
        f"- **Policy Evaluation Version:** `{POLICY_EVALUATION_VERSION}`",
        f"- **Evaluation ID:** `{evaluation_id}`",
        f"- **Replay Experiment ID:** `{replay_manifest['experiment_id']}`",
        f"- **Policy Version:** `{replay_manifest.get('champion_challenger_policy', {}).get('policy_version')}`",
        f"- **Policy Config Fingerprint:** `{replay_manifest.get('policy_config_fingerprint')}`",
        f"- **Confirmatory Hypotheses H1–H3:** Unchanged and evaluated strictly separately (`1.1.0`).",
        "",
        "## Mandatory Limitations & Framing",
        f"1. **Exploratory / Test Reuse:** {TEST_REUSE_LIMITATION}",
        f"2. **Simulated Historical Replay / PIT:** {PIT_LIMITATION}",
        f"3. **Shadow Process vs Frozen Snapshot:** {SHADOW_PROCESS_LIMITATION}",
        "",
        "## Headline Test Summary (Matched Mature Panel)",
        f"- **Total Alerts:** `{int(macro_ops['alert_count'])}` (`zero_alerts_observed={bool(macro_ops['zero_alerts_observed'])}`)",
        f"- **Total Decisions:** `{int(macro_ops['decision_event_count'])}`",
        f"- **Total Promotions:** `{int(macro_ops['promotion_count'])}` (`zero_promotions_observed={bool(macro_ops['zero_promotions_observed'])}`)",
        f"- **Macro Policy MAE vs Fixed Initial Champion MAE:** `{macro_vs_fixed['policy_mae']}` vs `{macro_vs_fixed['comparator_mae']}` (`delta={macro_vs_fixed['delta_mae_comparator_minus_policy']}`)",
        "",
        "## Per-ETF Policy Metrics (Matched Mature Panel)",
        "",
        "| Ticker | Strategy | Paired N | MAE | RMSE | Status |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    for row in metrics_df.loc[
        metrics_df["strategy"].isin(
            ("CHAMPION_CHALLENGER_POLICY", "FIXED_INITIAL_CHAMPION", "SHADOW_B3", "STATIC_SGD", "ONLINE_SGD", "HAR_X_OLS")
        )
    ].itertuples(index=False):
        mae_str = f"{row.mae:.6f}" if pd.notna(row.mae) else "N/A"
        rmse_str = f"{row.rmse:.6f}" if pd.notna(row.rmse) else "N/A"
        lines.append(f"| {row.ticker} | {row.strategy} | {row.paired_n} | {mae_str} | {rmse_str} | {row.status} |")
    return "\n".join(lines) + "\n"


def run_policy_evaluation(
    replay_dir: str | Path,
    *,
    output_root: str | Path | None = None,
    config: EvaluationConfig | None = None,
    require_strict_cutoff: bool = True,
) -> PolicyEvaluationResult:
    """Verify and evaluate a completed Stage 05 Drift-Triggered Champion-Challenger replay."""
    effective_config = config or EvaluationConfig()
    replay_manifest, outputs, verified_hashes, reconciliation = verify_policy_replay_artifacts(
        replay_dir,
        config=effective_config,
        require_strict_cutoff=require_strict_cutoff,
    )
    metrics_df, comparisons_df, ops_df, cov_df = evaluate_policy_tables(
        benchmark_evaluations=outputs["evaluation.csv"],
        benchmark_predictions=outputs["asset_volatility_predictions.csv"],
        policy_forecasts=outputs["policy_forecasts.csv"],
        policy_evaluations=outputs["policy_evaluations.csv"],
        policy_detector_stream=outputs["policy_detector_stream.csv"],
        policy_decision_events=outputs["policy_decision_events.csv"],
        policy_champion_timeline=outputs["policy_champion_timeline.csv"],
        policy_failures=outputs["policy_failures.csv"],
        initial_champion_by_ticker=replay_manifest["initial_champion"],
        tickers=effective_config.tickers,
        config=effective_config,
    )
    identity_payload = {
        "policy_evaluation_version": POLICY_EVALUATION_VERSION,
        "replay_experiment_id": replay_manifest["experiment_id"],
        "policy_config_fingerprint": replay_manifest.get("policy_config_fingerprint"),
        "replay_outputs_sha256": verified_hashes,
        "evaluation_config_version": effective_config.evaluation_config_version,
    }
    evaluation_id = _canonical_sha256(identity_payload)
    summary_md = _render_summary_markdown(
        evaluation_id=evaluation_id,
        replay_manifest=replay_manifest,
        metrics_df=metrics_df,
        comparisons_df=comparisons_df,
        ops_df=ops_df,
    )

    manifest: dict[str, Any] = {
        "stage": "06_policy_evaluation",
        "policy_evaluation_version": POLICY_EVALUATION_VERSION,
        "evaluation_id": evaluation_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "replay_experiment_id": replay_manifest["experiment_id"],
        "replay_config_version": replay_manifest["replay_config"]["replay_config_version"],
        "policy_version": replay_manifest["champion_challenger_policy"]["policy_version"],
        "policy_config_fingerprint": replay_manifest.get("policy_config_fingerprint"),
        "initial_champion": replay_manifest["initial_champion"],
        "source_lineage": replay_manifest.get("source_lineage", {}),
        "replay_window": replay_manifest.get("replay_window", {}),
        "test_reuse_exploratory_only": True,
        "h1_h3_confirmatory_unchanged": True,
        "point_in_time_source_availability_verified": False,
        "limitations": [
            TEST_REUSE_LIMITATION,
            PIT_LIMITATION,
            SHADOW_PROCESS_LIMITATION,
            *list(replay_manifest.get("limitations", [])),
        ],
        "replay_outputs_sha256": verified_hashes,
        "reconciliation": reconciliation,
        "artifact_sha256": {},
    }

    artifact_dir: Path | None = None
    if output_root is not None:
        base = Path(output_root).expanduser().resolve()
        target = base / "policy_experiments" / evaluation_id
        if target.exists():
            raise FileExistsError(f"policy evaluation artifact directory already exists: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=f".{target.name}.stage06p-", dir=target.parent)).resolve()
        try:
            file_map = {
                "policy_model_metrics.csv": metrics_df,
                "policy_comparisons.csv": comparisons_df,
                "policy_operations_summary.csv": ops_df,
                "policy_coverage_summary.csv": cov_df,
            }
            for filename, df in file_map.items():
                df.to_csv(stage / filename, index=False, float_format="%.17g", lineterminator="\n")
            (stage / "policy_reconciliation.json").write_text(
                json.dumps(reconciliation, indent=2, sort_keys=True, default=_json_default) + "\n",
                encoding="utf-8",
            )
            (stage / "policy_evaluation_summary.md").write_text(summary_md, encoding="utf-8")

            hashed_files = [
                *file_map.keys(),
                "policy_reconciliation.json",
                "policy_evaluation_summary.md",
            ]
            manifest["artifact_sha256"] = {
                name: _file_sha256(stage / name) for name in hashed_files
            }
            (stage / "policy_evaluation_manifest.json").write_text(
                json.dumps(manifest, indent=2, sort_keys=True, default=_json_default) + "\n",
                encoding="utf-8",
            )
            stage.replace(target)
            artifact_dir = target
        except Exception:
            if stage.exists() and stage.parent == target.parent:
                shutil.rmtree(stage)
            raise

    return PolicyEvaluationResult(
        evaluation_id=evaluation_id,
        policy_evaluation_version=POLICY_EVALUATION_VERSION,
        replay_experiment_id=str(replay_manifest["experiment_id"]),
        artifact_dir=artifact_dir,
        model_metrics=metrics_df,
        comparisons=comparisons_df,
        operations_summary=ops_df,
        coverage_summary=cov_df,
        reconciliation=reconciliation,
        manifest=manifest,
    )
