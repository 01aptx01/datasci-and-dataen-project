# ขั้นที่ 2: กำหนด Feature Contract สำหรับการทำนายความผันผวนรายสินทรัพย์ (Asset-Level Volatility Forecasting)

> **Feature Contract** คือข้อตกลงและพันธสัญญาระดับ Feature Engineering ที่กำหนด**กติกาการสร้างและตรวจสอบตัวแปรต้นรายสินทรัพย์ (Asset-Level Features)** เพื่อใช้ทำนายความผันผวนจริงล่วงหน้า 5 วันทำการ (`target_realized_vol_5d`) ของแต่ละหลักทรัพย์ (`SPY`, `IEF`, `GLD`) โดยครอบคลุมสูตรคำนวณ, หน้าต่างเวลาย้อนหลัง (Lookback Window), การจัดแนวข้อมูลตามเวลา (Point-in-Time Alignment), นโยบายจัดการค่าว่าง และเกณฑ์การตรวจสอบคุณภาพก่อนส่งเข้าโมเดล Machine Learning
>
> สำหรับรายละเอียดคำอธิบายคอลัมน์ ชนิดข้อมูล (Type) หน่วยวัด (Unit) บทบาท (Role) และเงื่อนไข Nullable ของตาราง `asset_volatility_features` และตารางข้อมูลประกอบ `asset_rolling_correlations` ให้อ้างอิงจากแหล่งข้อมูลกลางที่ **[datadict.md](./datadict.md)**

---

## สรุปภาพรวม (TL;DR)

1. **เป้าหมายหลักและระดับของข้อมูล (Objective & Granularity)**:
   - สร้างตาราง `asset_volatility_features` ที่มีระดับหน่วยข้อมูล (Grain) เป็น **1 แถว ต่อ 1 สินทรัพย์ (`ticker`) ณ สิ้นวันซื้อขาย `date` ($t$)** เพื่อใช้ทำนายความผันผวนจริงในอีก 5 วันทำการถัดไป ($t+1$ ถึง $t+5$) ของสินทรัพย์แต่ละตัว (`SPY`, `IEF`, `GLD`)
   - **การแยกขั้นตอนคำนวณความเสี่ยงพอร์ตโฟลิโอ (Downstream Portfolio Aggregation)**: โมเดล Machine Learning ไม่ได้ทำนายความผันผวนของพอร์ตคงที่โดยตรง แต่ทำนายความผันผวนรายสินทรัพย์ ($\hat{\sigma}_{\text{SPY},t}, \hat{\sigma}_{\text{IEF},t}, \hat{\sigma}_{\text{GLD},t}$) ก่อน จากนั้นจึงนำค่าพยากรณ์ทั้ง 3 สินทรัพย์ไปคำนวณรวมกับน้ำหนักพอร์ตที่ผู้ใช้กำหนด (เช่น ค่าเริ่มต้นสาธิต `50/30/20`) และค่าสหสัมพันธ์ระหว่างสินทรัพย์ (`asset_rolling_correlations`) ในขั้นตอน Downstream ตามที่กำหนดไว้ใน **[target_contract.md](./target_contract.md)**
2. **ราคาตั้งต้นมาตรฐาน (Price Input)**: ใช้คอลัมน์ **`adjusted_close`** จากตาราง `market_prices_daily` ตาม [data_contract.md](./data_contract.md) เป็นฐานในการคำนวณผลตอบแทนและตัวแปรต้นทั้งหมด
3. **ขอบเขตเวลา (Point-in-Time)**: Feature ทุกตัวของสินทรัพย์ $i$ ในแถววันที่ $t$ ต้องคำนวณจากข้อมูลย้อนหลังถึงสิ้นวัน $t$ เท่านั้น (**ห้าม**ใช้ข้อมูลหลังวัน $t$ โดยเด็ดขาด)
4. **การแยกความพร้อมของ Feature (`is_model_ready`) ออกจากความพร้อมของ Target (`is_label_mature`)**:
   - **โหมดพยากรณ์ใช้งานจริง (Live Inference ณ วัน $t$)**: ใช้เฉพาะตาราง `asset_volatility_features` ที่ `is_model_ready == True` โดยไม่มีคอลัมน์ Target และไม่ต้องรอให้ข้อมูลอนาคตครบ 5 วัน
   - **โหมดฝึกและประเมินผลโมเดล (Training & Evaluation)**: นำตาราง Feature ไป Join กับตาราง `asset_volatility_labels` ด้วยคีย์ `(date, ticker)` โดยคัดเฉพาะแถวที่ `is_warmup_buffer == False`, `is_model_ready == True` และ `is_label_mature == True` เท่านั้น
   - การแบ่ง Train / Validation / Test ต้องแบ่งตามลำดับเวลาและเว้นระยะตัดขาด (**Purge / Embargo Gap อย่างน้อย 5 วันซื้อขาย**) รวมถึงบังคับให้ **Fit ตัวแปลงข้อมูล (Scaler/Preprocessor) บนชุด Train เท่านั้น**

---

## 1. ขอบเขตและมิติเวลาของข้อมูล (Scope & Time Dimension)

| หัวข้อ | ข้อกำหนดและรายละเอียด |
| :--- | :--- |
| **วัตถุประสงค์ (Objective)** | สร้างตาราง `asset_volatility_features` สำหรับเป็นตัวแปรต้น ($X$) ในการทำนายความผันผวนจริงรายสินทรัพย์ล่วงหน้า 5 วันซื้อขาย ($t+1$ ถึง $t+5$) และสร้างตารางประกอบ `asset_rolling_correlations` สำหรับส่งให้ขั้นตอนคำนวณความเสี่ยงพอร์ตโฟลิโอในระดับ Downstream |
| **ระดับหน่วยข้อมูล (Granularity)** | • ตารางหลัก `asset_volatility_features`: **1 แถว ต่อ 1 สินทรัพย์ (`ticker`) ณ วันซื้อขาย `date` ($t$)**<br>• ตารางประกอบ `asset_rolling_correlations`: **1 แถว ต่อ 1 วันซื้อขาย `date` ($t$)** |
| **คีย์หลัก (Primary Key)** | `(date, ticker)` สำหรับตาราง `asset_volatility_features` |
| **สินทรัพย์ที่รองรับ (Assets)** | `SPY` (หุ้นสหรัฐฯ), `IEF` (พันธบัตรรัฐบาลสหรัฐฯ), `GLD` (ทองคำ) |
| **นโยบายน้ำหนักพอร์ตโฟลิโอ (Downstream Portfolio Weights)** | **ไม่ผูกน้ำหนักพอร์ตโฟลิโอเข้ากับตาราง Training Features หรือ Labels**<br>• น้ำหนักพอร์ตโฟลิโอ $w = (w_{\text{SPY}}, w_{\text{IEF}}, w_{\text{GLD}})$ จะถูกรับเข้ามาในขั้นตอนคำนวณความเสี่ยงพอร์ตโฟลิโอ (Downstream Inference / Risk Calculator) เมื่อผู้ใช้ร้องขอ<br>• ค่าสัดส่วน เช่น **`50/30/20`** ($w_{\text{SPY}}=0.50, w_{\text{IEF}}=0.30, w_{\text{GLD}}=0.20$) หรือ Equal Weight ใช้เป็นเพียง**ค่าเริ่มต้นสำหรับการสาธิต (Configurable Default)** ที่ผู้ใช้ปรับเปลี่ยนได้โดยไม่ต้องฝึกโมเดลใหม่ |
| **คอลัมน์ราคาตั้งต้น (Input Price Column)** | **`adjusted_close`** จากตาราง `market_prices_daily` เท่านั้น (สอดคล้องกับ [data_contract.md](./data_contract.md)) |
| **เขตเวลาอ้างอิง (Market Timezone)** | **`America/New_York`** (ครอบคลุมทั้ง EST/EDT) สำหรับกำหนดวันซื้อขาย `date` |
| **เวลาที่ข้อมูลพร้อมใช้ (Data Availability Cut-off)** | สร้างได้**หลังจากกระบวนการ Data Ingestion ยืนยันว่าดึงและตรวจสอบข้อมูลปิดตลาดของวัน $t$ เสร็จสมบูรณ์แล้ว (Ingestion Complete & Validated)** |
| **ข้อมูลที่ห้ามใช้ (Forbidden Data)** | ข้อมูลราคาหรือตัวแปรใดๆ ที่เกิดขึ้นหลังเวลาปิดตลาดวัน $t$ ($t+1, t+2, \dots$) และห้ามนำคอลัมน์จากตาราง Target เข้ามาในเมทริกซ์ $X$ |
| **การติดตามเวอร์ชันและ Lineage (Versioning & Lineage Metadata)** | บันทึก `feature_set_version = '2.0.0'`, `run_id`, `source_batch_id` และเวลาที่สร้างแถวในรูป `TIMESTAMPTZ` (UTC) ในคอลัมน์ `feature_as_of_utc` |

---

## 2. มาตรฐานการตั้งชื่อและโครงสร้างสคีมาสรุป (Naming Conventions & Output Schema Summary)

### 2.1 กฎการตั้งชื่อคอลัมน์ (Naming Conventions)

เนื่องจากตาราง `asset_volatility_features` มีคีย์หลักเป็น `(date, ticker)` ชื่อคอลัมน์ตัวแปรต้นจึงเป็นชื่อมาตรฐานเดียวกันทุกสินทรัพย์ (ไม่ต้องแยกเป็น `ret_spy_t`, `ret_ief_t` คนละคอลัมน์ในแถวเดียวกัน):
- `ret_1d_t`: ผลตอบแทนลอการิทึมรายวันของสินทรัพย์ `ticker` ณ สิ้นวัน $t$ ($r_{i,t}$)
- `ret_lag_<k>d`: ผลตอบแทนลอการิทึมรายวันของสินทรัพย์ `ticker` ย้อนหลัง $k$ วันทำการเทียบกับวัน $t$ ($r_{i,t-k}$ เช่น `ret_lag_1d`, `ret_lag_2d`)
- `ret_trailing_<n>d`: ผลตอบแทนสะสมแบบธรรมดาย้อนหลัง $n$ วันทำการ สิ้นสุดที่วัน $t$ ของสินทรัพย์ `ticker` (เช่น `ret_trailing_5d`, `ret_trailing_20d`)
- `rv_<n>d`: ค่าความผันผวนจริงย้อนหลัง (Annualized Realized Volatility) จากหน้าต่าง $n$ วันทำการ สิ้นสุดที่วัน $t$ ของสินทรัพย์ `ticker` (เช่น `rv_5d`, `rv_20d`, `rv_60d`)

### 2.2 โครงสร้างคอลัมน์ที่ Pipeline ต้องส่งออกและการคัดเข้าเมทริกซ์ $X$ (Output Schema Contract)

> รายละเอียดชนิดข้อมูล (Type), หน่วย (Unit), ความหมายรายคอลัมน์ และเงื่อนไข Nullable ดูได้ที่ **[datadict.md (หัวข้อ 2 และ 4)](./datadict.md)**

| ตาราง (Table) | กลุ่มคอลัมน์ (Column Group) | รายชื่อคอลัมน์ | การนำเข้าเมทริกซ์โมเดล ($X$) ของแต่ละ `ticker` |
| :--- | :--- | :--- | :--- |
| `asset_volatility_features` | **Primary Keys** | `date`, `ticker` | **ห้ามนำเข้า $X$ อัตโนมัติ** (ใช้เป็น Index, Join Key และตัวกรองแยกข้อมูลตาม `ticker`) |
| `asset_volatility_features` | **Core Return Features (5 ตัว)** | `ret_1d_t`, `ret_lag_1d`, `ret_lag_2d`, `ret_trailing_5d`, `ret_trailing_20d` | **นำเข้า $X$ (บังคับ - Baseline)** |
| `asset_volatility_features` | **Core Volatility Features (3 ตัว)** | `rv_5d`, `rv_20d`, `rv_60d` | **นำเข้า $X$ (บังคับ - Baseline)** |
| `asset_volatility_features` | **Experimental Features (2 ตัว)** | `rsi_14d`, `bb_width_20d` | นำเข้า $X$ เฉพาะรอบการทดลองที่ตั้งค่าเปิดใช้งาน |
| `asset_volatility_features` | **Status & Lineage Metadata** | `is_model_ready`, `is_warmup_buffer`, `feature_set_version`, `run_id`, `source_batch_id`, `feature_as_of_utc` | **ห้ามนำเข้า $X$ โดยเด็ดขาด** |
| `asset_rolling_correlations` | **Downstream Portfolio Inputs** | `date`, `corr_spy_ief_20d`, `corr_spy_gld_20d`, `corr_ief_gld_20d`, `is_corr_ready`, `run_id`, `source_batch_id`, `computed_at_utc` | **ไม่นำเข้า $X$ ของโมเดลรายสินทรัพย์** (ใช้ในขั้นตอนคำนวณความเสี่ยงพอร์ตโฟลิโอ Downstream) |

---

## 3. กติกาและสูตรการคำนวณ Feature รายสินทรัพย์ (Core Feature Generation Rules)

### 3.1 สูตรผลตอบแทนรายสินทรัพย์ (Per-Asset Return Formulas)

กำหนดให้ $P_{i,t}^{\text{adj}}$ คือค่าจากคอลัมน์ `adjusted_close` ของสินทรัพย์ $i \in \{\text{SPY}, \text{IEF}, \text{GLD}\}$ ณ วันซื้อขาย $t$:

1. **Simple Return รายวันของสินทรัพย์ $i$**:
   $$R_{i,t} = \frac{P_{i,t}^{\text{adj}}}{P_{i,t-1}^{\text{adj}}} - 1$$
2. **Log Return รายวันของสินทรัพย์ $i$ (`ret_1d_t`)**:
   $$r_{i,t} = \ln\left(\frac{P_{i,t}^{\text{adj}}}{P_{i,t-1}^{\text{adj}}}\right) = \ln(1 + R_{i,t})$$
3. **Lagged Log Returns ย้อนหลัง $k$ วันทำการ (`ret_lag_1d`, `ret_lag_2d`)**:
   $$\text{ret\_lag\_}k\text{d}_{i,t} = r_{i,t-k}, \qquad k \in \{1, 2\}$$
4. **Trailing Cumulative Return ย้อนหลัง $n$ วันทำการ (`ret_trailing_5d`, `ret_trailing_20d`)**:
   $$\text{ret\_trailing\_}n\text{d}_{i,t} = \frac{P_{i,t}^{\text{adj}}}{P_{i,t-n}^{\text{adj}}} - 1 = \exp\left(\sum_{j=0}^{n-1} r_{i,t-j}\right) - 1, \qquad n \in \{5, 20\}$$

*(หมายเหตุ: สำหรับสูตรการคำนวณผลตอบแทนและความผันผวนของพอร์ตโฟลิโอจากน้ำหนัก $w_i$ ได้ย้ายไปกำหนดไว้ในส่วน Downstream Portfolio Risk Calculation ของ [target_contract.md](./target_contract.md) เพื่อให้แยกขาดจาก Feature ของโมเดลรายสินทรัพย์อย่างชัดเจน)*

### 3.2 สูตรมาตรฐานสำหรับ Realized Volatility รายสินทรัพย์ ($RV_{i,n,t}$) และความสอดคล้องของสเกล

สำหรับสินทรัพย์ $i \in \{\text{SPY}, \text{IEF}, \text{GLD}\}$ และขนาดหน้าต่างย้อนหลัง $n \in \{5, 20, 60\}$ วันทำการ กำหนดให้คำนวณ **Annualized Realized Volatility** จากผลตอบแทนลอการิทึมรายวัน $r_{i,t}$ ของสินทรัพย์นั้นบนฐาน 252 วันทำการต่อปี:

$$RV_{i,n,t} = \sqrt{\frac{252}{n} \sum_{j=0}^{n-1} r_{i,t-j}^{2}}$$

- **ความสอดคล้องของสเกลระหว่าง Historical Features และ Target (Scale & Formula Alignment)**:
  - ทั้งตัวแปรต้นความผันผวนย้อนหลัง (`rv_5d`, `rv_20d`, `rv_60d`) และตัวแปรตาม (`target_realized_vol_5d` ใน [target_contract.md](./target_contract.md)) **ใช้สูตร Root-Mean-Square ของ Log Return แบบไม่หักค่าเฉลี่ย (Zero-mean assumption) และปรับสเกลเป็นรายปีด้วยตัวคูณ $\sqrt{252}$ (หน่วยเป็น Annualized Decimal เช่น `0.15` หมายถึง $15\%$ ต่อปี) เหมือนกันทุกประการ**
  - ห้ามสลับไปใช้ Sample Standard Deviation ที่หักค่าเฉลี่ยในบางคอลัมน์ หรือใช้สเกลรายวัน (Daily Scale) ปะปนกับสเกลรายปี (Annualized Scale) เพื่อให้โมเดลตระกูล Autoregressive / HAR-RV และ Tree-based เรียนรู้ความสัมพันธ์ในหน่วยเดียวกันโดยตรง

### 3.3 ตารางกติกาการคำนวณและช่วงเตือนเบื้องต้นราย Feature (Per-Asset Feature Specification)

| Feature Name | Table | สูตรการคำนวณ ณ วัน $t$ (สำหรับสินทรัพย์ $i$) | Lookback | Minimum Valid Observations | Initial Heuristic Alert Range (แยกตามสินทรัพย์) |
| :--- | :--- | :--- | :---: | :--- | :--- |
| `ret_1d_t` | `asset_volatility_features` | $r_{i,t} = \ln(P_{i,t}^{\text{adj}} / P_{i,t-1}^{\text{adj}})$ | 1 วัน | ผลตอบแทน 1 ค่า (ราคา 2 จุด: $t, t-1$) | `SPY`: $[-0.15, 0.15]$<br>`IEF`, `GLD`: $[-0.10, 0.10]$ |
| `ret_lag_1d` | `asset_volatility_features` | $r_{i,t-1}$ | 2 วัน | ผลตอบแทน 2 ค่า (ราคา 3 จุด: $t \dots t-2$) | `SPY`: $[-0.15, 0.15]$<br>`IEF`, `GLD`: $[-0.10, 0.10]$ |
| `ret_lag_2d` | `asset_volatility_features` | $r_{i,t-2}$ | 3 วัน | ผลตอบแทน 3 ค่า (ราคา 4 จุด: $t \dots t-3$) | `SPY`: $[-0.15, 0.15]$<br>`IEF`, `GLD`: $[-0.10, 0.10]$ |
| `ret_trailing_5d` | `asset_volatility_features` | $(P_{i,t}^{\text{adj}} / P_{i,t-5}^{\text{adj}}) - 1$ | 5 วัน | ผลตอบแทน 5 ค่า (ราคา 6 จุด: $t \dots t-5$) | `SPY`: $[-0.25, 0.25]$<br>`IEF`, `GLD`: $[-0.18, 0.18]$ |
| `ret_trailing_20d` | `asset_volatility_features` | $(P_{i,t}^{\text{adj}} / P_{i,t-20}^{\text{adj}}) - 1$ | 20 วัน | ผลตอบแทน 20 ค่า (ราคา 21 จุด: $t \dots t-20$) | `SPY`: $[-0.40, 0.40]$<br>`IEF`, `GLD`: $[-0.30, 0.30]$ |
| `rv_5d` | `asset_volatility_features` | $\sqrt{\frac{252}{5} \sum_{j=0}^{4} r_{i,t-j}^{2}}$ | 5 วัน | ผลตอบแทน 5 ค่า (ราคา 6 จุด) | `SPY`: $[0.02, 1.50]$<br>`IEF`, `GLD`: $[0.01, 1.00]$ |
| `rv_20d` | `asset_volatility_features` | $\sqrt{\frac{252}{20} \sum_{j=0}^{19} r_{i,t-j}^{2}}$ | 20 วัน | ผลตอบแทน 20 ค่า (ราคา 21 จุด) | `SPY`: $[0.02, 1.20]$<br>`IEF`, `GLD`: $[0.01, 0.80]$ |
| `rv_60d` | `asset_volatility_features` | $\sqrt{\frac{252}{60} \sum_{j=0}^{59} r_{i,t-j}^{2}}$ | 60 วัน | ผลตอบแทน 60 ค่า (ราคา 61 จุด) | `SPY`: $[0.03, 1.00]$<br>`IEF`, `GLD`: $[0.02, 0.70]$ |
| `corr_spy_ief_20d`<br>`corr_spy_gld_20d`<br>`corr_ief_gld_20d` | `asset_rolling_correlations` *(Downstream Historical Proxy)* | $\text{corr}_{20d}(r_{A, t-19\dots t}, r_{B, t-19\dots t})$ | 20 วัน | วันที่ตรงกันครบทั้ง 3 สินทรัพย์จำนวน 20 วันทำการ (Synchronized Window) | ค่าระหว่าง $[-1.0, 1.0]$ และเมทริกซ์ $3\times 3$ ต้องเป็น Symmetric & PSD |

### 3.4 กติกาการสร้างและตรวจสอบตารางสหสัมพันธ์ย้อนหลัง (`asset_rolling_correlations`) สำหรับขั้นตอน Downstream

1. **สถานะเป็นค่าประมาณจากอดีต (Historical Proxy Only)**:
   - ค่า `corr_spy_ief_20d`, `corr_spy_gld_20d`, `corr_ief_gld_20d` ณ วันอ้างอิง $t$ คำนวณจากผลตอบแทนลอการิทึมย้อนหลัง 20 วันทำการถึงวัน $t$ ($\{t-19, \dots, t\}$) เพื่อใช้เป็น **Historical Proxy** แทนความสัมพันธ์ระหว่างสินทรัพย์ในช่วง 5 วันข้างหน้า ($[t+1, t+5]$)
   - ค่าเหล่านี้**ไม่ใช่ค่าสหสัมพันธ์ที่พยากรณ์จากโมเดลสำหรับ 5 วันข้างหน้า** และต้องระบุข้อจำกัดนี้ในรายงานและหน้า Dashboard เสมอ
2. **การใช้ช่วงวันที่เดียวกันและข้อมูลที่จับคู่ครบทั้ง 3 สินทรัพย์ (Synchronized Complete-Case Window)**:
   - การคำนวณสหสัมพันธ์ทั้ง 3 คู่ ณ วัน $t$ **ต้องใช้เมทริกซ์ผลตอบแทนขนาด $20 \times 3$ จากช่วงวันที่ทำการ 20 วันชุดเดียวกันพอดี** ที่มีข้อมูลผลตอบแทนของทั้ง `SPY`, `IEF` และ `GLD` ครบทุกตัวพร้อมกัน (Complete-case Inner Alignment)
   - ห้ามคำนวณ Pairwise Correlation แยกคู่โดยใช้ชุดวันที่ไม่ตรงกัน (เช่น กรณีมีสินทรัพย์หนึ่งแหว่งในบางวัน) เพราะจะทำให้เมทริกซ์สหสัมพันธ์รวมไม่สอดคล้องกันทางคณิตศาสตร์
3. **การตรวจสอบสมบัติของเมทริกซ์สหสัมพันธ์และเมทริกซ์ความแปรปรวนร่วม (Matrix Symmetry & Positive Semidefinite Validation)**:
   - เมื่อประกอบค่าสหสัมพันธ์ทั้ง 3 คู่เข้าเป็นเมทริกซ์ $\mathbf{R}_t \in \mathbb{R}^{3 \times 3}$ (โดยมีแนวทแยงมุมหลักเป็น $1.0$) ระบบต้องตรวจสอบว่า:
     1. **Pairwise Bounds**: สมาชิกนอกแนวทแยงทุกตัวอยู่ในช่วง $[-1.0, 1.0]$
     2. **Symmetry**: $\mathbf{R}_t = \mathbf{R}_t^\top$ (และเมื่อรวมกับ $\hat{\sigma}_{i,t}$ เป็นเมทริกซ์ความแปรปรวนร่วม $\hat{\boldsymbol{\Sigma}}_t$ ต้องสมมาตรเช่นกัน คือ $\|\hat{\boldsymbol{\Sigma}}_t - \hat{\boldsymbol{\Sigma}}_t^\top\|_{\max} \le 10^{-12}$)
     3. **Positive Semidefiniteness (PSD)**: ค่าเจาะจงต่ำสุด (Minimum Eigenvalue) ต้องไม่ติดลบ ($\lambda_{\min}(\mathbf{R}_t) \ge -10^{-10}$ ตามความละเอียด Floating-point) เพื่อรับประกันว่าความแปรปรวนของพอร์ตโฟลิโอ $\mathbf{w}^\top \hat{\boldsymbol{\Sigma}}_t \mathbf{w} \ge 0$ สำหรับทุกเวกเตอร์น้ำหนัก $\mathbf{w}$
   - เฉพาะแถววันที่ $t$ ที่ผ่านเงื่อนไขครบทั้ง 3 ข้อเท่านั้นจึงจะตั้งค่า `is_corr_ready = True`

> [!NOTE]
> **นโยบายการใช้ค่าเตือนเบื้องต้นตามสินทรัพย์ (Asset-Specific Heuristic Alert Policy)**:
> 1. ค่าในคอลัมน์ **Initial Heuristic Alert Range** ที่แตกต่างกันตามสินทรัพย์ (`SPY` เทียบกับ `IEF` และ `GLD`) เป็นเพียง**ค่าเตือนเบื้องต้นจากความรู้โดเมน (Initial Heuristic Bounds)** เท่านั้น ก่อนนำไปใช้จริงในระบบแจ้งเตือน ต้องนำข้อมูลจริงเฉพาะในชุด **Training Set** มาคำนวณการแจกแจงเชิงประจักษ์ (เช่น Percentile ที่ 0.1% และ 99.9%) เพื่อสอบทานและปรับเทียบ (Calibrate) เกณฑ์อีกครั้ง
> 2. ค่าที่อยู่นอกช่วง Alert Range **ไม่ถือเป็นข้อมูลเสียที่ต้องลบแถวหรือหยุด Pipeline อัตโนมัติ** (ตราบใดที่ไม่ใช่ `NaN`, $\pm\infty$, หรือความผันผวนติดลบ) ให้บันทึกเป็น Warning ใน Audit Log เพื่อตรวจสอบว่าเป็นเหตุการณ์ตลาดผันผวนจริงหรือไม่

---

## 4. กติกาสำหรับชุด Feature ทดลองรายสินทรัพย์ (Experimental Feature Rules - Optional)

เพื่อให้ตาราง `asset_volatility_features` มีโครงสร้างสม่ำเสมอในระดับ `(date, ticker)` และรองรับการเปรียบเทียบโมเดลของทั้ง 3 สินทรัพย์ จึงกำหนดให้คำนวณตัวชี้วัดทางเทคนิคสำหรับการทดลองให้**ครบทุก `ticker` (`SPY`, `IEF`, `GLD`)** จากราคา `adjusted_close` ของสินทรัพย์นั้นๆ:

| Feature Name | Input Columns | สูตรและพารามิเตอร์ (คำนวณแยกตาม `ticker` $i$) | Lookback | Minimum Valid Observations | Anomaly / Theoretical Range |
| :--- | :--- | :--- | :---: | :--- | :---: |
| `rsi_14d` | `adjusted_close` ของ `ticker` $i$ | Wilder's Smoothing RSI: $100 - \frac{100}{1 + RS_{i,14,t}}$ | 14 วัน | การเปลี่ยนแปลงราคาครบ 14 ค่า (ราคา 15 จุด) | $[0.0, 100.0]$ (Theoretical Bound) |
| `bb_width_20d` | `adjusted_close` ของ `ticker` $i$ | $\frac{\text{Upper}_{i}(20, 2\sigma) - \text{Lower}_{i}(20, 2\sigma)}{\text{SMA}_{i,20,t}} = \frac{4 \cdot s_{P_{i}, 20, t}}{\text{SMA}_{i,20,t}}$ | 20 วัน | ราคาปิดปรับปรุงแล้วครบ 20 จุด | $[0.001, 0.60]$ (ค่าต้อง $\ge 0$ เสมอ) |

> **ขอบเขตและกติกาการทดลอง (Experimentation Governance)**:
> - `rsi_14d` และ `bb_width_20d` **ไม่ถือเป็นชุดฟีเจอร์มาตรฐาน (Core Features)** โดย Baseline Model ของทุกสินทรัพย์ต้องฝึกและวัดผลด้วย **Core Features ทั้ง 8 ตัว** ก่อนเสมอ
> - ในขั้นตอน Model Experimentation สามารถทดลองเปิดใช้ `rsi_14d` และ/หรือ `bb_width_20d` สำหรับแต่ละ `ticker` (เช่น ทดลองเปิดใช้เฉพาะโมเดลของ `SPY` หรือเปิดใช้ครบทั้ง `SPY`, `IEF`, `GLD`) และจะนำเข้าสู่ชุดฟีเจอร์ใช้งานจริงของสินทรัพย์ใดก็ต่อเมื่อผลการทดสอบบน Validation Set (ผ่าน Purged Walk-Forward CV) ยืนยันว่าลดค่า Error ลงอย่างมีนัยสำคัญเท่านั้น

---

## 5. กฎด้านเวลา การแบ่งชุดข้อมูล และการป้องกัน Data Leakage (Point-in-Time, Splitting & Preprocessing Rules)

1. **กฎการตัดเวลา (Strict Point-in-Time Cut-off Rule)**:
   $$\mathcal{F}_{i,t} = \{P_{i,s}^{\text{adj}} \mid s \le t\}$$
   ทุก Feature ของสินทรัพย์ $i$ ณ แถววันที่ $t$ ต้องคำนวณจากข้อมูลใน $\mathcal{F}_{i,t}$ เท่านั้น ห้ามมีขั้นตอนใดอ้างอิงข้อมูลของวัน $s > t$
2. **การจัดแนว Rolling Window (Window Alignment)**:
   - หน้าต่างย้อนหลังทุกตัว (`rolling(window=n, min_periods=n)`) ต้องเป็นแบบ Right-closed สิ้นสุดที่วัน $t$ พอดี และต้องจัดกลุ่มแยกตาม `ticker` (`partition_by="ticker"` หรือ `groupby("ticker")`) ก่อนคำนวณเสมอ เพื่อไม่ให้ข้อมูลข้ามสินทรัพย์ปะปนกัน
   - ห้ามใช้ `shift(-k)` โดยที่ $k > 0$ ในขั้นตอนสร้าง Feature โดยเด็ดขาด
3. **การผูกกฎ Purge / Embargo เข้ากับวิธีการแบ่งข้อมูล (Split Implementation & Purge Rule)**:
   - **ห้ามใช้ Random Split หรือ K-Fold ปกติที่สลับลำดับเวลา** การแบ่งชุดข้อมูลต้องเรียงตามเวลา (Chronological Split เช่น Train / Validation / Test หรือ Expanding-Window Walk-Forward Cross-Validation)
   - เนื่องจากตัวแปรตาม `target_realized_vol_5d` ณ วันอ้างอิง $t$ ใช้ผลตอบแทนของวัน $t+1, t+2, t+3, t+4, t+5$ ดังนั้นในการ Implement ตัวแบ่งชุดข้อมูลทุกจุดตัดเวลา (เช่น จุดตัดระหว่างชุด Train สิ้นสุดที่วัน $t_{\text{split}}$ และชุด Validation เริ่มที่วัน $t_{\text{val\_start}}$):
     - **บังคับตัดแถวฝึกสอนช่วงท้ายออกอย่างน้อย 5 วันทำการ (Purge Window = 5 Trading Days)**: แถวข้อมูลในชุดก่อนหน้าที่มี `target_end_date >= t_val_start` (คือ 5 วันทำการสุดท้ายก่อนจุดตัด) **ต้องถูกตัดออกจากชุดฝึกสอน (Purged)** เพื่อรับประกันว่าหน้าต่างคำนวณ Target ของชุด Train สิ้นสุดลงก่อนหรือภายในขอบเขตเวลาของชุด Train เท่านั้น ไม่ล้ำเข้าไปในชุด Validation/Test
4. **กฎการ Fit Preprocessing เฉพาะบนชุด Train (Train-Only Preprocessing Fit Rule)**:
   - กระบวนการเตรียมข้อมูลที่มีการคำนวณค่าสถิติจากข้อมูล (Stateful Preprocessing) เช่น การปรับสเกลตัวแปร (`StandardScaler`, `RobustScaler`, `MinMaxScaler`), การตัดค่าสุดโต่ง (Winsorization / Clipping Quantiles), หรือการคัดเลือกตัวแปร (Feature Selection) **ต้องเรียก `.fit()` บนชุดข้อมูล `Train` ของแต่ละ Fold และของแต่ละ `ticker` เท่านั้น**
   - จากนั้นจึงนำพารามิเตอร์ที่ได้จากชุด `Train` ไปเรียก `.transform()` บนชุด `Validation`, `Test` และข้อมูล `Live Inference` ห้ามนำข้อมูลทั้งตารางมา `.fit()` ก่อนแบ่งชุดข้อมูลโดยเด็ดขาด

---

## 6. นโยบายการจัดการค่าว่าง ช่วง Warm-up และการตรวจสอบคุณภาพ (Null Policy, Warm-up & Quality Checks)

### 6.1 การจำแนกประเภทของค่าว่างและการนิยาม Warm-up รายสินทรัพย์

1. **Warm-up Nulls (ค่าว่างเชิงโครงสร้างช่วงเริ่มต้นของแต่ละ `ticker`)**:
   - Feature ที่มี Lookback $N$ วันทำการของสินทรัพย์ $i$ จะเริ่มมีค่าได้เมื่อสินทรัพย์ $i$ มีผลตอบแทนรายวันที่ถูกต้องครบ $N$ ค่า (ต้องใช้ราคา `adjusted_close` ของสินทรัพย์นั้นอย่างน้อย $N+1$ วันทำการ)
   - คอลัมน์ที่ใช้หน้าต่างยาวที่สุดในกลุ่ม Core Features คือ `rv_60d` ($N=60$) ซึ่งต้องใช้ผลตอบแทนรายวันครบ 60 ค่า (ราคาปิด 61 วันทำการแรกของแต่ละ `ticker`)
   - แถวก่อนหน้านั้นถือเป็น **Warm-up Nulls** ตามธรรมชาติ **ห้ามเติมค่าด้วย `0`, ค่าเฉลี่ย, หรือทำ Forward-fill / Backward-fill โดยเด็ดขาด**
2. **Corrupted Nulls (ค่าว่างผิดปกติหลังพ้นช่วง Warm-up)**:
   - หากสินทรัพย์ `ticker` ใดผ่านจำนวนข้อมูลครบ 60 วันทำการของผลตอบแทนไปแล้ว (`is_model_ready` เคยเป็น `True` แล้ว) แต่เกิดค่า `Null`/`NaN` ขึ้นใน Core Features ตัวใดตัวหนึ่ง ให้ถือเป็นข้อผิดพลาดของข้อมูลด้วยรหัสมาตรฐาน **`CORRUPTED_FEATURE_NULL`** ต้องแยกเข้า Quarantine และหยุดการส่งต่อข้อมูลเฉพาะของ `ticker` นั้น (โดยที่โมเดลของ `ticker` อื่นที่ผ่านเกณฑ์ยังสร้างค่าพยากรณ์รายสินทรัพย์ได้ตามปกติ แต่ระบบต้องระงับการคำนวณความเสี่ยงพอร์ตโฟลิโอและแสดงสถานะข้อมูลไม่ครบถ้วนบน Dashboard)

### 6.2 การแยกนิยาม `is_model_ready` (ความพร้อมของ Feature) และ `is_label_mature` (ความครบของ Target)

ระบบแยกสถานะความพร้อมของตัวแปรต้นและตัวแปรตามออกจากกันอย่างชัดเจน เพื่อรองรับทั้งการฝึกโมเดลและการพยากรณ์ใช้งานจริง:

1. **ความพร้อมของ Feature รายสินทรัพย์ (`is_model_ready` ในตาราง `asset_volatility_features`)**:
   - กำหนด `is_model_ready = True` ณ แถว `(date, ticker)` ก็ต่อเมื่อ **คอลัมน์ในกลุ่ม Core Features ทั้ง 8 ตัวของ `ticker` นั้น (`ret_1d_t`, `ret_lag_1d`, `ret_lag_2d`, `ret_trailing_5d`, `ret_trailing_20d`, `rv_5d`, `rv_20d`, `rv_60d`) มีค่าครบถ้วน ไม่เป็น `Null` และไม่เป็น $\pm\infty$**
   - ไม่นำสถานะของ Experimental Features, ตาราง Correlation หรือตาราง Target มาเป็นเงื่อนไขบล็อก `is_model_ready` ของโมเดล Baseline รายสินทรัพย์
2. **ความพร้อมของ Target รายสินทรัพย์ (`is_label_mature` ในตาราง `asset_volatility_labels`)**:
   - กำหนด `is_label_mature = True` ณ แถว `(date, ticker)` ก็ต่อเมื่อมีข้อมูลผลตอบแทนในอนาคตครบทั้ง 5 วันทำการ ($t+1$ ถึง $t+5$) ของ `ticker` นั้นแล้ว
3. **ตารางสรุปเงื่อนไขการคัดกรองแถวตามโหมดการทำงาน**:
   - **โหมดฝึกและประเมินผลโมเดล (Training / Validation / Test)**:
     `is_warmup_buffer == False` **AND** `is_model_ready == True` **AND** `is_label_mature == True`
   - **โหมดพยากรณ์ล่วงหน้า ณ วันปัจจุบัน (Live Inference ณ วันล่าสุด $t$)**:
     - **ระดับรายสินทรัพย์**: สร้างค่าพยากรณ์ $\hat{\sigma}_{i,t}$ ได้ทันทีสำหรับทุก `ticker` ที่มี `is_model_ready == True` ณ วัน $t$
     - **ระดับพอร์ตโฟลิโอ (Downstream)**: คำนวณความเสี่ยงพอร์ตโฟลิโอได้ก็ต่อเมื่อทั้ง 3 สินทรัพย์ (`SPY`, `IEF`, `GLD`) มีค่าพยากรณ์ครบทุกตัว **และ** ตาราง `asset_rolling_correlations` ณ วัน $t$ มี `is_corr_ready == True` เท่านั้น (หากขาดตัวใดตัวหนึ่ง ต้องไม่คำนวณความเสี่ยงพอร์ตโฟลิโอและแสดงสถานะแจ้งเตือนข้อมูลไม่ครบบน Dashboard)

### 6.3 กฎการดึงข้อมูลเผื่อช่วง Warm-up จาก Config และการกันวัน Buffer ออกจากการวัดผล (Warm-up Buffer Strategy)

- กำหนดให้คำนวณวันเริ่มต้นดึงข้อมูล (`actual_fetch_start_date`) ย้อนหลังไปจากวันเริ่มวิเคราะห์ที่ตั้งไว้ใน Config (`config.start_date`) โดยต้องดึงข้อมูลราคา `adjusted_close` ล่วงหน้าอย่างน้อย **61 วันทำการของตลาด NYSE/NASDAQ** (ประมาณ 90–100 วันปฏิทินก่อน `config.start_date`)
- เพื่อให้ ณ วัน `date == config.start_date` สินทรัพย์ทุกตัวมีผลตอบแทนย้อนหลังครบ 60 ค่า และมีสถานะ `is_model_ready == True` ตั้งแต่วันแรกของช่วงวิเคราะห์
- **การป้องกันไม่ให้วัน Buffer รั่วไหลเข้าสู่ Evaluation**:
  - แถวข้อมูลทุกแถวที่มี `date < config.start_date` ต้องถูกตั้งค่าคอลัมน์สถานะ `is_warmup_buffer = True` (และตั้งค่า `is_warmup_buffer = False` สำหรับ `date >= config.start_date`)
  - ขั้นตอนการแบ่งชุดข้อมูล (Train/Validation/Test Split) และการคำนวณ Metric วัดผลทุกชนิด **ต้องกรองเอาเฉพาะแถวที่ `is_warmup_buffer == False` (`date >= config.start_date`) เท่านั้น** เพื่อไม่ให้นำแถวช่วง Buffer เข้าไปฝึกหรือวัดผลโมเดลโดยไม่ได้ตั้งใจ

### 6.4 ลำดับและเกณฑ์การตรวจสอบคุณภาพข้อมูล (Automated Quality Validation Checklist)

| ลำดับขั้นตอน | รายการตรวจสอบ | เกณฑ์ที่ต้องผ่าน (Pass Criteria) | การจัดการเมื่อล้มเหลว (Failure Action) |
| :---: | :--- | :--- | :--- |
| **1** | **Data Sorting** | จัดเรียงแถวใน `asset_volatility_features` ตาม **`(ticker, date)`** จากอดีตไปปัจจุบันก่อนคำนวณและก่อนส่งออกเสมอ | บังคับรันเป็นขั้นตอนแรกของ Pipeline |
| **2** | **Monotonic Dates per Ticker** | ภายในแต่ละ `ticker` ค่า `date` ต้องเรียงลำดับเพิ่มขึ้นอย่างเคร่งครัด (Strictly Monotonic Increasing) | Fail Pipeline สำหรับ `ticker` นั้นทันที |
| **3** | **Primary Key Uniqueness** | คู่คีย์หลัก **`(date, ticker)`** ใน `asset_volatility_features` ต้องไม่มีแถวซ้ำ (`duplicated_pk == 0`) | Fail Pipeline ทันที |
| **4** | **Schema Conformance** | ชื่อคอลัมน์และชนิดข้อมูลต้องตรงตามที่ระบุใน [datadict.md (หัวข้อ 2 และ 4)](./datadict.md) ทุกประการ | Fail Pipeline ทันที |
| **5** | **No Infinite Values** | ต้องไม่มีค่า $\pm\infty$ ในคอลัมน์ตัวเลขใดๆ ทั้งสิ้น | Fail Pipeline ทันที |
| **6** | **Volatility Non-negativity** | ค่าความผันผวน `rv_5d`, `rv_20d`, `rv_60d` ที่คำนวณแล้วทุกแถวต้องมีค่า $\ge 0.0$ | Fail Pipeline ทันที |
| **7** | **Correlation Matrix Validity (ตารางประกอบ)** | ในตาราง `asset_rolling_correlations`: (1) ทั้ง 3 คู่คำนวณจากหน้าต่าง 20 วันชุดเดียวกันที่มีข้อมูลครบทั้ง 3 สินทรัพย์ (2) ค่าอยู่ในช่วง $[-1.0, 1.0]$ และ (3) เมทริกซ์ $3\times 3$ เป็น **Symmetric และ Positive Semidefinite ($\lambda_{\min} \ge -10^{-10}$)** | ตั้ง `is_corr_ready = False`, บล็อกการคำนวณความเสี่ยงพอร์ตของวันนั้น และแจ้งเตือนบน Dashboard |
| **8** | **Model Ready Completeness** | ในแถวที่ `is_model_ready == True` ต้องไม่มีค่า `Null`/`NaN` ในกลุ่ม **Core Features รายสินทรัพย์ทั้ง 8 ตัว** ของ `ticker` นั้น | Quarantine แถวที่มีปัญหา (`CORRUPTED_FEATURE_NULL`) และแจ้ง Error |
| **9** | **Warm-up Buffer Isolation** | ตรวจสอบว่าแถวที่ส่งเข้าสู่ขั้นตอน Train / Validation / Test มีเฉพาะแถวที่ `is_warmup_buffer == False` (`date >= config.start_date`) เท่านั้น | บล็อกการส่งข้อมูลเข้าโมเดลหากพบแถว Buffer ปะปน |
| **10** | **Anomaly Range Check** | ตรวจสอบค่าเทียบกับช่วง Initial Heuristic Alert Range รายสินทรัพย์ในหัวข้อ 3.3 | บันทึก Warning ลงใน Audit Log เพื่อรอตรวจสอบ |
