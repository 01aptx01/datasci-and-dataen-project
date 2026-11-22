# Drift-Triggered Champion–Challenger Policy Contract (Experimental Policy v1.0.0)

**Document:** `docs/contract/champion_challenger_policy_contract.md`  
**Status:** Exploratory / Retrospective Policy Specification (separate from B0–B4 benchmark and H1–H3 confirmatory hypotheses)  
**Scope:** Per-ETF (`SPY`, `IEF`, `GLD`) Champion selection, ADWIN drift monitoring on served errors, paired shadow B3 comparison, snapshot promotion, and checkpoint reproducibility.

---

## 1. Boundary Against Approved B0–B4 & H1–H3 Contracts

1. **No alteration of B0–B4 or H1–H3:** `config/models.yaml`, `prediction_contract.md` (5 logical tables, 16-column `asset_volatility_predictions`), and `config/hypothesis_tests.yaml` (H1–H3) remain unchanged.
2. **Retrospective / Exploratory Framing:** This policy was specified after observing Stage 06 Test outcomes. Policy evaluation is reported separately from H1–H3 and must not be presented as a confirmatory test until evaluated on an unseen holdout period.
3. **Simulated Historical Replay Limitation:** As in `prediction_contract.md` and `target_contract.md`, `point_in_time_source_availability_verified` remains `false`. Historical price/feature availability is simulated using `target_end_date <= replay_date` and pipeline validation evidence.
4. **Static Dashboard Scope:** The web UI displays verified static historical replay snapshots and does not perform live inference, retraining, or live operational scheduling.

---

## 2. Protocol & Cutover Invariants

### 2.1 Splits, Cutover, and Label Maturity

- **Train:** `2021-09-27` .. `2024-09-30` (purged at `target_end_date >= 2024-10-01`: 5 anchors per ETF `2024-09-24..2024-09-30` excluded from initial Train fit).
- **Validation:** `2024-10-01` .. `2025-09-30` (`250` prediction-eligible XNYS anchors per ETF).
- **Validation → Test Cutover (`2025-10-01`):**
  - At the start of Test (`2025-10-01`, prior to issuing `2025-10-01` forecasts), only Validation rows with `target_end_date < 2025-10-01` (`245` rows per ETF in the approved dataset) are mature and purge-clean.
  - The final `5` Validation anchors (`2025-09-24..2025-09-30`) have `target_end_date` in `2025-10-01..2025-10-07` (`>= 2025-10-01`); they are immature at cutover, excluded from initial champion selection, and reported explicitly in `immature_at_cutover_count`.
- **Test:** `2025-10-01` .. `2026-09-25` (`data_cutoff = 2026-09-25`). Test rows and labels never enter SGD hyperparameter selection or initial champion selection.

### 2.2 Initial Champion Selection (Stage 04 Extension, `training_config_version: "1.2.0"`)

- **Candidate Set:** `B0` (`CONSTANT_BASELINE`), `B1` (`ROLLING_20D_BASELINE`), `B2` (`STATIC_SGD`). `B4` (`HAR_X_OLS`) and `B3` (`ONLINE_SGD`) are excluded.
- **Point-in-Time Candidate Predictions:**
  - `B0`: frozen Train-only eligible label mean per ETF.
  - `B1`: same-day `rv_20d` feature at Validation anchor `prediction_date`.
  - `B2`: frozen Train-fitted `SGDRegressor` and Train-fitted `RobustScaler` selected by the unchanged Stage 04 SGD objective `(mae_b2_validation + mae_b3_validation) / 2`.
- **Coverage Gate:** Expected cutover panel = all Validation prediction-eligible rows with `target_end_date < cutover_date` (and any Validation row whose label is expected mature before cutover). Every candidate in `{B0, B1, B2}` must produce finite nonnegative forecasts (`_is_valid_forecast`) and match a mature valid label (`paired_coverage == 1.0`, `expected_cutover_anchors >= minimum_cutover_anchors`). Incomplete coverage or zero mature cutover anchors fails explicitly (`TrainingError`) without silent row dropping.
- **Scoring & Tie-Break:** Select the candidate per ETF with minimum Validation MAE on the complete paired cutover panel. Ties within `tie_tolerance = 1e-12` resolve deterministically in `tie_break_order = ["B0", "B1", "B2"]`.

### 2.3 B2 vs B3 Initial and Cutover State Identity

- At Stage 04 initial state (`2024-10-01` pre-update), `B2` and `B3` share identical `SGDRegressor` weights, `RobustScaler` statistics, and `state_sha256` per ETF, yielding identical predictions on identical features.
- During Validation replay (`2024-10-01..2025-09-30`), `B2` remains frozen while `B3` updates post-forecast on eligible mature labels (`250` updates per ETF in the approved dataset: 5 Train-purged anchors maturing `2024-10-01..2024-10-07` + 245 Validation anchors maturing by `2025-09-30`). Consequently, `B3` at Test start (`2025-10-01`) generally differs from `B2`, and `B1` varies daily with `rv_20d`.

---

## 3. Daily Replay Policy Protocol (Stage 05 Policy Mode, `replay_config_version: "2.0.0"`)

Activated at `activation_start_date = 2025-10-01` (Test start). During Validation (`2024-10-01..2025-09-30`), B0–B4 and `shadow_b3` execute the standard predict-before-update loop with no policy switching.

### 3.1 Strict Daily Session Order (`processing_order`)

For each XNYS session `s`:

1. **`predict` & `save_forecast` (pre-update state):**
   - Generate B0–B4 benchmark forecasts (unchanged).
   - For `s >= activation_start_date`:
     - Generate **served Champion forecast** from the frozen `champion_snapshot[ticker]` (B0, B1, B2, or a frozen B3 snapshot).
     - Generate **shadow B3 forecast** from `shadow_b3[ticker]` (pre-update state).
     - Validate finite `>= 0` without clipping; log invalid/missing to `policy_failures.csv` and record immutable `policy_forecasts.csv` tagged with `champion_version_id` and `state_sha256`.
2. **`evaluate` (mature labels only: `is_label_mature and target_obs_count == 5 and target_end_date <= s`):**
   - Evaluate benchmark B0–B4 as before.
   - Evaluate pending policy forecasts whose `target_end_date <= s` in deterministic `(prediction_date, prediction_id)` order.
   - Only forecasts issued under the **currently active `champion_version_id`** enter the active detector stream and active paired comparison window. Matured forecasts from a **superseded champion version** are still recorded in `policy_evaluations.csv` for accuracy audit, but are **skipped** from the new version's ADWIN stream and paired comparison window with explicit reason `matured_under_newer_champion_version`.
   - Paired comparison records require BOTH valid served forecast and valid shadow B3 forecast for the same `(prediction_date, ticker)` and active `champion_version_id`.
3. **`adwin_monitor` (benchmark B3 monitor-only, unchanged).**
4. **`policy_adwin_and_decision`:**
   - Feed each current-champion mature served `absolute_error` for ticker `T` in deterministic `(prediction_date, prediction_id)` order to `policy_adwin[T]` (`ADWIN(delta=0.002)`).
   - Record `adwin_estimation_before`, `adwin_estimation`, `adwin_width`, `drift_detected`, and `drift_direction` (`error_increase`, `error_decrease`, `shift_neutral`, or `no_signal`).
   - **Multiple alerts in one session:** The **first alert** for ticker `T` in session `s` initiates the single decision evaluation for `(s, T)`; remaining mature errors of the active champion in session `s` continue feeding that same pre-decision ADWIN stream in deterministic order (never crossing into a newly promoted detector).
   - **Cooldown check:** If `cooldown_remaining[T] > 0`, the alert is recorded in `policy_detector_stream.csv` and `policy_decision_events.csv` with `decision_outcome = "cooldown_suppressed"`, `cooldown_active = true`, without hiding the event or resetting cooldown.
   - **Decision gate (when `cooldown_remaining[T] == 0`):**
     - Take up to the latest `window_pairs = 60` valid mature paired observations for active `champion_version_id`.
     - If `valid_pair_count < minimum_pairs (30)` → `decision_outcome = "insufficient_pairs"`.
     - Else if `champion_mae == 0` or non-finite/negative MAE → `decision_outcome = "invalid"` (zero/undefined denominator; no division by zero; champion retained).
     - Else compute `relative_improvement = (champion_mae - shadow_b3_mae) / champion_mae`:
       - If `relative_improvement >= 0.05` (`min_relative_improvement`) → `decision_outcome = "promoted"`:
         - Snapshot **current pre-update** `shadow_b3[ticker]` (`deepcopy` of estimator + frozen scaler) as the new frozen `champion_snapshot[ticker]`, effective **next XNYS session** (`s + 1`).
         - Create a new `champion_version_id` and record `rollback_target_version_id` + `rollback_target_state_sha256`.
         - Reset `policy_adwin[ticker]` to a fresh `ADWIN(delta=0.002)` and start a new paired window for the new champion version.
       - Else → `decision_outcome = "retained"` (champion unchanged, ADWIN stream preserved).
     - Set `cooldown_remaining[T] = cooldown_sessions (20)` after any evaluated decision (`promoted`, `retained`, `insufficient_pairs`, `invalid`). Decrement cooldown by 1 at end of each subsequent XNYS session.
5. **`update_b3`:**
   - Update benchmark `B3` and `shadow_b3` (memory-isolated copy, never aliasing `champion_snapshot`) with the deterministic batch of newly mature eligible labels (`target_end_date <= s`, no duplicates).
6. **`checkpoint_commit`:**
   - Atomically commit session tables and versioned `checkpoint.joblib` (`checkpoint_version = "2.0.0"`), including `champion_snapshots`, `shadow_b3`, `policy_adwin`, `policy_pending_forecasts`, `policy_paired_history`, `policy_cooldown_remaining`, ledgers, and `policy_config_fingerprint`.

---

## 4. Non-Overlapping Statistical & Methodological Notes

- Target 5-day forward windows overlap across consecutive sessions; paired observations are temporally dependent. The `30` / `60` pair window and `5%` threshold are **heuristic engineering gates** locked prior to Test replay, not formal hypothesis tests.
- Historical `shadow_b3` forecasts originate from a continuously updating shadow process (`partial_fit` after each mature label). Therefore, paired comparisons evaluate the **online shadow process** up to decision time, not a retrospective guarantee of the promoted frozen snapshot's future performance.
- All numeric policy parameters (`candidate_order`, `delta`, `window_pairs`, `minimum_pairs`, `min_relative_improvement`, `cooldown_sessions`, `tie_tolerance`, `policy_version`) live in `config/ml_training.yaml` and `config/ml_replay.yaml` and are hashed into every manifest.

---

## 5. Policy Evaluation Contract (Stage 06 Extension, `policy_evaluation_version: "1.2.0"`)

- **Isolation from H1–H3 & `1.1.0`:** Stage 06 `1.1.0` (`run_final_evaluation`) and `config/hypothesis_tests.yaml` remain unmodified. Policy evaluation runs via `run_policy_evaluation` into `policy_experiments/<evaluation_id>/`.
- **Matched Mature Test Panel:** All strategies (`CHAMPION_CHALLENGER_POLICY`, `FIXED_INITIAL_CHAMPION`, `SHADOW_B3`, and `B0`–`B4`) are compared per ETF (`SPY`, `IEF`, `GLD`) and equal-weight `MACRO` strictly on the intersection of mature, finite, nonnegative Test keys (`target_realized_vol_5d` consistency enforced within `1e-12`).
- **Edge & Operational Reporting:** Zero alerts, zero promotions, insufficient matched samples (`status = "INSUFFICIENT_SAMPLE"`), invalid forecasts, pending horizon rows, and calendar-day latencies (`label maturity`, `trigger anchor -> decision`, `decision -> effective`) are reported explicitly without division-by-zero or silent omission.
- **Event Reconciliation Gate:** Every decision event must reconcile 1:1 with a triggered ADWIN stream row, and every promoted decision must reconcile 1:1 with a `PROMOTED_SNAPSHOT_ACTIVE_NEXT_SESSION` timeline row satisfying `effective_from_date > decision_date`.
