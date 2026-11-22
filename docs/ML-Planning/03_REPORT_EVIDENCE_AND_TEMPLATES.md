# Team Report Preparation, Evidence Checklist & Fill-in Templates

**สำหรับทีม DS / Research / Report** · ข้อตกลง DEDS ณ 20 พฤศจิกายน 2026  
**สถานะเอกสาร:** โครงสร้างและแม่แบบที่จัดทำไว้ ณ 20 พฤศจิกายน 2026

> **อัปเดตสถานะ 23 พฤศจิกายน 2026:** ช่อง `TBD`, `PENDING` และข้อความว่ารอผลในแม่แบบด้านล่างบันทึกสถานะตอนจัดทำเอกสาร ไม่ใช่ทะเบียนสถานะปัจจุบัน ปัจจุบันมีผล Stage 03–06 ใน [ชุดรายงานและ handoff](../ml-results/README.md) และ [รายงาน Champion ADWIN](../ml-results/06_champion_adwin_only.md); ก่อนนำตัวเลขไปเขียนรายงาน ให้ใช้ identity, ขอบเขต และข้อจำกัดจาก run ที่อ้างถึงโดยตรง

> ใช้เอกสารนี้เพื่อเตรียม **ข้อความ รูป ตาราง และหลักฐาน** ระหว่างที่ระบบ ML ยังอยู่ระหว่างการพัฒนา ห้ามนำค่าตัวอย่างในไฟล์นี้ไปอ้างเป็น Experimental Result จริง

## 1. โครงสร้างรายงานอ้างอิงจากอาจารย์

จากไฟล์ **`DSDN Report Template.pdf`** ชื่อ “โครงร่างรายงานโครงงาน Data Science and Data Engineering 2569” อาจารย์ระบุว่า **ไม่จำเป็นต้องมีทุกหัวข้อ/หัวข้อย่อย** ขึ้นกับลักษณะโครงงาน จึงใช้โครงด้านล่างเป็นกรอบ ไม่ใช่รายการบังคับให้สร้างงานซ้ำโดยไม่จำเป็น

| Section ของ Template | เพื่อนสามารถเตรียม | ต้องรอผลจากเจ้าของ Implementation |
|---|---|---|
| 1. บทนำ | ที่มา ปัญหา วัตถุประสงค์ คำถามวิจัย ขอบเขตและประโยชน์ | ยืนยันขอบเขตที่ระบบทำสำเร็จจริงก่อน Final |
| 2. ข้อมูลและแหล่งข้อมูล | ETF คืออะไร, Yahoo Finance/yfinance, Calendar, Data Fields, Date Range, Limitations | Snapshot/Actual Counts/Versions/Source Metadata |
| 3. การออกแบบวิศวกรรมข้อมูล | สถาปัตยกรรมตามข้อตกลง, Diagram, Roles ของ 5 Tables | Pipeline Integration/Actual Run Evidence |
| 4. Data Quality | เตรียม Checklist Missing/Duplicates/Invalid/Calendar/Outlier | จำนวนปัญหาและผลตรวจจริง |
| 5. Data Preparation | 8 Core Features, Label Formula, Join 1:1, Split, Purge | Prep Report/Exclusion Counts จริง |
| 6. EDA | แผนกราฟ, Draft Captions, Research Questions; เมื่อมี Approved Data จึงวิเคราะห์จริง | Result Figures ที่ผ่าน Data/Quality Review |
| 7.1 Statistical Analysis | เตรียม H1–H3, H₀/Hₐ, Methods, Assumptions, Format | p-values, CI, N, Effect Sizes จริง |
| 7.2 Machine Learning | อธิบาย B0–B3, Scaler, Hyperparameter Grid, Validation Protocol | Selected Params/Model Performance จริง |
| 7.3 Time-Series | ความต่อเนื่องวันซื้อขาย, Delay, Overlap, Prequential, ADWIN | Actual Replay/Error Timeline/ADWIN Alerts |
| 8. Results & Evaluation | ออกแบบตาราง MAE/RMSE/Coverage/High-Vol/Year | ผล Test/Validation จริง |
| 9. Interpretation | เตรียมกรอบการตีความทั้งกรณีชนะ/แพ้/ไม่ Significant | เขียนข้อค้นพบหลังเห็นผลเท่านั้น |
| 10. Limitations | Historical adjusted-price vintage, Time Series dependence, Pending Labels, Proxy Correlation | ข้อจำกัดที่พบจริงตอนรันและผลที่รองรับ |
| 11. Conclusion & Future Work | สรุป Objectives/Scope และแนวทางเพิ่มเติมที่แยก MVP/Optional | ยืนยันข้อสรุปจากผลที่รันแล้ว |
| References/Appendix | Literature Matrix, Data Dictionary, Diagrams, Results Appendix | Final Traceability/Manifest |

### ส่วนที่ต้องเน้นในการรายงาน

1. **แยก “Design/Method” ออกจาก “Observed Results”** ทุกหัวข้อ
2. **Explain Why**: ทำไม Forward RV5, ทำไม 8 Features, ทำไม B0/B1, ทำไม B2/B3 Same Initial State, ทำไม Online Label Delay
3. **No Test Leakage**: Train-only H1, Frozen Test H2/H3, No Test-based Tuning
4. **Transparent Negative Results**: ถ้า B3 ไม่ชนะ/ไม่มีนัยสำคัญ ต้องรายงานตามจริง
5. **Scientific and Practical Interpretation**: p-value ไม่เท่ากับประโยชน์ทางปฏิบัติหรือผลตอบแทนการลงทุน

---

## 2. แม่แบบ Project Overview (คัดลอกไปปรับใช้ได้)

> **วัตถุประสงค์:** โครงงาน Adaptive Portfolio Risk Lab ศึกษาการพยากรณ์ความผันผวนที่เกิดขึ้นจริงใน 5 วันซื้อขายข้างหน้าของ ETF สามรายการ ได้แก่ SPY, IEF และ GLD โดยใช้ข้อมูลราคาย้อนหลังและฟีเจอร์ความผันผวน จากนั้นเปรียบเทียบ Baseline 2 วิธี กับ Static SGD และ Online SGD ที่เรียนรู้ต่อเนื่องเมื่อ Target Mature ตามเงื่อนไขเวลา ผลการพยากรณ์รายสินทรัพย์จะถูกนำไปประกอบกับ Correlation History เพื่อประมาณความผันผวนของพอร์ตตามน้ำหนักที่กำหนดโดยไม่ต้องฝึกโมเดลใหม่เมื่อเปลี่ยนน้ำหนักพอร์ต
>
> **คำถามหลัก:** (1) ความผันผวนย้อนหลังสัมพันธ์กับความผันผวนในอนาคตหรือไม่ (2) Online Learning ลดข้อผิดพลาดจาก Static Model ได้หรือไม่ (3) Online Learning ให้ประโยชน์เพิ่มเหนือ Rolling Volatility Baseline หรือไม่

**คำอธิบายเรื่องหน่วย:** Volatility ที่แสดงเป็น Annualized Decimal เช่น `0.18` คือ 18% annualized volatility ของ Horizon 5 วัน ไม่ใช่การทำนายผลตอบแทนหรือราคา

---

## 3. แม่แบบ Data Source & Quality Table

> ตารางตัวอย่างต่อไปนี้เป็น **โครงร่างว่าง** ไม่ใช่ผลตรวจจริง

| Field | SPY | IEF | GLD | หมายเหตุ |
|---|---|---|---|---|
| Raw Price Rows | TBD | TBD | TBD | Source/Snapshot: TBD |
| Unique XNYS Sessions | TBD | TBD | TBD | Calendar Version: TBD |
| Duplicate `(date,ticker)` Keys | TBD | TBD | TBD | วิธีจัดการ: TBD |
| Missing/Invalid Price Values | TBD | TBD | TBD | Rule/Reason: TBD |
| Valid Core Feature Rows | TBD | TBD | TBD | Exclude Warmup/Invalid: TBD |
| Mature Train Label Rows | TBD | TBD | TBD | Strict Train/Purge: TBD |
| Purged Train→Validation Anchors | TBD | TBD | TBD | ใช้ Actual `target_end_date` |
| Purged Validation→Test Anchors | TBD | TBD | TBD | ตาม Fixed Split |
| Pending Test Target Anchors | TBD | TBD | TBD | **ไม่ใช่ Forecast Failure** |

### Metadata ที่ต้องแนบทุกตาราง/กราฟ

```yaml
artifact_id: "TBD"
title: "TBD"
status: "DRAFT | ACTUAL | VERIFIED"
source_table: "TBD"
snapshot_id: "TBD"
feature_target_contract_version: "TBD"
split: "Train | Validation | Test | Descriptive Retrospective"
anchor_start_date: "TBD"
anchor_end_date: "TBD"
tickers: [SPY, IEF, GLD]
filters_eligibility: "TBD"
unit: "annualized decimal | percent | log return | count | correlation"
rows_before_after_filters: "TBD"
author_or_owner: "TBD"
verified_by: "TBD"
```

---

## 4. แม่แบบ EDA Summary และ Caption

### EDA Table

| EDA Question | Method/Plot | Dataset | Status | Main Observation | Caveat |
|---|---|---|---|---|---|
| ความต่างของ Log Return ระหว่าง ETF | Distribution + Quantile Table | Approved Train | PLANNED | TBD | Heavy Tail/Outliers/Regimes |
| ความผันผวนย้อนหลังเปลี่ยนแปลงอย่างไร | `rv_5d/20d/60d` Timeline | Train Features | PLANNED | TBD | Rolling Window/Warmup |
| H1 Past vs Future RV5 | Scatter + Regression/HAC Output | Purge-clean Mature Train | PLANNED | TBD | Correlation ≠ Causation |
| ความสัมพันธ์ระหว่าง ETF | 20-session Correlation Timeline | Approved Correlation History | PLANNED | TBD | Proxy ไม่ใช่ Correlation อนาคตจริง |

### Figure Caption Template

> **Figure [ID]: [Chart Name].** แสดง [ตัวแปร/หน่วย] สำหรับ [สินทรัพย์] ระหว่าง [วันที่เริ่ม] ถึง [วันที่สิ้นสุด] บน [Split] จาก [Source/Snapshot]. ใช้ตัวอย่าง `N=[ ]` หลัง [Eligibility/Filters]. ภาพสื่อให้เห็น [ข้อสังเกตเชิงพรรณนา] โดยไม่ใช้เป็นหลักฐานเลือกโมเดลจากชุด Test. ข้อจำกัดคือ [ ]

### หลักการตีความกราฟ

- Scatter Plot ที่ชันขึ้นอย่างเดียว **ไม่ใช่** ผลยืนยัน H1; ต้องมี OLS/HAC/Holm
- Heatmap ของ 8 Features บอกความสัมพันธ์ระหว่าง Features แต่ **ไม่** เป็นหลักฐานว่า Feature ต้องถูกเอาออก
- Plot “รายปี” ต้องระบุว่าเป็น **Partial Year** และแบ่ง Validation/Test ให้ถูก
- Time-series อาจมี Dependence และ Regimes เปลี่ยนไป; อย่าตีความค่าเฉลี่ยระยะยาวว่าใช้ได้ทุกช่วง

---

## 5. แม่แบบ Hypothesis Testing Results (H1–H3)

**สำคัญ:** Research Hypothesis ชื่อ H1/H2/H3 ต่างจากสัญลักษณ์ H₀/Hₐ (Null/Alternative) ของแต่ละข้อ

### 5.1 Summary Protocol ที่ล็อก

| Research ID | Question | Null | Alternative | Main Dataset | Primary Method |
|---|---|---|---|---|---|
| H1 | `rv_5d` สัมพันธ์เชิงบวกกับ Forward RV5? | `β <= 0` | `β > 0` | **Purge-clean Train** แยก ETF | OLS + HAC(5), Sensitivity (10/20), Holm 3 ETF |
| H2 | B3 ดีกว่า B2 หรือไม่? | `ΔMAE_macro <= 0` | `ΔMAE_macro > 0` | **Frozen Final Test**, paired | Synchronized Moving Block Bootstrap |
| H3 | B3 ดีกว่า B1 หรือไม่? | `ΔMAE_macro <= 0` | `ΔMAE_macro > 0` | **Frozen Final Test**, paired | Synchronized Moving Block Bootstrap |

**Global:** `alpha = 0.05`, one-sided alternative; H2/H3 family ปรับ Holm 2 Tests; bootstrap 10 XNYS sessions × 2,000 replicates, seed 42; sensitivity blocks 5/20; รายงาน 95% two-sided CI และ Adjusted p ตามข้อตกลง

### 5.2 H1 — Results Table (รอข้อมูลจริง)

| Ticker | N Train | β̂ | HAC SE | Test Statistic | Raw p | Holm p | 95% CI | Reject H₀? | Notes |
|---|---:|---:|---:|---:|---:|---:|---|---|---|
| SPY | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| IEF | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| GLD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |

**H1 Paragraph Template:**

> “จากชุด Train ที่ผ่านการตรวจ Eligibility และ Purge ของ [ETF] จำนวน `N=[ ]` ตัวอย่าง พบค่าความชัน OLS `β̂=[ ]` โดยใช้ HAC/Newey–West (`lag=5`), p-value ดิบ `[ ]`, p-value หลังปรับ Holm `[ ]` และ 95% CI `[ ]`. ที่ระดับนัยสำคัญ 0.05 จึง [Reject / Fail to Reject] H₀. ผลดังกล่าว [สนับสนุน/ยังไม่มีหลักฐานเพียงพอสนับสนุน] ความสัมพันธ์เชิงเส้นทิศทางบวกในช่วง Train โดย **ไม่** ยืนยันความเป็นเหตุและผลหรือความแม่นยำของโมเดลใน Test.”

### 5.3 H2/H3 — Results Table (รอข้อมูลจริง)

| Hypothesis | Comparison | N Paired (per ETF / Macro) | Macro ΔMAE | Relative Improvement % | 95% CI | Raw p | Holm p | Decision | Coverage Caveat |
|---|---|---|---|---|---|---|---|---|---|
| H2 | B2 − B3 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| H3 | B1 − B3 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |

**ความหมาย:**

\[
\Delta\mathrm{MAE}_{H2}=\tfrac13\sum_{i \in \{SPY,IEF,GLD\}}\mathrm{mean}_{t \in \mathrm{paired}_i}\big[|e_{B2,i,t}|-|e_{B3,i,t}|\big]
\]

H3 ใช้ B1 แทน B2. **ค่า Δ เป็นบวก = B3 MAE ต่ำกว่า** ภายในตัวอย่างที่จับคู่และรายงาน Coverage แล้ว; ไม่ได้บอกว่าดีกว่าทุกวันหรือทุก ETF.

**H2/H3 Paragraph Template:**

> “บน Frozen Test ช่วง [ ] โดยใช้คำทำนายของ [คู่เปรียบเทียบ] ใน Anchor/Ticker ชุดเดียวกันที่ Target Mature แล้ว ได้ Macro ΔMAE `[ ]` (ค่า + หมายถึง B3 Error ต่ำกว่า), Relative Improvement `[ ]%`, 95% CI `[ ]`, raw p `[ ]`, Holm-adjusted p `[ ]` ภายใต้วิธี Synchronized Moving Block Bootstrap. ผลการทดสอบที่ `α=0.05` คือ [Reject / Fail to Reject] H₀. ทั้งนี้ Forecast Coverage `[ ]`, Pending `[ ]` และข้อจำกัด `[ ]` เป็นบริบทสำคัญของการตีความ.”

**ข้อควรระวัง:** ไม่ใช้ CI 95% two-sided เป็นเกณฑ์เดียวแทน p-value one-sided หลัง Holm; ไม่อ้างความมีนัยสำคัญโดยอัตโนมัติหาก Method Validity ไม่ผ่าน

### 5.4 ผลลัพธ์ทั้ง 3 Hypotheses สรุปอย่างไร

| ผลที่เกิดขึ้นจริง | วิธีเขียน |
|---|---|
| H1 Significant, H2 Significant, H3 Significant | อธิบายแต่ละคำถามแยกกัน โดยไม่อ้าง H1 เป็นสาเหตุของ H2/H3 |
| H1 Not Significant แต่ H2/H3 มีผลดี | Regression H1 ไม่ให้หลักฐานพอใน Train แต่โมเดลหลาย Features อาจให้ผลต่างเชิงพยากรณ์ได้ |
| H2 Significant แต่ H3 ไม่ Significant | Online Learning อาจช่วยเหนือ Static SGD แต่ยังไม่พบหลักฐานพอว่าเหนือ Rolling RV20 |
| H2/H3 Not Significant ทั้งคู่ | รายงาน Effect Size, CI, N, Coverage และวิธีทดสอบ; ไม่ดัดแปลง Test เพื่อให้ผ่าน |
| ข้อมูลไม่เพียงพอ/Method ไม่เสถียร | ระบุว่า **Insufficient Evidence**, ไม่แทนด้วย p-value จากวิธีไม่เหมาะ |

---

## 6. แม่แบบ Evaluation ที่จะรอผลจริง

| Model | SPY MAE | IEF MAE | GLD MAE | Macro MAE | RMSE Summary | Paired N | Coverage |
|---|---:|---:|---:|---:|---|---|---|
| B0 `CONSTANT_BASELINE` | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| B1 `ROLLING_20D_BASELINE` | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| B2 `STATIC_SGD` | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| B3 `ONLINE_SGD` | TBD | TBD | TBD | TBD | TBD | TBD | TBD |

**อื่น ๆ ที่รอผล:** High-Volatility Group (> Train P80 Target ต่อ ETF), Rolling 20-session MAE, Monthly/Yearly Metrics ตาม Split, ADWIN Alert Timeline, Portfolio Risk Case Study ที่ใช้ Forecast/Correlation Snapshot เดียวกัน

**Date Interpretation:** Validation 2024 และ 2025, Test 2025 และ 2026 เป็น **ช่วงบางส่วนของปี** ตาม Split จริง ไม่ใช่เต็มปีทั้งหมด.

---

## 7. Literature Matrix Template

| Research Topic | Author/Year | Title / Venue / DOI / URL | Source Type | Relevant Claim (paraphrase) | Limits / Difference from our work | Reviewed By |
|---|---|---|---|---|---|---|
| Volatility persistence | TBD | TBD | TBD | TBD | TBD | TBD |
| Online learning with delayed labels | TBD | TBD | TBD | TBD | TBD | TBD |
| Forecast accuracy comparison | TBD | TBD | TBD | TBD | TBD | TBD |
| Time-series dependence robust inference | TBD | TBD | TBD | TBD | TBD | TBD |
| ADWIN change detection | TBD | TBD | TBD | TBD | TBD | TBD |
| Portfolio covariance and risk | TBD | TBD | TBD | TBD | TBD | TBD |

**ห้ามแต่งชื่อบทความ, DOI, ผลวิจัย หรือคำกล่าวอ้างที่ต้นฉบับไม่รองรับ.** ถ้าเป็นบทความรีวิว/เอกสาร Library ให้ระบุชนิดให้ชัด. ถ้าเป็นแนวคิดที่ทีมเสนอเอง อย่าอ้างว่าเป็นคำสั่งตรงจากอาจารย์.

---

## 8. Evidence Register / Work Handoff Template

| Evidence ID | Claim / Section | Input Source & Version | Required Result | Status | Responsible Owner | Verified Date |
|---|---|---|---|---|---|---|
| EV-001 | Raw/Valid Data Coverage | `market_prices_daily`, snapshot TBD | Train/Val/Test counts | PENDING | TBD | — |
| EV-002 | Feature/Target Consistency | Feature/Label Contracts | Rule/Counts/Figure | PENDING | TBD | — |
| EV-003 | H1 Statistical Result | Purge-clean Train + H1 output | Slope/HAC/Holm/CI | PENDING | Implementation Owner | — |
| EV-004 | B0–B3 Final Metrics | Frozen Test Predictions | Macro MAE/RMSE/Coverage | PENDING | Implementation Owner | — |
| EV-005 | H2/H3 Results | Same Frozen Test Predictions | ΔMAE/Bootstrap/Holm | PENDING | Implementation Owner | — |
| EV-006 | Drift Monitoring Evidence | ADWIN/Replay Logs | Alert Timeline | PENDING | Implementation Owner | — |
| EV-007 | Portfolio Risk Case | Valid Forecast + Correlation | Weight-sensitive risk result | PENDING | Implementation Owner | — |

สถานะที่ใช้: `PLANNED`, `DRAFT`, `PENDING_DATA`, `ACTUAL_RESULT`, `VERIFIED`, `BLOCKED`; ห้ามติด `VERIFIED` โดยไม่มีหลักฐานให้ตรวจสอบย้อนหลังได้

---

## 9. ข้อจำกัดที่ควรกล่าวอย่างตรงไปตรงมา

- **Historical adjusted prices** อาจถูกแก้ย้อนหลัง; การ Replay จาก Snapshot เดียวไม่เท่ากับมี historical data vintage จริง ณ แต่ละวัน
- การทำนาย Forward RV5 มี **5-session label delay** และ Targets ของวันติดกันซ้อนทับกัน; Inference แบบ IID ทั่วไปอาจไม่เหมาะ
- Test จบที่ `2026-09-25`; Forecast ท้ายช่วงที่ Label ยัง Pending ไม่รวมใน MAE แต่ **ไม่ใช่ Forecast Failure**
- **Correlation Proxy ย้อนหลัง 20 วัน** ไม่ได้รับประกันความสัมพันธ์ระหว่างสินทรัพย์ในอนาคต
- **Online ≠ Guaranteed Better**; Forecast Model ไม่ได้รับประกันผลตอบแทนจากการลงทุน
- จำนวนตัวอย่างที่ใช้ได้จริงและคะแนนทั้งหมดขึ้นกับ Quality Rules และ Eligibility ที่จะตรวจเมื่อรันระบบ
- คำอธิบายเชิงเหตุผล/กราฟไม่ใช่หลักฐานเชิงสาเหตุและไม่ใช่การยืนยันความมีนัยสำคัญ

## 10. Final QA ก่อนใช้ข้อความในรายงาน/พรีเซนต์

- [ ] ทุกตัวเลขเป็น Actual Verified Result หรือระบุชัดว่า DEMO/TBD
- [ ] ช่วงวัน/คำนิยาม SPY, IEF, GLD ตรงกับสเปกกลาง
- [ ] Forward RV5 คือ 5 XNYS Sessions หลัง Anchor ไม่รวมวัน t
- [ ] Split/Purge/Maturity ไม่ใช้ Future Label โดยไม่รู้ตัว
- [ ] ไม่มีการใช้ Test เลือก Features, Models, Parameter หรือ Test Procedure
- [ ] H1 แยก ETF + Holm 3 Tests, H2/H3 Macro + Holm 2 Tests
- [ ] วิธี CI/p-value อธิบาย assumptions และไม่อ้างว่าผล Significance เท่ากับ Practical Impact
- [ ] MAE รายงานร่วมกับ Pair N/Coverage และ Missing/Invalid/Pending
- [ ] ติดป้ายปีที่เป็น Partial-Year และแยก Validation/Test
- [ ] Claims เรื่อง Drift/Performance/Portfolio มี Artifact จริงรองรับ
- [ ] ข้อมูลอ้างอิง Literature มี Link/DOI ที่ตรวจจริง ไม่มีบทความแต่ง
- [ ] เจ้าของงานพัฒนาระบบทั้งหมด; เอกสารเพื่อนไม่ได้ไปแก้ Production Code/Contracts

---

## 11. เอกสารฐานที่ใช้จัดทำชุดนี้

- `01_SHARED_PROJECT_DECISIONS.md` — สรุปข้อตกลงหลักที่ล็อกไว้ทั้งหมด
- `02_DS_EDA_AND_RESEARCH_GUIDE.md` — แนวทางเตรียม DS/EDA/Research
- `DEDS_Next_Implementation_6_Stages_H1-H3_2026-11-20` — Technical Requirements (เจ้าของ Implementation ใช้; เพื่อนไม่จำเป็นต้องรับผิดชอบ)
- `DSDN Report Template.pdf` — อาจารย์ให้โครงร่างรายงานโดยไม่บังคับทุกหัวข้อ
- `C342 Ch8 Hypothesis Testing_2.pdf` — สไลด์แนวคิด Hypothesis Testing, Types of Tests, p-value, CI, Effect Size และการรายงานผล
