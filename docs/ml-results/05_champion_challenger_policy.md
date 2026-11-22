# Drift-Triggered Champion–Challenger Policy (v1.0.0) — Exploratory Historical Replay Results

> **Governance & Scope Notice:**
> - **Mode:** `SIMULATED HISTORICAL REPLAY` (`point_in_time_source_availability_verified = false`). Not live inference and not live operational retraining.
> - **Confirmatory Separation:** This policy is an **exploratory retrospective study** (`policy_version = 1.0.0`, `policy_evaluation_version = 1.2.0`). It is strictly separated from the frozen confirmatory hypotheses **H1–H3** (`config/hypothesis_tests.yaml`) and does **not** alter or overwrite any baseline B0–B4 benchmark outputs (`stage04_b4_20261122_s6`, Stage 05 `23616e7b...`, Stage 06 `ae5cc8cc...`).
> - **Shadow vs Served Distinction:** During replay, the paired comparison window evaluates the continuously updating **Shadow B3** process prior to decision time, whereas a promoted champion serves a **frozen pre-update B3 snapshot** starting on the **next trading session** (`effective_from_date > decision_date`).
> - **Honest Zero-Alert Real-Data Reporting:** On the real curated Test period (`2025-10-01` to `2026-09-25`), ADWIN (`delta = 0.002`) triggered **0 alerts** and **0 promotions** across all 3 ETFs (`SPY`, `IEF`, `GLD`). No hypothetical or synthetic alerts were injected into real-data outputs. Full alert → decision → retained / insufficient_pairs / invalid / cooldown_suppressed / promoted → next-session switch flows are verified separately through deterministic test fixtures (clearly labeled below).

---

## 1. Frozen Lineage, Config Fingerprints, and Run Identities

| Artifact / Stage | Identifier / Version | Exact Fingerprint / SHA-256 |
|---|---|---|
| Stage 03 Curated Features | `feat_20261122T143142_ad87117a` | `9ced880aa6f349691b2a4f84e1ffe66e3d282491e42bccfca86b29622d24445b` |
| Stage 03 Curated Labels | `target_20261122T143149_c9b24e99` | `b380152d6b107a7bcb9280e51d85afddfb10d2e198a1e6564339ce9409ae9a0b` |
| Stage 04 Training Config | `training_config_version = 1.2.0` | `7991e4d8a956ef379e41e104606b0e6de66059c4704355545075e998dce167ee` |
| Initial Champion Config | `policy_version = 1.0.0` (Validation cutover `< 2025-10-01`) | `367925ad360d03f3001aafc098417d4f9080c67babe1b31f657a28a7b75c2607` |
| Stage 04 Artifact Directory | `data/processed/ml_training/run_id=stage04_cc_policy_v1` | `initial_models.joblib`: `71b797d99614f4c2b9beb9587348f224fc9230f509c5d3c0b42f93654485c57e` (exact match with `stage04_b4_20261122_s6`) |
| Stage 05 Policy Replay Config | `replay_config_version = 2.0.0`, `checkpoint_version = 2.0.0` | `policy_config_fingerprint`: `8f1934baf1c1815faea9632d9395c2c77264bd1af6ca06b8449b6d1bdd389059` |
| Stage 05 Policy Replay Run | `5003376f7637a3b04f63719dd499f67946aa3b0f30bafd27772e1d20d4ec9779` | `policy_ledger_sha256`: `f14fc8bcee2290af108460a6391bbf5ae5d3f9f754377f276ecf15a022cfbd8c` |
| Stage 06 Policy Evaluation | `f6dd8cb131d7d7bebaefa0ca70f47e068956e5c2f4f99e448b1511711ddde844` | `policy_evaluation_version = 1.2.0` (`reconciliation_passed = true`) |
| Policy Handoff Bundle ZIP | `docs/ml-results/downloads/policy/ml-results-policy-f6dd8cb1.zip` | `86747b0378e0478b1fb819e5e755c39e4fecfc3b43d12793a43f55c74fdbc5ec` |
| Web Policy Sidecar Snapshot | `web/public/snapshots/policy/f6dd8cb1.../` + `ACTIVE.json` | `schemaVersion = 1.2.0`, baseline `ae5cc8cc...` preserved untouched |

### Baseline Preservation Verification (Real Data)
- **Stage 04 parity vs `stage04_b4_20261122_s6`:** `initial_models.joblib`, `selected_configs.json`, `b4_validation_evaluations.csv`, and `validation_candidate_evaluations.csv` have identical SHA-256 digests bit-for-bit.
- **Stage 05 parity vs `23616e7bab42de22ca0bb3153dfec8b695ea1d51ff9ad816bd02e14f849acfe6`:** `asset_volatility_predictions.csv`, `evaluation.csv`, and `drift_errors.csv` for all 5 benchmark models (`B0`–`B4`) match within `atol=1e-12` (exact numerical parity, excluding run UUIDs and wall-clock timestamps).

---

## 2. Stage 04 Initial Champion Selection (Validation Cutover `< 2025-10-01`)

Candidate pool: `{B0, B1, B2}` (`B3` and `B4` explicitly excluded). Only Validation rows whose 5-day realized volatility target matured strictly before `2025-10-01` (`target_end_date < 2025-10-01`, `is_label_mature == True`, `target_obs_count == 5`) were scored. All 5 immature anchors at cutover (`2025-09-24` through `2025-09-30`) were excluded. Zero Test labels were used.

| Ticker | Mature / Total Val Anchors | Immature Excluded | Paired Coverage | B0 MAE | B1 MAE | B2 MAE | Selected Initial Champion | Margin vs Runner-Up |
|---|---:|---:|---:|---:|---:|---:|---|---:|
| `SPY` | 245 / 250 | 5 | 100.00% | 0.078997 | 0.077645 | **0.058508** | **`B2` (`STATIC_SGD`)** | 0.019136 |
| `IEF` | 245 / 250 | 5 | 100.00% | 0.027368 | 0.017769 | **0.015989** | **`B2` (`STATIC_SGD`)** | 0.001780 |
| `GLD` | 245 / 250 | 5 | 100.00% | 0.052424 | 0.047528 | **0.047467** | **`B2` (`STATIC_SGD`)** | 0.000062 |

---

## 3. Real-Data Test Replay & Evaluation Summary (`2025-10-01` to `2026-09-25`)

### Coverage & Operational Audit
- **Eligible Test anchors:** 248 sessions/ETF (`744` served + `744` shadow = `1,488` published policy forecasts; `0` invalid forecasts; `100.00%` publish rate).
- **Mature evaluable Test anchors:** 243 sessions/ETF (`729` served + `729` shadow = `1,458` policy evaluations; `5` pending labels per ETF at strict cutoff `2026-09-25`; `97.98%` mature evaluation rate; mean label maturity lag `7.29` calendar days).
- **Policy ADWIN (`delta = 0.002`) observations & events:** `243` served mature observations per ETF (`729` total) → **`0` alerts, `0` decision events, `0` promotions** (`SPY`, `IEF`, `GLD` all remained on initial champion `v001` `B2` through `2026-09-25`).

### Matched Common Panel Performance (`paired_n = 243` per ETF, `729` MACRO)

| Strategy | SPY MAE | IEF MAE | GLD MAE | MACRO MAE | MACRO RMSE |
|---|---:|---:|---:|---:|---:|
| **Champion–Challenger Policy (Served)** | 0.039142 | 0.011510 | 0.106786 | **0.052479** | 0.099039 |
| Fixed Initial Champion (`B2` per ETF) | 0.039142 | 0.011510 | 0.106786 | 0.052479 | 0.099039 |
| Shadow B3 (`ONLINE_SGD`, continuously updating) | 0.038557 | 0.011503 | 0.096618 | 0.048892 | 0.093403 |
| `B0` (`CONSTANT_BASELINE`) | 0.051733 | 0.037564 | 0.138264 | 0.075853 | 0.119245 |
| `B1` (`ROLLING_20D_BASELINE`) | 0.044734 | 0.012243 | 0.121045 | 0.059340 | 0.099953 |
| `B2` (`STATIC_SGD`) | 0.039142 | 0.011510 | 0.106786 | 0.052479 | 0.099039 |
| `B3` (`ONLINE_SGD`) | 0.038557 | 0.011503 | 0.096618 | 0.048892 | 0.093403 |
| `B4` (`HAR_X_OLS`) | 0.036457 | 0.014575 | 0.102163 | 0.051065 | 0.094657 |

### Equal-Weight MACRO Paired Comparisons (`DeltaMAE = Comparator − Policy`, positive favors Policy)

| Comparison ID | Comparator | Paired N | Policy MAE | Comparator MAE | DeltaMAE | Relative Improvement |
|---|---|---:|---:|---:|---:|---:|
| `POLICY_VS_FIXED_INITIAL_CHAMPION` | `FIXED_INITIAL_CHAMPION` | 729 | 0.052479 | 0.052479 | 0.000000 | 0.00% |
| `POLICY_VS_SHADOW_B3` | `SHADOW_B3` | 729 | 0.052479 | 0.048892 | −0.003587 | −7.34% |
| `POLICY_VS_B0` | `CONSTANT_BASELINE` | 729 | 0.052479 | 0.075853 | +0.023374 | +30.81% |
| `POLICY_VS_B1` | `ROLLING_20D_BASELINE` | 729 | 0.052479 | 0.059340 | +0.006861 | +11.56% |
| `POLICY_VS_B2` | `STATIC_SGD` | 729 | 0.052479 | 0.052479 | 0.000000 | 0.00% |
| `POLICY_VS_B3` | `ONLINE_SGD` | 729 | 0.052479 | 0.048892 | −0.003587 | −7.34% |
| `POLICY_VS_B4` | `HAR_X_OLS` | 729 | 0.052479 | 0.051065 | −0.001415 | −2.77% |

**Interpretation of Real-Data Result:** Because `ADWIN(delta=0.002)` never fired on served `B2` mature absolute errors during the `2025-10-01..2026-09-25` Test window, the Drift-Triggered Champion–Challenger Policy behaved identically to Fixed Initial Champion (`B2`), outperforming `B0` (+30.81%) and `B1` (+11.56%) while trailing continuously-updating `B3` (−7.34%, mainly driven by `GLD` where `B3` MAE was `0.0966` vs `B2` `0.1068`) and `B4` (−2.77%). This transparently shows that a conservative `ADWIN(delta=0.002)` trigger can miss gradual error drift (e.g., `GLD`), motivating future out-of-sample policy sensitivity research without retroactively tuning thresholds on this Test set.

---

## 4. Evidence Level Separation: Real Data vs Deterministic Synthetic Fixtures

| Evidence Level | Scope | Verified Flows | Artifact / Test Reference |
|---|---|---|---|
| **Level 1: Real Curated Data** | `2025-10-01` – `2026-09-25` (`SPY`, `IEF`, `GLD`) | Cutover `B2` selection (245/245 mature Val rows), 1,488 forecasts, 1,458 evaluations, 729 ADWIN observations, **0 real alerts / 0 real switches**, exact B0–B4 parity, handoff ZIP + web policy sidecar `f6dd8cb1` rendered live in browser | `data/processed/ml_replay/experiments/5003376f...`, `data/processed/ml_evaluation/policy_experiments/f6dd8cb1...`, `docs/ml-results/downloads/policy/ml-results-policy-f6dd8cb1.zip`, `web/tests/policy.test.mjs` |
| **Level 2: Deterministic Synthetic Fixtures** *(not observed in real Test data)* | Controlled regime-shift & edge-case fixtures | Full `forecast → mature error → ADWIN alert → paired window (30/60, ≥5%, cooldown) → decision (insufficient_pairs, cooldown_suppressed, retained, invalid zero-MAE, promoted, B3-to-B3 promotion) → next-session effective champion → stale old-champion skip → 9 failure-injection points on promotion day → Stage 06 evaluation & hand-computed metrics → Export & snapshot integrity rejection of forged/tampered events → Web UI rendering of decision day vs effective day` | `tests/test_ml_replay.py`, `tests/test_ml_evaluation.py`, `tests/test_ml_results_handoff_export.py`, `web/tests/policy.test.mjs` |

---

## 5. Limitations
1. **Simulated Historical Replay & PIT Unverified:** `point_in_time_source_availability_verified = false`; market data were downloaded after the observation window and replayed using `target_end_date <= replay_date`.
2. **Retrospective Test Reuse:** Policy v1.0.0 was specified after observing Stage 06 Test outcomes (`ae5cc8cc...`), so all policy metrics are strictly **exploratory / non-confirmatory** and do not modify H1–H3.
3. **Shadow Process vs Frozen Snapshot:** Paired comparison measures the continuously updating Shadow B3 stream up to decision time, while promotion freezes a pre-update B3 snapshot to serve from the next session until a subsequent promotion.
4. **Zero Real Alerts Observed:** Promotion, retention, cooldown, and B3-to-B3 switching paths did not occur in real `2025-10-01..2026-09-25` Test data and are proven exclusively via deterministic fixtures.
