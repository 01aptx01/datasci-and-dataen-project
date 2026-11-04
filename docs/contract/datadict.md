# Data Dictionary — Adaptive Portfolio Risk Lab

**Document:** `contracts/datadict.md`  
**Scope:** 5 Logical Tables ของ SPY, IEF, GLD

**Data Dictionary** คือแหล่งอ้างอิงกลาง (Single Source of Truth) ของชื่อคอลัมน์ ชนิดข้อมูล หน่วย ความหมาย หน้าที่ (`Role`) กติกา `NULL` และคีย์ข้อมูล ส่วนรายละเอียดการคำนวณและการตรวจสอบให้ดู Contract ของขั้นตอนที่รับผิดชอบ

> **ขอบเขตที่เคาะแล้ว:** มี **5 ตารางหลักเท่านั้น** ส่วน `logs/quarantine.csv`, `logs/ingestion_runs.jsonl`, Raw Snapshots และ `outputs/evaluation.csv` เป็น **ไฟล์ประกอบ** ไม่ใช่ตารางหลักของระบบ และไม่เพิ่มตาราง `prediction_evaluations`

## เอกสารที่เกี่ยวข้อง

- [README.md](./README.md) — ภาพรวม 5 ตารางและการไหลของข้อมูล
- [data_contract.md](./data_contract.md) — Ingestion, Prices, Raw Snapshot, Quality, Quarantine และ Audit
- [feature_contract.md](./feature_contract.md) — Features, Lookback, Correlation และ Time Cut-off
- [target_contract.md](./target_contract.md) — Target 5 วันและ Portfolio Risk
- [prediction_contract.md](./prediction_contract.md) — ข้อมูลก่อน/หลังทำนายและการเก็บผลพยากรณ์

## สรุป 5 ตารางหลัก

| # | Table | Grain (1 แถว) | Key | ใช้เพื่อ |
|---|---|---|---|---|
| 1 | `market_prices_daily` | ราคา 1 ticker × 1 วันซื้อขาย | `(date, ticker)` | ราคาที่ผ่าน Validation + Returns |
| 2 | `asset_volatility_features` | Features 1 ticker ณ วัน `t` | `(date, ticker)` | ข้อมูลอดีตสำหรับ ML |
| 3 | `asset_volatility_labels` | Target 1 ticker ณ วันทำนาย `t` | `(date, ticker)` | คำตอบจริงเมื่อครบ 5 วันซื้อขาย |
| 4 | `asset_rolling_correlations` | Correlation ของทั้ง 3 ETF ณ วัน `t` | `date` | คำนวณความเสี่ยงพอร์ต |
| 5 | `asset_volatility_predictions` | คำทำนาย 1 ticker × 1 วิธี × 1 วัน × 1 ชุด Input/Model | `prediction_id` | Forecast สำหรับ Dashboard/Evaluation |

### มาตรฐานร่วม

- `date` / `prediction_date` คือวันที่ซื้อขายตาม **`America/New_York`** ชนิด `DATE` (`YYYY-MM-DD`); ไม่ใช่ Timestamp UTC
- ฟิลด์ที่ลงท้าย `_utc` เป็น `TIMESTAMPTZ` และบันทึกเป็นเวลา **UTC** แบบ ISO-8601 เช่น `2026-09-25T21:05:12Z`
- `ticker` รับเฉพาะ `SPY`, `IEF`, `GLD`; ทุกค่า Volatility เป็น **annualized decimal** เช่น `0.18` = 18% ต่อปี (ประมาณจากช่วง 5 วันสำหรับ Target/Prediction)
- `run_id` คือรหัสการประมวลผลที่สร้างแถวนั้น; `source_batch_id` ระบุ Raw Snapshot ต้นทางของแถวอ้างอิง และ **ไม่ถือว่า Rolling/Forward Window ใช้ Source Batch เดียวเสมอไป** หากมีหลาย Batch ให้บันทึกรายการ Input Sources ใน Manifest ที่ผูกกับ `run_id`
- แถวในช่วงก่อน `config.start_date` เป็น Warm-up (`is_warmup_buffer=True`) ใช้คำนวณ Rolling Features แต่ไม่เป็นตัวอย่างฝึก/วัดผล; ให้ใช้ Config เดียวกันระหว่าง Price และ Feature Table
- `VARCHAR`, `FLOAT`, `BOOLEAN`, `DATE`, `TIMESTAMPTZ` เป็น **ชนิดข้อมูลเชิงตรรกะ**; หากเก็บ CSV/Parquet ให้แปลงและตรวจชนิดตามนี้เมื่ออ่าน/เขียน

---

## 1. ตารางข้อมูลราคาตลาดและผลตอบแทนรายสินทรัพย์ (`market_prices_daily`)

ตารางผลลัพธ์จากกระบวนการ Data Ingestion & Initial Transformation ตามที่กำหนดใน [data_contract.md](./data_contract.md)
- **ระดับหน่วยข้อมูล (Grain)**: 1 แถว แทนข้อมูลราคาและผลตอบแทนของ 1 สินทรัพย์ (`ticker`) ณ 1 วันซื้อขาย (`date`)
- **Primary Key**: `(date, ticker)`
- **Mapping ราคา:** `adjusted_close`, `high` และ `low` มาจาก `Close`, `High`, `Low` ของ `yfinance` ในโหมด `auto_adjust=True` เดียวกัน; ผลตอบแทนและ Features/Targets หลักยังคำนวณจาก `adjusted_close` เท่านั้น
- **สถานะ Warm-up:** `is_warmup_buffer` ของตารางนี้คำนวณจาก `date < config.start_date` และต้องสอดคล้องกับคอลัมน์ชื่อเดียวกันใน `asset_volatility_features`

| Table | Column | Type | Unit / Format | Meaning & Example | Role | Nullable |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `market_prices_daily` | `date` | `DATE` | `YYYY-MM-DD` | วันเปิดทำการซื้อขายของตลาดหลักทรัพย์สหรัฐฯ (NYSE/NASDAQ) ณ วัน $t$ (เช่น `'2024-03-15'`) | Primary Key | No |
| `market_prices_daily` | `ticker` | `VARCHAR(16)` | uppercase string | รหัสหลักทรัพย์ (`'SPY'`, `'IEF'`, `'GLD'`) | Primary Key | No |
| `market_prices_daily` | `adjusted_close` | `FLOAT` | USD | ราคาปิดที่ปรับปรุง Corporate Actions (ปันผล, แตกพาร์) จากคอลัมน์ `Close` ของ `yfinance` เมื่อตั้ง `auto_adjust=True` (เช่น `510.25`) | Price Input | No |
| `market_prices_daily` | `high` | `FLOAT` | USD | ราคาสูงสุดรายวันที่ได้จาก `High` ของ `yfinance` ในโหมด `auto_adjust=True` จึงอยู่บนฐานปรับราคาเดียวกับ `adjusted_close`; ต้อง `high >= adjusted_close` (เผื่อ Floating-point tolerance) | Price / Quality Input | No |
| `market_prices_daily` | `low` | `FLOAT` | USD | ราคาต่ำสุดรายวันที่ได้จาก `Low` ของ `yfinance` ในโหมด `auto_adjust=True` จึงอยู่บนฐานปรับราคาเดียวกับ `adjusted_close`; ต้อง `low <= adjusted_close` (เผื่อ Floating-point tolerance) | Price / Quality Input | No |
| `market_prices_daily` | `simple_return` | `FLOAT` | decimal ratio | ผลตอบแทนรายวันแบบธรรมดาของสินทรัพย์ $i$: $R_{i,t} = (P_{i,t}^{\text{adj}} / P_{i,t-1}^{\text{adj}}) - 1$ | Derived Metric | Yes (1st row per `ticker`) |
| `market_prices_daily` | `log_return` | `FLOAT` | log ratio | ผลตอบแทนรายวันแบบลอการิทึมของสินทรัพย์ $i$: $r_{i,t} = \ln(P_{i,t}^{\text{adj}} / P_{i,t-1}^{\text{adj}})$ | Derived Metric | Yes (1st row per `ticker`) |
| `market_prices_daily` | `is_anomaly_flagged` | `BOOLEAN` | boolean flag | ธงแจ้งเตือนเมื่อ `abs(simple_return) > 0.20` (เปลี่ยนแปลงเกิน $\pm 20\%$ ใน 1 วัน) เพื่อส่งตรวจสอบโดยไม่ตัดแถวทิ้งอัตโนมัติ | Audit / Quality Flag | No |
| `market_prices_daily` | `is_warmup_buffer` | `BOOLEAN` | boolean flag | `True` ถ้าวันซื้อขายนี้อยู่ก่อน `config.start_date` (`date < config.start_date`); ให้ Downstream ใช้คำนวณ Rolling Features แต่ไม่รวมเป็นตัวอย่างฝึกหรือวัดผลตาม Feature Contract | Status (Filter only, not in $X$) | No |
| `market_prices_daily` | `run_id` | `VARCHAR(64)` | UUID / run string | รหัสการรัน Ingestion Pipeline ที่สร้างแถวข้อมูลนี้ ใช้เชื่อมโยงกลับไปยังพารามิเตอร์ `start_date`, `end_date` ใน Run Metadata (เช่น `'ing_20260925_001'`) | Metadata / Lineage | No |
| `market_prices_daily` | `source_batch_id` | `VARCHAR(64)` | batch identifier | รหัสชุดข้อมูลต้นทางจากการดึง `yfinance` ในรอบนั้น (เช่น `'yf_batch_20260925'`) | Metadata / Lineage | No |
| `market_prices_daily` | `ingested_at_utc` | `TIMESTAMPTZ` | ISO-8601 UTC (`YYYY-MM-DDTHH:MM:SSZ`) | วันและเวลาในเขตเวลา UTC ที่ดึงและตรวจสอบแถวข้อมูลสำเร็จ (เช่น `'2026-09-25T21:05:12Z'`) | Metadata / Audit | No |

---

## 2. ตาราง Feature สำหรับทำนายความผันผวนรายสินทรัพย์ (`asset_volatility_features`)

ตารางผลลัพธ์หลักจากกระบวนการ Feature Engineering ตามที่กำหนดใน [feature_contract.md](./feature_contract.md) สำหรับใช้เป็นตัวแปรต้น ($X$) ของโมเดลพยากรณ์ความผันผวนรายสินทรัพย์ (แทนที่ตาราง `portfolio_volatility_features` เดิมที่ผูกติดกับพอร์ต Equal Weight)
- **ระดับหน่วยข้อมูล (Grain)**: 1 แถว แทนชุดตัวแปรต้นของ 1 สินทรัพย์ (`ticker`) ณ สิ้นวันซื้อขาย `date` ($t$) หลังตลาดปิดและตรวจสอบข้อมูลเสร็จสมบูรณ์
- **Primary Key**: `(date, ticker)`

### 2.1 คอลัมน์คีย์หลักและผลตอบแทนย้อนหลังรายสินทรัพย์ (Keys & Asset Return Features)

| Table | Column | Type | Unit / Format | Meaning | Role | Nullable |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `asset_volatility_features` | `date` | `DATE` | `YYYY-MM-DD` | วันซื้อขายที่เป็นจุดอ้างอิง ณ สิ้นวัน $t$ | Primary Key | No |
| `asset_volatility_features` | `ticker` | `VARCHAR(16)` | uppercase string | รหัสหลักทรัพย์ของแถวนั้น (`'SPY'`, `'IEF'`, `'GLD'`) | Primary Key | No |
| `asset_volatility_features` | `ret_1d_t` | `FLOAT` | log ratio | ผลตอบแทนลอการิทึมรายวันของสินทรัพย์ `ticker` ณ วัน $t$: $r_{i,t} = \ln(P_{i,t}^{\text{adj}} / P_{i,t-1}^{\text{adj}})$ | Core Feature | Yes during warm-up (1st row per `ticker`) |
| `asset_volatility_features` | `ret_lag_1d` | `FLOAT` | log ratio | ผลตอบแทนลอการิทึมของสินทรัพย์ `ticker` ย้อนหลัง 1 วันทำการ ($r_{i,t-1}$) | Core Feature | Yes during warm-up (first 2 rows per `ticker`) |
| `asset_volatility_features` | `ret_lag_2d` | `FLOAT` | log ratio | ผลตอบแทนลอการิทึมของสินทรัพย์ `ticker` ย้อนหลัง 2 วันทำการ ($r_{i,t-2}$) | Core Feature | Yes during warm-up (first 3 rows per `ticker`) |
| `asset_volatility_features` | `ret_trailing_5d` | `FLOAT` | decimal ratio | ผลตอบแทนสะสมย้อนหลัง 5 วันทำการ สิ้นสุดที่วัน $t$ ของสินทรัพย์ `ticker`: $(P_{i,t}^{\text{adj}} / P_{i,t-5}^{\text{adj}}) - 1$ | Core Feature | Yes during warm-up (first 5 returns per `ticker`) |
| `asset_volatility_features` | `ret_trailing_20d` | `FLOAT` | decimal ratio | ผลตอบแทนสะสมย้อนหลัง 20 วันทำการ สิ้นสุดที่วัน $t$ ของสินทรัพย์ `ticker`: $(P_{i,t}^{\text{adj}} / P_{i,t-20}^{\text{adj}}) - 1$ | Core Feature | Yes during warm-up (first 20 returns per `ticker`) |

### 2.2 คอลัมน์ความผันผวนย้อนหลังรายสินทรัพย์ (Asset Historical Realized Volatility Features)

| Table | Column | Type | Unit / Format | Meaning | Role | Nullable |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `asset_volatility_features` | `rv_5d` | `FLOAT` | annualized decimal | ความผันผวนจริงย้อนหลัง 5 วันทำการ (รวมวัน $t$) ของสินทรัพย์ `ticker`: $\sqrt{\frac{252}{5}\sum_{j=0}^{4} r_{i,t-j}^2}$ | Core Feature | Yes during warm-up (first 5 returns per `ticker`) |
| `asset_volatility_features` | `rv_20d` | `FLOAT` | annualized decimal | ความผันผวนจริงย้อนหลัง 20 วันทำการ (รวมวัน $t$) ของสินทรัพย์ `ticker`: $\sqrt{\frac{252}{20}\sum_{j=0}^{19} r_{i,t-j}^2}$ | Core Feature | Yes during warm-up (first 20 returns per `ticker`) |
| `asset_volatility_features` | `rv_60d` | `FLOAT` | annualized decimal | ความผันผวนจริงย้อนหลัง 60 วันทำการ (รวมวัน $t$) ของสินทรัพย์ `ticker`: $\sqrt{\frac{252}{60}\sum_{j=0}^{59} r_{i,t-j}^2}$ | Core Feature | Yes during warm-up (first 60 returns per `ticker`) |

### 2.3 คอลัมน์ตัวชี้วัดทางเทคนิครายสินทรัพย์สำหรับการทดลอง (Experimental Features)

> **ข้อกำหนดการสร้าง Experimental Features**: คำนวณด้วยสูตรมาตรฐานเดียวกันให้ครบทั้ง 3 สินทรัพย์ (`SPY`, `IEF`, `GLD`) ตามคีย์ `(date, ticker)` เพื่อไม่ให้โครงสร้างตารางจำกัดอยู่เฉพาะ `SPY` ตัวเดียว โดยในการทดลองโมเดลสามารถเลือกเปิดใช้เป็นราย `ticker` หรือทุก `ticker` เพื่อเปรียบเทียบกับชุด Core Features (8 ตัว)

| Table | Column | Type | Unit / Format | Meaning | Role | Nullable |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `asset_volatility_features` | `rsi_14d` | `FLOAT` | index $[0, 100]$ | ดัชนี Relative Strength Index 14 วันทำการ (Wilder's Smoothing) คำนวณจาก `adjusted_close` ของสินทรัพย์ `ticker` นั้น ณ วัน $t$ | Experimental Feature | Yes during warm-up (first 14 returns per `ticker`) |
| `asset_volatility_features` | `bb_width_20d` | `FLOAT` | normalized ratio ($\ge 0$) | ความกว้างของ Bollinger Bands (20 วัน, $2\sigma$) หารด้วย $\text{SMA}_{20}$ คำนวณจาก `adjusted_close` ของสินทรัพย์ `ticker` นั้น ณ วัน $t$ | Experimental Feature | Yes during warm-up (first 20 prices per `ticker`) |

### 2.4 คอลัมน์สถานะและเมทาดาทาสำหรับตรวจสอบย้อนหลัง (Status & Lineage Metadata Columns)

| Table | Column | Type | Unit / Format | Meaning & Example | Role | Nullable |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `asset_volatility_features` | `is_model_ready` | `BOOLEAN` | boolean flag | ระบุว่าแถวข้อมูลของ `ticker` นั้นผ่านช่วง Warm-up และมี **Core Features ครบทั้ง 8 คอลัมน์** โดยไม่มี `Null` แล้ว (`True`/`False`) | Status (Filter only, not in $X$) | No |
| `asset_volatility_features` | `is_warmup_buffer` | `BOOLEAN` | boolean flag | ระบุว่าแถวข้อมูลนี้อยู่ในช่วงดึงเผื่อ Warm-up ก่อนวันเริ่มวิเคราะห์ (`date < config.start_date`) เพื่อป้องกันไม่ให้นำวัน Buffer เข้าสู่การวัดผลโมเดล | Status (Filter only, not in $X$) | No |
| `asset_volatility_features` | `feature_set_version` | `VARCHAR(16)` | semver | เวอร์ชันของสเปก Feature ที่ใช้คำนวณ (เช่น `'2.0.0'`) | Metadata | No |
| `asset_volatility_features` | `run_id` | `VARCHAR(64)` | UUID / run string | รหัสการสั่งรัน Feature Pipeline ในรอบนั้น (Pipeline Execution Run ID เช่น `'feat_run_20260925_001'`) เพื่ออ้างอิงกลับไปยัง Config ของการรัน | Metadata / Lineage | No |
| `asset_volatility_features` | `source_batch_id` | `VARCHAR(64)` | batch identifier | รหัส Raw Snapshot ของแถวราคา ณ `date` ที่เป็นจุดอ้างอิง; สำหรับ Rolling Features ที่อ่านข้อมูลจากหลาย Batch ต้องตรวจรายการแหล่งข้อมูลทั้งหมดจาก Input Manifest ที่ผูกกับ `run_id` (ไม่ถือว่า `source_batch_id` ตัวเดียวอธิบาย Rolling Window ทั้งหมด) | Metadata / Lineage | No |
| `asset_volatility_features` | `feature_as_of_utc` | `TIMESTAMPTZ` | ISO-8601 UTC (`YYYY-MM-DDTHH:MM:SSZ`) | วันและเวลา UTC ที่คำนวณและบันทึกแถว Feature สำเร็จ (เช่น `'2026-09-25T21:10:00Z'`) | Metadata / Audit | No |

---

## 3. ตารางตัวแปรตาม / เป้าหมายการทำนายรายสินทรัพย์ (`asset_volatility_labels`)

ตารางผลลัพธ์สำหรับการสร้าง Label/Target รายสินทรัพย์ ตามที่กำหนดใน [target_contract.md](./target_contract.md) (แทนที่ตาราง `portfolio_volatility_labels` เดิม)
- **ระดับหน่วยข้อมูล (Grain)**: 1 แถว แทนค่าความผันผวนจริงในช่วงอนาคต 5 วันทำการถัดจากวันอ้างอิง ($t+1$ ถึง $t+5$) ของสินทรัพย์ `ticker` ณ วันอ้างอิง `date` ($t$)
- **Primary Key**: `(date, ticker)`
- **Lifecycle:** แถวที่ยังไม่ครบ 5 วันซื้อขายคือ Pending (`is_label_mature=False`, `target_realized_vol_5d=NULL`, `label_matured_at_utc=NULL`); เมื่อผลจริงครบจึงเปลี่ยนเป็น Mature และบันทึกเวลาที่คำนวณเสร็จจริง
- **หน่วย Target:** `annualized decimal` จากสูตร $\sqrt{\frac{252}{5}\sum_{k=1}^{5}r_{i,t+k}^2}$ ตาม `target_contract.md`

| Table | Column | Type | Unit / Format | Meaning & Example | Role | Nullable |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `asset_volatility_labels` | `date` | `DATE` | `YYYY-MM-DD` | วันซื้อขายที่เป็นจุดอ้างอิง ณ วันทำนาย $t$ (ใช้ Join กับ `asset_volatility_features` ด้วย `(date, ticker)`) | Primary Key | No |
| `asset_volatility_labels` | `ticker` | `VARCHAR(16)` | uppercase string | รหัสหลักทรัพย์ (`'SPY'`, `'IEF'`, `'GLD'`) | Primary Key | No |
| `asset_volatility_labels` | `target_start_date` | `DATE` | `YYYY-MM-DD` | วันซื้อขายถัดไปวันแรกของหน้าต่างเป้าหมาย ($t+1$) ของสินทรัพย์ `ticker` | Target Metadata | Yes until $t+1$ exists |
| `asset_volatility_labels` | `target_end_date` | `DATE` | `YYYY-MM-DD` | วันซื้อขายลำดับที่ 5 หลังวันอ้างอิง ($t+5$) ของสินทรัพย์ `ticker` | Target Metadata | Yes until label matures ($t+5$) |
| `asset_volatility_labels` | `target_obs_count` | `INTEGER` | count $[0, 5]$ | จำนวนวันทำการในอนาคตที่มีข้อมูลผลตอบแทนจริงแล้วในช่วง $[t+1, t+5]$ (ต้องเท่ากับ `5` จึงจะสมบูรณ์) | Target Metadata | No |
| `asset_volatility_labels` | `target_realized_vol_5d` | `FLOAT` | annualized decimal | ความผันผวนจริง (Annualized Realized Volatility) ของสินทรัพย์ `ticker` จากผลตอบแทน 5 วันทำการถัดไป: $\sqrt{\frac{252}{5}\sum_{k=1}^{5} r_{i,t+k}^2}$ | Target ($y$) | Yes until label matures ($t+5$) |
| `asset_volatility_labels` | `is_label_mature` | `BOOLEAN` | boolean flag | ระบุว่ามีข้อมูลผลตอบแทนอนาคตของ `ticker` ครบทั้ง 5 วันทำการ ($t+1$ ถึง $t+5$) และคำนวณ `target_realized_vol_5d` สำเร็จแล้วหรือไม่ (`True`/`False`) | Status (Filter only, not in $X$) | No |
| `asset_volatility_labels` | `target_version` | `VARCHAR(16)` | semver | เวอร์ชันของสเปกการคำนวณ Target (เช่น `'2.0.0'`) | Metadata | No |
| `asset_volatility_labels` | `run_id` | `VARCHAR(64)` | UUID / run string | รหัสการสั่งรัน Target Pipeline ในรอบนั้น (Pipeline Execution Run ID เช่น `'lbl_run_20260925_001'`) | Metadata / Lineage | No |
| `asset_volatility_labels` | `source_batch_id` | `VARCHAR(64)` | batch identifier | รหัส Raw Snapshot ของแถวราคาวันอ้างอิง `t`; ผลตอบแทนในช่วง `t+1` ถึง `t+5` อาจมาจากหลาย Batch จึงต้องบันทึก Input Manifest ของการรันที่ผูกกับ `run_id` เพื่อไล่ย้อนครบถ้วน | Metadata / Lineage | No |
| `asset_volatility_labels` | `record_created_at_utc` | `TIMESTAMPTZ` | ISO-8601 UTC | เวลา UTC ที่สร้างแถว Label ครั้งแรก (รวมแถวที่ยัง Pending) | Metadata / Audit | No |
| `asset_volatility_labels` | `label_matured_at_utc` | `TIMESTAMPTZ` | ISO-8601 UTC | เวลาที่คำนวณ Target สำเร็จเมื่อข้อมูลจริงครบ 5 วันซื้อขาย; เป็น `NULL` ระหว่าง Pending | Metadata / Audit | Yes (Pending) |

---

## 4. ตารางข้อมูลประกอบสำหรับการคำนวณความเสี่ยงพอร์ตโฟลิโอ (`asset_rolling_correlations`)

ตารางข้อมูลประกอบสำหรับขั้นตอน **Downstream Portfolio Risk Calculation** ตามที่ระบุใน [feature_contract.md](./feature_contract.md) และ [target_contract.md](./target_contract.md)
- **วัตถุประสงค์และข้อจำกัดสำคัญ (Historical Proxy Disclaimer)**:
  - ตารางนี้เก็บค่าสหสัมพันธ์ย้อนหลัง 20 วันทำการ (สิ้นสุด ณ วันอ้างอิง $t$) เพื่อใช้เป็น **ตัวประมาณค่าจากอดีต (Historical Proxy)** สำหรับความสัมพันธ์ระหว่างสินทรัพย์ในช่วง 5 วันข้างหน้า ($[t+1, t+5]$) เมื่อนำมาประกอบกับค่าความผันผวนรายสินทรัพย์ที่โมเดลพยากรณ์ ($\hat{\sigma}_{\text{SPY},t}, \hat{\sigma}_{\text{IEF},t}, \hat{\sigma}_{\text{GLD},t}$)
  - **ค่าในตารางนี้ไม่ใช่ค่า Correlation ที่โมเดลพยากรณ์ล่วงหน้าสำหรับ 5 วันข้างหน้า** แต่คำนวณจากชุดข้อมูลผลตอบแทนที่เกิดขึ้นจริงถึงวัน $t$ เท่านั้น ทั้งนี้ต้องระบุข้อจำกัดนี้ไว้ในรายงานและแสดงคำอธิบายบนหน้า Dashboard อย่างชัดเจน
- **เงื่อนไขความสอดคล้องของเมทริกซ์ (Synchronized Window & Matrix Validity)**:
  - ค่าสหสัมพันธ์ทั้ง 3 คู่ ณ วัน $t$ ต้องคำนวณจาก**ช่วงวันที่ทำการ 20 วันชุดเดียวกันพอดี ($t-19$ ถึง $t$) ที่มีข้อมูลผลตอบแทนครบทั้ง 3 สินทรัพย์พร้อมกัน (Synchronized Complete Observations)** และเมทริกซ์สหสัมพันธ์ขนาด $3 \times 3$ ที่ได้ต้องมีสมบัติสมมาตร (Symmetric) และเป็น **Positive Semidefinite (PSD)**
- **ระดับหน่วยข้อมูล (Grain)**: 1 แถว ต่อ 1 วันซื้อขาย (`date`)
- **Primary Key**: `(date)`

| Table | Column | Type | Unit / Format | Meaning | Role | Nullable |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `asset_rolling_correlations` | `date` | `DATE` | `YYYY-MM-DD` | วันซื้อขายอ้างอิง ณ สิ้นวัน $t$ | Primary Key | No |
| `asset_rolling_correlations` | `corr_spy_ief_20d` | `FLOAT` | correlation $[-1, 1]$ | ค่าสหสัมพันธ์ Pearson ย้อนหลัง 20 วันทำการ (สิ้นสุดที่วัน $t$) ระหว่าง `log_return` ของ `SPY` และ `IEF` ใช้เป็น Historical Proxy สำหรับช่วง $[t+1, t+5]$ | Portfolio Risk Input (Historical Proxy) | Yes during warm-up (first 20 synchronized returns) |
| `asset_rolling_correlations` | `corr_spy_gld_20d` | `FLOAT` | correlation $[-1, 1]$ | ค่าสหสัมพันธ์ Pearson ย้อนหลัง 20 วันทำการ (สิ้นสุดที่วัน $t$) ระหว่าง `log_return` ของ `SPY` และ `GLD` ใช้เป็น Historical Proxy สำหรับช่วง $[t+1, t+5]$ | Portfolio Risk Input (Historical Proxy) | Yes during warm-up (first 20 synchronized returns) |
| `asset_rolling_correlations` | `corr_ief_gld_20d` | `FLOAT` | correlation $[-1, 1]$ | ค่าสหสัมพันธ์ Pearson ย้อนหลัง 20 วันทำการ (สิ้นสุดที่วัน $t$) ระหว่าง `log_return` ของ `IEF` และ `GLD` ใช้เป็น Historical Proxy สำหรับช่วง $[t+1, t+5]$ | Portfolio Risk Input (Historical Proxy) | Yes during warm-up (first 20 synchronized returns) |
| `asset_rolling_correlations` | `is_corr_ready` | `BOOLEAN` | boolean flag | `True` เมื่อค่าสหสัมพันธ์ทั้ง 3 คู่คำนวณจากหน้าต่าง 20 วันชุดเดียวกันครบถ้วน อยู่ในช่วง $[-1, 1]$ และเมทริกซ์ $3 \times 3$ ผ่านการตรวจ Symmetry และ Positive Semidefinite (PSD) แล้ว | Status | No |
| `asset_rolling_correlations` | `run_id` | `VARCHAR(64)` | UUID / run string | รหัสการสั่งรัน Pipeline ในรอบที่สร้างตารางสหสัมพันธ์นี้ (Pipeline Execution Run ID เช่น `'corr_run_20260925_001'`) | Metadata / Lineage | No |
| `asset_rolling_correlations` | `source_batch_id` | `VARCHAR(64)` | batch identifier | รหัส Snapshot ของแถวราคา ณ วันที่ `t` เป็นตัวอ้างอิงหลัก; หาก 20-day window ประกอบจากหลาย Batch ให้ใช้ Input Manifest ของ `run_id` ระบุแหล่งข้อมูลครบ | Metadata / Lineage | No |
| `asset_rolling_correlations` | `computed_at_utc` | `TIMESTAMPTZ` | ISO-8601 UTC (`YYYY-MM-DDTHH:MM:SSZ`) | วันและเวลา UTC ที่คำนวณและตรวจสอบเมทริกซ์สหสัมพันธ์สำเร็จ | Metadata / Audit | No |

---

## 5. ตารางผลพยากรณ์รายสินทรัพย์ (`asset_volatility_predictions`)

ผลที่โมเดลสร้างจาก Features ณ วัน `t` **ก่อน** ทราบผลจริงในอนาคต เพื่อนำไปคำนวณ Portfolio Risk หรือประเมิน MAE/RMSE ภายหลัง

- **Grain:** 1 คำทำนาย × 1 `prediction_date` × 1 `ticker` × 1 `model_name` × 1 ชุด Model/Input ที่ใช้จริง
- **Primary Key:** `prediction_id` (รหัสไม่ซ้ำและคงที่สำหรับการทำนายที่มีชุด Input/Model เดิม)
- **Logical Deduplication Key:** `(prediction_date, ticker, model_name, prediction_mode, model_version, feature_set_version, input_snapshot_id)`; รันคำขอเดิมซ้ำต้องไม่เพิ่ม Record เชิงธุรกิจซ้ำ
- **โมเดลเริ่มต้น:** `CONSTANT_BASELINE` (B0), `ROLLING_20D_BASELINE` (B1) และ `ONLINE_SGD` (B2) ตามสเปกที่เสนอไว้; B1 ใช้ `rv_20d` โดยตรง ส่วน B2 ใช้ Core Features 8 ตัว
- **Storage:** เป็นตารางหลักลำดับที่ 5 เท่านั้น; ไม่มีตาราง Evaluation เพิ่ม โดยเก็บผลประเมินใน `outputs/evaluation.csv`

| Table | Column | Type | Unit / Format | Meaning | Role | Nullable |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `asset_volatility_predictions` | `prediction_id` | `VARCHAR(64)` | stable ID / UUID | รหัสไม่ซ้ำของคำทำนายที่เผยแพร่ ใช้เชื่อมผลประเมินใน CSV | Primary Key | No |
| `asset_volatility_predictions` | `prediction_date` | `DATE` | `YYYY-MM-DD` | วันที่อ้างอิง `t` หลังปิดตลาดสหรัฐฯ; Feature ที่ใช้ต้องเป็นของวันเดียวกัน | Business Key / Time | No |
| `asset_volatility_predictions` | `ticker` | `VARCHAR(16)` | uppercase string | `SPY`, `IEF` หรือ `GLD` | Business Key | No |
| `asset_volatility_predictions` | `model_name` | `VARCHAR(64)` | enum-like string | วิธีพยากรณ์ เช่น `ROLLING_20D_BASELINE`, `ONLINE_SGD` | Business Key | No |
| `asset_volatility_predictions` | `model_version` | `VARCHAR(64)` | model/config version | เวอร์ชัน Model State หรือ Baseline Config ที่สร้างผลนี้ | Version / Lineage | No |
| `asset_volatility_predictions` | `prediction_mode` | `VARCHAR(32)` | `HISTORICAL_REPLAY` / `LATEST_BATCH` | ระบุว่าเป็นคำทำนายใน Replay หรือรอบ Batch ล่าสุด | Context | No |
| `asset_volatility_predictions` | `forecast_horizon_trading_days` | `INTEGER` | days | ต้องเท่ากับ `5`; เป็นวันซื้อขาย ไม่ใช่วันปฏิทิน | Prediction Metadata | No |
| `asset_volatility_predictions` | `target_start_date` | `DATE` | `YYYY-MM-DD` | วันซื้อขาย `t+1` ตาม Market Calendar; ไม่ใช่ผลจริง | Prediction Metadata | No |
| `asset_volatility_predictions` | `target_end_date` | `DATE` | `YYYY-MM-DD` | วันซื้อขาย `t+5` ตาม Market Calendar; ใช้ตรวจช่วงเวลาของ Prediction ก่อนจับคู่ Label | Prediction Metadata | No |
| `asset_volatility_predictions` | `predicted_vol_annualized` | `FLOAT` | annualized decimal | ค่าความผันผวน 5 วันถัดไปที่โมเดลพยากรณ์บนสเกลรายปี; ต้อง Finite และ `>= 0` | Prediction Output | No |
| `asset_volatility_predictions` | `feature_set_version` | `VARCHAR(16)` | semver | เวอร์ชันนิยาม Features ที่ใช้ทำนาย | Version / Lineage | No |
| `asset_volatility_predictions` | `feature_run_id` | `VARCHAR(64)` | run identifier | Run ที่สร้าง Features ของวัน `prediction_date` | Lineage | No |
| `asset_volatility_predictions` | `input_snapshot_id` | `VARCHAR(64)` | input manifest identifier | ระบุชุดข้อมูล/เวอร์ชัน Input ที่ใช้ร่วมกับ Model Version (ไม่ต้องสร้างตารางใหม่; ใช้ Manifest/Metadata File) | Lineage | No |
| `asset_volatility_predictions` | `last_training_target_end_date` | `DATE` | `YYYY-MM-DD` | วัน `t+5` ของ Label ล่าสุดที่ใช้ฝึก Model State; `NULL` สำหรับ Baseline ที่ไม่ได้ฝึกด้วย Labels | Leakage Audit | Yes (non-trained baseline) |
| `asset_volatility_predictions` | `run_id` | `VARCHAR(64)` | run identifier | รหัสของ Prediction Run ที่เขียนแถวนี้ | Execution Lineage | No |
| `asset_volatility_predictions` | `prediction_created_at_utc` | `TIMESTAMPTZ` | ISO-8601 UTC | เวลาที่สร้าง Prediction Record จริง แม้เป็นการจำลองย้อนหลัง | Audit Time | No |

**กติกาที่ต้องจำ**

1. ผลพยากรณ์ ณ วัน `t` ต้องคำนวณจาก Feature ณ วัน `t` และ Model State ที่ **ยังไม่ได้ใช้ Label ซึ่งยังไม่ Mature** ณ เวลาออกคำทำนาย; `last_training_target_end_date` ของ Online ML ต้องไม่เกินวัน `t` และต้องผ่าน Cut-off ของข้อมูลจริง
2. `predicted_vol_annualized` ต้องไม่ติดลบ เป็นตัวเลข Finite; หากโมเดลให้ค่าที่ไม่ผ่าน ให้นำไปจัดการตาม `prediction_contract.md` ก่อนเผยแพร่ ไม่ให้ Dashboard รับค่าที่ผิด
3. Forecast ต้องสร้าง/บันทึกก่อนนำผลจริงใน 5 วันข้างหน้าไปประเมิน; ห้ามแก้คำทำนายเดิมย้อนหลังเพื่อทำให้ MAE ดูดี
4. สำหรับ Portfolio Risk ต้องเลือก `prediction_date`/`model_name`/`prediction_mode` และชุด Prediction Run/เวอร์ชันที่ตรงกัน **ครบ SPY, IEF, GLD** พร้อม Correlation ของวันเดียวกัน; ข้อมูลไม่ครบ → `INCOMPLETE_INPUTS` (ไม่คำนวณพอร์ตบางส่วน)
5. `prediction_id` ต้องคงเดิมเมื่อ Input/Model/Config เดิมถูกรันซ้ำ; หากชุดข้อมูลหรือ Model Version เปลี่ยน ต้องบันทึก Record ใหม่อย่างตรวจสอบได้ ไม่แก้ Record เก่าโดยเงียบ ๆ; **ไม่สร้างระบบ Revision/Publication เพิ่มใน MVP**
6. `outputs/evaluation.csv` เก็บผลเมื่อ `is_label_mature=True` เท่านั้น โดย Join `prediction_date` ↔ `asset_volatility_labels.date` และ `ticker`, ตรวจ Target Window ตรงกัน แล้วคำนวณ Absolute/Squared Error เพื่อรวม MAE/RMSE

---

## 6. กฎการเลือกข้อมูลและป้องกัน Data Leakage

**ใช้เข้า Model ($X$) ได้ตามการทดลอง:**

- **B1 Rolling 20-Day Baseline:** ใช้ `asset_volatility_features.rv_20d` โดยตรงเป็นค่า Forecast ไม่ใช่การ Train ด้วย Feature Matrix 8 ตัว
- **B2 Online SGD:** ใช้ **Core Features 8 ตัว**: `ret_1d_t`, `ret_lag_1d`, `ret_lag_2d`, `ret_trailing_5d`, `ret_trailing_20d`, `rv_5d`, `rv_20d`, `rv_60d`
- **Experimental (เลือกทดลอง):** `rsi_14d`, `bb_width_20d`; ไม่บังคับใช้ในการทดสอบเริ่มต้น

**ห้ามใช้เป็นตัวแปรทำนายโดยอัตโนมัติ:** `date`, `ticker`, คอลัมน์ Metadata / Status / Lineage, คอลัมน์จาก `asset_volatility_labels`, คอลัมน์จาก `asset_volatility_predictions` และตาราง `asset_rolling_correlations` (Correlation ใช้ใน Portfolio Risk Engine)

**การเลือกแถว:**

| โหมด | เงื่อนไข |
|---|---|
| Train / Validation / Test | `is_warmup_buffer=False` + `is_model_ready=True` + `is_label_mature=True`; แบ่งตามเวลาและป้องกัน Label Window ซ้อนข้ามจุดแบ่ง |
| Batch Prediction ณ วัน `t` | `is_model_ready=True` และ `is_warmup_buffer=False`; ไม่ต้องรอ Label ของวัน `t` |
| Online Model Update | ใช้เฉพาะ Labels ที่รู้ผลจริงครบ 5 วันแล้ว ณ เวลา Update |
| Portfolio Risk | มี Forecast ที่สอดคล้องกันทั้ง 3 ETF และ `is_corr_ready=True` ของวันเดียวกัน |

## 7. ไฟล์ประกอบที่ไม่ใช่ Logical Tables

| Path | หน้าที่ | Schema / ข้อกำหนดหลัก |
|---|---|---|
| `data/raw/<source_batch_id>/raw_prices.csv` + `manifest.json` | Raw Snapshot และที่มาของข้อมูล | [data_contract.md](./data_contract.md) |
| `logs/quarantine.csv` | รายการที่ไม่ผ่าน Hard Validation | `run_id, source_batch_id, date, ticker, raw_value, reason, detected_at_utc` |
| `logs/ingestion_runs.jsonl` | บันทึก 1 JSON Object ต่อ Ingestion Run | `run_id`, เวลา, สถานะ, Counts, Ticker Details |
| `outputs/evaluation.csv` | ผลประเมินคำทำนายเมื่อ Target Mature | `prediction_id`, `prediction_date`, `ticker`, `model_name`, `target_realized_vol_5d`, `absolute_error`, `squared_error` และข้อมูลเวอร์ชัน/รันที่จำเป็น |

> **ไม่มีตาราง Quarantine, Audit, Evaluation แยกเพิ่ม** และเอกสารนี้ยังไม่กำหนดว่าจะเก็บ 5 ตารางหลักเป็น CSV, Parquet หรือ Database Table — เป็นการตัดสินใจในขั้น Implementation โดยไม่เปลี่ยน Logical Schema

## 8. หมายเหตุการปรับเอกสารตามลำดับงาน

- `data_contract.md` **v1.0.1** สอดคล้องกับ `market_prices_daily` 12 คอลัมน์ รวม `high`, `low`, `is_warmup_buffer` แล้ว
- `feature_contract.md` ยังต้องปรับคำว่า Baseline ให้แยก B1 (ใช้ `rv_20d` โดยตรง) กับ Online ML (ใช้ 8 Core Features) และชี้ Input Manifest เมื่อใช้หลาย Source Batches
- `target_contract.md` ฉบับถัดไปต้องเปลี่ยน `label_as_of_utc` เป็น `record_created_at_utc` + `label_matured_at_utc` เพื่อให้ Pending Labels ใช้ได้จริง
- `prediction_contract.md` ที่มีอยู่เป็น **Draft v0.1.0** และกล่าวถึง `prediction_evaluations` รวมถึง Revision/Publication System; เมื่อทำ Final ต้องปรับให้สอดคล้องกับ **ตาราง Predictions 1 ตาราง + `outputs/evaluation.csv`** และ **Prediction Schema แบบ MVP ใน Dictionary นี้**
- การแก้ Metadata/Schema จริงต้องแก้เอกสารที่เกี่ยวข้องและ Tests ให้ตรงกัน; **Final ในที่นี้หมายถึงสเปกที่ตกลงใช้ ไม่ใช่หลักฐานว่ารัน Pipeline ผ่านแล้ว**
