# DS / EDA / Research Preparation Guide

**เอกสารสำหรับเพื่อนร่วมทีม** · อ้างอิงข้อกำหนดกลางที่ล็อก ณ 20 พฤศจิกายน 2026  
**เป้าหมาย:** เตรียมงานวิทยาการข้อมูล การวิเคราะห์เบื้องต้น การค้นคว้า และการตีความผล **คู่ขนานกับการพัฒนาระบบที่เจ้าของงานทำเองทั้งหมด**

> เอกสารนี้ไม่ได้สั่งให้สมาชิกทีมพัฒนา ML Pipeline, Target Pipeline, Replay, ADWIN, Testing Infrastructure, เปลี่ยน Contracts หรือทำ GitHub Merge. งานเหล่านั้นเป็นของเจ้าของงาน Implement ทั้ง 6 Stages. ทีมสามารถเตรียมวิธีคิด การวิเคราะห์อิสระ และงานประกอบรายงานได้โดยไม่ทำให้ข้อกำหนดหลักเปลี่ยนไป.

## 1. ภาพรวม: อะไรทำได้ตอนนี้ อะไรต้องรอ?

| งาน | ทำได้ทันที? | ต้องใช้ข้อมูลอะไร | ผลลัพธ์สำหรับทีม |
|---|---|---|---|
| **Research & Literature** | **ได้เลย** | ข้อกำหนดโครงการและเอกสารอ้างอิงภายนอก | Literature Matrix, Concept Summary, Citations |
| **EDA Plan + Figure List** | **ได้เลย** | Data Dictionary / Feature Definitions | แผนกราฟ, คำถามที่กราฟต้องตอบ, Expected Fields |
| **Data Quality Review Plan** | **ได้เลย** | Schema และ Data Quality Rules | Checklist / เกณฑ์ตรวจ Missing-Duplicates-Invalid |
| **EDA / Descriptive Statistics จริง** | เมื่อมีข้อมูลที่อนุมัติ | Validated Dataset + Snapshot/Date Filters | กราฟ/ตารางที่ trace กลับไปยังข้อมูลได้ |
| **H1 Research Method Notes** | **ได้เลย** | H1 Spec, สมมติฐาน Time-Series | Research Hypothesis Table, Interpretation Guide |
| **H1 ผลจริง/p-value** | ต้องรอ Dataset และผลที่ตรวจผ่าน | Purge-clean Train, Regression/HAC/Holm Output | ตาราง/กราฟ H1 พร้อมข้อจำกัด |
| **H2/H3 Research Method Notes** | **ได้เลย** | Definition ของ B1/B2/B3, Paired Errors | Report Shell, Comparison Storyboard |
| **H2/H3 ผลจริง/p-value** | **ต้องรอ Final Replay** | Immutable Test Predictions + Mature Targets + Coverage | Result Tables, CI, Narrative |
| **Portfolio-risk concept diagrams** | **ได้เลย** | Volatility forecast + Correlation + Weight Definition | Diagram/Explanation |
| **Portfolio-risk output จริง** | ต้องรอ Portfolio Consumer | Valid Forecasts 3 ETF + Correlation Matrix | Illustrative cases with real evidence |

> **การมีไฟล์ราคาย้อนหลัง ≠ การมี Data Snapshot ที่ผ่าน Contract ทั้งหมด** อย่ารายงานสถิติว่าเป็นผลที่รับรองแล้วจนกว่าจะตรวจ Source, Date, Split, Keys และ Quality Status.

---

## 2. Data Map: เราจะอ่านข้อมูลแต่ละส่วนอย่างไร?

### 2.1 Logical Tables ที่ตกลงไว้ (5 ตาราง — ไม่เพิ่ม)

| Logical Table | Grain / จุดประสงค์ | DS/Research ใช้ทำอะไรได้ |
|---|---|---|
| `market_prices_daily` | หนึ่งแถวต่อวันซื้อขายและ ETF; ราคา OHLCV/Return ที่ผ่านการตรวจ | ราคาตามเวลา, Missing Sessions, Volatility Regimes, Return Distributions |
| `asset_volatility_features` | หนึ่งแถวต่อ `(date,ticker)`; ฟีเจอร์และ Readiness Flags | EDA ของ 8 Core Features, Time Trends, Distributions, Feature Correlations |
| `asset_rolling_correlations` | Correlation History (20-session proxy) | อธิบายการเคลื่อนร่วมกันของ ETF และ Portfolio Risk; **ไม่ใช่ Feature X ของ B2/B3** |
| `asset_volatility_labels` | Forward RV5 Target และ Target Window/Maturity | H1 บน Train, Distribution ของ Target, Target Counts; ใช้ด้วย Time Rules |
| `asset_volatility_predictions` | Prediction History ของ B0–B3 + Traceability | หลัง Final Replay เท่านั้นสำหรับ H2/H3, Model Scores, Error Analysis |

**ข้อสังเกต:** จำนวนคอลัมน์ที่ล็อก: `asset_volatility_labels` = 12, `asset_volatility_predictions` = 16. ห้ามสร้าง Schema คอลัมน์ใหม่เองจากการคาดเดา. หากต้องการคอลัมน์ที่ยังไม่ได้ระบุ ให้ขอ Data Dictionary/Contract ตัวจริง.

### 2.2 ช่วงเวลาที่ต้องยึด

| Split | Anchor-date range | วัตถุประสงค์สำหรับ DS |
|---|---|---|
| **Train** | `2021-09-27..2024-09-30` | EDA สำหรับออกแบบทฤษฎีและ H1; ต้องใช้ **Purge-clean + Eligible** เมื่อเกี่ยวข้องกับ Labels |
| **Validation** | `2024-10-01..2025-09-30` | ผลประกอบการคัดเลือกโมเดลโดยเจ้าของงาน; **ไม่ใช้เป็น Confirmatory Final Test** |
| **Test** | `2025-10-01..2026-09-25` | ใช้รายงานผล **ที่ Freeze แล้ว** เท่านั้น ไม่ใช้หาความสัมพันธ์เพื่อตัดสินใจออกแบบโมเดล |

**ข้อมูลต้นทาง/ราคา:** แผนหลักคงสิ้นสุด `2026-09-25`. มีความต้องการ **61 XNYS warmup sessions** สำหรับฟีเจอร์ย้อนหลัง; อย่าตีความว่า warmup sessions เป็น eligible train rows หรือเอาไปนับ Train Samples โดยอัตโนมัติ.

**Purge:** ที่รอยต่อ Train→Validation และ Validation→Test ให้กันแถวของ Split ก่อนหน้าที่ `target_end_date >= next_split_start_date` ออกจาก Fixed Split Training/Scoring ตาม Policy. **Online Update** มี Eligibility ต่างหากและใช้แถวเหล่านี้ได้ *หลัง* Mature ในลำดับเวลา ซึ่งเป็นงานของ Replay ไม่ใช่เหตุให้เพื่อนแก้ Split เอง.

### 2.3 ตัวแปรที่สำคัญสำหรับ Data Science

| Column / Concept | ความหมาย | หมายเหตุ |
|---|---|---|
| `date`, `ticker` | Key สำหรับ Join (1:1) | ตรวจ Duplicate/Missing Pairing ก่อนใช้ |
| `ret_1d_t` | Log Return ของวัน `t` | ไม่ใช่ Return ของวัน `t+1` |
| `ret_lag_1d`, `ret_lag_2d` | Return ของ 1/2 วันซื้อขายก่อน | ระวังวันหยุดตลาด ไม่ใช่ -1/-2 วันปฏิทิน |
| `ret_trailing_5d`, `ret_trailing_20d` | ผลตอบแทนสะสมย้อนหลัง | อย่าเปลี่ยนสูตรโดยไม่อ้าง Feature Contract |
| `rv_5d`, `rv_20d`, `rv_60d` | Realized Volatility ย้อนหลัง | อยู่ใน **Annualized Decimal** |
| `target_realized_vol_5d` | Volatility จริงจาก 5 Session **หลัง** `t` | ต้อง Mature และใช้ได้ตามเวลา |
| `target_end_date` | วันสุดท้ายของหน้าต่าง Forward Target | ใช้ตรวจ Purge และการถึงเวลาที่รู้ Label |
| `is_warmup_buffer` | แถวเป็นช่วงเก็บประวัติเพื่อคำนวณ Features | ต้อง False สำหรับ Train/EDA ที่มีเงื่อนไข Eligible |
| `is_model_ready` | Features พร้อมใช้ | ต้อง True ในชุดวิเคราะห์ที่ใช้กับ ML |
| `is_label_mature` | Label คำนวณได้ครบจากข้อมูล Snapshot | ต้องตรวจ `target_end_date` เทียบกับเวลาที่ต้องสมมติด้วย |
| `rsi_14d`, `bb_width_20d` | Experimental Features | **ไม่ใช่ Core 8** และ **ไม่ใช่ H3** ที่ล็อกไว้ |

