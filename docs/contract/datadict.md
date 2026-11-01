# Data Dictionary กลางของระบบ (Centralized Data Dictionary)

> **Data Dictionary** คือเอกสารอ้างอิงกลาง (Single Source of Truth) ที่กำหนดชื่อคอลัมน์ ชนิดข้อมูล (Data Type) หน่วยวัด (Unit) ความหมาย (Meaning) บทบาทของคอลัมน์ (Role) และเงื่อนไขค่าว่าง (Nullable) ของทุกตารางในระบบ
>
> **หลักการออกแบบระดับหน่วยข้อมูล (System-wide Grain Principle)**:
> ระบบนี้มุ่งเน้นการ**ทำนายความผันผวนจริงล่วงหน้า 5 วันทำการ (5-Day Forward Realized Volatility) แยกรายสินทรัพย์ (`SPY`, `IEF`, `GLD`)** ดังนั้นตารางข้อมูลราคาตั้งต้น ตาราง Feature สำหรับโมเดล และตาราง Target/Label จึงใช้ระดับหน่วยข้อมูล (Grain) เดียวกันคือ **1 แถวต่อ `(date, ticker)`** ส่วนการคำนวณความเสี่ยงของพอร์ตโฟลิโอตามสัดส่วนน้ำหนักที่ผู้ใช้กำหนด (เช่น `50/30/20`) เป็นขั้นตอน **Downstream Portfolio Risk Aggregation** ที่นำค่าพยากรณ์รายสินทรัพย์ไปประกอบกับตารางสหสัมพันธ์ (`asset_rolling_correlations`)

---

## เอกสารสัญญาที่เกี่ยวข้อง (Related Contracts)

- **ขั้นที่ 1 — การดึงและตรวจสอบข้อมูลตลาดรายสินทรัพย์**: [data_contract.md](./data_contract.md) (อ้างอิงตาราง `market_prices_daily`)
- **ขั้นที่ 2 — การสร้างและตรวจสอบ Feature รายสินทรัพย์**: [feature_contract.md](./feature_contract.md) (อ้างอิงตาราง `asset_volatility_features` และตารางประกอบ `asset_rolling_correlations`)
- **ขั้นที่ 3 — การสร้าง Target รายสินทรัพย์และการคำนวณความเสี่ยงพอร์ตโฟลิโอ (Downstream)**: [target_contract.md](./target_contract.md) (อ้างอิงตาราง `asset_volatility_labels` และสูตรรวมความเสี่ยงพอร์ตโฟลิโอ)
- *(หมายเหตุการอ้างอิงชื่อไฟล์: เอกสารชุดนี้ใช้ชื่อไฟล์มาตรฐานใน Repository คือ `data_contract.md`, `datadict.md`, `feature_contract.md` และ `target_contract.md` โดยตรงเพื่อแทนที่ฉบับเดิม หากมีการดาวน์โหลดแยกที่มีต่อท้าย เช่น `(1)` ต้องเปลี่ยนชื่อไฟล์กลับมาเป็นชื่อมาตรฐานข้างต้นเพื่อให้ลิงก์ภายในทำงานได้ถูกต้อง)*

> [!IMPORTANT]
> **มาตรฐานชนิดข้อมูลเวลาและรหัสอ้างอิง (Timestamp & Lineage ID Standards)**:
> 1. **คอลัมน์เวลา (`TIMESTAMPTZ`)**: คอลัมน์เวลาสำหรับการตรวจสอบย้อนหลัง (Audit Timestamps) ทุกตารางกำหนดให้ใช้ชนิดข้อมูล **`TIMESTAMPTZ`** (Timezone-aware Timestamp ที่จัดเก็บค่าเวลาในเขตเวลา **UTC** เสมอ ตามมาตรฐาน ISO-8601 รูปแบบ `YYYY-MM-DDTHH:MM:SSZ` เช่น `'2026-09-25T21:00:00Z'`) แทนการใช้ `TIMESTAMP_NTZ`
> 2. **การแยกความหมายระหว่าง `source_batch_id` และ `run_id`**:
>    - **`source_batch_id` (Data Batch ID)**: รหัสประจำชุดข้อมูลดิบต้นทางที่ดึงจาก `yfinance` ในตาราง `market_prices_daily` (เช่น `'yf_batch_20260925_01'`) ซึ่งจะถูกส่งต่อค่าเดิม (Propagate) ไปยังทุกตาราง Downstream เพื่อระบุว่าแถวข้อมูลนั้นสร้างมาจาก Snapshot ข้อมูลดิบชุดใด
>    - **`run_id` (Pipeline Execution Run ID)**: รหัสประจำการสั่งรัน Pipeline ของขั้นตอนที่สร้างตารางนั้นๆ โดยตรง (เช่น `'ing_run_...'`, `'feat_run_...'`, `'lbl_run_...'`, `'corr_run_...'`) เพื่อใช้อ้างอิงกลับไปยังไฟล์ Config และ Run Audit Log ของการรันรอบนั้น ห้ามนำ `run_id` กับ `source_batch_id` มาใช้สลับหรือแทนกัน

