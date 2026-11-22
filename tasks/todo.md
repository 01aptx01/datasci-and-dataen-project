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

- [ ] Train keys, X/y และ scaler ตรงกับ B2 ต่อ ETF และไม่เกิน cutoff
- [ ] Fit ครบสาม ETF ตรวจกรณี Train ไม่พอ, rank deficiency และ invalid forecasts
- [ ] บันทึกและโหลด artifact ได้ ตรวจ forecast, rerun และผล Validation พร้อม coverage

## Session 3 — Replay

- [ ] Forecast B4 ตรง OLS artifact, version และ Train label cutoff ถูกต้อง
- [ ] ตรวจ coverage, invalid, pending และ no-update ของ B4 พร้อมตรวจผล B0–B3
- [ ] ผล resume สอดคล้องกับ run ต่อเนื่องและปฏิเสธ checkpoint ไม่ตรง suite/artifact

## Session 4 — Evaluation

- [ ] แสดง paired panels, common B0–B4 และชุดอ้างอิง B0–B3 พร้อม N และ coverage
- [ ] ตรวจ MAE/RMSE, equal ETF weighting, DeltaMAE และกรณี B4 invalid
- [ ] ตรวจ H1–H3 เทียบ reference และส่งออกข้อมูล B4 สำหรับ downstream พร้อม portfolio

## Session 5 — Handoff และ Dashboard

- [ ] Export/prepare ตรวจห้าโมเดล, artifact identity, row counts และ checksum
- [ ] Build/test ผ่าน และตรวจ Forecast, Replay, Comparison, Portfolio กับข้อมูล B4
- [ ] ตรวจ pending, forecast ไม่ครบ และ drift ของ B3 บันทึกระดับข้อมูลที่ใช้ตรวจ

## Session 6 — รันจริง

- [ ] บันทึก Git revision, hashes และ run IDs ตรวจ inputs → artifacts → ZIP → policy
- [ ] เปิด build จาก snapshot จริง ตรวจ B4 บนหน้าจอเทียบกับ artifact
- [ ] สรุปผล B4 ราย ETF และ macro พร้อม coverage, panels, baseline และข้อจำกัด

รูปแบบหลักฐานต่อ session

- สถานะ: PASS / FAIL / BLOCKED
- คำสั่งและผลตรวจ:
- Artifacts / run IDs:
- เกณฑ์ที่ยังไม่ผ่านและสิ่งที่ขาด:

