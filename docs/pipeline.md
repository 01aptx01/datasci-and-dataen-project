# สรุปภาพรวมระบบและสัญญาข้อมูล (Project & Contract Overview)

เอกสารสรุปสำหรับอ่านทบทวนและนำเสนอ ครอบคลุมแนวคิดหลักของระบบ วิวัฒนาการการออกแบบ และสรุปสาระสำคัญจาก Contract ทั้ง 4 ฉบับที่ได้ดำเนินการเสร็จสิ้นในปัจจุบัน

---

## 1. เป้าหมายและแนวคิดหลักของระบบ (Core Concept)

- **โจทย์หลัก**: ประมาณความเสี่ยงจากความผันผวนของพอร์ตโฟลิโอที่ประกอบด้วย ETF 3 สินทรัพย์ ได้แก่ **`SPY`** (หุ้นสหรัฐฯ), **`IEF`** (พันธบัตรรัฐบาลสหรัฐฯ 7–10 ปี) และ **`GLD`** (ทองคำ)
- **หลักการออกแบบ (Decoupled Architecture)**:
  1. **พยากรณ์แยกรายสินทรัพย์ (Asset-Level Forecasting)**: โมเดลทำนายความผันผวนจริงล่วงหน้า 5 วันทำการ (5-Day Forward Realized Volatility: $\hat{\sigma}_{\text{SPY},t}, \hat{\sigma}_{\text{IEF},t}, \hat{\sigma}_{\text{GLD},t}$) ของแต่ละสินทรัพย์แยกกัน
  2. **คำนวณความเสี่ยงพอร์ตในขั้น Downstream**: นำค่าความผันผวนที่พยากรณ์ได้ มาประกอบกับ **สหสัมพันธ์ย้อนหลัง 20 วัน (Historical Correlation Proxy)** และ **น้ำหนักพอร์ตที่ผู้ใช้กำหนด** (ค่าเริ่มต้นสาธิต **`50/30/20`**)
  3. **ปรับน้ำหนักได้โดยไม่ต้องฝึกโมเดลใหม่**: เมื่อผู้ใช้เปลี่ยนสัดส่วนน้ำหนักพอร์ต ระบบสามารถคำนวณความเสี่ยงพอร์ตโฟลิโอใหม่ได้ทันทีจากผลพยากรณ์ที่มีอยู่

---

## 2. สถานะปัจจุบันและพัฒนาการของการออกแบบ (Current Status & Key Decisions)

### 2.1 สถานะปัจจุบันของโปรเจกต์
- **สิ่งที่ทำเสร็จแล้ว**:
  1. กำหนดและสอบทานสัญญาข้อมูลครบทั้ง 4 ฉบับใน `docs/contract/` ได้แก่ [data_contract.md](./contract/data_contract.md), [datadict.md](./contract/datadict.md), [feature_contract.md](./contract/feature_contract.md) และ [target_contract.md](./contract/target_contract.md) พร้อมจัดเตรียมโครงสร้างโฟลเดอร์ตั้งต้น (`config/`, `data/`, `logs/`, `src/`)
  2. **พัฒนา Data Ingestion Pipeline (`src/ingestion/`) เสร็จสมบูรณ์**: ครอบคลุมตั้งแต่การอ่านตั้งค่าจาก `config/ingestion.yaml`, คำนวณปฏิทินวันซื้อขายรวมช่วง Warm-up, ดึงข้อมูลแยกรายสินทรัพย์จาก `yfinance` พร้อมระบบ Retry, เก็บ Raw Snapshot แบบไม่เขียนทับ, แปลงข้อมูลเป็น Schema มาตรฐาน, ตรวจสอบความถูกต้องและคัดแยกข้อมูลเข้า Quarantine, อัปเดตตารางหลัก `market_prices_daily.parquet` แบบ Atomic Upsert, สร้างรายงาน Audit อัตโนมัติ ไปจนถึงตัวตั้งเวลารันหลังตลาดปิด (`scheduler.py`) และชุดทดสอบ (`test_ingestion.py`)
- **ขั้นตอนถัดไป**: พัฒนา Feature Pipeline (`asset_volatility_features`), Rolling Correlation Pipeline (`asset_rolling_correlations`) และ Target/Label Pipeline (`asset_volatility_labels`) ต่อจากตาราง `market_prices_daily`

### 2.2 จุดสำคัญที่ได้ปรับปรุงและล็อกสเปกจากช่วงออกแบบ Contract
1. **ปรับระดับหน่วยข้อมูล (Grain) เป็น `(date, ticker)` ทั้งระบบ**: เปลี่ยนจากการผูก Feature/Target เข้ากับพอร์ตน้ำหนักคงที่ (Equal Weight) มาเป็นระดับรายสินทรัพย์ เพื่อให้เปลี่ยนน้ำหนักพอร์ตได้อิสระ
2. **ล็อกมาตรฐานราคาและช่วงเวลา**: ดึงข้อมูลจาก `yfinance` ด้วย `auto_adjust=True` แล้วแปลงเป็นคอลัมน์มาตรฐาน `adjusted_close` ช่วงวิเคราะห์ตั้งต้นคือ `2021-09-27` ถึง `2026-09-25` (ดึงเผื่อช่วง Warm-up ล่วงหน้าอย่างน้อย 61 วันทำการ)
3. **แยกบทบาทของ Return**: ใช้ **Log Return** เป็นฐานคำนวณ Realized Volatility ทั้งใน Feature และ Target ส่วน **Simple Return** ใช้ตรวจค่ากระโดดผิดปกติ ($\pm 20\%$) และคำนวณผลตอบแทนพอร์ตย้อนหลัง
4. **แยก Data Dictionary เป็นแหล่งอ้างอิงกลาง**: รวมคำอธิบายคอลัมน์ ชนิดข้อมูล และเงื่อนไขค่าว่างไว้ที่ `datadict.md` ที่เดียว เพื่อลดความซ้ำซ้อนและป้องกัน Schema ขัดแย้งกัน

---

## 3. แผนภาพและตารางสรุปการไหลของข้อมูล (Data Lineage & Tables)

```mermaid
flowchart LR
    YF["Yahoo Finance<br>(yfinance)"] --> MPD["1. market_prices_daily<br>PK: (date, ticker)"]
    MPD --> AVF["2. asset_volatility_features<br>PK: (date, ticker)"]
    MPD --> ARC["3. asset_rolling_correlations<br>PK: (date)"]
    MPD --> AVL["4. asset_volatility_labels<br>PK: (date, ticker)"]
    
    AVF & AVL --> TRAIN["ฝึกและประเมินโมเดลรายสินทรัพย์"]
    AVF --> PRED["พยากรณ์ความผันผวน 5 วัน<br>(SPY, IEF, GLD)"]
    TRAIN -.-> PRED
    PRED & ARC --> PORT["คำนวณความเสี่ยงพอร์ตโฟลิโอ<br>(รวมกับน้ำหนัก w เช่น 50/30/20)"]
```

| ตาราง / ขั้นตอน | รับข้อมูลจาก | Grain & Primary Key | ข้อมูลสำคัญในตาราง | ส่งต่อไปที่ |
| :--- | :--- | :--- | :--- | :--- |
| **1. `market_prices_daily`** | Yahoo Finance (`yfinance`) | 1 สินทรัพย์ ต่อ 1 วันซื้อขาย<br>**PK**: `(date, ticker)` | `adjusted_close`, `simple_return`, `log_return`, `is_anomaly_flagged` | Feature, Correlation และ Target Pipeline |
| **2. `asset_volatility_features`** | `market_prices_daily` (ข้อมูลถึงวัน $t$) | 1 สินทรัพย์ ณ สิ้นวัน $t$<br>**PK**: `(date, ticker)` | **Core 8 ตัว**: `ret_1d_t`, `ret_lag_1d`, `ret_lag_2d`, `ret_trailing_5d`, `ret_trailing_20d`, `rv_5d`, `rv_20d`, `rv_60d`<br>**Experimental**: `rsi_14d`, `bb_width_20d`<br>**Status**: `is_model_ready`, `is_warmup_buffer` | ฝึกโมเดล (Join กับ Labels) และทำนายผล ณ วันปัจจุบัน (Inference) |
| **3. `asset_rolling_correlations`** | `market_prices_daily` (`log_return` 20 วันล่าสุด) | 1 วันซื้อขาย ณ สิ้นวัน $t$<br>**PK**: `(date)` | `corr_spy_ief_20d`, `corr_spy_gld_20d`, `corr_ief_gld_20d` (Historical Proxy), `is_corr_ready` | ขั้นตอนคำนวณความเสี่ยงพอร์ตโฟลิโอ (Downstream) |
| **4. `asset_volatility_labels`** | `market_prices_daily` (ข้อมูลอนาคต $t+1$ ถึง $t+5$) | 1 สินทรัพย์ ณ วันอ้างอิง $t$<br>**PK**: `(date, ticker)` | `target_realized_vol_5d` (Target $y$), `target_obs_count`, `is_label_mature` | ฝึกและวัดผลโมเดล Machine Learning |
| **5. Portfolio Risk (Downstream)** | ค่าพยากรณ์ $\hat{\sigma}_{i,t}$ + ตาราง Correlation + น้ำหนัก $\mathbf{w}$ | 1 วันซื้อขาย ต่อชุดน้ำหนักพอร์ต | เมทริกซ์ความแปรปรวนร่วม $\hat{\boldsymbol{\Sigma}}_t$ และความผันผวนพอร์ต $\hat{\sigma}_{p,t}$ | รายงานผลและหน้า Dashboard |

---

## 4. สูตรคำนวณและกติกาสำคัญสำหรับนำเสนอ (Key Formulas & Rules)

### 4.1 สูตรคำนวณหลัก
1. **ผลตอบแทนรายวัน (Daily Returns)**:
   $$R_{i,t} = \frac{P_{i,t}^{\text{adj}}}{P_{i,t-1}^{\text{adj}}} - 1 \quad (\text{Simple Return}), \qquad r_{i,t} = \ln\left(\frac{P_{i,t}^{\text{adj}}}{P_{i,t-1}^{\text{adj}}}\right) \quad (\text{Log Return})$$
2. **ความผันผวนจริงย้อนหลัง (Historical RV Features — `rv_5d`, `rv_20d`, `rv_60d`)**:
   $$RV_{i,n,t} = \sqrt{\frac{252}{n} \sum_{j=0}^{n-1} r_{i,t-j}^{2}} \quad (\text{หน่วย: Annualized Decimal บนฐาน 252 วันทำการ})$$
3. **ความผันผวนจริงล่วงหน้า 5 วัน (Target — `target_realized_vol_5d`)**:
   $$y_{i,t} = \sqrt{\frac{252}{5} \sum_{k=1}^{5} r_{i,t+k}^{2}} \quad (\text{ใช้ผลตอบแทนอนาคต } t+1 \text{ ถึง } t+5 \text{ เท่านั้น})$$
4. **การรวมความผันผวนของพอร์ตโฟลิโอ (Downstream Portfolio Volatility)**:
   $$\hat{\sigma}_{p,t} = \sqrt{\mathbf{w}^\top \hat{\boldsymbol{\Sigma}}_t \mathbf{w}} = \sqrt{\sum_{i} w_i^2 \hat{\sigma}_{i,t}^2 + 2 \sum_{i < j} w_i w_j \hat{\sigma}_{i,t} \hat{\sigma}_{j,t} \rho_{ij,t}}$$

---

### 4.2 กฎการตรวจสอบคุณภาพและการป้องกัน Data Leakage
- **Point-in-Time & Purge Gap**: Feature ณ วัน $t$ ใช้ข้อมูลได้ไม่เกินสิ้นวัน $t$ การแบ่งชุดข้อมูล Train/Validation/Test ต้องเรียงตามเวลาและเว้นระยะ **Purge Gap อย่างน้อย 5 วันทำการ** เพื่อไม่ให้ช่วงเวลาของ Target ซ้อนทับกัน และต้อง `.fit()` ตัวปรับสเกล (Scaler) บนชุด Train เท่านั้น
- **การจัดการข้อมูลขาดหายและค่าผิดปกติ**:
  - ตรวจสอบวันซื้อขายเทียบกับปฏิทินตลาดสหรัฐฯ (NYSE/NASDAQ) **ห้ามทำ Forward-fill ข้ามวันโดยพลการ**
  - หากราคาเปลี่ยนแปลงเกิน $\pm 20\%$ ในวันเดียว (`abs(simple_return) > 0.20`) จะติดธงเตือน `is_anomaly_flagged = True` เพื่อตรวจสอบโดยไม่ตัดข้อมูลทิ้งทันที
  - ค่าว่างในช่วงเริ่มต้นที่ข้อมูลยังไม่ครบหน้าต่าง (เช่น 60 วันแรกของ `rv_60d`) ถือเป็น **Warm-up Null** ตามธรรมชาติ ห้ามเติม `0`
- **การแยกผลกระทบเมื่อข้อมูลมีปัญหา (Per-Ticker vs. Portfolio Policy)**:
  - **ระดับรายสินทรัพย์**: หากสินทรัพย์ใดไม่ผ่าน Validation จะถูกแยกเข้า Quarantine และหยุดเฉพาะสินทรัพย์นั้น ส่วนสินทรัพย์อื่นที่ผ่านเกณฑ์ยังสร้างคำพยากรณ์รายตัว ($\hat{\sigma}_{i,t}$) ได้ตามปกติ
  - **ระดับพอร์ตโฟลิโอ**: ต้องมีคำพยากรณ์ครบทั้ง 3 สินทรัพย์ และเมทริกซ์สหสัมพันธ์ต้องพร้อมใช้ (`is_corr_ready == True` คือคำนวณจาก 20 วันชุดเดียวกันและเป็น Symmetric & Positive Semidefinite) หากขาดตัวใดตัวหนึ่ง **ระบบจะระงับการคำนวณพอร์ต (`portfolio_vol = Null`, `status = 'INCOMPLETE_INPUTS'`) และแจ้งเตือนบน Dashboard โดยไม่แอบคำนวณจากสินทรัพย์ที่เหลือเพียงบางส่วน**

---

## 5. รายละเอียด Data Ingestion Pipeline ที่พัฒนาเพิ่ม (`src/ingestion/`)

ส่วนงานดึงและเตรียมข้อมูลราคาตลาดรายวัน (`market_prices_daily`) ได้ถูกพัฒนาเป็นโมดูลครบวงจรภายใต้ `src/ingestion/` โดยควบคุมผ่านไฟล์ตั้งค่า [`config/ingestion.yaml`](../config/ingestion.yaml) และปฏิบัติตามข้อกำหนดใน `data_contract.md` อย่างเคร่งครัด

### 5.1 แผนภาพลำดับการทำงานของ Ingestion Pipeline (Execution Flow)

```mermaid
flowchart TD
    SCHED["scheduler.py<br>ตรวจวันเปิดตลาด XNYS<br>& รอหลังตลาดปิด + Buffer 30 นาที"] --> RUN["run.py<br>Orchestrator หลัก"]
    CFG["config.py<br>โหลดและตรวจ config/ingestion.yaml"] --> RUN
    CAL["calendar.py<br>คำนวณวันเริ่มดึงรวม Warm-up 61 วัน<br>& รายการวันซื้อขายที่คาดหวัง"] --> RUN
    META_START["run_metadata.py (start_run)<br>ออก run_id, source_batch_id<br>บันทึกสถานะ RUNNING"] --> FETCH["fetch.py<br>ดึงข้อมูล yfinance แยกราย Ticker<br>พร้อม Retry แบบ Exponential Backoff"]
    RUN --> META_START
    FETCH --> RAW["raw_storage.py<br>บันทึก Raw Parquet + SHA-256<br>(ห้ามเขียนทับ run เดิม)"]
    RAW --> TF["transform.py<br>แปลงเวลาเป็น America/New_York<br>คำนวณ Simple/Log Return & Flags"]
    TF --> VAL["validate.py<br>ตรวจ Schema, ราคา > 0, PK ซ้ำ,<br>วันซื้อขายขาดหาย และ Return Anomaly"]
    VAL --> QUAR["quarantine.py<br>แยก Ticker ที่ไม่ผ่านเข้า Quarantine<br>และคัดเฉพาะ Ticker ที่ผ่านไป Validated"]
    QUAR --> PUB["publish.py<br>Atomic Upsert ลงตารางหลัก<br>market_prices_daily.parquet"]
    PUB --> META_END["run_metadata.py (finish_run)<br>& audit_report.py<br>สรุปสถานะและสร้างรายงาน JSON/MD"]
```

### 5.2 ตารางสรุปหน้าที่ของแต่ละโมดูลใน `src/ingestion/`

