# Prompts สำหรับทำ B4 ทีละ session

คัดลอก prompt ของ session ที่ต้องการไปใช้ทีละอัน แต่ละ prompt ให้อ่านกติกาการผ่านในแผนและบันทึกหลักฐานลง checklist ก่อนจบงาน

## Session 1 — ตรวจข้อมูลและตรึงวิธีทดลอง

```text
ทำ Session 1 ของแผน B4 ใน tasks/plan.md เท่านั้น อ่าน tasks/todo.md และปฏิบัติตามกติกา PASS/FAIL/BLOCKED ในแผน ตรวจ branch และรักษาการแก้ไขที่มีอยู่

1. สำรวจ CLI/API, config, runtime และ input จริงของ ingestion, features, labels, correlations, dataset/H1, Training, Replay, Evaluation และ Export ระบุคำสั่งจาก repo จริง พร้อม input/output และ dependencies ในแผน ถ้าขาด curated artifacts ให้ตรวจข้อมูลที่กู้ได้หรือสร้าง input ผ่าน pipeline เดิม บันทึก lineage และแยกผลรอบใหม่จาก ZIP อ้างอิง
2. ตรวจว่าสาม ETF ครบ ช่วง XNYS ตรงกัน และโหลด inputs/manifest ของ dataset ได้ ตรวจ keys, readiness, maturity, purge และข้อจำกัดเรื่อง source point-in-time จาก manifest
3. ตรึงชื่อ/เวอร์ชัน B4, OLS พร้อม intercept, Core Features 8 ตัวและลำดับเดิม, Train sample และ scaler เดียวกับ B2, cutoff, การจัดการ rank deficiency/ข้อมูลไม่พอ/forecast invalid และเกณฑ์ Validation ต่อ ETF ระบุรูปแบบเทียบ B4 กับ B1/B2/B3 และวิธีเก็บรอบ B0–B3 จาก input เดียวกัน บันทึกข้อกำหนด Git HEAD ของ exporter และตำแหน่ง run ใหม่

ก่อนผ่าน ตรวจหลักฐานว่าอ่านหรือสร้างข้อมูลจริงที่จำเป็นได้ และมี spec/คำสั่งที่ใช้ทำซ้ำได้ ให้สถานะ BLOCKED ถ้า input จริงยังไม่พร้อม แม้ spec จะเสร็จ บันทึกคำสั่ง ผล และ paths ใน tasks/todo.md แล้วสรุปสถานะ หยุดที่ Session 1
```

## Session 2 — Training และ Validation

```text
ทำ Session 2 เท่านั้น อ่าน tasks/plan.md และ tasks/todo.md ตรวจหลักฐานว่า Session 1 ผ่านก่อนลงมือ อิงทางเข้าจริงใน src/ml_training/README.md

1. ใช้ Train split, target, feature order และแถว eligible เดียวกับ B2 สำหรับ SPY, IEF และ GLD ตรวจ row keys, X, y และ scaler identity จาก Train เท่านั้น ฝึก OLS พร้อม intercept และ freeze โมเดล
2. จัดการ Train ไม่พอ, rank deficiency และค่าไม่ finite ตาม spec บันทึก coefficients, intercept, feature order, scaler identity, จำนวนและ fingerprint ของ Train keys, target_end_date ล่าสุดจาก label ที่ใช้จริง, versions, lineage และ checksum ใน artifact ที่ Replay โหลดได้
3. ตรวจ Validation ของ B4 แยกจากการเลือก SGD config รายงาน MAE/RMSE, counts, coverage และเหตุผลของ forecast invalid ต่อ ETF ทวนว่าการเลือก B2/B3 ยังใช้ objective และ sample rules เดิม

ก่อนผ่าน รันชุดตรวจ Training ที่เกี่ยวข้องและทดสอบโหลด artifact กลับมาเปรียบเทียบ forecast กับโมเดลที่ fit รันซ้ำด้วย input เดิม ตรวจผลเชิงตัวเลขตาม tolerance ที่บันทึกไว้และตรวจ cutoff ครบทุก ETF ต้องมี Validation evidence จริงก่อน PASS บันทึกคำสั่ง ผล และ artifacts ใน tasks/todo.md หยุดที่ Session 2
```

## Session 3 — Replay และ checkpoint

```text
ทำ Session 3 เท่านั้น อ่าน tasks/plan.md และ tasks/todo.md ตรวจ PASS และ artifact ของ Session 2 รวม checksum, feature order, cutoff และ versions ก่อนเริ่ม

1. เพิ่ม B4 ใน registry/order และตัวโหลด artifact เพิ่มทางทำนาย B4 โดยเฉพาะใน src/ml_replay/pipeline.py ตรวจว่ากิ่ง B3 ใช้กับ B3 เท่านั้น ใช้ schema เดิมและใส่ model version กับ last_training_target_end_date ของ B4
2. บันทึก expected/published/invalid/missing และ pending/evaluable ตาม semantics เดิม ทำนายก่อน label mature และประเมินเมื่อครบตามปฏิทินเท่านั้น ตรึง B4 และคง update/ADWIN ของ B3
3. ผูก fingerprint/checkpoint กับ suite, artifact และ config ทดสอบ run ต่อเนื่องเทียบ stop/resume และ checkpoint ที่ไม่เข้ากัน เทียบผล B0–B3 กับรอบอ้างอิงโดยใช้ input และ config ที่เทียบกันได้ แยก metadata ของแต่ละ run ตอนเทียบ

ก่อนผ่าน รันชุดตรวจ Replay ที่เกี่ยวข้อง ตรวจตัวอย่าง forecast B4 เทียบการคำนวณจาก artifact โดยตรง ตรวจ invalid/pending, no-update, resume และ B0–B3 parity บันทึกคำสั่ง ผล และตำแหน่ง outputs ใน tasks/todo.md หากตรวจไม่ครบให้ลงสถานะตามแผน หยุดที่ Session 3
```

