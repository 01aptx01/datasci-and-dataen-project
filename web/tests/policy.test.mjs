import assert from "node:assert/strict";
import { createHash } from "node:crypto";
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
  const forecasts = [
    // SPY: mature day, pending day, and an invalid forecast day (recorded in failures)
    { policy_prediction_id: "pf-spy-1-s", experiment_id: REPLAY_ID, policy_version: "1.0.0", prediction_date: "2026-01-02", split: "test", ticker: "SPY", role: "SERVED_CHAMPION", model_id: "B2", model_name: "STATIC_SGD", champion_version_id: "v001", model_state_sha256: HASH_A, target_start_date: "2026-01-03", target_end_date: "2026-01-08", predicted_vol_annualized: "0.1400", is_promoted_snapshot: "False" },
    { policy_prediction_id: "pf-spy-1-h", experiment_id: REPLAY_ID, policy_version: "1.0.0", prediction_date: "2026-01-02", split: "test", ticker: "SPY", role: "SHADOW_B3", model_id: "B3", model_name: "ONLINE_SGD", champion_version_id: "shadow_b3", model_state_sha256: HASH_B, target_start_date: "2026-01-03", target_end_date: "2026-01-08", predicted_vol_annualized: "0.1300", is_promoted_snapshot: "False" },
    { policy_prediction_id: "pf-spy-2-s", experiment_id: REPLAY_ID, policy_version: "1.0.0", prediction_date: "2026-01-09", split: "test", ticker: "SPY", role: "SERVED_CHAMPION", model_id: "B2", model_name: "STATIC_SGD", champion_version_id: "v001", model_state_sha256: HASH_A, target_start_date: "2026-01-12", target_end_date: "2026-01-16", predicted_vol_annualized: "0.1500", is_promoted_snapshot: "False" },
    { policy_prediction_id: "pf-spy-2-h", experiment_id: REPLAY_ID, policy_version: "1.0.0", prediction_date: "2026-01-09", split: "test", ticker: "SPY", role: "SHADOW_B3", model_id: "B3", model_name: "ONLINE_SGD", champion_version_id: "shadow_b3", model_state_sha256: HASH_B, target_start_date: "2026-01-12", target_end_date: "2026-01-16", predicted_vol_annualized: "0.1450", is_promoted_snapshot: "False" },
    // IEF: alert without switch (retained)
    { policy_prediction_id: "pf-ief-1-s", experiment_id: REPLAY_ID, policy_version: "1.0.0", prediction_date: "2026-01-02", split: "test", ticker: "IEF", role: "SERVED_CHAMPION", model_id: "B2", model_name: "STATIC_SGD", champion_version_id: "v001", model_state_sha256: HASH_A, target_start_date: "2026-01-03", target_end_date: "2026-01-08", predicted_vol_annualized: "0.0600", is_promoted_snapshot: "False" },
    { policy_prediction_id: "pf-ief-1-h", experiment_id: REPLAY_ID, policy_version: "1.0.0", prediction_date: "2026-01-02", split: "test", ticker: "IEF", role: "SHADOW_B3", model_id: "B3", model_name: "ONLINE_SGD", champion_version_id: "shadow_b3", model_state_sha256: HASH_B, target_start_date: "2026-01-03", target_end_date: "2026-01-08", predicted_vol_annualized: "0.0590", is_promoted_snapshot: "False" },
    // GLD: decision on 2026-01-08 -> promoted snapshot v002 (B3) effective 2026-01-09
    { policy_prediction_id: "pf-gld-1-s", experiment_id: REPLAY_ID, policy_version: "1.0.0", prediction_date: "2026-01-02", split: "test", ticker: "GLD", role: "SERVED_CHAMPION", model_id: "B2", model_name: "STATIC_SGD", champion_version_id: "v001", model_state_sha256: HASH_A, target_start_date: "2026-01-03", target_end_date: "2026-01-08", predicted_vol_annualized: "0.1800", is_promoted_snapshot: "False" },
    { policy_prediction_id: "pf-gld-1-h", experiment_id: REPLAY_ID, policy_version: "1.0.0", prediction_date: "2026-01-02", split: "test", ticker: "GLD", role: "SHADOW_B3", model_id: "B3", model_name: "ONLINE_SGD", champion_version_id: "shadow_b3", model_state_sha256: HASH_B, target_start_date: "2026-01-03", target_end_date: "2026-01-08", predicted_vol_annualized: "0.1100", is_promoted_snapshot: "False" },
    { policy_prediction_id: "pf-gld-2-s", experiment_id: REPLAY_ID, policy_version: "1.0.0", prediction_date: "2026-01-08", split: "test", ticker: "GLD", role: "SERVED_CHAMPION", model_id: "B2", model_name: "STATIC_SGD", champion_version_id: "v001", model_state_sha256: HASH_A, target_start_date: "2026-01-09", target_end_date: "2026-01-15", predicted_vol_annualized: "0.1750", is_promoted_snapshot: "False" },
    { policy_prediction_id: "pf-gld-2-h", experiment_id: REPLAY_ID, policy_version: "1.0.0", prediction_date: "2026-01-08", split: "test", ticker: "GLD", role: "SHADOW_B3", model_id: "B3", model_name: "ONLINE_SGD", champion_version_id: "shadow_b3", model_state_sha256: HASH_B, target_start_date: "2026-01-09", target_end_date: "2026-01-15", predicted_vol_annualized: "0.1120", is_promoted_snapshot: "False" },
    { policy_prediction_id: "pf-gld-3-s", experiment_id: REPLAY_ID, policy_version: "1.0.0", prediction_date: "2026-01-09", split: "test", ticker: "GLD", role: "SERVED_CHAMPION", model_id: withAlerts ? "B3" : "B2", model_name: withAlerts ? "ONLINE_SGD" : "STATIC_SGD", champion_version_id: withAlerts ? "v002" : "v001", model_state_sha256: withAlerts ? HASH_C : HASH_A, target_start_date: "2026-01-12", target_end_date: "2026-01-16", predicted_vol_annualized: withAlerts ? "0.1110" : "0.1760", is_promoted_snapshot: withAlerts ? "True" : "False" },
    { policy_prediction_id: "pf-gld-3-h", experiment_id: REPLAY_ID, policy_version: "1.0.0", prediction_date: "2026-01-09", split: "test", ticker: "GLD", role: "SHADOW_B3", model_id: "B3", model_name: "ONLINE_SGD", champion_version_id: "shadow_b3", model_state_sha256: HASH_B, target_start_date: "2026-01-12", target_end_date: "2026-01-16", predicted_vol_annualized: "0.1110", is_promoted_snapshot: "False" },
  ];

  // Note: pf-spy-2-s has NO evaluation (pending label test)
  const evaluations = [
    { policy_prediction_id: "pf-spy-1-s", experiment_id: REPLAY_ID, policy_version: "1.0.0", prediction_date: "2026-01-02", evaluation_date: "2026-01-08", split: "test", ticker: "SPY", role: "SERVED_CHAMPION", model_id: "B2", model_name: "STATIC_SGD", champion_version_id: "v001", model_state_sha256: HASH_A, target_start_date: "2026-01-03", target_end_date: "2026-01-08", predicted_vol_annualized: "0.1400", target_realized_vol_5d: "0.1000", absolute_error: "0.0400", squared_error: "0.0016" },
    { policy_prediction_id: "pf-spy-1-h", experiment_id: REPLAY_ID, policy_version: "1.0.0", prediction_date: "2026-01-02", evaluation_date: "2026-01-08", split: "test", ticker: "SPY", role: "SHADOW_B3", model_id: "B3", model_name: "ONLINE_SGD", champion_version_id: "shadow_b3", model_state_sha256: HASH_B, target_start_date: "2026-01-03", target_end_date: "2026-01-08", predicted_vol_annualized: "0.1300", target_realized_vol_5d: "0.1000", absolute_error: "0.0300", squared_error: "0.0009" },
    { policy_prediction_id: "pf-ief-1-s", experiment_id: REPLAY_ID, policy_version: "1.0.0", prediction_date: "2026-01-02", evaluation_date: "2026-01-08", split: "test", ticker: "IEF", role: "SERVED_CHAMPION", model_id: "B2", model_name: "STATIC_SGD", champion_version_id: "v001", model_state_sha256: HASH_A, target_start_date: "2026-01-03", target_end_date: "2026-01-08", predicted_vol_annualized: "0.0600", target_realized_vol_5d: "0.0500", absolute_error: "0.0100", squared_error: "0.0001" },
    { policy_prediction_id: "pf-ief-1-h", experiment_id: REPLAY_ID, policy_version: "1.0.0", prediction_date: "2026-01-02", evaluation_date: "2026-01-08", split: "test", ticker: "IEF", role: "SHADOW_B3", model_id: "B3", model_name: "ONLINE_SGD", champion_version_id: "shadow_b3", model_state_sha256: HASH_B, target_start_date: "2026-01-03", target_end_date: "2026-01-08", predicted_vol_annualized: "0.0590", target_realized_vol_5d: "0.0500", absolute_error: "0.0090", squared_error: "0.000081" },
    { policy_prediction_id: "pf-gld-1-s", experiment_id: REPLAY_ID, policy_version: "1.0.0", prediction_date: "2026-01-02", evaluation_date: "2026-01-08", split: "test", ticker: "GLD", role: "SERVED_CHAMPION", model_id: "B2", model_name: "STATIC_SGD", champion_version_id: "v001", model_state_sha256: HASH_A, target_start_date: "2026-01-03", target_end_date: "2026-01-08", predicted_vol_annualized: "0.1800", target_realized_vol_5d: "0.1000", absolute_error: "0.0800", squared_error: "0.0064" },
    { policy_prediction_id: "pf-gld-1-h", experiment_id: REPLAY_ID, policy_version: "1.0.0", prediction_date: "2026-01-02", evaluation_date: "2026-01-08", split: "test", ticker: "GLD", role: "SHADOW_B3", model_id: "B3", model_name: "ONLINE_SGD", champion_version_id: "shadow_b3", model_state_sha256: HASH_B, target_start_date: "2026-01-03", target_end_date: "2026-01-08", predicted_vol_annualized: "0.1100", target_realized_vol_5d: "0.1000", absolute_error: "0.0100", squared_error: "0.0001" },
  ];

  const detectorStream = [
    { policy_prediction_id: "pf-spy-1-s", experiment_id: REPLAY_ID, policy_version: "1.0.0", ticker: "SPY", prediction_date: "2026-01-02", evaluation_date: "2026-01-08", feed_order_in_session: "1", champion_version_id: "v001", champion_model_id: "B2", champion_state_sha256: HASH_A, absolute_error: "0.0400", adwin_delta: "0.002", adwin_width: "32", adwin_estimation: "0.035", drift_detected: withAlerts ? "True" : "False", drift_direction: withAlerts ? "error_increase" : "no_signal", triggered_decision: withAlerts ? "True" : "False", cooldown_remaining_before: "0", decision_event_id: withAlerts ? "ev-spy-1" : "" },
    { policy_prediction_id: "pf-ief-1-s", experiment_id: REPLAY_ID, policy_version: "1.0.0", ticker: "IEF", prediction_date: "2026-01-02", evaluation_date: "2026-01-08", feed_order_in_session: "1", champion_version_id: "v001", champion_model_id: "B2", champion_state_sha256: HASH_A, absolute_error: "0.0100", adwin_delta: "0.002", adwin_width: "40", adwin_estimation: "0.011", drift_detected: withAlerts ? "True" : "False", drift_direction: withAlerts ? "error_increase" : "no_signal", triggered_decision: withAlerts ? "True" : "False", cooldown_remaining_before: "0", decision_event_id: withAlerts ? "ev-ief-1" : "" },
    { policy_prediction_id: "pf-gld-1-s", experiment_id: REPLAY_ID, policy_version: "1.0.0", ticker: "GLD", prediction_date: "2026-01-02", evaluation_date: "2026-01-08", feed_order_in_session: "1", champion_version_id: "v001", champion_model_id: "B2", champion_state_sha256: HASH_A, absolute_error: "0.0800", adwin_delta: "0.002", adwin_width: "64", adwin_estimation: "0.042", drift_detected: withAlerts ? "True" : "False", drift_direction: withAlerts ? "error_increase" : "no_signal", triggered_decision: withAlerts ? "True" : "False", cooldown_remaining_before: "0", decision_event_id: withAlerts ? "ev-gld-1" : "" },
  ];

  const decisionEvents = withAlerts
    ? [
        { event_id: "ev-spy-1", experiment_id: REPLAY_ID, policy_version: "1.0.0", ticker: "SPY", decision_date: "2026-01-08", effective_from_date: "", trigger_prediction_id: "pf-spy-1-s", trigger_prediction_date: "2026-01-02", trigger_absolute_error: "0.0400", drift_direction: "error_increase", champion_version_id_before: "v001", champion_model_id_before: "B2", champion_state_sha256_before: HASH_A, challenger_model_id: "B3", challenger_state_sha256: HASH_B, window_size: "60", minimum_pairs: "30", valid_pair_count: "12", champion_window_mae: "0.0400", challenger_window_mae: "0.0300", delta_mae_champion_minus_challenger: "0.0100", relative_improvement: "0.25", min_relative_improvement: "0.05", cooldown_active: "False", cooldown_remaining_before: "0", decision_outcome: "insufficient_pairs", decision_reason: "valid_pair_count_below_minimum_30", switched: "False", champion_version_id_after: "v001", champion_model_id_after: "B2", champion_state_sha256_after: HASH_A, rollback_target_version_id: "", rollback_target_model_id: "", rollback_target_state_sha256: "" },
        { event_id: "ev-ief-1", experiment_id: REPLAY_ID, policy_version: "1.0.0", ticker: "IEF", decision_date: "2026-01-08", effective_from_date: "", trigger_prediction_id: "pf-ief-1-s", trigger_prediction_date: "2026-01-02", trigger_absolute_error: "0.0100", drift_direction: "error_increase", champion_version_id_before: "v001", champion_model_id_before: "B2", champion_state_sha256_before: HASH_A, challenger_model_id: "B3", challenger_state_sha256: HASH_B, window_size: "60", minimum_pairs: "30", valid_pair_count: "45", champion_window_mae: "0.0100", challenger_window_mae: "0.0098", delta_mae_champion_minus_challenger: "0.0002", relative_improvement: "0.02", min_relative_improvement: "0.05", cooldown_active: "False", cooldown_remaining_before: "0", decision_outcome: "retained", decision_reason: "relative_improvement_below_threshold", switched: "False", champion_version_id_after: "v001", champion_model_id_after: "B2", champion_state_sha256_after: HASH_A, rollback_target_version_id: "", rollback_target_model_id: "", rollback_target_state_sha256: "" },
        { event_id: "ev-gld-1", experiment_id: REPLAY_ID, policy_version: "1.0.0", ticker: "GLD", decision_date: "2026-01-08", effective_from_date: "2026-01-09", trigger_prediction_id: "pf-gld-1-s", trigger_prediction_date: "2026-01-02", trigger_absolute_error: "0.0800", drift_direction: "error_increase", champion_version_id_before: "v001", champion_model_id_before: "B2", champion_state_sha256_before: HASH_A, challenger_model_id: "B3", challenger_state_sha256: HASH_B, window_size: "60", minimum_pairs: "30", valid_pair_count: "48", champion_window_mae: "0.0800", challenger_window_mae: "0.0500", delta_mae_champion_minus_challenger: "0.0300", relative_improvement: "0.375", min_relative_improvement: "0.05", cooldown_active: "False", cooldown_remaining_before: "0", decision_outcome: "promoted", decision_reason: "challenger_beat_champion_by_at_least_5pct", switched: "True", champion_version_id_after: "v002", champion_model_id_after: "B3", champion_state_sha256_after: HASH_C, rollback_target_version_id: "v001", rollback_target_model_id: "B2", rollback_target_state_sha256: HASH_A },
      ]
    : [];

  const championTimeline = [
    { timeline_event_id: "tl-spy-init", experiment_id: REPLAY_ID, policy_version: "1.0.0", ticker: "SPY", event_type: "INITIAL_CHAMPION_CUTOVER", decision_event_id: "", decision_date: "2025-09-30", effective_from_date: "2025-10-01", from_champion_version_id: "", from_model_id: "", from_state_sha256: "", to_champion_version_id: "v001", to_model_id: "B2", to_state_sha256: HASH_A, rollback_target_version_id: "", rollback_target_model_id: "", rollback_target_state_sha256: "", reason: "initial_validation_cutover_selection" },
    { timeline_event_id: "tl-ief-init", experiment_id: REPLAY_ID, policy_version: "1.0.0", ticker: "IEF", event_type: "INITIAL_CHAMPION_CUTOVER", decision_event_id: "", decision_date: "2025-09-30", effective_from_date: "2025-10-01", from_champion_version_id: "", from_model_id: "", from_state_sha256: "", to_champion_version_id: "v001", to_model_id: "B2", to_state_sha256: HASH_A, rollback_target_version_id: "", rollback_target_model_id: "", rollback_target_state_sha256: "", reason: "initial_validation_cutover_selection" },
    { timeline_event_id: "tl-gld-init", experiment_id: REPLAY_ID, policy_version: "1.0.0", ticker: "GLD", event_type: "INITIAL_CHAMPION_CUTOVER", decision_event_id: "", decision_date: "2025-09-30", effective_from_date: "2025-10-01", from_champion_version_id: "", from_model_id: "", from_state_sha256: "", to_champion_version_id: "v001", to_model_id: "B2", to_state_sha256: HASH_A, rollback_target_version_id: "", rollback_target_model_id: "", rollback_target_state_sha256: "", reason: "initial_validation_cutover_selection" },
    ...(withAlerts
      ? [{ timeline_event_id: "tl-gld-promo-1", experiment_id: REPLAY_ID, policy_version: "1.0.0", ticker: "GLD", event_type: "PROMOTED_SNAPSHOT_ACTIVE_NEXT_SESSION", decision_event_id: "ev-gld-1", decision_date: "2026-01-08", effective_from_date: "2026-01-09", from_champion_version_id: "v001", from_model_id: "B2", from_state_sha256: HASH_A, to_champion_version_id: "v002", to_model_id: "B3", to_state_sha256: HASH_C, rollback_target_version_id: "v001", rollback_target_model_id: "B2", rollback_target_state_sha256: HASH_A, reason: "challenger_beat_champion_by_at_least_5pct" }]
      : []),
  ];

  const failures = withAlerts
    ? [{ failure_id: "fail-spy-1", experiment_id: REPLAY_ID, policy_version: "1.0.0", session_date: "2026-01-12", ticker: "SPY", role: "SERVED_CHAMPION", model_id: "B2", champion_version_id: "v001", stage: "predict", reason: "negative_prediction_unclipped", raw_value: "-0.042" }]
    : [];

  const modelMetrics = [
    { split: "test", ticker: "SPY", system_id: "POLICY_CHAMPION_CHALLENGER", model_name: "POLICY_SERVED", paired_n: "1", expected_eligible_anchor_count: "2", paired_coverage: "0.5", mae: "0.0400", rmse: "0.0400", comparison_panel: "matched", evaluation_scope: "exploratory_policy_test" },
    { split: "test", ticker: "IEF", system_id: "POLICY_CHAMPION_CHALLENGER", model_name: "POLICY_SERVED", paired_n: "1", expected_eligible_anchor_count: "1", paired_coverage: "1.0", mae: "0.0100", rmse: "0.0100", comparison_panel: "matched", evaluation_scope: "exploratory_policy_test" },
    { split: "test", ticker: "GLD", system_id: "POLICY_CHAMPION_CHALLENGER", model_name: "POLICY_SERVED", paired_n: "1", expected_eligible_anchor_count: "3", paired_coverage: "0.3333", mae: "0.0800", rmse: "0.0800", comparison_panel: "matched", evaluation_scope: "exploratory_policy_test" },
    { split: "test", ticker: "MACRO", system_id: "POLICY_CHAMPION_CHALLENGER", model_name: "POLICY_SERVED", paired_n: "3", expected_eligible_anchor_count: "6", paired_coverage: "0.5", mae: "0.043333", rmse: "", comparison_panel: "matched", evaluation_scope: "exploratory_policy_test" },
  ];

  const comparisons = [
    { comparison_id: "POLICY_VS_FIXED_INITIAL_CHAMPION", policy_system: "POLICY_CHAMPION_CHALLENGER", comparator_system: "FIXED_INITIAL_CHAMPION", comparator_model: "B2", split: "test", ticker: "GLD", paired_n: "1", expected_eligible_anchor_count: "3", paired_coverage: "0.3333", policy_mae: "0.0800", comparator_mae: "0.0900", delta_mae_comparator_minus_policy: "0.0100", relative_improvement_pct: "11.11", policy_rmse: "0.0800", comparator_rmse: "0.0900", direction_definition: "comparator_mae_minus_policy_mae", pairing_policy: "same_key", evaluation_scope: "exploratory_policy_test", status: "OK" },
    { comparison_id: "POLICY_VS_FIXED_INITIAL_CHAMPION", policy_system: "POLICY_CHAMPION_CHALLENGER", comparator_system: "FIXED_INITIAL_CHAMPION", comparator_model: "B2", split: "test", ticker: "MACRO", paired_n: "3", expected_eligible_anchor_count: "6", paired_coverage: "0.5", policy_mae: "0.043333", comparator_mae: "0.046667", delta_mae_comparator_minus_policy: "0.003334", relative_improvement_pct: "7.14", policy_rmse: "", comparator_rmse: "", direction_definition: "comparator_mae_minus_policy_mae", pairing_policy: "equal_etf_weight", evaluation_scope: "exploratory_policy_test", status: "OK" },
  ];

  const operationsSummary = [
    { ticker: "SPY", initial_champion_model_id: "B2", final_champion_model_id: "B2", final_champion_version_id: "v001", detector_observations: "1", alert_count: withAlerts ? "1" : "0", decision_count: withAlerts ? "1" : "0", promotion_count: "0", retained_count: "0", insufficient_pairs_count: withAlerts ? "1" : "0", invalid_decision_count: "0", cooldown_suppressed_count: "0", b3_to_b3_promotion_count: "0", served_invalid_forecast_count: withAlerts ? "1" : "0", shadow_invalid_forecast_count: "0", median_eval_to_alert_latency_sessions: withAlerts ? "4" : "", median_decision_to_effective_latency_sessions: "" },
    { ticker: "IEF", initial_champion_model_id: "B2", final_champion_model_id: "B2", final_champion_version_id: "v001", detector_observations: "1", alert_count: withAlerts ? "1" : "0", decision_count: withAlerts ? "1" : "0", promotion_count: "0", retained_count: withAlerts ? "1" : "0", insufficient_pairs_count: "0", invalid_decision_count: "0", cooldown_suppressed_count: "0", b3_to_b3_promotion_count: "0", served_invalid_forecast_count: "0", shadow_invalid_forecast_count: "0", median_eval_to_alert_latency_sessions: withAlerts ? "4" : "", median_decision_to_effective_latency_sessions: "" },
    { ticker: "GLD", initial_champion_model_id: "B2", final_champion_model_id: withAlerts ? "B3" : "B2", final_champion_version_id: withAlerts ? "v002" : "v001", detector_observations: "1", alert_count: withAlerts ? "1" : "0", decision_count: withAlerts ? "1" : "0", promotion_count: withAlerts ? "1" : "0", retained_count: "0", insufficient_pairs_count: "0", invalid_decision_count: "0", cooldown_suppressed_count: "0", b3_to_b3_promotion_count: "0", served_invalid_forecast_count: "0", shadow_invalid_forecast_count: "0", median_eval_to_alert_latency_sessions: withAlerts ? "4" : "", median_decision_to_effective_latency_sessions: withAlerts ? "1" : "" },
    { ticker: "MACRO", initial_champion_model_id: "MIXED", final_champion_model_id: "MIXED", final_champion_version_id: "MIXED", detector_observations: "3", alert_count: withAlerts ? "3" : "0", decision_count: withAlerts ? "3" : "0", promotion_count: withAlerts ? "1" : "0", retained_count: withAlerts ? "1" : "0", insufficient_pairs_count: withAlerts ? "1" : "0", invalid_decision_count: "0", cooldown_suppressed_count: "0", b3_to_b3_promotion_count: "0", served_invalid_forecast_count: withAlerts ? "1" : "0", shadow_invalid_forecast_count: "0", median_eval_to_alert_latency_sessions: withAlerts ? "4" : "", median_decision_to_effective_latency_sessions: withAlerts ? "1" : "" },
  ];

  const coverageSummary = [
    { ticker: "SPY", expected_eligible_prediction_anchors: "2", served_forecast_count: "2", shadow_forecast_count: "2", served_invalid_count: withAlerts ? "1" : "0", shadow_invalid_count: "0", served_mature_evaluable_count: "1", shadow_mature_evaluable_count: "1", served_pending_count: "1", matched_all_systems_n: "1", served_forecast_coverage: "1.0", served_evaluation_coverage: "0.5" },
    { ticker: "IEF", expected_eligible_prediction_anchors: "1", served_forecast_count: "1", shadow_forecast_count: "1", served_invalid_count: "0", shadow_invalid_count: "0", served_mature_evaluable_count: "1", shadow_mature_evaluable_count: "1", served_pending_count: "0", matched_all_systems_n: "1", served_forecast_coverage: "1.0", served_evaluation_coverage: "1.0" },
    { ticker: "GLD", expected_eligible_prediction_anchors: "3", served_forecast_count: "3", shadow_forecast_count: "3", served_invalid_count: "0", shadow_invalid_count: "0", served_mature_evaluable_count: "1", shadow_mature_evaluable_count: "1", served_pending_count: "2", matched_all_systems_n: "1", served_forecast_coverage: "1.0", served_evaluation_coverage: "0.3333" },
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
    championChallengerPolicy: { paired_window_size: 60, minimum_valid_pairs: 30, min_relative_mae_improvement: 0.05, cooldown_sessions: 10 },
    initialChampion: { SPY: "B2", IEF: "B2", GLD: "B2" },
    initialChampionSummary: {},
    replayWindow: { start: "2025-10-01", end: "2026-09-25" },
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

  // On decision date (2026-01-08), GLD must still serve v001 (B2) with pending promotion notice
  const gldDecisionDay = selectPolicyDayState(loaded, "GLD", "2026-01-08");
  assert.equal(gldDecisionDay.activeTimelineEntry?.toChampionVersionId, "v001");
  assert.equal(gldDecisionDay.activeTimelineEntry?.toModelId, "B2");
  assert.equal(gldDecisionDay.pendingPromotionDecision?.effectiveFromDate, "2026-01-09");

  // On effective date (2026-01-09), GLD switches to promoted B3 snapshot v002
  const gldEffectiveDay = selectPolicyDayState(loaded, "GLD", "2026-01-09");
  assert.equal(gldEffectiveDay.activeTimelineEntry?.toChampionVersionId, "v002");
  assert.equal(gldEffectiveDay.activeTimelineEntry?.toModelId, "B3");
  assert.equal(gldEffectiveDay.pendingPromotionDecision, null);

  // IEF alert without switch keeps v001 (B2)
  const iefDay = selectPolicyDayState(loaded, "IEF", "2026-01-08");
  assert.equal(iefDay.activeTimelineEntry?.toModelId, "B2");
  assert.equal(iefDay.decisionsOnDate[0]?.decisionOutcome, "retained");

  // SPY pending label (2026-01-09) and invalid forecast failure (2026-01-12)
  const spyPending = selectPolicyDayState(loaded, "SPY", "2026-01-09");
  assert.equal(spyPending.servedPendingLabel, true);
  const spyInvalid = selectPolicyDayState(loaded, "SPY", "2026-01-12");
  assert.equal(spyInvalid.servedFailure?.reason, "negative_prediction_unclipped");

  // Rendered views include required disclosures, 3-signal separation, outcomes, and next-session notice
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

  // 1. Tampered CSV bytes -> SHA-256 mismatch
  const tampered = buildPolicyFixture({ withAlerts: true });
  const origBytes = tampered.files.get(`snapshots/policy/${EVAL_ID}/policy_decision_events.csv`);
  const altered = new Uint8Array(origBytes);
  altered[10] ^= 1;
  tampered.files.set(`snapshots/policy/${EVAL_ID}/policy_decision_events.csv`, altered);
  const badHash = await loadPolicySnapshot(makeFetcher(tampered.files), "http://localhost:4173/");
  assert.equal(badHash.status, "error");
  if (badHash.status === "error") assert.match(badHash.message, /SHA-256 mismatch/i);

  // 2. Forged decision event with valid re-signed checksums but no ADWIN trigger -> rejected!
  const forged = buildPolicyFixture({ withAlerts: false });
  const forgedDecisionRows = [{
    event_id: "ev-forged", experiment_id: REPLAY_ID, policy_version: "1.0.0", ticker: "GLD",
    decision_date: "2026-01-08", effective_from_date: "2026-01-09", trigger_prediction_id: "pf-gld-1-s",
    trigger_prediction_date: "2026-01-02", trigger_absolute_error: "0.0800", drift_direction: "error_increase",
    champion_version_id_before: "v001", champion_model_id_before: "B2", champion_state_sha256_before: HASH_A,
    challenger_model_id: "B3", challenger_state_sha256: HASH_B, window_size: "60", minimum_pairs: "30",
    valid_pair_count: "48", champion_window_mae: "0.08", challenger_window_mae: "0.05",
    delta_mae_champion_minus_challenger: "0.03", relative_improvement: "0.375", min_relative_improvement: "0.05",
    cooldown_active: "False", cooldown_remaining_before: "0", decision_outcome: "promoted",
    decision_reason: "forged", switched: "True", champion_version_id_after: "v002",
    champion_model_id_after: "B3", champion_state_sha256_after: HASH_C, rollback_target_version_id: "v001",
    rollback_target_model_id: "B2", rollback_target_state_sha256: HASH_A,
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
