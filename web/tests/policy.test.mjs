import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  loadPolicySnapshot,
  POLICY_EXPECTED_HEADERS,
  selectPolicyDayState,
} from "../dist/assets/data/policySnapshot.js";
import { renderPolicyMonitoringPanel, renderReplayPolicyCard } from "../dist/assets/policyView.js";
import { renderMonitoringFeatureDrift } from "../dist/assets/featureDriftView.js";
import { parseDriftTimeline } from "../dist/assets/data/loadSnapshot.js";
import { parseDriftTimelineRow } from "../dist/assets/data/schemas.js";

const sha256Hex = (bytes) => createHash("sha256").update(bytes).digest("hex");
const encode = (text) => new TextEncoder().encode(text);
const toCsv = (headers, rows) =>
  `${headers.join(",")}\n${rows.map((row) => headers.map((h) => String(row[h] ?? "")).join(",")).join("\n")}${rows.length ? "\n" : ""}`;

const HASH_A = "a".repeat(64);
const HASH_B = "b".repeat(64);
const HASH_C = "c".repeat(64);
const HASH_CFG = "d".repeat(64);
const EVAL_ID = "1".repeat(64);
const REPLAY_ID = "2".repeat(64);

function buildPolicyFixture({ withAlerts = true } = {}) {
  const fcBase = {
    experiment_id: REPLAY_ID, policy_version: "1.0.0", split: "test",
    model_version: "v1.0.0", prediction_mode: "historical_replay",
    forecast_horizon_trading_days: "5", feature_set_version: "2.0.0",
    feature_run_id: "feat_fixture", input_snapshot_id: "snap_fixture",
    last_training_target_end_date: "2024-09-30", champion_effective_from_date: "2025-10-01",
    run_id: "run_fixture", prediction_created_at_utc: "2026-11-23T00:00:00Z",
  };
  const forecasts = [
    { ...fcBase, policy_prediction_id: "pf-spy-1-s", prediction_date: "2026-01-02", ticker: "SPY", role: "SERVED_CHAMPION", champion_version_id: "v001", model_id: "B2", model_name: "STATIC_SGD", is_frozen_snapshot: "True", state_sha256: HASH_A, target_start_date: "2026-01-03", target_end_date: "2026-01-08", predicted_vol_annualized: "0.1400" },
    { ...fcBase, policy_prediction_id: "pf-spy-1-h", prediction_date: "2026-01-02", ticker: "SPY", role: "SHADOW_B3", champion_version_id: "shadow_b3", model_id: "B3", model_name: "ONLINE_SGD", is_frozen_snapshot: "False", state_sha256: HASH_B, target_start_date: "2026-01-03", target_end_date: "2026-01-08", predicted_vol_annualized: "0.1300" },
    { ...fcBase, policy_prediction_id: "pf-spy-2-s", prediction_date: "2026-01-09", ticker: "SPY", role: "SERVED_CHAMPION", champion_version_id: "v001", model_id: "B2", model_name: "STATIC_SGD", is_frozen_snapshot: "True", state_sha256: HASH_A, target_start_date: "2026-01-12", target_end_date: "2026-01-16", predicted_vol_annualized: "0.1500" },
    { ...fcBase, policy_prediction_id: "pf-spy-2-h", prediction_date: "2026-01-09", ticker: "SPY", role: "SHADOW_B3", champion_version_id: "shadow_b3", model_id: "B3", model_name: "ONLINE_SGD", is_frozen_snapshot: "False", state_sha256: HASH_B, target_start_date: "2026-01-12", target_end_date: "2026-01-16", predicted_vol_annualized: "0.1450" },
    { ...fcBase, policy_prediction_id: "pf-ief-1-s", prediction_date: "2026-01-02", ticker: "IEF", role: "SERVED_CHAMPION", champion_version_id: "v001", model_id: "B2", model_name: "STATIC_SGD", is_frozen_snapshot: "True", state_sha256: HASH_A, target_start_date: "2026-01-03", target_end_date: "2026-01-08", predicted_vol_annualized: "0.0600" },
    { ...fcBase, policy_prediction_id: "pf-ief-1-h", prediction_date: "2026-01-02", ticker: "IEF", role: "SHADOW_B3", champion_version_id: "shadow_b3", model_id: "B3", model_name: "ONLINE_SGD", is_frozen_snapshot: "False", state_sha256: HASH_B, target_start_date: "2026-01-03", target_end_date: "2026-01-08", predicted_vol_annualized: "0.0590" },
    { ...fcBase, policy_prediction_id: "pf-gld-1-s", prediction_date: "2026-01-02", ticker: "GLD", role: "SERVED_CHAMPION", champion_version_id: "v001", model_id: "B2", model_name: "STATIC_SGD", is_frozen_snapshot: "True", state_sha256: HASH_A, target_start_date: "2026-01-03", target_end_date: "2026-01-08", predicted_vol_annualized: "0.1800" },
    { ...fcBase, policy_prediction_id: "pf-gld-1-h", prediction_date: "2026-01-02", ticker: "GLD", role: "SHADOW_B3", champion_version_id: "shadow_b3", model_id: "B3", model_name: "ONLINE_SGD", is_frozen_snapshot: "False", state_sha256: HASH_B, target_start_date: "2026-01-03", target_end_date: "2026-01-08", predicted_vol_annualized: "0.1100" },
    { ...fcBase, policy_prediction_id: "pf-gld-2-s", prediction_date: "2026-01-08", ticker: "GLD", role: "SERVED_CHAMPION", champion_version_id: "v001", model_id: "B2", model_name: "STATIC_SGD", is_frozen_snapshot: "True", state_sha256: HASH_A, target_start_date: "2026-01-09", target_end_date: "2026-01-15", predicted_vol_annualized: "0.1750" },
    { ...fcBase, policy_prediction_id: "pf-gld-2-h", prediction_date: "2026-01-08", ticker: "GLD", role: "SHADOW_B3", champion_version_id: "shadow_b3", model_id: "B3", model_name: "ONLINE_SGD", is_frozen_snapshot: "False", state_sha256: HASH_B, target_start_date: "2026-01-09", target_end_date: "2026-01-15", predicted_vol_annualized: "0.1120" },
    { ...fcBase, policy_prediction_id: "pf-gld-3-s", prediction_date: "2026-01-09", ticker: "GLD", role: "SERVED_CHAMPION", champion_version_id: withAlerts ? "v002" : "v001", model_id: withAlerts ? "B3" : "B2", model_name: withAlerts ? "ONLINE_SGD" : "STATIC_SGD", is_frozen_snapshot: "True", state_sha256: withAlerts ? HASH_C : HASH_A, target_start_date: "2026-01-12", target_end_date: "2026-01-16", predicted_vol_annualized: withAlerts ? "0.1110" : "0.1760", champion_effective_from_date: withAlerts ? "2026-01-09" : "2025-10-01" },
    { ...fcBase, policy_prediction_id: "pf-gld-3-h", prediction_date: "2026-01-09", ticker: "GLD", role: "SHADOW_B3", champion_version_id: "shadow_b3", model_id: "B3", model_name: "ONLINE_SGD", is_frozen_snapshot: "False", state_sha256: HASH_B, target_start_date: "2026-01-12", target_end_date: "2026-01-16", predicted_vol_annualized: "0.1110" },
  ];

  const evBase = {
    experiment_id: REPLAY_ID, policy_version: "1.0.0", split: "test", model_version: "v1.0.0",
    target_version: "2.0.0", evaluation_date: "2026-01-08", label_available_replay_date: "2026-01-08",
    stale_champion_skipped_from_policy: "False", policy_skip_reason: "",
    prediction_run_id: "run_fixture", evaluation_run_id: "run_fixture",
  };
  const evaluations = [
    { ...evBase, policy_prediction_id: "pf-spy-1-s", prediction_date: "2026-01-02", ticker: "SPY", role: "SERVED_CHAMPION", champion_version_id: "v001", active_champion_version_id_at_eval: "v001", model_id: "B2", model_name: "STATIC_SGD", is_frozen_snapshot: "True", state_sha256: HASH_A, target_start_date: "2026-01-03", target_end_date: "2026-01-08", predicted_vol_annualized: "0.1400", target_realized_vol_5d: "0.1000", absolute_error: "0.0400", squared_error: "0.0016" },
    { ...evBase, policy_prediction_id: "pf-spy-1-h", prediction_date: "2026-01-02", ticker: "SPY", role: "SHADOW_B3", champion_version_id: "shadow_b3", active_champion_version_id_at_eval: "v001", model_id: "B3", model_name: "ONLINE_SGD", is_frozen_snapshot: "False", state_sha256: HASH_B, target_start_date: "2026-01-03", target_end_date: "2026-01-08", predicted_vol_annualized: "0.1300", target_realized_vol_5d: "0.1000", absolute_error: "0.0300", squared_error: "0.0009" },
    { ...evBase, policy_prediction_id: "pf-ief-1-s", prediction_date: "2026-01-02", ticker: "IEF", role: "SERVED_CHAMPION", champion_version_id: "v001", active_champion_version_id_at_eval: "v001", model_id: "B2", model_name: "STATIC_SGD", is_frozen_snapshot: "True", state_sha256: HASH_A, target_start_date: "2026-01-03", target_end_date: "2026-01-08", predicted_vol_annualized: "0.0600", target_realized_vol_5d: "0.0500", absolute_error: "0.0100", squared_error: "0.0001" },
    { ...evBase, policy_prediction_id: "pf-ief-1-h", prediction_date: "2026-01-02", ticker: "IEF", role: "SHADOW_B3", champion_version_id: "shadow_b3", active_champion_version_id_at_eval: "v001", model_id: "B3", model_name: "ONLINE_SGD", is_frozen_snapshot: "False", state_sha256: HASH_B, target_start_date: "2026-01-03", target_end_date: "2026-01-08", predicted_vol_annualized: "0.0590", target_realized_vol_5d: "0.0500", absolute_error: "0.0090", squared_error: "0.000081" },
    { ...evBase, policy_prediction_id: "pf-gld-1-s", prediction_date: "2026-01-02", ticker: "GLD", role: "SERVED_CHAMPION", champion_version_id: "v001", active_champion_version_id_at_eval: "v001", model_id: "B2", model_name: "STATIC_SGD", is_frozen_snapshot: "True", state_sha256: HASH_A, target_start_date: "2026-01-03", target_end_date: "2026-01-08", predicted_vol_annualized: "0.1800", target_realized_vol_5d: "0.1000", absolute_error: "0.0800", squared_error: "0.0064" },
    { ...evBase, policy_prediction_id: "pf-gld-1-h", prediction_date: "2026-01-02", ticker: "GLD", role: "SHADOW_B3", champion_version_id: "shadow_b3", active_champion_version_id_at_eval: "v001", model_id: "B3", model_name: "ONLINE_SGD", is_frozen_snapshot: "False", state_sha256: HASH_B, target_start_date: "2026-01-03", target_end_date: "2026-01-08", predicted_vol_annualized: "0.1100", target_realized_vol_5d: "0.1000", absolute_error: "0.0100", squared_error: "0.0001" },
  ];

  const detectorStream = [
    { experiment_id: REPLAY_ID, policy_version: "1.0.0", policy_prediction_id: "pf-spy-1-s", prediction_date: "2026-01-02", evaluation_date: "2026-01-08", ticker: "SPY", champion_version_id: "v001", champion_model_id: "B2", champion_state_sha256: HASH_A, feed_order_in_session: "1", absolute_error: "0.0400", adwin_delta: "0.002", adwin_width: "32", adwin_estimation_before: "0.020", adwin_estimation: "0.035", drift_detected: withAlerts ? "True" : "False", drift_direction: withAlerts ? "error_increase" : "no_signal", triggered_decision: withAlerts ? "True" : "False", cooldown_active: "False", cooldown_remaining_before: "0", prediction_run_id: "run_fixture", evaluation_run_id: "run_fixture" },
    { experiment_id: REPLAY_ID, policy_version: "1.0.0", policy_prediction_id: "pf-ief-1-s", prediction_date: "2026-01-02", evaluation_date: "2026-01-08", ticker: "IEF", champion_version_id: "v001", champion_model_id: "B2", champion_state_sha256: HASH_A, feed_order_in_session: "1", absolute_error: "0.0100", adwin_delta: "0.002", adwin_width: "40", adwin_estimation_before: "0.008", adwin_estimation: "0.011", drift_detected: withAlerts ? "True" : "False", drift_direction: withAlerts ? "error_increase" : "no_signal", triggered_decision: withAlerts ? "True" : "False", cooldown_active: "False", cooldown_remaining_before: "0", prediction_run_id: "run_fixture", evaluation_run_id: "run_fixture" },
    { experiment_id: REPLAY_ID, policy_version: "1.0.0", policy_prediction_id: "pf-gld-1-s", prediction_date: "2026-01-02", evaluation_date: "2026-01-08", ticker: "GLD", champion_version_id: "v001", champion_model_id: "B2", champion_state_sha256: HASH_A, feed_order_in_session: "1", absolute_error: "0.0800", adwin_delta: "0.002", adwin_width: "64", adwin_estimation_before: "0.025", adwin_estimation: "0.042", drift_detected: withAlerts ? "True" : "False", drift_direction: withAlerts ? "error_increase" : "no_signal", triggered_decision: withAlerts ? "True" : "False", cooldown_active: "False", cooldown_remaining_before: "0", prediction_run_id: "run_fixture", evaluation_run_id: "run_fixture" },
  ];

  const decisionEvents = withAlerts
    ? [
        { experiment_id: REPLAY_ID, policy_version: "1.0.0", event_id: "ev-spy-1", decision_date: "2026-01-08", ticker: "SPY", trigger_prediction_id: "pf-spy-1-s", trigger_prediction_date: "2026-01-02", drift_direction: "error_increase", adwin_estimation_before: "0.020", adwin_estimation_after: "0.035", adwin_width: "32", champion_version_id_before: "v001", champion_model_id_before: "B2", champion_state_sha256_before: HASH_A, shadow_model_id: "B3", shadow_state_sha256_pre_update: HASH_B, comparison_window_pairs: "60", minimum_pairs: "30", min_relative_improvement: "0.05", valid_pair_count: "12", champion_window_mae: "0.0400", shadow_b3_window_mae: "0.0300", relative_improvement: "0.25", decision_outcome: "insufficient_pairs", decision_reason: "valid_pair_count_below_minimum_30", switched: "False", champion_version_id_after: "v001", champion_model_id_after: "B2", champion_state_sha256_after: HASH_A, effective_from_date: "", rollback_target_version_id: "", rollback_target_model_id: "", rollback_target_state_sha256: "", cooldown_active: "False", cooldown_remaining_before: "0", cooldown_remaining_after: "20", detector_reset_after_decision: "False", run_id: "run_fixture" },
        { experiment_id: REPLAY_ID, policy_version: "1.0.0", event_id: "ev-ief-1", decision_date: "2026-01-08", ticker: "IEF", trigger_prediction_id: "pf-ief-1-s", trigger_prediction_date: "2026-01-02", drift_direction: "error_increase", adwin_estimation_before: "0.008", adwin_estimation_after: "0.011", adwin_width: "40", champion_version_id_before: "v001", champion_model_id_before: "B2", champion_state_sha256_before: HASH_A, shadow_model_id: "B3", shadow_state_sha256_pre_update: HASH_B, comparison_window_pairs: "60", minimum_pairs: "30", min_relative_improvement: "0.05", valid_pair_count: "45", champion_window_mae: "0.0100", shadow_b3_window_mae: "0.0098", relative_improvement: "0.02", decision_outcome: "retained", decision_reason: "relative_improvement_below_threshold", switched: "False", champion_version_id_after: "v001", champion_model_id_after: "B2", champion_state_sha256_after: HASH_A, effective_from_date: "", rollback_target_version_id: "", rollback_target_model_id: "", rollback_target_state_sha256: "", cooldown_active: "False", cooldown_remaining_before: "0", cooldown_remaining_after: "20", detector_reset_after_decision: "False", run_id: "run_fixture" },
        { experiment_id: REPLAY_ID, policy_version: "1.0.0", event_id: "ev-gld-1", decision_date: "2026-01-08", ticker: "GLD", trigger_prediction_id: "pf-gld-1-s", trigger_prediction_date: "2026-01-02", drift_direction: "error_increase", adwin_estimation_before: "0.025", adwin_estimation_after: "0.042", adwin_width: "64", champion_version_id_before: "v001", champion_model_id_before: "B2", champion_state_sha256_before: HASH_A, shadow_model_id: "B3", shadow_state_sha256_pre_update: HASH_B, comparison_window_pairs: "60", minimum_pairs: "30", min_relative_improvement: "0.05", valid_pair_count: "48", champion_window_mae: "0.0800", shadow_b3_window_mae: "0.0500", relative_improvement: "0.375", decision_outcome: "promoted", decision_reason: "challenger_beat_champion_by_at_least_5pct", switched: "True", champion_version_id_after: "v002", champion_model_id_after: "B3", champion_state_sha256_after: HASH_C, effective_from_date: "2026-01-09", rollback_target_version_id: "v001", rollback_target_model_id: "B2", rollback_target_state_sha256: HASH_A, cooldown_active: "False", cooldown_remaining_before: "0", cooldown_remaining_after: "20", detector_reset_after_decision: "True", run_id: "run_fixture" },
      ]
    : [];

  const championTimeline = [
    { experiment_id: REPLAY_ID, policy_version: "1.0.0", timeline_event_id: "tl-spy-init", event_type: "INITIAL_CHAMPION_CUTOVER", recorded_date: "2025-10-01", decision_date: "2025-09-30", effective_from_date: "2025-10-01", ticker: "SPY", version_seq: "1", from_champion_version_id: "", from_model_id: "", from_state_sha256: "", to_champion_version_id: "v001", to_model_id: "B2", to_state_sha256: HASH_A, rollback_target_version_id: "", rollback_target_model_id: "", rollback_target_state_sha256: "", decision_event_id: "", reason: "initial_validation_cutover_selection", run_id: "run_fixture" },
    { experiment_id: REPLAY_ID, policy_version: "1.0.0", timeline_event_id: "tl-ief-init", event_type: "INITIAL_CHAMPION_CUTOVER", recorded_date: "2025-10-01", decision_date: "2025-09-30", effective_from_date: "2025-10-01", ticker: "IEF", version_seq: "1", from_champion_version_id: "", from_model_id: "", from_state_sha256: "", to_champion_version_id: "v001", to_model_id: "B2", to_state_sha256: HASH_A, rollback_target_version_id: "", rollback_target_model_id: "", rollback_target_state_sha256: "", decision_event_id: "", reason: "initial_validation_cutover_selection", run_id: "run_fixture" },
    { experiment_id: REPLAY_ID, policy_version: "1.0.0", timeline_event_id: "tl-gld-init", event_type: "INITIAL_CHAMPION_CUTOVER", recorded_date: "2025-10-01", decision_date: "2025-09-30", effective_from_date: "2025-10-01", ticker: "GLD", version_seq: "1", from_champion_version_id: "", from_model_id: "", from_state_sha256: "", to_champion_version_id: "v001", to_model_id: "B2", to_state_sha256: HASH_A, rollback_target_version_id: "", rollback_target_model_id: "", rollback_target_state_sha256: "", decision_event_id: "", reason: "initial_validation_cutover_selection", run_id: "run_fixture" },
    ...(withAlerts
      ? [{ experiment_id: REPLAY_ID, policy_version: "1.0.0", timeline_event_id: "tl-gld-promo-1", event_type: "PROMOTED_SNAPSHOT_ACTIVE_NEXT_SESSION", recorded_date: "2026-01-08", decision_date: "2026-01-08", effective_from_date: "2026-01-09", ticker: "GLD", version_seq: "2", from_champion_version_id: "v001", from_model_id: "B2", from_state_sha256: HASH_A, to_champion_version_id: "v002", to_model_id: "B3", to_state_sha256: HASH_C, rollback_target_version_id: "v001", rollback_target_model_id: "B2", rollback_target_state_sha256: HASH_A, decision_event_id: "ev-gld-1", reason: "challenger_beat_champion_by_at_least_5pct", run_id: "run_fixture" }]
      : []),
  ];

  const failures = withAlerts
    ? [{ experiment_id: REPLAY_ID, policy_version: "1.0.0", prediction_date: "2026-01-12", split: "test", ticker: "SPY", role: "SERVED_CHAMPION", champion_version_id: "v001", model_id: "B2", model_name: "STATIC_SGD", failure_type: "INVALID_FORECAST", reason: "negative_prediction_unclipped", raw_value: "-0.042", run_id: "run_fixture" }]
    : [];

  const modelMetrics = [
    { split: "test", ticker: "SPY", strategy: "CHAMPION_CHALLENGER_POLICY", initial_champion_model_id: "B2", paired_n: "1", evaluable_n: "1", mae: "0.0400", rmse: "0.0400", mse: "0.0016", status: "COMPUTED", evaluation_scope: "retrospective_exploratory_non_confirmatory" },
    { split: "test", ticker: "IEF", strategy: "CHAMPION_CHALLENGER_POLICY", initial_champion_model_id: "B2", paired_n: "1", evaluable_n: "1", mae: "0.0100", rmse: "0.0100", mse: "0.0001", status: "COMPUTED", evaluation_scope: "retrospective_exploratory_non_confirmatory" },
    { split: "test", ticker: "GLD", strategy: "CHAMPION_CHALLENGER_POLICY", initial_champion_model_id: "B2", paired_n: "1", evaluable_n: "1", mae: "0.0800", rmse: "0.0800", mse: "0.0064", status: "COMPUTED", evaluation_scope: "retrospective_exploratory_non_confirmatory" },
    { split: "test", ticker: "MACRO", strategy: "CHAMPION_CHALLENGER_POLICY", initial_champion_model_id: "PER_ETF", paired_n: "3", evaluable_n: "3", mae: "0.043333", rmse: "0.051962", mse: "0.0027", status: "COMPUTED", evaluation_scope: "retrospective_exploratory_non_confirmatory" },
  ];

  const comparisons = [
    { comparison_id: "POLICY_VS_FIXED_INITIAL_CHAMPION", split: "test", ticker: "GLD", policy_strategy: "CHAMPION_CHALLENGER_POLICY", comparator_strategy: "FIXED_INITIAL_CHAMPION", paired_n: "1", policy_mae: "0.0800", comparator_mae: "0.0900", delta_mae_comparator_minus_policy: "0.0100", relative_mae_improvement: "0.1111", policy_rmse: "0.0800", comparator_rmse: "0.0900", delta_rmse_comparator_minus_policy: "0.0100", status: "COMPUTED", evaluation_scope: "retrospective_exploratory_non_confirmatory", confirmatory_hypothesis: "False", test_reuse_limitation: "Exploratory fixture" },
    { comparison_id: "POLICY_VS_FIXED_INITIAL_CHAMPION", split: "test", ticker: "MACRO", policy_strategy: "CHAMPION_CHALLENGER_POLICY", comparator_strategy: "FIXED_INITIAL_CHAMPION", paired_n: "3", policy_mae: "0.043333", comparator_mae: "0.046667", delta_mae_comparator_minus_policy: "0.003334", relative_mae_improvement: "0.0714", policy_rmse: "0.051962", comparator_rmse: "0.055000", delta_rmse_comparator_minus_policy: "0.003038", status: "COMPUTED", evaluation_scope: "retrospective_exploratory_non_confirmatory", confirmatory_hypothesis: "False", test_reuse_limitation: "Exploratory fixture" },
  ];

  const operationsSummary = [
    { split: "test", ticker: "SPY", initial_champion_model_id: "B2", final_champion_model_id: "B2", final_champion_version_id: "v001", matched_common_panel_n: "1", detector_observation_count: "1", alert_count: withAlerts ? "1" : "0", decision_event_count: withAlerts ? "1" : "0", promotion_count: "0", retained_count: "0", insufficient_pairs_count: withAlerts ? "1" : "0", invalid_decision_count: "0", cooldown_suppressed_count: "0", stale_champion_skipped_eval_count: "0", served_invalid_forecast_count: withAlerts ? "1" : "0", shadow_invalid_forecast_count: "0", pending_served_forecast_count: "1", mean_label_maturity_lag_calendar_days: "6.0", mean_trigger_anchor_to_decision_calendar_days: withAlerts ? "6.0" : "", mean_decision_to_effective_calendar_days: "", first_alert_date: withAlerts ? "2026-01-08" : "", first_promotion_date: "", zero_alerts_observed: withAlerts ? "False" : "True", zero_promotions_observed: "True" },
    { split: "test", ticker: "IEF", initial_champion_model_id: "B2", final_champion_model_id: "B2", final_champion_version_id: "v001", matched_common_panel_n: "1", detector_observation_count: "1", alert_count: withAlerts ? "1" : "0", decision_event_count: withAlerts ? "1" : "0", promotion_count: "0", retained_count: withAlerts ? "1" : "0", insufficient_pairs_count: "0", invalid_decision_count: "0", cooldown_suppressed_count: "0", stale_champion_skipped_eval_count: "0", served_invalid_forecast_count: "0", shadow_invalid_forecast_count: "0", pending_served_forecast_count: "0", mean_label_maturity_lag_calendar_days: "6.0", mean_trigger_anchor_to_decision_calendar_days: withAlerts ? "6.0" : "", mean_decision_to_effective_calendar_days: "", first_alert_date: withAlerts ? "2026-01-08" : "", first_promotion_date: "", zero_alerts_observed: withAlerts ? "False" : "True", zero_promotions_observed: "True" },
    { split: "test", ticker: "GLD", initial_champion_model_id: "B2", final_champion_model_id: withAlerts ? "B3" : "B2", final_champion_version_id: withAlerts ? "v002" : "v001", matched_common_panel_n: "1", detector_observation_count: "1", alert_count: withAlerts ? "1" : "0", decision_event_count: withAlerts ? "1" : "0", promotion_count: withAlerts ? "1" : "0", retained_count: "0", insufficient_pairs_count: "0", invalid_decision_count: "0", cooldown_suppressed_count: "0", stale_champion_skipped_eval_count: "0", served_invalid_forecast_count: "0", shadow_invalid_forecast_count: "0", pending_served_forecast_count: "2", mean_label_maturity_lag_calendar_days: "6.0", mean_trigger_anchor_to_decision_calendar_days: withAlerts ? "6.0" : "", mean_decision_to_effective_calendar_days: withAlerts ? "1.0" : "", first_alert_date: withAlerts ? "2026-01-08" : "", first_promotion_date: withAlerts ? "2026-01-08" : "", zero_alerts_observed: withAlerts ? "False" : "True", zero_promotions_observed: withAlerts ? "False" : "True" },
    { split: "test", ticker: "MACRO", initial_champion_model_id: "PER_ETF", final_champion_model_id: "PER_ETF", final_champion_version_id: "", matched_common_panel_n: "3", detector_observation_count: "3", alert_count: withAlerts ? "3" : "0", decision_event_count: withAlerts ? "3" : "0", promotion_count: withAlerts ? "1" : "0", retained_count: withAlerts ? "1" : "0", insufficient_pairs_count: withAlerts ? "1" : "0", invalid_decision_count: "0", cooldown_suppressed_count: "0", stale_champion_skipped_eval_count: "0", served_invalid_forecast_count: withAlerts ? "1" : "0", shadow_invalid_forecast_count: "0", pending_served_forecast_count: "3", mean_label_maturity_lag_calendar_days: "6.0", mean_trigger_anchor_to_decision_calendar_days: withAlerts ? "6.0" : "", mean_decision_to_effective_calendar_days: withAlerts ? "1.0" : "", first_alert_date: withAlerts ? "2026-01-08" : "", first_promotion_date: withAlerts ? "2026-01-08" : "", zero_alerts_observed: withAlerts ? "False" : "True", zero_promotions_observed: withAlerts ? "False" : "True" },
  ];

  const coverageSummary = [
    { split: "test", ticker: "SPY", role: "SERVED_CHAMPION", expected_anchors_observed: "2", published_forecasts: "2", invalid_forecasts: withAlerts ? "1" : "0", mature_evaluated: "1", pending_labels: "1", evaluation_failures: "0", matched_common_panel_n: "1", publish_rate: "1.0", mature_evaluation_rate: "0.5" },
    { split: "test", ticker: "SPY", role: "SHADOW_B3", expected_anchors_observed: "2", published_forecasts: "2", invalid_forecasts: "0", mature_evaluated: "1", pending_labels: "1", evaluation_failures: "0", matched_common_panel_n: "1", publish_rate: "1.0", mature_evaluation_rate: "0.5" },
    { split: "test", ticker: "IEF", role: "SERVED_CHAMPION", expected_anchors_observed: "1", published_forecasts: "1", invalid_forecasts: "0", mature_evaluated: "1", pending_labels: "0", evaluation_failures: "0", matched_common_panel_n: "1", publish_rate: "1.0", mature_evaluation_rate: "1.0" },
    { split: "test", ticker: "IEF", role: "SHADOW_B3", expected_anchors_observed: "1", published_forecasts: "1", invalid_forecasts: "0", mature_evaluated: "1", pending_labels: "0", evaluation_failures: "0", matched_common_panel_n: "1", publish_rate: "1.0", mature_evaluation_rate: "1.0" },
    { split: "test", ticker: "GLD", role: "SERVED_CHAMPION", expected_anchors_observed: "3", published_forecasts: "3", invalid_forecasts: "0", mature_evaluated: "1", pending_labels: "2", evaluation_failures: "0", matched_common_panel_n: "1", publish_rate: "1.0", mature_evaluation_rate: "0.3333" },
    { split: "test", ticker: "GLD", role: "SHADOW_B3", expected_anchors_observed: "3", published_forecasts: "3", invalid_forecasts: "0", mature_evaluated: "1", pending_labels: "2", evaluation_failures: "0", matched_common_panel_n: "1", publish_rate: "1.0", mature_evaluation_rate: "0.3333" },
  ];

  const tables = {
    policyForecasts: { path: "policy_forecasts.csv", rows: forecasts },
    policyEvaluations: { path: "policy_evaluations.csv", rows: evaluations },
    policyDetectorStream: { path: "policy_detector_stream.csv", rows: detectorStream },
    policyDecisionEvents: { path: "policy_decision_events.csv", rows: decisionEvents },
    policyChampionTimeline: { path: "policy_champion_timeline.csv", rows: championTimeline },
    policyFailures: { path: "policy_failures.csv", rows: failures },
    policyModelMetrics: { path: "policy_model_metrics.csv", rows: modelMetrics },
    policyComparisons: { path: "policy_comparisons.csv", rows: comparisons },
    policyOperationsSummary: { path: "policy_operations_summary.csv", rows: operationsSummary },
    policyCoverageSummary: { path: "policy_coverage_summary.csv", rows: coverageSummary },
  };

  const files = new Map();
  const manifestFiles = {};
  for (const [key, spec] of Object.entries(tables)) {
    const csv = toCsv(POLICY_EXPECTED_HEADERS[key], spec.rows);
    const bytes = encode(csv);
    files.set(`snapshots/policy/${EVAL_ID}/${spec.path}`, bytes);
    manifestFiles[key] = {
      path: spec.path,
      sha256: sha256Hex(bytes),
      bytes: bytes.byteLength,
      rowCount: spec.rows.length,
      headers: [...POLICY_EXPECTED_HEADERS[key]],
    };
  }

  const reconciliationBytes = encode(JSON.stringify({
    total_alerts: withAlerts ? 3 : 0,
    total_decisions: withAlerts ? 3 : 0,
    total_promotions: withAlerts ? 1 : 0,
  }));
  files.set(`snapshots/policy/${EVAL_ID}/policy_reconciliation.json`, reconciliationBytes);

  const manifest = {
    schemaVersion: "1.2.0",
    policyVersion: "1.0.0",
    policyEvaluationVersion: "1.2.0",
    policyEvaluationId: EVAL_ID,
    policyReplayExperimentId: REPLAY_ID,
    policyConfigFingerprint: HASH_CFG,
    replayConfigVersion: "2.0.0",
    checkpointVersion: "2.0.0",
    sourceBundleName: "fixture-policy-bundle.zip",
    sourceZipSha256: null,
    sourceVerificationStatus: "SOURCE VERIFIED",
    mode: "SIMULATED HISTORICAL REPLAY",
    exploratoryOnly: true,
    h1H3ConfirmatoryUnchanged: true,
    pointInTimeSourceAvailabilityVerified: false,
    championChallengerPolicy: { comparison: { window_pairs: 60, minimum_pairs: 30, min_relative_improvement: 0.05 }, promotion: { cooldown_sessions: 20 } },
    initialChampion: { SPY: "B2", IEF: "B2", GLD: "B2" },
    initialChampionSummary: {},
    replayWindow: { start_date: "2024-10-01", strict_data_cutoff: "2026-09-25" },
    limitations: ["Exploratory simulated historical replay; not live inference."],
    createdAtUtc: "2026-11-23T00:00:00Z",
    builtFromCommit: "fixture",
    expectedCounts: {
      policyForecastRows: forecasts.length,
      policyEvaluationRows: evaluations.length,
      policyDetectorStreamRows: detectorStream.length,
      policyDecisionEventRows: decisionEvents.length,
      policyChampionTimelineRows: championTimeline.length,
      policyFailureRows: failures.length,
      policyModelMetricsRows: modelMetrics.length,
      policyComparisonsRows: comparisons.length,
      policyOperationsSummaryRows: operationsSummary.length,
      policyCoverageSummaryRows: coverageSummary.length,
      policyAlertCount: withAlerts ? 3 : 0,
      policyDecisionCount: withAlerts ? 3 : 0,
      policyPromotionCount: withAlerts ? 1 : 0,
    },
    reconciliationSha256: sha256Hex(reconciliationBytes),
    files: manifestFiles,
  };
  const manifestBytes = encode(JSON.stringify(manifest));
  files.set(`snapshots/policy/${EVAL_ID}/policy_snapshot_manifest.json`, manifestBytes);

  const activeBytes = encode(JSON.stringify({
    schemaVersion: "1.2.0",
    activePolicyEvaluationId: EVAL_ID,
    policyReplayExperimentId: REPLAY_ID,
    manifestPath: `${EVAL_ID}/policy_snapshot_manifest.json`,
    manifestSha256: sha256Hex(manifestBytes),
    mode: "SIMULATED HISTORICAL REPLAY",
    exploratoryOnly: true,
  }));
  files.set("snapshots/policy/ACTIVE.json", activeBytes);
  return { files, manifest };
}

const makeFetcher = (files) => async (input) => {
  const key = new URL(String(input)).pathname.replace(/^\//, "");
  const bytes = files.get(key);
  return bytes ? new Response(bytes, { status: 200 }) : new Response("not found", { status: 404 });
};

test("policy snapshot verifies checksums, next-session promotion timing, pending & invalid states", async () => {
  const { files } = buildPolicyFixture({ withAlerts: true });
  const loaded = await loadPolicySnapshot(makeFetcher(files), "http://localhost:4173/");
  assert.equal(loaded.status, "ready");
  if (loaded.status !== "ready") return;

  const gldDecisionDay = selectPolicyDayState(loaded, "GLD", "2026-01-08");
  assert.equal(gldDecisionDay.activeTimelineEntry?.toChampionVersionId, "v001");
  assert.equal(gldDecisionDay.activeTimelineEntry?.toModelId, "B2");
  assert.equal(gldDecisionDay.pendingPromotionDecision?.effectiveFromDate, "2026-01-09");

  const gldEffectiveDay = selectPolicyDayState(loaded, "GLD", "2026-01-09");
  assert.equal(gldEffectiveDay.activeTimelineEntry?.toChampionVersionId, "v002");
  assert.equal(gldEffectiveDay.activeTimelineEntry?.toModelId, "B3");
  assert.equal(gldEffectiveDay.pendingPromotionDecision, null);

  const iefDay = selectPolicyDayState(loaded, "IEF", "2026-01-08");
  assert.equal(iefDay.activeTimelineEntry?.toModelId, "B2");
  assert.equal(iefDay.decisionsOnDate[0]?.decisionOutcome, "retained");

  const spyPending = selectPolicyDayState(loaded, "SPY", "2026-01-09");
  assert.equal(spyPending.servedPendingLabel, true);
  const spyInvalid = selectPolicyDayState(loaded, "SPY", "2026-01-12");
  assert.equal(spyInvalid.servedFailure?.reason, "negative_prediction_unclipped");

  const gldDecisionHtml = renderPolicyMonitoringPanel(loaded, { ticker: "GLD", date: "2026-01-08" });
  assert.match(gldDecisionHtml, /Simulated Historical Replay/);
  assert.match(gldDecisionHtml, /B3 Monitor ADWIN/);
  assert.match(gldDecisionHtml, /Feature Drift \(W1 \/ PSI\)/);
  assert.match(gldDecisionHtml, /Pending Promotion/);
  assert.match(gldDecisionHtml, /2026-01-09/);
  assert.match(gldDecisionHtml, /Promoted · สลับรุ่นวันถัดไป/);

  const iefHtml = renderPolicyMonitoringPanel(loaded, { ticker: "IEF", date: "2026-01-08" });
  assert.match(iefHtml, /Retained · คงแชมเปี้ยนเดิม/);
  assert.match(iefHtml, /relative_improvement_below_threshold/);

  const spyInvalidHtml = renderPolicyMonitoringPanel(loaded, { ticker: "SPY", date: "2026-01-12" });
  assert.match(spyInvalidHtml, /negative_prediction_unclipped/);
  assert.match(spyInvalidHtml, /ข้อมูลไม่พอ/);

  const replayCard = renderReplayPolicyCard(loaded, "2026-01-09", "GLD");
  assert.match(replayCard, /Active: B3 \(v002\)/);
  assert.match(replayCard, /tab=policy/);
});

test("no-alert policy snapshot renders honest empty state without fabricating alerts", async () => {
  const { files } = buildPolicyFixture({ withAlerts: false });
  const loaded = await loadPolicySnapshot(makeFetcher(files), "http://localhost:4173/");
  assert.equal(loaded.status, "ready");
  if (loaded.status !== "ready") return;
  assert.equal(loaded.decisionEvents.length, 0);
  const html = renderPolicyMonitoringPanel(loaded, { ticker: "SPY", date: "2026-01-02" });
  assert.match(html, /ไม่พบ ADWIN Alert หรือการสลับรุ่นใน snapshot นี้/);
  assert.match(html, /ไม่มีการสร้างเหตุการณ์สมมติ/);
  assert.doesNotMatch(html, /Promoted · สลับรุ่นวันถัดไป/);

  const tabsHtml = renderMonitoringFeatureDrift(
    { status: "missing", message: "No feature drift" },
    { ticker: "SPY", date: "2026-01-02", feature: "ret_1d_t", windowSize: 60, metric: "wasserstein_normalized", tab: "policy", model: "ONLINE_SGD" },
    "<div>Error panel</div>",
    html,
  );
  assert.match(tabsHtml, /id="monitor-policy-tab"/);
  assert.match(tabsHtml, /id="monitor-policy-panel"[^>]*>/);
  assert.doesNotMatch(tabsHtml, /id="monitor-policy-panel"[^>]*hidden/);
});

test("policy loader handles missing sidecar and fails closed on tampered or forged events", async () => {
  const missing = await loadPolicySnapshot(async () => new Response("missing", { status: 404 }), "http://localhost:4173/");
  assert.equal(missing.status, "missing");
  assert.match(renderPolicyMonitoringPanel(missing, { ticker: "SPY", date: "2026-01-02" }), /ไม่สร้าง alert/);

  const tampered = buildPolicyFixture({ withAlerts: true });
  const origBytes = tampered.files.get(`snapshots/policy/${EVAL_ID}/policy_decision_events.csv`);
  const altered = new Uint8Array(origBytes);
  altered[10] ^= 1;
  tampered.files.set(`snapshots/policy/${EVAL_ID}/policy_decision_events.csv`, altered);
  const badHash = await loadPolicySnapshot(makeFetcher(tampered.files), "http://localhost:4173/");
  assert.equal(badHash.status, "error");
  if (badHash.status === "error") assert.match(badHash.message, /SHA-256 mismatch/i);

  const forged = buildPolicyFixture({ withAlerts: false });
  const forgedDecisionRows = [{
    experiment_id: REPLAY_ID, policy_version: "1.0.0", event_id: "ev-forged", decision_date: "2026-01-08",
    ticker: "GLD", trigger_prediction_id: "pf-gld-1-s", trigger_prediction_date: "2026-01-02",
    drift_direction: "error_increase", adwin_estimation_before: "0.025", adwin_estimation_after: "0.042",
    adwin_width: "64", champion_version_id_before: "v001", champion_model_id_before: "B2",
    champion_state_sha256_before: HASH_A, shadow_model_id: "B3", shadow_state_sha256_pre_update: HASH_B,
    comparison_window_pairs: "60", minimum_pairs: "30", min_relative_improvement: "0.05",
    valid_pair_count: "48", champion_window_mae: "0.08", shadow_b3_window_mae: "0.05",
    relative_improvement: "0.375", decision_outcome: "promoted", decision_reason: "forged", switched: "True",
    champion_version_id_after: "v002", champion_model_id_after: "B3", champion_state_sha256_after: HASH_C,
    effective_from_date: "2026-01-09", rollback_target_version_id: "v001", rollback_target_model_id: "B2",
    rollback_target_state_sha256: HASH_A, cooldown_active: "False", cooldown_remaining_before: "0",
    cooldown_remaining_after: "20", detector_reset_after_decision: "True", run_id: "run_fixture",
  }];
  const forgedCsvBytes = encode(toCsv(POLICY_EXPECTED_HEADERS.policyDecisionEvents, forgedDecisionRows));
  forged.files.set(`snapshots/policy/${EVAL_ID}/policy_decision_events.csv`, forgedCsvBytes);
  const forgedManifest = structuredClone(forged.manifest);
  forgedManifest.expectedCounts.policyDecisionEventRows = 1;
  forgedManifest.expectedCounts.policyDecisionCount = 1;
  forgedManifest.files.policyDecisionEvents.sha256 = sha256Hex(forgedCsvBytes);
  forgedManifest.files.policyDecisionEvents.bytes = forgedCsvBytes.byteLength;
  forgedManifest.files.policyDecisionEvents.rowCount = 1;
  const forgedManifestBytes = encode(JSON.stringify(forgedManifest));
  forged.files.set(`snapshots/policy/${EVAL_ID}/policy_snapshot_manifest.json`, forgedManifestBytes);
  forged.files.set("snapshots/policy/ACTIVE.json", encode(JSON.stringify({
    schemaVersion: "1.2.0",
    activePolicyEvaluationId: EVAL_ID,
    policyReplayExperimentId: REPLAY_ID,
    manifestPath: `${EVAL_ID}/policy_snapshot_manifest.json`,
    manifestSha256: sha256Hex(forgedManifestBytes),
    mode: "SIMULATED HISTORICAL REPLAY",
    exploratoryOnly: true,
  })));
  const forgedResult = await loadPolicySnapshot(makeFetcher(forged.files), "http://localhost:4173/");
  assert.equal(forgedResult.status, "error");
  if (forgedResult.status === "error") assert.match(forgedResult.message, /Forged or ungrounded decision event/i);
  assert.match(renderPolicyMonitoringPanel(forgedResult, { ticker: "GLD", date: "2026-01-08" }), /ไม่ผ่านการตรวจสอบ Integrity/);
});

test("real published policy snapshot from dist/snapshots/policy loads and reconciles honestly with 0 alerts", async () => {
  const distRoot = new URL("../dist/", import.meta.url);
  const diskFetch = async (input) => {
    const rel = new URL(String(input)).pathname.replace(/^\//, "");
    try {
      const bytes = new Uint8Array(await readFile(new URL(rel, distRoot)));
      return new Response(bytes, { status: 200 });
    } catch {
      return new Response("missing", { status: 404 });
    }
  };
  const loaded = await loadPolicySnapshot(diskFetch, "http://localhost:4173/");
  assert.equal(loaded.status, "ready");
  if (loaded.status !== "ready") return;
  assert.equal(loaded.manifest.policyVersion, "1.0.0");
  assert.equal(loaded.manifest.mode, "SIMULATED HISTORICAL REPLAY");
  assert.equal(loaded.manifest.pointInTimeSourceAvailabilityVerified, false);
  assert.deepEqual(loaded.manifest.initialChampion, { SPY: "B2", IEF: "B2", GLD: "B2" });
  assert.equal(loaded.forecasts.length, 1488);
  assert.equal(loaded.evaluations.length, 1458);
  assert.equal(loaded.detectorStream.length, 729);
  assert.equal(loaded.decisionEvents.length, 0);
  assert.equal(loaded.championTimeline.length, 3);
  const spyEnd = selectPolicyDayState(loaded, "SPY", "2026-09-25");
  assert.equal(spyEnd.servedPendingLabel, true);
  assert.equal(spyEnd.activeTimelineEntry?.toModelId, "B2");
  const html = renderPolicyMonitoringPanel(loaded, { ticker: "GLD", date: "2026-09-25" });
  assert.match(html, /ไม่พบ ADWIN Alert หรือการสลับรุ่นใน snapshot นี้/);
});

test("parseDriftTimeline & baseline drift alert check support declared non-zero driftAlertRows", () => {
  const headers = [
    "prediction_id", "prediction_date", "ticker", "absolute_error_evaluation", "absolute_error_adwin",
    "drift_detected", "adwin_delta", "adwin_width", "adwin_estimation", "alert_record_present",
  ];
  const csv = toCsv(headers, [{
    prediction_id: "p1", prediction_date: "2026-01-08", ticker: "SPY",
    absolute_error_evaluation: "0.05", absolute_error_adwin: "0.05",
    drift_detected: "True", adwin_delta: "0.002", adwin_width: "32",
    adwin_estimation: "0.02", alert_record_present: "True",
  }]);
  const rows = parseDriftTimeline(csv, { expectedHeaders: { driftErrorTimeline: headers } });
  assert.equal(rows.length, 1);
  assert.equal(rows[0].driftDetected, true);
  assert.equal(rows[0].alertRecordPresent, true);
  const parsedRow = parseDriftTimelineRow({
    prediction_id: "p2", prediction_date: "2026-01-09", ticker: "GLD",
    absolute_error_evaluation: "0.06", absolute_error_adwin: "0.06",
    drift_detected: "True", adwin_delta: "0.002", adwin_width: "64",
    adwin_estimation: "0.03", alert_record_present: "True",
  });
  assert.equal(parsedRow.driftDetected, true);
  assert.equal(parsedRow.alertRecordPresent, true);
});