## Session 4 — Evaluation และการเปรียบเทียบ

```text
ทำ Session 4 เท่านั้น อ่าน tasks/plan.md และ tasks/todo.md ตรวจ PASS ของ Session 3 และ Replay manifest ที่จะใช้

1. ทำให้ Stage 06 รองรับ B4 ใน audit, coverage, metrics ราย ETF/macro, rolling/period metrics และ portfolio risk ใช้วันและ ticker ตรงกันกับ correlations เดิม ให้ macro ให้น้ำหนัก ETF เท่ากัน
2. สร้างผลชุดร่วม B0–B4, ชุดอ้างอิง B0–B3 และคู่ B4–B2/B3/B1 ที่ match date/ticker/split และ mature/valid ตามกติกา รายงาน paired N, coverage, MAE/RMSE และนิยาม DeltaMAE ให้ทิศทางชัดเจน กำหนด artifact สำหรับส่งต่อ B4 comparisons แยกบทบาทจาก H2/H3
3. ตรวจว่า H1–H3 ใช้ข้อมูลและวิธีเดิม และเปรียบเทียบผลกับ baseline เมื่อ input/config เดียวกัน ระบุผล B4 บน Test เดิมเป็น retrospective

ก่อนผ่าน รันชุดตรวจ Evaluation และคำนวณตัวอย่าง MAE/RMSE, macro และ DeltaMAE ด้วยมือ ทดสอบ B4 invalid ที่ทำให้ชุดร่วมห้าโมเดลลดลง และ pending ที่ยังไม่มีคะแนน บันทึกผลตรวจและไฟล์ส่งต่อใน tasks/todo.md หยุดที่ Session 4
```

## Session 5 — Export, snapshot และ Dashboard

```text
ทำ Session 5 เท่านั้น อ่าน tasks/plan.md และ tasks/todo.md ตรวจ PASS ของ Session 4 และตรวจ schema/manifest ของผล B4 ก่อนเริ่ม

1. ตรวจจุดล็อก B0–B3 ใน exporter, prepare_snapshot, snapshot policy, TypeScript parser/labels/order และ tests เพิ่ม B4 ใน flow จริง เชื่อมข้อมูล B4 comparisons ตาม schema ที่ Session 4 กำหนด รักษาการ verify Git identity, SHA-256, member hashes และ row counts
2. ตรวจ policy ของ snapshot แต่ละเวอร์ชันกับ artifact ที่มันอ้างถึง ทดสอบข้อมูล B4 ที่ valid และ archive/policy ที่ hash หรือ identity ผิด ตรวจ drift ตาม source manifest ของ B3 และสถานะ B4 ที่เป็น static
3. ใช้คำสั่งใน web/README.md รัน build/test และเปิด preview ตรวจ Forecast, Replay รายวัน/รายเดือน, เปรียบเทียบโมเดล และ Portfolio เลือก B4 ตรวจวันที่ pending และวันที่ forecast ไม่ครบสาม ETF บันทึกชัดเจนว่าตรวจด้วยข้อมูลแบบใด

ก่อนผ่าน ต้องมี export/prepare ที่ผ่านสำหรับ snapshot ที่มี B4, มีหลักฐานการปฏิเสธข้อมูลผิด และตรวจหน้าเว็บได้จริง บันทึกคำสั่ง ผล และ artifacts ใน tasks/todo.md ระบุระดับการตรวจ และเก็บการยืนยัน dataset จริงไว้ Session 6 หยุดที่ Session 5
```

## Session 6 — รันจริงตั้งแต่ input ถึงหน้าเว็บ

```text
ทำ Session 6 เท่านั้น อ่าน tasks/plan.md และ tasks/todo.md ตรวจหลักฐาน PASS ของ Sessions 1–5 และ artifacts/inputs ที่ระบุไว้

1. ตรวจว่า Git HEAD ตรงกับ code identity ที่ exporter ต้องการ ระบุ Git revision, config hashes, input snapshot, data cutoff และ run IDs ของรอบจริง ใช้ผล B0–B3 อ้างอิงจาก input เดียวกันและแยก output paths จากผลเดิม
2. รันตามคำสั่งจาก Session 1: Dataset/H1 → Training → Replay → Evaluation → Export → prepare snapshot → build/preview ตรวจผลหลังแต่ละ stage ก่อนเริ่ม stage ถัดไป ตั้งแต่ lineage, feature order, frozen model, pending/coverage และ H1–H3 ถึง manifests, row counts และ checksum ของ ZIP/snapshot
3. เปิดเว็บด้วย snapshot จริง เลือก B4 และเทียบ forecast/metrics/portfolio อย่างน้อยหนึ่งตัวอย่างกับ artifact รวมวันที่ pending หรือข้อมูลไม่ครบถ้ามี สรุปผลราย ETF และ macro พร้อม N, coverage, paired results, baseline และข้อจำกัดของ Test ที่เคยเปิดดูและระดับหลักฐาน point-in-time

ก่อนผ่าน ทุก stage ต้องมีหลักฐานจากรอบจริงและหน้าเว็บต้องอ่าน artifact ชุดเดียวกัน หากติด input, runtime หรือ Git identity ให้บันทึก BLOCKED พร้อมคำสั่งและขั้นที่หยุด หากผลผิดเกณฑ์ให้แก้และตรวจซ้ำในขอบเขตเดิม บันทึกสถานะและหลักฐานใน tasks/todo.md
```
