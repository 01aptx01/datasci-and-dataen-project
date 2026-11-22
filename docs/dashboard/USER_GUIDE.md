# คู่มือทำงานกับ Forecast Replay และ Portfolio Scenario Lab

คู่มือนี้ช่วยให้ผู้สอน นักศึกษา และผู้ตรวจงานเริ่มจากข้อมูลที่บันทึกไว้ใน Adaptive Portfolio Risk Lab, ตรวจว่า forecast เปิดเผย Actual ได้เมื่อใด และลองเปลี่ยนน้ำหนักพอร์ตโดยไม่เปลี่ยนข้อมูลต้นทาง

> Dashboard นี้เป็น frozen historical snapshot ไม่ใช่ข้อมูลตลาดสด ไม่มีการ train, inference หรือสร้าง forecast ใหม่ และไม่ใช่คำแนะนำการลงทุน

**Snapshot ปัจจุบัน:** Evaluation `12b9f92cbdcbb7816a767f8565bb004f3243b114480e5f3f316c497af4014e76`, Replay `0f6dad49e04b684df6d32d7abca7738fa8c06774c5e848476b62e8fa46a2c99a`, cutoff `2026-09-25`. Dashboard Guide ระบุ ZIP/checksum และ policy sidecar ที่ใช้อยู่

## เริ่มจาก Overview

1. เปิดหน้า Overview
2. เลือกคำถามที่ต้องการ: **01 · FORECAST** สำหรับดู prediction, **02 · PORTFOLIO RISK** สำหรับลองน้ำหนักพอร์ต หรือ **03 · EVIDENCE** สำหรับอ่านหลักฐานผลทดลอง
3. ตรวจ Evaluation ID, Replay ID และสถานะของ snapshot ที่ pin ไว้ก่อนนำตัวเลขไปอ้างอิง

วันที่, model, ticker และ view จะตามไปในหน้า Forecasts, Portfolio, Monitoring, Research และ Provenance เมื่อ route รองรับ selection นั้น

## อ่าน forecast ใน Replay

1. เปิด Forecasts จาก Overview หรือเมนูหลัก
2. ใช้ปุ่ม **วันก่อนหน้า** / **วันถัดไป**, ตัวเลือกวันที่ หรือ slider เพื่อเลือก XNYS session ที่บันทึกไว้
3. อ่าน Forecast RV5, สถานะ source, ช่วง target และวันที่เลือกจากกราฟ/ตาราง
4. ใช้ตาราง **เทียบ forecast ทั้ง 5 โมเดล** เพื่อเทียบ B0–B4 สำหรับวันและสินทรัพย์เดียวกัน เมื่อมีแถวที่บันทึกไว้ครบตามตัวเลือก
5. เปิด source record เพื่อดู Prediction ID, target end และค่าจากแถวที่เลือก

Replay อ่าน saved predictions เท่านั้น ปุ่มเปลี่ยนวันไม่ได้เรียกโมเดลมาทำนายอีกครั้ง

### ทำความเข้าใจ Actual, Error และ Pending

มุมมอง As-of ซ่อน Actual/Error เมื่อ target ยังไม่ครบวันซื้อขายที่กำหนด ระบบจะเปิดค่าได้เมื่อถึง target end และ source row เป็น Evaluable เท่านั้น

Pending คือแถวที่ไม่มี label ให้ประเมินใน snapshot นั้น การเลื่อน As-of หรือเปิด Retrospective ไม่สร้าง Actual/Error ให้แถว Pending และไม่ยืนยันว่า source data เคยพร้อมใช้งานจริง ณ วันจำลอง Retrospective อ่านค่า evaluation ที่บันทึกไว้หลัง eligibility

## ลอง Scenario A/B ใน Portfolio

1. จาก Replay เลือก **ใช้วันและโมเดลนี้ใน Portfolio** เพื่อเปิด Portfolio พร้อม selection เดิม
2. เปิด **Scenario Lab**; Scenario A และ B เริ่มด้วย 50/30/20 (SPY/IEF/GLD) และแก้แต่ละชุดได้
3. เปลี่ยนตัวเลขหรือ slider; น้ำหนักของแต่ละ Scenario ต้องรวมกันเป็น 100% จึงจะแสดงผลเปรียบเทียบ
4. อ่าน Scenario A risk, Scenario B risk และ **ส่วนต่าง · B − A** ของวันและ model ที่เลือก หน่วย pp คือ percentage points
5. กราฟด้านล่างใช้ fixed weights กับ covariance rows ที่บันทึกไว้ในแต่ละวัน; ใช้ตารางกราฟถ้าต้องการอ่านค่าโดยไม่พึ่งสีหรือเส้น

การคำนวณใช้ sqrt(wᵀΣw) จาก covariance ที่บันทึกไว้ของ model/date เดียวกัน เปลี่ยนน้ำหนักเท่านั้น ไม่มีการ optimize หรือคาดการณ์ผลตอบแทน

### Risk budget

Risk budget ไม่มีค่าเริ่มต้นที่ dashboard แนะนำ เว้นช่องว่างไว้ได้ หากต้องการกำหนดเกณฑ์ ให้กรอกความเสี่ยงรายปีเป็นเปอร์เซ็นต์แล้วอ่านจำนวนวันที่เกินเกณฑ์; ตัวเลขนี้เป็นจำนวนครั้งในข้อมูล ไม่ใช่ความน่าจะเป็น ใช้ปุ่ม **ล้างขีด** เพื่อลบค่า

หากผลรวม Scenario ไม่ครบ 100% ให้แก้ค่าน้ำหนักตามข้อความเตือน ระบบไม่ปรับสัดส่วนแทนผู้ใช้

## ตรวจ Monitoring, Research และ Provenance

- **Monitoring:** แยกแท็บ **Feature Drift** กับ **Champion–Challenger Policy**. Feature Drift แสดง W1/PSI ของการกระจาย feature; Policy แสดง ADWIN บน error ของ Champion ที่เสิร์ฟจริง, event การตัดสินใจ และ timeline รุ่นโมเดลจาก policy sidecar. Policy replay ที่ pin อยู่บันทึก mature errors 243 ครั้งต่อ ETF, 0 alerts และ 0 switches; นี่เป็นผลของ replay ชุดนี้เท่านั้น ไม่ได้ยืนยันว่าไม่มี drift หรือว่าข้อมูลพร้อมใช้จริง ณ วันจำลอง. ดู ID และ checksum ใน [Dashboard Guide](../../web/DASHBOARD_GUIDE.md)
- **Research:** อ่าน H1–H3 พร้อม effect, sample size, p-value, confidence interval และ scope แยกผล official ออกจาก descriptive metrics ตามป้ายกำกับ
- **Provenance:** เปิด disclosure เพื่ออ่าน source files, SHA-256, commit และข้อจำกัด; ปุ่ม copy ใช้คัดลอก ID หรือ hash ที่อยู่ข้างกัน
- **Guide:** เปิดอภิธานศัพท์เมื่อพบคำอย่าง Forward RV5, As-of, Evaluable, Pending หรือ percentage points

## คำที่ใช้ใน dashboard

| คำ | ความหมาย |
|---|---|
| Forward RV5 | ความผันผวนแบบ annualized ที่สรุปจาก 5 XNYS sessions ถัดไป ไม่ใช่ราคาหรือผลตอบแทน |
| As-of | มุมมองสาธิตการเปิดเผย label ตาม target-end rule จาก saved data |
| Evaluable | แถวที่ source มีผลจริงและผ่านเงื่อนไขให้ประเมิน |
| Pending | ไม่มี Actual/Error ที่ใช้ประเมินได้ใน frozen snapshot |
| pp | ส่วนต่างแบบ percentage points เช่น 5.0% − 4.5% = 0.5 pp |
| Frozen snapshot | ชุดข้อมูลย้อนหลังที่ pin ไว้; ไม่อัปเดตตามตลาดสด |

## ก่อนอ้างผลในรายงานหรือชั้นเรียน

ระบุ Evaluation ID, Replay ID, split, date, model, ticker และ As-of/Retrospective view ที่อ่าน ตรวจว่าแถวนั้น Evaluable หรือ Pending และแยก official result ออกจาก descriptive range ทุกครั้ง

Snapshot ปัจจุบันมี strict cutoff 2026-09-25; report approval ยัง pending และ point-in-time source availability ยังไม่ได้ยืนยัน ผลย้อนหลังไม่รับรอง performance ในอนาคต
