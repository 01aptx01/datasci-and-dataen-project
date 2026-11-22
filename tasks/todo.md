# Checklist B4 ราย session

ทำตาม [แผน](plan.md) และ [prompts](prompts.md) ติ๊กเมื่อมีหลักฐานจริงและบันทึกคำสั่ง ผล และ path หรือ run ID ใต้ session นั้น

## Session 1 — Input และวิธีทดลอง

- [x] ตรวจ branch, runtime, path/คำสั่ง, ข้อมูลจริงสาม ETF, manifests และแผนสร้างหรือกู้ input
- [x] ตรึง B4: ฟีเจอร์ 8 ตัว, sample, scaler, OLS, cutoff, rank/invalid policy และเกณฑ์ Validation
- [x] ระบุ baseline run, ชุดแถวเปรียบเทียบ, suite/artifact identity และข้อกำหนด Git ก่อน export

### หลักฐาน Session 1
- **สถานะ**: `PASS`
- **Branch & Runtime**:
  - Branch: `feature/add-model` @ `220066d65af0973c6a9ad570b175a891d7e16ed6` (รักษา `tasks/` เดิม; `logs/ingestion_runs.jsonl` มีรายการรัน ingestion เพิ่ม 1 บรรทัด)
  - Python: `3.10.11` (`.venv\Scripts\python.exe` สร้างด้วย `uv sync --locked --group dev`, `scikit-learn==1.7.2`, `river==0.22.0`, `pandas==2.2.3`, `numpy==2.2.6`, `scipy==1.15.3`, `statsmodels==0.15.0`, `yfinance==1.8.0`, `pandas-market-calendars==5.5.0`, `pyarrow==25.0.1`)
  - Node/npm: `v25.2.1` / `11.6.2`
- **คำสั่งและผลตรวจแต่ละ Stage (สร้าง input จริงใหม่เพราะ `data/` เดิมมีเพียง `.gitkeep`)**:
  - **Ingestion**: `.venv\Scripts\python.exe -m src.ingestion.run --config config/ingestion.yaml` → `run_20261122_143125_b6e5` (`SUCCESS`, `portfolio_ready=True`, `source_batch_id=yf_20261122_143125_b6e5`), output: `data/raw/yfinance/run_id=run_20261122_143125_b6e5/`, `data/curated/market_prices_daily.parquet`, `data/audit/run_id=run_20261122_143125_b6e5/`.
  - **Features & Correlations**: `.venv\Scripts\python.exe -m src.features.run --config config/features.yaml` → `feat_20261122T143142_ad87117a` (`COMMITTED`, `feature_rows=3948`, `correlation_rows=1316`, `feature_warning_count=3`, `failed_tickers=[]`), output: `data/curated/asset_volatility_features.parquet`, `data/curated/asset_rolling_correlations.parquet` (1,296 rows `is_corr_ready=True`), `data/audit/features/run_id=feat_20261122T143142_ad87117a/{manifest.json,publish-transaction.json,quality_results.parquet}`.
  - **Targets/Labels**: `.venv\Scripts\python.exe -m src.targets.run --config config/target.yaml` → `target_20261122T143149_c9b24e99` (`COMMITTED`, `rows_in_run=3765`, `mature_rows_in_run=3750`, `pending_rows_in_run=15`, `finding_count=0`), output: `data/curated/asset_volatility_labels.parquet`, `data/audit/targets/run_id=target_20261122T143149_c9b24e99/{manifest.json,publish-transaction.json}`.
  - **Dataset & H1 (Stage 03)**: Python API `src.ml_dataset.{DatasetConfig, load_validated_inputs, prepare_ml_dataset, analyze_h1}` (`config/ml_dataset.yaml`) → `manifest_verification="verified"`, `source_quality_passed=true`, `point_in_time_source_availability_verified=false`; 3 ETFs ครบ (`SPY`, `IEF`, `GLD`), `dup keys=0`, XNYS ตรงกัน (`features: 2021-06-30..2026-09-25`, `labels: 2021-09-27..2026-09-25`), `prediction_eligible_rows=3765`, `supervised_eligible_rows=3720` (`train=752`, `validation=245`, `test=243` ต่อ ETF), `fixed_purged_rows=30`, `online_update_eligible_rows=3750`.
  - **Training (Stage 04)**: Python API `src.ml_training.run_training_selection(prepared, inputs.labels, artifact_dir=...)` (`config/ml_training.yaml`) → output ใหม่ `data/processed/ml_training/run_id=<b4-training-run>/`.
  - **Replay (Stage 05)**: Python API `src.ml_replay.run_final_replay(prepared, inputs.labels, initial_model_artifact_dir=..., output_root="data/processed/ml_replay")` (`config/ml_replay.yaml`) → `data/processed/ml_replay/experiments/<experiment_id>/`.
  - **Evaluation (Stage 06)**: `.venv\Scripts\python.exe -m src.ml_evaluation.run --config config/ml_evaluation.yaml` → `data/processed/ml_evaluation/experiments/<evaluation_id>/`.
  - **Export & Web**: `.venv\Scripts\python.exe scripts/export_ml_results_handoff.py --source-dir ... --replay-dir ... --output-dir ...`; `cd web && npm run build && npm test && npm run preview` (ใช้ `scripts/web/prepare_snapshot.py` และ `web/snapshot.policy.json`).