| โมดูล | ฟังก์ชันหลัก | หน้าที่และกลไกสำคัญ |
| :--- | :--- | :--- |
| **`config.py`** | `load_config()`, `validate_config()` | โหลดไฟล์ `config/ingestion.yaml` และตรวจสอบความถูกต้องของพารามิเตอร์ทั้งหมด (เช่น ต้องมีครบ `SPY`, `IEF`, `GLD`, `interval == '1d'`, `auto_adjust == True`, `warmup_trading_days > 0`, Timezone ถูกต้อง) |
| **`calendar.py`** | `build_ingestion_window()`, `get_effective_end_date()` | ใช้ `pandas_market_calendars` (ตลาด `XNYS`) ถอยหลังหาวันเริ่มดึงจริง (`actual_fetch_start_date`) ให้ครอบคลุมช่วง Warm-up 61 วันทำการก่อน `start_date` พร้อมคำนวณ `effective_end_date` ไม่ให้เกินวันซื้อขายล่าสุดที่ตลาดปิดจริง และบวก `api_end_date` เพิ่ม 1 วันสำหรับ yfinance |
| **`run_metadata.py`** | `start_run()`, `finish_run()` | สร้าง `run_id` (`run_YYYYMMDD_HHMMSS_<hex>`) และ `source_batch_id` เก็บเลข Git Commit และเวอร์ชันไลบรารี บันทึกไฟล์ลง `data/audit/<run_id>/run_metadata.json` |
| **`fetch.py`** | `fetch_ticker()`, `fetch_all()` | ดึงข้อมูลจาก `yfinance` แยกทีละสินทรัพย์ (`auto_adjust=True`, `actions=False`, `repair=False`, `keepna=True`) ตรวจคอลัมน์ราคา `Close`, `High`, `Low` หากเกิดข้อผิดพลาดเครือข่ายจะลองใหม่สูงสุด `max_attempts` ครั้งด้วย Exponential Backoff |
| **`raw_storage.py`** | `save_raw_snapshot()` | บันทึก DataFrame ดิบก่อนแปลงลง `data/raw/<source_batch_id>/raw_prices.csv` พร้อมสร้าง `manifest.json` เก็บค่าแฮช `SHA-256` และเวอร์ชัน `yfinance` ตาม Data Contract ข้อ 3 โดยไม่เขียนทับ Snapshot เดิม |
| **`transform.py`** | `transform_ticker()`, `transform_all()` | แปลง Index เป็นวันที่ตามโซนเวลา `America/New_York` แมป `Close`, `High`, `Low` เป็น Schema มาตรฐาน 12 คอลัมน์ คัดกรองวันที่ไม่เกิน `effective_end_date` คำนวณ `simple_return` และ `log_return` แยกรายสินทรัพย์ ติดธง `is_anomaly_flagged` และ `is_warmup_buffer` |
| **`validate.py`** | `validate_ticker()`, `validate_all()` | ตรวจความถูกต้องแยกรายสินทรัพย์: (1) คอลัมน์ครบ 12 ตัว (2) ราคา Finite และ $> 0$ (`NON_POSITIVE_PRICE`) (3) `low <= adjusted_close <= high` (`INVALID_HIGH_LOW`) (4) `is_warmup_buffer` ตรงกับวันก่อน `start_date` (`INVALID_WARMUP_FLAG`) (5) PK ไม่ซ้ำ (`DUPLICATE_PRIMARY_KEY`) (6) วันซื้อขายครบตาม `expected_trading_days` (7) Returns เป็น Null ได้เฉพาะแถวแรก |
| **`quarantine.py`** | `handle_quarantine_and_publish()` | บันทึกรายการที่ไม่ผ่าน Hard Fail ลงใน **`logs/quarantine.csv`** แบบ Append-only (7 คอลัมน์มาตรฐาน) พร้อมแยกเก็บ JSON per-run และคัดเฉพาะ Ticker ที่ผ่านไป Validated |
| **`publish.py`** | `publish_market_prices()` | นำเฉพาะสินทรัพย์ที่ได้สถานะ `PUBLISHED` มาทำ **Atomic Upsert** ลงตารางหลัก `data/curated/market_prices_daily.parquet` ตามคีย์ `(date, ticker)` นับจำนวนแถวที่ `inserted`, `updated`, และ `unchanged` |
| **`audit_report.py`** | `create_run_report()` | รวบรวมสถิติทุกขั้นตอน สร้างรายงาน JSON/MD และบันทึกผลการรัน 1 บรรทัดลงใน **`logs/ingestion_runs.jsonl`** แบบ Append-only ตาม Data Contract ข้อ 7 |
| **`scheduler.py`** | `run_after_market_close()` | ตรวจสอบวันเปิดทำการของตลาด `XNYS` และรอจนกว่าจะเลยเวลาปิดตลาดตามจริงบวกระยะ Buffer ก่อนสั่งรัน Ingestion |
| **`test_ingestion.py`** | ชุดทดสอบ `pytest` | ทดสอบครอบคลุมการคำนวณ Warm-up และ `effective_end_date`, การดักจับ Schema/ราคา/High-Low/Warmup Flag, การเขียน Quarantine CSV และ Audit JSONL |

### 5.3 โครงสร้างการจัดเก็บข้อมูลและผลลัพธ์ (Storage Layout)

| โฟลเดอร์ / ไฟล์ปลายทาง | รูปแบบไฟล์ | คำอธิบาย |
| :--- | :--- | :--- |
| `data/raw/<source_batch_id>/` | `raw_prices.csv`, `manifest.json` | ข้อมูลดิบรวมทุก Ticker พร้อม Manifest และค่าแฮช `SHA-256` ตาม Data Contract ข้อ 3 |
| `logs/quarantine.csv` | `CSV` (Append-only) | ไฟล์บันทึกข้อมูล/เหตุการณ์ที่ไม่ผ่าน Hard Validation พร้อม `run_id`, `source_batch_id`, `reason` |
| `logs/ingestion_runs.jsonl` | `JSONL` (Append-only) | บันทึกประวัติและสถิติจำนวนแถวของการรันทุกรอบ 1 Run ต่อ 1 บรรทัด JSON Object |
| `data/validated/run_id=<run_id>/` | `ticker=<T>/data.parquet` | ข้อมูลรายสินทรัพย์ที่ผ่านการตรวจสอบในรอบรันนั้นและได้รับอนุญาตให้เผยแพร่ (`PUBLISHED`) |
| `data/curated/market_prices_daily.parquet` | `Parquet` (ตารางหลัก) | ตารางราคาตลาดมาตรฐาน 12 คอลัมน์ที่ผ่านการ Upsert สะสมพร้อมส่งต่อให้ Feature และ Target Pipeline |
| `data/audit/<run_id>/` และ `data/audit/run_id=<run_id>/` | `run_metadata.json`, `publish_report.json`, `run_report.json`, `run_report.md` | รายงานสรุปผลการรันและสถิติจำนวนแถวประจำรอบ |
| `data/audit/scheduler/` | `<YYYY-MM-DD>.json` | บันทึกประวัติการตรวจสอบเวลาเปิด-ปิดตลาดของ `scheduler.py` |

### 5.4 สถานะการรันและรหัสคืนค่า (Overall Status & Exit Codes)

ใน `run.py` ระบบจะสรุปสถานะรวมและคืนค่า Exit Code เพื่อให้ระบบตั้งเวลาหรือ CI/CD ตรวจสอบได้ทันที:
- **`SUCCESS` (Exit Code `0`)**: สินทรัพย์ทั้ง 3 ตัว (`SPY`, `IEF`, `GLD`) ผ่านการตรวจสอบและถูกอัปเดตลงตารางหลักครบถ้วน (`portfolio_ready = True`)
- **`PARTIAL_SUCCESS` (Exit Code `2`)**: มีสินทรัพย์บางตัวผ่านและถูกอัปเดตลงตารางหลัก แต่มีบางตัวถูกบล็อกเข้า Quarantine (`portfolio_ready = False`)
- **`FAILED` (Exit Code `1`)**: สินทรัพย์ทั้งหมดไม่ผ่านการตรวจสอบ หรือเกิดข้อผิดพลาดระดับระบบ/การตั้งค่า (`portfolio_ready = False`)

### 5.5 คำสั่งสำหรับใช้งานและทดสอบ (CLI Usage)

```bash
# รัน Ingestion Pipeline ตามไฟล์ตั้งค่า
python -m src.ingestion.run --config config/ingestion.yaml

# รันผ่านตัวเช็คเวลาปิดตลาด (รอหลังตลาด XNYS ปิด 30 นาที)
python -m src.ingestion.scheduler --config config/ingestion.yaml --buffer-minutes 30

# รันชุดทดสอบ Unit Tests ของ Ingestion Pipeline
pytest src/ingestion/test_ingestion.py
```