---

## 1. ตารางข้อมูลราคาตลาดและผลตอบแทนรายสินทรัพย์ (`market_prices_daily`)

ตารางผลลัพธ์จากกระบวนการ Data Ingestion & Initial Transformation ตามที่กำหนดใน [data_contract.md](./data_contract.md)
- **ระดับหน่วยข้อมูล (Grain)**: 1 แถว แทนข้อมูลราคาและผลตอบแทนของ 1 สินทรัพย์ (`ticker`) ณ 1 วันซื้อขาย (`date`)
- **Primary Key**: `(date, ticker)`

| Table | Column | Type | Unit / Format | Meaning & Example | Role | Nullable |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `market_prices_daily` | `date` | `DATE` | `YYYY-MM-DD` | วันเปิดทำการซื้อขายของตลาดหลักทรัพย์สหรัฐฯ (NYSE/NASDAQ) ณ วัน $t$ (เช่น `'2024-03-15'`) | Primary Key | No |
| `market_prices_daily` | `ticker` | `VARCHAR(16)` | uppercase string | รหัสหลักทรัพย์ (`'SPY'`, `'IEF'`, `'GLD'`) | Primary Key | No |
| `market_prices_daily` | `adjusted_close` | `FLOAT` | USD | ราคาปิดที่ปรับปรุง Corporate Actions (ปันผล, แตกพาร์) จากคอลัมน์ `Close` ของ `yfinance` เมื่อตั้ง `auto_adjust=True` (เช่น `510.25`) | Price Input | No |
| `market_prices_daily` | `simple_return` | `FLOAT` | decimal ratio | ผลตอบแทนรายวันแบบธรรมดาของสินทรัพย์ $i$: $R_{i,t} = (P_{i,t}^{\text{adj}} / P_{i,t-1}^{\text{adj}}) - 1$ | Derived Metric | Yes (1st row per `ticker`) |
| `market_prices_daily` | `log_return` | `FLOAT` | log ratio | ผลตอบแทนรายวันแบบลอการิทึมของสินทรัพย์ $i$: $r_{i,t} = \ln(P_{i,t}^{\text{adj}} / P_{i,t-1}^{\text{adj}})$ | Derived Metric | Yes (1st row per `ticker`) |
| `market_prices_daily` | `is_anomaly_flagged` | `BOOLEAN` | boolean flag | ธงแจ้งเตือนเมื่อ `abs(simple_return) > 0.20` (เปลี่ยนแปลงเกิน $\pm 20\%$ ใน 1 วัน) เพื่อส่งตรวจสอบโดยไม่ตัดแถวทิ้งอัตโนมัติ | Audit / Quality Flag | No |
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
| `asset_volatility_features` | `source_batch_id` | `VARCHAR(64)` | batch identifier | รหัสชุดข้อมูลดิบต้นทาง (`market_prices_daily.source_batch_id` เช่น `'yf_batch_20260925_01'`) ที่ส่งต่อมาโดยไม่เปลี่ยนค่า เพื่อระบุ Snapshot ข้อมูลราคาต้นทาง | Metadata / Lineage | No |
| `asset_volatility_features` | `feature_as_of_utc` | `TIMESTAMPTZ` | ISO-8601 UTC (`YYYY-MM-DDTHH:MM:SSZ`) | วันและเวลา UTC ที่คำนวณและบันทึกแถว Feature สำเร็จ (เช่น `'2026-09-25T21:10:00Z'`) | Metadata / Audit | No |

---

## 3. ตารางตัวแปรตาม / เป้าหมายการทำนายรายสินทรัพย์ (`asset_volatility_labels`)