- **Lineage ข้อมูลจริงรอบใหม่**:
  - `source_batch_ids`: `["yf_20261122_143125_b6e5"]` (`Yahoo Finance:1.8.0`)
  - `source_input_sha256`: `044ed39a9f96a84386951f0326eaf8f4d2eea3d8faacda9a8cc54ebc7e2e55fc`
  - `feature_parquet_sha256`: `9ced880aa6f349691b2a4f84e1ffe66e3d282491e42bccfca86b29622d24445b`
  - `target_parquet_sha256`: `b380152d6b107a7bcb9280e51d85afddfb10d2e198a1e6564339ce9409ae9a0b`
  - ข้อจำกัดจาก manifest: `point_in_time_source_availability_verified=false` (Simulated Historical Replay จาก snapshot ที่ดาวน์โหลดภายหลัง).
- **Spec B4 ที่ตรึงไว้**:
  - **Identity & Versions**: `model_id="B4"`, `model_name="HAR_X_OLS"`, UI label `"B4 · HAR-X (OLS)"`, `model_version="b4_ols_v1.0.0"`, `model_suite_version="1.1.0"`, `training_config_version="1.1.0"`, `evaluation_config_version="1.1.0"`, `handoff_schema_version="1.1.0"`.
  - **Model & Features**: OLS พร้อม intercept (`fit_intercept=True`, unregularized) ทำนาย `target_realized_vol_5d` (annualized decimal, t+1..t+5) จาก 8 Core Features ลำดับเดิม: `ret_1d_t`, `ret_lag_1d`, `ret_lag_2d`, `ret_trailing_5d`, `ret_trailing_20d`, `rv_5d`, `rv_20d`, `rv_60d`.
  - **Train Sample, Scaler & Cutoff**: ใช้แถว Train (`2021-09-27..2024-09-30`, `752` แถว/ETF, `target_end_date < 2024-10-01`) และ `RobustScaler` ตัวเดียวกับ B2 ต่อ ETF (fit เฉพาะ Train แล้ว freeze); `data_cutoff="2026-09-25"`; B4 freeze ตลอด Replay (ไม่อัปเดตออนไลน์และไม่เข้า ADWIN).
  - **Degenerate / Rank / Invalid Policy**: Train `< 9` แถวหรือมี non-finite `X`/`y` → fail fit (`TrainingError`); design matrix `[1, X_scaled]` มี `rank < 9` → fail fit (`TrainingError`); full rank แต่ `cond([1, X_scaled]) > 1e8` → บันทึก warning ใน diagnostics/manifest โดยไม่ fail; forecast ติดลบ/`NaN`/`inf` → ปฏิเสธโดยไม่ clip (`reject_and_count_without_clipping`), บันทึก failure reason และนับใน coverage.
  - **เกณฑ์ Validation ต่อ ETF**: fit ครบ 3 ETF, `rank == 9`, `max(target_end_date) < 2024-10-01`, มีคู่ Validation ที่ประเมินได้ `> 0` ต่อ ETF (คาด 245/ETF), รายงาน MAE/RMSE, counts, coverage และสาเหตุ invalid โดยไม่นำไปปน objective เลือก B2/B3.
  - **Comparison & Baseline Run**: ZIP อ้างอิงอยู่ที่ [ml-results-handoff-82572c84.zip](file:///f:/ComSci/Coding/Project/datasci-and-dataen-project/docs/ml-results/downloads/ml-results-handoff-82572c84.zip) (`evaluation_id=82572c84...`, `replay_id=3cbf81eb...`, `yf_20261113_180842_f703`). รอบใหม่รัน B0–B4 จาก input `feat_20261122T143142_ad87117a` / `target_20261122T143149_c9b24e99` เดียวกัน รายงานผลชุดร่วม B0–B4, ชุดอ้างอิง B0–B3 จากรอบเดียวกัน และคู่ `B4 vs B2/B3/B1` ที่ match `(prediction_date, ticker, split)` ด้วย `DeltaMAE = comparator_MAE - B4_MAE` (บวก = B4 error ต่ำกว่า, retrospective บน Test).
  - **Git HEAD & Output Paths รอบใหม่**: `scripts/export_ml_results_handoff.py` ตรวจ `git show HEAD:src/ml_evaluation/<file>` และ `config/ml_evaluation.yaml` / `config/hypothesis_tests.yaml` เทียบ `code_sha256_by_file` ดังนั้นก่อนรัน Stage 06/Export จริงใน Session 6 ต้อง commit โค้ด/config ที่แก้ใน `src/ml_evaluation/` ให้ตรงกับ `HEAD`. ตำแหน่ง run ใหม่แยกจาก ZIP เดิม: `data/audit/ml_dataset/run_id=stage03_h1_b4_<run>`, `data/processed/ml_training/run_id=stage04_b4_<run>`, `data/processed/ml_replay/experiments/<new_id>`, `data/processed/ml_evaluation/experiments/<new_id>`.
- **Artifacts / run IDs**: `run_20261122_143125_b6e5`, `feat_20261122T143142_ad87117a`, `target_20261122T143149_c9b24e99`.
- **เกณฑ์ที่ยังไม่ผ่านและสิ่งที่ขาด**: ไม่มี (พร้อมสำหรับ Session 2).

## Session 2 — Training

- [x] Train keys, X/y และ scaler ตรงกับ B2 ต่อ ETF และไม่เกิน cutoff
- [x] Fit ครบสาม ETF ตรวจกรณี Train ไม่พอ, rank deficiency และ invalid forecasts
- [x] บันทึกและโหลด artifact ได้ ตรวจ forecast, rerun และผล Validation พร้อม coverage

### หลักฐาน Session 2
- **สถานะ**: `PASS`
- **โค้ดที่เพิ่ม/แก้**:
  - [pipeline.py](file:///f:/ComSci/Coding/Project/datasci-and-dataen-project/src/ml_training/pipeline.py): เพิ่ม `fit_b4_ols`, `evaluate_b4_validation`, `b4_state_sha256`, `scaler_state_sha256`, `_train_keys_fingerprint` และเชื่อมใน `run_training_selection(..., include_b4=True)` กับ `_persist_artifacts` (บันทึก `b4_models` ลง `initial_models.joblib`, `b4_validation_evaluations.csv` พร้อม SHA-256 และ metadata ใน `training_manifest.json`)
  - [__init__.py](file:///f:/ComSci\Coding\Project\datasci-and-dataen-project\src\ml_training\__init__.py): export สัญลักษณ์ B4
  - [test_ml_training.py](file:///f:/ComSci/Coding/Project/datasci-and-dataen-project/tests/test_ml_training.py) และ [test_ml_replay.py](file:///f:/ComSci/Coding/Project/datasci-and-dataen-project/tests/test_ml_replay.py): เพิ่ม 6 unit tests ของ B4 และคง `include_b4=False` ใน fixture 5 แถวเดิมของ Replay จนถึง Session 3
- **คำสั่งและผลตรวจ**:
  - Unit tests: `.venv\Scripts\python.exe -m pytest tests\test_ml_training.py tests\test_ml_replay.py -v` → **25 passed** (ครอบคลุม parity กับ B2, reload/rerun `atol=1e-15`, `n_train < 9`, `rank < 9`, `cond > 1e8` warning, non-finite inputs, invalid/negative forecast rejection และ B2/B3 selection ไม่เปลี่ยน)
  - Real data Training & Validation (`run_training_selection(prepared, inputs.labels, artifact_dir=...)` บน `feat_20261122T143142_ad87117a` / `target_20261122T143149_c9b24e99`):
    - **B2/B3 Selected Configs** (ไม่ถูกกระทบโดย B4): `SPY` `eta0=0.0001;alpha=0.001;max_iter=20` (`joint_mae=0.058424`), `IEF` `eta0=0.0001;alpha=0.001;max_iter=20` (`joint_mae=0.015972`), `GLD` `eta0=0.0001;alpha=1e-05;max_iter=50` (`joint_mae=0.047363`), `paired_coverage=1.0` ทุก ETF
    - **B4 (`HAR_X_OLS`, `b4_ols_v1.0.0`) Validation ต่อ ETF** (`train_keys_count=752`, `last_training_target_end_date=2024-09-30`, `design_rank=9`, `ill_conditioned=false`, `invalid_count=0`, `coverage=1.0`):
      - `SPY`: `MAE=0.0677885`, `RMSE=0.1124468`, `valid=245/245`, `cond=6.7274`
      - `IEF`: `MAE=0.0178751`, `RMSE=0.0214478`, `valid=245/245`, `cond=4.1858`
      - `GLD`: `MAE=0.0494148`, `RMSE=0.0679756`, `valid=245/245`, `cond=3.6950`
    - **Artifact Reload & Rerun Parity**: `scaler_match_b2=True`, `state_hash_match=True`, `max_diff_disk=0.00e+00`, `max_diff_rerun=0.00e+00` ครบทั้ง 3 ETF
- **Artifacts / run IDs**:
  - `data/processed/ml_training/run_id=stage04_b4_20261122_01` (`initial_models.joblib`, `training_manifest.json`, `b4_validation_evaluations.csv`, `validation_candidate_evaluations.csv`, `selected_configs.json`, `training_config.json`)
  - Rerun verification: `data/processed/ml_training/run_id=stage04_b4_20261122_01_rerun`
- **เกณฑ์ที่ยังไม่ผ่านและสิ่งที่ขาด**: ไม่มี (พร้อมสำหรับ Session 3).

## Session 3 — Replay

- [x] Forecast B4 ตรง OLS artifact, version และ Train label cutoff ถูกต้อง
- [x] ตรวจ coverage, invalid, pending และ no-update ของ B4 พร้อมตรวจผล B0–B3
- [x] ผล resume สอดคล้องกับ run ต่อเนื่องและปฏิเสธ checkpoint ไม่ตรง suite/artifact

### หลักฐาน Session 3
- **สถานะ**: `PASS`
- **ตรวจ Session 2 Artifact ก่อนเริ่ม**: `data/processed/ml_training/run_id=stage04_b4_20261122_01/training_manifest.json` (`selection_status=selected`, `checksums_ok=True`, `feature_order` 8 ตัวตรง, `train_cutoff=2024-09-30`, `last_training_target_end_date=2024-09-30`, `b4_ols_v1.0.0`)
- **โค้ดและสัญญาที่อัปเดต**:
  - [models.yaml](file:///f:/ComSci/Coding/Project/datasci-and-dataen-project/config/models.yaml): `model_suite_version="1.1.0"`, เพิ่ม `B4` (`HAR_X_OLS`, `strategy: ols`, `update_policy: frozen_after_initial_fit`)
  - [prediction_contract.md](file:///f:/ComSci/Coding/Project/datasci-and-dataen-project/docs/contract/prediction_contract.md) และ [datadict.md](file:///f:/ComSci/Coding/Project/datasci-and-dataen-project/docs/contract/datadict.md): เพิ่ม `HAR_X_OLS` (`B4`)
  - [pipeline.py](file:///f:/ComSci/Coding/Project/datasci-and-dataen-project/src/ml_replay/pipeline.py): เพิ่ม `B4` ใน `MODEL_NAMES`/`MODEL_ORDER`, ตรวจ `MODEL_SUITE_VERSION="1.1.0"`, โหลดและตรวจ checksum/scaler/cutoff ของ `b4_models`, แยกกิ่ง `B3` และ `B4` ชัดเจน, ผูก `b4_initial_state_sha256_by_ticker`/`model_suite_version`/`model_order` ใน `compatibility_fingerprint`, และตรวจ `b4_frozen_state_verified=True`
  - [test_ml_contract_config.py](file:///f:/ComSci/Coding/Project/datasci-and-dataen-project/tests/test_ml_contract_config.py) และ [test_ml_replay.py](file:///f:/ComSci/Coding/Project/datasci-and-dataen-project/tests/test_ml_replay.py): อัปเดต fixture และเพิ่ม unit tests ของ B4 direct parity, invalid/pending, stop/resume และ incompatible checkpoint
- **คำสั่งและผลตรวจ**:
  - Unit tests:
    - `.venv\Scripts\python.exe -m pytest tests\test_ml_replay.py -v` (รันคู่ใน `task-361`) → **16 passed**
    - `.venv\Scripts\python.exe -m pytest tests\test_ml_contract_config.py -v` → **3 passed**
  - Real Final Replay (`run_final_replay` บน `feat_20261122T143142_ad87117a` / `target_20261122T143149_c9b24e99` + `stage04_b4_20261122_01`):
    - `completed=True`, `sessions=498` (`2024-10-01`..`2026-09-25`), `b2_frozen=True`, `b4_frozen=True`
    - `predictions_by_model`: `1,494` ต่อโมเดลทั้ง 5 โมเดล (รวม `7,470` แถว), `evaluations_by_model`: `1,479` ต่อโมเดล, `pending_by_model`: `15` ต่อโมเดล, `invalid_by_model`: `0` ต่อโมเดล
    - B4 direct artifact parity (`30` sampled predictions): `max_direct_diff = 9.02e-17`, `model_version = ["b4_ols_v1.0.0"]`, `last_training_target_end_date = ["2024-09-30"]`
    - B3 only updates/ADWIN: `updates_count=1494`, `drift_errors_count=1479`
    - B0–B3 Test parity เทียบ ZIP อ้างอิง `ml-results-handoff-82572c84.zip` (`count=729` ต่อโมเดล): `CONSTANT_BASELINE` MAE `0.075853` (ref `0.075854`), `ROLLING_20D_BASELINE` `0.059340` (ref `0.059340`), `STATIC_SGD` `0.052479` (ref `0.052479`), `ONLINE_SGD` `0.048892` (ref `0.048892`); `HAR_X_OLS` `0.051065`
- **Artifacts / run IDs**:
  - Replay experiment: `data/processed/ml_replay/experiments/b39bd163e0176a90aad5b8b1accb4adacaca5af8bfacb8cb937676f25da32101` (`outputs/{asset_volatility_predictions.csv,evaluation.csv,coverage.csv,drift_errors.csv,drift_alerts.csv,updates.csv,forecast_failures.csv}`, `experiment_manifest.json`, `checkpoints/committed/`)
- **เกณฑ์ที่ยังไม่ผ่านและสิ่งที่ขาด**: ไม่มี (พร้อมสำหรับ Session 4).

## Session 4 — Evaluation

- [x] แสดง paired panels, common B0–B4 และชุดอ้างอิง B0–B3 พร้อม N และ coverage
- [x] ตรวจ MAE/RMSE, equal ETF weighting, DeltaMAE และกรณี B4 invalid
- [x] ตรวจ H1–H3 เทียบ reference และส่งออกข้อมูล B4 สำหรับ downstream พร้อม portfolio

### หลักฐาน Session 4
- **สถานะ**: `PASS`
- **ตรวจ Session 3 Replay Manifest ก่อนเริ่ม**: `data/processed/ml_replay/experiments/b39bd163e0176a90aad5b8b1accb4adacaca5af8bfacb8cb937676f25da32101/experiment_manifest.json` (`status=COMPLETED`, `b2_frozen_state_verified=True`, `b4_frozen_state_verified=True`, `model_suite_version=1.1.0`)
- **โค้ดที่อัปเดต**:
  - [config.py](file:///f:/ComSci/Coding/Project/datasci-and-dataen-project/src/ml_evaluation/config.py) & [ml_evaluation.yaml](file:///f:/ComSci/Coding/Project/datasci-and-dataen-project/config/ml_evaluation.yaml): `evaluation_config_version="1.1.0"`, เพิ่ม `HAR_X_OLS` ใน `MODEL_NAMES`
  - [pipeline.py](file:///f:/ComSci/Coding/Project/datasci-and-dataen-project/src/ml_evaluation/pipeline.py): รองรับ 5 โมเดลใน `forecast_audit.csv`, `coverage.csv`, `model_metrics.csv` (`common B0-B4 matured valid anchors`), `high_volatility_metrics.csv`, `monthly_metrics.csv`, `yearly_metrics.csv`, `rolling_mae20.csv`, `portfolio_risk.csv`; เพิ่ม `reference_b0_b3_metrics.csv` และ `b4_comparisons.csv` (แยกบทบาท retrospective ของ B4 ออกจาก H2/H3 ใน `hypothesis_results.csv` และ `pair_comparisons.csv`, นิยาม `delta_mae_comparator_minus_b4 = comparator_MAE - B4_MAE`)
  - [test_ml_evaluation.py](file:///f:/ComSci/Coding/Project/datasci-and-dataen-project/tests/test_ml_evaluation.py): เพิ่ม unit tests คำนวณ MAE/RMSE, equal-ETF Macro และ DeltaMAE ด้วยมือ และทดสอบ B4 invalid ลดชุดร่วม 5 โมเดลโดยไม่ลดชุดอ้างอิง B0–B3 และ pending ไม่ถูกคิดคะแนน
- **คำสั่งและผลตรวจ**:
  - Unit tests: `.venv\Scripts\python.exe -m pytest tests\test_ml_evaluation.py -v` → **19 passed**
  - Real H1 & Stage 06 Evaluation (`analyze_h1` + `run_final_evaluation` บน Replay `b39bd163...`):
    - **Common B0–B4 & Reference B0–B3** (`paired_n=729`, `243/248` ต่อ ETF, `paired_coverage=0.979839`, pending 15 แถวไม่ถูกคิดคะแนน):
      - `CONSTANT_BASELINE`: `MAE=0.075853`, `RMSE=0.119245`
      - `ROLLING_20D_BASELINE`: `MAE=0.059340`, `RMSE=0.099953`
      - `STATIC_SGD`: `MAE=0.052479`, `RMSE=0.099039`
      - `ONLINE_SGD`: `MAE=0.048892`, `RMSE=0.093403`
      - `HAR_X_OLS` (`B4`): `MAE=0.051065`, `RMSE=0.094657`
    - **B4 Retrospective Paired Comparisons (`b4_comparisons.csv`)** (`DeltaMAE = comparator_MAE - B4_MAE`):
      - `B4_VS_B2`: `MACRO DeltaMAE=+0.001415` (`+2.70%`), `SPY +0.002685`, `IEF -0.003065`, `GLD +0.004624`
      - `B4_VS_B3`: `MACRO DeltaMAE=-0.002172` (`-4.44%`), `SPY +0.002100`, `IEF -0.003072`, `GLD -0.005545`
      - `B4_VS_B1`: `MACRO DeltaMAE=+0.008276` (`+13.95%`), `SPY +0.008277`, `IEF -0.002332`, `GLD +0.018882`
    - **H1–H3 Parity เทียบ ZIP อ้างอิง**: `H2` (`n=729`, `effect=0.003587`, `p_adj=0.001999`, `Reject H₀`) และ `H3` (`n=729`, `effect=0.010448`, `p_adj=0.005997`, `Reject H₀`) ตรง ZIP อ้างอิง; `H1` (`n=752` ต่อ ETF) `Reject H₀` ทั้ง 3 ETF
    - **Portfolio Risk**: `498` แถว (`OK`) ครบทั้ง 5 โมเดลรวม `HAR_X_OLS` ใช้ correlations ชุดเดียวกัน
- **Artifacts / run IDs**:
  - H1: `data/audit/ml_dataset/run_id=stage03_h1_b4_20261122_01`
  - Evaluation: `data/processed/ml_evaluation/experiments/b90df6ae5a3a2445f68e533a346c9aa24bdb248b67a4888142911de34b5125ec` (`b4_comparisons.csv`, `reference_b0_b3_metrics.csv`, `model_metrics.csv`, `portfolio_risk.csv`, `hypothesis_results.csv`, `execution_manifest.json`)
- **เกณฑ์ที่ยังไม่ผ่านและสิ่งที่ขาด**: ไม่มี (พร้อมสำหรับ Session 5).

## Session 5 — Handoff และ Dashboard

- [x] Export/prepare ตรวจห้าโมเดล, artifact identity, row counts และ checksum
- [x] Build/test ผ่าน และตรวจ Forecast, Replay, Comparison, Portfolio กับข้อมูล B4
- [x] ตรวจ pending, forecast ไม่ครบ และ drift ของ B3 บันทึกระดับข้อมูลที่ใช้ตรวจ

### หลักฐาน Session 5
- **สถานะ**: `PASS`
- **ระดับข้อมูลที่ใช้ตรวจ**: Export จากผล Evaluation รอบจริง `b90df6ae...` (`repo_root=None` ใน Session 5; เก็บการตรวจ Git HEAD ของ exporter และการยืนยัน full end-to-end dataset จริงไว้ Session 6) ร่วมกับ synthetic incomplete-ETF fixture test ใน [b4.test.mjs](file:///f:/ComSci/Coding/Project/datasci-and-dataen-project/web/tests/b4.test.mjs)
- **โค้ดและ Policy ที่อัปเดต**:
  - [export_ml_results_handoff.py](file:///f:/ComSci/Coding/Project/datasci-and-dataen-project/scripts/export_ml_results_handoff.py) & [test_ml_results_handoff_export.py](file:///f:/ComSci/Coding/Project/datasci-and-dataen-project/tests/test_ml_results_handoff_export.py): เพิ่ม `HAR_X_OLS`, `b4_comparisons.csv`, `reference_b0_b3_metrics.csv`, `handoff_schema_version="1.1.0"`
  - [prepare_snapshot.py](file:///f:/ComSci/Coding/Project/datasci-and-dataen-project/scripts/web/prepare_snapshot.py): รองรับทั้ง `1.0.0` (4 โมเดล) และ `1.1.0` (5 โมเดล + `b4Comparisons` + `referenceB0B3Metrics`)
  - [snapshot.b4.policy.json](file:///f:/ComSci/Coding/Project/datasci-and-dataen-project/web/snapshot.b4.policy.json): policy `1.1.0` สำหรับ B4 snapshot (แยกจาก [snapshot.policy.json](file:///f:/ComSci/Coding/Project/datasci-and-dataen-project/web/snapshot.policy.json) `1.0.0` เดิม)
  - Web TypeScript & Tests: [schemas.ts](file:///f:/ComSci/Coding/Project/datasci-and-dataen-project/web/src/data/schemas.ts), [loadSnapshot.ts](file:///f:/ComSci/Coding/Project/datasci-and-dataen-project/web/src/data/loadSnapshot.ts), [replay.ts](file:///f:/ComSci/Coding/Project/datasci-and-dataen-project/web/src/data/replay.ts), [stitch.ts](file:///f:/ComSci/Coding/Project/datasci-and-dataen-project/web/src/stitch.ts), [stitchOther.ts](file:///f:/ComSci/Coding/Project/datasci-and-dataen-project/web/src/stitchOther.ts), [b4.test.mjs](file:///f:/ComSci/Coding/Project/datasci-and-dataen-project/web/tests/b4.test.mjs)
- **คำสั่งและผลตรวจ**:
  - Export unit tests: `.venv\Scripts\python.exe -m pytest tests\test_ml_results_handoff_export.py -v` → **5 passed**
  - Export B4 ZIP (`repo_root=None`): `data/processed/handoff_b4/ml-results-handoff-b4-b90df6ae.zip` (`sha256=9818537d1ecf2843ce8c0a00764245d7ffb546fa3baf42fab77ae7af07c6b34c`)
  - Prepare B4 snapshot + Tampered Rejection:
    - `.venv\Scripts\python.exe scripts\web\prepare_snapshot.py --repo-root . --policy web\snapshot.b4.policy.json --output web\public\snapshots` → `SNAPSHOT VERIFIED` (`test_pending_rows=75`)
    - Tampered `zipSha256` → `rc=1` (`SNAPSHOT REJECTED: SHA256SUMS.txt does not match the pinned ZIP identity`)
    - Tampered `evaluationId` → `rc=1` (`SNAPSHOT REJECTED: Evaluation ID does not match the pinned review snapshot`)
  - Web Build & Automated Tests: `cd web && npm test` → **33/33 passed** (รวม `1.0.0` baseline 29 tests + `1.1.0` B4 snapshot, `b4Comparisons`, `pending` และ `INCOMPLETE_INPUTS` incomplete-ETF portfolio risk 4 tests)
  - Live Preview UI Inspection (`npm run preview` @ `http://localhost:4173` ผ่าน `agent-browser`, zero browser errors):
    - `#/portfolio?model=HAR_X_OLS`: แสดงพอร์ต `B4` วันที่ `2026-09-25` (`9.442% ต่อปี`, `SPY 11.526%`, `IEF 7.010%`, `GLD 14.759%`)
    - `#/forecasts`: เลือก `HAR_X_OLS` + filter `pending` → `แถวตามตัวกรอง=5`, `Pending=5`
    - `#/replay?model=HAR_X_OLS&date=2026-09-25`: ตรวจทั้งมุมมองรายเดือนและรายวัน แสดง `Forecast 1.623%`, `Actual —`, `Abs Error —`, `VALID / PENDING / PENDING_LABEL`
    - `#/models`: แสดงครบ 5 โมเดล `B0–B4` (`B4 5.11 pp`) และตาราง `การเปรียบเทียบ B4 · HAR-X (OLS) แบบ Retrospective` (`B4_VS_B2 +0.14 pp`, `B4_VS_B3 -0.22 pp`, `B4_VS_B1 +0.83 pp`, `Paired N=729`, `Coverage=97.98%`)
    - `#/monitoring`: แสดง `ADWIN 0 alerts · 729 observations` (`SPY · B3`) และ `สถานะ B4 · HAR-X (OLS): Static (Frozen)`
- **เกณฑ์ที่ยังไม่ผ่านและสิ่งที่ขาด**: ไม่มี (พร้อมสำหรับ Session 6; หมายเหตุว่าใน Session 6 ต้องจัดการ CRLF/LF ของ Git HEAD exporter ก่อนรันรอบจริง).

## Session 6 — รันจริง

- [ ] บันทึก Git revision, hashes และ run IDs ตรวจ inputs → artifacts → ZIP → policy
- [ ] เปิด build จาก snapshot จริง ตรวจ B4 บนหน้าจอเทียบกับ artifact
- [ ] สรุปผล B4 ราย ETF และ macro พร้อม coverage, panels, baseline และข้อจำกัด

### หลักฐาน Session 6
- **สถานะ**: `BLOCKED`
- **คำสั่งและผลตรวจ**:
  - ตรวจ Session 1–5 ใน [todo.md](file:///f:/ComSci/Coding/Project/datasci-and-dataen-project/tasks/todo.md): Sessions 1–4 `PASS`, **Session 5 `BLOCKED`** (ยังไม่ได้ตรวจหน้าเว็บจริงใน Chrome เพราะไม่พบ `DevToolsActivePort`)
  - ตรวจ Git revision & exporter Git HEAD verification: `git rev-parse HEAD` → `2b5c947d8dbc0c701ff1411134f1547f8b1bcac3` (`feature/add-model`, clean); ทดสอบ `verify_source_artifacts(..., repo_root=Path("."))` บน Stage 06 `b90df6ae...` → `ArtifactVerificationError: Stage 06 code hashes do not match the current Git source` (เนื่องจากไฟล์ `src/ml_evaluation/*.py` บน Windows เป็น CRLF ขณะที่ `git show HEAD:src/ml_evaluation/*.py` เป็น LF)
- **Artifacts / run IDs ที่พร้อมอยู่ (จาก Sessions 1–5)**:
  - Source/Features/Targets: `run_20261122_143125_b6e5`, `feat_20261122T143142_ad87117a`, `target_20261122T143149_c9b24e99`
  - H1 / Training / Replay / Evaluation: `stage03_h1_b4_20261122_01`, `stage04_b4_20261122_01`, `b39bd163e0176a90aad5b8b1accb4adacaca5af8bfacb8cb937676f25da32101`, `b90df6ae5a3a2445f68e533a346c9aa24bdb248b67a4888142911de34b5125ec`
  - Handoff ZIP (non-Git-HEAD export จาก Session 5): `data/processed/handoff_b4/ml-results-handoff-b4-b90df6ae.zip` (`sha256=9818537d1ecf2843ce8c0a00764245d7ffb546fa3baf42fab77ae7af07c6b34c`), policy [snapshot.b4.policy.json](file:///f:/ComSci/Coding/Project/datasci-and-dataen-project/web/snapshot.b4.policy.json)
- **เกณฑ์ที่ยังไม่ผ่านและสิ่งที่ขาด**:
  1. Session 5 ยัง `BLOCKED` (ต้องเปิด Chrome remote debugging `chrome://inspect/#remote-debugging` เพื่อตรวจหน้าเว็บจริงให้ผ่านก่อน)
  2. Git HEAD code-hash mismatch ของ `scripts/export_ml_results_handoff.py` บน Windows (`CRLF` บนดิสก์ vs `LF` ใน `git show HEAD:`) ทำให้ `export_results_bundle(..., repo_root=Path("."))` หยุดที่ขั้นตอน verify Git identity ของ exporter (ต้องรันบน LF working tree หรือให้ exporter/evaluation เทียบ line-ending ให้ตรงกันก่อนรันรอบ Export จริงใน Session 6)

รูปแบบหลักฐานต่อ session

- สถานะ: PASS / FAIL / BLOCKED
- คำสั่งและผลตรวจ:
- Artifacts / run IDs:
- เกณฑ์ที่ยังไม่ผ่านและสิ่งที่ขาด:

