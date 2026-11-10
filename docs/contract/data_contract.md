# Data Contract — Market Data Ingestion & Validation

**Project:** Adaptive Portfolio Risk Lab  
**Document:** `contracts/data_contract.md`  
**Scope:** ข้อมูลราคาประจำวันของ `SPY`, `IEF`, `GLD` ตั้งแต่การดึงข้อมูลจนถึงการเผยแพร่ `market_prices_daily`

> **วัตถุประสงค์:** กำหนดข้อตกลงว่าข้อมูลที่รับจาก Yahoo Finance ผ่าน `yfinance` ต้องมีรูปแบบ ความหมาย คุณภาพ และการจัดการข้อผิดพลาดอย่างไร ก่อนส่งต่อให้ Feature, Target และ Correlation Pipelines โดยเน้นการตรวจสอบย้อนกลับและการรันซ้ำได้ **ไม่สร้างระบบฐานข้อมูลหรือ Logging เกินความจำเป็น**

เอกสารนี้ใช้คู่กับ [`datadict.md`](./datadict.md) ซึ่งเป็นแหล่งอ้างอิงกลางของชื่อคอลัมน์ ชนิดข้อมูล หน่วย และ Nullable; [`feature_contract.md`](./feature_contract.md), [`target_contract.md`](./target_contract.md) และ [`prediction_contract.md`](./prediction_contract.md) กำหนดกติกาของข้อมูลขั้นถัดไป

## 1. ขอบเขตและผลลัพธ์ที่ต้องส่งมอบ

| รายการ | ข้อกำหนดที่ใช้จริง |
|---|---|
| Source | Yahoo Finance ผ่าน Python library `yfinance` (ไม่ใช่ API ทางการที่รับประกันบริการ) |
| สินทรัพย์ | `SPY` (หุ้นสหรัฐฯ - S&P 500 ETF), `IEF` (พันธบัตรรัฐบาลสหรัฐฯ), `GLD` (ทองคำ - Gold Trust) เท่านั้น |
| ความถี่ | Daily / หนึ่งวันซื้อขายของตลาดสหรัฐฯ |
| Grain ของข้อมูลที่ผ่านตรวจ | 	1 แถว แทนข้อมูลราคาและผลตอบแทนของ 1 สินทรัพย์ (ticker) ณ 1 วันซื้อขาย (date) |
| Primary Key | `(date, ticker)` ต้องไม่ซ้ำ |
| ตารางปลายทางหลัก | **`market_prices_daily`** (เป็น 1 ใน 5 Logical Tables ของระบบ) |
| ข้อมูลดิบ | `data/raw/<source_batch_id>/raw_prices.csv` พร้อม `manifest.json` |
| ข้อมูลไม่ผ่าน Validation | **`logs/quarantine.csv`** (ไฟล์ CSV ไม่ใช่ตาราง Database) |
| ประวัติการรัน | **`logs/ingestion_runs.jsonl`** (ไฟล์ JSONL ไม่ใช่ตาราง Database) |
| การทำงาน | Batch ตามคำสั่งหรือรอบรายวันหลังข้อมูลราคาปิดพร้อมใช้งาน; ไม่ใช่ Real-time |

## 2. ช่วงเวลา การดึงข้อมูล และ Trading Calendar

### 2.1 Configuration

- `start_date` และ `end_date` คือ **ช่วงวันที่ต้องการวิเคราะห์แบบ Inclusive** `[start_date, end_date]` ในเขตวันซื้อขายของสหรัฐฯ
- ค่าเริ่มต้นสำหรับการทดลองย้อนหลังตาม Proposal: `start_date = 2021-09-27`, `end_date = 2026-09-25` (เปลี่ยนได้ผ่าน Config)
- `warmup_trading_days = 61` ใช้คำนวณ `fetch_start_date` ย้อนหลัง **อย่างน้อย 61 วันซื้อขาย** ก่อน `start_date` เพื่อให้สามารถคำนวณ `rv_60d` ในวันแรกของช่วงวิเคราะห์ได้ (60 ผลตอบแทนต้องอาศัยราคา 61 จุด)
- ข้อมูลก่อน `start_date` เป็น **Warm-up Buffer** ให้ขั้นตอน Downstream ใช้สร้าง Features แต่ **ไม่ใช้เป็นตัวอย่างสำหรับการวัดผลโมเดล** ตาม Feature Contract
- แถวข้อมูลใน `market_prices_daily` ต้องกำหนด `is_warmup_buffer = (date < start_date)` โดยอ้างอิง `start_date` ของรอบประมวลผลนั้น และส่งสถานะนี้ต่อให้ Feature Pipeline; หากเปลี่ยนช่วงวิเคราะห์ต้องคำนวณ Flag ใหม่อย่างสอดคล้องกับ Config ที่บันทึกใน Audit
- `end_date` สำหรับรอบรายวันต้องไม่เกิน **วันซื้อขายล่าสุดที่ข้อมูลราคาปิดพร้อมจริง**; หากวันที่ร้องขอยังไม่พร้อม ให้ระบุ `effective_end_date` ที่ใช้จริงไว้ใน Audit ไม่ตีความวันที่ยังไม่พร้อมเป็น Missing Trading Day
- `yfinance.download()` รับ `end` แบบ **Exclusive** จึงให้ส่ง `api_end_date = effective_end_date + 1 calendar day` และคัดกรองวันที่ที่ได้รับอีกครั้งให้ไม่เกิน `effective_end_date`

### 2.2 Trading Dates และ Timezones

- ใช้ปฏิทินวันซื้อขายของตลาดสหรัฐฯ ที่สอดคล้องกับ ETF ทั้ง 3 ตัว เช่น `exchange_calendars` หรือ `pandas_market_calendars` เพื่อหาวันที่คาดว่าจะมีข้อมูล (Expected Trading Days)
- `date` เป็น **วันที่ซื้อขายตาม `America/New_York`** ในรูป `YYYY-MM-DD` ไม่มีส่วนของเวลา; ต้องจัดการเวลา EST/EDT ก่อนแปลงเป็น `DATE`
- เวลาเหตุการณ์ใน Audit/Lineage ทุกค่าต้องเป็น UTC แบบ ISO-8601 เช่น `2026-09-25T21:05:12Z`
- **ห้ามถือว่าวันหยุดตลาดเป็นข้อมูลขาดหาย** และห้ามใช้ข้อมูลของวันซื้อขายที่ยังไม่ปิด/ยังไม่พร้อมเป็นราคาปิดสุดท้าย
- ตรวจความครบถ้วนกับ **Expected Trading Days ในช่วงที่ควรมีข้อมูลจริง** ไม่ใช่เทียบกับจำนวนวันปฏิทิน

## 3. Raw Snapshot และการระบุที่มาข้อมูล

### 3.1 การดึงและเก็บ Raw

1. เรียก `yfinance` โดยระบุ `auto_adjust=True`, `interval='1d'`, Ticker ทั้ง 3 และช่วงวันที่ตาม Config อย่างชัดเจน (ไม่พึ่งค่า Default ที่อาจเปลี่ยน)
2. จัดรูปผลลัพธ์ให้อยู่ในรูปที่บันทึกเป็นไฟล์ได้ โดย **รักษาค่าที่ได้รับจากต้นทางและคอลัมน์ราคาเดิม**; ยังไม่ลบข้อมูลผิดหรือคำนวณ Returns ในชั้น Raw
3. บันทึกเป็น `data/raw/<source_batch_id>/raw_prices.csv` และสร้าง `manifest.json` ในโฟลเดอร์เดียวกัน ก่อนเริ่มใช้ผลลัพธ์เพื่อเผยแพร่ข้อมูลที่ผ่าน Validation
4. Raw Snapshot ที่บันทึกแล้ว **ห้ามเขียนทับ**; หากดึงข้อมูลใหม่ให้ใช้ `source_batch_id` ใหม่ หากประมวลผลย้อนหลังจาก Raw เดิมให้ใช้ Batch ID เดิมแต่สร้าง `run_id` ใหม่

`manifest.json` ต้องเก็บอย่างน้อย `source_batch_id`, `source`, `tickers`, `auto_adjust`, `interval`, `requested_start_date`, `requested_end_date`, `api_end_date`, `downloaded_at_utc`, `raw_file_path`, `rows_fetched_raw`, เวอร์ชัน `yfinance` และ SHA-256 checksum ของไฟล์ Raw

> Raw Snapshot คือหลักฐานว่าในรอบนั้นระบบได้รับข้อมูลอะไรจริง ไม่ใช่ข้อมูลที่ผ่านการแก้ไขแล้ว ข้อมูล Yahoo Finance โดยเฉพาะราคาที่มีการปรับย้อนหลังอาจเปลี่ยนเมื่อดึงต่างเวลากัน ดังนั้นการทำ Historical Replay เพื่อเปรียบเทียบโมเดลต้อง **ล็อก Snapshot ที่ใช้ทดลอง** และระบุข้อจำกัดว่า Snapshot ย้อนหลังที่ดาวน์โหลดภายหลังไม่ใช่หลักฐานว่าราคาฉบับปรับย้อนหลังทุกค่าเคยพร้อมใช้ในอดีต ณ วันนั้น

### 3.2 ความหมายของรหัสอ้างอิง

| Field | ความหมาย | ตัวอย่าง |
|---|---|---|
| `source_batch_id` | รหัส Raw Snapshot ที่อ่านเป็นต้นทางของแถวข้อมูล | `yf_batch_20260925_01` |
| `run_id` | รหัส **การประมวลผล Ingestion หนึ่งครั้ง**; หากรันซ้ำต้องได้รหัสใหม่ | `ing_run_20260925_001` |
| `ingested_at_utc` | เวลา UTC ที่แถวผ่านการประมวลผลและพร้อมเผยแพร่ | `2026-09-25T21:05:12Z` |

ใน `market_prices_daily` ให้ `source_batch_id` ของแต่ละแถวอ้างถึง Snapshot ที่ใช้สร้างค่าของแถวนั้นจริง หากขั้นตอน Features/Targets ใช้ข้อมูลหลาย Snapshot จะต้องอ้างอิง **ชุดข้อมูลที่อ่านจริง (Input Manifest/Snapshot Version)** ในระดับการรัน Downstream ไม่กล่าวอ้างว่าทุก Rolling Window มาจาก Batch เดียวโดยอัตโนมัติ

## 4. Schema Contract: `market_prices_daily`

**Grain:** `(date, ticker)`; **Primary Key:** `(date, ticker)`; **รูปแบบ:** Long Format

| Column | Type / Unit | Nullable | กติกา |
|---|---|---|---|
| `date` | `DATE` / `YYYY-MM-DD` | No | วันซื้อขายตามตลาดสหรัฐฯ |
| `ticker` | `VARCHAR(16)` | No | ต้องเป็น `SPY`, `IEF` หรือ `GLD` |
| `open` | `FLOAT` / USD | No | ราคาเปิดจาก `Open` ในโหมด `auto_adjust=True`; Finite และ `> 0`; ต้องอยู่ระหว่าง `low` กับ `high` |
| `adjusted_close` | `FLOAT` / USD | No | ตัวเลข Finite และ `> 0`; ราคาปิดปรับปรุงแล้วจาก `Close` เมื่อ `auto_adjust=True` |
| `high` | `FLOAT` / USD | No | ราคาสูงสุดของวันจาก `High` ในโหมด `auto_adjust=True`; Finite และ `> 0` |
| `low` | `FLOAT` / USD | No | ราคาต่ำสุดของวันจาก `Low` ในโหมด `auto_adjust=True`; Finite และ `> 0` |
| `simple_return` | `FLOAT` / decimal ratio | เฉพาะแถวราคาแรกสุดของ Ticker | ผลตอบแทนธรรมดารายวัน |
| `log_return` | `FLOAT` / log ratio | เฉพาะแถวราคาแรกสุดของ Ticker | ผลตอบแทนแบบลอการิทึม |
| `is_anomaly_flagged` | `BOOLEAN` | No | `True` เมื่อ `abs(simple_return) > 0.20`; แถวแรกให้ `False` |
| `is_warmup_buffer` | `BOOLEAN` | No | `True` เมื่อ `date < config.start_date`; ใช้ระบุแถวที่ดึงเพิ่มเพื่อคำนวณ Rolling Features ไม่ใช้วัดผลโมเดล |
| `run_id` | `VARCHAR(64)` | No | อ้างอิง Run ที่เผยแพร่แถวนี้ |
| `source_batch_id` | `VARCHAR(64)` | No | อ้างอิง Raw Snapshot ที่ใช้สร้างแถวนี้ |
| `ingested_at_utc` | `TIMESTAMPTZ` / UTC | No | เวลาประมวลผลแถวสำเร็จ |

ลำดับคอลัมน์มาตรฐานของ `market_prices_daily` ที่ใช้ในโค้ดและเมื่อ Export เป็นไฟล์:

```python
columns = [
    "date",
    "ticker",
    "open",
    "adjusted_close",
    "high",
    "low",
    "simple_return",
    "log_return",
    "is_anomaly_flagged",
    "is_warmup_buffer",
    "run_id",
    "source_batch_id",
    "ingested_at_utc",
]
```

ให้ยึดความหมายคอลัมน์ใน [`datadict.md`](./datadict.md) เป็นหลักสำหรับการอธิบายทั่วทั้งระบบ หากมีการเปลี่ยน Schema ต้องแก้ Data Dictionary และ Tests ให้ตรงกัน

### 4.1 Canonical Price และ Schema Mapping

- เมื่อเรียก `yfinance` ด้วย **`auto_adjust=True`** ให้ใช้คอลัมน์ `Close` ที่ได้รับเป็น **ราคาปิดปรับปรุงแล้ว** แล้วเปลี่ยนชื่อเป็น `adjusted_close` ในชั้น Transformation
- นำคอลัมน์ **`Open` → `open`**, **`High` → `high`** และ **`Low` → `low`** จากผล `yfinance` **ในรอบเดียวกันและด้วย `auto_adjust=True` เหมือนกัน**; ทั้งสามคอลัมน์เป็นราคา Open/High/Low บนฐานการปรับราคาเดียวกับ `adjusted_close` เพื่อเก็บข้อมูลตลาดและตรวจคุณภาพ
- `simple_return` และ `log_return` รวมถึง Features/Targets หลัก **ยังคำนวณจาก `adjusted_close` เท่านั้น**; `open`, `high` กับ `low` ไม่ได้เพิ่มเป็นตัวแปรที่ต้องฝึก ML โดยอัตโนมัติ
- ไม่ใช้ `Adj Close` อีกชุด หรือผสมราคา `Open`, `High`, `Low`, `Close` แบบ **ไม่ปรับราคา** กับ `adjusted_close` ที่ปรับราคาแล้ว
- คอลัมน์ที่แหล่งข้อมูลไม่ได้ส่งมาแต่เป็นคอลัมน์บังคับต้อง **Fail Validation** แทนการเดาค่าทดแทน
- แปลงข้อมูลเป็น Long Format, ระบุ `ticker` และ `date` อย่างชัดเจน; เรียงข้อมูลตาม `ticker`, `date` ก่อนคำนวณ Returns

### 4.2 สูตรผลตอบแทน

กำหนด `Pᵢ,ₜ` เป็น `adjusted_close` ของสินทรัพย์ `i` ณ วันซื้อขาย `t`

**Simple Return** (ใช้ตรวจความผิดปกติและวิเคราะห์ผลตอบแทนพอร์ต):

$$R_{i,t}=\frac{P_{i,t}}{P_{i,t-1}}-1$$

**Log Return** (ใช้สร้าง Features และ Targets ด้าน Volatility):

$$r_{i,t}=\ln\!\left(\frac{P_{i,t}}{P_{i,t-1}}\right)=\ln(1+R_{i,t})$$

- ต้องคำนวณแยกตาม `ticker` และเรียงวันซื้อขายจากเก่าไปใหม่เท่านั้น
- แถวราคาแรกสุดของแต่ละ Ticker อนุญาตให้ `simple_return`, `log_return` เป็น `NULL` ได้ เพราะไม่มีราคาก่อนหน้า
- แถวที่มีราคาก่อนหน้าครบต้องได้ Returns ที่เป็น Finite; ไม่เติม `0` เพื่อกลบข้อมูลขาดหาย
- เมื่อขาดวันซื้อขายจริง ให้ถือว่าชุดข้อมูลของ Ticker นั้นไม่ผ่านก่อนคำนวณต่อ ไม่ใช้ราคาข้ามช่องว่างเสมือนเป็นผลตอบแทนของหนึ่งวันซื้อขายปกติ

## 5. Data Quality Gates

| Check | เกณฑ์ผ่าน | ระดับการจัดการ |
|---|---|---|
| Schema / Types | มีคอลัมน์บังคับและแปลงชนิดได้ถูกต้อง | **Hard Fail** |
| Ticker Domain | `ticker ∈ {SPY, IEF, GLD}` | **Hard Fail** |
| Date Validity | วันที่ถูกต้อง อยู่ในขอบเขตที่ขอ และเรียงเพิ่มขึ้นหลัง Sort | **Hard Fail** |
| Primary Key | `(date, ticker)` ไม่ซ้ำในชุดที่เผยแพร่ | **Hard Fail** |
| Price Validity | `open`, `adjusted_close`, `high`, `low` เป็น Finite และ `> 0` ทุกค่า | **Hard Fail** |
| High/Low Consistency | `low <= open <= high`, `low <= adjusted_close <= high` และ `low <= high` (ยอมให้คลาดเคลื่อนระดับ Floating-point เล็กน้อย) | **Hard Fail** |
| Warm-up Flag | `is_warmup_buffer` เป็น Boolean และเท่ากับ `(date < config.start_date)` | **Hard Fail** |
| Return Validity | Returns คำนวณถูกต้อง ไม่มี `Inf`/`NaN` นอกแถวแรก | **Hard Fail** |
| Trading Day Completeness | ไม่มีวันซื้อขายที่ควรมีแต่ขาดข้อมูล (เฉพาะวันที่ข้อมูลพร้อมแล้ว) | **Hard Fail** |
| Extreme Daily Return | `abs(simple_return) > 0.20` | **Warning / Flag** ไม่ Fail อัตโนมัติ |

**หมายเหตุเรื่อง Anomaly:** กรณีเพิ่มขึ้นหรือลดลงเกิน 20% ให้ตั้ง `is_anomaly_flagged=True` และนับใน Audit แต่ไม่ลบ/Quarantine/หยุด Pipeline อัตโนมัติ เพราะอาจเป็นเหตุการณ์ตลาดจริง หากตรวจสอบต่อแล้วพบว่าข้อมูลผิดจริง จึงแก้ปัญหาตามหลักฐานและประมวลผลใหม่ โดยเก็บ Raw เดิมไว้

### 5.1 เมื่อเจอ Hard Fail

- บันทึกรายการผิดลง `logs/quarantine.csv` **หากระบุ Ticker/วันที่หรือเหตุการณ์ที่ผิดได้** (รวมกรณีวันที่ควรมีแต่ไม่มีแถว Raw)
- **หยุดเผยแพร่ข้อมูลของ Ticker นั้นสำหรับรอบที่กำลังประมวลผล** ทั้งชุด ไม่ส่งชุดใหม่ของ Ticker นั้นไปสร้าง Feature/Target/Prediction
- Ticker อื่นที่ผ่านครบทุก Gate สามารถเผยแพร่และประมวลผลต่อได้
- เมื่อเป็นความล้มเหลวระดับแหล่งข้อมูลที่ไม่สามารถระบุ Ticker/แยกผลได้ ให้บันทึกใน Audit และหยุดทั้งรอบตามความเหมาะสม
- ไม่แก้ค่าราคาแบบคาดเดา ไม่ Forward-fill/Backward-fill/Interpolate เพื่อให้ผ่าน Gate โดยไม่มีเหตุผลและหลักฐาน
- **ข้อมูลที่เคยผ่านและเผยแพร่ในรอบก่อนต้องไม่ถูกลบเพียงเพราะรอบใหม่ล้มเหลว** แต่ต้องไม่แอบนำข้อมูลเก่ามาปะปนกับรอบใหม่แล้วรายงานว่าทุก Ticker สดและครบโดยไม่ตรวจวันที่/เวอร์ชัน

### 5.2 ผลกระทบต่อ Portfolio Risk และ Dashboard

- โมเดลรายสินทรัพย์ที่มีข้อมูลพร้อมยังสร้างผลทำนายของตัวเองได้
- Portfolio Risk ณ วัน `t` ต้องมี Forecast ครบ **SPY, IEF, GLD** ของวันอ้างอิงเดียวกัน และมี Correlation Matrix วันเดียวกันที่ `is_corr_ready=True`
- ถ้าขาดองค์ประกอบ ให้ `portfolio_vol = NULL` และ `status = 'INCOMPLETE_INPUTS'` พร้อมแจ้งบน Dashboard; **ห้ามปรับน้ำหนักสินทรัพย์ที่เหลือใหม่เอง**

## 6. Quarantine — `logs/quarantine.csv`

เป็นไฟล์หลักฐานสำหรับข้อมูล/เหตุการณ์ที่ **ไม่ผ่านกฎบังคับ** ไม่ใช่ตารางหลักของระบบ และไม่ใช่ทางเข้าของ ML

| Column | คำอธิบาย |
|---|---|
| `run_id` | รหัส Run ที่ตรวจพบ |
| `source_batch_id` | รหัส Raw Batch (อาจว่างหากดึงไม่สำเร็จจนไม่มี Snapshot) |
| `date` | วันซื้อขายของรายการผิด; ว่างได้หากเป็นปัญหาระดับ Schema/Fetch |
| `ticker` | Ticker ที่เกี่ยวข้อง; ว่างได้หากเป็นปัญหาระดับ Batch |
| `raw_value` | ค่าเดิมที่ผิด หรือข้อความสรุปรายการ Raw ที่ผิด; ว่างได้เมื่อวันซื้อขายไม่มีข้อมูล |
| `reason` | รหัสสาเหตุแบบ `UPPER_SNAKE_CASE` |
| `detected_at_utc` | เวลา UTC ที่ตรวจพบ |

**รหัสหลักที่ใช้:** `NON_POSITIVE_PRICE`, `NULL_REQUIRED_FIELD`, `DUPLICATE_PRIMARY_KEY`, `MISSING_EXPECTED_TRADING_DAY`, `INVALID_SCHEMA`, `INVALID_HIGH_LOW`, `INVALID_WARMUP_FLAG`, `INVALID_RETURN` (สามารถเพิ่มรหัสเมื่อมี Test/เหตุผลใหม่ พร้อมอัปเดตเอกสาร)

```csv
run_id,source_batch_id,date,ticker,raw_value,reason,detected_at_utc
ing_001,yf_001,2026-09-23,SPY,-100,NON_POSITIVE_PRICE,2026-09-24T01:00:00Z
ing_001,yf_001,2026-09-23,GLD,,MISSING_EXPECTED_TRADING_DAY,2026-09-24T01:00:00Z
```

*ตัวอย่างสมมติ* — ข้อผิดพลาดหนึ่งรายการอาจมีมากกว่าหนึ่ง `reason`; บันทึกแยกรายการ/เหตุผลได้ และไม่จำเป็นต้องทำให้จำนวน Quarantine เท่ากับจำนวน Raw Rows ที่ไม่ผ่าน (เพราะเหตุการณ์วันหายไม่มีแถว Raw)

**กติกาการเขียนไฟล์:** เขียนหัวคอลัมน์ครั้งเดียวและ Append แถวใหม่โดยไม่ลบประวัติ; Run ใหม่ใช้ `run_id` ใหม่แม้พบข้อผิดพลาดเดิม ห้ามใช้ Quarantine CSV เป็นข้อมูลที่ต้อง Join เข้า Model โดยตรง

## 7. Ingestion Audit — `logs/ingestion_runs.jsonl`

ไฟล์นี้ใช้บันทึกผลของ **ทุกการรัน** ไม่ใช่เพียงรอบที่ล้มเหลว หนึ่ง Run จบลงด้วย **หนึ่ง JSON Object ในหนึ่งบรรทัด** (JSONL)

| Field | ความหมาย |
|---|---|
| `run_id` | รหัสรัน (ต้องไม่ซ้ำระหว่างการรัน) |
| `source_batch_id` | Raw Snapshot ที่ใช้ หรือ `null` หากยังไม่มี |
| `started_at_utc`, `finished_at_utc` | เวลาเริ่ม/จบเป็น UTC |
| `status` | `SUCCESS`, `PARTIAL_SUCCESS`, `FAILED` |
| `config_start_date`, `config_end_date` | ช่วงข้อมูลที่ร้องขอ |
| `actual_fetch_start_date`, `effective_end_date` | ขอบเขตการดึง/ตรวจสอบที่ใช้จริง |
| `raw_snapshot_path` | ที่เก็บ Raw Snapshot ถ้าสร้างสำเร็จ |
| `rows_fetched_raw` | จำนวนแถวดิบที่ดึงได้ |
| `rows_validated_passed` | จำนวนแถวที่ผ่านกฎเฉพาะแถว (อาจยังไม่ได้เผยแพร่เพราะ Ticker ล้มเหลว) |
| `rows_published` | จำนวนแถวที่เผยแพร่เข้าตารางหลักจริง |
| `rows_quarantined` | จำนวนรายการผิดที่บันทึกใน CSV (อาจรวมวันหายที่ไม่มี Raw Row) |
| `rows_anomaly_flagged` | จำนวนแถวที่เข้าเกณฑ์ Warning |
| `tickers` | สถานะและจำนวนข้างต้นแยก SPY/IEF/GLD |
| `error_message` | สรุปข้อผิดพลาด หรือ `null` หากไม่มี |

**ตัวอย่างข้อมูลสมมติ (จัดหลายบรรทัดให้อ่านง่าย; ใน `.jsonl` จริงต้องอยู่บรรทัดเดียว):**

```json
{
  "run_id": "ing_001",
  "source_batch_id": "yf_001",
  "started_at_utc": "2026-09-24T01:00:00Z",
  "finished_at_utc": "2026-09-24T01:00:05Z",
  "status": "PARTIAL_SUCCESS",
  "config_start_date": "2021-09-27",
  "config_end_date": "2026-09-23",
  "actual_fetch_start_date": "2021-06-28",
  "effective_end_date": "2026-09-23",
  "raw_snapshot_path": "data/raw/yf_001/raw_prices.csv",
  "rows_fetched_raw": 300,
  "rows_validated_passed": 299,
  "rows_published": 200,
  "rows_quarantined": 1,
  "rows_anomaly_flagged": 0,
  "tickers": {
    "SPY": {"status": "FAILED", "rows_fetched_raw": 100, "rows_validated_passed": 99, "rows_published": 0},
    "IEF": {"status": "SUCCESS", "rows_fetched_raw": 100, "rows_validated_passed": 100, "rows_published": 100},
    "GLD": {"status": "SUCCESS", "rows_fetched_raw": 100, "rows_validated_passed": 100, "rows_published": 100}
  },
  "error_message": "SPY: NON_POSITIVE_PRICE"
}
```

**สถานะทั้งรอบ:**

- `SUCCESS`: Ticker ทั้งสามผ่านและเผยแพร่ได้ครบตามขอบเขตที่ต้องการ
- `PARTIAL_SUCCESS`: มีอย่างน้อยหนึ่ง Ticker เผยแพร่ได้ และมีอีก Ticker ล้มเหลว
- `FAILED`: ไม่มี Ticker ใดเผยแพร่ได้ หรือเกิดความผิดพลาดร้ายแรงระดับ Pipeline

**กติกา:** Append-only; บันทึกแม้เกิด Exception ที่จับและจัดการได้; จำนวน `rows_validated_passed` อาจมากกว่า `rows_published` เพราะนโยบาย Fail-fast ราย Ticker ไม่บังคับให้ `raw = passed + quarantine` เสมอไป

## 8. การรันซ้ำ การ Retry และการ Backfill

### 8.1 Idempotency

- เมื่อประมวลผล Raw Snapshot เดิมด้วย Config/เวอร์ชันการแปลงเดิม **ค่าเชิงธุรกิจ** ของ `market_prices_daily` ต้องเหมือนเดิม
- ห้ามมี `(date, ticker)` ซ้ำเมื่อรัน Pipeline เดิมซ้ำ; ให้เตรียมข้อมูลในพื้นที่ชั่วคราว ตรวจสอบก่อน แล้ว **Replace/Upsert ตามคีย์ที่ผ่านการตรวจ** แบบไม่เกิดแถวซ้ำ (รายละเอียดขึ้นกับ CSV/Parquet/DB ที่เลือกภายหลัง)
- `run_id` และ `ingested_at_utc` อาจต่างกันในแต่ละครั้งได้ เพราะเป็นประวัติการรัน ไม่ใช่ข้อมูลธุรกิจ; Audit/Quarantine เก็บเพิ่มตาม Run ได้ตามปกติ
- ไม่เขียนทับ Raw Snapshot เดิม และไม่เผยแพร่ข้อมูลครึ่งชุดของ Ticker ที่ Fail Validation

### 8.2 Retry และ Backfill

- เมื่อเจอข้อผิดพลาดชั่วคราวจากการเชื่อมต่อ/Timeout ให้ Retry แบบจำกัดจำนวน (ค่าเริ่มต้น **สูงสุด 3 ครั้ง**) และบันทึกผลสำเร็จ/ล้มเหลวใน Audit
- **ห้าม Retry เพื่อฝืนผ่านข้อผิดพลาดด้านคุณภาพข้อมูล** เช่น ราคาติดลบหรือคีย์ซ้ำ; ต้องตรวจสาเหตุหรือดึงใหม่เป็น Batch ใหม่ตามหลักฐาน
- Backfill ให้ประมวลผลจาก Raw Snapshot ที่ระบุแน่นอน (หรือบันทึก Snapshot ใหม่หากต้องดึงข้อมูลอีกครั้ง) พร้อม `run_id` ใหม่ เพื่อสร้าง `market_prices_daily` ได้ใหม่โดยยังตรวจสอบต้นทางได้
- หาก Source ปรับราคาย้อนหลัง ต้องเก็บ Snapshot เก่าไว้ ไม่แก้เงียบ ๆ; บันทึกว่า Run ใหม่ใช้ Source Batch ใหม่และตรวจความต่างของข้อมูลก่อนเผยแพร่

## 9. Acceptance Criteria และ Automated Tests ขั้นต่ำ

ถือว่า Data Ingestion Stage **ผ่าน Definition of Done** เมื่อพิสูจน์ได้ว่า:

1. ดึง SPY/IEF/GLD ภายในช่วงเวลาที่กำหนด รวม Warm-up ตาม Trading Calendar; บันทึก Raw Snapshot และ Manifest ได้
2. `market_prices_daily` มี Schema 13 คอลัมน์ตาม Data Dictionary รวม `open`, `high`, `low`, `is_warmup_buffer` และไม่มี `(date, ticker)` ซ้ำ
3. ราคา `open`/`adjusted_close`/`high`/`low` ติดลบหรือเป็นศูนย์, `low > high`, ราคาเปิดหรือปิดอยู่นอกช่วง High/Low, Null Required Field, Duplicate และ Missing Trading Day ถูกตรวจพบ; ไม่ส่งข้อมูลผิดไป Downstream
4. วันหยุดตลาดไม่ถูกนับเป็น Missing และแถวแรกของแต่ละ Ticker สามารถมี Return เป็น `NULL` ได้ตามกฎ; `is_warmup_buffer` ต้องตรงกับ `date < config.start_date` ทุกแถว
5. กรณี Return เกิน `±20%` ถูก Flag/บันทึก Warning โดยไม่ตัดแถวอัตโนมัติ
6. หาก Ticker หนึ่ง Fail ระบบแยกผลของ Ticker นั้น แต่ยังเผยแพร่ Ticker อื่นที่ผ่านได้อย่างถูกต้อง; Portfolio ต้องไม่แอบใช้ข้อมูลไม่ครบ
7. มีรายการใน `quarantine.csv` และสรุปใน `ingestion_runs.jsonl` ที่ผูกกันด้วย `run_id`; Count แยก Raw/Validated/Published ถูกต้องตามนิยาม
8. เมื่อรันจาก Snapshot เดิมซ้ำ ไม่เกิดคีย์ซ้ำ และข้อมูลธุรกิจที่ได้ตรงกัน; ทวนสอบ Source ได้จาก Manifest และ Checksum

> **หลักฐานส่งอาจารย์:** Raw Snapshot ตัวอย่าง + Manifest, Data Quality/Test Report, Quarantine CSV ของชุดข้อมูลทดสอบที่ใส่ข้อมูลผิด, Audit JSONL และผลทดสอบ Idempotency เป็นหลักฐานการทำงานจริง ไม่ใช่แค่การบรรยายกฎในเอกสาร

## 10. ความสอดคล้องกับเอกสารอื่นและข้อจำกัด

- รายชื่อ **5 ตารางหลัก** อยู่ใน [`README.md`](./README.md): `market_prices_daily`, `asset_volatility_features`, `asset_volatility_labels`, `asset_rolling_correlations`, `asset_volatility_predictions` — เอกสารนี้ **ไม่เพิ่มตาราง Quarantine หรือ Audit**
- Quarantine และ Audit เป็นไฟล์ประกอบของ Data Engineering; `outputs/evaluation.csv` เป็นผลประเมิน ML ที่อยู่นอกขอบเขต Ingestion
- การใช้ `auto_adjust=True` ช่วยกำหนด Canonical Price ที่สม่ำเสมอ แต่ข้อมูลปรับย้อนหลังมีข้อจำกัดด้าน Historical Point-in-Time; ต้องระบุ Snapshot Version เมื่อเทียบผลการทดลอง
- เอกสารนี้นิยาม **ข้อกำหนดสำหรับการ Implementation** ไม่ได้อ้างว่าระบบหรือ Automated Tests ถูกพัฒนาและรันผ่านแล้ว
- เมื่อปรับชื่อ/ชนิดข้อมูลในอนาคต ให้แก้ `datadict.md` และ Test ที่เกี่ยวข้องควบคู่กัน การเปลี่ยนกฎของ Feature/Target/Prediction ต้องตรวจผลกระทบข้าม Contract ด้วย

**ข้อสรุปที่ใช้ร่วมกัน:** **1 ตาราง Ingestion หลัก (`market_prices_daily`) + Raw Snapshot + Quarantine CSV + Audit JSONL**; ไม่มีฐานข้อมูล/ระบบ Logging เพิ่มเพื่อเรื่องนี้โดยเฉพาะ
