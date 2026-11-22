# แผนเพิ่ม B4 ด้วย Core Features เดิม

B4 คือ HAR-style regression แบบเพิ่ม return features (HAR-X) จากข้อมูลรายวัน ใช้ OLS พร้อม intercept แยก SPY, IEF และ GLD เพื่อทำนาย `target_realized_vol_5d` ในหน่วย annualized decimal สำหรับวันซื้อขาย t+1 ถึง t+5 ตามสัญญาเดิม

## ข้อตกลงการทดลอง

- ใช้ PreparedDataset และ Core Features เดิมตามลำดับ `ret_1d_t`, `ret_lag_1d`, `ret_lag_2d`, `ret_trailing_5d`, `ret_trailing_20d`, `rv_5d`, `rv_20d`, `rv_60d` รวมถึง XNYS, readiness, maturity, split และ purge เดิม
- ใช้แถว Train เดียวกับ B2 สำหรับแต่ละ ETF ตรวจด้วยคีย์ (date, ticker) รวมถึงค่า X และ y ใช้ RobustScaler ที่ fit จาก Train ชุดเดียวกันและตรึงไว้ เพื่อให้ preprocessing ของ B2 และ B4 ตรงกัน
- B4 ใช้ OLS แบบไม่มี regularization ตรึงทั้ง estimator และ scaler หลังฝึก B4 เทียบ B2 จึงเป็นการเปรียบเทียบวิธี fit รวมถึงผลของ L2 ของ B2 ส่วน B4 เทียบ B3 ยังมีผลจากการอัปเดตออนไลน์ของ B3 ด้วย
- ใช้ชื่อในข้อมูลเบื้องต้น `HAR_X_OLS` และป้าย `B4 · HAR-X (OLS)` ให้ตรึงชื่อและเวอร์ชันจริงใน Session 1 ตรวจ forecast ติดลบหรือไม่ finite เป็น invalid พร้อม reason และ coverage ตาม policy เดิม
- ใช้ Validation ตรวจวิธีและความพร้อมของ B4 โดยแยกจาก objective ที่เลือกพารามิเตอร์ B2/B3 ตรึงวิธีก่อนเปิดผล Test ของ B4 การเปรียบเทียบบน Test เดิมเป็น retrospective การยืนยันบน holdout ใหม่เป็นงานทดลองแยก
- เก็บผลอ้างอิง B0–B3 และผลใหม่แยกด้วย run IDs ใช้ B0 ค่าเฉลี่ยและ B1 rolling RV20 ตามนิยามเดิม การอัปเดต B3 และ ADWIN ใช้กติกาเดิม การเปรียบเทียบ H1–H3 ใช้ sample rules และ hypotheses เดิม

## กติกาการผ่านแต่ละ session

เริ่มที่ Session 1 และใช้ prompt ตาม [prompts.md](prompts.md) หนึ่ง session ต่อครั้ง ตรวจหลักฐานของขั้นก่อนเริ่มขั้นถัดไป บันทึกใน [todo.md](todo.md) ว่ารันคำสั่งอะไร ได้ผลอย่างไร และหลักฐานอยู่ที่ไหน

- **PASS** เมื่อเกณฑ์บังคับครบและมีหลักฐานจากคำสั่งหรือ artifact จริง
- **FAIL** เมื่อผลผิดเกณฑ์ ให้แก้และรันการตรวจที่เกี่ยวข้องซ้ำใน session เดิม
- **BLOCKED** เมื่อข้อมูล เครื่องมือ หรือผลจากขั้นก่อนหน้าที่จำเป็นยังไม่มี ให้ระบุสิ่งที่ขาดและผลตรวจที่ทำได้แล้ว คง checkbox ของเกณฑ์ที่ยังตรวจไม่ได้ไว้
- การผ่านด้วย fixture ระบุได้เฉพาะเกณฑ์ด้านพฤติกรรมของโค้ด ผลทดลองจริงและการตรวจหน้าเว็บด้วยข้อมูลจริงอยู่ใน Session 6

## Session 1 — ตรวจ input และตรึงวิธีทดลอง

- ตรวจ branch, working tree, Python/Node และคำสั่งของแต่ละ stage ตรวจ config และ local artifacts สำหรับ curated prices, features, labels, rolling correlations, manifests และ H1 ที่ Evaluation ใช้
- ตรวจช่วงวัน XNYS, ครบสาม ETF, schema, lineage และ checksum ที่มีอยู่ จากการตรวจครั้งก่อน `data/` มีเพียงไฟล์ .gitkeep จึงต้องตรวจสถานะปัจจุบันและระบุแหล่ง input ที่กู้ได้หรือสร้างขึ้นใหม่ตามขั้นตอน ingestion → features/targets → dataset/H1 ก่อนนับว่าผ่าน gate ข้อมูล ZIP เดิมใช้เป็นผลอ้างอิง
- ตรึง model ID/name/version, สูตร, feature order, split/cutoff, criteria สำหรับ Train ไม่พอหรือ design matrix รวม intercept มี rank ต่ำกว่า 9 และเกณฑ์รับผล Validation เช่น fit สำเร็จครบ ETF และมีคู่ Validation ที่ประเมินได้ต่อ ETF พร้อมรายงาน coverage ใช้ Diagnostics แจ้ง ill conditioning แยกจาก rank deficiency
- กำหนดเวอร์ชัน bundle/replay/evaluation และแนวทาง snapshot เดิมกับ snapshot ใหม่ วางตำแหน่งไฟล์และคำสั่งสำหรับรัน B0–B3 อ้างอิงกับ B0–B4 จาก input ชุดเดียวกัน รวมถึงเวลาที่ต้องใช้ Git revision ที่ตรงกับ exporter
- **Gate:** โหลดหรือเตรียม input จริงได้และตรวจ manifest/keys ครบ มีวิธีทดลองที่ตรึงไว้ก่อนดู B4 Test และระบุคำสั่งกับ output ของแต่ละช่วง

## Session 2 — ฝึก B4 และตรวจ Validation

- ใช้ทางเข้า Training ตาม `src/ml_training/README.md` ต่อจากตัวเลือกแถวเดิม ให้ B4 ฝึกจาก Train ที่ eligible และใช้ scaler เดียวกับ B2 ต่อ ETF โดยจัดสถานะและการวัดผล B4 แยกจาก SGD search
- บันทึก intercept, coefficients, feature order, scaler identity, จำนวนและ fingerprint ของ Train keys, วัน `target_end_date` ล่าสุดของ Train ที่ใช้จริง, source lineage, รุ่นของ model/artifact และ SHA-256 ตามรูปแบบที่ Replay ตรวจได้
- เพิ่มการตรวจข้อมูลไม่พอ, rank deficiency, input ไม่ finite และ invalid forecasts ประเมิน Validation ต่อ ETF พร้อม MAE/RMSE, counts, coverage และ audit reasons ตามแผน
- **Gate:** ฝึกได้ครบสาม ETF, คีย์และค่า X/y ตรงกับ B2, cutoff ผ่าน, โหลด artifact แล้วได้ forecast ตรงกับโมเดลที่ fit และ rerun ให้ผลเชิงตัวเลขสอดคล้องใน tolerance ที่บันทึกไว้ ผลเลือก config ของ B2/B3 ยังเป็นไปตาม objective เดิม

## Session 3 — เชื่อม Replay

- อัปเดต model registry/order และ contract พร้อมตัวอ่าน bundle ระบุทางทำนาย B4 โดยเฉพาะใน `src/ml_replay/pipeline.py` กิ่ง else เดิมเป็นทางของ B3 จึงต้องตรวจจากพฤติกรรมจริงว่า B4 ได้ค่าจาก OLS artifact
- ใช้ prediction schema เดิมระบุ identity, model version และ Train label cutoff เพิ่ม B4 ใน expected coverage, failure records และ evaluation หลัง label mature ตัว B4 คง frozen ตลอด Replay และมีเฉพาะ B3 ที่เข้าทาง update และ ADWIN
- ผูก fingerprint และ checkpoint กับ suite/artifact version ทดสอบการ resume และการปฏิเสธการ resume จาก checkpoint ที่ไม่เข้ากันโดยให้ข้อความชัดเจน เก็บ output เดิมไว้ใน run ของมัน
- **Gate:** ผลทำนาย B4 ตรงกับ artifact, ค่าไม่ valid ถูกนับครบ, pending ไม่ถูกประเมินก่อนครบกำหนด, run ต่อเนื่องกับ resume ให้ผลเทียบกันได้เมื่อไม่นับ metadata เฉพาะการรัน และผล B0–B3 ตรง baseline เมื่อใช้ inputs และเงื่อนไขเดียวกัน

## Session 4 — ประเมินผลแบบจับคู่

- ขยายตัวอ่านและตัวตรวจชุดโมเดลของ Stage 06 ให้รู้จัก B4 พร้อม metric ราย ETF, macro แบบให้น้ำหนัก ETF เท่ากัน, coverage, rolling/period metrics และ portfolio risk ที่ใช้ correlations เดิม
- กำหนดผลสามชุดชัดเจน คือชุดร่วม B0–B4 ที่ forecast valid และ label mature, ชุดอ้างอิง B0–B3 บนรอบเดียวกัน และคู่ B4 กับ B2/B3/B1 ที่ match (prediction_date, ticker, split) รายงาน N, coverage, MAE/RMSE และทิศทาง DeltaMAE เช่น error ของ comparator ลบ error ของ B4
- เก็บ B4 comparisons เป็น retrospective แยกจาก H2/H3 ใช้ schema แยกหรือ schema ที่บอกคู่และทิศทางชัดเจน ตัวอ่าน pair เดิมตรึงอีกฝั่งเป็น B3 ระบุ artifact ที่ผู้ใช้และ dashboard จะอ่านใน Session 5
- **Gate:** มีตัวอย่างตรวจด้วยมือเรื่อง join, macro และทิศทาง delta, ทดสอบกรณี B4 invalid แล้วชุดร่วมลดแต่ชุดอ้างอิงเดิมยังตรวจได้, pending ไม่ปะปนคะแนน และ H1–H3 ตรงรอบอ้างอิงเมื่อ inputs/config เดียวกัน

## Session 5 — เชื่อม Export และ Dashboard

- เพิ่มการรองรับ B4 ใน `scripts/export_ml_results_handoff.py`, `scripts/web/prepare_snapshot.py`, policy, parser/type และลำดับตัวเลือกใน `web/src` ตรวจทั้งจุดที่ระบุสี่โมเดล, ชื่อคอลัมน์ของคู่เปรียบเทียบ และตัวนับที่ตรึงกับ snapshot เก่า
- ใช้ไฟล์และชื่อ artifact ที่ระบุได้ชัดเจน คงการตรวจ SHA-256, evaluation/replay IDs, schema และ row counts ของแต่ละ snapshot ให้สัมพันธ์กับข้อมูลจริง ส่วน drift ของ B3 ตรวจตาม manifest ของรอบนั้น รวมกรณีมี alert ถ้าข้อมูลจริงมี
- ตรวจ Forecast, Replay รายวัน/รายเดือน, เปรียบเทียบโมเดล และ Portfolio ของ B4 รวมวันที่ pending และวันที่ forecast ไม่ครบสาม ETF ระบุว่าสไลด์เดิมอ้างอิงผลชุดไหน การปรับสไลด์ให้โชว์ B4 เป็นขอบเขตแยก
- **Gate:** export และ prepare snapshot ผ่านบนชุดตรวจที่มี B4, validator ปฏิเสธ identity/checksum ผิด, build/test ผ่าน และเปิด preview ตรวจการเลือก B4 จริง ผลของ gate นี้ระบุระดับข้อมูลที่ใช้ตรวจ

## Session 6 — รันจริงและตรวจทั้งสาย

- ตรึง revision ตามที่ exporter ตรวจจาก Git HEAD และบันทึก input snapshot/config hashes กับ run IDs ใช้ output path ใหม่ รัน Dataset/H1 → Training → Replay → Evaluation → Export → prepare snapshot → build/preview จาก input ชุดเดียวกัน
- สร้าง policy ของ snapshot จาก archive และ manifest จริง ตรวจ join, row counts, checksums, coverage, duplicate keys, cutoff, frozen state, การเทียบ run อ้างอิง และ spot-check ผลจากไฟล์ต้นทางถึงหน้าจอ
- สรุปผล per ETF และ macro พร้อม N/coverage, คู่ B4–B2/B3/B1, ข้อจำกัดของ Test เดิม และหลักฐานการรัน ระบุระดับหลักฐานเรื่อง source point-in-time ตามที่ dataset manifest ยืนยันได้จริง
- **Gate:** เส้นทางจริงตั้งแต่ source inputs ถึง Dashboard ผ่านครบ เปิดหน้าเว็บแล้วเลือก B4 และตรวจผลกับ artifact ได้ หากข้อมูลจริงหรือข้อกำหนด Git ของ exporter ยังไม่พร้อม ให้ระบุ BLOCKED พร้อมสิ่งที่ขาด