### 2.4 สิ่งที่ต้องตรวจทุกครั้งก่อนวาดกราฟ

- ข้อมูลมาจาก Source ไหน, Snapshot ไหน, Pipeline/Contract เวอร์ชันอะไร และเป็นราคาที่ผ่าน Validation หรือยัง
- 1 Key `(date,ticker)` ต่อแถวจริงไหม; Missing/NaN/Inf, Duplicates, ความผิดปกติของค่าทางการเงินมีหรือไม่
- วันที่เป็น XNYS Sessions หรือไม่; `t+5` หมายถึงวันที่ซื้อขายที่ห้าต่อจาก `t` ไม่ใช่ 5 วันปฏิทิน
- กราฟมีข้อมูล **Training / Validation / Test** ปะปนหรือไม่; ถ้ามีเพื่ออธิบายเชิงประวัติ ต้องแบ่งสี/ป้าย Split และห้ามนำไปเลือก Model/Features
- ความผันผวนบนกราฟอยู่ในหน่วย `annualized decimal` หรือ `percent`? ระบุบนแกนให้ตรงและไม่คูณ 100 ซ้ำ
- รูปมีค่า Sample Size `N` และช่วงวันครบหรือยัง; มี Leakage/Selection Bias จากการเอาเฉพาะแถวที่ Mature ย้อนหลังหรือไม่

---

## 3. Workstream A — EDA (Exploratory Data Analysis)

**วัตถุประสงค์:** ทำให้คนอ่านเข้าใจลักษณะของ SPY/IEF/GLD, ความต่างของ Volatility และเหตุผลที่เลือก Features/Baselines โดย **ไม่อ้างว่ากราฟ EDA พิสูจน์ความแม่นยำของ ML**.

### 3.1 คำถาม EDA ที่แนะนำ

1. ETF ทั้งสามมีช่วงที่ Return/Volatility สูง-ต่ำต่างกันอย่างไร?
2. การกระจายของ Log Return สมมาตรหรือมีหางยาว/Outlier?
3. `rv_5d`, `rv_20d`, `rv_60d` เคลื่อนไหวไปในทิศทางเดียวกันบ่อยแค่ไหน?
4. กลุ่มวันที่ผันผวนสูงต่างจากวันปกติอย่างไร (เฉพาะ EDA ไม่ใช่ Model Selection)?
5. `rv_5d` มีความสัมพันธ์กับ Forward RV5 อย่างไรใน **Purge-clean Train**?
6. การเคลื่อนสัมพันธ์กันระหว่าง SPY/IEF/GLD เปลี่ยนไปตามเวลาหรือไม่ (Correlation Proxy 20 Sessions)?
7. ข้อมูลมีฤดูกาล/ช่วงตลาดปิด/รอยต่อวันหยุดที่กระทบจำนวน observations หรือไม่?
8. Missing/Invalid/Warmup/Pending/Eligible Rows มีสัดส่วนเท่าไรต่อ ETF?

### 3.2 กราฟที่น่าทำ (เป็น **แผน** ไม่ใช่ผลจริง)

| ชื่อกราฟ | X / Y | ข้อมูล / Filter | สิ่งที่ช่วยอธิบาย |
|---|---|---|---|
| G01 Price/Return Timeline | วันซื้อขาย / ราคาหรือ Return | Validated Market Prices | ลักษณะการเคลื่อนของสินทรัพย์ (ราคาควรแสดงปรับสเกลหรือแยก panel) |
| G02 Return Distribution | Log Return / Frequency | Approved Train | หางยาว ความไม่สมมาตร/Outliers |
| G03 Volatility Timeline | วันซื้อขาย / `rv_5d`, `rv_20d`, `rv_60d` | Feature Train | ความผันผวนสูงต่ำและหน้าต่างย้อนหลังต่างกันอย่างไร |
| G04 Feature Correlation Heatmap | Core 8 × Core 8 | Feature Train | Multicollinearity และความซ้ำซ้อนของ Features |
| G05 Future RV5 Distribution | `target_realized_vol_5d` / Frequency | **Purge-clean Mature Train** | รูปร่าง/ความเบ้ของ Target |
| G06 Past vs Future RV5 Scatter | `rv_5d` / Forward RV5 | **Purge-clean Mature Train** | สนับสนุน Research Question H1 (ยังไม่ใช่ผล Test) |
| G07 Rolling Correlation | วันซื้อขาย / Pairwise Corr | Rolling Correlation Data | เหตุผลของ Covariance Proxy ใน Portfolio Risk |
| G08 Data Quality Funnel | ขั้นตอนเตรียมข้อมูล / จำนวนแถว | Join/Eligibility Report | ทำไมจำนวนแถวลดลงจาก Raw → Eligible |
| G09 Split Timeline | วัน/Train-Val-Test | Date Manifest | อธิบาย Purge, Label Delay และ Test Cutoff |
| G10 Hypothesis Result Panel | H1–H3 / Effect + CI | **รอผลจริง** | สรุปคำถามวิจัยครบสามข้อหลังระบบรันผ่าน |
| G11 Model Score Comparison | B0–B3 / MAE + Coverage | **รอ Final Test Results** | Baseline vs ML ที่ใช้วันคู่กันอย่างยุติธรรม |
| G12 Error Timeline & ADWIN | วัน/Absolute Error + Alerts | **รอ Replay Outputs** | ความเปลี่ยนแปลงของ Error ตามเวลา ไม่อ้างเหตุและผล |

ไม่จำเป็นต้องทำครบทั้ง 12 ภาพ เลือกภาพที่ตอบคำถามได้และมี Source Traceability ก่อน ควรให้รูปแรก ๆ ใช้ **Train** ตามวัตถุประสงค์ Exploratory; ถ้าภายหลังแสดง Full Historical Trend เพื่อ Context ให้ติดป้ายเป็น **Descriptive Retrospective View / Not for Model Selection**.

### 3.3 ค่าสรุปเชิงพรรณนาที่ควรมี

- `N`, Start/End Date, Missing %, Duplicate Count ต่อ ETF และ Split
- Return: Mean, Median, SD, Min/Max, Quantiles (เช่น 5/25/50/75/95%), skewness/kurtosis *ถ้าเหมาะสม*
- Volatility Features: Median, P80, Range, Correlation ของ `rv_5d`, `rv_20d`, `rv_60d`
- Label: N Mature/Pending/Purged, Target Distribution บน Train
- Correlation: Pairs SPY–IEF, SPY–GLD, IEF–GLD ตามช่วงที่ข้อมูลพร้อม
- บันทึก Rule สำหรับ Outliers ไม่ลบ/ปรับข้อมูลเพียงเพราะไม่สวย; ให้แจ้งเจ้าของ Dataset

### 3.4 เกณฑ์พร้อมส่งต่อสำหรับงาน EDA

งานหนึ่งชิ้นควรมี: **คำถาม → แหล่งข้อมูลและ Snapshot → Filters → วิธีคำนวณ → กราฟ/ตาราง → สรุปข้อสังเกต → ข้อจำกัด**. ห้ามรายงานว่า `rv_5d` "มีนัยสำคัญ" จนกว่าจะมีผล H1 ที่ใช้ HAC/Holm จาก Train จริง.

---

## 4. Workstream B — Statistical Analysis และ H1–H3

งานของเพื่อนสามารถเป็น **Research Design, Method Interpretation, Report Draft และ Visual Template**; การรัน Hypothesis Tests ที่เป็นผลหลักของโครงการอยู่ใน Implementation ของเจ้าของงาน และรอชุดข้อมูล/ผลที่ผ่าน Gate ก่อนสรุป.

### H1 — Volatility Persistence (ใช้ Train)

**คำถาม:** `rv_5d` ณ วัน `t` มีความสัมพันธ์เชิงบวกกับ Forward RV5 ใน 5 วันซื้อขายถัดไปหรือไม่ แยก SPY/IEF/GLD?

\[
RV^{forward5}_{i,t}=\alpha_i+\beta_i rv_{5d,i,t}+\varepsilon_{i,t}
\]

- H₀: `beta_i <= 0`; Hₐ: `beta_i > 0` (one-sided)
- Dataset: **Purge-clean eligible Mature Train**, แยก ETF; ต้องป้องกัน Label ของ Train ที่ต้องใช้ราคาหลัง Train Cutoff
- วิธี: OLS Slope + **HAC/Newey–West Standard Errors**; Main lag `5 XNYS sessions`; Sensitivity lag `10`, `20`
- การทดสอบ 3 ETF เป็น **Family เดียว**, ปรับ Multiple Testing ด้วย **Holm** ที่ `alpha=0.05`
- ต้องรายงาน: Beta, HAC Standard Error, Test Statistic, Raw p, Holm-adjusted p, 95% CI, N, Graph, Effect Interpretation
- ข้อจำกัด: H1 วัด **ความสัมพันธ์เชิงเส้น** ไม่ใช่เหตุและผล และไม่พิสูจน์ว่า ML ชนะ Baseline; Target Window ซ้อนทับกันข้ามวัน

**ตัวอย่างการอ่าน (ไม่ใช่ผลจริง):** ถ้า `beta=0.40` เมื่อ `rv_5d` เพิ่ม `0.01` (1 percentage point) ค่า Forward RV5 ที่เส้น regression คาดหมายเพิ่ม `0.004` (0.4 percentage points) ภายใต้โมเดลเชิงเส้น.

### H2 — Online SGD vs Static SGD (ใช้ Frozen Test)

**คำถาม:** B3 มี Absolute Error เฉลี่ยต่ำกว่า B2 หรือไม่?

\[
d^{(2)}_{i,t}=|y_{i,t}-\widehat y_{B2,i,t}|-|y_{i,t}-\widehat y_{B3,i,t}|
\]

- H₀: `E_macro[d2] <= 0`; Hₐ: `E_macro[d2] > 0`
- **ค่า d เป็นบวก = B3 Error ต่ำกว่า**; ค่า Macro หมายถึง **เฉลี่ยแยก ETF แล้วเฉลี่ยสาม ETF น้ำหนักเท่ากัน** (ไม่ใช่ 50/30/20)
- ใช้เฉพาะ Forecast **วัน/ETF เดียวกัน**, Final Test ที่ Target Mature และผ่าน Validity/Version Rules; แสดง Expected/Successful/Invalid/Pending/Paired Counts
- วิธีหลักที่เลือก: **Synchronized Moving Block Bootstrap** ของ Paired Differences เพื่อคำนึงถึง Dependence ตามเวลาและระหว่าง ETF
- Params: Main Block = `10` XNYS sessions, `2,000` replicates, seed `42`; Sensitivity = Blocks `5` และ `20`
- ต้องรายงาน: Macro DeltaMAE, Relative Improvement %, 95% CI, Raw/Adjusted p-value, Pair N, Coverage, ข้อจำกัด

### H3 — Online SGD vs Rolling RV20 (ใช้ Frozen Test)

เหมือน H2 ทุกข้อ แต่เปลี่ยนคู่เปรียบเทียบเป็น:

\[
d^{(3)}_{i,t}=|y_{i,t}-\widehat y_{B1,i,t}|-|y_{i,t}-\widehat y_{B3,i,t}|
\]

- H₀: `E_macro[d3] <= 0`; Hₐ: `E_macro[d3] > 0`
- H2/H3 เป็น **Family ของ 2 Macro Tests** และใช้ **Holm Correction** ร่วมกัน
- H3 **ไม่ใช่** การเพิ่ม `rsi_14d` หรือ `bb_width_20d`; ส่วนนี้เป็น Optional Ablation ภายหลัง

### กฎการตีความตามที่อาจารย์สอน

- `p <= 0.05` (หลังปรับ Multiple Testing ที่เกี่ยวข้อง): **Reject H₀**; ไม่เท่ากับพิสูจน์ Hₐ 100%
- `p > 0.05`: **Fail to Reject H₀**; ไม่ใช่ยืนยันว่า H₀ ถูกต้อง
- แยก **Statistical Significance** จาก **Practical Importance**, และแสดง Effect Size/CI ไม่รายงานเฉพาะ p-value
- **95% two-sided CI** กับ **one-sided p-value** ไม่ควรใช้ช่วงคร่อมศูนย์เป็นเกณฑ์ตัดสินแทน p-value โดยอัตโนมัติ โดยเฉพาะหลัง Holm
- ถ้าไม่สามารถคำนวณ inference ได้อย่างน่าเชื่อถือ ให้ระบุ **Insufficient Statistical Evidence** พร้อมเหตุผล ไม่แต่งตัวเลข
- H1 ไม่ Significant ไม่ตัด Feature และ H2/H3 ไม่ Significant ไม่แปลว่า Implementation ผิด

### เอกสารที่ทีมเตรียมล่วงหน้าได้

1. **Hypothesis Table**: Research Question, H₀/Hₐ, Split, Sign, Metric, Test, Family Correction, Limitation
2. **Method Explainer**: ทำไม H1 ต้อง HAC และ H2/H3 ต้อง Block Bootstrap แทน IID t-test ทั่วไป
3. **Report Shell**: ช่องใส่ p/CI/Effect/N และประโยคสรุปทั้ง Reject/Fail-to-Reject
4. **Results QA**: เช็กรายงานปี/ETF/Pairing/NaNs/Pending/Coverage และไม่อ้างว่าผลใด "ชนะ" จากกราฟพรรณนา

---

## 5. Workstream C — Research & Literature Review

เตรียม **หลักฐานทางวิชาการที่สนับสนุนการตัดสินใจ** โดยไม่แอบเปลี่ยนโมเดลหรือหลักการประเมินที่ตกลงแล้ว

| Research Topic | คำถามที่ควรหาคำตอบ/อธิบาย | ใช้ประกอบส่วนใด |
|---|---|---|
| Realized volatility & annualization | Realized volatility วัดอะไร; ทำไม 5-day horizon ต้องรอ Label | Problem/Target Definition |
| Volatility clustering / persistence | ทำไม RV ย้อนหลังอาจสัมพันธ์กับ RV ในอนาคต | H1 Hypothesis / EDA Discussion |
| Online vs Batch/Static Learning | ประโยชน์และความเสี่ยงของ incremental learning เมื่อ Distribution เปลี่ยน | Model Rationale / H2 |
| Label delay & Prequential Evaluation | ทำไมทำนายก่อนแล้วค่อย Update เมื่อเห็นคำตอบ | Time-Series & Leakage |
| Concept Drift / Error Monitoring | ADWIN ตรวจอะไร และเหตุใด Alert ไม่เท่ากับ auto retrain | Design & Discussion |
| Baselines in Forecasting | ทำไมต้องเทียบ Constant Mean, RV20 กับ SGD | H3 / Evaluation |
| Predictive Error & Dependence | Paired forecast comparisons, HAC, Block Bootstrap, Overlapping Targets | Statistical Method / Limitations |
| Correlation/Covariance Portfolio Volatility | Correlation Proxy และผลต่อความเสี่ยงเมื่อปรับน้ำหนัก | Portfolio Consumer |
| Data provider limitations | Yahoo/yfinance, adjusted-price revisions, missing sessions | Data Source & Limitations |

**กฎ Literature:** จดผู้แต่ง ปี ชื่อเรื่อง Venue/Publisher URL/DOI วันที่เข้าถึง (สำหรับเว็บ), ประโยคที่บทความรองรับ, และข้อจำกัด/ความต่างจากงานเรา. **ห้ามแต่ง DOI/ชื่อบทความ และห้ามอ้างว่าข้อความเป็นผลวิจัยของเราหากเป็นเพียงข้อค้นพบจากแหล่งอ้างอิง**.

**กรอบรายงานอาจารย์:** Template 2569 ให้หัวข้อ 1–11 พร้อม 7.1 Statistical Analysis, 7.2 ML, 7.3 Time-Series Analysis แต่ระบุชัดว่า **ไม่จำเป็นต้องมีทุกหัวข้อ/หัวข้อย่อย** ให้เลือกตามลักษณะโครงการ.

---

## 6. Workstream D — Figures, Storytelling และเนื้อหารายงาน

### โครงเรื่องที่เล่าให้เข้าใจง่าย

1. **ปัญหา:** สัดส่วนพอร์ตเปลี่ยนได้ แต่ความผันผวนสินทรัพย์เปลี่ยนตามเวลา; ต้องการวิธีประมาณความเสี่ยง
2. **ข้อมูล:** ETF 3 ตัว, วันซื้อขาย XNYS, ราคา→Returns→Features/Forward RV5
3. **วิธีการ:** Baseline B0/B1 vs SGD B2/B3, Train/Validation/Test, Label Delay/Purge
4. **การทดลอง:** ทำไม B2/B3 เริ่มเท่ากัน, ฝึก/เลือกค่าเมื่อไร, อัปเดตอย่างไร
5. **หลักฐาน:** MAE/RMSE/Coverage, H1–H3, High-Volatility & Temporal Diagnostics
6. **การใช้งาน:** ใช้ Forecast + Correlation เพื่อคำนวณ Portfolio Risk โดยปรับน้ำหนักไม่ Retrain
7. **ข้อจำกัด:** Backfilled adjusted prices, Test Window ที่จำกัด, ไม่มี Guarantee ว่า Online ชนะ

### ตัวอย่างข้อความที่ใช้ได้อย่างปลอดภัยก่อนมีผลจริง

> “โครงงานนี้มีเป้าหมายพยากรณ์ realized volatility ใน 5 วันซื้อขายถัดไปสำหรับ SPY, IEF และ GLD โดยเปรียบเทียบ Static SGD กับ Online SGD ซึ่งได้รับคำตอบจริงล่าช้า 5 วันซื้อขาย และกำหนดกระบวนการประเมินแบบจับคู่ล่วงหน้า”

### ตัวอย่างข้อความที่ยัง **ห้าม** ใช้ก่อนมีผลจริง

> “Online SGD พยากรณ์แม่นกว่า Static SGD อย่างมีนัยสำคัญทางสถิติ”  
> “H1–H3 ผ่านทั้งหมด”  
> “ระบบตรวจจับ Drift ได้จริงและทำให้พอร์ตปลอดภัยขึ้น”

ข้อความข้างต้นต้องมี Results/Interpretation ที่ตรวจสอบแล้วและต้องไม่ขยายข้อสรุปเกินหลักฐาน

---

## 7. ส่งงานให้เจ้าของโปรเจกต์อย่างไรไม่ให้ต้องทำซ้ำ

สำหรับแต่ละส่วนที่เพื่อนทำ ควรแนบ Metadata:

```text
Deliverable Title:
Owner/Contact:
Purpose / Research Question:
Status: PLAN | DRAFT | ACTUAL-DATA-ANALYSIS | VERIFIED-RESULT
Source Dataset / Version / Snapshot:
Split / Anchor Range / Filter / N:
Method / Calculation:
Figures / Tables:
Key Findings (Observation Only):
Limitations / Uncertainty:
Literature / Citations:
Depends On (what owner needs to provide):
Questions / Conflicts to owner:
```

**อย่าแก้ Shared Contracts หรือเขียนค่าคาดคะเนลงไฟล์ผลจริง**. หากพบข้อมูล Missing หรือขัดกับ Data Dictionary ให้ส่งรายการปัญหา/ภาพประกอบและบันทึกวิธี Reproduce ให้เจ้าของ Pipeline ตรวจ.

## 8. Checklist ก่อนแชร์งานในทีม

- [ ] อ้าง Spec ของโครงการตรงกับไฟล์ 01 และข้อกำหนด B0–B3 / Core 8 / Horizon 5
- [ ] ระบุ Clearly ว่าผลนั้นคือ **PLAN / DEMO / ACTUAL / VERIFIED**
- [ ] บันทึก Source, Snapshot, ETF, Dates, Split, Eligibility, N, หน่วย
- [ ] EDA ที่เกี่ยวข้องกับ Label อยู่บน Train ที่ Purge-clean เมื่อจะใช้สนับสนุน H1
- [ ] ไม่ใช้ Test เลือก Feature/Model/Hyperparameter/Testing Method
- [ ] ไม่ใช้ p-value จาก Independent Sample Test ที่ละเลย Overlapping Targets
- [ ] H2/H3 อยู่บน Paired Frozen Predictions และรอ Results จริง
- [ ] ภาพประกอบ/กราฟมีคำอธิบายและข้อจำกัด ไม่อ้างเหตุและผลเกินข้อมูล
- [ ] อ้างอิงบทความ/ข้อมูลจริง ตรวจสอบ DOI และ Link แล้ว
- [ ] ไม่มอบหมายงานเขียน Pipeline/Model/ADWIN/Checkpoint ให้เพื่อนโดยอัตโนมัติ
