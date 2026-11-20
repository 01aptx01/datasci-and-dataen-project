# START HERE — DEDS Team Reference Package

**โครงงาน:** Adaptive Portfolio Risk Lab · SPY / IEF / GLD  
**ฉบับ:** 1.0 · ข้อตกลงอ้างอิง ณ 20 พฤศจิกายน 2026  
**สถานะ:** Shared reference / Design locked / Implementation & empirical results pending  
**กลุ่มผู้อ่าน:** เพื่อนร่วมทีมที่เตรียม Data Science, EDA, Statistical Research, Literature Review, Visualizations และเนื้อหารายงาน

> **ย้ำขอบเขตทีม:** ผู้ประสานงาน/เจ้าของงานพัฒนาระบบรับผิดชอบ **Implementation ทั้ง 6 Stages ด้วยตนเอง** (Contracts, Target, Dataset, Models, Replay, Evaluation/Portfolio) ชุดเอกสารนี้ **ไม่ได้แบ่งงานเขียนโค้ดหรือมอบหมายให้เพื่อนแก้ Repository** แต่ให้เพื่อนอ้างอิงข้อกำหนดเดียวกันเพื่อทำงานด้านวิเคราะห์และงานวิจัย/รายงานที่เตรียมล่วงหน้าได้

## เปิดไฟล์ไหนก่อน?

| ลำดับ | เอกสาร | ใช้เพื่อ |
|---|---|---|
| 1 | [`01_SHARED_PROJECT_DECISIONS.md`](./01_SHARED_PROJECT_DECISIONS.md) | **แหล่งอ้างอิงกลาง**: ภาพรวม เป้าหมาย สูตร Target, 8 Features, B0–B3, Split, 7 หัวข้อใหญ่, 3 Hypotheses, Metrics, ข้อจำกัด และข้อตกลงสำคัญ |
| 2 | [`02_DS_EDA_AND_RESEARCH_GUIDE.md`](./02_DS_EDA_AND_RESEARCH_GUIDE.md) | รายละเอียดว่าเพื่อนสามารถ **เตรียมอะไรคู่ขนาน** ได้บ้าง ต้องใช้ข้อมูลชุดไหน ผลที่ต้องเก็บและสิ่งที่ต้องหลีกเลี่ยง |
| 3 | [`03_REPORT_EVIDENCE_AND_TEMPLATES.md`](./03_REPORT_EVIDENCE_AND_TEMPLATES.md) | แม่แบบหัวข้อรายงาน, ตาราง EDA, H1–H3, Evidence Log, Figure Captions และรายการที่รอผลจาก Implementation |

ชุดนี้เป็น **เอกสารสำหรับสมาชิกทีม** ส่วนไฟล์ Requirements `DEDS_Next_Implementation_6_Stages_H1-H3_2026-11-20` เป็นข้อกำหนดเชิงวิศวกรรมสำหรับเจ้าของงาน/AI ในขั้นพัฒนาต่อ **ไม่ใช่สิ่งที่เพื่อนจำเป็นต้องลงมือทำ**

## โปรเจกต์นี้ตอบคำถามอะไร?

- เราสามารถทำนาย **ความผันผวนที่เกิดขึ้นจริงใน 5 วันซื้อขายข้างหน้า** (Forward RV5) ของ `SPY`, `IEF`, `GLD` ได้แม่นยำเพียงใด?
- การฝึก **Online SGD (B3)** ต่อเนื่องเมื่อ Label Mature จะช่วยลด Error จาก **Static SGD (B2)** หรือไม่?
- Online SGD ดีกว่า Baseline ที่เรียบง่ายอย่าง **Rolling RV20 (B1)** หรือไม่?
- นำ Forecast ของแต่ละ ETF ไปประมาณ **ความเสี่ยงรวมของพอร์ตตามน้ำหนักที่ผู้ใช้กำหนด** โดยไม่ต้องฝึกโมเดลใหม่เมื่อปรับน้ำหนักได้อย่างไร?

## 7 กลุ่มข้อตกลงที่ล็อกแล้ว — อ่านละเอียดในไฟล์ 01

1. Initial Training: B2/B3 เริ่มจาก Model+Scaler State เดียวกัน, ฝึกแยก ETF
2. Training Window: B2 Frozen; B3 Incremental จาก Mature Labels ไม่ Rolling Refit
3. Online Update: Predict → Save → Evaluate → ADWIN → Update → Checkpoint
4. Preprocessing & Hyperparameters: Core 8, RobustScaler Train-only, SGD Grid 27 ชุด/ETF
5. Validation & Test: Time Split, Purge, Replay ต่อเนื่อง, No Test Tuning
6. Evaluation: Paired Macro MAE, Coverage, Temporal, High-Vol; Hypothesis H1–H3
7. Contracts & Engineering: คง 5 Logical Tables, Lineage, Checkpoint, Testing Gates

## ข้อเท็จจริงที่ต้องสื่อสารให้ตรงกัน

| คำพูดที่ถูกต้อง | ไม่ควรพูดว่า |
|---|---|
| ระบบ **มีแผนจะ** พยากรณ์ Forward RV5 | ระบบทำงานครบและแม่นแล้ว (ยังไม่มีผลยืนยัน) |
| `0.15` สำหรับ volatility คือ **15% annualized volatility** | ทำนายราคาหรือผลตอบแทน 15% |
| H1 ใช้ **Train ที่ Purge-clean** | ใช้ Train/Validation/Test ปนกันทดสอบ H1 |
| H2/H3 **รอ Frozen Test Predictions จริง** | ใช้ผลตัวอย่างสร้าง p-value หรือรายงานว่าชนะแล้ว |
| Pending Label คือยังไม่มีผลครบ 5 วัน | โมเดลทำนายล้มเหลว |
| B3 อาจชนะหรือแพ้ก็ได้ | Online Learning ต้องชนะเสมอ |

## สิ่งที่เริ่มทำได้ทันทีและสิ่งที่ต้องรอ

**เริ่มได้ทันทีโดยไม่รอ Model:** หาบทความอ้างอิงและสรุปแนวคิด, เตรียมเหตุผลทางทฤษฎี, ออกแบบชุดกราฟและ Data Quality Checklist, ร่างหัวข้อรายงาน, วาง H1–H3 Interpretation Plan และรูปแบบหลักฐาน

**เริ่มเมื่อได้รับข้อมูลที่ตรวจแล้ว:** EDA และกราฟจริงบน Approved Train / Research Snapshot, วิเคราะห์ Distribution/Correlation/Volatility History, เตรียมสถิติเชิงพรรณนาและภาพประกอบรายงาน

**ต้องรอระบบจากเจ้าของงาน:** ผล H1 ที่รันจากชุด Train/Purge จริง, H2/H3 p-values และ CI, B0–B3 Test Scores, Coverage, ADWIN Alerts, Portfolio Risk Consumer ผลจริง รวมถึง Claims ว่าคู่ไหนชนะ

## กฎใช้ข้อมูลร่วมกัน

- ก่อนวิเคราะห์ให้บันทึก **ชื่อ Dataset, Snapshot/Version, ช่วงวัน, Split, Timezone/Calendar, จำนวนแถว, Data Filters** ทุกครั้ง
- ใช้ข้อมูลเพื่อ **EDA** ได้ แต่ห้ามนำ Insight จาก Test ไปเลือก Features, Models, Hyperparameters หรือวิธีทดสอบย้อนหลัง
- ถ้าใช้ Sample/Synthetic Data ในสไลด์ตัวอย่าง ต้องติดป้าย **DEMO / NOT ACTUAL RESULTS** ชัดเจน
- เมื่อพบ Conflict กับเอกสาร/โค้ดเดิม ให้ **สอบถามเจ้าของงาน** ก่อนแก้ข้อกำหนดหรือแชร์ผลเป็นข้อสรุปหลัก
- เอกสารนี้เป็น **สเปกและแผนวิจัย** ไม่ใช่หลักฐานว่าระบบ ML ได้ผ่าน Tests แล้ว

## ข้อความสั้นสำหรับส่งในกลุ่ม

> ส่งเอกสารอ้างอิงกลางของโปรเจกต์ DEDS ครับ ชุดนี้รวบรวมข้อตกลงที่เราล็อกไว้ทั้งหมด ทั้งเป้าหมาย SPY/IEF/GLD, Forward RV5, Features, B0–B3, ช่วงข้อมูล, H1–H3 และแนวทางประเมินผล **ส่วน Implementation ของ Pipeline/ML/Replay ผมรับผิดชอบเองทั้งหมด** อยากให้ทุกคนใช้ชุดนี้เป็นฐานสำหรับเตรียม EDA, Research, ภาพประกอบ และเนื้อหารายงานคู่ขนานกัน โดยยังไม่สรุปผลทดสอบจริงจนกว่าจะมี Outputs จากระบบครับ
