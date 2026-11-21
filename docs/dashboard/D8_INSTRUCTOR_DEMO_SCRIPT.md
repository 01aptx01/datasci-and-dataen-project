# D8 — Instructor Demo Script

**Duration:** 8–10 minutes  
**App:** Adaptive Portfolio Risk Lab · verified review snapshot  
**Purpose:** show how to read a saved forecast, wait for its label to mature, compare models, inspect recorded drift evidence, and change portfolio risk without fitting a model.

## Before presenting

- Open the dashboard at **Overview** and wait until the snapshot status says it is verified.
- Keep the displayed Evaluation ID and Replay ID visible when discussing evidence. The current pinned snapshot is Evaluation **82572c8417041976e1ce540d921e29a5f28c1d5d2a2d953a74c03582e7ca9be2** and Replay **3cbf81eb9242d8894d2f67f39065a17ff1ef55a2e098773aead915949ab11b12**.
- Use **โหมดนำเสนอ** to expand the workspace. Press Escape or the same button to leave.
- The guided tour picks a demonstration date from verified rows at runtime. Do not replace it with a hand-picked date if that date lacks a complete same-date comparison.
- Explain that the app reads a frozen **Simulated Historical Replay**. It does not fetch market data, run inference, train, or update the model.

## Run of show

| Time | Show | Say |
|---|---|---|
| 0:00–1:00 | Overview → **เริ่มเรียนรู้การทดลอง**. On stop 1, open Guide. | “งานนี้ทำนาย Forward RV5 หรือความผันผวนแบบ annualized ของ 5 วันซื้อขายถัดไป ไม่ได้ทำนายราคาหรือผลตอบแทน” |
| 1:00–2:30 | Guided stop 2 → Forecasts. Point to the selected XNYS date and the B0–B3 same-date table. | “นี่คือ prediction ที่บันทึกไว้ของทั้งสี่โมเดลสำหรับสินทรัพย์และวันเดียวกัน การเลื่อนวันเปลี่ยน observation ที่อ่าน ไม่ได้เรียกโมเดลให้ทำนายใหม่” |
| 2:30–3:30 | Guided stop 3 → change the as-of date to the saved target end date, then reveal Actual/Error. | “Actual ใช้ประเมินได้เมื่อ target ครบห้า sessions และแถวต้นทางเป็น EVALUABLE ตัวช่วย as-of นี้สาธิตกฎจาก snapshot; ไม่ได้พิสูจน์ว่าข้อมูลทุกแหล่งมีอยู่ ณ วันจำลอง และ Pending จะไม่เปิดเผยค่า” |
| 3:30–5:00 | Guided stop 4 → Models. Compare **All Test** and **Last 20 available sessions**; point out paired N and “descriptive only”. | “Official Test เป็นผล Stage 06 ที่ตรึงไว้ ส่วนช่วงย่อยเป็นค่าสรุปเชิงพรรณนาจากวันคู่กัน จำนวนตัวอย่างและค่า MAE/RMSE จึงเปลี่ยนได้ แต่ H1–H3, p-values และช่วงความเชื่อมั่นไม่เปลี่ยน” |
| 5:00–6:30 | Guided stop 5 → Drift. Show the conceptual flow, rolling MAE20, zero-alert count, then select a point or date in the source table. | “กราฟและ inspector อ่าน error กับ ADWIN fields ที่บันทึกจริง ชุดนี้มี 0 recorded alerts ซึ่งไม่ได้พิสูจน์ว่าไม่มี drift หรือ detector จะคงที่ในอนาคต ส่วน update/checkpoint เป็นขั้นของแนวคิด; handoff นี้ไม่มี event log มายืนยันสถานะรายวัน” |
| 6:30–7:45 | Guided stop 6 → Portfolio. Compare Default **50/30/20** with **60/20/20** and reset. | “เราใช้ forecast และ covariance แถวเดิม แล้วคำนวณ √(wᵀΣw) ใหม่เมื่อเปลี่ยนน้ำหนัก ไม่มีการ fit หรือเปลี่ยน prediction; ตัวเลขคือความผันผวนพอร์ตแบบ annualized ไม่ใช่ผลตอบแทน” |
| 7:45–9:00 | Open Research → show H1 Train-only and H2/H3 frozen Test evidence; then Provenance. | “ผลสถิติอ่านจาก Stage 06 และผูกกับ Evaluation/Replay ID ที่แสดง ข้อสรุปนี้อธิบายชุดทดลองย้อนหลัง ไม่รับรองผลในข้อมูลสดหรืออนาคต” |
| 9:00–10:00 | Return to the relevant source footer or Provenance file list for questions. | “แต่ละ claim ตรวจย้อนกลับได้จาก source file, split, selection, N และ run IDs ที่หน้าเว็บระบุ” |

## Interaction cues

- To move a saved session, use the date selector or First / Previous / Next / Last controls. Dates come from saved observations; they are not generated calendar days.
- To inspect a row, use the source disclosure below the chart. The source view keeps the selected date, model, prediction ID, target end and status together.
- For a drift observation, select a plotted point with mouse or keyboard, or open the chart data table and select its date. The inspector reports both stored error fields, **drift_detected**, **alert_record_present**, **adwin_delta**, **adwin_width**, and **adwin_estimation**.
- For a portfolio what-if, keep ticker forecasts and covariance fixed while changing only the allocation. Use **Reset to 50/30/20** after the comparison.
- If the guided tour cannot find a fully eligible example in a future snapshot, it says so. Continue with the independent evidence panels and do not imply that a missing record exists.

## Limits to state plainly

- The teaching as-of control is a derived eligibility view from saved records and the five-session target-end rule. It is not a verified historical data-vintage reconstruction.
- A zero ADWIN alert count describes the pinned Test timeline only.
- The published handoff does not include event-level B3 update/checkpoint records. No factual update markers are shown.
- Custom-range scores are descriptive; they are not new significance tests and do not replace the official Stage 06 results.
- Review approval is pending in this snapshot.