ตารางผลลัพธ์สำหรับการสร้าง Label/Target รายสินทรัพย์ ตามที่กำหนดใน [target_contract.md](./target_contract.md) (แทนที่ตาราง `portfolio_volatility_labels` เดิม)
- **ระดับหน่วยข้อมูล (Grain)**: 1 แถว แทนค่าความผันผวนจริงในช่วงอนาคต 5 วันทำการถัดจากวันอ้างอิง ($t+1$ ถึง $t+5$) ของสินทรัพย์ `ticker` ณ วันอ้างอิง `date` ($t$)
- **Primary Key**: `(date, ticker)`

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
| `asset_volatility_labels` | `source_batch_id` | `VARCHAR(64)` | batch identifier | รหัสชุดข้อมูลดิบต้นทาง (`market_prices_daily.source_batch_id` เช่น `'yf_batch_20260925_01'`) ที่ใช้คำนวณ Target | Metadata / Lineage | No |
| `asset_volatility_labels` | `label_as_of_utc` | `TIMESTAMPTZ` | ISO-8601 UTC (`YYYY-MM-DDTHH:MM:SSZ`) | วันและเวลา UTC ที่คำนวณและบันทึกค่า Target สำเร็จหลังข้อมูลวัน $t+5$ ปิดตลาด (เช่น `'2026-09-25T21:15:00Z'`) | Metadata / Audit | No |

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
| `asset_rolling_correlations` | `source_batch_id` | `VARCHAR(64)` | batch identifier | รหัสชุดข้อมูลดิบต้นทาง (`market_prices_daily.source_batch_id` เช่น `'yf_batch_20260925_01'`) | Metadata / Lineage | No |
| `asset_rolling_correlations` | `computed_at_utc` | `TIMESTAMPTZ` | ISO-8601 UTC (`YYYY-MM-DDTHH:MM:SSZ`) | วันและเวลา UTC ที่คำนวณและตรวจสอบเมทริกซ์สหสัมพันธ์สำเร็จ | Metadata / Audit | No |

---

## 5. กฎการคัดกรองคอลัมน์เข้าโมเดลและการใช้อ้างอิง (Model Matrix Selection & Governance Rules)

1. **การแยก Keys (`date`, `ticker`) ออกจากตัวแปรทำนาย ($X$)**:
   - คอลัมน์ `date` และ `ticker` มีบทบาทเป็น **`Primary Key`** เท่านั้น ใช้สำหรับจัดเรียงเวลา (Sorting), จับคู่ตาราง (Join ระหว่าง `asset_volatility_features` กับ `asset_volatility_labels`), และกรองแยกชุดข้อมูลตามสินทรัพย์ (`ticker == 'SPY'`, `'IEF'`, หรือ `'GLD'`)
   - Pipeline เตรียมข้อมูลเข้าโมเดลต้อง**ตรวจสอบและคัดแยก `date` และ `ticker` ออกจากเมทริกซ์ตัวแปรต้น $X$ โดยอัตโนมัติ** ห้ามส่งรหัส `ticker` หรือ `date` เข้าเป็น Predictor ดิบโดยไม่ได้ตั้งใจ
2. **กฎการคัดคอลัมน์เข้าเมทริกซ์ตัวแปรต้น ($X$) ของแต่ละสินทรัพย์**:
   - **อนุญาตให้นำเข้า $X$ เป็นค่าเริ่มต้น (Baseline)**: เฉพาะคอลัมน์ในตาราง `asset_volatility_features` ที่มี `Role = Core Feature` ทั้ง 8 คอลัมน์ของสินทรัพย์นั้น (`ret_1d_t`, `ret_lag_1d`, `ret_lag_2d`, `ret_trailing_5d`, `ret_trailing_20d`, `rv_5d`, `rv_20d`, `rv_60d`)
   - **อนุญาตให้นำเข้า $X$ เฉพาะรอบการทดลอง**: คอลัมน์ที่มี `Role = Experimental Feature` (`rsi_14d`, `bb_width_20d`) เมื่อตั้งค่าเปิดใช้งานในการทดลองเปรียบเทียบเท่านั้น
   - **ห้ามนำเข้า $X$ โดยเด็ดขาด**: คอลัมน์ที่มี `Role` เป็น `Primary Key`, `Status`, `Metadata`, `Metadata / Lineage`, `Metadata / Audit`, `Target Metadata`, `Target (y)` และคอลัมน์จากตาราง `asset_rolling_correlations` (เว้นแต่จะกำหนดการทดลอง Cross-asset Feature แยกต่างหากอย่างเป็นทางการ)
3. **กฎการคัดกรองแถวสำหรับ Training vs. Inference**:
   - **สำหรับการฝึกและประเมินผลโมเดล (Training / Validation / Test)**: ใช้เฉพาะแถวที่ `is_warmup_buffer == False`, `is_model_ready == True` และเมื่อ Join กับตาราง `asset_volatility_labels` แล้วต้องมี `is_label_mature == True`
   - **สำหรับการพยากรณ์ใช้งานจริง ณ วันปัจจุบัน (Live Inference ณ วัน $t$)**: ใช้แถวของวัน $t$ ที่มี `is_model_ready == True` โดยไม่ต้องรอให้ `is_label_mature == True`
4. **การควบคุมการแก้ไข Schema (Schema Evolution)**:
   - หากมีการเพิ่ม ลด หรือแก้ไขนิยามคอลัมน์ ต้องอัปเดตที่ `datadict.md` นี้ก่อนเสมอ พร้อมปรับเพิ่มเลขเวอร์ชันใน `feature_set_version` หรือ `target_version` และบันทึกใน Run Metadata
