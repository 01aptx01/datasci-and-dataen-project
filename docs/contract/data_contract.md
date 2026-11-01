# ขั้นที่ 1: กำหนด Data Contract สำหรับการดึงและตรวจสอบข้อมูลตลาดรายสินทรัพย์

> **Data Contract** คือข้อตกลงและพันธสัญญาระหว่างแหล่งข้อมูลภายนอกกับระบบภายใน (Feature Pipeline, Target Pipeline และโมเดลทำนายความผันผวนรายสินทรัพย์) เพื่อรับประกันว่าข้อมูลราคาตลาดรายวันที่นำเข้ามามีโครงสร้าง ชนิดข้อมูล มาตรฐานเวลา และเกณฑ์การตรวจสอบคุณภาพที่ชัดเจนก่อนนำไปประมวลผลต่อ
>
> สำหรับรายละเอียดคำอธิบายคอลัมน์ ชนิดข้อมูล (Data Type) หน่วยวัด (Unit) บทบาท (Role) และเงื่อนไขค่าว่าง (Nullable) ของตาราง `market_prices_daily` รวมถึงตาราง Feature และ Target รายสินทรัพย์ (`asset_volatility_features`, `asset_volatility_labels`) ให้อ้างอิงจากแหล่งข้อมูลกลางที่ **[datadict.md](./datadict.md)** ซึ่งใช้ระดับหน่วยข้อมูลหลัก (Grain) เป็น `(date, ticker)` สอดคล้องกันทั้งระบบ

---

## 1. ข้อมูลพื้นฐานของระบบและขอบเขตข้อมูล (Ingestion Specification & Scope)

| หัวข้อ | ข้อกำหนด / รายละเอียด |
| :--- | :--- |
| **แหล่งข้อมูล (Source)** | Yahoo Finance ดึงข้อมูลผ่านไลบรารี `yfinance` |
| **สินทรัพย์ที่รองรับ (Assets)** | `SPY` (หุ้นสหรัฐฯ - S&P 500 ETF), `IEF` (พันธบัตรรัฐบาลสหรัฐฯ 7-10 ปี), `GLD` (ทองคำ - Gold Trust) |
| **ความถี่ (Frequency)** | รายวัน (Daily) เฉพาะวันเปิดทำการซื้อขายของตลาดหลักทรัพย์สหรัฐฯ |
| **ระดับหน่วยข้อมูล (Granularity)** | 1 แถว แทนข้อมูลราคาและผลตอบแทนของ 1 สินทรัพย์ (`ticker`) ณ 1 วันซื้อขาย (`date`) |
| **คีย์หลัก (Primary Key)** | `(date, ticker)` เพื่อรับประกันความไม่ซ้ำซ้อนของข้อมูลรายสินทรัพย์ |
| **การกำหนดช่วงเวลาผ่าน Config (Configurable Time Range)** | • กำหนดช่วงเวลาวิเคราะห์ผ่านไฟล์ตั้งค่า (Configuration) ด้วยพารามิเตอร์ `start_date` และ `end_date` (ค่าตั้งต้นสำหรับ Baseline: `start_date = '2021-09-27'`, `end_date = '2026-09-25'`) แบบรวมวันเริ่มต้นและวันสิ้นสุด (**Inclusive**: `[start_date, end_date]`)<br>• **การดึงเผื่อช่วง Warm-up (`fetch_start_date`)**: ระบบรองรับการดึงข้อมูลย้อนหลังก่อน `start_date` ตามค่า `warmup_trading_days` ใน Config (เช่น ย้อนหลังอย่างน้อย 61 วันทำการ หรือประมาณ 90–100 วันปฏิทิน) เพื่อให้วัน `start_date` มีข้อมูลพร้อมคำนวณ Rolling Features ทันที<br>• **การบันทึก Metadata ของแต่ละ Run**: ทุกครั้งที่รัน Pipeline ต้องบันทึกค่าพารามิเตอร์ที่ใช้จริง (`config_start_date`, `config_end_date`, `actual_fetch_start_date`, `actual_min_date`, `actual_max_date`) ผูกกับ `run_id` และ `source_batch_id` ใน Run Metadata Log<br>• **รายละเอียดการเรียก API (`yfinance` Implementation Detail)**: เนื่องจากพารามิเตอร์ `end` ของ `yfinance.download()` มีความหมายแบบ **Exclusive** (ไม่รวมวันสุดท้าย) โมดูล Ingestion ต้องส่งค่า `api_end_date = end_date + 1 calendar day` (เช่น ส่ง `end='2026-09-26'` เมื่อต้องการข้อมูลครอบคลุมถึงวันที่ `'2026-09-25'`) แล้วคัดกรองผลลัพธ์ให้อยู่ในช่วง `date <= end_date` |

---

## 2. ข้อกำหนดทางเทคนิคและการแปลงโครงสร้างข้อมูล (Technical & Transformation Contract)

| หัวข้อ | ข้อกำหนด / รายละเอียด |
| :--- | :--- |
| **การปรับราคาและการแปลง Schema จาก `yfinance` (Price Adjustment & Schema Mapping)** | • กำหนดให้เรียกใช้ `yfinance` โดยตั้งค่าพารามิเตอร์ **`auto_adjust=True`** เพียงวิธีเดียวสำหรับทุก `ticker` เพื่อให้ราคาได้รับการปรับปรุงผลกระทบจาก Corporate Actions (เงินปันผล Dividend และการแตกพาร์ Stock Split) ย้อนหลังอย่างสม่ำเสมอ<br>• **กฎการแปลงชื่อคอลัมน์เป็น Schema มาตรฐาน**: เมื่อตั้งค่า `auto_adjust=True` ไลบรารี `yfinance` จะส่งคืนราคาปิดที่ปรับปรุงแล้วภายใต้ชื่อคอลัมน์ **`Close`** (และไม่มีคอลัมน์ `Adj Close` แยกต่างหาก) ดังนั้นขั้นตอน Ingestion Transformation **ต้องทำหน้าที่แปลงชื่อคอลัมน์ `Close` จากผลลัพธ์ของ `yfinance` (ภายใต้โหมด `auto_adjust=True`) ให้เป็นชื่อมาตรฐาน `adjusted_close`** พร้อมจัดโครงสร้างให้อยู่ในรูปแบบ Long Format ตามคีย์ `(date, ticker)`<br>• **การยืนยันราคาอ้างอิงเดียว (Single Canonical Price)**: ยืนยันให้ใช้คอลัมน์ **`adjusted_close`** เพียงคอลัมน์เดียวในการคำนวณผลตอบแทนรายวัน (`simple_return`, `log_return`), ตัวแปรต้น (Features) และตัวแปรตาม (Targets) ทั้งหมดในระบบ ห้ามนำราคา `Close` ที่ยังไม่ปรับปรุงหรือราคา `Open`/`High`/`Low` มาปะปนในการคำนวณผลตอบแทน |
| **นิยามผลตอบแทนรายสินทรัพย์ (Asset Return Definitions)** | คำนวณผลตอบแทนรายวันแยกตามราย `ticker` โดยเรียงลำดับตาม `date` จากอดีตไปปัจจุบัน และใช้ $P_{i,t}^{\text{adj}}$ จากคอลัมน์ `adjusted_close`:<br>1. **Simple Return (`simple_return`)**:<br>$$R_{i,t} = \frac{P_{i,t}^{\text{adj}}}{P_{i,t-1}^{\text{adj}}} - 1$$<br>ใช้สำหรับการตรวจสอบเกณฑ์ความผิดปกติรายวัน (Anomaly Threshold) และการคำนวณผลตอบแทนพอร์ตโฟลิโอในขั้นตอน Downstream<br>2. **Log Return (`log_return`)**:<br>$$r_{i,t} = \ln\left(\frac{P_{i,t}^{\text{adj}}}{P_{i,t-1}^{\text{adj}}}\right) = \ln(1 + R_{i,t})$$<br>ใช้เป็นผลตอบแทนหลักสำหรับคำนวณ Realized Volatility ทั้งในตาราง Feature และตาราง Target |
| **ปฏิทินซื้อขาย (Trading Calendar)** | อิงตามปฏิทินวันทำการของตลาดหลักทรัพย์สหรัฐฯ (**NYSE/NASDAQ Trading Calendar** เช่น ผ่านไลบรารี `exchange_calendars` หรือ `pandas_market_calendars`) เพื่อสร้างชุด **วันที่คาดว่าจะมีการซื้อขาย (Expected Trading Days)** ในช่วง `[actual_fetch_start_date, end_date]` สำหรับใช้ตรวจสอบข้อมูลขาดหาย |
| **มาตรฐานเวลาและเขตเวลา (Timezone & Availability)** | • **เขตเวลาอ้างอิงของตลาด (Market Timezone)**: กำหนดเป็น **`America/New_York`** (ครอบคลุมทั้ง EST และ EDT ตาม Daylight Saving Time) เพื่อระบุวันซื้อขาย `date` ของตลาดสหรัฐฯ อย่างถูกต้องก่อนตัด Timezone ของวันที่ออกเป็น `DATE` (`YYYY-MM-DD`)<br>• **การจัดเก็บเวลา Audit (Audit Timestamp)**: คอลัมน์ `ingested_at_utc` ต้องจัดเก็บเป็นชนิดข้อมูลที่มี Timezone กำกับชัดเจน (`TIMESTAMPTZ` / ISO-8601 UTC เช่น `'2026-09-25T21:00:00Z'`)<br>• **จุดเวลาที่ข้อมูลพร้อมใช้งาน (Data Cut-off)**: ข้อมูลของวันซื้อขาย $t$ จะถือว่าพร้อมใช้งานได้ก็ต่อเมื่อตลาดสหรัฐฯ ปิดทำการแล้ว และกระบวนการ Ingestion ดึงข้อมูลครบทุก `ticker` พร้อมผ่านการตรวจสอบ Validation เสร็จสมบูรณ์ |

---

## 3. เกณฑ์การตรวจสอบคุณภาพข้อมูล (Data Validation Rules)

ระบบต้องรันการตรวจสอบคุณภาพข้อมูลบนชุดข้อมูลที่แปลง Schema แล้วก่อนบันทึกลงตาราง `market_prices_daily`:

1. **ความถูกต้องของ Schema และขอบเขตค่า (Schema & Domain Validity)**:
   - คอลัมน์ทั้งหมดต้องมีชื่อและชนิดข้อมูลตรงตามที่กำหนดใน [datadict.md (หัวข้อ 1)](./datadict.md)
   - `date` ต้องอยู่ในรูปแบบมาตรฐาน `YYYY-MM-DD` และเมื่อจัดกลุ่มตาม `ticker` แล้วต้องเรียงลำดับจากอดีตไปปัจจุบันอย่างเคร่งครัด (Strictly Monotonic Increasing)
   - `ticker` ต้องอยู่ในเซ็ตของสินทรัพย์ที่ระบบรองรับเท่านั้น: `{'SPY', 'IEF', 'GLD'}`
   - `adjusted_close` ต้องเป็นตัวเลขจริง (Finite Float ไม่เป็น `NaN` หรือ $\pm\infty$) และมีค่ามากกว่าศูนย์เสมอ ($\text{adjusted\_close} > 0$)
   - `simple_return` และ `log_return` อนุญาตให้เป็น `Null` ได้เฉพาะแถวแรกสุด (First Observation) ของแต่ละ `ticker` เท่านั้น แถวถัดไปทั้งหมดต้องไม่เป็น `Null` หรือ $\pm\infty$
2. **ความไม่ซ้ำซ้อนของคีย์หลัก (Primary Key Uniqueness)**:
   - ห้ามมีคู่คีย์ `(date, ticker)` ซ้ำกันในตาราง `market_prices_daily` โดยเด็ดขาด (`duplicated_pk_count == 0`)
3. **การตรวจจับความผิดปกติของราคา (Anomaly Detection - Warning Flag)**:
   - **เกณฑ์การตรวจจับ (Symmetric Simple Return Threshold)**: กำหนดเกณฑ์เตือนบนคอลัมน์ **`simple_return`** โดยตรงเมื่อราคาเปลี่ยนแปลงเกิน $\pm 20\%$ ใน 1 วันทำการ:
     $$\text{simple\_return} > 0.20 \quad \text{หรือ} \quad \text{simple\_return} < -0.20 \qquad (|R_{i,t}| > 0.20)$$
     *(หมายเหตุ: กำหนดเกณฑ์บน `simple_return` แทน `|log_return| > ln(1.20)` เนื่องจากในสเกลลอการิทึม การเพิ่มขึ้น $+20\%$ คือ $\ln(1.20) \approx +0.1823$ แต่การลดลง $-20\%$ คือ $\ln(0.80) \approx -0.2231$ ซึ่งไม่สมมาตร การใช้ `simple_return` จึงตรงตามความหมายทางธุรกิจและไม่คลุมเครือ)*
   - **แนวทางปฏิบัติเมื่อพบค่าเกินเกณฑ์**:
     - ตั้งค่าคอลัมน์ `is_anomaly_flagged = True` ในแถวข้อมูลนั้น (ค่าปกติคือ `False`)
     - **ไม่ตัดแถวข้อมูลทิ้งและไม่หยุด Pipeline โดยอัตโนมัติ** เนื่องจากอาจเป็นเหตุการณ์ความผันผวนรุนแรงที่เกิดขึ้นจริงในตลาด (Extreme Market Event)
     - บันทึกรายการแถวที่พบลงใน Audit Log / Quarantine Review Queue เพื่อตรวจสอบยืนยันกับแหล่งข้อมูลสำรองก่อนตัดสินใจ

---

## 4. นโยบายการจัดการข้อมูลขาดหาย การกักกันข้อมูล และข้อผิดพลาด (Missing Data, Quarantine & Failure Policy)

| สถานการณ์ | แนวทางปฏิบัติและผลกระทบต่อการรัน Pipeline |
| :--- | :--- |
| **1. การตรวจสอบวันทำการที่ขาดหาย (Missing Trading Days Check)** | • นำชุดวันที่ของแต่ละ `ticker` ไปเปรียบเทียบกับชุด **Expected Trading Days** จากปฏิทิน NYSE/NASDAQ ในช่วง `[actual_fetch_start_date, config_end_date]`<br>• วันหยุดราชการหรือวันหยุดตลาดที่ทุกสินทรัพย์ไม่มีข้อมูลตามปฏิทิน NYSE/NASDAQ ถือเป็นภาวะปกติ ไม่นับเป็นข้อมูลขาดหาย<br>• หาก `ticker` ใดไม่มีข้อมูลในวันที่ปฏิทินระบุว่าตลาดเปิดทำการจริง ให้ถือเป็น **Hard Validation Error (`MISSING_TRADING_DAY`)**<br>• **ข้อห้ามเด็ดขาด**: **ห้ามใช้ Forward-fill, Backward-fill หรือ Interpolation ข้ามวันทำการโดยพลการ** เพื่อสร้างราคาหรือผลตอบแทนเทียม เว้นแต่จะมีเหตุผลทางธุรกิจที่ระบุและอนุมัติไว้ในสเปกอย่างชัดเจน |
| **2. การกักกันข้อมูลและขอบเขตการหยุดทำงานแยกตามระดับ (Quarantine Impact: Per-Ticker vs. Portfolio & Dashboard Behavior)** | เมื่อพบแถวข้อมูลที่ไม่ผ่านเกณฑ์บังคับ (เช่น `adjusted_close <= 0`, ค่าเป็น `Null`/`Inf` ผิดตำแหน่ง, PK ซ้ำ, หรือวันทำการขาดหาย) ระบบต้องแยกแถวที่มีปัญหาเข้าสู่ตารางกักกัน (`market_prices_quarantine`) และบังคับใช้พฤติกรรมของระบบในแต่ละชั้นดังนี้:<br>1. **ระดับการดึงข้อมูลและพยากรณ์รายสินทรัพย์ (Per-Ticker Ingestion & Per-Asset Prediction)**:<br>   - **หยุดการประมวลผลเฉพาะ `ticker` ที่พบข้อผิดพลาด (Fail-fast เฉพาะ Ticker)** โดยไม่ส่งข้อมูลของ `ticker` ที่มีปัญหาเข้าสู่ Feature/Target Pipeline<br>   - **สินทรัพย์ (`ticker`) อื่นที่ผ่านการตรวจสอบครบทุกเงื่อนไข ยังคงสร้าง Feature และรันโมเดลเพื่อสร้างค่าพยากรณ์ความผันผวนรายสินทรัพย์ ($\hat{\sigma}_{i,t}$) ได้ตามปกติ**<br>2. **ระดับการคำนวณความเสี่ยงพอร์ตโฟลิโอ (Downstream Portfolio Risk Calculation)**:<br>   - การคำนวณความผันผวนของพอร์ตโฟลิโอ ณ วัน $t$ **ต้องมีข้อมูลครบทั้ง 3 สินทรัพย์ (`SPY`, `IEF`, `GLD`)**<br>   - หากค่าพยากรณ์ความผันผวน ($\hat{\sigma}_{i,t}$) ของ `ticker` ใดตัวหนึ่งขาดหาย หรือเมทริกซ์สหสัมพันธ์ (`asset_rolling_correlations`) ของวันนั้นไม่พร้อมใช้งาน (`is_corr_ready == False`) **ระบบต้องระงับการคำนวณและไม่แสดงค่าความเสี่ยงพอร์ตโฟลิโอของวันนั้น (`portfolio_vol = Null`, `status = 'INCOMPLETE_INPUTS'`)**<br>3. **ระดับการแสดงผลบนหน้าจอผู้ใช้ (Dashboard / Reporting UI Behavior)**:<br>   - หน้า Dashboard **ต้องแสดงสถานะแจ้งเตือนว่า "ข้อมูลไม่ครบถ้วนสำหรับการคำนวณความเสี่ยงพอร์ตโฟลิโอ" (พร้อมระบุ `ticker` ที่ติดสถานะ Quarantine/Missing)** ขณะที่ยังสามารถแสดงกราฟหรือค่าพยากรณ์ของสินทรัพย์รายตัวที่ผ่านการตรวจสอบได้<br>   - **ห้ามนำสินทรัพย์ที่เหลือมาปรับน้ำหนักใหม่เองหรือคำนวณความเสี่ยงพอร์ตโฟลิโอแบบไม่ครบองค์ประกอบโดยเงียบๆ (No Silent Partial Portfolio Calculation) โดยเด็ดขาด** |
| **3. การบันทึกสถิติการตรวจสอบและเหตุผลการกักกัน (Mandatory Validation & Quarantine Audit Logging)** | ทุกครั้งที่รัน Ingestion Pipeline ต้องบันทึกข้อมูลสรุปผลการตรวจสอบลงในตาราง/ไฟล์ `ingestion_run_audit_log` อย่างครบถ้วน โดยแยกความหมายของรหัสอ้างอิงอย่างชัดเจน:<br>• **`source_batch_id`**: รหัสประจำชุดข้อมูลดิบ (Data Batch ID เช่น `'yf_batch_20260925_01'`) ที่ดึงมาจาก `yfinance` ในรอบนั้น และส่งต่อไปยังตาราง Downstream ทุกตารางโดยไม่เปลี่ยนค่า<br>• **`run_id`**: รหัสประจำการรัน Pipeline ในรอบการประมวลผลนั้น (Pipeline Execution Run ID เช่น `'ing_run_20260925_001'`) ซึ่งผูกกับพารามิเตอร์ `config_start_date`, `config_end_date`, `actual_fetch_start_date` และเวลา `executed_at_utc`<br>• **จำนวนแถวก่อนและหลังตรวจสอบ (Row Counts)**:<br>  - `rows_fetched_raw` (จำนวนแถวดิบที่ดึงได้ก่อนตรวจสอบ แยกตาม `ticker` และรวมทั้งหมด)<br>  - `rows_validated_passed` (จำนวนแถวที่ผ่านเกณฑ์และบันทึกลง `market_prices_daily` แยกตาม `ticker`)<br>  - `rows_quarantined` (จำนวนแถวที่ถูกแยกเข้ากักกัน แยกตาม `ticker`)<br>  - `rows_anomaly_flagged` (จำนวนแถวที่ `is_anomaly_flagged = True` แยกตาม `ticker`)<br>• **รายละเอียดแถวที่ถูกกักกัน (`quarantine_records`)**: ต้องบันทึก `run_id`, `source_batch_id`, `date`, `ticker`, ค่าราคาดิบที่พบ, และรหัสสาเหตุมาตรฐาน (`UPPER_SNAKE_CASE` `quarantine_reason`) ได้แก่ `NON_POSITIVE_PRICE`, `NULL_REQUIRED_FIELD`, `DUPLICATE_PRIMARY_KEY`, `MISSING_EXPECTED_TRADING_DAY`, หรือ `UNVERIFIED_EXTREME_ANOMALY` |
